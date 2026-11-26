"""Exercise per-observation dependency boundaries with versioned evidence."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from au_ree_v2.cli import execute
from au_ree_v2.derived_cache import DerivedCache
from au_ree_v2.observation_ablation import plan_replay
from au_ree_v2.observation_incremental import IncrementalObservations, load_reviews
from au_ree_v2.observation_semantics import RESOURCE_PROFILE, RESOURCE_UNITS


ROOT = Path(__file__).resolve().parents[1]
SHA = "a" * 64
CAPTURE = {
    "observation_id": "inventory-observation", "project_id": "project-a",
    "source_sha256": SHA, "physical_page": 1, "profile_id": RESOURCE_PROFILE,
    "native": {"token": "4", "unit": "Mt", "quantity": "ore_mt", "token_state": "NUMBER"},
    "context": {"scope": "north", "basis": "TREO", "category": "INDICATED",
                "statement_id": "statement-1", "effective_date": "2024-01-01"},
    "anchors": [{"source_sha256": SHA, "page": 1, "table_index": 1, "row": 2, "column": 3,
                 "role": "token", "quote": "4"}],
}
VERDICT = {"profile_id": RESOURCE_PROFILE, "profile_version": "legacy-v1", "reason": "selected", "status": "ACCEPT"}


class ObservationIncrementalTests(unittest.TestCase):
    @staticmethod
    def _stages(cache, *, journal=(), metadata=None):
        engine = IncrementalObservations(ROOT, cache)
        raw, raw_data = engine.project("candidate/e1", CAPTURE, metadata)
        normalized, normalized_data = engine.normalize("candidate/e1", raw)
        decision, _ = engine.assess("candidate/e1", raw, raw_data, normalized, normalized_data,
                                    VERDICT, "EXTRACTED", journal)
        return raw, normalized, decision

    def test_related_review_and_binding_changes_reuse_numeric_projection(self):
        with TemporaryDirectory() as tmp:
            cache_dir = Path(tmp) / "cache"
            before = self._stages(DerivedCache(cache_dir))
            self.assertEqual(before[2].evidence_status, "VERIFIED")
            review_path = Path(tmp) / "review.json"
            review_path.write_text(json.dumps({
                "schema": "shadow-observation-review-v1",
                "decisions": [{"candidate_id": "candidate", "decision_id": "review-1",
                               "reviewer": "reviewer", "disposition": "REJECT", "reason": "reviewed",
                               "decided_at": "2026-11-26T00:00:00Z"}],
            }), encoding="utf-8")
            reviews = load_reviews(review_path, {"candidate"})["candidate"]
            updated = DerivedCache(cache_dir)
            observed = self._stages(updated, journal=reviews)
            self.assertEqual(observed, self._stages(DerivedCache(), journal=reviews))
            self.assertEqual(observed[:2], before[:2])
            self.assertEqual(observed[2].comparability, "NOT_COMPARABLE")
            self.assertEqual(observed[2].evidence_status, "UNVERIFIED")
            self.assertEqual([event["state"] for event in updated.events], ["HIT", "HIT", "COMPUTED"])
            self.assertEqual(updated.events[-1]["changed_input_sha256"], ["disposition_mapping", "manual_decisions"])

            rebound = DerivedCache(cache_dir)
            updated_raw, updated_norm, updated_assessment = self._stages(rebound, metadata={"deposit_id": "new-deposit"})
            self.assertEqual(updated_raw.raw_id, before[0].raw_id)
            self.assertEqual(updated_norm, before[1])
            self.assertEqual([event["state"] for event in rebound.events], ["COMPUTED", "HIT", "COMPUTED"])
            self.assertNotEqual(updated_assessment, before[2])

    def test_target_unit_change_reuses_original_projection(self):
        with TemporaryDirectory() as tmp:
            self._stages(DerivedCache(tmp))
            updated = DerivedCache(tmp)
            with patch.dict(RESOURCE_UNITS, {"ore_mt": "kt"}):
                result = self._stages(updated)
                self.assertEqual(result, self._stages(DerivedCache()))
            self.assertEqual(str(result[1].value), "4000")
            self.assertEqual(result[1].unit, "kt")
            self.assertEqual([event["state"] for event in updated.events], ["HIT", "COMPUTED", "COMPUTED"])

    def test_preview_leaves_files_untouched_and_rejects_formal_entry(self):
        with TemporaryDirectory() as tmp:
            cache_path = Path(tmp) / "cache"
            plan = plan_replay(ROOT, cache=DerivedCache(cache_path, force=("normalization",)))
            self.assertFalse(plan["writes"])
            self.assertEqual(plan["forced_stages"], ["assessment", "normalization"])
            self.assertFalse(cache_path.exists())
            with self.assertRaisesRegex(ValueError, "disposable cache"):
                plan_replay(ROOT, cache=DerivedCache(ROOT))
            with self.assertRaisesRegex(ValueError, "applies to semantic-ablation"):
                execute(SimpleNamespace(module="all", cache_plan=True))
