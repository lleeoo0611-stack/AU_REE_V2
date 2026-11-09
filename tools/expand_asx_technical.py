"""Bounded ASX technical-document discovery from existing Census issuer identities."""
import argparse,hashlib,json,re,shutil
from pathlib import Path
from urllib.parse import urljoin,urldefrag
from au_ree_v2.acquisition import request,failure_details
from au_ree_v2.asx import fetch_pdf,is_asx_document,HOSTS
from au_ree_v2.discovery import Links
from au_ree_v2.pdf_extract import project_registry,publication_date,_matches
from au_ree_v2.store import filehash

def archive_rejected(raw):
    """An HTTP200 denial page is an acquisition failure, never an empty archive."""
    return bool(re.search(rb'request\s+rejected|access\s+denied|verify\s+you\s+are\s+human',raw,re.I))

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',required=True);p.add_argument('--out',required=True)
    p.add_argument('--max-documents',type=int,default=30)
    p.add_argument('--years',type=int,nargs='+',default=[2026,2025])
    p.add_argument('--issuer-code',action='append',default=[],help='Additional issuer archive search context only; never project attribution')
    a=p.parse_args()
    if any(y<2000 or y>2026 for y in a.years):p.error('years must be within 2000..2026')
    if any(not re.fullmatch(r'[A-Z][A-Z0-9]{1,4}',c) for c in a.issuer_code):p.error('invalid ASX issuer code')
    root=Path(a.root);out=Path(a.out);(out/'data/snapshots').mkdir(parents=True,exist_ok=True)
    manifest=json.loads((root/'data/manifest.json').read_text('utf8'))['snapshots'];sources={s['key']:s for s in manifest}
    known={s['sha256'] for s in manifest if s['kind']=='pdf'};codes={}
    import pymupdf
    for project in project_registry(root):
        s=sources.get(project['identity_source'])
        if not s:continue
        found={s['asx_code']} if s.get('asx_code') else set()
        if not found and s['kind']=='pdf':
            if filehash(root/s['path'])!=s['sha256']:raise ValueError('IDENTITY_SOURCE_HASH_MISMATCH')
            with pymupdf.open(root/s['path']) as doc:found=set(re.findall(r'\bASX\s*[:|]\s*([A-Z][A-Z0-9]{1,4})\b',doc[0].get_text()))
        if len(found)==1:codes.setdefault(next(iter(found)),[]).append(project['entity_id'])
    for code in a.issuer_code:codes.setdefault(code,[])
    discovered={};receipts=[]
    def archive(raw,url,suffix):
        sha=hashlib.sha256(raw).hexdigest();path=out/'data/snapshots'/(sha+suffix)
        if not path.exists():path.write_bytes(raw)
        if filehash(path)!=sha:raise ValueError('SNAPSHOT_HASH_MISMATCH')
        return sha
    archive_file=out/'archive_discovery.json'
    if archive_file.exists():
        prior=json.loads(archive_file.read_text('utf8'));discovered={r['url']:r for r in prior['documents']};receipts=prior['receipts']
        for receipt in receipts:
            if receipt.get('sha256'):
                cached=out/'data/snapshots'/(receipt['sha256']+'.html')
                if filehash(cached)!=receipt['sha256']:raise ValueError('ARCHIVE_SNAPSHOT_HASH_MISMATCH')
                if archive_rejected(cached.read_bytes()):
                    receipt.update(previous_status=receipt.get('previous_status',receipt['status']),status='UNAVAILABLE',failure_status='ARCHIVE_HTTP200_REJECTION')
    visited={r['url'] for r in receipts}
    for code,projects in sorted(codes.items()):
        for year in sorted(set(a.years),reverse=True):
            url=f'https://www.asx.com.au/asx/v2/statistics/announcements.do?by=asxCode&asxCode={code}&timeframe=Y&year={year}'
            if url in visited:continue
            receipt=dict(url=url,code=code,year=year,project_context=projects)
            try:
                raw,_=request(url,max_attempts=1,min_interval=1,timeout=15,max_bytes=3*1024*1024,allowed_hosts=HOSTS)
                sha=archive(raw,url,'.html');receipt['sha256']=sha
                if archive_rejected(raw):raise ValueError('ARCHIVE_HTTP200_REJECTION')
                parser=Links();parser.feed(raw.decode('utf8',errors='replace'))
                for href,label in parser.links:
                    target=urldefrag(urljoin(url,href))[0];date=parser.link_dates.get(href)
                    if not is_asx_document(target) or not re.search(r'mineral resource|\bMRE\b|metallurg|feasibility|\bPFS\b|\bDFS\b|scoping|JORC|recovery|production',label,re.I):continue
                    if date and date>'2026-11-05':continue
                    discovered[target]=dict(url=target,title=' '.join(label.split()),publication_date=date,code=code,
                        project_context=projects,origin_url=url,origin_sha256=sha)
                receipt.update(status='PARSED',sha256=sha)
            except Exception as e:
                receipt.update(status='UNAVAILABLE',**failure_details(e))
                if str(e)=='ARCHIVE_HTTP200_REJECTION':receipt['failure_status']='ARCHIVE_HTTP200_REJECTION'
            receipts.append(receipt);archive_file.write_text(json.dumps(dict(codes=codes,receipts=receipts,documents=list(discovered.values())),ensure_ascii=False,indent=2)+'\n',encoding='utf8')
            print('archive',code,year,receipt['status'],len(discovered),flush=True)
    archive_file.write_text(json.dumps(dict(codes=codes,receipts=receipts,documents=list(discovered.values())),ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    downloads_file=out/'downloads.json';downloaded=json.loads(downloads_file.read_text('utf8')) if downloads_file.exists() else []
    done={r['url'] for r in downloaded}
    def priority(r):
        t=r['title'];score=4*bool(re.search(r'mineral resource|\bMRE\b',t,re.I))+3*bool(re.search(r'feasibility|\bPFS\b|\bDFS\b|scoping',t,re.I))+bool(re.search(r'metallurg|recovery',t,re.I))
        return (-score,r.get('publication_date') or '',r['url'])
    # Two per issuer first, then fill remaining budget, keeping the full discovered inventory.
    ordered=sorted(discovered.values(),key=priority);selected=[];counts={}
    for limit in (2,1000):
        for r in ordered:
            if r in selected or counts.get(r['code'],0)>=limit:continue
            selected.append(r);counts[r['code']]=counts.get(r['code'],0)+1
    for row in selected[:a.max_documents]:
        if row['url'] in done:continue
        r=dict(row)
        if shutil.disk_usage(out).free<170*1024*1024:r.update(status='DEFERRED',failure_status='LOCAL_DISK_RESERVE')
        else:
            try:
                raw,_,receipt=fetch_pdf(row['url'],archive=archive);sha=archive(raw,receipt['resolved_url'],'.pdf')
                r.update(status='PDF_ACQUIRED',document_sha256=sha,path='data/snapshots/'+sha+'.pdf',asx_acquisition=receipt,already_in_manifest=sha in known)
            except Exception as e:r.update(status='UNAVAILABLE',**failure_details(e))
        downloaded.append(r);downloads_file.write_text(json.dumps(downloaded,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
        print('document',len(downloaded),r['status'],r['title'][:80],flush=True)
    inventory=[];registry=project_registry(root)
    for r in downloaded:
        if r['status']!='PDF_ACQUIRED':continue
        path=out/r['path']
        if filehash(path)!=r['document_sha256']:raise ValueError('DOCUMENT_HASH_MISMATCH')
        with pymupdf.open(path) as doc:
            pages=[dict(physical_page=p.number+1,text=p.get_text(sort=True)) for p in doc]
        data=dict(version='native-page-text-v1',source_sha256=r['document_sha256'],url=r['url'],pages=pages)
        raw=(json.dumps(data,ensure_ascii=False,sort_keys=True)+'\n').encode();sha=archive(raw,r['url'],'.pages.json')
        projects=[p['entity_id'] for p in _matches(pages[0]['text'][:2500],registry)]
        inventory.append(dict(url=r['url'],title=r['title'],source_sha256=r['document_sha256'],publication_date=r.get('publication_date'),
            native_header_date=publication_date(pages[0]['text']),physical_pages=len(pages),
            first_page_project_name_matches=projects,attribution='EXACT_NAME_SEARCH_CONTEXT_NOT_IDENTITY_OR_RESOURCE_ADMISSION',
            native_text_path='data/snapshots/'+sha+'.pages.json',native_text_sha256=sha,already_in_manifest=r['already_in_manifest']))
    (out/'native_inventory.json').write_text(json.dumps(inventory,ensure_ascii=False,indent=2)+'\n',encoding='utf8')

if __name__=='__main__':main()
