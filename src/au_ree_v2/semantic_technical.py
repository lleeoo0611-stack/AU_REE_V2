"""Source-bound extraction for the existing within-table elemental leach use.

The pre-existing technical cells supply physical identity and the scalar
baseline. A narrow adapter verifies each eligible cell in the original and
links its printed caption/headers to explicitly identified experimental text.
No row is promoted into project-level performance by this adapter.
"""

import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from .document_processing import DocumentUnavailable, PdfDocumentCache
from .technical import technical_compare
from .technical_tables import quantity_binding, technical_cells, technical_numbers


PROFILE = "WITHIN_TABLE_ELEMENT_LEACH"
VERSION = "source-bound-table-leach-v1"
BASELINE_VERSION = "frozen-technical-cells-projection-v1"
CONTEXT_FIELDS = (
    "scope", "case_id", "table_scope_id", "sample_id", "sample_population", "test_id", "basis",
    "feed", "endpoint", "scale", "process_stage", "grain_mm", "acid_concentration", "acid_unit",
    "reagent", "source_column", "study_date", "date_role", "evidence_mode", "statistic",
    "reagent_basis_warning", "scenario",
)
NUMERIC_FIELDS = ("value", "grain_mm", "acid_concentration")
INTEGER_FIELDS = ("physical_page", "table_index", "row_index", "column_index", "source_column")
JSON_FIELDS = ("bbox", "header_path", "bounds", "limitations", "allowed_analysis", "contract_reasons", "raw")
CAPTION = re.compile(
    r"^Table\s+(?P<table>\d+)\s*[-–—:]\s*Summary of (?P<program>[\w -]+?)\s+"
    r"Bottle[- ]roll Results for (?P<sample>[\w-]+)$", re.I,
)
BOUNDARY = re.compile(r"\s*(?:;|\bbut\b|\bwhereas\b|\bwhile\b)\s*|(?<!\d)\.\s+|(?<=%)\.\s+", re.I)
ANALYTE = r"TREO|MREO|CeO2|Nd2O3|Pr6O11|Dy2O3|Tb4O7|Nd|Pr|Dy|Tb|Ce"
CLAIM_CUES = {
    "NEGATED": r"\b(?:did not|does not|was not|were not|never|no evidence of)\b",
    "CONDITIONAL": r"\b(?:if|assuming|provided that|subject to)\b",
    "TARGET": r"\b(?:target(?:s|ed|ing)?|expected|planned|will|aim(?:s|ed)?)\b",
    "HISTORICAL_REFERENCE": r"\b(?:previous|historical|earlier|prior)\b",
    "ENGINEERING_DESIGN": r"\b(?:design(?:ed)?|model(?:led|ed)?|forecast)\b",
    "TESTWORK": r"\b(?:testwork|tests?|laboratory|bench|bottle[- ]roll|pilot[- ]scale)\b",
    "ACTUAL_OPERATING_RESULT": r"\b(?:commercial operations?|operating plant|plant operated)\b",
}


def technical_rows(cells_path, resolved_path):
    """Load the public technical export with its original attribution and dates."""
    with Path(resolved_path).open(encoding="utf-8-sig", newline="") as stream:
        resolved = {}
        for row in csv.DictReader(stream):
            key = (row["evidence_id"], row["project_id"])
            if key in resolved and resolved[key] != row:
                raise ValueError(f"Conflicting resolved technical evidence: {key}")
            resolved[key] = row
    with Path(cells_path).open(encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream):
            item = resolved[row["evidence_id"], row["project_id"]]
            if row["source_sha256"] != item["source_sha256"] or row["physical_page"] != item["pdf_page"]:
                raise ValueError(f"Technical cell source locator does not reconcile: {row['evidence_id']}")
            for key in NUMERIC_FIELDS + INTEGER_FIELDS + JSON_FIELDS:
                if key not in row:
                    continue
                parse = float if key in NUMERIC_FIELDS else int if key in INTEGER_FIELDS else json.loads
                row[key] = parse(row[key]) if row[key] else None
            raw = json.loads(item["raw"]) if item["raw"] else {}
            row.update(variable=item["variable"], study_date=item["effective_date"] or None,
                       date_role=raw.get("date_role"), attribution=item["attribution"],
                       sample_population=raw.get("sample_population") or row["sample_id"] or None,
                       evidence_reason=row["selection_reason"] or None)
            yield row


