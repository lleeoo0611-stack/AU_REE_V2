"""Admit source-bound bulk Mineral Resource facts to the existing evidence store."""

from collections import Counter, defaultdict
from datetime import datetime
from decimal import Decimal, DecimalException
import json
import math
from pathlib import Path
import re

from .derived_cache import code_fingerprint
from .evidence import claim_evidence_ids, ingest_sources, normalize, resource_statement_metrics
from .normalization import MASS_FRACTION, unit_factor
from .numeric_evidence import header_unit_issue, numeric_witness_issue, scalar_decimal, unit_header_matches_value_column
from .observation_schema import RawObservation, VALUE_EVIDENCE_ROLES, payload, value_evidence_issue
from .observation_semantics import SemanticEngine
from .pdf_extract import project_registry
from .resource_estimate import compare_resource_estimates, cutoff_signature, normalize_cutoff
from .resource_estimate import reported_resource_table_label as _table_label
from .resource_jorc import admission_issue as jorc_admission_issue
from .resource_source import (
    _CONTEXT_ROLES, _cutoff, _effective_dates, _estimate_dates_in_context, caption_estimate_periods,
    cutoff_column_declaration, discover, locally_bound_span, resolved_estimate_date, verified_context_anchors,
)
from .selection_rules import RESOURCE_ADMISSION_VERSION, RESOURCE_ADMISSION_VERSION_GLOB, date_end, source_check
from .store import canonical, digest, filehash


SCHEMA = "formal-resource-admission-receipt-v2"
ADMISSION_VERSION = RESOURCE_ADMISSION_VERSION
REQUIRED_QUANTITIES = frozenset({"ore_mt", "grade"})
RESOURCE_QUANTITIES = REQUIRED_QUANTITIES | {"contained_treo_kt"}
MATERIALS = frozenset({"WHOLE_ORE", "BULK_ORE", "RESOURCE_BULK_ORE"})
DENOMINATORS = MATERIALS | {"RESOURCE_BULK_ORE_MASS"}
QUANTITY_UNITS = {"ore_mt": "Mt", "grade": "ppm", "contained_treo_kt": "kt TREO"}


def _scope_conditions(raw):
    return dict(raw.context.conditions)


def _location(anchor):
    return anchor.sha256, anchor.page, anchor.table, anchor.row


def _source_metadata_issue(source, cutoff, root, acquired_through):
    if source is None:
        return "SOURCE_NOT_SELECTED"
    if source.get("kind") != "pdf":
        return "SOURCE_NOT_PINNED_PDF"
    if problem := source_check(source, cutoff, root, acquired_through):
        return problem
    try:
        publication = date_end(source["publication_date"])
        available = date_end(source["available_date"])
        acquisition = datetime.fromisoformat(source["acquired_at"])
        if acquisition.tzinfo is None or publication > available:
            return "SOURCE_TIMING_UNESTABLISHED"
    except (TypeError, ValueError, KeyError):
        return "SOURCE_TIMING_UNESTABLISHED"
    return None


def _authorized_projects(claims, projects, sources):
    """Use only already registered identities and source-edition declarations."""
    registered = {row["entity_id"] for row in projects}
    by_source = defaultdict(set)
    for project in claims["projects"]:
        if project.get("entity_kind", "PROJECT") != "PROJECT":
            continue
        pid = "AU-" + digest([project.get("entity_namespace", "project_registry_v1"), str(project["id"])])[:20]
        if pid not in registered:
            continue
        for observation in project.get("observations", ()):
            if observation.get("source_key") and observation.get("source_sha256"):
                by_source[observation["source_key"], observation["source_sha256"]].add(pid)
    return {
        sha: sorted(registered.intersection(source.get("summary_project_ids") or by_source[source["key"], sha]))
        for sha, source in sources.items()
    }


def _value_disposition(raw, source, selected_row):
    anchor = raw.evidence
    if _location(anchor) != (source["sha256"], *selected_row) or anchor.source_id != source["key"]:
        return "VALUE_SOURCE_OR_ROW_MISMATCH", False, False
    witnesses = tuple(item for item in raw.evidence_anchors if item.role in VALUE_EVIDENCE_ROLES)
    if (len(witnesses) != 1 or type(anchor.column) is not int or not anchor.text_span
            or not anchor.bbox or anchor.bbox[0] >= anchor.bbox[2] or anchor.bbox[1] >= anchor.bbox[3]):
        return "NUMERIC_EVIDENCE_LOCATION_INSUFFICIENT", False, False
    issue = numeric_witness_issue(anchor.quote, raw.original_value, raw.original_unit,
                                  span=anchor.text_span.in_quote, cell=True, token_state=raw.source_value_state)
    if issue:
        return issue, False, False
    headers = [header for header in raw.evidence_anchors if header.role in {"unit", "VALUE_UNIT_HEADER"}]
    if len(headers) != 1:
        return "UNIT_HEADER_NOT_UNIQUELY_BOUND", True, False
    header = headers[0]
    if (header.source_id != source["key"] or _location(header)[:3] != _location(anchor)[:3]
            or not unit_header_matches_value_column(header, anchor) or type(header.row) is not int or header.row >= anchor.row
            or not header.quote or not header.bbox or header.bbox[3] > anchor.bbox[1] + .01):
        return "UNIT_HEADER_SOURCE_OR_COLUMN_MISMATCH", True, False
    if issue := header_unit_issue(header.quote, raw.original_unit):
        return issue, True, False
    if issue := value_evidence_issue(raw, witnesses):
        return issue, True, False
    return None, True, True


