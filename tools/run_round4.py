"""Round four: source-first deterministic replays and per-task acceptance gates."""
import argparse,json,os,shutil,subprocess,sys
from pathlib import Path
REPO=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(REPO/'src'),str(REPO/'tools')]
import run_round2 as prior
import run_round3 as third
from au_ree_v2.round2_pipeline import FILES,read_csv,write_csv,write_json
from au_ree_v2.coverage_task_audit import identical_replays
from au_ree_v2.store import filehash
DATE='2026-11-13'
BASELINE='e87d679ae1e05a0516849ba15da536b9ed039a00'

def full_baseline(work,census):
    from au_ree_v2 import round3_schema as schema
    before=third.historical_replay(work,census)
    decisions=json.loads((REPO/'config/researcher_rule_decisions.json').read_text('utf8'))
    for stage in range(1,5):
        after=work/f'round3-{stage}'
        if stage==1:schema.migrate(before,after,REPO)
        else:
            fills,_,_=third.round3_collect(stage,before,decisions,census)
            schema.fill(before,after,fills,decisions,REPO)
        identical_replays(after,REPO/f'results/round3-{stage}-2026-11-11/projection')
        before=after
    return before

def apply(stage,before,after,decisions,census):
    from au_ree_v2 import round4_schema as schema
    if stage==0:return schema.merge(before,after,REPO)
    if stage==1:return schema.classify(before,after,REPO)
    _,rows=read_csv(before/'專案總表.csv');_,trace=read_csv(before/'field_provenance.csv')
    if stage==2:
        from au_ree_v2.round4_stage import collect_charley_exit
        fills,reviews,extra=collect_charley_exit(rows,trace,decisions,REPO,census)
    elif stage==3:
        from au_ree_v2.round4_stage import collect_stage_three_point
        fills,reviews,extra=collect_stage_three_point(rows,trace,decisions,REPO,census)
    elif stage==4:
        from au_ree_v2.round4_tenements import collect
        fills,reviews,extra=collect(rows,trace,decisions,REPO,census)
    else:
        shutil.copytree(before,after);return [],[],[],{}
    new,changed=schema.fill(before,after,fills,decisions,REPO)
    return new,changed,reviews,extra

def protection(census):
    p=prior.protected_snapshot(census)
    # All frozen results through round three are protected, not just round two.
    names=subprocess.check_output(['git','ls-tree','-rz','--name-only',BASELINE,'results'],cwd=REPO).decode('utf8').split('\0')
    for name in names:
        if name.startswith('results/asx-current/') or name=='results/round3-3-2026-11-11/README.md':continue
        if (REPO/name).is_file():p['protected'][name]=filehash(REPO/name)
    return p

def write_records(path,records,fields):
    fields=list(dict.fromkeys(fields+[k for r in records for k in r]))
    write_csv(path,fields,[{k:json.dumps(v,ensure_ascii=False,sort_keys=True) if isinstance(v,(dict,list)) else v for k,v in r.items()} for r in records])

def comparison_report(tasks,baseline,projection,coordinate_distribution):
    """Separate de-duplication, applicability and genuinely new evidence."""
    keys=('original_53_columns','all_retained_columns','tiered_coverage')
    def denominators(record):
        return {'original_53_columns':record['original_53_columns']['denominator'],
                'all_retained_columns':record['all_retained_columns']['denominator'],
                'tiered_combined':record['tiered_coverage']['combined']['denominator']}
    initial=denominators(baseline);merged=denominators(tasks[0]);final=denominators(projection)
    merge_delta={k:merged[k]-initial[k] for k in initial}
    excluded=projection.get('not_applicable_stage_excluded',0)
    applicability={'original_53_columns':0,'all_retained_columns':-excluded,'tiered_combined':-excluded}
    if any(final[k]!=initial[k]+merge_delta[k]+applicability[k] for k in initial):raise ValueError('ROUND4_DENOMINATOR_RECONCILIATION')
    research=sum(t['new_cells'] for t in tasks[2:5])
    removed=tasks[0]['original_53_columns']['filled']-baseline['original_53_columns']['filled']
    if projection['original_53_columns']['filled']!=baseline['original_53_columns']['filled']+removed+research:raise ValueError('ROUND4_EVIDENCE_RECONCILIATION')
    return dict(version='round4-coverage-comparison-v1',baseline_commit=BASELINE,
        baseline={k:baseline[k] for k in keys},tasks=tasks,new_research_cells=research,
        merge_not_new_evidence=True,not_applicable_not_filled=True,
        evidence_changes=dict(baseline=baseline['original_53_columns']['filled'],merge_delta=removed,new_research=research,final=projection['original_53_columns']['filled']),
        denominator_changes=dict(baseline=initial,merge=merge_delta,not_applicable_stage=applicability,final=final),
        applicability=dict(after_task1=tasks[1].get('not_applicable_stage_excluded',0),final=excluded,additional_after_task1=excluded-tasks[1].get('not_applicable_stage_excluded',0),tier1=projection['tiered_coverage']['tier1']['not_applicable_stage_excluded'],tier2=projection['tiered_coverage']['tier2']['not_applicable_stage_excluded']),
        coordinate_source_distribution=coordinate_distribution,**{k:projection[k] for k in keys})

