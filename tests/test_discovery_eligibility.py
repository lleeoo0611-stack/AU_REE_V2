import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from au_ree_v2.discovery import candidates,discover
from au_ree_v2.acquisition import request


class DiscoveryTests(unittest.TestCase):
    def test_dedup_relative_pdf_and_security(self):
        seed={'key':'a','url':'https://issuer.test/reports/','allowed_hosts':['issuer.test']}
        raw=b'<a href="../one.pdf">Annual Report</a><a href="../one.pdf#p2">same</a><a href="https://evil.test/t.pdf">bad</a><a href="secret.pdf?to' + b'ken=x">secret</a>'
        rows=candidates(raw,seed)
        self.assertEqual(1,len(rows));self.assertEqual('https://issuer.test/one.pdf',rows[0]['url'])
        self.assertIsNone(rows[0]['publication_date'])

    def test_failure_isolation_immutable_and_idempotent(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'data/snapshots').mkdir(parents=True)
            (root/'data/manifest.json').write_text('{"snapshots":[]}')
            config={'max_documents_per_seed':3,'seeds':[{'key':'bad','url':'https://issuer.test/bad','allowed_hosts':['issuer.test']},{'key':'ok','url':'https://issuer.test/ok','allowed_hosts':['issuer.test']}]}
            def fetch(url):
                if url.endswith('bad'):raise TimeoutError()
                return (b'%PDF-1.0' if url.endswith('.pdf') else b'<a href="a.pdf">DFS</a>'),{}
            a=discover(root,config,fetch);before=json.loads((root/'data/manifest.json').read_text())
            discover(root,config,fetch);after=json.loads((root/'data/manifest.json').read_text())
            self.assertEqual(before,after);self.assertEqual(2,len(after['snapshots']))
            self.assertEqual('UNAVAILABLE',a['sources'][0]['status'])
            self.assertEqual('SNAPSHOT_PDF_PARSE_FAILED',a['documents'][0]['status'])

    def test_transient_retry_only(self):
        from urllib.error import HTTPError
        with patch('urllib.request.urlopen',side_effect=HTTPError('https://x',503,'retry',{},None)) as p,patch('time.sleep'):
            with self.assertRaises(HTTPError):request('https://x')
            self.assertEqual(3,p.call_count)
        with patch('urllib.request.urlopen',side_effect=HTTPError('https://x',404,'missing',{},None)) as p:
            with self.assertRaises(HTTPError):request('https://x')
            self.assertEqual(1,p.call_count)
