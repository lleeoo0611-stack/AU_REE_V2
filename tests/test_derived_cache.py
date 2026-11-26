"""Check that reusable products survive retries and never consume partial output."""

from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import time
from tempfile import TemporaryDirectory
import unittest

from au_ree_v2.derived_cache import DerivedCache, downstream


def _concurrent_writer(directory):
    cache = DerivedCache(directory)

    def build():
        time.sleep(.04)
        return ["complete"]

    value = cache.compute("pdf", "source-and-page", {"original_sha": "pinned"}, build)
    return value, cache.events[-1]["state"]


class DerivedCacheTests(unittest.TestCase):
    def test_modes_changed_dependencies_and_path_independence(self):
        with TemporaryDirectory() as folder:
            directory = Path(folder) / "cache"
            off = DerivedCache(directory, mode="off")
            self.assertEqual(off.compute("normalization", "obs", {"rule": 1}, lambda: ("value",)), ["value"])
            self.assertFalse(directory.exists())

            cold = DerivedCache(directory)
            cold.compute("normalization", "obs", {"rule": 1}, lambda: ["value"], upstream={"raw": "a"})
            moved = directory.with_name("relocated")
            directory.rename(moved)
            warm = DerivedCache(moved)
            self.assertEqual(warm.compute("normalization", "obs", {"rule": 1}, self.fail, upstream={"raw": "a"}),
                             ["value"])
            warm.compute("normalization", "obs", {"rule": 2}, lambda: ["changed"], upstream={"raw": "a"})
            self.assertEqual(warm.events[-1]["changed_input_sha256"], ["rule"])
            self.assertEqual(warm.events[-1]["reason"], "DEPENDENCIES_CHANGED")
            self.assertEqual(downstream(["normalization"]), ["assessment", "normalization"])
            self.assertIn("bm25-query", downstream(["pdf"]))

    def test_corrupt_interrupted_and_disagreeing_repairs(self):
        with TemporaryDirectory() as folder:
            directory = Path(folder)
            cache = DerivedCache(directory)
            cache.compute("extraction", "a", {"source": 1}, lambda: [42])
            product = next((directory / "products").rglob("*.json"))
            product.write_text('{"state": "SUCCESS",', encoding="utf-8")
            partial = product.parent / ("." + product.name + ".interrupted.tmp")
            partial.write_text("partial", encoding="utf-8")

            def fail():
                raise RuntimeError("producer interrupted")

            retry = DerivedCache(directory)
            with self.assertRaisesRegex(RuntimeError, "interrupted"):
                retry.compute("extraction", "a", {"source": 1}, fail)
            self.assertEqual(retry.events[-1]["state"], "FAILED")
            self.assertEqual(retry.events[-1]["reason"], "PRODUCT_INVALID")
            self.assertFalse(product.exists())
            self.assertEqual(len(list((directory / "quarantine").iterdir())), 1)
            self.assertEqual(retry.compute("extraction", "a", {"source": 1}, lambda: [42]), [42])
            force = DerivedCache(directory, force=("extraction",))
            with self.assertRaisesRegex(ValueError, "Nondeterministic"):
                force.compute("extraction", "a", {"source": 1}, lambda: [99])
            self.assertEqual(retry.compute("extraction", "a", {"source": 1}, self.fail), [42])

    def test_two_processes_publish_once(self):
        with TemporaryDirectory() as directory:
            with ProcessPoolExecutor(max_workers=2) as pool:
                first, second = list(pool.map(_concurrent_writer, (directory, directory)))
            self.assertEqual(first[0], second[0])
            self.assertEqual({first[1], second[1]}, {"COMPUTED", "HIT"})
            self.assertEqual(len(list((Path(directory) / "products").rglob("*.json"))), 1)
