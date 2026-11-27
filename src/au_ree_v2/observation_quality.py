"""Automatically audit source-first observation discovery on a fixed document frame."""

from collections import Counter, defaultdict
from datetime import date
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path
import re

from .derived_cache import atomic_json
from .document_processing import DocumentUnavailable, PdfDocumentCache
from .numeric_evidence import numeric_token_spans, quantity_literals, scalar_decimal
from .observation_schema import payload, value_evidence_issue
from .observation_semantics import RESOURCE_PROFILE, SemanticEngine
from .observation_shadow import jsonl, write
from .pdf_extract import candidate_value_issues, project_registry
from .selection_rules import date_end
from .semantic_resource import located_column_headers
from .semantic_technical import CLAIM_CUES, PROFILE as TECHNICAL_PROFILE
from .store import digest, filehash
from .tabular import read_csv
from .technical import technical_compare
from .technical_tables import cells, path_above


FRAME = "config/ontology/quality_frame_v1.json"
RULE_VERSION = "observation-automated-quality-v2"
RELEASE = "results/ree-project-census/coverage-locked-20261125"
PARTITIONS = ("DEVELOPMENT", "EVALUATION")
QUALITY_ARTIFACTS = ("sources.jsonl", "pages.jsonl", "observations.jsonl",
                     "unbound_lexemes.jsonl", "resource_duplicates.jsonl")


def _validate_frame(frame):
    if frame["schema"] != "observation-quality-frame-v1" or set(frame["partitions"]) != set(PARTITIONS):
        raise ValueError("Unsupported observation quality frame")
    date.fromisoformat(frame["cutoff"])
    project_sets, edition_sets, group_sets = [], [], []
    for partition in PARTITIONS:
        entries = frame["partitions"][partition]
        hashes = [entry["source_sha256"] for entry in entries]
        if not entries or len(hashes) != len(set(hashes)):
            raise ValueError("The quality frame needs distinct sources in each partition")
        for entry in entries:
            pages = entry["pages"]
            if not pages or any(type(page) is not int or page < 1 for page in pages) or pages != sorted(set(pages)):
                raise ValueError("The quality frame requires sorted unique positive physical pages")
            if entry["source_sha256"] not in entry["edition_sha256"] or not entry["project_ids"]:
                raise ValueError("Each selected edition needs its report family and Project bindings")
        project_sets.append({project for entry in entries for project in entry["project_ids"]})
        edition_sets.append({edition for entry in entries for edition in entry["edition_sha256"]})
        group_sets.append({entry["group_id"] for entry in entries})
    if any(left & right for left, right in (project_sets, edition_sets, group_sets)):
        raise ValueError("Development and evaluation must be disjoint by Project, report family and edition")


def _load_frame(root):
    frame = json.loads((root / FRAME).read_bytes())
    _validate_frame(frame)
    for name, sha in frame["input_sha256"].items():
        path = (root / name).resolve()
        if not path.is_relative_to(root) or filehash(path) != sha:
            raise ValueError(f"Frozen quality design input differs: {name}")
    return frame


def _rate(count, denominator):
    return {"numerator": count, "denominator": denominator, "ratio": count / denominator if denominator else None}


def _flat(text):
    return " ".join(str(text or "").split())


def _unit_in(text, unit):
    if not unit or not text:
        return False
    aliases = {"Mt": ("Mt", "million tonnes", "million metric tonnes"),
               "t": ("t", "tonnes"), "kt": ("kt", "'000 tonnes", "‘000 tonnes"),
               "t TREO": ("t TREO", "TREO (t)", "TREO(t)"),
               "kt TREO": ("kt TREO", "TREO (kt)", "TREO(kt)", "'000 tonnes")}
    forms = aliases.get(unit, (unit,))
    # Keep SI-prefix case (m/M) and permit spaces around slash-separated units.
    return any(re.search(r"(?<![A-Za-z])" + r"\s*".join(re.escape(part) for part in form.split())
                         + r"(?![A-Za-z])", text) for form in forms)


def _page_views(page):
    evidence = page.get("evidence") or {}
    views = {name: text for name, text in evidence.get("text_views", {}).items() if _flat(text)}
    digests = {name: digest(_flat(text)) for name, text in views.items()}
    if not views:
        status = "NO_READABLE_VIEW"
    elif len(views) == 1:
        status = "SINGLE_VIEW"
    elif len(set(digests.values())) == 1:
        status = "NORMALIZED_TEXT_AGREEMENT"
    else:
        status = "TEXT_OR_LAYOUT_DIVERGENCE"
    return views, {"status": status, "view_sha256": digests, "method": evidence.get("method"),
                   "ocr_model_sha256": evidence.get("model_sha256"), "native_error": evidence.get("native_error"),
                   "parser_version": evidence.get("version"), "backend_version": evidence.get("backend_version"),
                   "table_parser_version": evidence.get("table_parser_version")}