def _flat(text):
    return " ".join(str(text or "").split())


def _anchor(sha, page, quote, role, **location):
    return {"source_sha256": sha, "physical_page": page, "quote": _flat(quote),
            "role": role, **location}


def baseline_technical(candidates):
    """Expose the original extractor's cells in the shared observation shape."""
    results = []
    for row in candidates:
        identifier = row.get("evidence_id") or row["candidate_id"]
        sha, page = row["source_sha256"], row["physical_page"]
        context = {key: row.get(key) or None for key in CONTEXT_FIELDS}
        mode = row.get("evidence_mode")
        context["claim_nature"] = mode if mode in {"TESTWORK", "ENGINEERING_MODEL"} else "UNKNOWN"
        context["project_attribution"] = row.get("attribution")
        results.append({
            "candidate_id": identifier, "observation_id": identifier, "project_id": row["project_id"],
            "source_sha256": sha, "physical_page": page, "profile_id": PROFILE, "use": PROFILE,
            "native": {"quantity": row["quantity"], "variable": row.get("variable") or
                       "reported_technical_" + row["quantity"], "token": row.get("original_token"),
                       "unit": row.get("unit"), "value": row.get("value"), "bounds": row.get("bounds"),
                       "token_state": row.get("token_state")},
            "context": context, "status": "CANDIDATE",
            "provenance": {"source_case_id": row.get("case_id"), "table_caption": row.get("table_caption"),
                           "header_path": row.get("header_path") or [], "limitations": row.get("limitations") or [],
                           "table_index": row.get("table_index"), "row_index": row.get("row_index"),
                           "column_index": row.get("column_index"), "bbox": row.get("bbox"),
                           "legacy_reasons": (row.get("contract_reasons") or {}).get(PROFILE)},
            "evidence_reason": row.get("evidence_reason") or row.get("selection_reason") or None,
            "anchors": [_anchor(sha, page, row.get("original_token"), "FROZEN_TABLE_CELL", bbox=row.get("bbox"))],
            "extraction_version": BASELINE_VERSION,
        })
    return sorted(results, key=lambda r: r["candidate_id"])


def _quoted_headers(headers, page):
    if not headers:
        return False
    # The geometric extractor can insert whitespace (for example 50 g/L).
    # Require the complete header text after removing whitespace, never a fuzzy match.
    compact = re.sub(r"\s+", "", page).casefold()
    return all(re.sub(r"\s+", "", h).casefold() in compact for h in headers if _flat(h))


def _program_text(texts, program):
    pattern = re.compile(r"^\s*" + re.escape(program) + r"\s*:\s*(?:intermittent\s+)?"
                         r"bottle[- ]roll\s+leach\s+testing\s*$", re.I)
    found = []
    for page, text in enumerate(texts, 1):
        lines = text.splitlines()
        for i, line in enumerate(lines):
            if not pattern.fullmatch(line.strip()):
                continue
            paragraph = []
            for following in lines[i+1:]:
                if re.fullmatch(r"\s*\d+(?:\.\d+)*\.\s*", following):
                    break
                paragraph.append(following)
            found.append((page, line, _flat(" ".join(paragraph))))
    return found[0] if len(found) == 1 else None


def _sample_reference(texts, sample, number):
    # Link the sample within the same sentence or a directly adjoining source
    # sentence explicitly saying where those results are presented.
    pattern = re.compile(
        r"\b" + re.escape(sample) + r"\s+composite\b[^.;]{1,490}?"
        r"(?:\s|\.\s*The results are presented in\s+)Table\s+" + number + r"\b", re.I,
    )
    found = [(page, match.group()) for page, text in enumerate(texts, 1)
             for match in pattern.finditer(_flat(text))]
    return found[0] if len(found) == 1 else None


