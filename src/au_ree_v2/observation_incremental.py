"""Dependencies and reviewed inputs for typed shadow observations."""

from collections import defaultdict
import json
from pathlib import Path
import unicodedata

from . import normalization as units, observation_pipeline, ontology
from .derived_cache import code_fingerprint
from .observation_schema import (
    SCHEMA_VERSION, EvidenceAnchor, ManualDecision, ObservationContext, RawObservation, payload,
)
from .observation_semantics import (
    ASSESSMENT_VERSION, NORMALIZATION_VERSION, OBSERVATION_STATUS, PROFILE_DIMENSIONS,
    RESOURCE_UNITS, SemanticEngine,
)
from .store import digest


REVIEW_SCHEMA = "shadow-observation-review-v1"
BINDING_FIELDS = frozenset({"project_id", "deposit_id", "scope_id", "effective_date", "publication_date",
                            "source_sha256"})
NORMALIZATION_DIMENSIONS = ("unit", "chemical_basis", "material_basis", "denominator_basis", "scope")


def load_reviews(path, candidates):
    """Read a versioned, append-only decision list kept outside the disposable cache."""
    if path is None:
        return {}
    journal = json.loads(Path(path).read_bytes())
    if journal.get("schema") != REVIEW_SCHEMA or not isinstance(journal.get("decisions"), list):
        raise ValueError("Unsupported shadow review journal")
    reviews = defaultdict(list)
    seen = set()
    for record in journal["decisions"]:
        if not isinstance(record, dict):
            raise ValueError("Shadow review decisions must be objects")
        candidate_id = record.get("candidate_id")
        if candidate_id not in candidates or record.get("decision_id") in seen:
            raise ValueError("Shadow review requires a known candidate and unique decision ID")
        expected = record.get("expected_binding", {})
        if (not isinstance(expected, dict) or expected.keys() - BINDING_FIELDS
                or any(value is not None and (not isinstance(value, str) or not value.strip())
                       for value in expected.values())):
            raise ValueError("Invalid reviewed source or entity binding")
        decision = ManualDecision(**{key: record.get(key) for key in
                                    ("decision_id", "reviewer", "disposition", "reason", "decided_at")})
        if decision.disposition not in {"ACCEPT", "REJECT", "REVIEW"}:
            raise ValueError("Unsupported shadow review disposition")
        seen.add(decision.decision_id)
        reviews[candidate_id].append({**payload(decision), "expected_binding": expected})
    return dict(reviews)


def review_verdict(raw, verdict, journal):
    if not journal:
        return verdict
    latest = journal[-1]
    expected = latest["expected_binding"]
    actual = {name: getattr(raw, name) for name in expected if name != "source_sha256"}
    actual["source_sha256"] = raw.evidence.sha256
    mismatch = sorted(name for name, value in expected.items() if actual.get(name) != value)
    status = verdict["status"]
    if status not in {"SOURCE_BLOCKED", "BLOCKED", "CONFLICT", "NOT_APPLICABLE"}:
        if mismatch or latest["disposition"] == "REVIEW":
            status = "REVIEW"
        elif latest["disposition"] == "REJECT":
            status = "INCOMPATIBLE"
    reason = verdict["reason"] + "|SHADOW_REVIEW:" + latest["decision_id"] + ":" + latest["disposition"]
    if mismatch:
        reason += "|REVIEWED_BINDING_MISMATCH:" + ",".join(mismatch)
    return {**verdict, "status": status, "reason": reason,
            "missing": sorted(set(verdict.get("missing", ())) | set(mismatch))}


