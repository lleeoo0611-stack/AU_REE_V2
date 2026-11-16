"""Seal existing pipeline outputs, compare cohorts and stress adopted item coding."""
import argparse,csv,json,math,shutil,statistics
from pathlib import Path
from au_ree_v2.analysis import write_csv,interval_mcda
from au_ree_v2.store import canonical,filehash
from au_ree_v2.cli import code_version

ROOT=Path(__file__).resolve().parents[1]
OLD=ROOT/'results/phase20-2026-11-05'
CODES=['R1','S1','T1','D1','I4','C1']


def rows(path):
    csv.field_size_limit(32*1024*1024)
    with Path(path).open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))


def phase22_diagnostics(out,receipt):
    """Summarise existing engine outputs; no alternative scoring or registry."""
    from collections import Counter,defaultdict
    import sqlite3
    native={r['entity_id'] for r in rows(out/'government_native_entities.csv')}
    pairs=rows(out/'government_identity_candidates.csv')
    pair_keys={frozenset((r['a'],r['b'])) for r in pairs}
    from au_ree_v2.store import digest
    links=json.loads((ROOT/'data/identity_links.json').read_text(encoding='utf8'))['links']
    reference=[]
    for r in rows(OLD/'entity_hierarchy.csv'):
        if r['relation']!='OFFICIAL_PROJECT_REFERENCES_MINERAL_DEPOSIT_NATIVE_ID':continue
        a,b=r['parent_id'],r['child_id']
        reference.append(dict(a=a,b=b,relation=r['relation'],source_key='SA_NATIVE_FOREIGN_ID',
            source_sha256=r['source_sha'],locator=r['locator'],generated=frozenset((a,b)) in pair_keys,
            reference_status='PREEXISTING_OFFICIAL_FOREIGN_ID_RELATION;USED_REGRESSION_NOT_INDEPENDENT_TEST'))
    for link in links:
        if link.get('status')=='CANDIDATE':continue
        a,b=('AU-'+digest([str(v[0]),str(v[1])])[:20] for v in (link['left'],link['right']))
        if a not in native or b not in native:continue
        reference.append(dict(a=a,b=b,relation=link['relation'],source_key=link['source_key'],
            source_sha256=link['source_sha256'],locator=link.get('locator'),
            generated=frozenset((a,b)) in pair_keys,
            reference_status='EXISTING_USED_DOCUMENT_SUPPORTED_LINK_NOT_INDEPENDENT_TEST'))
    if reference:write_csv(out/'pair_generation_reference.csv',reference,list(reference[0]))
    db=sqlite3.connect('file:'+str(ROOT/'work/phase5/canonical.sqlite')+'?mode=ro',uri=True);db.row_factory=sqlite3.Row
    claims=json.loads((ROOT/'data/claims.json').read_text(encoding='utf8'));bindings=[]
    originals={'kennedy_mre20240704','browns_wolverine_mre20250116'}
    for project in claims['projects']:
        for o in project.get('observations',[]):
            if o.get('source_key') not in originals:continue
            records=[dict(r) for r in db.execute('SELECT * FROM observations WHERE source_sha=? AND variable=? AND scope=? AND effective_date=?',
                (o['source_sha256'],o['variable'],o['scope'],o['effective_date']))]
            active=[r for r in records if json.loads(r['raw']).get('source_key')==o['source_key']]
            # Claims input and SQLite must agree; source-page inspection is a
            # separately declared single-agent review, not a classifier label.
            assert active and all(r['value']==o['value'] and r['unit']==o['unit'] and r['basis']==o['basis'] for r in active)
            bindings.append(dict(project_native_id=project['id'],variable=o['variable'],value=o['value'],unit=o['unit'],
                basis=o['basis'],effective_date=o['effective_date'],category=o.get('category'),scope=o['scope'],
                statement_id=o.get('statement_id'),source_sha256=o['source_sha256'],page=o['pdf_page'],locator=o['locator'],
                observation_ids=';'.join(sorted(r['obs_id'] for r in active)),statuses=';'.join(sorted({r['status'] for r in active})),
                evidence_type='DERIVED_OR_NORMALIZED' if o.get('transform') or o.get('transformation') or o['variable'] in ('normalized_resource_treo_ppm','reported_resource_magnet_ppm') and project['id']=='browns-range' else 'REPORTED',
                review='SAME_AGENT_ORIGINAL_TABLE_AND_RENDERED_PAGE;NOT_INDEPENDENT_GOLD'))
    write_csv(out/'source_cell_binding_check.csv',bindings,list(bindings[0]))
    quality=dict(candidate_reference='census_validation_v3.json: 25 records /24 native groups; single-agent prospective sealed test',
        used_reference='census_validation_v2.json: 52 records/46 groups, converted to used validation after tuning',
        pairing=dict(candidate_pairs=len(pairs),statuses=dict(Counter(r['status'] for r in pairs)),reference_relations=len(reference),
            recovered=sum(r['generated'] for r in reference),recall=sum(r['generated'] for r in reference)/len(reference) if reference else None,
            reference_limit='Used source-supported links with both endpoints in current government set; not exhaustive or independent'),
        identity=dict(new_automatic_identity_merges=0,legacy_unresolved_pairs=receipt['eligibility_audit']['unresolved_pairs'],
            false_merge_rate=None,false_split_rate=None,wrong_relation_rate=None,
            reason='No independent exhaustive identity truth; Kennedy native crosswalk remains candidate'),
        cell_binding=dict(rows=len(bindings),all_database_bindings_match=True,
            dimensions=['value','unit','REO basis','effective date','statement category','material/resource scope','original SHA/page'],
            independent_review=False,unique_new_reported_cells=12,rebound_existing_reported_cells=2,
            note='19 claim rows include transformations and repeated denominator cells; not19 new measurements'))
    (out/'quality_validation.json').write_text(canonical(quality)+'\n',encoding='utf8')
    rank=rows(out/'six_domain/ranking.csv');draws=rows(out/'six_domain/shared_draw_ranks.csv')
    groups=defaultdict(list)
    for r in draws:groups[r['scenario'],r['uncertainty'],r['method'],r['draw_id']].append(r)
    comparisons=defaultdict(list)
    for (scenario,family,method,draw),rr in groups.items():
        for a in rr:
            for b in rr:
                if a['project_id']>=b['project_id']:continue
                comparisons[scenario,family,method,a['project_id'],b['project_id']].append(float(a['rank'])-float(b['rank']))
    pairwise=[]
    for key,values in comparisons.items():
        pairwise.append(dict(zip(('scenario','uncertainty','method','a','b'),key),draws=len(values),
            a_above=sum(x<0 for x in values)/len(values),tied=sum(x==0 for x in values)/len(values),
            b_above=sum(x>0 for x in values)/len(values),interpretation='MODEL_FREQUENCY_NOT_SUCCESS_OR_UNKNOWN_DISCLOSURE_PROBABILITY'))
    write_csv(out/'shared_draw_pairwise_order.csv',pairwise,list(pairwise[0]))
    balance=[];complete={r['project_id'] for r in rows(out/'six_domain/matrix.csv')}
    census=defaultdict(list)
    for r in rows(out/'census.csv'):census[r['entity_id']].append(r)
    technical={r['project_id']:r for r in rows(out/'aim_c_technical_features.csv')}
    trace={}
    for r in rows(out/'value_trace.csv'):trace[r['entity_id'],r['criterion']]=r['raw_value']
    resource_ids={r['entity_id'] for r in rows(out/'cohort_coverage.csv') if r['resource_defined']=='1'}
    membership={r['entity_id']:r['canonical_id'] for r in rows(out/'canonical_membership.csv')}
    resource_values=defaultdict(list)
    for r in rows(out/'resources.csv'):
        if r['entity_id'] in resource_ids:resource_values[membership.get(r['entity_id'],r['entity_id'])].append(r)
    # Never sum independent statements/deposit scopes to make a Project total.
    inventories={pid:rr[0]['contained_treo_kt'] for pid,rr in resource_values.items()
        if len({(r['scope'],r['date'],r['source_sha'],r['contained_treo_kt']) for r in rr})==1}
    for r in rows(out/'disclosure_composite_matrix.csv'):
        pid=r['project_id'];meta=census[pid];tech=technical.get(pid,{})
        balance.append(dict(project_id=pid,project_name=r['project_name'],full_six=pid in complete,
            states=';'.join(sorted({x['state'] for x in meta if x['state']})),
            deposit_types=';'.join(sorted({x['deposit_type'] for x in meta if x['deposit_type']})),
            reported_inventory_kt_TREO=inventories.get(pid),development_ord=trace.get((pid,'D1')),
            primary_source_shas_n=len(json.loads(tech.get('source_shas','[]'))),
            scoped_engineering_studies=tech.get('engineering_study_cases_n'),
            interpretation='DESCRIPTIVE_SELECTED_GROUPS;NESTED_SCOPES;NOT_NATIONAL_REPRESENTATIVE_OR_CAUSAL'))
    write_csv(out/'cohort_balance.csv',balance,list(balance[0]))
    summary={}
    for label,flag in [('complete',True),('other_registered',False)]:
        rr=[r for r in balance if r['full_six']==flag];inv=[float(r['reported_inventory_kt_TREO']) for r in rr if r['reported_inventory_kt_TREO'] is not None]
        summary[label]=dict(n=len(rr),states=dict(Counter(r['states'] or 'UNKNOWN' for r in rr)),
            deposit_types=dict(Counter(r['deposit_types'] or 'UNKNOWN' for r in rr)),inventory_n=len(inv),
            inventory_median_kt=statistics.median(inv) if inv else None,
            development_known=sum(r['development_ord'] is not None for r in rr),
            primary_document_sources_median=statistics.median(r['primary_source_shas_n'] for r in rr))
    robustness=dict(shared_methods=['SAW','PROMETHEE_II','TOPSIS'],seed=20261102,draws_per_scenario_family=1000,
        maximum_binomial_Monte_Carlo_standard_error=math.sqrt(.25/1000),
        error_note='Simulation frequency sampling error only; not geological measurement uncertainty or success probability',
        unknown_disclosure='Bounds only; no distribution or midpoint assigned',
        rounding='Source reporting resolution only, not measurement uncertainty',
        leaders=[dict(scenario=r['scenario'],method=m,project=r['project_name']) for r in rank for m,col in [('SAW','saw_rank'),('PROMETHEE_II','promethee_rank'),('TOPSIS','topsis_rank')] if float(r[col])==1],
        independent_high_impact_recoding_completed=False,
        recoding_limit='Same-agent source review cannot satisfy independent Nolans/Goschen/Jupiter recoding; adopted coding retained',
        aim_c_balance=summary)
    (out/'research_analysis.json').write_text(canonical(robustness)+'\n',encoding='utf8');db.close()


