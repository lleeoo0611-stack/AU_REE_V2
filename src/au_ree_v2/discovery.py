"""Bounded official/issuer link discovery; raw bytes precede any observations."""
import hashlib
import json
import re
import io
from pypdf import PdfReader
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlsplit, urldefrag
from .acquisition import request
from .security import sensitive_reference


class Links(HTMLParser):
    def __init__(self):
        super().__init__(); self.links=[]; self.current=None
    def handle_starttag(self, tag, attrs):
        if tag=='a': self.current=[dict(attrs).get('href',''),'']
    def handle_data(self, data):
        if self.current is not None:self.current[1]+=data
    def handle_endtag(self, tag):
        if tag=='a' and self.current is not None:
            self.links.append(self.current); self.current=None


def candidates(raw, seed):
    parser=Links(); parser.feed(raw.decode('utf-8',errors='replace'))
    rows={}
    for href,label in parser.links:
        url=urldefrag(urljoin(seed['url'],href))[0]
        host=urlsplit(url).hostname
        if urlsplit(url).scheme!='https' or host not in seed['allowed_hosts'] or sensitive_reference(url):continue
        if not re.search(seed.get('pattern',r'\.pdf(?:[?\s]|$)'),url+' '+label,re.I):continue
        key=hashlib.sha256(url.encode()).hexdigest()
        rows[key]={'candidate_id':key,'url':url,'title':label.strip(),'seed_key':seed['key'],
                   'publication_date':None,'status':'DISCOVERED_NOT_OBSERVATION',
                   'project_id':seed.get('project_id'),'identity_status':'SOURCE_CONTEXT_ONLY_NOT_EQUIVALENCE'}
    return [rows[k] for k in sorted(rows)]


def discover(root, registry, fetch=request):
    root=Path(root); path=root/'data/manifest.json'
    manifest=json.loads(path.read_text(encoding='utf-8')); outcomes=[]; found=[]
    def save(raw, meta, suffix):
        sha=hashlib.sha256(raw).hexdigest(); dest=root/'data/snapshots'/(sha+suffix)
        if not dest.exists():dest.write_bytes(raw)
        now=datetime.now(timezone.utc).isoformat()
        entry={**meta,'sha256':sha,'path':dest.relative_to(root).as_posix(),'acquired_at':now,'available_date':now[:10]}
        if not any(s['key']==entry['key'] and s['sha256']==sha for s in manifest['snapshots']):manifest['snapshots'].append(entry)
        return sha
    for seed in registry['seeds']:
        try:
            raw,_=fetch(seed['url']); sha=save(raw,{'key':'discovery_'+seed['key'],'url':seed['url'],'kind':'discovery_html'},'.html')
            rows=candidates(raw,seed)
            for row in rows[:registry.get('max_documents_per_seed',10)]:
                row['discovery_sha256']=sha
                try:
                    doc,_=fetch(row['url'])
                    if not doc.startswith(b'%PDF'):raise ValueError('NOT_PDF')
                    row['document_sha256']=save(doc,{'key':'discovered_'+row['candidate_id'],'url':row['url'],'kind':'pdf','discovery_sha256':sha},'.pdf')
                    row['status']='SNAPSHOT_REQUIRES_DATED_SCOPE_EXTRACTION'
                    try:
                        reader=PdfReader(io.BytesIO(doc));row['physical_pages']=len(reader.pages)
                        row['text_quality']='REQUIRES_PAGE_VALIDATION_NO_AUTOMATIC_NUMERIC_EXTRACTION'
                    except Exception:
                        row['status']='SNAPSHOT_PDF_PARSE_FAILED'
                except Exception as exc:row['status']='DOWNLOAD_UNAVAILABLE';row['reason']=type(exc).__name__
                found.append(row)
            outcomes.append({'seed_key':seed['key'],'status':'PARSED','links_found':len(rows),'links_attempted':min(len(rows),registry.get('max_documents_per_seed',10)),'sha256':sha,'limitation':'STATIC_HTML_ONLY_NO_JAVASCRIPT_OR_PAGINATION'})
        except Exception as exc:outcomes.append({'seed_key':seed['key'],'status':'UNAVAILABLE','reason':type(exc).__name__})
    path.write_text(json.dumps(manifest,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    result={'version':'discovery-v1','sources':outcomes,'documents':found}
    (root/'data/discovery_latest.json').write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    return result
