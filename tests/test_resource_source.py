"""Engineering fixtures for native resource-row context and exact cell binding."""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from au_ree_v2.observation_schema import value_evidence_issue
from au_ree_v2.resource_source import _positioned_value_issues, candidates_on_page, discover


SHA = "a" * 64
SOURCE = {"key": "fixture", "sha256": SHA, "kind": "pdf", "publication_date": "2025-06-01",
          "available_date": "2025-06-02", "acquired_at": "2025-06-02T11:00:00Z", "summary_project_ids": ["P"]}
REGISTRY = [{"entity_id": "P", "name": "Alpha Project", "aliases": ["Alpha"]},
            {"entity_id": "Q", "name": "Beta Project", "aliases": ["Beta"]}]
CAPTION = "Table 2: Alpha Project Total JORC Mineral Resource estimate effective 2025-05-01 at 500 ppm TREO cut-off"


def grid(data, *, index=0, top=100):
    width, height = 550, 15
    step = width / len(data[0])
    return {"physical_page": 1, "table_index": index, "bbox": [0, top, width, top + len(data) * height],
            "cells": data, "rows": [[[column * step, top + row * height, (column + 1) * step,
                                      top + (row + 1) * height] for column in range(len(cells))]
                                    for row, cells in enumerate(data)]}


def records(*, caption=CAPTION, values=("50", "2,000", "100,000"), headers=None):
    data = [headers or ["Classification", "Dry ore tonnage (Mt)", "Total Rare Earth Oxides (TREO)", "TREO"],
            [None, None, "(ppm)", "(t)"], ["Indicated", "30", "2,000", "60,000"],
            ["Inferred", "20", "2,000", "40,000"], ["Total", *values]]
    return candidates_on_page(SOURCE, REGISTRY, 1, [([5, 75, 545, 97], caption)], [grid(data)])