def compare_cohorts(out,config):
    before={r['project_id']:r for r in rows(OLD/'six_domain/matrix.csv')}
    after={r['project_id']:r for r in rows(out/'six_domain/matrix.csv')}
    common=sorted(before.keys()&after.keys());delta=[]
    for pid in common:
        for code in CODES:
            if not math.isclose(float(before[pid][code]),float(after[pid][code]),rel_tol=1e-12,abs_tol=1e-12):
                raise ValueError('Common-cohort point utility changed: '+pid+' '+code)
    old_ranks=rows(OLD/'six_domain/ranking.csv');new_ranks=rows(out/'six_domain/ranking.csv')
    for scenario in config['scenarios']:
        a={r['project_id']:r for r in old_ranks if r['scenario']==scenario};b={r['project_id']:r for r in new_ranks if r['scenario']==scenario}
        for method,prefix in [('SAW','saw'),('TOPSIS','topsis'),('PROMETHEE_II','promethee')]:
            reversals=sum((float(a[x][prefix])-float(a[y][prefix]))*(float(b[x][prefix])-float(b[y][prefix])) < -1e-12
                          for i,x in enumerate(common) for y in common[i+1:])
            for pid in common:
                score_changed=not math.isclose(float(a[pid][prefix]),float(b[pid][prefix]),rel_tol=1e-12,abs_tol=1e-12)
                if method in ('SAW','TOPSIS') and score_changed:raise ValueError('Fixed-anchor score changed on common cohort')
                delta.append(dict(scenario=scenario,method=method,project_id=pid,before_score=a[pid][prefix],after_score=b[pid][prefix],
                    before_rank=a[pid][prefix+'_rank'],after_rank=b[pid][prefix+'_rank'],common_pair_reversals=reversals,
                    score_changed=score_changed,interpretation='Insertion displacement separate from common-pair reversal; PROMETHEE flow depends on comparison cohort'))
    write_csv(out/'cohort_rank_changes.csv',delta,list(delta[0]))
    return dict(before_n=len(before),after_n=len(after),common_ids=common,new_ids=sorted(after.keys()-before.keys()),
        exited_ids=sorted(before.keys()-after.keys()),common_point_utilities_unchanged=True,
        SAW_TOPSIS_common_scores_unchanged=True,evidence_update_fixed_old_cohort='Common point utilities identical; new evidence and population insertion effects separated')


