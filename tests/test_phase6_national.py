"""Live raw-first national census and primary-evidence regression contracts."""
import copy,json,tempfile,unittest,uuid
from pathlib import Path
from unittest.mock import patch
from au_ree_v2.acquisition import wfs,select_snapshots,government_changes
from au_ree_v2.store import connect,digest,logical_dump,filehash
from au_ree_v2.evidence import ingest_sources,ingest_claims,resource_values
from au_ree_v2.national import ingest_government,live_government_inventory,live_government_coverage,government_link_candidates,resource_quality_checks,raw_domain_coverage
from au_ree_v2.resolution import resolve,technical_coverage
from au_ree_v2.hierarchy import build
from au_ree_v2.studies import ingest as ingest_studies
ROOT=Path(__file__).resolve().parents[1]

class GovernmentAdapterTests(unittest.TestCase):
    def test_wfs_paging_requires_total_and_distinct_native_keys(self):
        s=dict(url='https://official.invalid/wfs',type_name='x:test',id_field='id',page_size=2)
        def response(url,params):
            if params.get('resultType')=='hits':return b'<FeatureCollection numberMatched="3"/>',{}
            start=params['startIndex'];items=[dict(properties={'id':n}) for n in ([1,2] if start==0 else [3])]
            return json.dumps(dict(type='FeatureCollection',features=items,numberMatched=3)).encode(),{}
        saved=[]
        with patch('au_ree_v2.acquisition.request',side_effect=response):
            d=wfs(s,saved.append)
        self.assertEqual(3,len(d['features']));self.assertEqual(3,len(saved));self.assertTrue(d['inventory']['complete'])
        def repeated(url,params):
            if params.get('resultType')=='hits':return b'<FeatureCollection numberMatched="3"/>',{}
            return json.dumps(dict(type='FeatureCollection',features=[dict(properties={'id':1})])).encode(),{}
        with patch('au_ree_v2.acquisition.request',side_effect=repeated):
            with self.assertRaisesRegex(ValueError,'duplicate'):wfs(s)

    def test_one_ambiguous_ree_native_key_does_not_block_other_locations(self):
        root=ROOT/'work/tests'/uuid.uuid4().hex;root.mkdir(parents=True);path=root/'raw.json'
        features=[dict(attributes=dict(id=k,name=n,commodity='Rare earth elements'),geometry=dict(x=120,y=-30)) for k,n in [(1,'Ambiguous A'),(1,'Ambiguous B'),(2,'Valid')]]
        path.write_text(json.dumps(dict(features=features,inventory=dict(complete=True,count=3))))
        s=dict(key='test',kind='government_arcgis',path='raw.json',sha256=filehash(path),namespace='TEST_SITE',state='WA',id_field='id',name_field='name',commodity_fields=['commodity'],available_date='2026-11-03')
        db=connect(root/'test.sqlite');db.execute('INSERT INTO sources VALUES(?,?,?,?,?,?,?,?)',(s['sha256'],'test','https://official.invalid',None,'now','raw.json',s['kind'],'{}'))
        result=ingest_government(db,root,s)
        self.assertEqual(1,result['ree_native_records']);self.assertEqual(1,db.execute('SELECT count(*) FROM entities').fetchone()[0])
        self.assertEqual(2,db.execute('SELECT count(*) FROM review_queue').fetchone()[0]);db.close()


    def test_incremental_delta_uses_native_values_not_generated_wfs_fid(self):
        folder=ROOT/'work/tests'/uuid.uuid4().hex;folder.mkdir(parents=True)
        old=dict(type='FeatureCollection',features=[dict(id='random-a',properties=dict(id=1,name='A'))])
        raw=json.dumps(old).encode();(folder/'old.json').write_bytes(raw)
        source=dict(kind='government_wfs',id_field='id')
        same=dict(type='FeatureCollection',features=[dict(id='random-b',properties=dict(id=1,name='A'))])
        previous=dict(path='old.json',sha256=filehash(folder/'old.json'))
        delta=government_changes(folder,source,previous,json.dumps(same).encode())
        self.assertEqual(0,delta['changed_native_id_groups']);self.assertEqual(1,delta['unchanged_native_id_groups'])
        same['features'].append(dict(properties=dict(id=2,name='B')))
        delta=government_changes(folder,source,previous,json.dumps(same).encode())
        self.assertEqual(1,delta['added_native_id_groups']);self.assertEqual(0,delta['removed_native_id_groups'])



    def test_public_derivative_keeps_original_bytes_and_scientific_values(self):
        from au_ree_v2.security import public_snapshot,public_export,sensitive_reference
        folder=ROOT/'work/tests'/uuid.uuid4().hex;folder.mkdir(parents=True)
        raw=('state,ore_mt,reference\nSA,243,https://official.test/report?to'+'ken=fictional_test_secret').encode()
        safe,meta=public_snapshot(folder,raw,'.csv')
        self.assertNotIn(b'fictional_test_secret',safe);self.assertIn(b'SA,243',safe)
        self.assertFalse(sensitive_reference(safe.decode()))
        self.assertEqual(raw,(folder/'work/retained_originals'/(meta['unpublished_original_sha256']+'.csv')).read_bytes())
        data=public_export(dict(value=243,reference=raw.decode()))
        self.assertEqual(243,data['value']);self.assertNotIn('fictional_test_secret',data['reference'])


