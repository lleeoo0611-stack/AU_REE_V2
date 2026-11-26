"""Four-arm, checksum-bound evaluation of the shadow observation pipeline."""

from collections import Counter
from csv import DictReader
from decimal import Decimal
from importlib.metadata import version
import json
from pathlib import Path
import re
from time import perf_counter

from .derived_cache import DEPENDENCIES, DerivedCache, atomic_json, downstream
from .observation_incremental import IncrementalObservations, load_reviews
from .observation_schema import AnalysisFeature, ValidatedObservation
from .observation_semantics import RESOURCE_PROFILE, RESOURCE_UNITS, ResourceContract
from .observation_shadow import (
    ARMS, BASELINE, PORTFOLIO, RELEASE, STUDY, by_id, comparison_sections, evaluate_captures,
    formal_projection, jsonl, observation_group, partition, read_jsonl, write,
)
from .semantic_technical import PROFILE as TECHNICAL_PROFILE, technical_audit
from .store import digest, filehash


FOUR_ARM_DEFINITIONS = {
    "E0V0": "Frozen legacy captures and complete legacy profile verdicts",
    "E1V0": "Bound-source captures and complete legacy profile verdicts",
    "E0V1": "Frozen legacy captures and integrated normalization, ontology and research assessment",
    "E1V1": "Bound-source captures and integrated normalization, ontology and research assessment",
}


def _checked(path, expected):
    if filehash(path) != expected:
        raise ValueError(f"Input differs from the frozen observation snapshot: {path.name}")
    return path


def _shadow_settings(root):
    study, prior, release = (root / name for name in (STUDY, BASELINE, RELEASE))
    receipt = json.loads((study / "verification.json").read_bytes())
    inventory = json.loads((prior / "inventory_manifest.json").read_bytes())
    gain = json.loads((prior / "verification.json").read_bytes())["byte_identical_replay_sha256"]
    overlay = json.loads((root / PORTFOLIO / "verification.json").read_bytes())["byte_identical_replay"]
    for name, sha in inventory["release_inputs_sha256"].items():
        _checked(release / name, sha)
    files = {
        "captures": _checked(study / "decisions.jsonl", receipt["byte_identical_shadow_replay"]["decisions.jsonl"]),
        "seeds": _checked(prior / "candidates.jsonl", inventory["candidate_sha256"]),
        "holdout": _checked(study / "review_split.json", receipt["review_package_sha256"]["review_split.json"]),
        "reference": _checked(study / "review_reference_template.json",
                             receipt["review_package_sha256"]["review_reference_template.json"]),
        "review_pages": _checked(study / "review_pages.jsonl", receipt["review_package_sha256"]["review_pages.jsonl"]),
        "review_evaluation": _checked(study / "review_evaluation.json",
                                     receipt["review_package_sha256"]["review_evaluation.json"]),
        "legacy_decisions": _checked(prior / "decisions.jsonl", gain["decisions.jsonl"]),
        "portfolio": _checked(root / PORTFOLIO / "decisions_overlay.jsonl", overlay["decisions_overlay.jsonl"]),
        "profiles": root / "config/ontology/shadow_profiles_v1.json",
        "evidence_policy": root / "config/evidence_policy.json",
        "comparability_ontology": root / "config/ontology/comparability_v1.json",
        "portfolio_ontology": root / "config/ontology/resource_portfolio_v1.json",
        "observation_ontology": root / "config/ontology/observation_v1.json",
        "census": release / "REE project census.csv",
    }
    return release, files


def _resource_seeds(files, frozen):
    seeds = read_jsonl(files["seeds"])
    if {r["candidate_id"] for r in seeds} != {r["candidate_id"] for r in frozen
                                               if r["profile_id"] == RESOURCE_PROFILE}:
        raise ValueError("Resource captures and candidate frame do not reconcile")
    return seeds


