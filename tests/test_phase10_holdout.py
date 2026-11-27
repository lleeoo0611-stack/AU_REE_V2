import hashlib
import json
from pathlib import Path
import re
import unittest

from au_ree_v2.phase10_holdout import OUTPUT, _page_signals, _sample_pages
from au_ree_v2.resource_admission_flow import load_frame


ROOT = Path(__file__).resolve().parents[1]


class TextDocument:
    """A document view with native text blocks suitable for source-cue tests."""

    def __init__(self, *pages):
        self.pages = pages

    def __len__(self):
        return len(self.pages)

    def text(self, page, *, positioned=False):
        return self.pages[page - 1]

    def blocks(self, page):
        return [(0, 0, 100, 100, self.pages[page - 1], 0, 0)]


class Phase10HoldoutTests(unittest.TestCase):
    def test_report_reprinting_an_already_used_estimate_is_excluded(self):
        document = TextDocument(
            "Held River Project exploration activities",
            "Known Hill Rare Earth Project Mineral Resource Estimate: 20 Mt at 1,000 ppm TREO.",
        )
        signals, issue = _page_signals(document, "Held River", set(), re.compile("Known Hill", re.I))
        self.assertEqual(signals, {})
        self.assertEqual(issue, "PRIOR_PROJECT_ESTIMATE_REPRINT_CUE")

    def test_exact_prior_page_bytes_are_excluded_after_text_normalization(self):
        text = "Held River Project exploration activities. " * 6
        page_hash = hashlib.sha256(" ".join(text.split()).encode()).hexdigest()
        signals, issue = _page_signals(TextDocument(text), "Held River", {page_hash}, re.compile(r"(?!)"))
        self.assertEqual(signals, {})
        self.assertEqual(issue, "DUPLICATE_PRIOR_PAGE")

    def test_cross_project_and_ownership_cues_do_not_count_as_quantitative(self):
        document = TextDocument(
            "Held River Project comprises a 100% ownership interest. Known Hill leach recovery is under review.",
            "Held River Project is planning further REE drilling.",
        )
        signals, issue = _page_signals(document, "Held River", set(), re.compile("Known Hill", re.I))
        self.assertIsNone(issue)
        self.assertIn("TECHNICAL_CROSS_PROJECT_CONTEXT_CUE", signals[1])
        self.assertNotIn("TECHNICAL_QUANTITY_CUE", signals[1])
        self.assertEqual(_sample_pages(signals, "a" * 64), ([1], [2]))

    def test_frozen_frame_loads_without_round_eight_or_nine_editions(self):
        frame = load_frame(ROOT / OUTPUT)
        rows = frame["frame_validation"]["sources"]
        prior = load_frame(ROOT / "config/ontology/resource_admission_round9_frame_v1.json")
        self.assertTrue(frame["frame_validation"]["protocol"]["frozen_before_phase10_rule_evaluation"])
        self.assertTrue({source["source_sha256"] for source in frame["sources"]}.isdisjoint(
            source["source_sha256"] for source in prior["sources"]
        ))
        self.assertTrue(all(row["role"] == "UNSEEN_REGISTERED_FAMILY" for row in rows.values()))
        self.assertEqual(len(rows), len({row["project_id"] for row in rows.values()}))
        manifest = json.loads((ROOT / OUTPUT).read_bytes())
        self.assertEqual(manifest["validation"]["generator_sha256"], hashlib.sha256(
            (ROOT / "src/au_ree_v2/phase10_holdout.py").read_bytes()
        ).hexdigest())


if __name__ == "__main__":
    unittest.main()
