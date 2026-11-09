import copy
import json
import tempfile
import unittest
from pathlib import Path

import pymupdf

from au_ree_v2.reviewed_discovery import validate_issue_date, validate_discovery
from au_ree_v2.store import filehash


class DiscoveryIssueDate(unittest.TestCase):
    def setUp(self):
        self.identity = {
            "publication_date": "2023-09-06",
            "document_issue_date": "2023-09-05",
            "date_evidence_role": "DOCUMENT_ISSUE_DATE_WITH_ASX_URL_RELEASE_DATE",
            "publication_date_role": "ASX_DATED_URL",
            "date_evidence": {"page": 1, "markers": ["Signed 5 September 2023"]},
        }
        self.source = {"url": "https://announcements.asx.com.au/asxpdf/20230906/pdf/abc123.pdf", "kind": "pdf"}
        self.text = "signed 5 september 2023"
        self.cutoff = "2026-11-05"

    def check(self, identity=None, source=None, text=None):
        validate_issue_date(identity or self.identity, source or self.source, self.cutoff,
                            self.text if text is None else text)

    def test_valid_roles(self):
        self.check()

    def test_reject_url_variants(self):
        urls = [
            "https://example.org/asxpdf/20230906/pdf/abc123.pdf",
            "http://announcements.asx.com.au/asxpdf/20230906/pdf/abc123.pdf",
            "https://announcements.asx.com.au.evil.test/asxpdf/20230906/pdf/abc123.pdf",
            "https://user@announcements.asx.com.au/asxpdf/20230906/pdf/abc123.pdf",
            "https://announcements.asx.com.au/asxpdf/20230906/pdf/abc123.pdf?date=20230906",
            "https://announcements.asx.com.au/asxpdf/20230906/pdf/abc123.pdf#date",
            "https://announcements.asx.com.au/other/20230906/abc123.pdf",
        ]
        for url in urls:
            with self.subTest(url=url), self.assertRaises(ValueError):
                self.check(source=dict(self.source, url=url))

    def test_release_mismatch(self):
        with self.assertRaises(ValueError):
            self.check(identity=dict(self.identity, publication_date="2023-09-07"))

    def test_signature_later_than_release(self):
        with self.assertRaises(ValueError):
            self.check(identity=dict(self.identity, document_issue_date="2023-09-07"))

    def test_after_cutoff(self):
        self.cutoff = "2023-09-05"
        with self.assertRaises(ValueError):
            self.check()

    def test_missing_date_or_markers(self):
        for text in ["", "signed 5 september 2022", "5 september 2023"]:
            with self.subTest(text=text), self.assertRaises(ValueError):
                self.check(text=text)
        with self.assertRaises(ValueError):
            self.check(identity=dict(self.identity, date_evidence={"page": 1, "markers": []}))

    def test_missing_or_wrong_roles(self):
        for field in ["publication_date_role", "date_evidence_role"]:
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.check(identity=dict(self.identity, **{field: "UNKNOWN"}))

    def test_integration_receipt_hash_and_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pdf = root / "source.pdf"
            doc = pymupdf.open()
            page = doc.new_page()
            page.insert_text((50, 50), "Signed 5 September 2023\nExample Project in Western Australia\nExample Limited")
            doc.save(pdf)
            doc.close()
            sha = filehash(pdf)
            source = dict(self.source, path="source.pdf", sha256=sha, asset_set="test",
                          evidence=[{"page": 1, "markers": ["Example Project"]}])
            identity = dict(self.identity, source_index=0, source_key="test",
                            name_marker="Example Project", state="WA", state_marker="Western Australia",
                            project_evidence={"page": 1, "markers": ["Example Project"]})
            candidate = dict(candidate_key="example", name="Example Project", aliases=[],
                             decision="ADMIT_PROJECT", reason="Test", country="AU", scope="Test",
                             sources=[source], identity=identity)
            ledger = root / "ledger.json"
            ledger.write_text(json.dumps(dict(version="reviewed-project-discovery-v1",
                cutoff=self.cutoff, acquired_through="2026-11-10", candidates=[candidate])), encoding="utf8")
            receipt = [{"url": self.source["url"], "document_sha256": sha, "status": "PDF_ACQUIRED"}]
            (root / "downloads.json").write_text(json.dumps(receipt), encoding="utf8")
            result = validate_discovery(ledger, {"test": root}, [], self.cutoff)
            self.assertEqual(result["sources"][sha]["publication_date"], "2023-09-06")
            self.assertEqual(result["sources"][sha]["document_issue_date"], "2023-09-05")
            self.assertEqual(result["sources"][sha]["publication_date_role"], "ASX_DATED_URL")
            receipt[0]["document_sha256"] = "wrong"
            (root / "downloads.json").write_text(json.dumps(receipt), encoding="utf8")
            with self.assertRaisesRegex(ValueError, "URL_HASH_NOT_CAPTURED"):
                validate_discovery(ledger, {"test": root}, [], self.cutoff)
            source["sha256"] = "wrong"
            candidate["sources"] = [source]
            cfg = json.loads(ledger.read_text())
            cfg["candidates"] = [candidate]
            ledger.write_text(json.dumps(cfg), encoding="utf8")
            with self.assertRaisesRegex(ValueError, "SOURCE_HASH_OR_PATH"):
                validate_discovery(ledger, {"test": root}, [], self.cutoff)


if __name__ == "__main__":
    unittest.main()
