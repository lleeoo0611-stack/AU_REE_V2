"""Read-only, dated experiment inputs; separate training from formal MCDA releases.

Version 1 evaluates fixed-horizon binary events. Preference learning and survival
estimators require their own label contracts and are deliberately not inferred
from existing researcher-assumption rankings.
"""

import csv
import io
import json
import re
import shutil
import subprocess
import tempfile
from collections import Counter
from datetime import date
from pathlib import Path

from .experiment_data import load_dataset, validate_cases
from .store import canonical, digest, filehash


COHORTS = ("AU_REE", "GLOBAL_REE", "GLOBAL_REE_PLUS_OTHER")
MODES = ("new_project", "future_project", "leave_country")


def _day(value, name):
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValueError(name + " requires a complete ISO date")
    date.fromisoformat(value)
    return value


def _counts(rows):
    return {"rows": len(rows), "projects": len({r["project_id"] for r in rows}),
            "labels": dict(sorted(Counter(str(r.get("label")) for r in rows).items()))}


def _member(row, cohort, auxiliary):
    if cohort == "AU_REE":
        return row["country"] == "AUS" and row["commodity"] == "REE"
    if cohort == "GLOBAL_REE":
        return row["commodity"] == "REE"
    return row["commodity"] in {"REE", *auxiliary}


def make_split(cases, spec, evaluation_as_of, seed=0, auxiliary_commodities=()):
    """Freeze one target test panel before selecting any source-domain cohort.

    Group holdout identities are selected without labels. For a fixed-horizon
    task all evaluation windows must have matured, including early positives.
    Label availability is checked in addition to window maturity.
    """
    mode = spec.get("mode")
    if mode not in MODES:
        raise ValueError("Unsupported split mode: " + str(mode))
    split_id = spec.get("id")
    if not isinstance(split_id, str) or not split_id:
        raise ValueError("Every split needs an id")
    train_cutoff = _day(spec.get("train_cutoff"), "train_cutoff")
    test_start = _day(spec.get("test_start"), "test_start")
    test_end = _day(spec.get("test_end"), "test_end")
    _day(evaluation_as_of, "evaluation_as_of")
    if not train_cutoff < test_start <= test_end <= evaluation_as_of:
        raise ValueError("Require train_cutoff < test_start <= test_end <= evaluation_as_of")
    country = spec.get("target_country", "AUS")
    commodity = spec.get("target_commodity", "REE")
    if not isinstance(country, str) or not re.fullmatch(r"[A-Z]{3}", country):
        raise ValueError("target_country must be an ISO3 country code")
    if not isinstance(commodity, str) or not commodity:
        raise ValueError("target_commodity is required")
    ordered = sorted(cases, key=lambda r: r["case_id"])
    candidates = [r for r in ordered if r["country"] == country
                  and r["commodity"] == commodity and test_start <= r["as_of"] <= test_end]
    candidate_projects = sorted({r["project_id"] for r in candidates})
    explicit = spec.get("test_project_ids")
    if explicit is not None:
        if not isinstance(explicit, list) or not all(isinstance(p, str) for p in explicit):
            raise ValueError("test_project_ids must be a list of stable Project IDs")
        if len(explicit) != len(set(explicit)) or set(explicit) - set(candidate_projects):
            raise ValueError("Duplicate or unavailable test_project_ids")
        held = set(explicit)
    elif mode == "new_project":
        fraction = spec.get("holdout_fraction", .25)
        if isinstance(fraction, bool) or not isinstance(fraction, (int, float)) or not 0 < fraction <= 1:
            raise ValueError("holdout_fraction must be in (0,1]")
        ranked = sorted(candidate_projects, key=lambda p: (digest([seed, split_id, p]), p))
        n = max(1, round(len(ranked) * fraction)) if ranked else 0
        held = set(ranked[:n])
    else:
        held = set(candidate_projects)
    # The same Project must never supply historical training rows in a new-Project test.
    test_candidates = [r for r in candidates if r["project_id"] in held]
    test = []
    excluded = []
    for row in test_candidates:
        if row["horizon_end"] > evaluation_as_of:
            reason = "TEST_HORIZON_NOT_MATURE"
        elif row.get("label") not in (0, 1):
            reason = "TEST_LABEL_" + row.get("label_status", "UNKNOWN")
        elif not row.get("label_available_at") or row["label_available_at"] > evaluation_as_of:
            reason = "TEST_LABEL_NOT_YET_KNOWN"
        else:
            test.append(row)
            continue
        excluded.append({"case_id": row["case_id"], "role": "test", "reason": reason})
    train_pool = []
    for row in ordered:
        if row["as_of"] > train_cutoff:
            continue
        if mode == "new_project" and row["project_id"] in held:
            reason = "HELD_OUT_PROJECT"
        elif mode == "leave_country" and row["country"] == country:
            reason = "HELD_OUT_COUNTRY"
        elif row["horizon_end"] > train_cutoff:
            reason = "TRAIN_HORIZON_NOT_MATURE"
        elif row.get("label") not in (0, 1):
            reason = "TRAIN_LABEL_" + row.get("label_status", "UNKNOWN")
        elif not row.get("label_available_at") or row["label_available_at"] > train_cutoff:
            reason = "TRAIN_LABEL_NOT_YET_KNOWN"
        else:
            train_pool.append(row)
            continue
        excluded.append({"case_id": row["case_id"], "role": "train", "reason": reason})
    training = {name: [r for r in train_pool if _member(r, name, auxiliary_commodities)]
                for name in COHORTS}
    test_ids = [r["case_id"] for r in test]
    manifest = {"id": split_id, "mode": mode, "train_cutoff": train_cutoff,
                "test_start": test_start, "test_end": test_end,
                "target_country": country, "target_commodity": commodity,
                "held_out_project_ids": sorted(held),
                "candidate_test_case_ids": [r["case_id"] for r in test_candidates],
                "test_case_ids": test_ids, "test_panel_sha256": digest(test_ids),
                "test_counts": _counts(test),
                "test_label_coverage": len(test) / len(test_candidates) if test_candidates else None,
                "training": {name: {"case_ids": [r["case_id"] for r in rows],
                                     "counts": _counts(rows)} for name, rows in training.items()},
                "excluded": sorted(excluded, key=lambda r: (r["role"], r["case_id"]))}
    manifest["split_sha256"] = digest(manifest)
    return {"manifest": manifest, "test": test, "training": training}


