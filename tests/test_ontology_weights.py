"""Frozen panel replays and edge cases for the independent weighting experiment."""
import math
import tempfile
import unittest
from pathlib import Path

from tools import ontology_weights as experiment


class ObjectiveWeightTests(unittest.TestCase):
    def test_constants_and_perfect_redundancy(self):
        data = [dict(a=x, b=x, c=0.2) for x in (0, 0.5, 1)]
        for method in ("critic", "entropy"):
            self.assertEqual(experiment.fit_group(data, ("a", "c"), method), {"a": 1, "c": 0})
            with self.assertRaisesRegex(ValueError, "no varying criterion"):
                experiment.fit_group(data, ("c",), method)
        with self.assertRaisesRegex(ValueError, "no estimable contrast"):
            experiment.fit_group(data, ("a", "b"), "critic")
        with self.assertRaisesRegex(ValueError, "no varying criterion"):
            experiment.fit_group([dict(a=0, b=1)] * 4, ("a", "b"), "entropy")

    def test_entropy_zeros_and_critic_conflict(self):
        rows = [dict(a=x, b=1 - x) for x in (0, 0.25, 0.75, 1)]
        for method in ("critic", "entropy"):
            self.assertAlmostEqual(experiment.fit_group(rows, ("a", "b"), method)["a"], 0.5)
        rows = [dict(a=0, b=1), dict(a=0, b=1), dict(a=1, b=0)]
        wa = experiment.fit_group(rows, ("a", "b"), "entropy")["a"]
        self.assertAlmostEqual(wa, 1 / (2 - math.log(2) / math.log(3)))

    def test_published_saw_replay_and_sensitivity(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            summary = experiment.audit(experiment.DEFAULT_RELEASE, experiment.ROOT / "config/research.json", out)
            self.assertEqual(len(summary["input_sha256"]), 4)
            wa = summary["panels"]["official_wa_resource_screen"]
            infra = summary["panels"]["issuer_resource_infrastructure"]
            self.assertEqual((wa["projects"], infra["projects"]), (17, 6))
            for panel in (wa, infra):
                for label, result in panel["results"].items():
                    self.assertAlmostEqual(sum(result["weights"].values()), 1)
                    self.assertEqual(result["loo_valid"], panel["projects"])
                    if label == "equal_within_domain":
                        self.assertEqual(result["ranks_changed_from_official"], 0)
            self.assertAlmostEqual(infra["results"]["critic"]["weights"]["R1"], 1 / 3)
            self.assertNotAlmostEqual(infra["results"]["flat_critic"]["weights"]["R1"], 1 / 3)
            self.assertEqual(len(experiment.read_csv(out / "weighting_ranks.csv")), 75)
            self.assertEqual(len(experiment.read_csv(out / "weighting_leave_one_out.csv")), 75)


if __name__ == "__main__":
    unittest.main()
