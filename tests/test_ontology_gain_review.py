"""Synthetic checks for reference integrity; these cases are outside the experimental sample."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import pymupdf

from tools.verify_ontology_gain_review import verify


class SourceReviewChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        with pymupdf.open() as pdf:
            pdf.new_page().insert_text((60, 60), "Synthetic measured resource 12 Mt")
            data = pdf.tobytes()
        sha = hashlib.sha256(data).hexdigest()
        (self.root / sha).write_bytes(data)
        self.source = {"candidate_id": "synthetic-1", "source_sha256": sha}
        self.reference = {**self.source, "verdict": "SUPPORTED", "source_access": "VERIFIED",
                          "reason": "Explicit synthetic resource row.",
                          "anchors": [{"page": 1, "text": "measured resource 12 Mt"}]}
        self.sample = self.root / "sample.jsonl"
        self.labels = self.root / "labels.jsonl"
        self.sample.write_text(json.dumps(self.source), encoding="utf-8")

    def check(self, reference):
        self.labels.write_text(json.dumps(reference), encoding="utf-8")
        return verify(self.sample, self.labels, self.root)

    def test_anchor_requires_matching_pdf_and_page(self):
        self.assertEqual(self.check(self.reference)["physical_pages_verified"], 1)
        with self.assertRaisesRegex(ValueError, "anchor mismatch"):
            self.check(dict(self.reference, anchors=[{"page": 1, "text": "another deposit"}]))
        with self.assertRaisesRegex(ValueError, "Invalid physical PDF page"):
            self.check(dict(self.reference, anchors=[{"page": 2, "text": "12 Mt"}]))

    def test_no_positive_without_an_original_or_correct_packet(self):
        with self.assertRaisesRegex(ValueError, "cannot substantiate"):
            self.check(dict(self.reference, source_access="NO_ORIGINAL", anchors=[]))
        with self.assertRaisesRegex(ValueError, "cover exactly"):
            self.check(dict(self.reference, candidate_id="absent"))

    def test_additional_page_source_must_belong_to_target_statement(self):
        foreign = {"page": 1, "text": "12 Mt", "source_sha256": "a" * 64}
        with self.assertRaisesRegex(ValueError, "Unbound supporting source"):
            self.check(dict(self.reference, anchors=self.reference["anchors"] + [foreign]))
