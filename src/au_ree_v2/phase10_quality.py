"""Measure resource-pipeline quality against frozen locators and explicit controls."""

from collections import Counter, defaultdict
from contextlib import ExitStack
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from importlib.metadata import version
import json
from pathlib import Path

import pymupdf
from pypdf import PdfReader
from pypdf.errors import DependencyError, PdfReadError

from .normalization import MASS_FRACTION, MASS_IN_TONNES, unit_factor
from .numeric_evidence import numeric_token_spans, quantity_literals, scalar_decimal
from .observation_schema import (
    EvidenceAnchor, RawObservation, TextSpan, raw_from_payload, validate_normalized_binding, value_evidence_issue,
)
from .observation_semantics import SemanticEngine
from .store import canonical, digest, filehash
from .tabular import read_csv


VERSION = "phase10-silver-quality-v1"
BASELINE = "results/phase22-2026-11-06/resolved_evidence.csv"
LOCK = "results/phase22-2026-11-06/snapshot_lock.json"
CENSUS = "results/ree-project-census/coverage-locked-20261125"
CENSUS_FACTS = f"{CENSUS}/resource_statement_observations.csv"
CENSUS_RECEIPT = f"{CENSUS}/source_selection.csv"
FROZEN_INPUTS = {
    BASELINE: "f66bb33519686526d166f729055742ea7ac66766f86e1435f49ac687b6964bc8",
    LOCK: "3d0848bd302294ff247bd931579e0c5fcec25f0908c83dd72a9fdfeada97981d",
}
CENSUS_INPUTS = {
    CENSUS_FACTS: "067e6bf1d8ba46426fb5f16ec7ab404606aa58c181b6ec57445ea6321e97aeb2",
    CENSUS_RECEIPT: "aa475199f5e13d1f14e3807e4ebfb70ec062e80d70cbc757a36e9452b1aafa75",
}
CLASSES = ("DETERMINISTIC_VERIFIED", "CROSS_SOURCE_SUPPORTED", "PARSER_CONSENSUS",
           "SYNTHETIC_GROUND_TRUTH", "UNVERIFIED")
RESOURCE_GATES = {"SOURCE_BOUND_CANONICAL", "CORROBORATING_PRESENTATION"}
ACCEPTED_EVIDENCE = "VALID_RAW_EVIDENCE"


def rate(numerator, denominator, *, unmeasured=None):
    return {"numerator": numerator, "denominator": denominator,
            "value": numerator / denominator if denominator and unmeasured is None else None,
            "status": "MEASURED" if denominator and unmeasured is None else "UNMEASURED",
            **({"reason": unmeasured} if unmeasured else {})}


def _flat(text):
    return " ".join(text.split()) if text else ""


def _literal(value):
    try:
        number = Decimal(value)
    except (InvalidOperation, TypeError):
        return None
    return number if number.is_finite() else None


def _read(value):
    return value if isinstance(value, dict) else json.loads(Path(value).read_bytes())


def _find_original(root, locations, assets, sha):
    paths = ([assets / sha, assets / f"{sha}.pdf"] if assets else []) + [
        root / "data/snapshots" / f"{sha}.pdf", *locations.get(sha, ()),
    ]
    return next((path for path in paths if path.is_file() and filehash(path) == sha), None)


def _locations(root):
    data = _read(root / "data/manifest.json")
    snapshots = data["snapshots"] if isinstance(data, dict) else data
    found = defaultdict(list)
    for entry in snapshots:
        if entry.get("kind") == "pdf" and entry.get("path"):
            path = (root / entry["path"]).resolve()
            if path.is_relative_to(root):
                found[entry["sha256"]].append(path)
    return found


def _published_marker(text, marker):
    marker = _flat(str(marker))
    if not marker:
        return False
    if _literal(marker.replace(",", "")) is not None:
        return bool(numeric_token_spans(text, marker))
    return marker.casefold() in text.casefold()


def _unique_quote_witness(text, quote, value, unit):
    if not quote or text.count(quote) != 1:
        return False
    start = text.index(quote)
    return any(start <= left < right <= start + len(quote)
               for left, right in numeric_token_spans(text, value, unit))


