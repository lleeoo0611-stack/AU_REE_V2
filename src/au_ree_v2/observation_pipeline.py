"""Bind established extraction records to the common observation contract."""

from dataclasses import replace
import json

from .numeric_evidence import numeric_token_spans
from .observation_schema import EvidenceAnchor, ManualDecision, ObservationContext, RawObservation, TextSpan, VALUE_EVIDENCE_ROLES
from .store import canonical


def _text(value):
    if isinstance(value, str):
        return value if value.strip() else None
    return canonical(value) if value is not None else None


def _index(*values):
    return next((value for value in values if value is not None and value != ""
                 and not (type(value) is int and value < 0)), None)


def anchor_from_candidate(anchor, *, source_id=None):
    """Carry physical PDF locations and legacy locators without rewriting the source."""
    bbox = anchor.get("bbox")
    span = anchor.get("text_span")
    return EvidenceAnchor(
        source_id=source_id or _text(anchor.get("source_key")),
        sha256=_text(anchor.get("source_sha256") or anchor.get("source_sha")),
        page=_index(anchor.get("physical_page"), anchor.get("pdf_page"), anchor.get("page")),
        table=_index(anchor.get("table_index"), anchor.get("table")),
        row=_index(anchor.get("row_index"), anchor.get("row")),
        column=_index(anchor.get("column_index"), anchor.get("column")),
        quote=_text(anchor.get("quote")),
        bbox=tuple(bbox) if bbox else None,
        locator=_text(anchor.get("locator")),
        role=_text(anchor.get("role") or anchor.get("field")),
        offset=_index(anchor.get("offset"), anchor.get("token_occurrence_in_quote")),
        text_span=TextSpan(**span) if isinstance(span, dict) else span,
    )


def _legacy_resource_span(anchor, anchors, native):
    """Recover the historic resource block offset from its captured full text witness."""
    if anchor.text_span or anchor.role != "token" or anchor.offset is None or not anchor.quote or not anchor.bbox:
        return anchor
    blocks = {other.quote for other in anchors if other.role == "estimate_reference" and other.quote
              and other.page == anchor.page and other.sha256 == anchor.sha256 and other.bbox == anchor.bbox}
    if len(blocks) != 1:
        return anchor
    block = blocks.pop()
    quote_start = block.find(anchor.quote)
    if quote_start < 0 or block.find(anchor.quote, quote_start + 1) != -1:
        return anchor
    matches = [(start, end) for start, end in numeric_token_spans(block, native.get("token"), native.get("unit"))
               if start == anchor.offset and quote_start <= start and end <= quote_start + len(anchor.quote)]
    if len(matches) != 1:
        return anchor
    start, end = matches[0]
    return replace(anchor, text_span=TextSpan("BLOCK", "MUPDF_NATIVE_BLOCK_WHITESPACE_FOLDED",
                                             start, end, quote_start))


def _kind(candidate, variable):
    if candidate.get("profile_id") == "WITHIN_TABLE_ELEMENT_LEACH" or "technical_" in variable:
        return "TECHNICAL"
    if variable in {"magnet_reo_share_pct", "ndpr_share_pct"} or "composition" in variable:
        return "STRATEGIC_COMPOSITION"
    if candidate.get("profile_id") == "DIRECT_RESOURCE_UNIT_COMPARISON_V1":
        return "RESOURCE"
    return "OTHER"


