"""Offline acquisition fixtures: no real websites, network or research approvals."""
import copy
import gzip
import hashlib
import io
import json
import socket
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch
import pymupdf
from au_ree_v2.acquisition import PublicDownloadSession
from au_ree_v2.public_document_repair import (RepairSession,pdf_validation,html_diagnosis,
    verify_document_identity,public_value,retry_delay,atomic_json)
from au_ree_v2.public_document_browser import accept_browser_pdf,acquire_browser,response_info
from au_ree_v2.store import filehash,digest

ROOT=Path(__file__).resolve().parents[1]


def native_pdf(scanned=False):
    doc=pymupdf.open();page=doc.new_page()
    if scanned:
        pix=pymupdf.Pixmap(pymupdf.csRGB,(0,0,100,100),False);pix.clear_with(200)
        page.insert_image(pymupdf.Rect(20,20,120,120),pixmap=pix)
    else:page.insert_text((30,40),'Mock Public Work\nGovernment Research\nDecember 2025\nID-2025\nTable 1 resource')
    raw=doc.tobytes();doc.close();return raw


class Clock:
    def __init__(self):self.value=0;self.sleeps=[]
    def now(self):return self.value
    def sleep(self,seconds):self.sleeps.append(seconds);self.value+=seconds


class Transport:
    def __init__(self,responses):self.responses=list(responses);self.calls=[]
    def guard(self,url):
        if not url.startswith('https://publisher.test/'):raise ValueError('REQUEST_DESTINATION_NOT_ALLOWED')
    def download(self,url,path,**kwargs):
        self.calls.append((url,kwargs));response=self.responses.pop(0)
        receipt=dict(http_status=200,final_url=url,redirects=[],content_type='application/pdf',retry_after=None,tls_verification=True)
        if isinstance(response,Exception):
            if isinstance(response,urllib.error.HTTPError):receipt.update(http_status=response.code,retry_after=response.headers.get('Retry-After'))
            else:receipt['http_status']=None
            response.public_download_receipt=receipt;raise response
        path.write_bytes(response);receipt.update(bytes=len(response),wire_bytes=len(response));return receipt


class RepairTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.cfg=json.loads((ROOT/'config/public_acquisition_repair.json').read_text('utf8'))
        self.cfg['allowed_hosts']=['publisher.test'];self.clock=Clock()
        self.work=dict(action_id='work',url='https://publisher.test/original.pdf',project_ids=['P'],columns=['grade'],target_edition='2025',entry_urls=['https://publisher.test/entry'],download_link_pattern=r'original\.pdf')
        self.cfg['works']=[self.work]
    def session(self,responses):
        t=Transport(responses);s=RepairSession(self.cfg,self.root/'assets',t,self.clock.sleep,self.clock.now);return s,t
    def error(self,code,retry=None):return urllib.error.HTTPError(self.work['url'],code,'failure',{'Retry-After':retry} if retry else {},None)

    def test_http200_challenge_is_not_pdf_or_formal_evidence(self):
        s,t=self.session([b'<title>Just a moment</title>Verify you are human'])
        r=s.acquire(self.work,self.work['url'])
        self.assertEqual('NOT_PDF_HTML_OR_OTHER_BODY',r['status'])
        self.assertEqual('WEBSITE_VERIFICATION_PAGE',s.state['attempts'][0]['body_diagnosis'])
        self.assertEqual({},s.state['documents']);self.assertEqual(1,len(t.calls))

    def test_normal_article_with_hidden_captcha_is_not_challenge(self):
        self.assertEqual('NON_PDF_BODY',html_diagnosis('<title>Public report</title><style>.grecaptcha-badge{visibility:hidden}</style><h1>Report published</h1><div class="g-recaptcha"></div>'))

    def test_pdf_scan_and_corruption(self):
        p=self.root/'scan.pdf';p.write_bytes(native_pdf(True))
        r=pdf_validation(p);self.assertEqual('EXISTING_OCR_OR_MANUAL_REVIEW',r['extraction_route'])
        self.assertFalse(r['scientific_admission'])
        p.write_bytes(p.read_bytes()[:-30])
        with self.assertRaises(ValueError):pdf_validation(p)

    def test_attachment_and_inline_share_validation_pipeline(self):
        s,t=self.session([]);raw=native_pdf()
        for method in ('BROWSER_ATTACHMENT_DOWNLOAD_EVENT','BROWSER_INLINE_PDF_RESPONSE'):
            path=s.stage();path.write_bytes(raw)
            r=accept_browser_pdf(s,self.work,path,self.work['url'],method)
            self.assertTrue(r['validation']['container_validated']);self.assertFalse(r['scientific_admission'])
        self.assertEqual(1,len(s.state['documents']))

    def test_cache_and_manual_reimport_do_not_add_source_or_observation(self):
        raw=native_pdf();s,t=self.session([raw])
        a=s.acquire(self.work,self.work['url']);b=s.acquire(self.work,self.work['url'])
        self.assertTrue(b['cache_hit']);self.assertEqual(1,len(t.calls));self.assertEqual(1,len(s.state['documents']))
        p=self.root/'manual.pdf';p.write_bytes(raw)
        meta=dict(original_url=self.work['url'],actual_source_url=self.work['url'],acquired_at='2026-11-11T00:00:00+00:00',method='normal download',publisher='Government Research',title='Mock Public Work',publication_date='2025-12',work_edition='2025')
        s.manual_import(self.work,p,meta);s.manual_import(self.work,p,meta)
        self.assertEqual(1,len(s.state['documents']))
        self.assertTrue(all(not d['scientific_admission'] for d in s.state['documents'].values()))

    def test_missing_manual_metadata_or_bad_file_cannot_be_observation(self):
        s,t=self.session([]);p=self.root/'broken.pdf';p.write_bytes(b'%PDF-broken')
        with self.assertRaisesRegex(ValueError,'METADATA_REQUIRED'):s.manual_import(self.work,p,{})
        meta=dict(original_url=self.work['url'],actual_source_url=self.work['url'],acquired_at='2026-11-11T00:00:00+00:00',method='normal download',publisher='Government Research',title='Mock Public Work',publication_date='2025-12',work_edition='2025')
        with self.assertRaises(ValueError):s.manual_import(self.work,p,meta)
        self.assertEqual({},s.state['documents'])

    def test_403_then_alternative_keeps_both_statuses(self):
        s,t=self.session([self.error(403),native_pdf()])
        self.assertEqual(403,s.acquire(self.work,self.work['url'])['http_status'])
        r=s.acquire(self.work,'https://publisher.test/alternative.pdf')
        self.assertEqual('PDF_ACQUIRED',r['status'])
        self.assertEqual([403,200],[a['http_status'] for a in s.state['attempts']])

    def test_repeat403_is_cached_and_persistent_domain_denial_pauses(self):
        s,t=self.session([self.error(403),self.error(403)])
        s.acquire(self.work,self.work['url']);s.acquire(self.work,self.work['url'])
        s.acquire(self.work,'https://publisher.test/second')
        r=s.acquire(self.work,'https://publisher.test/third')
        self.assertEqual('NOT_REQUESTED_DOMAIN_PAUSED',r['status']);self.assertEqual(2,len(t.calls))

    def test_timeout_has_no_http_status_and_retries_are_bounded(self):
        s,t=self.session([urllib.error.URLError(TimeoutError()) for i in range(3)])
        r=s.acquire(self.work,self.work['url'])
        self.assertEqual('TIMEOUT_NO_HTTP_RESPONSE',r['status']);self.assertIsNone(r['http_status'])
        self.assertEqual(3,len(t.calls));self.assertEqual([2,4],self.clock.sleeps)

    def test_retry_after_is_obeyed_or_deferred_without_early_request(self):
        s,t=self.session([self.error(429,'1200')])
        r=s.acquire(self.work,self.work['url'])
        self.assertTrue(r['next_retry_at']);self.assertEqual([],self.clock.sleeps);self.assertEqual(1,len(t.calls))
        self.assertEqual(1200,retry_delay('1200'))

    def test_503_short_retry_after_can_finish_inside_budget(self):
        s,t=self.session([self.error(503,'3'),native_pdf()])
        self.assertEqual('PDF_ACQUIRED',s.acquire(self.work,self.work['url'])['status'])
        self.assertEqual([3],self.clock.sleeps);self.assertEqual(2,len(t.calls))

    def test_interrupted_unknown_attempt_is_not_blindly_retried(self):
        s,t=self.session([])
        s.state['attempts'].append(dict(action_id='work',status='STARTED',request_fingerprint=digest([self.work['url'],'pdf']),at='2026-11-11T00:00:00+00:00',http_status=None));s.save()
        resumed=RepairSession(self.cfg,s.out,t,self.clock.sleep,self.clock.now)
        result=resumed.acquire(self.work,self.work['url'])
        self.assertEqual('INTERRUPTED_OUTCOME_UNCERTAIN_REVIEW_BEFORE_RETRY',result['status']);self.assertEqual([],t.calls)

    def test_public_receipts_drop_cookie_and_query_values(self):
        result=public_value(dict(url='https://publisher.test/a.pdf?signature=private&token=secret',cookies='x',authorization='y'))
        self.assertNotIn('private',json.dumps(result));self.assertNotIn('secret',json.dumps(result));self.assertNotIn('cookies',result)

    def test_work_identity_requires_native_edition_not_title_similarity(self):
        s,t=self.session([native_pdf()]);d=s.acquire(self.work,self.work['url']);doc=pymupdf.open(s.out/d['path']);text=doc[0].get_text();doc.close()
        proofs=[dict(page=1,role=r,markers=['Mock'],page_text_sha256=hashlib.sha256(text.encode()).hexdigest()) for r in ('title','publisher','edition_or_report_identifier','key_table_or_section')]
        review=dict(action_id='work',document_sha256=d['sha256'],publisher='Government Research',title='Mock Public Work',publication_date='2025-12',publication_date_precision='MONTH',work_edition='2025',report_identifier='ID-2025',physical_pages=1,reviewer='test only',decision='QUALIFIED_SAME_WORK_EDITION',native_proofs=proofs)
        self.assertFalse(verify_document_identity(s,self.work,review)['scientific_admission'])
        bad=copy.deepcopy(review);bad['work_edition']='2026'
        with self.assertRaisesRegex(ValueError,'DIFFERENT_EDITION'):verify_document_identity(s,self.work,bad)
        bad=copy.deepcopy(review);bad['publisher']='Different publisher'
        with self.assertRaisesRegex(ValueError,'NOT_NATIVE'):verify_document_identity(s,self.work,bad)

    def test_hash_different_alternative_requires_reference_and_content_comparison(self):
        s,t=self.session([native_pdf(),native_pdf()])
        original=s.acquire(self.work,self.work['url'])
        alternative=s.acquire(self.work,'https://publisher.test/alternative.pdf')
        with pymupdf.open(s.out/alternative['path']) as pdf:text=pdf[0].get_text()
        proofs=[dict(page=1,role=r,markers=['Mock'],page_text_sha256=hashlib.sha256(text.encode()).hexdigest()) for r in ('title','publisher','edition_or_report_identifier','key_table_or_section')]
        review=dict(action_id='work',document_sha256=alternative['sha256'],publisher='Government Research',title='Mock Public Work',publication_date='2025-12',publication_date_precision='MONTH',work_edition='2025',report_identifier='ID-2025',physical_pages=1,reviewer='test only',decision='QUALIFIED_SAME_WORK_EDITION',native_proofs=proofs)
        with self.assertRaisesRegex(ValueError,'ALTERNATIVE_COMPARISON_REQUIRED'):verify_document_identity(s,self.work,review)
        self.work['identity_reference_sha256']=original['sha256']
        review['same_edition_comparison']=dict(reference_sha256=original['sha256'],key_pages=[1])
        self.assertFalse(verify_document_identity(s,self.work,review)['scientific_admission'])

    def test_normal_browser_event_workflow_for_inline_and_attachment(self):
        raw=native_pdf();work=self.work
        class Download:
            url=work['url']
            def save_as(self,path):Path(path).write_bytes(raw)
            def cancel(self):page.cancelled=True
        class Response:
            status=200;url=work['url'];headers={'content-type':'application/pdf','content-length':str(len(raw))}
            def body(self):
                if mode=='attachment':raise RuntimeError('Attachment body unavailable')
                if mode.startswith('pdf'):raise AssertionError('Non-200 PDF body must not be admitted')
                return raw
        class Event:
            value=Download()
            def __enter__(self):return self
            def __exit__(self,*args):
                if mode!='attachment':raise TimeoutError('No download event for inline PDF')
        class Link:
            def get_attribute(self,key):return work['url']
            def click(self):
                response=Response()
                if mode.startswith('pdf'):
                    response.status=int(mode[3:]);response.headers=dict(response.headers,**{'retry-after':'1200'})
                page.events['response'](response)
                if mode=='attachment' or mode.startswith('pdf'):page.events['download'](Download())
        class Locator:
            def evaluate_all(self,*args):return [work['url']] if page.ready else []
            def all(self):return [Link()]
        class Page:
            url=work['entry_urls'][0]
            def __init__(self):self.events={};self.ready=False;self.cancelled=False
            def set_default_timeout(self,n):pass
            def on(self,name,fn):self.events[name]=fn
            def goto(self,*args,**kwargs):return type('Navigation',(),dict(status=int(mode[3:]) if mode.startswith('nav') else 200,url=self.url,headers={'content-type':'text/html','retry-after':'1200'}))()
            def content(self):return '<title>Official publication</title><a href="original.pdf">PDF</a>'
            def locator(self,*args):return Locator()
            def expect_download(self,**kwargs):return Event()
            def wait_for_function(self,expression,*,arg,timeout):
                self.ready=True;self.wait_budget=timeout
                if not 0<timeout<=10000:raise AssertionError('Dynamic wait must be bounded')
        class Browser:
            def new_context(self,**kwargs):
                self.ignore_https_errors=kwargs['ignore_https_errors'];return self
            def new_page(self):return page
            def close(self):pass
            def route(self,*args):pass
        class Runtime:
            def __enter__(self):return self
            def __exit__(self,*args):pass
            @property
            def chromium(self):return self
            def launch(self,**kwargs):return browser
        for mode in ('inline','attachment','nav429','nav503','pdf403','pdf503','pdf206'):
            with self.subTest(mode=mode):
                page=Page();browser=Browser()
                s=RepairSession(self.cfg,self.root/mode,Transport([]),self.clock.sleep,self.clock.now)
                r=acquire_browser(s,work,Runtime())
                self.assertFalse(browser.ignore_https_errors)
                if mode in ('inline','attachment'):
                    self.assertEqual('PDF_ACQUIRED_BROWSER_PENDING_IDENTITY',r['status']);self.assertEqual(1,len(s.state['documents']))
                    self.assertEqual('READY',r['dynamic_link_wait'])
                    method=next(iter(s.state['documents'].values()))['acquisition_method']
                    self.assertEqual('BROWSER_INLINE_PDF_RESPONSE' if mode=='inline' else 'BROWSER_ATTACHMENT_DOWNLOAD_EVENT',method)
                    self.assertEqual(200,r['pdf_responses'][0]['status']);self.assertEqual([],r['redirects'])
                else:
                    self.assertEqual({},s.state['documents'])
                    if mode in ('nav429','nav503','pdf503'):
                        self.assertIn('next_retry_at',r)
                        self.assertTrue(acquire_browser(s,work,Runtime())['cache_hit'])
                    if mode.startswith('pdf'):self.assertTrue(page.cancelled)


