"""Protect the distinction between a newly usable field and a second source for it."""
import json
import unittest
from pathlib import Path

from tools.ontology_gain_metrics import load_rows
from tools.ontology_portfolio import BASE, EVIDENCE, OUT, POLICY, changes, normalized_token


class PortfolioTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = load_rows(OUT / "decisions_overlay.jsonl")
        cls.evidence = json.loads(EVIDENCE.read_bytes())

    def test_every_frozen_candidate_and_previous_decision_is_retained(self):
        prior = load_rows(BASE / "decisions.jsonl")
        self.assertEqual(set(self.rows), set(prior))
        for cid, row in self.rows.items():
            self.assertEqual(row["B1"], prior[cid]["B1"])
            if prior[cid]["B1"]["status"] == "BLOCKED":
                self.assertEqual(row["C"]["status"], "BLOCKED")

    def test_gain_is_separated_from_reprint_and_never_recounts_a_field(self):
        rows = tuple(self.rows.values())
        for first, second, expected in [("B1", "L", (12, 12, 8)), ("L", "N", (3, 3, 0)), ("N", "C", (8, 0, 0))]:
            delta = changes(rows, first, second)
            self.assertEqual(delta["candidate_losses"], [])
            self.assertEqual(tuple(len(delta[k]) for k in ("candidate_additions", "new_project_fields", "new_projects")),
                             expected)

    def test_estimate_exclusion_and_uncertain_precision_are_preserved(self):
        for control in self.evidence["negative_controls"]:
            self.assertEqual(self.rows[control["candidate_id"]]["C"]["reason"], control["relation"])
        for row in self.evidence["assertions"]:
            if row["relation"] == "SAME_ESTIMATE_ROUNDING_ONLY":
                self.assertEqual(self.rows[row["candidate_id"]]["C"]["status"], "INSUFFICIENT")
                self.assertEqual(self.rows[row["target_candidate_id"]]["C"]["normalized_value"], "4.12")

    def test_token_that_only_occurs_inside_a_different_number_is_rejected(self):
        policy = json.loads(Path(POLICY).read_bytes())
        witness = next(r for r in self.evidence["selected_witnesses"] if r["text"] == "4.12")
        row = load_rows(BASE / "candidates.jsonl")[witness["candidate_id"]]
        anchors = [{"role":"row", "page":row["physical_page"], "text":"14.12"},
                   {"role":"header", "page":row["physical_page"], "text":"TREO (%)"}]
        with self.assertRaisesRegex(ValueError, "numeric token"):
            normalized_token(witness, row, anchors, policy)
