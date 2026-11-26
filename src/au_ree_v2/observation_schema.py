"""Versioned records crossing extraction, validation, storage and research boundaries."""

from dataclasses import InitVar, dataclass, fields
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from math import isfinite
import re

from .store import digest

SCHEMA_VERSION = "observation-v2"
RAW_ID_VERSION = "observation-v1"
QUANTITY_KINDS = frozenset({"RESOURCE", "STRATEGIC_COMPOSITION", "TECHNICAL", "EVENT", "OTHER"})
EVIDENCE_STATES = frozenset({"VERIFIED", "UNVERIFIED", "SOURCE_BLOCKED", "CONFLICT", "NOT_APPLICABLE"})
COMPARABILITY_STATES = frozenset({"COMPARABLE", "DESCRIPTIVE_ONLY", "INSUFFICIENT_CONTEXT",
                                 "NOT_COMPARABLE", "NOT_APPLICABLE"})
VALUE_EVIDENCE_ROLES = frozenset({"token", "FROZEN_TABLE_CELL", "VERIFIED_TABLE_CELL", "NUMERIC_VALUE"})


def _require_text(value, name):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} requires nonempty text")


def _optional_text(value, name):
    if value is not None:
        _require_text(value, name)


def _tuple_of(value, kind, name):
    if not isinstance(value, tuple) or any(not isinstance(item, kind) for item in value):
        raise ValueError(f"{name} requires a tuple of {kind.__name__}")


def _finite_decimal(value):
    if not isinstance(value, Decimal) or not value.is_finite():
        raise ValueError("Normalized and analysis values require finite Decimal values")


def payload(record):
    """Serialize Decimal without silently reducing the precision of reported evidence."""
    def encode(value):
        if isinstance(value, Decimal):
            return str(value)
        if isinstance(value, tuple):
            return [encode(item) for item in value]
        if hasattr(value, "__dataclass_fields__"):
            return {field.name: encode(getattr(value, field.name)) for field in fields(value)}
        return value

    return {"schema_version": SCHEMA_VERSION, **encode(record)}


@dataclass(frozen=True, slots=True)
class EvidenceAnchor:
    source_id: str | None
    sha256: str | None
    page: int | None = None
    table: int | str | None = None
    row: int | str | None = None
    column: int | str | None = None
    quote: str | None = None
    bbox: tuple[float, float, float, float] | None = None
    locator: str | None = None
    role: str | None = None
    offset: int | None = None

    def __post_init__(self):
        for name in ("source_id", "quote", "locator", "role"):
            _optional_text(getattr(self, name), name)
        if self.sha256 is not None:
            _require_text(self.sha256, "sha256")
            if len(self.sha256) != 64 or any(c not in "0123456789abcdef" for c in self.sha256):
                raise ValueError("sha256 requires a lowercase SHA-256 hex digest")
        if self.page is not None and (type(self.page) is not int or self.page < 1):
            raise ValueError("Physical page numbers start at one")
        if self.offset is not None and (type(self.offset) is not int or self.offset < 0):
            raise ValueError("Evidence offset must be a nonnegative integer")
        for name in ("table", "row", "column"):
            value = getattr(self, name)
            if type(value) is int and value >= 0:
                continue
            _optional_text(value, name)
        if self.bbox is not None:
            if (not isinstance(self.bbox, tuple) or len(self.bbox) != 4
                    or any(type(x) not in (int, float) or not isfinite(x) for x in self.bbox)
                    or self.bbox[0] > self.bbox[2] or self.bbox[1] > self.bbox[3]):
                raise ValueError("bbox requires four finite ordered coordinates")


@dataclass(frozen=True, slots=True)
class ObservationContext:
    sample: str | None = None
    process: str | None = None
    endpoint: str | None = None
    scale: str | None = None
    conditions: tuple[tuple[str, str], ...] = ()

    def __post_init__(self):
        for name in ("sample", "process", "endpoint", "scale"):
            _optional_text(getattr(self, name), name)
        _tuple_of(self.conditions, tuple, "conditions")
        if any(len(item) != 2 or any(not isinstance(part, str) or not part.strip() for part in item)
               for item in self.conditions):
            raise ValueError("Each condition needs a nonempty key and reported value")
        if len(dict(self.conditions)) != len(self.conditions):
            raise ValueError("Condition keys must be unique")


@dataclass(frozen=True, slots=True)
class ManualDecision:
    decision_id: str
    reviewer: str
    disposition: str
    reason: str
    decided_at: str

    def __post_init__(self):
        for field in fields(self):
            _require_text(getattr(self, field.name), field.name)
        datetime.fromisoformat(self.decided_at)