class StreamingTests(unittest.TestCase):
    def test_browser_response_metadata_preserves_complete_redirect_chain(self):
        class Request:
            def __init__(self,url,prior=None,status=302):self.url=url;self.redirected_from=prior;self.status=status
            def response(self):return type('Response',(),dict(status=self.status))()
        first=Request('https://publisher.test/original.pdf',status=301)
        middle=Request('https://publisher.test/second.pdf',first,status=302)
        last=Request('https://publisher.test/final.pdf',middle)
        response=type('Response',(),dict(status=503,url=last.url,request=last,headers={'Content-Type':'application/pdf','Retry-After':'1200','Content-Length':'100'}))()
        info=response_info(response)
        self.assertEqual([301,302],[r['status'] for r in info['redirects']])
        self.assertEqual(first.url,info['redirects'][0]['from_url']);self.assertEqual(last.url,info['final_url'])
        self.assertEqual('application/pdf',info['content_type']);self.assertEqual('1200',info['retry_after']);self.assertEqual(503,info['status'])

    def test_gzip_stream_preserves_bytes_and_reports_actual_headers(self):
        with tempfile.TemporaryDirectory() as temp:
            raw=native_pdf();compressed=gzip.compress(raw);response=io.BytesIO(compressed)
            response.status=200;response.headers={'Content-Type':'application/pdf','Content-Encoding':'gzip','Content-Length':str(len(compressed))}
            response.geturl=lambda:'https://publisher.test/original.pdf'
            s=PublicDownloadSession({'publisher.test'},connect_timeout=3,read_timeout=7)
            with patch.object(s.opener,'open',return_value=response) as opened:
                target=Path(temp)/'staging';receipt=s.download('https://publisher.test/original.pdf',target,max_bytes=100000,total_timeout=20)
            self.assertEqual(raw,target.read_bytes());self.assertTrue(receipt['tls_verification'])
            self.assertEqual(3,opened.call_args.kwargs['timeout']);self.assertEqual(len(compressed),receipt['wire_bytes'])

    def test_size_and_total_deadline_are_bounded(self):
        for kind in ('size','deadline'):
            with self.subTest(kind=kind),tempfile.TemporaryDirectory() as temp:
                response=io.BytesIO(b'x'*100);response.status=200;response.headers={};response.geturl=lambda:'https://publisher.test/original.pdf'
                s=PublicDownloadSession({'publisher.test'})
                ticks=iter([0,2,2])
                with patch.object(s.opener,'open',return_value=response):
                    with self.assertRaises((ValueError,TimeoutError)):
                        s.download('https://publisher.test/original.pdf',Path(temp)/'staging',max_bytes=10,total_timeout=1,clock=(lambda:next(ticks)) if kind=='deadline' else __import__('time').monotonic)
