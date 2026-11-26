import copy
import json
from pathlib import Path
import unittest

from au_ree_v2.semantic_technical import (
    PROFILE, _program_text, _sample_reference, _technical_context,
    baseline_technical, extract_technical, narrative_mentions, technical_gate,
)


ROOT = Path(__file__).resolve().parents[1]
POLICY = json.loads((ROOT / "config/evidence_policy.json").read_bytes())


def _cell(**changes):
    row = {
        "evidence_id": "synthetic-cell", "project_id": "synthetic-project", "source_sha256": "a" * 64,
        "physical_page": 2, "table_index": 0, "row_index": 4, "column_index": 2,
        "bbox": [25., 35., 45., 55.], "table_caption": "Table 4 - Summary of Phase B Program Bottle Roll Results for HLC-West",
        "header_path": ["HLC-West Final Extraction (%)", "6 mm crush", "50g/L HCl"],
        "original_token": "75.0", "value": 75., "quantity": "extraction_pct", "unit": "%",
        "token_state": "NUMBER", "basis": "Nd", "scope": "Test-specific", "case_id": "test-a",
        "sample_id": "HLC-West", "sample_population": "HLC-West", "study_date": "2026-01-30",
        "scale": "BOTTLE_ROLL", "evidence_mode": "TESTWORK", "feed": "SOURCE_NAMED_COMPOSITE",
        "endpoint": "LEACH_SOLUTION", "grain_mm": 6., "source_column": 2, "acid_unit": "g/L",
    }
    return {**row, **changes}


PROCEDURE = """Phase B Program: intermittent bottle roll leach testing
Each test used a 1 kg aliquot over 28 days and a pulp density of 50 w/w% solids.
Elemental analysis of the leach solutions was performed using ICP-OES.
Starting initial hydrochloric acid concentration (20 and 50kg/t).
6.4.
HLC-West composite was analysed. The results are presented in Table 4 below."""
TABLE = """Table 4 - Summary of Phase B Program Bottle Roll Results for HLC-West
HLC-West Final Extraction (%)
6 mm crush
50g/L HCl"""


class TechnicalSemanticTests(unittest.TestCase):
    def test_complete_observation_links_sample_to_analytic_process_and_keeps_acid_units(self):
        row = _cell()
        old = baseline_technical([row])[0]
        new = _technical_context(old, [PROCEDURE, TABLE], row, {})
        self.assertEqual(new["status"], "SOURCE_VERIFIED_CANDIDATE")
        self.assertEqual(old["native"], new["native"])
        for key, expected in {"process_stage": "LEACH_EXTRACTION", "procedure_duration_days": 28,
                              "pulp_density_mass_pct": 50, "aliquot_mass_kg": 1, "acid_unit": "g/L",
                              "reagent_basis_warning": "PRINTED_G_L_AND_PROCEDURE_KG_T_NOT_RECONCILED"}.items():
            self.assertEqual(new["context"][key], expected)
        self.assertEqual(new["context"]["basis"], "Nd")
        self.assertIn(1, {a["physical_page"] for a in new["anchors"]})
        self.assertEqual(technical_gate(old, POLICY, "V0")["status"], "ACCEPT")
        self.assertEqual(technical_gate(new, POLICY, "V1")["status"], "ACCEPT")
        self.assertEqual(technical_gate(new, POLICY, "V1")["profile_id"], PROFILE)

    def test_reject_wrong_page_token_geometry_and_unit(self):
        row = _cell()
        r = baseline_technical([row])[0]
        for invalid in (None, dict(row, bbox=[0, 0, 20, 20]), dict(row, original_token="65.0"),
                        dict(row, unit="ppm"), dict(row, basis="Nd2O3"), dict(row, source_column=4)):
            out = _technical_context(r, [PROCEDURE, TABLE], invalid, {})
            self.assertEqual(out["status"], "BLOCKED")
        with self.subTest("missing immutable file"):
            out = extract_technical([row], ROOT / "tests")[0]
            self.assertEqual(out["evidence_reason"], "ORIGINAL_TECHNICAL_SOURCE_UNVERIFIED")

    def test_same_page_other_sample_and_uncertain_program_remain_unlinked(self):
        self.assertIsNone(_sample_reference([PROCEDURE], "HLC-East", "4"))
        self.assertIsNone(_sample_reference([PROCEDURE], "HLC-West", "40"))
        self.assertIsNone(_program_text([PROCEDURE, PROCEDURE], "Phase B Program"))
        row = _cell()
        r = baseline_technical([dict(row, sample_id="HLC-Central")])[0]
        self.assertEqual(_technical_context(r, [PROCEDURE, TABLE], row, {})["status"], "INSUFFICIENT")

    def test_reported_tech_percents_keep_claim_and_element_for_each_measure(self):
        text = ("The plant target is 90% TREO recovery, but the operating plant measured 80% TREO recovery. "
                "Tests reported 75% Nd extraction; Nd recovery did not reach 70%; "
                "assuming Nd recovery of 72%, the scenario applies.")
        mentions = narrative_mentions(text, "hash", 3)
        values = [(m["native"]["token"], m["basis"], m["claim_nature"]) for m in mentions]
        self.assertEqual(values, [("90%", "TREO", "TARGET"), ("80%", "TREO", "ACTUAL_OPERATING_RESULT"),
                                  ("75%", "Nd", "TESTWORK"), ("70%", "Nd", "NEGATED"),
                                  ("72%", "Nd", "CONDITIONAL")])
        for m in mentions:
            start, end = m["anchor"]["offset"]
            self.assertEqual(text[start:end], m["native"]["token"])
            span = m["anchor"]["text_span"]
            self.assertEqual((span["scope"], span["start"], span["end"]), ("PAGE", start, end))
            quote_offset = span["quote_start"]
            self.assertEqual(m["anchor"]["quote"][start - quote_offset:end - quote_offset],
                             m["native"]["token"])
        more = narrative_mentions("Bench tests measured an extraction of Nd2O3 at 74%; feed moisture was 8%.", "hash", 3)
        self.assertEqual([(m["basis"], m["native"]["value"]) for m in more], [("Nd2O3", 74.)])

    def test_missing_and_not_applicable_are_distinct(self):
        row = baseline_technical([_cell()])[0]
        missing = copy.deepcopy(row)
        missing["native"].update(value=None, bounds=[75., 80.], token_state="RANGE")
        missing["status"] = "INSUFFICIENT"
        self.assertEqual(technical_gate(missing, POLICY, "V1")["status"], "INSUFFICIENT")
        out_of_scope = baseline_technical([_cell(quantity="recovery_pct")])[0]
        self.assertEqual(technical_gate(out_of_scope, POLICY, "V0")["status"], "NOT_APPLICABLE")
