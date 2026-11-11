"""Explicitly authorized partial publication: NT acceptance remains incomplete."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

REPO=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(REPO/'src'),str(REPO/'tools')]
import run_round2 as prior
from au_ree_v2.round2_pipeline import FILES,read_csv,write_json,apply_fills,collect,metrics,write_csv
from au_ree_v2.coverage_task_audit import identical_replays,compare_projections
from au_ree_v2.iteration_review import audit_summary
from au_ree_v2.presentation_notes import convert_summary
from au_ree_v2.store import filehash

DECISION_ID='round2-partial-publication-20261111'
RULE='PUBLISH_VERIFIED_ROUND2_WITH_NT_PENDING'
SCOPE='ROUND2_72_VERIFIED_CELLS_NT_UNCHANGED'
EVIDENCE='助理：「沒有合併主線或更新 asx-current；NT 座標基準與控制點驗收仍待完成。」\n使用者：「更新總表」'
RESULT=REPO/'results/round2-partial-publication-2026-11-11'
STATUS='PARTIAL_NT_ACCEPTANCE_NOT_MET'


def approval(decisions):
    records=decisions.get('decisions',[])
    found=[d for d in records if d.get('decision_id')==DECISION_ID or d.get('rule')==RULE]
    required=dict(decision_id=DECISION_ID,rule=RULE,scope=SCOPE,decided_by='USER_EXPLICIT_APPROVAL',decided_date='2026-11-11',approval_evidence=EVIDENCE)
    if len(found)!=1 or any(found[0].get(k)!=v for k,v in required.items()):
        raise ValueError('PARTIAL_PUBLICATION_EXPLICIT_APPROVAL_REQUIRED')
    return found[0]


def tree_hashes(path):
    path=Path(path)
    return {p.relative_to(path).as_posix():filehash(p) for p in sorted(path.rglob('*')) if p.is_file()}


def tested_implementation():
    result=prior.implementation_hashes()
    result.update({p.relative_to(REPO).as_posix():filehash(p) for p in sorted((REPO/'tests').rglob('*')) if p.is_file() and p.suffix in ('.py','.json')})
    return result


def nt_unchanged(before,after):
    _,old=read_csv(Path(before)/'專案總表.csv');_,new=read_csv(Path(after)/'專案總表.csv')
    from au_ree_v2.official_location_adapters import native_state
    indexed={r['專案ID']:r for r in new}
    for row in old:
        if native_state(row.get('州省地區'))=='NT':
            if any(row.get(k,'')!=indexed[row['專案ID']].get(k,'') for k in ('緯度','經度')):
                raise ValueError('PARTIAL_PUBLICATION_NT_COORDINATES_CHANGED')


def presentation_changes(before,after,out):
    _,old=read_csv(Path(before)/'專案總表.csv');_,new=read_csv(Path(after)/'專案總表.csv')
    _,oldp=read_csv(Path(before)/'field_provenance.csv');_,newp=read_csv(Path(after)/'field_provenance.csv')
    rows={r['專案ID']:r for r in new}
    op={(p['project_id'],p['column']):p for p in oldp};np={(p['project_id'],p['column']):p for p in newp}
    changes=[]
    for row in old:
        pid=row['專案ID']
        for column,value in row.items():
            if not value:continue
            trace_changed=op.get((pid,column))!=np.get((pid,column))
            if value!=rows[pid][column] or trace_changed:
                if column!='總說明':raise ValueError('PARTIAL_EXISTING_PRESENTATION_CORE_CHANGED')
                changes.append(dict(project_id=pid,column=column,old_value=value,new_value=rows[pid][column],reason='DERIVED_PRESENTATION_NOTE_REFRESH_NOT_NEW_EVIDENCE',old_provenance=json.dumps(op.get((pid,column)),ensure_ascii=False,sort_keys=True),new_provenance=json.dumps(np.get((pid,column)),ensure_ascii=False,sort_keys=True)))
    write_csv(Path(out)/'changed_cells.csv',['project_id','column','old_value','new_value','reason','old_provenance','new_provenance'],changes)
    return dict(existing_note_value_changes=sum(r['old_value']!=r['new_value'] for r in changes),existing_note_provenance_changes=len(changes),note_changes_are_scientific_evidence_gain=False)


def protection(census):
    snapshot=prior.protected_snapshot(census)
    tracked=subprocess.check_output(['git','ls-files','-z','--','results'],cwd=REPO).decode('utf8').split('\0')
    for name in tracked:
        if name and not name.startswith('results/asx-current/') and (REPO/name).is_file():
            snapshot['protected'][name]=filehash(REPO/name)
    old=REPO/'work/round2-original-dirty-hashes.json'
    if old.exists():
        for name in json.loads(old.read_text('utf8')):
            snapshot['protected'][name]=filehash(REPO/name)
    return snapshot


def prepare(work,census,out=RESULT):
    work,census,out=map(lambda p:Path(p).resolve(),(work,census,out))
    if work.is_relative_to(census) or out.is_relative_to(census):raise ValueError('PARTIAL_OUTPUT_MUST_BE_OUTSIDE_CENSUS')
    if not out.is_relative_to(REPO/'results'):raise ValueError('PARTIAL_REPORT_MUST_BE_IN_REPO_RESULTS')
    if work.exists() or out.exists():raise ValueError('PARTIAL_PUBLICATION_FRESH_DIRECTORIES_REQUIRED')
    os.chdir(REPO);sys.addaudithook(prior.offline_guard)
    decisions=json.loads((REPO/'config/researcher_rule_decisions.json').read_text('utf8'))
    decision=approval(decisions);implementation=tested_implementation()
    snapshot=protection(census);current=tree_hashes(REPO/'results/asx-current')
    work.mkdir(parents=True);out.mkdir(parents=True)
    write_json(out/'protected_files.json',snapshot)
    write_json(out/'prepublication_current_hashes.json',current)
    shutil.copytree(REPO/'results/asx-current',out/'prepublication-current')
    historical=work/'baseline-decisions.json'
    historical.write_bytes(subprocess.check_output(['git','show',prior.BASELINE+':config/researcher_rule_decisions.json'],cwd=REPO))
    passes={}
    for pass_name in ('a','b'):
        print('Full independent offline partial-publication reconstruction:',pass_name,flush=True)
        baseline=prior.source_replay(work/pass_name,census,historical)
        before=baseline
        for stage in 'ABCD':
            fills,queue,extra=collect(stage,before,decisions,REPO)
            after=work/pass_name/stage
            apply_fills(before,after,fills,decisions,REPO)
            identical_replays(after,REPO/f'results/round2-{stage}-2026-11-11/projection')
            before=after
        additions,changes=compare_projections(baseline,before)
        if len(additions)!=72 or changes:raise ValueError('PARTIAL_PUBLICATION_ONLY_PRIOR_72_CELLS')
        nt_unchanged(baseline,before)
        passes[pass_name]=before
        prior.verify_protected(snapshot)
    hashes=identical_replays(passes['a'],passes['b'])
    shutil.copytree(passes['a'],out/'projection')
    for name in ('presentation-a','presentation-b'):convert_summary(out/'projection',out/name)
    presentation=tree_hashes(out/'presentation-a')
    if presentation!=tree_hashes(out/'presentation-b'):raise ValueError('PARTIAL_PRESENTATION_REPLAY_MISMATCH')
    note_changes=presentation_changes(out/'prepublication-current',out/'presentation-a',out)
    if tree_hashes(REPO/'results/asx-current')!=current:raise ValueError('CURRENT_CHANGED_DURING_VALIDATION')
    xml=out/'offline-tests.xml'
    result=subprocess.run([sys.executable,str(REPO/'tools/run_offline_regression.py'),'--fixture-root',str(census),'--overlay',str(work/'regression-overlay'),'--junitxml',str(xml)],cwd=REPO)
    if result.returncode:raise ValueError('PARTIAL_FULL_REGRESSION_FAILED')
    tests=prior.tests_pass(xml)
    if tested_implementation()!=implementation:raise ValueError('PARTIAL_IMPLEMENTATION_CHANGED_DURING_VALIDATION')
    prior.verify_protected(snapshot)
    if tree_hashes(REPO/'results/asx-current')!=current:raise ValueError('CURRENT_CHANGED_DURING_VALIDATION')
    receipt=dict(version='round2-authorized-partial-publication-v1',decision=decision,
        status='VALIDATED_PENDING_EXPLICIT_PUBLISH',published=False,task_c_acceptance=STATUS,
        nt_real_control_point_validated=False,nt_coordinates_unchanged=True,new_evidence_cells=72,
        independent_full_source_rebuilds=2,independent_presentation_rebuilds=2,
        core_output_hashes=hashes,presentation_output_hashes=presentation,
        implementation_sha256=implementation,researcher_decisions_sha256=filehash(REPO/'config/researcher_rule_decisions.json'),
        census_sha256=snapshot['census_sha256'],core_coverage=metrics(out/'projection'),
        tests=tests,presentation_note_changes=note_changes,network_requests=0,existing_conclusion='INCOMPLETE/CONTINUE_UNCHANGED')
    write_json(out/'validation.json',receipt)
    write_json(out/'rebuild_receipt.json',receipt)
    (out/'README.md').write_text('# 第二輪經研究者同意部分發布\n\n使用者在被告知 NT 座標基準與真實控制點驗收未完成後，指示「更新總表」。本次僅發布已驗證的 72 格，不新增任何 NT 座標。\n\nC 驗收狀態為 PARTIAL_NT_ACCEPTANCE_NOT_MET，NT metadata 與真實控制點驗收仍未完成，不宣稱完整驗收。其他條件包含兩次完整離線來源重建、兩次呈現重建及全套回歸測試。所有既有核心數值、provenance、Census、inventory、凍結歷史及原 INCOMPLETE／CONTINUE 結論不變。舊 A–D／總結收據保留為發布前歷史。總說明屬衍生呈現，其文字／provenance 更新另列 changed_cells.csv，不計入新增 72 格證據。\n',encoding='utf8')
    return receipt


def validate_publication_inputs(out):
    out=Path(out)
    if (out/'publication_receipt.json').exists():raise ValueError('PARTIAL_ALREADY_PUBLISHED_CHECK_RECEIPT')
    receipt=json.loads((out/'validation.json').read_text('utf8'))
    approval(json.loads((REPO/'config/researcher_rule_decisions.json').read_text('utf8')))
    if receipt.get('decision')!=approval(json.loads((REPO/'config/researcher_rule_decisions.json').read_text('utf8'))):raise ValueError('PARTIAL_APPROVAL_CHANGED')
    if receipt.get('independent_full_source_rebuilds')!=2 or receipt.get('independent_presentation_rebuilds')!=2 or receipt.get('new_evidence_cells')!=72:raise ValueError('PARTIAL_REPLAY_ACCEPTANCE_REQUIRED')
    if receipt.get('task_c_acceptance')!=STATUS or receipt.get('nt_real_control_point_validated') is not False or receipt.get('nt_coordinates_unchanged') is not True:raise ValueError('PARTIAL_NT_STATUS_REQUIRED')
    if tested_implementation()!=receipt['implementation_sha256']:raise ValueError('PARTIAL_ACCEPTED_IMPLEMENTATION_CHANGED')
    if prior.tests_pass(out/'offline-tests.xml')!=receipt['tests']:raise ValueError('PARTIAL_TEST_RECEIPT_CHANGED')
    if {n:filehash(out/'projection'/n) for n in FILES}!=receipt['core_output_hashes']:raise ValueError('PARTIAL_CORE_CHANGED')
    for name in ('presentation-a','presentation-b'):
        if tree_hashes(out/name)!=receipt['presentation_output_hashes']:raise ValueError('PARTIAL_PRESENTATION_CHANGED')
    prior.verify_protected(json.loads((out/'protected_files.json').read_text('utf8')))
    if tree_hashes(REPO/'results/asx-current')!=json.loads((out/'prepublication_current_hashes.json').read_text('utf8')):raise ValueError('PARTIAL_CURRENT_CHANGED_SINCE_VALIDATION')
    return receipt


def publish(out=RESULT):
    out=Path(out).resolve();os.chdir(REPO);sys.addaudithook(prior.offline_guard)
    receipt=validate_publication_inputs(out)
    target=REPO/'results/asx-current'
    for source in (out/'presentation-a').iterdir():
        if source.is_file():shutil.copyfile(source,target/source.name)
    audited=audit_summary(target)
    validation=dict(receipt,published=True,status='PUBLISHED_USER_AUTHORIZED_PARTIAL_NT_PENDING',delivery=out.relative_to(REPO).as_posix(),presentation_audit=audited)
    write_json(target/'validation.json',validation)
    readme=(out/'README.md').read_text('utf8')+'\n目前狀態：已按使用者同意部分發布。原53欄證據口徑 2,141／4,929（43.44%）；呈現欄總說明不計為新增證據。source_consistency.csv 保留為既有來源一致性診斷，不是本輪覆蓋率或完整 NT 驗收證明。\n'
    (target/'README.md').write_text(readme,encoding='utf8')
    (target/'REVIEW.md').write_text(readme,encoding='utf8')
    write_json(target/'publication_status.json',dict(published=True,status=validation['status'],task_c_acceptance=STATUS,nt_real_control_point_validated=False,decision_id=DECISION_ID))
    final=dict(validation,current_output_hashes=tree_hashes(target))
    write_json(out/'publication_receipt.json',final)
    prior.verify_protected(json.loads((out/'protected_files.json').read_text('utf8')))
    return final


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work',type=Path)
    parser.add_argument('--census-root',type=Path,default=REPO.parent/'AU_REE_V2')
    parser.add_argument('--out',type=Path,default=RESULT)
    parser.add_argument('--publish-current',action='store_true')
    args=parser.parse_args()
    if args.work:prepare(args.work,args.census_root,args.out)
    elif not args.publish_current:parser.error('--work or --publish-current is required')
    if args.publish_current:publish(args.out)
