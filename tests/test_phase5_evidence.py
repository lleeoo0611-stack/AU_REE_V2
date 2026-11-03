import csv,json,unittest,uuid,copy,tempfile
from pathlib import Path
from au_ree_v2.store import connect,digest,logical_dump,filehash
from au_ree_v2.acquisition import select_snapshots
from au_ree_v2.evidence import ingest_sources,ingest_claims,resource_values,transformation_issues
from au_ree_v2.resolution import resolve,technical_coverage
from au_ree_v2.studies import ingest
from au_ree_v2.pdf_extract import extract_page,capture_pages,readable
from au_ree_v2.analysis import prepare
from au_ree_v2.discovery import discover

ROOT=Path(__file__).resolve().parents[1]


class Phase5Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.work=ROOT/'work/tests'/uuid.uuid4().hex;cls.work.mkdir(parents=True)
        cls.db=connect(cls.work/'canonical.sqlite');cls.snaps=json.loads((ROOT/'results/phase5-2026-11-03/snapshot_lock.json').read_text(encoding='utf-8'));cls.shas={s['sha256'] for s in cls.snaps}
        ingest_sources(cls.db,ROOT,cls.snaps);ingest_claims(cls.db,ROOT,cls.snaps,'2026-11-03')
        cls.resources=resource_values(cls.db,'2026-11-03',cls.shas);cls.cases=ingest(cls.db,ROOT,cls.snaps,'2026-11-03');cls.ids=resolve(cls.db,ROOT,cls.snaps)
    @classmethod
    def tearDownClass(cls):cls.db.close()

    def test_resource_increment_and_no_new_project_ids(self):
        self.assertEqual(16,len(self.resources))
        self.assertEqual(28,self.db.execute("SELECT COUNT(*) FROM entities WHERE kind='PROJECT'").fetchone()[0])
        for native,kt in [('north-stanmore',155.83104),('cowalinya',138.33),('mt-clere',84.84),('salazar',270.94),('redlings',12.43),('mangaroon',311.792)]:
            eid=self.db.execute('SELECT entity_id FROM entities WHERE native_namespace=? AND native_id=?',('WA_DMPE_REE_2026_PROJECT',native)).fetchone()[0]
            self.assertAlmostEqual(kt,self.resources[eid]['contained_treo_kt'])
        self.assertFalse(any('burracoppin' in r['scope'].lower() for r in self.resources.values()))

    def test_seven_pairs_resolved_and_shared_parent_not_merged(self):
        self.assertEqual(9,len(self.ids['accepted']))
        self.assertEqual(31,sum(r['status']!='DOCUMENT_SUPPORTED_EQUIVALENCE' for r in self.ids['candidates']))
        self.assertEqual(1,self.db.execute("SELECT COUNT(*) FROM relations WHERE relation='CONTAINS_DOCUMENTED_REE_SCOPE_NOT_IDENTITY_EQUIVALENCE'").fetchone()[0])
        cov=technical_coverage(self.db,self.ids,self.resources,self.cases,self.shas)
        self.assertEqual(6,sum(r['status']=='NO_CONTROLLED_PRIMARY_TECHNICAL_SCOPE_YET' for r in cov))
        self.assertEqual(2,sum(r['status']=='PRIMARY_RESOURCE_BASIS_OR_FRACTION_NOT_COMPARABLE' for r in cov))

    def test_yttria_has_specific_location_diagnostic(self):
        rows=[json.loads(r['details']) for r in self.db.execute("SELECT details FROM review_queue WHERE reason='IDENTITY_DECISION_REVIEW'")]
        self.assertTrue(any('3685.359_METRES_EXCEEDS_500M' in r['reason'] for r in rows))
        self.assertTrue(any(r['name']=='Yttria' and r['status']=='LOCATION_CONFLICT_REVIEW' for r in self.ids['candidates']))

    def test_company_equity_is_not_project_finance(self):
        rows=self.db.execute("SELECT e.kind,o.value,o.basis FROM observations o JOIN entities e USING(entity_id) WHERE variable='issuer_equity_raised_aud_m' AND status='AUTO_VALIDATED'").fetchall()
        self.assertEqual([24.9,55],sorted(r['value'] for r in rows));self.assertTrue(all(r['kind']=='COMPANY' for r in rows))
        self.assertEqual(0,self.db.execute("SELECT COUNT(*) FROM observations WHERE variable='financing_ord'").fetchone()[0])

    def test_selective_ocr_recovers_encoding_and_retains_native(self):
        source=ROOT/'data/snapshots/4c1bc8edc6d26b0c5eaf16e385c0e95534c071092624e9d14c338d2783002eb7.pdf'
        a=extract_page(source,6,tessdata=ROOT/'data/ocr',markers=['$24.9 million','$55 million'])
        self.assertEqual('MUPDF_TESSERACT_200DPI_SELECTED_PAGE',a['method']);self.assertIn('$24.9 million',a['text']);self.assertNotEqual(a['native_text'],a['text'])
        self.assertEqual(filehash(ROOT/'data/ocr/eng.traineddata'),a['model_sha256'])
        with self.assertRaises(ValueError):extract_page(source,0)

    def test_ocr_artifact_page_binding_is_enforced(self):
        for s in self.snaps:
            if s['key']=='asm_ar2026_page_6':
                obj=json.loads((ROOT/s['path']).read_text());self.assertEqual(6,obj['physical_page']);self.assertEqual('EXTRACTED_REQUIRES_SCOPE_VALIDATION',obj['status'])
        self.assertFalse(readable('ƵƌŝŶŐϮϬϮϱ'))

    def test_selected_leach_and_mrec_not_whole_ore_recovery(self):
        self.assertEqual(7,len(self.cases));cases=[c for c in self.cases if c['project_native_id']=='cowalinya'];self.assertEqual(2,len(cases))
        self.assertTrue(all('whole_ore_concentrate_recovery_pct' not in c['parameters'] for c in cases))
        self.assertTrue(all(c['scale']!='DFS_MODEL' for c in cases))
        self.assertEqual(0,self.db.execute("SELECT COUNT(*) FROM observations WHERE variable='recovery_pct' AND status='AUTO_VALIDATED'").fetchone()[0])

    def test_government_conflicts_excluded_not_corrected(self):
        out=self.work/'panels';cfg=json.loads((ROOT/'config/research.json').read_text());prepared=prepare(self.db,'2026-11-03',self.snaps,self.resources,{},cfg,out,canonical_ids=self.ids['mapping'],cases=self.cases)
        self.assertEqual(17,prepared['government_screen_n']);self.assertEqual(6,prepared['panels']['issuer_resource_composition'])
        exclusions=list(csv.DictReader((out/'official_summary_exclusions.csv').open(encoding='utf-8')))
        self.assertEqual({'Cowalinya','Mt Clere','Mons'},{r['project_name'] for r in exclusions})
        self.assertTrue(all(9.9<float(r['grade_ratio'])<10.1 for r in exclusions))

    def test_magnet_sum_is_scope_bound(self):
        p=next(p for p in json.loads((ROOT/'data/claims.json').read_text())['projects'] if p['id']=='salazar')
        o=next(o for o in p['observations'] if o['variable']=='magnet_reo_share_pct')
        self.assertAlmostEqual(100*274/1178,o['value']);self.assertEqual([],transformation_issues(o,p['observations']))
        altered=copy.deepcopy(p['observations']);next(v for v in altered if v['variable']=='reported_dy2o3_ppm')['scope']='other deposit'
        self.assertTrue(transformation_issues(o,altered))

    def test_reingestion_is_idempotent(self):
        before=digest(logical_dump(self.db));ingest_sources(self.db,ROOT,self.snaps);ingest_claims(self.db,ROOT,self.snaps,'2026-11-03');ingest(self.db,ROOT,self.snaps,'2026-11-03');resolve(self.db,ROOT,self.snaps)
        self.assertEqual(before,digest(logical_dump(self.db)))

    def test_discovery_follows_bounded_pages_and_deduplicates(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'data/snapshots').mkdir(parents=True);(root/'data/manifest.json').write_text('{"snapshots":[]}')
            cfg={'max_pages_per_seed':2,'seeds':[{'key':'issuer','url':'https://issuer.test/reports','allowed_hosts':['issuer.test']}]}
            def fetch(url):
                if url.endswith('.pdf'):return b'%PDF-1.0',{}
                if 'page=2' in url:return b'<a href="a.pdf">duplicate</a><a href="b.pdf">next report</a><a href="?page=3">Next</a>',{}
                return b'<a href="a.pdf">report</a><a href="?page=2">Next</a>',{}
            result=discover(root,cfg,fetch);self.assertEqual(2,len(result['sources']));self.assertEqual(2,len(result['documents']))

    def test_page_capture_is_idempotent_and_invalid_page_is_local(self):
        import shutil
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'data/snapshots').mkdir(parents=True)
            source=next(s for s in self.snaps if s['key']=='north_stanmore_mre2025')
            shutil.copyfile(ROOT/source['path'],root/source['path'])
            (root/'data/manifest.json').write_text(json.dumps({'snapshots':[source]}))
            a=capture_pages(root,source,[6,999]);before=(root/'data/manifest.json').read_bytes()
            b=capture_pages(root,source,[6,999]);self.assertEqual(before,(root/'data/manifest.json').read_bytes())
            self.assertEqual(a,b);self.assertEqual('UNAVAILABLE',a[1]['status']);self.assertEqual(2,len(json.loads(before)['snapshots']))

    def test_direct_pdf_discovery_is_not_html(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'data/snapshots').mkdir(parents=True);(root/'data/manifest.json').write_text('{"snapshots":[]}')
            cfg={'seeds':[{'key':'pdf','url':'https://issuer.test/report','allowed_hosts':['issuer.test']}]}
            result=discover(root,cfg,lambda url:(b'%PDF-1.6\nfixture',{}))
            manifest=json.loads((root/'data/manifest.json').read_text())
            self.assertEqual('DIRECT_PDF_CAPTURED',result['sources'][0]['status'])
            self.assertEqual('pdf',manifest['snapshots'][0]['kind']);self.assertTrue(manifest['snapshots'][0]['path'].endswith('.pdf'))

    def test_comparison_preserves_missing_and_measures_resource_increment(self):
        from au_ree_v2.analysis import compare_runs
        out=self.work/'comparison';cfg=json.loads((ROOT/'config/research.json').read_text());prepare(self.db,'2026-11-03',self.snaps,self.resources,{},cfg,out,canonical_ids=self.ids['mapping'],cases=self.cases)
        (out/'snapshot_lock.json').write_text(json.dumps(self.snaps))
        comparison=compare_runs(ROOT/'results/phase4-2026-11-03',out)
        self.assertEqual(7,comparison['before']['resource_defined']);self.assertEqual(16,comparison['after']['resource_defined'])
        self.assertIsNone(comparison['after']['unresolved_pairs'])
        self.assertTrue((out/'comparison_provenance.json').exists())

    def test_obsolete_assertion_is_superseded_without_merging_yttria(self):
        from au_ree_v2.store import issue,canonical
        decision=next(d for d in json.loads((ROOT/'data/identity_links.json').read_text())['links'] if d['source_key']=='yttria_2025')
        details=canonical({'decision':decision,'reason':'AssertionError'})
        issue(self.db,None,decision['source_sha256'],'IDENTITY_DECISION_REVIEW',details)
        result=resolve(self.db,ROOT,self.snaps)
        status=self.db.execute('SELECT status FROM review_queue WHERE details=?',(details,)).fetchone()[0]
        self.assertEqual('SUPERSEDED_BY_SPECIFIC_DIAGNOSTIC',status)
        self.assertEqual(31,sum(r['status']!='DOCUMENT_SUPPORTED_EQUIVALENCE' for r in result['candidates']))