def _table_location(raw, page):
    anchor = raw.evidence
    indices = (anchor.table, anchor.row, anchor.column)
    if not all(type(value) is int for value in indices):
        return None, "TABLE_COORDINATES_INSUFFICIENT"
    matches = [table for table in page.get("tables", ()) if table["table_index"] == anchor.table
               and table["physical_page"] == anchor.page]
    if len(matches) != 1:
        return None, "TABLE_GRID_UNAVAILABLE"
    table, = matches
    try:
        row = table["cells"][anchor.row]
        cell = row[anchor.column]
    except (IndexError, TypeError):
        return None, "TABLE_ROW_COLUMN_MISMATCH"
    if _flat(cell) != _flat(anchor.quote):
        return None, "TABLE_CELL_TEXT_MISMATCH"
    boxes = table.get("rows", ())
    box = boxes[anchor.row][anchor.column] if anchor.row < len(boxes) and anchor.column < len(boxes[anchor.row]) else None
    if anchor.bbox is not None and (box is None or any(abs(p - q) >= .01 for p, q in zip(anchor.bbox, box))):
        return None, "TABLE_CELL_GEOMETRY_MISMATCH"
    row_labels = [value for value in row[:anchor.column] if value and re.search(r"[A-Za-z]", str(value))]
    grid = cells(table)
    target = next((c for c in grid if (c["row"], c["column"]) == (anchor.row, anchor.column)), None)
    headers = path_above(target, grid, anchor.row) if target else []
    if table.get("external_header") and anchor.column < len(table.get("header", ())):
        headers.insert(0, table["header"][anchor.column])
    if not row_labels:
        return None, "TABLE_ROW_LABEL_UNBOUND"
    if not (_unit_in(anchor.quote, raw.original_unit) or _unit_in(" ".join(_flat(header) for header in headers), raw.original_unit)):
        return False, "TABLE_COLUMN_UNIT_UNBOUND"
    explicit = [witness for witness in raw.evidence_anchors if witness.role == "unit"
                and (witness.row is not None or witness.bbox is not None)]
    if explicit:
        header_cells = located_column_headers(target, grid) if target else []
        actual_headers = {(cell["row"], cell["column"]): cell for cell in header_cells}
        for witness in explicit:
            cell = actual_headers.get((witness.row, witness.column))
            if (not cell or (witness.sha256, witness.page, witness.table) != (anchor.sha256, anchor.page, anchor.table)
                    or witness.bbox is None or any(abs(p - q) >= .01 for p, q in zip(witness.bbox, cell["bbox"]))
                    or _flat(witness.quote) != _flat(cell["text"]) or not _unit_in(witness.quote, raw.original_unit)):
                return False, "TABLE_UNIT_WITNESS_MISMATCH"
    if table.get("continuation_candidate"):
        return True, "CONTINUATION_HEADER_REPEATED_SCOPE_UNCONFIRMED"
    return True, "TABLE_CELL_AND_EXPLICIT_HEADER_BOUND" if explicit else "TABLE_CELL_AND_HEADER_BOUND"


def _numeric_location(raw, page, views):
    if raw.source_value_state in {"NOT_REPORTED", "NOT_APPLICABLE"} or not raw.original_value:
        return {"status": raw.source_value_state or "NOT_REPORTED", "numeric_bound": False, "unit_bound": False,
                "parser_support": {}}
    issue = value_evidence_issue(raw, raw.evidence_anchors or (raw.evidence,))
    if issue:
        return {"status": issue, "numeric_bound": False, "unit_bound": False, "parser_support": {}}
    anchor = raw.evidence
    quote = _flat(anchor.quote)
    supports = {name: ("QUOTE_FOUND" if quote and quote in _flat(text) else "QUOTE_UNBOUND")
                for name, text in views.items()}
    if anchor.table is not None:
        unit, status = _table_location(raw, page)
        return {"status": status, "numeric_bound": unit is not None, "unit_bound": bool(unit),
                "parser_support": supports}
    explicit = anchor.text_span
    if explicit and explicit.scope == "PAGE":
        original = views.get(explicit.view)
        if not original or original[explicit.quote_start:explicit.quote_start + len(anchor.quote or "")] != anchor.quote:
            return {"status": "TEXT_SPAN_SOURCE_MISMATCH", "numeric_bound": False, "unit_bound": False,
                    "parser_support": supports}
    if explicit and explicit.scope == "BLOCK":
        matching = [text for box, text in page.get("blocks", ()) if box and anchor.bbox and
                    all(abs(p - q) < .01 for p, q in zip(anchor.bbox, box)) and
                    text[explicit.quote_start:explicit.quote_start + len(anchor.quote or "")] == anchor.quote]
        if len(matching) != 1:
            return {"status": "BLOCK_SPAN_SOURCE_UNBOUND", "numeric_bound": False, "unit_bound": False,
                    "parser_support": supports}
    # A short unlocated quote composed only of a number is not page evidence.
    spans = list(numeric_token_spans(quote, raw.original_value, raw.original_unit))
    if len(spans) == 1:
        start, end = spans[0]
        prefix, suffix = quote[:start].strip(), quote[end:].strip()
        if prefix and suffix and len(prefix) + len(suffix) >= 12:
            context = r"(?<!\w)" + re.escape(prefix[-45:]) + r"\s*(.{1,32}?)\s*" + re.escape(suffix[:45])
            for name, text in views.items():
                if supports[name] == "QUOTE_FOUND":
                    continue
                reported = re.findall(context, _flat(text))
                if len(reported) == 1 and re.fullmatch(r"[+−\-\d,eE.]+", reported[0].strip()) and not list(
                        numeric_token_spans(reported[0], raw.original_value, raw.original_unit)):
                    supports[name] = "SAME_CONTEXT_DIFFERENT_NUMERIC_TOKEN"
    if "SAME_CONTEXT_DIFFERENT_NUMERIC_TOKEN" in supports.values():
        return {"status": "PARSER_NUMERIC_CONFLICT", "numeric_bound": False, "unit_bound": False,
                "parser_support": supports}
    witnessed = bool(quote and ("QUOTE_FOUND" in supports.values() or explicit and explicit.scope == "BLOCK"))
    unit = witnessed and _unit_in(quote, raw.original_unit)
    status = "TEXT_VALUE_AND_UNIT_BOUND" if unit else "TEXT_UNIT_UNBOUND" if witnessed else "TEXT_QUOTE_UNBOUND"
    return {"status": status, "numeric_bound": witnessed, "unit_bound": bool(unit), "parser_support": supports}


