"""Native table regressions using the frozen public PDFs, with no network access."""

from dataclasses import replace
import json
from pathlib import Path
import unittest

from au_ree_v2.formal_resource_admission import _value_disposition
from au_ree_v2.numeric_evidence import NATIVE_GEOMETRIC_UNIT_HEADER, scalar_decimal
from au_ree_v2.observation_schema import value_evidence_issue
from au_ree_v2.pdf_extract import project_registry
from au_ree_v2.resource_estimate import normalize_cutoff
from au_ree_v2.resource_source import discover
from au_ree_v2.resource_table_layout import composite_grade_basis
from au_ree_v2.store import filehash


ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / "results/phase22-2026-11-06/snapshot_lock.json"


class NativeResourceTableLayoutTests(unittest.TestCase):
    def discover_locked(self, key, pages, context_pages, *, project_native_id=None):
        source = next(row for row in json.loads(LOCK.read_bytes()) if row["key"] == key)
        registry = project_registry(ROOT)
        project = next(row for row in registry if (row["native_id"] == project_native_id if project_native_id
                                                   else row["identity_source"] == key))
        source = dict(source, summary_project_ids=[project["entity_id"]])
        self.assertEqual(filehash(ROOT / source["path"]), source["sha256"])
        result = discover(ROOT, source, registry, page_numbers=pages, context_pages=context_pages)
        for candidate in result["candidates"]:
            for item in (*candidate["observations"], *candidate["material_observations"]):
                self.assertIsNone(value_evidence_issue(item, item.evidence_anchors))
                self.assertEqual(item.evidence.sha256, source["sha256"])
            self.assertFalse(any(reason.startswith("RESOURCE_POSITIONED_TOKEN_") for reason in candidate["issues"]))
        return result

    def test_total_section_confirms_the_registered_wolverine_scope(self):
        result = self.discover_locked("browns_wolverine_mre20250116", [5], [1, 39],
                                      project_native_id="browns-range")
        target_table = [row for row in result["candidates"] if row["table"] == 0]
        total, = [row for row in target_table if row["row_role"] == "ESTIMATE_TOTAL"]
        self.assertEqual((total["physical_page"], total["table"], total["row"]), (5, 0, 17))
        self.assertNotIn("PROJECT_SCOPE_EXTENT_UNRESOLVED", total["issues"])
        self.assertEqual(total["jorc_assessment"]["status"], "AFFIRMED")
        reported = next(item for item in total["observations"] if item.variable == "contained_treo_kt")
        self.assertEqual(scalar_decimal(reported.original_value, reported.original_unit), 70500)
        self.assertEqual(dict(reported.context.conditions)["scope_coverage"], "PROJECT_TOTAL")
        self.assertTrue(any(anchor.role == "resource_section" and anchor.locator == "NAMED_SCOPE_TOTAL_SECTION"
                            and anchor.page == 5 and anchor.table == 0 and anchor.row < 17 and anchor.bbox
                            for anchor in reported.evidence_anchors))
        for component in (row for row in target_table if row is not total):
            self.assertIn("RESOURCE_COMPONENT_EXCLUDED", component["issues"])

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
            self.assertEqual(grade.effective_date, "2025-10")
            self.assertEqual(grade.effective_date_precision, "MONTH")
            self.assertEqual(grade.effective_date_role, "ESTIMATE_EDITION_DATE")
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

    def test_native_estimate_mass_and_composite_grade_keep_distinct_north_stanmore_domains(self):
        result = self.discover_locked("north_stanmore_mre2025", [6, 7], [8])
        totals = {}
        scopes = set()
        estimates = set()
        for row in result["candidates"]:
            if row["row_role"] != "ESTIMATE_TOTAL":
                continue
            mass, grade = row["observations"]
            composite, = row["material_observations"]
            values = mass, grade, composite
            fields = dict(grade.context.conditions)
            label = fields["reported_table_label"]
            totals[label] = tuple(scalar_decimal(item.original_value, item.original_unit) for item in values)
            self.assertEqual([item.variable for item in values], ["ore_mt", "grade", "grade_treosc"])
            self.assertEqual([item.original_unit for item in values], ["t", "ppm", "ppm"])
            self.assertEqual([grade.chemical_basis, composite.chemical_basis], ["TREO", "TREO+SC2O3"])
            self.assertEqual(len({(item.evidence.page, item.evidence.table, item.evidence.row) for item in values}), 1)
            self.assertEqual(len({item.evidence.column for item in values}), 3)
            self.assertEqual(len({item.estimate_id for item in values}), 1)
            self.assertEqual(len({item.scope_id for item in values}), 1)
            source = {"key": "north_stanmore_mre2025", "sha256": mass.evidence.sha256}
            selected_row = row["physical_page"], row["table"], row["row"]
            for item in values:
                self.assertEqual(_value_disposition(item, source, selected_row), (None, True, True))
            if label == "1":
                header, = [value for value in grade.evidence_anchors if value.role == "unit"]
                self.assertNotEqual(header.column, grade.evidence.column)
                self.assertEqual(header.locator, NATIVE_GEOMETRIC_UNIT_HEADER)
                x0, y0, x1, y1 = header.bbox
                offset = 40
                for invalid in (replace(header, locator=None), replace(header, bbox=(x0 - offset, y0, x1 - offset, y1))):
                    wrong = replace(grade, evidence_anchors=tuple(invalid if value is header else value
                                                                  for value in grade.evidence_anchors))
                    self.assertEqual(_value_disposition(wrong, source, selected_row),
                                     ("UNIT_HEADER_SOURCE_OR_COLUMN_MISMATCH", True, False))
            self.assertEqual(mass.effective_date, "2025-08")
            self.assertEqual(mass.publication_date, "2025-08-11")
            self.assertEqual(mass.effective_date_precision, "MONTH")
            self.assertEqual(mass.effective_date_role, "ESTIMATE_EDITION_DATE")
            anchor, = [value for value in mass.evidence_anchors if value.role == "reported_estimate_period"]
            self.assertTrue(anchor.bbox)
            self.assertEqual(anchor.quote[slice(*anchor.text_span.in_quote)], "August 2025")
            cutoff = normalize_cutoff(json.loads(fields["cutoff_grade"]))
            self.assertEqual((cutoff["basis"], cutoff["operator"], str(cutoff["value_ppm"])), ("TREO+SC2O3", ">=", "330"))
            self.assertIn("≥330ppm TREO + Sc2O3", cutoff["original"]["text"])
            self.assertIn("RESOURCE_CUTOFF_ANALYTE_NOT_TREO", row["issues"])
            if label in {"2", "3"}:
                self.assertIn({"2": "HGMIN", "3": "MIN"}[label], grade.scope_id)
                self.assertNotEqual(fields.get("scope_coverage"), "PROJECT_TOTAL")
            scopes.add(grade.scope_id)
            estimates.add(grade.estimate_id)
        self.assertEqual(totals, {"1": (320_640_000, 486, 510), "2": (55_025_000, 1029, 1059),
                                  "3": (265_615_000, 374, 397)})
        self.assertEqual(len(scopes), 3)
        self.assertEqual(len(estimates), 3)

    def test_composite_grade_abbreviation_needs_a_matching_analyte_declaration(self):
        abbreviation = [{"text": "TREOSc\n(ppm)"}]
        self.assertIsNone(composite_grade_basis(abbreviation, None))
        self.assertIsNone(composite_grade_basis(abbreviation, {"basis": "TREO"}))
        self.assertEqual(composite_grade_basis(abbreviation, {"basis": "TREO+SC2O3"}), "TREO+SC2O3")
        self.assertEqual(composite_grade_basis([{"text": "TREO + ScO\n2 3"}, {"text": "(ppm)"}], None), "TREO+SC2O3")


if __name__ == "__main__":
    unittest.main()
