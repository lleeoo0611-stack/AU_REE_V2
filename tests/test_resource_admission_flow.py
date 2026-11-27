"""An admission frame chooses source editions and pages, never source claims."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from au_ree_v2.resource_admission_flow import load_frame


class ResourceAdmissionFrameTests(unittest.TestCase):
    def test_fixed_quality_frame_uses_only_edition_and_page_scope(self):
        root = Path(__file__).resolve().parents[1]
        frame = load_frame(root / "config/ontology/quality_frame_v1.json")
        self.assertEqual(frame["classification"], "PUBLIC_REAL_SOURCE_REPLAY")
        self.assertEqual(len(frame["sources"]), 5)
        self.assertEqual(sum(len(row["pages"]) for row in frame["sources"]), 19)
        self.assertTrue(all(set(row) == {"source_key", "source_sha256", "pages"} for row in frame["sources"]))

    def test_rejects_ambiguous_editions_and_invalid_physical_pages(self):
        row = {"source_key": "source", "source_sha256": "a" * 64, "pages": [1]}
        invalid_sources = ([row, {**row, "source_key": "alias"}], [{**row, "pages": [True]}],
                           [{**row, "pages": [0]}], [{**row, "pages": [2, 2]}])
        with TemporaryDirectory() as directory:
            path = Path(directory) / "frame.json"
            for sources in invalid_sources:
                with self.subTest(sources=sources), self.assertRaises(ValueError):
                    path.write_text(json.dumps({"schema": "resource-admission-frame-v1", "sources": sources}))
                    load_frame(path)