def _arithmetic(candidate):
    if candidate.get("kind") != "RESOURCE_TABLE_TOTAL":
        return "NOT_APPLICABLE"
    bounds = candidate.get("rounding_bounds_kt")
    contained = candidate.get("values", {}).get("contained_treo_kt")
    index = (candidate.get("row_token_indices") or {}).get("contained_treo_kt", 2)
    tokens = candidate.get("original_tokens", ())
    if not bounds or contained is None or index >= len(tokens):
        return "NO_COMPATIBLE_REPORTED_CONTAINED_TRIPLE"
    # The recognizer calculates a mass × grade interval from printed precision.
    # Compare it to the reported contained mass's own rounding interval.
    printed = scalar_decimal(tokens[index], None)
    if printed is None or not printed.is_finite():
        return "REPORTED_CONTAINED_TOKEN_UNPARSEABLE"
    scale = Decimal(1) if re.search(r"000|\bkt\b", candidate["header"], re.I) else Decimal(".001")
    midpoint = Decimal(str(contained))
    half = Decimal(5).scaleb(printed.as_tuple().exponent - 1) * scale
    agrees = max(Decimal(str(bounds[0])), midpoint - half) <= min(Decimal(str(bounds[1])), midpoint + half)
    return "WITHIN_REPORTED_PRECISION" if agrees else "REPORTED_CONTAINED_CONFLICT"


def _event_stance(raw):
    context = dict(raw.context.conditions)
    if raw.quantity_kind != "EVENT":
        return context.get("claim_nature")
    quote = raw.evidence.quote or ""
    if re.search(r"\b(?:has|have|had|is|are|will|can|could) not\b|\bno longer\b", quote, re.I):
        return "NEGATED"
    if re.search(r"\b(?:to be commissioned|schedule[ds]? to|plans? to|proposed to|would commence)\b", quote, re.I):
        return "TARGET"
    for key in ("NEGATED", "CONDITIONAL", "TARGET", "HISTORICAL_REFERENCE", "ENGINEERING_DESIGN"):
        if re.search(CLAIM_CUES[key], quote, re.I):
            return key
    if re.search(r"\b(?:was completed|were completed|has (?:been )?completed|commenced|entered operation|commissioned)\b",
                 quote, re.I):
        return "COMPLETED_EVENT_MENTION"
    return "EVENT_STANCE_UNRESOLVED"


def _temporal(raw, entry, cutoff):
    values = {"publication": raw.publication_date or entry["publication_date"],
              "effective": raw.effective_date, "date_used": entry["date_used"]}
    reasons = [f"{name.upper()}_AFTER_CUTOFF" for name, value in values.items() if value and date_end(value[:10]) > cutoff]
    if entry["cutoff_status"] != "WITHIN_CUTOFF" or not entry["date_used"]:
        reasons.append("SOURCE_DATE_UNVERIFIED")
    if raw.publication_date and entry["publication_date"] and raw.publication_date[:10] != entry["publication_date"]:
        reasons.append("PUBLICATION_METADATA_CONFLICT")
    if not raw.effective_date:
        reasons.append("EFFECTIVE_DATE_UNDISCLOSED")
    return {**values, "basis": entry["date_basis"], "acquired_at": entry["acquired_at"], "reasons": reasons}


