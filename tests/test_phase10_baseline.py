"""Check the standalone audit of the archived Census contract."""

import ast
from hashlib import sha256
import json
from pathlib import Path
import tempfile
import unittest

from tools.phase10_baseline import RECOVERY_SCHEMA, RELEASE, _complexity, _imports, _recovery_inventory, census_inventory


ROOT = Path(__file__).resolve().parents[1]


class Phase10BaselineTests(unittest.TestCase):
    def test_sealed_census_coordinate_ledger(self):
        census = census_inventory(ROOT, ROOT / RELEASE)
        self.assertEqual((census["projects"], census["columns"]), (93, 51))
        self.assertEqual(census["total_cells"], sum(census[k] for k in
                         ("present", "not_applicable", "missing_applicable")))
        self.assertEqual(census["total_cells"], census["provenance_coordinates"])
        self.assertEqual(census["historical_frozen_denominator"] - census["applicable"],
                         census["historical_applicable_now_excluded"])
        self.assertEqual([census["priority_classes"][k]["open_applicable_gaps"] for k in ("P1", "P2")], [271, 79])

    def test_live_receipt_does_not_override_missing_or_wrong_bytes(self):
        digests = {sha256(data).hexdigest(): data for data in (b"verified", b"missing", b"changed")}
        planned = {digest: [({"key": text.decode()}, {}, "snapshot")] for digest, text in digests.items()}
        contract = {"cutoff": "2026-11-13"}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "assets").mkdir()
            for digest, text in digests.items():
                if text != b"missing":
                    (root / "assets" / digest).write_bytes(text if text == b"verified" else b"wrong")
            receipt = root / "recovery.json"
            receipt.write_text(json.dumps({
                "assets": "assets", "contract": contract, "verified": 3, "expected": 3, "version": RECOVERY_SCHEMA,
                "receipts": [{"locked_sha256": digest} for digest in digests],
            }), encoding="utf-8")
            inventory = _recovery_inventory(receipt, planned, contract)
        self.assertEqual((inventory["current_verified"], inventory["current_missing"], inventory["current_invalid"]),
                         (1, 1, 1))

    def test_module_audit_counts_function_local_import_without_double_counting_nested_branches(self):
        tree = ast.parse("""
def outside(value):
    from . import first
    def inside(other):
        from au_ree_v2.second import name
        if other:
            return 1
    if value and first:
        return inside(value)
""")
        self.assertEqual(_imports(tree, {"first", "second"}), ["first", "second"])
        outer = tree.body[0]
        self.assertEqual(_complexity(outer), 3)
        self.assertEqual(_complexity(outer.body[1]), 2)


if __name__ == "__main__":
    unittest.main()