def _value_evidence_detail(raw, source, selected_row):
    issue, numeric, unit = _value_disposition(raw, source, selected_row)
    return dict(raw_observation_id=raw.observation_id, raw_id=raw.raw_id,
                numeric_located=numeric, numeric_and_unit_located=unit,
                evidence_status="VERIFIED" if not issue else "UNVERIFIED", evidence_issue=issue,
                raw=payload(raw))


def _attested_text(anchor):
    if anchor.text_span is None:
        return anchor.quote
    start, end = anchor.text_span.in_quote
    return anchor.quote[start:end]


def _cutoff_issue(raw, anchors, row, contextual):
    context = _scope_conditions(raw)
    expected = cutoff_signature(normalize_cutoff(context.get("cutoff_grade") or context.get("cutoff")))
    found = set(_cutoff([*(anchor.quote for anchor in anchors if anchor.role == "scope"),
                         *(_attested_text(anchor) for anchor in contextual if anchor.role == "estimate_cutoff")]))
    for anchor in anchors:
        if anchor.role != "cutoff_value" or anchor.row != row or type(anchor.column) is not int:
            continue
        columns = sorted((header for header in anchors if header.role == "cutoff_header"
                          and header.column == anchor.column and type(header.row) is int and header.row < row
                          and header.bbox[3] <= anchor.bbox[1] + .01), key=lambda header: header.row)
        if matched := cutoff_column_declaration(" ".join(column.quote for column in columns), anchor.quote):
            found.add(matched[0])
    if expected is None or expected[1] != "TREO" or found != {expected}:
        return "RESOURCE_CUTOFF_EVIDENCE_MISMATCH"
    return None


def _group_context(observations, source, project_ids, cutoff, selected_row, *, registry=()):
    first = observations[0]
    if first.project_id not in project_ids:
        return "PROJECT_SOURCE_BINDING_NOT_ESTABLISHED"
    keys = ("project_id", "deposit_id", "scope_id", "statement_id", "estimate_id", "effective_date",
            "chemical_basis", "denominator_basis")
    if any(any(getattr(item, key) != getattr(first, key) for key in keys) for item in observations):
        return "CROSS_PROJECT_SCOPE_STATEMENT_EDITION_OR_BASIS"
    if not all(getattr(first, key) for key in ("scope_id", "statement_id", "estimate_id", "effective_date")):
        return "RESOURCE_STATEMENT_SCOPE_OR_DATE_UNRESOLVED"
    context = _scope_conditions(first)
    for item in observations:
        if issue := jorc_admission_issue(item):
            return issue
    shared = ("category", "resource_type", "scope_coverage", "cutoff_grade", "cutoff", "reporting_standard",
              "effective_date_role", "effective_date_precision")
    if any(any(_scope_conditions(item).get(key) != context.get(key) for key in shared) for item in observations):
        return "RESOURCE_ROW_CONTEXT_CONFLICT"
    if (context.get("resource_type") != "MINERAL_RESOURCE" or context.get("reporting_standard") != "JORC"
            or context.get("scope_coverage") not in {"PROJECT_TOTAL", "DEPOSIT_TOTAL"}
            or not (context.get("cutoff_grade") or context.get("cutoff"))):
        return "RESOURCE_CLASSIFICATION_SCOPE_OR_CUTOFF_UNRESOLVED"
    if any(item.quantity_kind != "RESOURCE" or item.chemical_basis != "TREO" for item in observations):
        return "RESOURCE_QUANTITY_OR_CHEMICAL_BASIS_MISMATCH"
    if any(_scope_conditions(item).get("particle_size_um") is not None for item in observations):
        return "RESOURCE_PARTICLE_SIZE_FRACTION_NOT_COMPARABLE"
    if first.denominator_basis not in DENOMINATORS or any(
            item.material_basis not in MATERIALS and not (item.variable == "contained_treo_kt"
            and item.material_basis == "RESOURCE_CONTAINED_OXIDE_MASS_KT") for item in observations):
        return "RESOURCE_MATERIAL_OR_DENOMINATOR_MISMATCH"
    if (first.effective_date_precision not in {"DAY", "MONTH"}
            or context.get("effective_date_precision") not in {None, first.effective_date_precision}):
        return "RESOURCE_EFFECTIVE_DATE_UNRESOLVED"
    limit = min(date_end(source["publication_date"]), cutoff)
    if first.effective_date > limit:
        return "RESOURCE_EFFECTIVE_DATE_AFTER_DISCLOSURE_OR_CUTOFF"
    if date_end(first.effective_date) > limit:
        return "RESOURCE_EFFECTIVE_DATE_PRECISION_INSUFFICIENT_FOR_TIMING"
    if any((item.publication_date and item.publication_date != source["publication_date"])
           or (item.acquisition_date and item.acquisition_date != source["acquired_at"]) for item in observations):
        return "RESOURCE_SOURCE_TIMING_MISMATCH"
    contextual = set(verified_context_anchors(observations, registry))
    if any(anchor.role in _CONTEXT_ROLES.values() and anchor not in contextual
           for item in observations for anchor in item.evidence_anchors):
        return "RESOURCE_CONTEXT_EVIDENCE_BINDING_MISMATCH"
    for item in observations:
        for anchor in item.evidence_anchors:
            if anchor.role == "estimate_reference" and anchor.locator in {
                    "SCOPED_ADJACENT_ESTIMATE_NOTE", "SAME_NAMED_REPORT_AND_MATCHED_ESTIMATE_SECTION"} and (
                    not anchor.quote or not anchor.text_span or anchor.text_span.in_quote != locally_bound_span(
                        anchor.quote, context.get("reported_table_label"), first.project_id, registry)):
                return "RESOURCE_CONTEXT_EVIDENCE_BINDING_MISMATCH"
        anchors = [anchor for anchor in item.evidence_anchors
                   if anchor.source_id == source["key"] and _location(anchor)[:3] == (source["sha256"], *selected_row[:2])
                   and anchor.quote and anchor.bbox]
        roles = {anchor.role for anchor in anchors}
        if not {"scope", "row"} <= roles:
            return "RESOURCE_SCOPE_OR_ROW_EVIDENCE_MISSING"
        if not any(anchor.role == "row" and anchor.row == selected_row[2] for anchor in anchors):
            return "RESOURCE_ROW_EVIDENCE_MISMATCH"
        explicit_dates = _effective_dates(_attested_text(anchor) for anchor in anchors
                                          if anchor.role in {"scope", "estimate_reference", "resource_section"})
        for anchor in contextual:
            if anchor.role == "estimate_effective_date":
                explicit_dates |= _estimate_dates_in_context(_attested_text(anchor), anchor.locator)
        caption_periods = [(period, anchor.quote[start:end]) for anchor in anchors if anchor.role == "scope"
                           for period, (start, end), _ in caption_estimate_periods(anchor.quote)]
        dates = explicit_dates | {period for period, _ in caption_periods}
        if resolved_estimate_date(dates) != item.effective_date:
            return "RESOURCE_EFFECTIVE_DATE_EVIDENCE_MISMATCH"
        if item.effective_date_precision == "MONTH":
            expected_role = "STATEMENT_EFFECTIVE_DATE" if item.effective_date in explicit_dates else "ESTIMATE_EDITION_DATE"
            if (item.effective_date_role != expected_role
                    or (context.get("original_estimate_date") and
                        (item.effective_date, context["original_estimate_date"]) not in caption_periods)):
                return "RESOURCE_EFFECTIVE_DATE_EVIDENCE_MISMATCH"
        if issue := _cutoff_issue(item, anchors, selected_row[2], contextual):
            return issue
    return None


