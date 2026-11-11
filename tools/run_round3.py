"""Sequential round-three research: explicit approvals, fresh offline replays, gated publication."""
import argparse, json, os, shutil, subprocess, sys
from pathlib import Path
REPO=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(REPO/'src'),str(REPO/'tools')]
import run_round2 as prior
from au_ree_v2.round2_pipeline import FILES, read_csv,write_csv,write_json,collect,apply_fills,metrics
from au_ree_v2.coverage_task_audit import identical_replays,compare_projections
from au_ree_v2.store import filehash
EVIDENCE='甲1 甲2 刪掉 乙1 (a) 放寬條件、(c) Mt Stirling 共點、(d) VIC／TAS核准 乙2 可以，核准 乙5 第一個全產期'
DATE='2026-11-11'
RETIRED=['重算磁性元素-HTML磁性稀土_kt','預估年產重稀土_t_per_year']

def coverage3(folder):
    from au_ree_v2.stage_rules import selected_mre
    columns,rows=read_csv(Path(folder)/'專案總表.csv');_,trace=read_csv(Path(folder)/'field_provenance.csv')
    retained=[c for c in columns if c not in RETIRED]
    resources=[c for c in retained if c in ['礦石蘊藏量_Mt','TREO品位_pct','總TREO蘊藏量_kt','磁鐵稀土氧化物蘊藏量_kt','磁鐵稀土佔TREO_pct','NdPr蘊藏量_kt_需兩者皆公布','完整重稀土組合蘊藏量_kt_需8元素皆公布','預估年產TREO_t_per_year','預估年產NdPr_t_per_year','有TREO資源估計','已公布元素數_共15項','已公布元素總和_kt','元素總和/TREO','元素數據一致性檢查','四項磁性元素皆公布','磁性元素重算值_NdPrTbDy_kt'] or '_氧化' in c]
    nonresource=[c for c in retained if c not in resources]
    tier1=[];tier2=[]
    for row in rows:
        status,_=selected_mre(row,trace)
        (tier2 if status is False and not row['總TREO蘊藏量_kt'] else tier1).append(row)
    def count(rs,cs):return sum(bool(r[c]) for r in rs for c in cs)
    def metric(n,d):return dict(filled=n,denominator=d,coverage=n/d if d else None)
    extras=count(tier2,resources)
    a=metric(count(tier1,retained),len(tier1)*len(retained));a['rows']=len(tier1)
    b=metric(count(tier2,retained),len(tier2)*len(nonresource)+extras);b.update(rows=len(tier2),base_denominator=len(tier2)*len(nonresource),existing_filled_resource_cells=extras)
    return dict(original_53_columns=metric(count(rows,retained),len(rows)*53),all_retained_columns=metric(count(rows,retained),len(rows)*len(retained)),tiered_coverage=dict(tier1=a,tier2=b,combined=metric(a['filled']+b['filled'],a['denominator']+b['denominator']),resource_columns=resources,nonresource_columns=nonresource,convention='Filled resource exceptions in tier 2 contribute one numerator AND denominator cell; absent MRE is not proof of absence.'))

def historical_replay(work,census):
    historical=work/'baseline-decisions.json';work.mkdir(parents=True)
    historical.write_bytes(subprocess.check_output(['git','show',prior.BASELINE+':config/researcher_rule_decisions.json'],cwd=REPO))
    before=prior.source_replay(work/'source',census,historical)
    decisions=json.loads((REPO/'config/researcher_rule_decisions.json').read_text('utf8'))
    for stage in 'ABCD':
        fills,queue,extra=collect(stage,before,decisions,REPO)
        after=work/stage;apply_fills(before,after,fills,decisions,REPO)
        identical_replays(after,REPO/f'results/round2-{stage}-{DATE}/projection')
        before=after
    return before

