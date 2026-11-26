import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pymupdf

from au_ree_v2.derived_cache import DerivedCache
from au_ree_v2.document_processing import DocumentUnavailable, PdfDocumentCache
from au_ree_v2.nlp import (
    PageIndex, automatic_observations, discover_source_observations, extract_bound_observations, recognize_source,
)
from au_ree_v2.store import filehash


def mock_ocr(path, page, tessdata):
    return {"source_sha256": filehash(path), "physical_page": page,
            "model_sha256": filehash(tessdata / "eng.traineddata"),
            "method": "MOCK_OCR", "text": "Mineral resource 6 Mt."}


def mock_ocr_comparison(document, page, tessdata, model_sha):
    return {"source_sha256": document.sha256, "physical_page": page, "model_sha256": model_sha,
            "method": "MUPDF_TESSERACT_200DPI_SELECTED_PAGE", "text": "Mineral resource 7 Mt."}


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


class PersistentDocumentNLPTests(unittest.TestCase):
    @staticmethod
    def make_pdf(assets, text):
        target = assets / "unsealed.pdf"
        with pymupdf.open() as document:
            page = document.new_page()
            if text:
                page.insert_text((40, 80), text)
            document.save(target)
        sha = filehash(target)
        target.rename(assets / f"{sha}.pdf")
        return sha

    def test_pdf_cache_restores_exact_views_across_handles_and_asset_move(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            assets = root / "assets"
            assets.mkdir()
            sha = self.make_pdf(assets, "A mineral resource estimate in this source")

            def views(document):
                return [len(document), document.text(1), document.text(1, positioned=True),
                        document.blocks(1), document.words(1), document.bounds(1),
                        document.tables(1), document.native_text(1)]

            with PdfDocumentCache(assets, cache=DerivedCache(root / "cache")) as documents:
                expected = views(documents.open(sha))
                self.assertEqual(documents.counts["opened_documents"], 1)
            moved = assets.rename(root / "moved-assets")
            cache = DerivedCache(root / "cache")
            with PdfDocumentCache(moved, cache=cache) as documents:
                self.assertEqual(views(documents.open(sha)), expected)
                self.assertEqual(documents.counts["opened_documents"], 0)
                self.assertEqual(documents.counts["native_tables"], 0)
                self.assertEqual(documents.counts["verified_hashes"], 1)
                self.assertEqual(cache.receipt()["counts"]["pdf"], {"HIT": 8})

    @patch("au_ree_v2.document_processing.extract_page", new=mock_ocr)
    def test_ocr_model_content_change_reuses_native_views_and_invalidates_ocr(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            sha = self.make_pdf(root, None)
            model = root / "eng.traineddata"
            model.write_bytes(b"first OCR model")

            def result():
                cache = DerivedCache(root / "cache")
                with PdfDocumentCache(root, cache=cache) as documents:
                    evidence = documents.open(sha).evidence(1, tessdata=root)
                    return evidence, cache.receipt()["counts"], documents.counts["ocr"]

            first, stages, ran = result()
            self.assertEqual((stages["ocr"], ran), ({"COMPUTED": 1}, 1))
            warmed, stages, ran = result()
            self.assertEqual(warmed, first)
            self.assertEqual((stages["ocr"], ran), ({"HIT": 1}, 0))
            model.write_bytes(b"changed OCR model")
            changed, stages, ran = result()
            self.assertNotEqual(changed["model_sha256"], first["model_sha256"])
            self.assertEqual((stages["pdf"], stages["ocr"], ran), ({"HIT": 3}, {"COMPUTED": 1}, 1))

    @patch("au_ree_v2.document_processing.PdfDocument._comparison_ocr", new=mock_ocr_comparison)
    def test_opt_in_ocr_support_does_not_replace_readable_native_text(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            sha = self.make_pdf(root, "Mineral resource 6 Mt.")
            (root / "eng.traineddata").write_bytes(b"mock OCR model")
            outputs = []
            for expected in ("COMPUTED", "HIT"):
                cache = DerivedCache(root / "cache")
                with PdfDocumentCache(root, cache=cache) as documents:
                    document = documents.open(sha)
                    primary = document.evidence(1, tessdata=root)
                    self.assertEqual(primary["method"], "PYPDF_NATIVE")
                    self.assertIsNone(primary["model_sha256"])
                    compared = document.evidence(1, tessdata=root, compare_ocr=True)
                    self.assertEqual(compared["text"], primary["text"])
                    self.assertEqual(compared["status"], "PARSER_DISAGREEMENT_REQUIRES_REVIEW")
                    self.assertEqual(compared["text_views"]["MUPDF_TESSERACT_200DPI_SELECTED_PAGE"],
                                     "Mineral resource 7 Mt.")
                    self.assertEqual(cache.receipt()["counts"]["ocr"], {expected: 1})
                    outputs.append(compared)
            self.assertEqual(*outputs)

    def test_missing_original_never_returns_cached_extraction(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            sha = self.make_pdf(root, "Crater Project mineral resource: 6 Mt at 200 ppm TREO.")
            row = {"candidate_id": "res", "observation_id": "res", "project_id": "Crater",
                   "source_sha256": sha, "physical_page": 1, "target_variable": "ore_mt",
                   "raw": {"page_markers": ["6", "200"]}}

            def result():
                cache = DerivedCache(root / "cache")
                with PdfDocumentCache(root, cache=cache) as documents:
                    capture = extract_bound_observations([row], [], documents)[0][0]
                    return capture, cache.receipt()["counts"], documents.counts

            cold, stages, calls = result()
            self.assertEqual((cold["status"], cold["native"]["token"]), ("EXTRACTED", "6"))
            self.assertEqual(stages["extraction"], {"COMPUTED": 1})
            warm, stages, calls = result()
            self.assertEqual(warm, cold)
            self.assertEqual(stages["extraction"], {"HIT": 1})
            self.assertEqual(calls["opened_documents"], 0)
            (root / f"{sha}.pdf").unlink()
            absent, stages, _ = result()
            self.assertEqual(absent["status"], "SOURCE_BLOCKED")
            self.assertEqual(stages["extraction"], {"SOURCE_BLOCKED": 1})

    def test_discovery_reads_selected_pages_with_no_frozen_candidate_inputs(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "data").mkdir()
            (root / "data/claims.json").write_text('{"projects":[]}', encoding="utf-8")
            file = root / "issuer-original.pdf"
            with pymupdf.open() as pdf:
                page = pdf.new_page()
                page.insert_text((40, 60), "Crater Project mineral resource is 6 Mt at 200 ppm TREO.")
                page.insert_text((40, 90), "Testwork measured 90% Nd recovery, but 70% Dy recovery.")
                pdf.new_page().insert_text((40, 60), "Copyright holder and report layout.")
                pdf.new_page()
                pdf.save(file)
            sha = filehash(file)
            source = {"key": "issuer", "sha256": sha, "path": file.name, "kind": "pdf",
                      "url": "https://example.org/report.pdf", "publication_date": "2026-01-01"}
            registry = [{"entity_id": "CRATER", "native_id": "crater", "aliases": ["Crater"]}]

            def discover():
                return discover_source_observations(root, source, registry, page_numbers=[4, 1, 3, 2],
                                                    cache=DerivedCache(root / "cache"))

            initial, repeat = discover(), discover()
            self.assertEqual(initial["pages"], repeat["pages"])
            self.assertEqual(repeat["parser_operations"].get("opened_documents", 0), 0)
            self.assertEqual([row["status"] for row in initial["pages"]],
                             ["DISCOVERED", "NO_CANDIDATES", "UNREADABLE", "PAGE_UNAVAILABLE"])
            page = initial["pages"][0]
            self.assertIn("PYPDF_NATIVE", page["evidence"]["text_views"])
            candidates = page["observations"]
            self.assertTrue({"6", "200", "90%", "70%"} <= {row.original_value for row in candidates})
            discovery = [item for item in candidates if item.extractor_version == "source-page-discovery-v1"]
            for item in discovery:
                self.assertEqual(item.project_id, "CRATER")
                self.assertEqual(item.publication_date, "2026-01-01")
                anchor = item.evidence
                start, end = anchor.text_span.in_quote
                self.assertEqual(anchor.quote[start:end], item.original_value)
            file.unlink()
            with self.assertRaisesRegex(DocumentUnavailable, "PDF_BYTES_UNAVAILABLE"):
                discover()

    def test_pdf_edition_change_recomputes_only_affected_extraction(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            first = self.make_pdf(root, "Crater Project mineral resource: 6 Mt at 200 ppm TREO.")
            updated = self.make_pdf(root, "Crater Project mineral resource: 8 Mt at 200 ppm TREO.")
            second = self.make_pdf(root, "Caldera Project mineral resource: 5 Mt at 100 ppm TREO.")

            def capture(sha, mass, directory):
                entries = [
                    {"candidate_id": "original", "observation_id": "original", "project_id": "Crater",
                     "source_sha256": sha, "physical_page": 1, "target_variable": "ore_mt",
                     "raw": {"page_markers": [str(mass), "200"]}},
                    {"candidate_id": "other", "observation_id": "other", "project_id": "Caldera",
                     "source_sha256": second, "physical_page": 1, "target_variable": "ore_mt",
                     "raw": {"page_markers": ["5", "100"]}},
                ]
                cache = DerivedCache(directory)
                with PdfDocumentCache(root, cache=cache) as documents:
                    records = extract_bound_observations(entries, [], documents)[0]
                    return records, cache.receipt()["counts"], documents.counts

            initial, _, _ = capture(first, 6, root / "cache")
            changed, stages, counts = capture(updated, 8, root / "cache")
            self.assertEqual(changed, capture(updated, 8, None)[0])
            self.assertEqual(changed[1], initial[1])
            self.assertEqual(changed[0]["native"]["token"], "8")
            self.assertEqual(stages["extraction"], {"COMPUTED": 1, "HIT": 1})
            self.assertEqual(counts["opened_documents"], 1)

    def test_bm25_added_and_removed_document_reuses_unaffected_terms(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            first = self.make_pdf(root, "Crater mineral resource estimate 6 Mt")
            second = self.make_pdf(root, "Caldera mineral resource estimate 11 Mt")

            def rank(hashes, directory):
                cache = DerivedCache(directory)
                with PdfDocumentCache(root, cache=cache, max_documents=1) as documents:
                    index = PageIndex.from_documents(documents, hashes)
                    query = index.rank_pair("Crater Caldera", "resource")
                    return query, cache.receipt(), documents.counts

            initial, _, _ = rank([first], root / "cache")
            added, receipt, calls = rank([first, second], root / "cache")
            fresh, _, _ = rank([first, second], None)
            self.assertEqual(added, fresh)
            self.assertNotEqual(added, initial)
            self.assertEqual(calls["opened_documents"], 1)
            self.assertEqual(receipt["counts"]["bm25-index"], {"HIT": 1, "COMPUTED": 2})
            self.assertEqual(receipt["counts"]["bm25-query"], {"COMPUTED": 1})
            self.assertEqual(rank([second, first], root / "cache")[0], added)
            self.assertEqual(rank([first], root / "cache")[0], initial)
            (root / f"{second}.pdf").unlink()
            with self.assertRaisesRegex(DocumentUnavailable, "PDF_BYTES_UNAVAILABLE"):
                rank([first, second], root / "cache")

    def test_added_entity_binding_invalidates_recognition_for_original(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "data").mkdir()
            claims = root / "data/claims.json"
            claims.write_text('{"projects":[]}', encoding="utf-8")
            sha = self.make_pdf(root, "Crater Project mineral resource: 6 Mt at 200 ppm TREO.")
            source = {"key": "release", "sha256": sha, "path": f"{sha}.pdf", "kind": "pdf",
                      "url": "https://example.org/report.pdf", "publication_date": "2025-02-03"}

            def recognize(directory):
                cache = DerivedCache(directory)
                report = recognize_source(root, source, [], cache=cache, page_numbers=[1])
                return report, cache.receipt()["counts"]["recognition"]

            initial, count = recognize(root / "cache")
            self.assertEqual(count, {"COMPUTED": 1})
            self.assertEqual(recognize(root / "cache"), (initial, {"HIT": 1}))
            claims.write_text(json.dumps({"projects": [{"id": "Crater",
                              "observations": [{"source_sha256": sha}]}]}), encoding="utf-8")
            updated, count = recognize(root / "cache")
            self.assertEqual(count, {"COMPUTED": 1})
            self.assertNotEqual(updated["source_binding_sha256"], initial["source_binding_sha256"])
            self.assertEqual(updated, recognize(None)[0])


if __name__ == "__main__":
    unittest.main()
