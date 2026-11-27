"""Fail-closed checks on the last boundary before canonical resource facts."""

from contextlib import closing
from dataclasses import replace
import json
from pathlib import Path
import unittest

from au_ree_v2.evidence import resource_values
from au_ree_v2.formal_resource_admission import _evaluate, _insert_bundle
from au_ree_v2.observation_schema import EvidenceAnchor, ObservationContext, RawObservation, TextSpan
from au_ree_v2.observation_semantics import SemanticEngine
from au_ree_v2.resource_jorc import VERSION as JORC_VERSION
from au_ree_v2.store import canonical, connect, entity


ROOT = Path(__file__).resolve().parents[1]
SOURCE = dict(sha256='a' * 64, key='synthetic', kind='pdf', url='https://example.invalid/synthetic.pdf',
              path='test-only.pdf', publication_date='2025-02-01', available_date='2025-02-01',
              acquired_at='2025-02-01T00:00:00+00:00')


def observation(project, quantity, column, token, unit, header):
    origin = dict(sha256=SOURCE['sha256'], source_id=SOURCE['key'], page=1, table=0)
    left = column * 20
    value = EvidenceAnchor(**origin, row=2, column=column, quote=token, bbox=(left, 40, left + 20, 60),
                           text_span=TextSpan('QUOTE', 'MUPDF_NATIVE_TABLE_CELL', 0, len(token)), role='token')
    unit_anchor = EvidenceAnchor(**origin, row=0, column=column, quote=header, role='unit',
                                 bbox=(left, 0, left + 20, 20))
    quote = 'Table 2: Synthetic project Total JORC Mineral Resource as at 2025-01-01 at 500 ppm TREO cut-off'
    scope = EvidenceAnchor(**origin, quote=quote, role='scope',
                           bbox=(0, 0, 40, 2))
    compliance = replace(scope, role='jorc_target', locator='SCOPE_CAPTION',
                         text_span=TextSpan('QUOTE', 'MUPDF_NATIVE_TEXT_BLOCK', 0, len(quote)))
    label = EvidenceAnchor(**origin, row=2, column=0, quote='Total', role='row', bbox=(0, 40, 20, 60))
    context = ObservationContext(conditions=(('category', 'MEASURED_INDICATED_INFERRED_TOTAL'),
                                             ('reporting_standard', 'JORC'), ('scope_coverage', 'PROJECT_TOTAL'),
                                             ('jorc_status', 'AFFIRMED'), ('jorc_rule_version', JORC_VERSION),
                                             ('reported_table_label', '2'),
                                             ('resource_type', 'MINERAL_RESOURCE'), ('cutoff_grade', '500 ppm TREO')))
    return RawObservation(quantity, project, quantity, 'RESOURCE', replace(value, role=None), 'synthetic-parser',
                          original_value=token, original_unit=unit, scope_id='Synthetic project deposit',
                          material_basis='RESOURCE_BULK_ORE', chemical_basis='TREO',
                          denominator_basis='RESOURCE_BULK_ORE_MASS', context=context,
                          effective_date='2025-01-01', publication_date=SOURCE['publication_date'],
                          acquisition_date=SOURCE['acquired_at'], statement_id='new-extracted-statement',
                          estimate_id='same-estimate', source_value_state='NUMBER',
                          evidence_anchors=(value, unit_anchor, scope, label, compliance))