@dataclass(frozen=True, slots=True)
class RawObservation:
    observation_id: str
    project_id: str | None
    variable: str
    quantity_kind: str
    evidence: EvidenceAnchor
    extractor_version: str
    original_value: str | None = None
    original_unit: str | None = None
    deposit_id: str | None = None
    scope_id: str | None = None
    material_basis: str | None = None
    chemical_basis: str | None = None
    denominator_basis: str | None = None
    context: ObservationContext = ObservationContext()
    effective_date: str | None = None
    publication_date: str | None = None
    acquisition_date: str | None = None
    statement_id: str | None = None
    estimate_id: str | None = None
    related_observation_ids: tuple[str, ...] = ()
    manual_decisions: tuple[ManualDecision, ...] = ()
    source_value_state: str | None = None
    extraction_fingerprint: str | None = None
    evidence_anchors: tuple[EvidenceAnchor, ...] = ()

    def __post_init__(self):
        for name in ("observation_id", "variable", "extractor_version"):
            _require_text(getattr(self, name), name)
        if not isinstance(self.quantity_kind, str) or self.quantity_kind not in QUANTITY_KINDS:
            raise ValueError(f"Unsupported quantity kind {self.quantity_kind!r}")
        for name in ("project_id", "original_value", "original_unit", "deposit_id", "scope_id",
                     "material_basis", "chemical_basis", "denominator_basis", "statement_id",
                     "estimate_id", "source_value_state", "extraction_fingerprint"):
            _optional_text(getattr(self, name), name)
        for name in ("effective_date", "publication_date", "acquisition_date"):
            value = getattr(self, name)
            if value is not None:
                _require_text(value, name)
                if len(value) in (4, 7):
                    date.fromisoformat(value + ("-01-01" if len(value) == 4 else "-01"))
                else:
                    datetime.fromisoformat(value)
        if not isinstance(self.evidence, EvidenceAnchor) or not isinstance(self.context, ObservationContext):
            raise ValueError("Typed evidence and observation context required")
        _tuple_of(self.related_observation_ids, str, "related_observation_ids")
        _tuple_of(self.manual_decisions, ManualDecision, "manual_decisions")
        _tuple_of(self.evidence_anchors, EvidenceAnchor, "evidence_anchors")

    @property
    def raw_id(self):
        # Evidence edition and extraction specification qualify the existing observation ID.
        # Review, normalization and research use never form part of a raw identity.
        anchor = self.evidence
        return digest([RAW_ID_VERSION, self.observation_id, anchor.sha256 or anchor.source_id,
                       anchor.page, anchor.table, anchor.row, anchor.column, anchor.bbox, anchor.offset,
                       self.variable, self.extractor_version, self.extraction_fingerprint])

    @property
    def normalization_fingerprint(self):
        """Identify the original value and scientific conditions read by the normalizer."""
        return digest([self.raw_id, self.original_value, self.original_unit, self.source_value_state,
                       self.quantity_kind, self.scope_id or dict(self.context.conditions).get("reported_scope"),
                       self.chemical_basis, self.material_basis,
                       self.denominator_basis])


def _flat(text):
    return " ".join(text.split())


def _contains_value(quote, value):
    if not quote or not value:
        return False
    token = re.escape(_flat(value))
    return bool(re.search(r"(?<![0-9,.+−-])" + token + r"(?![0-9]|[,.][0-9]|[Ee][+-]?[0-9])", _flat(quote)))


