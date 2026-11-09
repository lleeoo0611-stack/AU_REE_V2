"""Replay a hash-pinned PDF from an official public WAMEX appendix archive.

The public document-list POST is read-only. Ephemeral public storage links are
used in memory only; receipts bind the stable report URL, archive hash and exact
PDF hash. No archive paths are extracted and no raw source is a public output.
"""
import argparse,hashlib,io,json,re,zipfile
from pathlib import Path
from urllib.parse import urlsplit
from au_ree_v2.acquisition import request


def capture(report_number,archive_name,expected_sha,out):
    if not isinstance(report_number,int) or not 1<=report_number<=999999 or not re.fullmatch('[0-9a-f]{64}',expected_sha):
        raise ValueError('WAMEX_REPORT_AND_EXPECTED_HASH_REQUIRED')
    out=Path(out);snap=out/'data/snapshots';snap.mkdir(parents=True,exist_ok=True)
    endpoint='https://wamex.dmp.wa.gov.au/Wamex/Search/ReportDetails/ReportDocuments_Read'
    stable='https://wamex.dmp.wa.gov.au/Wamex/Search/ReportDetails?ANumber='+str(report_number)
    raw,_=request(endpoint,{'aNumber[0]':report_number,'page':1,'pageSize':100},method='POST',allowed_hosts={'wamex.dmp.wa.gov.au'},max_attempts=1,max_bytes=3000000)
    listing=json.loads(raw)
    if listing.get('Errors') or not isinstance(listing.get('Data'),list) or len(listing['Data'])!=listing.get('Total') or any(r.get('ANumber')!=report_number for r in listing['Data']):
        raise ValueError('WAMEX_PUBLIC_DOCUMENT_LIST_INCOMPLETE_OR_MISMATCHED')
    safe=[{k:r.get(k) for k in ['ANumber','FileName','FileType','FileSize','BLTId']} for r in listing['Data']]
    matches=[r for r in listing['Data'] if r['FileName']==archive_name and r['FileType']=='.zip']
    if len(matches)!=1:raise ValueError('WAMEX_EXACT_ARCHIVE_REQUIRED')
    resource=matches[0];link=resource.get('Link','');parts=urlsplit(link)
    if (parts.scheme!='https' or parts.hostname not in {'warsydprdstagsdspub.blob.core.windows.net','uploads.dmp.wa.gov.au'}
        or parts.username or parts.password or parts.port not in (None,443)):
        raise ValueError('WAMEX_UNEXPECTED_PUBLIC_STORAGE_HOST')
    body,_=request(link,max_attempts=1,max_bytes=64*1024*1024,timeout=45,min_interval=1)
    archive_sha=hashlib.sha256(body).hexdigest();(snap/(archive_sha+'.zip')).write_bytes(body)
    found=[]
    with zipfile.ZipFile(io.BytesIO(body)) as archive:
        infos=archive.infolist()
        if len(infos)>1000 or sum(z.file_size for z in infos)>512*1024*1024:raise ValueError('WAMEX_ARCHIVE_EXPANSION_BUDGET')
        for z in infos:
            if not z.filename.casefold().endswith('.pdf') or z.file_size>40*1024*1024:continue
            pdf=archive.read(z)
            if hashlib.sha256(pdf).hexdigest()==expected_sha:
                if not pdf.startswith(b'%PDF-'):raise ValueError('WAMEX_EXPECTED_MEMBER_NOT_PDF')
                found.append((z.filename,pdf))
    if len(found)!=1:raise ValueError('WAMEX_EXPECTED_PDF_NOT_UNIQUE_IN_ARCHIVE')
    name,pdf=found[0];path='data/snapshots/'+expected_sha+'.pdf';(out/path).write_bytes(pdf)
    import pymupdf
    with pymupdf.open(stream=pdf,filetype='pdf') as d:pages=len(d)
    receipt=dict(key='wamex_'+str(report_number)+'_hash_pinned_appendix',url=stable,kind='pdf',status='PDF_ACQUIRED',document_sha256=expected_sha,path=path,physical_pages=pages,
        acquisition_method='OFFICIAL_PUBLIC_REPORT_LIST_EXACT_ARCHIVE_AND_PDF_SHA256',archive_sha256=archive_sha,archive_name=archive_name,archive_member=name,
        sanitized_public_document_list=safe,ephemeral_link_published=False,resource_effective_date_inferred=False)
    (out/'downloads.json').write_text(json.dumps([receipt],ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    return {k:receipt[k] for k in ['key','status','document_sha256','physical_pages','archive_sha256']}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--report',required=True,type=int);p.add_argument('--archive-name',required=True);p.add_argument('--expected-sha256',required=True);p.add_argument('--out',required=True)
    a=p.parse_args();print(json.dumps(capture(a.report,a.archive_name,a.expected_sha256,a.out),ensure_ascii=False,indent=2))
