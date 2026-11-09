"""Append source-verified ASX codes; explicitly merge only same-code same-project rows."""
import argparse,json
from au_ree_v2.project_identity import extend_summary

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for key in ['input','out','identity-ledger']:p.add_argument('--'+key,required=True)
    p.add_argument('--asset-root',action='append',required=True);a=p.parse_args()
    r=extend_summary(a.input,a.out,a.identity_ledger,dict(v.split('=',1) for v in a.asset_root))
    print(json.dumps({k:r[k] for k in ['rows','columns','validated_asx_codes','identity_merges']},ensure_ascii=False,indent=2))
