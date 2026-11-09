"""ASX transport tests use generated PDFs; no live network or frozen data needed."""
import hashlib
import io
import json
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch
from pypdf import PdfWriter
from au_ree_v2.asx import fetch_pdf,is_asx_document,linked_pdf,HOSTS
from au_ree_v2.acquisition import request,failure_details
from au_ree_v2.discovery import discover

ROOT=Path(__file__).resolve().parents[1]
PDF='https://announcements.asx.com.au/asxpdf/20250711/pdf/06lq7vsvvk6yms.pdf'
OLD=PDF.replace('announcements.','www.')
WRAPPER='https://www.asx.com.au/asx/v2/statistics/displayAnnouncement.do?display=pdf&idsId=03126345'


def pdf_bytes():
    writer=PdfWriter();writer.add_blank_page(width=100,height=100)
    buf=io.BytesIO();writer.write(buf);return buf.getvalue()


def wrapper(url=PDF):
    return ('<form action="announcementTerms.do"><input name="pdfURL" value="'+url+'" type="hidden"></form>').encode()


class ASX(unittest.TestCase):
    def setUp(self):self.pdf=pdf_bytes();self.calls=[];self.responses={};self.archived=[]
    def fetch(self,url,**kwargs):
        self.calls.append((url,kwargs))
        result=self.responses[url]
        if isinstance(result,Exception):raise result
        return result,{}
    def archive(self,raw,url,suffix):
        sha=hashlib.sha256(raw).hexdigest();self.archived.append((sha,raw,url,suffix));return sha
    def test_direct_pdf_is_validated_and_bounded(self):
        self.responses[PDF]=self.pdf
        raw,_,receipt=fetch_pdf(PDF,self.fetch,self.archive)
        self.assertEqual(self.pdf,raw);self.assertEqual('PDF_ACQUIRED',receipt['status'])
        self.assertEqual(1,receipt['attempts'][0]['physical_pages'])
        self.assertEqual(HOSTS,self.calls[0][1]['allowed_hosts'])
        self.assertEqual(1,self.calls[0][1]['max_attempts'])
        self.assertEqual(2,self.calls[0][1]['max_redirects'])
    def test_wrapper_link_is_archived_before_public_download(self):
        self.responses={WRAPPER:wrapper(),PDF:self.pdf}
        raw,_,receipt=fetch_pdf(WRAPPER,self.fetch,self.archive)
        self.assertEqual(self.pdf,raw);self.assertFalse(receipt['terms_submitted'])
        self.assertTrue(receipt['attempts'][0]['terms_interstitial_seen'])
        self.assertEqual(hashlib.sha256(wrapper()).hexdigest(),receipt['attempts'][0]['response_sha256'])
        self.assertEqual([WRAPPER,PDF],[c[0] for c in self.calls])
        self.assertEqual(PDF,receipt['resolved_url'])
    def test_iframe_html_entities_and_duplicates(self):
        body=('<iframe src="'+PDF+'"></iframe><a href="'+PDF+'">PDF</a>').encode()
        self.assertEqual(PDF,linked_pdf(body,WRAPPER))
    def test_ambiguous_files_are_not_downloaded(self):
        self.responses[WRAPPER]=wrapper()+wrapper(PDF.replace('06lq7vsvvk6yms','other'))
        with self.assertRaisesRegex(ValueError,'ASX_AMBIGUOUS'):fetch_pdf(WRAPPER,self.fetch,self.archive)
        self.assertEqual(1,len(self.calls))
    def test_untrusted_urls_never_requested(self):
        for url in [PDF.replace('https:','http:'),PDF.replace('asx.com.au','asx.com.au.evil.test'),
                    PDF.replace('https://','https://user:pass@'),PDF+'?token=secret',PDF.replace('.au/','.au:444/'),
                    'https://www.asx.com.au/asx/v2/statistics/displayAnnouncement.do?display=pdf&idsId=x']:
            with self.subTest(url=url):
                self.assertFalse(is_asx_document(url))
                with self.assertRaises(ValueError):fetch_pdf(url,self.fetch)
        self.assertFalse(self.calls)
    def test_external_hidden_link_is_not_followed(self):
        self.responses[WRAPPER]=wrapper('https://evil.test/secret.pdf')
        with self.assertRaisesRegex(ValueError,'TERMS_INTERSTITIAL'):fetch_pdf(WRAPPER,self.fetch,self.archive)
        self.assertEqual(1,len(self.calls))
    def test_same_static_path_fallback_records_original_403(self):
        self.responses={OLD:urllib.error.HTTPError(OLD,403,'Forbidden',{},io.BytesIO(b'blocked')),PDF:self.pdf}
        _,_,receipt=fetch_pdf(OLD,self.fetch,self.archive)
        self.assertEqual('HTTP_403_RESTRICTED',receipt['attempts'][0]['failure_status'])
        self.assertEqual('SAME_ASX_STATIC_PATH',receipt['attempts'][1]['basis'])
        self.assertEqual(b'blocked',self.archived[0][1])
    def test_429_stops_without_retry_or_alternative(self):
        self.responses[OLD]=urllib.error.HTTPError(OLD,429,'rate limited',{'Retry-After':'60'},io.BytesIO(b'rate'))
        with self.assertRaises(urllib.error.HTTPError) as caught:fetch_pdf(OLD,self.fetch,self.archive)
        self.assertEqual(1,len(self.calls))
        self.assertIn('asx_acquisition',failure_details(caught.exception))
    def test_403_with_retry_after_is_deferred(self):
        self.responses[OLD]=urllib.error.HTTPError(OLD,403,'wait',{'Retry-After':'60'},io.BytesIO(b'wait'))
        with self.assertRaises(urllib.error.HTTPError):fetch_pdf(OLD,self.fetch,self.archive)
        self.assertEqual(1,len(self.calls))
    def test_200_challenge_is_not_a_pdf(self):
        self.responses={OLD:b'<html>Incapsula CAPTCHA</html>',PDF:self.pdf}
        _,_,receipt=fetch_pdf(OLD,self.fetch,self.archive)
        self.assertEqual('ASX_ANTI_BOT_CHALLENGE',receipt['attempts'][0]['validation_error'])
    def test_no_invented_id_route_when_wrapper_is_blocked(self):
        self.responses[WRAPPER]=b'<html>Incapsula CAPTCHA</html>'
        with self.assertRaisesRegex(ValueError,'ASX_ANTI_BOT'):fetch_pdf(WRAPPER,self.fetch,self.archive)
        self.assertEqual(1,len(self.calls))
    def test_fake_pdf_is_archived_and_rejected(self):
        self.responses[PDF]=b'%PDF-1.7 fake'
        with self.assertRaisesRegex(ValueError,'ASX_INVALID_PDF'):fetch_pdf(PDF,self.fetch,self.archive)
        self.assertEqual('.response',self.archived[0][3])
    def test_owner_permissions_do_not_reject_readable_pdf(self):
        writer=PdfWriter();writer.add_blank_page(width=100,height=100)
        writer.encrypt('',owner_password='owner-fixture');buf=io.BytesIO();writer.write(buf)
        self.responses[PDF]=buf.getvalue()
        _,_,receipt=fetch_pdf(PDF,self.fetch)
        self.assertEqual('PDF_ACQUIRED',receipt['status'])
    def test_password_required_pdf_is_rejected(self):
        writer=PdfWriter();writer.add_blank_page(width=100,height=100)
        writer.encrypt('secret-fixture');buf=io.BytesIO();writer.write(buf)
        self.responses[PDF]=buf.getvalue()
        with self.assertRaisesRegex(ValueError,'ASX_INVALID_PDF'):fetch_pdf(PDF,self.fetch,self.archive)
    def test_request_budget_is_enforced(self):
        self.responses[WRAPPER]=wrapper()
        with self.assertRaisesRegex(ValueError,'ASX_REQUEST_BUDGET_EXHAUSTED'):fetch_pdf(WRAPPER,self.fetch,self.archive,max_requests=1)
        self.assertEqual(1,len(self.calls))
    def test_byte_budget_even_for_custom_transport(self):
        self.responses[PDF]=self.pdf
        with self.assertRaisesRegex(ValueError,'BYTE_BUDGET'):fetch_pdf(PDF,self.fetch,max_bytes=1)
    def test_final_url_cannot_escape_scope(self):
        def transport(url,**kwargs):return self.pdf,{'X-Resolved-URL':'https://evil.test/file.pdf'}
        with self.assertRaisesRegex(ValueError,'RESOLVED_URL'):fetch_pdf(PDF,transport)
    def test_redirects_count_towards_budget(self):
        def transport(url,**kwargs):
            self.calls.append(url)
            return wrapper(),{'X-Redirect-Chain':json.dumps([WRAPPER]),'X-Resolved-URL':WRAPPER}
        with self.assertRaisesRegex(ValueError,'ASX_REQUEST_BUDGET_EXHAUSTED'):fetch_pdf(WRAPPER,transport,max_requests=2)
        self.assertEqual(1,len(self.calls))
    def test_guard_blocks_redirect_before_network(self):
        handlers=[]
        def build(handler):handlers.append(handler);return object()
        with patch('urllib.request.build_opener',side_effect=build):
            with self.assertRaises(AttributeError):request(PDF,allowed_hosts=HOSTS)
        with self.assertRaisesRegex(ValueError,'DESTINATION_NOT_ALLOWED'):
            handlers[0].redirect_request(urllib.request.Request(PDF),None,302,'',{},'https://evil.test/x')
    def test_guard_blocks_initial_destination(self):
        with patch('urllib.request.build_opener') as build:
            with self.assertRaisesRegex(ValueError,'DESTINATION_NOT_ALLOWED'):request('https://evil.test/x',allowed_hosts=HOSTS)
            build.assert_not_called()
    def test_transport_429_preserves_retry_after(self):
        error=urllib.error.HTTPError(PDF,429,'wait',{'Retry-After':'60'},io.BytesIO(b'wait'))
        with patch('urllib.request.urlopen',side_effect=error) as open_url,patch('time.sleep') as sleep:
            with self.assertRaises(urllib.error.HTTPError) as caught:request(PDF,max_attempts=1,min_interval=0)
            self.assertEqual(60,caught.exception.retry_after_seconds)
            self.assertEqual(1,open_url.call_count);sleep.assert_not_called()
    def test_guard_checks_appended_query_parameters(self):
        with patch('urllib.request.build_opener'):
            with self.assertRaisesRegex(ValueError,'DESTINATION_NOT_ALLOWED'):
                request(PDF,params={'token':'fixture'},allowed_hosts=HOSTS)
    def test_discovery_integration_and_verified_cache(self):
        (ROOT/'work').mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ROOT/'work') as tmp:
            root=Path(tmp);(root/'data/snapshots').mkdir(parents=True)
            (root/'data/manifest.json').write_text('{"snapshots":[]}')
            archive='https://issuer.test/archive'
            self.responses={archive:('<a href="'+WRAPPER.replace('&','&amp;')+'">Mineral resource</a>').encode(),WRAPPER:wrapper(),PDF:self.pdf}
            config=dict(asx_public_acquisition=True,seeds=[dict(key='fixture',url=archive,allowed_hosts=['issuer.test','www.asx.com.au'])])
            result=discover(root,config,self.fetch);doc=result['documents'][0]
            self.assertEqual('SNAPSHOT_REQUIRES_DATED_SCOPE_EXTRACTION',doc['status'])
            manifest=json.loads((root/'data/manifest.json').read_text())
            original=next(s for s in manifest['snapshots'] if s['kind']=='pdf')
            self.assertEqual(WRAPPER,original['url'])
            self.assertEqual(PDF,original['asx_acquisition']['resolved_url'])
            self.calls.clear();again=discover(root,config,self.fetch)
            self.assertEqual('REUSED_VERIFIED_ORIGINAL',again['documents'][0]['status'])
            self.assertEqual([archive],[c[0] for c in self.calls])
            (root/original['path']).write_bytes(b'corrupted')
            failed=discover(root,config,self.fetch)
            self.assertEqual('IMMUTABLE_SNAPSHOT_CONTENT_MISMATCH',failed['sources'][0]['validation_error'])
    def test_direct_seed_integration_and_default_compatibility(self):
        (ROOT/'work').mkdir(exist_ok=True)
        for enabled in (False,True):
            with self.subTest(enabled=enabled),tempfile.TemporaryDirectory(dir=ROOT/'work') as tmp:
                root=Path(tmp);(root/'data/snapshots').mkdir(parents=True)
                (root/'data/manifest.json').write_text('{"snapshots":[]}')
                self.responses={WRAPPER:wrapper(),PDF:self.pdf}
                cfg=dict(asx_public_acquisition=enabled,seeds=[dict(key='test',url=WRAPPER,allowed_hosts=list(HOSTS))])
                result=discover(root,cfg,self.fetch)
                self.assertEqual(1 if enabled else 0,len(result['documents']))


if __name__=='__main__':unittest.main()