def _typed_assessments(rows, metadata, pipeline, reviews, workspace=None):
    for row in rows:
        did = row["candidate_id"]
        journal = reviews.get(did, [])
        typed = {}
        for extraction, arm in (("e0", "E0V1"), ("e1", "E1V1")):
            capture = row[extraction]
            subject = f"{did}/{extraction}"
            # Attachment identity keeps alternate source representations distinct.
            projection = {**capture, "extraction_fingerprint": did}
            raw, raw_data = pipeline.project(subject, projection, metadata.get(did))
            normalized, normalized_data = pipeline.normalize(subject, raw)
            semantic, semantic_data = pipeline.assess(subject, raw, raw_data, normalized, normalized_data,
                                                       row[arm], capture["status"], journal)
            feature = None
            if normalized and semantic.evidence_status == "VERIFIED" and semantic.comparability == "COMPARABLE":
                validated = ValidatedObservation(normalized, semantic)
                feature = AnalysisFeature(validated, raw.variable, semantic.rule_version,
                                          normalized.value, normalized.unit)
            if semantic.evidence_status == "SOURCE_BLOCKED":
                pipeline.cache.record("assessment", subject, "SOURCE_BLOCKED", reason=semantic.reason)
            elif semantic.evidence_status == "CONFLICT":
                pipeline.cache.record("assessment", subject, "CONFLICT", reason=semantic.reason)
            elif semantic.comparability == "INSUFFICIENT_CONTEXT":
                pipeline.cache.record("assessment", subject, "INSUFFICIENT_CONTEXT", reason=semantic.reason,
                                      missing_context=list(semantic.missing_context))
            if workspace is not None and arm == "E1V1":
                workspace.append(raw, normalized=(normalized,) if normalized else (), assessments=(semantic,),
                                 features=(feature,) if feature else ())
            typed[arm] = {
                "raw": {**raw_data, "raw_id": raw.raw_id},
                "normalized": normalized_data, "assessment": semantic_data,
                "analysis_feature": {"name": feature.name, "definition_version": feature.definition_version,
                                     "value": str(feature.value), "unit": feature.unit} if feature else None,
            }
            if journal:
                typed[arm]["manual_decisions"] = journal
        row["integrated"] = typed


def _coverage(rows, frozen):
    previous = by_id(frozen)
    return {
        "retained_candidate_count": len(rows),
        "identical_e0_captures": sum(r["e0"] == previous[r["candidate_id"]]["e0"] for r in rows),
        "identical_e1_captures": sum(r["e1"] == previous[r["candidate_id"]]["e1"] for r in rows),
        "identical_profile_decisions": {
            arm: sum(r[arm] == previous[r["candidate_id"]][arm] for r in rows) for arm in ARMS
        },
    }


def _rate(numerator, denominator):
    return {"numerator": numerator, "denominator": denominator,
            "ratio": numerator / denominator if denominator else None}


def _source_bound(capture):
    return capture["status"] in {"EXTRACTED", "SOURCE_VERIFIED_CANDIDATE"}


def _complete_source_capture(row):
    typed = row["integrated"]["E1V1"]
    raw = typed["raw"]
    # This is a measurable profile readiness proxy, independent of unlabelled recall.
    return (_source_bound(row["e1"]) and raw["original_value"] is not None and raw["original_unit"] is not None
            and any(a["sha256"] and a["page"] and a["quote"] for a in raw["evidence_anchors"])
            and not typed["assessment"]["missing_context"])


def _value_groups(rows, arm):
    return {(observation_group(r, arm), Decimal(str(r[arm]["normalized"]["value"])),
             r[arm]["normalized"]["unit"])
            for r in rows if r[arm]["status"] == "ACCEPT" and r[arm]["normalized"] is not None}


