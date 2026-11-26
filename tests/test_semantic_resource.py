"""Source geometry, provenance and resource relation regression cases."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from au_ree_v2.semantic_resource import _resolve, extract_resource_observations, resource_relations


SHA = "a" * 64


def frozen_candidate(key="source-row", kind="ore_mt", markers=None, **fields):
    row = {"candidate_id": key, "observation_id": key, "project_id": "P", "source_sha256": SHA,
           "physical_page": 2, "target_variable": kind, "statement_kind": "MINERAL_RESOURCE",
           "statement_id": "s", "scope": "Deposit-wide resource", "category": "INFERRED", "basis": "TREO",
           "raw": {"page_markers": markers or ["Total 106.6 4.1 4,389"]}}
    row.update(fields)
    return row


def table(index, content, y=100):
    return {"physical_page": 2, "table_index": index, "bbox": [0, y, 500, y + 20 * len(content)],
            "cells": content, "rows": [[(i * 100, y + j * 20, (i + 1) * 100, y + (j + 1) * 20)
                                        for i in range(len(row))] for j, row in enumerate(content)]}


class ResourceObservationTests(unittest.TestCase):
    def test_source_value_is_inferred_from_columns_and_not_expected_number(self):
        geo = table(1, [["Classification", "Tonnage (Mt)", "TREO (%)", "TREO (‘000 tonnes)"],
                        ["Total", "106.6", "4.1", "4,389"]])
        row = frozen_candidate(kind="contained_treo_kt", value=0)
        result = _resolve(row, ([], [], [geo]))
        self.assertEqual(result["native"]["token"], "4,389")
        self.assertEqual(result["native"]["unit"], "‘000 tonnes")
        self.assertEqual(result["anchors"][0]["column"], 3)

    def test_bad_units_and_ambiguous_same_page_cells_stay_unresolved(self):
        resource = [["Classification", "Tonnage (Mt)", "TREO (%)", "TREO (kt)"],
                    ["Total", "106.6", "4.1", "4,389"]]
        both_reports = [table(0, resource, 50), table(1, resource, 260)]
        duplicate = _resolve(frozen_candidate(kind="grade"), ([], [], both_reports))
        self.assertEqual(duplicate["reasons"], ["COMPETING_SOURCE_WITNESSES"])
        heavy_minerals = table(0, [["Classification", "Tonnage (Mt)", "TREO (% HM)", "TREO (kt)"],
                                  ["Total", "106.6", "4.1", "4,389"]])
        result = _resolve(frozen_candidate(kind="grade"), ([], [], [heavy_minerals]))
        self.assertEqual(result["status"], "INSUFFICIENT")

    def test_detached_header_must_be_on_same_page_and_aligned(self):
        header = table(1, [["Classification", "Tonnes", "TREO"], [None, "(Mt)", "(%)"]])
        body = table(2, [["Total", "30", "0.2"]], 155)
        row = frozen_candidate(kind="grade", markers=["Total 30 0.2"])
        bound = _resolve(row, ([], [], [header, body]))
        self.assertEqual(bound["native"]["token"], "0.2")
        body["bbox"][2] -= 10
        unbound = _resolve(row, ([], [], [header, body]))
        self.assertEqual(unbound["status"], "INSUFFICIENT")

    def test_negated_conditional_and_target_claims_never_become_reported_resources(self):
        row = frozen_candidate(kind="grade", markers=["106.6", "4.12"])
        for text in [
            "The mineral resource is not 106.6 Mt at 4.12% TREO.",
            "If the mineral resource is 106.6 Mt at 4.12% TREO, the project can proceed.",
            "Exploration target projected from the mineral resource is 106.6 Mt at 4.12% TREO.",
        ]:
            with self.subTest(text=text):
                self.assertEqual(_resolve(row, ([], [([0, 0, 200, 100], text)], []))["status"], "INSUFFICIENT")

    def test_rounded_discussion_corroborates_but_does_not_replace_source_token(self):
        caption = "Table 1: Mineral Resource as at 30 June 2024 at 2.5% TREO cut-off"
        geo = table(1, [["Classification", "Tonnage (Mt)", "TREO (%)", "TREO (kt)"],
                        ["Total", "106.6", "4.1", "4,389"]])
        prose = "The mineral resource is 106.6 Mt at 4.12% TREO and is summarised in Table 1."
        sources = ([], [([0, 76, 420, 98], caption), ([0, 12, 400, 35], prose)], [geo])
        a = _resolve(frozen_candidate("table", "grade"), sources)
        b = _resolve(frozen_candidate("prose", "grade", ["106.6", "4.12"]), sources)
        self.assertEqual(a["native"]["token"], "4.1")
        self.assertEqual(b["native"]["token"], "4.12")
        [rel] = resource_relations([a, b])
        self.assertEqual(rel["relation"], "SAME_ESTIMATE_ROUNDING_ONLY")
        self.assertEqual(rel["status"], "REVIEW_REQUIRED")

    def test_same_cell_and_cross_project_boundaries(self):
        geo = table(1, [["Classification", "Tonnage (Mt)", "TREO (%)", "TREO (kt)"],
                        ["Total", "106.6", "4.1", "4,389"]])
        a = _resolve(frozen_candidate("source-a"), ([], [], [geo]))
        b = _resolve(frozen_candidate("source-b"), ([], [], [geo]))
        [relation] = resource_relations([a, b])
        self.assertEqual(relation["relation"], "SAME_REPORTED_CELL")
        b["project_id"] = "different-project"
        self.assertEqual(resource_relations([a, b]), [])

    def test_asset_bytes_must_match_the_pinned_sha(self):
        with TemporaryDirectory() as directory:
            (Path(directory) / SHA).write_bytes(b"incorrect content")
            [record] = extract_resource_observations([frozen_candidate()], directory)
        self.assertEqual(record["status"], "SOURCE_BLOCKED")
        self.assertIsNone(record["native"])


if __name__ == "__main__":
    unittest.main()
