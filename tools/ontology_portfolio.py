"""Run the portfolio-wide resource comparison with source-bound estimate relations."""
import argparse
import json
import re
from collections import Counter
from decimal import Decimal
from pathlib import Path

from tools import ontology_gain_compare as previous
from tools.ontology_gain_metrics import load_rows
from tools import normalization_comparison as normalized


ROOT = previous.ROOT
BASE = previous.OUTPUT
OUT = ROOT / "results/ontology-portfolio-20261126"
POLICY = ROOT / "config/ontology/resource_portfolio_v1.json"
EVIDENCE = ROOT / "config/ontology/portfolio_statement_evidence_v1.json"
ARMS = ("B1", "L", "N", "C")
RECOVERABLE = {"MISSING_OR_UNSUPPORTED_UNIT", "NONPOSITIVE_OR_UNBOUND_NUMERIC_TOKEN"}


def context_anchors(assertion, sides, read_page):
    anchors = {side: [] for side in sides}
    for anchor in assertion["anchors"]:
        side = anchor["side"]
        row = sides[side]
        if row["source_sha256"] != anchor["source_sha256"]:
            raise ValueError("Evidence anchor uses the wrong source edition")
        text = " ".join(anchor["text"].split())
        pages = read_page(anchor["source_sha256"], anchor["page"])
        if not text or pages is None or not any(text in page for page in pages):
            raise ValueError(f"Cannot verify evidence anchor {anchor['source_sha256']} p{anchor['page']}")
        anchors[side].append(anchor)
    if any(not group for group in anchors.values()):
        raise ValueError("Each side needs its own source evidence")
    return anchors


def normalized_token(native, row, anchors, policy):
    quantity, target, factors = normalized.FIELDS[row["target_column"]]
    unit = policy["crosswalk"]["QUDT"]["lexical_units"].get(native["unit"])
    if unit not in factors and unit == "kt" and "kt TREO" in factors:
        unit = "kt TREO"
    if unit not in factors or row["target_variable"] != quantity:
        raise ValueError("Unit has no exact conversion for this quantity")
    token = native["text"]
    bound = numeric_pattern(token)
    if not any(a["page"] == row["physical_page"] and a["role"] in {"row", "narrative", "context"}
               and bound.search(a["text"]) for a in anchors):
        raise ValueError("Native numeric token is not bound to its physical table row or narrative")
    native_unit = re.compile(r"(?<![A-Za-z])" + re.escape(native["unit"].split(" TREO")[0]) + r"(?![A-Za-z])")
    if not any(a["page"] == row["physical_page"] and a["role"] in {"header", "narrative", "context"}
               and native_unit.search(a["text"]) for a in anchors):
        raise ValueError(f"Missing native unit {native['unit']!r} on page for {row['candidate_id']}")
    value = normalized._positive(token, unit)
    expected = Decimal(str(native["canonical_value"]))
    if value is None or not normalized._equal(value * Decimal(factors[unit]), expected):
        raise ValueError("Native token does not reconcile with the asserted converted value")
    stored_unit = row["unit"]
    if stored_unit not in factors or not normalized._equal(Decimal(str(row["value"])) * Decimal(factors[stored_unit]), expected):
        raise ValueError("Native token does not reconcile with the frozen evidence value")
    return token, unit, expected, target


def numeric_pattern(token):
    return re.compile(r"(?<![0-9,.])" + re.escape(token) + r"(?![0-9,.])")


def source_ok(row, read_page, cutoff):
    return (row["status"] == "AUTO_VALIDATED" and not row["source_gates"]
            and row["cutoff"] == cutoff and row["source_kind"] == "pdf"
            and bool(row["physical_page"]) and read_page.verified_file(row["source_sha256"]) is not None)