class ResourceSourceTests(unittest.TestCase):
    def test_resource_quantities_carry_located_header_and_context(self):
        first, second, total = records()
        self.assertIn("RESOURCE_COMPONENT_OR_COMPETING_TOTALS", first["issues"])
        self.assertIn("RESOURCE_COMPONENT_OR_COMPETING_TOTALS", second["issues"])
        self.assertEqual(total["issues"], ())
        self.assertEqual(len({observation.statement_id for observation in total["observations"]}), 1)
        self.assertEqual([(o.original_value, o.original_unit) for o in total["observations"]],
                         [("50", "Mt"), ("2,000", "ppm"), ("100,000", "t")])
        for column, observation in enumerate(total["observations"], 1):
            with self.subTest(quantity=observation.variable):
                self.assertEqual(observation.scope_id, "Alpha Project")
                self.assertEqual(observation.project_id, "P")
                self.assertEqual(observation.effective_date, "2025-05-01")
                anchor, = [a for a in observation.evidence_anchors if a.role == "unit"]
                self.assertEqual((anchor.page, anchor.table, anchor.column), (1, 0, column))
                self.assertLess(anchor.row, observation.evidence.row)
                self.assertIsNotNone(anchor.bbox)
                self.assertIsNone(value_evidence_issue(observation, observation.evidence_anchors))

    def test_wrong_unit_and_non_scalar_remain_outside_eligible_rows(self):
        total = records(values=("50", "2,000 kg", "100,000"))[-1]
        self.assertIn("RESOURCE_TOKEN_UNREADABLE_OR_UNIT_CONFLICT:grade", total["issues"])
        for literal in ("1,200–2,000", "<2,000"):
            with self.subTest(literal=literal):
                total = records(values=("50", literal, "100,000"))[-1]
                self.assertIn("RESOURCE_NOT_SCALAR:grade", total["issues"])
                self.assertEqual(total["observations"][1].original_value, literal)
        total = records(headers=["Classification", "Dry ore tonnage (Mt)", "TREO excluding CeO2", "Contained TREO (g/L)"])[-1]
        self.assertIn("RESOURCE_COLUMN_UNBOUND:grade", total["issues"])
        self.assertIn("RESOURCE_CONTAINED_UNIT_OR_BASIS_UNRESOLVED", total["issues"])

    def test_matching_number_in_neighboring_column_does_not_resolve_parser_conflict(self):
        total = records()[-1]
        words = []
        for observation in total["observations"]:
            x0, y0, x1, y1 = observation.evidence.bbox
            text = "2,099" if observation.variable == "grade" else observation.original_value
            words.append((x0 + 2, y0 + 2, x1 - 2, y1 - 2, text))
        # The expected grade token next to that cell has the wrong column.
        words.append((10, words[0][1], 20, words[0][3], "2,000"))
        self.assertEqual(list(_positioned_value_issues(total, words)), ["RESOURCE_POSITIONED_TOKEN_CONFLICT:grade"])

    def test_wrong_entity_scope_same_caption_or_different_statement_is_held(self):
        for caption, reason in (
            (CAPTION.replace("Alpha Project", "Beta Project"), "SOURCE_PROJECT_NOT_REGISTERED_FOR_ADMISSION"),
            (CAPTION.replace("Alpha Project", "Alpha Project only southern prospects"), "PROJECT_SCOPE_EXTENT_UNRESOLVED"),
            (CAPTION + " as at 2024-05-01", "RESOURCE_ESTIMATE_DATE_CONFLICT"),
            (CAPTION + " and 800 ppm TREO cut-off", "RESOURCE_CUTOFF_BASIS_OR_VALUE_CONFLICT"),
            (CAPTION + " (continued)", "CONTINUATION_SCOPE_UNCONFIRMED"),
        ):
            with self.subTest(reason=reason):
                self.assertIn(reason, records(caption=caption)[-1]["issues"])
        first = records()[-1]["observations"][0]
        other = records(caption=CAPTION.replace("2025-05-01", "2025-04-01"))[-1]["observations"][0]
        self.assertNotEqual(first.statement_id, other.statement_id)

    def test_context_pages_require_the_same_numbered_report(self):
        primary = [([5, 75, 545, 97], CAPTION.replace("JORC ", "")),
                   ([5, 650, 545, 670], "Alpha Mineral Resource estimate 2025 Page 1 of 3")]
        table = grid([["Classification", "Tonnage (Mt)", "Total Rare Earth Oxides (TREO) (%)"],
                      ["Inferred", "50", "2.2"]])
        supplied = {2: [([5, 650, 545, 670], "Alpha Mineral Resource estimate 2025 Page 2 of 3"),
                        ([5, 150, 545, 170], "Reported in accordance with the guidelines of JORC. Tonnage was estimated on a dry basis.")]}
        found, = candidates_on_page(SOURCE, REGISTRY, 1, primary, [table], supporting_pages=supplied)
        self.assertEqual(found["issues"], ())
        self.assertEqual({a.page for a in found["observations"][0].evidence_anchors if a.role == "estimate_reference"}, {2})
        box, title = supplied[2][0]
        supplied[2][0] = box, title.replace("2025", "2024")
        found, = candidates_on_page(SOURCE, REGISTRY, 1, primary, [table], supporting_pages=supplied)
        self.assertIn("DRY_BULK_ORE_BASIS_UNRESOLVED", found["issues"])
        self.assertIn("RESOURCE_REPORTING_STANDARD_UNRESOLVED", found["issues"])

    def test_blocked_source_produces_all_fixed_page_dispositions(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "source.pdf").write_bytes(b"different source bytes")
            found = discover(root, {**SOURCE, "path": "source.pdf"}, REGISTRY, page_numbers=[1, 3])
        self.assertEqual(found["candidates"], ())
        self.assertEqual([(p["physical_page"], p["status"]) for p in found["pages"]],
                         [(1, "SOURCE_BLOCKED"), (3, "SOURCE_BLOCKED")])