class CanonicalResourceBindings(unittest.TestCase):
    def setUp(self):
        self.engine = SemanticEngine(ROOT)
        self.project = 'AU-test-fixture'

    def bundle(self):
        return (observation(self.project, 'ore_mt', 1, '7.3', 'Mt', 'Dry ore tonnage (Mt)'),
                observation(self.project, 'grade', 2, '0.96', '%', 'TREO (%)'),
                observation(self.project, 'contained_treo_kt', 3, '70,500', 't', 'Contained TREO (t)'))

    def evaluate(self, raws):
        return _evaluate({'observations': raws, 'physical_page': 1, 'table': 0, 'row': 2}, SOURCE,
                         {self.project}, '2025-02-02', self.engine)

    def persist_legacy_pair(self, db, *, mass=7.3):
        self.project = entity(db, 'fixture', 'synthetic', 'PROJECT')
        db.execute('INSERT INTO sources VALUES(?,?,?,?,?,?,?,?)',
                   (SOURCE['sha256'], SOURCE['key'], SOURCE['url'], SOURCE['publication_date'],
                    SOURCE['acquired_at'], SOURCE['path'], SOURCE['kind'], canonical(SOURCE)))
        raw = {'source_key': SOURCE['key'], 'pdf_page': 1, 'cutoff_grade': '0.05% TREO',
               'resource_type': 'MINERAL_RESOURCE', 'reporting_standard': 'JORC', 'scope_coverage': 'PROJECT_TOTAL',
               'material_basis': 'RESOURCE_BULK_ORE', 'composition_denominator_basis': 'RESOURCE_BULK_ORE_MASS'}
        for quantity, unit, value, identifier in (('ore_mt', 'Mt', mass, 'immutable-old-ore'),
                                                   ('grade', '%', 0.96, 'immutable-old-grade')):
            db.execute('INSERT INTO observations VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                       (identifier, self.project, quantity, value, unit, 'TREO', 'Synthetic project deposit',
                        'historical statement', 'MEASURED_INDICATED_INFERRED_TOTAL', '2025-01-01',
                        SOURCE['sha256'], 'physical PDF page 1 Table 2', 'AUTO_VALIDATED', '[]', canonical(raw),
                        'normalization-v1'))
        return {'immutable-old-ore', 'immutable-old-grade'}

    def test_boundary_rejects_wrong_token_header_row_statement_date_and_basis(self):
        ore, grade, contained = self.bundle()
        token, header, scope, label, compliance = grade.evidence_anchors
        cases = (
            (replace(grade, original_value='0.97'), 'NUMERIC_EVIDENCE_BINDING_MISMATCH'),
            (replace(grade, evidence_anchors=(token, replace(header, quote='TREO (ppm)'), scope, label, compliance)),
             'NUMERIC_EVIDENCE_BINDING_MISMATCH'),
            (replace(grade, evidence_anchors=(token, replace(header, column=0), scope, label, compliance)),
             'UNIT_HEADER_SOURCE_OR_COLUMN_MISMATCH'),
            (replace(grade, evidence=replace(grade.evidence, row=1)), 'VALUE_SOURCE_OR_ROW_MISMATCH'),
            (replace(grade, statement_id='different-statement'), 'CROSS_PROJECT_SCOPE_STATEMENT_EDITION_OR_BASIS'),
            (replace(grade, project_id='AU-other-fixture'), 'CROSS_PROJECT_SCOPE_STATEMENT_EDITION_OR_BASIS'),
            (replace(grade, effective_date='2025-01-02'), 'CROSS_PROJECT_SCOPE_STATEMENT_EDITION_OR_BASIS'),
            (replace(grade, chemical_basis='REO'), 'CROSS_PROJECT_SCOPE_STATEMENT_EDITION_OR_BASIS'),
        )
        for bad, reason in cases:
            with self.subTest(reason=reason):
                result, facts, _ = self.evaluate((ore, bad, contained))
                self.assertIsNone(facts)
                self.assertIn(reason, result['reasons'])

    def test_no_scalar_promotion_and_no_inconsistent_contained(self):
        ore, grade, contained = self.bundle()
        bound = observation(self.project, 'grade', 2, '<0.96', '%', 'TREO (%)')
        result, facts, _ = self.evaluate((ore, replace(bound, source_value_state='BOUND'), contained))
        self.assertIsNone(facts)
        self.assertIn('RESOURCE_VALUE_NOT_SCALAR', result['reasons'])
        fabricated = observation(self.project, 'contained_treo_kt', 3, '970,000', 't', 'Contained TREO (t)')
        result, facts, _ = self.evaluate((ore, grade, fabricated))
        self.assertIsNone(facts)
        self.assertIn('REPORTED_CONTAINED_CONFLICT', result['reasons'])

    def test_an_internally_matching_but_unwitnessed_date_does_not_pass(self):
        raws = tuple(replace(raw, effective_date='2025-01-02') for raw in self.bundle())
        result, facts, _ = self.evaluate(raws)
        self.assertIsNone(facts)
        self.assertIn('RESOURCE_EFFECTIVE_DATE_EVIDENCE_MISMATCH', result['reasons'])

    def test_an_internally_matching_but_unwitnessed_cutoff_does_not_pass(self):
        raws = tuple(replace(raw, context=replace(raw.context, conditions=tuple(
            (key, '1,000 ppm TREO' if key == 'cutoff_grade' else value) for key, value in raw.context.conditions)))
                     for raw in self.bundle())
        result, facts, _ = self.evaluate(raws)
        self.assertIsNone(facts)
        self.assertIn('RESOURCE_CUTOFF_EVIDENCE_MISMATCH', result['reasons'])

    def test_exact_historical_edition_keeps_ids_and_adds_only_contained(self):
        with closing(connect(':memory:')) as db:
            historical_ids = self.persist_legacy_pair(db)
            raws = self.bundle()
            result, facts, _ = self.evaluate(raws)
            self.assertEqual(result['status'], 'CANONICAL_ELIGIBLE', result['reasons'])
            rows, historical = _insert_bundle(db, ROOT, SOURCE, facts, raws, historical_ids)
            self.assertEqual({identity for identity, added in rows if not added}, historical_ids)
            self.assertEqual(historical['statement_id'], 'historical statement')
            self.assertEqual(sum(added for _, added in rows), 1)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM observations').fetchone()[0], 3)
            record = db.execute("SELECT * FROM observations WHERE variable='contained_treo_kt'").fetchone()
            self.assertEqual(record['value'], 70.5)
            self.assertEqual(record['scope'], 'Synthetic project deposit')
            self.assertEqual(set(json.loads(record['raw'])['resource_identity_link']['canonical_observation_ids'].values()),
                             historical_ids)
            rerun, _ = _insert_bundle(db, ROOT, SOURCE, facts, raws, historical_ids)
            self.assertEqual([identity for identity, _ in rows], [identity for identity, _ in rerun])
            self.assertFalse(any(added for _, added in rerun))

    def test_equivalent_estimate_with_competing_mass_keeps_both_qualified_sides(self):
        with closing(connect(':memory:')) as db:
            historical_ids = self.persist_legacy_pair(db, mass=8.3)
            raws = self.bundle()
            result, facts, _ = self.evaluate(raws)
            self.assertEqual(result['status'], 'CANONICAL_ELIGIBLE')
            rows, historical = _insert_bundle(db, ROOT, SOURCE, facts, raws, historical_ids)
            active = {identifier for identifier, added in rows if added}
            self.assertEqual(len(active), 3)
            self.assertEqual(historical['conflict']['reason'], 'CONCURRENT_SAME_ESTIMATE_VALUES')
            decisions = []
            values = resource_values(db, '2025-02-02', {SOURCE['sha256']}, strict=True,
                                     active_claim_ids=historical_ids, scope_audit=decisions, admitted_resource_ids=active)
            self.assertNotIn(self.project, values)
            self.assertTrue(any(row['reason'] == 'CONCURRENT_SOURCE_CONFLICT' and
                                set(json.loads(row['observation_ids'])) == historical_ids | active
                                for row in decisions), decisions)


if __name__ == '__main__':
    unittest.main()
