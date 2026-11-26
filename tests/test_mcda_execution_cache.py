"""R cache integration across real pinned interchange and isolated workspaces."""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from au_ree_v2.analysis import plan_mcda, run_r
from au_ree_v2.cli import research_configuration
from au_ree_v2.store import digest, filehash
from au_ree_v2.tabular import read_csv, write_csv


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "results/phase21-2026-11-05/six_domain"
INPUTS = {"matrix.csv", "weights.csv", "criteria.csv"}


class MCDACacheTests(unittest.TestCase):
    def setUp(self):
        self.rscript = shutil.which("Rscript")
        if not self.rscript:
            self.skipTest("R unavailable")
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.cache = self.root / "cache"
        self.addCleanup(patch.stopall)
        patch.dict("os.environ", {"AU_REE_MCDA_CACHE": str(self.cache)}).start()
        self.config = research_configuration(ROOT)
        self.config["monte_carlo"] = {**self.config["monte_carlo"], "reps": 4}

    def interchange(self, name, counts):
        path = self.root / name
        for panel in counts:
            folder = path / panel
            folder.mkdir(parents=True)
            for name in INPUTS:
                shutil.copyfile(FIXTURE / name, folder / name)
            if counts[panel] == 6:
                rows = read_csv(folder / "matrix.csv")
                extra = {**rows[-1], "project_id": "AU-ADDITIONAL", "canonical_project_id": "AU-ADDITIONAL",
                         "project_name": "Additional project"}
                write_csv(folder / "matrix.csv", [*rows, extra], list(rows[0]))
        return path

    def run_panels(self, path, counts, **options):
        return run_r(ROOT, path, {"panels": counts}, self.config, self.rscript, **options)

    def plan(self, path, counts, **options):
        return plan_mcda(ROOT, path, {"panels": counts}, self.config, self.rscript, **options)["stages"]

    def scientific(self, path):
        return {p.relative_to(path): filehash(p) for p in path.glob("*/*.csv") if p.name not in INPUTS}

    def test_panel_core_and_cohort_invalidation_matches_full_rebuild(self):
        counts = {"six_domain": 5, "peer": 6}
        cache_off = self.interchange("full", counts)
        self.run_panels(cache_off, counts, cache_mode="off")
        self.assertFalse(self.cache.exists())
        original = self.interchange("original", counts)
        before = self.plan(original, counts)
        self.assertFalse(self.cache.exists())
        self.assertEqual({"COMPUTE"}, {r["action"] for r in before.values()})
        self.run_panels(original, counts)
        relocated = self.interchange("relocated", counts)
        (relocated / "unrelated.md").write_text("Documentation only.", encoding="utf8")
        result = self.run_panels(relocated, counts)
        self.assertEqual({"REUSED_VERIFIED"}, {r[k] for r in result.values()
                                              for k in ("cache_status", "cohort_cache_status")})
        self.assertEqual(self.scientific(cache_off), self.scientific(original))
        self.assertEqual(self.scientific(original), self.scientific(relocated))

        forced = self.plan(relocated, counts, force_panels=("peer",))
        self.assertEqual("REUSE", forced["six_domain/core"]["action"])
        self.assertEqual("FORCED_REBUILD", forced["six_domain/cohort"]["reason"])
        self.assertEqual("FORCED_REBUILD", forced["peer/core"]["reason"])

        for folder in (relocated, cache_off):
            path = folder / "peer/weights.csv"
            weights = read_csv(path)
            first_scenario = weights[0]["scenario"]
            scenario = [row for row in weights if row["scenario"] == first_scenario]
            scenario[0]["weight"] = float(scenario[0]["weight"]) + 0.01
            scenario[1]["weight"] = float(scenario[1]["weight"]) - 0.01
            write_csv(path, weights, list(weights[0]))
        changed = self.plan(relocated, counts, previous={"stages": before})
        self.assertEqual("REUSE", changed["six_domain/core"]["action"])
        self.assertEqual({"peer/weights.csv"}, changed["six_domain/cohort"]["changed_dependencies"]["inputs"].keys())
        incremental = self.run_panels(relocated, counts)
        self.assertEqual("REUSED_VERIFIED", incremental["six_domain"]["cache_status"])
        self.assertEqual("COMPUTED_AND_CACHED", incremental["six_domain"]["cohort_cache_status"])
        self.assertEqual("COMPUTED_AND_CACHED", incremental["peer"]["cache_status"])
        self.run_panels(cache_off, counts, cache_mode="off")
        self.assertEqual(self.scientific(cache_off), self.scientific(relocated))
        self.assertNotEqual(self.scientific(original), self.scientific(relocated))

        counts["peer"] = 5
        for folder in (relocated, cache_off):
            shutil.copyfile(FIXTURE / "matrix.csv", folder / "peer/matrix.csv")
        membership = self.run_panels(relocated, counts)
        self.assertEqual("REUSED_VERIFIED", membership["six_domain"]["cache_status"])
        self.assertEqual("COMPUTED_AND_CACHED", membership["six_domain"]["cohort_cache_status"])
        self.assertNotIn("AU-ADDITIONAL", (relocated / "peer/ranking.csv").read_text(encoding="utf8"))
        self.run_panels(cache_off, counts, cache_mode="off")
        self.assertEqual(self.scientific(cache_off), self.scientific(relocated))

        self.config["monte_carlo"] = {**self.config["monte_carlo"], "seed": 51}
        seed_plan = self.plan(relocated, counts)
        self.assertEqual("COMPUTE", seed_plan["six_domain/core"]["action"])
        self.assertEqual("REUSE", seed_plan["six_domain/cohort"]["action"])

    def test_incomplete_bundle_is_quarantined_and_rebuilt(self):
        counts = {"six_domain": 5}
        path = self.interchange("outputs", counts)
        self.run_panels(path, counts)
        expected = self.scientific(path)
        key = self.plan(path, counts)["six_domain/core"]["key"]
        receipt = self.cache / key / "receipt.json"
        damaged = json.loads(receipt.read_bytes())
        damaged["outputs"].pop("shared_draw_ranks.csv")
        damaged["output_sha256"] = digest(damaged["outputs"])
        receipt.write_text(json.dumps(damaged), encoding="utf8")
        self.assertEqual("INCOMPLETE_CACHE_OUTPUTS", self.plan(path, counts)["six_domain/core"]["reason"])
        result = self.run_panels(path, counts)
        self.assertEqual("COMPUTED_AND_CACHED", result["six_domain"]["cache_status"])
        invalid = list((self.cache / "quarantine").glob("*/invalid.json"))
        self.assertEqual([{"key": key, "reason": "INCOMPLETE_CACHE_OUTPUTS"}],
                         [json.loads(p.read_bytes()) for p in invalid])
        self.assertEqual(expected, self.scientific(path))

    def test_concurrent_executions_publish_one_verified_bundle(self):
        counts = {"six_domain": 5}
        first = self.interchange("first", counts)
        second = self.interchange("second", counts)
        with ThreadPoolExecutor(2) as pool:
            futures = [pool.submit(self.run_panels, path, counts) for path in (first, second)]
            outcomes = [future.result()["six_domain"] for future in futures]
        for status in ("cache_status", "cohort_cache_status"):
            self.assertEqual({"COMPUTED_AND_CACHED", "REUSED_VERIFIED"}, {r[status] for r in outcomes})
        self.assertEqual(self.scientific(first), self.scientific(second))
        self.assertEqual(2, len(list(self.cache.glob("*/receipt.json"))))

    def test_failed_forced_run_keeps_the_completed_bundle(self):
        counts = {"six_domain": 5}
        path = self.interchange("outputs", counts)
        self.run_panels(path, counts)
        expected = self.scientific(path)
        key = self.plan(path, counts)["six_domain/core"]["key"]
        receipt = self.cache / key / "receipt.json"
        pristine = receipt.read_bytes()
        actual_run = subprocess.run

        def simulate_interruption(command, **options):
            if "-e" in command:
                return actual_run(command, **options)
            raise subprocess.TimeoutExpired(command, timeout=300)

        with patch("au_ree_v2.analysis.subprocess.run", side_effect=simulate_interruption):
            with self.assertRaises(subprocess.TimeoutExpired):
                self.run_panels(path, counts, force_panels=("six_domain",))
        self.assertEqual(pristine, receipt.read_bytes())
        status = json.loads((path / "six_domain/r_cache.json").read_bytes())
        self.assertEqual("FAILED", status["status"])
        self.assertEqual("TimeoutExpired", status["error"])
        self.assertEqual(expected, self.scientific(path))
        self.assertEqual("REUSED_VERIFIED", self.run_panels(path, counts)["six_domain"]["cache_status"])
        self.assertEqual(2, len(list(self.cache.glob("*/receipt.json"))))
