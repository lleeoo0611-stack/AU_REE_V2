"""Fail before publication if controlled text carries credential-like URL parameters."""
import re
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from au_ree_v2.security import sensitive_reference
pattern=re.compile(r'[?&]\s*(?:access[_\s-]*token|api[_\s-]*key|token|signature|sig)\s*=',re.I)
roots=[ROOT/d for d in ('src','R','config','data','docs','results','tests','tools','.github')]
roots += list((ROOT/'work').glob('*/runs'))+[ROOT/'work/runs']
files=set(p for base in roots for p in base.rglob('*') if p.is_file())
files.update(p for p in ROOT.iterdir() if p.is_file())
paths=[p for p in sorted(files) if p.suffix.lower() in
       ('.json','.jsonl','.csv','.md','.yml','.yaml','.py','.r','.toml','.geojson','.html')]
found=[]
for path in paths:
    if sensitive_reference(path.read_text(encoding='utf-8-sig')):
        found.append(path.relative_to(ROOT).as_posix())
if found:raise SystemExit('Credential-like URL parameters: '+', '.join(found))
for manifest in (ROOT/'results').glob('*/provenance.json'):
    recorded=json.loads(manifest.read_text(encoding='utf-8'))
    for name,sha in recorded['files'].items():
        target=manifest.parent/name
        if hashlib.sha256(target.read_bytes()).hexdigest()!=sha:
            raise SystemExit('Published output checksum mismatch: '+str(target.relative_to(ROOT)))
print('Publication scan passed:',len(paths),'text artifacts')