def task0(work,census,publish=False):
    os.chdir(REPO);sys.addaudithook(prior.offline_guard)
    out=REPO/f'results/round3-0-{DATE}'
    if work.exists() or out.exists():raise ValueError('FRESH_OUTPUT_REQUIRED')
    protection=prior.protected_snapshot(census)
    implementation=prior.implementation_hashes()
    outputs={}
    for p in ('a','b'):
        print('Task 0 full offline replay',p,flush=True)
        outputs[p]=historical_replay(work/p,census)
        prior.verify_protected(protection)
    hashes=identical_replays(outputs['a'],outputs['b'])
    out.mkdir(parents=True);shutil.copytree(outputs['a'],out/'projection')
    current=REPO/'results/asx-current'
    receipt=json.loads((REPO/f'results/round2-partial-publication-{DATE}/publication_receipt.json').read_text('utf8'))
    for name,sha in receipt['current_output_hashes'].items():
        if filehash(current/name)!=sha:raise ValueError('CURRENT_CHANGED_SINCE_EXISTING_PUBLICATION:'+name)
    write_csv(out/'new_cells.csv',['project_id','column','value'],[])
    write_csv(out/'changed_cells.csv',['project_id','column','old_value','new_value','reason'],[])
    write_csv(out/'review_queue.csv',['task','reason'],[dict(task='3b',reason='C-NT deferred: datum/control acceptance required')])
    summary=dict(task=0,new_cells=0,round2_cells_already_published=72,independent_full_rebuilds=2,bitwise_identical_files=hashes,network_requests=0,preexisting_values_and_provenance_unchanged=True,c_main='PASS',c_nt='DEFERRED_TASK_3B',existing_conclusion='INCOMPLETE/CONTINUE_UNCHANGED',**coverage3(out/'projection'))
    write_json(out/'summary.json',summary)
    xml=out/'offline-tests.xml'
    completed=subprocess.run([sys.executable,str(REPO/'tools/run_offline_regression.py'),'--fixture-root',str(census),'--overlay',str(work/'regression'),'--junitxml',str(xml)],cwd=REPO)
    if completed.returncode:raise ValueError('FULL_OFFLINE_REGRESSION_FAILED')
    summary['tests']=prior.tests_pass(xml)
    if prior.implementation_hashes()!=implementation:raise ValueError('IMPLEMENTATION_CHANGED')
    prior.verify_protected(protection)
    write_json(out/'summary.json',summary);write_json(out/'rebuild_receipt.json',dict(output_hashes=hashes,census_sha256=protection['census_sha256'],independent_full_rebuilds=2,tests=summary['tests']))
    (out/'README.md').write_text('# 第三輪任務 0\n\n基線 cde12ab 已依先前「更新總表」指示發布第二輪 72 格，原53欄 2,141／4,929。本次不重複新增，也不改既有總說明及 provenance。重新從 Census 與封存來源兩次獨立完整離線重建 A/B/C-main/D，四份 CSV、summary、audit 逐位元一致；C-NT 拆出至任務3b，不將未通過 NT 驗收說成已完成。\n\n三種覆蓋率列於 summary；51欄及兩層為本輪刪欄後口徑預覽，尚未改結構。第2層既有資源格同時計入分子與分母。Census、inventory、凍結結果、INCOMPLETE／CONTINUE 不變。\n',encoding='utf8')
    if publish:
        path=REPO/f'results/round2-summary-{DATE}/publication_status.json'
        old=json.loads(path.read_text('utf8'))
        old.setdefault('history',[]).append(dict(status='ROUND3_C_MAIN_VERIFIED_ALREADY_PUBLISHED',published=True,baseline_commit='cde12ab',c_main='PASS',c_nt='DEFERRED_TASK_3B',evidence=f'results/round3-0-{DATE}/rebuild_receipt.json'))
        write_json(path,old)
        write_json(out/'publication_status.json',dict(published=True,status='VERIFIED_EXISTING_PUBLICATION_NO_CELL_CHANGE',current_preserved=True,nt_acceptance='DEFERRED_TASK_3B'))
    print(json.dumps(summary,ensure_ascii=False),flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--task',type=int,required=True);parser.add_argument('--work',type=Path,required=True);parser.add_argument('--census-root',type=Path,default=REPO.parent/'AU_REE_V2');parser.add_argument('--publish-current',action='store_true');args=parser.parse_args()
    if args.task!=0:raise ValueError('TASK_NOT_IMPLEMENTED')
    task0(args.work.resolve(),args.census_root.resolve(),args.publish_current)
