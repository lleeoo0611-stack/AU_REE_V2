"""Evaluate normalization against the existing Phase 22 Census exports and frozen PDFs."""

import argparse
from collections import Counter
from decimal import Decimal
import json
from pathlib import Path
import re
import unicodedata

import pymupdf

from au_ree_v2.store import filehash
from au_ree_v2.tabular import read_csv
from tools.category_grades import run as category_grade_comparison
from tools.compare_census_release import index, release
from tools.normalization_comparison import compare_release, selected_pdf_sources

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "results/ree-project-census/gap173-20261122"
PILOT = ROOT / "results/normalization-pilot-20261125"


def document_pages(folder, fixture, assets):
    """Bind every reviewed page to a dated, verified PDF in the canonical receipt."""
    cutoff = fixture["cutoff"]
    allowed = selected_pdf_sources(folder)
    refs = set()
    text_pages = 0
    for sha, pages in fixture["documents"].items():
        if not re.fullmatch(r"[a-f0-9]{64}", sha) or allowed.get(sha) != cutoff:
            raise ValueError(f"Unverified source or cutoff: {sha}")
        for number in pages:
            if int(number) < 1:
                raise ValueError(f"Invalid physical page: {sha}:{number}")
            refs.add(f"{sha}:{number}")
        if assets is None:
            continue
        pdf = assets / sha
        if filehash(pdf) != sha:
            raise ValueError(f"Original PDF changed: {sha}")
        with pymupdf.open(pdf) as doc:
            for number, evidence in pages.items():
                page = doc[int(number) - 1]
                # NFKC permits a PDF's subscript digits and nonbreaking spaces.
                text = " ".join(unicodedata.normalize("NFKC", page.get_text()).split()).casefold()
                for marker in evidence["markers"]:
                    expected = " ".join(unicodedata.normalize("NFKC", marker).split()).casefold()
                    if expected not in text:
                        raise ValueError(f"Expected marker missing on {sha}:{number}: {marker!r}")
                if evidence["markers"]:
                    text_pages += 1
    return refs, text_pages


def check_cases(baseline, current, fixture, refs):
    prior = index([r for r in read_csv(baseline / "followup_review.csv")
                   if r["class"] in {"D1", "E1"} and r["outcome"] == "HELD"], ("project_id", "column"))
    tested = set()
    outcomes = Counter()
    reasons = Counter()
    for case in fixture["cases"]:
        if not case["pages"] or not set(case["pages"]) <= refs:
            raise ValueError(f"Unregistered case evidence: {case['project_id']}")
        for column in case["columns"]:
            key = (case["project_id"], column)
            if key in tested or key not in prior or prior[key]["class"] != case["group"]:
                raise ValueError(f"Unexpected or duplicated reviewed cell: {key}")
            if current["states"].get(key) != "UNKNOWN":
                raise ValueError(f"Reviewed hold disagrees with current release: {key}")
            tested.add(key)
            outcomes[case["group"]] += 1
            reasons[(case["group"], case["reason"])] += 1
    if tested != prior.keys():
        raise ValueError("Review omitted baseline D1/E1 cells")
    return {"held_by_class": dict(sorted(outcomes.items())),
            "held_by_reason": [{"class": group, "reason": reason, "cells": n}
                               for (group, reason), n in sorted(reasons.items())]}


def check_controls(current, observations, fixture, refs):
    keys = set()
    for control in fixture["controls"]:
        pid = control["project_id"]
        key = (pid, control.get("column") or control["variable"])
        if key in keys:
            raise ValueError(f"Duplicated positive control: {key}")
        keys.add(key)
        pages = control["pages"]
        if not pages or not set(pages) <= refs:
            raise ValueError(f"Unregistered positive control evidence: {pid}")
        sources = {ref.split(":")[0] for ref in pages}
        if "column" in control:
            key = (pid, control["column"])
            if not sources.intersection(current["trace"][key]["source_sha256"].split(";")):
                raise ValueError(f"Positive control missing source lineage: {key}")
            actual = current["cells"][key]
        else:
            candidates = [r for r in observations if r["project_id"] == pid and r["variable"] == control["variable"]
                          and r["unit"] == control["unit"] and r["source_sha256"] in sources
                          and r["selected_for_census"] == "1" and f"{r['source_sha256']}:{r['physical_page']}" in pages]
            if len(candidates) != 1:
                raise ValueError(f"Missing or ambiguous positive observation: {pid} {control['variable']}")
            actual = candidates[0]["value"]
        if not actual or Decimal(actual) != Decimal(str(control["expected"])):
            raise ValueError(f"Positive control differs: {control}")
    return len(keys)


def evaluate(baseline, folder, fixture, assets):
    current = release(folder)
    if current["manifest"]["cutoff"] != fixture["cutoff"]:
        raise ValueError("Release cutoff differs from the original review")
    refs, text_pages = document_pages(folder, fixture, assets)
    findings = check_cases(baseline, current, fixture, refs)
    observed = read_csv(folder / "resource_statement_observations.csv")
    controls = check_controls(current, observed, fixture, refs)
    coverage = json.loads((folder / "coverage.json").read_bytes())["gap_review"]
    base_coverage = json.loads((baseline / "coverage.json").read_bytes())["gap_review"]
    if coverage["baseline_applicable"] != base_coverage["baseline_applicable"]:
        raise ValueError("The frozen coverage denominator changed")
    return {"cutoff": fixture["cutoff"], "census_sha256": current["manifest"]["census_csv_sha256"],
            "coverage": {"before": base_coverage["filled_within_baseline"],
                         "after": coverage["filled_within_baseline"], "denominator": coverage["baseline_applicable"],
                         "remaining_applicable_blanks": sum(s == "UNKNOWN" for s in current["states"].values())},
            "review": {**findings, "positive_controls": controls, "documents": len(fixture["documents"]),
                       "reviewed_pages": len(refs), "pdf_bytes_checked": assets is not None,
                       "native_text_pages_checked": text_pages},
            "unit_comparison": compare_release(folder)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release", type=Path, default=BASELINE, help="Published or replayed Census directory")
    parser.add_argument("--assets", type=Path, required=True, help="Existing hash-named frozen PDF directory")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    fixture = json.loads((PILOT / "case_review.json").read_bytes())
    report = evaluate(BASELINE, args.release, fixture, args.assets)
    unit_sources = {row["source_sha256"] for row in report["unit_comparison"]["observations"]}
    for sha in sorted(unit_sources):
        if not re.fullmatch(r"[a-f0-9]{64}", sha) or filehash(args.assets / sha) != sha:
            raise ValueError(f"Original from unit comparison changed: {sha}")
    report["unit_comparison"]["verified_pdf_count"] = len(unit_sources)
    report["category_grade_comparison"] = category_grade_comparison(args.release, args.assets)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
