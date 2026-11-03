"""Primary-document expansion; scopes, historical policy and native title IDs."""
import csv
import json
import tempfile
import unittest
import uuid
from pathlib import Path
from au_ree_v2.acquisition import select_snapshots
from au_ree_v2.evidence import html_text, ingest_sources, ingest_claims, ingest_events, resource_values, validate_pages
from au_ree_v2.store import connect, digest, logical_dump
from au_ree_v2.hierarchy import build
from au_ree_v2.resolution import resolve as identity
from au_ree_v2.selection import resolve
from au_ree_v2.discovery import discover

ROOT=Path(__file__).resolve().parents[1]


class Phase8EvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder=ROOT/'work/tests'/uuid.uuid4().hex;cls.folder.mkdir(parents=True)
        cls.db=connect(cls.folder/'canonical.sqlite')
        baseline=json.loads((ROOT/'results/phase7-2026-11-03/snapshot_lock.json').read_text())
        current=select_snapshots(ROOT,'2026-11-03')
        cls.snaps=baseline+[s for s in current if s['key'] in ('yangibana_ar2026','wudinna_mre2026','kalkaroo_ree2020','nolans_quarter202610')]
        cls.policy=json.loads((ROOT/'config/evidence_policy.json').read_text())
        ingest_sources(cls.db,ROOT,cls.snaps)
        cls.original={r['entity_id']:dict(r) for r in cls.db.execute('SELECT * FROM entities')}
        ingest_claims(cls.db,ROOT,cls.snaps,'2026-11-03',conflict_selection=True)
        ingest_events(cls.db,ROOT,cls.snaps,'2026-11-03');build(cls.db,cls.snaps)
        cls.resources=resource_values(cls.db,'2026-11-03',{s['sha256'] for s in cls.snaps},strict=True)
        cls.identity=identity(cls.db,ROOT,cls.snaps,'2026-11-03',cls.policy['identity_rule_version'])
        from au_ree_v2.studies import ingest
        cls.cases=ingest(cls.db,ROOT,cls.snaps,'2026-11-03')
        cls.selected=resolve(cls.db,cls.snaps,'2026-11-03',cls.resources,cls.cases,cls.identity['mapping'],cls.policy,ROOT)

    @classmethod
    def tearDownClass(cls):cls.db.close()

    def pid(self,namespace,native):
        return self.db.execute('SELECT entity_id FROM entities WHERE native_namespace=? AND native_id=?',(namespace,native)).fetchone()[0]

    def test_three_new_resource_scopes_not_added_projects(self):
        self.assertEqual(22,len(self.resources))
        self.assertIn(self.pid('SA_MINING_PROJECT_SITE_NO','1123290'),self.resources)
        for eid,record in self.original.items():
            self.assertEqual(record,dict(self.db.execute('SELECT * FROM entities WHERE entity_id=?',(eid,)).fetchone()))
        self.assertEqual(31,len(self.selected['projects']))

    def test_yangibana_mineral_resource_not_reserve_or_ownership_fraction(self):
        pid=self.pid('WA_DMPE_REE_2026_PROJECT','yangibana');r=self.resources[pid]
        self.assertEqual((29.93,.93,276.955),(r['ore_mt'],r['grade_pct'],r['contained_treo_kt']))
        self.assertEqual(85.7,self.selected['values'][pid]['TC1']['value'])
        self.assertEqual(0,self.selected['values'][pid]['C1']['value'])
        self.assertNotIn('S1',self.selected['values'][pid])  # NdPr alone is not NdPrDyTb.

    def test_wudinna_rounded_group_basis_and_exploration_target_excluded(self):
        pid=self.pid('SA_MINING_PROJECT_SITE_NO','1123290');r=self.resources[pid]
        self.assertEqual((150,.047,70.4),(r['ore_mt'],r['grade_pct'],r['contained_treo_kt']))
        self.assertAlmostEqual(112/470*100,self.selected['values'][pid]['S1']['value'])
        self.assertNotIn('D1',self.selected['values'][pid])  # Planned Scoping is not completed.
        self.assertNotIn('T1',self.selected['values'][pid])  # ISR resource fraction is not recovery.

    def test_kalkaroo_sample_statistics_never_form_resource_or_overall_recovery(self):
        pid=self.pid('SA_MINING_PROJECT_SITE_NO','1130520')
        self.assertNotIn(pid,self.resources)
        rows=[c for c in self.selected['inventory'] if c['entity_id']==pid and c['variable'].startswith('reported_technical_')]
        self.assertEqual(4,len(rows));self.assertTrue(all(not r['reason'] for r in rows))
        self.assertNotIn('T1',self.selected['values'].get(pid,{}))

    def test_latest_nolans_status_retains_pending_close_and_null_events(self):
        pid=self.pid('AUSTRADE_2026_REE_PROJECT','nolans-rare-earths-project')
        c=self.selected['values'][pid]['C1'];self.assertEqual(2,c['value'])
        self.assertEqual('2026-10-30',c['effective_date'])
        events=self.db.execute("SELECT value,status,raw FROM observations WHERE variable='commercial_event'").fetchall()
        self.assertEqual(19,len(events));self.assertTrue(all(e['value'] is None and e['status']=='AUTO_VALIDATED' for e in events))
        states=[json.loads(e['raw']).get('finance_state') for e in events]
        self.assertNotIn('FINANCIAL_CLOSE',states);self.assertNotIn('DRAWN',states)

    def test_same_scope_different_financing_instruments_are_distinct_raw_events(self):
        from au_ree_v2.selection import export
        export(self.selected,self.folder)
        with (self.folder/'technical_commercial_coverage.csv').open() as f:
            commercial=next(r for r in csv.DictReader(f) if r['criterion']=='C1')
        self.assertEqual('18',commercial['validated_events'])  # 19 typed events, one Development.

    def test_endpoint_intersection_expands_without_relaxing_t1(self):
        eligible={self.identity['mapping'].get(e,e) for e in self.resources}
        self.assertEqual(2,sum('TC1' in v for e,v in self.selected['values'].items() if e in eligible))
        self.assertEqual(5,sum('C1' in v for e,v in self.selected['values'].items() if e in eligible))
        self.assertEqual(0,sum('T1' in v for v in self.selected['values'].values()))

    def test_identity_extensions_are_versioned_and_never_change_source_ids(self):
        old=identity(self.db,ROOT,self.snaps,'2026-11-03')
        for namespace,native,ga in [('WA_MINDEX_SITE_DEPOSIT','S0002531','335930'),('SA_MINDEP_SITE_DEPOSIT','11871','806972')]:
            a=self.pid(namespace,native);b=self.pid('GA_ENO',ga)
            self.assertNotEqual(old['mapping'][a],old['mapping'][b])
            self.assertEqual(self.identity['mapping'][a],self.identity['mapping'][b])

    def test_documented_prospects_do_not_duplicate_combined_resource(self):
        pid=self.pid('SA_MINING_PROJECT_SITE_NO','1123290')
        children=self.db.execute("SELECT child_id FROM relations WHERE parent_id=? AND relation='CONTAINS_ISSUER_DOCUMENTED_PROSPECT_NOT_RESOURCE_SUM'",(pid,)).fetchall()
        self.assertEqual(2,len(children))
        self.assertTrue(all(row[0] not in self.resources for row in children))

    def test_ingestion_is_idempotent(self):
        before=digest(logical_dump(self.db))
        ingest_claims(self.db,ROOT,self.snaps,'2026-11-03',conflict_selection=True)
        ingest_events(self.db,ROOT,self.snaps,'2026-11-03')
        self.assertEqual(before,digest(logical_dump(self.db)))


