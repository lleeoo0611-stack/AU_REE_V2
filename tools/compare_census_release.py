"""Compare two completed, published Census releases. No source acquisition or scoring."""
import argparse
import json
from collections import Counter
from pathlib import Path

from au_ree_v2.store import filehash
from au_ree_v2.tabular import read_csv, write_csv


CELL_KEY = ('project_id', 'column')
TRACE_KEYS = ('source_sha256', 'locator', 'scope', 'method', 'observation_ids', 'effective_date')
DELTA_FIELDS = ('project_id', 'project_name', 'column', 'change', 'field_family', 'reason',
                'old_state', 'new_state', 'old_value', 'new_value', 'old_status', 'new_status',
                *[prefix + '_' + key for prefix in ('old','new') for key in TRACE_KEYS],
                'old_rules_sha256', 'new_rules_sha256')
RANKS = ('saw_rank', 'promethee_rank', 'topsis_rank')
ROBUSTNESS = ('weight_uncertainty.csv', 'rounding_uncertainty.csv', 'function_sensitivity.csv',
              'cohort_sensitivity.csv', 'evidence_cohort_sensitivity.csv', 'method_comparison.csv')


def index(rows, keys):
    indexed = {}
    for row in rows:
        key = tuple(row[k] for k in keys)
        if key in indexed or any(not value for value in key):
            raise ValueError(f'Unstable or duplicate row key {keys}: {key}')
        indexed[key] = row
    return indexed


def required_csv(folder, name):
    path = folder/name
    if not path.is_file():
        raise FileNotFoundError(path)
    return read_csv(path)


def state(value, status):
    if bool(value) != (status['value_state']=='PRESENT'):
        raise ValueError(f"Census value disagrees with field_status: {status['project_id']} {status['column']}")
    if value:
        return 'PRESENT'
    if not status['status'] or status['value_state'] != 'BLANK':
        raise ValueError(f"Missing blank disposition: {status['project_id']} {status['column']}")
    return 'NOT_APPLICABLE' if status['status'].startswith('NOT_APPLICABLE_') else 'UNKNOWN'


def family(column):
    if column in ('開發商','未上市公司','ASX代碼'):
        return 'COMPANY'
    if column in ('礦床型態','礦床型態代碼','開發階段','開發階段代碼','開發階段類別','產品/產出'):
        return 'SCIENTIFIC_DESCRIPTION'
    if column in ('經度','緯度'):
        return 'SPATIAL_COORDINATE'
    if column.endswith(('_kt','_pct','_Mt','_t_per_year')) or column in (
            'NdPr蘊藏量_kt_需兩者皆公布','完整重稀土組合蘊藏量_kt_需8元素皆公布','元素總和/TREO'):
        return 'SCIENTIFIC_NUMERIC'
    return 'OTHER_CENSUS'


def transition(old, new, was, now):
    if was == now:
        return 'UPDATED' if old != new else 'EVIDENCE_OR_REASON_CHANGED'
    if now == 'PRESENT':
        return 'FILLED'
    if was == 'PRESENT':
        return 'WITHDRAWN'
    return 'REOPENED' if was == 'NOT_APPLICABLE' else 'RECLASSIFIED_NOT_APPLICABLE'


def release(folder):
    census = required_csv(folder,'REE project census.csv')
    if not census:
        raise ValueError(f'No published Census rows in {folder}')
    cols = tuple(census[0])
    population = index(census,('專案ID',))
    keyed = {(pid, c): row[c] for (pid,),row in population.items() for c in cols}
    status = index(required_csv(folder,'field_status.csv'),CELL_KEY)
    trace = index(required_csv(folder,'field_provenance.csv'),CELL_KEY)
    if set(keyed) != set(status) or set(keyed) != set(trace):
        raise ValueError(f'Status or provenance omits or adds Census cells in {folder}')
    if any(v != trace[k]['value'] for k,v in keyed.items()):
        raise ValueError(f'Provenance value differs from Census in {folder}')
    states = {k:state(v,status[k]) for k,v in keyed.items()}
    manifest = json.loads((folder/'census_release.json').read_bytes())
    if filehash(folder/'REE project census.csv') != manifest['census_csv_sha256']:
        raise ValueError(f'Published Census checksum differs from release receipt in {folder}')
    return dict(folder=folder, columns=cols, population=population, cells=keyed, status=status,
                trace=trace, states=states, manifest=manifest)


