"""Restore a full cycle review from its hash-checked difference chain, offline."""
import argparse
from pathlib import Path
from au_ree_v2.review_storage import restore_review,sha


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--review',required=True);parser.add_argument('--out',required=True)
    args=parser.parse_args();out=Path(args.out)
    if out.exists():raise ValueError('RESTORE_OUTPUT_EXISTS')
    raw=restore_review(args.review);out.parent.mkdir(parents=True,exist_ok=True);out.write_bytes(raw)
    print(sha(raw))
