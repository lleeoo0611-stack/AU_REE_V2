"""Check the public unattended validation entrypoint and its source isolation."""

import hashlib
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from au_ree_v2.cli import execute
from au_ree_v2.observation_validation import _stage_originals, run


class ObservationValidationTests(unittest.TestCase):
    def test_disposable_source_view_checks_bytes_and_removes_stale_links(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            library = root / "library"
            (root / "data").mkdir()
            library.mkdir()
            pdf = b"%PDF-1.7\nexact original"
            sha = hashlib.sha256(pdf).hexdigest()
            original = library / f"{sha}.pdf"
            original.write_bytes(pdf)
            (root / "data" / "manifest.json").write_text('{"snapshots":[]}', encoding="utf-8")
            view = root / "view"
            self.assertEqual(_stage_originals(root, view, (library,))["verified_pdfs"], 1)
            self.assertEqual((view / sha).read_bytes(), pdf)
            original.write_bytes(b"%PDF-1.7\ndifferent edition")
            self.assertEqual(_stage_originals(root, view, (library,))["verified_pdfs"], 0)
            self.assertFalse((view / sha).is_symlink())
            self.assertEqual(original.read_bytes(), b"%PDF-1.7\ndifferent edition")

    def test_source_gap_and_quality_failure_do_not_stop_independent_stages(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "data").mkdir()
            (root / "data" / "manifest.json").write_text('{"snapshots":[]}', encoding="utf-8")
            attempts = []

            def quality(*args, **options):
                raise OSError("source parser unavailable")

            def shadow(*args, **options):
                attempts.append("shadow")
                return {"status": "SHADOW_COMPLETE"}

            def bridge(*args, **options):
                attempts.append("bridge")
                return {"status": "COMPLETE"}

            def recover(*args, **options):
                return {"status": "BLOCKED_MISSING_ASSETS", "expected": 715, "verified": 658, "missing": 57}

            stages = {
                "au_ree_v2.source_recovery": SimpleNamespace(recover_census_assets=recover),
                "au_ree_v2.observation_quality": SimpleNamespace(run=quality),
                "au_ree_v2.observation_ablation": SimpleNamespace(replay=shadow),
                "au_ree_v2.formal_resource_bridge": SimpleNamespace(run=bridge),
            }
            output = root / "validation"
            with patch.dict(sys.modules, stages):
                result = run(root, output, online=False, database=root / "formal.sqlite",
                             formal_run=root / "frozen-run")
            self.assertEqual(attempts, ["shadow", "bridge"])
            self.assertEqual(result["status"], "FAILED")
            self.assertEqual(result["stages"]["automated_quality"]["reason"], "OSError")
            self.assertEqual(result["stages"]["formal_93"]["missing"], 57)
            self.assertEqual(json.loads((output / "validation.json").read_bytes()), result)

    def test_dry_run_does_not_create_outputs(self):
        output = "/unused-observation-validation-output"
        result = execute(SimpleNamespace(module="observation-validate", out=output, dry_run=True,
                                         cache_plan=False, force_stage=[], shadow_reviews=None))
        self.assertEqual(result, {"status": "DRY_RUN", "module": "observation-validate", "writes": False})
