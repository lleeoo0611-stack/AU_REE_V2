"""Match archived candidates offline; emit validated review drafts, never edit CSVs."""
import argparse
from collections import Counter
import copy,csv,json,sqlite3,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from au_ree_v2.candidate_table_matcher import *
from au_ree_v2.store import filehash


def read_csv(path):
    with path.open(encoding='utf-8-sig',newline='') as handle:return list(csv.DictReader(handle))


def write_csv(path,rows,columns):
    with path.open('w',encoding='utf-8-sig',newline='') as handle:
        writer=csv.DictWriter(handle,columns);writer.writeheader();writer.writerows(rows)


def run(candidate_root,before,out,database=None):
    import pymupdf
    from au_ree_v2.asx_validation import validate_reviews
    from au_ree_v2.archived_element_additions import verify_single_oxide
    candidate_root,before,out=map(Path,(candidate_root,before,out))
    if out.exists():raise ValueError('MATCH_REQUIRES_FRESH_OUTPUT')
    out.mkdir(parents=True)
    table_rows=read_csv(before/'專案總表.csv');trace=read_csv(before/'field_provenance.csv')
    ledger_path=ROOT/'config/asx_source_reviews.json'
    ledger=json.loads(ledger_path.read_text('utf8'));draft=copy.deepcopy(ledger)
    asset_cfg=json.loads((ROOT/'config/asx_local_asset_roots.json').read_text('utf8'))
    roots={k:(ROOT/v).resolve() for k,v in asset_cfg['roots'].items()}
    projects=[dict(entity_id=r['專案ID'],name=r['專案名稱'].split(' — ')[0],aliases=[r['專案名稱']]) for r in table_rows]
    pages=[(p,json.loads(p.read_text('utf8'))) for p in sorted(candidate_root.glob('*/page-*.json'))]
    queue=[];corroborations=[];accepted=[];scanned=[];per_project=[]
    original_hashes={p.name:filehash(p) for p in before.iterdir() if p.is_file()}
    base_ledger_hash=filehash(ledger_path)
    for row in table_rows:
        if not row['礦石蘊藏量_Mt'] or not row['總TREO蘊藏量_kt']:continue
        missing=[o for o in OXIDES if not next(v for k,v in row.items() if k.startswith(o+'_'))]
        if not missing:continue
        pid=row['專案ID'];ore_trace=[t for t in trace if t['project_id']==pid and t['column']=='礦石蘊藏量_Mt']
        if len(ore_trace)!=1:continue
        sha=ore_trace[0]['source_sha256']
        related={r['source_sha256'] for r in ledger['reviews'] if r['project_id']==pid}|{sha}
        own_pages=[(p,data) for p,data in pages if data['source_sha256'] in related]
        error=None;review=None
        try:review,_,observations=selected_review(row,trace,ledger['reviews'])
        except ValueError as exc:error=str(exc)
        project_before=len(accepted);queue_before=len(queue)
        for path,data in own_pages:
            for candidate in data['tables']:
                identity=dict(project= row['專案名稱'],project_id=pid,source_sha256=data['source_sha256'],page=data['physical_page'],table_index=candidate['index'])
                scanned.append(identity)
                values=json.dumps(candidate['cells'],ensure_ascii=False,separators=(',',':'))
                try:
                    if data['source_sha256']!=sha:raise ValueError('CROSS_DOCUMENT_MRE_PROOF_REQUIRED')
                    # Already independently reviewed canonical Dubbo 2017 resource.
                    if pid=='AU-2cfeb25aefee0c4f95fb' and data['physical_page']==26:
                        columns,_=infer_columns(candidate['cells'])
                        match=match_rows(candidate['cells'],columns,row['礦石蘊藏量_Mt'],7400)
                        y=columns.get('Y2O3');token=candidate['cells'][match['row']][y['column']] if y else None
                        if not y or header_unit(y['header'])!='ppm' or numeric(token)!=Decimal(1400):raise ValueError('DUBBO_NATIVE_VALUE_CONFLICT')
                        additions=json.loads((ROOT/'config/asx_archived_element_additions.json').read_text('utf8'))
                        entry=next(e for e in additions['reviews'] if e['project_id']==pid)
                        dbpath=Path(database) if database else roots['canonical']/'work/phase22/verified-performance-v3/isolated-round-0/after/canonical.sqlite'
                        with sqlite3.connect(dbpath.resolve().as_uri()+'?mode=ro',uri=True) as db:
                            db.row_factory=sqlite3.Row
                            verify_single_oxide(row,trace,db,entry,roots)
                        corroborations.append(dict(**identity,oxide='Y2O3',original_token=str(token),unit='ppm',value_kt=float(numeric(row['礦石蘊藏量_Mt'])*numeric(token)*Decimal('.001')),method='AUTO_MATCHED_SAME_SCOPE_TABLE',row=match['row'],column=y['column'],table_bbox=candidate['bbox'],tolerances=match,validation='EXISTING_VERIFY_SINGLE_OXIDE_PASSED',new_cells=0))
                        continue
                    if error:raise ValueError(error)
                    ore,grade=observations['ore_mt'],observations['grade']
                    binding=ore['cell_binding']
                    if data['physical_page']!=binding['page']:raise ValueError('CANDIDATE_OUTSIDE_SELECTED_RESOURCE_PAGE')
                    columns,_=infer_columns(candidate['cells'])
                    if any('ce2o3' in compact(v) or 'ceo23' in compact(v) for cellrow in candidate['cells'] for v in cellrow):raise ValueError('NONCANONICAL_CE2O3_BASIS')
                    if not any(o in columns for o in missing):raise ValueError('NO_MISSING_CANONICAL_OXIDE_COLUMN')
                    # Unit evidence is mandatory before numeric comparison.
                    ore_header=compact(columns.get('ore',{}).get('header',''))
                    source_ore_unit=ore.get('original_unit',ore['unit'])
                    if (source_ore_unit=='Mt' and not any(u in ore_header for u in ('(mt)','million'))) or (source_ore_unit=='kt' and not any(u in ore_header for u in ('(kt)','000'))) or (source_ore_unit=='t' and not any(u in ore_header for u in ('(t)','tonnes'))):raise ValueError('ORE_UNIT_UNKNOWN_OR_CONFLICT')
                    if header_unit(columns.get('grade',{}).get('header',''))!=grade.get('original_unit',grade['unit']):raise ValueError('GRADE_UNIT_MISMATCH')
                    match=match_rows(candidate['cells'],columns,numeric(ore.get('original_token',ore['value'])),numeric(grade.get('original_token',grade['value'])),row_label=binding['row_label'])
                    asset=(roots[review['asset_set']]/review['path']).resolve()
                    if not asset.is_relative_to(roots[review['asset_set']]) or filehash(asset)!=sha:raise ValueError('SOURCE_SHA_MISMATCH')
                    with pymupdf.open(asset) as doc:
                        page=doc[data['physical_page']-1]
                        live=page.find_tables().tables[candidate['index']]
                        if live.extract()!=candidate['cells'] or list(live.bbox)!=candidate['bbox']:raise ValueError('CANDIDATE_SNAPSHOT_DIFFERS_FROM_SOURCE')
                        new=[]
                        for oxide in missing:
                            if oxide not in columns:continue
                            col=columns[oxide];token=candidate['cells'][match['row']][col['column']]
                            if token is None or str(token).strip()=='':continue
                            unit=header_unit(col['header'])
                            if unit not in ('ppm','%','kg/t','t','kt'):raise ValueError('UNIT_UNKNOWN_OR_CONFLICT:'+unit)
                            observation=make_native_observation(page,live,match['row'],col['column'],oxide,token,unit,review,ore)
                            observation['candidate_match']['tolerances']=match
                            new.append(observation)
                    if not new:raise ValueError('NO_INDIVIDUAL_OXIDE_VALUE_ON_SELECTED_ROW')
                    replacement=copy.deepcopy(review)
                    replacement['observations']+=new
                    replacement['candidate_table_match_method']='AUTO_MATCHED_SAME_SCOPE_TABLE'
                    grades={o['basis']:o['value'] for o in replacement['observations'] if o['basis'] in OXIDES}
                    widths={o['basis']:o.get('rounding_half_width',float(rounding_half_width(o.get('original_token',o['value']))*FACTORS.get(o.get('original_unit',o['unit']),Decimal(1)))) for o in replacement['observations'] if o['basis'] in OXIDES}
                    closure=closure_check(grades,widths,float(numeric(grade.get('original_token',grade['value']))*FACTORS[grade.get('original_unit',grade['unit'])]),rounding_half_width(grade.get('original_token',grade['value']))*FACTORS[grade.get('original_unit',grade['unit'])])
                    if closure:replacement['oxide_sum_tolerance_ppm']=float(closure['tolerance_ppm'])
                    candidate_ledger=out/'validation-input.json'
                    candidate_ledger.write_text(json.dumps(dict(version='asx-source-review-v2',acquired_through=ledger['acquired_through'],reviews=[replacement]),ensure_ascii=False,indent=2)+'\n',encoding='utf8')
                    validate_reviews(candidate_ledger,roots,projects,cutoff='2026-11-05')
                    accepted.append(dict(**identity,review_id=review['review_id'],observations=new,closure=closure))
                    for index,old in enumerate(draft['reviews']):
                        if old['review_id']==review['review_id']:draft['reviews'][index]=replacement
                except (ValueError,KeyError,IndexError,TypeError) as exc:
                    queue.append(dict(**identity,condition=str(exc),candidate_values=values))
        per_project.append(dict(project_id=pid,project=row['專案名稱'],missing_individual_oxides=len(missing),validated_tables=len(accepted)-project_before,review_queue=len(queue)-queue_before))
    # Multiple independently passing tables for one resource are ambiguous. Never
    # silently choose last. Keep every candidate in the review queue instead.
    counts=Counter(a['project_id'] for a in accepted)
    for pid,count in counts.items():
        if count>1:
            for a in accepted:
                if a['project_id']==pid:queue.append(dict(**{k:a[k] for k in ('project','project_id','source_sha256','page','table_index')},condition='MULTIPLE_ACCEPTABLE_TABLES',candidate_values=json.dumps(a['observations'],ensure_ascii=False)))
            draft['reviews']=[copy.deepcopy(next(o for o in ledger['reviews'] if o['review_id']==r['review_id'])) if r['project_id']==pid else r for r in draft['reviews']]
    accepted=[a for a in accepted if counts[a['project_id']]==1]
    if filehash(ledger_path)!=base_ledger_hash or any(filehash(before/name)!=h for name,h in original_hashes.items()):raise ValueError('MATCH_INPUT_CHANGED')
    (out/'review_drafts.json').write_text(json.dumps(dict(method='AUTO_MATCHED_SAME_SCOPE_TABLE',reviews=accepted,corroborations=corroborations),ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    (out/'validated_source_reviews.json').write_text(json.dumps(draft,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    write_csv(out/'review_queue.csv',queue,['project','project_id','source_sha256','page','table_index','condition','candidate_values'])
    summary=dict(version='candidate-table-match-v1',network_requests=0,projects=per_project,candidate_pages=len(pages),scanned_tables=len(scanned),validated_tables=len(accepted),validated_new_observations=sum(len(a['observations']) for a in accepted),corroborated_existing_cells=len(corroborations),review_queue=len(queue),rejection_reasons=dict(sorted(Counter(q['condition'] for q in queue).items())),source_ledger_sha256=base_ledger_hash,baseline_hashes=original_hashes,limitation='Validated review drafts only; no CSV edits. Run the existing source-review exporter and compare original values/provenance before publishing.')
    (out/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    return summary


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidates',type=Path,default=ROOT/'work/attachment-elements-20261111/extraction-v2')
    parser.add_argument('--before',type=Path,default=ROOT/'results/asx-current')
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--database',type=Path)
    args=parser.parse_args()
    def offline(event,args):
        if event in ('socket.connect','socket.getaddrinfo'):raise PermissionError('MATCH_OFFLINE_ONLY')
    sys.addaudithook(offline)
    print(json.dumps(run(args.candidates,args.before,args.out,args.database),ensure_ascii=False,indent=2))