def coding_stress(out,config):
    matrix=rows(out/'six_domain/matrix.csv');by_id={r['project_id']:i for i,r in enumerate(matrix)}
    original=[[float(r[c]) for c in CODES] for r in matrix];items=[r for r in rows(out/'disclosure_items.csv') if r['project_id'] in by_id]
    output=[]
    for scenario,dw in config['scenarios'].items():
        weights=[dw[next(c['domain'] for c in config['criteria'] if c['code']==code)] for code in CODES]
        baseline=interval_mcda([[(v,v) for v in rr] for rr in original],weights,config['promethee_threshold'])
        for item in items:
            actual=int(item['value']);alternative=1-actual;xx=[list(r) for r in original]
            xx[by_id[item['project_id']]][CODES.index('T1')]+=(alternative-actual)/7
            result=interval_mcda([[(v,v) for v in rr] for rr in xx],weights,config['promethee_threshold'])
            for method,rr in result.items():
                leaders={matrix[i]['project_id'] for i,r in enumerate(rr) if r['rank_best']==1}
                old={matrix[i]['project_id'] for i,r in enumerate(baseline[method]) if r['rank_best']==1}
                for project,r in zip(matrix,rr):
                    output.append(dict(scenario=scenario,method=method,changed_project_id=item['project_id'],item=item['item'],
                        assessment_id=item['assessment_id'],adopted_value=actual,counterfactual_value=alternative,
                        project_id=project['project_id'],**r,leader_set_changed=leaders!=old,
                        interpretation='One binary item stress, fixed denominator7; not recoding, measurement uncertainty, probability or confidence interval'))
    write_csv(out/'disclosure_coding_sensitivity.csv',output,list(output[0]))
    return dict(complete_groups=len(matrix),reviewed_positive_and_zero_items=len(items),
        leader_changing_variants=len({(r['scenario'],r['method'],r['changed_project_id'],r['item']) for r in output if r['leader_set_changed']}),
        rule='Each adopted 0/1 inverted individually; hypothetical stress only, original judgments retained')