def _bound_original(row, raw, text, pages):
    if not text or not row["locator"]:
        return None, "ARCHIVED_LOCATOR_OR_ORIGINAL_TEXT_UNAVAILABLE"
    quote, declared = _flat(raw.get("raw_text")), raw.get("original_token") or raw.get("original_value")
    unit = raw.get("original_unit") or row["unit"]
    markers = raw.get("page_markers") or []
    if declared and _unique_quote_witness(text, quote, str(declared), unit):
        return {"literal": str(declared), "unit": unit, "page_certainty": "EXACT_ARCHIVED_QUOTE"}, None
    if declared and row.get("archive") == CENSUS_FACTS:
        spans = numeric_token_spans(text, str(declared), unit)
        units_at_start = {reading.start for reading in quantity_literals(text)}
        if len(spans) == 1 and spans[0][0] in units_at_start:
            return {"literal": str(declared), "unit": unit,
                    "page_certainty": "UNIQUE_ARCHIVED_LITERAL_WITH_PRINTED_UNIT"}, None
        return None, "CENSUS_ARCHIVED_LITERAL_OR_ADJACENT_UNIT_UNBOUND"
    if not markers or not all(_published_marker(text, marker) for marker in markers):
        return None, "ARCHIVED_MARKERS_NOT_ALL_BOUND"
    value = _literal(row["value"])
    if value is None:
        return None, "ARCHIVED_VALUE_NOT_SCALAR"
    # A number computed during a historical transform is not a printed source token.
    if any(raw.get(key) for key in ("transform", "source_transform", "basis_transform", "species_conversion")):
        return None, "ARCHIVED_ROW_HAS_TRANSFORM"
    forms = {format(value, "f"), format(value.normalize(), "f"), format(value, ",f"),
             format(value.normalize(), ",f")}
    occurrences = {(start, end) for form in forms for start, end in numeric_token_spans(text, form, unit)}
    selected = {text[start:end] for start, end in occurrences}
    if len(selected) != 1:
        return None, "PRINTED_VALUE_ABSENT_OR_AMBIGUOUS"
    printed, = selected
    # Other occurrences are permitted for the page-level retrieval target. Cell
    # comparisons still require an exact prior grid location (recorded below).
    return {"literal": printed, "unit": unit, "page_certainty": "ARCHIVED_MARKERS_AND_PRINTED_LITERAL",
            "same_literal_occurrences": len(occurrences), "physical_pages_in_original": pages}, None


def _reference(row, raw, binding, reason, text, view, input_sha):
    page = int(row["pdf_page"])
    coordinates = {name: raw.get(f"{name}_index") for name in ("table", "row", "column")}
    cell = coordinates if all(type(value) is int and value >= 0 for value in coordinates.values()) else None
    return {
        "reference_id": row["evidence_id"],
        "project_id": row["project_id"], "source_sha": row["source_sha256"],
        "locator": {"page": page, "published_description": row["locator"], "cell": cell,
                    "verification": binding},
        "raw_value": binding["literal"] if binding else raw.get("original_token"),
        "unit": binding["unit"] if binding else raw.get("original_unit") or row["unit"],
        "baseline_value": row["value"], "baseline_unit": row["unit"],
        "quantity_kind": row["domain"], "quantity": row["variable"], "species": row["basis"] or None,
        "material_basis": raw.get("material_basis"), "estimate_scope": row["scope"] or None,
        "cutoff": raw.get("cutoff_grade") or raw.get("cutoff"),
        "research_as_of": row.get("research_as_of", "2026-11-05"),
        "evidence_chain": {"archive": row.get("archive", BASELINE), "archive_sha256": input_sha,
                           "archive_observation_id": row["evidence_id"],
                           "original_page_text_sha256": digest(text) if text else None,
                           "original_page_text_view": view,
                           "archive_label_provenance": raw.get("extraction_method") or row["reason"]},
        "reference_method": "FROZEN_BASELINE_NUMERIC_AND_ORIGINAL_PDF_PAGE",
        "reference_class": "DETERMINISTIC_VERIFIED" if binding else "UNVERIFIED",
        "confidence_status": "PREEXISTING_SILVER_PAGE_TARGET" if binding else "UNVERIFIED",
        "unverified_reason": reason, "independent_truth": False,
    }


