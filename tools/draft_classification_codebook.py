"""Produce a DRAFT inventory from existing text cells; never approve a codebook."""
import argparse
import csv
import json
from pathlib import Path
from au_ree_v2.classification import draft_codebook


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--table',required=True)
    parser.add_argument('--out',required=True)
    args=parser.parse_args();out=Path(args.out)
    if out.exists():raise ValueError('DRAFT_OUTPUT_EXISTS_USE_NEW_PATH_TO_PRESERVE_REVIEW')
    with Path(args.table).open(encoding='utf-8-sig',newline='') as f:rows=list(csv.DictReader(f))
    cfg=draft_codebook(rows);out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(cfg,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps({g:dict(distinct=len(cfg[g]),unmapped=sum(e['status']=='UNMAPPED' for e in cfg[g].values()),
            occurrences=sum(e['count'] for e in cfg[g].values())) for g in ('deposit_type','development_stage')},indent=2))


if __name__=='__main__':main()
