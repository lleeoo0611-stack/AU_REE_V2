"""Round five: source-first deterministic replays and per-task acceptance gates."""
import argparse,json,os,shutil,subprocess,sys
from pathlib import Path
REPO=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(REPO/'src'),str(REPO/'tools')]
import run_round2 as prior
import run_round3 as third
import run_round4 as fourth
from au_ree_v2.round2_pipeline import FILES,read_csv,write_csv,write_json
from au_ree_v2.coverage_task_audit import identical_replays
from au_ree_v2.store import filehash
DATE='2026-11-13'
BASELINE='a35b151c92cc982dc0758cb4966c1655cf9fe9bb'

def full_baseline(work,census):
    before=fourth.full_baseline(work,census)
    decisions=json.loads((REPO/'config/researcher_rule_decisions.json').read_text('utf8'))
    for stage in range(6):
        after=work/f'round4-{stage}'
        fourth.apply(stage,before,after,decisions,census)
        identical_replays(after,REPO/f'results/round4-{stage}-{DATE}/projection')
        before=after
    return before

def verify_existing(folder):
    baseline=REPO/f'results/round4-5-{DATE}/projection'
    _,old=read_csv(baseline/'專案總表.csv');_,new=read_csv(folder/'專案總表.csv')
    byid={r['專案ID']:r for r in new}
    if set(byid)!={r['專案ID'] for r in old}:raise ValueError('ROUND5_COHORT_CHANGED')
    for r in old:
        for c,v in r.items():
            if v and byid[r['專案ID']][c]!=v:raise ValueError('ROUND5_EXISTING_VALUE_CHANGED')
    _,old=read_csv(baseline/'field_provenance.csv');_,new=read_csv(folder/'field_provenance.csv')
    trace={(r['project_id'],r['column']):r for r in new}
    for p in old:
        q=trace[p['project_id'],p['column']]
        if any(q.get(k,'')!=v for k,v in p.items()) or any(v for k,v in q.items() if k not in p):raise ValueError('ROUND5_EXISTING_PROVENANCE_CHANGED')
    if filehash(baseline/'census_inventory.csv')!=filehash(folder/'census_inventory.csv'):raise ValueError('ROUND5_INVENTORY_CHANGED')

def apply(stage,before,after,decisions,census):
    from au_ree_v2 import round4_schema as schema
    from au_ree_v2.round5_stage import collect_task1
    _,rows=read_csv(before/'專案總表.csv');_,trace=read_csv(before/'field_provenance.csv')
    if stage==1:
        fills,reviews,extra=collect_task1(rows,trace,decisions,REPO,census)
        extra['outcome_diff']=extra.pop('hit_review_diff')
    elif stage==2:
        from au_ree_v2.round5_ocr import collect_task2
        task1_extra=collect_task1(rows,trace,decisions,REPO,census)[2]
        fills,reviews,extra=collect_task2(rows,trace,decisions,REPO,census,task1_extra)
    elif stage==3:
        from au_ree_v2.round5_wa import collect as collect_task3
        fills,reviews,extra=collect_task3(rows,trace,decisions,REPO,census)
    else:
        shutil.copytree(before,after);return [],[],[],{}
    new,changed=schema.fill(before,after,fills,decisions,REPO)
    verify_existing(after)
    return new,changed,reviews,extra

def protection(census):
    p=prior.protected_snapshot(census)
    # All frozen results through round three are protected, not just round two.
    names=subprocess.check_output(['git','ls-tree','-rz','--name-only',BASELINE,'results'],cwd=REPO).decode('utf8').split('\0')
    for name in names:
        if name.startswith('results/asx-current/'):continue
        if (REPO/name).is_file():p['protected'][name]=filehash(REPO/name)
    return p

def write_records(path,records,fields):
    fields=list(dict.fromkeys(fields+[k for r in records for k in r]))
    write_csv(path,fields,[{k:json.dumps(v,ensure_ascii=False,sort_keys=True) if isinstance(v,(dict,list)) else v for k,v in r.items()} for r in records])

def comparison_report(tasks,baseline,projection,coordinate_distribution):
    keys=('original_53_columns','all_retained_columns','tiered_coverage')
    initial=baseline.get('not_applicable_stage_excluded',0);final=projection.get('not_applicable_stage_excluded',0)
    research=sum(t['new_cells'] for t in tasks)
    if projection['original_53_columns']['filled']!=baseline['original_53_columns']['filled']+research:raise ValueError('ROUND5_EVIDENCE_RECONCILIATION')
    for key in ('all_retained_columns',):
        if projection[key]['denominator']!=baseline[key]['denominator']-(final-initial):raise ValueError('ROUND5_DENOMINATOR_RECONCILIATION')
    ocr=json.loads((REPO/f'results/round5-2-{DATE}/summary.json').read_text('utf8'))
    return dict(version='round5-coverage-comparison-v1',baseline_commit=BASELINE,baseline={k:baseline[k] for k in keys},tasks=tasks,new_research_cells=research,not_applicable_not_filled=True,not_applicable_stage=dict(baseline=initial,final=final,denominator_reduction=final-initial),ocr=ocr.get('ocr_statistics',{}),coordinate_source_distribution=coordinate_distribution,**{k:projection[k] for k in keys})

