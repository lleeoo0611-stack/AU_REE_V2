"""Freeze/check local evidence for the four engineering changes; never acquire sources."""
import argparse
import csv
import json
import shutil
import subprocess
from pathlib import Path
from au_ree_v2.store import filehash

ROOT = Path(__file__).resolve().parents[1]
RECEIPTS = ROOT/'results/convergence-codebook'
LOCAL = ROOT/'work/convergence-engineering/baseline'
DATABASE = ROOT/'../AU_REE_V2/work/phase22/verified-performance-v3/isolated-round-0/after/canonical.sqlite'


def read(path):
    with path.open(encoding='utf-8-sig', newline='') as handle:
        return list(csv.DictReader(handle))


def freeze():
    path = RECEIPTS/'baseline.json'
    if path.exists():
        raise ValueError('BASELINE_ALREADY_FROZEN')
    tracked = subprocess.check_output(['git', 'ls-files', '-z', 'results'], cwd=ROOT).decode().split('\0')
    history = {p:filehash(ROOT/p) for p in tracked if p.startswith('results/asx') and not p.startswith('results/asx-current/')
               and not p.endswith('/LATEST.md')}
    LOCAL.mkdir(parents=True, exist_ok=False)
    for p in (ROOT/'results/asx-current').iterdir():
        if p.is_file(): shutil.copyfile(p, LOCAL/p.name)
    rows = read(LOCAL/'專案總表.csv')
    assert len(rows) == 93 and len(rows[0]) == 53
    assert sum(bool(v) for r in rows for v in r.values()) == 1944
    value = dict(version='convergence-engineering-baseline-v1',
                 commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT).decode().strip(),
                 rows=93, columns=53, filled_cells=1944, blank_cells=2985,
                 database_sha256=filehash(DATABASE), historical_files=history,
                 protected_csv_sha256={n:filehash(LOCAL/n) for n in ('專案總表.csv','field_provenance.csv','census_inventory.csv')},
                 review_ledger_sha256={p.name:filehash(p) for p in (ROOT/'config').glob('asx_*reviews.json')})
    RECEIPTS.mkdir(exist_ok=True, parents=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    return value


def verify(current=None):
    value=json.loads((RECEIPTS/'baseline.json').read_text('utf8'))
    current=Path(current) if current else ROOT/'results/asx-current'
    assert filehash(DATABASE)==value['database_sha256'], 'CENSUS_CHANGED'
    for p, sha in value['historical_files'].items():
        assert filehash(ROOT/p)==sha, 'HISTORY_CHANGED:'+p
    for name, sha in value['review_ledger_sha256'].items():
        assert filehash(ROOT/'config'/name)==sha, 'REVIEW_LEDGER_CHANGED:'+name
    for name, sha in value['protected_csv_sha256'].items():
        assert filehash(current/name)==sha, 'PROTECTED_CSV_CHANGED:'+name
    return dict(passed=True, protected_filled_cells=1944, cell_values_and_provenance_byte_identical=True,
                census_sha256=value['database_sha256'], census_unchanged=True,
                historical_files_unchanged=len(value['historical_files']),review_ledgers_unchanged=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--freeze',action='store_true')
    parser.add_argument('--current')
    args=parser.parse_args()
    result=freeze() if args.freeze else verify(args.current)
    print(json.dumps({k:v for k,v in result.items() if k not in ('historical_files',)},ensure_ascii=False,indent=2))
