"""Research-risk checks for source-domain comparisons and frozen test panels."""
import copy
import json
import tempfile
import unittest
from pathlib import Path

from au_ree_v2.experiment_data import validate_cases
from au_ree_v2.experiments import make_split, run_experiment
from au_ree_v2.store import digest, filehash


ROOT = Path(__file__).resolve().parents[1]
FEATURES = ["R1", "S1", "T1", "D1", "I4", "C1"]
UNITS = {"R1": "kt TREO", "S1": "%", "T1": "%", "D1": "ordinal", "I4": "km", "C1": "ordinal"}


def synthetic_dataset():
    """Fictional source IDs and observations; never use as research evidence."""
    def row(pid, year, country, commodity, positive, index):
        as_of = f"{year}-01-01"
        values = [100 + index * 100, 10 + index, 20 + 10 * (index % 7),
                  2 + index % 3, 100 + 80 * index, index % 4]
        features = dict(zip(FEATURES, values))
        features["permit_granted"] = index % 2
        lineage = {f: {"observation_ids": [f"SYNTHETIC-{pid}-{year}-{f}"],
                       "source_sha256": digest(["SYNTHETIC", pid, year, f]),
                       "locator": "SYNTHETIC_FIXTURE_ONLY", "known_at": as_of,
                       "known_at_basis": "VERIFIED_PUBLICATION", "effective_date": as_of,
                       "unit": UNITS.get(f, "binary"), "basis": "SYNTHETIC_FIXED_DEFINITION"}
                   for f in features}
        return {"case_id": f"{pid}-{year}", "project_id": pid, "country": country,
                "commodity": commodity, "scope": "PROJECT", "as_of": as_of,
                "at_risk": True, "features": features, "lineage": lineage,
                "outcome": {"target": "FID", "event_status": "OBSERVED" if positive else "NO_EVENT_VERIFIED",
                            "event_date": f"{year}-08-01" if positive else None,
                            "known_at": f"{year}-08-02" if positive else f"{year+1}-01-05",
                            "followup_end": None if positive else f"{year+1}-01-01",
                            "source_sha256": digest(["SYNTHETIC_EVENT", pid, year]),
                            "locator": "SYNTHETIC_FIXTURE_ONLY"}}
    cases = []
    for prefix, country, commodity in [("AU", "AUS", "REE"), ("CA", "CAN", "REE"),
                                        ("US", "USA", "LITHIUM")]:
        cases.extend(row(f"{prefix}-{i}", 2019, country, commodity, i % 2, i) for i in range(6))
    # A previously negative Project can have its first event in a later window.
    cases.append(row("AU-0", 2022, "AUS", "REE", 1, 5))
    cases.extend(row(f"AU-H{i}", 2022, "AUS", "REE", i % 2, i) for i in range(6))
    return {"schema_version": "experiment-dataset-v1", "synthetic": True,
            "identity_map_sha256": digest(sorted({r["project_id"] for r in cases})), "cases": cases}


def split_spec(mode="new_project"):
    return {"id": mode, "mode": mode, "train_cutoff": "2021-12-31", "test_start": "2022-01-01",
            "test_end": "2022-12-31", "target_country": "AUS", "target_commodity": "REE",
            "test_project_ids": ["AU-0", "AU-H0", "AU-H1"]}


def checked_cases(data=None):
    return validate_cases(data or synthetic_dataset(), "FID", 365, "2023-12-31", FEATURES)["cases"]


def experiment_config(dataset_path):
    return {"schema_version": "experiment-config-v1", "task": "event_prediction",
            "dataset": str(dataset_path), "target": {"name": "FID", "horizon_days": 365},
            "evaluation_as_of": "2023-12-31", "seed": 31,
            "feature_sets": {"six_criteria": FEATURES}, "models": ["prior", "logistic", "fixed_mcda"],
            "auxiliary_commodities": ["LITHIUM"],
            "mcda_baseline": {"research_config": str(ROOT / "config/research.json"),
                              "scenario": "development_assumption"},
            "splits": [split_spec()]}


