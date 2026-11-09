"""Opt-in public ASX PDF delivery, with wrapper-to-file provenance.

Resolve only URLs supplied by ASX. No announcement-ID conversion, terms POST,
cookies, CAPTCHA service, proxy rotation or unbounded retries are required.
"""
import hashlib
import io
import json
import re
import urllib.error
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit, urlunsplit, parse_qs

from .acquisition import request, failure_details
from .security import sensitive_reference

VERSION='asx-public-pdf-v1'
HOSTS=frozenset(('www.asx.com.au','announcements.asx.com.au'))
PDF_PATH=re.compile(r'/asxpdf/\d{8}/pdf/[A-Za-z0-9]+\.pdf\Z')


def _safe(url):
    try:
        p=urlsplit(url)
        return (p.scheme=='https' and p.hostname in HOSTS and not p.username and not p.password
                and p.port in (None,443) and not p.fragment and not sensitive_reference(url))
    except ValueError:return False


def is_asx_document(url):
    if not _safe(url):return False
    p=urlsplit(url)
    return bool(PDF_PATH.fullmatch(p.path) or
        (p.path in ('/asx/statistics/displayAnnouncement.do','/asx/v2/statistics/displayAnnouncement.do')
         and parse_qs(p.query).get('display')==['pdf']
         and len(parse_qs(p.query).get('idsId',[]))==1
         and re.fullmatch(r'\d{1,12}',parse_qs(p.query)['idsId'][0])))


class _PDFLinks(HTMLParser):
    def __init__(self):super().__init__();self.links=[]
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        value=(a.get('value') if tag=='input' and a.get('name','').lower()=='pdfurl' else
               a.get('href') if tag=='a' else a.get('src') if tag in ('iframe','embed') else
               a.get('data') if tag=='object' else None)
        if value:self.links.append(value)


def linked_pdf(raw,base):
    parser=_PDFLinks();parser.feed(raw.decode('utf8',errors='replace'))
    links={urljoin(base,v) for v in parser.links}
    links={v for v in links if _safe(v) and PDF_PATH.fullmatch(urlsplit(v).path) and not urlsplit(v).query}
    # Several unrelated files on a page cannot establish one document identity.
    if len(links)>1:raise ValueError('ASX_AMBIGUOUS_PDF_LINKS')
    return next(iter(links),None)


def _alternate(url):
    p=urlsplit(url)
    if not PDF_PATH.fullmatch(p.path) or p.query:return None
    host='announcements.asx.com.au' if p.hostname=='www.asx.com.au' else 'www.asx.com.au'
    return urlunsplit(('https',host,p.path,'',''))