def _census_references(root, sources):
    source_rows = [row for row in read_csv(root / CENSUS_RECEIPT)
                   if row["source_sha256"] in sources and row["kind"] == "pdf"
                   and row["version_status"] == "PINNED_SHA_VERIFIED"
                   and row["cutoff"] == "2026-11-13" and row["cutoff_status"] == "WITHIN_CUTOFF"]
    eligible = {row["source_sha256"] for row in source_rows}
    for row in read_csv(root / CENSUS_FACTS):
        if (row["source_sha256"] not in eligible or row["selected_for_census"] != "1"
                or not row["project_id"] or not row["physical_page"].isdigit() or not row["unit"]
                or _literal(row["value"]) is None):
            continue
        yield {
            **row, "evidence_id": row["observation_id"], "pdf_page": row["physical_page"], "domain": "Resource",
            "reason": "ARCHIVED_SELECTED_CENSUS_OBSERVATION", "archive": CENSUS_FACTS,
            "research_as_of": "2026-11-13", "raw": canonical({
                "original_token": row["original_token"], "original_unit": row["original_unit"],
                "cutoff": row["cutoff"], "material_basis": row["material_basis"] or None,
                "source_transform": row["source_transform"],
            }),
        }


def _references(root, frame, assets, cutoff):
    inputs = {**FROZEN_INPUTS}
    if cutoff == "2026-11-13":
        inputs.update(CENSUS_INPUTS)
    if any(filehash(root / name) != sha for name, sha in inputs.items()):
        raise ValueError("A frozen historical reference input differs from its recorded fingerprint")
    sources = {row["source_sha256"] for row in frame["sources"]}
    lock = _read(root / LOCK)
    entries = lock.get("snapshots", []) if isinstance(lock, dict) else lock
    known = {row["sha256"] for row in entries} if isinstance(entries, list) else set()
    indexed = _locations(root)
    by_source = defaultdict(list)
    for row in read_csv(root / BASELINE):
        if (row["source_sha256"] in sources and row["reason"] == ACCEPTED_EVIDENCE and row["origin"] == "OBSERVATION"
                and row["domain"] in {"Resource", "Strategic"} and row["project_id"] and row["pdf_page"].isdigit()
                and row["unit"] and _literal(row["value"]) is not None):
            by_source[row["source_sha256"]].append(row)
    archive_ids = {row["evidence_id"] for rows in by_source.values() for row in rows}
    if cutoff == "2026-11-13":
        for row in _census_references(root, sources):
            if row["evidence_id"] not in archive_ids:
                by_source[row["source_sha256"]].append(row)
    references = []
    original_status = {}
    for sha in sorted(sources):
        path = _find_original(root, indexed, assets, sha)
        reason = "ORIGINAL_SHA_UNAVAILABLE"
        view = None
        primary_error = None
        texts, pages = {}, 0
        with ExitStack() as stack:
            if path is not None:
                try:
                    reader = PdfReader(path)
                    pages, view, reason = len(reader.pages), "PYPDF_NATIVE", None
                    def read_page(page):
                        return reader.pages[page - 1].extract_text()
                except (OSError, ValueError, DependencyError, PdfReadError) as exc:
                    primary_error = type(exc).__name__
                    try:
                        native = stack.enter_context(pymupdf.open(path))
                        pages, view, reason = len(native), "MUPDF_NATIVE_FALLBACK", None
                        def read_page(page):
                            return native[page - 1].get_text()
                    except (OSError, ValueError, pymupdf.FileDataError) as exc:
                        reason = f"ORIGINAL_TEXT_UNREADABLE:{type(exc).__name__}"
            original_status[sha] = {"sha_verified": path is not None, "archive_snapshot_listed": sha in known,
                                    "source_text_status": reason or "SOURCE_OPENED", "view": view,
                                    "pypdf_open_error": primary_error}
            for row in sorted(by_source[sha], key=lambda item: item["evidence_id"]):
                raw = json.loads(row["raw"])
                page = int(row["pdf_page"])
                if 1 <= page <= pages and page not in texts:
                    try:
                        texts[page] = _flat(read_page(page))
                    except (OSError, ValueError, DependencyError, PdfReadError):
                        texts[page] = ""
                text = texts.get(page, "")
                binding, issue = _bound_original(row, raw, text, pages)
                if row.get("archive", BASELINE) == BASELINE and sha not in known:
                    binding, issue = None, "ORIGINAL_NOT_IN_FROZEN_PHASE22_LOCK"
                references.append(_reference(row, raw, binding, reason or issue, text, view,
                                             inputs[row.get("archive", BASELINE)]))
    return references, original_status, inputs


