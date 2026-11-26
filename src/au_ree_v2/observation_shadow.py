"""Read the frozen Phase 22 evidence and run paired observations beside formal results."""
import json
from collections import Counter
from itertools import combinations
from pathlib import Path
from time import perf_counter

from .observation_semantics import RESOURCE_PROFILE, ResourceContract, assess_technical, corroborate_reported_cell
from .store import canonical, digest, filehash


BASELINE = "results/ontology-gain-20261126"
PORTFOLIO = "results/ontology-portfolio-20261126"
RELEASE = "results/ree-project-census/gap173-20261122"
STUDY = "results/observation-shadow-20261126"
ARMS = ("E0V0", "E0V1", "E1V0", "E1V1")
DIMENSIONS = ("basis", "material_basis", "denominator_basis", "feed", "endpoint", "scale", "process_stage",
              "claim_nature", "sample_id", "case_id", "effective_date", "estimate_date", "cutoff")


def read_jsonl(path):
    with path.open(encoding="utf-8") as source:
        return [json.loads(line) for line in source if line.strip()]


def write(path, data):
    path.write_text(data, encoding="utf-8", newline="\n")


def jsonl(path, rows):
    write(path, "".join(canonical(r) + "\n" for r in rows))


def existing_resource(seed, decision):
    native = {"quantity": seed["variable"], "token": seed["original_token"], "unit": seed["original_unit"],
              "token_state": None, "bounds": None}
    for link in decision["lineage"]:
        if link.get("action") == "VERIFY_NATIVE_SELECTED_VALUE":
            native.update(token=link["original_token"], unit=link["original_unit"])
        elif decision["reason"] == "VERIFIED_CORROBORATING_REPRESENTATION" and link.get("facts"):
            native.update(token=link["facts"]["from"]["text"], unit=link["facts"]["from"]["unit"])
    return {
        "candidate_id": seed["candidate_id"], "observation_id": seed["observation_id"], "project_id": seed["project_id"],
        "physical_page": seed["physical_page"], "source_sha256": seed["source_sha256"],
        "profile_id": RESOURCE_PROFILE, "status": "LEGACY_SOURCE_VIEW",
        "native": native,
        "context": {k: seed.get(k) for k in ("scope", "category", "basis", "material_basis", "denominator_basis",
                                           "statement_id", "effective_date", "cutoff_grade", "date_role")},
        "anchors": decision["lineage"], "reasons": seed["source_gates"],
    }


def stable_row(e0, e1, decisions, split, source_id=None):
    row = {k: e0[k] for k in ("candidate_id", "observation_id", "project_id", "physical_page", "source_sha256",
                              "profile_id")}
    return {**row, "split": split, "target_quantity": e0.get("target_quantity", e0["native"]["quantity"]),
            "source_observation_group": source_id or row["observation_id"],
            "e0": e0, "e1": e1, **decisions}


def partition(row, frozen):
    if (row["project_id"] in frozen["quarantine_projects"]
            or row["source_sha256"] in frozen["quarantine_source_sha256"]):
        return "QUARANTINED_FOR_INDEPENDENT_REVIEW"
    return "DEVELOPMENT_OR_REGRESSION"


def by_id(rows):
    out = {r["candidate_id"]: r for r in rows}
    if len(out) != len(rows):
        raise ValueError("Each candidate representation needs a unique stable ID")
    return out


def summary_for(rows, arm):
    accepted = [r for r in rows if r[arm]["status"] == "ACCEPT"]
    extraction = "e0" if arm.startswith("E0") else "e1"
    fields = set()
    comparable = {}
    missing = Counter()
    for r in rows:
        item = r[extraction]
        context = item.get("context") or {}
        missing.update(key for key in DIMENSIONS if context.get(key) is None or context.get(key) == "")
    for r in accepted:
        item = r[extraction]
        context = item.get("context") or {}
        quantity = r["target_quantity"]
        fields.add((r["project_id"], quantity, r["profile_id"]))
        if r["profile_id"] == RESOURCE_PROFILE:
            category = context.get("category") or r["e0"]["context"].get("category")
            groups = comparable.setdefault((quantity, category), {})
            groups.setdefault(r["project_id"], set()).add(observation_group(r, arm))
    pairs = set()
    for projects in comparable.values():
        for a, b in combinations(sorted(projects), 2):
            if not projects[a] & projects[b]:
                pairs.add((a, b))
    return {
        "candidate_records": len(rows), "candidate_observation_groups": len({r["source_observation_group"] for r in rows}),
        "source_tokens_present": sum((r[extraction].get("native") or {}).get("token") not in (None, "") for r in rows),
        "extraction_dispositions": dict(Counter(r[extraction]["status"] for r in rows)),
        "accepted_source_records": len(accepted),
        "accepted_observation_groups": len({observation_group(r, arm) for r in accepted}),
        "new_corroborating_records": sum(r[arm]["reason"] == "VERIFIED_SAME_SOURCE_CELL_CORROBORATION"
                                         for r in accepted),
        "project_field_use_count": len(fields), "projects": sorted({r["project_id"] for r in accepted}),
        "descriptive_resource_pairs": len(pairs),
        "disposition": dict(Counter(r[arm]["status"] for r in rows)), "context_missing": dict(missing),
    }