def _project_values(engine, observations):
    facts = []
    for raw in observations:
        if raw.source_value_state not in {"SCALAR", "NUMBER"}:
            return None, "RESOURCE_VALUE_NOT_SCALAR"
        normalized = engine.normalize(raw, target_unit=QUANTITY_UNITS[raw.variable])
        if normalized is None:
            return None, "RESOURCE_NORMALIZATION_UNRESOLVED"
        original = scalar_decimal(raw.original_value, raw.original_unit)
        if original is None or original <= 0:
            return None, "RESOURCE_NORMALIZATION_OUT_OF_DOMAIN"
        try:
            # The printed resolution and the exact ratio follow the same existing
            # normalizer, so gapped or bounded values never supply a criterion.
            half = (Decimal(5).scaleb(original.as_tuple().exponent - 1) * normalized.value / original)
            value, half_width = float(normalized.value), float(half)
        except (DecimalException, ValueError, OverflowError):
            return None, "RESOURCE_NORMALIZATION_OUT_OF_DOMAIN"
        if not math.isfinite(value) or not math.isfinite(half_width):
            return None, "RESOURCE_NORMALIZATION_OUT_OF_DOMAIN"
        context = _scope_conditions(raw)
        fact = dict(variable=raw.variable, value=value,
                    unit="kt" if raw.variable == "contained_treo_kt" else normalized.unit, basis="TREO",
                    scope=raw.scope_id, statement_id=raw.statement_id, category=context.get("category"),
                    effective_date=raw.effective_date, source_sha=raw.evidence.sha256,
                    locator=f"physical page {raw.evidence.page}; table {raw.evidence.table}; "
                            f"row {raw.evidence.row}; column {raw.evidence.column}",
                    rounding_half_width=half_width, normalized=payload(normalized))
        if reasons := normalize(fact):
            return None, "+".join(reasons)
        facts.append(fact)
    by_variable = {fact["variable"]: {**fact, "raw": canonical(fact)} for fact in facts}
    reported = by_variable.get("contained_treo_kt")
    metrics = resource_statement_metrics(by_variable["ore_mt"], by_variable["grade"], reported)
    if not all(math.isfinite(x) for x in [metrics["calculated_from_rounded_inputs_kt"], *metrics["rounding_bounds_kt"]]):
        return None, "RESOURCE_NORMALIZATION_OUT_OF_DOMAIN"
    lower, upper = metrics["rounding_bounds_kt"]
    if reported and not lower <= reported["value"] <= upper:
        return None, "REPORTED_CONTAINED_CONFLICT"
    return facts, None


