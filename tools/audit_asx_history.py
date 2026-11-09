"""Retest every historical ASX failure, then assess recovered candidate evidence."""
import argparse,json
from pathlib import Path
from au_ree_v2.asx_audit import retest,assess

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',required=True);p.add_argument('--out',required=True)
    p.add_argument('--assess-only',action='store_true');p.add_argument('--download-only',action='store_true')
    a=p.parse_args()
    if not a.assess_only:print(json.dumps(retest(a.root,a.out)['summary']),flush=True)
    if not a.download_only:assess(a.root,a.out)

if __name__=='__main__':main()