class Phase6NationalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder=ROOT/'work/tests'/uuid.uuid4().hex;cls.folder.mkdir(parents=True)
        # This is a Phase6 regression, not an assertion that future data cannot grow.
        cls.db=connect(cls.folder/'canonical.sqlite');cls.snaps=json.loads((ROOT/'results/phase6-2026-11-03/snapshot_lock.json').read_text());cls.shas={s['sha256'] for s in cls.snaps}
        ingest_sources(cls.db,ROOT,cls.snaps);ingest_claims(cls.db,ROOT,cls.snaps,'2026-11-03')
        cls.cases=ingest_studies(cls.db,ROOT,cls.snaps,'2026-11-03');cls.resources=resource_values(cls.db,'2026-11-03',cls.shas);build(cls.db,cls.snaps);cls.ids=resolve(cls.db,ROOT,cls.snaps)
    @classmethod
    def tearDownClass(cls):cls.db.close()

    def test_seven_states_have_current_originals_not_relabelled_archive(self):
        rows=live_government_inventory(self.db,self.snaps);cov=live_government_coverage(ROOT,self.snaps,rows)
        complete=[r for r in cov if r['status'].startswith('COMPLETE')]
        self.assertEqual({'WA','QLD','TAS','NSW','VIC','NT','SA'},{r['state'] for r in complete})
        self.assertGreater(sum(r['raw_records'] for r in complete),90000)
        self.assertGreater(len({r['entity_id'] for r in rows}),400)
        self.assertTrue(all(r['source_role'].startswith('LIVE_GOVERNMENT') for r in rows))
        self.assertFalse(any('LEGACY_E1' in r['namespace'] for r in rows))
        self.assertEqual(1006,self.db.execute('SELECT count(*) FROM census_screen_index').fetchone()[0])
        self.assertFalse(any(r['reason']=='GOVERNMENT_SOURCE_INGEST_FAILED' for r in self.db.execute('SELECT reason FROM review_queue')))

    def test_idempotence_and_existing_stable_ids(self):
        before=digest(logical_dump(self.db));ingest_sources(self.db,ROOT,self.snaps);ingest_claims(self.db,ROOT,self.snaps,'2026-11-03');ingest_studies(self.db,ROOT,self.snaps,'2026-11-03');build(self.db,self.snaps);resolve(self.db,ROOT,self.snaps)
        self.assertEqual(before,digest(logical_dump(self.db)))
        old=json.loads((ROOT/'results/phase5-2026-11-03/logical_database.json').read_text(encoding='utf8'))
        for e in old['entities']:
            actual=self.db.execute('SELECT * FROM entities WHERE entity_id=?',(e['entity_id'],)).fetchone()
            self.assertEqual(e,dict(actual))

    def test_source_parents_and_raw_text_keep_scope_and_null_values(self):
        rows=live_government_inventory(self.db,self.snaps)
        self.assertTrue(any(r['namespace']=='WA_MINDEX_PROJECT' and r['kind']=='PROJECT_CANDIDATE' for r in rows))
        self.assertGreater(self.db.execute("SELECT count(*) FROM relations WHERE relation='GOVERNMENT_PROJECT_SITE_MEMBERSHIP'").fetchone()[0],200)
        raw=list(self.db.execute("SELECT * FROM observations WHERE status='DOCUMENTED_GOVERNMENT_RAW'"))
        self.assertGreater(len(raw),1000);self.assertTrue(all(r['value'] is None for r in raw))
        self.assertTrue(all(json.loads(r['raw'])['effective_date_status'].startswith('NOT_DISCLOSED') for r in raw))
        self.assertTrue(any(r['domain']=='Technical' for r in raw_domain_coverage(self.db,self.shas)))

    def test_new_scoped_resources_and_bases(self):
        self.assertEqual(19,len(self.resources))
        goschen=self.db.execute("SELECT entity_id FROM entities WHERE native_namespace='AUSTRADE_2026_REE_PROJECT' AND native_id='goschen'").fetchone()[0]
        self.assertAlmostEqual(74,self.resources[goschen]['contained_treo_kt']);self.assertIn('Area 1 ONLY',self.resources[goschen]['scope'])
        nar=self.db.execute("SELECT entity_id FROM entities WHERE native_namespace='project_registry_v1' AND native_id='narraburra'").fetchone()[0]
        self.assertAlmostEqual(94.9*738.95/1000,self.resources[nar]['contained_treo_kt'])
        self.assertFalse(any('Lyons 11' in r['scope'] for r in self.resources.values()))
        self.assertTrue(any(r['variable']=='reported_resource_grade_pct' and r['value']==.32 for r in self.db.execute('SELECT * FROM observations')))

    def test_old_pairs_reduced_without_merging_location_conflicts(self):
        import csv
        with (ROOT/'results/phase5-2026-11-03/unresolved_identity_pairs.csv').open(encoding='utf8') as stream:
            old={tuple(sorted((r['a'],r['b']))) for r in csv.DictReader(stream)}
        remaining=[r for r in self.ids['candidates'] if tuple(sorted((r['a'],r['b']))) in old and r['status']!='DOCUMENT_SUPPORTED_EQUIVALENCE']
        self.assertEqual(28,len(remaining))
        self.assertEqual(12,len(self.ids['accepted']))
        self.assertTrue(any(r['name']=='Yttria' and r['status']=='LOCATION_CONFLICT_REVIEW' for r in self.ids['candidates']))
        new=government_link_candidates(self.db,self.snaps);self.assertGreater(len(new),10)
        self.assertTrue(all(r['status']=='CANDIDATE_NAME_STATE_ONLY_NO_IDENTITY_EQUIVALENCE' for r in new))

    def test_shared_brothers_and_selected_circle_leach_do_not_duplicate_resources(self):
        cov=technical_coverage(self.db,self.ids,self.resources,self.cases,self.shas)
        names={r['canonical_project_id']:r['status'] for r in cov}
        self.assertEqual('PRIMARY_SHARED_RESOURCE_CONTEXT_ONLY_NO_ADDITIVE_RESOURCE',names['AU-47d12ebe6b66df8e5936'])
        case=next(c for c in self.cases if c['project_native_id']=='circle-valley')
        self.assertEqual('LEACH_SOLUTION',case['endpoint']);self.assertEqual('BENCH_FIVE_COMPOSITES',case['scale'])
        self.assertEqual('PRIMARY_PROCESS_EVIDENCE_ONLY_NOT_COMPARABLE_RESOURCE',names['AU-7537d9555628040fab40'])
        self.assertEqual(76,case['parameters']['treo_leach_average_pct']);self.assertNotIn('whole_ore_concentrate_recovery_pct',case['parameters'])
        lyons=[r for r in resource_quality_checks(self.db,self.shas) if 'Lyons11' in r['statement_id']]
        self.assertEqual('SOURCE_ARITHMETIC_CONFLICT',lyons[0]['status'])

    def test_frozen_phase5_reconstructs_16_scopes_and_six_gaps(self):
        db=connect(self.folder/'frozen.sqlite');snaps=json.loads((ROOT/'results/phase5-2026-11-03/snapshot_lock.json').read_text(encoding='utf8'));shas={s['sha256'] for s in snaps}
        ingest_sources(db,ROOT,snaps);ingest_claims(db,ROOT,snaps,'2026-11-03');resources=resource_values(db,'2026-11-03',shas);cases=ingest_studies(db,ROOT,snaps,'2026-11-03');ids=resolve(db,ROOT,snaps)
        self.assertEqual(16,len(resources));self.assertEqual(6,sum(r['status']=='NO_CONTROLLED_PRIMARY_TECHNICAL_SCOPE_YET' for r in technical_coverage(db,ids,resources,cases,shas)));self.assertEqual([],live_government_inventory(db,snaps));db.close()

if __name__=='__main__':unittest.main()
