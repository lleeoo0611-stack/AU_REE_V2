"""Versioned records crossing extraction, validation, storage and research boundaries."""

from dataclasses import dataclass, fields
from datetime import date, datetime
from decimal import Decimal
from math import isfinite

from .store import digest

SCHEMA_VERSION = "observation-v1"
QUANTITY_KINDS = frozenset({"RESOURCE", "STRATEGIC_COMPOSITION", "TECHNICAL", "EVENT", "OTHER"})
EVIDENCE_STATES = frozenset({"VERIFIED", "UNVERIFIED", "SOURCE_BLOCKED", "CONFLICT", "NOT_APPLICABLE"})
COMPARABILITY_STATES = frozenset({"COMPARABLE", "DESCRIPTIVE_ONLY", "INSUFFICIENT_CONTEXT",
                                 "NOT_COMPARABLE", "NOT_APPLICABLE"})


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
        return digest([SCHEMA_VERSION, self.observation_id, anchor.sha256 or anchor.source_id,
                       anchor.page, anchor.table, anchor.row, anchor.column, anchor.bbox, anchor.offset,
                       self.variable, self.extractor_version, self.extraction_fingerprint])


@dataclass(frozen=True, slots=True)
class NormalizedObservation:
    raw_id: str
    version: str
    value: Decimal
    unit: str
    formula: str
    conditions: tuple[str, ...] = ()
    chemical_basis: str | None = None

    def __post_init__(self):
        for name in ("raw_id", "version", "unit", "formula"):
            _require_text(getattr(self, name), name)
        _finite_decimal(self.value)
        _tuple_of(self.conditions, str, "conditions")
        _optional_text(self.chemical_basis, "chemical_basis")


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

    def __post_init__(self):
        for name in ("raw_id", "purpose", "rule_version", "ontology_version", "reason"):
            _require_text(getattr(self, name), name)
        if not isinstance(self.evidence_status, str) or self.evidence_status not in EVIDENCE_STATES:
            raise ValueError("Unknown evidence disposition")
        if not isinstance(self.comparability, str) or self.comparability not in COMPARABILITY_STATES:
            raise ValueError("Unknown comparability disposition")
        _tuple_of(self.supporting_evidence, EvidenceAnchor, "supporting_evidence")
        if self.evidence_status == "VERIFIED" and not any(
            anchor.sha256 and (anchor.page or anchor.locator)
            for anchor in self.supporting_evidence
        ):
            raise ValueError("Verified evidence requires a fingerprint and source locator")
        _tuple_of(self.missing_context, str, "missing_context")
        _optional_text(self.normalized_version, "normalized_version")


@dataclass(frozen=True, slots=True)
class ValidatedObservation:
    normalized: NormalizedObservation
    assessment: SemanticAssessment

    def __post_init__(self):
        if (not isinstance(self.normalized, NormalizedObservation)
                or not isinstance(self.assessment, SemanticAssessment)
                or self.normalized.raw_id != self.assessment.raw_id
                or self.normalized.version != self.assessment.normalized_version
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
