import copy
import json
import unittest
from pathlib import Path
from au_ree_v2.pdf_extract import narrative_candidates, recognize_document, project_registry
from au_ree_v2.selection import technical_record, technical_compare
ROOT=Path(__file__).resolve().parents[1]
V5='document-recognition-v5-technical-cells'

class Phase15Repairs(unittest.TestCase):
    def test_direct_recovery_bound_not_other_percentages(self):
        text='Example Project reports 85.7% TREO recovery at 25% grade and 8% moisture. Overall TREO recovery of 85% was reported for Example Project.'
        rows=narrative_candidates(text,1,[dict(entity_id='test',aliases=['Example Project'])],V5)
        good=[n['value'] for r in rows for n in r['numbers'] if n.get('quantity_role')]
        self.assertEqual([85.7,85.0],good)

    def test_representativeness_requires_bound_evidence(self):
        p=json.loads((ROOT/'config/evidence_policy.json').read_text())
        c=dict(project_id='p',evidence_id='e',source_sha256='a'*64,variable='recovery_pct',
               raw=dict(sample_id='S',representativeness='SOURCE_ASSERTED',representativeness_evidence=dict(
                   source_sha256='a'*64,pdf_page=2,quote='Sample S represents the selected interval',sample_id='S',target_population='selected interval')))
        r=technical_record(c,p)
        self.assertEqual('SOURCE_ASSERTED',r['representativeness'])
        self.assertEqual('selected interval',r['representativeness_evidence']['target_population'])
        c['raw']['representativeness_evidence']['source_sha256']='b'*64
        self.assertEqual('RESOURCE_REPRESENTATIVENESS_NOT_ESTABLISHED',technical_record(c,p)['representativeness'])

    def test_within_composite_physical_contract_does_not_require_acid(self):
        r=dict(variable='grade_pct',unit='%',value=25.,basis='TREO',scope='table',study_date='2026-07-13',case_id='case',
               sample_population='S',statistic='INDIVIDUAL_TEST',evidence_mode='LAB_TEST',source_sha256='a'*64,pdf_page=3)
        contract=dict(version='technical-use-v2',variables=['grade_pct'],unit='%',basis=['TREO'],requires={},
                      analysis_scope='WITHIN_SAMPLE',required_conditions=['sample_population','statistic'])
        self.assertEqual([],technical_compare(r,contract))
        contract['required_conditions']+=['reagent','residence_hours']
        self.assertIn('MISSING_CONDITIONS',technical_compare(r,contract))

    def test_native_element_table_enters_production_path(self):
        source=dict(key='dubbo_scoping2025',kind='pdf',sha256='734d9ea35fd9617eb2bad21c48fec17cdae08a5c66fa3e3cf7857390d04218ab',path='data/snapshots/734d9ea35fd9617eb2bad21c48fec17cdae08a5c66fa3e3cf7857390d04218ab.pdf',url='https://announcements.asx.com.au/asxpdf/20250711/pdf/06lq7vsvvk6yms.pdf',publication_date='2025-07-11')
        data=recognize_document(ROOT,source,project_registry(ROOT),parser_version=V5,page_numbers={30,31,32})
        cells=[c for c in data['candidates'] if c['kind']=='TECHNICAL_TABLE_CELL' and c['physical_page'] in (30,31,32)]
        self.assertEqual(270,len(cells))
        negative=[c for c in cells if c['value'] is not None and c['value']<0]
        self.assertEqual([-0.5],[c['value'] for c in negative])
        self.assertTrue(all(c['bbox'] and c['header_path'] for c in cells))


