"""Bounded official/issuer link discovery; raw bytes precede any observations."""
import hashlib
import json
import re
import io
from pypdf import PdfReader
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlsplit, urldefrag, quote
from .acquisition import request
from .security import sensitive_reference
from .store import filehash


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
        if seed.get('keywords') and not any(k.casefold() in (url+' '+label).casefold() for k in seed['keywords']):continue
        if not re.search(seed.get('pattern',r'\.pdf(?:[?\s]|$)'),url+' '+label,re.I):continue
        key=hashlib.sha256(url.encode()).hexdigest()
        rows[key]={'candidate_id':key,'url':url,'title':label.strip(),'seed_key':seed['key'],
                   'publication_date':None,'status':'DISCOVERED_NOT_OBSERVATION',
                   'project_id':seed.get('project_id'),'identity_status':'SOURCE_CONTEXT_ONLY_NOT_EQUIVALENCE'}
    return list(rows.values())  # Preserve issuer feed order; hashes are not chronology.


def discover(root, registry, fetch=request):
    root=Path(root); path=root/'data/manifest.json'
    manifest=json.loads(path.read_text(encoding='utf-8')); outcomes=[]; found=[]
    captured_urls={s['url'] for s in manifest['snapshots'] if s['kind']=='pdf'}
    def save(raw, meta, suffix):
        from .security import public_snapshot
        raw,redaction=public_snapshot(root,raw,suffix)
        meta={**meta,**redaction}
        sha=hashlib.sha256(raw).hexdigest(); dest=root/'data/snapshots'/(sha+suffix)
        if not dest.exists():dest.write_bytes(raw)
        if filehash(dest)!=sha:raise ValueError('IMMUTABLE_SNAPSHOT_CONTENT_MISMATCH')
        now=datetime.now(timezone.utc).isoformat()
        entry={**meta,'sha256':sha,'path':dest.relative_to(root).as_posix(),'acquired_at':now,'available_date':now[:10]}
        if not any(s['key']==entry['key'] and s['sha256']==sha for s in manifest['snapshots']):manifest['snapshots'].append(entry)
        return sha
    queue=[]
    for seed in registry['seeds']:
        queue.append(dict(seed))
        for query in seed.get('queries',[]):
            if seed.get('search_url_template'):queue.append(dict(seed,url=seed['search_url_template'].format(query=quote(query)),key=seed['key']+'_search_'+hashlib.sha256(query.encode()).hexdigest()[:12]))
    seen_pages=set();seen_documents=set();page_counts={};document_counts={}
    for seed in queue:
        if seed['url'] in seen_pages:continue
        seen_pages.add(seed['url'])
        family=seed.get('pagination_family',seed['key'])
        page_counts[family]=page_counts.get(family,0)+1
        if page_counts[family]>registry.get('max_pages_per_seed',3):continue
        try:
            raw,_=fetch(seed['url'])
            if raw.startswith(b'%PDF'):
                sha=save(raw,{'key':'discovery_'+seed['key'],'url':seed['url'],'kind':'pdf'},'.pdf')
                found.append({'candidate_id':hashlib.sha256(seed['url'].encode()).hexdigest(),'url':seed['url'],'seed_key':seed['key'],'publication_date':None,'document_sha256':sha,'status':'DIRECT_PDF_REQUIRES_DATED_SCOPE_EXTRACTION'})
                outcomes.append({'seed_key':seed['key'],'status':'DIRECT_PDF_CAPTURED','sha256':sha});continue
            sha=save(raw,{'key':'discovery_'+seed['key'],'url':seed['url'],'kind':'discovery_html'},'.html')
            parser=Links();parser.feed(raw.decode('utf-8',errors='replace'))
            for href,label in parser.links:
                url=urldefrag(urljoin(seed['url'],href))[0]
                if urlsplit(url).scheme=='https' and urlsplit(url).hostname in seed['allowed_hosts'] and not sensitive_reference(url) and (re.search(r'next|older',label,re.I) or re.search(r'/page/\d|[?&]page=',url)):
                    queue.append(dict(seed,url=url,key=family+'_page_'+hashlib.sha256(url.encode()).hexdigest()[:12],pagination_family=family,queries=[]))
                elif (seed.get('detail_pattern') and urlsplit(url).scheme=='https'
                      and urlsplit(url).hostname in seed['allowed_hosts'] and not sensitive_reference(url)
                      and re.search(seed['detail_pattern'],url)
                      and any(k.casefold() in (label+' '+url).casefold() for k in seed.get('keywords',[]))):
                    queue.append(dict(seed,url=url,key=family+'_detail_'+hashlib.sha256(url.encode()).hexdigest()[:12],pagination_family=family,queries=[]))
            rows=candidates(raw,seed)
            rows=[r for r in rows if r['url'] not in seen_documents]
            rows.sort(key=lambda row:row['url'] in captured_urls)
            budget=max(0,registry.get('max_documents_per_seed',10)-document_counts.get(family,0))
            for row in rows[:budget]:
                document_counts[family]=document_counts.get(family,0)+1
                seen_documents.add(row['url'])
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
                        try:
                            import pymupdf
                            with pymupdf.open(stream=doc,filetype='pdf') as reader:row['physical_pages']=len(reader)
                            row['text_quality']='NATIVE_PYPDF_UNAVAILABLE_MUPDF_READABLE_REQUIRES_PAGE_VALIDATION'
                        except Exception:row['status']='SNAPSHOT_PDF_PARSE_FAILED'
                except Exception as exc:row['status']='DOWNLOAD_UNAVAILABLE';row['reason']=type(exc).__name__
                found.append(row)
            outcomes.append({'seed_key':seed['key'],'status':'PARSED','links_found':len(rows),'links_attempted':min(len(rows),budget),'sha256':sha,'limitation':'BOUNDED_STATIC_HTML_SEARCH_AND_LINKED_PAGINATION_NO_JAVASCRIPT'})
        except Exception as exc:outcomes.append({'seed_key':seed['key'],'status':'UNAVAILABLE','reason':type(exc).__name__})
    path.write_text(json.dumps(manifest,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    result={'version':'discovery-v2','sources':outcomes,'documents':found}
    (root/'data/discovery_latest.json').write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    return result