def run(task,work,census,publish=False):
    from au_ree_v2 import round4_schema as schema
    os.chdir(REPO);sys.addaudithook(prior.offline_guard)
    out=REPO/f'results/round4-{task}-{DATE}'
    if work.exists():raise ValueError('FRESH_WORK_REQUIRED')
    if out.exists() and any(out.iterdir()) and not (task==4 and set(p.name for p in out.iterdir())=={'acquisition'}):raise ValueError('FRESH_RESULTS_REQUIRED')
    if task and not (REPO/f'results/round4-{task-1}-{DATE}/rebuild_receipt.json').exists():raise ValueError('PREVIOUS_TASK_NOT_ACCEPTED')
    from au_ree_v2.round3_publication import tree_hashes
    expected_current=tree_hashes(REPO/'results/asx-current') if publish else None
    protected=protection(census);implementation=prior.implementation_hashes()
    decisions=json.loads((REPO/'config/researcher_rule_decisions.json').read_text('utf8'))
    passes={};data=None
    for pass_name in ('a','b'):
        print(f'Round4 task {task}: independent FULL offline replay {pass_name}',flush=True)
        before=full_baseline(work/pass_name,census)
        for stage in range(task+1):
            after=work/pass_name/f'round4-{stage}'
            data=apply(stage,before,after,decisions,census)
            if stage<task:identical_replays(after,REPO/f'results/round4-{stage}-{DATE}/projection')
            before=after
        passes[pass_name]=before;prior.verify_protected(protected)
    hashes=identical_replays(passes['a'],passes['b']);out.mkdir(parents=True,exist_ok=True)
    shutil.copytree(passes['a'],out/'projection')
    new,changed,reviews,extra=data
    for name,records,fields in [('new_cells.csv',new,['project_id','column','new_value']),('changed_cells.csv',changed,['project_id','column','old_value','new_value','reason']),('review_queue.csv',reviews,['project_id','reason'])]:write_records(out/name,records,fields)
    for key,value in extra.items():
        if isinstance(value,(dict,list)):write_json(out/(key+'.json'),value)
        if key=='hit_reviews':write_records(out/'hit_reviews.csv',value,['row_number','project_id','source_sha256'])
    projection=json.loads((out/'projection/summary.json').read_text('utf8'))
    summary=dict(task=task,baseline_commit=BASELINE,new_cells=len(new),changed_cells=len(changed),review_queue=len(reviews),independent_full_rebuilds=2,bitwise_identical_files=hashes,offline_rebuild_network_requests=0,existing_conclusion='INCOMPLETE/CONTINUE_UNCHANGED',**{k:projection[k] for k in ('original_53_columns','all_retained_columns','tiered_coverage')})
    _,coordinate_trace=read_csv(out/'projection/field_provenance.csv')
    _,coordinate_rows=read_csv(out/'projection/專案總表.csv')
    centroid_ids={p['project_id'] for p in coordinate_trace if 'TENEMENT_CENTROID' in str(p)}
    paired_ids={r['專案ID'] for r in coordinate_rows if r.get('緯度') and r.get('經度')}
    summary['coordinate_source_distribution']=dict(occurrence_point_rows=len(paired_ids-centroid_ids),tenement_centroid_rows=len(centroid_ids),coordinate_pair_rows=len(paired_ids))
    summary['network_requests']=extra.get('request_count',0)
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
    write_json(out/'rebuild_receipt.json',dict(output_hashes=hashes,census_sha256=protected['census_sha256'],independent_full_rebuilds=2,tests=summary['tests'],implementation_sha256=implementation))
    descriptions={0:'依原件日期與明示更名合併 GoldArc／Asra。合併不是新研究證據；完整被合併列、衝突值、原 provenance 及總說明保存在 merged_rows.json。',1:'A1／A2 尚無產品的空格標 NOT_APPLICABLE_STAGE，僅調整適用分母；PENDING_CODEBOOK 改為有來源理由的 UNKNOWN。',2:'依明示研究者決策將四個 Charley 專案標為 X／退出，原始開發階段維持空白；不擴大套用其他專案。',3:'逐命中核查專案來源、段落定位、已完成／當前語意三點。任何 UNCLEAR、未讀頁、缺檔、未知日期維持待審。',4:'只採核實官方礦權多邊形及原件礦權號。礦權幾何代表點不是礦體實測點；最大距離超過 25 km 不回填；TAS 不嘗試。',5:'逐任務彙總新增證據、合併減量、不適用分母與實際覆蓋率；總說明及既有呈現精度不改。'}
    (out/'README.md').write_text(f'# 第四輪任務 {task}\n\n{descriptions[task]}\n\n新增 {len(new)} 格，變更 {len(changed)} 項，待審 {len(reviews)} 項。兩次從 Census 和封存來源完整離線重建，四份 CSV、summary、audit 逐位元一致；完整測試通過。Census、inventory、凍結歷史及 INCOMPLETE／CONTINUE 結論不變。三種覆蓋口徑見 summary.json。\n',encoding='utf8')
    if task==5:
        tasks=[json.loads((REPO/f'results/round4-{n}-{DATE}/summary.json').read_text('utf8')) for n in range(6)]
        baseline=json.loads((REPO/'results/round3-4-2026-11-11/projection/summary.json').read_text('utf8'))
        write_json(out/'coverage_comparison.json',comparison_report(tasks,baseline,projection,summary['coordinate_source_distribution']))
        summary_out=REPO/f'results/round4-summary-{DATE}';summary_out.mkdir(exist_ok=True)
        shutil.copyfile(out/'coverage_comparison.json',summary_out/'coverage_comparison.json')
        if publish:
            from au_ree_v2.round4_release import publish as release
            release(REPO,DATE,work,out,expected_current,prior.tests_pass)
    print(json.dumps(summary,ensure_ascii=False),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--task',type=int,choices=range(6),required=True);p.add_argument('--work',type=Path,required=True);p.add_argument('--census-root',type=Path,default=REPO.parent/'AU_REE_V2');p.add_argument('--publish-current',action='store_true');a=p.parse_args()
    run(a.task,a.work.resolve(),a.census_root.resolve(),a.publish_current)