def _retrieval(references, receipt, ks):
    known = defaultdict(set)
    for ref in references:
        if ref["reference_class"] == "DETERMINISTIC_VERIFIED":
            known[ref["source_sha"]].add(ref["locator"]["page"])
    ranking = {row["source_sha256"]: row["candidate_pages"]["resource"]
               for row in receipt.get("retrieval_sources", ()) if "resource" in row.get("candidate_pages", {})}
    details = []
    for sha, pages in sorted(known.items()):
        ranked = list(dict.fromkeys(ranking.get(sha, ())))
        details.append({"source_sha": sha, "known_locator_pages": sorted(pages), "ranking_available": sha in ranking,
                        "matches": {str(k): len(set(ranked[:k]) & pages) for k in ks}})
    eligible = [row for row in details if row["ranking_available"]]
    return {"cutoffs": {str(k): {
                "silver_hit_at_k": rate(sum(row["matches"][str(k)] > 0 for row in eligible), len(eligible)),
                "silver_recall_at_k": rate(sum(row["matches"][str(k)] for row in eligible),
                                          sum(len(row["known_locator_pages"]) for row in eligible)),
            } for k in ks}, "queries": details,
            "interpretation": "Recall applies only to pre-existing source-page targets, not all relevant pages."}


def _predictions(receipt):
    records = {}
    for disposition in receipt.get("dispositions", ()):
        for row in disposition.get("observations", ()):
            if row["raw_id"] not in records:
                records[row["raw_id"]] = (row, disposition)
    return records


def _pair(references, predictions):
    def cell(raw):
        anchor = raw["evidence"]
        parts = [anchor[name] for name in ("table", "row", "column")]
        return tuple(parts) if all(type(value) is int for value in parts) else None

    pairs = []
    for ref in references:
        if ref["reference_class"] != "DETERMINISTIC_VERIFIED":
            continue
        joined = []
        expected = ref["locator"]["cell"]
        for item, state in predictions.values():
            raw = item["raw"]
            anchor = raw["evidence"]
            if ((ref["project_id"], ref["source_sha"], ref["locator"]["page"], ref["quantity"])
                    != (raw["project_id"], anchor["sha256"], anchor["page"], raw["variable"])):
                continue
            identity = item.get("canonical_observation_id") == ref["reference_id"]
            coordinates = cell(raw) == tuple(expected[name] for name in ("table", "row", "column")) if expected else False
            if identity or coordinates:
                joined.append((item, state, "CANONICAL_ID" if identity else "ARCHIVED_CELL"))
        if len(joined) == 1:
            pairs.append((ref, *joined[0]))
    return pairs