def value_evidence_issue(raw, supporting_evidence):
    """Check all explicit value anchors and return a scientific binding disposition."""
    _tuple_of(supporting_evidence, EvidenceAnchor, "supporting_evidence")
    primary = raw.evidence
    # Untyped anchors were used as numeric evidence before roles were recorded.
    witnesses = tuple(anchor for anchor in supporting_evidence
                      if anchor.role is None or anchor.role in VALUE_EVIDENCE_ROLES)
    if (primary.role is not None and primary.role not in VALUE_EVIDENCE_ROLES
            or not raw.original_value or not any(char.isdigit() for char in raw.original_value)
            or not primary.sha256 or not witnesses):
        return "NUMERIC_EVIDENCE_LOCATION_INSUFFICIENT"
    if primary.quote is not None and not _contains_value(primary.quote, raw.original_value):
        return "NUMERIC_EVIDENCE_BINDING_MISMATCH"
    complete = True
    for anchor in witnesses:
        known = ("page", "table", "row", "column", "offset", "locator")
        mismatch = any(getattr(primary, key) is not None and getattr(anchor, key) is not None
                       and getattr(primary, key) != getattr(anchor, key) for key in known)
        boxes = primary.bbox is not None and anchor.bbox is not None
        matching_box = boxes and all(abs(a - b) < .01 for a, b in zip(primary.bbox, anchor.bbox))
        if ((anchor.sha256 is not None and anchor.sha256 != primary.sha256) or mismatch or (boxes and not matching_box)
                or (anchor.quote is not None and not _contains_value(anchor.quote, raw.original_value))):
            return "NUMERIC_EVIDENCE_BINDING_MISMATCH"
        same_page = primary.page is not None and anchor.page == primary.page
        cell = all(getattr(primary, key) is not None and getattr(primary, key) == getattr(anchor, key)
                   for key in ("table", "row", "column"))
        # Non-paged sources can identify a table cell with a complete table/row/column key.
        cell &= same_page or primary.page is None and anchor.page is None
        if (not anchor.sha256 or not anchor.quote
                or (primary.offset is not None and anchor.offset is None)):
            complete = False
            continue
        # Extractors locate narrative text by its recorded span or source
        # block, so an offset is compared together with the same excerpt.
        same_text = (same_page and anchor.offset is not None and anchor.offset == primary.offset
                     and primary.quote is not None and _flat(anchor.quote) == _flat(primary.quote))
        # A box must enclose a real region. The raw location may come from the
        # same provider with small floating-point variations in coordinates.
        box = (same_page and matching_box and primary.bbox[0] < primary.bbox[2]
               and primary.bbox[1] < primary.bbox[3])
        complete &= cell or same_text or box
    return None if complete else "NUMERIC_EVIDENCE_LOCATION_INSUFFICIENT"


@dataclass(frozen=True, slots=True)
class NormalizedObservation:
    raw_id: str
    version: str
    value: Decimal
    unit: str
    formula: str
    conditions: tuple[str, ...] = ()
    chemical_basis: str | None = None
    raw_fingerprint: str | None = None

    def __post_init__(self):
        for name in ("raw_id", "version", "unit", "formula"):
            _require_text(getattr(self, name), name)
        _finite_decimal(self.value)
        _tuple_of(self.conditions, str, "conditions")
        _optional_text(self.chemical_basis, "chemical_basis")
        if self.raw_fingerprint is not None:
            if not isinstance(self.raw_fingerprint, str) or not re.fullmatch("[0-9a-f]{64}", self.raw_fingerprint):
                raise ValueError("Normalization fingerprint must be a SHA-256 digest")


def validate_normalized_binding(raw, normalized):
    if (not isinstance(normalized, NormalizedObservation) or normalized.raw_id != raw.raw_id
            or normalized.raw_fingerprint != raw.normalization_fingerprint):
        raise ValueError("Normalization must bind the original observation contents")


@dataclass(frozen=True, slots=True)
class SemanticAssessment:
    raw_id: str
    purpose: str
    rule_version: str
    ontology_version: str
    evidence_status: str
    comparability: str
    reason: str
    missing_context: tuple[str, ...] = ()
    supporting_evidence: tuple[EvidenceAnchor, ...] = ()
    normalized_version: str | None = None
    raw_fingerprint: str | None = None
    normalized_fingerprint: str | None = None
    raw: InitVar[RawObservation | None] = None
    normalized: InitVar[NormalizedObservation | None] = None

    def __post_init__(self, raw, normalized):
        for name in ("raw_id", "purpose", "rule_version", "ontology_version", "reason"):
            _require_text(getattr(self, name), name)
        if not isinstance(self.evidence_status, str) or self.evidence_status not in EVIDENCE_STATES:
            raise ValueError("Unknown evidence disposition")
        if not isinstance(self.comparability, str) or self.comparability not in COMPARABILITY_STATES:
            raise ValueError("Unknown comparability disposition")
        _tuple_of(self.supporting_evidence, EvidenceAnchor, "supporting_evidence")
        _tuple_of(self.missing_context, str, "missing_context")
        _optional_text(self.normalized_version, "normalized_version")
        if raw is not None and self.raw_fingerprint is None:
            object.__setattr__(self, "raw_fingerprint", digest(payload(raw)))
        if normalized is not None and self.normalized_fingerprint is None:
            object.__setattr__(self, "normalized_fingerprint", digest(payload(normalized)))
        if raw is not None or self.raw_fingerprint is not None or self.evidence_status == "VERIFIED":
            validate_assessment_binding(raw, self, normalized)
        elif normalized is not None or self.normalized_fingerprint is not None:
            raise ValueError("Assessment must bind the original observation before linking normalization")


