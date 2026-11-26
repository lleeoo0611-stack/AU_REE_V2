"""Source-bound research use assessment shared by shadow runs and evaluation."""
import json
import re
from decimal import Context, Decimal, DecimalException, localcontext
from pathlib import Path

from . import resource_use
from .normalization import (
    MAGNET_ATOMIC_WEIGHTS, MAGNET_SPECIES, MASS_FRACTION, MASS_IN_TONNES, oxide_factor, unit_factor,
)
from .numeric_evidence import scalar_decimal
from .observation_schema import (
    NormalizedObservation, SemanticAssessment, validate_normalized_binding, value_evidence_issue,
)
from .ontology import compare_context, load_observation_vocabulary, normalize_context
from .store import digest
from .tabular import read_csv


RESOURCE_PROFILE = "DIRECT_RESOURCE_UNIT_COMPARISON_V1"
NORMALIZATION_VERSION = "observation-normalization-v2"
ASSESSMENT_VERSION = "observation-assessment-v3"
RESOURCE_UNITS = {variable: unit for variable, unit, _ in resource_use.FIELDS.values()}
OBSERVATION_STATUS = {
    "ACCEPT": "COMPARABLE", "COMPARABLE": "COMPARABLE", "DESCRIPTIVE_ONLY": "DESCRIPTIVE_ONLY",
    "INSUFFICIENT": "INSUFFICIENT_CONTEXT", "INSUFFICIENT_CONTEXT": "INSUFFICIENT_CONTEXT",
    "REVIEW": "INSUFFICIENT_CONTEXT", "BLOCKED": "INSUFFICIENT_CONTEXT", "SOURCE_BLOCKED": "INSUFFICIENT_CONTEXT",
    "INCOMPATIBLE": "NOT_COMPARABLE", "NOT_COMPARABLE": "NOT_COMPARABLE", "CONFLICT": "NOT_COMPARABLE",
    "NOT_APPLICABLE": "NOT_APPLICABLE",
}
MATERIAL_DENOMINATORS = {"WHOLE_ORE", "BULK_ORE", "CONCENTRATE", "PRODUCT"}
PROFILE_DIMENSIONS = {"basis": "chemical_basis", "sample_id": "sample"}


