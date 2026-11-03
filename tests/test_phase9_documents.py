"""Document recognition without Project-specific numerical transcription."""
import json
import unittest
import uuid
from pathlib import Path
from au_ree_v2.acquisition import select_snapshots
from au_ree_v2.pdf_extract import (project_registry, resource_rows, leach_tables,
    narrative_candidates, publication_date, recognize_document)
from au_ree_v2.evidence import ingest_sources, ingest_claims, ingest_recognized, resource_values, load_claims
from au_ree_v2.store import connect, digest, logical_dump

ROOT=Path(__file__).resolve().parents[1]


class DocumentRecognitionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry=project_registry(ROOT)
        cls.snapshots=json.loads((ROOT/'results/phase9-2026-11-03/snapshot_lock.json').read_text())
        config=json.loads((ROOT/'results/phase9-2026-11-03/configuration.json').read_text())
        cls.claims=load_claims(ROOT,config['claims_sha256'])[0]
        cls.artifacts={s['source_sha256']:json.loads((ROOT/s['path']).read_text(encoding='utf-8'))
                       for s in cls.snapshots if s['kind']=='document_extraction'}

    def artifact(self,key):
        source=next(s for s in self.snapshots if s['key']==key)
        return self.artifacts[source['sha256']]

    def test_unconfigured_resource_table_columns_and_oxide_definitions(self):
        data=self.artifact('yttria_maiden2024')
        row=next(c for c in data['candidates'] if c['kind']=='RESOURCE_TABLE_TOTAL' and not c['issues'])
        self.assertEqual({'ore_mt':15.,'grade':490.},row['values'])
        self.assertEqual('INDICATED_INFERRED_TOTAL',row['category'])
        self.assertEqual('ppm',row['units']['grade'])
        self.assertEqual(2,row['physical_page']);self.assertTrue(row['bboxes'])
        self.assertIn('plus Y',row['basis_definition']);self.assertIn('200 ppm TREO-Ce',row['cutoff'])
        self.assertEqual(3.7,next(x['value'] for x in row['extra_values'] if x['label']=='Tb4O7'))

    def test_reserve_and_resource_never_added(self):
        data=self.artifact('mt_weld_2024')
        resource=next(c for c in data['candidates'] if c['kind']=='RESOURCE_TABLE_TOTAL' and c['physical_page']==2)
        reserve=next(c for c in data['candidates'] if c['kind']=='RESOURCE_TABLE_TOTAL' and c['physical_page']==3)
        self.assertEqual(106.6,resource['values']['ore_mt'])
        self.assertEqual(4389.,resource['values']['contained_treo_kt'])
        self.assertEqual('ORE_RESERVE',reserve['resource_type'])
        self.assertIn('RESERVE_SUBSET_NOT_RESOURCE',reserve['issues'])
        # Printed table says4.1; narrative says4.12. Preserve table precision.
        self.assertEqual(4.1,resource['values']['grade'])

    def test_density_column_never_promoted_to_treo_grade(self):
        rows=[c for c in self.artifact('koppamurra_pfs2026')['candidates'] if c['kind']=='RESOURCE_TABLE_TOTAL' and c['physical_page']==8]
        self.assertTrue(rows)
        self.assertTrue(all('TABLE_COLUMN_OR_UNIT_UNRESOLVED' in c['issues'] for c in rows))

    def test_new_leach_tables_have_separate_acids_samples_and_endpoints(self):
        data=self.artifact('discovery_asra_primary_met_alternative_530e7a5f3d94')
        rows=[c for c in data['candidates'] if c['kind']=='LEACH_TABLE_ROW' and not c['issues']]
        self.assertEqual(16,len(rows));self.assertTrue(all(not c['issues'] for c in rows))
        means=[c for c in rows if c['statistic']=='SOURCE_REPORTED_MEAN']
        self.assertEqual([49.,66.],sorted(c['values']['TREO'] for c in means))
        self.assertEqual(2,len({c['reagent'] for c in means}))
        self.assertTrue(all(c['endpoint']=='LEACH_SOLUTION' and c['residence_hours']==16 and c['temperature_c']==50 for c in rows))
        self.assertTrue(all(c['acid_concentration'] is None and c['feed']=='SELECTED_DRILL_INTERVALS' for c in rows))
        self.assertTrue(all(c['basis'].endswith('EXCLUDING_SC') for c in rows))

    def test_qualitative_full_recovery_never_becomes_100_percent(self):
        data=self.artifact('discovery_ar3_quarter_detail_alternative_615bb4ec1725')
        rows=[c for c in data['candidates'] if 'full recoveries' in c['raw_text']]
        self.assertTrue(rows);self.assertTrue(all(not c.get('numbers') for c in rows))

    def test_company_cash_not_attributed_by_adjacent_project(self):
        rows=narrative_candidates('Koppamurra Project is under evaluation. The Company raised financing of $5 million.',1,self.registry)
        self.assertTrue(rows);self.assertIsNone(rows[-1]['project_id'])

    def test_forward_looking_study_is_not_completed(self):
        rows=narrative_candidates('Koppamurra Project DFS will commence in 2027.',1,self.registry)
        self.assertIn('FORWARD_LOOKING_NOT_COMPLETED_EVENT',rows[0]['issues'])

    def test_release_date_not_cited_resource_or_quarter_end_date(self):
        self.assertEqual('2026-10-30',publication_date('ASX Release: 30 October 2026\nFor the quarter ended30 September2026'))
        self.assertIsNone(publication_date('Quarterly report\nRefer announcement 10 September 2026'))
        self.assertEqual('2026-10-30',publication_date('ASX ANNOUNCEMENT\nASX: AR3 | ASX Release: 30 October 2026\nrefer ASX announcement 11 August 2026'))

    def test_missing_and_non_resource_totals_remain_candidates(self):
        rows=resource_rows('Mineral Resource\nTREO (%)\nTotal 0 5\n',1,self.registry)
        self.assertTrue(rows);self.assertTrue(rows[0]['issues'])

    def test_no_manual_claims_for_newly_acquired_documents(self):
        used={o['source_sha256'] for p in self.claims['projects'] for o in p['observations']}
        for key in ('discovery_asra_primary_met_alternative_530e7a5f3d94','discovery_ar3_quarter_detail_alternative_615bb4ec1725'):
            data=self.artifact(key);self.assertNotIn(data['source_sha256'],used)
            self.assertEqual(data['source_sha256'],next(s['sha256'] for s in self.snapshots if s['key']==key))

    def test_fresh_parse_of_new_primary_documents_reproduces_frozen_candidates(self):
        for key in ('discovery_asra_primary_met_alternative_530e7a5f3d94','discovery_ar3_quarter_detail_alternative_615bb4ec1725'):
            source=next(s for s in self.snapshots if s['key']==key)
            fresh=recognize_document(ROOT,source,self.registry,parser_version=self.artifact(key)['version'])
            self.assertEqual(self.artifact(key)['candidates'],fresh['candidates'])
            self.assertEqual(self.artifact(key)['publication_date'],fresh['publication_date'])

    def test_source_tampering_is_rejected(self):
        source=dict(next(s for s in self.snapshots if s['key']=='yttria_maiden2024'),sha256='0'*64)
        with self.assertRaisesRegex(ValueError,'SOURCE_HASH_MISMATCH'):recognize_document(ROOT,source,self.registry)

    def test_changed_structured_number_with_unchanged_row_is_rejected(self):
        from au_ree_v2.pdf_extract import candidate_value_issues
        data=self.artifact('yttria_maiden2024')
        row=next(c for c in data['candidates'] if c['kind']=='RESOURCE_TABLE_TOTAL' and not c['issues'])
        changed=dict(row,values={**row['values'],'grade':999})
        self.assertEqual(['ROW_TOKEN_VALUE_MISMATCH'],candidate_value_issues(changed))

    def test_extraction_version_must_be_in_historical_lock(self):
        from au_ree_v2.selection import observation_visible
        self.assertFalse(observation_visible({'extraction_artifact_sha256':'new'}, {'original'}))
        self.assertTrue(observation_visible({'extraction_artifact_sha256':'new'}, {'original','new'}))
        self.assertTrue(observation_visible({}, {'original'}))

    def test_incremental_capture_reuses_verified_original_and_parser_contract(self):
        from au_ree_v2.pdf_extract import capture_documents
        from unittest.mock import patch
        import shutil
        folder=ROOT/'work/tests'/uuid.uuid4().hex;(folder/'data/snapshots').mkdir(parents=True)
        source=next(s for s in self.snapshots if s['key']=='yttria_maiden2024')
        artifact=next(s for s in self.snapshots if s.get('source_sha256')==source['sha256'] and s['kind']=='document_extraction')
        # The historical fixture is v1; test reuse with its original layout
        # contract. Phase10 separately tests upgrade invalidation.
        shutil.copyfile(ROOT/source['path'],folder/source['path'])
        shutil.copyfile(ROOT/artifact['path'],folder/artifact['path'])
        (folder/'data/claims.json').write_text(json.dumps(self.claims),encoding='utf-8')
        (folder/'data/manifest.json').write_text(json.dumps({'snapshots':[source,artifact]}))
        with patch('au_ree_v2.pdf_extract.DOCUMENT_VERSION',self.artifact('yttria_maiden2024')['version']), patch('au_ree_v2.pdf_extract.RESOURCE_LAYOUT_VERSION',None), patch('au_ree_v2.pdf_extract.recognize_document',side_effect=AssertionError('unchanged document must not be parsed')):
            rows=capture_documents(folder,[source],only_missing=True)
        self.assertEqual('REUSED_VERIFIED_EXTRACTION',rows[0]['status'])
        # Conversely, a parser upgrade cannot silently reuse a v1 derivative.
        # The sentinel proves extraction was attempted; its deliberate failure
        # remains local and does not overwrite either immutable source artifact.
        original_bytes=(folder/source['path']).read_bytes()
        artifact_bytes=(folder/artifact['path']).read_bytes()
        with patch('au_ree_v2.pdf_extract.DOCUMENT_VERSION','new-parser-version'), patch('au_ree_v2.pdf_extract.RESOURCE_LAYOUT_VERSION',None), patch('au_ree_v2.pdf_extract.recognize_document',side_effect=RuntimeError('EXPECTED_NEW_PARSER_ATTEMPT')) as parser:
            rows=capture_documents(folder,[source],only_missing=True)
        parser.assert_called_once()
        self.assertEqual('EXTRACTION_FAILED',rows[0]['status'])
        self.assertEqual('EXPECTED_NEW_PARSER_ATTEMPT',rows[0]['reason'])
        self.assertEqual(original_bytes,(folder/source['path']).read_bytes())
        self.assertEqual(artifact_bytes,(folder/artifact['path']).read_bytes())


class AutomaticIngestionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder=ROOT/'work/tests'/uuid.uuid4().hex;cls.folder.mkdir(parents=True)
        cls.db=connect(cls.folder/'canonical.sqlite')
        cls.snaps=json.loads((ROOT/'results/phase9-2026-11-03/snapshot_lock.json').read_text())
        config=json.loads((ROOT/'results/phase9-2026-11-03/configuration.json').read_text())
        cls.claims=load_claims(ROOT,config['claims_sha256'])[0]
        ingest_sources(cls.db,ROOT,cls.snaps);ingest_claims(cls.db,ROOT,cls.snaps,'2026-11-03',conflict_selection=True,claims_data=cls.claims)
        cls.before=resource_values(cls.db,'2026-11-03',{s['sha256'] for s in cls.snaps},strict=True)
        cls.result=ingest_recognized(cls.db,ROOT,cls.snaps,'2026-11-03',{'parser_version':'document-recognition-v1'})

    @classmethod
    def tearDownClass(cls):cls.db.close()

    def test_new_technical_numbers_reach_existing_observation_store(self):
        rows=list(self.db.execute("SELECT * FROM observations WHERE transform_version='document-recognition-v1' AND variable='reported_technical_extraction_treo_pct' AND status='AUTO_VALIDATED'"))
        self.assertEqual(16,len(rows))
        self.assertTrue(all(r['value'] is not None and json.loads(r['raw'])['endpoint']=='LEACH_SOLUTION' for r in rows))

    def test_no_resource_doubling_or_changed_confirmed_values(self):
        after=resource_values(self.db,'2026-11-03',{s['sha256'] for s in self.snaps},strict=True)
        self.assertEqual(self.before,after)

    def test_repeated_ingestion_stable(self):
        before=digest(logical_dump(self.db))
        ingest_recognized(self.db,ROOT,self.snaps,'2026-11-03',{'parser_version':'document-recognition-v1'})
        self.assertEqual(before,digest(logical_dump(self.db)))

    def test_explicit_parent_relation_does_not_merge_project_ids(self):
        from au_ree_v2.resolution import document_relations
        before={r[0] for r in self.db.execute('SELECT entity_id FROM entities')}
        found=document_relations(self.db,ROOT,self.snaps,'2026-11-03')
        self.assertTrue(found)
        self.assertTrue(all(r['parent_id']!=r['child_id'] and r['relation'].endswith('NOT_IDENTITY') for r in found))
        self.assertEqual(before,{r[0] for r in self.db.execute('SELECT entity_id FROM entities')})

    def test_text_values_are_null_and_never_financing_score(self):
        rows=list(self.db.execute("SELECT variable,value FROM observations WHERE transform_version='document-recognition-v1' AND variable LIKE '%disclosure'"))
        self.assertTrue(rows);self.assertTrue(all(r['value'] is None for r in rows))
        self.assertEqual(0,self.db.execute("SELECT count(*) FROM observations WHERE transform_version='document-recognition-v1' AND variable IN ('financing_ord','recovery_pct')").fetchone()[0])

    def test_individual_oxide_is_not_mislabelled_as_total_treo(self):
        row=self.db.execute("SELECT basis,raw FROM observations WHERE variable='reported_technical_extraction_sc2o3_pct' LIMIT 1").fetchone()
        self.assertEqual('Sc2O3',row['basis']);self.assertIn('EXCLUDING_SC',json.loads(row['raw'])['source_total_basis'])

    def test_changed_parser_or_broken_artifact_fails_locally(self):
        result=ingest_recognized(self.db,ROOT,self.snaps,'2026-11-03',{'parser_version':'unsupported'})
        self.assertTrue(result);self.assertTrue(all(r['status']=='EXTRACTION_FAILED' for r in result))


if __name__=='__main__':unittest.main()
