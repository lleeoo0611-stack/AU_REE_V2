"""Source-bound research use assessment shared by shadow runs and evaluation."""
import json

from . import resource_use
from .ontology import normalize_context
from .tabular import read_csv


RESOURCE_PROFILE = "DIRECT_RESOURCE_UNIT_COMPARISON_V1"


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
        vocabulary = json.loads((root / "config/ontology/comparability_v1.json").read_bytes())
        portfolio = json.loads((root / "config/ontology/resource_portfolio_v1.json").read_bytes())
        mappings = portfolio["crosswalk"]["QUDT"]["lexical_units"]
        definitions = [r for r in vocabulary["mappings"] if r["dimension"] != "unit" or r["label"] not in mappings]
        definitions.extend({"dimension": "unit", "label": k, "concept": v, "relation": "exactMatch",
                            "basis": "Source-bound metric unit; selected original gate still applies."}
                           for k, v in mappings.items() if k != v)
        self.vocabulary = {**vocabulary, "mappings": definitions}

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