class Phase15Contracts(unittest.TestCase):
    def test_range_negative_and_missing_preserve_source(self):
        from au_ree_v2.technical_tables import number_token,technical_numbers
        self.assertEqual(-.5,number_token('−0.5')['value'])
        r=number_token('60–70%');self.assertIsNone(r['value']);self.assertEqual([60.,70.],r['bounds'])
        self.assertEqual('NOT_APPLICABLE',number_token('N/A')['token_state'])
        self.assertEqual('NOT_REPORTED',number_token('-')['token_state'])
        r=technical_numbers('Example extraction of 60–70% was reported.')
        self.assertEqual(1,len(r));self.assertIsNone(r[0]['value']);self.assertEqual([60,70],r[0]['bounds'])

    def test_direct_quantity_negatives_and_extraction_binding(self):
        from au_ree_v2.technical_tables import technical_numbers,direct_role
        cases=[('Extraction of Nd reached 82%.',82.),('TREO recovery of 85%.',85.),('Overall recovery is 75%.',75.),
               ('Grade 8% and moisture 5%, with IRR of 33%.',None),('Mining recovery of 95%.',None),
               ('Core recovery was 98.5%.',None),('Deportment recovery of 90%.',None)]
        for text,expected in cases:
            found=[n['value'] for n in technical_numbers(text) if direct_role(text,n)]
            self.assertEqual([] if expected is None else [expected],found,text)

    def test_cumulative_ratio_and_stage_product_are_not_interchangeable(self):
        from au_ree_v2.technical import ratio
        self.assertAlmostEqual(29.2/68.,ratio(dict(value=29.2,denominator='original'),dict(value=68.,denominator='original'),'SAME_ORIGINAL_FEED_CUMULATIVE'))
        self.assertIsNone(ratio(dict(value=29.2,denominator='cleaner_feed'),dict(value=68.,denominator='original'),'SAME_ORIGINAL_FEED_CUMULATIVE'))
        self.assertAlmostEqual(80*.9,ratio(dict(value=80,basis='CeO2',process_id='c',denominator='B',**{'from':'B'}),dict(value=90,basis='CeO2',process_id='c',denominator='A',to='B'),'SERIAL_STAGE_FEEDS'))
        self.assertIsNone(ratio(dict(value=80,denominator='stage',**{'from':'parallel'}),dict(value=90,denominator='stage',to='B'),'SERIAL_STAGE_FEEDS'))

    def test_source_rounding_interval_not_arbitrary_tolerance(self):
        from au_ree_v2.technical import rounding_interval
        self.assertEqual((91.65,91.75),rounding_interval('91.7'))
        self.assertEqual((.924-.00005,.924+.00005),rounding_interval('0.9240'))

    def test_source_claim_not_project_extrapolation(self):
        record=dict(variable='x',unit='%',value=85,basis='TREO',scope='composite',study_date='2026-01-01',case_id='c',representativeness='SOURCE_ASSERTED',representativeness_evidence=dict(target_population='S'))
        contract=dict(version='technical-use-v2',variables=['x'],unit='%',analysis_scope='PROJECT_EXTRAPOLATION')
        self.assertIn('SAMPLE_REPRESENTATIVENESS_LIMITATION',technical_compare(record,contract))

    def test_historical_t1_retained_and_current_disclosure_versioned(self):
        current=json.loads((ROOT/'config/evidence_policy.json').read_text())
        old=json.loads((ROOT/'results/phase14-2026-11-04/configuration.json').read_text())['research']['evidence_resolution']
        for code in ('TC1','TC2'):self.assertEqual(old['criteria'][code],current['criteria'][code])
        self.assertEqual(old['criteria']['T1'],current['criteria']['T_RECOVERY_LEGACY'])
        self.assertEqual([],current['criteria']['T1']['variables'])
        self.assertEqual('technical-disclosure-transparency-v1',current['criteria']['T1']['derived_by'])
        self.assertEqual(old['technical_comparability'],current['technical_comparability'])
        self.assertNotEqual(current['criteria']['T_RECOVERY_LEGACY']['requires'],current['criteria']['TC1']['requires'])

    def test_scientific_invalidity_local_to_negative_cell(self):
        from au_ree_v2.pdf_extract import candidate_value_issues
        base=dict(kind='TECHNICAL_TABLE_CELL',value=-.5,original_token='-0.5',bounds=None,unit='%')
        self.assertEqual(['PERCENT_OUT_OF_RANGE'],candidate_value_issues(base))
        self.assertEqual([],candidate_value_issues(dict(base,value=7.8,original_token='7.8')))
        self.assertEqual(['CELL_TOKEN_VALUE_MISMATCH'],candidate_value_issues(dict(base,value=.5)))

    def test_legacy_function_results_remain_legacy(self):
        text='Example Project reports 85.7% TREO recovery.'
        for version in ['document-recognition-v1','document-recognition-v3-bound-quantities','document-recognition-v4-native-resource-totals']:
            rows=narrative_candidates(text,1,[dict(entity_id='test',aliases=['Example Project'])],version)
            self.assertFalse(any(n['quantity_role'] for r in rows for n in r['numbers']))

    def test_table_cache_without_geometry_requires_new_parse(self):
        from unittest.mock import patch
        source=dict(key='dubbo_scoping2025',kind='pdf',sha256='734d9ea35fd9617eb2bad21c48fec17cdae08a5c66fa3e3cf7857390d04218ab',path='data/snapshots/734d9ea35fd9617eb2bad21c48fec17cdae08a5c66fa3e3cf7857390d04218ab.pdf',url='https://announcements.asx.com.au/asxpdf/20250711/pdf/06lq7vsvvk6yms.pdf',publication_date='2025-07-11')
        d=recognize_document(ROOT,source,project_registry(ROOT),parser_version=V5,table_cache={30:[],31:[],32:[]},page_numbers={30,31,32})
        self.assertEqual(270,len([c for c in d['candidates'] if c['kind']=='TECHNICAL_TABLE_CELL' and c['physical_page'] in (30,31,32)]))