def _quality(rows):
    """Count profile transitions separately from source-backed typed coverage."""
    result = {}
    for profile in (RESOURCE_PROFILE, TECHNICAL_PROFILE):
        subset = [r for r in rows if r["profile_id"] == profile]
        first, last = "E0V0", "E1V1"
        prior = {observation_group(r, first) for r in subset if r[first]["status"] == "ACCEPT"}
        after = {observation_group(r, last) for r in subset if r[last]["status"] == "ACCEPT"}
        established = {r["project_id"] for r in subset if r[first]["status"] == "ACCEPT"}
        comparable = {r["project_id"] for r in subset if r[last]["status"] == "ACCEPT"}
        evidence_additions = [r for r in subset if r[first]["status"] != "ACCEPT"
                             and r[last]["reason"] == "VERIFIED_SAME_SOURCE_CELL_CORROBORATION"]
        evidence_ids = {r["candidate_id"] for r in evidence_additions}
        new_context = set()
        for row in subset:
            if row["candidate_id"] in evidence_ids or row[last]["status"] != "ACCEPT":
                continue
            group = observation_group(row, last)
            if group not in prior or not _source_bound(row["e1"]):
                continue
            anchors = row["e1"]["anchors"]
            old_roles = {a.get("role") for a in row["e0"]["anchors"]}
            if any(a.get("role") in {"EXPLICIT_SAMPLE_TABLE_REFERENCE", "PROGRAM_LEACH_PROCEDURE",
                                     "ANALYTICAL_ENDPOINT"}
                   and a["role"] not in old_roles for a in anchors):
                new_context.add(group)
        applicable = [r for r in subset if r[last]["status"] != "NOT_APPLICABLE"]
        result[profile] = {
            "gain_by_evidence_type": {
                "new_comparable_observation_groups": len(after - prior),
                "new_distinct_values_in_new_groups": sum(group in after - prior
                                                         for group, *_ in _value_groups(subset, last)),
                "new_source_corroborating_records": len(evidence_additions),
                "existing_comparable_groups_with_new_source_context": len(new_context),
                "lost_legacy_comparable_observation_groups": len(prior - after),
                "new_projects_with_a_comparable_observation": len(comparable - established),
            },
            "source_bound_capture_on_applicable_candidates": _rate(
                sum(_source_bound(r["e1"]) for r in applicable), len(applicable)),
            "source_bound_token_unit_required_context_on_applicable_candidates": _rate(
                sum(_complete_source_capture(r) for r in applicable), len(applicable)),
            "typed_by_arm": {},
        }
        for arm in ("E0V1", "E1V1"):
            extraction = "e0" if arm == "E0V1" else "e1"
            typed = [r["integrated"][arm] for r in subset]
            pairable = [r for r in subset if (r[extraction]["native"] or {}).get("token") not in (None, "")
                        and (r[extraction]["native"] or {}).get("unit")]
            result[profile]["typed_by_arm"][arm] = {
                "normalizable_capture": _rate(sum(r["integrated"][arm]["normalized"] is not None for r in pairable),
                                              len(pairable)),
                "evidence_status": dict(Counter(t["assessment"]["evidence_status"] for t in typed)),
                "comparability": dict(Counter(t["assessment"]["comparability"] for t in typed)),
                "verified_comparable_normalized_records": sum(t["analysis_feature"] is not None for t in typed),
            }
    return result


def _typed_replay_counts(rows):
    """Count candidates, deduplicated observation groups and Projects for each outcome."""
    arm = "E1V1"
    counts = {}
    for profile in (RESOURCE_PROFILE, TECHNICAL_PROFILE):
        cohort = [row for row in rows if row["profile_id"] == profile]

        def total(selected):
            return {"candidates": len(selected),
                    "observation_groups": len({observation_group(row, arm) for row in selected}),
                    "projects": len({row["project_id"] for row in selected if row.get("project_id")})}

        dispositions = {"evidence_status": {}, "comparability": {}}
        for dimension, statuses in dispositions.items():
            for status in sorted({row["integrated"][arm]["assessment"][dimension] for row in cohort}):
                statuses[status] = total([row for row in cohort
                                          if row["integrated"][arm]["assessment"][dimension] == status])
        counts[profile] = {"evaluated": total(cohort), **dispositions,
                           "usable_under_shadow_profile": total([row for row in cohort
                                                                  if row["integrated"][arm]["analysis_feature"]])}
    return {"arm": arm, "formal_admissions_by_shadow": 0,
            "grouping": "A group with multiple source representations may occur in multiple outcome categories.",
            "profiles": counts}


