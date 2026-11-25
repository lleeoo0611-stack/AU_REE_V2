import json
import unittest
from decimal import Decimal
from pathlib import Path

from tools.normalization_comparison import _admit, _pair_report, compare_release


class ResourceUnitComparison(unittest.TestCase):
    def setUp(self):
        self.row = {
            "project_id": "project1", "statement_group_id": "group1", "statement_id": "mre1",
            "source_sha256": "digest", "scope": "selected ore", "category": "INFERRED",
            "effective_date": "2026-05-01", "selected_for_census": "1", "observation_id": "observation1",
            "variable": "grade", "value": "470", "unit": "ppm", "basis": "TREO", "material_basis": "",
            "denominator_basis": "", "locator": "PDF p3 Table 1", "statement_kind": "RESOURCE_CONTEXT",
            "source_transform": "", "original_token": "470", "original_unit": "ppm",
            "selection_role": "MATCHED_SELECTED_STATEMENT",
        }
        self.row["source_statement_key"] = json.dumps([
            "project1", "digest", "mre1", "selected ore", "2026-05-01", "RESOURCE_CONTEXT", None])
        self.lineage = {"column": "TREO品位_pct", "project_id": "project1", "statement_group_id": "group1",
                        "source_sha256": "digest", "source_statement_keys": json.dumps([self.row["source_statement_key"]])}
        self.approved = {"digest": "2026-11-13"}

    def admit(self, **updates):
        return _admit(dict(self.row, **updates), self.lineage, self.approved, Decimal("0.047"))

    def test_direct_units_require_original_stored_and_census_agreement(self):
        self.assertIsNotNone(self.admit())
        self.assertIsNotNone(self.admit(original_token="0.047%", original_unit="%"))
        for changes in ({"original_token": "469"}, {"value": "471"}, {"original_token": "1,2.3"},
                        {"original_token": ""}, {"original_token": "<470"}, {"original_unit": "%HM"},
                        {"original_unit": "%TREO"}, {"basis": "NdPr"}, {"material_basis": "CONCENTRATE"},
                        {"denominator_basis": "HEAVY_MINERALS"}, {"source_transform": '{"rule":"estimate"}'}):
            with self.subTest(changes=changes):
                self.assertIsNone(self.admit(**changes))

    def test_source_identity_scope_estimate_and_cutoff_cannot_cross(self):
        for changes in ({"project_id": "other"}, {"scope": "nested subset"}, {"statement_group_id": "g2"},
                        {"statement_id": "old"}, {"selected_for_census": "0"}, {"source_sha256": "other"},
                        {"selection_role": "REJECTED"}, {"category": "RESERVE"}, {"statement_kind": "RESERVE"},
                        {"effective_date": "2026-12-01"}, {"source_statement_key": "[]"}):
            with self.subTest(changes=changes):
                self.assertIsNone(self.admit(**changes))
        self.approved.clear()
        self.assertIsNone(self.admit())

    def test_pairs_match_field_category_and_distinct_project(self):
        first = self.admit()
        second = dict(first, project_id="project2", native_unit="%")
        dissimilar = dict(first, project_id="project3", category="INDICATED")
        wrong_field = dict(first, project_id="project4", column="礦石蘊藏量_Mt")
        report = _pair_report([first, dict(first), second, dissimilar, wrong_field])
        self.assertEqual(report["distinct_project_pairs_any_field"],
                         {"native_unit": 0, "observation_unit": 1, "census_unit": 1})
        self.assertEqual(report["distinct_pairs_added_from_native_to_census"], 1)

    def test_frozen_release_effect_is_reproducible(self):
        release = Path(__file__).resolve().parents[1] / "results/ree-project-census/gap173-20261122"
        report = compare_release(release)
        self.assertEqual(report["eligibility"]["included_cells"], 62)
        self.assertEqual(report["distinct_project_pairs_any_field"],
                         {"native_unit": 80, "observation_unit": 106, "census_unit": 106})
        self.assertEqual(report["distinct_pairs_lost_from_native_to_census"], 0)
        self.assertEqual(report["by_column"]["TREO品位_pct"]["census_unit"], 72)
