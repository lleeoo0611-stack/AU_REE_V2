"""Measure unit compatibility using only observations already admitted to the Census."""

import json
from collections import Counter, defaultdict
from decimal import Decimal
from itertools import combinations
from pathlib import Path

from au_ree_v2.tabular import read_csv


from au_ree_v2.resource_use import (
    CATEGORIES, DIRECT_METHODS, FIELDS, NUMBER, _admit, _equal, _keyed, _positive,
    diagnose_admission, direct_cell, selected_pdf_sources,
)


def _pair_report(rows):
    by_field = defaultdict(list)
    for row in rows:
        by_field[row["column"]].append(row)
    combined = defaultdict(set)
    by_column = {}
    for column in FIELDS:
        pairs = defaultdict(set)
        for left, right in combinations(by_field[column], 2):
            pair = tuple(sorted((left["project_id"], right["project_id"])))
            if pair[0] == pair[1] or left["category"] != right["category"]:
                continue
            for stage in ("native_unit", "observation_unit", "census_unit"):
                if left[stage] == right[stage]:
                    pairs[stage].add(pair)
        by_column[column] = {"eligible_projects": len({r["project_id"] for r in by_field[column]})}
        for stage in ("native_unit", "observation_unit", "census_unit"):
            by_column[column][stage] = len(pairs[stage])
            combined[stage].update(pairs[stage])
    return {
        "by_column": by_column,
        "distinct_project_pairs_any_field": {stage: len(pairs) for stage, pairs in combined.items()},
        "distinct_pairs_added_from_native_to_census": len(combined["census_unit"] - combined["native_unit"]),
        "distinct_pairs_lost_from_native_to_census": len(combined["native_unit"] - combined["census_unit"]),
    }


def compare_release(release_dir):
    """Audit units in selected rows of frozen published exports, without any ingestion."""
    source = Path(release_dir)
    observations = _keyed(read_csv(source / "resource_statement_observations.csv"), "observation_id")
    census = _keyed(read_csv(source / "REE project census.csv"), "專案ID")
    approved = selected_pdf_sources(source)
    eligible, exclusions = [], Counter()
    seen = set()
    for cell in read_csv(source / "resource_statement_lineage.csv"):
        column = cell["column"]
        if column not in FIELDS:
            continue
        project = cell["project_id"]
        if (project, column) in seen:
            raise ValueError(f"Duplicate resource lineage cell: {project}, {column}")
        seen.add((project, column))
        obs, canonical_value, reason = direct_cell(cell, census, observations)
        if reason:
            exclusions[reason] += 1
            continue
        record = _admit(obs, cell, approved, canonical_value)
        if record is None:
            exclusions["native_unit_source_context_or_numeric_gate"] += 1
            continue
        eligible.append(record)
    return {
        "scope": "Unit compatibility for directly reported, selected, in-cutoff PDF resource fields in matching resource categories. Project-specific cutoffs, estimation dates, moisture and TREO definitions may differ.",
        "stages": {"native_unit": "Exact original unit string",
                   "observation_unit": "Exact exported observation unit",
                   "census_unit": "Already published Census unit verified against the original token"},
        "eligibility": {"included_cells": len(eligible), "excluded_selected_cells": dict(sorted(exclusions.items()))},
        **_pair_report(eligible),
        "observations": sorted(eligible, key=lambda r: (r["column"], r["project_id"])),
    }
