from pathlib import Path
import unittest

from au_ree_v2.phase10_quality import _bound_original, _pair, _retrieval, _synthetic


ROOT = Path(__file__).resolve().parents[1]


class Phase10QualityTests(unittest.TestCase):
    def test_retrieval_counts_known_pages_once_and_does_not_score_missing_queries(self):
        refs = [
            {"reference_class": "DETERMINISTIC_VERIFIED", "source_sha": "a", "locator": {"page": page}}
            for page in (2, 2, 3)
        ]
        refs.extend((
            {"reference_class": "PARSER_CONSENSUS", "source_sha": "a", "locator": {"page": 1}},
            {"reference_class": "DETERMINISTIC_VERIFIED", "source_sha": "b", "locator": {"page": 2}},
        ))
        receipt = {"retrieval_sources": [{"source_sha256": "a", "candidate_pages": {"resource": [1, 2, 2, 3]}}]}
        result = _retrieval(refs, receipt, (1, 2, 3))
        self.assertEqual(result["cutoffs"]["1"]["silver_hit_at_k"]["numerator"], 0)
        self.assertEqual(result["cutoffs"]["2"]["silver_hit_at_k"]["numerator"], 1)
        self.assertEqual(result["cutoffs"]["2"]["silver_recall_at_k"]["denominator"], 2)
        self.assertEqual(result["cutoffs"]["3"]["silver_recall_at_k"]["value"], 1)
        self.assertFalse(result["queries"][1]["ranking_available"])

    def test_measurement_pair_requires_project_report_page_quantity_and_location(self):
        ref = {
            "reference_class": "DETERMINISTIC_VERIFIED", "reference_id": "canonical-1", "project_id": "p1",
            "source_sha": "a", "quantity": "grade", "locator": {"page": 2, "cell": {"table": 1, "row": 4, "column": 2}},
        }
        raw = {"project_id": "p1", "variable": "grade",
               "evidence": {"sha256": "a", "page": 2, "table": 1, "row": 4, "column": 2}}
        item = {"raw": raw, "raw_id": "same-located-cell", "canonical_observation_id": None}
        other = {**item, "raw_id": "same-number-other-project", "raw": {**raw, "project_id": "p2"},
                 "canonical_observation_id": "canonical-1"}
        predictions = {entry["raw_id"]: (entry, {}) for entry in (item, other)}
        self.assertEqual([(x[1]["raw_id"], x[3]) for x in _pair([ref], predictions)],
                         [("same-located-cell", "ARCHIVED_CELL")])
        copy = {**item, "raw_id": "duplicate"}
        predictions[copy["raw_id"]] = (copy, {})
        self.assertEqual(_pair([ref], predictions), [])

    def test_archived_markers_need_printed_literal_and_untransformed_value(self):
        row = {"value": "7.3", "unit": "Mt", "locator": "Physical PDF p5 Table2 Wolverine Total MRE"}
        raw = {"page_markers": ["Wolverine Total", "0.96"]}
        good = "Table2 Wolverine Total 7.3 Mt 0.96%"
        binding, issue = _bound_original(row, raw, good, 20)
        self.assertIsNone(issue)
        self.assertEqual(binding["literal"], "7.3")
        self.assertIsNone(_bound_original(row, raw, good.replace("7.3", "67.3"), 20)[0])
        self.assertIsNone(_bound_original(row, {**raw, "transform": "converted"}, good, 20)[0])
        subscript = {"original_token": "2", "raw_text": "2"}
        self.assertIsNone(_bound_original({**row, "value": "2"}, subscript, "Nd2O3", 20)[0])

    def test_synthetic_negative_controls_are_separate_known_answers(self):
        refs, summary = _synthetic(ROOT)
        self.assertEqual(len(refs), 8)
        self.assertTrue(all(row["reference_class"] == "SYNTHETIC_GROUND_TRUTH" for row in refs))
        self.assertEqual((summary["true_positive"], summary["false_positive"], summary["false_negative"]), (4, 0, 0))
        self.assertEqual(summary["normalization_expectation_agreement"]["numerator"], 8)