class IncrementalObservations:
    """Address projections, scalar conversions and use decisions independently."""

    def __init__(self, root, cache):
        self.cache = cache
        self.engine = SemanticEngine(root)
        self.mappings = {(row["dimension"], ontology._label(row["label"])): row
                         for row in self.engine.vocabulary["mappings"]}
        self.ontology_code = code_fingerprint(ontology.normalize_context, ontology._label)
        self.projection_code = code_fingerprint(
            RawObservation, EvidenceAnchor, ObservationContext, ManualDecision, payload,
            files=(observation_pipeline.__file__,),
        )
        self.normalization_code = code_fingerprint(
            SemanticEngine.normalize, SemanticEngine._value_in_domain, SemanticEngine.raw_context,
            SemanticEngine.map_observation, units.decimal_token, units.unit_factor,
        )
        from . import observation_schema

        self.assessment_code = code_fingerprint(
            SemanticEngine.assess, SemanticEngine.raw_context, review_verdict,
            files=(observation_schema.__file__,),
        )

    def _vocabulary(self, context):
        # Include only the applicable mappings. An edit to another concept leaves
        # unaffected items reusable, even if in the same ontology document.
        return {
            "version": self.engine.vocabulary["version"],
            "code": self.ontology_code, "unicode": unicodedata.unidata_version,
            "mappings": {dimension: self.mappings.get((dimension, ontology._label(value)))
                         for dimension, value in context.items() if isinstance(value, str)},
        }

    def project(self, subject, capture, metadata):
        from .observation_schema import raw_from_payload

        def build():
            return payload(observation_pipeline.raw_from_candidate(
                capture, metadata=metadata, extractor_version=(
                    capture.get("extraction_version") or "frozen-resource-source-view-v1"),
            ))

        data = self.cache.compute("projection", subject, {
            "code": self.projection_code, "schema": SCHEMA_VERSION, "entity_and_source_metadata": metadata,
        }, build, upstream={"capture": digest(capture)}, validate=raw_from_payload)
        return raw_from_payload(data), data

    def normalize(self, subject, raw):
        from .observation_schema import normalized_from_payload

        def build():
            normalized = self.engine.normalize(raw)
            return payload(normalized) if normalized is not None else None

        def load(data):
            if data is None:
                return None
            return normalized_from_payload(data, raw=raw)

        context = self.engine.raw_context(raw)
        used = {key: context.get(key) for key in NORMALIZATION_DIMENSIONS}
        original = ontology.normalize_context({"unit": used["unit"]}, self.engine.vocabulary)["context"]["unit"]
        target = RESOURCE_UNITS.get(raw.variable, original)
        vocabulary = self._vocabulary(used)
        vocabulary["target_mapping"] = self._vocabulary({"unit": target})["mappings"]
        mapped_target = target if target in {"t TREO", "kt TREO"} else ontology.normalize_context(
            {"unit": target}, self.engine.vocabulary)["context"]["unit"]
        factors = {
            name: {unit: factors[unit] for unit in {original, mapped_target} if unit in factors}
            for name, factors in (("mass", units.MASS_IN_TONNES), ("fraction", units.MASS_FRACTION))
        }
        data = self.cache.compute("normalization", subject, {
            "code": self.normalization_code, "version": NORMALIZATION_VERSION, "vocabulary": vocabulary,
            "quantity_target": target, "unit_rules": factors, "token_pattern": [units.NUMBER.pattern, units.NUMBER.flags],
        }, build, upstream={"raw_normalization_context": raw.normalization_fingerprint}, validate=load)
        return load(data), data

    def assess(self, subject, raw, raw_data, normalized, normalized_data, verdict, capture_status, journal):
        from .observation_schema import assessment_from_payload

        def load(data):
            return assessment_from_payload(data, raw=raw, normalized=normalized)

        current = review_verdict(raw, verdict, journal)

        def build():
            verified = (capture_status in {"EXTRACTED", "SOURCE_VERIFIED_CANDIDATE"}
                        and current["status"] == "ACCEPT")
            return payload(self.engine.assess(
                raw, current, normalized=normalized, evidence_status="VERIFIED" if verified else None,
                apply_profile=True, supporting_evidence=raw.evidence_anchors or (raw.evidence,),
            ))

        purpose = verdict["profile_id"]
        profile = self.engine.profiles["profiles"][purpose]
        context = self.engine.raw_context(raw)
        if normalized is not None:
            context["unit"] = normalized.unit
            context["chemical_basis"] = normalized.chemical_basis or context["chemical_basis"]
        dimensions = {PROFILE_DIMENSIONS.get(key, key) for key in profile["required_context"]}
        data = self.cache.compute("assessment", subject, {
            "code": self.assessment_code, "version": ASSESSMENT_VERSION,
            "research_use": profile, "profile_version": self.engine.profiles["version"],
            "vocabulary": self._vocabulary({key: context.get(key) for key in dimensions}),
            "profile_dimension_aliases": PROFILE_DIMENSIONS, "disposition_mapping": OBSERVATION_STATUS[current["status"]],
            "legacy_verdict": verdict, "source_qualification": capture_status, "manual_decisions": journal,
        }, build, upstream={"raw_observation": digest(raw_data), "normalization": digest(normalized_data)},
            validate=load)
        return load(data), data