def repository_readiness(root):
    """Audit named existing catalogues; never infer whole-database absence."""
    root = Path(root)
    report = {"scope": "NAMED_CATALOGUES_ONLY_NOT_ALL_DATABASE_EVIDENCE", "inputs": {},
              "required_before_real_training": [
                  "Verified Project-by-date feature exports with availability evidence",
                  "Dated target events plus explicit follow-up for negative labels",
                  "Source-supported country and commodity metadata",
                  "Versioned canonical identity mapping"]}
    for name, key in [("data/candidate_milestone_evidence.json", "candidate_milestones"),
                      ("data/study_cases.json", "study_cases")]:
        path = root / name
        if not path.is_file():
            report[key] = {"status": "NOT_AVAILABLE_IN_CHECKOUT"}
            continue
        report["inputs"][name] = filehash(path)
        payload = json.loads(path.read_text(encoding="utf-8"))
        rows = payload if isinstance(payload, list) else payload.get("events", payload.get("cases", []))
        if key == "candidate_milestones":
            report[key] = {"records": len(rows),
                           "projects": len({r.get("project_id") for r in rows if r.get("project_id")}),
                           "event_types": dict(sorted(Counter(r.get("event_type", "UNKNOWN") for r in rows).items())),
                           "nonempty_event_dates": sum(bool(r.get("event_date")) for r in rows),
                           "complete_day_event_dates": sum(bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(r.get("event_date", "")))) for r in rows)}
        else:
            report[key] = {"records": len(rows), "operating_outcomes_inferred": False}
    research = root / "config/research.json"
    if research.is_file():
        report["inputs"]["config/research.json"] = filehash(research)
        config = json.loads(research.read_text(encoding="utf-8"))
        report["weight_status"] = config.get("weight_status")
        report["T1_interpretation"] = next((c.get("interpretation") for c in config.get("criteria", []) if c.get("code") == "T1"), None)
    return report


