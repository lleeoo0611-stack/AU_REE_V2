"""Report coverage of the resource-use experiment against every frozen Census project."""
import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

from au_ree_v2.store import filehash
from tools.ontology_gain_inventory import COLUMNS, RELEASE, jsonl, report, rows

ROOT = Path(__file__).resolve().parents[1]
PILOT = ROOT / "results/ontology-gain-20261126"
OUTPUT = ROOT / "results/ontology-portfolio-20261126"
COMPARISON = ROOT / "results/ree-project-census/coverage-locked-20261125/REE project census.csv"
LEGACY_ARMS = ("A0", "B0", "A1", "B1")
EXTENSIONS = ("N", "C")
CENSUS = "REE project census.csv"
CORE_FIELDS = tuple(column for column, _ in COLUMNS.values())
ACCEPT = "ACCEPT"


def keyed(records, key):
    index = {}
    for row in records:
        value = key(row)
        if value in index:
            raise ValueError(f"Duplicate scope key: {value}")
        index[value] = row
    return index


def read_jsonl(path):
    with path.open(encoding="utf-8-sig") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def study_status(census_row, fields, status_rows):
    present = tuple(f for f in fields if status_rows[f]["value_state"] == "PRESENT")
    if any(bool(census_row[f]) != (f in present) for f in fields):
        raise ValueError(f"Census value and field statuses disagree for {census_row['專案ID']}")
    if len(present) == len(fields) and census_row["有TREO資源估計"] == "是":
        return "COMPLETE_SELECTED_TREO_RESOURCE", present
    if not present and all(status_rows[f]["status"] == "NOT_APPLICABLE_NO_MRE" for f in fields):
        return "NO_SELECTED_RESOURCE", present
    return "PARTIAL_SELECTED_RESOURCE", present


def compare_decisions(candidates, decisions, overlay):
    """Link decisions to the same observation/use and preserve an unmodified baseline."""
    candidate_map = keyed(candidates, lambda r: r["candidate_id"])
    decision_map = keyed(decisions, lambda r: r["candidate_id"])
    if set(candidate_map) != set(decision_map):
        raise ValueError("Decision IDs differ from the frozen candidate IDs")
    overlay_map = keyed(overlay, lambda r: r["candidate_id"]) if overlay is not None else {}
    if not overlay_map.keys() <= candidate_map.keys():
        raise ValueError("Overlay contains unknown candidate IDs")
    for cid, candidate in candidate_map.items():
        decision = decision_map[cid]
        for field in ("project_id", "observation_id", "use_id", "target_variable"):
            if decision[field] != candidate[field] or (
                    field in overlay_map.get(cid, {}) and overlay_map[cid][field] != candidate[field]):
                raise ValueError(f"Decision identity mismatch: {cid} {field}")
        if overlay is not None:
            changes = overlay_map.get(cid, {})
            inherited = decision["B1"]
            decision = dict(decision)
            for arm in EXTENSIONS:
                outcome = changes.get(arm, inherited)
                if (arm in changes and outcome["status"] == ACCEPT and inherited["status"] != ACCEPT
                        and not (outcome.get("evidence_identity") or changes.get("evidence_identity"))):
                    raise ValueError(f"Overlay admission is missing evidence identity: {cid} {arm}")
                decision[arm] = outcome
                inherited = outcome
            decision_map[cid] = decision
    return decision_map


def field_use(candidate):
    return candidate["project_id"], COLUMNS[candidate["target_variable"]][0], candidate["use_id"]


def measure_change(candidates, decisions, all_uses, accepted_counts, first, second):
    added = all_uses[second] - all_uses[first]
    removed = all_uses[first] - all_uses[second]
    new_records = [r for r in candidates if decisions[r["candidate_id"]][first]["status"] != ACCEPT
                   and decisions[r["candidate_id"]][second]["status"] == ACCEPT]
    added_support = sorted(r["candidate_id"] for r in new_records if field_use(r) in all_uses[first])
    before_projects = {pid for pid, _, _ in all_uses[first]}
    after_projects = {pid for pid, _, _ in all_uses[second]}
    return {
        "newly_accepted_observation_records": len(new_records),
        "additional_accepted_observation_records": accepted_counts[second] - accepted_counts[first],
        "added_evidence_for_existing_project_field_uses": added_support,
        "added_project_field_uses": [list(entry) for entry in sorted(added)],
        "removed_project_field_uses": [list(entry) for entry in sorted(removed)],
        "added_project_ids": sorted(after_projects - before_projects),
        "removed_project_ids": sorted(before_projects - after_projects),
    }


