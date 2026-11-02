"""Fail before publication if controlled text carries credential-like URL parameters."""
import re
import subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
pattern=re.compile(r'[?&]\s*(?:access[_\s-]*token|api[_\s-]*key|token|signature|sig)\s*=',re.I)
paths=[p for p in ROOT.rglob('*') if p.is_file() and '.git' not in p.parts
       and p.suffix.lower() in ('.json','.jsonl','.csv','.md','.yml','.yaml','.py','.r','.toml','.geojson')
       and not ('tests' in p.parts and 'work' in p.parts)]
found=[]
for path in paths:
    if pattern.search(path.read_text(encoding='utf-8-sig')):
        found.append(path.relative_to(ROOT).as_posix())
if found:raise SystemExit('Credential-like URL parameters: '+', '.join(found))
print('Publication scan passed:',len(paths),'text artifacts')
