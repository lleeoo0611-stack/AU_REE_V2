"""Real local HTTP responses; production URL/redirect rules remain enabled."""
import hashlib
import http.client
import json
import sqlite3
import tempfile
import threading
import unittest
import urllib.request
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from au_ree_v2 import acquisition as a
from au_ree_v2.store import SCHEMA
import test_strict_acquisition as strict_fixtures

ROOT = Path(__file__).resolve().parents[1]
PDF = b'%PDF-1.7 immutable reviewed test document\n'
SHA = hashlib.sha256(PDF).hexdigest()


class LocalFallback(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(dir=ROOT/'work')
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        (self.root/'config').mkdir()
        self.calls, self.routes = [], {}
        case = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                host = self.headers['Host'].split(':')[0]
                case.calls.append((host, self.path, 'GET', self.headers.get('User-Agent')))
                default = (200, b'User-agent: *\nAllow: /\n', {}) if self.path == '/robots.txt' else (404, b'missing', {})
                status, body, headers = case.routes.get((host, self.path), default)
                self.send_response(status)
                for key, value in headers.items():
                    self.send_header(key, value)
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_POST(self):
                case.calls.append((self.headers['Host'], self.path, 'POST', None))
                self.send_error(405)

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        port = self.server.server_port

        class LocalWire(urllib.request.HTTPSHandler):
            # Only the test wire changes: HTTPS-labelled requests go to this
            # local HTTP server. No public DNS, proxies or external sockets.
            def https_open(self, req):
                def connection(*args, **kwargs):
                    return http.client.HTTPConnection('127.0.0.1', port, timeout=kwargs.get('timeout', 5))
                return self.do_open(connection, req)

        self.local_wire = LocalWire
        self.sleep = patch.object(a.time, 'sleep')
        self.sleep.start()
        self.addCleanup(self.sleep.stop)
        self.policy = dict(enabled=True,trigger_statuses=['NOT_PDF','HOST_STOPPED','HTTP_404','LOGIN_OR_CAPTCHA','ROBOTS_DISALLOWED'],
                           issuer_ir_indexes={},approved_hosts=['mirror.test'],max_candidates_per_source=8,
                           max_fallback_requests_per_build=400,search_api=dict(enabled=False,provider=None))

    def make(self):
        (self.root/'config/evidence_policy.json').write_text(json.dumps({'same_sha_fallback':self.policy}))
        primary = a.StrictTransport({'primary.test':'document','www.asx.com.au':'asx','announcements.asx.com.au':'asx'})
        helper = a.SameSHAAlternates(self.root, primary)
        for transport in (primary, helper.transport):
            redirect = next(h for h in transport.opener.handlers if isinstance(h, urllib.request.HTTPRedirectHandler))
            transport.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), self.local_wire(), redirect)
        return primary, helper

    def source(self, *urls):
        return dict(key='reviewed',kind='pdf',url='https://primary.test/main.pdf',source_sha256=SHA,
                    issuer=dict(name='Reviewed issuer',asx_code='TEST'),title_tokens=['North Stanmore'],
                    publication_date='2026-06-01',alternate_policy='SAME_SHA_ONLY',alternate_urls=list(urls))

    def find(self, helper, source):
        receipt = dict(key=source['key'],status='UNAVAILABLE',stop_reason='NOT_PDF',http_status=200)
        result = helper.find(source, receipt, {SHA}, self.root)
        return result, receipt

    def test_identical_bytes_adopted_without_editing_configuration(self):
        _, helper = self.make()
        source = self.source('https://mirror.test/copy.pdf')
        self.routes['mirror.test','/copy.pdf'] = (200, PDF, {})
        before = (self.root/'config/evidence_policy.json').read_bytes()
        result, receipt = self.find(helper, source)
        self.assertEqual('ALTERNATE_SAME_SHA', receipt['status'])
        self.assertEqual(SHA, result['sha256'])
        self.assertEqual(PDF, Path(result['path']).read_bytes())
        self.assertEqual('https://mirror.test/copy.pdf', result['url'])
        helper.save(self.root)
        proposed = json.loads((self.root/'proposed_sources_patch.json').read_text())
        self.assertTrue(proposed['requires_researcher_approval'])
        self.assertEqual(['https://mirror.test/copy.pdf'], proposed['changes'][0]['alternate_urls'])
        self.assertEqual(before, (self.root/'config/evidence_policy.json').read_bytes())
        self.assertTrue(all(c[3]=='AU_REE_V2/0.1 public research' for c in self.calls))

    def test_different_sha_discarded_and_written_to_review_queue(self):
        _, helper = self.make()
        self.routes['mirror.test','/wrong.pdf'] = (200, b'%PDF wrong edition', {})
        result, receipt = self.find(helper, self.source('https://mirror.test/wrong.pdf'))
        self.assertIsNone(result)
        self.assertFalse(list(self.root.glob('*.pdf')))
        mismatches = json.loads(receipt['alternate_mismatches'])
        self.assertEqual('ALTERNATE_SHA_MISMATCH', mismatches[0]['reason'])
        from au_ree_v2.cli import strict_claims
        db = sqlite3.connect(':memory:')
        db.executescript(SCHEMA)
        strict_claims(db,self.root,[],{'projects':[]},[receipt],self.root/'pages')
        self.assertEqual(1,db.execute("SELECT count(*) FROM review_queue WHERE reason='ALTERNATE_SHA_MISMATCH'").fetchone()[0])
        db.close()

    def test_index_network_failure_remains_a_network_failure(self):
        self.policy['issuer_ir_indexes'] = {'TEST':'https://mirror.test/announcements'}
        _, helper = self.make()
        with patch.object(helper.transport.opener, 'open', side_effect=urllib.error.URLError('fixture refused connection')):
            result, receipt = self.find(helper, self.source())
        self.assertIsNone(result)
        self.assertTrue(receipt['network_error'])
        self.assertIn('fixture refused connection', helper.reports[0]['stop_reason'])

    def test_robots_disallow_prevents_pdf_request(self):
        _, helper = self.make()
        self.routes['mirror.test','/robots.txt'] = (200, b'\xef\xbb\xbfUser-agent: *\nDisallow: /blocked.pdf\n', {})
        result, _ = self.find(helper, self.source('https://mirror.test/blocked.pdf'))
        self.assertIsNone(result)
        self.assertEqual(['/robots.txt'], [c[1] for c in self.calls])
        self.assertIn('ROBOTS_DISALLOWED', str(helper.reports))

    def test_robots_404_and_410_allow_primary_and_alternate_requests_once(self):
        for code in (404,410):
            with self.subTest(code=code):
                self.calls.clear()
                primary, helper = self.make()
                for host in ('primary.test','mirror.test'):
                    self.routes[host,'/robots.txt'] = (code,b'missing rules',{})
                    for name in ('first.pdf','second.pdf'):
                        self.routes[host,'/'+name] = (200,PDF,{})
                self.assertEqual(PDF,primary('https://primary.test/first.pdf')[0])
                self.assertEqual(PDF,primary('https://primary.test/second.pdf')[0])
                result, receipt = self.find(helper,self.source('https://mirror.test/first.pdf'))
                self.assertEqual('ALTERNATE_SAME_SHA',receipt['status'])
                self.assertEqual(SHA,result['sha256'])
                self.assertEqual(PDF,helper.transport('https://mirror.test/second.pdf')[0])
                counts = Counter((c[0],c[1]) for c in self.calls)
                self.assertEqual(1,counts['primary.test','/robots.txt'])
                self.assertEqual(1,counts['mirror.test','/robots.txt'])
                self.assertFalse(primary.stopped)
                self.assertEqual(2,sum(a['http_status']==code for a in primary.attempts))

    def test_robots_authentication_and_rate_limits_stop_the_host(self):
        for code in (401,429):
            with self.subTest(code=code):
                self.calls.clear()
                primary, helper = self.make()
                for host in ('primary.test','mirror.test'):
                    self.routes[host,'/robots.txt'] = (code,b'restricted',{})
                with self.assertRaises(urllib.error.HTTPError):
                    primary('https://primary.test/first.pdf')
                with self.assertRaisesRegex(ValueError,'HOST_STOPPED'):
                    primary('https://primary.test/second.pdf')
                result, _ = self.find(helper,self.source('https://mirror.test/first.pdf','https://mirror.test/second.pdf'))
                self.assertIsNone(result)
                self.assertEqual([('primary.test','/robots.txt'),('mirror.test','/robots.txt')],[(c[0],c[1]) for c in self.calls])
                self.assertEqual({'primary.test':str(code),'mirror.test':str(code)},primary.stopped)

    def test_robots_server_errors_and_network_failures_remain_cached_disallow(self):
        primary, helper = self.make()
        self.routes['primary.test','/robots.txt'] = (503,b'server unavailable',{})
        with self.assertRaises(urllib.error.HTTPError):
            primary('https://primary.test/first.pdf')
        with self.assertRaisesRegex(ValueError,'ROBOTS_DISALLOWED'):
            primary('https://primary.test/second.pdf')
        self.assertEqual(['/robots.txt','/robots.txt'],[c[1] for c in self.calls])
        for failure in (urllib.error.URLError('fixture refused connection'),urllib.error.URLError(TimeoutError())):
            with self.subTest(failure=str(failure)):
                primary, helper = self.make()
                with patch.object(primary.opener,'open',side_effect=failure) as request:
                    with self.assertRaises(urllib.error.URLError):
                        primary('https://primary.test/first.pdf')
                    before = request.call_count
                    with self.assertRaisesRegex(ValueError,'ROBOTS_DISALLOWED'):
                        primary('https://primary.test/second.pdf')
                    self.assertEqual(before,request.call_count)
                    self.assertIn(before,(1,2))

    def test_document_404_and_410_still_stop_host_after_missing_robots(self):
        for code in (404,410):
            with self.subTest(code=code):
                self.calls.clear()
                primary, _ = self.make()
                self.routes['primary.test','/robots.txt'] = (404,b'no robots',{})
                self.routes['primary.test','/missing.pdf'] = (code,b'no document',{})
                with self.assertRaises(urllib.error.HTTPError):
                    primary('https://primary.test/missing.pdf')
                with self.assertRaisesRegex(ValueError,'HOST_STOPPED'):
                    primary('https://primary.test/later.pdf')
                self.assertEqual(['/robots.txt','/missing.pdf'],[c[1] for c in self.calls])
                self.assertEqual(str(code),primary.stopped['primary.test'])

    def test_4xx_stops_all_later_requests_to_host(self):
        _, helper = self.make()
        result, _ = self.find(helper, self.source('https://mirror.test/404.pdf','https://mirror.test/later.pdf'))
        self.assertIsNone(result)
        self.assertEqual(['/robots.txt','/404.pdf'], [c[1] for c in self.calls])
        self.assertEqual('404', helper.transport.stopped['mirror.test'])

    def test_candidate_budget_skips_remaining_documents_and_index(self):
        self.policy.update(max_candidates_per_source=2,issuer_ir_indexes={'TEST':'https://issuer.test/index'})
        _, helper = self.make()
        for i in range(3):
            self.routes['mirror.test',f'/{i}.pdf'] = (200, b'%PDF wrong', {})
        self.find(helper,self.source(*(f'https://mirror.test/{i}.pdf' for i in range(3))))
        self.assertEqual(2,helper.reports[0]['candidate_count'])
        self.assertNotIn('/2.pdf',[c[1] for c in self.calls])
        self.assertNotIn('/index',[c[1] for c in self.calls])

    def test_build_request_budget_covers_robots_and_retries(self):
        self.policy['max_fallback_requests_per_build'] = 2
        _, helper = self.make()
        self.routes['mirror.test','/retry.pdf'] = (503, b'temporary', {})
        self.find(helper,self.source('https://mirror.test/retry.pdf','https://mirror.test/next.pdf'))
        self.assertLessEqual(len(self.calls),2)
        before=len(self.calls)
        self.find(helper,self.source('https://mirror.test/third.pdf'))
        self.assertEqual(before,len(self.calls))
        self.assertIn('FALLBACK_REQUEST_BUDGET_EXHAUSTED',str(helper.reports))

    def test_redirect_outside_allowed_hosts_never_followed(self):
        _, helper = self.make()
        self.routes['mirror.test','/redirect.pdf'] = (302,b'',{'Location':'https://outside.test/secret.pdf'})
        result, _ = self.find(helper,self.source('https://mirror.test/redirect.pdf'))
        self.assertIsNone(result)
        self.assertFalse(any(c[0]=='outside.test' for c in self.calls))
        self.assertIn('REDIRECT_DESTINATION_NOT_APPROVED',str(helper.reports))

    def test_allowed_redirect_still_checks_destination_robots(self):
        self.policy['issuer_ir_indexes'] = {'TEST':'https://issuer.test/index'}
        _, helper = self.make()
        self.routes['mirror.test','/redirect.pdf'] = (302,b'',{'Location':'https://issuer.test/blocked.pdf'})
        self.routes['issuer.test','/robots.txt'] = (200,b'User-agent: *\nDisallow: /blocked.pdf\n',{})
        result, _ = self.find(helper,self.source('https://mirror.test/redirect.pdf'))
        self.assertIsNone(result)
        self.assertFalse(any(c[1]=='/blocked.pdf' for c in self.calls))

    def test_terms_and_login_pages_are_not_parsed_or_submitted(self):
        from au_ree_v2.discovery import candidates
        for body in (b'<html>Terms and conditions<a href="https://mirror.test/hidden.pdf">North Stanmore</a>',
                     b'<html><form action="/login"><input type="password"></form>',
                     b'<html><title>Login</title><a href="https://mirror.test/hidden.pdf">North Stanmore</a>',
                     b'<html><form action="/login"></form>'):
            with self.subTest(body=body):
                self.policy['issuer_ir_indexes'] = {'TEST':'https://issuer.test/index'}
                _, helper = self.make()
                self.routes['issuer.test','/index'] = (200,body,{})
                with patch('au_ree_v2.discovery.candidates',wraps=candidates) as parse:
                    result, _ = self.find(helper,self.source())
                self.assertIsNone(result)
                parse.assert_not_called()
                before = len(self.calls)
                with self.assertRaisesRegex(ValueError,'HOST_STOPPED'):
                    helper.transport('https://issuer.test/another.pdf')
                self.assertEqual(before,len(self.calls))
        self.assertFalse(any(c[1]=='/hidden.pdf' or c[2]=='POST' for c in self.calls))

    def test_login_candidate_stops_remaining_requests_to_same_host(self):
        _, helper = self.make()
        self.routes['mirror.test','/login.pdf'] = (200,b'<html><h1>Sign in</h1>',{})
        self.routes['mirror.test','/next.pdf'] = (200,PDF,{})
        result, _ = self.find(helper,self.source('https://mirror.test/login.pdf','https://mirror.test/next.pdf'))
        self.assertIsNone(result)
        self.assertEqual(['/robots.txt','/login.pdf'],[c[1] for c in self.calls])
        self.assertEqual('CAPTCHA_OR_LOGIN',helper.primary.stopped['mirror.test'])

    def test_long_primary_queries_keep_receipts_readable_without_dropping_attempts(self):
        primary, helper = self.make()
        for index in range(40):
            path = '/query?where=' + 'x'*5000 + '&page=' + str(index)
            self.routes['primary.test',path] = (200,PDF,{})
            primary('https://primary.test'+path)
        self.assertEqual(41,len(primary.attempts))
        payload = json.dumps(primary.attempts)
        self.assertLess(len(payload),131072)
        self.assertFalse(any('url' in a for a in primary.attempts))
        self.routes['mirror.test','/copy.pdf'] = (200,PDF,{})
        self.find(helper,self.source('https://mirror.test/copy.pdf'))
        self.assertTrue(all('url' in a for a in primary.attempts if a['host']=='mirror.test'))

    def test_first_non_pdf_stops_www_in_probe_and_main_build(self):
        primary, _ = self.make()
        registry=dict(sources=[dict(key=host+str(i),kind='pdf',url='https://'+host+'/'+str(i)+'.pdf')
                              for host in ('www.asx.com.au','announcements.asx.com.au') for i in range(3)])
        self.routes['www.asx.com.au','/0.pdf'] = (200,b'<html>Terms and conditions<form action="/consent"></form>',{})
        for i in range(3):
            self.routes['announcements.asx.com.au',f'/{i}.pdf'] = (200,PDF,{})
        rows=a.strict_asx_probe(registry,primary)
        self.assertEqual(['UNAVAILABLE','HOST_STOPPED','HOST_STOPPED','FETCHED','FETCHED','FETCHED'],[r['status'] for r in rows])
        before=len(self.calls)
        with self.assertRaisesRegex(ValueError,'HOST_STOPPED'):
            primary('https://www.asx.com.au/another.pdf')
        self.assertEqual(before,len(self.calls))
        self.assertEqual(['/robots.txt','/0.pdf'],[c[1] for c in self.calls if c[0]=='www.asx.com.au'])

    def test_index_filters_by_title_or_seven_day_date_and_is_fetched_once(self):
        self.policy['issuer_ir_indexes'] = {'TEST':'https://issuer.test/index'}
        _, helper = self.make()
        body=b'<a href="https://mirror.test/wrong.pdf">Other project</a><a href="https://mirror.test/title.pdf">North Stanmore</a><table><tr><td>04/06/2026</td><td><a href="https://mirror.test/date.pdf">Quarterly</a></td></tr></table>'
        self.routes['issuer.test','/index']=(200,body,{})
        self.routes['mirror.test','/title.pdf']=(200,b'%PDF different',{})
        self.routes['mirror.test','/date.pdf']=(200,PDF,{})
        self.assertIsNotNone(self.find(helper,self.source())[0])
        self.assertIsNotNone(self.find(helper,self.source())[0])
        counts=Counter((c[0],c[1]) for c in self.calls)
        self.assertEqual(1,counts['issuer.test','/index'])
        self.assertEqual(0,counts['mirror.test','/wrong.pdf'])

    def test_main_acquisition_stops_www_after_first_non_pdf(self):
        primary,_=self.make()
        (self.root/'data').mkdir()
        (self.root/'data/manifest.json').write_text('{"snapshots":[]}')
        registry={'sources':[dict(self.source(),key=str(i),url=f'https://www.asx.com.au/{i}.pdf') for i in range(2)]}
        self.routes['www.asx.com.au','/0.pdf']=(200,b'<html>Terms and conditions</html>',{})
        with patch.object(a,'strict_dns_preflight',return_value=[]):
            selected,receipts=a.strict_refresh(self.root,registry,self.root/'work',{},'2026-11-13',primary)
        self.assertEqual([],selected)
        self.assertEqual(['UNAVAILABLE','HOST_STOPPED'],[r['status'] for r in receipts])
        self.assertEqual(['/robots.txt','/0.pdf'],[c[1] for c in self.calls])

    def test_invalid_budgets_and_unimplemented_search_fail_before_requests(self):
        for field,value in [('max_candidates_per_source',9),('max_fallback_requests_per_build',401)]:
            with self.subTest(field=field):
                old=self.policy[field]
                self.policy[field]=value
                with self.assertRaisesRegex(ValueError,'INVALID_FALLBACK_BUDGET'):self.make()
                self.policy[field]=old
        self.policy['search_api']['enabled']=True
        with self.assertRaisesRegex(ValueError,'SEARCH_API_PROVIDER_NOT_IMPLEMENTED'):self.make()
        self.assertFalse(self.calls)


