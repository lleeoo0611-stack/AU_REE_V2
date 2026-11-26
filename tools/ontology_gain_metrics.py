"""Score paired decisions after source review. Labels are never used by the comparators."""
import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

from tools.verify_ontology_gain_review import diagnostic_packet

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results/ontology-gain-20261126"
ARMS = ("A0", "B0", "A1", "B1")
CONTRASTS = (("A0", "B0"), ("A0", "A1"), ("B0", "B1"), ("A1", "B1"), ("A0", "B1"))
LABELS = {"SUPPORTED", "INCOMPATIBLE", "INSUFFICIENT", "NOT_REVIEWED"}
NO_VERDICT = {"NOT_EVALUABLE", "NOT_IMPLEMENTED", "ERROR"}
STATES = {"ACCEPT", "INCOMPATIBLE", "INSUFFICIENT", "BLOCKED", *NO_VERDICT}


def load_rows(path):
    result = {}
    with path.open(encoding="utf-8-sig") as stream:
        for line in stream:
            row = json.loads(line)
            key = row["candidate_id"]
            if key in result:
                raise ValueError(f"Duplicate candidate in {path}: {key}")
            result[key] = row
    return result


def rate(n, d):
    return {"numerator": n, "denominator": d, "rate": n / d if d else None}


def consolidate_source_groups(cases, references):
    """Merge independently reviewed repetitions with the frozen source-cell identities."""
    parent = {}

    def root(key):
        parent.setdefault(key, key)
        while parent[key] != key:
            parent[key] = parent[parent[key]]
            key = parent[key]
        return key

    for row in cases:
        key = row["candidate_id"]
        native = root("frozen:" + row["independent_observation_id"])
        group = references.get(key, {}).get("reviewed_evidence_group_id")
        if group:
            reviewed = root("review:" + row["use_id"] + ":" + group)
            if reviewed != native:
                parent[reviewed] = native
    for row in cases:
        row["independent_observation_id"] = root("frozen:" + row["independent_observation_id"])


def grouped_primary(cases):
    groups = defaultdict(list)
    for r in cases:
        groups[r["independent_observation_id"], r["use_id"]].append(r)
    records = []
    for group in groups.values():
        refs = {r["reference"] for r in group}
        if len(refs) > 1:
            raise ValueError("Different adjudications on a deduplicated study observation")
        record = {"reference": next(iter(refs))}
        for arm in ARMS:
            states = {r[arm] for r in group}
            record[arm] = "ACCEPT" if "ACCEPT" in states else "NO_ACCEPTANCE"
        records.append(record)
    return records


def arm_metrics(cases, arm):
    accepted = [r for r in cases if r[arm] == "ACCEPT"]
    accepted_by_label = Counter(r["reference"] for r in accepted)
    labels = Counter(r["reference"] for r in cases)
    good = accepted_by_label["SUPPORTED"]
    bad = accepted_by_label["INCOMPATIBLE"]
    insufficient = accepted_by_label["INSUFFICIENT"]
    return {
        "cases": len(cases), "accepted": len(accepted), "accepted_by_label": dict(accepted_by_label),
        "decisions": dict(Counter(r[arm] for r in cases)), "reference_labels": dict(labels),
        "precision_on_determinate_labels": rate(good, good + bad),
        "supported_share_of_reviewed_admissions": rate(good, good + bad + insufficient),
        "recall_on_supported_labels": rate(good, labels["SUPPORTED"]),
        "insufficient_evidence_share": rate(labels["INSUFFICIENT"], len(cases)),
        "unreviewed_share": rate(labels["NOT_REVIEWED"], len(cases)),
    }


def delta(cases, first, second):
    comparable = [r for r in cases if r[first] not in NO_VERDICT and r[second] not in NO_VERDICT]
    gains = [r for r in comparable if r[first] != "ACCEPT" and r[second] == "ACCEPT"]
    losses = [r for r in comparable if r[first] == "ACCEPT" and r[second] != "ACCEPT"]
    supported = [r for r in gains if r["reference"] == "SUPPORTED"]
    def observation_use(row):
        return row["independent_observation_id"], row["use_id"]
    already_used = {observation_use(r) for r in cases if r[first] == "ACCEPT"}
    newly_used = [r for r in supported if observation_use(r) not in already_used]
    after = {observation_use(r) for r in cases if r[second] == "ACCEPT"}
    # This use fixes one selected resource statement and scalar per project/column.
    # A second rendering of that scalar cannot create another use for the Project.
    before_fields = {(r["project_id"], r.get("target_column"), r["use_id"]) for r in cases if r[first] == "ACCEPT"}
    new_fields = {(r["project_id"], r.get("target_column"), r["use_id"]) for r in supported} - before_fields
    result = {"paired": len(comparable), "unevaluable_or_unimplemented": len(cases) - len(comparable),
              "added": len(gains), "removed": len(losses)}
    for key, group in (("added_by_reference", gains), ("removed_by_reference", losses)):
        counts = Counter(r["reference"] for r in group)
        result[key] = {label: counts[label] for label in sorted(LABELS)}
    return {**result, "newly_supported_record_ids": [r["candidate_id"] for r in supported],
            "new_supported_observations": len({r["independent_observation_id"] for r in newly_used}),
            "new_supported_observation_uses": len({observation_use(r) for r in newly_used}),
            "new_supported_records_already_represented": sum(observation_use(r) in already_used for r in supported),
            "independent_accepted_uses_before": len(already_used), "independent_accepted_uses_after": len(after),
            "distinct_uses_with_gains": sorted({r["use_id"] for r in newly_used}),
            "new_selected_project_fields": [list(key) for key in sorted(new_fields)],
            "projects_with_supported_gains": sorted({r["project_id"] for r in newly_used}),
            "ids_added": [r["candidate_id"] for r in gains], "ids_removed": [r["candidate_id"] for r in losses]}


