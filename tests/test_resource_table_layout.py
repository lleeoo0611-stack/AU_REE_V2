"""Native table regressions using the frozen public PDFs, with no network access."""

import json
from pathlib import Path
import unittest

from au_ree_v2.numeric_evidence import scalar_decimal
from au_ree_v2.observation_schema import value_evidence_issue
from au_ree_v2.pdf_extract import project_registry
from au_ree_v2.resource_source import discover
from au_ree_v2.store import filehash


ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / "results/phase22-2026-11-06/snapshot_lock.json"


class NativeResourceTableLayoutTests(unittest.TestCase):
    def discover_locked(self, key, pages, context_pages):
        source = next(row for row in json.loads(LOCK.read_bytes()) if row["key"] == key)
        registry = project_registry(ROOT)
        project = next(row for row in registry if row["identity_source"] == key)
        source = dict(source, summary_project_ids=[project["entity_id"]])
        self.assertEqual(filehash(ROOT / source["path"]), source["sha256"])
        result = discover(ROOT, source, registry, page_numbers=pages, context_pages=context_pages)
        for candidate in result["candidates"]:
            for item in (*candidate["observations"], *candidate["material_observations"]):
                self.assertIsNone(value_evidence_issue(item, item.evidence_anchors))
                self.assertEqual(item.evidence.sha256, source["sha256"])
            self.assertFalse(any(reason.startswith("RESOURCE_POSITIONED_TOKEN_") for reason in candidate["issues"]))
        return result

    def test_caption_only_mons_keeps_local_scope_cutoff_and_byproduct(self):
        result = self.discover_locked("mons_mre2025", [1, 7], [1, 7])
        candidates = result["candidates"]
        self.assertEqual([row["physical_page"] for row in candidates], [1, 7])
        for candidate in candidates:
            self.assertEqual(candidate["row_role"], "SOLE_CLASSIFIED_ESTIMATE")
            self.assertIn("RESOURCE_CUTOFF_ANALYTE_NOT_TREO", candidate["issues"])
            self.assertIn("RESOURCE_POTENTIAL_BYPRODUCT_REE_NOT_COMPARABLE", candidate["issues"])
            mass, grade = candidate["observations"]
            self.assertEqual((mass.original_value, mass.original_unit), ("7.23", "Mt"))
            self.assertEqual((grade.original_value, grade.original_unit), ("538", "ppm"))
            self.assertEqual(grade.scope_id, "Block 3 East")
            self.assertIsNone(grade.effective_date)
            self.assertEqual(grade.chemical_basis, "TREO")
            conditions = dict(grade.context.conditions)
            self.assertEqual(conditions["category"], "INFERRED")
            self.assertEqual(conditions["estimate_period"], "2025-10")
            self.assertEqual(conditions["product_role"], "POTENTIAL_BYPRODUCT_REE")
            self.assertEqual(conditions["scope_coverage"], "REPORTED_ESTIMATE_SCOPE")
            cutoff = json.loads(conditions["cutoff_grade"])
            self.assertEqual((cutoff["value"], cutoff["unit"], cutoff["basis"]), ("70", "g/t", "GA2O3"))
            anchors = grade.evidence_anchors
            self.assertTrue(any(anchor.role == "classification" and anchor.page == grade.evidence.page
                                and anchor.bbox and "Inferred Mineral Resource" in anchor.quote for anchor in anchors))
            self.assertTrue(any(anchor.role == "reported_cutoff" and anchor.bbox and anchor.text_span
                                and cutoff["text"] in anchor.quote for anchor in anchors))
            self.assertTrue(any(anchor.role == "reported_product_role" and anchor.page == 7 and anchor.bbox
                                and "potential by-product" in anchor.quote for anchor in anchors))

    def test_burracoppin_positions_fine_and_bulk_material_as_separate_observations(self):
        result = self.discover_locked("burracoppin_maiden2023", [1, 2], [1, 2])
        candidate, = [row for row in result["candidates"] if row["material_observations"]]
        self.assertEqual(candidate["physical_page"], 2)
        self.assertIn("RESOURCE_PARTICLE_SIZE_FRACTION_NOT_COMPARABLE", candidate["issues"])
        observations = {row.variable: row for row in candidate["observations"]}
        bulk, = candidate["material_observations"]
        self.assertEqual((bulk.variable, bulk.original_value, bulk.original_unit), ("bulk_ore_mt", "35,709,000", "t"))
        self.assertEqual(bulk.denominator_basis, "RESOURCE_BULK_ORE_MASS")
        columns = {bulk.evidence.column}
        for variable, value, unit in (("ore_mt", "14731000", "t"), ("grade", "1356.4", "ppm"),
                                      ("contained_treo_kt", "20000", "t")):
            item = observations[variable]
            self.assertEqual(str(scalar_decimal(item.original_value, item.original_unit)), value)
            self.assertEqual(item.original_unit, unit)
            self.assertEqual(item.denominator_basis, "RESOURCE_PARTICLE_SIZE_FRACTION_MASS")
            self.assertEqual(item.chemical_basis, "TREO")
            self.assertEqual(item.evidence.row, bulk.evidence.row)
            self.assertNotIn(item.evidence.column, columns)
            columns.add(item.evidence.column)
            conditions = dict(item.context.conditions)
            self.assertEqual(conditions["scope_coverage"], "PARTICLE_SIZE_FRACTION")
            size = json.loads(conditions["particle_size"])
            self.assertEqual((size["operator"], size["value"], size["unit"]), ("<", "45", "µm"))
        grade_anchors = observations["grade"].evidence_anchors
        self.assertTrue(any(anchor.role == "particle_size" and anchor.page == 2 and anchor.column is not None
                            and "-45µm" in anchor.quote for anchor in grade_anchors))
        self.assertTrue(any(anchor.role == "fraction_grade_basis" and anchor.page == 1 and anchor.bbox
                            and "-45μm size fraction" in anchor.quote for anchor in grade_anchors))


if __name__ == "__main__":
    unittest.main()
