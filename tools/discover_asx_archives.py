"""Capture explicit issuer/year archives including titles outside keyword filters.

Issuer codes are search context, never automatic project identity evidence.
"""
import argparse,hashlib,json,re
from pathlib import Path
from urllib.parse import urljoin,urldefrag
from au_ree_v2.acquisition import request,failure_details
from au_ree_v2.asx import HOSTS,is_asx_document
from au_ree_v2.discovery import Links
from au_ree_v2.store import filehash
def archive_rejected(raw):
    return bool(re.search(rb'request\s+rejected|access\s+denied|verify\s+you\s+are\s+human',raw,re.I))

def discover(codes,years,out,fetch=request,cutoff='2026-11-05'):
    out=Path(out);(out/'data/snapshots').mkdir(parents=True,exist_ok=True)
    target=out/'archive_discovery.json'
    result=json.loads(target.read_text('utf8')) if target.exists() else dict(codes=sorted(set(codes)),years=sorted(set(years)),receipts=[],documents=[])
    if result['codes']!=sorted(set(codes)) or result['years']!=sorted(set(years)):raise ValueError('ARCHIVE_SEARCH_SCOPE_CHANGED')
    for r in result['receipts']:
        if r.get('sha256') and filehash(out/'data/snapshots'/(r['sha256']+'.html'))!=r['sha256']:raise ValueError('ARCHIVE_HASH_MISMATCH')
    done={r['url'] for r in result['receipts']};documents={r['url']:r for r in result['documents']}
    for code in sorted(set(codes)):
        if not re.fullmatch('[A-Z][A-Z0-9]{1,4}',code):raise ValueError('INVALID_ISSUER_CODE')
        for year in sorted(set(years)):
            if not 2000<=year<=2026:raise ValueError('INVALID_ARCHIVE_YEAR')
            url=f'https://www.asx.com.au/asx/v2/statistics/announcements.do?by=asxCode&asxCode={code}&timeframe=Y&year={year}'
            if url in done:continue
            receipt=dict(url=url,code=code,year=year)
            try:
                raw,_=fetch(url,max_attempts=1,min_interval=1,timeout=15,max_bytes=3*1024*1024,allowed_hosts=HOSTS)
                sha=hashlib.sha256(raw).hexdigest();(out/'data/snapshots'/(sha+'.html')).write_bytes(raw);receipt['sha256']=sha
                if archive_rejected(raw):raise ValueError('ARCHIVE_HTTP200_REJECTION')
                parser=Links();parser.feed(raw.decode('utf8',errors='replace'))
                count=0
                for href,label in parser.links:
                    dest=urldefrag(urljoin(url,href))[0];day=parser.link_dates.get(href)
                    if not is_asx_document(dest) or not day or day>cutoff:continue
                    count+=1;documents[dest]=dict(url=dest,title=' '.join(label.split()),archive_date=day,
                        origin_url=url,origin_sha256=sha,issuer_code_context=code)
                receipt.update(status='PARSED',document_links=count)
            except Exception as e:
                receipt.update(status='UNAVAILABLE',**failure_details(e))
                if str(e)=='ARCHIVE_HTTP200_REJECTION':receipt['failure_status']=str(e)
            result['receipts'].append(receipt);result['documents']=list(documents.values())
            target.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
            print(code,year,receipt['status'],receipt.get('document_links',0),flush=True)
    return result

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--issuer-code',action='append',required=True)
    p.add_argument('--years',type=int,nargs='+',required=True);p.add_argument('--out',required=True);a=p.parse_args()
    discover(a.issuer_code,a.years,a.out)

if __name__=='__main__':main()
