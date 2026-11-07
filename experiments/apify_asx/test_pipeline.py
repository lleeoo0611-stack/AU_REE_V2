import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('apify_experiment', Path(__file__).with_name('pipeline.py'))
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)


class ExperimentTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.work = Path(self.tmp.name)
        self.config = json.loads((p.HERE / 'config.google-serp.json').read_text())
        self.baseline = p.load_baseline()
        self.projects = p.registry(self.baseline)
        self.plan = p.query_plan(self.config, self.projects, '2026-11-07')

    def tearDown(self):
        self.tmp.cleanup()

    def test_baseline_ids_and_header_order(self):
        self.assertEqual((len(self.baseline['rows']), len(self.baseline['headers'])), (33, 52))
        self.assertEqual(len({r[0] for r in self.baseline['rows']}), 33)

    def test_query_budget_offset_cutoff(self):
        self.assertEqual(self.plan['planned_queries'], 16)
        self.assertEqual(self.plan['all_available_queries'], 267)
        self.assertTrue(all('before:2026-11-08' in j['query'] for j in self.plan['jobs']))
        config = dict(self.config, query_offset=16)
        second = p.query_plan(config, self.projects, '2026-11-07')
        self.assertFalse({j['query_id'] for j in self.plan['jobs']} & {j['query_id'] for j in second['jobs']})

    def test_url_guards(self):
        for url in ('http://announcements.asx.com.au/a.pdf', 'https://announcements.asx.com.au.evil.test/a.pdf',
                    'https://announcements.asx.com.au/a.pdf?token=secret', 'https://user@announcements.asx.com.au/a.pdf',
                    'https://127.0.0.1/a.pdf', 'https://announcements.asx.com.au:444/a.pdf'):
            with self.assertRaises(ValueError):
                p.document_url(url, self.config['allowed_document_hosts'])

    def test_missing_token_never_calls_transport(self):
        with self.assertRaisesRegex(ValueError, 'APIFY_TOKEN_MISSING'):
            p.ApifyClient('', transport=lambda *x: self.fail('transport called'))

    def fake_transport(self, pages, failure=None):
        calls = []
        def transport(method, url, body, headers):
            calls.append((method, url, body, headers))
            self.assertNotIn('secret', url)
            self.assertEqual(headers['Authorization'], 'Bearer secret')
            if failure:
                raise failure
            if method == 'POST':
                payload = {'data': {'id': 'run1', 'status': 'SUCCEEDED', 'defaultDatasetId': 'ds1'}}
                return json.dumps(payload).encode(), {}
            page = pages.pop(0)
            return json.dumps(page[0]).encode(), page[1]
        return transport, calls

    def test_api_pagination_auth_and_budget(self):
        pages = [([{'organicResults': []}], {'X-Apify-Pagination-Total': '2', 'X-Apify-Pagination-Offset': '0', 'X-Apify-Pagination-Count': '1'}),
                 ([{'organicResults': []}], {'X-Apify-Pagination-Total': '2', 'X-Apify-Pagination-Offset': '1', 'X-Apify-Pagination-Count': '1'})]
        transport, calls = self.fake_transport(pages)
        rows = p.ApifyClient('secret', transport).search(self.config, self.plan, self.work)
        self.assertEqual(len(rows), 2)
        self.assertIn('maxTotalChargeUsd=1.0', calls[0][1])
        self.assertIn('offset=1', calls[-1][1])
        self.assertFalse(any('secret' in f.read_text() for f in self.work.rglob('*.json')))

    def test_uncertain_start_is_not_retried(self):
        transport, calls = self.fake_transport([], TimeoutError('redacted'))
        client = p.ApifyClient('secret', transport)
        with self.assertRaises(TimeoutError):
            client.search(self.config, self.plan, self.work)
        with self.assertRaisesRegex(ValueError, 'RUN_ALREADY_REQUESTED'):
            client.search(self.config, self.plan, self.work)
        self.assertEqual(len(calls), 1)

    def test_truncated_pagination_rejected(self):
        transport, _ = self.fake_transport([([], {'X-Apify-Pagination-Total': '2', 'X-Apify-Pagination-Offset': '0', 'X-Apify-Pagination-Count': '0'})])
        with self.assertRaisesRegex(ValueError, 'DATASET_TRUNCATED'):
            p.ApifyClient('secret', transport).search(self.config, self.plan, self.work)

    def test_result_dedup_does_not_assign_identity(self):
        url = 'https://announcements.asx.com.au/asxpdf/20260101/pdf/example.pdf'
        item = {'searchQuery': {'term': self.plan['jobs'][3]['query']}, 'organicResults': [{'url': url}, {'url': url + '#page=2'}]}
        results = p.flatten_results([item], self.plan, self.config)
        self.assertEqual(len(results), 1)
        self.assertNotIn('project_id', results[0])

    def test_pdf_content_dedup_and_real_parser(self):
        import pymupdf
        doc = pymupdf.open()
        page = doc.new_page()
        page.insert_text((40, 40), '7 November 2026\nRare earth JORC Mineral Resource report\nTest Project')
        raw = doc.tobytes()
        doc.close()
        hits = [{'url': 'https://announcements.asx.com.au/' + str(i) + '.pdf'} for i in range(2)]
        docs, candidates = p.stage_documents(self.work, hits, self.config, self.projects, fetch=lambda *a: raw)
        self.assertEqual([d['status'] for d in docs], ['EXTRACTED_REVIEW_REQUIRED', 'DUPLICATE_CONTENT'])
        self.assertEqual(docs[0]['pages'], 1)

    def test_non_pdf_fails_without_values(self):
        docs, candidates = p.stage_documents(self.work, [{'url': 'https://announcements.asx.com.au/a.pdf'}], self.config, self.projects, fetch=lambda *a: b'<html>blocked</html>')
        self.assertEqual(docs[0]['status'], 'FETCH_OR_EXTRACTION_FAILED')
        self.assertFalse(candidates)

    def test_resource_reserve_is_never_promoted(self):
        pid = self.baseline['rows'][0][0]
        c = dict(candidate_id='x', kind='RESOURCE_TABLE_TOTAL', project_id=pid, issues=[], basis='TREO', category='MEASURED_INDICATED_TOTAL', resource_type='ORE_RESERVE')
        d = dict(candidate_id='x', project_id=pid, decision='VERIFIED_REPLACE_RESOURCE', reviewer='reviewer', reason='reason', supersedes_same_scope=True)
        with self.assertRaises(ValueError):
            p.apply_decisions(copy.deepcopy(self.baseline), {'x': c}, [d], self.work, '2026-11-07')

    def test_verified_resource_clears_old_composition(self):
        import pymupdf
        pid = next(r[0] for r in self.baseline['rows'] if r[30] > 0)
        doc = pymupdf.open()
        page = doc.new_page()
        page.insert_text((40, 40), '7 November 2026\nResource effective 1 November 2026\nReplaces the previous same-scope estimate\nTotal 10 0.5')
        raw = doc.tobytes()
        doc.close()
        sha, path = p.archive(self.work, raw, '.pdf')
        c = dict(candidate_id='verified', kind='RESOURCE_TABLE_TOTAL', project_id=pid, issues=[],
                 basis='TREO', category='MEASURED_INDICATED_TOTAL', resource_type='MINERAL_RESOURCE',
                 scope='Mineral Resource total', source_sha256=sha, publication_date='2026-11-07',
                 source_key='test_fixture', physical_page=1, raw_text='Total 10 0.5', header='Tonnes TREO',
                 values={'ore_mt': 10.0, 'grade': .5}, units={'ore_mt':'Mt', 'grade':'%'},
                 source_url='https://announcements.asx.com.au/fixture.pdf')
        artifact_sha, artifact = p.archive(self.work, (p.canonical({'candidates':[c]})+'\n').encode(), '.extraction.json')
        c = dict(c, retained_pdf=str(path.relative_to(self.work)), retained_extraction=str(artifact.relative_to(self.work)), extraction_sha256=artifact_sha)
        d = dict(candidate_id='verified', project_id=pid, decision='VERIFIED_REPLACE_RESOURCE', reviewer='fixture reviewer',
                 reason='Synthetic fixture validates scope replacement only', supersedes_same_scope=True,
                 scope=c['scope'], source_sha256=sha, effective_date='2026-11-01',
                 evidence=[{'role':'effective_date','physical_page':1,'marker':'Resource effective 1 November 2026'},
                           {'role':'same_scope_replacement','physical_page':1,'marker':'Replaces the previous same-scope estimate'}])
        data = copy.deepcopy(self.baseline)
        result = p.apply_decisions(data, {'verified':c}, [d], self.work, '2026-11-07')
        row = next(r for r in data['rows'] if r[0] == pid)
        self.assertEqual(len(result), 1)
        self.assertEqual(row[15:18], [10., .5, 50.])
        self.assertEqual(row[37:], [''] * 15)
        self.assertEqual(row[18:22], [''] * 4)
        self.assertEqual(row[30], 0)
        d['effective_date'] = '2026-11-08'
        with self.assertRaisesRegex(ValueError, 'DATE_MISSING_OR_AFTER_CUTOFF'):
            p.apply_decisions(copy.deepcopy(self.baseline), {'verified':c}, [d], self.work, '2026-11-07')

    def test_export_formulas_and_blanks(self):
        from openpyxl import load_workbook
        summary = {'export_date': '2026-11-07', 'status': 'PLANNED_NO_LIVE_SEARCH'}
        out = p.export_master(copy.deepcopy(self.baseline), self.work, summary, [])
        wb = load_workbook(out)
        ws = wb['專案總表']
        self.assertEqual(ws.max_column, 52)
        self.assertEqual(ws.max_row, 34)
        self.assertEqual(ws['V2'].value, '=IF(COUNT(AS2:AZ2)=8,SUM(AS2:AZ2),"")')
        self.assertIn('AS2:AT2', ws['AJ2'].value)
        self.assertIsNone(ws['AK2'].value)
        self.assertEqual(ws.freeze_panes, 'E2')
        self.assertTrue(ws.auto_filter.ref)


class AnnouncementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = json.loads((p.HERE / 'config.json').read_text())
        cls.plan = p.query_plan(cls.config, p.registry(p.load_baseline()), '2026-11-07')

    def sample(self, **extra):
        return dict(announcement_id='03139933', ticker='LYC', company_name='Fixture issuer',
                    announcement_date='2026-11-06', headline='Quarterly activities report',
                    file_url=None, source_url='https://www.asx.com.au/asx/v2/statistics/announcements.do?announcementId=03139933', **extra)

    def test_actor_input_matches_four_documented_fields(self):
        data = p.actor_input(self.config, self.plan)
        self.assertEqual(self.config['actor'], 'nexgendata~asx-company-announcements')
        self.assertEqual(set(data), {'tickers', 'marketSensitiveOnly', 'announcementType', 'maxResults'})
        self.assertEqual(data['maxResults'], 19)
        self.assertIn('LYC', data['tickers'])
        self.assertTrue(self.plan['ticker_evidence'])
        self.assertFalse(self.plan['date_range_supported'])
        self.assertFalse(self.plan['keyword_search_supported'])

    def test_missing_file_url_preserves_announcement_wrapper(self):
        row = self.sample()
        hits = p.flatten_results([row, row], self.plan, self.config)
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]['announcement_id'], '03139933')
        self.assertEqual(hits[0]['url'], row['source_url'])
        self.assertTrue(hits[0]['eligible_for_download'])
        self.assertNotIn('project_id', hits[0])

    def test_keyword_priority_does_not_discard_quarterly(self):
        normal = self.sample()
        jorc = dict(normal, announcement_id='03139934', headline='JORC Mineral Resource Estimate')
        hits = p.flatten_results([normal, jorc], self.plan, self.config)
        self.assertEqual(len(hits), 2)
        self.assertEqual(hits[0]['announcement_id'], '03139934')
        self.assertTrue(hits[0]['keyword_hits'])
        self.assertTrue(hits[1]['eligible_for_download'])

    def test_future_and_missing_url_records_retained(self):
        future = dict(self.sample(), announcement_date='2026-11-08')
        missing = dict(self.sample(), announcement_id='03139935', source_url=None)
        hits = p.flatten_results([future, missing], self.plan, self.config)
        self.assertEqual(len(hits), 2)
        self.assertTrue(all(not r['eligible_for_download'] for r in hits))
        self.assertIn('ANNOUNCEMENT_AFTER_CUTOFF', {r['status'] for r in hits})

    def test_conflicting_duplicate_id_needs_review(self):
        a = self.sample()
        b = dict(a, headline='Changed announcement content')
        with self.assertRaisesRegex(ValueError, 'CONFLICTING_DUPLICATE_ANNOUNCEMENT_ID'):
            p.flatten_results([a,b], self.plan, self.config)

    def test_announcement_link_is_validated_and_resolved(self):
        url = 'https://announcements.asx.com.au/asxpdf/20261106/pdf/fixture.pdf'
        html = '<a href="' + url + '">Download</a>'
        self.assertEqual(p.announcement_pdf_link(html, self.sample()['source_url'], self.config), url)
        for bad in ('<a href="https://evil.test/a.pdf">PDF</a>',
                    html + '<a href="https://www.asx.com.au/other.pdf">Other</a>',
                    '<p>You must accept the terms</p>' + html):
            with self.assertRaises(ValueError):
                p.announcement_pdf_link(bad, self.sample()['source_url'], self.config)

    def test_announcements_api_uses_actor_specific_payload(self):
        calls = []
        def transport(method, url, body, headers):
            calls.append((method,url,body))
            if method == 'POST':
                return json.dumps({'data': {'id':'run1','status':'SUCCEEDED','defaultDatasetId':'ds1'}}).encode(), {}
            return json.dumps([self.sample()]).encode(), {'X-Apify-Pagination-Total':'1','X-Apify-Pagination-Offset':'0','X-Apify-Pagination-Count':'1'}
        with tempfile.TemporaryDirectory() as work:
            rows = p.ApifyClient('fixture-secret', transport).search(self.config,self.plan,work)
        self.assertEqual(len(rows),1)
        self.assertIn('/acts/nexgendata~asx-company-announcements/runs',calls[0][1])
        self.assertEqual(set(json.loads(calls[0][2])), {'tickers','marketSensitiveOnly','announcementType','maxResults'})


if __name__ == '__main__':
    unittest.main()