def _code_contract(root):
    package = Path(__file__).parent
    # Include the shared scoring/store implementation, even when executed from a checkout.
    paths = [package / name for name in ("experiments.py", "experiment_data.py",
             "experiment_models.py", "mcda.py", "store.py", "evidence_model.py")]
    code = {p.name: filehash(p) for p in paths}
    try:
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root,
                                         text=True, stderr=subprocess.DEVNULL).strip()
    except (OSError, subprocess.CalledProcessError):
        commit = "UNCOMMITTED"
    return {"commit": commit, "files": code, "content_sha256": digest(code)}


def _mcda_settings(root, config, features):
    settings = config.get("mcda_baseline", {})
    path = Path(settings.get("research_config", "config/research.json"))
    path = path if path.is_absolute() else root / path
    research = json.loads(path.read_text(encoding="utf-8"))
    criteria = {c["code"]: c for c in research["criteria"]}
    if any(f not in criteria for f in features):
        raise ValueError("FIXED_MCDA_REQUIRES_EXISTING_CRITERIA")
    domains = [criteria[f]["domain"] for f in features]
    # Do not silently redistribute a domain weight across multiple new criteria.
    if len(domains) != len(set(domains)) or set(domains) != set(research["scenarios"][settings.get("scenario", "development_assumption")]):
        raise ValueError("FIXED_MCDA_REQUIRES_ONE_EXISTING_CRITERION_PER_DOMAIN")
    weights = research["scenarios"][settings.get("scenario", "development_assumption")]
    return {f: criteria[f] for f in features}, {f: weights[criteria[f]["domain"]] for f in features}, filehash(path)


def _outcome_mcda_settings(root, config, features):
    """Frozen utility definitions; learned coefficients never edit research weights."""
    settings = config.get("mcda_baseline", {})
    path = Path(settings.get("research_config", "config/research.json"))
    path = path if path.is_absolute() else root / path
    research = json.loads(path.read_text(encoding="utf-8"))
    criteria = {c["code"]: c for c in research["criteria"]}
    additional = config.get("additional_utility_criteria", {})
    if not isinstance(additional, dict) or set(additional) & set(criteria):
        raise ValueError("Experimental utility criteria must be a mapping without existing criterion overrides")
    if any(not isinstance(value, dict) or not isinstance(value.get("unit"), str) or not value["unit"]
           for value in additional.values()):
        raise ValueError("Experimental utility criteria require explicit scoring definitions and units")
    criteria.update(additional)
    if any(f not in criteria for f in features):
        raise ValueError("OUTCOME_MCDA_REQUIRES_REGISTERED_UTILITY_CRITERIA")
    return {f: criteria[f] for f in features}, filehash(path)


def _publish(out, report, predictions):
    """Write an immutable result directory; exact repeat is allowed."""
    out = Path(out).resolve()
    fields = ["split_id", "cohort", "feature_set", "model", "case_id", "project_id",
              "label", "kind", "method", "probability", "utility_score", "score_lower", "score_upper", "rank_best", "rank_worst"]
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(predictions)
    csv_text = stream.getvalue()
    import hashlib
    report["predictions_sha256"] = hashlib.sha256(csv_text.encode()).hexdigest()
    text = canonical(report) + "\n"
    artifacts = {"experiment_report.json": text, "predictions.csv": csv_text}
    if out.exists():
        if not out.is_dir() or set(p.name for p in out.iterdir()) != set(artifacts):
            raise ValueError("Experiment output must be new or an identical previous experiment directory")
        if any((out / name).read_text(encoding="utf-8") != content for name, content in artifacts.items()):
            raise ValueError("EXPERIMENT_OUTPUT_IMMUTABLE: select a new output directory")
        return
    out.parent.mkdir(parents=True, exist_ok=True)
    temp = Path(tempfile.mkdtemp(prefix="experiment-", dir=out.parent))
    try:
        for name, content in artifacts.items():
            (temp / name).write_text(content, encoding="utf-8")
        temp.rename(out)
    finally:
        if temp.exists():
            shutil.rmtree(temp)


