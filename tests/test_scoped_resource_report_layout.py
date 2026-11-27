"""Check independently located estimate scopes within one locked public PDF."""

import json
from pathlib import Path
import unittest

from au_ree_v2.observation_schema import value_evidence_issue
from au_ree_v2.pdf_extract import project_registry
from au_ree_v2.resource_source import discover
from au_ree_v2.store import filehash


ROOT = Path(__file__).resolve().parents[1]
SOURCE_KEY = "mangaroon_mre2023"
SOURCE_SHA = "eb484b6f7118d7319173b4f3637b2b66e9058abdf69bf6d5cc1cf358306190e5"


def observation(row, variable):
    result, = (item for item in row["observations"] if item.variable == variable)
    return result


class ScopedResourceReportLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        lock = json.loads((ROOT / "results/phase22-2026-11-06/snapshot_lock.json").read_bytes())
        source = next(row for row in lock if row["key"] == SOURCE_KEY)
        registry = project_registry(ROOT)
        project = next(row for row in registry if row["identity_source"] == SOURCE_KEY)
        cls.project_id = project["entity_id"]
        if filehash(ROOT / source["path"]) != SOURCE_SHA or source["sha256"] != SOURCE_SHA:
            raise AssertionError("The frozen test requires the exact original PDF")
        source = dict(source, summary_project_ids=[cls.project_id])
        result = discover(ROOT, source, registry, page_numbers=[1, 16])
        cls.rows = result["candidates"]

    def test_named_section_binds_table_total_to_yin_only(self):
        rows = [row for row in self.rows if (row["physical_page"], row["table"]) == (16, 1)]
        total, = (row for row in rows if row["row_role"] == "ESTIMATE_TOTAL")
        self.assertEqual(total["row"], 13)
        self.assertEqual(total["project_id"], self.project_id)
        self.assertIn("PROJECT_SCOPE_EXTENT_UNRESOLVED", total["issues"])
        self.assertNotIn("RESOURCE_CONTAINED_UNIT_OR_BASIS_UNRESOLVED", total["issues"])
        self.assertEqual([(item.original_value, item.original_unit) for item in total["observations"]],
                         [("29.98", "Mt"), ("1.04", "%"), ("312,300", "t")])
        for item in total["observations"]:
            self.assertEqual(item.scope_id, "Yin")
            self.assertEqual(item.chemical_basis, "TREO")
            self.assertIsNone(item.effective_date)
            self.assertEqual(item.publication_date, "2023-11-30")
            conditions = dict(item.context.conditions)
            self.assertEqual(conditions["category"], "MEASURED_INDICATED_INFERRED_TOTAL")
            self.assertEqual(conditions["scope_coverage"], "REPORTED_ESTIMATE_SCOPE")
            self.assertEqual(json.loads(conditions["cutoff_grade"]), {
                "value": "0.20", "unit": "%", "basis": "TREO", "operator": None,
                "text": "0.20% TREO Cut-off"})
            self.assertTrue(any(anchor.role == "classification" and anchor.sha256 == SOURCE_SHA and anchor.page == 16
                                and anchor.bbox and anchor.locator == "NAMED_ESTIMATE_SECTION_HEADING"
                                and "Yin Ironstone Complex" in anchor.quote for anchor in item.evidence_anchors))
        contained = observation(total, "contained_treo_kt")
        header, = (anchor for anchor in contained.evidence_anchors if anchor.role == "unit")
        self.assertEqual((header.quote, header.page, header.table, header.column),
                         ("TREO (t)", 16, 1, contained.evidence.column))
        self.assertEqual((contained.evidence.page, contained.evidence.table, contained.evidence.row, contained.evidence.column),
                         (16, 1, 13, 16))

    def test_geology_subtotals_remain_components(self):
        oxide, fresh = (row for row in self.rows if (row["physical_page"], row["table"]) == (16, 1)
                        and row["row"] in (11, 12))
        for row, material in ((oxide, "Oxide"), (fresh, "Fresh")):
            self.assertEqual(row["row_role"], "COMPONENT")
            self.assertIn("RESOURCE_COMPONENT_EXCLUDED", row["issues"])
            for item in row["observations"]:
                self.assertEqual(item.material_basis, material)
                self.assertIsNone(item.denominator_basis)
                self.assertTrue(any(anchor.role == "reported_resource_material" and anchor.bbox
                                    and anchor.quote == material for anchor in item.evidence_anchors))

    def test_cutoff_scenarios_preserve_disclosures_and_other_deposit(self):
        yin = [row for row in self.rows if (row["physical_page"], row["table"]) == (1, 1)]
        gifford = [row for row in self.rows if (row["physical_page"], row["table"]) == (16, 2)]
        for rows, scope, cutoffs in ((yin, "Yin", ["0.20", "0.40", "1.00"]),
                                     (gifford, "Gifford Creek Carbonatite", ["0.90", "0.70", "0.50", "0.30"])):
            grades = [observation(row, "grade") for row in rows]
            self.assertEqual({grade.scope_id for grade in grades}, {scope})
            self.assertEqual([json.loads(dict(grade.context.conditions)["cutoff_grade"])["value"] for grade in grades],
                             cutoffs)
            self.assertEqual(len({grade.estimate_id for grade in grades}), len(cutoffs))
            for row in rows:
                self.assertEqual(row["row_role"], "CUTOFF_SCENARIO")
                self.assertIn("RESOURCE_CUTOFF_SCENARIO_NOT_PROJECT_TOTAL", row["issues"])
                if scope == "Gifford Creek Carbonatite":
                    self.assertIsNone(row["project_id"])
                for item in row["observations"]:
                    self.assertIsNone(value_evidence_issue(item, item.evidence_anchors))
                    self.assertEqual(item.evidence.sha256, SOURCE_SHA)
        alternative = observation(yin[0], "contained_treo_kt")
        self.assertEqual((alternative.original_value, alternative.evidence.page), ("311,800", 1))
        self.assertEqual(observation(gifford[0], "contained_treo_kt").original_value, "67,500")
        self.assertFalse(any(reason.startswith("RESOURCE_POSITIONED_TOKEN_") for row in self.rows for reason in row["issues"]))
