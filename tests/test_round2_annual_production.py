import copy
import csv
import json
from pathlib import Path
import unittest
from au_ree_v2.round2_annual_production import (validate_candidate, proposed_decision,
    apply_annual_production, _approved, COLUMNS, HREO)


class AnnualProductionRound2Test(unittest.TestCase):
    def candidate(self, **changes):
        item=dict(column=COLUMNS[0], source_stated=True, product_basis='TOTAL_RARE_EARTH_OXIDE',
                  annual_basis='EXPLICIT_PER_ANNUM', scope_relation='Selected project; subset mine plan',
                  original_token='1,250', original_unit='tpa', value=1250)
        item.update(changes)
        return item

    def test_source_stated_tpa_accepted(self):
        self.assertEqual(validate_candidate(self.candidate()), '1250')

    def test_unit_conversion_only(self):
        self.assertEqual(validate_candidate(self.candidate(original_token='1.25', original_unit='ktpa')), '1250')

    def test_feed_grade_recovery_derivation_rejected(self):
        with self.assertRaisesRegex(ValueError, 'SOURCE_STATED'):
            validate_candidate(self.candidate(source_stated=False, derivation='feed * grade * recovery'))

    def test_derived_even_marked_stated_rejected(self):
        with self.assertRaisesRegex(ValueError, 'SOURCE_STATED'):
            validate_candidate(self.candidate(derivation='feed * grade'))

    def test_nonoxide_without_equivalent_rejected(self):
        for product in ['MREC', 'MONAZITE_CONCENTRATE', 'WET_FLOTATION_CONCENTRATE']:
            with self.subTest(product=product), self.assertRaisesRegex(ValueError, 'OXIDE_EQUIVALENT'):
                validate_candidate(self.candidate(product_basis=product))

    def test_source_stated_equivalent_accepted(self):
        self.assertEqual(validate_candidate(self.candidate(product_basis='REO_EQUIVALENT_IN_MIXED_CARBONATE')), '1250')

    def test_dy_tb_not_eight_heavy(self):
        with self.assertRaisesRegex(ValueError, '8_ELEMENT'):
            validate_candidate(self.candidate(column=COLUMNS[2], product_basis='HREO_8_ELEMENT', hre_elements=['Dy','Tb']))

    def test_eight_heavy_matches_table_y_not_gd(self):
        self.assertIn('Y', HREO)
        self.assertNotIn('Gd', HREO)
        self.assertEqual(validate_candidate(self.candidate(column=COLUMNS[2], product_basis='HREO_8_ELEMENT', hre_elements=list(HREO))), '1250')

    def test_non_annual_unit_rejected(self):
        with self.assertRaisesRegex(ValueError, 'EXPLICIT_UNIT'):
            validate_candidate(self.candidate(original_unit='tonnes'))

    def test_token_value_must_match(self):
        with self.assertRaisesRegex(ValueError, 'TOKEN_VALUE'):
            validate_candidate(self.candidate(value=1251))

    def test_decision_removal_and_scope(self):
        d=proposed_decision()
        self.assertEqual(_approved([d]),d)
        self.assertIsNone(_approved([]))
        self.assertIsNone(_approved([dict(d,scope='other')]))
        self.assertIsNone(_approved([dict(d,decided_by=None)]))

    def test_archived_cells_additive_dated_and_documented(self):
        from au_ree_v2 import round2_annual_production
        repo=Path(round2_annual_production.__file__).resolve().parents[2]
        self.assertTrue((repo/'work/asx-round6-sources/data/snapshots/40b378004d36b7b852cb7990438a126a84b0827a0ec4042ad3f7524923622f70.pdf').is_file(), 'Local archived source bytes required for integration test')
        with (repo/'results/asx-current/專案總表.csv').open(encoding='utf-8-sig', newline='') as f: rows=list(csv.DictReader(f))
        with (repo/'results/asx-current/field_provenance.csv').open(encoding='utf-8-sig', newline='') as f: prov=list(csv.DictReader(f))
        targets={'AU-d9fb1b1e3e2ec9fa0851','AU-447261eed0e81eae88bf'}
        # A fixed pre-D fixture works before and after publishing current.
        for row in rows:
            if row['專案ID'] in targets:
                row['開發階段代碼']='B1'
                row[COLUMNS[0]]=''
        before=copy.deepcopy((rows,prov))
        result=apply_annual_production(rows,prov,[proposed_decision()],repo)
        self.assertEqual((rows,prov),before)
        self.assertEqual({f['value'] for f in result['fills']},{'3645','3041'})
        dated=next(f for f in result['fills'] if f['value']=='3645')
        self.assertIn('STAGE_SOURCE_DATED',dated['qualifier'])
        self.assertIn('Exploration Target',dated['scope'])
        self.assertEqual(len(result['document_inventory']),24)
        self.assertTrue(all(d['sha256_verified'] for d in result['document_inventory']))
        self.assertTrue(any(r['reason']=='MULTIPLE_STAGE_ANNUAL_OUTPUTS_REQUIRE_RESEARCHER_SELECTION' for r in result['reviews']))
        self.assertEqual(apply_annual_production(rows,prov,[],repo)['fills'],[])
        for row in rows:
            if row['專案ID'] in targets:row[COLUMNS[0]]='999'
        self.assertEqual(apply_annual_production(rows,prov,[proposed_decision()],repo)['fills'],[])


if __name__=='__main__':
    unittest.main()