def run_experiment(root, config_path, out=None, dry_run=False):
    """Run a frozen event experiment or return a concrete readiness block."""
    root = Path(root).resolve()
    config_path = Path(config_path)
    config_path = config_path if config_path.is_absolute() else root / config_path
    config = json.loads(config_path.read_text(encoding="utf-8"))
    if config.get("schema_version") != "experiment-config-v1":
        raise ValueError("Unsupported experiment config schema")
    if config.get("task") != "event_prediction":
        raise ValueError("Version 1 implements event_prediction only; no MCDA ranks are inferred as outcome labels")
    seed = config.get("seed", 0)
    if type(seed) is not int or not 0 <= seed < 2**32:
        raise ValueError("seed must be an integer in [0, 2**32)")
    evaluation = _day(config.get("evaluation_as_of"), "evaluation_as_of")
    target = config.get("target", {})
    horizon = target.get("horizon_days")
    if type(horizon) is not int or horizon <= 0 or not isinstance(target.get("name"), str) or not target["name"]:
        raise ValueError("target requires name and positive horizon_days")
    sets = config.get("feature_sets", {})
    if not sets or any(not isinstance(fs, list) or not fs or not all(isinstance(f, str) and f for f in fs) or len(fs) != len(set(fs)) for fs in sets.values()):
        raise ValueError("feature_sets require nonempty unique feature names")
    cohort_sets = config.get("cohort_feature_sets", {})
    if (not isinstance(cohort_sets, dict) or set(cohort_sets) - set(COHORTS)
            or any(not isinstance(names, list) or not all(isinstance(n, str) for n in names)
                   or len(names) != len(set(names)) or set(names) - set(sets)
                   for names in cohort_sets.values())):
        raise ValueError("cohort_feature_sets must name configured feature sets for known cohorts")
    features = sorted(set(f for fs in sets.values() for f in fs))
    specs = config.get("splits", [])
    if not specs or len({s.get("id") for s in specs}) != len(specs):
        raise ValueError("splits require unique ids")
    models = config.get("models", ["prior", "logistic"])
    if not isinstance(models, list) or not models or len(models) != len(set(models)) or set(models) - {"prior", "logistic", "fixed_mcda", "outcome_mcda"}:
        raise ValueError("Supported models: prior, logistic, fixed_mcda, outcome_mcda")
    auxiliary = config.get("auxiliary_commodities", [])
    if not isinstance(auxiliary, list) or not all(isinstance(c, str) and c and c != "REE" for c in auxiliary):
        raise ValueError("auxiliary_commodities must list explicit non-REE commodity groups")
    report = {"schema_version": "experiment-report-v1", "task": config["task"],
              "status": "BLOCKED", "config": config, "config_sha256": filehash(config_path),
              "code": _code_contract(root), "seed": seed, "dry_run": dry_run,
              "research_status": "EXPERIMENTAL_NOT_FORMAL_MCDA_RELEASE",
              "limitations": ["Fixed hyperparameters; no tuning or model selection on the test set",
                              "Binary complete-horizon analysis; censored cases remain unlabelled",
                              "Outcome-fitted MCDA coefficients are predictive associations, not elicited stakeholder preferences or causal effects",
                              "No expert-preference learner, survival estimator, NLP extractor or automatic historical source reconstruction",
                              "Global pooling is a comparison baseline, not a validated domain-adaptation method"],
              "readiness": repository_readiness(root), "splits": [], "variants": []}
    dataset_path = Path(config.get("dataset", "data/experiments/project_time_cases.json"))
    dataset_path = dataset_path if dataset_path.is_absolute() else root / dataset_path
    predictions = []
    if not dataset_path.is_file():
        report["block_reason"] = "VERIFIED_PROJECT_TIME_DATASET_REQUIRED"
    else:
        dataset = load_dataset(dataset_path)
        checked = validate_cases(dataset, target["name"], horizon, evaluation, features)
        report.update(dataset_sha256=filehash(dataset_path),
                      identity_map_sha256=dataset["identity_map_sha256"],
                      dataset_validation=checked["summary"], exclusions=checked["exclusions"],
                      synthetic=dataset["synthetic"])
        if dataset["synthetic"]:
            report["research_status"] = "SYNTHETIC_VALIDATION_ONLY"
        success = 0
        blocked = 0
        for spec in specs:
            split = make_split(checked["cases"], spec, evaluation, seed, auxiliary)
            report["splits"].append(split["manifest"])
            for cohort, train in split["training"].items():
                test = split["test"]
                for set_name, selected in sorted(sets.items()):
                    for model in models:
                        entry = {"split_id": spec["id"], "cohort": cohort, "feature_set": set_name,
                                 "model_name": model, "test_panel_sha256": split["manifest"]["test_panel_sha256"]}
                        try:
                            if cohort in cohort_sets and set_name not in cohort_sets[cohort]:
                                raise ValueError("FEATURE_SET_NOT_APPROVED_FOR_COHORT")
                            if not test:
                                raise ValueError("NO_LABELLED_MATURE_TEST_CASES")
                            if model != "fixed_mcda" and not train:
                                raise ValueError("NO_LABELLED_MATURE_TRAIN_CASES")
                            if model in {"logistic", "outcome_mcda"} and len({r["label"] for r in train}) < 2:
                                raise ValueError("TRAINING_REQUIRES_BOTH_EVENT_CLASSES")
                            criteria = weights = None
                            if model == "fixed_mcda":
                                criteria, weights, sha = _mcda_settings(root, config, selected)
                                entry["research_config_sha256"] = sha
                            elif model == "outcome_mcda":
                                criteria, sha = _outcome_mcda_settings(root, config, selected)
                                entry["research_config_sha256"] = sha
                            if model in {"fixed_mcda", "outcome_mcda"}:
                                for row in (train + test if model == "outcome_mcda" else test):
                                    for feature in selected:
                                        if row["features"].get(feature) is not None and row["lineage"][feature]["unit"] != criteria[feature]["unit"]:
                                            raise ValueError(model.upper() + "_UNIT_MISMATCH: " + feature)
                            if dry_run:
                                entry.update(status="PLANNED", train_counts=_counts(train), test_counts=_counts(test))
                            else:
                                from .experiment_models import fit_predict
                                result = fit_predict(train, test, selected, model, seed, criteria=criteria, weights=weights)
                                entry.update(status="COMPLETED", metrics=result["metrics"], fitted_model=result["model"])
                                labels = {r["case_id"]: r["label"] for r in test}
                                for pred in result["predictions"]:
                                    base = {"split_id": spec["id"], "cohort": cohort, "feature_set": set_name,
                                            "model": model, "case_id": pred["case_id"], "project_id": pred["project_id"],
                                            "label": labels[pred["case_id"]], "kind": pred["kind"]}
                                    if pred["kind"] == "probability":
                                        predictions.append({**base, "probability": pred["prediction"],
                                                            "utility_score": pred.get("utility_score")})
                                    else:
                                        for method, bounds in sorted(pred["prediction"].items()):
                                            predictions.append({**base, "method": method, **bounds})
                            success += 1
                        except (ValueError, ImportError) as exc:
                            entry.update(status="BLOCKED", reason=str(exc))
                            blocked += 1
                        report["variants"].append(entry)
        report["completed_or_planned_variants"] = success
        report["blocked_variants"] = blocked
        report["status"] = ("PLANNED" if dry_run else "COMPLETED") if success and not blocked else (
            "PARTIAL" if success else "BLOCKED")
    if not dry_run:
        if not out:
            raise ValueError("experiment requires --out unless --dry-run")
        _publish(out, report, predictions)
    return report