def recover_selected(row, native, anchors, selection, policy, baseline):
    entry = selection.cells.get((row["project_id"], row["target_column"]))
    if not entry:
        return baseline
    cell, direct, published, reason = entry
    if reason or direct["observation_id"] != row["observation_id"]:
        return baseline
    raw = row["raw"]
    if baseline["status"] == "ACCEPT":
        return baseline
    token, unit, value, target = normalized_token(native, row, anchors, policy)
    if direct["original_token"] and direct["original_token"] != token:
        return baseline
    if direct["original_unit"] and direct["original_unit"] != unit:
        return baseline
    if not any(numeric_pattern(token).search(str(marker)) for marker in raw.get("page_markers", [])):
        return previous.response("INSUFFICIENT", "ORIGINAL_SELECTED_CELL_MARKER_MISSING", baseline["lineage"])
    if not normalized._equal(value, published):
        return baseline
    observation = dict(direct, original_token=token, original_unit=unit)
    lineage = [{"action": "VERIFY_NATIVE_SELECTED_VALUE", "policy": policy["version"], "original_token": token,
                "original_unit": native["unit"], "normalized_value": str(value), "anchors": anchors}]
    result = previous.from_old_checks(observation, cell, selection.approved, published, lineage)
    if result["status"] == "ACCEPT":
        result.update(field=row["target_column"], resource_category=row["category"],
                      normalized_value=str(published), normalized_unit=target,
                      source_sha256=row["source_sha256"], page=row["physical_page"],
                      source_statement_key=row["source_statement_key"])
    return result


def relation_outcome(assertion, candidate, target, target_decision, anchors, policy):
    relation = assertion["relation"]
    trace = [{"action": relation, "policy": policy["version"], "target_candidate_id": target["candidate_id"],
              "estimate": assertion["estimate"], "facts": assertion["facts"],
              "anchors": assertion["anchors"], "rationale": assertion["rationale"]}]
    if relation in policy["confirmed_exclusions"]:
        return previous.response("INCOMPATIBLE", relation, trace)
    if relation in policy["non_numeric_support"]:
        return previous.response("INSUFFICIENT", relation, trace)
    if relation not in policy["same_estimate_relations"]:
        raise ValueError(f"Unknown statement relation {relation}")
    facts = assertion["facts"]
    if (candidate["category"] != target["category"] or candidate["category"] != assertion["estimate"]["category"]
            or candidate["statement_kind"] not in {"MINERAL_RESOURCE", "RESOURCE_CONTEXT"}
            or target["statement_kind"] != "RESOURCE_CONTEXT"
            or any(candidate.get(k) != target.get(k) for k in ("basis", "material_basis", "denominator_basis"))
            or candidate["basis"] != "TREO"
            or candidate.get("source_transform") or target.get("source_transform")
            or candidate["target_variable"] != facts["quantity_kind"]):
        return previous.response("INSUFFICIENT", "NO_EXACT_RESOURCE_CONTEXT", trace)
    estimate = assertion["estimate"]
    if (not all(estimate.get(k) for k in ("scope", "estimate_date", "cutoff"))
            or estimate["scope"] != target["scope"] or estimate["estimate_date"] != target["effective_date"]):
        return previous.response("INSUFFICIENT", "ESTIMATE_RELATION_CONTEXT_INCOMPLETE", trace)
    if target_decision["status"] != "ACCEPT":
        return previous.response("INSUFFICIENT", "SELECTED_VALUE_STILL_NOT_VERIFIED", trace)
    _, _, source_value, _ = normalized_token(facts["from"], candidate, anchors["candidate"], policy)
    _, _, target_value, _ = normalized_token(facts["to"], target, anchors["target"], policy)
    if not normalized._equal(source_value, target_value) or not normalized._equal(
            target_value, Decimal(target_decision["normalized_value"])):
        return previous.response("INSUFFICIENT", "ORIGINAL_AND_SELECTED_VALUE_DIFFER", trace)
    return {**target_decision, "reason": "VERIFIED_CORROBORATING_REPRESENTATION", "lineage": trace,
            "source_sha256": candidate["source_sha256"], "page": candidate["physical_page"],
            "source_statement_key": candidate["source_statement_key"]}


