import unittest, tempfile, json, hashlib, subprocess
from pathlib import Path
from unittest.mock import patch, Mock
from urllib.error import HTTPError, URLError
from au_ree_v2.acquisition import StrictTransport, strict_refresh

class StrictAcquisitionTests(unittest.TestCase):
    def setUp(self):
        # These transport/registry unit fixtures do not depend on public DNS.
        self.dns=patch('au_ree_v2.acquisition.strict_dns_preflight',return_value=[dict(host='example.com',status='DNS_OK',error='')])
        self.dns.start();self.addCleanup(self.dns.stop)
    def error(self,code):return HTTPError('https://example.com/a',code,'test',{},None)
    def response(self,raw=b'%PDF test'):
        r=Mock();r.__enter__=Mock(return_value=r);r.__exit__=Mock(return_value=False)
        r.status=200;r.headers={};r.geturl.return_value='https://example.com/a';r.read.return_value=raw
        return r
    @patch('au_ree_v2.acquisition.time.sleep')
    def test_all_4xx_stop_host(self,sleep):
        for code in (400,401,403,404,408,429):
            t=StrictTransport({'example.com':'document'});t.opener.open=Mock(side_effect=self.error(code))
            with self.assertRaises(HTTPError):t('https://example.com/a')
            with self.assertRaisesRegex(ValueError,'HOST_STOPPED'):t('https://example.com/b')
            self.assertEqual(t.opener.open.call_count,1)
    @patch('au_ree_v2.acquisition.time.sleep')
    def test_retry_only_once(self,sleep):
        for error in (self.error(503),URLError(TimeoutError())):
            t=StrictTransport({'example.com':'document'});t.opener.open=Mock(side_effect=error)
            with self.assertRaises(Exception):t('https://example.com/a')
            self.assertEqual(t.opener.open.call_count,2)
        t=StrictTransport({'example.com':'document'});t.opener.open=Mock(side_effect=URLError('DNS'))
        with self.assertRaises(URLError):t('https://example.com/a')
        self.assertEqual(t.opener.open.call_count,1)
    @patch('au_ree_v2.acquisition.time.sleep')
    def test_challenge_stops(self,sleep):
        t=StrictTransport({'example.com':'document'});t.opener.open=Mock(return_value=self.response(b'<html>captcha</html>'))
        with self.assertRaisesRegex(ValueError,'CAPTCHA_OR_LOGIN'):t('https://example.com/a')
        with self.assertRaisesRegex(ValueError,'HOST_STOPPED'):t('https://example.com/b')
    @patch('au_ree_v2.acquisition.time.monotonic',return_value=100)
    @patch('au_ree_v2.acquisition.time.sleep')
    def test_spacing_ua(self,sleep,clock):
        t=StrictTransport({'example.com':'document'});t.opener.open=Mock(return_value=self.response())
        t('https://example.com/a',headers={'User-Agent':'bad'});t('https://example.com/b')
        sleep.assert_called_with(3)
        self.assertEqual(t.opener.open.call_args.args[0].get_header('User-agent'),'AU_REE_V2/0.1 public research')
    def fixture(self,root):
        (root/'data/snapshots').mkdir(parents=True)
        raw=b'%PDF original';sha=hashlib.sha256(raw).hexdigest();path='data/snapshots/'+sha+'.pdf';(root/path).write_bytes(raw)
        source=dict(key='pdf',kind='pdf',url='https://example.com/a',source_sha256=sha)
        snapshot=dict(source,sha256=sha,path=path,publication_date='2026-01-01',available_date='2026-01-01',acquired_at='2026-01-01')
        (root/'data/manifest.json').write_text(json.dumps({'snapshots':[snapshot]}))
        subprocess.run(['git','init','-q'],cwd=root,check=True);subprocess.run(['git','add','data'],cwd=root,check=True)
        subprocess.run(['git','-c','user.name=Test','-c','user.email=test@example.invalid','commit','-qm','fixture'],cwd=root,check=True)
        return {'sources':[source]},raw
    def test_sha_changed_no_fallback(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);registry,_=self.fixture(root)
            with patch.object(StrictTransport,'__call__',return_value=(b'%PDF changed',{})):
                snapshots,outcomes=strict_refresh(root,registry,root/'work',{},'2026-11-13')
            self.assertEqual(snapshots,[]);self.assertEqual(outcomes[0]['status'],'SOURCE_SHA_CHANGED')
    def test_fallback_must_be_committed_exact(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);registry,_=self.fixture(root)
            with patch.object(StrictTransport,'__call__',side_effect=self.error(403)):
                snapshots,outcomes=strict_refresh(root,registry,root/'work',{},'2026-11-13')
                self.assertEqual(len(snapshots),1)
                Path(root/snapshots[0]['path']).write_bytes(b'changed')
                snapshots,outcomes=strict_refresh(root,registry,root/'work',{},'2026-11-13')
                self.assertFalse(snapshots)
    def test_new_work_cache_and_no_manifest_mutation(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);registry,raw=self.fixture(root);before=(root/'data/manifest.json').read_bytes()
            with patch.object(StrictTransport,'__call__',return_value=(raw,{})):
                one,_=strict_refresh(root,registry,root/'work',{},'2026-11-13');two,_=strict_refresh(root,registry,root/'work',{},'2026-11-13')
            self.assertNotEqual(one[0]['path'],two[0]['path']);self.assertTrue(Path(one[0]['path']).is_relative_to(root/'work'))
            self.assertEqual(before,(root/'data/manifest.json').read_bytes())
    def test_redirect_rejects_unknown_and_cross_class(self):
        import urllib.request
        t=StrictTransport({'example.com':'document','gov.example':'government','cdn.example':'document'})
        handler=next(h for h in t.opener.handlers if isinstance(h,urllib.request.HTTPRedirectHandler))
        request=urllib.request.Request('https://example.com/a')
        for url in ('https://unknown.example/a','https://gov.example/a','http://example.com/a'):
            with self.assertRaisesRegex(ValueError,'REDIRECT_DESTINATION_NOT_APPROVED'):
                handler.redirect_request(request,None,302,'',{},url)
        self.assertEqual(handler.redirect_request(request,None,302,'',{},'https://cdn.example/a').full_url,'https://cdn.example/a')
    def test_stopped_redirect_destination(self):
        import urllib.request
        t=StrictTransport({'example.com':'document','cdn.example':'document'});t.stopped['cdn.example']='403'
        handler=next(h for h in t.opener.handlers if isinstance(h,urllib.request.HTTPRedirectHandler))
        with self.assertRaisesRegex(ValueError,'HOST_STOPPED'):
            handler.redirect_request(urllib.request.Request('https://example.com/a'),None,302,'',{},'https://cdn.example/a')

    def test_approved_host_classifications(self):
        from au_ree_v2.acquisition import STRICT_HOSTS
        self.assertNotIn('www.aspecthuntley.com.au',STRICT_HOSTS)
        self.assertEqual(STRICT_HOSTS['api.investi.com.au'],'aggregator')
    def test_rejected_redirect_records_original_http(self):
        import urllib.request
        t=StrictTransport({'example.com':'document'})
        handler=next(h for h in t.opener.handlers if isinstance(h,urllib.request.HTTPRedirectHandler))
        with self.assertRaises(ValueError):
            handler.redirect_request(urllib.request.Request('https://example.com/a'),None,302,'',{},'https://unknown.example/a')
        self.assertEqual(t.http['example.com'],302)
        self.assertEqual(t.attempts,[{'host':'example.com','http_status':302}])