def _evaluate(candidate, source, project_ids, cutoff, engine, *, registry=()):
    selected_row = candidate["physical_page"], candidate["table"], candidate["row"]
    observations = tuple(candidate["observations"])
    material_observations = tuple(candidate.get("material_observations", ()))
    if not all(isinstance(raw, RawObservation) for raw in (*observations, *material_observations)):
        raise TypeError("Resource extraction must return typed raw observations")
    issues = list(candidate.get("issues", ()))
    variables = [raw.variable for raw in observations]
    if not REQUIRED_QUANTITIES <= set(variables) <= RESOURCE_QUANTITIES or len(set(variables)) != len(variables):
        issues.append("RESOURCE_SAME_ROW_PAIR_NOT_UNIQUE")
    columns = [raw.evidence.column for raw in observations]
    if len(set(columns)) != len(columns):
        issues.append("RESOURCE_VALUE_COLUMNS_OVERLAP")
    details = [_value_evidence_detail(raw, source, selected_row) for raw in observations]
    material_details = [_value_evidence_detail(raw, source, selected_row) for raw in material_observations]
    issues.extend(item["evidence_issue"] for item in details if item["evidence_issue"])
    bound = {(anchor.role, anchor.sha256, anchor.page, anchor.bbox, anchor.quote, anchor.locator, anchor.text_span.in_quote)
             for anchor in verified_context_anchors(observations, registry)} if observations else set()
    first = observations[0] if observations else None
    claimed = ({**_scope_conditions(first), 'effective_date': first.effective_date,
                'chemical_basis': first.chemical_basis, 'material_basis': first.material_basis,
                'denominator_basis': first.denominator_basis} if first else {})
    gains = {}
    for field, result in candidate.get("context_field_gains", {}).items():
        value = result["value"]
        if (canonical(value) if isinstance(value, dict) else value) != claimed.get(field):
            continue
        verified = []
        for anchor in result["evidence"]:
            if not (span := anchor.get("text_span")):
                continue
            quote_start = span.get("quote_start", 0)
            key = (anchor["field"], anchor.get("source_sha256"), anchor["page"], tuple(anchor["bbox"]),
                   anchor["quote"], anchor["locator"],
                   (span["start"] - quote_start, span["end"] - quote_start))
            if key in bound:
                verified.append(anchor)
        if verified:
            gains[field] = {**result, "evidence": verified}
    if observations and (issue := _group_context(observations, source, project_ids, cutoff, selected_row, registry=registry)):
        issues.append(issue)
    facts = None
    if not issues:
        facts, issue = _project_values(engine, observations)
        if issue:
            issues.append(issue)
    return dict(source_sha256=source["sha256"], source_key=source["key"],
                physical_page=selected_row[0], table=selected_row[1], row=selected_row[2],
                project_id=observations[0].project_id if observations else None,
                candidate_id=candidate.get("candidate_id"), jorc_assessment=candidate.get("jorc_assessment"),
                row_role=candidate.get("row_role"), context_field_gains=gains,
                statement_id=observations[0].statement_id if observations else None,
                estimate_id=observations[0].estimate_id if observations else None,
                status="CANONICAL_ELIGIBLE" if facts else "NOT_ADMITTED", reasons=sorted(set(issues)),
                observations=details, material_observations=material_details,
                canonical_observation_ids=[]), facts, observations


def _same_reported_quantity(legacy, fact):
    if legacy["basis"] != fact["basis"] or legacy["category"] != fact["category"]:
        return False
    if fact["variable"] == "grade" and legacy["unit"] in MASS_FRACTION:
        value = Decimal(str(legacy["value"])) * unit_factor(legacy["unit"], fact["unit"], MASS_FRACTION)
    elif legacy["unit"] == fact["unit"] or fact["variable"] == "contained_treo_kt" and legacy["unit"] == "kt TREO":
        value = Decimal(str(legacy["value"]))
    else:
        return False
    return value == Decimal(str(fact["value"]))


class _HistoricalEstimateHold(ValueError):
    def __init__(self, reason, related, *, equivalence=()):
        super().__init__(reason)
        self.audit = {"reason": reason, "historical_observations": [_legacy_location(row) for row in related],
                      "equivalence": list(equivalence)}


def _legacy_location(row):
    document = json.loads(row["raw"])
    return {"observation_id": row["obs_id"], "source_sha256": row["source_sha"], "locator": row["locator"],
            "physical_page": document.get("pdf_page"), "statement_id": row["statement_id"],
            "scope": row["scope"], "value": row["value"], "unit": row["unit"],
            "page_extraction_sha256": document.get("page_extraction_sha256")}


def _named_scope_matches(extracted, historical):
    def named(text):
        return " ".join(re.sub(r"\bdeposit\s*$", "", text, flags=re.I).casefold().split())

    if named(extracted) == named(historical):
        return True
    # Older locators can describe a single named deposit with explicit
    # exclusions of other deposits and pilot stockpiles. Preserve other qualifiers.
    match = re.fullmatch(r"(.+?)\s+only;\s*excludes\s+(?:pilot(?: plant)? stockpiles and other deposits|"
                         r"other deposits and pilot(?: plant)? stockpiles)", historical.strip(), re.I)
    return bool(match and named(extracted) == named(match[1]))


def _artifact_text(root, legacy, snapshot_index, row, source, label):
    artifact = snapshot_index.get((legacy.get("page_extraction_key"), legacy.get("page_extraction_sha256")))
    if (not artifact or artifact["kind"] != "pdf_page_extraction"
            or artifact.get("source_sha256") != source["sha256"] or artifact.get("physical_page") != row.page):
        return None
    path = root / artifact["path"]
    try:
        if filehash(path) != artifact["sha256"]:
            return None
        parsed = json.loads(path.read_bytes())
    except (OSError, ValueError):
        return None
    if parsed.get("source_sha256") != source["sha256"] or parsed.get("physical_page") != row.page:
        return None
    content = parsed.get("positioned_text") or parsed.get("text") or ""
    tables = list(re.finditer(r"^\s*Table\s+(\d+(?:\.\d+)*[a-z]?)\s*:", content, re.M | re.I))
    indices = [i for i, match in enumerate(tables) if match[1].casefold() == label]
    if len(indices) != 1:
        return None
    index = indices[0]
    region = content[tables[index].start():tables[index + 1].start() if index + 1 < len(tables) else None]
    return region, artifact["sha256"]