class ValidatedParent(unittest.TestCase):
    def test_own_transcription_hash_is_not_used_as_parent_pdf_hash(self):
        for kind in ('official_table_transcription','official_project_catalogue_transcription'):
            for valid in (True,False):
                with self.subTest(kind=kind,valid=valid),tempfile.TemporaryDirectory(dir=ROOT/'work') as folder:
                    root=Path(folder)
                    registry,pdf=strict_fixtures.StrictAcquisitionTests.fixture(self,root)
                    parent=registry['sources'][0]['source_sha256']
                    body=b'project,value\nreviewed,1\n';sha=hashlib.sha256(body).hexdigest()
                    path='data/snapshots/'+sha+'.csv';(root/path).write_bytes(body)
                    child=dict(key='table',kind=kind,url=registry['sources'][0]['url'],source_sha256=sha,
                               parent_source_sha256=parent if valid else '0'*64,committed_snapshot_sha256=sha)
                    registry['sources'].append(child)
                    manifest=json.loads((root/'data/manifest.json').read_text())
                    manifest['snapshots'].append(dict(child,sha256=sha,path=path,publication_date='2026-01-01',available_date='2026-01-01',acquired_at='2026-01-01'))
                    (root/'data/manifest.json').write_text(json.dumps(manifest))
                    import subprocess
                    subprocess.run(['git','add','data'],cwd=root,check=True)
                    subprocess.run(['git','-c','user.name=Test','-c','user.email=test@example.invalid','commit','-qm','transcription'],cwd=root,check=True)
                    with patch.object(a,'strict_dns_preflight',return_value=[]),patch.object(a.StrictTransport,'__call__',return_value=(pdf,{})):
                        selected,receipts=a.strict_refresh(root,registry,root/'work',{},'2026-11-13')
                    self.assertEqual(valid,any(s['key']=='table' for s in selected))
                    self.assertEqual('COMMITTED_SNAPSHOT_SAME_SHA' if valid else 'SOURCE_NOT_ACQUIRED',receipts[-1]['status'])


