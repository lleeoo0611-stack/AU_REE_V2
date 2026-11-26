"""Exercise the fixed public frame without depending on the external source kit."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from au_ree_v2.observation_ablation import replay
from au_ree_v2.observation_semantics import RESOURCE_PROFILE
from au_ree_v2.semantic_technical import PROFILE as TECHNICAL_PROFILE


class ObservationAblationTests(unittest.TestCase):
    def test_frozen_four_arm_replay_and_independent_review_status(self):
        root = Path(__file__).resolve().parents[1]
        with TemporaryDirectory() as directory:
            output = Path(directory)
            result = replay(root, output)
            report = json.loads((output / "comparison.json").read_bytes())
            self.assertEqual(result["capture_mode"], "FROZEN_CAPTURE_REPLAY")
            self.assertEqual(result["candidates"], 732)
            self.assertEqual(report["fixed_census_project_count"], 93)
            self.assertEqual(set(report["frozen_capture_and_verdict_match"]["identical_profile_decisions"].values()),
                             {732})
            for profile, expected in [(RESOURCE_PROFILE, {"E0V0": 88, "E0V1": 88, "E1V0": 88, "E1V1": 90}),
                                      (TECHNICAL_PROFILE, {arm: 269 for arm in ("E0V0", "E0V1", "E1V0", "E1V1")})]:
                stats = report["comparison"][profile]["by_arm"]
                self.assertEqual({arm: row["accepted_source_records"] for arm, row in stats.items()}, expected)
            quality = report["quality"]
            self.assertEqual(quality[RESOURCE_PROFILE]["gain_by_evidence_type"]["new_source_corroborating_records"], 2)
            self.assertEqual(quality[RESOURCE_PROFILE]["gain_by_evidence_type"]["new_distinct_values_in_new_groups"], 0)
            self.assertEqual(quality[TECHNICAL_PROFILE]["gain_by_evidence_type"][
                "existing_comparable_groups_with_new_source_context"], 269)
            self.assertEqual(quality[TECHNICAL_PROFILE]["typed_by_arm"]["E1V1"][
                "verified_comparable_normalized_records"], 269)
            self.assertIsNone(report["independent_review"]["f1"])
            self.assertEqual(report["independent_review"]["source_first_pages"], 8)
            self.assertEqual(report["independent_review"]["pages_fully_annotated"], 0)