class ExperimentSplitTests(unittest.TestCase):
    def test_new_project_removes_its_earlier_rows_from_every_cohort(self):
        result = make_split(checked_cases(), split_spec(), "2023-12-31", auxiliary_commodities=["LITHIUM"])
        held = {r["project_id"] for r in result["test"]}
        for rows in result["training"].values():
            self.assertFalse(held & {r["project_id"] for r in rows})
        self.assertEqual([5, 11, 17], [len(rows) for rows in result["training"].values()])

    def test_future_project_can_use_past_but_never_future_labels(self):
        cases = checked_cases()
        result = make_split(cases, split_spec("future_project"), "2023-12-31")
        self.assertIn("AU-0-2019", [r["case_id"] for r in result["training"]["AU_REE"]])
        cases[0]["label_available_at"] = "2022-01-01"
        later = make_split(cases, split_spec("future_project"), "2023-12-31")
        self.assertNotIn(cases[0]["case_id"], [r["case_id"] for r in later["training"]["GLOBAL_REE"]])

    def test_leave_country_excludes_all_target_country_training(self):
        result = make_split(checked_cases(), split_spec("leave_country"), "2023-12-31", auxiliary_commodities=["LITHIUM"])
        self.assertEqual([], result["training"]["AU_REE"])
        self.assertTrue(all(r["country"] != "AUS" for r in result["training"]["GLOBAL_REE_PLUS_OTHER"]))

    def test_test_panel_and_split_are_stable_under_input_order(self):
        cases = checked_cases()
        first = make_split(cases, split_spec(), "2023-12-31", seed=11)
        second = make_split(list(reversed(cases)), split_spec(), "2023-12-31", seed=11)
        self.assertEqual(first, second)
        self.assertEqual(first["manifest"]["test_panel_sha256"], digest([r["case_id"] for r in first["test"]]))

    def test_early_positive_does_not_bypass_unmatured_train_window(self):
        cases = checked_cases()
        case = next(r for r in cases if r["case_id"] == "CA-1-2019")
        case["horizon_end"] = "2022-05-01"
        result = make_split(cases, split_spec(), "2023-12-31")
        self.assertNotIn(case["case_id"], result["manifest"]["training"]["GLOBAL_REE"]["case_ids"])
        self.assertTrue(any(r["case_id"] == case["case_id"] and r["reason"] == "TRAIN_HORIZON_NOT_MATURE" for r in result["manifest"]["excluded"]))

    def test_early_positive_does_not_bypass_unmatured_test_window(self):
        cases = checked_cases()
        case = next(r for r in cases if r["case_id"] == "AU-H1-2022")
        case["horizon_end"] = "2024-01-01"
        result = make_split(cases, split_spec(), "2023-12-31")
        self.assertNotIn(case["case_id"], result["manifest"]["test_case_ids"])
        self.assertAlmostEqual(2/3, result["manifest"]["test_label_coverage"])

    def test_unknowns_remain_visible_and_do_not_become_negative_training(self):
        cases = checked_cases()
        row = next(r for r in cases if r["case_id"] == "CA-0-2019")
        row.update(label=None, label_status="CENSORED", label_available_at=None)
        result = make_split(cases, split_spec(), "2023-12-31")
        self.assertNotIn(row["case_id"], result["manifest"]["training"]["GLOBAL_REE"]["case_ids"])
        self.assertTrue(any(r["reason"] == "TRAIN_LABEL_CENSORED" for r in result["manifest"]["excluded"]))

    def test_temporal_overlap_is_rejected(self):
        spec = split_spec()
        spec["train_cutoff"] = spec["test_start"]
        with self.assertRaisesRegex(ValueError, "train_cutoff"):
            make_split(checked_cases(), spec, "2023-12-31")


class ExperimentRunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.dataset = self.root / "dataset.json"
        self.dataset.write_text(json.dumps(synthetic_dataset()), encoding="utf-8")
        self.config = self.root / "experiment.json"
        self.config.write_text(json.dumps(experiment_config(self.dataset)), encoding="utf-8")

    def test_dry_run_writes_nothing_and_uses_shared_test_ids(self):
        before = {p.name: filehash(p) for p in self.root.iterdir()}
        result = run_experiment(self.root, self.config, self.root / "output", dry_run=True)
        self.assertEqual(result["status"], "PLANNED")
        self.assertEqual(before, {p.name: filehash(p) for p in self.root.iterdir()})
        self.assertEqual(1, len({v["test_panel_sha256"] for v in result["variants"]}))

    def test_real_run_is_reproducible_and_never_edits_inputs(self):
        before = (filehash(self.dataset), filehash(self.config))
        output = self.root / "output"
        result = run_experiment(self.root, self.config, output)
        self.assertEqual(result["status"], "COMPLETED")
        self.assertEqual(result["research_status"], "SYNTHETIC_VALIDATION_ONLY")
        hashes = {p.name: filehash(p) for p in output.iterdir()}
        repeated = run_experiment(self.root, self.config, output)
        self.assertEqual(result, repeated)
        self.assertEqual(hashes, {p.name: filehash(p) for p in output.iterdir()})
        self.assertEqual(before, (filehash(self.dataset), filehash(self.config)))
        self.assertEqual(9, len(result["variants"]))

    def test_existing_output_cannot_be_replaced_by_different_experiment(self):
        output = self.root / "output"
        run_experiment(self.root, self.config, output)
        config = json.loads(self.config.read_text())
        config["seed"] += 1
        self.config.write_text(json.dumps(config), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "IMMUTABLE"):
            run_experiment(self.root, self.config, output)

    def test_missing_dataset_produces_readiness_without_synthetic_fallback(self):
        self.dataset.unlink()
        result = run_experiment(self.root, self.config, self.root / "blocked")
        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(result["block_reason"], "VERIFIED_PROJECT_TIME_DATASET_REQUIRED")
        self.assertEqual(result["variants"], [])

    def test_wrong_mcda_unit_blocks_only_the_mcda_comparison(self):
        data = synthetic_dataset()
        for row in data["cases"]:
            row["lineage"]["R1"]["unit"] = "t TREO"
        self.dataset.write_text(json.dumps(data), encoding="utf-8")
        result = run_experiment(self.root, self.config, dry_run=True)
        self.assertEqual(result["status"], "PARTIAL")
        blocked = [v for v in result["variants"] if v["status"] == "BLOCKED"]
        self.assertEqual(3, len(blocked))
        self.assertTrue(all("FIXED_MCDA_UNIT_MISMATCH" in v["reason"] for v in blocked))

    def test_outcome_mcda_uses_frozen_criteria_and_separate_learned_weights(self):
        config = json.loads(self.config.read_text())
        config["models"] = ["outcome_mcda"]
        self.config.write_text(json.dumps(config), encoding="utf-8")
        research_before = filehash(ROOT / "config/research.json")
        result = run_experiment(self.root, self.config, self.root / "outcome")
        self.assertEqual("COMPLETED", result["status"])
        self.assertEqual(3, result["completed_or_planned_variants"])
        self.assertEqual(research_before, filehash(ROOT / "config/research.json"))
        self.assertEqual(1, len({v["test_panel_sha256"] for v in result["variants"]}))
        self.assertTrue(all(v["fitted_model"]["name"] == "outcome_mcda" for v in result["variants"]))

    def test_added_utility_definition_enables_nlp_feature_without_overriding_formal_criteria(self):
        config = json.loads(self.config.read_text())
        config["models"] = ["outcome_mcda"]
        config["feature_sets"] = {"nlp": FEATURES + ["permit_granted"]}
        self.config.write_text(json.dumps(config), encoding="utf-8")
        blocked = run_experiment(self.root, self.config, dry_run=True)
        self.assertEqual("BLOCKED", blocked["status"])
        config["additional_utility_criteria"] = {"permit_granted": {
            "direction": "MAX", "function": "linear", "low": 0, "high": 1, "unit": "binary"}}
        self.config.write_text(json.dumps(config), encoding="utf-8")
        result = run_experiment(self.root, self.config, self.root / "nlp")
        self.assertEqual("COMPLETED", result["status"])
        config["additional_utility_criteria"]["R1"] = dict(config["additional_utility_criteria"]["permit_granted"])
        self.config.write_text(json.dumps(config), encoding="utf-8")
        invalid = run_experiment(self.root, self.config, dry_run=True)
        self.assertEqual("BLOCKED", invalid["status"])

    def test_outcome_mcda_rejects_training_unit_mismatch(self):
        config = json.loads(self.config.read_text())
        config["models"] = ["outcome_mcda"]
        self.config.write_text(json.dumps(config), encoding="utf-8")
        data = synthetic_dataset()
        for row in data["cases"]:
            row["lineage"]["R1"]["unit"] = "t TREO"
        self.dataset.write_text(json.dumps(data), encoding="utf-8")
        result = run_experiment(self.root, self.config, dry_run=True)
        self.assertEqual("BLOCKED", result["status"])
        self.assertTrue(all("OUTCOME_MCDA_UNIT_MISMATCH" in v["reason"] for v in result["variants"]))

    def test_cross_commodity_feature_scope_is_explicit_and_recorded(self):
        config = json.loads(self.config.read_text())
        config["cohort_feature_sets"] = {"GLOBAL_REE_PLUS_OTHER": []}
        self.config.write_text(json.dumps(config), encoding="utf-8")
        result = run_experiment(self.root, self.config, dry_run=True)
        self.assertEqual("PARTIAL", result["status"])
        blocked = [v for v in result["variants"] if v["status"] == "BLOCKED"]
        self.assertEqual(3, len(blocked))
        self.assertTrue(all(v["cohort"] == "GLOBAL_REE_PLUS_OTHER" and
                            v["reason"] == "FEATURE_SET_NOT_APPROVED_FOR_COHORT" for v in blocked))
        self.assertEqual(1, len({v["test_panel_sha256"] for v in result["variants"]}))


if __name__ == "__main__":
    unittest.main()