class Phase15DatabaseIntegration(unittest.TestCase):
    def test_native_cells_ingest_twice_without_new_projects_or_duplicate_observations(self):
        import sqlite3
        from au_ree_v2.store import SCHEMA,canonical,entity
        from au_ree_v2.evidence import ingest_recognized
        m=json.loads((ROOT/'data/manifest.json').read_text())['snapshots']
        keys={'dubbo_scoping2025','cummins_scoping2023','discovery_rarex_met_search_result_alternative_f9ffac4be94a'}
        originals=[s for s in m if s['key'] in keys and s['kind']=='pdf']
        originals=list({s['sha256']:s for s in originals}.values());shas={s['sha256'] for s in originals}
        aa=[s for s in m if s['kind']=='document_extraction' and s.get('source_sha256') in shas and s.get('parser_version')==V5]
        artifacts=list({sha:max([s for s in aa if s['source_sha256']==sha],key=lambda s:s['acquired_at']) for sha in shas}.values())
        snapshots=originals+artifacts
        db=sqlite3.connect(':memory:');db.row_factory=sqlite3.Row;db.executescript(SCHEMA)
        claims=json.loads((ROOT/'data/claims.json').read_text())
        for p in claims['projects']:
            if p.get('entity_kind','PROJECT')=='PROJECT':entity(db,p.get('entity_namespace','project_registry_v1'),str(p['id']),'PROJECT')
        projects=db.execute('SELECT count(*) FROM entities').fetchone()[0]
        for s in snapshots:db.execute('INSERT OR IGNORE INTO sources VALUES(?,?,?,?,?,?,?,?)',(s['sha256'],s['key'],s['url'],s.get('publication_date'),s['acquired_at'],s['path'],s['kind'],canonical(s)))
        policy=json.loads((ROOT/'config/evidence_policy.json').read_text())['document_pipeline']
        results=ingest_recognized(db,ROOT,snapshots,'2026-11-03',policy,'2026-11-04')
        failures=[r for r in results if r['status']=='EXTRACTION_FAILED'];self.assertEqual([],failures)
        before=[tuple(r) for r in db.execute('SELECT * FROM observations ORDER BY obs_id')]
        ingest_recognized(db,ROOT,snapshots,'2026-11-03',policy,'2026-11-04')
        self.assertEqual(before,[tuple(r) for r in db.execute('SELECT * FROM observations ORDER BY obs_id')])
        self.assertEqual(projects,db.execute('SELECT count(*) FROM entities').fetchone()[0])
        cells=[(json.loads(r['raw']),r['status']) for r in db.execute('SELECT * FROM observations') if json.loads(r['raw']).get('kind')=='TECHNICAL_TABLE_CELL']
        dubbo=[(r,s) for r,s in cells if r['physical_page'] in (30,31,32) and r['source_sha256']=='734d9ea35fd9617eb2bad21c48fec17cdae08a5c66fa3e3cf7857390d04218ab']
        self.assertEqual(270,len(dubbo));self.assertEqual(269,sum(s=='AUTO_VALIDATED' for r,s in dubbo))
        self.assertEqual([-.5],[r['value'] for r,s in dubbo if s=='REVIEW'])
        for r,status in cells:
            self.assertEqual(r['original_token'],r['raw_text'])
            self.assertTrue(r['extraction_artifact_sha256']);self.assertTrue(r['bbox'])
        from au_ree_v2.selection import resolve
        policy_all=json.loads((ROOT/'config/evidence_policy.json').read_text())
        selected=resolve(db,snapshots,'2026-11-03',{},[],{},policy_all,ROOT,'2026-11-04')
        self.assertTrue(selected['decisions'])
        self.assertFalse(any(r['criterion']=='T1' and r['value'] is not None for r in selected['decisions']))
        self.assertFalse(list(db.execute('PRAGMA foreign_key_check')))
        self.assertEqual('ok',db.execute('PRAGMA integrity_check').fetchone()[0])
        db.close()