def _parser_consensus(root, assets, originals, predictions):
    """An original same-file parser check. These rows never enter accuracy scores."""
    indexed = _locations(root)
    by_source = defaultdict(list)
    for item, _ in predictions.values():
        raw = item["raw"]
        if item["numeric_and_unit_located"] and raw["evidence"].get("page") and raw.get("original_value"):
            by_source[raw["evidence"]["sha256"]].append((item, raw))
    refs = []
    evaluated = 0
    for sha, rows in sorted(by_source.items()):
        if not originals.get(sha, {}).get("sha_verified"):
            continue
        path = _find_original(root, indexed, assets, sha)
        if path is None:
            continue
        try:
            pypdf = PdfReader(path)
            native = pymupdf.open(path)
        except (OSError, ValueError, DependencyError, PdfReadError, pymupdf.FileDataError):
            continue
        with native:
            texts = {}
            for item, raw in rows:
                a = raw["evidence"]
                page = a["page"]
                if page > min(len(native), len(pypdf.pages)):
                    continue
                if page not in texts:
                    try:
                        texts[page] = (_flat(pypdf.pages[page - 1].extract_text()),
                                       _flat(native[page - 1].get_text()))
                    except (OSError, ValueError, DependencyError, PdfReadError):
                        texts[page] = ("", "")
                if not all(texts[page]):
                    continue
                evaluated += 1
                quote = _flat(a.get("quote"))
                if not all(_unique_quote_witness(text, quote, raw["original_value"], raw["original_unit"])
                           for text in texts[page]):
                    continue
                refs.append({
                    "reference_id": digest(["parser-consensus", item["raw_id"]]),
                    "project_id": raw["project_id"], "source_sha": sha, "locator": a,
                    "raw_value": raw["original_value"], "unit": raw["original_unit"],
                    "quantity_kind": raw["quantity_kind"], "quantity": raw["variable"],
                    "species": raw["chemical_basis"], "material_basis": raw["material_basis"],
                    "estimate_scope": raw["scope_id"],
                    "cutoff": dict(raw["context"]["conditions"]).get("cutoff_grade"),
                    "evidence_chain": {"candidate_raw_id": item["raw_id"], "same_original": True,
                                       "pypdf_page_sha256": digest(texts[page][0]),
                                       "mupdf_page_sha256": digest(texts[page][1])},
                    "reference_method": "TWO_TEXT_VIEWS_AGREE_ON_UNIQUE_PRINTED_QUOTE",
                    "reference_class": "PARSER_CONSENSUS", "confidence_status": "SAME_FILE_DIAGNOSTIC",
                    "independent_truth": False,
                })
    return refs, rate(len(refs), evaluated)


def _internals(root, predictions, receipt):
    engine = SemanticEngine(root)
    verified_claims = verified_bindings = normalized = valid_normalized = 0
    schema_failures = Counter()
    for item, _ in predictions.values():
        if item["evidence_status"] != "VERIFIED":
            continue
        verified_claims += 1
        try:
            raw = raw_from_payload(item["raw"])
        except (TypeError, ValueError, KeyError) as exc:
            schema_failures[type(exc).__name__] += 1
            continue
        if value_evidence_issue(raw, raw.evidence_anchors or (raw.evidence,)) is not None:
            continue
        verified_bindings += 1
        result = engine.normalize(raw)
        if result is None:
            continue
        normalized += 1
        validate_normalized_binding(raw, result)
        value = scalar_decimal(raw.original_value, raw.original_unit)
        source_unit = engine.map_observation(raw)["context"]["unit"]
        expected = value
        if source_unit != result.unit:
            factors = next((units for units in (MASS_FRACTION, MASS_IN_TONNES)
                            if source_unit in units and result.unit in units), None)
            expected = value * unit_factor(source_unit, result.unit, factors) if factors and value is not None else None
        if expected is not None and result.value == expected and result.formula:
            valid_normalized += 1
    dispositions = receipt.get("dispositions", ())
    compatible = 0
    known = set(receipt.get("canonical_observation_ids", ()))
    for row in dispositions:
        observation_ids = set(row["canonical_observation_ids"])
        detail_ids = {item["canonical_observation_id"] for item in row.get("observations", ())
                      if item.get("canonical_observation_id")}
        if row["status"] in RESOURCE_GATES:
            compatible += bool(observation_ids and observation_ids == detail_ids and observation_ids <= known
                               and all(item["evidence_status"] == "VERIFIED" for item in row["observations"]))
        elif row["status"] == "CANONICAL_ELIGIBLE" and receipt.get("schema") == "phase10-shadow-v1":
            compatible += not observation_ids and not detail_ids and not row["reasons"] and bool(row["observations"]) and all(
                item["evidence_status"] == "VERIFIED" for item in row["observations"])
        else:
            compatible += not observation_ids and not detail_ids and bool(row["reasons"])
    return {
        "semantic_binding_consistency": rate(verified_bindings, verified_claims),
        "verified_records_with_normalized_scalar": rate(normalized, verified_bindings),
        "normalization_validity": rate(valid_normalized, normalized),
        "admission_consistency": rate(compatible, len(dispositions)),
        "deserialization_failure_types": dict(schema_failures),
        "interpretation": "Stored bindings, Decimal unit arithmetic on version-bound scalars and admission receipt lineage. Engineering consistency, separately from external truth.",
    }