class SemanticEngine:
    """Map typed evidence and apply explicit research rules while retaining source provenance."""

    def __init__(self, root):
        self.vocabulary = load_observation_vocabulary(root)
        self.profiles = json.loads((Path(root) / "config/ontology/shadow_profiles_v1.json").read_bytes())

    def raw_context(self, raw):
        conditions = {key: value for key, value in raw.context.conditions if re.fullmatch(r"[a-z][a-z0-9_]*", key)}
        fields = {
            "project_id": raw.project_id, "deposit_id": raw.deposit_id, "scope": raw.scope_id or conditions.get("reported_scope"),
            "resource_kind": conditions.get("resource_kind") or conditions.get("statement_kind"),
            "quantity_kind": raw.quantity_kind, "variable": raw.variable, "unit": raw.original_unit,
            "material_basis": raw.material_basis, "chemical_basis": raw.chemical_basis,
            "denominator_basis": raw.denominator_basis, "sample": raw.context.sample,
            "process": raw.context.process, "endpoint": raw.context.endpoint, "scale": raw.context.scale,
            "effective_date": raw.effective_date, "statement_id": raw.statement_id, "estimate_id": raw.estimate_id,
        }
        # Named contract fields take precedence over free-form condition keys.
        combined = {**conditions, **fields}
        return {key: None if value in {"UNKNOWN", "UNRESOLVED", "UNSPECIFIED"} else value
                for key, value in combined.items()}

    def map_observation(self, raw):
        """Expose original-to-concept traces for the standard crosswalk and local context."""
        return normalize_context(self.raw_context(raw), self.vocabulary)

    def normalize(self, raw, *, target_unit=None, target_species=None):
        """Return a versioned scalar projection only when its conversion is witnessed."""
        if (raw.original_value is None or raw.original_unit is None
                or raw.source_value_state not in {None, "NUMBER", "SCALAR"}):
            return None
        mapped = self.map_observation(raw)["context"]
        original_unit = mapped["unit"]
        if original_unit is None:
            return None
        target_unit = target_unit or RESOURCE_UNITS.get(raw.variable, original_unit)
        if target_unit not in {"t TREO", "kt TREO"}:
            target_unit = normalize_context({"unit": target_unit}, self.vocabulary)["context"]["unit"]
        chemical, material, denominator = (mapped[key] for key in ("chemical_basis", "material_basis", "denominator_basis"))
        qualified_mass = {"t TREO", "kt TREO"}
        if ({raw.original_unit, target_unit} & qualified_mass) and chemical != "TREO":
            return None
        conditions = [f"{key}={mapped[key]}" for key in ("scope", "chemical_basis", "material_basis", "denominator_basis")
                      if mapped.get(key) is not None]
        if raw.original_unit != original_unit:
            conditions.append(f"unit alias: {raw.original_unit} → {original_unit}")

        species = chemical
        try:
            with localcontext(Context(prec=28)):
                value = scalar_decimal(raw.original_value, original_unit)
                if (value is None or not value.is_finite()
                        or not self._value_in_domain(value, original_unit, raw.variable)):
                    return None
                factors = []
                if original_unit != target_unit:
                    if (original_unit in MASS_IN_TONNES and target_unit in MASS_IN_TONNES
                            and (raw.quantity_kind != "RESOURCE" or mapped["scope"])
                            and (raw.variable != "contained_treo_kt" or chemical == "TREO")):
                        factors.append(("metric mass", unit_factor(original_unit, target_unit, MASS_IN_TONNES)))
                    elif (original_unit in MASS_FRACTION and target_unit in MASS_FRACTION
                          and chemical and material and denominator
                          and (raw.quantity_kind != "RESOURCE" or mapped["scope"])
                          and raw.quantity_kind in {"RESOURCE", "STRATEGIC_COMPOSITION"}):
                        factors.append(("same-denominator mass fraction", unit_factor(original_unit, target_unit, MASS_FRACTION)))
                    else:
                        return None
                if target_species is not None:
                    species = normalize_context({"chemical_basis": target_species}, self.vocabulary)["context"]["chemical_basis"]
                    if species is None or not chemical:
                        return None
                    if species != chemical:
                        same_ore_mass = {material, denominator} <= {"WHOLE_ORE", "BULK_ORE"}
                        if (raw.quantity_kind != "STRATEGIC_COMPOSITION" or not mapped["scope"]
                                or denominator not in MATERIAL_DENOMINATORS or original_unit not in MASS_FRACTION
                                or (denominator != material and not same_ore_mass)):
                            return None
                        element = next((key for key, labels in MAGNET_SPECIES.items() if {chemical, species} <= labels), None)
                        if element is None:
                            return None
                        weight = MAGNET_ATOMIC_WEIGHTS[element]
                        factor = oxide_factor(element, chemical, species, weight)
                        factors.append((f"stoichiometry {chemical} → {species} (atomic weight {weight})", factor))
                        conditions.append(f"target_species={species}")
                formula = "original_value"
                for rule, factor in factors:
                    value *= factor
                    formula += f" × {factor} [{rule}]"
                if not value.is_finite() or not self._value_in_domain(value, target_unit, raw.variable):
                    return None
        except (DecimalException, ValueError):
            return None
        version = NORMALIZATION_VERSION + ":" + digest([self.vocabulary["version"], target_unit, formula, conditions])
        return NormalizedObservation(raw.raw_id, version, value, target_unit, formula, tuple(conditions), species,
                                     raw_fingerprint=raw.normalization_fingerprint)

    @staticmethod
    def _value_in_domain(value, unit, variable):
        if unit == "%":
            return 0 <= value <= 100 and (variable != "grade" or value > 0)
        if unit == "ppm":
            return 0 <= value <= 1_000_000 and (variable != "grade" or value > 0)
        if unit in MASS_IN_TONNES:
            return value >= 0 and (variable not in {"ore_mt", "contained_treo_kt"} or value > 0)
        return True

    def assess(self, raw, decision, *, normalized=None, evidence_status=None, supporting_evidence=(), expected_context=None,
               apply_profile=False):
        """Preserve the source gate and assess a declared use as a separate decision."""
        if normalized is not None:
            validate_normalized_binding(raw, normalized)
        status = decision["status"]
        comparison = OBSERVATION_STATUS[status]
        missing = set(decision.get("missing", ()))
        reason = decision["reason"]
        purpose = decision["profile_id"]
        rule_version = ASSESSMENT_VERSION + ":" + decision["profile_version"]
        context = self.raw_context(raw)
        if normalized is not None:
            context["unit"] = normalized.unit
            context["chemical_basis"] = normalized.chemical_basis or context["chemical_basis"]
        required = set()
        if apply_profile:
            profile = self.profiles["profiles"][purpose]
            rule_version += ":" + self.profiles["version"] + ":" + digest(profile)
            if comparison != "NOT_APPLICABLE":
                dimensions = [PROFILE_DIMENSIONS.get(name, name) for name in profile["required_context"]]
                mapped = normalize_context({key: context.get(key) for key in dimensions}, self.vocabulary)["context"]
                required.update(key for key, value in mapped.items() if value is None)
        if expected_context is not None:
            _, target, expected_missing, incompatible = compare_context(context, expected_context, self.vocabulary)
            rule_version += ":" + digest(target["context"])
            required.update(expected_missing)
            if comparison in {"COMPARABLE", "INSUFFICIENT_CONTEXT"} and incompatible:
                comparison = "NOT_COMPARABLE"
                reason += "|CONTEXT_MISMATCH:" + ",".join(incompatible)
        if comparison == "COMPARABLE" and required:
            comparison = "INSUFFICIENT_CONTEXT"
            reason += "|REQUIRED_CONTEXT_MISSING"
        missing.update(required)
        if status in {"BLOCKED", "SOURCE_BLOCKED", "CONFLICT"}:
            evidence_status = "CONFLICT" if status == "CONFLICT" else "SOURCE_BLOCKED"
        elif evidence_status is None:
            evidence_status = "NOT_APPLICABLE" if status == "NOT_APPLICABLE" else "UNVERIFIED"
        supporting_evidence = tuple(supporting_evidence)
        if evidence_status == "VERIFIED":
            issue = value_evidence_issue(raw, supporting_evidence)
            if issue == "NUMERIC_EVIDENCE_BINDING_MISMATCH":
                evidence_status = "CONFLICT"
                comparison = "NOT_COMPARABLE"
                reason += "|" + issue
            elif issue is not None:
                evidence_status = "UNVERIFIED"
                reason += "|" + issue
                missing.add("numeric_evidence_location")
        return SemanticAssessment(raw.raw_id, purpose, rule_version,
                                  self.vocabulary["version"], evidence_status, comparison, reason,
                                  tuple(sorted(missing)), supporting_evidence,
                                  normalized.version if normalized is not None else None,
                                  raw=raw, normalized=normalized)