def compare(candidates, old, selection, read_page, policy, evidence):
    if set(candidates) != set(old):
        raise ValueError("The same frozen observations must enter all rules")
    expected = {k for k, r in old.items() if r["B1"]["reason"] in RECOVERABLE}
    witnesses = {r["candidate_id"] for r in evidence["selected_witnesses"]}
    exclusions = {r["candidate_id"] for r in evidence["selected_witnesses_excluded"]}
    if witnesses & exclusions or witnesses | exclusions != expected:
        raise ValueError("Native evidence must account for the complete predeclared reason stratum")
    for cid, decision in old.items():
        if decision["B1"]["status"] == "ACCEPT" and not source_ok(candidates[cid], read_page, evidence["cutoff"]):
            raise ValueError(f"Prior accepted original unavailable or changed: {cid}")
    decisions = {cid: {arm: d["B1"] for arm in ARMS} for cid, d in old.items()}
    for cid, decisions_by_arm in decisions.items():
        if decisions_by_arm["C"]["reason"] == "DIFFERENT_SELECTED_SOURCE_CELL":
            decisions_by_arm["C"] = previous.response("INSUFFICIENT", "UNVERIFIED_SELECTED_STATEMENT_RELATION",
                                                        decisions_by_arm["B1"]["lineage"])
    for witness in evidence["selected_witnesses"]:
        row = candidates[witness["candidate_id"]]
        cid = row["candidate_id"]
        if not source_ok(row, read_page, evidence["cutoff"]):
            continue
        anchors = context_anchors(witness, {"candidate": row}, read_page)["candidate"]
        decisions[cid]["N"] = recover_selected(row, witness, anchors, selection, policy, decisions[cid]["N"])
        # Compare the same recovered source token against the existing literal unit
        # factors, without the new lexical adapter.
        if witness["unit"] in normalized.FIELDS[row["target_column"]][2]:
            decisions[cid]["L"] = decisions[cid]["N"]
        decisions[cid]["C"] = decisions[cid]["N"]
    verified = {}
    for assertion in evidence["assertions"]:
        cid, target_id = assertion["candidate_id"], assertion["target_candidate_id"]
        candidate, target = candidates[cid], candidates[target_id]
        if cid in verified or cid == target_id:
            raise ValueError("Every relation must identify two distinct observations")
        if candidate["project_id"] != target["project_id"] or candidate["project_id"] != assertion["estimate"]["project_id"]:
            raise ValueError("Ambiguous Project identity")
        if candidate["target_variable"] != target["target_variable"]:
            raise ValueError("Assertion switches the declared quantity")
        anchors = context_anchors(assertion, {"candidate": candidate, "target": target}, read_page)
        verified[cid] = assertion, anchors
    for cid, (assertion, anchors) in verified.items():
        tid = assertion["target_candidate_id"]
        candidate, target = candidates[cid], candidates[tid]
        if decisions[cid]["C"]["status"] == "ACCEPT":
            continue
        if not all(source_ok(row, read_page, evidence["cutoff"]) for row in (candidate, target)):
            decisions[cid]["C"] = previous.response("BLOCKED", "CANONICAL_SOURCE_OR_OBSERVATION_INELIGIBLE")
            continue
        decisions[cid]["C"] = relation_outcome(assertion, candidate, target, decisions[tid]["N"], anchors, policy)
    for control in evidence["negative_controls"]:
        cid, tid = control["candidate_id"], control["target_candidate_id"]
        candidate, target = candidates[cid], candidates[tid]
        if cid in verified or candidate["project_id"] != target["project_id"] or control["relation"] not in policy["confirmed_exclusions"]:
            raise ValueError("Negative statement control must be separate and bound to the same Project")
        # Scope conflicts can be established within one document by two separately
        # reviewed table locations. The fixture binds whichever sides are cited.
        sides = {"candidate": candidate, "target": target}
        context_anchors(control, sides, read_page)
        if decisions[cid]["C"]["status"] not in {"ACCEPT", "BLOCKED"}:
            decisions[cid]["C"] = previous.response("INCOMPATIBLE", control["relation"], [control])
    return decisions


