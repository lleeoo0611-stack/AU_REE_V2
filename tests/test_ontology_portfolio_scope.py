"""Coverage checks for the frozen Census population and the iterative rule overlay."""
import unittest

from tools.ontology_portfolio_scope import COMPARISON, PILOT, RELEASE, compare_decisions, measure_change, observe


class PortfolioScopeTests(unittest.TestCase):
    def test_frozen_scope_covers_every_census_row(self):
        projects, excluded, result = observe(RELEASE, PILOT, COMPARISON)
        self.assertEqual(len({p["project_id"] for p in projects}), 93)
        self.assertTrue(result["coverage_locked_comparison"]["same_ids"])
        self.assertEqual(result["resource_classes"], {
            "COMPLETE_SELECTED_TREO_RESOURCE": 37, "PARTIAL_SELECTED_RESOURCE": 1,
            "NO_SELECTED_RESOURCE": 55,
        })
        self.assertEqual(result["census_projects_with_in_scope_candidates"], 40)
        self.assertEqual(result["census_projects_without_in_scope_candidates"], 53)
        self.assertEqual(result["candidate_records_in_census"], 349)
        self.assertEqual(len(excluded), 2)
        self.assertEqual(result["arms"]["B1"]["unique_project_field_uses"], 65)
        self.assertEqual(result["arms"]["B1"]["projects_with_accepted_use"], 29)

    def test_overlay_is_bound_to_identity_and_preserves_baseline(self):
        row = dict(candidate_id="observation-use", project_id="project", observation_id="observation",
                   use_id="declared-use", target_variable="grade")
        decision = {**row, "B1": {"status": "INSUFFICIENT"}}
        with self.assertRaisesRegex(ValueError, "unknown candidate"):
            compare_decisions([row], [decision], [{"candidate_id": "unregistered"}])
        with self.assertRaisesRegex(ValueError, "missing evidence identity"):
            compare_decisions([row], [decision], [{"candidate_id": row["candidate_id"], "C": {"status": "ACCEPT"}}])
        admitted = {"status": "ACCEPT", "evidence_identity": "verified-source-cell"}
        result = compare_decisions([row], [decision], [{"candidate_id": row["candidate_id"], "C": admitted}])
        self.assertEqual(result[row["candidate_id"]]["B1"], {"status": "INSUFFICIENT"})
        self.assertEqual(result[row["candidate_id"]]["N"], {"status": "INSUFFICIENT"})
        self.assertEqual(result[row["candidate_id"]]["C"], admitted)
        result = compare_decisions([row], [decision], [{"candidate_id": row["candidate_id"], "N": admitted}])
        self.assertEqual(result[row["candidate_id"]]["C"], admitted)

    def test_new_source_for_an_existing_field_does_not_increase_unique_use(self):
        row = dict(candidate_id="repeat", project_id="project", target_variable="grade", use_id="compare")
        decisions = {"repeat": {"N": {"status": "INSUFFICIENT"}, "C": {"status": "ACCEPT"}}}
        existing = {("project", "TREO品位_pct", "compare")}
        result = measure_change([row], decisions, {"N": existing, "C": existing}, {"N": 1, "C": 2}, "N", "C")
        self.assertEqual(result["newly_accepted_observation_records"], 1)
        self.assertEqual(result["added_project_field_uses"], [])
        self.assertEqual(result["added_evidence_for_existing_project_field_uses"], ["repeat"])


if __name__ == "__main__":
    unittest.main()
