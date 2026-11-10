"""Bounded public-document acquisition; downloaded bytes are never observations.

An eight-work repair session is not a complete coverage cycle. Originals and
private response bodies stay local. Receipts contain no cookies or credentials.
"""
import hashlib
import json
import re
import socket
import ssl
import time
import urllib.error
from datetime import datetime,timedelta,timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qsl,urljoin,urlsplit,urlunsplit,urlencode
from .acquisition import PublicDownloadSession
from .store import filehash,digest


def utc():return datetime.now(timezone.utc).isoformat()


def safe_url(url):
    if not url:return url
    p=urlsplit(url)
    # Strip all query values from published receipts, retaining a fingerprint.
    query=urlencode([(k,'REMOVED') for k,v in parse_qsl(p.query,keep_blank_values=True)])
    return urlunsplit((p.scheme,p.netloc,p.path,query,''))


def public_value(value):
    if isinstance(value,dict):return {k:public_value(v) for k,v in value.items() if k not in ('cookies','set-cookie','authorization','private_url')}
    if isinstance(value,list):return [public_value(v) for v in value]
    if isinstance(value,str) and value.startswith('https://'):return safe_url(value)
    return value


def atomic_json(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(path.suffix+'.tmp')
    tmp.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf8',newline='\n')
    tmp.replace(path)


def _pdf_validation(path):
    import pymupdf
    from pypdf import PdfReader
    path=Path(path)
    with path.open('rb') as f:
        head=f.read(8);f.seek(max(0,path.stat().st_size-4096));tail=f.read()
    if not head.startswith(b'%PDF-'):raise ValueError('NOT_PDF_HTML_OR_OTHER_BODY')
    if b'%%EOF' not in tail:raise ValueError('PDF_MISSING_EOF')
    try:reader=PdfReader(str(path),strict=True)
    except Exception:raise ValueError('PDF_PARSE_OR_INTEGRITY_FAILED') from None
    if reader.is_encrypted and not reader.decrypt(''):raise ValueError('PDF_PASSWORD_REQUIRED')
    with pymupdf.open(path) as doc:
        if doc.needs_pass or doc.is_repaired:raise ValueError('PDF_ENCRYPTED_OR_REPAIRED')
        if not len(doc) or len(doc)!=len(reader.pages):raise ValueError('PDF_PAGE_COUNT_MISMATCH')
        counts=[]
        for i,page in enumerate(doc):
            counts.append(len(page.get_text().strip()));reader.pages[i].get_contents()
        return dict(format='PDF',container_validated=True,physical_pages=len(doc),
            native_text_characters=sum(counts),text_pages=sum(n>0 for n in counts),
            extraction_route='NATIVE_TEXT_REVIEW' if any(counts) else 'EXISTING_OCR_OR_MANUAL_REVIEW',
            scientific_admission=False)


def pdf_validation(path):
    try:return _pdf_validation(path)
    except ValueError:raise
    except Exception:raise ValueError('PDF_PARSE_OR_INTEGRITY_FAILED') from None


def html_diagnosis(text):
    import html
    title=' '.join(re.findall(r'<title[^>]*>(.*?)</title>',text,re.I|re.S))
    visible=re.sub(r'<(script|style)\b[^>]*>.*?</\1\s*>',' ',text,flags=re.I|re.S)
    visible=html.unescape(re.sub('<[^>]+>',' ',visible))
    visible=' '.join(visible.split())
    if (re.search(r'captcha|just a moment|verify|attention required',title,re.I)
        or re.search(r'verify (?:that )?you are (?:a )?human|checking your browser',visible[:5000],re.I)):
        return 'WEBSITE_VERIFICATION_PAGE'
    if re.search(r'log\s*in|sign\s*in|authentication required',title,re.I):return 'LOGIN_OR_RESTRICTED_ENTRY'
    if re.search(r'request rejected|access denied|forbidden',title+' '+visible[:700],re.I):return 'DENIAL_PAGE_CAUSE_UNCONFIRMED'
    if re.search(r'enable javascript|javascript is required',visible[:1000],re.I):return 'JAVASCRIPT_REQUIRED_PAGE'
    return 'NON_PDF_BODY'


def body_diagnosis(path):
    with Path(path).open('rb') as f:raw=f.read(3*1024*1024)
    return html_diagnosis(raw.decode('utf8',errors='replace'))


class Links(HTMLParser):
    def __init__(self,base):super().__init__();self.base=base;self.links=[]
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        value=attrs.get('href') if tag=='a' else attrs.get('src') if tag in ('iframe','embed') else attrs.get('data') if tag=='object' else None
        if value:
            url=urljoin(self.base,value)
            if urlsplit(url).scheme=='https':self.links.append(url)


def retry_delay(value,now=None):
    if not value:return None
    now=now or datetime.now(timezone.utc)
    try:return max(0,float(value))
    except (ValueError,TypeError):
        try:return max(0,(parsedate_to_datetime(value)-now).total_seconds())
        except (ValueError,TypeError,OverflowError):return None


def diagnose(exc):
    if isinstance(exc,urllib.error.HTTPError):
        return {403:'HTTP_403_CAUSE_UNCONFIRMED',401:'HTTP_401_ACCESS_RESTRICTED',404:'HTTP_404_URL_NOT_FOUND',
                410:'HTTP_410_GONE',429:'HTTP_429_RATE_LIMITED',503:'HTTP_503_TEMPORARY'}.get(exc.code,'HTTP_'+str(exc.code))
    reason=getattr(exc,'reason',exc)
    if isinstance(reason,ssl.SSLError):return 'TLS_ERROR'
    if isinstance(reason,socket.gaierror):return 'DNS_ERROR'
    if isinstance(reason,(TimeoutError,socket.timeout)):return 'TIMEOUT_NO_HTTP_RESPONSE'
    if isinstance(reason,ConnectionRefusedError):return 'CONNECTION_REFUSED_NO_HTTP_RESPONSE'
    if isinstance(exc,ValueError):return str(exc) if re.fullmatch('[A-Z0-9_]{3,100}',str(exc)) else 'VALIDATION_ERROR'
    return 'TRANSPORT_ERROR_NO_CONFIRMED_HTTP_RESPONSE'


class RepairSession:
    def __init__(self,config,out,session=None,sleep=time.sleep,clock=time.monotonic):
        self.config=config;self.out=Path(out);self.out.mkdir(parents=True,exist_ok=True)
        self.sleep=sleep;self.clock=clock
        p=config['policy']
        if p.get('apify_enabled') is not False:raise ValueError('PAID_ACTORS_DISABLED')
        if type(p['global_workers']) is not int or not 1<=p['global_workers']<=2 or type(p['per_domain_workers']) is not int or p['per_domain_workers']!=1:raise ValueError('INVALID_WORKER_LIMIT')
        if type(p['max_retries']) is not int or not 0<=p['max_retries']<=2:raise ValueError('INVALID_RETRY_LIMIT')
        for k in ('connect_timeout','read_timeout','job_timeout','work_timeout','max_bytes','html_max_bytes','min_domain_interval','domain_denials_before_pause'):
            if type(p[k]) not in (int,float) or p[k]<=0:raise ValueError('INVALID_BUDGET:'+k)
        if p['max_bytes']>64*1024*1024 or p['html_max_bytes']>3*1024*1024:raise ValueError('INVALID_SIZE_LIMIT')
        self.policy=p
        self.http=session or PublicDownloadSession(config['allowed_hosts'],p['connect_timeout'],p['read_timeout'])
        state=self.out/'repair_state.json'
        self.state=json.loads(state.read_text('utf8')) if state.exists() else dict(version='public-document-repair-v1',attempts=[],domains={},cache={},documents={})
        self.last={}
        for attempt in self.state['attempts']:
            if attempt.get('status')=='STARTED' and attempt.get('request_fingerprint'):
                # A crashed/killed attempt is never automatically retried. Check
                # whether an atomic validated document receipt already committed.
                doc=next((d for d in self.state['documents'].values() if d['key']==attempt['action_id']
                          and d['acquired_at']>=attempt['at']),None)
                if doc and filehash(self.out/doc['path'])==doc['document_sha256']:
                    result=dict(status=doc['status'],sha256=doc['document_sha256'],path=doc['path'],source_id=doc['source_id'])
                else:result=dict(status='INTERRUPTED_OUTCOME_UNCERTAIN_REVIEW_BEFORE_RETRY',http_status=attempt.get('http_status'))
                attempt.update(result);self.state['cache'][attempt['request_fingerprint']]=result
        self.save()

    def save(self):atomic_json(self.out/'repair_state.json',self.state)

    def stage(self):
        folder=self.out/'staging';folder.mkdir(exist_ok=True)
        return folder/(str(time.time_ns())+'.part')

    def archive(self,path,suffix):
        sha=filehash(path);target=self.out/'data/snapshots'/(sha+suffix);target.parent.mkdir(parents=True,exist_ok=True)
        if not target.exists():path.replace(target)
        else:
            if filehash(target)!=sha:raise ValueError('SNAPSHOT_HASH_MISMATCH')
            path.unlink()
        return sha,target

    def pdf(self,path,work,url,method,metadata=None):
        if Path(path).stat().st_size>self.policy['max_bytes']:raise ValueError('DOCUMENT_BYTE_BUDGET_EXCEEDED')
        validation=pdf_validation(path);sha,target=self.archive(path,'.pdf')
        document=dict(key=work['action_id'],kind='pdf',source_id=sha,document_sha256=sha,
            path=target.relative_to(self.out).as_posix(),url=url,resolved_url=url,
            original_url=work['url'],acquired_at=utc(),acquisition_method=method,
            bytes=target.stat().st_size,status='PDF_ACQUIRED' if validation['text_pages'] else 'PDF_ACQUIRED_PENDING_OCR',
            identity_status='PENDING_WORK_EDITION_REVIEW',validation=validation,
            publication_date=None,resource_effective_date=None,source_document_version=None,
            physical_pages=validation['physical_pages'],project_ids=work['project_ids'],possible_columns=work['columns'],
            scientific_admission=False,**(metadata or {}))
        self.state['documents'].setdefault(sha,document)
        # Same bytes have one source identity; work associations live in attempts/reviews.
        downloads=[d for d in self.state['documents'].values() if d['status'].startswith('PDF_ACQUIRED')]
        atomic_json(self.out/'downloads.json',downloads);self.save()
        return document

    def reuse(self,work,path,url,expected_sha,receipt_path):
        path=Path(path);rows=json.loads(Path(receipt_path).read_text('utf8'))
        if filehash(path)!=expected_sha or not any(r.get('document_sha256')==expected_sha and r.get('url')==url and r.get('status')=='PDF_ACQUIRED' for r in rows):
            raise ValueError('REUSE_HASH_OR_CAPTURE_RECEIPT_MISMATCH')
        tmp=self.stage()
        import shutil
        shutil.copyfile(path,tmp)
        result=self.pdf(tmp,work,url,'REUSED_VERIFIED_LOCAL_SNAPSHOT',dict(reused=True,original_capture_receipt_sha256=filehash(receipt_path)))
        self.state['attempts'].append(dict(action_id=work['action_id'],method='LOCAL_CACHE',status='REUSED',document_sha256=result['document_sha256'],at=utc()))
        self.save();return result

    def acquire(self,work,url,*,kind='pdf',entry_url=None,refresh=False):
        """One sequential worker; both configured concurrency ceilings are respected."""
        self.http.guard(url)
        key=digest([url,kind]);cache=self.state['cache'].get(key)
        if cache and not refresh:
            if cache.get('path') and filehash(self.out/cache['path'])!=cache['sha256']:raise ValueError('CACHE_HASH_MISMATCH')
            retry_at=cache.get('next_retry_at')
            due=retry_at and datetime.fromisoformat(retry_at)<=datetime.now(timezone.utc)
            if not due or cache.get('attempts_total',0)>=self.policy['max_retries']+1:
                self.state.setdefault('cache_hits',[]).append(dict(action_id=work['action_id'],request_fingerprint=key,at=utc(),status=cache['status']))
                self.save()
                return dict(cache,cache_hit=True)
        if cache and refresh:raise ValueError('EXPLICIT_REFRESH_REQUIRES_NEW_SESSION_AND_NEW_EVIDENCE')
        host=urlsplit(url).hostname;domain=self.state['domains'].get(host,{})
        if domain.get('paused'):
            record=dict(action_id=work['action_id'],url=safe_url(url),method='HTTP',status='NOT_REQUESTED_DOMAIN_PAUSED',
                        http_status=None,at=utc(),reason='Prior explicit denials; try official alternative or manual route')
            self.state['attempts'].append(record);self.save();return record
        started=self.clock();result=None;record=dict(status='WORK_BUDGET_DEFERRED',http_status=None)
        offset=cache.get('attempts_total',0) if cache else 0
        for n in range(offset,self.policy['max_retries']+1):
            remaining=self.policy['job_timeout']-(self.clock()-started)
            if remaining<=0:break
            pause=max(0,self.policy['min_domain_interval']-(self.clock()-self.last.get(host,-1e12)))
            if pause>=remaining:break
            if pause:self.sleep(pause)
            path=self.stage();record=dict(action_id=work['action_id'],url=safe_url(url),entry_url=safe_url(entry_url),
                method='HTTP_NORMAL_SESSION',at=utc(),attempt=n+1,http_status=None,status='STARTED',
                request_fingerprint=key,client='AU_REE_V2/0.1 public research')
            self.state['attempts'].append(record);self.save();self.last[host]=self.clock()
            try:
                response=self.http.download(url,path,max_bytes=self.policy['max_bytes'] if kind=='pdf' else self.policy['html_max_bytes'],
                    total_timeout=max(.001,remaining-pause),referer=entry_url)
                record.update(public_value(response))
                if response.get('http_status')!=200:raise ValueError('HTTP_NON_200_DOCUMENT_RESPONSE')
                if kind=='pdf':
                    try:doc=self.pdf(path,work,url,'HTTP_NORMAL_SESSION',dict(entry_url=entry_url,final_url=response['final_url']))
                    except ValueError:
                        record['body_diagnosis']=body_diagnosis(path);raise
                    result=dict(status=doc['status'],path=doc['path'],sha256=doc['document_sha256'],source_id=doc['source_id'])
                else:
                    diagnosis=body_diagnosis(path)
                    if diagnosis!='NON_PDF_BODY':raise ValueError(diagnosis)
                    sha,target=self.archive(path,'.html')
                    links=Links(response['final_url']);links.feed(target.read_text('utf8',errors='replace'))
                    result=dict(status='ENTRY_CAPTURED',path=target.relative_to(self.out).as_posix(),sha256=sha,
                                links=list(dict.fromkeys(links.links)),final_url=response['final_url'])
                record.update(status=result['status'],sha256=result['sha256'],path=result['path'])
                self.state['cache'][key]=result;self.save();return result
            except Exception as exc:
                response=getattr(exc,'public_download_receipt',{})
                record.update(public_value(response));status=diagnose(exc)
                if status=='TIMEOUT_NO_HTTP_RESPONSE' and record.get('http_status') is not None:status='READ_TIMEOUT_AFTER_HTTP_RESPONSE'
                if status=='TRANSPORT_ERROR_NO_CONFIRMED_HTTP_RESPONSE' and record.get('http_status') is not None:status='BODY_TRANSFER_ERROR_AFTER_HTTP_RESPONSE'
                record.update(status=status,error_summary=type(exc).__name__+':'+status)
                if path.exists():
                    # Rejected bytes remain private evidence; never appear in downloads.json.
                    sha,target=self.archive(path,'.rejected');record.update(rejected_body_sha256=sha,rejected_body_path=target.relative_to(self.out).as_posix())
                code=record.get('http_status')
                if code in (401,403):
                    domain['denials']=domain.get('denials',0)+1
                    if domain['denials']>=self.policy['domain_denials_before_pause']:domain.update(paused=True,reason='EXPLICIT_REPEATED_DENIAL')
                    self.state['domains'][host]=domain
                transient=code in (408,429,500,502,503,504) or status in ('TIMEOUT_NO_HTTP_RESPONSE','READ_TIMEOUT_AFTER_HTTP_RESPONSE','BODY_TRANSFER_ERROR_AFTER_HTTP_RESPONSE','DNS_ERROR','TRANSPORT_ERROR_NO_CONFIRMED_HTTP_RESPONSE')
                delay=retry_delay(record.get('retry_after'))
                delay=max(delay or 0,self.policy['backoff_seconds']*(2**n))
                if transient and (delay>=self.policy['job_timeout']-(self.clock()-started) or n==self.policy['max_retries']):
                    record['next_retry_at']=(datetime.now(timezone.utc)+timedelta(seconds=delay)).isoformat()
                self.save()
                if not transient or n==self.policy['max_retries'] or 'next_retry_at' in record:break
                self.sleep(delay)
        result=dict(status=(record['status'] if result is None else result['status']),http_status=record.get('http_status'),
                    next_retry_at=record.get('next_retry_at'),attempts_total=record.get('attempt',offset))
        self.state['cache'][key]=result;self.save();return result

    def manual_import(self,work,path,metadata):
        required=('original_url','actual_source_url','acquired_at','method','publisher','title','publication_date','work_edition')
        if any(not str(metadata.get(k,'')).strip() for k in required):raise ValueError('MANUAL_IMPORT_METADATA_REQUIRED_PENDING_REVIEW')
        if metadata['original_url']!=work['url']:raise ValueError('MANUAL_IMPORT_ORIGINAL_IDENTITY_MISMATCH')
        self.http.guard(metadata['actual_source_url']);datetime.fromisoformat(metadata['acquired_at'].replace('Z','+00:00'))
        tmp=self.stage()
        import shutil
        shutil.copyfile(path,tmp)
        return self.pdf(tmp,work,metadata['actual_source_url'],'MANUAL_NORMAL_DOWNLOAD',dict(manual_metadata=metadata))


def verify_document_identity(session,work,review):
    """A reviewed work/edition identity is separate from scientific field admission.

    Hash-different alternatives require native edition identifiers and key-section
    evidence, not title similarity. This does not create a new observation.
    """
    import pymupdf
    sha=review['document_sha256'];doc=session.state['documents'].get(sha)
    if not doc or filehash(session.out/doc['path'])!=sha:raise ValueError('IDENTITY_DOCUMENT_HASH_MISMATCH')
    required=('publisher','title','publication_date','work_edition','report_identifier','reviewer','decision')
    if any(not str(review.get(k,'')).strip() for k in required):raise ValueError('IDENTITY_REVIEW_METADATA_REQUIRED')
    if review['action_id']!=work['action_id'] or review['decision']!='QUALIFIED_SAME_WORK_EDITION':raise ValueError('IDENTITY_WRONG_WORK_OR_EDITION')
    if review['work_edition']!=work['target_edition']:raise ValueError('IDENTITY_DIFFERENT_EDITION_NOT_MERGED')
    reference=work.get('identity_reference_sha256') or work.get('reuse',{}).get('sha256')
    if doc['url']!=work['url'] and sha!=reference:
        comparison=review.get('same_edition_comparison',{})
        if not reference or comparison.get('reference_sha256')!=reference or not comparison.get('key_pages'):
            raise ValueError('IDENTITY_ALTERNATIVE_COMPARISON_REQUIRED')
        reference_doc=session.state['documents'].get(reference)
        reference_path=(session.out/reference_doc['path']) if reference_doc else Path(work.get('reuse',{}).get('path',''))
        if not reference_path.is_file() or filehash(reference_path)!=reference:raise ValueError('IDENTITY_REFERENCE_HASH_MISMATCH')
        with pymupdf.open(reference_path) as old,pymupdf.open(session.out/doc['path']) as new:
            if len(old)!=len(new) or any(' '.join(a.get_text().split())!=' '.join(b.get_text().split()) for a,b in zip(old,new)):
                raise ValueError('IDENTITY_ALTERNATIVE_CONTENT_DIFFERS')
            for page in comparison['key_pages']:
                if type(page) is not int or not 1<=page<=len(old):raise ValueError('IDENTITY_COMPARISON_PAGE_INVALID')
                if old[page-1].get_pixmap().samples!=new[page-1].get_pixmap().samples:raise ValueError('IDENTITY_KEY_PAGE_RENDER_DIFFERS')
    proofs=review.get('native_proofs',[])
    required_roles={'publisher','title','edition_or_report_identifier','key_table_or_section'}
    if not required_roles<={p.get('role') for p in proofs}:raise ValueError('IDENTITY_INSUFFICIENT_NATIVE_PROOFS')
    with pymupdf.open(session.out/doc['path']) as pdf:
        if review.get('physical_pages')!=len(pdf):raise ValueError('IDENTITY_PAGE_COUNT_MISMATCH')
        for proof in proofs:
            if type(proof.get('page')) is not int or not 1<=proof['page']<=len(pdf):raise ValueError('IDENTITY_INVALID_PAGE')
            text=pdf[proof['page']-1].get_text()
            if proof.get('page_text_sha256')!=hashlib.sha256(text.encode('utf8')).hexdigest():raise ValueError('IDENTITY_NATIVE_PAGE_HASH_MISMATCH')
            norm=lambda v:' '.join(v.split()).casefold()
            if not proof.get('markers') or any(norm(m) not in norm(text) for m in proof['markers']):raise ValueError('IDENTITY_NATIVE_MARKER_MISMATCH')
        for field,role in [('publisher','publisher'),('title','title'),('report_identifier','edition_or_report_identifier'),('work_edition','edition_or_report_identifier')]:
            native=' '.join(pdf[p['page']-1].get_text() for p in proofs if p['role']==role)
            if norm(review[field]) not in norm(native):raise ValueError('IDENTITY_REVIEW_VALUE_NOT_NATIVE:'+field)
        precision=review.get('publication_date_precision')
        if precision=='MONTH':
            month=datetime.strptime(review['publication_date'],'%Y-%m').strftime('%B %Y')
            if norm(month) not in norm(' '.join(p.get_text() for p in pdf)):raise ValueError('IDENTITY_PUBLICATION_MONTH_NOT_NATIVE')
        elif precision=='DAY':
            evidence=review.get('publication_date_evidence',{})
            path=(session.out/evidence.get('path','')).resolve()
            if not path.is_relative_to(session.out.resolve()) or not path.is_file() or filehash(path)!=evidence.get('sha256'):
                raise ValueError('IDENTITY_PUBLICATION_ENTRY_HASH')
            marker=datetime.strptime(review['publication_date'],'%Y-%m-%d').strftime('%d %B %Y').lstrip('0')
            import html
            text=html.unescape(re.sub('<[^>]+>',' ',path.read_text('utf8')))
            if norm(marker) not in norm(text):raise ValueError('IDENTITY_PUBLICATION_DAY_NOT_IN_ENTRY')
            receipts=[a for a in session.state['attempts'] if a.get('status')=='ENTRY_CAPTURED' and a.get('path')==evidence['path'] and a.get('sha256')==evidence['sha256'] and a.get('action_id')==work['action_id']]
            if not receipts:
                raise ValueError('IDENTITY_PUBLICATION_ENTRY_RECEIPT')
            links=Links(receipts[0]['final_url']);links.feed(path.read_text('utf8'))
            if doc['url'] not in links.links:raise ValueError('IDENTITY_ENTRY_MUST_LINK_ACTUAL_DOCUMENT')
        else:raise ValueError('IDENTITY_PUBLICATION_PRECISION_REQUIRED')
    result=dict(review,identity_status='QUALIFIED_SAME_WORK_EDITION',scientific_admission=False,
                note='Work/edition qualification only; field values require the existing source-review validators')
    doc.update(identity_status=result['identity_status'],publication_date=review['publication_date'],
               source_document_version=review['work_edition'])
    session.save();atomic_json(session.out/'downloads.json',list(session.state['documents'].values()))
    return result