def observation_group(row, arm):
    if arm in {"E1V1", "AUTO_E1V1"} and row.get("same_cell_group"):
        return row["same_cell_group"]
    return row["source_observation_group"]


def use_relations(rows, seeds, relations, arm="E1V1"):
    candidate_rows = by_id(rows)
    candidate_seeds = by_id(seeds)
    for relation in relations:
        if relation["relation"] != "SAME_REPORTED_CELL" or relation["status"] != "CONFIRMED":
            continue
        left_id, right_id = relation["candidate_ids"]
        left, right = candidate_rows[left_id], candidate_rows[right_id]
        corroborate_reported_cell(left, right, relation, candidate_seeds[left_id], candidate_seeds[right_id], arm)
        corroborate_reported_cell(right, left, relation, candidate_seeds[right_id], candidate_seeds[left_id], arm)


def transitions(rows):
    comparison = {}
    for old, new in (("E0V0","E0V1"), ("E0V0","E1V0"), ("E1V0","E1V1"), ("E0V0","E1V1")):
        name = f"{old}_to_{new}"
        changes = [r for r in rows if r[old]["status"] != r[new]["status"] or r[old]["reason"] != r[new]["reason"]]
        comparison[name] = {
            "gained": [r["candidate_id"] for r in changes if r[old]["status"] != "ACCEPT" and r[new]["status"] == "ACCEPT"],
            "lost": [r["candidate_id"] for r in changes if r[old]["status"] == "ACCEPT" and r[new]["status"] != "ACCEPT"],
            "dispositions": [{"candidate_id": r["candidate_id"], "before": r[old]["status"], "after": r[new]["status"],
                              "reason_before": r[old]["reason"], "reason_after": r[new]["reason"]} for r in changes],
        }
    return comparison


