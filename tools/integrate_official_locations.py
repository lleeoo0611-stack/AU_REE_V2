"""Stage approved government locations, or reproduce the baseline byte-for-byte."""
import argparse
import csv
import hashlib
import json
import shutil
import sys
from pathlib import Path
REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO/'src'))
from au_ree_v2.official_location_adapters import (DATASETS,proposed_decisions,decision_for,
 acquire_dataset,build_location_candidates,match_project,validate_candidate_pair,verify_acquisition_snapshots,native_state,load_project_context)
from au_ree_v2.iteration_review import audit_summary
from au_ree_v2.blank_classification import load_blank_rules,classify_blanks

BASE_FILES=('專案總表.csv','field_provenance.csv','missing_fields.csv','census_inventory.csv','summary.json','audit.json')
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def read_csv(path):
    with Path(path).open(encoding='utf-8-sig',newline='') as f:
        r=csv.DictReader(f);rows=list(r);return r.fieldnames,rows
def write_csv(path,fields,rows):
    with Path(path).open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
def run(before,out,decisions_path=None,acquisitions_path=None,acquire=False,references_path=None,aliases_path=None):
    before=Path(before);out=Path(out)
    if out.exists():raise ValueError('LOCATION_FRESH_OUTPUT_REQUIRED')
    decisions=json.loads(Path(decisions_path).read_text('utf-8-sig')) if decisions_path else {'decisions':proposed_decisions()}
    enabled=[k for k in DATASETS if decision_for(k,decisions)]
    out.mkdir(parents=True);projection=out/'projection';projection.mkdir()
    for name in sorted(set(BASE_FILES) | set(json.loads((before/'summary.json').read_text('utf8'))['output_hashes'])):
        shutil.copyfile(before/name,projection/name)
    cols,rows=read_csv(before/'專案總表.csv');pcols,provenance=read_csv(before/'field_provenance.csv');mcols,missing=read_csv(before/'missing_fields.csv')
    acquisitions=[];queue=[];new=[]
    references,alias_map=load_project_context(references_path,aliases_path) if enabled else ({},{})
    # No approval means not even opening a supplied acquisition cache.
    if enabled:
        if acquisitions_path:
            acquisitions=json.loads(Path(acquisitions_path).read_text('utf-8-sig'))
            acquisitions=[verify_acquisition_snapshots(result,decisions) for result in acquisitions]
        elif acquire:
            for dataset in enabled:
                if DATASETS[dataset]['kind']=='wfs_linked':
                    base=next((x for x in acquisitions if x['dataset']=='SA_SARIG' and x['status']=='COMPLETE'),None)
                    ids=[x['feature'].get('properties',{}).get('MINERAL_DEPOSIT_NO') for x in base['features']] if base else []
                    if not ids:
                        queue.append(dict(project_id='',reason='SA_PROJECTS_REQUIRES_REE_DEPOSIT_LINKS',candidates=dataset));continue
                else:ids=[]
                acquisitions.append(acquire_dataset(dataset,decisions,out/'snapshots',linked_deposit_ids=ids))
            (out/'acquisitions.json').write_text(json.dumps(acquisitions,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
        else:queue.append(dict(project_id='',reason='APPROVED_BUT_NO_SNAPSHOTS;USE_ACQUIRE_EXPLICITLY',candidates=''))
    candidates,rejected=build_location_candidates(acquisitions,decisions)
    for reject in rejected:queue.append(dict(project_id='',reason=reject['reason'],candidates=json.dumps(reject,ensure_ascii=False)))
    for row in rows:
        if row['緯度'] or row['經度']:continue
        state=native_state(row['州省地區'])
        if state in ('VIC','TAS'):
            queue.append(dict(project_id=row['專案ID'],reason='NO_DOCUMENTED_ENDPOINT_VIC_TAS',candidates=''));continue
        reference=references.get(row['專案ID']);alias_proof=alias_map.get(row['專案ID'])
        aliases=alias_proof['aliases'] if alias_proof else []
        match_args=dict(aliases=aliases,reference=(reference['longitude'],reference['latitude']) if reference else None,max_distance_m=reference['max_distance_m'] if reference else None)
        primary=[c for c in candidates if c['dataset']!='GA_OZMIN']
        result=match_project(row,primary,**match_args)
        pool=primary
        if result['status']=='NO_EXACT_NAME_MATCH':
            pool=[c for c in candidates if c['dataset']=='GA_OZMIN'];result=match_project(row,pool,**match_args)
        if result['status']!='AUTO_MATCHED_OFFICIAL_POINT':
            queue.append(dict(project_id=row['專案ID'],reason=result['status'] if enabled else 'DATASET_NOT_APPROVED',candidates=json.dumps(result['candidates'],ensure_ascii=False)));continue
        c=result['candidates'][0]
        for attr in validate_candidate_pair(row,c,decisions,pool,aliases=aliases,verified_reference=reference):
            if alias_proof:
                scope=json.loads(attr['scope']);scope['exact_alias_proof']={k:v for k,v in alias_proof.items() if k!='source_path'};attr['scope']=json.dumps(scope,ensure_ascii=False,sort_keys=True)
            column=attr['column'];value=format(attr['value'],'.10g');row[column]=value
            trace={k:'' for k in pcols};trace.update(project_id=row['專案ID'],column=column,value=value,
                source_sha256=attr['source_sha'],source_url=attr['source_url'],locator=attr['locator'],method=attr['method'],scope=attr['scope'],
                observation_ids='[]',review_ids=json.dumps([attr['decision_id']]),review_methods='["AUTO_MATCHED_OFFICIAL_POINT"]',
                acquired_through=c['acquired_at'],publication_date_role='DATASET_VERSION_UNKNOWN' if not c['source_version'] else 'DATASET_VERSION_NOT_MRE',
                source_kind='GOVERNMENT_SPATIAL_CATALOGUE',resource_effective_date_unknown='True',public_release_date_unknown=str(not bool(c['source_version'])))
            provenance.append(trace);new.append(dict(project_id=row['專案ID'],column=column,old_value='',new_value=value,decision_id=attr['decision_id']))
    if new:
        changed={(x['project_id'],x['column']) for x in new};missing=[x for x in missing if (x['project_id'],x['column']) not in changed]
        summary=json.loads((projection/'summary.json').read_text('utf8'))
        summary['filled_counts']={c:sum(bool(r[c]) for r in rows) for c in cols}
        summary['blank_coverage']=classify_blanks(rows,missing,provenance,load_blank_rules(REPO/'config/blank_classification_legacy53.json'))
        write_csv(projection/'專案總表.csv',cols,rows);write_csv(projection/'field_provenance.csv',pcols,provenance);write_csv(projection/'missing_fields.csv',mcols,missing)
        summary['output_hashes']={n:sha(projection/n) for n in summary['output_hashes']}
        (projection/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
        (projection/'audit.json').write_text(json.dumps(audit_summary(projection),ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    unchanged=all((before/n).read_bytes()==(projection/n).read_bytes() for n in BASE_FILES)
    if not enabled and not unchanged:raise AssertionError('LOCATION_UNAPPROVED_BASELINE_CHANGED')
    write_csv(out/'new_cells.csv',['project_id','column','old_value','new_value','decision_id'],new)
    write_csv(out/'changed_cells.csv',['project_id','column','old_value','new_value'],[])
    write_csv(out/'review_queue.csv',['project_id','reason','candidates'],queue)
    report=dict(task='task2',new_cells=len(new),changed_cells=0,review_queue=len(queue),enabled_datasets=enabled,
        network_requests=sum(x['network_requests'] for x in acquisitions) if acquire else 0,baseline_bitwise_identical=unchanged,
        baseline_hashes={n:sha(before/n) for n in BASE_FILES},output_hashes={n:sha(projection/n) for n in BASE_FILES},
        decision_file_sha256=sha(decisions_path) if decisions_path else None,
        reference_mapping_sha256=sha(references_path) if enabled and references_path else None,
        alias_mapping_sha256=sha(aliases_path) if enabled and aliases_path else None,
        approved_counts='MEASURED_FROM_COMPLETE_APPROVED_SNAPSHOTS' if acquisitions else 'NOT_MEASURED_WITHOUT_APPROVED_SNAPSHOTS',
        complete_datasets=[x['dataset'] for x in acquisitions if x.get('status')=='COMPLETE'],
        approved_datasets_without_complete_snapshot=[k for k in enabled if k not in {x['dataset'] for x in acquisitions if x.get('status') in ('COMPLETE','SCHEMA_REPORT_ONLY')}],excluded_states=['VIC','TAS'])
    (out/'summary.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    (out/'proposed_decisions.json').write_text(json.dumps(proposed_decisions(),ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    measured='依完整核准快照驗得新增 '+str(len(new))+' 格；未成功取得的資料集不計增量，仍待審。' if acquisitions else '核准後數量尚未測得，不能估算為已補值。'
    licenses='\n'.join('- '+k+'：CC BY 4.0，'+v['license'] for k,v in DATASETS.items())
    (out/'README.md').write_text('# 任務 2：政府座標\n\n新增 '+str(len(new))+' 格。未核准時零網路請求，projection/ 六份基線檔逐位元一致。\n\n只接受同州、確定名稱、唯一官方礦點；位置為代表點，非資源邊界。QLD 僅採 GDA94 屬性對，不混用 EPSG3857 geometry。NT 僅欄位報告，SA projects 僅輔助連結。VIC／TAS 無文件端點，維持空白。\n\n'+measured+'每次正式取得須明確傳 --acquire；離線重播使用 --acquisitions。\n\n## 授權\n'+licenses+'\n',encoding='utf8')
    return report
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--before',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--decisions',type=Path);p.add_argument('--acquisitions',type=Path);p.add_argument('--acquire',action='store_true')
    p.add_argument('--references',type=Path);p.add_argument('--aliases',type=Path)
    a=p.parse_args();print(json.dumps(run(a.before,a.out,a.decisions,a.acquisitions,a.acquire,a.references,a.aliases),ensure_ascii=False,indent=2))

