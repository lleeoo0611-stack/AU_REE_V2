"""Synthetic edge cases and compatibility checks for the research-only ablation."""
import json
import unittest
from decimal import Decimal

from tools import ontology_gain_compare as gain
from tools.normalization_comparison import _admit, diagnose_admission


class GainComparisonTests(unittest.TestCase):
    def setUp(self):
        self.rules = gain.load_rules()
        self.obs = dict(project_id="p", observation_id="direct", variable="ore_mt", source_sha256="sha",
                        physical_page="4", locator="PDF p4 Table 1 TOTAL", effective_date="2025-12-31",
                        category="INFERRED", scope="resource A", statement_id="mre", statement_group_id="group",
                        statement_kind="RESOURCE_CONTEXT", basis="TREO", original_unit="Mt", unit="Mt",
                        source_transform="", material_basis="", denominator_basis="", original_token="12",
                        value="12", selected_for_census="1", selection_role="MATCHED_SELECTED_STATEMENT")
        self.obs["source_statement_key"] = json.dumps([self.obs[k] for k in
            ("project_id","source_sha256","statement_id","scope","effective_date","statement_kind")])
        self.cell = dict(project_id="p", column=gain.COLUMNS["ore_mt"], source_sha256="sha",
                         statement_group_id="group", source_statement_keys=json.dumps([self.obs["source_statement_key"]]))
        self.selection = gain.FrozenSelection.__new__(gain.FrozenSelection)
        self.selection.approved = {"sha": "2026-11-13"}
        self.selection.observations = {"direct": self.obs}
        self.selection.cells = {("p", self.cell["column"]): (self.cell, self.obs, Decimal(12), None)}
        self.row = {**self.obs, "candidate_id":"c", "independent_observation_id":"e", "target_variable":"ore_mt",
                    "use_id":gain.USE,"use_definition_version":"v1","split":"DEVELOPMENT","source_gates":[],
                    "status":"AUTO_VALIDATED","raw":{},"group_statement":"group",
                    "inherited_selection_role":"MATCHED_SELECTED_STATEMENT"}

    def decisions(self, row):
        return gain.decide(row, self.selection, lambda *args: (), self.rules)

    def test_diagnostics_preserve_admission_and_numeric_gate(self):
        for changes in ({}, {"original_unit":"M Tonnes"}, {"basis":"THM"}, {"effective_date":"2027"},
                        {"original_token":"<12"}, {"original_token":"99"}, {"selection_role":"NOT_SELECTED"}):
            obs = {**self.obs, **changes}
            args = (obs, self.cell, self.selection.approved, Decimal(12))
            record, reason = diagnose_admission(*args)
            self.assertEqual(record, _admit(*args))
            self.assertEqual(record is None, reason is not None)

    def test_excluded_alias_reaches_semantic_arm_without_changing_use(self):
        # An additional transcription has a different observation ID, yet the
        # source SHA, page, locator, project and entire original edition agree.
        row = dict(self.row, observation_id="alternate", variable="reported_resource_ore_mt", original_unit="M Tonnes")
        result = self.decisions(row)
        self.assertNotEqual(result["A0"]["status"], "ACCEPT")
        self.assertEqual(result["B0"]["status"], "ACCEPT")
        self.assertEqual(result["B0"]["normalized_value"], "12")
        self.assertEqual([t["action"] for t in result["B0"]["lineage"]],
                         ["EXACT_QUANTITY_MAPPING","EXACT_UNIT_MAPPING","BIND_SAME_REPORTED_CELL"])
        for changes in ({"source_sha256":"other"}, {"locator":"another row"}, {"material_basis":"CONCENTRATE"},
                        {"basis":"NdPr"}, {"original_token":"13"}, {"effective_date":"2028"}):
            self.assertNotEqual(self.decisions({**row, **changes})["B0"]["status"], "ACCEPT")

    def test_source_gates_apply_before_any_mapping_or_pdf_access(self):
        for gate in ("SOURCE_NOT_AVAILABLE","SOURCE_VERSION_UNKNOWN","AFTER_CUTOFF","PROJECT_IDENTITY_UNCONFIRMED"):
            def forbidden(*args):
                self.fail("page extraction reached an ineligible source")
            result = gain.decide({**self.row, "source_gates":[gate]}, self.selection, forbidden, self.rules)
            for arm in gain.ARMS:
                self.assertEqual(result[arm]["status"], "BLOCKED")
                self.assertIn(gate, result[arm]["reason"])

    def test_same_table_header_binding_and_ambiguity(self):
        table = (["Category","M Tonnes","% TREO"], [["Inferred","6","1.5"],["TOTAL","12","1.5"]], (0,0,10,10))
        raw = {k:self.obs[k] for k in ("source_sha256","variable","category","statement_id","scope")}
        raw.update(pdf_page=4,page_markers=["TOTAL 12 1.5"])
        obs = dict(self.obs, original_unit="", original_token="")
        read_page = lambda *args: ("TOTAL 12 1.5",)
        read_page.tables = lambda *args: [table]
        recovered, lineage = gain.recover_token(obs, raw, read_page, self.rules)
        self.assertEqual((recovered["original_token"], recovered["original_unit"]), ("12", "M Tonnes"))
        self.assertEqual(lineage[0]["header"], "M Tonnes")
        self.assertEqual(lineage[0]["column"], 1)
        self.assertEqual(gain.recover_token(obs, dict(raw, page_markers=["12", "1.5"]), read_page, self.rules), (obs, []))
        read_page.tables = lambda *args: [table, table]
        self.assertEqual(gain.recover_token(obs, raw, read_page, self.rules), (obs, []))

    def test_duplicate_evidence_does_not_add_a_project_pair(self):
        a = self.decisions(self.row)
        b = {**a,"project_id":"other","candidate_id":"other-source"}
        repeated = {**a,"candidate_id":"repeat"}
        matched = gain.pair_list([a, b, repeated])
        self.assertEqual(len(matched), len(gain.ARMS))
        self.assertTrue(all({r["left"],r["right"]} == {"p","other"} for r in matched))
        self.assertTrue(all(r["status"] == "SHARED_OBSERVATION_NOT_INDEPENDENT" for r in matched))
        b = {**b,"independent_observation_id":"distinct"}
        self.assertTrue(all(r["status"] == "DISTINCT_OBSERVATIONS" for r in gain.pair_list([a,b])))

    def test_preexisting_admissions_require_the_replayed_source_bytes(self):
        page = lambda *args: ()
        page.verified_file = lambda *_: None
        result = gain.decide(self.row, self.selection, page, self.rules)
        self.assertTrue(all(result[a]["reason"] == "FROZEN_SOURCE_BYTES_UNAVAILABLE_AT_REPLAY" for a in gain.ARMS))


if __name__ == "__main__":
    unittest.main()