class Phase15FlowTests(unittest.TestCase):
    def test_parallel_products_are_two_paths_not_serial_stages(self):
        from au_ree_v2.technical import flow_consistency
        common=dict(quantity='stage_recovery_pct',selection_reason=None,source_sha256='test',project_id='p',basis='CeO2',fraction_scope='in THM, in size')
        values=[('MUP','ROM','WCP',99.5),('WCP','WCP','Raw HMC',94.5),('CUP','Raw HMC','HMC',1.9),('CUP','Raw HMC','REEC',97.5),('Overall','ROM','HMC / REEC',91.7)]
        rows=[dict(common,process_stage=stage,from_material=fr,to_material=to,value=v,original_token=str(v),evidence_id=str(i)) for i,(stage,fr,to,v) in enumerate(values)]
        results=flow_consistency(rows)
        self.assertEqual(2,len(results));self.assertEqual(1,sum(r['rounding_consistent'] for r in results))
        self.assertTrue(all(len(r['stage_evidence_ids'])==3 for r in results))
        self.assertAlmostEqual(99.5*.945*.975,next(r['calculated_pct'] for r in results if r['rounding_consistent']))



class Phase15BenchmarkRegression(unittest.TestCase):
    def test_fixed_original_page_quantities_not_corpus_accuracy(self):
        from tools.evaluate_technical import evaluate
        result=evaluate(ROOT,V5)
        for row in result['results']:
            if row['partition'].startswith('DEVELOPMENT'):
                self.assertEqual(0,row['false_positive'],row)
                self.assertEqual(0,row['false_negative'],row)
                self.assertEqual(row['expected_cells'],row['strict_quantity_unit_scope_correct'])
                self.assertEqual(row['true_positive'],row['located_matches'])
        self.assertTrue(any(r['partition'].startswith('NOT_USED') for r in result['results']))

if __name__=='__main__':unittest.main()