def _technical_context(record, texts, actual, relations):
    current = record["physical_page"]
    sha = record["source_sha256"]
    printed = texts[current - 1]
    source_row = record["provenance"]
    native = record["native"]
    if actual is None or any(actual.get(k) != native.get(k) for k in ("unit", "value", "bounds", "token_state")):
        return dict(record, status="BLOCKED", evidence_reason="ORIGINAL_TECHNICAL_TOKEN_MISMATCH")
    raw_value = actual["original_token"]
    geometry = all(abs(a - b) < .01 for a, b in zip(source_row["bbox"], actual["bbox"]))
    if (not geometry or _flat(raw_value) != _flat(native["token"])
            or actual["basis"] != record["context"]["basis"]
            or actual["source_column"] != record["context"]["source_column"]):
        return dict(record, status="BLOCKED", evidence_reason="ORIGINAL_TECHNICAL_TOKEN_MISMATCH")
    caption = _flat(source_row["table_caption"])
    parsed = CAPTION.fullmatch(caption)
    headers = source_row["header_path"]
    if not parsed or headers != actual["header_path"] or not _quoted_headers(headers, printed):
        return dict(record, status="INSUFFICIENT", evidence_reason="ORIGINAL_TABLE_HEADER_UNVERIFIED")
    if (parsed["sample"] != record["context"]["sample_id"]
            or len([line for line in printed.splitlines() if _flat(line) == caption]) != 1):
        return dict(record, status="INSUFFICIENT", evidence_reason="AMBIGUOUS_TABLE_OR_SAMPLE_BINDING")
    if caption not in relations:
        relations[caption] = _program_text(texts, parsed["program"]), _sample_reference(texts, parsed["sample"], parsed["table"])
    program, reference = relations[caption]
    if not program or not reference:
        return dict(record, status="INSUFFICIENT", evidence_reason="EXPLICIT_PROGRAM_OR_SAMPLE_LINK_MISSING")
    context = dict(record["context"], process_stage="LEACH_EXTRACTION", claim_nature="TESTWORK")
    relation = dict(program=parsed["program"], sample=parsed["sample"], table_number=parsed["table"],
                    proof="EXPLICIT_PROGRAM_CAPTION_AND_SAMPLE_TABLE_REFERENCE")
    procedure_page, heading, paragraph = program
    anchors = [
        _anchor(sha, current, raw_value, "VERIFIED_TABLE_CELL", bbox=actual["bbox"],
                row_index=actual["row_index"], column_index=actual["column_index"], table_index=actual["table_index"]),
        _anchor(sha, current, caption, "TABLE_CAPTION"),
        _anchor(sha, reference[0], reference[1], "EXPLICIT_SAMPLE_TABLE_REFERENCE"),
        _anchor(sha, procedure_page, heading, "PROGRAM_LEACH_PROCEDURE"),
    ]
    for name, pattern in {
        "procedure_duration_days": r"over\s+(\d+)\s+days",
        "pulp_density_mass_pct": r"pulp density of\s+(\d+(?:\.\d+)?)\s*w/w%",
        "aliquot_mass_kg": r"(\d+(?:\.\d+)?)\s*kg aliquot",
    }.items():
        reasoning = list(re.finditer(pattern, paragraph, re.I))
        if len(reasoning) == 1:
            match = reasoning[0]
            context[name] = float(match[1])
            anchors.append(_anchor(sha, procedure_page, match[0], name))
    liquid_phase = re.search(r"Elemental analysis of the leach solutions was performed using [\w-]+", paragraph, re.I)
    if liquid_phase:
        context["endpoint"] = "LEACH_SOLUTION"
        anchors.append(_anchor(sha, procedure_page, liquid_phase[0], "ANALYTICAL_ENDPOINT"))
    if context.get("acid_unit") == "g/L":
        acid = re.search(r"starting initial hydrochloric acid concentration \([^)]*kg/t\)", paragraph, re.I)
        if acid:
            context["reagent_basis_warning"] = "PRINTED_G_L_AND_PROCEDURE_KG_T_NOT_RECONCILED"
            anchors.append(_anchor(sha, procedure_page, acid[0], "REAGENT_BASIS_MISMATCH"))
    return dict(record, context=context, anchors=anchors, relation=relation,
                status="SOURCE_VERIFIED_CANDIDATE")


