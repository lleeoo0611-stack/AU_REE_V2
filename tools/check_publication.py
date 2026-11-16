"""Fail before publication if controlled text carries credential-like URL parameters."""
import re
import hashlib
import json
import subprocess
import sys
import io
import zipfile
import gzip
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from au_ree_v2.security import sensitive_reference
pattern=re.compile(r'[?&]\s*(?:access[_\s-]*token|api[_\s-]*key|token|signature|sig)\s*=',re.I)
roots=[ROOT/d for d in ('src','R','config','data','docs','results','tests','tools','.github')]
# Only the publication tree is a release payload. Ignored local historical runs
# may retain originals and must not be treated as files intended for upload.
files=set(p for base in roots for p in base.rglob('*') if p.is_file())
files.update(p for p in ROOT.iterdir() if p.is_file())
paths=[p for p in sorted(files) if p.suffix.lower() in
       ('.json','.jsonl','.csv','.md','.yml','.yaml','.py','.r','.toml','.geojson','.html','.response','.upstream','.zip','.gz')]
found=[]
manifest_data=json.loads((ROOT/'data/manifest.json').read_text(encoding='utf-8'))
escaped_originals={ROOT/s['path'] for s in manifest_data['snapshots'] if s.get('encoding_errors')=='backslashreplace'}
private_shas={s['unpublished_original_sha256'] for s in manifest_data['snapshots'] if s.get('publication_derivative')}
tracked=set(subprocess.check_output(['git','ls-files'],cwd=ROOT,text=True).splitlines())
staged=set(subprocess.check_output(['git','diff','--cached','--name-only'],cwd=ROOT,text=True).splitlines())
for path in paths:
    raw=path.read_bytes()
    if hashlib.sha256(raw).hexdigest() in private_shas:
        relative=path.relative_to(ROOT).as_posix()
        if relative in tracked or relative in staged:raise SystemExit('Unpublished original included in Git payload: '+relative)
        ignored=subprocess.run(['git','check-ignore','-q','--',relative],cwd=ROOT).returncode==0
        if not ignored:raise SystemExit('Unpublished original must be explicitly ignored: '+relative)
        continue
    if raw.startswith(b'\x1f\x8b'):
        content=gzip.decompress(raw).decode('utf-8-sig',errors='strict')
    elif raw.startswith(b'PK\x03\x04'):
        # Resource batch exports may include CSV + PDF licence/data dictionary.
        # Inspect their contents, including a ZIP stored as an original response.
        parts=[]
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            for member in archive.infolist():
                if member.is_dir():continue
                if member.file_size>50_000_000:raise SystemExit('Archive member exceeds publication scan budget')
                body=archive.read(member)
                if body.startswith(b'%PDF'):
                    import pymupdf
                    with pymupdf.open(stream=body,filetype='pdf') as doc:parts.append('\n'.join(page.get_text() for page in doc))
                else:parts.append(body.decode('utf-8-sig',errors='strict'))
        content='\n'.join(parts)
    elif raw.startswith(b'%PDF'):
        import pymupdf
        with pymupdf.open(stream=raw,filetype='pdf') as doc:content='\n'.join(page.get_text() for page in doc)
    else:content=raw.decode('utf-8-sig',errors='backslashreplace' if path in escaped_originals else 'strict')
    if sensitive_reference(content):
        found.append(path.relative_to(ROOT).as_posix())
if found:raise SystemExit('Credential-like URL parameters: '+', '.join(found))
for manifest in (ROOT/'results').glob('*/provenance.json'):
    recorded=json.loads(manifest.read_text(encoding='utf-8'))
    for name,sha in recorded['files'].items():
        target=manifest.parent/name
        if hashlib.sha256(target.read_bytes()).hexdigest()!=sha:
            raise SystemExit('Published output checksum mismatch: '+str(target.relative_to(ROOT)))
print('Publication scan passed:',len(paths),'text artifacts')