def _purpose(raw, recognition, normalized, engine, policy):
    context = dict(raw.context.conditions)
    if raw.quantity_kind == "RESOURCE":
        missing = [key for key in ("category", "resource_type") if not context.get(key)]
        if not (raw.estimate_id or raw.statement_id or raw.effective_date):
            missing.append("estimate_version")
        if raw.variable in {"grade", "contained_treo_kt"} and not all(
                (raw.chemical_basis, raw.material_basis, raw.denominator_basis)):
            missing.append("material_chemical_denominator_basis")
        category = context.get("resource_type") or context.get("statement_kind")
        if category and category != "MINERAL_RESOURCE":
            return RESOURCE_PROFILE, "INCOMPATIBLE", ["RESOURCE_CLASS_SCOPE_MISMATCH"]
        return RESOURCE_PROFILE, "INSUFFICIENT" if missing else "COMPARABLE", missing
    if raw.variable == "reported_technical_extraction_pct":
        missing = [key for key, value in {"sample": raw.context.sample, "feed": context.get("feed"),
                   "process": raw.context.process, "scale": raw.context.scale, "endpoint": raw.context.endpoint}.items()
                   if not value or value.endswith("UNSPECIFIED")]
        contract = policy["technical_analysis"]["contracts"][TECHNICAL_PROFILE]
        record = {**recognition, "variable": raw.variable, "basis": raw.chemical_basis,
                  "study_date": raw.effective_date, "value": float(normalized.value) if normalized else None}
        missing.extend(technical_compare(record, contract, contract.get("model_assumptions", ())))
        return TECHNICAL_PROFILE, "INSUFFICIENT" if missing else "COMPARABLE", missing
    if raw.quantity_kind == "STRATEGIC_COMPOSITION":
        missing = [name for name in ("material_basis", "chemical_basis", "denominator_basis") if not getattr(raw, name)]
        return "STRATEGIC_COMPOSITION_DISCLOSURE", "INSUFFICIENT" if missing else "DESCRIPTIVE_ONLY", missing
    if raw.quantity_kind == "EVENT":
        return "EVENT_DISCLOSURE_MENTION", "DESCRIPTIVE_ONLY", []
    return "NO_APPLICABLE_USE_PROFILE", "NOT_APPLICABLE", []


def _reported_value_state(raw, normalized):
    if raw.quantity_kind == "EVENT":
        return "NON_NUMERIC_EVENT_MENTION"
    if not raw.original_value or raw.source_value_state in {"NOT_REPORTED", "NOT_APPLICABLE"}:
        return raw.source_value_state or "NOT_REPORTED"
    if raw.source_value_state in {"RANGE", "BOUND"}:
        return "REPORTED_" + raw.source_value_state
    value = scalar_decimal(raw.original_value, raw.original_unit)
    if value is None:
        return "TOKEN_UNPARSEABLE"
    if raw.original_unit == "%" and not 0 <= value <= 100:
        return "PERCENT_OUT_OF_RANGE"
    if value == 0:
        return "REPORTED_ZERO"
    return "REPORTED_SCALAR" if normalized is not None else "NORMALIZATION_UNRESOLVED"


def _audit_observation(raw, page, views, entry, cutoff, engine, policy, official):
    context = dict(raw.context.conditions)
    identifier = context.get("recognition_candidate_id")
    recognized = next((c for c in page.get("recognition", ()) if c.get("candidate_id") == identifier), {})
    location = _numeric_location(raw, page, views)
    normalized = engine.normalize(raw)
    profile, requested, missing = _purpose(raw, recognized, normalized, engine, policy)
    temporal = _temporal(raw, entry, cutoff)
    stance = _event_stance(raw)
    arithmetic = _arithmetic(recognized)
    reported_state = _reported_value_state(raw, normalized)
    issues = candidate_value_issues(recognized) if recognized else []
    issues.extend(sorted(set(recognized.get("issues", ()))))
    if reported_state in {"PERCENT_OUT_OF_RANGE", "TOKEN_UNPARSEABLE", "NORMALIZATION_UNRESOLVED"}:
        issues.append(reported_state)
    identity = "PROJECT_SCOPE_BOUND" if raw.project_id in entry["project_ids"] else (
        "OUT_OF_PARTITION_PROJECT" if raw.project_id else "PROJECT_SCOPE_UNRESOLVED")
    comparable = requested
    if identity != "PROJECT_SCOPE_BOUND":
        issues.append(identity)
        missing.append("project_scope")
    if stance in {"NEGATED", "CONDITIONAL", "TARGET", "HISTORICAL_REFERENCE", "ENGINEERING_DESIGN"} and comparable != "NOT_APPLICABLE":
        comparable = "INCOMPATIBLE"
        issues.append("CLAIM_STANCE_OUTSIDE_MEASURED_USE")
    if reported_state == "PERCENT_OUT_OF_RANGE" and comparable != "NOT_APPLICABLE":
        comparable = "INCOMPATIBLE"
    if arithmetic == "REPORTED_CONTAINED_CONFLICT":
        issues.append(arithmetic)
    timing_failures = [reason for reason in temporal["reasons"] if reason != "EFFECTIVE_DATE_UNDISCLOSED"]
    issues.extend(timing_failures)
    status = "UNVERIFIED"
    if location["status"] in {"PARSER_NUMERIC_CONFLICT", "TABLE_CELL_TEXT_MISMATCH", "TABLE_ROW_COLUMN_MISMATCH",
                              "TABLE_CELL_GEOMETRY_MISMATCH", "TABLE_UNIT_WITNESS_MISMATCH", "TEXT_SPAN_SOURCE_MISMATCH",
                              "NUMERIC_EVIDENCE_BINDING_MISMATCH"} or arithmetic == "REPORTED_CONTAINED_CONFLICT":
        status = "CONFLICT"
        if comparable != "NOT_APPLICABLE":
            comparable = "CONFLICT"
    elif timing_failures:
        status = "SOURCE_BLOCKED"
        if comparable != "NOT_APPLICABLE":
            comparable = "SOURCE_BLOCKED"
    elif location["numeric_bound"] and location["unit_bound"]:
        status = "VERIFIED"
    if comparable == "COMPARABLE" and (status != "VERIFIED" or normalized is None or missing or issues
                                       or location["status"].startswith("CONTINUATION_")):
        comparable = "INSUFFICIENT"
    result = engine.assess(raw, {"status": comparable, "reason": "SOURCE_FIRST_AUTOMATED_QUALITY",
                                "profile_id": profile, "profile_version": RULE_VERSION, "missing": sorted(set(missing))},
                           normalized=normalized, evidence_status=status,
                           supporting_evidence=raw.evidence_anchors or (raw.evidence,),
                           apply_profile=profile in (RESOURCE_PROFILE, TECHNICAL_PROFILE))
    canonical_match = (raw.observation_id, raw.evidence.sha256, raw.project_id) in official
    return {"observation_id": raw.observation_id, "raw": payload(raw), "raw_id": raw.raw_id,
            "project_id": raw.project_id, "variable": raw.variable, "quantity_kind": raw.quantity_kind,
            "assessment": payload(result), "normalized": payload(normalized) if normalized else None,
            "rule_violations_or_limits": sorted(set(issues)), "numeric_location": location, "report_timing": temporal,
            "resource_arithmetic": arithmetic, "claim_stance": stance, "identity_scope": identity,
            "reported_value_state": reported_state,
            "matches_existing_census_selected_observation_id": canonical_match}


