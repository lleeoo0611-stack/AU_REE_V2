"""Create a fresh, reversible source-decimal presentation; does not publish."""
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from au_ree_v2.numeric_presentation import present
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source',required=True,type=Path);p.add_argument('--out',required=True,type=Path)
    a=p.parse_args();print(json.dumps(present(a.source,a.out,ROOT),ensure_ascii=False,indent=2))
