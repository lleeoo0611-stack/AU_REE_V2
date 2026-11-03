import copy,json,uuid,unittest,csv,os,shutil
from pathlib import Path
from unittest.mock import patch
from au_ree_v2.store import connect,entity,canonical,digest,logical_dump
from au_ree_v2.acquisition import select_snapshots
from au_ree_v2.evidence import ingest_sources,ingest_claims,resource_values,transformation_issues
from au_ree_v2.resolution import resolve
from au_ree_v2.hierarchy import build
from au_ree_v2.studies import ingest,prepare
from au_ree_v2.security import sensitive_reference

ROOT=Path(__file__).resolve().parents[1]
class ResolutionStudyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.work=ROOT/'work/tests'/uuid.uuid4().hex;cls.work.mkdir(parents=True)
        cls.db=connect(cls.work/'canonical.sqlite');cls.snapshots=json.loads((ROOT/'results/phase4-2026-11-03/snapshot_lock.json').read_text())
        ingest_sources(cls.db,ROOT,cls.snapshots);ingest_claims(cls.db,ROOT,cls.snapshots,'2026-11-03')
        cls.cases=ingest(cls.db,ROOT,cls.snapshots,'2026-11-03');build(cls.db,cls.snapshots)
        cls.resolved=resolve(cls.db,ROOT,cls.snapshots)
    @classmethod
    def tearDownClass(cls):cls.db.close()

    def test_complete_native_ledger_and_no_source_records_lost(self):
        ledger=self.resolved['ledger'];self.assertEqual(339,len(ledger));self.assertEqual(339,len({r['target_id'] for r in ledger}))
        self.assertEqual(22,sum(r['status']=='LEGACY_ONLY_NO_OFFICIAL_ID' for r in ledger))
        self.assertTrue(all(r['status'] for r in ledger))

    def test_full_screen_index_coverage_is_not_project_promotion(self):
        rows=self.db.execute('SELECT * FROM census_screen_index').fetchall()
        self.assertEqual(1006,len(rows));self.assertEqual(7,len({r['state'] for r in rows}))
        self.assertEqual(121,len({r['parent_candidate_id'] for r in rows if r['parent_candidate_id']}))
        self.assertTrue(all(self.db.execute('SELECT kind FROM entities WHERE entity_id=?',(r['parent_candidate_id'],)).fetchone()[0]=='PROJECT_CANDIDATE' for r in rows if r['parent_candidate_id']))
        for row in rows:self.assertFalse(sensitive_reference(row['raw']))

    def test_encoded_reference_guard(self):
        from urllib.parse import quote
        value='https://example.invalid/?'+'access_token'+'=test-only'
        for i in range(7):
            self.assertTrue(sensitive_reference(value));value=quote(value,safe='')
        self.assertFalse(sensitive_reference('https://example.gov.au/download?inline='))

    def test_typed_supported_equivalence_not_name_only_merge(self):
        accepted=self.resolved['accepted']
        self.assertEqual(1,sum(r['kind']=='PROJECT' for r in accepted))
        self.assertEqual(1,sum(r['kind']=='DEPOSIT' for r in accepted))
        self.assertTrue(all(r['status']=='DOCUMENT_SUPPORTED_RULE_NOT_INDEPENDENT_APPROVAL' for r in accepted))
        self.assertTrue(any(r['name']=='Yttria' and r['status']=='LOCATION_CONFLICT_REVIEW' for r in self.resolved['candidates']))
        kinds={r['entity_id']:r['kind'] for r in self.resolved['membership']}
        self.assertTrue(all(kinds[r['alias_id']]==kinds[r['canonical_id']] for r in accepted))

    def test_resolution_is_idempotent_and_preserves_original_ids(self):
        before=digest(logical_dump(self.db));resolve(self.db,ROOT,self.snapshots)
        self.assertEqual(before,digest(logical_dump(self.db)))

    def test_oxide_reconciliation_and_seven_resource_scopes(self):
        values=resource_values(self.db,'2026-11-03',{s['sha256'] for s in self.snapshots});self.assertEqual(7,len(values))
        dubbo=next(r for r in values.values() if 'Toongi' in r['scope'])
        self.assertAlmostEqual(.88,dubbo['grade_pct']);self.assertAlmostEqual(661.584,dubbo['contained_treo_kt'])
        claims=json.loads((ROOT/'data/claims.json').read_text(encoding='utf8'))
        p=next(p for p in claims['projects'] if p['id']=='dubbo-project');grade=next(o for o in p['observations'] if o['variable']=='grade')
        self.assertEqual([],transformation_issues(grade,p['observations']))
        wrong=copy.deepcopy(grade);wrong['value']=7400;self.assertTrue(transformation_issues(wrong,p['observations']))
        other=copy.deepcopy(p['observations']);other[0]['scope']='different deposit';self.assertTrue(transformation_issues(grade,other))

    def test_endpoint_and_finance_contracts_do_not_fill_missing(self):
        self.assertEqual(5,len(self.cases))
        c=json.loads((ROOT/'config/research.json').read_text());panels,trace=prepare(self.cases,c,self.work/'out',self.resolved['mapping'])
        self.assertEqual({'beneficiation_concentrate_screen':2},panels)
        self.assertEqual({84,85.7},{r['raw_value'] for r in trace if r['criterion']=='TC1'})
        self.assertEqual(0,self.db.execute("SELECT COUNT(*) FROM observations WHERE variable='financing_ord'").fetchone()[0])
        self.assertEqual(0,self.db.execute("SELECT COUNT(*) FROM observations WHERE variable='recovery_pct'").fetchone()[0])
        self.assertTrue(any(c['finance_state']=='NO_BINDING_FINANCING_REPORTED' for c in self.cases))
        # All finance/flow facts remain case-scoped, not resource scores.
        self.assertEqual({r['element'] for r in self.cases if r['endpoint']=='LEACH_SOLUTION'},{'Nd'})

    def test_concurrent_cases_exclude_only_affected_project(self):
        duplicate=copy.deepcopy(next(c for c in self.cases if c['case_id']=='browns-dfs2025'));duplicate['case_id']='test-concurrent-study-scope'
        config=json.loads((ROOT/'config/research.json').read_text())
        panels,trace=prepare(self.cases+[duplicate],config,self.work/'conflict-panel',self.resolved['mapping'])
        self.assertEqual({'beneficiation_concentrate_screen':1},panels)
        self.assertEqual({85.7},{r['raw_value'] for r in trace if r['criterion']=='TC1'})

    def test_r_does_not_invent_measurement_intervals_for_point_case_inputs(self):
        from au_ree_v2.analysis import run_r
        rscript=os.environ.get('RSCRIPT') or shutil.which('Rscript')
        windows=Path('C:/Program Files/R/R-4.5.2/bin/Rscript.exe')
        if not rscript and windows.exists():rscript=str(windows)
        if not rscript:self.skipTest('R unavailable; CI installs R')
        config=json.loads((ROOT/'config/research.json').read_text());folder=self.work/'r-contract'
        panels,_=prepare(self.cases,config,folder,self.resolved['mapping'])
        run_r(ROOT,folder,dict(panels=panels),config,rscript)
        with (folder/'beneficiation_concentrate_screen/rounding_uncertainty.csv').open() as f:rows=list(csv.DictReader(f))
        self.assertTrue(rows)
        self.assertTrue(all(r['uncertainty']=='NOT_QUANTIFIED_NO_SOURCE_BOUNDS' and r['q05']==r['q95']=='' for r in rows))

    def test_one_unreadable_case_does_not_block_other_cases(self):
        from pypdf import PdfReader
        target=next(s['path'] for s in self.snapshots if s['key']=='jupiter_scoping2026')
        def reader(path):
            if str(path).replace('\\','/').endswith(target):raise OSError('test only')
            return PdfReader(path)
        tmp=connect(self.work/'isolated.sqlite')
        try:
            ingest_sources(tmp,ROOT,self.snapshots)
            with patch('au_ree_v2.studies.PdfReader',side_effect=reader):rows=ingest(tmp,ROOT,self.snapshots,'2026-11-03')
            self.assertEqual(4,len(rows))
        finally:tmp.close()

    def test_nonunique_native_id_never_merges_named_sa_locations(self):
        db=connect(self.work/'nonunique.sqlite');sha='a'*64
        try:
            db.execute('INSERT INTO sources VALUES(?,?,?,?,?,?,?,?)',(sha,'test','https://example.gov.au',None,'now','test','test','{}'))
            for name in ('Olympic Dam','Clarke'):
                eid=entity(db,'TEST',name,'SOURCE_RECORD')
                raw=dict(source_kind='LEGACY_NATIONAL_E1_SELECTED_FEATURE',source_key='SA_GEODATA_MINDEP',original_native_id=77,
                         legacy_target_id=name,original_attributes={'MINERAL_DEPOSIT_NO':77,'DEPOSIT_NAME':name})
                db.execute('INSERT INTO records VALUES(?,?,?,?,?,?,?,?,?)',(eid,sha,name,'SA',None,None,None,None,canonical(raw)))
            result=resolve(db,self.work,[dict(key='test',sha256=sha,available_date='2026-11-03')])
            self.assertEqual(2,len(result['ledger']));self.assertTrue(all(r['status']=='NATIVE_ID_NONUNIQUE_REVIEW' for r in result['ledger']))
            self.assertEqual(0,db.execute("SELECT COUNT(*) FROM entities WHERE kind='SITE'").fetchone()[0])
        finally:db.close()

    def test_rebuild_gap_audit_and_formal_policy_separation(self):
        from au_ree_v2.resolution import technical_coverage
        from au_ree_v2.eligibility import audit
        technical=technical_coverage(self.db,self.resolved,resource_values(self.db,'2026-11-03',{s['sha256'] for s in self.snapshots}),self.cases,{s['sha256'] for s in self.snapshots})
        out=self.work/'audit';out.mkdir(exist_ok=True)
        a=audit(self.db,out,self.resolved,technical,{'coverage':[]},{},'2026-11-03',self.snapshots)
        b=audit(self.db,out,self.resolved,technical,{'coverage':[]},{},'2026-11-03',self.snapshots)
        self.assertEqual(a,b);self.assertEqual(38,a['unresolved_pairs']);self.assertEqual(18,a['primary_scope_gaps'])
        self.assertEqual(0,a['formal_c1_evaluated']);self.assertEqual(27,a['registry_groups'])