def _review(files, rows):
    reference = json.loads(files["review_evaluation"].read_bytes())
    pages = read_jsonl(files["review_pages"])
    locations = {(r["source_sha256"], r["physical_page"]) for r in pages}
    return {
        "state": "AWAITING_INDEPENDENT_ANNOTATION",
        "document_families": len({r["group_id"] for r in pages}),
        "source_first_pages": len(pages),
        "source_first_pages_with_predictions": len({(r["source_sha256"], r["physical_page"]) for r in rows}
                                                  & locations),
        "pages_fully_annotated": reference["pages_fully_annotated"],
        "unseen_technical_source_available": reference["unseen_technical_sources"],
        "precision": None, "recall": None, "f1": None, "false_admissions": None, "false_exclusions": None,
        "complete_observation_accuracy": None,
    }


def _write_outputs(root, output, rows, relations, settings, study, files, frozen, capture_mode, engineering,
                   source_coverage, development_only, started, reviews):
    sections = comparison_sections(rows, settings)
    release_path = files["census"]
    with release_path.open(encoding="utf-8-sig", newline="") as stream:
        projects = {r["專案ID"] for r in DictReader(stream)}
    report = {
        "schema": "unified-observation-ablation-v1", "cutoff": study["cutoff"], "formal_effect": "SIDE_OUTPUT_ONLY",
        "capture_mode": capture_mode, "arm_definitions": FOUR_ARM_DEFINITIONS,
        "development_only": development_only, "original_source_coverage": source_coverage,
        "profile_count_definition": "Profile verdicts use the full legacy gate and its purpose constraints. "
                                    "Typed V1 results separately expose verification and comparability.",
        "fixed_census_project_count": len(projects), "comparison": sections,
        "frozen_capture_and_verdict_match": _coverage(rows, frozen), "quality": _quality(rows),
        "independent_review": _review(files, rows), "relationship_digest": digest(relations),
        "typed_replay_counts": _typed_replay_counts(rows),
        "technical_context": technical_audit([r["e0"] for r in rows if r["profile_id"] == TECHNICAL_PROFILE],
                                             [r["e1"] for r in rows if r["profile_id"] == TECHNICAL_PROFILE]),
        "input_sha256": {str(path.relative_to(root)) if path.is_relative_to(root) else name: filehash(path)
                         for name, path in sorted(files.items())},
        "code_sha256": {name: filehash(Path(__file__).with_name(name)) for name in (
            "observation_ablation.py", "observation_shadow.py", "observation_pipeline.py", "observation_schema.py",
            "observation_incremental.py", "numeric_evidence.py",
            "observation_semantics.py", "normalization.py", "ontology.py", "resource_use.py", "technical.py",
            "technical_tables.py", "semantic_resource.py", "semantic_technical.py", "document_processing.py", "nlp.py",
            "pdf_extract.py",
        )},
        "dependencies": {name: version(name) for name in ("PyMuPDF", "pypdf")},
        "canonical_payload_sha256": {"decisions": digest(rows), "relationship_candidates": digest(relations)},
    }
    if reviews:
        report["manual_review_sha256"] = digest(reviews)
    output.mkdir(parents=True, exist_ok=True)
    jsonl(output / "decisions.jsonl", rows)
    jsonl(output / "relationship_candidates.jsonl", relations)
    write(output / "comparison.json", json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    engineering["elapsed_seconds"] = round(perf_counter() - started, 6)
    try:
        import resource
        import sys

        max_rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        engineering["process_peak_rss_bytes"] = max_rss if sys.platform == "darwin" else max_rss * 1024
    except ImportError:
        pass
    write(output / "engineering.json", json.dumps(engineering, indent=2, sort_keys=True) + "\n")
    return {"status": "SHADOW_COMPLETE", "output": str(output), "candidates": len(rows),
            "capture_mode": capture_mode, "elapsed_seconds": engineering["elapsed_seconds"]}


def _original_coverage(assets, seeds, technical_old, frozen, rows, source_states):
    def file_available(sha):
        return (isinstance(sha, str) and re.fullmatch(r"[0-9a-f]{64}", sha)
                and ((assets / sha).is_file() or (assets / f"{sha}.pdf").is_file()))

    frozen_e1 = {r["candidate_id"]: r["e1"] for r in frozen}
    decisions = by_id(rows)
    eligible_resources = [r for r in seeds if type(r["physical_page"]) is int and not r["source_gates"]]
    eligible_technical = [r for r in technical_old.values() if r["native"]["quantity"] == "extraction_pct"]
    report = {}
    for profile, cohort in ((RESOURCE_PROFILE, eligible_resources), (TECHNICAL_PROFILE, eligible_technical)):
        present = [decisions[r["candidate_id"]] for r in cohort if file_available(r["source_sha256"])]
        missing = [decisions[r["candidate_id"]] for r in cohort if not file_available(r["source_sha256"])]
        present_identical = [r for r in present if r["e1"] == frozen_e1[r["candidate_id"]]]
        report[profile] = {
            "original_requery_candidates": len(cohort),
            "candidate_named_assets_present": len(present),
            "source_bound_captures": sum(_source_bound(r["e1"]) for r in present + missing),
            "present_asset_captures_matching_frozen": len(present_identical),
            "present_asset_acceptances_by_arm": {arm: sum(r[arm]["status"] == "ACCEPT" for r in present)
                                                 for arm in ARMS},
            "original_absent_legacy_acceptances_blocked_in_e1v1": sum(
                r["E0V0"]["status"] == "ACCEPT" and r["E1V1"]["status"] in {"BLOCKED", "SOURCE_BLOCKED"}
                for r in missing),
            "missing_source_sha256": sorted({r["source_sha256"] for r in missing}),
            "unavailable_source_reasons": {sha: source_states[sha] for sha in sorted({
                r["source_sha256"] for r in cohort if source_states[r["source_sha256"]] != "ORIGINAL_VERIFIED"
            })},
            "unavailable_candidate_ids": sorted(r["candidate_id"] for r in cohort
                                                if source_states[r["source_sha256"]] != "ORIGINAL_VERIFIED"),
        }
    return report


def _read_frame(root, development_only, review_path):
    release, files = _shadow_settings(root)
    study, settings, policy = (json.loads(files[k].read_bytes()) for k in ("holdout", "profiles", "evidence_policy"))
    frozen = read_jsonl(files["captures"])
    seeds = _resource_seeds(files, frozen)
    reviews = load_reviews(review_path, {r["candidate_id"] for r in frozen})
    if development_only:
        frozen = [r for r in frozen if partition(r, study) == "DEVELOPMENT_OR_REGRESSION"]
        seeds = [r for r in seeds if partition(r, study) == "DEVELOPMENT_OR_REGRESSION"]
    technical_old = {r["candidate_id"]: r["e0"] for r in frozen if r["profile_id"] == TECHNICAL_PROFILE}
    return release, files, study, settings, policy, frozen, seeds, technical_old, reviews


def _source_states(documents, seeds, technical):
    from .document_processing import DocumentUnavailable

    hashes = {r["source_sha256"] for r in seeds if type(r["physical_page"]) is int and not r["source_gates"]}
    hashes.update(r["source_sha256"] for r in technical.values() if r["native"]["quantity"] == "extraction_pct")
    states = {}
    for sha in sorted(hashes):
        try:
            documents.verify(sha)
        except DocumentUnavailable as exc:
            states[sha] = str(exc)
        else:
            states[sha] = "ORIGINAL_VERIFIED"
    return states


def _plan_inputs(files, pipeline, reviews, assets, development_only):
    module = Path(__file__).parent
    return {
        "pdf": {"originals": assets, "parser": filehash(module / "document_processing.py"),
                "parser_dependencies": [version("PyMuPDF"), version("pypdf")]},
        "extraction": {"candidate_seeds": filehash(files["seeds"]),
                       "capture_base": filehash(files["captures"]), "development_only": development_only,
                       "extractors": {name: filehash(module / name) for name in
                                      ("nlp.py", "semantic_resource.py", "semantic_technical.py", "technical_tables.py")}},
        "projection": {"projection_code": pipeline.projection_code},
        "normalization": {"conversion": filehash(module / "normalization.py"), "rules": pipeline.normalization_code,
                          "resource_units": RESOURCE_UNITS,
                          "conversion_vocabulary": {name: filehash(files[name]) for name in
                                                    ("comparability_ontology", "portfolio_ontology", "observation_ontology")}},
        "assessment": {"profiles": filehash(files["profiles"]), "evidence_policy": filehash(files["evidence_policy"]),
                       "old_decisions": filehash(files["legacy_decisions"]), "portfolio": filehash(files["portfolio"]),
                       "manual_decisions": {candidate: digest(records) for candidate, records in reviews.items()},
                       "assessment_code": pipeline.assessment_code},
    }


def _previous_plan(cache):
    if cache.directory is not None:
        try:
            value = json.loads((cache.directory / "latest-ablation.json").read_bytes())
            if isinstance(value, dict) and all(isinstance(item, dict) for item in value.values()):
                return value
        except (OSError, ValueError):
            pass
    return {}


def plan_replay(root, *, originals=None, development_only=False, cache=None, review_path=None):
    """Preview known dependency changes before building any artifact."""
    from .document_processing import PdfDocumentCache

    cache = cache if cache is not None else DerivedCache()
    _validate_paths(Path(root).resolve(), None, originals, cache, review_path)
    _, files, _, _, _, _, seeds, technical, reviews = _read_frame(Path(root), development_only, review_path)
    if originals is not None:
        if not Path(originals).is_dir():
            raise ValueError("Original source assets must be a directory")
        with PdfDocumentCache(originals) as documents:
            assets = _source_states(documents, seeds, technical)
    else:
        assets = None
    inputs = _plan_inputs(files, IncrementalObservations(root, cache), reviews, assets, development_only)
    previous = _previous_plan(cache)
    changes = {stage: sorted(key for key in values.keys() | previous.get(stage, {}).keys()
                             if previous.get(stage, {}).get(key) != values.get(key))
               for stage, values in inputs.items()}
    affected = downstream(stage for stage, keys in changes.items() if keys)
    states = {}
    for stage in DEPENDENCIES:
        if stage in {"ocr", "recognition", "bm25-index", "bm25-query"} or (
                stage in {"pdf", "extraction"} and originals is None):
            action = "INACTIVE_IN_THIS_REPLAY"
        elif cache.mode in {"off", "refresh"} or stage in cache.force:
            action = "COMPUTE"
        elif not previous:
            action = "LOOK_UP_OR_COMPUTE"
        elif stage in affected:
            action = "RECHECK_AFFECTED_ITEMS"
        else:
            action = "CHECK_EXISTING_PRODUCTS"
        states[stage] = {"action": action, "changed_inputs": changes.get(stage, [])}
    prior_assets = previous.get("pdf", {}).get("originals") or {}
    source_changes = {sha: {"before": prior_assets.get(sha), "after": (assets or {}).get(sha)}
                      for sha in sorted(prior_assets.keys() | (assets or {}).keys())
                      if prior_assets.get(sha) != (assets or {}).get(sha)}
    prior_reviews = previous.get("assessment", {}).get("manual_decisions", {})
    manual_changes = sorted(key for key in prior_reviews.keys() | reviews.keys()
                            if prior_reviews.get(key) != inputs["assessment"]["manual_decisions"].get(key))
    return {"status": "CACHE_PLAN", "writes": False, "mode": cache.mode, "stages": states,
            "forced_stages": sorted(cache.force), "changed_sources": source_changes,
            "changed_review_candidates": manual_changes, "dependency_graph": DEPENDENCIES,
            "scope": "Known input changes; per-product checks and exact reuse are recorded during execution."}


def _run(root, output, originals, development_only, cache, reviews_path, *, frozen_run=None, workspace=None):
    from . import nlp
    from .document_processing import PdfDocumentCache

    started = perf_counter()
    release, files, study, settings, policy, frozen, seeds, technical_old, reviews = _read_frame(
        root, development_only, reviews_path)
    pipeline = IncrementalObservations(root, cache)
    old = by_id(read_jsonl(files["legacy_decisions"]))
    portfolio = by_id(read_jsonl(files["portfolio"]))
    if set(old) != set(portfolio) or any(portfolio[cid]["B1"] != r["B1"] for cid, r in old.items()):
        raise ValueError("Legacy and reviewed decisions differ from their shared baseline")
    if frozen_run is not None:
        from .semantic_technical import baseline_technical

        formal_technical, formal_files = formal_projection(root, Path(frozen_run), settings)
        formal_captures = by_id(baseline_technical(formal_technical))
        if any(formal_captures.get(cid) != capture for cid, capture in technical_old.items()):
            raise ValueError("Formal technical captures differ from the frozen ablation cohort")
        files.update(formal_files)
    extracted = perf_counter()
    engineering = {}
    mode = "FROZEN_CAPTURE_REPLAY"
    source_coverage = None
    source_states = None
    if originals is None:
        resource_new = {r["candidate_id"]: r["e1"] for r in frozen if r["profile_id"] == RESOURCE_PROFILE}
        technical_new = {r["candidate_id"]: r["e1"] for r in frozen if r["profile_id"] == TECHNICAL_PROFILE}
    else:
        if not Path(originals).is_dir():
            raise ValueError("Original source assets must be a directory")
        mode = "SUPPLIED_ORIGINALS_REPLAY"
        with PdfDocumentCache(originals, cache=cache) as documents:
            source_states = _source_states(documents, seeds, technical_old)
            for sha, status in source_states.items():
                if status != "ORIGINAL_VERIFIED":
                    cache.record("pdf", sha, "SOURCE_BLOCKED", reason=status)
            resources, technical = nlp.extract_bound_observations(seeds, list(technical_old.values()), documents)
            engineering["parser_operations"] = dict(documents.counts)
        resource_new, technical_new = by_id(resources), by_id(technical)
    engineering["capture_seconds"] = round(perf_counter() - extracted, 6)
    if set(resource_new) != {r["candidate_id"] for r in seeds} or set(technical_old) != set(technical_new):
        raise ValueError("Retain every candidate ID, including blocked or incomplete captures")
    contract = ResourceContract(root, release, settings["profiles"][RESOURCE_PROFILE])
    rows, relations = evaluate_captures(seeds, technical_old, technical_new, resource_new,
                                        old, portfolio, contract, policy, study, settings)
    _typed_assessments(rows, by_id(seeds), pipeline, reviews, workspace)
    if originals is not None:
        source_coverage = _original_coverage(Path(originals), seeds, technical_old, frozen, rows, source_states)
    summary = _write_outputs(root, output, rows, relations, settings, study, files, frozen, mode, engineering,
                             source_coverage, development_only, started, reviews)
    if workspace is not None:
        summary["staged_e1_records"] = len(rows)
    return summary, _plan_inputs(files, pipeline, reviews, source_states, development_only)


def _validate_paths(root, output, originals, cache, review_path):
    def overlap(left, right):
        return left.is_relative_to(right) or right.is_relative_to(left)

    protected = [root / name for name in ("data", "config", "results", ".git")]
    if output is not None and any(overlap(output, path) for path in protected):
        raise ValueError("Write ablation output separately from frozen inputs")
    if cache.directory is not None:
        extra = [Path(path).resolve() for path in (output, originals, review_path) if path is not None]
        if any(overlap(cache.directory, path) for path in protected + extra):
            raise ValueError("Keep disposable cache separate from originals, decisions and run outputs")


def replay(root, output, *, originals=None, development_only=False, workspace=None, cache=None,
           review_path=None, frozen_run=None):
    """Replay the fixed frame; keep cache telemetry outside the scientific outputs."""
    root, output = Path(root).resolve(), Path(output).resolve()
    cache = cache if cache is not None else DerivedCache()
    _validate_paths(root, output, originals, cache, review_path)
    try:
        summary, inputs = _run(root, output, originals, development_only, cache, review_path,
                               frozen_run=frozen_run, workspace=workspace)
    except Exception as exc:
        atomic_json(output / "cache_run.json", {**cache.receipt(), "status": "FAILED", "error": str(exc)})
        raise
    receipt = {**cache.receipt(), "status": "COMPLETED", "plan_inputs": inputs}
    atomic_json(output / "cache_run.json", receipt)
    if cache.directory is not None and cache.mode != "off":
        atomic_json(cache.directory / "latest-ablation.json", inputs)
    return {**summary, "cache_counts": receipt["counts"]}


def replay_formal_projection(root, originals, frozen_run, output, **options):
    """Read verified formal projections before the optional integrated side run."""
    return replay(root, output, originals=originals, frozen_run=frozen_run, **options)