def _legacy_completions(root, source, observations, reused, snapshot_index, label):
    """Recover omissions only from a pinned, uniquely identified legacy table row."""
    first = observations[0]
    context = _scope_conditions(first)
    captions = {anchor.quote for anchor in first.evidence_anchors if anchor.role == "scope" and anchor.bbox}
    values = {raw.variable: raw for raw in observations if raw.variable in reused}
    if len(captions) != 1 or not REQUIRED_QUANTITIES <= values.keys():
        return {}
    caption = next(iter(captions))
    clean = lambda value: " ".join(value.casefold().split())
    tokens = [values[variable].original_value for variable in sorted(REQUIRED_QUANTITIES)]
    columns = [r"(?<![\w.,])" + re.escape(token) + r"(?![\w.,])" for token in tokens]
    completed = {}
    for row in reused.values():
        declared = json.loads(row["raw"])
        recovered = _artifact_text(root, declared, snapshot_index, first.evidence, source, label)
        markers = declared.get("page_markers", [])
        if (not recovered or not isinstance(markers, list) or not all(isinstance(m, str) for m in markers)
                or not any(_table_label(marker) == label for marker in markers)
                or any(not any(re.fullmatch(pattern, m.strip()) for m in markers) for pattern in columns)):
            continue
        region, artifact_sha = recovered
        if clean(region).count(clean(caption)) != 1 or any(clean(m) not in clean(region) for m in markers):
            continue
        occurrences = [line.strip() for line in region.splitlines() if re.match(r"\s*Total\b", line, re.I)
                       and all(re.search(pattern, line) for pattern in columns)]
        if len(occurrences) != 1:
            continue
        completed[row["obs_id"]] = {
            "rule": "PINNED_NATIVE_RESOURCE_ROW", "legacy_observation_id": row["obs_id"],
            "legacy_raw_sha256": digest(declared), "source_sha256": source["sha256"],
            "physical_page": first.evidence.page,
            "fields": {"deposit_id": first.deposit_id, "scope_coverage": context.get("scope_coverage"),
                       "material_basis": first.material_basis, "denominator_basis": first.denominator_basis,
                       "cutoff_grade": context.get("cutoff_grade"), "resource_type": context.get("resource_type"),
                       "reporting_standard": context.get("reporting_standard")},
            "evidence": {"legacy_page_artifact_sha256": artifact_sha, "printed_table": label,
                         "pinned_row_quote": occurrences[0], "native_scope": first.scope_id,
                         "native_anchors": [payload(anchor) for anchor in first.evidence_anchors]}}
    return completed


def _estimate_fields(raw):
    context = _scope_conditions(raw)
    return {"deposit_id": raw.deposit_id, "scope_coverage": context.get("scope_coverage"),
            "material_basis": raw.material_basis, "composition_denominator_basis": raw.denominator_basis,
            "cutoff_grade": context.get("cutoff_grade") or context.get("cutoff"),
            "resource_type": context.get("resource_type"), "reporting_standard": context.get("reporting_standard")}


def _historical_statement(db, root, source, observations, facts, active_claim_ids, snapshot_index):
    """Link selected historical observations only after scientific context equivalence."""
    raw = observations[0]
    labels = {_table_label(anchor.quote) for anchor in raw.evidence_anchors if anchor.role == "scope"}
    if len(labels) != 1 or None in labels:
        return None
    label = next(iter(labels))
    facts_by_variable = {fact["variable"]: fact for fact in facts}
    groups = defaultdict(lambda: defaultdict(list))
    for legacy in db.execute("""SELECT * FROM observations WHERE entity_id=? AND source_sha=?
            AND effective_date=? AND status='AUTO_VALIDATED' AND transform_version='normalization-v1'
            AND variable IN ('ore_mt','grade','contained_treo_kt')""",
            (raw.project_id, source["sha256"], raw.effective_date)):
        if legacy["obs_id"] not in active_claim_ids or legacy["variable"] not in facts_by_variable:
            continue
        legacy = dict(legacy)
        reported = json.loads(legacy["raw"])
        if (reported.get("pdf_page") != raw.evidence.page
                or reported.get("source_key") != source["key"]
                or _table_label(legacy["locator"]) != label):
            continue
        groups[legacy["scope"], legacy["statement_id"]][legacy["variable"]].append(legacy)
    paired = [(key, variables) for key, variables in groups.items() if REQUIRED_QUANTITIES <= variables.keys()]
    if not paired:
        return None
    related = [row for _, variables in paired for rows in variables.values() for row in rows]
    if len(paired) != 1:
        raise _HistoricalEstimateHold("HISTORICAL_SOURCE_TABLE_STATEMENT_AMBIGUOUS", related)
    (scope, statement_id), variables = paired[0]
    if any(len(options) != 1 for options in variables.values()):
        raise _HistoricalEstimateHold("HISTORICAL_SOURCE_TABLE_STATEMENT_AMBIGUOUS", related)
    reused = {variable: options[0] for variable, options in variables.items()}
    if not _named_scope_matches(raw.scope_id, scope):
        raise _HistoricalEstimateHold("HISTORICAL_ESTIMATE_SCOPE_UNRESOLVED", related)
    matching_pair = all(_same_reported_quantity(reused[key], facts_by_variable[key]) for key in REQUIRED_QUANTITIES)
    completions = _legacy_completions(root, source, observations, reused, snapshot_index, label) if matching_pair else {}
    by_variable = {item.variable: item for item in observations}
    comparisons = []
    for variable, row in reused.items():
        fact = {**facts_by_variable[variable], "entity_id": raw.project_id, "scope": scope, "statement_id": statement_id,
                "raw": canonical(_estimate_fields(by_variable[variable]))}
        checked = compare_resource_estimates(row, fact, left_completion=completions.get(row["obs_id"]))
        comparisons.append({"observation_id": row["obs_id"], "variable": variable, **checked})
    issues = {check["status"] for check in comparisons} - {"EQUIVALENT"}
    if issues:
        reason = "HISTORICAL_ESTIMATE_CONTEXT_MISMATCH" if "INCOMPATIBLE" in issues else "HISTORICAL_ESTIMATE_CONTEXT_UNRESOLVED"
        raise _HistoricalEstimateHold(reason, related, equivalence=comparisons)
    if not matching_pair:
        return dict(scope=scope, statement_id=statement_id, reported_table_label=label, reused={},
                    equivalence=comparisons, legacy_completion={},
                    conflict={"reason": "CONCURRENT_SAME_ESTIMATE_VALUES",
                              "historical_observations": [_legacy_location(row) for row in related]})
    # A second reported contained value for the same proven estimate remains
    # a competing fact. The selector records both original witnesses.
    kept = {name: row for name, row in reused.items() if _same_reported_quantity(row, facts_by_variable[name])}
    return dict(scope=scope, statement_id=statement_id, reported_table_label=label, reused=kept,
                equivalence=comparisons, legacy_completion=completions)


