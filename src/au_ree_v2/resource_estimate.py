"""Compare source-bound resource estimates without treating missing facts as matches."""

import json
import re

from .normalization import cutoff_signature, date_precision, normalize_cutoff, overlapping_month_and_day
from .store import digest


VERSION = "resource-estimate-context-v3"
_COMPLETABLE = frozenset({"cutoff_grade", "scope_coverage", "deposit_id", "material_basis", "denominator_basis",
                          "resource_type", "reporting_standard"})
_CONTEXT_DIMENSIONS = (
    "project_id", "deposit", "scope", "scope_coverage", "resource_type", "reporting_standard", "category", "effective_date",
    "cutoff_grade", "material_basis", "chemical_basis", "denominator_basis",
)
_TABLE_LABEL = re.compile(r"\btable\s*(\d+(?:\.\d+)*[a-z]?)\b", re.I)


def _label(value):
    return " ".join(str(value).split()) if value is not None else ""


def _tag(value):
    tag = re.sub(r"[ -]+", "_", _label(value)).upper()
    return tag if tag not in {"", "UNKNOWN", "UNSPECIFIED", "UNRESOLVED", "N/A", "NONE"} else None


def _payload(row):
    raw = row.get("raw")
    try:
        raw = json.loads(raw) if isinstance(raw, str) else raw
    except ValueError:
        return {}
    return raw if isinstance(raw, dict) else {}


def reported_resource_table_label(text):
    """Read one report's printed table identifier, preserving subtable suffixes."""
    labels = {match.casefold() for match in _TABLE_LABEL.findall(text or "")}
    return next(iter(labels)) if len(labels) == 1 else None


def resource_location_context(observation):
    """Get the physical page and printed table from the scope witness."""
    row = dict(observation)
    raw = _payload(row)
    native = raw.get("source_bound_observation") or {}
    scope_labels = {label for anchor in native.get("evidence_anchors", ()) if anchor.get("role") == "scope"
                    and (label := reported_resource_table_label(anchor.get("quote"))) is not None}
    label = next(iter(scope_labels)) if len(scope_labels) == 1 else (
        reported_resource_table_label(row.get("locator")) if not scope_labels else None)
    return {"physical_page": raw.get("pdf_page"), "printed_table": label}


def _completion_fields(row, raw, completion):
    if not isinstance(completion, dict) or completion.get("rule") != "PINNED_NATIVE_RESOURCE_ROW":
        return {}
    if (completion.get("legacy_observation_id") != row.get("obs_id")
            or completion.get("legacy_raw_sha256") != digest(raw)
            or completion.get("source_sha256") != row.get("source_sha")
            or completion.get("physical_page") != raw.get("pdf_page")
            or type(completion.get("physical_page")) is not int):
        return {}
    evidence = completion.get("evidence")
    if (not isinstance(evidence, dict) or not re.fullmatch(r"[0-9a-f]{64}", raw.get("page_extraction_sha256") or "")
            or evidence.get("legacy_page_artifact_sha256") != raw["page_extraction_sha256"]
            or not isinstance(evidence.get("pinned_row_quote"), str) or not evidence["pinned_row_quote"].strip()
            or evidence.get("printed_table") != reported_resource_table_label(row.get("locator"))
            or not evidence.get("printed_table")):
        return {}
    native_anchors = evidence.get("native_anchors")
    if not isinstance(native_anchors, list) or not {"scope", "row"} <= {
            anchor.get("role") for anchor in native_anchors if isinstance(anchor, dict)
            and anchor.get("sha256") == row.get("source_sha") and anchor.get("page") == raw.get("pdf_page")
            and anchor.get("quote") and anchor.get("bbox")}:
        return {}
    fields = completion.get("fields")
    if not isinstance(fields, dict) or fields.keys() - _COMPLETABLE:
        return {}
    return fields


