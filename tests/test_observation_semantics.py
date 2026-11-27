import unittest
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

from au_ree_v2.observation_schema import EvidenceAnchor, ObservationContext, RawObservation, TextSpan, ValidatedObservation
from au_ree_v2.observation_semantics import RESOURCE_PROFILE, SemanticEngine
from au_ree_v2.numeric_evidence import numeric_token_spans, scalar_decimal


ROOT = Path(__file__).resolve().parents[1]


class ObservationSemanticsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = SemanticEngine(ROOT)
        cls.anchor = EvidenceAnchor("report", "a" * 64, page=5, table=1, row=4, column=2, quote="18,300 ppm TREO")
        cls.grade = RawObservation("historical-grade", "project", "grade", "RESOURCE", cls.anchor,
                                   "extractor-v1", "18,300", "ppm", scope_id="zone-a", chemical_basis="TREO",
                                   material_basis="Whole ore", denominator_basis="Whole ore")
        cls.decision = {"status": "ACCEPT", "profile_id": "grade-use", "profile_version": "v1", "reason": "DECLARED_GATE"}

    def test_unit_conversion_keeps_original_and_distinguishes_normalizations(self):
        percent = self.engine.normalize(self.grade)
        ppm = self.engine.normalize(self.grade, target_unit="ppm")
        self.assertEqual((Decimal("1.83"), "%"), (percent.value, percent.unit))
        self.assertEqual((Decimal("18300"), "ppm"), (ppm.value, ppm.unit))
        self.assertEqual(percent.raw_id, ppm.raw_id)
        self.assertNotEqual(percent.version, ppm.version)
        self.assertIn("0.0001", percent.formula)
        self.assertIn("denominator_basis=WHOLE_ORE", percent.conditions)
        self.assertEqual(self.grade.original_value, "18,300")

    def test_gallium_mass_fractions_round_trip_without_changing_source_context(self):
        for unit in ("g/t", "mg/kg"):
            with self.subTest(unit=unit):
                anchor = replace(self.anchor, quote=f"70 {unit} Ga₂O₃")
                raw = replace(self.grade, chemical_basis="Ga₂O₃", original_value="70", original_unit=unit,
                              evidence=anchor)
                ppm = self.engine.normalize(raw, target_unit="ppm")
                self.assertEqual((ppm.value, ppm.unit, ppm.chemical_basis), (Decimal("70"), "ppm", "Ga2O3"))
                self.assertEqual(ppm.raw_fingerprint, raw.normalization_fingerprint)
                self.assertIn("same-denominator mass fraction", ppm.formula)
                self.assertIn("material_basis=WHOLE_ORE", ppm.conditions)
                self.assertEqual((raw.original_value, raw.original_unit, raw.evidence.quote),
                                 ("70", unit, f"70 {unit} Ga₂O₃"))
                inverse = self.engine.normalize(replace(raw, original_unit="ppm"), target_unit=unit)
                self.assertEqual((inverse.value, inverse.unit, inverse.chemical_basis), (Decimal("70"), unit, "Ga2O3"))
                for change in ({"original_unit": "mg/L"}, {"denominator_basis": "volume"},
                               {"denominator_basis": "Concentrate"}, {"chemical_basis": "UNKNOWN"}):
                    self.assertIsNone(self.engine.normalize(replace(raw, **change), target_unit="ppm"))
                self.assertIsNone(self.engine.normalize(raw, target_unit="ppm", target_species="Ga"))
        volumetric = replace(self.grade, denominator_basis="volume")
        self.assertIsNone(self.engine.normalize(volumetric, target_unit="%"))

    def test_invalid_or_unbound_resource_tokens_stay_raw(self):
        for change in ({"scope_id": None}, {"chemical_basis": "NdPr"}, {"material_basis": None},
                       {"denominator_basis": None}, {"source_value_state": "CONFLICT"},
                       {"original_value": "13-18"}, {"original_value": "<13"}, {"original_value": "1000001"}):
            with self.subTest(change=change):
                self.assertIsNone(self.engine.normalize(replace(self.grade, **change)))

    def test_stoichiometry_uses_preserved_material_mass_and_explicit_species(self):
        element = replace(self.grade, variable="reported_pr_ppm", quantity_kind="STRATEGIC_COMPOSITION",
                          chemical_basis="Praseodymium", original_value="100")
        oxide = self.engine.normalize(element, target_species="Pr₆O₁₁")
        self.assertEqual(oxide.chemical_basis, "Pr6O11")
        self.assertAlmostEqual(float(oxide.value), 120.81606438243, places=8)
        self.assertIn("atomic weight 140.908", oxide.formula)
        self.assertIsNone(self.engine.normalize(element, target_species="Nd2O3"))
        self.assertIsNone(self.engine.normalize(element, target_species="Pr7O24"))
        for denominator in (None, "TREO", "Concentrate"):
            with self.subTest(denominator=denominator):
                self.assertIsNone(self.engine.normalize(replace(element, denominator_basis=denominator), target_species="Pr6O11"))

    def test_ontology_preserves_resource_type_stage_scale_and_recovery_ambiguity(self):
        raw = replace(self.grade, context=ObservationContext(process="Leaching", scale="Pilot scale",
                      conditions=(("resource_kind", "Exploration Target"), ("measurement_role", "Engineering design"))))
        mapped = self.engine.map_observation(raw)
        self.assertEqual(mapped["context"]["resource_kind"], "EXPLORATION_TARGET")
        self.assertEqual(mapped["context"]["process"], "LEACHING")
        self.assertEqual(mapped["context"]["scale"], "PILOT")
        self.assertEqual(mapped["context"]["measurement_role"], "ENGINEERING_DESIGN")
        mapping = self.engine.vocabulary["crosswalk"]
        self.assertIn("JORC", mapping)
        self.assertIn("EarthResourceML", mapping)
        self.assertEqual(mapping["QUDT"]["units"]["ppm"], "unit:PPM")
        unresolved = self.engine.map_observation(replace(raw, chemical_basis="NdPr"))
        self.assertIsNone(unresolved["context"]["chemical_basis"])
        self.assertEqual(unresolved["unresolved_mappings"][0]["relation"], "closeMatch")

    def test_assessment_separates_verification_and_comparison(self):
        normalized = self.engine.normalize(self.grade)
        unchecked = self.engine.assess(self.grade, self.decision, normalized=normalized)
        self.assertEqual(("UNVERIFIED", "COMPARABLE"), (unchecked.evidence_status, unchecked.comparability))
        with self.assertRaises(ValueError):
            ValidatedObservation(normalized, unchecked)
        for anchor in (replace(self.anchor, sha256="b" * 64), replace(self.anchor, page=6)):
            conflict = self.engine.assess(self.grade, self.decision, evidence_status="VERIFIED",
                                          supporting_evidence=(anchor,))
            self.assertEqual((conflict.evidence_status, conflict.comparability), ("CONFLICT", "NOT_COMPARABLE"))
        checked = self.engine.assess(self.grade, self.decision, normalized=normalized, evidence_status="VERIFIED",
                                     supporting_evidence=(self.anchor,), expected_context={"unit": "%", "chemical_basis": "TREO"})
        self.assertEqual(checked.comparability, "COMPARABLE")
        self.assertEqual(ValidatedObservation(normalized, checked).assessment, checked)
        limited = self.engine.assess(self.grade, self.decision, expected_context={"sample": "sample-a"})
        self.assertEqual((limited.comparability, limited.missing_context), ("INSUFFICIENT_CONTEXT", ("sample",)))
        incompatible = self.engine.assess(self.grade, self.decision, expected_context={"chemical_basis": "REE"})
        self.assertEqual(incompatible.comparability, "NOT_COMPARABLE")
        self.assertNotEqual(incompatible.rule_version, limited.rule_version)
        blocked = self.engine.assess(self.grade, {**self.decision, "status": "SOURCE_BLOCKED"},
                                     evidence_status="VERIFIED", supporting_evidence=(self.anchor,))
        self.assertEqual(blocked.evidence_status, "SOURCE_BLOCKED")

    def test_profile_requirements_downgrade_legacy_admission_for_missing_scientific_context(self):
        decision = {**self.decision, "profile_id": RESOURCE_PROFILE}
        raw = replace(self.grade, statement_id="mre-1", effective_date="2024-08",
                      context=ObservationContext(conditions=(("category", "Inferred"),)))
        self.assertEqual(self.engine.assess(raw, decision, apply_profile=True).comparability, "COMPARABLE")
        incomplete = self.engine.assess(replace(raw, chemical_basis="NdPr"), decision, apply_profile=True)
        self.assertEqual((incomplete.comparability, incomplete.missing_context), ("INSUFFICIENT_CONTEXT", ("chemical_basis",)))

    def test_verification_distinguishes_numeric_location_from_context(self):
        numeric = replace(self.anchor, role="NUMERIC_VALUE", bbox=(10, 20, 30, 40), offset=0,
                          text_span=TextSpan("QUOTE", "FIXTURE", 0, 6))
        raw = replace(self.grade, evidence=numeric)
        context = EvidenceAnchor("report", numeric.sha256, page=7, quote="Pilot leaching context", role="TEST_SCALE")
        norm = self.engine.normalize(raw)
        valid = self.engine.assess(raw, self.decision, normalized=norm, evidence_status="VERIFIED",
                                   supporting_evidence=(numeric, context))
        self.assertEqual(valid.evidence_status, "VERIFIED")
        self.assertIn(context, valid.supporting_evidence)
        for wrong in (replace(numeric, row=5), replace(numeric, column=4), replace(numeric, offset=6),
                      replace(numeric, bbox=(40, 40, 60, 60)), replace(numeric, quote="18,300.5 ppm TREO")):
            with self.subTest(wrong=wrong):
                conflict = self.engine.assess(raw, self.decision, evidence_status="VERIFIED",
                                              supporting_evidence=(numeric, wrong, context))
                self.assertEqual(conflict.evidence_status, "CONFLICT")
                self.assertIn("BINDING_MISMATCH", conflict.reason)
        for missing in ((), (context,), (replace(numeric, sha256=None),),
                        (replace(numeric, offset=None),),
                        (replace(numeric, table=None, row=None, column=None, bbox=None, offset=None),)):
            with self.subTest(missing=missing):
                pending = self.engine.assess(raw, self.decision, evidence_status="VERIFIED",
                                             supporting_evidence=missing)
                self.assertEqual(pending.evidence_status, "UNVERIFIED")
                self.assertIn("NUMERIC_EVIDENCE_LOCATION_INSUFFICIENT", pending.reason)
                self.assertIn("numeric_evidence_location", pending.missing_context)
        with self.assertRaisesRegex(ValueError, "observation contents"):
            self.engine.assess(replace(raw, original_value="2"), self.decision, normalized=norm)

    def test_complete_numeric_tokens_reject_chemistry_exponents_and_wrong_spans(self):
        for quote, value in (("Nd2O3", "2"), ("Nd₂O₃", "2"), ("1e1000", "1000"), ("5 × 10^1000", "1000"),
                             ("Grade <70 ppm", "70"),
                             ("70–90 ppm", "70"), ("2026-11-06", "2026"), ("Table 3", "3")):
            with self.subTest(quote=quote, value=value):
                self.assertEqual(numeric_token_spans(quote, value, "ppm"), ())
                anchor = replace(self.anchor, quote=quote)
                raw = replace(self.grade, evidence=anchor, original_value=value)
                verdict = self.engine.assess(raw, self.decision, evidence_status="VERIFIED",
                                             supporting_evidence=(anchor,))
                self.assertEqual(verdict.evidence_status, "CONFLICT")
        quote = "Measured 90% and 70%."
        span = TextSpan("BLOCK", "FIXTURE_SOURCE_BLOCK", 46, 49, quote_start=37)
        anchor = replace(self.anchor, quote=quote, offset=46, text_span=span)
        raw = replace(self.grade, evidence=anchor, original_value="70%", original_unit="%")
        verdict = self.engine.assess(raw, self.decision, evidence_status="VERIFIED",
                                     supporting_evidence=(anchor,))
        self.assertEqual(verdict.evidence_status, "CONFLICT")
        legacy = replace(anchor, text_span=None)
        pending = self.engine.assess(replace(raw, evidence=legacy), self.decision, evidence_status="VERIFIED",
                                      supporting_evidence=(legacy,))
        self.assertEqual(pending.evidence_status, "UNVERIFIED")
        right = replace(anchor, offset=54, text_span=TextSpan("BLOCK", "FIXTURE_SOURCE_BLOCK", 54, 57, quote_start=37))
        verdict = self.engine.assess(replace(raw, evidence=right), self.decision, evidence_status="VERIFIED",
                                     supporting_evidence=(right,))
        self.assertEqual(verdict.evidence_status, "VERIFIED")
        contradictory = replace(right, offset=46)
        verdict = self.engine.assess(replace(raw, evidence=contradictory), self.decision,
                                     evidence_status="VERIFIED", supporting_evidence=(contradictory,))
        self.assertEqual(verdict.evidence_status, "CONFLICT")

    def test_printed_signed_decimal_and_units_preserve_scientific_dispositions(self):
        for token, unit, value in (("−.5%", "%", "-0.5"), ("+1,000 ppm", "ppm", "1000"),
                                   ("3.5e−2 ppm", "ppm", "0.035"), ("1\u202f000 ppm", "ppm", "1000"),
                                   ("3.5 × 10⁻² ppm", "ppm", "0.035"),
                                   ("0", "%", "0")):
            with self.subTest(token=token, unit=unit):
                self.assertEqual(scalar_decimal(token, unit), Decimal(value))
        self.assertEqual(numeric_token_spans("Measured 70 ppm", "70%", "%"), ())
        self.assertEqual(numeric_token_spans("Measured 70Mt", "70", "kt"), ())
        self.assertEqual(numeric_token_spans("grade<70 ppm", "70", "ppm"), ())
        for token, state in (("≤0.1 ppm", "BOUND"), ("70–90%", "RANGE")):
            with self.subTest(token=token):
                anchor = replace(self.anchor, quote=token)
                raw = replace(self.grade, original_value=token, original_unit="%" if "%" in token else "ppm",
                              evidence=anchor, source_value_state=state)
                verdict = self.engine.assess(raw, self.decision, evidence_status="VERIFIED",
                                             supporting_evidence=(anchor,))
                self.assertEqual(verdict.evidence_status, "VERIFIED")
                self.assertIsNone(self.engine.normalize(raw))

    def test_explicit_unit_header_binds_the_same_table_column(self):
        number = replace(self.anchor, quote="18,300")
        unit = replace(number, quote="Tonnes (Mt)", role="unit")
        wrong_column = replace(unit, column=number.column + 1)
        raw = replace(self.grade, evidence=number, evidence_anchors=(number, unit))
        verdict = self.engine.assess(raw, self.decision, evidence_status="VERIFIED",
                                     supporting_evidence=(number,))
        self.assertEqual(verdict.evidence_status, "CONFLICT")
        accepted = self.engine.assess(replace(raw, evidence_anchors=(number, wrong_column)), self.decision,
                                      evidence_status="VERIFIED", supporting_evidence=(number,))
        self.assertEqual(accepted.evidence_status, "VERIFIED")