def _insert_bundle(db, root, source, facts, observations, active_claim_ids, *, snapshot_index=None):
    first = observations[0]
    scope_context = _scope_conditions(first)
    for raw in observations:
        if issue := jorc_admission_issue(raw):
            raise ValueError(issue)
    historical = _historical_statement(db, Path(root), source, observations, facts, active_claim_ids, snapshot_index or {})
    scope, statement = (historical["scope"], historical["statement_id"]) if historical else (first.scope_id, first.statement_id)
    reuse = historical["reused"] if historical else {}
    bundle = digest(["source-bound-resource-statement-v2", first.project_id, source["sha256"],
                     scope, statement, first.effective_date,
                     first.evidence.page, first.evidence.table, first.evidence.row])
    db.execute("SAVEPOINT automatic_resource_bundle")
    try:
        ingest_sources(db, root, [source])
        stored = db.execute("SELECT source_key,publication_date FROM sources WHERE sha=?", (source["sha256"],)).fetchone()
        if tuple(stored) != (source["key"], source["publication_date"]):
            raise ValueError("CANONICAL_SOURCE_METADATA_CONFLICT")
        results = []
        for fact, raw in zip(facts, observations, strict=True):
            if fact["variable"] in reuse:
                results.append((reuse[fact["variable"]]["obs_id"], False))
                continue
            identity = digest([ADMISSION_VERSION, bundle, raw.raw_id, fact["variable"], raw.evidence.column,
                               raw.original_value, raw.original_unit, fact["value"], fact["unit"], fact["basis"],
                               fact["category"], raw.deposit_id, raw.material_basis, raw.denominator_basis,
                               scope_context.get("cutoff_grade") or scope_context.get("cutoff")])
            record = dict(fact, domain="Resource", scope=scope, statement_id=statement, admission_bundle_id=bundle,
                          automation_method=ADMISSION_VERSION, decision_mode="AUTOMATIC",
                          source_key=source["key"], source_sha256=source["sha256"], source_kind=source["kind"],
                          publication_date=source["publication_date"], available_date=source["available_date"],
                          source_acquisition_date=source["acquired_at"],
                          source_document_version=source.get("source_document_version") or source["sha256"],
                          pdf_page=raw.evidence.page, **_estimate_fields(raw), estimate_id=raw.estimate_id,
                          jorc_status=scope_context.get("jorc_status"),
                          jorc_rule_version=scope_context.get("jorc_rule_version"),
                          effective_date_precision=raw.effective_date_precision,
                          effective_date_role=raw.effective_date_role or "STATEMENT_EFFECTIVE_DATE",
                          original_reported_unit=raw.original_unit, original_token=raw.original_value,
                          source_bound_observation=payload(raw))
            if original_date := scope_context.get("original_estimate_date"):
                record["original_estimate_date"] = original_date
            if historical and historical.get("conflict"):
                record["historical_pair_conflict"] = historical["conflict"]
            elif historical:
                record["resource_identity_link"] = {
                    "rule": "EXACT_SAME_SOURCE_TABLE_AND_STATEMENT",
                    "reported_table_label": historical["reported_table_label"],
                    "canonical_observation_ids": {variable: row["obs_id"] for variable, row in reuse.items()
                                                  if variable in REQUIRED_QUANTITIES},
                    "legacy_completion": historical["legacy_completion"],
                    "estimate_equivalence": historical["equivalence"],
                }
            values = (identity, raw.project_id, fact["variable"], fact["value"], fact["unit"], fact["basis"],
                      scope, statement, fact["category"], fact["effective_date"], source["sha256"],
                      fact["locator"], "AUTO_VALIDATED", "[]", canonical(record), ADMISSION_VERSION)
            existing = db.execute("SELECT * FROM observations WHERE obs_id=?", (identity,)).fetchone()
            if existing is not None and tuple(existing)[:14] != values[:14]:
                raise ValueError("CANONICAL_OBSERVATION_ID_COLLISION")
            if existing is None:
                db.execute("INSERT INTO observations VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", values)
            results.append((identity, existing is None))
    except BaseException:
        db.execute("ROLLBACK TO automatic_resource_bundle")
        db.execute("RELEASE automatic_resource_bundle")
        raise
    db.execute("RELEASE automatic_resource_bundle")
    return results, historical


def _scientific_group(first, facts):
    """Coalesce equal presentations of the same declared estimate in one edition."""
    context = _scope_conditions(first)
    return digest([first.project_id, first.evidence.sha256, first.scope_id, first.estimate_id,
                   first.effective_date, first.deposit_id, context.get("category"),
                   context.get("cutoff_grade") or context.get("cutoff"), first.denominator_basis,
                   sorted((f["variable"], f["value"], f["unit"], f["rounding_half_width"]) for f in facts)])


def _coordinate_key(row):
    raw = json.loads(row["raw"])
    original = raw.get("source_bound_observation") or {}
    anchor = original.get("evidence") or {}
    coordinates = tuple(anchor.get(field) for field in ("page", "table", "row", "column"))
    if any(value is None for value in coordinates):
        return None
    return (row["entity_id"], row["source_sha"], row["variable"], row["statement_id"], row["effective_date"],
            row["scope"], row["category"], row["value"], row["unit"], row["basis"], *coordinates)