def run(task,work,census,publish=False):
    from au_ree_v2 import round4_schema as schema
    os.chdir(REPO);sys.addaudithook(prior.offline_guard)
    out=REPO/f'results/round5-{task}-{DATE}'
    if work.exists():raise ValueError('FRESH_WORK_REQUIRED')
    if out.exists() and any(out.iterdir()) and not (task in (2,3) and set(p.name for p in out.iterdir()) <= {'acquisition','ocr','ocr_manifest.json'}):raise ValueError('FRESH_RESULTS_REQUIRED')
    if task==2 and not (out/'ocr_manifest.json').exists():raise ValueError('OFFLINE_OCR_ENGINE_OR_EXECUTION_REQUIRED')
    if task>1 and not (REPO/f'results/round5-{task-1}-{DATE}/rebuild_receipt.json').exists():raise ValueError('PREVIOUS_TASK_NOT_ACCEPTED')
    from au_ree_v2.round3_publication import tree_hashes
    expected_current=tree_hashes(REPO/'results/asx-current') if publish else None
    protected=protection(census);implementation=prior.implementation_hashes()
    decisions=json.loads((REPO/'config/researcher_rule_decisions.json').read_text('utf8'))
    passes={};audit_passes={};data=None
    for pass_name in ('a','b'):
        print(f'Round5 task {task}: independent FULL offline replay {pass_name}',flush=True)
        before=full_baseline(work/pass_name,census)
        for stage in range(1,task+1):
            after=work/pass_name/f'round5-{stage}'
            data=apply(stage,before,after,decisions,census)
            if stage<task:identical_replays(after,REPO/f'results/round5-{stage}-{DATE}/projection')
            before=after
        passes[pass_name]=before
        audit_folder=work/pass_name/'task-audit';audit_folder.mkdir()
        new,changed,reviews,extra=data
        write_json(audit_folder/'audit_payload.json',dict(new_cells=new,changed_cells=changed,reviews=reviews,extra=extra))
        for name,records,fields in [('new_cells.csv',new,['project_id','column','new_value']),('changed_cells.csv',changed,['project_id','column','old_value','new_value','reason']),('review_queue.csv',reviews,['project_id','reason'])]:write_records(audit_folder/name,records,fields)
        for key,value in extra.items():
            if isinstance(value,(dict,list)):write_json(audit_folder/(key+'.json'),value)
            if key in ('hit_reviews','outcome_diff'):write_records(audit_folder/(key+'.csv'),value,['row_number','project_id','source_sha256'])
        audit_passes[pass_name]=tree_hashes(audit_folder)
        prior.verify_protected(protected)
    if audit_passes['a']!=audit_passes['b']:raise ValueError('ROUND5_AUDIT_NOT_BITWISE_IDENTICAL')
    hashes=identical_replays(passes['a'],passes['b']);out.mkdir(parents=True,exist_ok=True)
    shutil.copytree(passes['a'],out/'projection')
    new,changed,reviews,extra=data
    write_json(out/'audit_payload.json',dict(new_cells=new,changed_cells=changed,reviews=reviews,extra=extra))
    for name,records,fields in [('new_cells.csv',new,['project_id','column','new_value']),('changed_cells.csv',changed,['project_id','column','old_value','new_value','reason']),('review_queue.csv',reviews,['project_id','reason'])]:write_records(out/name,records,fields)
    for key,value in extra.items():
        if isinstance(value,(dict,list)):write_json(out/(key+'.json'),value)
        if key in ('hit_reviews','outcome_diff'):write_records(out/(key+'.csv'),value,['row_number','project_id','source_sha256'])
    projection=json.loads((out/'projection/summary.json').read_text('utf8'))
    summary=dict(task=task,baseline_commit=BASELINE,new_cells=len(new),changed_cells=len(changed),review_queue=len(reviews),independent_full_rebuilds=2,bitwise_identical_files=hashes,offline_rebuild_network_requests=0,existing_conclusion='INCOMPLETE/CONTINUE_UNCHANGED',**{k:projection[k] for k in ('original_53_columns','all_retained_columns','tiered_coverage')})
    _,coordinate_trace=read_csv(out/'projection/field_provenance.csv')
    _,coordinate_rows=read_csv(out/'projection/專案總表.csv')
    centroid_ids={p['project_id'] for p in coordinate_trace if 'TENEMENT_CENTROID' in str(p)}
    paired_ids={r['專案ID'] for r in coordinate_rows if r.get('緯度') and r.get('經度')}
    summary['coordinate_source_distribution']=dict(occurrence_point_rows=len(paired_ids-centroid_ids),tenement_centroid_rows=len(centroid_ids),coordinate_pair_rows=len(paired_ids))
    summary['bitwise_identical_audit_files']=audit_passes['a']
    summary['network_requests']=extra.get('request_count',0)
    summary['ocr_statistics']={k:extra[k] for k in ('ocr_classification_counts','ocr_confidence_histogram','ocr_pages_expected','ocr_pages_executed','ocr_projects_unblocked') if k in extra}
    summary['not_applicable_stage_excluded']=projection.get('not_applicable_stage_excluded',0)
    write_json(out/'summary.json',summary)
    # Fail before expensive regression on oversized or unsafe publication payloads.
    from au_ree_v2.round3_release import verify_public_tree
    verify_public_tree(out)
    xml=out/'offline-tests.xml'
    result=subprocess.run([sys.executable,str(REPO/'tools/run_offline_regression.py'),'--fixture-root',str(census),'--overlay',str(work/'regression'),'--junitxml',str(xml)],cwd=REPO)
    if result.returncode:raise ValueError('FULL_OFFLINE_REGRESSION_FAILED')
    summary['tests']=prior.tests_pass(xml)
    if implementation!=prior.implementation_hashes():raise ValueError('IMPLEMENTATION_CHANGED_DURING_ACCEPTANCE')
    prior.verify_protected(protected)
    write_json(out/'summary.json',summary)
    write_json(out/'rebuild_receipt.json',dict(output_hashes=hashes,audit_hashes=audit_passes['a'],census_sha256=protected['census_sha256'],independent_full_rebuilds=2,tests=summary['tests'],implementation_sha256=implementation))
    descriptions={1:'修正三點優先順序並以有來源的別名重判全部 812 筆命中；不推定新階段。',2:'固定門檻離線 OCR；所有文字與 OCR 命中、日期及未讀頁阻擋均保留。',3:'WA 僅移除 sortBy，沿用精確原件礦權號與 25 km 限制；其他州不嘗試。',4:'彙總新增證據與不適用分母，驗證後發布 current。'}
    lines=[f'# 第五輪任務 {task}', '',descriptions[task],'',f'新增 {len(new)} 格，變更 {len(changed)} 項，待審 {len(reviews)} 項。兩次完整離線來源重建逐位元一致，完整測試通過。既有填值、provenance、Census、inventory、凍結結果及 INCOMPLETE／CONTINUE 不變。','三種覆蓋率與分層分子分母見 summary.json。不為預估新增量放寬條件。']
    lines+=extra.get('readme_lines',[])
    if task==1:
        lines+=['','## 別名造成原 FAIL 轉為 PASS／UNCLEAR']
        for h in extra.get('hit_reviews',[]):
            if h.get('round4_outcome')=='FAIL' and h.get('outcome') in ('PASS','UNCLEAR'):
                lines.append('- '+json.dumps(h,ensure_ascii=False,sort_keys=True))
        lines+=['','## 每列狀態',json.dumps(extra.get('project_stage_status',[]),ensure_ascii=False,indent=2)]
    if task in (2,3):
        lines+=['','## 未新增原因（逐列／頁）']+['- '+json.dumps(r,ensure_ascii=False,sort_keys=True) for r in reviews]
    (out/'README.md').write_text('\n'.join(lines)+'\n',encoding='utf8')
    if task==4:
        tasks=[json.loads((REPO/f'results/round5-{n}-{DATE}/summary.json').read_text('utf8')) for n in range(1,5)]
        baseline=json.loads((REPO/f'results/round4-5-{DATE}/projection/summary.json').read_text('utf8'))
        write_json(out/'coverage_comparison.json',comparison_report(tasks,baseline,projection,summary['coordinate_source_distribution']))
        summary_out=REPO/f'results/round5-summary-{DATE}';summary_out.mkdir(exist_ok=True)
        shutil.copyfile(out/'coverage_comparison.json',summary_out/'coverage_comparison.json')
        if publish:
            from au_ree_v2.round5_release import publish as release
            release(REPO,DATE,work,out,expected_current,prior.tests_pass)
    print(json.dumps(summary,ensure_ascii=False),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--task',type=int,choices=range(1,5),required=True);p.add_argument('--work',type=Path,required=True);p.add_argument('--census-root',type=Path,default=REPO.parent/'AU_REE_V2');p.add_argument('--publish-current',action='store_true');a=p.parse_args()
    run(a.task,a.work.resolve(),a.census_root.resolve(),a.publish_current)
