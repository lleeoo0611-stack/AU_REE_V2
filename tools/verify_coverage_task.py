"""Accept two independent source replays and report additive coverage changes."""
import argparse
import csv
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO/'src'))
from au_ree_v2.coverage_task_audit import compare_projections,identical_replays,verify_protected,coverage
from au_ree_v2.iteration_review import audit_summary
from au_ree_v2.store import filehash


def verify(before,a,b,baseline,out,task,tests,core_receipt):
    before,a,b,out=map(Path,(before,a,b,out))
    protected=verify_protected(REPO,baseline)
    hashes=identical_replays(a,b)
    audit_summary(a);audit_summary(b)
    added,changed=compare_projections(before,a,allow_derived=True)
    outcomes=[]
    for path in tests:
        root=ET.parse(path).getroot()
        suites=[root] if root.tag=='testsuite' else list(root.findall('testsuite'))
        if not suites or any(int(s.get(k,'0')) for s in suites for k in ('failures','errors','skipped')):
            raise ValueError('COVERAGE_TESTS_NOT_ALL_PASSING:'+str(path))
        outcomes.append(dict(file=Path(path).name,sha256=filehash(path),tests=sum(int(s.get('tests','0')) for s in suites),failures=0,errors=0,skipped=0))
    decision_path=REPO/'config/researcher_rule_decisions.json'
    decisions=json.loads(decision_path.read_text('utf8'))
    receipt=json.loads(Path(core_receipt).read_text('utf8'))
    if receipt.get('independent_rebuilds')!=2 or receipt.get('projection_configuration_sha256',{}).get(decision_path.name)!=filehash(decision_path):
        raise ValueError('COVERAGE_REBUILD_DECISION_HASH_MISSING')
    if any(d.get('decided_by') for d in decisions['decisions']):
        raise ValueError('COVERAGE_REPORT_EXPECTS_UNAPPROVED_DEFAULT_CONFIGURATION')
    if task in ('task3','task2','task4'):
        identical_replays(before,a)
    out.mkdir(parents=True,exist_ok=True)
    fields=['project_id','project','column','old_value','new_value']
    for name,rows in [('new_cells.csv',added),('changed_cells.csv',changed)]:
        with (out/name).open('w',encoding='utf-8-sig',newline='') as h:
            w=csv.DictWriter(h,fields);w.writeheader();w.writerows(rows)
    result=dict(task=task,decided_by_default=None,decision_sha256=filehash(decision_path),
                before=coverage(before),after=coverage(a),new_cells=len(added),changed_cells=len(changed),
                independent_source_rebuilds=2,identical_six_output_files=True,
                core_rebuild_receipt_sha256=filehash(core_receipt),tests=outcomes,
                protection=protected,output_hashes=hashes,published_current=False)
    (out/'acceptance.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for arg in ('before','a','b','baseline','out','core-receipt'):p.add_argument('--'+arg,type=Path,required=True)
    p.add_argument('--task',choices=['task1','task3','task2','task4'],required=True)
    p.add_argument('--tests',type=Path,nargs='+',required=True)
    a=p.parse_args();print(json.dumps(verify(a.before,a.a,a.b,a.baseline,a.out,a.task,a.tests,a.core_receipt),ensure_ascii=False,indent=2))