def main():
    global OLD
    p=argparse.ArgumentParser();p.add_argument('--run',default='work/phase5/latest.json');p.add_argument('--out',default='results/phase21-2026-11-05');p.add_argument('--baseline');p.add_argument('--census-root',default='work/phase21/census');a=p.parse_args()
    if a.baseline:OLD=ROOT/a.baseline
    receipt=json.loads(Path(a.run).read_text(encoding='utf8'));source=Path(receipt['output_dir']);out=ROOT/a.out;out.mkdir(parents=True,exist_ok=True)
    if receipt['status']!='COMPLETED' or receipt['r_skipped']:raise ValueError('Require completed main CLI with R')
    if receipt['code']['content_sha256']!=code_version(ROOT)['content_sha256']:raise ValueError('Run source code differs from current code')
    for pattern in ('*.csv','disclosure_analysis.json','disclosure_baseline.json','configuration.json','snapshot_lock.json','eligibility_audit.json','summary.json'):
        for file in source.glob(pattern):shutil.copy2(file,out/file.name)
    for panel,result in receipt['r_results'].items():
        if result['status']!='COMPLETED':continue
        for file in (source/panel).glob('*'):
            if file.suffix not in ('.csv','.json','.svg'):continue
            if a.baseline and file.name in ('r_cache.json','r_cohort_cache.json'):continue
            target=out/panel/file.name;target.parent.mkdir(exist_ok=True);shutil.copy2(file,target)
    for file in (ROOT/a.census_root).glob('*'):shutil.copy2(file,out/file.name)
    config=json.loads((out/'configuration.json').read_text(encoding='utf8'))['research']
    change=compare_cohorts(out,config);stress=coding_stress(out,config)
    matrix=rows(out/'disclosure_composite_matrix.csv');gaps=[]
    for r in matrix:
        missing=[c for c in CODES if r[c]=='']
        gaps.append(dict(project_id=r['project_id'],project_name=r['project_name'],scope=r['scope'],missing_domain_count=len(missing),
            missing_criteria=';'.join(missing),full_six_point=not missing,interpretation='Evidence recovery priority, not independent Project approval or potential rank'))
    gaps.sort(key=lambda r:(r['missing_domain_count'],r['project_name']))
    write_csv(out/'six_domain_gap_priority.csv',gaps,list(gaps[0]))
    old_groups={r['project_id'] for r in rows(OLD/'disclosure_composite_matrix.csv')}
    if not old_groups<={r['project_id'] for r in matrix}:raise ValueError('Established group identity disappeared')
    before_path=OLD/'national_source_coverage.csv' if a.baseline else ROOT/'work/phase21/census_phase20/national_source_coverage.csv'
    before={r['source_key']:r for r in rows(before_path)}
    after=rows(out/'national_source_coverage.csv');comparisons=[]
    for r in after:
        if r['source_key'] not in before or not r['raw_records']:continue
        b=before[r['source_key']]
        comparisons.append(dict(source_key=r['source_key'],state=r['state'],before_sha256=b['source_sha256'],after_sha256=r['source_sha256'],
            previous_source_previous_rule=b['candidate_records'] if a.baseline else b['previous_rule_candidates'],previous_source_current_rule=(r['candidate_records'] if r['source_sha256']==b['source_sha256'] else None) if a.baseline else b['candidate_records'],
            current_source_previous_rule=r['previous_rule_candidates'],current_source_current_rule=r['candidate_records'],
            before_raw_records=b['raw_records'],after_raw_records=r['raw_records'],unit='SOURCE_RECORDS_INCLUDING_RELATED_ROLES_NOT_PROJECTS'))
    write_csv(out/'source_version_rule_comparison.csv',comparisons,list(comparisons[0]))
    result=dict(status='VERIFIED_WITH_DECLARED_LIMITS',code=receipt['code'],run_id=receipt['run_id'],cutoff=receipt['cutoff'],
        counts=dict(canonical_groups=receipt['canonical_projects_n'],resource_cases=receipt['resource_defined_n'],full_six=receipt['full_evidence_n'],
            point_disclosure=sum(r['T1']!='' for r in matrix),government_native_candidates=receipt['live_government_native_entities_n'],
            government_raw_source_records=receipt['live_government_raw_records_n'],source_snapshots=receipt['source_count'],entity_kinds=receipt['census_by_kind']),
        point_domain_coverage={c:sum(r[c]!='' for r in matrix) for c in CODES},cohort_change=change,coding_sensitivity=stress,
        formal_C1=receipt['eligibility_audit'],known_group_ids_preserved=True,scientific_definition_unchanged=True,
        new_complete_case_origin=('Existing-group recovery: Wolverine/Browns Range; Kennedy national discovery enters resource/composition ranking only' if a.baseline else 'Existing-group evidence recovery: Cummins Range and Nolans; no new national-discovery complete MCDA case'),
        barkly='Registered Project plus2source-bound prospects; source40Mt*2100ppm vsreported82kt conflict prevents R1; detailed prospectus403, unknown transparency retained',
        limits=['Single-agent source-field validation is not independent gold or national recall','ACT dedicated adapter and external territories incomplete',
            'Performance receipts distinguish current controlled measurement from earlier development runs','No error-induced or missing-value zero imputation'])
    (out/'evaluation.json').write_text(canonical(result)+'\n',encoding='utf8')
    if a.baseline:phase22_diagnostics(out,receipt)
    print(canonical(result))


if __name__=='__main__':main()
