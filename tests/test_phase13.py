"""Bounded retrieval, noun/column binding and frozen benchmark compatibility."""
import importlib.util
import json
import tempfile
import unittest
from datetime import datetime,timezone,timedelta
from email.utils import format_datetime
from pathlib import Path
from urllib.error import HTTPError
from unittest.mock import patch
from au_ree_v2 import acquisition
from au_ree_v2.discovery import candidates,discover,search_tasks
from au_ree_v2.pdf_extract import narrative_candidates,project_registry

ROOT=Path(__file__).resolve().parents[1]
SPEC=importlib.util.spec_from_file_location('document_evaluator',ROOT/'tools/evaluate_documents.py')
EVAL=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(EVAL)


class Phase13Tests(unittest.TestCase):
    def setUp(self):acquisition._last_request.clear()

    def test_retry_after_seconds_is_not_retried_early(self):
        error=HTTPError('https://retry.test',429,'rate',{'Retry-After':'17'},None)
        with patch('urllib.request.urlopen',side_effect=error) as fetch,patch('time.sleep') as sleep:
            with self.assertRaises(HTTPError):acquisition.request('https://retry.test')
        self.assertEqual(3,fetch.call_count)
        self.assertEqual([17.,17.],[call.args[0] for call in sleep.call_args_list if call.args[0]>=1])
        self.assertEqual('HTTP_429_RATE_LIMITED',acquisition.failure_details(error)['failure_status'])

    def test_long_retry_after_is_deferred_not_capped(self):
        error=HTTPError('https://retry.test',429,'rate',{'Retry-After':'120'},None)
        with patch('urllib.request.urlopen',side_effect=error) as fetch,patch('time.sleep') as sleep:
            with self.assertRaises(HTTPError):acquisition.request('https://retry.test')
        self.assertEqual(1,fetch.call_count);sleep.assert_not_called()
        self.assertEqual(120,acquisition.failure_details(error)['retry_after_seconds'])

    def test_http_date_retry_after_and_permanent_error(self):
        date=format_datetime(datetime.now(timezone.utc)+timedelta(seconds=20))
        error=HTTPError('https://retry.test',503,'rate',{'Retry-After':date},None)
        with patch('urllib.request.urlopen',side_effect=error) as fetch,patch('time.sleep') as sleep:
            with self.assertRaises(HTTPError):acquisition.request('https://retry.test')
        self.assertEqual(3,fetch.call_count)
        self.assertEqual(2,len([c for c in sleep.call_args_list if c.args[0]>15]))
        for code in (403,404):
            with patch('urllib.request.urlopen',side_effect=HTTPError('https://permanent.test',code,'',{},None)) as fetch:
                with self.assertRaises(HTTPError):acquisition.request('https://permanent.test')
                self.assertEqual(1,fetch.call_count)

    def test_timeout_and_non_pdf_are_explicit_not_absence(self):
        self.assertEqual('TIMEOUT',acquisition.failure_details(TimeoutError())['failure_status'])
        self.assertEqual('NON_PDF_RESPONSE',acquisition.failure_details(ValueError('NOT_PDF'))['failure_status'])
        self.assertIn('NOT_DOCUMENT_ABSENCE',acquisition.failure_details(TimeoutError())['interpretation'])

    def test_official_archive_native_identity_and_row_date(self):
        raw=b'<table><tr><td>18/08/2026</td><td><a href="/asx/v2/statistics/displayAnnouncement.do?display=pdf&amp;idsId=03126345">MRE and PFS</a></td></tr></table>'
        seed=dict(key='asx',url='https://www.asx.com.au/',allowed_hosts=['www.asx.com.au'],authority='EXCHANGE')
        row,=candidates(raw,seed)
        self.assertEqual('2026-08-18',row['publication_date']);self.assertIn('idsId=03126345',row['url'])
        self.assertNotIn('VERIFIED_ISSUER_ORIGINAL',row['authority'])

    def test_search_fallback_and_pagination_share_one_budget(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'work') as tmp:
            root=Path(tmp);(root/'data/snapshots').mkdir(parents=True)
            (root/'data/manifest.json').write_text('{"snapshots":[]}')
            config=dict(max_pages_per_seed=2,max_documents_per_seed=0,seeds=[dict(key='issuer',url='https://issuer.test/',allowed_hosts=['issuer.test'],fallback_urls=['https://issuer.test/other'],search_url_template='https://issuer.test/?s={query}',queries=['metallurgical','JORC','PFS'])])
            urls=[]
            def fetch(url):urls.append(url);return b'<a href="?page=2">Next</a>',{}
            result=discover(root,config,fetch)
            self.assertEqual(2,len(urls));self.assertEqual(2,len(result['sources']))

    def test_existing_original_is_not_requested_again(self):
        import hashlib
        with tempfile.TemporaryDirectory(dir=ROOT/'work') as tmp:
            root=Path(tmp);(root/'data/snapshots').mkdir(parents=True)
            raw=b'%PDF-known';sha=hashlib.sha256(raw).hexdigest();file=root/'data/snapshots'/(sha+'.pdf');file.write_bytes(raw)
            (root/'data/manifest.json').write_text(json.dumps(dict(snapshots=[dict(key='known',kind='pdf',url='https://issuer.test/a.pdf',sha256=sha,path=file.relative_to(root).as_posix())])))
            config=dict(seeds=[dict(key='issuer',url='https://issuer.test/',allowed_hosts=['issuer.test'])]);urls=[]
            def fetch(url):urls.append(url);return b'<a href="a.pdf">DFS</a>',{}
            result=discover(root,config,fetch)
            self.assertEqual(['https://issuer.test/'],urls)
            self.assertEqual('REUSED_VERIFIED_ORIGINAL',result['documents'][0]['status'])

    def test_quantity_noun_binding_not_project_specific(self):
        registry=[dict(entity_id='p',aliases=['Example Project'])]
        text='Example Project leach tests reported moisture averaging 13.3% and tailings with an average 7.3% TREO. Example Project tests achieved extraction averaging 81%.'
        old=narrative_candidates(text,1,registry,parser_version='document-recognition-v2-mineralogy')
        new=narrative_candidates(text,1,registry,parser_version='document-recognition-v3-bound-quantities')
        values=lambda rows:[n['value'] for c in rows for n in c['numbers'] if n.get('quantity_role')]
        self.assertIn(13.3,values(old));self.assertNotIn(13.3,values(new));self.assertNotIn(7.3,values(new));self.assertIn(81.,values(new))
        coordinated='Example Project testwork showed total rare earth extraction achieved up to 82%, averaging 76%.'
        self.assertEqual([82.,76.],values(narrative_candidates(coordinated,1,registry,parser_version='document-recognition-v3-bound-quantities')))

    def test_historical_benchmark_and_current_columns(self):
        old=EVAL.evaluate_phase12(ROOT)
        self.assertEqual(json.loads((ROOT/'data/phase12_document_benchmark.json').read_text()),old)
        new=EVAL.evaluate_phase12(ROOT,parser_version='document-recognition-v3-bound-quantities')
        self.assertEqual(0,new['numeric_metrics']['false_positive']);self.assertEqual(13,new['numeric_metrics']['true_positive'])
        for case in new['acceptance_results']:
            if 'P2O5_not_TREO' in case['label']:self.assertFalse(case['actual_acceptance'])

    def test_gap_queries_use_document_terms_not_internal_criterion_codes(self):
        registry=json.loads((ROOT/'config/discovery.json').read_text())
        tasks=search_tasks(ROOT,registry,ROOT/'results/phase12-2026-11-04/evidence_pipeline_diagnostics.csv')
        self.assertTrue(tasks)
        for t in tasks:
            self.assertFalse(any(q.endswith(' '+t['criterion']) for q in t['queries']))
            self.assertTrue(t['queries'])

    def test_new_original_values_preserve_old_contract_and_stage_boundaries(self):
        from au_ree_v2.evidence import load_claims,normalize,validate_pages
        from au_ree_v2.selection import technical_record,technical_compare
        old,_=load_claims(ROOT,'9f0d526dc2f97532f313f5ff67f4b41ddf8e9ec109bf481a137281705c3b633a')
        current,_=load_claims(ROOT,'42e120a1d6c0d1bddfa91559b13d15dd4e524f9c22f32ed5c36ac79c87ba30a7');by_id={p['id']:p for p in current['projects']}
        before={json.dumps(o,sort_keys=True) for p in old['projects'] for o in p['observations']}
        for p in old['projects']:
            for o in p['observations']:self.assertIn(o,by_id[p['id']]['observations'])
        new=[o for p in current['projects'] for o in p['observations'] if json.dumps(o,sort_keys=True) not in before]
        self.assertEqual(16,len(new))
        snapshots=json.loads((ROOT/'data/manifest.json').read_text())['snapshots'];sources={s['key']:s for s in snapshots};cache={}
        policy=json.loads((ROOT/'config/evidence_policy.json').read_text())
        for o in new:
            self.assertFalse(normalize(o));validate_pages(ROOT,sources[o['source_key']],o,snapshots,cache)
            if o['domain']=='Technical':
                self.assertEqual('LABORATORY',o['scale']);self.assertIsNone(o.get('measurement_bounds'))
                record=technical_record(dict(o,raw=o,evidence_id='new',project_id='p',origin='OBSERVATION',reason=None),policy)
                self.assertTrue(technical_compare(record,policy['criteria']['TC1']))

    def test_selective_ocr_does_not_run_when_native_markers_suffice(self):
        import pymupdf
        from au_ree_v2.pdf_extract import extract_page
        source=next(s for s in json.loads((ROOT/'data/manifest.json').read_text())['snapshots'] if s['key']=='mt_weld_2024')
        with patch.object(pymupdf.Page,'get_textpage_ocr',side_effect=AssertionError('unnecessary OCR')):
            result=extract_page(ROOT/source['path'],2,tessdata='not-needed',markers=['106.6'])
        self.assertEqual('PYPDF_NATIVE',result['method']);self.assertEqual(source['sha256'],result['source_sha256'])

    def test_sensitivity_axes_are_not_new_recovery_measurements(self):
        text='Example Project Base Case NPV TREO Recovery (-/+10%) 17 356 A$:US$ (0.7) 16% Recovery 25%.'
        rows=narrative_candidates(text,1,[dict(entity_id='p',aliases=['Example Project'])],parser_version='document-recognition-v3-bound-quantities')
        self.assertFalse([n for c in rows for n in c['numbers'] if n.get('quantity_role')])

    def test_verified_native_table_cache_matches_fresh_parse(self):
        import pymupdf
        from au_ree_v2.pdf_extract import recognize_document
        from au_ree_v2.store import canonical,filehash
        snapshots=json.loads((ROOT/'results/phase12-2026-11-04/snapshot_lock.json').read_text())
        source=next(s for s in snapshots if s['key']=='cummins_mre2023')
        artifact=next(s for s in snapshots if s['kind']=='document_extraction' and s['source_sha256']==source['sha256'])
        self.assertEqual(artifact['sha256'],filehash(ROOT/artifact['path']))
        data=json.loads((ROOT/artifact['path']).read_text())
        cache={p['physical_page']:[t for t in data['tables'] if t['physical_page']==p['physical_page']] for p in data['pages']}
        fresh=recognize_document(ROOT,source,project_registry(ROOT),parser_version='document-recognition-v3-bound-quantities')
        with patch.object(pymupdf.Page,'find_tables',side_effect=AssertionError('verified native table should be reused')):
            cached=recognize_document(ROOT,source,project_registry(ROOT),parser_version='document-recognition-v3-bound-quantities',table_cache=cache)
        self.assertEqual(canonical(fresh),canonical(cached))

    def test_terms_interstitial_is_not_submitted_or_hidden_pdf_fetched(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'work') as tmp:
            root=Path(tmp);(root/'data/snapshots').mkdir(parents=True);(root/'data/manifest.json').write_text('{"snapshots":[]}')
            cfg=dict(seeds=[dict(key='exchange',url='https://exchange.test/archive',allowed_hosts=['exchange.test'])]);urls=[]
            def fetch(url):
                urls.append(url)
                if url.endswith('/archive'):return b'<a href="a.pdf">MRE</a>',{}
                return b'<form action="announcementTerms.do"><input name="pdfURL" value="https://protected.test/secret.pdf"></form>',{}
            result=discover(root,cfg,fetch)
            self.assertEqual(['https://exchange.test/archive','https://exchange.test/a.pdf'],urls)
            self.assertEqual('TERMS_INTERSTITIAL_NOT_ACCEPTED',result['documents'][0]['failure_status'])

    def test_shareholders_is_not_an_older_page_link(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'work') as tmp:
            root=Path(tmp);(root/'data/snapshots').mkdir(parents=True);(root/'data/manifest.json').write_text('{"snapshots":[]}')
            cfg=dict(max_documents_per_seed=0,seeds=[dict(key='issuer',url='https://issuer.test/archive',allowed_hosts=['issuer.test'])]);urls=[]
            def fetch(url):urls.append(url);return b'<a href="report.pdf">Annual Report to Shareholders</a>',{}
            discover(root,cfg,fetch)
            self.assertEqual(['https://issuer.test/archive'],urls)

    def test_new_safe_capture_keeps_historical_public_derivative_proof(self):
        import hashlib
        with tempfile.TemporaryDirectory(dir=ROOT/'work') as tmp:
            root=Path(tmp);(root/'data/snapshots').mkdir(parents=True)
            private='a'*64
            def source(raw,date,**extra):
                sha=hashlib.sha256(raw).hexdigest();path=root/'data/snapshots'/(sha+'.html');path.write_bytes(raw)
                return dict(key='issuer_page',kind='discovery_html',url='https://issuer.test/',sha256=sha,path=path.relative_to(root).as_posix(),available_date='2026-11-03',acquired_at=date,**extra)
            old=dict(key='issuer_page',kind='discovery_html',url='https://issuer.test/',sha256=private,path='data/snapshots/'+private+'.html',available_date='2026-11-03',acquired_at='2026-11-03T01:00:00Z')
            derivative=source(b'public derivative','2026-11-03T02:00:00Z',publication_derivative=True,unpublished_original_sha256=private)
            safe=source(b'later safe content','2026-11-03T03:00:00Z')
            manifest=root/'data/manifest.json';manifest.write_text(json.dumps(dict(snapshots=[old,derivative,safe])))
            self.assertEqual([safe],acquisition.select_snapshots(root,'2026-11-03'))
            # Corrupt historical public bytes still fail, even with a valid latest capture.
            (root/derivative['path']).write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'checksum mismatch'):acquisition.select_snapshots(root,'2026-11-03')
            (root/derivative['path']).write_bytes(b'public derivative')
            manifest.write_text(json.dumps(dict(snapshots=[old,safe])))
            with self.assertRaisesRegex(ValueError,'checksum mismatch'):acquisition.select_snapshots(root,'2026-11-03')
        snapshots=json.loads((ROOT/'data/manifest.json').read_text())['snapshots']
        private_paths={ROOT/s['path'] for s in snapshots if any(d.get('unpublished_original_sha256')==s['sha256'] for d in snapshots)}
        expected={s['sha256'] for s in acquisition.select_snapshots(ROOT,'2026-11-03')}
        exists=Path.exists
        with patch.object(Path,'exists',lambda path:False if path in private_paths else exists(path)):
            public={s['sha256'] for s in acquisition.select_snapshots(ROOT,'2026-11-03')}
        self.assertEqual(expected,public)


if __name__=='__main__':unittest.main()
