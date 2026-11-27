"""Engineering fixtures for native resource-row context and exact cell binding."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from au_ree_v2.observation_schema import value_evidence_issue
from au_ree_v2.resource_estimate import normalize_cutoff
from au_ree_v2.resource_jorc import admission_issue
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


def records(*, caption=CAPTION, values=("50", "2,000", "100,000"), headers=None, notes=()):
    data = [headers or ["Classification", "Dry ore tonnage (Mt)", "Total Rare Earth Oxides (TREO)", "TREO"],
            [None, None, "(ppm)", "(t)"], ["Indicated", "30", "2,000", "60,000"],
            ["Inferred", "20", "2,000", "40,000"], ["Total", *values]]
    return candidates_on_page(SOURCE, REGISTRY, 1,
                              [([5, 75, 545, 97], caption), *[([5, 182 + n * 15, 545, 195 + n * 15], note)
                                                           for n, note in enumerate(notes)]], [grid(data)])


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

    def test_different_composition_basis_in_bound_note_holds_the_entire_row(self):
        value_table = grid([["Classification", "Dry ore tonnage (Mt)", "TREO (%)"],
                            ["Inferred", "10", "7.5"]])
        blocks = [([5, 75, 545, 97], CAPTION),
                  ([5, 136, 545, 151], "TREO = Total Rare Earth Oxides excluding CeO2.")]
        row, = candidates_on_page(SOURCE, REGISTRY, 1, blocks, [value_table])
        self.assertIn("TREO_EXCLUDED_OXIDE_BASIS", row["issues"])
        self.assertTrue(all(observation.chemical_basis is None for observation in row["observations"]))

    def test_context_pages_require_the_same_numbered_report(self):
        primary = [([5, 75, 545, 97], CAPTION.replace("JORC ", "")),
                   ([5, 650, 545, 670], "Alpha Mineral Resource estimate 2025 Page 1 of 3")]
        table = grid([["Classification", "Tonnage (Mt)", "Total Rare Earth Oxides (TREO) (%)"],
                      ["Inferred", "50", "2.2"]])
        supplied = {2: [([5, 650, 545, 670], "Alpha Mineral Resource estimate 2025 Page 2 of 3"),
                        ([5, 150, 545, 170], "Reported in accordance with the guidelines of JORC. Tonnage was estimated on a dry basis.")]}
        found, = candidates_on_page(SOURCE, REGISTRY, 1, primary, [table], supporting_pages=supplied)
        self.assertIn("RESOURCE_JORC_SCOPE_UNRESOLVED", found["issues"])
        supplied[2][1] = supplied[2][1][0], "Table 2 was reported in accordance with JORC. Tonnage was estimated on a dry basis."
        found, = candidates_on_page(SOURCE, REGISTRY, 1, primary, [table], supporting_pages=supplied)
        self.assertEqual(found["issues"], ())
        self.assertEqual({a.page for a in found["observations"][0].evidence_anchors if a.role == "estimate_reference"}, {2})
        self.assertTrue(all(admission_issue(item) is None for item in found["observations"]))
        box, title = supplied[2][0]
        supplied[2][0] = box, title.replace("2025", "2024")
        found, = candidates_on_page(SOURCE, REGISTRY, 1, primary, [table], supporting_pages=supplied)
        self.assertIn("DRY_BULK_ORE_BASIS_UNRESOLVED", found["issues"])
        self.assertIn("RESOURCE_REPORTING_STANDARD_UNRESOLVED", found["issues"])

    def test_target_jorc_negation_keeps_the_original_located_evidence(self):
        for wording in ("non-JORC", "not JORC-compliant", "JORC (not compliant)",
                        "Not reported in accordance with the guidelines of JORC."):
            with self.subTest(wording=wording):
                total = records(caption=CAPTION.replace("JORC", wording))[-1]
                assessment = total["jorc_assessment"]
                self.assertEqual(assessment["status"], "DENIED")
                denial, = assessment["evidence"]
                self.assertIn(wording, denial["quote"])
                self.assertEqual((denial["applicability"], denial["source_sha256"], denial["physical_page"]),
                                 ("TARGET", SHA, 1))
                self.assertEqual(denial["bbox"], [5, 75, 545, 97])
                self.assertEqual(assessment["subject"]["estimate_id"], total["observations"][0].estimate_id)
                self.assertTrue(all(admission_issue(item) == "RESOURCE_JORC_NEGATED" for item in total["observations"]))
                self.assertNotIn("reporting_standard", dict(total["observations"][0].context.conditions))

    def test_other_estimate_standards_and_unrelated_negative_predicates_are_disjoint(self):
        notes = ("The old estimate in Table 1 was not JORC-compliant.",
                 "The JORC resource in Table 2 has not materially changed.",
                 "No JORC Mineral Resource changes have been identified in Table 2.",
                 "The JORC resource in Table 2 has not been converted to an Ore Reserve.")
        affirmative = records(notes=notes)[-1]
        self.assertEqual(affirmative["issues"], ())
        self.assertTrue(all(admission_issue(item) is None for item in affirmative["observations"]))
        self.assertIn(("OTHER_ESTIMATE", "DENIED"), {(e["applicability"], e["polarity"])
                                                     for e in affirmative["jorc_assessment"]["evidence"]})
        just_other = records(caption=CAPTION.replace("JORC ", ""),
                             notes=("The old estimate in Table 1 was reported in accordance with JORC.",))[-1]
        self.assertIn("RESOURCE_JORC_SCOPE_UNRESOLVED", just_other["issues"])
        contradictory = records(notes=("The old estimate in Table 1 was reported in accordance with JORC; "
                                       "the current estimate in Table 2 is not compliant.",))[-1]
        self.assertEqual(contradictory["jorc_assessment"]["status"], "CONFLICT")
        self.assertEqual({e["polarity"] for e in contradictory["jorc_assessment"]["evidence"]
                          if e["applicability"] == "TARGET"}, {"AFFIRMED", "DENIED"})
        no_table_ref = "The old estimate was reported in accordance with JORC; the current estimate is not compliant."
        contradictory = records(notes=(no_table_ref,))[-1]
        self.assertEqual(contradictory["jorc_assessment"]["status"], "CONFLICT")
        self.assertTrue(all(admission_issue(item) == "RESOURCE_JORC_CONFLICT"
                            for item in contradictory["observations"]))
        denied = records(caption=CAPTION.replace("JORC ", ""), notes=(no_table_ref,))[-1]
        self.assertEqual(denied["jorc_assessment"]["status"], "DENIED")
        no_resource = records(caption=CAPTION.replace("JORC ", ""),
                              notes=("There are no JORC Mineral Resources in Table 2.",))[-1]
        self.assertEqual(no_resource["jorc_assessment"]["status"], "DENIED")
        unspecified = records(notes=("Not reported in accordance with the guidelines of JORC.",))[-1]
        self.assertEqual(unspecified["jorc_assessment"]["status"], "UNRESOLVED_SCOPE")
        contradiction = records(notes=("This Mineral Resource estimate does not comply with JORC.",))[-1]
        self.assertEqual(contradiction["jorc_assessment"]["status"], "CONFLICT")

    def test_cutoff_keeps_operator_original_phrase_and_normalized_basis(self):
        for words, operator in (("above 500 ppm", ">"), ("at least 500 ppm", ">="), ("≤ 0.05 %", "<="),
                                ("< 500 ppm", "<"), ("at 500 ppm", "DECLARED_CUTOFF")):
            with self.subTest(words=words):
                total = records(caption=CAPTION.replace("at 500 ppm", words))[-1]
                raw = json.loads(dict(total["observations"][0].context.conditions)["cutoff_grade"])
                normalized = normalize_cutoff(raw)
                self.assertEqual((normalized["basis"], normalized["value_ppm"], normalized["operator"]),
                                 ("TREO", "500", operator))
                self.assertIn(words.removeprefix("at "), raw["text"])

    def test_blocked_source_produces_all_fixed_page_dispositions(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "source.pdf").write_bytes(b"different source bytes")
            found = discover(root, {**SOURCE, "path": "source.pdf"}, REGISTRY, page_numbers=[1, 3])
        self.assertEqual(found["candidates"], ())
        self.assertEqual([(p["physical_page"], p["status"]) for p in found["pages"]],
                         [(1, "SOURCE_BLOCKED"), (3, "SOURCE_BLOCKED")])
