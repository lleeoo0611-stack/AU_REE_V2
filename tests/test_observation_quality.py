"""Synthetic quality controls complement the fixed real-PDF evaluation frame."""

from copy import deepcopy
from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path
from shutil import copytree
from tempfile import TemporaryDirectory
import unittest

from au_ree_v2.observation_quality import (
    FRAME, _arithmetic, _event_stance, _numeric_location, _quantity_literal_gaps, _validate_frame,
    compare_fixed, run,
)
from au_ree_v2.observation_schema import EvidenceAnchor, ObservationContext, RawObservation, TextSpan

ROOT = Path(__file__).resolve().parents[1]
SHA = "7" * 64


def _raw(anchor, *, kind="TECHNICAL", value="70", unit="%"):
    return RawObservation("o", "p", "reported_technical_extraction_pct", kind, anchor, "test",
                          original_value=value, original_unit=unit, context=ObservationContext(),
                          evidence_anchors=(anchor,))


class ObservationQualityTests(unittest.TestCase):
    def test_frozen_partitions_exclude_shared_project_family_and_edition(self):
        fixture = json.loads((ROOT / FRAME).read_bytes())
        _validate_frame(fixture)
        for field in ("project_ids", "edition_sha256", "group_id"):
            invalid = deepcopy(fixture)
            development = invalid["partitions"]["DEVELOPMENT"][0]
            evaluation = invalid["partitions"]["EVALUATION"][0]
            if isinstance(evaluation[field], list):
                evaluation[field] += development[field]
            else:
                evaluation[field] = development[field]
            with self.assertRaisesRegex(ValueError, "must be disjoint"):
                _validate_frame(invalid)

    def test_missing_originals_keep_all_expected_pages_and_unmeasured_accuracy(self):
        with TemporaryDirectory() as directory:
            temporary = Path(directory)
            assets, outcome = temporary / "assets", temporary / "quality"
            assets.mkdir()
            report = run(ROOT, assets, outcome)
            evaluation = report["partitions"]["EVALUATION"]
            self.assertEqual(evaluation["source_asset_available"]["denominator"], 3)
            self.assertEqual(evaluation["page_status"], {"SOURCE_BLOCKED": 12})
            self.assertEqual(evaluation["numeric_token_located"]["denominator"], 0)
            self.assertEqual(report["formal_admission"], "NOT_EXECUTED")
            self.assertEqual(evaluation["formal_admission"], "NOT_EXECUTED")
            self.assertIsNone(evaluation["new_official_admissions"])
            self.assertIsNone(report["independent_accuracy"]["precision"])
            self.assertEqual(len((outcome / "pages.jsonl").read_text().splitlines()), 19)

    def test_frozen_comparison_does_not_confuse_source_coverage_with_extraction(self):
        with TemporaryDirectory() as directory:
            temporary = Path(directory)
            originals, before, after = (temporary / name for name in ("assets", "before", "after"))
            originals.mkdir()
            run(ROOT, originals, before)
            copytree(before, after)
            both = compare_fixed(before, after)
            self.assertEqual(both["status"], "SAME_SOURCE_COVERAGE")
            self.assertEqual(both["full_frame"]["baseline"], both["full_frame"]["updated"])
            self.assertEqual(both["formal_admission"], "NOT_EXECUTED")

            asset_file = after / "sources.jsonl"
            assets = [json.loads(line) for line in asset_file.read_bytes().splitlines()]
            assets[0].update(status="SOURCE_VERIFIED", asset_path_present=True)
            replacement = "".join(json.dumps(row) + "\n" for row in assets).encode()
            asset_file.write_bytes(replacement)
            with self.assertRaisesRegex(ValueError, "Unverified fixed quality output"):
                compare_fixed(before, after)

            manifest = after / "quality.json"
            report = json.loads(manifest.read_bytes())
            report["scientific_outputs_sha256"][asset_file.name] = sha256(replacement).hexdigest()
            manifest.write_text(json.dumps(report))
            target = temporary / "difference.json"
            result = compare_fixed(before, after, target)
            self.assertEqual(result["status"], "COVERAGE_CHANGED")
            self.assertEqual(len(result["verified_source_coverage_changes"]), 1)
            self.assertEqual(result["matched_verified_sources"]["updated"]["DEVELOPMENT"]["expected_pages"], 0)
            self.assertEqual(json.loads(target.read_bytes()), result)

            report["frame_sha256"] = "different"
            manifest.write_text(json.dumps(report))
            with self.assertRaisesRegex(ValueError, "changed partitions separately"):
                compare_fixed(before, after)

    def test_explicit_source_location_and_parser_conflict(self):
        source = "Header\nRecovery achieved was 70% after treatment."
        quote = source.splitlines()[1]
        quote_start = source.index(quote)
        start = source.index("70")
        anchor = EvidenceAnchor("test", SHA, page=1, quote=quote, role="token",
                                text_span=TextSpan("PAGE", "MUPDF_POSITIONED", start, start + 2, quote_start))
        raw = _raw(anchor)
        joined = {"MUPDF_POSITIONED": source, "PYPDF_NATIVE": source}
        self.assertTrue(_numeric_location(raw, {}, joined)["unit_bound"])
        disagreement = {**joined, "PYPDF_NATIVE": source.replace("70%", "90%")}
        self.assertEqual(_numeric_location(raw, {}, disagreement)["status"], "PARSER_NUMERIC_CONFLICT")
        moved = {**joined, "MUPDF_POSITIONED": " " + source}
        self.assertEqual(_numeric_location(raw, {}, moved)["status"], "TEXT_SPAN_SOURCE_MISMATCH")

    def test_table_unit_binds_to_the_geometric_column_and_continuation_stays_unresolved(self):
        source = "Recovery %\nOther ppm\nComposite A 70 25"
        target = [10, 10, 20, 20]
        anchor = EvidenceAnchor("test", SHA, page=1, table=0, row=1, column=1,
                                quote="70", bbox=tuple(target), role="token")
        table = {"physical_page": 1, "table_index": 0,
                 "cells": [["Sample", "Recovery %", "Other ppm"], ["Composite A", "70", "25"]],
                 "rows": [[[0, 0, 10, 10], [10, 0, 20, 10], [20, 0, 30, 10]],
                          [[0, 10, 10, 20], target, [20, 10, 30, 20]]]}
        page = {"tables": [table]}
        views = {"MUPDF_POSITIONED": source}
        self.assertTrue(_numeric_location(_raw(anchor), page, views)["unit_bound"])
        wrong_unit = _numeric_location(_raw(anchor, unit="ppm"), page, views)
        self.assertTrue(wrong_unit["numeric_bound"])
        self.assertFalse(wrong_unit["unit_bound"])
        unit = EvidenceAnchor("test", SHA, page=1, table=0, row=0, column=1,
                              quote="Recovery %", bbox=(10, 0, 20, 10), role="unit")
        with_unit = replace(_raw(anchor), evidence_anchors=(anchor, unit))
        self.assertEqual(_numeric_location(with_unit, page, views)["status"], "TABLE_CELL_AND_EXPLICIT_HEADER_BOUND")
        for wrong in (replace(unit, sha256="8" * 64), replace(unit, column=2), replace(unit, row=1),
                      replace(unit, bbox=(20, 0, 30, 10))):
            misplaced = replace(with_unit, evidence_anchors=(anchor, wrong))
            location = _numeric_location(misplaced, page, views)
            self.assertEqual(location["status"], "TABLE_UNIT_WITNESS_MISMATCH")
            self.assertTrue(location["numeric_bound"])
            self.assertFalse(location["unit_bound"])
        table["continuation_candidate"] = {"physical_page": 0, "table_index": 0}
        self.assertEqual(_numeric_location(_raw(anchor), page, views)["status"],
                         "CONTINUATION_HEADER_REPEATED_SCOPE_UNCONFIRMED")

    def test_arithmetic_does_not_mistake_rounding_for_conflict(self):
        candidate = {"kind": "RESOURCE_TABLE_TOTAL", "rounding_bounds_kt": [10.3, 10.4],
                     "values": {"contained_treo_kt": 10}, "original_tokens": ["100", "0.01", "10"],
                     "header": "Tonnes (Mt) | TREO (%) | TREO (kt)"}
        self.assertEqual(_arithmetic(candidate), "WITHIN_REPORTED_PRECISION")
        self.assertEqual(_arithmetic({**candidate, "rounding_bounds_kt": [10.6, 10.9]}), "REPORTED_CONTAINED_CONFLICT")

    def test_literally_reported_but_unbound_quantity_is_retained(self):
        text = "In 2023, a test targeted 70%; Nd2O3 was written on page 12."
        gaps = _quantity_literal_gaps({"MUPDF_POSITIONED": text}, "MUPDF_POSITIONED", ())
        self.assertEqual([item["text"] for item in gaps], ["70%"])
        event = _raw(EvidenceAnchor("test", SHA, page=1, quote="Commissioning did not occur."),
                     kind="EVENT", value=None, unit=None)
        self.assertEqual(_event_stance(event), "NEGATED")
