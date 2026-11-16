"""Shared source-to-criterion comparability, with real Phase9 observations."""
import copy
import csv
import json
import random
import unittest
import uuid
from pathlib import Path
from au_ree_v2.selection import technical_record, technical_compare, technical_comparability
from au_ree_v2.pdf_extract import (resource_rows, positioned_resource_columns,
    project_registry, candidate_value_issues)

ROOT=Path(__file__).resolve().parents[1]


class TechnicalComparabilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.policy=json.loads((ROOT/'config/evidence_policy.json').read_text())
        cls.inventory=[]
        with (ROOT/'results/phase9-2026-11-03/resolved_evidence.csv').open(encoding='utf-8',newline='') as stream:
            for row in csv.DictReader(stream):
                if row['domain']!='Technical':continue
                c=dict(json.loads(row['raw']),**{k:v for k,v in row.items() if k!='raw'})
                c['raw']=json.loads(row['raw']);c['value']=float(row['value']) if row['value'] else None
                c['reason']=None if row['reason']=='VALID_RAW_EVIDENCE' else row['reason']
                cls.inventory.append(c)
        cls.rows=technical_comparability(cls.inventory,cls.policy)

    def source(self,case,variable='whole_ore_concentrate_recovery_pct'):
        return copy.deepcopy(next(c for c in self.inventory if c.get('case_id')==case and c['variable']==variable))

    def compare(self,c,code='TC1'):
        return technical_compare(technical_record(c,self.policy),self.policy['criteria'][code],self.policy['technical_comparability']['model_assumptions'])

    def test_two_independent_projects_two_cases_not_four_oxide_cases(self):
        good=[r for r in self.rows if r['comparability_status']=='NUMERIC_COMPARABLE']
        self.assertEqual(4,len(good))
        self.assertEqual(2,len({r['project_id'] for r in good}))
        self.assertEqual(2,len({r['case_id'] for r in good}))
        self.assertEqual({'TC1','TC2'},{r['comparison_group'] for r in good})
        self.assertTrue(all(r['independent_projects']==2 and r['assumptions'] for r in good))

    def test_three_semantic_classes_without_quality_score(self):
        self.assertEqual({'A_MINERALOGY_PROCESSING','B_PROCESS_PERFORMANCE','C_EVIDENCE_QUALITY'},{r['semantic_class'] for r in self.rows})
        self.assertFalse(any(r['comparability_status']=='NUMERIC_COMPARABLE' and r['semantic_class']=='C_EVIDENCE_QUALITY' for r in self.rows))

    def test_jupiter_alternative_design_never_overwrites_base(self):
        rows=[r for r in self.rows if r['case_id']=='jupiter-scoping-base2026']
        self.assertEqual({58.,63.},{r['value'] for r in rows})
        self.assertTrue(all(r['comparability_status']=='NOT_COMPARABLE' for r in rows))
        self.assertTrue(all('ENDPOINT_MISMATCH' in r['reason_codes'] for r in rows))

    def test_koppamurra_mine_plan_is_not_global_resource_or_separated_reo(self):
        r=next(r for r in self.rows if r['variable']=='resource_to_final_mreo_recovery_pct')
        self.assertEqual(68,r['value']);self.assertEqual('CALCINED_MIXED_REO',r['endpoint'])
        self.assertIn('ENDPOINT_MISMATCH',r['reason_codes'])
        self.assertIn('243Mt',r['scope']);self.assertEqual('CASE_MINE_PLAN',r['scope_kind'])

    def test_dubbo_zones_are_not_independent_projects_or_multiplied(self):
        rows=[r for r in self.rows if r['case_id']=='dubbo-heap-scoping2025' and r['variable'].startswith('nd_')]
        self.assertEqual([68.7,75.9,79.9],sorted(r['value'] for r in rows))
        self.assertEqual(1,len({r['case_id'] for r in rows}));self.assertEqual(1,len({r['project_id'] for r in rows}))
        self.assertTrue(all('REO_BASIS_MISMATCH' in r['reason_codes'] for r in rows))

    def test_cowalinya_grade_is_not_recovery_selected_population_is_preserved(self):
        r=next(r for r in self.rows if r['variable']=='mrec_treo_grade_pct')
        self.assertEqual(51.8,r['value']);self.assertIn('QUANTITY_MISMATCH',r['reason_codes'])
        selected=next(r for r in self.rows if r['variable']=='magnet_extraction_to_leach_pct')
        self.assertIn('45',selected['sample_population']);self.assertIn('SAMPLE_REPRESENTATIVENESS_LIMITATION',selected['reason_codes'])

    def test_circle_conditions_and_mean_maximum_are_distinct(self):
        rows=[r for r in self.rows if r['case_id']=='circle-valley-ansto-five-composites2022' and 'leach_' in r['variable'] and r['unit']=='%']
        self.assertTrue(rows);self.assertTrue(all(r['temperature_c']==50 and r['residence_hours']==6 and r['acid_concentration']==10 for r in rows))
        self.assertEqual({'SOURCE_REPORTED_MEAN','SOURCE_REPORTED_MAXIMUM'},{r['statistic'] for r in rows})

    def test_asra_acids_oxides_tests_and_means_never_pool(self):
        rows=[r for r in self.rows if r['variable'].startswith('reported_technical_extraction_') and not r['evidence_reason']]
        self.assertEqual(112,len(rows));self.assertEqual(16,len({r['case_id'] for r in rows}))
        self.assertEqual(1,len({r['project_id'] for r in rows}));self.assertEqual(2,len({r['reagent'] for r in rows}))
        self.assertEqual(7,len({r['basis'] for r in rows}))
        self.assertTrue(all(r['comparability_status']=='NOT_COMPARABLE' and 'MISSING_CONDITIONS' in r['reason_codes'] for r in rows))

    def test_input_order_invariance_and_duplicates_do_not_increase_samples(self):
        rows=copy.deepcopy(self.inventory);random.Random(42).shuffle(rows)
        self.assertEqual(self.rows,technical_comparability(rows+rows,self.policy))

    def test_invalid_duplicate_cannot_displace_valid_contract_or_inflate_projects(self):
        a=self.source('browns-dfs2025');b=dict(a,reason='SOURCE_HASH_MISMATCH',evidence_id='invalid',value=99)
        for data in ([a,b],[b,a]):
            r=technical_comparability(data,self.policy)[0]
            self.assertEqual('TC1',r['comparison_group']);self.assertEqual(84,r['value'])
            self.assertEqual('NUMERIC_COMPARABLE',r['comparability_status']);self.assertEqual(1,r['independent_projects'])

    def test_concurrent_values_conflict_locally_without_averaging(self):
        a=self.source('browns-dfs2025');b=dict(a,value=99,evidence_id='conflicting')
        for inventory in ([a,b],[b,a]):
            rows=technical_comparability(inventory,self.policy)
            self.assertEqual(1,len(rows));self.assertIsNone(rows[0]['value'])
            self.assertEqual(['CONFLICTING_EVIDENCE'],rows[0]['reason_codes'])

    def test_unknown_and_invalid_source_do_not_become_zero(self):
        c=self.source('browns-dfs2025');c['value']=None
        self.assertIn('NO_FINITE_NUMERIC_VALUE',self.compare(c))
        c['reason']='SOURCE_HASH_MISMATCH';c['value']=84
        self.assertIn('EVIDENCE_NOT_VALIDATED',self.compare(c))

    def test_percent_range_never_corrected_or_clipped(self):
        base=self.source('browns-dfs2025')
        for value in (-1,101):self.assertIn('PERCENT_OUT_OF_RANGE',self.compare(dict(base,value=value)))

    def test_all_semantic_dimensions_are_enforced(self):
        base=self.source('browns-dfs2025')
        for key,value,reason in [('endpoint','LEACH_SOLUTION','ENDPOINT_MISMATCH'),('feed','CONCENTRATE','FEED_MISMATCH'),('basis','Nd','REO_BASIS_MISMATCH'),('scale','BENCH','TEST_SCALE_MISMATCH'),('scope',None,'SCOPE_MISMATCH'),('unit','ppm','UNIT_MISMATCH')]:
            with self.subTest(key=key):self.assertIn(reason,self.compare(dict(base,**{key:value})))

    def test_two_cases_in_same_project_need_scope_choice(self):
        a=self.source('browns-dfs2025');b=dict(a,case_id='other-mine-plan',evidence_id='other')
        rows=technical_comparability([a,b],self.policy)
        self.assertTrue(all(r['comparability_status']=='NOT_COMPARABLE' for r in rows))
        self.assertEqual(rows,technical_comparability([b,a],self.policy))

    def test_design_comparison_requires_declared_assumptions(self):
        c=technical_record(self.source('browns-dfs2025'),self.policy)
        self.assertIn('MODEL_ASSUMPTIONS_NOT_DEFINED',technical_compare(c,self.policy['criteria']['TC1']))


class TechnicalEndToEndTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from au_ree_v2.store import connect
        from au_ree_v2.evidence import ingest_sources
        from au_ree_v2.studies import ingest
        cls.folder=ROOT/'work/tests'/uuid.uuid4().hex;cls.folder.mkdir(parents=True)
        cls.db=connect(cls.folder/'canonical.sqlite')
        cls.snaps=[s for s in json.loads((ROOT/'results/phase9-2026-11-03/snapshot_lock.json').read_text()) if s['key'] in ('browns_range_2025','yangibana_quarter2026')]
        cls.policy=json.loads((ROOT/'config/evidence_policy.json').read_text())
        ingest_sources(cls.db,ROOT,cls.snaps)
        cls.cases=ingest(cls.db,ROOT,cls.snaps,'2026-11-03')

    @classmethod
    def tearDownClass(cls):cls.db.close()

    def select(self,cases=None):
        from au_ree_v2.selection import resolve
        return resolve(self.db,self.snaps,'2026-11-03',{},self.cases if cases is None else cases,{},self.policy,ROOT)

    def test_original_pages_through_case_validation_selection_and_matrix(self):
        from au_ree_v2.studies import prepare
        from au_ree_v2.cli import research_configuration
        result=self.select();self.assertEqual(2,len(self.cases))
        self.assertEqual([84,85.7],sorted(v['TC1']['value'] for v in result['values'].values()))
        self.assertFalse(any('T1' in v for v in result['values'].values()))
        panels,trace=prepare(self.cases,research_configuration(ROOT),self.folder,{},result)
        self.assertEqual({'beneficiation_concentrate_screen':2},panels)
        self.assertEqual(4,len(trace))
        self.assertEqual(result['values'],self.select(list(reversed(self.cases)))['values'])

    def test_conflict_gate_blocks_only_related_project_before_matrix(self):
        cases=copy.deepcopy(self.cases);duplicate=copy.deepcopy(next(c for c in cases if c['case_id']=='browns-dfs2025'))
        duplicate['parameters']['whole_ore_concentrate_recovery_pct']=99
        result=self.select(cases+[duplicate])
        brown=duplicate['project_id'];self.assertNotIn('TC1',result['values'].get(brown,{}))
        self.assertEqual([85.7],[v['TC1']['value'] for v in result['values'].values() if 'TC1' in v])


class PositionedLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry=project_registry(ROOT)
        cls.lock=json.loads((ROOT/'results/phase9-2026-11-03/snapshot_lock.json').read_text())

    def repair(self,key,page):
        source=next(s for s in self.lock if s['key']==key)
        artifact=next(s for s in self.lock if s.get('source_sha256')==source['sha256'] and s['kind']=='document_extraction')
        data=json.loads((ROOT/artifact['path']).read_text());text=data['pages'][page-1]['text']
        candidates=[c for c in data['candidates'] if c['physical_page']==page]
        return positioned_resource_columns(candidates,[t for t in data['tables'] if t['physical_page']==page],text,self.registry)

    def test_density_is_explicitly_aligned_and_definition_still_missing(self):
        rows=[c for c in self.repair('koppamurra_pfs2026',8) if c['kind']=='RESOURCE_TABLE_TOTAL']
        r=rows[0];self.assertEqual({'ore_mt':243.,'grade':751.},r['values'])
        self.assertEqual(2,r['row_token_indices']['grade']);self.assertEqual(['REO_DEFINITION_NOT_LOCATED'],r['issues'])
        self.assertEqual([],candidate_value_issues(r))
        r['values']['grade']=1.6;self.assertIn('ROW_TOKEN_VALUE_MISMATCH',candidate_value_issues(r))
        self.assertIn('TABLE_COLUMN_OR_UNIT_UNRESOLVED',rows[1]['issues'])

    def test_wolverine_keeps_deposit_scope_not_dfs_inventory(self):
        r=next(c for c in self.repair('browns_range_2025',54) if c['kind']=='RESOURCE_TABLE_TOTAL')
        self.assertEqual({'ore_mt':7.3,'grade':.96},r['values']);self.assertEqual('%',r['units']['grade'])
        self.assertEqual([],r['issues']);self.assertIn('Wolverine',r['scope']);self.assertNotIn('stockpile',r['scope'])

    def test_unseen_mineral_fraction_and_multiple_project_tables_fail_safely(self):
        import fitz
        for key,page in [('burracoppin_maiden2023',2),('brockman_ar2025',17)]:
            source=next(s for s in self.lock if s['key']==key)
            with fitz.open(ROOT/source['path']) as doc:
                p=doc[page-1];text=p.get_text(sort=True)
                tables=[dict(cells=t.extract(),bbox=list(t.bbox)) for t in p.find_tables().tables]
                rows=resource_rows(text,page,self.registry)
                positioned_resource_columns(rows,tables,text,self.registry)
                self.assertTrue(rows)
                self.assertTrue(all(c['issues'] for c in rows),key)


if __name__=='__main__':unittest.main()