def cell_changes(old, new):
    if old['columns'] != new['columns']:
        raise ValueError(f"Ordered Census contract differs: {old['columns']} -> {new['columns']}")
    if old['population'].keys() != new['population'].keys():
        removed = sorted(old['population'].keys() - new['population'].keys())
        added = sorted(new['population'].keys() - old['population'].keys())
        raise ValueError(f'Population changed; a common denominator requires a crosswalk. Removed {removed}, added {added}')
    changes = []
    for k,x in old['cells'].items():
        pid,col = k
        y = new['cells'][k]
        a,b = old['trace'][k], new['trace'][k]
        sa,sb = old['status'][k],new['status'][k]
        if x == y and sa['status'] == sb['status'] and all(a[n] == b[n] for n in TRACE_KEYS):
            continue
        was,now = old['states'][k],new['states'][k]
        change = transition(x,y,was,now)
        cause = sb['findings'] if now != 'PRESENT' else (b['scope'] or b['locator'] or b['method'])
        out = dict(project_id=pid,project_name=new['population'][pid,]['專案名稱'],column=col,
                   change=change,field_family=family(col),reason=cause,old_state=was,new_state=now,
                   old_value=x,new_value=y,old_status=sa['status'],new_status=sb['status'])
        for prefix, trace, snap in [('old',a,old),('new',b,new)]:
            out.update({prefix+'_'+n: trace[n] for n in TRACE_KEYS})
            out[prefix+'_rules_sha256']=snap['manifest']['configuration_files']['summary_rules.json']
        changes.append(out)
    return changes


def records_delta(before, after, keys, fields):
    a,b = index(before,keys),index(after,keys)
    changed = []
    for k in sorted(a.keys() & b.keys()):
        fields_delta = {n: [a[k].get(n), b[k].get(n)] for n in fields if a[k].get(n) != b[k].get(n)}
        if fields_delta:
            changed.append(dict(key=k, changes=fields_delta))
    return dict(old_count=len(a), new_count=len(b), removed=sorted(a.keys()-b.keys()),
                added=sorted(b.keys()-a.keys()), changed=changed)


def panel_result(name, old, new):
    receipts = [s['manifest']['ranking_panels'].get(name,{}) for s in (old,new)]
    ranking, digests = [], []
    for snap, receipt in zip((old,new),receipts):
        if not receipt:
            ranking.append([]); digests.append({}); continue
        hashes = receipt['digests']
        path = snap['folder']/'MCDA'/name/'ranking.csv'
        if path.exists() and filehash(path) != hashes.get('ranking.csv'):
            raise ValueError(f'Ranking checksum differs from release receipt: {path}')
        if receipt['status']=='COMPLETED' and not path.is_file():
            raise FileNotFoundError(path)
        r = read_csv(path)
        if len({x['project_id'] for x in r}) != receipt['ranked_projects']:
            raise ValueError(f'Ranking cohort count differs from receipt: {name}')
        ranking.append(r); digests.append(hashes)
    a,b = receipts
    col = ('scenario','project_id')
    positions = records_delta(*ranking,col,RANKS)
    scores = records_delta(*ranking,col,('saw','topsis','promethee'))['changed']
    ha,hb=digests
    files = sorted(set(ha)|set(hb)|set(ROBUSTNESS)|{'matrix.csv','weights.csv','criteria.csv','ranking.csv'})
    compared = {f:('SAME' if ha[f]==hb[f] else 'CHANGED') if ha.get(f) and hb.get(f) else 'UNAVAILABLE'
                for f in files}
    old_ids,new_ids = ({r['project_id'] for r in roll} for roll in ranking)
    return dict(old_projects=len(old_ids),new_projects=len(new_ids), removed_projects=sorted(old_ids-new_ids),
                added_projects=sorted(new_ids-old_ids), old_status=a.get('status'),new_status=b.get('status'),
                criteria_before=a.get('criteria'),criteria_after=b.get('criteria') if a.get('criteria')!=b.get('criteria') else 'SAME',
                rank_changes=positions['changed'],added_scenario_projects=positions['added'],
                removed_scenario_projects=positions['removed'],score_changes=scores, comparison_by_file=compared,
                changed_or_unavailable_hashes={f:[ha.get(f),hb.get(f)] for f in files if compared[f]!='SAME'})


def followup_rows(old, new, earlier, notes):
    """Attach review notes to precisely the prior release's still-active cells."""
    prior = index(earlier, CELL_KEY)
    active = {key for key, row in prior.items()
              if row['class'] not in ('P1', 'P2', 'D2') and old['states'][key] == 'UNKNOWN'}
    reviewed = index(notes, CELL_KEY)
    if reviewed.keys() != active:
        raise ValueError('Follow-up review does not match the previous active Census cohort')
    rows = []
    outcomes = {'PRESENT': 'FILLED', 'NOT_APPLICABLE': 'RECLASSIFIED_NOT_APPLICABLE', 'UNKNOWN': 'HELD'}
    for key in sorted(active):
        record, note = prior[key], reviewed[key]
        if record['current_status'] != old['status'][key]['status'] or record['class'] != note['class']:
            raise ValueError(f'Follow-up baseline mismatch: {key}')
        if not all(note[field].strip() for field in ('finding', 'reviewed_evidence', 'reopen_if')):
            raise ValueError(f'Incomplete follow-up evidence: {key}')
        pid, column = key
        trace = new['trace'][key]
        rows.append(dict(project_id=pid, project_name=new['population'][pid,]['專案名稱'],
                         column=column, **{'class': record['class']},
                         outcome=outcomes[new['states'][key]], current_value=new['cells'][key],
                         previous_status=record['current_status'], current_status=new['status'][key]['status'],
                         source_sha256=trace['source_sha256'], locator=trace['locator'],
                         finding=note['finding'], reviewed_evidence=note['reviewed_evidence'],
                         reopen_if=note['reopen_if']))
    return rows