def validate_assessment_binding(raw, assessment, normalized=None):
    """Enforce subject and exact normalization binding again when staging or reloading."""
    if not isinstance(raw, RawObservation) or assessment.raw_id != raw.raw_id:
        raise ValueError("Assessment must bind the original observation")
    if assessment.raw_fingerprint is not None and assessment.raw_fingerprint != digest(payload(raw)):
        raise ValueError("Assessment must bind the original observation contents")
    if assessment.evidence_status == "VERIFIED":
        if not assessment.raw_fingerprint:
            raise ValueError("Verified evidence must bind the original observation contents")
        if issue := value_evidence_issue(raw, assessment.supporting_evidence):
            raise ValueError(f"Verified support must bind the original value and location: {issue}")
    if normalized is not None:
        validate_normalized_binding(raw, normalized)
        if assessment.normalized_version != normalized.version:
            raise ValueError("Assessment must match the normalization version")
    if assessment.normalized_fingerprint is not None:
        if normalized is None or assessment.normalized_fingerprint != digest(payload(normalized)):
            raise ValueError("Assessment must match the normalization contents")
    if assessment.evidence_status == "VERIFIED" and assessment.normalized_version is not None:
        if normalized is None or assessment.normalized_fingerprint is None:
            raise ValueError("Verified assessment must bind the referenced normalization")


@dataclass(frozen=True, slots=True)
class ValidatedObservation:
    normalized: NormalizedObservation
    assessment: SemanticAssessment

    def __post_init__(self):
        if (not isinstance(self.normalized, NormalizedObservation)
                or not isinstance(self.assessment, SemanticAssessment)
                or self.normalized.raw_id != self.assessment.raw_id
                or self.normalized.version != self.assessment.normalized_version
                or digest(payload(self.normalized)) != self.assessment.normalized_fingerprint
                or self.assessment.evidence_status != "VERIFIED"):
            raise ValueError("Validation requires matching verified evidence for this normalization version")


@dataclass(frozen=True, slots=True)
class AnalysisFeature:
    observation: ValidatedObservation
    name: str
    definition_version: str
    value: Decimal
    unit: str

    def __post_init__(self):
        if (not isinstance(self.observation, ValidatedObservation)
                or self.observation.assessment.comparability != "COMPARABLE"):
            raise ValueError("Research features require purpose-specific comparability")
        for name in ("name", "definition_version", "unit"):
            _require_text(getattr(self, name), name)
        _finite_decimal(self.value)


def _record_fields(mapping):
    if not isinstance(mapping, dict) or mapping.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("Unsupported observation record schema")
    return {name: value for name, value in mapping.items() if name != "schema_version"}


def _anchor(mapping):
    return EvidenceAnchor(**{**mapping, "bbox": tuple(mapping["bbox"]) if mapping.get("bbox") is not None else None})


def raw_from_payload(mapping):
    data = _record_fields(mapping)
    raw_id = data.pop("raw_id", None)
    context = data.pop("context")
    raw = RawObservation(**{
        **data,
        "evidence": _anchor(data["evidence"]),
        "context": ObservationContext(**{**context, "conditions": tuple(tuple(pair) for pair in context["conditions"])}),
        "related_observation_ids": tuple(data["related_observation_ids"]),
        "manual_decisions": tuple(ManualDecision(**item) for item in data["manual_decisions"]),
        "evidence_anchors": tuple(_anchor(item) for item in data["evidence_anchors"]),
    })
    if raw_id is not None and raw_id != raw.raw_id:
        raise ValueError("Serialized raw observation ID does not match")
    return raw


def normalized_from_payload(mapping, *, raw=None):
    data = _record_fields(mapping)
    if not isinstance(data.get("value"), str):
        raise ValueError("Serialized normalization requires a textual Decimal")
    try:
        value = Decimal(data["value"])
    except InvalidOperation as exc:
        raise ValueError("Invalid serialized normalization value") from exc
    record = NormalizedObservation(**{**data, "value": value, "conditions": tuple(data["conditions"])})
    if raw is not None:
        validate_normalized_binding(raw, record)
    return record


def assessment_from_payload(mapping, *, raw, normalized=None):
    data = _record_fields(mapping)
    if (data.get("raw_fingerprint") is None or
            (data.get("normalized_version") is not None and data.get("normalized_fingerprint") is None)):
        raise ValueError("Serialized assessment lacks binding fingerprints")
    return SemanticAssessment(**{
        **data,
        "missing_context": tuple(data["missing_context"]),
        "supporting_evidence": tuple(_anchor(item) for item in data["supporting_evidence"]),
    }, raw=raw, normalized=normalized)
