"""Paired page retrieval uses only the same original documents in both arms."""
import csv
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from tools.nlp_page_retrieval import PageIndex, rank_pair, rule_pages


A, B, C = "a" * 64, "b" * 64, "c" * 64


class PageRetrievalTests(unittest.TestCase):
    def test_augments_same_rule_queue_with_project_and_field_specific_text(self):
        pages = [(A, 1, "Financial statements for the year"),
                 (A, 2, "Arcadia location map. Geographic coordinates and projection."),
                 (A, 3, "Arcadia 2024 Annual Financial Report"),
                 (B, 1, "Location map of another project and a different district.")]
        result = rank_pair(pages, ["Arcadia Project"], "緯度", [(C, 1), (A, 1), (A, 1)], k=2)
        self.assertEqual(result, {"rules": [(A, 1)], "rules_nlp": [(A, 1), (A, 2)]})
        self.assertEqual(result, rank_pair(reversed(pages), ["Arcadia Project"], "經度", [(A, 1)], k=2))

    def test_budget_image_only_ties_and_unmatched_pages(self):
        pages = [(A, 1, ""), (B, 2, "Geology and mineralisation."), (B, 1, "Geology and mineralisation."),
                 (C, 3, "Information for shareholders.")]
        index = PageIndex(pages)
        self.assertEqual(index.rank_pair("Project", "deposit", [(A, 1)], k=1)["rules_nlp"], [(A, 1)])
        self.assertEqual(index.rank_pair("Project", "deposit", k=5)["rules_nlp"], [(B, 1), (B, 2)])
        self.assertEqual(index.rank_pair("Project", "coordinate"), {"rules": [], "rules_nlp": []})
        self.assertEqual(PageIndex([(A, 2, "")]).rank_pair([], "stage", [(A, 2)])["rules"], [(A, 2)])

    def test_inputs_require_unique_document_and_page(self):
        for pages in ([(A, 0, "x")], [("invalid", 1, "x")], [(B, 1, "x"), (B, 1, "x")]):
            with self.subTest(pages=pages), self.assertRaises(ValueError):
                PageIndex(pages)
        for field, k in (("custom", 1), ("stage", 0), ("stage", 1.5)):
            with self.subTest(field=field, k=k), self.assertRaises(ValueError):
                PageIndex([]).rank_pair([], field, k=k)

    def test_only_explicit_source_page_bindings_reach_rules(self):
        with TemporaryDirectory() as tmp:
            def table(name, fields, records):
                with (Path(tmp) / name).open("w", newline="", encoding="utf-8") as stream:
                    writer = csv.writer(stream)
                    writer.writerow(fields)
                    writer.writerows(records)
            table("field_provenance.csv", ["project_id", "column", "source_sha256", "pdf_page"], [
                  ["id", "開發階段", A, "2;4"], ["id", "礦床型態", A + ";" + B, "78;91"]])
            table("field_status.csv", ["project_id", "column", "findings"], [
                  ["id", "緯度", json.dumps([{"source_sha256": C, "scope_references": [
                      {"source_sha256": B, "page": 8}]}])]])
            table("milestone_events.csv", ["project_id", "source_sha256", "physical_page"], [["id", A, 2]])
            table("spatial_point_quality.csv", ["project_id", "review_details"], [
                  ["id", json.dumps({"notice_sha256": A, "physical_page": 5,
                                     "scope_report_sha256": B, "scope_report_page": 6})]])
            # This target-looking page exists only in independently scored case notes.
            table("gap_review.csv", ["project_id", "column", "source_sha256", "pdf_page"], [["id", "經度", C, 99]])
            actual = rule_pages(tmp)
        self.assertEqual(actual, {("id", "stage"): ((A, 2), (A, 4)),
                                  ("id", "coordinate"): ((B, 8), (A, 5), (B, 6))})