def assessment(status, reason, profile, version, *, normalized=None, missing=(), evidence=()):
    return {"status": status, "reason": reason, "profile_id": profile, "profile_version": version,
            "normalized": normalized, "missing": list(missing), "provenance": list(evidence),
            "formal_admission": "NOT_ASSESSED_BY_RESEARCH_PROFILE"}


class ResourceContract:
    """Use the same selected-cell and numerical admission as the portfolio reports."""

    def __init__(self, root, release, profile):
        self.profile = profile
        self.approved = resource_use.selected_pdf_sources(release)
        self.observations = resource_use._keyed(read_csv(release / "resource_statement_observations.csv"), "observation_id")
        self.census = resource_use._keyed(read_csv(release / "REE project census.csv"), "專案ID")
        self.lineage = {(r["project_id"], r["column"]): r
                        for r in read_csv(release / "resource_statement_lineage.csv") if r["column"] in resource_use.FIELDS}
        self.vocabulary = load_observation_vocabulary(root, extended=False)

    def evaluate(self, seed, captured, previous, version):
        def answer(status, reason, **kwargs):
            return assessment(status, reason, RESOURCE_PROFILE, version, **kwargs)

        if seed["source_gates"] or seed["status"] != "AUTO_VALIDATED" or captured.get("status") == "SOURCE_BLOCKED":
            return answer("SOURCE_BLOCKED", previous["reason"], missing=seed["source_gates"])
        if previous["status"] == "ACCEPT":
            return answer("ACCEPT", previous["reason"],
                          normalized={"value": previous["normalized_value"], "unit": previous["normalized_unit"]},
                          evidence=previous["lineage"])
        native = captured.get("native") or {}
        column = seed["target_column"]
        entry = self.lineage.get((seed["project_id"], column))
        if entry is None or native.get("token") is None or not native.get("unit"):
            return self.unresolved(previous, captured, version)
        direct, published, problem = resource_use.direct_cell(entry, self.census, self.observations)
        if problem or direct["observation_id"] != seed["observation_id"]:
            return self.unresolved(previous, captured, version)
        if (captured["project_id"] != seed["project_id"] or captured["source_sha256"] != seed["source_sha256"]
                or captured["physical_page"] != seed["physical_page"]):
            return answer("SOURCE_BLOCKED", "CAPTURED_SOURCE_SCOPE_MISMATCH")
        if native.get("quantity") != seed["target_variable"] or native["quantity"] not in self.profile["quantities"]:
            return answer("INSUFFICIENT", "QUANTITY_NOT_BOUND_TO_NATIVE_CELL")
        # Only fill absent fields in the frozen direct observation. Preserve original
        # published tokens and conversion factors when they already exist.
        if not captured.get("anchors") or captured.get("status") != "EXTRACTED":
            return self.unresolved(previous, captured, version)
        if version == "V1":
            missing = [k for k in self.profile["required_context"] if not seed.get(k)]
            if missing:
                return answer("INSUFFICIENT", "USE_CONTEXT_INCOMPLETE", missing=missing, evidence=captured["anchors"])
            context = captured.get("context") or {}
            conflicts = [k for k in ("category", "scope") if context.get(k) and context[k] != seed[k]]
            if conflicts:
                return answer("REVIEW", "EXTRACTED_CONTEXT_CONFLICTS_WITH_SELECTED_SCOPE", missing=conflicts,
                              evidence=captured["anchors"])
        token = str(native["token"])
        units = normalize_context({"unit": native["unit"]}, self.vocabulary)
        unit = units["context"]["unit"]
        if unit is None:
            return answer("INSUFFICIENT", "UNRESOLVED_UNIT_MAPPING")
        if version.endswith("V1") and native.get("token_state") in {"RANGE", "BOUND", "CONFLICT", "NOT_APPLICABLE"}:
            return answer("INSUFFICIENT", "NON_SCALAR_OBSERVATION", evidence=captured["anchors"])
        if direct["original_token"] and direct["original_token"] != token:
            return answer("INSUFFICIENT", "NEW_TOKEN_DIFFERS_FROM_FROZEN_NATIVE_TOKEN", evidence=captured["anchors"])
        if direct["original_unit"] and direct["original_unit"] != unit:
            return answer("INSUFFICIENT", "NEW_UNIT_DIFFERS_FROM_FROZEN_NATIVE_UNIT", evidence=captured["anchors"])
        bound = {**direct, "original_token": token, "original_unit": unit}
        admitted, reason = resource_use.diagnose_admission(bound, entry, self.approved, published)
        provenance = [*captured["anchors"], *units["mappings"]]
        if admitted:
            expected_unit = resource_use.FIELDS[column][1]
            return answer("ACCEPT", "REPLAYED_SELECTED_SOURCE_VALUE", normalized={"value": str(published), "unit": expected_unit},
                          evidence=provenance)
        return answer("INSUFFICIENT", reason, evidence=provenance)

    @staticmethod
    def unresolved(previous, captured, version):
        status, reason = previous["status"], previous["reason"]
        if version.endswith("V1") and reason == "DIFFERENT_SELECTED_SOURCE_CELL":
            # Source-cell identity can be unresolved even for two valid reports
            # of the same estimate. This affects routing, not numeric admission.
            status, reason = "REVIEW", "SELECTED_ESTIMATE_RELATION_UNVERIFIED"
        return assessment(status, reason, RESOURCE_PROFILE, version,
                          missing=captured.get("reasons", ()), evidence=captured.get("anchors", ()))


