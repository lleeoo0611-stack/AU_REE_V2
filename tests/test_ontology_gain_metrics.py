"""Synthetic scoring counterexamples, never part of the real evidence cohort."""
import unittest

from tools.ontology_gain_metrics import arm_metrics, delta


class GainMetricsTests(unittest.TestCase):
    def rows(self):
        transitions = [
            ("INCOMPATIBLE", "ACCEPT", "SUPPORTED"), ("BLOCKED", "ACCEPT", "INCOMPATIBLE"),
            ("INSUFFICIENT", "ACCEPT", "INSUFFICIENT"), ("ACCEPT", "INCOMPATIBLE", "SUPPORTED"),
            ("BLOCKED", "ACCEPT", "NOT_REVIEWED"), ("NOT_IMPLEMENTED", "ACCEPT", "SUPPORTED"),
            ("ERROR", "ACCEPT", "NOT_REVIEWED"), ("ACCEPT", "ACCEPT", "SUPPORTED"),
        ]
        return [dict(A0=a, B1=b, reference=label, candidate_id=str(i), observation_id=str(i),
                     project_id="p", use_id="u", independent_observation_id=str(i)) for i, (a, b, label) in enumerate(transitions)]

    def test_gain_loss_unknown_and_unsupported_baseline(self):
        result = delta(self.rows(), "A0", "B1")
        self.assertEqual(result["added"], 4)
        self.assertEqual(result["removed_by_reference"]["SUPPORTED"], 1)
        self.assertEqual(result["unevaluable_or_unimplemented"], 2)
        self.assertEqual(set(result["added_by_reference"].values()), {1})
        self.assertEqual(delta(self.rows(), "A0", "A0")["added"], 0)

    def test_restatement_adds_a_supported_record_but_no_new_observation(self):
        cases = self.rows()
        cases[0]["independent_observation_id"] = cases[-1]["independent_observation_id"]
        result = delta(cases, "A0", "B1")
        self.assertEqual(result["new_supported_records_already_represented"], 1)
        self.assertEqual(result["new_supported_observation_uses"], 0)

    def test_partial_labels_and_empty_denominators(self):
        result = arm_metrics(self.rows(), "B1")
        self.assertEqual(result["precision_on_determinate_labels"]["rate"], 3 / 4)
        self.assertEqual(result["supported_share_of_reviewed_admissions"]["rate"], 3 / 5)
        self.assertEqual(result["recall_on_supported_labels"]["rate"], 3 / 4)
        self.assertIsNone(arm_metrics([], "B1")["recall_on_supported_labels"]["rate"])