def run(root, originals, frozen_run, output, *, development_only=False):
    """The evidence under evaluation comes from existing Phase 22 outputs and its static kit."""
    from .semantic_resource import extract_resource_observations, resource_relations
    from .semantic_technical import baseline_technical, extract_technical, technical_audit, technical_gate, technical_rows

    start = perf_counter()
    root, originals, frozen_run, output = map(Path, (root, originals, frozen_run, output))
    prior, release = root / BASELINE, root / RELEASE
    profile_path = root / "config/ontology/shadow_profiles_v1.json"
    policy_path = root / "config/evidence_policy.json"
    manifest_path = root / STUDY / "review_split.json"
    study = json.loads(manifest_path.read_bytes())
    settings = json.loads(profile_path.read_bytes())
    policy = json.loads(policy_path.read_bytes())
    input_manifest = json.loads((prior / "inventory_manifest.json").read_bytes())
    seed_path = prior / "candidates.jsonl"
    technical_path = frozen_run / "technical_cells.csv"
    resolved_path = frozen_run / "resolved_evidence.csv"
    formal_census = frozen_run / "census.csv"
    old_path = prior / "decisions.jsonl"
    upstream = json.loads((prior / "upstream_audit.json").read_bytes())
    if (filehash(seed_path) != input_manifest["candidate_sha256"] or study["cutoff"] != input_manifest["cutoff"]
            or filehash(technical_path) != upstream["run_outputs_sha256"][technical_path.name]):
        raise ValueError("Shadow requires the checksum-bound Phase 22 replay inputs")
    if any(filehash(release / n) != sha for n, sha in input_manifest["release_inputs_sha256"].items()):
        raise ValueError("Shadow release input differs from the original Phase 22 snapshot")
    resource_seeds = read_jsonl(seed_path)
    technical_seeds = list(technical_rows(technical_path, resolved_path))
    projection = settings["frozen_formal_projection"]
    if (digest(technical_seeds) != projection["technical_semantic_rows_sha256"]
            or filehash(formal_census) != projection["census_csv_sha256"]):
        raise ValueError("Formal resource Census or technical evidence under comparison differs from the frozen projection")
    if development_only:
        resource_seeds = [r for r in resource_seeds if partition(r, study) == "DEVELOPMENT_OR_REGRESSION"]
        technical_seeds = [r for r in technical_seeds if partition(r, study) == "DEVELOPMENT_OR_REGRESSION"]
    old = by_id(read_jsonl(old_path))
    portfolio_path = root / PORTFOLIO / "decisions_overlay.jsonl"
    portfolio = by_id(read_jsonl(portfolio_path))
    if set(old) != set(portfolio) or any(portfolio[cid]["B1"] != r["B1"] for cid, r in old.items()):
        raise ValueError("Prior deterministic and reviewed portfolio arms do not share their original baseline")
    e1_resources = by_id(extract_resource_observations(resource_seeds, originals))
    technical_old = by_id(baseline_technical(technical_seeds))
    technical_new = by_id(extract_technical(technical_seeds, originals))
    if set(e1_resources) != {r["candidate_id"] for r in resource_seeds} or set(technical_old) != set(technical_new):
        raise ValueError("Keep unextracted inputs with explicit absence or review dispositions")
    contract = ResourceContract(root, release, settings["profiles"][RESOURCE_PROFILE])
    rows = []
    seed_map = by_id(resource_seeds)
    for seed in resource_seeds:
        cid = seed["candidate_id"]
        previous = portfolio[cid]["C"]
        e0, e1 = existing_resource(seed, previous), e1_resources[cid]
        e0["target_quantity"] = seed["target_variable"]
        e0["inherited_portfolio_adjudication"] = previous != old[cid]["B1"]
        verdicts = {arm: contract.evaluate(seed, e0 if arm.startswith("E0") else e1, previous, arm[-2:]) for arm in ARMS}
        group = seed["independent_observation_id"]
        if previous["reason"] == "VERIFIED_CORROBORATING_REPRESENTATION":
            peer = previous["lineage"][0]["target_candidate_id"]
            if peer in seed_map:
                group = seed_map[peer]["independent_observation_id"]
        row = stable_row(e0, e1, verdicts, partition(seed, study), group)
        row["AUTO_E0V0"] = contract.evaluate(seed, existing_resource(seed, old[cid]["B1"]), old[cid]["B1"], "V0")
        row["AUTO_E1V1"] = contract.evaluate(seed, e1, old[cid]["B1"], "V1")
        rows.append(row)
    for cid, e0 in technical_old.items():
        e1 = technical_new[cid]
        verdicts = {}
        for arm in ARMS:
            version = arm[-2:]
            candidate = e0 if arm.startswith("E0") else e1
            gate = technical_gate(candidate, policy, version)
            verdicts[arm] = assess_technical(candidate, gate, version)
        rows.append(stable_row(e0, e1, verdicts, partition(e0, study)))
    rows.sort(key=lambda r: (r["profile_id"], r["candidate_id"]))
    relations = resource_relations(list(e1_resources.values()))
    use_relations(rows, resource_seeds, relations)
    use_relations(rows, resource_seeds, relations, "AUTO_E1V1")
    output.mkdir(parents=True, exist_ok=True)
    for row in rows:
        for arm in ARMS:
            row[arm]["profile_version"] = settings["version"] + ":" + arm[-2:]
    sections = {}
    for profile_id in settings["profiles"]:
        selected = [r for r in rows if r["profile_id"] == profile_id]
        sections[profile_id] = {
            "by_arm": {arm: summary_for(selected, arm) for arm in ARMS},
            "quarantined_by_arm": {arm: summary_for(
                [r for r in selected if r["split"] == "QUARANTINED_FOR_INDEPENDENT_REVIEW"], arm) for arm in ARMS},
            "contrasts": transitions(selected),
        }
    input_paths = [seed_path, technical_path, resolved_path, formal_census, old_path, portfolio_path,
                   manifest_path, profile_path, policy_path]
    module_names = ("observation_shadow.py", "observation_semantics.py", "semantic_resource.py",
                    "semantic_technical.py", "resource_use.py", "technical.py", "technical_tables.py", "ontology.py")
    from importlib.metadata import version
    receipt = {"schema": "observation-shadow-v1", "profiles": settings["version"], "seed": study["seed"],
               "cutoff": study["cutoff"], "base_commit": study["commit"], "development_only": development_only,
               "input_sha256": {p.name: filehash(p) for p in input_paths},
               "code_sha256": {n: filehash(Path(__file__).with_name(n)) for n in module_names},
               "dependencies": {"PyMuPDF": version("PyMuPDF")}, "sections": sections,
               "relationship_candidates": len(relations), "relationship_digest": digest(relations),
               "technical_context_audit": technical_audit(list(technical_old.values()), list(technical_new.values())),
               "resource_capture": dict(Counter(r["status"] for r in e1_resources.values())),
               "automatic_resource_reproduction": {
                   "baseline": sum(r["AUTO_E0V0"]["status"] == "ACCEPT" for r in rows if "AUTO_E0V0" in r),
                   "candidate_admissions": sum(r["AUTO_E1V1"]["status"] == "ACCEPT" for r in rows if "AUTO_E1V1" in r),
                   "automatically_recovered_ids": [r["candidate_id"] for r in rows if "AUTO_E1V1" in r
                                                    and r["AUTO_E0V0"]["status"] != "ACCEPT" and r["AUTO_E1V1"]["status"] == "ACCEPT"],
                   "interpretation": "Automatic reconstruction from B1, explicitly separate from the inherited C baseline."
               },
               "independent_validation_pending": True, "independent_precision": None, "independent_recall": None,
               "promotion_ready": False, "formal_effect": "SIDE_OUTPUT_ONLY"}
    jsonl(output / "decisions.jsonl", rows)
    jsonl(output / "relationship_candidates.jsonl", relations)
    write(output / "comparison.json", json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    return {"status": "SHADOW_COMPLETE", "output": str(output), "candidates": len(rows),
            "relationship_candidates": len(relations), "elapsed_seconds": round(perf_counter() - start, 3)}