def publish(candidates_path, release, assets, output, evidence_path):
    candidates = load_rows(candidates_path)
    old = load_rows(BASE / "decisions.jsonl")
    audit = json.loads((BASE / "decision_audit.json").read_bytes())
    if previous.sha(candidates_path) != audit["candidate_file_sha256"]:
        raise ValueError("Restore the frozen preselection inventory")
    original_inventory = json.loads((BASE / "inventory_manifest.json").read_bytes())
    for filename, checksum in original_inventory["release_inputs_sha256"].items():
        if previous.sha(release / filename) != checksum:
            raise ValueError(f"Release input differs from the original research baseline: {filename}")
    evidence = json.loads(evidence_path.read_bytes())
    policy = json.loads(POLICY.read_bytes())
    cutoff = json.loads((release / "census_release.json").read_bytes())["cutoff"]
    if evidence["cutoff"] != cutoff or policy["use"] != previous.USE:
        raise ValueError("Research cutoff or declared use mismatch")
    selection = previous.FrozenSelection(release)
    decisions = compare(candidates, old, selection, previous.page_reader(assets), policy, evidence)
    rows = []
    for cid, arms in sorted(decisions.items()):
        row = candidates[cid]
        # The declared use permits one selected Project-field value, even when several
        # source rows represent it. Census exports continue to control project scope.
        slot = [row[k] for k in ("project_id", "target_column", "use_id")]
        rows.append({"candidate_id": cid, "project_id": row["project_id"], "field": row["target_column"],
                     "evidence_identity": slot, **arms})
    output.mkdir(parents=True, exist_ok=True)
    previous.jsonlines(output / "decisions_overlay.jsonl", rows)
    pairs = project_pairs(decisions, old)
    previous.jsonlines(output / "project_pairs.jsonl", pairs)
    summary = {"candidate_sha256": previous.sha(candidates_path), "prior_decisions_sha256": previous.sha(BASE / "decisions.jsonl"),
               "rules_sha256": previous.sha(POLICY), "source_assertions_sha256": previous.sha(evidence_path),
               "code_sha256": previous.sha(Path(__file__)), "cutoff": cutoff, "candidates": len(rows),
               "definition": {"B1":"Published prior extraction and ontology",
                              "L":"Same newly read source cells, restricted to literal legacy units",
                              "N":"Same newly read source cells plus explicit unit mapping",
                              "C":"Same native evidence plus separately verified source-to-estimate relationships"},
               "dispositions": {arm: dict(Counter(r[arm]["status"] for r in rows)) for arm in ARMS},
               "descriptive_project_pairs": {
                   arm: len({(r["left"], r["right"]) for r in pairs
                             if r["arm"] == arm and r["status"] == "DISTINCT_OBSERVATIONS"})
                   for arm in ARMS},
               "changes": {f"{a}_to_{b}": changes(rows, a, b) for a, b in
                           (("B1","L"),("L","N"),("B1","N"),("N","C"),("B1","C"))},
               "verified_statement_assertions": dict(Counter(r["relation"] for r in evidence["assertions"])),
               "verified_negative_controls": dict(Counter(r["relation"] for r in evidence["negative_controls"])),
               "reference_scope": "Development source adjudication, not a new independent holdout."}
    previous.write_json(output / "effect_summary.json", summary)
    return summary


def project_pairs(decisions, old):
    # Adapt the existing report's arm slots without changing the frozen evaluator.
    labels = {"A0": "B1", "B0": "L", "A1": "N", "B1": "C"}
    inputs = []
    for cid, arms in decisions.items():
        row = {k: old[cid][k] for k in ("candidate_id", "project_id", "independent_observation_id")}
        row.update({slot: arms[arm] for slot, arm in labels.items()})
        inputs.append(row)
    return [{**record, "arm": labels[record["arm"]]} for record in previous.pair_list(inputs)]


def changes(rows, a, b):
    def admitted(arm):
        return [r for r in rows if r[arm]["status"] == "ACCEPT"]
    before, after = admitted(a), admitted(b)
    before_ids = {r["candidate_id"] for r in before}
    after_ids = {r["candidate_id"] for r in after}
    new_slots = {tuple(r["evidence_identity"]) for r in after} - {tuple(r["evidence_identity"]) for r in before}
    return {"candidate_additions": sorted(after_ids - before_ids), "candidate_losses": sorted(before_ids - after_ids),
            "new_project_fields": sorted(new_slots), "new_projects": sorted({r["project_id"] for r in after}
                                                                             - {r["project_id"] for r in before})}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidates", type=Path, default=BASE / "candidates.jsonl")
    parser.add_argument("--release", type=Path, default=previous.RELEASE)
    parser.add_argument("--assets", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=OUT)
    parser.add_argument("--evidence", type=Path, default=EVIDENCE)
    args = parser.parse_args()
    publish(args.candidates, args.release, args.assets, args.output, args.evidence)
