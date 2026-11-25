import json
import unittest

from tools.ontology_comparability import MODEL, assert_facts, compare_pair, compare_release, DEFAULT_ASSETS


class ResourceOntology(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.model = json.loads(MODEL.read_bytes())

    def observation(self, project, **changes):
        base = {"column":"ore", "project_id":project, "observation_id":"obs-"+project,
                "variable":"ore_mt", "effective_date":"2025-01-01", "category":"INFERRED",
                "census_unit":"Mt", "repeated_source_table":None, "facets":{}}
        return {**base, **changes}

    def test_two_unknowns_do_not_satisfy_a_constraint(self):
        result = compare_pair(self.observation("a"), self.observation("b"), self.model)
        self.assertEqual(result["baseline"], "CANDIDATE")
        self.assertEqual(result["nominal_status"], "UNRESOLVED")
        self.assertIn("moisture", result["nominal_unknowns"])
        self.assertEqual(result["strict_status"], "UNRESOLVED")

    def test_explicit_conflict_survives_other_missing_facets(self):
        first = self.observation("a", facets={"cutoff_metric":"HM", "cutoff_level":10000})
        second = self.observation("b", facets={"cutoff_metric":"USD_PER_T","cutoff_level":30})
        result = compare_pair(first, second, self.model)
        self.assertEqual(result["nominal_status"], "CONFLICT")
        self.assertEqual(result["nominal_conflicts"], "cutoff_metric")
        self.assertIn("moisture", result["nominal_unknowns"])

    def test_nominal_match_and_operational_match_are_separate(self):
        common = {"scope_extent":"NAMED_RESOURCE", "cutoff_metric":"HM", "cutoff_level":10000,
                  "moisture":"DRY", "hm_size_fraction_um":"38-710"}
        first = self.observation("a", facets=common)
        second = self.observation("b", effective_date="2024-02-02", facets={**common,"hm_size_fraction_um":"20-250"})
        result = compare_pair(first, second, self.model)
        self.assertEqual(result["nominal_status"], "MATCH")
        self.assertEqual(result["strict_status"], "CONFLICT")
        self.assertIn("hm_size_fraction_um", result["strict_extra_conflicts"])
        self.assertEqual(result["vintage"], "DIFFERENT_RECORDED_DATES")
        complete = {**common, "operational_cutoff_definition":"same method", "cutoff_boundary":"GE"}
        matched = compare_pair(dict(first, facets=complete), dict(second, facets=complete), self.model)
        self.assertEqual(matched["strict_status"], "MATCH")

    def test_duplicate_table_is_one_statement_even_if_documents_have_different_ids(self):
        first = self.observation("a", repeated_source_table="verified-table")
        second = self.observation("b", repeated_source_table="verified-table")
        self.assertEqual(compare_pair(first, second, self.model)["strict_status"], "SAME_STATEMENT")
        second["effective_date"] = "2025-02-01"
        self.assertEqual(compare_pair(first, second, self.model)["strict_status"], "UNRESOLVED")

    def test_same_treo_label_and_inclusion_of_y_do_not_establish_oxide_sum(self):
        facets = {"scope_extent":"PROJECT", "cutoff_metric":"TREO", "cutoff_level":1000,
                  "moisture":"DRY","treo_includes_y":"YES"}
        result = compare_pair(self.observation("a", variable="grade", facets=facets),
                              self.observation("b", variable="grade", facets=facets), self.model)
        self.assertEqual(result["nominal_unknowns"], "oxide_sum")
        self.assertEqual(result["nominal_status"], "UNRESOLVED")

    def test_conflicting_curated_source_statements_fail_closed(self):
        with self.assertRaises(ValueError):
            assert_facts({"cutoff_metric":"THM"}, {"cutoff_metric":"TVHM"})
        with self.assertRaises(ValueError):
            assert_facts({}, {"cutoff_metric":None})

    @unittest.skipUnless(any(DEFAULT_ASSETS.glob("54ae6be3b275*")),
                         "locked static originals required for the offline release replay")
    def test_frozen_release_regression(self):
        report = compare_release()
        summary = report["summary"]
        self.assertEqual((summary["direct_observations"], summary["projects"], summary["cross_project_field_pairs"]),
                         (62, 28, 699))
        self.assertEqual(summary["baseline_field_pairs"], 194)
        self.assertEqual(summary["among_baseline_candidates"]["strict_status"],
                         {"CONFLICT":179, "UNRESOLVED":13, "SAME_STATEMENT":2})
        self.assertEqual(len(report["oxide_extension"]), 4)
        self.assertEqual(summary["census_values_written"], 0)


if __name__ == "__main__":
    unittest.main()