def observe(release, pilot, comparison, overlay_path=None):
    census_path = release / CENSUS
    census = keyed(rows(census_path), lambda r: r["專案ID"])
    selections = keyed(rows(release / "census_selection.csv"), lambda r: r["project_id"])
    release_certificate = json.loads((release / "census_release.json").read_bytes())
    if set(census) != set(release_certificate["selected_census_ids"]) or set(census) != set(selections):
        raise ValueError("Census membership differs from the frozen selectors")
    if filehash(census_path) != release_certificate["census_csv_sha256"]:
        raise ValueError("Census contents differ from the frozen release")
    comparison_ids = set(keyed(rows(comparison), lambda r: r["專案ID"]))
    statuses = keyed((r for r in rows(release / "field_status.csv") if r["column"] in CORE_FIELDS),
                     lambda r: (r["project_id"], r["column"]))
    published_observations = Counter(r["project_id"] for r in rows(release / "resource_statement_observations.csv")
                                     if r["selection_role"] == "MATCHED_SELECTED_STATEMENT")
    roles = Counter(r["project_id"] for r in rows(release / "census_identity_roles.csv")
                    if r["role"] == "DOCUMENTED_CANONICAL_ALIAS")
    formal = set(json.loads((release / "formal_c1_release.json").read_bytes())["formally_releasable"])
    candidates = read_jsonl(pilot / "candidates.jsonl")
    manifest = json.loads((pilot / "inventory_manifest.json").read_bytes())
    if manifest["cutoff"] != release_certificate["cutoff"] or manifest["run_id"] != release_certificate["run_id"] or (
            manifest["candidate_sha256"] != filehash(pilot / "candidates.jsonl")):
        raise ValueError("Candidate manifest does not match the frozen release")
    overlay = read_jsonl(overlay_path) if overlay_path else None
    decisions = compare_decisions(candidates, read_jsonl(pilot / "decisions.jsonl"), overlay)
    arms = (*LEGACY_ARMS, *EXTENSIONS) if overlay is not None else LEGACY_ARMS
    grouped = defaultdict(list)
    for row in candidates:
        grouped[row["project_id"]].append(row)
    by_project = []
    all_uses = defaultdict(set)
    accepted_counts = Counter()
    by_arm_dispositions = {arm: Counter() for arm in arms}
    for pid, project in sorted(census.items()):
        group = grouped.get(pid, [])
        field_status = {field: statuses[pid, field] for field in CORE_FIELDS}
        status, present = study_status(project, CORE_FIELDS, field_status)
        result = {
            "project_id": pid, "canonical_project_id": selections[pid]["canonical_project_id"],
            "project_name": project["專案名稱"], "jurisdiction": project["州省地區"],
            "in_coverage_locked_release": pid in comparison_ids, "resource_class": status,
            "has_complete_treo_resource": project["有TREO資源估計"] == "是",
            "published_core_fields": list(present),
            "core_field_status": {field: entry["status"] for field, entry in field_status.items()},
            "candidate_observations": len(group), "source_records": len({r["source_sha256"] for r in group}),
            "usable_source_context_candidate_count": sum(r["status"] == "AUTO_VALIDATED" and not r["source_gates"]
                                                        for r in group),
            "source_or_identity_gate_counts": dict(Counter(reason for r in group for reason in r["source_gates"])),
            "static_pdf_candidates": sum(r["source_kind"] == "pdf" for r in group),
            "government_or_other_source_candidates": sum(r["source_kind"] != "pdf" for r in group),
            "candidate_only_without_selected_resource": status == "NO_SELECTED_RESOURCE" and bool(group),
            "released_selected_resource_observations": published_observations[pid],
            "documented_identity_alias_records": roles[pid],
            "formal_mcda_eligible_at_freeze": pid in formal,
        }
        for arm in arms:
            use_ids = set()
            disposition, reasons = Counter(), Counter()
            for candidate in group:
                outcome = decisions[candidate["candidate_id"]][arm]
                disposition[outcome["status"]] += 1
                if outcome["status"] == ACCEPT:
                    use_ids.add(field_use(candidate))
                else:
                    reasons[outcome["reason"]] += 1
            all_uses[arm].update(use_ids)
            accepted_counts[arm] += disposition[ACCEPT]
            by_arm_dispositions[arm].update(disposition)
            result[f"{arm}_coverage"] = ("ACCEPTED_DESCRIPTIVE_USE" if use_ids else
                                         "CANDIDATES_NONE_ADMITTED" if group else "NO_IN_SCOPE_CANDIDATES")
            result[f"{arm}_accepted_observations"] = disposition[ACCEPT]
            result[f"{arm}_distinct_field_uses"] = len(use_ids)
            result[f"{arm}_accepted_fields"] = sorted({field for _, field, _ in use_ids})
            result[f"{arm}_other_decisions"] = dict(reasons)
        by_project.append(result)
    excluded = []
    for row in candidates:
        if row["project_id"] not in census:
            excluded.append({
                **{k: row[k] for k in ("candidate_id", "observation_id", "project_id", "scope", "variable",
                                       "source_sha256", "physical_page", "use_id")},
                "scope_status": "PROJECT_ID_OUTSIDE_FROZEN_CENSUS",
                "source_gates": row["source_gates"],
                "decisions": {arm: decisions[row["candidate_id"]][arm]["status"] for arm in arms},
            })
    if any(outcome == ACCEPT for row in excluded for outcome in row["decisions"].values()):
        raise ValueError("A project outside the Census received a descriptive-use admission")
    metrics = {
        arm: {"accepted_observations": accepted_counts[arm], "unique_project_field_uses": len(all_uses[arm]),
              "projects_with_accepted_use": len({pid for pid, _, _ in all_uses[arm]}),
              "projects_by_coverage": dict(Counter(row[f"{arm}_coverage"] for row in by_project)),
              "candidate_dispositions": dict(by_arm_dispositions[arm])}
        for arm in arms
    }
    deltas = {f"{second}_vs_{first}": measure_change(candidates, decisions, all_uses, accepted_counts, first, second)
              for first, second in (("B1", "N"), ("N", "C"), ("B1", "C"))} if overlay is not None else {}
    return by_project, excluded, {
        "census_projects": len(census), "cutoff": release_certificate["cutoff"],
        "coverage_locked_comparison": {"same_ids": set(census) == comparison_ids,
                                      "only_in_frozen_release": sorted(set(census) - comparison_ids),
                                      "only_in_coverage_locked_release": sorted(comparison_ids - set(census))},
        "resource_classes": dict(Counter(row["resource_class"] for row in by_project)),
        "coverage_by_resource_class": {
            arm: {resource_class: dict(Counter(row[f"{arm}_coverage"] for row in by_project
                                                if row["resource_class"] == resource_class))
                  for resource_class in sorted({row["resource_class"] for row in by_project})}
            for arm in arms
        },
        "candidate_records": len(candidates),
        "candidate_records_in_census": len(candidates) - len(excluded),
        "census_projects_with_in_scope_candidates": len(set(grouped) & set(census)),
        "census_projects_without_in_scope_candidates": len(set(census) - set(grouped)),
        "candidate_records_outside_census": len(excluded),
        "excluded_project_ids": sorted(set(grouped) - set(census)),
        "candidate_only_project_ids": [row["project_id"] for row in by_project
                                       if row["candidate_only_without_selected_resource"]],
        "formal_mcda_eligible_at_freeze": len(formal),
        "use": manifest["use"], "fields": list(CORE_FIELDS), "arms": metrics, **deltas,
        "input_sha256": {
            "census": filehash(census_path), "comparison_census": filehash(comparison),
            "candidates": filehash(pilot / "candidates.jsonl"), "baseline_decisions": filehash(pilot / "decisions.jsonl"),
            "overlay": filehash(overlay_path) if overlay_path else None,
            "formal_c1_release": filehash(release / "formal_c1_release.json"),
            "field_status": filehash(release / "field_status.csv"),
            "census_selection": filehash(release / "census_selection.csv"),
            "census_identity_roles": filehash(release / "census_identity_roles.csv"),
            "public_resource_observations": filehash(release / "resource_statement_observations.csv"),
        },
    }


def write_outputs(output, projects, excluded, summary):
    output.mkdir(parents=True, exist_ok=True)
    with (output / "project_scope.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(projects[0]), lineterminator="\n")
        writer.writeheader()
        for row in projects:
            writer.writerow({k: json.dumps(v, ensure_ascii=False, sort_keys=True) if isinstance(v, (list, dict))
                             else v for k, v in row.items()})
    jsonl(output / "excluded_project_candidates.jsonl", excluded)
    report(output / "portfolio_summary.json", summary)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release", type=Path, default=RELEASE)
    parser.add_argument("--pilot", type=Path, default=PILOT)
    parser.add_argument("--comparison-census", type=Path, default=COMPARISON)
    parser.add_argument("--overlay", type=Path)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    write_outputs(args.output, *observe(args.release, args.pilot, args.comparison_census, args.overlay))