class RepositoryContract(unittest.TestCase):
    def test_source_budget_and_declared_metadata(self):
        import subprocess,csv
        def git(*args):return subprocess.check_output(['git',*args],cwd=ROOT).decode('utf8')
        def lines(ref,end=None):
            revisions=[ref,end] if end else [ref]
            return sum(int(v) for row in git('diff','--numstat',*revisions,'--','src').splitlines() for v in row.split('\t')[:2])
        # Preserve the original round's limit separately from the approved v4 work.
        self.assertLessEqual(lines('12f45f4','e84c0e0'),250)
        self.assertLessEqual(lines('09ace21'),250)
        self.assertLessEqual(lines('070df10'),2134)  # Researcher approved v7, 2026-11-17.
        self.assertLessEqual(lines('ac65aaf'),60)
        self.assertEqual('src/au_ree_v2/census.py',git('diff','--name-only','ac65aaf','--','src').strip())
        self.assertEqual('',git('diff','--name-only','--diff-filter=A','12f45f4','--','src','config'))
        with (ROOT/'results/integrated-rebuild-2026-11-15/acquisition_report.csv').open(encoding='utf-8-sig',newline='') as f:
            blocked={r['key'] for r in csv.DictReader(f) if r['host']=='www.asx.com.au' and r['stop_reason']=='NOT_PDF'}
        self.assertEqual(37,len(blocked))
        sources=json.loads((ROOT/'config/sources.json').read_text(encoding='utf8'))['sources']
        self.assertEqual(37,sum(s['key'] in blocked and all(k in s for k in ('issuer','title_tokens','alternate_urls','alternate_policy')) for s in sources))
        policy=json.loads((ROOT/'config/evidence_policy.json').read_text())['same_sha_fallback']
        self.assertFalse(policy['search_api']['enabled'])


if __name__=='__main__':
    unittest.main()