def _measurement_key(row):
    raw, anchor = row["raw"], row["raw"]["evidence"]
    return digest([anchor["sha256"], anchor["page"], anchor["table"], anchor["row"], anchor["column"],
                   anchor.get("text_span") or anchor["offset"], anchor["quote"], anchor["bbox"], raw["project_id"],
                   raw["scope_id"], raw["variable"], raw["original_value"], raw["original_unit"]])


def _quantity_literal_gaps(views, method, observations):
    if not views:
        return []
    view = "MUPDF_POSITIONED" if "MUPDF_POSITIONED" in views else method if method in views else next(iter(views))
    text = views[view]
    bound = {(row.evidence.text_span.start, row.original_unit) for row in observations if row.evidence.text_span
             and row.evidence.text_span.scope == "PAGE" and row.evidence.text_span.view == view}
    return [{"text_view": view, "start": item.start, "end": item.end, "text": text[item.start:item.end],
             "kind": item.kind, "unit": item.unit, "reason": "UNIT_BEARING_LEXEME_WITHOUT_PAGE_SPAN_LINK"}
            for item in quantity_literals(text) if (item.start, item.unit) not in bound]


def _resource_duplicates(rows):
    groups = defaultdict(list)
    for row in rows:
        raw = row["raw"]
        if row["quantity_kind"] != "RESOURCE" or row["identity_scope"] != "PROJECT_SCOPE_BOUND" or not row["normalized"]:
            continue
        norm = row["normalized"]
        groups[(row["project_id"], row["variable"], Decimal(norm["value"]), norm["unit"])].append(row)
    result = []
    for group in groups.values():
        if len({row["source_sha256"] for row in group}) < 2:
            continue
        keys = ("estimate_id", "scope_id", "effective_date", "chemical_basis", "material_basis", "denominator_basis")
        identities = {tuple(row["raw"][key] for key in keys) for row in group}
        status = ("REPEATED_EXPLICIT_ESTIMATE_IDENTITY" if len(identities) == 1 and all(next(iter(identities))) else
                  "REPEATED_VALUE_SCOPE_OR_EDITION_UNRESOLVED")
        result.append({"status": status, "project_id": group[0]["project_id"],
                       "observation_ids": sorted({row["observation_id"] for row in group}),
                       "source_sha256": sorted({row["source_sha256"] for row in group})})
    return result