def assess_technical(candidate, gate, version):
    reason = gate.get("evidence_reason") or "|".join(gate["reasons"]) or "USE_CONTRACT_SATISFIED"
    status = gate["status"]
    stance = candidate["context"].get("claim_nature")
    if version == "V1" and status == "ACCEPT" and stance in {
            "TARGET", "NEGATED", "CONDITIONAL", "ENGINEERING_DESIGN", "HISTORICAL_REFERENCE",
    }:
        status, reason = "INCOMPATIBLE", "CLAIM_NATURE_OUTSIDE_MEASURED_LEACH_USE"
    normalized = None
    if status == "ACCEPT":
        normalized = {"value": candidate["native"]["value"], "unit": candidate["native"]["unit"]}
    return assessment(status, reason, gate["profile_id"], version, normalized=normalized, evidence=candidate["anchors"])


def corroborate_reported_cell(row, peer, relation, seed, peer_seed, arm):
    """A witnessed source cell can corroborate a verified estimate without adding a value."""
    if (row[arm]["status"] not in {"REVIEW", "INSUFFICIENT", "INCOMPATIBLE"}
            or peer[arm]["status"] != "ACCEPT"
            or seed["status"] != "AUTO_VALIDATED" or seed["source_gates"]
            or row["e1"]["native"] != peer["e1"]["native"]
            or seed["source_sha256"] != peer_seed["source_sha256"]
            or seed["project_id"] != peer_seed["project_id"]
            or seed["target_variable"] != peer_seed["target_variable"]
            or seed["statement_kind"] not in {"RESOURCE_CONTEXT", "MINERAL_RESOURCE"}
            or seed["basis"] != "TREO"
            or seed.get("source_transform")
            or any(seed.get(k) != peer_seed.get(k) for k in ("category", "basis", "material_basis", "denominator_basis"))):
        return
    row[arm] = assessment("ACCEPT", "VERIFIED_SAME_SOURCE_CELL_CORROBORATION", RESOURCE_PROFILE, "V1",
                          normalized=peer[arm]["normalized"], evidence=[relation])
    if arm == "E1V1":
        row["same_cell_group"] = peer.get("same_cell_group", peer["source_observation_group"])
