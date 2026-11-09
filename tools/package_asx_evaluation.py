import argparse,json
from au_ree_v2.asx_audit import package_evaluation

def main():
    p=argparse.ArgumentParser(description='Package ASX retest, research opportunities and Census summary provenance')
    for key in ('root','audit-dir','summary-dir','out'):p.add_argument('--'+key,required=True)
    a=p.parse_args();r=package_evaluation(a.root,a.audit_dir,a.summary_dir,a.out)
    print(json.dumps(dict(retrieval=r['retrieval'],candidate_count=r['candidate_count'],summary_rows=r['project_summary']['rows']),ensure_ascii=False))

if __name__=='__main__':main()
