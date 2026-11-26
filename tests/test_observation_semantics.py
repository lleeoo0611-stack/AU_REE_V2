import unittest
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

from au_ree_v2.observation_schema import EvidenceAnchor, ObservationContext, RawObservation, ValidatedObservation
from au_ree_v2.observation_semantics import RESOURCE_PROFILE, SemanticEngine


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
            with self.assertRaisesRegex(ValueError, "bind the original"):
                self.engine.assess(self.grade, self.decision, evidence_status="VERIFIED", supporting_evidence=(anchor,))
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
        numeric = replace(self.anchor, role="NUMERIC_VALUE", bbox=(10, 20, 30, 40), offset=5)
        raw = replace(self.grade, evidence=numeric)
        context = EvidenceAnchor("report", numeric.sha256, page=7, quote="Pilot leaching context", role="TEST_SCALE")
        norm = self.engine.normalize(raw)
        valid = self.engine.assess(raw, self.decision, normalized=norm, evidence_status="VERIFIED",
                                   supporting_evidence=(numeric, context))
        self.assertEqual(valid.evidence_status, "VERIFIED")
        self.assertIn(context, valid.supporting_evidence)
        for wrong in (replace(numeric, row=5), replace(numeric, column=4), replace(numeric, offset=6),
                      replace(numeric, bbox=(40, 40, 60, 60)), replace(numeric, quote="18,300.5 ppm TREO")):
            with self.subTest(wrong=wrong), self.assertRaisesRegex(ValueError, "BINDING_MISMATCH"):
                self.engine.assess(raw, self.decision, evidence_status="VERIFIED",
                                   supporting_evidence=(numeric, wrong, context))
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