class Phase8AcquisitionTests(unittest.TestCase):
    def test_failed_html_container_does_not_block_independent_pdf_resource(self):
        from unittest.mock import patch
        folder=ROOT/'work/tests'/uuid.uuid4().hex;folder.mkdir(parents=True)
        db=connect(folder/'canonical.sqlite')
        snaps=[s for s in select_snapshots(ROOT,'2026-11-03') if s['key'] in ('mt_weld_2024','wudinna_mre2026')]
        try:
            ingest_sources(db,ROOT,snaps)
            with patch('au_ree_v2.evidence.html_text',side_effect=ValueError('ARTICLE_BODY_MISSING_OR_AMBIGUOUS')):
                ingest_claims(db,ROOT,snaps,'2026-11-03',conflict_selection=True)
            values=resource_values(db,'2026-11-03',{s['sha256'] for s in snaps},strict=True)
            self.assertEqual(1,len(values));self.assertEqual(106.6,next(iter(values.values()))['ore_mt'])
            self.assertGreater(db.execute("SELECT count(*) FROM observations WHERE issues LIKE '%EXTRACTION_HTML_READ_FAILED%'").fetchone()[0],0)
        finally:db.close()

    def test_corrupt_existing_snapshot_is_isolated_and_not_overwritten(self):
        import hashlib
        folder=ROOT/'work/tests'/uuid.uuid4().hex;(folder/'data/snapshots').mkdir(parents=True)
        (folder/'data/manifest.json').write_text('{"snapshots":[]}')
        raw=b'<p>original</p>';sha=hashlib.sha256(raw).hexdigest();dest=folder/'data/snapshots'/(sha+'.html')
        dest.write_bytes(b'changed')
        result=discover(folder,dict(seeds=[dict(key='x',url='https://issuer.test',allowed_hosts=['issuer.test'])]),lambda url:(raw,{}))
        self.assertEqual('UNAVAILABLE',result['sources'][0]['status'])
        self.assertEqual(b'changed',dest.read_bytes());self.assertEqual([],json.loads((folder/'data/manifest.json').read_text())['snapshots'])

    def test_lse_body_is_decoded_without_using_scripts_or_css_as_evidence(self):
        s=next(s for s in select_snapshots(ROOT,'2026-11-03') if s['key']=='wudinna_mre2026')
        text=html_text(ROOT,s)
        self.assertIn('Total 150 470 101 10 112',text)
        self.assertNotIn('font-family:',text);self.assertNotIn('injectNewsDetails',text)
        with self.assertRaisesRegex(ValueError,'HTML_MARKER'):
            validate_pages(ROOT,s,dict(source_sha256=s['sha256'],source_markers=['injectNewsDetails']),[s])

    def test_three_complete_qld_inventories_keep_native_title_identity_and_original_pages(self):
        snaps=select_snapshots(ROOT,'2026-11-03');ids=[]
        from au_ree_v2.store import filehash
        for key,count in [('qld_epm_live',2816),('qld_mdl_live',201),('qld_ml_live',2505)]:
            s=next(s for s in snaps if s['key']==key);d=json.loads((ROOT/s['path']).read_text())
            self.assertTrue(d['inventory']['complete']);self.assertEqual(count,len(d['features']))
            self.assertEqual('TENEMENT',s['entity_kind']);self.assertEqual('ALL_TENURE_RECORDS',s['record_filter'])
            ids.extend(f['attributes']['permitid'] for f in d['features'])
            for page in s['original_responses']:self.assertEqual(page['sha256'],filehash(ROOT/page['path']))
        self.assertEqual(5522,len(set(ids)))

    def test_detail_discovery_is_bounded_and_archives_before_extraction(self):
        folder=ROOT/'work/tests'/uuid.uuid4().hex;(folder/'data/snapshots').mkdir(parents=True)
        (folder/'data/manifest.json').write_text('{"snapshots":[]}')
        calls=[]
        def fetch(url):
            calls.append(url)
            if url.endswith('/news'):return b'<a href="/announcements/a">Quarterly</a><a href="/announcements/b">Quarterly</a>',{}
            return b'<a href="https://issuer.test/a.pdf">Quarterly report</a>',{}
        result=discover(folder,dict(max_pages_per_seed=2,max_documents_per_seed=0,seeds=[dict(key='x',url='https://issuer.test/news',allowed_hosts=['issuer.test'],keywords=['Quarterly'],detail_pattern='/announcements/')]),fetch)
        self.assertEqual(2,len(calls));self.assertEqual(2,len(result['sources']))
        self.assertEqual(0,len(result['documents']))


if __name__=='__main__':unittest.main()