def _synthetic(root):
    cases = (
        ("ZERO", "Measured 0% recovered", "0%", "%", "0%", True, True),
        ("SCIENTIFIC", "Measured 2.5e-3 ppm in ore", "2.5e-3", "ppm", "2.5e-3", True, True),
        ("BOUND", "Measured ≤0.1 ppm", "≤0.1", "ppm", "≤0.1", True, False),
        ("RANGE", "Measured 2–3%", "2–3%", "%", "2–3%", True, False),
        ("CHEMICAL_SUBSCRIPT", "Nd2O3 is an oxide", "2", "ppm", "2", False, False),
        ("EXPONENT", "Printed 1e1000 ppm", "1000", "ppm", "1000", False, False),
        ("WRONG_OCCURRENCE", "Measured 90% and 70%", "70%", "%", "90%", False, False),
        ("WRONG_UNIT", "Measured 12 ppm", "12", "%", "12", False, False),
    )
    engine = SemanticEngine(root)
    references = []
    for key, text, value, unit, marked, expected, normalized in cases:
        i = text.index(marked)
        source = sha256(text.encode("utf-8")).hexdigest()
        anchor = EvidenceAnchor(key, source, page=1, quote=text, text_span=TextSpan("QUOTE", "SYNTHETIC", i, i + len(marked)))
        raw = RawObservation(key, "SYNTHETIC", "observed_value", "TECHNICAL", anchor, VERSION, value, unit)
        issue = value_evidence_issue(raw, (anchor,))
        result = engine.normalize(raw) if issue is None else None
        references.append({
            "reference_id": key, "project_id": raw.project_id, "source_sha": source,
            "locator": {"page": 1, "quote": text, "span": [i, i + len(marked)]},
            "raw_value": value, "unit": unit, "quantity_kind": raw.quantity_kind, "quantity": raw.variable,
            "species": None, "material_basis": None, "estimate_scope": None, "cutoff": None,
            "evidence_chain": {"explicit_fixture_target": marked, "known_numeric_binding": expected,
                               "known_normalizable": normalized},
            "reference_method": "DECLARED_SYNTHETIC_LITERAL_AND_OFFSET",
            "reference_class": "SYNTHETIC_GROUND_TRUTH", "confidence_status": "KNOWN_SYNTHETIC_ANSWER",
            "independent_truth": True, "predicted_verified": issue is None, "predicted_normalizable": result is not None,
        })
    tp = sum(x["evidence_chain"]["known_numeric_binding"] and x["predicted_verified"] for x in references)
    fp = sum(not x["evidence_chain"]["known_numeric_binding"] and x["predicted_verified"] for x in references)
    fn = sum(x["evidence_chain"]["known_numeric_binding"] and not x["predicted_verified"] for x in references)
    return references, {"true_positive": tp, "false_positive": fp, "false_negative": fn,
                        "precision": rate(tp, tp + fp), "recall": rate(tp, tp + fn), "f1": rate(2 * tp, 2 * tp + fp + fn),
                        "normalization_expectation_agreement": rate(sum(
                            x["evidence_chain"]["known_normalizable"] == x["predicted_normalizable"] for x in references),
                            len(references))}