def _section(sources, pages, rows, duplicates):
    numeric = [row for row in rows if row["quantity_kind"] != "EVENT"]
    available = [row for row in rows if row["assessment"]["evidence_status"] == "VERIFIED"]
    comparable = [row for row in available if row["assessment"]["comparability"] == "COMPARABLE" and row["normalized"]]
    source_eligible = [source for source in sources if source["status"] == "SOURCE_VERIFIED"]
    comparable_pages = [page for page in pages if page["parser"]["status"] in
                        {"NORMALIZED_TEXT_AGREEMENT", "TEXT_OR_LAYOUT_DIVERGENCE"}]
    present = sum(source["asset_path_present"] for source in sources)
    multiple_views = [r for r in numeric if len(r["numeric_location"]["parser_support"]) >= 2]
    ocr_requested = [page for page in pages if page["ocr_comparison_requested"]]
    ocr_observed = [page for page in ocr_requested if page["parser"]["ocr_model_sha256"]]
    resource = [row for row in numeric if row["quantity_kind"] == "RESOURCE"]
    return {
        "expected_sources": len(sources), "source_fingerprint_match": _rate(len(source_eligible), len(sources)),
        "source_asset_available": _rate(present, len(sources)),
        "fingerprint_match_among_present_sources": _rate(len(source_eligible), present),
        "source_status": dict(Counter(source["status"] for source in sources)),
        "expected_pages": len(pages), "page_status": dict(Counter(page["status"] for page in pages)),
        "page_processing_issues": dict(Counter(page["reason"] for page in pages if page["reason"])),
        "unit_bearing_lexemes_without_page_span_link": sum(p["unit_bearing_lexemes_without_page_span_link"] for p in pages),
        "parser_view_status": dict(Counter(page["parser"]["status"] for page in pages)),
        "requested_ocr_comparison_pages_with_result": _rate(len(ocr_observed), len(ocr_requested)),
        "ocr_page_dispositions": dict(Counter(page["parser"]["status"] for page in ocr_observed)),
        "parser_normalized_text_agreement": _rate(sum(p["parser"]["status"] == "NORMALIZED_TEXT_AGREEMENT"
                                                       for p in comparable_pages), len(comparable_pages)),
        "parser_candidate_dispositions": dict(Counter(r["numeric_location"]["status"] for r in numeric)),
        "parser_bound_quote_agreement": _rate(sum(all(value == "QUOTE_FOUND" for value in
                                                       row["numeric_location"]["parser_support"].values())
                                                  for row in multiple_views), len(multiple_views)),
        "discovered_observation_representations": len(rows),
        "observation_kinds": dict(Counter(r["quantity_kind"] for r in rows)),
        "deduplicated_source_observations": len({_measurement_key(r) for r in rows}),
        "observation_projects_in_partition": len({r["project_id"] for r in rows
                                                  if r["identity_scope"] == "PROJECT_SCOPE_BOUND"}),
        "numeric_token_located": _rate(sum(r["numeric_location"]["numeric_bound"] for r in numeric), len(numeric)),
        "numeric_token_and_unit_located": _rate(sum(r["numeric_location"]["numeric_bound"]
                                                  and r["numeric_location"]["unit_bound"] for r in numeric), len(numeric)),
        "numeric_normalizable": _rate(sum(r["normalized"] is not None for r in numeric), len(numeric)),
        "automated_evidence_status": dict(Counter(r["assessment"]["evidence_status"] for r in rows)),
        "comparability": dict(Counter(r["assessment"]["comparability"] for r in rows)),
        "verified_comparable_observations": len({_measurement_key(r) for r in comparable}),
        "verified_comparable_projects": len({r["project_id"] for r in comparable if r["project_id"]}),
        "usable_analysis_fields": len({(r["project_id"], r["assessment"]["purpose"], r["variable"]) for r in comparable}),
        "matches_existing_census_selected_observation_id": sum(r["matches_existing_census_selected_observation_id"]
                                                               for r in rows),
        "formal_admission": "NOT_EXECUTED",
        "new_official_admissions": None,
        "resource_evidence": {
            "discovered_observation_representations": len(resource),
            "deduplicated_source_observations": len({_measurement_key(r) for r in resource}),
            "numeric_token_located": _rate(sum(r["numeric_location"]["numeric_bound"] for r in resource), len(resource)),
            "numeric_token_and_unit_located": _rate(sum(r["numeric_location"]["numeric_bound"] and
                                                       r["numeric_location"]["unit_bound"] for r in resource), len(resource)),
            "verified_observation_representations": sum(r["assessment"]["evidence_status"] == "VERIFIED"
                                                        for r in resource),
            "explicit_table_unit_header_representations": sum(
                r["numeric_location"]["status"] == "TABLE_CELL_AND_EXPLICIT_HEADER_BOUND" for r in resource
            ),
            "numeric_dispositions": dict(Counter(r["numeric_location"]["status"] for r in resource)),
            "verification_dispositions": dict(Counter(r["assessment"]["evidence_status"] for r in resource)),
        },
        "resource_duplicate_diagnostics": dict(Counter(r["status"] for r in duplicates)),
        "reported_value_state": dict(Counter(r["reported_value_state"] for r in rows)),
        "resource_arithmetic": dict(Counter(r["resource_arithmetic"] for r in rows)),
        "claim_stance": dict(Counter(r["claim_stance"] for r in rows if r["claim_stance"])),
        "rule_violations_or_limits": dict(Counter(item for r in rows for item in r["rule_violations_or_limits"])),
    }


