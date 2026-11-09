"""Capture explicitly located public research sources with bounded, replayable receipts."""
import argparse, hashlib, json
from pathlib import Path
from urllib.parse import urlsplit
from au_ree_v2.acquisition import request, failure_details
from au_ree_v2.asx import is_asx_document, fetch_pdf
from au_ree_v2.security import sensitive_reference
from au_ree_v2.store import filehash


def capture(config, out):
    cfg=json.loads(Path(config).read_text('utf8'));out=Path(out)
    (out/'data/snapshots').mkdir(parents=True,exist_ok=True)
    target=out/'downloads.json'
    rows=json.loads(target.read_text('utf8')) if target.exists() else []
    requests={r['url']:r for r in cfg['documents']}
    if len(requests)!=len(cfg['documents']):raise ValueError('RESEARCH_DUPLICATE_URL')
    for old in rows:
        if old['url'] not in requests:raise ValueError('RESEARCH_CAPTURE_SCOPE_CHANGED')
        if any(old.get(k)!=requests[old['url']].get(k) for k in ('kind','key')):raise ValueError('RESEARCH_CAPTURE_SCOPE_CHANGED')
        if old.get('path') and filehash(out/old['path'])!=old['document_sha256']:
            raise ValueError('RESEARCH_CAPTURE_HASH_MISMATCH')
    done={r['url'] for r in rows}
    for spec in cfg['documents']:
        if spec['url'] in done:continue
        url=spec['url'];parts=urlsplit(url)
        if spec['kind'] not in ('html','pdf'):raise ValueError('RESEARCH_KIND_REQUIRED')
        if (parts.scheme!='https' or not parts.hostname or parts.username or parts.password or
            parts.port not in (None,443) or sensitive_reference(url)):
            raise ValueError('RESEARCH_PUBLIC_HTTPS_REQUIRED')
        row=dict(spec)
        def archive(raw, resolved, suffix):
            sha=hashlib.sha256(raw).hexdigest();p=out/'data/snapshots'/(sha+suffix)
            if not p.exists():p.write_bytes(raw)
            if filehash(p)!=sha:raise ValueError('RESEARCH_CAPTURE_HASH_MISMATCH')
            return sha
        try:
            if is_asx_document(url):
                raw,headers,receipt=fetch_pdf(url,archive=archive)
                resolved=receipt['resolved_url'];row['asx_acquisition']=receipt
            else:
                hosts={parts.hostname,*spec.get('redirect_hosts',[])}
                raw,headers=request(url,allowed_hosts=hosts,max_attempts=1,timeout=25,
                    max_bytes=40*1024*1024 if spec['kind']=='pdf' else 3*1024*1024,min_interval=1)
                resolved=headers.get('X-Resolved-URL',url)
            suffix='.pdf' if spec['kind']=='pdf' else '.html'
            sha=archive(raw,resolved,suffix)
            row.update(document_sha256=sha,path='data/snapshots/'+sha+suffix,resolved_url=resolved)
            if spec['kind']=='pdf':
                import pymupdf
                if not raw.startswith(b'%PDF-'):raise ValueError('RESEARCH_NOT_PDF')
                with pymupdf.open(stream=raw,filetype='pdf') as d:
                    row['physical_pages']=len(d)
                    if not any(p.get_text().strip() for p in d):raise ValueError('RESEARCH_NO_NATIVE_TEXT')
                row['status']='PDF_ACQUIRED'
            else:
                import re
                if re.search(rb'request\s+rejected|access\s+denied|verify\s+you\s+are\s+human',raw,re.I):
                    raise ValueError('RESEARCH_HTTP200_DENIAL')
                row['status']='HTML_CAPTURED'
        except Exception as exc:
            row.update(status='UNAVAILABLE',**failure_details(exc))
        rows.append(row);target.write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
        print(row['status'],row['key'],flush=True)
    return rows


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--requests',required=True);p.add_argument('--out',required=True)
    a=p.parse_args();capture(a.requests,a.out)


if __name__=='__main__':main()
