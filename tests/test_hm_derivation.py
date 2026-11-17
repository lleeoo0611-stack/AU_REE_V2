"""Offline native-cell HM derivation and the two approved oxide conversions."""
import copy
import json
import subprocess
import tempfile
import types
import unittest
from decimal import Decimal
from pathlib import Path
import pymupdf
from au_ree_v2.census import summary_hm_percent, summary_partial_contract
from au_ree_v2.census import summary_resource_fields, summary_settings

ROOT = Path(__file__).resolve().parents[1]


class HMSourceContracts(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.pdf = Path(self.temp.name)/'native.pdf'
        doc = pymupdf.open()
        page = doc.new_page()
        page.insert_text((40, 40), 'Project resource estimate')
        page.insert_text((40, 60), 'Total HM oxide table')
        for x, token in ((50, '620'), (120, 'Mt'), (200, '2.2'), (250, '%'),
                         (350, '13.64'), (420, 'Mt')):
            page.insert_text((x, 100), token)
        doc.save(self.pdf)
        doc.close()
        self.evidence = dict(page=1, markers=['Project resource estimate', 'Total HM oxide table'])
        def cell(value, unit, x, ux):
            return dict(value=value, unit=unit, original_token=str(value),
                        evidence=copy.deepcopy(self.evidence),
                        cell_binding=dict(page=1, row_bbox=[40, 85, 460, 104],
                                          column_bbox=[x-2, 80, x+45, 110],
                                          unit_bbox=[ux-2, 85, ux+25, 104]))
        self.ore = cell(620, 'Mt', 50, 120)
        self.grade = cell(2.2, '%', 200, 250)
        self.native_hm = cell(13.64, 'Mt', 350, 420)
        self.spec = dict(mode='BULK_ORE_AND_HM_HOSTED_OXIDES_ONLY',
                         mass_inputs=dict(ore_mt=self.ore, hm_mass_mt=dict(
                             value=13.64, unit='Mt', derivation='ORE_MT_X_HM_GRADE_PERCENT',
                             inputs=dict(ore_mt=copy.deepcopy(self.ore), hm_grade_percent=self.grade))))
        for name in ('denominator_proof', 'mass_cutoff_proof', 'oxide_cutoff_proof'):
            self.spec[name] = dict(evidence=copy.deepcopy(self.evidence))
        self.source = dict(resolved_path=str(self.pdf))

    def observations(self, spec=None, conversion=True):
        spec = spec or self.spec
        review = dict(source_sha256='a'*64, statement_id='hm', scope='Total HM',
                      effective_date='2024-12-03', partial_resource_projection=spec)
        rows = [dict(variable='ore_mt', value=620, unit='Mt', basis='TREO',
                     raw=json.dumps(dict(review_contract=review)))]
        bases = ('La2O3', 'CeO2', 'Pr6O11', 'Nd2O3', 'Sm2O3', 'Eu2O3', 'Gd2O3',
                 'Tb4O7', 'Dy2O3', 'Ho2O3', 'Er2O3', 'Tm2O3', 'Yb2O3', 'Lu2O3', 'Y2O3')
        for basis in bases:
            raw = dict(original_token='0.1', original_unit='%HM', review_contract=review,
                       normalization='REPORTED_HM_MASS_X_OXIDE_PERCENT_DIVIDED_BY_BULK_ORE')
            if conversion and basis in ('Pr6O11', 'Tb4O7'):
                raw['species_conversion'] = dict(
                    source_species='Pr2O3' if basis == 'Pr6O11' else 'Tb2O3',
                    target_species=basis, method='STOICHIOMETRIC_STANDARD_ATOMIC_WEIGHTS')
            pct = summary_hm_percent(raw, basis)
            ppm = Decimal('13.64')*pct*10/Decimal('620')/Decimal('.001')
            rows.append(dict(variable='reported_oxide_ppm', value=float(ppm), unit='ppm',
                             basis=basis, raw=json.dumps(raw)))
        return rows

    def check_contract(self, spec=None):
        return summary_partial_contract(self.observations(spec), self.source)

    def test_correct_two_cell_derivation_and_both_species_pass(self):
        self.assertTrue(self.check_contract()['basis_proof_verified'])

    def test_wrong_derived_value_is_rejected(self):
        self.spec['mass_inputs']['hm_mass_mt']['value'] = 13.65
        with self.assertRaisesRegex(ValueError, 'HM_DERIVED_MASS_MISMATCH'):
            self.check_contract()

    def test_either_wrong_native_region_is_rejected(self):
        for name in ('ore_mt', 'hm_grade_percent'):
            spec = copy.deepcopy(self.spec)
            spec['mass_inputs']['hm_mass_mt']['inputs'][name]['cell_binding']['column_bbox'] = [500, 80, 540, 110]
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'HM_DERIVED_INPUT_CELL_MISMATCH'):
                self.check_contract(spec)

    def test_ore_input_must_agree_with_contract_ore(self):
        self.spec['mass_inputs']['ore_mt']['value'] = 621
        with self.assertRaisesRegex(ValueError, 'HM_DERIVED_MASS_MISMATCH'):
            self.check_contract()

    def test_wrong_declared_or_native_unit_is_rejected(self):
        for change in ('declaration', 'native'):
            spec = copy.deepcopy(self.spec)
            grade = spec['mass_inputs']['hm_mass_mt']['inputs']['hm_grade_percent']
            if change == 'declaration':
                grade['unit'] = 'Mt'
            else:
                grade['cell_binding']['unit_bbox'] = self.ore['cell_binding']['unit_bbox']
            with self.subTest(change=change), self.assertRaisesRegex(ValueError, 'HM_DERIVED_INPUT_UNIT_OR_MARKERS'):
                self.check_contract(spec)

    def test_two_markers_are_required_for_each_derived_input(self):
        self.grade['evidence']['markers'] = ['Project resource estimate']
        with self.assertRaisesRegex(ValueError, 'HM_DERIVED_INPUT_UNIT_OR_MARKERS'):
            self.check_contract()

    def test_unsupported_mass_derivation_is_rejected(self):
        self.spec['mass_inputs']['hm_mass_mt']['derivation'] = 'UNREVIEWED_FORMULA'
        with self.assertRaisesRegex(ValueError, 'HM_MASS_DERIVATION_UNSUPPORTED'):
            self.check_contract()

    def test_atomic_weight_factors_match_full_precision_values(self):
        expected = {'Pr6O11': ('Pr2O3', '1.032339537859332409577548490'),
                    'Tb4O7': ('Tb2O3', '1.021865697955702793790846993')}
        for target, (source, factor) in expected.items():
            raw = dict(original_token='1', species_conversion=dict(
                source_species=source, target_species=target,
                method='STOICHIOMETRIC_STANDARD_ATOMIC_WEIGHTS', factor=factor))
            self.assertEqual(summary_hm_percent(raw, target), Decimal(factor))

    def test_four_decimal_factors_are_rejected(self):
        for source, target, factor in (('Pr2O3', 'Pr6O11', '1.0323'), ('Tb2O3', 'Tb4O7', '1.0219')):
            raw = dict(original_token='0.1', species_conversion=dict(
                source_species=source, target_species=target,
                method='STOICHIOMETRIC_STANDARD_ATOMIC_WEIGHTS', factor=factor))
            with self.subTest(target=target), self.assertRaisesRegex(ValueError, 'HM_SPECIES_FACTOR_MISMATCH'):
                summary_hm_percent(raw, target)

    def test_unsupported_species_and_wrong_target_are_rejected(self):
        for source, target, declared in (('Ce2O3', 'CeO2', 'CeO2'), ('Pr2O3', 'Pr6O11', 'Tb4O7')):
            raw = dict(original_token='0.1', species_conversion=dict(
                source_species=source, target_species=declared,
                method='STOICHIOMETRIC_STANDARD_ATOMIC_WEIGHTS'))
            with self.subTest(source=source), self.assertRaisesRegex(ValueError, 'HM_SPECIES_CONVERSION_UNSUPPORTED'):
                summary_hm_percent(raw, target)

    def test_mass_transform_mismatch_is_not_adjusted(self):
        rows = self.observations()
        rows[4]['value'] += 1
        before = copy.deepcopy(rows)
        with self.assertRaisesRegex(ValueError, 'HM_SOURCE_MASS_TRANSFORM_MISMATCH'):
            summary_partial_contract(rows, self.source)
        self.assertEqual(rows, before)

    def test_native_mass_and_unconverted_tokens_still_pass_unchanged(self):
        spec = copy.deepcopy(self.spec)
        spec['mass_inputs']['hm_mass_mt'] = copy.deepcopy(self.native_hm)
        rows = self.observations(spec, conversion=False)
        before = copy.deepcopy(rows)
        self.assertTrue(summary_partial_contract(rows, self.source)['basis_proof_verified'])
        self.assertEqual(rows, before)
        self.assertEqual(summary_hm_percent(dict(original_token='0.070'), 'Gd2O3'), Decimal('0.070'))

    def compare_legacy_output(self, spec, source):
        legacy = types.ModuleType('au_ree_v2._v7_legacy_census')
        legacy.__package__ = 'au_ree_v2'
        code = subprocess.check_output(['git', 'show', 'ac65aaf:src/au_ree_v2/census.py'], cwd=ROOT)
        exec(compile(code, 'ac65aaf/census.py', 'exec'), legacy.__dict__)
        observations = []
        for index, row in enumerate(self.observations(spec, conversion=False)):
            flat = json.loads(row['raw'])
            contract = flat.pop('review_contract')
            claim = dict(row, **flat, raw=dict(review_contract=contract))
            observations.append(dict(row, source_sha='a'*64, obs_id=str(index), scope='Total HM',
                                     statement_id='hm', effective_date='2024-12-03', locator='native p1',
                                     status='AUTO_VALIDATED', raw=json.dumps(claim)))
        rules, decisions = summary_settings(ROOT)
        columns = json.loads((ROOT/'config/project_summary_columns.json').read_text())
        outputs = []
        for function in (legacy.summary_resource_fields, summary_resource_fields):
            row = dict.fromkeys(columns, '')
            row['專案ID'] = 'offline-hm-regression'
            def put(column, value, *args):
                row[column] = value
            bundle, detail, reason = function(row, observations, {'a'*64: source}, rules, decisions, put)
            self.assertIsNotNone(bundle)
            outputs.append((row, detail, reason))
        self.assertEqual(outputs[0], outputs[1])

    def test_existing_native_hm_output_all_columns_matches_baseline(self):
        spec = copy.deepcopy(self.spec)
        spec['mass_inputs']['hm_mass_mt'] = copy.deepcopy(self.native_hm)
        self.compare_legacy_output(spec, dict(self.source, key='native', url='https://example.invalid/native.pdf'))

    def test_other_existing_partial_mode_output_matches_baseline(self):
        doc = pymupdf.open(self.pdf)
        doc[0].insert_text((50, 130), 'Cerium Ce2O3 1.171')
        doc[0].insert_text((50, 160), 'Ce2O3')
        other = self.pdf.with_name('other.pdf')
        doc.save(other)
        doc.close()
        spec = dict(mode='ORE_AND_COMPATIBLE_OXIDES_ONLY', source_species='Ce2O3',
                    basis_proof=dict(page=1, row_bbox=[48, 118, 250, 134], evidence=self.evidence),
                    resource_header=dict(page=1, bbox=[48, 148, 100, 164]))
        self.compare_legacy_output(spec, dict(key='other', url='https://example.invalid/other.pdf', resolved_path=str(other)))


if __name__ == '__main__':
    unittest.main()
