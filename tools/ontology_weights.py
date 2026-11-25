"""Research-only sensitivity of SAW weights on released Phase 22 scores.

Run from any checkout: python tools/ontology_weights.py
The source of performance scores is the published, evidence-linked MCDA panel.
No extraction, database access or MCDA import is performed by this audit.
"""
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
from statistics import correlation, stdev


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RELEASE = ROOT / "results/ree-project-census/nlp-retrieval-20261126"
DEFAULT_OUTPUT = ROOT / "results/ontology-comparability-20261126"
PANELS = {
    "official_wa_resource_screen": "balanced_resource_assumption",
    "issuer_resource_infrastructure": "development_assumption",
}
METHODS = ("equal_within_domain", "critic", "entropy")


def read_csv(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def write_csv(path, rows):
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=rows[0].keys(), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def fit_group(matrix, codes, method):
    """Fit to training projects only. Inputs already run from worst to best."""
    if method not in METHODS:
        raise ValueError(f"unknown weight method {method}")
    if method == "equal_within_domain":
        return {c: 1 / len(codes) for c in codes}
    if len(matrix) < 3:
        raise ValueError("insufficient projects to fit empirical weights")
    columns = {}
    for c in codes:
        x = [row[c] for row in matrix]
        lo, hi = min(x), max(x)
        if hi > lo:
            columns[c] = [(v - lo) / (hi - lo) for v in x]
    if not columns:
        raise ValueError("no varying criterion in domain")
    if len(columns) == 1:
        return {c: float(c in columns) for c in codes}
    strengths = {}
    for c, x in columns.items():
        if method == "critic":
            conflict = sum(1 - max(-1, min(1, correlation(x, y)))
                           for other, y in columns.items() if other != c)
            strengths[c] = stdev(x) * conflict
        else:
            total = sum(x)
            probabilities = [v / total for v in x if v > 0]
            strengths[c] = 1 + sum(p * math.log(p) for p in probabilities) / math.log(len(x))
    total = sum(strengths.values())
    if total < 1e-12:
        raise ValueError("no estimable contrast among criteria")
    return {c: strengths.get(c, 0) / total for c in codes}


def fit(matrix, domains, budgets, method):
    if method == "flat_critic":
        return fit_group(matrix, [c for codes in domains.values() for c in codes], "critic")
    weights = {}
    for domain, codes in domains.items():
        within = fit_group(matrix, codes, method)
        weights.update({c: budgets[domain] * w for c, w in within.items()})
    return weights


def score_and_rank(matrix, weights):
    scores = {p: sum(w * x[c] for c, w in weights.items()) for p, x in matrix.items()}
    ordered = sorted(scores, key=scores.get, reverse=True)
    ranks = {}
    start = 0
    while start < len(ordered):
        end = start + 1
        while end < len(ordered) and scores[ordered[end]] == scores[ordered[start]]:
            end += 1
        for p in ordered[start:end]:
            ranks[p] = (start + 1 + end) / 2
        start = end
    return scores, ranks


def winners(ranks):
    return sorted(p for p in ranks if ranks[p] == min(ranks.values()))


def panel_data(panel, scenario, config, lineage, release):
    ranking = release / "MCDA" / panel / "ranking.csv"
    official = {}
    for row in read_csv(ranking):
        if row["scenario"] == scenario:
            p = row["project_id"]
            if p in official:
                raise ValueError(f"duplicate published alternative {p}")
            official[p] = row
    codes = (config["screen_panels"] if panel in config["screen_panels"]
             else config["panels"])[panel]
    criteria = {row["code"]: row for row in config["criteria"] if row["code"] in codes}
    if set(criteria) != set(codes):
        raise ValueError("criterion definition missing")
    domains = {}
    for code in sorted(codes):
        domains.setdefault(criteria[code]["domain"], []).append(code)
    if panel in config["screen_panels"]:
        if len(domains) != 1:
            raise ValueError("resource screen must contain only Resource criteria")
        budgets = {next(iter(domains)): 1.0}
    else:
        scenario_weights = config["scenarios"][scenario]
        total = sum(scenario_weights[d] for d in domains)
        budgets = {d: scenario_weights[d] / total for d in domains}
    matrix = {}
    for row in lineage:
        if row["panel"] != panel:
            continue
        project, code = row["project_id"], row["criterion"]
        x = matrix.setdefault(project, {})
        if code in x or code not in codes or not json.loads(row["evidence"]):
            raise ValueError(f"duplicate, unknown or unsourced criterion {panel} {project} {code}")
        value = float(row["score"])
        if not math.isfinite(value) or not 0 <= value <= 1:
            raise ValueError(f"invalid directed utility {row['score']}")
        x[code] = value
    if not official or set(matrix) != set(official) or any(set(row) != set(codes) for row in matrix.values()):
        raise ValueError(f"published panel membership or criterion coverage mismatch: {panel}")
    return matrix, domains, budgets, criteria, official, ranking


def audit(release, config_path, output):
    config = json.loads(config_path.read_text(encoding="utf-8"))
    lineage_path = release / "mcda_criterion_lineage.csv"
    lineage = read_csv(lineage_path)
    inputs = [config_path, lineage_path]
    panels = {}
    rank_rows, loo_rows = [], []
    for panel, scenario in PANELS.items():
        matrix, domains, budgets, criteria, official, path = panel_data(
            panel, scenario, config, lineage, release)
        inputs.append(path)
        names = {p: x["project_name"] for p, x in official.items()}
        official_ranks = {p: float(x["saw_rank"]) for p, x in official.items()}
        results = {}
        methods = (*METHODS, "flat_critic") if len(domains) > 1 else METHODS
        for method in methods:
            weights = fit(list(matrix.values()), domains, budgets, method)
            scores, ranks = score_and_rank(matrix, weights)
            if method == "equal_within_domain" and (ranks != official_ranks or any(
                abs(v - float(official[p]["saw"])) > 1e-12 for p, v in scores.items()
            )):
                raise ValueError(f"equal weighting does not reproduce released SAW: {panel}")
            for p in matrix:
                rank_rows.append(dict(panel=panel, scenario=scenario, method=method, project_id=p,
                                      project_name=names[p], saw=scores[p], rank=ranks[p],
                                      published_saw=official[p]["saw"], published_rank=official_ranks[p]))
            max_weight_shift, max_rank_shift, changed_top = 0.0, 0.0, 0
            failed = []
            for held in matrix:
                training = [x for p, x in matrix.items() if p != held]
                try:
                    fold_weights = fit(training, domains, budgets, method)
                except ValueError as exc:
                    failed.append({"held": held, "reason": str(exc)})
                    continue
                _, fold_ranks = score_and_rank(matrix, fold_weights)
                shift = max(abs(weights[c] - fold_weights[c]) for c in weights)
                rank_shift = max(abs(ranks[p] - fold_ranks[p]) for p in matrix)
                max_weight_shift = max(max_weight_shift, shift)
                max_rank_shift = max(max_rank_shift, rank_shift)
                fold_top = winners(fold_ranks)
                changed_top += fold_top != winners(ranks)
                loo_rows.append(dict(panel=panel, method=method, held_project_id=held,
                                     weights=json.dumps(fold_weights, sort_keys=True),
                                     top_ids="|".join(fold_top), held_rank=fold_ranks[held],
                                     largest_weight_shift=shift, largest_rank_shift=rank_shift))
            results[method] = dict(weights=weights, top=[names[p] for p in winners(ranks)],
                                   ranks_changed_from_official=sum(ranks[p] != official_ranks[p] for p in ranks),
                                   greatest_shift_from_official=max(abs(ranks[p] - official_ranks[p]) for p in ranks),
                                   loo_valid=len(matrix) - len(failed), loo_failed=failed,
                                   loo_top_changes=changed_top, loo_max_weight_shift=max_weight_shift,
                                   loo_max_rank_shift=max_rank_shift)
        pairs = {}
        for i, c in enumerate(sorted(criteria)):
            for d in sorted(criteria)[i + 1:]:
                x, y = ([row[k] for row in matrix.values()] for k in (c, d))
                pairs[f"{c}/{d}"] = correlation(x, y) if min(x) < max(x) and min(y) < max(y) else None
        panels[panel] = dict(scenario=scenario, projects=len(matrix), domains=budgets,
                             criteria=criteria, pearson_correlations=pairs, results=results)
    hashes = {str(path.relative_to(ROOT).as_posix() if path.is_relative_to(ROOT) else path.name):
              hashlib.sha256(path.read_bytes()).hexdigest() for path in inputs}
    summary = dict(
        design="Hypothesis-generating, purposive panels; no released MCDA or Census writes.",
        performance="Same complete panel and published benefit utilities for SAW in all arms. No fill.",
        weighting=("Equal benchmark retains the published domain budgets. CRITIC and Shannon entropy "
                   "use within-domain sample min-max columns fitted to training projects only. "
                   "Flat CRITIC estimates weights jointly across all criteria and ignores domain budgets. "
                   "Empty empirical contrast abstains; a single-criterion domain retains its fixed budget."),
        sensitivity=("Omit one project to learn weights; score the full fixed cohort for comparable ranks. "
                     "This measures influence, not out-of-sample validity. Hierarchical domain budgets stay fixed."),
        limits=("WA screen has algebraically related inventory and grade. With two criteria, the CRITIC "
                "correlation term cancels in the ratio. For the infrastructure pilot n=6; four distances "
                "share regional factors; correlation is not semantic equivalence. Neither sample defines preferences."),
        input_sha256=hashes, panels=panels)
    output.mkdir(parents=True, exist_ok=True)
    write_csv(output / "weighting_ranks.csv", rank_rows)
    write_csv(output / "weighting_leave_one_out.csv", loo_rows)
    (output / "weighting_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release", type=Path, default=DEFAULT_RELEASE)
    parser.add_argument("--config", type=Path, default=ROOT / "config/research.json")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    audit(args.release, args.config, args.output)