def run(root, output, holdout_manifest, *, admission, assets=None, ks=(1, 5, 10, 24)):
    """Return and persist layered references, keeping production science untouched."""
    root, output = Path(root).resolve(), Path(output)
    frame, receipt = _read(holdout_manifest), _read(admission)
    assets = Path(assets) if assets else None
    if (not isinstance(holdout_manifest, dict) and receipt.get("manifest_sha256")
            and filehash(holdout_manifest) != receipt["manifest_sha256"]):
        raise ValueError("Admission receipt is bound to a different holdout manifest")
    target = {row["source_sha256"] for row in frame["sources"]}
    if {row["source_sha256"] for row in receipt.get("source_dispositions", ())} - target:
        raise ValueError("Admission receipt contains sources outside the selected frame")
    silver, originals, inputs = _references(root, frame, assets, receipt.get("cutoff"))
    predictions = _predictions(receipt)
    pairs = _pair(silver, predictions)
    consensus, agreement = _parser_consensus(root, assets, originals, predictions)
    numeric = units = 0
    pair_audit = []
    for ref, item, _, identity in pairs:
        raw = item["raw"]
        raw_value = scalar_decimal(raw["original_value"], raw["original_unit"])
        ref_value = scalar_decimal(ref["raw_value"], ref["unit"])
        a = raw_value is not None and raw_value == ref_value
        b = raw["original_unit"] == ref["unit"]
        numeric += a
        units += b
        pair_audit.append({"reference_id": ref["reference_id"], "raw_id": item["raw_id"], "identity": identity,
                           "numeric_match": a, "unit_match": b})
    synthesis, synthetic = _synthetic(root)
    refs = [*silver, *consensus, *synthesis]
    scope_reason = "NO_EXHAUSTIVE_INDEPENDENT_REAL_SOURCE_TRUTH"
    classes = dict(Counter(ref["reference_class"] for ref in refs))
    technical = receipt.get("technical_dispositions", ())
    issues = Counter(issue for row in technical for issue in row["numeric_issues"])
    summary = {
        "schema": VERSION, "cutoff": receipt.get("cutoff"), "frame_sha256": digest(frame),
        "admission_scientific_sha256": receipt.get("scientific_sha256"), "reference_sha256": digest(refs),
        "reference_input_sha256": inputs,
        "pdf_parser_versions": {"pypdf": version("pypdf"), "pymupdf": version("PyMuPDF")},
        "classes": {name: classes.get(name, 0) for name in CLASSES}, "originals": originals,
        "frame_counts": {"document_editions": len(target), "sha_verified_editions": sum(
            item["sha_verified"] for item in originals.values()), "historical_reference_observations": len(silver),
            "distinct_predictions": len(predictions), "identity_matched_measurement_pairs": len(pairs)},
        "retrieval": _retrieval(silver, receipt, ks),
        "silver_numeric_extraction_agreement": rate(numeric, len(pairs)),
        "silver_unit_extraction_agreement": rate(units, len(pairs)),
        "silver_precision": rate(0, 0, unmeasured="NO_EXHAUSTIVE_POSITIVE_AND_NEGATIVE_SILVER_FRAME"),
        "silver_recall": rate(0, 0, unmeasured="NO_EXHAUSTIVE_LOCALIZED_SILVER_NUMERIC_FRAME"),
        "silver_f1": rate(0, 0, unmeasured="SILVER_PRECISION_UNMEASURED"),
        "silver_pair_audit": pair_audit,
        "same_file_parser_agreement": agreement,
        "engineering_consistency": _internals(root, predictions, receipt),
        "independent_evidence_yield": rate(0, 0, unmeasured="NO_PROVEN_DISTINCT_EVIDENCE_CHAINS"),
        "technical_diagnostics": {"candidate_rows": len(technical), "numeric_issue_types": dict(sorted(issues.items())),
                                  "formal_observations_written": 0, "accuracy_status": "UNMEASURED"},
        "real_independent_accuracy": {name: rate(0, 0, unmeasured=scope_reason) for name in ("precision", "recall", "f1")},
        "synthetic_known_answer": synthetic,
    }
    output.mkdir(parents=True, exist_ok=True)
    (output / "silver_references.jsonl").write_text("".join(canonical(ref) + "\n" for ref in refs), encoding="utf-8")
    (output / "quality_measurement.json").write_text(json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                                                    encoding="utf-8")
    return summary
