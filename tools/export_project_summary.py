"""Export the existing Census using the uploaded 52-column project table contract."""
import argparse,json
from au_ree_v2.project_summary import export_summary

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('root','database','run-dir','out'):p.add_argument('--'+key,required=True)
    p.add_argument('--template');p.add_argument('--as-of',default='2026-11-05')
    p.add_argument('--review-ledger');p.add_argument('--discovery-ledger');p.add_argument('--asset-root',action='append',default=[],help='NAME=PATH of immutable downloaded source assets')
    a=p.parse_args();assets=dict(v.split('=',1) for v in a.asset_root)
    r=export_summary(a.root,a.database,a.run_dir,a.out,a.template,a.as_of,a.review_ledger,assets,a.discovery_ledger)
    print(json.dumps(r,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