def _inactive_admissions(db, active, requested_shas):
    records = [dict(row) for row in db.execute("SELECT * FROM observations WHERE transform_version GLOB ? ORDER BY obs_id",
                                               (RESOURCE_ADMISSION_VERSION_GLOB,))]
    current = {key: row["obs_id"] for row in records if row["obs_id"] in active and (key := _coordinate_key(row))}
    result = []
    for row in records:
        if row["obs_id"] in active:
            continue
        replacement = current.get(_coordinate_key(row))
        status = ("REVALIDATED_AS_NEW_RULE_EDITION" if replacement else "SOURCE_NOT_REQUESTED_IN_THIS_RUN"
                  if row["source_sha"] not in requested_shas else "NOT_REVALIDATED_IN_THIS_RUN")
        result.append({**_legacy_location(row), "transform_version": row["transform_version"], "reason": status,
                       "current_observation_id": replacement})
    return result


def admit(db, root, snapshots, cutoff, page_requests, *, acquired_through=None, claims_data=None,
          cache=None, classification="PUBLIC_REAL_SOURCE_REPLAY", context_pages_by_sha=None,
          preferred_source_keys=None, document_cache=None):
    """Re-extract selected immutable PDF editions and save complete same-row witnesses.

    The caller owns the database transaction and current-run visibility. Historical
    observations are append-only. A receipt describes evidence verification and
    canonical storage; the formal selector independently admits criterion inputs.
    """
    root = Path(root)
    claims = claims_data if claims_data is not None else json.loads((root / "data/claims.json").read_bytes())
    active_claim_ids = claim_evidence_ids(claims)
    engine = SemanticEngine(root)
    registry = project_registry(root, db, snapshots, mapping={}, claims_data=claims)
    context_pages_by_sha = context_pages_by_sha or {}
    preferred_source_keys = preferred_source_keys or {}
    sources = {}
    ambiguous = set()
    for source in snapshots:
        sha = source["sha256"]
        if sha in preferred_source_keys and source["key"] != preferred_source_keys[sha]:
            continue
        if sha in sources and sources[sha] != source:
            ambiguous.add(sha)
        sources[sha] = source
    allowed = _authorized_projects(claims, registry, sources)
    snapshot_index = {(row["key"], row["sha256"]): row for row in snapshots}
    source_reasons, dispositions, accepted, active_automatic = [], [], {}, set()
    grouped = defaultdict(list)
    counts = Counter(source_requests=len(page_requests))
    for sha, pages in sorted(page_requests.items()):
        context_pages = context_pages_by_sha.get(sha, ())
        if (not re.fullmatch(r"[a-f0-9]{64}", sha) or not pages and document_cache is None
                or any(type(page) is not int or page < 1 for page in (*pages, *context_pages))):
            raise ValueError("Admission requests require a pinned SHA and positive physical pages")
        source = sources.get(sha)
        counts["pages_requested"] += len(set(pages))
        reason = ("SOURCE_EDITION_METADATA_AMBIGUOUS" if sha in ambiguous else
                  _source_metadata_issue(source, cutoff, root, acquired_through))
        if not reason and source.get("case_classification", "PUBLIC_REAL_SOURCE_REPLAY") != classification:
            reason = "SOURCE_CLASSIFICATION_MISMATCH"
        available = (root / source["path"]).is_file() if source and source.get("path") else False
        sha_verified = (True if reason in {None, "SOURCE_TIMING_UNESTABLISHED", "SOURCE_CLASSIFICATION_MISMATCH"}
                        else False if reason == "SOURCE_HASH_MISMATCH" else None)
        if reason:
            source_reasons.append(dict(source_sha256=sha, source_key=source["key"] if source else None,
                                       status="SOURCE_BLOCKED", reason=reason, pages=sorted(set(pages)),
                                       asset_available=available, sha_verified=sha_verified))
            continue
        if not pages:
            source_reasons.append(dict(source_sha256=sha, source_key=source["key"], status="SOURCE_CHECKED",
                                       reason="NO_VALUE_PAGES_SELECTED", pages=[], context_pages=sorted(set(context_pages)),
                                       context_page_dispositions=[], asset_available=available, sha_verified=sha_verified))
            continue
        context_options = {"context_pages": tuple(sorted(set(context_pages)))} if context_pages else {}
        if document_cache is not None:
            context_options["document_cache"] = document_cache
        discovery = discover(root, dict(source, summary_project_ids=allowed[sha]), registry,
                             page_numbers=sorted(set(pages)), cache=cache, **context_options)
        page_statuses = {row["status"] for row in discovery["pages"]}
        gaps = page_statuses - {"NO_CANDIDATES", "DISCOVERED"}
        source_status = ("SOURCE_BLOCKED" if page_statuses == {"SOURCE_BLOCKED"} else
                         "SOURCE_CHECKED_WITH_GAPS" if gaps else "SOURCE_CHECKED")
        source_reasons.append(dict(source_sha256=sha, source_key=source["key"], status=source_status,
                                   asset_available=available, sha_verified=sha_verified,
                                   source_timing={k: source[k] for k in ("publication_date", "available_date", "acquired_at")},
                                   authorized_projects=allowed[sha], pages=discovery["pages"],
                                   context_pages=sorted(set(context_pages)),
                                   context_page_dispositions=discovery.get("context_page_dispositions", [])))
        for candidate in discovery["candidates"]:
            summary, facts, raws = _evaluate(candidate, source, allowed[sha], cutoff, engine, registry=registry)
            dispositions.append(summary)
            if facts:
                grouped[_scientific_group(raws[0], facts)].append((summary, source, facts, raws))
    # Start the transaction explicitly so a released savepoint never publishes
    # facts before the caller's encompassing formal build commits or rolls back.
    if grouped and not db.in_transaction:
        db.execute("BEGIN IMMEDIATE")
    for key in sorted(grouped):
        entries = sorted(grouped[key], key=lambda entry: tuple(entry[0][field] for field in ("physical_page", "table", "row")))
        summary, source, facts, raws = entries[0]
        try:
            rows, historical = _insert_bundle(db, root, source, facts, raws, active_claim_ids,
                                               snapshot_index=snapshot_index)
        except ValueError as exc:
            for disposition, *_ in entries:
                disposition.update(status="NOT_ADMITTED", reasons=[str(exc)])
                if isinstance(exc, _HistoricalEstimateHold):
                    disposition["historical_match_rejected"] = exc.audit
            continue
        identifiers = [identity for identity, _ in rows]
        legacy_ids = {row["obs_id"] for row in historical["reused"].values()} if historical else set()
        new_edition_ids = sorted(set(identifiers) - legacy_ids)
        active_automatic.update(new_edition_ids)
        bundle_id = None
        if new_edition_ids:
            stored = db.execute("SELECT raw FROM observations WHERE obs_id=?", (new_edition_ids[0],)).fetchone()
            bundle_id = json.loads(stored["raw"])["admission_bundle_id"]
        for identity, created in rows:
            accepted[identity] = accepted.get(identity, False) or created
        for index, (disposition, _, _, observations) in enumerate(entries):
            disposition.update(status="SOURCE_BOUND_CANONICAL" if index == 0 else "CORROBORATING_PRESENTATION",
                               canonical_observation_ids=identifiers, admission_bundle_id=bundle_id,
                               reasons=["MATCHING_ESTIMATE_PRESENTATION"] if index else ["COMPLETE_SAME_ROW_RESOURCE_STATEMENT"])
            if historical:
                relation = {"scope": historical["scope"], "statement_id": historical["statement_id"],
                            "reported_table_label": historical["reported_table_label"],
                            "estimate_equivalence": historical["equivalence"]}
                if conflict := historical.get("conflict"):
                    disposition["historical_conflict"] = {**relation, **conflict}
                else:
                    disposition["historical_link"] = {**relation, "reused_observation_ids": sorted(legacy_ids)}
            by_quantity = {fact["variable"]: identity for fact, identity in zip(facts, identifiers, strict=True)}
            for raw, detail in zip(observations, disposition["observations"], strict=True):
                detail["canonical_observation_id"] = by_quantity[raw.variable]
    raw_candidates = [item for disposition in dispositions for item in disposition["observations"]]
    unique = {item["raw_id"]: item for item in raw_candidates}
    materials = {item["raw_id"]: item for row in dispositions for item in row["material_observations"]}
    inactive = _inactive_admissions(db, active_automatic, page_requests)
    counts.update(candidate_rows=len(dispositions), candidate_observations=len(raw_candidates),
                  deduplicated_observations=len(unique), numeric_located=sum(x["numeric_located"] for x in unique.values()),
                  numeric_and_unit_located=sum(x["numeric_and_unit_located"] for x in unique.values()),
                  evidence_verified=sum(x["evidence_status"] == "VERIFIED" for x in unique.values()),
                  material_candidate_observations=len(materials),
                  material_numeric_and_unit_located=sum(x["numeric_and_unit_located"] for x in materials.values()),
                  canonical_added=sum(accepted.values()), canonical_reused=sum(not x for x in accepted.values()),
                  canonical_stored=len(accepted), accepted_statements=sum(x["status"] == "SOURCE_BOUND_CANONICAL" for x in dispositions),
                  canonical_inactive=len(inactive),
                  rejected_statements=sum(x["status"] == "NOT_ADMITTED" for x in dispositions),
                  accepted_projects=len({x["project_id"] for x in dispositions if x["canonical_observation_ids"]}),
                  source_blocked=sum(x["status"] == "SOURCE_BLOCKED" for x in source_reasons),
                  sources_with_incomplete_pages=sum(x["status"] == "SOURCE_CHECKED_WITH_GAPS" for x in source_reasons),
                  sources_available=sum(x["asset_available"] for x in source_reasons),
                  sources_sha_verified=sum(x["sha_verified"] is True for x in source_reasons))
    rules = code_fingerprint(discover, SemanticEngine, value_evidence_issue, source_check, resource_statement_metrics,
                             files=[Path(__file__), Path(__file__).with_name("resource_jorc.py"),
                                    Path(__file__).with_name("resource_discourse.py"),
                                    Path(__file__).with_name("resource_table_layout.py"),
                                    Path(__file__).with_name("resource_estimate.py"),
                                    Path(__file__).with_name("resource_source.py"),
                                    root / "config/ontology/observation_v1.json",
                                    root / "config/ontology/comparability_v1.json"])
    inputs = digest([cutoff, acquired_through, page_requests, context_pages_by_sha, preferred_source_keys,
                     allowed, classification, sorted(active_claim_ids),
                     [entry for entry in source_reasons if entry.get("source_timing")]])
    return dict(schema=SCHEMA, version=ADMISSION_VERSION, classification=classification,
                cutoff=cutoff, acquired_through=acquired_through, input_sha256=inputs, rules_sha256=rules,
                status="COMPLETE_WITH_GAPS" if counts["source_blocked"] or counts["sources_with_incomplete_pages"] else "COMPLETE",
                counts=dict(counts),
                canonical_observation_ids=sorted(accepted), active_admission_observation_ids=sorted(active_automatic),
                inactive_admission_observation_ids=[row["observation_id"] for row in inactive],
                inactive_admissions=inactive,
                source_dispositions=source_reasons, dispositions=dispositions,
                scientific_sha256=digest([inputs, rules, source_reasons, dispositions, sorted(accepted)]))