def run(root, originals, output, *, tessdata=None, cache=None):
    """Recheck all fixed pages, including unreadable, blocked and empty pages."""
    from .nlp import discover_source_observations

    root, output = Path(root).resolve(), Path(output).resolve()
    frame = _load_frame(root)
    cutoff = frame["cutoff"]
    registry = project_registry(root)
    policy = json.loads((root / "config/evidence_policy.json").read_bytes())
    formal_path = root / RELEASE / "resource_statement_observations.csv"
    official = {(row["observation_id"], row["source_sha256"], row["project_id"]) for row in read_csv(formal_path)
                if row["selected_for_census"] == "1"}
    engine = SemanticEngine(root)
    sources, pages, rows, unbound = [], [], [], []
    with PdfDocumentCache(originals, cache=cache) as documents:
        for partition in PARTITIONS:
            for entry in frame["partitions"][partition]:
                sha = entry["source_sha256"]
                identity = {"partition": partition, "source_sha256": sha, "source_key": entry["source_key"],
                            "group_id": entry["group_id"], "stratum": entry["stratum"]}
                reason, found = None, {}
                # Pin one lower-median page per edition for an OCR witness,
                # alongside the default OCR fallback on unreadable native text.
                ocr_sample = entry["pages"][(len(entry["pages"]) - 1) // 2] if tessdata else None
                assets = Path(originals)
                present = (assets / sha).is_file() or (assets / f"{sha}.pdf").is_file()
                try:
                    path = documents.verify(sha)
                except DocumentUnavailable as exc:
                    source_status, reason = "SOURCE_BLOCKED", str(exc)
                else:
                    source_status = "SOURCE_VERIFIED"
                    source = {"sha256": sha, "key": entry["source_key"], "path": str(path.resolve()), "kind": "pdf",
                              "url": "", "publication_date": entry["publication_date"], "acquired_at": entry["acquired_at"]}
                    try:
                        report = discover_source_observations(root, source, registry, page_numbers=entry["pages"],
                                                              cache=cache, tessdata=tessdata,
                                                              ocr_comparison_pages=(ocr_sample,) if ocr_sample else ())
                        found = {page["physical_page"]: page for page in report["pages"]}
                    except DocumentUnavailable as exc:
                        reason = str(exc)
                    except (OSError, ValueError, RuntimeError) as exc:
                        reason = "DOCUMENT_PROCESSING_ERROR:" + type(exc).__name__
                sources.append({**identity, "status": source_status, "reason": reason, "asset_path_present": present,
                                "project_ids": entry["project_ids"],
                                "edition_sha256": entry["edition_sha256"], "expected_pages": entry["pages"]})
                for number in entry["pages"]:
                    page = found.get(number, {})
                    views, parser = _page_views(page)
                    status = page.get("status") or ("SOURCE_BLOCKED" if source_status == "SOURCE_BLOCKED" else
                                                    "PARSE_FAILED" if reason else "PAGE_UNAVAILABLE")
                    candidates = []
                    for raw in page.get("observations", ()):
                        record = _audit_observation(raw, page, views, entry, cutoff, engine, policy, official)
                        candidates.append({**identity, "physical_page": number, **record})
                    literal_gaps = _quantity_literal_gaps(views, parser["method"], page.get("observations", ()))
                    unbound.extend({**identity, "physical_page": number, **literal} for literal in literal_gaps)
                    rows.extend(candidates)
                    pages.append({**identity, "physical_page": number, "status": status, "parser": parser,
                                  "reason": page.get("error") or reason, "candidate_count": len(candidates),
                                  "ocr_comparison_requested": number == ocr_sample,
                                  "unit_bearing_lexemes_without_page_span_link": len(literal_gaps)})
    duplicates = [{"partition": partition, **item} for partition in PARTITIONS
                  for item in _resource_duplicates([row for row in rows if row["partition"] == partition])]
    report = {"status": "QUALITY_COMPLETE", "schema": RULE_VERSION, "frame_sha256": filehash(root / FRAME),
              "cutoff": cutoff, "classification": frame["classification"], "design": frame["design"],
              "formal_effect": "SIDE_OUTPUT_ONLY", "formal_admission": "NOT_EXECUTED",
              "existing_selection_input_sha256": filehash(formal_path), "identity_registry_sha256": digest(registry),
              "rule_inputs_sha256": {name: filehash(root / name) for name in (
                  "config/evidence_policy.json", "config/ontology/observation_v1.json",
                  "config/ontology/comparability_v1.json", "config/ontology/shadow_profiles_v1.json",
              )},
              "rule_code_sha256": {name: filehash(Path(__file__).with_name(name)) for name in (
                  "observation_quality.py", "nlp.py", "observation_schema.py", "observation_semantics.py",
                  "numeric_evidence.py", "document_processing.py", "pdf_extract.py", "technical_tables.py",
                  "semantic_resource.py", "semantic_technical.py", "normalization.py", "ontology.py",
              )},
              "independent_accuracy": {"status": "UNMEASURED_NO_INDEPENDENT_REFERENCE", "precision": None,
                                       "recall": None, "f1": None, "false_admissions": None,
                                       "false_exclusions": None},
              "denominator_scope": {"sources": "all preregistered editions", "pages": "every preregistered physical page",
                                    "numeric_representations": "all discovered non-event representations",
                                    "parser_page_agreement": "pages with at least two nonempty parser views",
                                    "parser_quote_agreement": "numeric representations with two candidate quote comparisons",
                                    "unbound_lexemes": "unit-bearing lexical readings without an exact page-span cross-link, including tables"},
              "partitions": {partition: _section(*([row for row in records if row["partition"] == partition]
                                                  for records in (sources, pages, rows, duplicates))) for partition in PARTITIONS}}
    output.mkdir(parents=True, exist_ok=True)
    jsonl(output / "sources.jsonl", sources)
    jsonl(output / "pages.jsonl", pages)
    jsonl(output / "observations.jsonl", rows)
    jsonl(output / "unbound_lexemes.jsonl", unbound)
    jsonl(output / "resource_duplicates.jsonl", duplicates)
    report["scientific_outputs_sha256"] = {name: filehash(output / name) for name in QUALITY_ARTIFACTS}
    write(output / "quality.json", json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    return report


def _source_identity(row):
    return (row["partition"], row["source_key"], row["source_sha256"], row["group_id"], row["stratum"])


def _fixed_artifacts(folder):
    folder = Path(folder)
    manifest = (folder / "quality.json").read_bytes()
    report = json.loads(manifest)
    if (report["schema"] not in {"observation-automated-quality-v1", RULE_VERSION}
            or report["status"] != "QUALITY_COMPLETE"):
        raise ValueError("A completed fixed quality report is required")
    rows = {}
    for name in QUALITY_ARTIFACTS:
        original = (folder / name).read_bytes()
        if sha256(original).hexdigest() != report["scientific_outputs_sha256"].get(name):
            raise ValueError(f"Unverified fixed quality output: {name}")
        if name in {"sources.jsonl", "pages.jsonl", "observations.jsonl"}:
            rows[name] = [json.loads(line) for line in original.splitlines()]
    sources = {_source_identity(r): r for r in rows["sources.jsonl"]}
    expected = {(identity, page) for identity, source in sources.items() for page in source["expected_pages"]}
    pages = {(_source_identity(r), r["physical_page"]) for r in rows["pages.jsonl"]}
    observations = {(_source_identity(r), r["physical_page"]) for r in rows["observations.jsonl"]}
    if (len(sources) != len(rows["sources.jsonl"]) or len(pages) != len(rows["pages.jsonl"])
            or pages != expected or not observations <= pages):
        raise ValueError("Fixed quality observations do not match the source and page inventory")
    return report, sha256(manifest).hexdigest(), rows


def _comparison_metrics(rows, selected):
    result = {}
    for partition in PARTITIONS:
        sources, pages, observations = [
            [row for row in rows[name] if row["partition"] == partition and _source_identity(row) in selected]
            for name in QUALITY_ARTIFACTS[:3]
        ]
        metrics = _section(sources, pages, observations, _resource_duplicates(observations))
        result[partition] = {key: metrics[key] for key in (
            "expected_sources", "source_asset_available", "source_fingerprint_match", "expected_pages", "page_status",
            "discovered_observation_representations", "deduplicated_source_observations", "numeric_token_located",
            "numeric_token_and_unit_located", "numeric_normalizable", "automated_evidence_status",
            "verified_comparable_observations", "verified_comparable_projects", "resource_evidence",
        )}
    return result


def compare_fixed(baseline, updated, output=None):
    """Compare archived quality receipts without blending acquisition and extraction effects."""
    before, before_sha, before_rows = _fixed_artifacts(baseline)
    after, after_sha, after_rows = _fixed_artifacts(updated)
    before_sources, after_sources = (
        {_source_identity(row): (row["expected_pages"], row["edition_sha256"], row["project_ids"])
         for row in rows["sources.jsonl"]} for rows in (before_rows, after_rows)
    )
    frame_keys = ("frame_sha256", "cutoff", "classification")
    if any(before[key] != after[key] for key in frame_keys) or before_sources != after_sources:
        raise ValueError("Compare additions or changed partitions separately from the fixed frame")
    availability = [
        {_source_identity(row): {"status": row["status"], "asset_path_present": row["asset_path_present"]}
         for row in records["sources.jsonl"]} for records in (before_rows, after_rows)
    ]
    changes = [{"partition": source[0], "source_key": source[1], "source_sha256": source[2],
                "before": availability[0][source], "after": availability[1][source]}
               for source in sorted(before_sources) if availability[0][source] != availability[1][source]]
    comparison = {
        "schema": "fixed-observation-quality-comparison-v1",
        "status": "COVERAGE_CHANGED" if changes else "SAME_SOURCE_COVERAGE",
        "interpretation": "FIXED_FRAME_ENGINEERING_REGRESSION",
        **{key: before[key] for key in frame_keys},
        "report_sha256": {"baseline": before_sha, "updated": after_sha},
        "rule_code_sha256": {"baseline": before["rule_code_sha256"], "updated": after["rule_code_sha256"]},
        "rule_inputs_sha256": {"baseline": before["rule_inputs_sha256"], "updated": after["rule_inputs_sha256"]},
        "verified_source_coverage_changes": changes,
        "full_frame": {"baseline": _comparison_metrics(before_rows, before_sources),
                       "updated": _comparison_metrics(after_rows, after_sources)},
        "formal_admission": "NOT_EXECUTED",
    }
    if changes:
        matched = {key for key in before_sources if all(scope[key]["status"] == "SOURCE_VERIFIED"
                                                       for scope in availability)}
        comparison["matched_verified_sources"] = {
            "baseline": _comparison_metrics(before_rows, matched),
            "updated": _comparison_metrics(after_rows, matched),
        }
    if output is not None:
        atomic_json(output, comparison)
    return comparison
