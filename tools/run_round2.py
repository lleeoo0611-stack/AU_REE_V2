"""Two fresh complete offline source replays per round-two task; explicit gated publication."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

REPO=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(REPO/'src'),str(REPO/'tools')]
from au_ree_v2.round2_pipeline import FILES,read_csv,write_json,apply_fills,collect,summarize_task,metrics
from au_ree_v2.coverage_task_audit import identical_replays,compare_projections
from au_ree_v2.iteration_review import audit_summary
from au_ree_v2.store import filehash
from au_ree_v2.project_summary import export_summary
from au_ree_v2.project_identity import extend_summary
from au_ree_v2.presentation_notes import convert_summary
from rebuild_asx_census import load_assets,review_cutoff
from apply_archived_element_additions import apply as apply_archived
from integrate_official_locations import run as integrate_locations

BASELINE='877b4da'

def offline_guard(event,args):
    if event in ('socket.connect','socket.getaddrinfo'):
        raise PermissionError('ROUND2_NO_NETWORK_REQUESTS')

def source_replay(work,census,historical):
    database=census/'work/phase22/verified-performance-v3/isolated-round-0/after/canonical.sqlite'
    ledger_paths=[REPO/'config'/n for n in ('asx_source_reviews.json','asx_discovery_reviews.json','asx_project_identity_reviews.json','asx_location_reviews.json')]
    ledgers=[json.loads(p.read_text('utf8')) for p in ledger_paths]
    assets=load_assets(REPO/'config/asx_local_asset_roots.json',census,ledgers)
    cutoff=review_cutoff(ledgers)
    export_summary(census,database,census/'results/phase22-2026-11-06',work/'base52',cutoff=cutoff,
                   review_ledger=ledger_paths[0],asset_roots=assets,discovery_ledger=ledger_paths[1],
                   location_ledger=ledger_paths[3],user_template_mapping=REPO/'config/user_template_mapping.json',researcher_decisions=historical)
    extend_summary(work/'base52',work/'base53',ledger_paths[2],assets)
    apply_archived(work/'base53',work/'archived',REPO/'config/asx_archived_element_additions.json',database)
    integrate_locations(work/'archived',work/'official',historical,REPO/'results/coverage-approved-2026-11-11/government/acquisitions.json')
    result=work/'official/projection'
    expected=json.loads((REPO/'results/coverage-approved-2026-11-11/presentation/retired_consistency_trace.json').read_text('utf8'))['core_summary']['output_hashes']
    for name,sha in expected.items():
        if filehash(result/name)!=sha:
            raise ValueError('ROUND2_BASELINE_SOURCE_REPLAY_MISMATCH:'+name)
    if audit_summary(result)['filled_cells']!=2069:
        raise ValueError('ROUND2_BASELINE_NOT_2069')
    return result

def protected_snapshot(census):
    database=census/'work/phase22/verified-performance-v3/isolated-round-0/after/canonical.sqlite'
    tracked=subprocess.check_output(['git','ls-tree','-r','--name-only',BASELINE,'results'],cwd=REPO,text=True).splitlines()
    frozen={n:filehash(REPO/n) for n in tracked if not n.startswith('results/asx-current/') and (REPO/n).is_file()}
    for name in ('asx_source_reviews.json','asx_discovery_reviews.json','asx_project_identity_reviews.json','asx_location_reviews.json','asx_archived_element_additions.json'):
        frozen['config/'+name]=filehash(REPO/'config'/name)
    return dict(census_path=str(database),census_sha256=filehash(database),protected=frozen)

def verify_protected(snapshot):
    if filehash(snapshot['census_path'])!=snapshot['census_sha256']:
        raise ValueError('ROUND2_CENSUS_CHANGED')
    for name,sha in snapshot['protected'].items():
        if filehash(REPO/name)!=sha:
            raise ValueError('ROUND2_FROZEN_FILE_CHANGED:'+name)

def implementation_hashes():
    return {p.relative_to(REPO).as_posix():filehash(p) for root in ('src','tools','config') for p in sorted((REPO/root).rglob('*')) if p.is_file() and p.suffix in ('.py','.json') and '__pycache__' not in p.parts}

def tests_pass(path):
    root=ET.parse(path).getroot()
    suites=[root] if root.tag=='testsuite' else list(root.iter('testsuite'))
    if not suites or sum(int(s.get('tests',0)) for s in suites)<878 or any(int(s.get(k,0)) for s in suites for k in ('errors','failures','skipped')):
        raise ValueError('ROUND2_COMPLETE_REGRESSION_REQUIRED')
    return dict(tests=sum(int(s.get('tests',0)) for s in suites),failures=0,errors=0,skipped=0,junit_sha256=filehash(path))

def run(task,work,census,run_tests=False):
    work,census=Path(work).resolve(),Path(census).resolve()
    if work.exists():
        raise ValueError('ROUND2_FRESH_WORK_REQUIRED')
    work.mkdir(parents=True)
    os.chdir(REPO)
    sys.addaudithook(offline_guard)
    protection=protected_snapshot(census)
    write_json(work/'protection.json',protection)
    historical=work/'baseline-decisions.json'
    historical.write_bytes(subprocess.check_output(['git','show',BASELINE+':config/researcher_rule_decisions.json'],cwd=REPO))
    decision_path=REPO/'config/researcher_rule_decisions.json'
    decision_sha=filehash(decision_path)
    implementation=implementation_hashes()
    decisions=json.loads(decision_path.read_text('utf8'))
    stages='ABCD'[:'ABCD'.index(task)+1]
    outputs={}
    for pass_name in ('a','b'):
        print('Full independent offline source reconstruction:',task,pass_name,flush=True)
        pass_dir=work/pass_name
        before=source_replay(pass_dir,census,historical)
        outputs[pass_name]={'baseline':before}
        for stage in stages:
            fills,reviews,extra=collect(stage,before,decisions,REPO)
            after=pass_dir/stage
            apply_fills(before,after,fills,decisions,REPO)
            compare_projections(outputs[pass_name]['baseline'],after)
            outputs[pass_name][stage]=after
            before=after
        verify_protected(protection)
        if filehash(decision_path)!=decision_sha:
            raise ValueError('ROUND2_DECISIONS_CHANGED_DURING_REPLAY')
    for stage in ['baseline']+list(stages):
        identical_replays(outputs['a'][stage],outputs['b'][stage])
        if stage != 'baseline' and stage != task:
            previous=REPO/('results/round2-'+stage+'-2026-11-11/projection')
            if previous.exists(): identical_replays(previous,outputs['a'][stage])
    prior='baseline' if task=='A' else 'ABCD'['ABCD'.index(task)-1]
    out=REPO/('results/round2-'+task+'-2026-11-11')
    summary=summarize_task(task,outputs['a'][prior],outputs['a'][task],outputs['b'][task],decisions,REPO,out)
    shutil.copytree(outputs['a'][task],out/'projection')
    write_json(out/'rebuild_receipt.json',dict(version='round2-full-source-replay-v1',task=task,baseline_commit=BASELINE,
        census_sha256=protection['census_sha256'],inventory_sha256=filehash(outputs['a'][task]/'census_inventory.csv'),
        independent_full_rebuilds=2,all_stages=[*stages],output_hashes={n:filehash(outputs['a'][task]/n) for n in FILES},
        researcher_decisions_sha256=decision_sha,implementation_sha256=implementation,historical_decisions_sha256=filehash(historical),network_requests=0,
        protected_files=len(protection['protected']),existing_conclusion='INCOMPLETE/CONTINUE_UNCHANGED'))
    estimate={'A':'35–40','B':'30','C':'10–24','D':'0–12'}[task]
    text=f'# 第二輪任務 {task}\n\n新增 {summary["new_cells"]} 格；預期範圍 {estimate} 格。既有填值與 provenance 全部保留，changed_cells.csv 為空。\n\n依 A → B → C → D 順序套用。此任務兩次從 Census、原始封存來源與既有 review ledger 獨立完整離線重建；四份 CSV、summary.json 與 audit.json 逐位元一致。全程零網路請求。\n\n原 53 欄證據口徑與有 TREO MRE 研究列口徑均見 summary.json；不把總說明呈現變更當作新證據。\n\n決定、來源頁碼／locator 見 new_cells.csv，未決案件與候選見 review_queue.csv。Census、inventory、凍結歷史及 INCOMPLETE／CONTINUE 結論不變。\n'
    if task=='C':
        text+='\n## 待研究者決定與阻礙\n多 site 代表點、VIC／TAS 新來源尚未核准，維持空白。實際增量低於預期：WA 有公司欄位但來源未填公司時亦拒絕自動匹配，不把缺公司當作無公司欄位；多點與同名不同公司仍保守留白。NT ZIP 的 CSV SHA 已驗證，但封存 metadata 未能確認 MGA datum（GDA94／AGD66），因此不填 NT 座標；真實控制點誤差驗收未完成，不能聲稱 NT 轉換完成。\n'
    (out/'README.md').write_text(text,encoding='utf8')
    if run_tests:
        xml=out/'offline-tests.xml'
        result=subprocess.run([sys.executable,str(REPO/'tools/run_offline_regression.py'),'--fixture-root',str(census),'--overlay',str(work/'regression-overlay'),'--junitxml',str(xml)],cwd=REPO)
        if result.returncode:
            raise ValueError('ROUND2_FULL_REGRESSION_FAILED')
        if implementation_hashes()!=implementation: raise ValueError('ROUND2_IMPLEMENTATION_CHANGED_DURING_VALIDATION')
        write_json(out/'validation.json',dict(passed=True,implementation_sha256=implementation,**tests_pass(xml)))
    verify_protected(protection)
    print(json.dumps(dict(task=task,new_cells=summary['new_cells'],out=str(out)),ensure_ascii=False),flush=True)
    return summary

def validated_reports():
    os.chdir(REPO)
    reports={task:REPO/('results/round2-'+task+'-2026-11-11') for task in 'ABCD'}
    records={task:json.loads((p/'summary.json').read_text('utf8')) for task,p in reports.items()}
    for task,p in reports.items():
        tests_pass(p/'offline-tests.xml')
        receipt=json.loads((p/'rebuild_receipt.json').read_text('utf8'))
        if receipt.get('independent_full_rebuilds')!=2:
            raise ValueError('ROUND2_DOUBLE_REPLAY_REQUIRED')
        if {n:filehash(p/'projection'/n) for n in FILES}!=receipt['output_hashes']:
            raise ValueError('ROUND2_OUTPUT_CHANGED_AFTER_ACCEPTANCE')
    last_receipt=json.loads((reports['D']/'rebuild_receipt.json').read_text('utf8'))
    last_validation=json.loads((reports['D']/'validation.json').read_text('utf8'))
    if filehash(REPO/'config/researcher_rule_decisions.json')!=last_receipt['researcher_decisions_sha256'] or implementation_hashes()!=last_validation['implementation_sha256']:
        raise ValueError('ROUND2_FINAL_ACCEPTED_IMPLEMENTATION_CHANGED')
    return reports,records

def publication_status(records):
    complete=records['C'].get('nt_real_control_point_validated') is True
    return dict(published=False,ready_to_publish=complete,
                status='READY_PENDING_EXPLICIT_PUBLISH' if complete else 'BLOCKED_NT_METADATA_AND_REAL_CONTROL_POINT',
                nt_real_control_point_validated=complete,
                task_c_acceptance='COMPLETE' if complete else 'PARTIAL_NT_ACCEPTANCE_NOT_MET')

def write_unchanged_or_new(path,value):
    path=Path(path)
    if path.exists():
        if json.loads(path.read_text('utf8'))!=value:
            raise ValueError('ROUND2_EXISTING_SUMMARY_DIFFERS:'+path.name)
        return
    write_json(path,value)

def write_summary():
    """Report accepted offline additions without publishing an incomplete task C."""
    reports,records=validated_reports()
    comparison=REPO/'results/round2-summary-2026-11-11'
    comparison.mkdir(exist_ok=True)
    result=dict(baseline=records['A']['before'],
                stages={k:dict(new_cells=v['new_cells'],coverage=v['after']) for k,v in records.items()},
                total_new_cells=sum(v['new_cells'] for v in records.values()),
                final=metrics(reports['D']/'projection'),publication=publication_status(records))
    write_unchanged_or_new(comparison/'coverage_comparison.json',result)
    write_unchanged_or_new(comparison/'publication_status.json',result['publication'])
    return reports,records,comparison

def publish():
    reports,records,comparison=write_summary()
    if not publication_status(records)['ready_to_publish']:
        raise ValueError('ROUND2_PUBLICATION_BLOCKED_NT_METADATA_AND_REAL_CONTROL_POINT')
    if (comparison/'publication_receipt.json').exists():
        raise ValueError('ROUND2_ALREADY_PUBLISHED_CHECK_RECEIPT')
    final=reports['D']/'projection'
    for name in ('presentation-a','presentation-b'):
        if (comparison/name).exists():
            raise ValueError('ROUND2_PRESENTATION_OUTPUT_ALREADY_EXISTS:'+name)
    convert_summary(final,comparison/'presentation-a')
    convert_summary(final,comparison/'presentation-b')
    for name in (*FILES,'retired_consistency_trace.json'):
        if filehash(comparison/'presentation-a'/name)!=filehash(comparison/'presentation-b'/name):
            raise ValueError('ROUND2_PRESENTATION_MISMATCH')
    target=REPO/'results/asx-current'
    for source in (comparison/'presentation-a').iterdir():
        if source.is_file():
            shutil.copyfile(source,target/source.name)
    audit_summary(target)
    write_json(comparison/'publication_receipt.json',dict(published=True,network_requests=0,final_original_evidence=metrics(final),presentation=audit_summary(target)))

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--task',choices=list('ABCD'))
    parser.add_argument('--work',type=Path)
    parser.add_argument('--census-root',type=Path,default=REPO.parent/'AU_REE_V2')
    parser.add_argument('--run-tests',action='store_true')
    parser.add_argument('--publish-current',action='store_true')
    parser.add_argument('--write-summary',action='store_true')
    args=parser.parse_args()
    if args.task:
        if not args.work: parser.error('--task requires --work')
        run(args.task,args.work,args.census_root,args.run_tests)
    elif not (args.publish_current or args.write_summary):
        parser.error('--task, --write-summary or --publish-current is required')
    if args.write_summary: write_summary()
    if args.publish_current: publish()
