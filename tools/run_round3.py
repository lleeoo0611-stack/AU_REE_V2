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

# Runner extension (integrated after task 0 acceptance)
def round3_collect(task,before,decisions,census):
    _,rows=read_csv(Path(before)/'專案總表.csv');_,trace=read_csv(Path(before)/'field_provenance.csv')
    if task==2:
        from au_ree_v2.round3_stage import collect_stage_absence
        settings=json.loads((REPO/'config/round3_stage.json').read_text('utf8'))
        return collect_stage_absence(rows,trace,decisions,REPO,census,settings)
    if task==3:
        from au_ree_v2.round3_locations import collect, verify_official_acquisition
        fills,reviews,extra=collect(rows,trace,decisions,REPO)
        acquisition=verify_official_acquisition(REPO);extra['new_official_acquisition']=acquisition
        for item in acquisition['datasets']:
            reviews.append(dict(project_id='',project=item['state'],reason=item['status'],details=item))
        return fills,reviews,extra
    if task==4:
        from au_ree_v2.round3_annual import collect
        return collect(rows,trace,decisions,REPO)
    return [],[],{}

def sequential(task,work,census,publish=False):
    from au_ree_v2 import round3_schema as schema
    os.chdir(REPO);sys.addaudithook(prior.offline_guard)
    out=REPO/f'results/round3-{task}-{DATE}'
    if work.exists() or out.exists():raise ValueError('FRESH_OUTPUT_REQUIRED')
    if not (REPO/f'results/round3-{task-1}-{DATE}/rebuild_receipt.json').exists():raise ValueError('PREVIOUS_TASK_MUST_PASS_FIRST')
    from au_ree_v2.round3_publication import tree_hashes
    current_at_runner_start=tree_hashes(REPO/'results/asx-current') if task==5 and publish else None
    protection=prior.protected_snapshot(census);implementation=prior.implementation_hashes()
    decisions=json.loads((REPO/'config/researcher_rule_decisions.json').read_text('utf8'));passes={};stage_data={}
    for pass_name in ('a','b'):
        print('Task',task,'full independent offline replay',pass_name,flush=True)
        before=historical_replay(work/pass_name,census)
        for stage in range(1,min(task,4)+1):
            after=work/pass_name/f'round3-{stage}'
            if stage==1:
                new,changed,reviews=schema.migrate(before,after,REPO);extra={}
            else:
                fills,reviews,extra=round3_collect(stage,before,decisions,census)
                new,changed=schema.fill(before,after,fills,decisions,REPO)
            if stage<task:identical_replays(after,REPO/f'results/round3-{stage}-{DATE}/projection')
            stage_data[stage]=dict(new=new,changed=changed,reviews=reviews,extra=extra)
            before=after
        passes[pass_name]=before;prior.verify_protected(protection)
    hashes=identical_replays(passes['a'],passes['b'])
    out.mkdir(parents=True);shutil.copytree(passes['a'],out/'projection')
    data=stage_data.get(task,dict(new=[],changed=[],reviews=[],extra={}))
    for name,key,basefields in [('new_cells.csv','new',['project_id','column','new_value']),('changed_cells.csv','changed',['project_id','column','old_value','new_value','reason']),('review_queue.csv','reviews',['project_id','project','reason'])]:
        records=data[key];fields=list(dict.fromkeys(basefields+[k for r in records for k in r]))
        normalized=[{k:json.dumps(v,ensure_ascii=False,sort_keys=True) if isinstance(v,(dict,list)) else v for k,v in r.items()} for r in records]
        write_csv(out/name,fields,normalized)
    if task==1:shutil.copyfile(REPO/'config/retired_columns.json',out/'retired_columns.json')
    for key,value in data['extra'].items():
        if isinstance(value,(dict,list)):write_json(out/(key+'.json'),value)
    s=json.loads((out/'projection/summary.json').read_text('utf8'))
    summary=dict(task=task,new_cells=len(data['new']),changed_cells=len(data['changed']),review_queue=len(data['reviews']),independent_full_rebuilds=2,bitwise_identical_files=hashes,network_requests=data['extra'].get('new_official_acquisition',{}).get('request_count',0),offline_rebuild_network_requests=0,preexisting_values_and_provenance_unchanged=True,existing_conclusion='INCOMPLETE/CONTINUE_UNCHANGED',**{k:s[k] for k in ('original_53_columns','all_retained_columns','tiered_coverage')})
    write_json(out/'summary.json',summary)
    xml=out/'offline-tests.xml';completed=subprocess.run([sys.executable,str(REPO/'tools/run_offline_regression.py'),'--fixture-root',str(census),'--overlay',str(work/'regression'),'--junitxml',str(xml)],cwd=REPO)
    if completed.returncode:raise ValueError('FULL_OFFLINE_REGRESSION_FAILED')
    summary['tests']=prior.tests_pass(xml)
    if prior.implementation_hashes()!=implementation:raise ValueError('IMPLEMENTATION_CHANGED')
    prior.verify_protected(protection)
    write_json(out/'summary.json',summary);write_json(out/'rebuild_receipt.json',dict(output_hashes=hashes,census_sha256=protection['census_sha256'],independent_full_rebuilds=2,tests=summary['tests'],implementation_sha256=implementation))
    details={1:'刪除兩個原本全空欄位，只重分類空白。Wimmera/WIM100 雖無 TREO 總量，仍有已選礦石資源量，因此實測有MRE38列／無MRE55列，與題示估計37／56不同。第2層已填資源格同時計入分子及分母。被刪欄及每格分類變更見 changed_cells.csv。'+schema.LIMITATION,2:'僅在每份關聯封存原件皆完整可讀、日期可知，且沒有任一關鍵字時推定。命中、未讀頁、缺檔或未知日期全部入 review queue；影像主導／無可抽取文字的PDF頁必須有原件與完整頁面渲染SHA相符的逐頁視覺核查，否則保留待審；沒有宣稱OCR已完成。視覺結果、渲染方法及關鍵字版本保存在每份原件的manifest。增加relinquish保守搜尋詞，部分退還礦權只進待審、不判成整個專案退出。不為湊數放寬。原始開發階段欄不填推定。',3:'只採同州唯一精確名稱／單site且公司不矛盾的代表點。NT以完整同名控制點比較三種datum，不能辨別GDA94/GDA2020時明確標註並取GDA94。Mt Stirling與Yttria同一2024-04-16礦床估計，不可直接加總；保留既有Yttria點，距離見shared_deposit_points.json。VIC/TAS僅官方資料且授權明確才接納；遇存取限制立即停止。',4:'只限Cummins Range，依p60設計基準及p76分期解釋選首個全產期，不把價目表NdPr價格當年產量。',5:'彙總各任務實測增量與三種覆蓋率；既有總說明與provenance保留，不隨新增證據改寫。'}
    text=f'# 第三輪任務 {task}\n\n新增 {summary["new_cells"]} 格；變更／刪除空白分類 {summary["changed_cells"]} 格。\n\n{details[task]}\n\n兩次獨立完整離線來源重建；四份CSV、summary及audit逐位元一致，完整回歸通過。Census、inventory、凍結歷史與INCOMPLETE／CONTINUE結論不動。\n'
    if task==1:text+='\n資源欄明確清單：\n'+''.join('- '+c+'\n' for c in s['tiered_coverage']['resource_columns'])+'\n第2層一般欄：\n'+''.join('- '+c+'\n' for c in s['tiered_coverage']['nonresource_columns'])
    if task==3:
        distances=data['extra']['shared_deposit_points']
        text+='\nYttria既有點與MINEDEX點距離：'+', '.join(f"{d['distance_to_minedex_m']:.3f} m" for d in distances)+'；既有點保持不變。本輪新增WA10格、NT4格、Mt Stirling2格。VIC完整封存18794筆、39筆REE/monazite候選，但指定空白列沒有同州、公司、唯一site可同時成立的匹配，新增0；TAS HTTP403後停止，新增0。VIC來源project欄為目錄來源類別，不冒充採礦專案群組。\n'
    (out/'README.md').write_text(text,encoding='utf8')
    if task==5:
        summary_out=REPO/f'results/round3-summary-{DATE}';summary_out.mkdir()
        records=[json.loads((REPO/f'results/round3-{i}-{DATE}/summary.json').read_text('utf8')) for i in range(5)]
        write_json(summary_out/'coverage_comparison.json',dict(baseline=dict(commit='cde12ab',filled=2141,denominator=4929),tasks=records,total_new_cells=sum(r['new_cells'] for r in records),**{k:s[k] for k in ('original_53_columns','all_retained_columns','tiered_coverage')}))
        if publish:
            from au_ree_v2.round3_release import publish_round3
            from au_ree_v2.round3_locations import nt_candidates
            def verify_nt_fresh():
                acquisitions=json.loads((REPO/'results/coverage-approved-2026-11-11/government/acquisitions.json').read_text('utf8'))
                return nt_candidates(acquisitions,decisions)[1]
            publish_round3(REPO,DATE,work,out,summary_out,current_at_runner_start,schema,prior.tests_pass,verify_nt_fresh)
    print(json.dumps(summary,ensure_ascii=False),flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--task',type=int,required=True);parser.add_argument('--work',type=Path,required=True);parser.add_argument('--census-root',type=Path,default=REPO.parent/'AU_REE_V2');parser.add_argument('--publish-current',action='store_true');args=parser.parse_args()
    if args.task==0:task0(args.work.resolve(),args.census_root.resolve(),args.publish_current)
    else:sequential(args.task,args.work.resolve(),args.census_root.resolve(),args.publish_current)