def resource_estimate_context(observation, completion=None):
    """Read scientific dimensions, preferring every explicitly published field."""
    row = dict(observation)
    raw = _payload(row)
    completed = _completion_fields(row, raw, completion)
    nested = raw.get("source_bound_observation") or {}
    review = raw.get("review_contract") or (raw.get("raw") or {}).get("review_contract") or {}

    def context(*values):
        return next((value for value in values if value is not None and value != ""), None)

    cutoff_values = [value for value in (raw.get("cutoff_grade"), raw.get("cutoff"), review.get("cutoff"))
                     if value is not None and value != ""]
    if not cutoff_values and completed.get("cutoff_grade") is not None:
        cutoff_values = [completed["cutoff_grade"]]
    cutoffs = [normalize_cutoff(value) for value in cutoff_values]
    cutoff_keys = {cutoff_signature(value) for value in cutoffs}
    cutoff = cutoffs[0] if len(cutoff_keys) == 1 and cutoffs[0] else None
    scope_coverage = _tag(context(raw.get("scope_coverage"), completed.get("scope_coverage")))
    resource_type = _tag(context(raw.get("resource_type"), raw.get("statement_kind"), completed.get("resource_type")))
    if resource_type in {"RESOURCE", "MRE", "MINERAL_RESOURCE"}:
        resource_type = "MINERAL_RESOURCE"
    reporting_standard = _tag(context(raw.get("reporting_standard"), review.get("reporting_standard"),
                                      completed.get("reporting_standard")))
    scope = _label(row.get("scope")).casefold() or None
    deposit_id = context(raw.get("deposit_id"), nested.get("deposit_id"), completed.get("deposit_id"))
    deposit = {"id": str(deposit_id)} if deposit_id else (
        {"kind": "PROJECT_SCOPE", "scope": scope} if scope and scope_coverage == "PROJECT_TOTAL" else None)
    material = _tag(context(raw.get("material_basis"), nested.get("material_basis"), completed.get("material_basis")))
    if material in {"WHOLE_ORE", "BULK_ORE", "RESOURCE_BULK_ORE", "RESOURCE_ORE"}:
        material = "BULK_ORE"
    denominator = _tag(context(raw.get("composition_denominator_basis"), raw.get("denominator_basis"),
                               nested.get("denominator_basis"), completed.get("denominator_basis")))
    if denominator in {"WHOLE_ORE", "BULK_ORE", "RESOURCE_BULK_ORE", "RESOURCE_BULK_ORE_MASS"}:
        denominator = "BULK_ORE_MASS"
    reported_bases = {_tag(basis) for basis in (row.get("basis"), raw.get("chemical_basis"), nested.get("chemical_basis")) if basis}
    chemical = next(iter(reported_bases)) if len(reported_bases) == 1 else None
    date = row.get("effective_date")
    precision = date_precision(date)
    declared_precision = context(raw.get("effective_date_precision"), review.get("date_precision"))
    date_role = context(raw.get("effective_date_role"), raw.get("date_role"), review.get("effective_date_role"))
    return {"project_id": row.get("entity_id"), "deposit": deposit, "scope": scope, "scope_coverage": scope_coverage,
            "resource_type": resource_type, "reporting_standard": reporting_standard,
            "category": _tag(row.get("category")), "effective_date": date, "cutoff_grade": cutoff,
            "effective_date_precision": precision if not declared_precision or declared_precision == precision else None,
            "effective_date_role": date_role,
            "chemical_basis": chemical, "material_basis": material, "denominator_basis": denominator}


def is_jorc_mineral_resource(observation):
    context = resource_estimate_context(observation)
    return context['resource_type'] == 'MINERAL_RESOURCE' and context['reporting_standard'] == 'JORC'


def compare_resource_estimates(left_row, right_row, *, left_completion=None, right_completion=None, compare_date=True):
    """Require explicit equivalent context on both sides of a new scientific link."""
    left = resource_estimate_context(left_row, left_completion)
    right = resource_estimate_context(right_row, right_completion)
    issues = []
    for dimension in _CONTEXT_DIMENSIONS:
        if dimension == "effective_date" and not compare_date:
            continue
        a, b = left[dimension], right[dimension]
        if a is None or b is None or a == "" or b == "":
            reason = "ESTIMATE_CONTEXT_UNRESOLVED"
        elif dimension == "effective_date" and (
                left["effective_date_precision"] is None or right["effective_date_precision"] is None
                or overlapping_month_and_day(a, b)):
            reason = "ESTIMATE_EFFECTIVE_DATE_PRECISION_INSUFFICIENT_FOR_EQUIVALENCE"
        elif dimension == "effective_date" and a == b and left["effective_date_precision"] == "MONTH" and (
                not left["effective_date_role"] or left["effective_date_role"] != right["effective_date_role"]):
            reason = "ESTIMATE_EFFECTIVE_DATE_ROLE_UNRESOLVED"
        elif (cutoff_signature(a) if dimension == "cutoff_grade" else a) != (
                cutoff_signature(b) if dimension == "cutoff_grade" else b):
            reason = "DIFFERENT_ESTIMATE_CONTEXT"
        else:
            continue
        issues.append({"dimension": dimension, "reason": reason, "left": a, "right": b})
    status = ("INCOMPATIBLE" if any(row["reason"] == "DIFFERENT_ESTIMATE_CONTEXT" for row in issues)
              else "UNRESOLVED" if issues else "EQUIVALENT")
    return {"version": VERSION, "status": status, "issues": issues, "left": left, "right": right}


def resource_evidence_locations(rows):
    locations = []
    for row in rows:
        if row is None:
            continue
        row = dict(row)
        raw = _payload(row)
        witness = (raw.get("source_bound_observation") or {}).get("evidence") or {}
        locations.append({"observation_id": row.get("obs_id"), "source_sha256": row.get("source_sha"),
                          "statement_id": row.get("statement_id"), "bundle_id": raw.get("admission_bundle_id"),
                          "locator": row.get("locator"), "physical_page": witness.get("page", raw.get("pdf_page")),
                          "table": witness.get("table"), "row": witness.get("row"), "column": witness.get("column"),
                          "bbox": witness.get("bbox")})
    return locations
