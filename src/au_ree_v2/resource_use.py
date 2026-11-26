"""Source-bound resource admission for the existing declared comparison use."""

import json
from decimal import Decimal

from .normalization import MASS_FRACTION, MASS_IN_TONNES, NUMBER, decimal_token, unit_factor
from .selection_rules import date_end
from .tabular import read_csv


# Convert to the published column units. Material fractions are deliberately absent.
FIELDS = {
    "礦石蘊藏量_Mt": ("ore_mt", "Mt", {u: format(unit_factor(u, "Mt", MASS_IN_TONNES), "f")
                                      for u in ("t", "kt", "Mt")}),
    "TREO品位_pct": ("grade", "%", {u: format(unit_factor(u, "%", MASS_FRACTION), "f")
                                   for u in ("ppm", "%")}),
    "總TREO蘊藏量_kt": ("contained_treo_kt", "kt TREO", {
        u: format(unit_factor(u, "kt TREO", MASS_IN_TONNES), "f") for u in ("kg", "t", "t TREO", "kt", "kt TREO")
    }),
}
DIRECT_METHODS = {"ore_mt": "SAME_SOURCE_STATEMENT_SCOPE_DATE",
                  "grade": "SAME_SOURCE_STATEMENT_SCOPE_DATE", "contained_treo_kt": "REPORTED"}
CATEGORIES = {"MEASURED", "INDICATED", "INFERRED", "MEASURED_INDICATED_TOTAL",
              "MEASURED_INFERRED_TOTAL", "INDICATED_INFERRED_TOTAL", "MEASURED_INDICATED_INFERRED_TOTAL"}
def _positive(token, unit):
    number = decimal_token(token, unit)
    return number if number is not None and number > 0 else None


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


def diagnose_admission(obs, lineage, verified_sources, published):
    """Return the original admission and its first failing check, in evaluation order."""
    column = lineage["column"]
    variable, unit, factors = FIELDS[column]
    native = obs["original_unit"]
    stored = obs["unit"]
    if obs["selected_for_census"] != "1" or obs["selection_role"] != "MATCHED_SELECTED_STATEMENT":
        return None, "NOT_MATCHED_SELECTED_STATEMENT"
    if obs["statement_kind"] != "RESOURCE_CONTEXT" or obs["category"] not in CATEGORIES:
        return None, "RESOURCE_KIND_OR_CATEGORY"
    if obs["basis"] != "TREO" or obs["material_basis"] or obs["denominator_basis"]:
        return None, "CHEMICAL_MATERIAL_OR_DENOMINATOR_BASIS"
    if obs["source_transform"] or obs["variable"] != variable:
        return None, "TRANSFORMED_VALUE_OR_DIFFERENT_QUANTITY"
    if obs["project_id"] != lineage["project_id"] or obs["statement_group_id"] != lineage["statement_group_id"]:
        return None, "PROJECT_OR_STATEMENT_GROUP_MISMATCH"
    if obs["source_sha256"] not in verified_sources or obs["source_sha256"] != lineage["source_sha256"]:
        return None, "SOURCE_NOT_VERIFIED_OR_MISMATCH"
    if not all(obs[k] for k in ("scope", "locator", "effective_date", "statement_id", "statement_group_id")):
        return None, "INCOMPLETE_STATEMENT_CONTEXT"
    if date_end(obs["effective_date"]) > verified_sources[obs["source_sha256"]]:
        return None, "RESOURCE_EFFECTIVE_AFTER_CUTOFF"
    key = json.loads(obs["source_statement_key"])
    if (obs["source_statement_key"] not in json.loads(lineage["source_statement_keys"])
            or key[:6] != [obs[k] for k in ("project_id", "source_sha256", "statement_id",
                                           "scope", "effective_date", "statement_kind")]):
        return None, "SOURCE_STATEMENT_KEY_MISMATCH"
    if native not in factors or stored not in factors:
        return None, "MISSING_OR_UNSUPPORTED_UNIT"
    original = _positive(obs["original_token"], native)
    stored_value = _positive(obs["value"], stored)
    if original is None or stored_value is None:
        return None, "NONPOSITIVE_OR_UNBOUND_NUMERIC_TOKEN"
    canonical = original * Decimal(factors[native])
    if not (_equal(canonical, stored_value * Decimal(factors[stored])) and _equal(canonical, published)):
        return None, "ORIGINAL_STORED_PUBLISHED_DISAGREE"
    return {"project_id": obs["project_id"], "column": column, "category": obs["category"],
            "observation_id": obs["observation_id"], "source_sha256": obs["source_sha256"],
            "native_unit": native, "observation_unit": stored, "census_unit": unit}, None


def _admit(obs, lineage, verified_sources, published):
    return diagnose_admission(obs, lineage, verified_sources, published)[0]


def direct_cell(cell, census, observations):
    """Resolve a published cell's direct observation, before testing its units/context."""
    column = cell["column"]
    if cell["method"] != DIRECT_METHODS[FIELDS[column][0]] or json.loads(cell["unresolved_support_ids"]):
        return None, None, "derived_or_unresolved"
    canonical_value = _positive(census[cell["project_id"]][column], FIELDS[column][1])
    if canonical_value is None or not _equal(canonical_value, Decimal(cell["value"])):
        raise ValueError(f"Resource lineage disagrees with Census: {cell['project_id']}, {column}")
    observation_ids = set(json.loads(cell["selected_resource_observation_ids"]))
    observation_ids.intersection_update(json.loads(cell["supporting_observation_ids"]))
    direct = [observations[identifier] for identifier in sorted(observation_ids)
              if observations[identifier]["variable"] == FIELDS[column][0]]
    if len(direct) != 1:
        return None, canonical_value, "missing_or_ambiguous_direct_observation"
    return direct[0], canonical_value, None
