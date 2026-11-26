import tempfile
import unittest
from pathlib import Path

import pymupdf

from au_ree_v2.document_processing import DocumentUnavailable, PdfDocumentCache
from au_ree_v2.nlp import PageIndex, automatic_observations, extract_bound_observations
from au_ree_v2.store import filehash


class DocumentNLPTests(unittest.TestCase):
    @staticmethod
    def make_pdf(assets):
        path = assets / "original.pdf"
        with pymupdf.open() as pdf:
            page = pdf.new_page()
            page.insert_text((40, 100), "Crater Project mineral resource: 6 Mt at 200 ppm TREO.")
            page.insert_text((40, 70), "Laboratory feed and leach extraction test.")
            page = pdf.new_page()
            page.insert_text((40, 70), "Concentrate composition Nd2O3 and Dy2O3.")
            pdf.save(path)
        sha = filehash(path)
        path.rename(assets / f"{sha}.pdf")
        return sha

    def test_cache_preserves_independent_parser_views_and_refuses_wrong_bytes(self):
        with tempfile.TemporaryDirectory() as folder:
            assets = Path(folder)
            sha = self.make_pdf(assets)
            with PdfDocumentCache(assets) as documents:
                source = documents.open(sha)
                self.assertIs(source, documents.open(sha))
                first = source.evidence(1)
                self.assertEqual(first["status"], "PARSER_DISAGREEMENT_REQUIRES_REVIEW")
                self.assertEqual(first["source_sha256"], sha)
                self.assertEqual(first, source.evidence(1))
                self.assertEqual(len(source.bounds(1)), 4)
                self.assertTrue(source.words(1))
                self.assertEqual(source.tables(1), source.tables(1))
                self.assertEqual(documents.counts["opened_documents"], 1)
                self.assertEqual(documents.counts["pypdf_text"], 1)
                self.assertEqual(documents.counts["positioned_text"], 1)
                self.assertEqual(documents.counts["native_tables"], 1)
                other = "a" * 64
                (assets / other).write_bytes((assets / f"{sha}.pdf").read_bytes())
                with self.assertRaisesRegex(DocumentUnavailable, "SOURCE_HASH_MISMATCH"):
                    documents.open(other)

    def test_bm25_retains_rule_queue_and_accepts_domain_queries(self):
        with tempfile.TemporaryDirectory() as folder:
            assets = Path(folder)
            sha = self.make_pdf(assets)
            with PdfDocumentCache(assets) as documents:
                index = PageIndex.from_documents(documents, [sha, sha])
                self.assertEqual(index.rank_pair("Crater Project", "resource")["rules_nlp"], [(sha, 1)])
                self.assertEqual(index.rank_pair("Crater Project", "technical")["rules_nlp"], [(sha, 1)])
                result = index.rank_pair("Crater Project", "strategic_composition", [(sha, 1)])
                self.assertEqual(result, {"rules": [(sha, 1)], "rules_nlp": [(sha, 1), (sha, 2)]})
                self.assertEqual(documents.counts["positioned_text"], 2)

    def test_cached_recognition_produces_located_raw_observations(self):
        source = {"source_key": "release", "source_sha256": "a" * 64}
        common = {"physical_page": 1, "project_id": "Crater", **source}
        row = {"kind": "RESOURCE_TABLE_TOTAL", "candidate_id": "resource-1",
               "raw_text": "Total 9 1.0 200 42", "row_index": 3,
               "original_tokens": ["9", "1.0", "200", "42"], "row_token_indices": {"ore_mt": 1, "grade": 2},
               "units": {"ore_mt": "Mt", "grade": "ppm"}, "scope": "Open-pit estimate",
               "positioned_column_evidence": {"method": "positioned-resource-columns-v4"},
               "extra_values": [{"label": "Nd2O3", "original_token": "42", "unit": "ppm"}], **common}
        cell = {"kind": "TECHNICAL_TABLE_CELL", "candidate_id": "cell-1",
                "raw_text": "80.0", "original_token": "80.0", "unit": "%", "quantity": "extraction_pct",
                "row_index": 2, "table_index": 0, "column_index": 1, "bbox": [0, 0, 3, 4],
                "sample_id": "S1", "reagent": "HCl", "token_state": "NUMBER", **common}
        event = {"kind": "SCOPED_TEXT_DISCLOSURE", "candidate_id": "event-1", "domain": "Development",
                 "raw_text": "The company expects to commence construction.", "issues": ["FORWARD_LOOKING"],
                 "row_index": 1, **common}
        report = {"version": "document-recognition-v6-context-bound", "candidates": [row, cell, event], **source}
        observations = list(automatic_observations(report))
        self.assertEqual(observations, list(automatic_observations(report)))
        self.assertEqual([(r.quantity_kind, r.original_value) for r in observations],
                         [("RESOURCE", "1.0"), ("RESOURCE", "200"), ("STRATEGIC_COMPOSITION", "42"),
                          ("TECHNICAL", "80.0"), ("EVENT", None)])
        self.assertEqual(observations[2].chemical_basis, "Nd2O3")
        self.assertIsNone(observations[2].denominator_basis)
        self.assertEqual(observations[2].related_observation_ids, tuple(r.observation_id for r in observations[:2]))
        self.assertEqual(observations[3].context.sample, "S1")
        self.assertEqual(observations[3].evidence.column, 1)
        self.assertIn(("recognition_issues", '["FORWARD_LOOKING"]'), observations[4].context.conditions)
        with self.assertRaisesRegex(ValueError, "different source edition"):
            list(automatic_observations({**report, "source_sha256": "b" * 64}))

    def test_both_extractors_share_original_table_and_content_order(self):
        with tempfile.TemporaryDirectory() as folder:
            assets = Path(folder)
            sha = self.make_pdf(assets)
            resource = {"candidate_id": "res", "observation_id": "res", "project_id": "Crater",
                        "source_sha256": sha, "physical_page": 1, "target_variable": "ore_mt",
                        "raw": {"page_markers": ["6", "200"]}}
            technical = {"candidate_id": "tech", "source_sha256": sha, "physical_page": 1,
                         "native": {"quantity": "extraction_pct"}, "evidence_reason": None,
                         "provenance": {"bbox": [10, 10, 25, 25], "table_index": 0,
                                        "row_index": 1, "column_index": 1}}
            with PdfDocumentCache(assets, max_documents=1) as documents:
                resource_result, technical_result = extract_bound_observations([resource], [technical], documents)
                self.assertEqual(resource_result[0]["native"]["token"], "6")
                self.assertEqual(technical_result[0]["status"], "BLOCKED")
                self.assertEqual(documents.counts["verified_hashes"], 1)
                self.assertEqual(documents.counts["opened_documents"], 1)
                self.assertEqual(documents.counts["native_tables"], 1)
                self.assertEqual(documents.counts["content_order_text"], 2)
                self.assertEqual(documents.counts["cached_documents"], 1)


if __name__ == "__main__":
    unittest.main()