def extract_technical(candidates, assets, *, documents=None):
    """Verify original cells and attach explicit procedure links before scoring."""
    return reextract_technical(baseline_technical(candidates), assets, documents=documents)


def reextract_technical(captured, assets, *, documents=None):
    """Re-read source-bound cells using the frozen or live legacy projection."""
    if documents is None:
        with PdfDocumentCache(assets) as cache:
            return reextract_technical(captured, assets, documents=cache)
    import pymupdf

    groups = defaultdict(list)
    for row in captured:
        groups[row["source_sha256"]].append(row)
    result = []
    for sha, rows in sorted(groups.items(), key=lambda item: str(item[0])):
        relevant = [row for row in rows if row["native"]["quantity"] == "extraction_pct"]
        result.extend(row for row in rows if row["native"]["quantity"] != "extraction_pct")
        if not relevant:
            continue
        try:
            document = documents.open(sha)
        except DocumentUnavailable:
            result.extend(dict(row, extraction_version=VERSION, status="BLOCKED",
                               evidence_reason="ORIGINAL_TECHNICAL_SOURCE_UNVERIFIED") for row in relevant)
            continue
        texts = [document.text(page) for page in range(1, len(document) + 1)]
        relations = {}
        geometry_by_page = {}
        for original in relevant:
            row = dict(original, extraction_version=VERSION)
            page = row["physical_page"]
            box = row["provenance"]["bbox"]
            if row["evidence_reason"]:
                result.append(dict(row, status="BLOCKED"))
                continue
            if type(page) is not int or not 1 <= page <= len(document) or not box:
                result.append(dict(row, status="BLOCKED", evidence_reason="ORIGINAL_TECHNICAL_LOCATOR_UNBOUND"))
                continue
            rect = pymupdf.Rect(box)
            if not pymupdf.Rect(document.bounds(page)).contains(rect) or rect.is_empty:
                result.append(dict(row, status="BLOCKED", evidence_reason="ORIGINAL_TECHNICAL_LOCATOR_UNBOUND"))
                continue
            if page not in geometry_by_page:
                tables, error = document.tables(page)
                geometry_by_page[page] = ({
                    (cell["table_index"], cell["row_index"], cell["column_index"]): cell
                    for table in tables
                    for cell in technical_cells(table, document.text(page, positioned=True))
                    if cell["quantity"] == "extraction_pct"
                }, error)
            cells, error = geometry_by_page[page]
            if error:
                result.append(dict(row, status="BLOCKED", evidence_reason="ORIGINAL_TECHNICAL_TABLE_UNREADABLE",
                                   table_parser_error=error))
                continue
            indices = tuple(row["provenance"][key] for key in ("table_index", "row_index", "column_index"))
            result.append(_technical_context(row, texts, cells.get(indices), relations))
    return sorted(result, key=lambda row: row["candidate_id"])


