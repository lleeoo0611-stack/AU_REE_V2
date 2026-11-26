"""Keep experimental results separate from the formal workflow."""
from argparse import Namespace
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from au_ree_v2.cli import execute
from au_ree_v2.observation_semantics import assess_technical
from au_ree_v2.observation_shadow import partition


class ShadowTests(unittest.TestCase):
    def test_default_keeps_the_existing_entry_point(self):
        args = Namespace(module="all")
        with patch("au_ree_v2.cli._execute", return_value={"status": "COMPLETE"}) as formal:
            self.assertEqual(execute(args), {"status": "COMPLETE"})
            formal.assert_called_once_with(args)

    def test_opt_in_does_not_annotate_or_write_formal_results(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            run = root / "work/runs/one"
            run.mkdir(parents=True)
            result = run / "ranking.csv"
            result.write_bytes(b"project,rank\np1,1\n")
            args = Namespace(module="all", semantic_shadow=True, root=folder, work=str(root / "work"),
                             dry_run=False, shadow_originals="assets", shadow_output=str(root / "side-output"))
            formal = {"output_dir": str(run), "status": "COMPLETE"}
            with patch("au_ree_v2.cli._execute", return_value=formal), \
                    patch("au_ree_v2.observation_shadow.run", return_value={"status": "SHADOW_COMPLETE"}) as shadow:
                updated = execute(args)
                self.assertEqual(updated["semantic_shadow"]["status"], "SHADOW_COMPLETE")
                self.assertNotIn("semantic_shadow", formal)
                self.assertEqual(result.read_bytes(), b"project,rank\np1,1\n")
                self.assertEqual(shadow.call_args.args[2], str(run))
                args.shadow_output = str(run)
                with self.assertRaisesRegex(ValueError, "separate"):
                    execute(args)

    def test_quarantine_follows_either_project_or_original_source(self):
        split = {"quarantine_projects": ["p1"], "quarantine_source_sha256": ["a"]}
        self.assertTrue(partition({"project_id": "p2", "source_sha256": "a"}, split).startswith("QUARANTINED"))
        self.assertTrue(partition({"project_id": "p1", "source_sha256": "b"}, split).startswith("QUARANTINED"))

    def test_target_can_be_a_candidate_but_is_rejected_for_measured_leach(self):
        candidate = {"context": {"claim_nature": "TARGET"}, "native": {"value": 80, "unit": "%"}, "anchors": []}
        native_gate = {"status": "ACCEPT", "profile_id": "WITHIN_TABLE_ELEMENT_LEACH", "reasons": []}
        self.assertEqual(assess_technical(candidate, native_gate, "V0")["status"], "ACCEPT")
        self.assertEqual(assess_technical(candidate, native_gate, "V1")["reason"],
                         "CLAIM_NATURE_OUTSIDE_MEASURED_LEACH_USE")