def fetch_pdf(url,fetch=None,archive=None,max_bytes=40*1024*1024,max_requests=3):
    """Return bytes, headers, receipt; failures carry the same receipt on the exception.

    ``archive(raw, url, suffix)`` returns a SHA after immutable storage. Every
    received wrapper and rejected body precedes interpretation. HTTP 429 and
    Retry-After stop the entire resolution; no alternative is tried early.
    """
    if not is_asx_document(url):raise ValueError('ASX_DOCUMENT_URL_NOT_ALLOWED')
    if not 1<=max_requests<=3 or not 1<=max_bytes<=40*1024*1024:raise ValueError('ASX_INVALID_BUDGET')
    fetch=fetch or request
    receipt=dict(version=VERSION,requested_url=url,attempts=[],terms_submitted=False,
                 interpretation='RETRIEVAL_NOT_PROJECT_OR_EVIDENCE_VALIDATION')
    queue=[(url,'SOURCE_URL')];seen=set();last=None
    def used():return sum(1+len(a.get('redirects',[])) for a in receipt['attempts'])
    while queue and used()<max_requests:
        target,basis=queue.pop(0)
        if target in seen:continue
        seen.add(target)
        attempt=dict(url=target,basis=basis);receipt['attempts'].append(attempt)
        try:
            raw,headers=fetch(target,headers={'Accept':'application/pdf,text/html;q=0.9'},
                timeout=25,max_bytes=max_bytes,allowed_hosts=HOSTS,max_attempts=1,min_interval=1.,
                max_redirects=max_requests-used())
            if len(raw)>max_bytes:raise ValueError('DOCUMENT_BYTE_BUDGET_EXCEEDED')
            resolved=headers.get('X-Resolved-URL',target)
            attempt['redirects']=json.loads(headers.get('X-Redirect-Chain','[]'))
            if not is_asx_document(resolved):raise ValueError('ASX_RESOLVED_URL_NOT_ALLOWED')
            attempt.update(resolved_url=resolved,bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())
            if raw.startswith(b'%PDF-'):
                from pypdf import PdfReader
                try:
                    reader=PdfReader(io.BytesIO(raw))
                    # Owner permissions are common in readable public ASX PDFs.
                    # Only reject encryption when an actual password is needed.
                    if reader.is_encrypted and not reader.decrypt(''):raise ValueError('password required')
                    pages=len(reader.pages)
                    if pages<1:raise ValueError('unreadable')
                except Exception:
                    if archive:attempt['response_sha256']=archive(raw,target,'.response')
                    raise ValueError('ASX_INVALID_PDF') from None
                attempt.update(status='PDF_VALIDATED',physical_pages=pages)
                receipt.update(status='PDF_ACQUIRED',resolved_url=resolved,document_sha256=attempt['sha256'])
                return raw,headers,receipt
            if archive:attempt['response_sha256']=archive(raw,target,'.html')
            attempt['terms_interstitial_seen']=b'announcementTerms.do' in raw
            link=linked_pdf(raw,resolved)
            if link:
                attempt.update(status='PUBLIC_PDF_LINK_RESOLVED',linked_pdf_url=link)
                queue.insert(0,(link,'ASX_RESPONSE_PDF_URL'))
                continue
            lower=raw.lower()
            status=('TERMS_INTERSTITIAL_NOT_ACCEPTED' if attempt['terms_interstitial_seen'] else
                    'ASX_ANTI_BOT_CHALLENGE' if any(x in lower for x in (b'incapsula',b'captcha',b'access denied',b'just a moment')) else
                    'ASX_NON_PDF_RESPONSE')
            raise ValueError(status)
        except Exception as exc:
            last=exc
            attempt['redirects']=getattr(exc,'request_redirects',attempt.get('redirects',[]))
            attempt.update(status='UNAVAILABLE',**failure_details(exc))
            if isinstance(exc,urllib.error.HTTPError) and archive:
                body=exc.read(min(max_bytes,256*1024)+1)
                if len(body)<=min(max_bytes,256*1024):attempt['response_sha256']=archive(body,target,'.html')
            # Limit fallback to the identical static file on the other ASX host.
            # Timeouts/5xx are deferred, and malformed or ambiguous files fail closed.
            can_fallback=(isinstance(exc,urllib.error.HTTPError) and exc.code in (403,404)) or (
                isinstance(exc,ValueError) and str(exc) in ('ASX_ANTI_BOT_CHALLENGE','ASX_NON_PDF_RESPONSE'))
            if (getattr(exc,'retry_after_seconds',None) is not None or getattr(exc,'code',None)==429
                or (getattr(exc,'headers',None) and exc.headers.get('Retry-After') is not None)):break
            alternative=_alternate(target) if can_fallback else None
            if alternative and alternative not in seen:queue.append((alternative,'SAME_ASX_STATIC_PATH'))
            else:break
    if queue and used()>=max_requests:last=ValueError('ASX_REQUEST_BUDGET_EXHAUSTED')
    last=last or ValueError('ASX_PDF_UNAVAILABLE')
    receipt['status']='UNAVAILABLE';last.asx_receipt=receipt
    raise last
