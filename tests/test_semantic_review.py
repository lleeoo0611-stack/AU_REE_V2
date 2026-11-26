import json
import tempfile
import unittest
from pathlib import Path

from au_ree_v2.store import filehash
from tools.semantic_review import Components, compare_reference, located_token, score_arm, select_pages


class SemanticReviewTests(unittest.TestCase):
    def test_family_transitively_groups_two_projects(self):
        groups = Components()
        groups.link(("project:a", "sha:original"))
        groups.link(("project:b", "sha:reprint"))
        groups.link(("sha:original", "sha:reprint"))
        self.assertEqual(len(groups.grouped()), 1)

    def test_seeded_page_selection_preserves_general_pages(self):
        raw = {n: "Mineral Resource" for n in range(1, 10)}
        raw[10] = "Exploration"
        staged = select_pages(raw, ["RESOURCE"], "source")
        self.assertEqual(staged, select_pages(dict(reversed(list(raw.items()))), ["RESOURCE"], "source"))
        self.assertEqual(staged[10], ["GENERAL"])
        self.assertEqual(len(staged), 4)

    def test_token_locator_requires_unique_quote_and_offset(self):
        body = "A: 0.96% and 0.96% B: 100.96"
        self.assertIsNone(located_token(body, "0.96", "0.96"))
        self.assertIsNone(located_token(body, "100.96", "0.96"))
        self.assertIsNone(located_token(body, "A: 0.96% and 0.96%", "0.96"))
        self.assertEqual(located_token(body, "A: 0.96% and 0.96%", "0.96", 1), body.rindex("0.96%"))

    def test_source_denominator_counts_missing_candidates_and_rejects_wrong_context(self):
        text = "A 7.3 Mt with JORC resource; B 12 Mt and no scope."
        page = {"page_id": "test", "source_sha256": "fixture", "physical_page": 2}
        labels = {}
        for quote, token in (("A 7.3 Mt", "7.3"), ("B 12 Mt", "12")):
            labels["test", located_token(text, quote, token)] = {
                "token": token, "unit": "Mt", "quantity": "ore_mt", "verdict": "CONFIRMED",
                "project_id": "X", "context": {"scope": "selected"},
            }
        decision = {"physical_page": 2, "source_sha256": "fixture", "project_id": "X", "candidate_id": "example",
                    "e0": {"native": {"token": "7.3", "unit": "Mt", "quantity": "ore_mt"},
                           "context": {"scope": "alternative"},
                           "anchors": [{"quote": "A 7.3 Mt", "page": 2}]},
                    "E0V0": {"status": "ACCEPT"}}
        outcome = score_arm([decision], {("fixture", 2): page}, {"test": text}, "E0V0", labels)
        self.assertEqual(outcome["numeric_with_own_unit_recall"]["denominator"], 2)
        self.assertEqual(outcome["numeric_with_own_unit_recall"]["numerator"], 1)
        self.assertEqual(outcome["complete_observation_recall"]["numerator"], 0)
        self.assertEqual(outcome["raw_counts"]["unextracted_confirmed"], 1)
        self.assertEqual(outcome["raw_counts"]["accepted_with_conflicting_attributes"], 1)

    def test_provisional_labels_do_not_produce_independent_metrics(self):
        with tempfile.TemporaryDirectory() as target:
            packet = Path(target) / "packet.jsonl"
            packet.write_text(json.dumps({"page_id": "p"}) + "\n", encoding="utf-8")
            reference = {"packet_sha256": filehash(packet), "pages": [{"page_id": "p", "enumeration": "COMPLETE"}],
                         "review_kind": "AI_PROVISIONAL"}
            value = compare_reference(packet, reference, [], Path(target))
            self.assertIsNone(value["accuracy"])
            self.assertTrue(value["independent_validation_pending"])