def technical_gate(candidate, policy, version):
    """Evaluate the historical technical contract on either extraction snapshot."""
    native, context = candidate["native"], candidate["context"]
    contract = policy["technical_analysis"]["contracts"][PROFILE]
    record = {**context, **native, "evidence_reason": candidate["evidence_reason"]}
    reasons = technical_compare(record, contract, contract.get("model_assumptions", []))
    if native["variable"] not in contract["variables"]:
        status = "NOT_APPLICABLE"
    elif candidate["status"] == "BLOCKED" or (candidate["evidence_reason"] and candidate["status"] == "CANDIDATE"):
        status = "BLOCKED"
    elif candidate["status"] == "INSUFFICIENT" or native["value"] is None:
        status = "INSUFFICIENT"
    elif reasons:
        status = "INSUFFICIENT" if set(reasons) <= {"MISSING_CONDITIONS", "SCOPE_MISMATCH"} else "INCOMPATIBLE"
    else:
        status = "ACCEPT"
    reason = candidate["evidence_reason"] or "|".join(reasons) or "HISTORICAL_TECHNICAL_USE_SATISFIED"
    return dict(status=status, reason=reason, reasons=reasons, evidence_reason=candidate["evidence_reason"],
                profile_id=PROFILE, profile_version=contract["version"], validator_version=version)


def _named_clause_number(clause, number):
    result = quantity_binding(clause, number)
    if result["quantity_role"]:
        return result
    # Preserve a negated or targeted quantity as a source mention even if it
    # cannot be interpreted as an observed process value.
    prefix = clause[:number["start"]]
    suffix = clause[number["start"] + len(number["token"]):]
    bound_after = re.match(r"\s*(" + ANALYTE + r")\s+(recovery|extraction)\b", suffix, re.I)
    if bound_after:
        return dict(quantity_role="REPORTED_" + bound_after[2].upper(), basis=bound_after[1])
    bound_before = re.search(r"\b(recovery|extraction)\s+of\s+(" + ANALYTE + r")\s+(?:at|was|is|reached)\s*$",
                             prefix, re.I)
    if bound_before:
        return dict(quantity_role="REPORTED_" + bound_before[1].upper(), basis=bound_before[2])
    match = re.search(r"\b(?:(" + ANALYTE + r")\s+)?(recovery|extraction)\b(?:(?![%;]).){0,60}$", prefix, re.I)
    if match and re.search(r"\b(?:did not|does not|target(?:ed)?|expected|assuming|if)\b", prefix, re.I):
        return dict(quantity_role="REPORTED_" + match[2].upper(), basis=match[1])
    return result


def narrative_mentions(text, source_sha256, physical_page):
    """Preserve scoped claim mentions, using local clause cues and token offsets."""
    result = []
    positions = [0, *(m.end() for m in BOUNDARY.finditer(text))]
    for start, end in zip(positions, [*positions[1:], len(text)]):
        clause = text[start:end]
        preceding_end = 0
        for number in technical_numbers(clause):
            binding = _named_clause_number(clause, number)
            local = clause[preceding_end:number["start"]]
            preceding_end = number["start"] + len(number["token"])
            if not binding["quantity_role"]:
                continue
            marker = next((key for key, pattern in CLAIM_CUES.items() if re.search(pattern, local, re.I)), "UNKNOWN")
            offset = start + number["start"]
            result.append({**binding, "native": dict(number), "claim_nature": marker,
                           "anchor": _anchor(source_sha256, physical_page, clause, "TECHNICAL_NARRATIVE_CLAUSE",
                                             offset=[offset, offset + len(number["token"])])})
    return result


def technical_audit(before, after):
    """Expose case and missing-field counts, preserving the non-target denominator."""
    def counts(rows):
        return {"observations": len(rows), "projects": len({r["project_id"] for r in rows}),
                "states": dict(Counter(r["status"] for r in rows)),
                "missing": {key: sum(r["context"].get(key) is None for r in rows)
                            for key in ("feed", "endpoint", "scale", "process_stage", "test_id")}}
    return {"all_technical_cells": counts(before),
            "target_before": counts([r for r in before if r["native"]["quantity"] == "extraction_pct"]),
            "target_after": counts([r for r in after if r["native"]["quantity"] == "extraction_pct"]),
            "target_linked_fields": dict(Counter(a["role"] for r in after if r.get("relation") for a in r["anchors"])),
            "other_technical_cells": counts([r for r in before if r["native"]["quantity"] != "extraction_pct"])}
