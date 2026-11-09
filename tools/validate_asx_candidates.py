import argparse,json
from pathlib import Path
from au_ree_v2.store import filehash
from au_ree_v2.asx_validation import audit_candidate_cohort,compare_summaries

def main():
    p=argparse.ArgumentParser(description='Audit all frozen candidates and compare reviewed summary with baseline')
    for key in ('root','audit-dir','review-ledger','before','after','out'):p.add_argument('--'+key,required=True)
    p.add_argument('--allow-cohort-expansion',action='store_true',help='Report fills in the original cohort separately from explicitly reviewed new project rows')
    a=p.parse_args()
    if json.loads((Path(a.after)/'summary.json').read_text('utf8')).get('review_ledger_sha256')!=filehash(a.review_ledger):raise ValueError('VALIDATED_SUMMARY_LEDGER_MISMATCH')
    c=audit_candidate_cohort(a.root,a.audit_dir,a.review_ledger,a.out);s=compare_summaries(a.before,a.after,a.out,a.allow_cohort_expansion)
    print(json.dumps(dict(candidates=c,increment=s),ensure_ascii=False,indent=2))

if __name__=='__main__':main()
