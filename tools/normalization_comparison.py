"""Measure unit compatibility using only observations already admitted to the Census."""

import json
import re
from collections import Counter, defaultdict
from decimal import Decimal
from itertools import combinations
from pathlib import Path

from au_ree_v2.selection_rules import date_end
from au_ree_v2.tabular import read_csv


# Convert to the published column units. Material fractions are deliberately absent.
FIELDS = {
    "礦石蘊藏量_Mt": ("ore_mt", "Mt", {"t": "0.000001", "kt": "0.001", "Mt": "1"}),
    "TREO品位_pct": ("grade", "%", {"ppm": "0.0001", "%": "1"}),
    "總TREO蘊藏量_kt": (
        "contained_treo_kt", "kt TREO",
        {"kg": "0.000001", "t": "0.001", "t TREO": "0.001", "kt": "1", "kt TREO": "1"},
    ),
}
DIRECT_METHODS = {"ore_mt": "SAME_SOURCE_STATEMENT_SCOPE_DATE",
                  "grade": "SAME_SOURCE_STATEMENT_SCOPE_DATE", "contained_treo_kt": "REPORTED"}
CATEGORIES = {"MEASURED", "INDICATED", "INFERRED", "MEASURED_INDICATED_TOTAL",
              "MEASURED_INFERRED_TOTAL", "INDICATED_INFERRED_TOTAL", "MEASURED_INDICATED_INFERRED_TOTAL"}
NUMBER = re.compile(r"(?:[0-9]+|[0-9]{1,3}(?:,[0-9]{3})+)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?")


def _positive(token, unit):
    if unit == "%" and token.endswith("%"):
        token = token[:-1].strip()
    if not NUMBER.fullmatch(token):
        return None
    number = Decimal(token.replace(",", ""))
    return number if number > 0 else None


def _equal(left, right):
    return abs(left - right) <= max(abs(left), abs(right)) * Decimal("1e-12")


def selected_pdf_sources(directory):
    cutoff = json.loads((directory / "census_release.json").read_bytes())["cutoff"]
    return {row["source_sha256"]: cutoff for row in read_csv(directory / "source_selection.csv")
            if row["kind"] == "pdf" and row["cutoff"] == cutoff and row["cutoff_status"] == "WITHIN_CUTOFF"
            and row["version_status"] in {"PINNED_SHA_VERIFIED", "RECEIPT_SHA_VERIFIED"}}


def _keyed(rows, key):
    result = {}
    for row in rows:
        identifier = row[key]
        if not identifier or identifier in result:
            raise ValueError(f"Missing or duplicate {key}: {identifier!r}")
        result[identifier] = row
    return result


def _admit(obs, lineage, verified_sources, published):
    column = lineage["column"]
    variable, unit, factors = FIELDS[column]
    native = obs["original_unit"]
    stored = obs["unit"]
    if (obs["selected_for_census"] != "1" or obs["selection_role"] != "MATCHED_SELECTED_STATEMENT"
            or obs["statement_kind"] != "RESOURCE_CONTEXT" or obs["basis"] != "TREO"
            or obs["category"] not in CATEGORIES or obs["material_basis"] or obs["denominator_basis"]
            or obs["source_transform"] or obs["variable"] != variable):
        return None
    if (obs["project_id"] != lineage["project_id"] or obs["statement_group_id"] != lineage["statement_group_id"]
            or obs["source_sha256"] not in verified_sources or obs["source_sha256"] != lineage["source_sha256"]
            or not all(obs[k] for k in ("scope", "locator", "effective_date", "statement_id", "statement_group_id"))):
        return None
    if date_end(obs["effective_date"]) > verified_sources[obs["source_sha256"]]:
        return None
    key = json.loads(obs["source_statement_key"])
    if (obs["source_statement_key"] not in json.loads(lineage["source_statement_keys"])
            or key[:6] != [obs[k] for k in ("project_id", "source_sha256", "statement_id",
                                           "scope", "effective_date", "statement_kind")]):
        return None
    if native not in factors or stored not in factors:
        return None
    original = _positive(obs["original_token"], native)
    stored_value = _positive(obs["value"], stored)
    if original is None or stored_value is None:
        return None
    canonical = original * Decimal(factors[native])
    if not (_equal(canonical, stored_value * Decimal(factors[stored])) and _equal(canonical, published)):
        return None
    return {"project_id": obs["project_id"], "column": column, "category": obs["category"],
            "observation_id": obs["observation_id"], "source_sha256": obs["source_sha256"],
            "native_unit": native, "observation_unit": stored, "census_unit": unit}


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
        if cell["method"] != DIRECT_METHODS[FIELDS[column][0]] or json.loads(cell["unresolved_support_ids"]):
            exclusions["derived_or_unresolved"] += 1
            continue
        canonical_value = _positive(census[project][column], FIELDS[column][1])
        if canonical_value is None or not _equal(canonical_value, Decimal(cell["value"])):
            raise ValueError(f"Resource lineage disagrees with Census: {project}, {column}")
        observation_ids = set(json.loads(cell["selected_resource_observation_ids"]))
        observation_ids.intersection_update(json.loads(cell["supporting_observation_ids"]))
        direct = [observations[identifier] for identifier in sorted(observation_ids)
                  if observations[identifier]["variable"] == FIELDS[column][0]]
        if len(direct) != 1:
            exclusions["missing_or_ambiguous_direct_observation"] += 1
            continue
        record = _admit(direct[0], cell, approved, canonical_value)
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