def compare(before, after, out, *, review_notes=None):
    old,new = (release(Path(x)) for x in (before,after))
    delta = cell_changes(old,new)
    def both(name):
        return [required_csv(x['folder'],name) for x in (old,new)]
    def count(rows,key):
        return dict(sorted(Counter(r[key] for r in rows).items()))
    ro,rn = both('resource_statement_observations.csv')
    resource_fields = ('statement_group_id','statement_id','source_sha256','scope','effective_date','category',
                       'cutoff','reporting_standard','selected_for_census','variable','value','unit','basis',
                       'material_basis','locator','physical_page','transform_version')
    resources=records_delta(ro,rn,('project_id','observation_id'),resource_fields)
    resources['selected_groups']=[len({r['statement_group_id'] for r in roll if r['selected_for_census']=='1'})
                                  for roll in (ro,rn)]
    resources['complete_treo_projects']=[sum(all(r.get(c) for c in ('礦石蘊藏量_Mt','TREO品位_pct','總TREO蘊藏量_kt'))
                                              for r in x['population'].values()) for x in (old,new)]
    resources['scope_decisions']=records_delta(*both('resource_scope_selection.csv'),('project_id',),
                                              ('source_sha256','reason','scope','alternative_scopes'))
    panels = sorted(set(old['manifest']['ranking_panels']) | set(new['manifest']['ranking_panels']))
    named = {name:panel_result(name,old,new) for name in panels}
    gis=[]
    for key in ('census_gis_sensitivity.csv','census_gis_rank_sensitivity.csv'):
        first,second=both(key)
        gis.append(dict(file=key,old_status=count(first,'status'), new_status=count(second,'status'),
                        byte_identical=filehash(old['folder']/key)==filehash(new['folder']/key)))
    out=Path(out)
    if out.resolve() == old['folder'].resolve():
        raise ValueError('Write the comparison to the new release or a separate directory to preserve the baseline')
    out.mkdir(parents=True,exist_ok=True)
    write_csv(out/'coverage_delta.csv',delta,DELTA_FIELDS)
    summary=dict(census=dict(projects=len(new['population']), columns=len(new['columns']), cells=len(new['cells']),
                             counts=[dict(Counter(x['states'].values())) for x in (old,new)],
                             unknown_by_reason=[dict(Counter(x['status'][k]['status'] for k,v in x['states'].items()
                                                     if v=='UNKNOWN')) for x in (old,new)],
                             changes=count(delta,'change'), fills_by_family=count([r for r in delta if r['change']=='FILLED'],'field_family'),
                             transition_counts=dict(Counter(r['old_state']+' -> '+r['new_state'] for r in delta))),
                 releases=[dict(run_id=x['manifest']['run_id'], cutoff=x['manifest']['cutoff'],
                               code=x['manifest']['code'],mode=x['manifest']['mode'],
                               configuration_sha256=x['manifest']['configuration_sha256'], claims_sha256=x['manifest']['claims_sha256'],
                               release_manifest_sha256=filehash(x['folder']/'census_release.json'),
                               methods=x['manifest']['methods'],monte_carlo=x['manifest']['monte_carlo']) for x in (old,new)],
                 resource=resources,panels=named,
                 panel_membership=records_delta(*both('mcda_panel_decisions.csv'),('panel','project_id'),
                                               ('canonical_project_id','status','formal_c1_status')),
                 criteria_lineage=records_delta(*both('mcda_criterion_lineage.csv'),('panel','project_id','criterion'),
                                               ('canonical_project_id','score','scope','case_id','evidence_status','evidence')),
                 spatial=gis,
                 panel_hash_basis='Each ranking.csv rehashed; unpublished matrices and sensitivity tables compared using their release manifest SHA-256. Missing digests mean unavailable.')
    if review_notes is not None:
        rows = followup_rows(old, new, required_csv(old['folder'], 'gap_review.csv'), read_csv(review_notes))
        fields = ('project_id', 'project_name', 'column', 'class', 'outcome', 'current_value',
                  'previous_status', 'current_status', 'source_sha256', 'locator', 'finding',
                  'reviewed_evidence', 'reopen_if')
        write_csv(out/'followup_review.csv', rows, fields)
        summary['followup'] = dict(active_at_baseline=len(rows), outcomes=count(rows, 'outcome'),
                                   remaining_by_class=count([r for r in rows if r['outcome']=='HELD'], 'class'))
    (out/'research_comparison.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    return summary


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('before',type=Path); parser.add_argument('after',type=Path)
    parser.add_argument('--out',required=True,type=Path)
    parser.add_argument('--review-notes', type=Path, help='Case notes for all previously active cells; a published followup_review.csv can be replayed.')
    args=parser.parse_args()
    print(json.dumps(compare(args.before,args.after,args.out,review_notes=args.review_notes)['census'],ensure_ascii=False))