def evaluate(inventory, decisions, sample, primary, extra):
    if not inventory or set(inventory) != set(decisions):
        raise ValueError("Every arm needs the complete frozen population")
    if set(sample) != set(primary) or not set(primary) <= set(inventory):
        raise ValueError("Primary references must cover exactly the predeclared sample")
    if set(extra) & set(primary) or not set(extra) <= set(inventory):
        raise ValueError("Disagreement reviews must be disjoint from the primary sample")
    labels = {**primary, **extra}
    strata = defaultdict(list)
    cases, pending = [], []
    for key, row in inventory.items():
        result = decisions[key]
        if result["observation_id"] != row["observation_id"] or result["project_id"] != row["project_id"] or result["use_id"] != row["use_id"]:
            raise ValueError(f"Evidence/unit identity changed in decisions: {key}")
        label = labels.get(key, {}).get("verdict", "NOT_REVIEWED")
        states = {arm: result[arm]["status"] for arm in ARMS}
        if label not in LABELS or not set(states.values()) <= STATES:
            raise ValueError(f"Unknown verdict or decision for {key}")
        if key in labels and labels[key]["source_sha256"] != row["source_sha256"]:
            raise ValueError(f"Reference points at a different document: {key}")
        case = {k: result[k] for k in ("candidate_id", "project_id", "observation_id", "use_id")}
        case.update(states, reference=label, independent_observation_id=row["independent_observation_id"],
                    target_column=row["target_column"], split=row["split"])
        cases.append(case)
        if key in sample:
            strata[sample[key]["stratum"]].append(case)
        if label in {"INSUFFICIENT", "NOT_REVIEWED"}:
            pending.append(key)
    consolidate_source_groups(cases, labels)
    primary_cases = [r for r in cases if r["candidate_id"] in primary]
    unique_reviewed = grouped_primary(primary_cases)
    return {
        "review_status": "PROVISIONAL_SOURCE_REVIEW_NO_INDEPENDENT_HUMAN",
        "unit": "one frozen candidate observation x declared use",
        "population": len(cases), "independent_population_uses": len({(r["independent_observation_id"], r["use_id"]) for r in cases}),
        "primary_sample": len(primary), "additional_disagreement_reviews": len(extra),
        "primary_summary": {a: arm_metrics(primary_cases, a) for a in ARMS},
        "primary_independent_observations": {a: arm_metrics(unique_reviewed, a) for a in ARMS},
        "primary_by_stratum": {s: {a: arm_metrics(rs, a) for a in ARMS} for s, rs in sorted(strata.items())},
        "aggregation": "Raw sample (micro) and stratum counts; no population precision or recall estimated.",
        "full_decision_counts": {a: dict(Counter(r[a] for r in cases)) for a in ARMS},
        "full_review_counts": dict(Counter(r["reference"] for r in cases)),
        "paired_contrasts_using_all_available_reviews": {
            f"{a}_to_{b}": delta(cases, a, b) for a, b in CONTRASTS},
        "overall_change_by_split": {
            s: delta([r for r in cases if r["split"] == s], "A0", "B1")
            for s in sorted({r["split"] for r in cases})},
        "ids_needing_evidence_or_review": pending,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, default=RESULTS)
    parser.add_argument("--review-dir", type=Path, help="Directory containing sealed source annotations")
    parser.add_argument("--additional-review", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    root = args.results
    reference = args.review_dir or root
    inputs = [load_rows(root / name) for name in ("candidates.jsonl", "decisions.jsonl", "review_sample.jsonl")]
    inputs.append(load_rows(reference / "source_review_primary.jsonl"))
    default_extra = reference / "source_review_additional.jsonl"
    extra_file = args.additional_review or default_extra
    additional = load_rows(extra_file) if args.additional_review or extra_file.exists() else {}
    acceptance_differences = set(json.loads((root / "disagreement_ids.json").read_bytes()))
    if set(additional) != acceptance_differences - set(inputs[3]):
        raise ValueError("Supplemental admission review does not cover the remaining acceptance disagreements")
    diagnostic_packet(root)
    dispositions = load_rows(reference / "source_review_dispositions.jsonl")
    if set(dispositions) != set(load_rows(root / "review_dispositions.jsonl")):
        raise ValueError("Diagnostic review does not match its separate packet")
    if set(dispositions) & set(additional):
        raise ValueError("Duplicate supplemental review")
    additional.update(dispositions)
    report = evaluate(*inputs, additional)
    report["additional_review_types"] = {"acceptance": len(acceptance_differences - set(inputs[3])),
                                         "nonadmission_status": len(dispositions)}
    report["diagnostic_review_by_reference"] = dict(Counter(r["verdict"] for r in dispositions.values()))
    certificate = ROOT / "results/ree-project-census/gap173-20261122/formal_c1_release.json"
    gates = json.loads(certificate.read_bytes())
    gains = report["paired_contrasts_using_all_available_reviews"]["A0_to_B1"]
    report["formal_mcda"] = {
        "release": certificate.relative_to(ROOT).as_posix(), "gates_checked": gates["gates_checked"],
        "eligible_at_freeze": gates["formally_releasable"],
        "gaining_projects_already_formally_releasable": sorted(
            set(gains["projects_with_supported_gains"]) & set(gates["formally_releasable"])),
        "effect": "Research eligibility only; all six existing gates and official outputs are read-only."}
    (args.output or root / "metrics.json").write_text(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2)
                                                      + "\n", encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