def raw_from_candidate(candidate, *, source_id=None, extractor_version, metadata=None):
    """Use the native cell and its context, leaving unresolved input explicitly absent."""
    metadata = metadata or {}
    context = candidate.get("context") or {}
    provenance = candidate.get("provenance") or {}
    native = candidate.get("native") or {}
    source_id = source_id or candidate.get("source_key") or metadata.get("source_key")
    sha = candidate.get("source_sha256")
    page = candidate.get("physical_page")
    anchors = tuple(
        anchor_from_candidate(anchor, source_id=source_id if anchor.get("source_sha256") == sha else None)
        for anchor in candidate.get("anchors", ())
        if anchor.get("source_sha256") or anchor.get("source_sha")
    )
    # Legacy narrative offsets were block-relative. Translate only the historic
    # resource extractor's exactly co-located block and uniquely located excerpt.
    if candidate.get("profile_id") == "DIRECT_RESOURCE_UNIT_COMPARISON_V1":
        anchors = tuple(_legacy_resource_span(anchor, anchors, native) for anchor in anchors)
    located = next((anchor for anchor in anchors if anchor.sha256 == sha and anchor.page == page
                    and anchor.role in VALUE_EVIDENCE_ROLES), None)
    evidence = anchor_from_candidate({
        "source_sha256": sha, "physical_page": page,
        "table_index": _index(located.table if located else None, provenance.get("table_index")),
        "row_index": _index(located.row if located else None, provenance.get("row_index")),
        "column_index": _index(located.column if located else None, provenance.get("column_index")),
        "offset": located.offset if located else None,
        "text_span": located.text_span if located else None,
        "bbox": located.bbox if located and located.bbox else provenance.get("bbox"),
        "quote": located.quote if located and located.quote else candidate.get("source_excerpt") or
                 (metadata.get("source_excerpt") if not anchors else None),
        "locator": context.get("original_locator") or metadata.get("locator"),
    }, source_id=source_id)

    def field(*keys):
        return next((_text(record[key]) for record in (context, metadata)
                     for key in keys if key in record and _text(record[key]) is not None), None)

    variable = _text(native.get("variable") or native.get("quantity") or candidate.get("target_quantity")
                     or metadata.get("variable"))
    if variable is None:
        raise ValueError("A raw observation requires a declared variable even if the source value is absent")
    reserved = {"sample_id", "sample", "process", "process_stage", "endpoint", "scale", "scope", "scope_id",
                "table_scope_id", "deposit_id", "material_basis", "material", "chemical_basis", "basis",
                "denominator_basis", "denominator", "edition_effective_date", "effective_date", "study_date",
                "publication_date", "acquisition_date", "acquired_at", "statement_id", "estimate_id", "original_locator"}
    conditions = {key: text for key, value in context.items()
                  if key not in reserved and (text := _text(value)) is not None}
    for key, value in (("reported_bounds", native.get("bounds")), ("reported_scope", context.get("scope"))):
        if (text := _text(value)) is not None:
            conditions[key] = text
    return RawObservation(
        observation_id=candidate["observation_id"], project_id=_text(candidate.get("project_id")),
        variable=variable, quantity_kind=candidate.get("quantity_kind") or _kind(candidate, variable),
        evidence=evidence, extractor_version=extractor_version,
        original_value=_text(native.get("token")), original_unit=_text(native.get("unit")),
        deposit_id=field("deposit_id"), scope_id=field("scope_id", "table_scope_id", "scope"),
        material_basis=field("material_basis", "material"), chemical_basis=field("chemical_basis", "basis"),
        denominator_basis=field("denominator_basis", "denominator"),
        context=ObservationContext(field("sample_id", "sample"), field("process_stage", "process"),
                                   field("endpoint"), field("scale"), tuple(sorted(conditions.items()))),
        effective_date=field("edition_effective_date", "effective_date", "study_date"),
        publication_date=field("publication_date"), acquisition_date=field("acquisition_date", "acquired_at"),
        statement_id=field("statement_id"), estimate_id=field("estimate_id"),
        related_observation_ids=tuple(candidate.get("related_observation_ids") or ()),
        manual_decisions=tuple(ManualDecision(**decision) for decision in candidate.get("manual_decisions", ())),
        source_value_state=_text(native.get("token_state")),
        extraction_fingerprint=_text(candidate.get("extraction_fingerprint")), evidence_anchors=anchors,
    )


def canonical_resource_observation(db, observation_id):
    """Project the existing Evidence Model row, using only declared original tokens."""
    cursor = db.execute(
        """SELECT f.*, e.kind AS entity_kind FROM resource_statement_facts f
           LEFT JOIN entities e USING (entity_id) WHERE f.obs_id = ?""",
        (observation_id,),
    )
    record = cursor.fetchone()
    if record is None:
        raise KeyError(observation_id)
    row = dict(zip((column[0] for column in cursor.description), record))
    raw = json.loads(row["payload"])
    page = _index(raw.get("pdf_page"), raw.get("physical_page"))
    return raw_from_candidate({
        "observation_id": observation_id,
        "project_id": row["entity_id"] if row["entity_kind"] == "PROJECT" else None,
        "source_sha256": row["source_sha"],
        "physical_page": int(page) if type(page) in (int, str) and str(page).isdigit() and int(page) > 0 else None,
        "profile_id": "DIRECT_RESOURCE_UNIT_COMPARISON_V1",
        "native": {"quantity": row["variable"], "token": row["reported_token"], "unit": row["reported_unit"]},
        "context": {"category": row["category"], "statement_kind": row["statement_kind"],
                    "cutoff_grade": row["cutoff_grade"], "scope": row["scope"]},
    }, source_id=row["source_key"], extractor_version="canonical-resource-facts-v1",
        metadata={**row, "deposit_id": row["entity_id"] if row["entity_kind"] == "DEPOSIT" else None})
