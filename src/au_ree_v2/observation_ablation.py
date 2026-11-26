"""Four-arm, checksum-bound evaluation of the shadow observation pipeline."""

from collections import Counter
from csv import DictReader
from decimal import Decimal
from importlib.metadata import version
import json
from pathlib import Path
import re
from time import perf_counter

from .observation_schema import AnalysisFeature, ValidatedObservation, payload
from .observation_semantics import RESOURCE_PROFILE, ResourceContract
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


def _typed_assessments(rows, metadata, root, workspace=None):
    from .observation_pipeline import raw_from_candidate
    from .observation_semantics import SemanticEngine

    engine = SemanticEngine(root)
    for row in rows:
        did = row["candidate_id"]
        typed = {}
        for extraction, arm in (("e0", "E0V1"), ("e1", "E1V1")):
            capture = row[extraction]
            # Attachment identity keeps alternate representations distinct even
            # when they refer to the same canonical observation and location.
            projection = {**capture, "extraction_fingerprint": did}
            raw = raw_from_candidate(projection, extractor_version=(
                capture.get("extraction_version") or "frozen-resource-source-view-v1"),
                metadata=metadata.get(did),
            )
            normalized = engine.normalize(raw)
            decision = row[arm]
            # Only source-witnessed candidates with a supported profile can be
            # marked as verified by the ablation. Imported acceptances remain
            # in the profile verdict with their original provenance.
            verified = (capture["status"] in {"EXTRACTED", "SOURCE_VERIFIED_CANDIDATE"}
                        and decision["status"] == "ACCEPT"
                        and raw.evidence.sha256 and raw.evidence.page and raw.evidence.quote)
            status = "VERIFIED" if verified else None
            semantic = engine.assess(raw, decision, normalized=normalized, evidence_status=status, apply_profile=True,
                                     supporting_evidence=raw.evidence_anchors or (raw.evidence,))
            feature = None
            if normalized and semantic.evidence_status == "VERIFIED" and semantic.comparability == "COMPARABLE":
                validated = ValidatedObservation(normalized, semantic)
                feature = AnalysisFeature(validated, raw.variable, semantic.rule_version,
                                          normalized.value, normalized.unit)
            if workspace is not None and arm == "E1V1":
                workspace.append(raw, normalized=(normalized,) if normalized else (), assessments=(semantic,),
                                 features=(feature,) if feature else ())
            typed[arm] = {
                "raw": {**payload(raw), "raw_id": raw.raw_id},
                "normalized": payload(normalized) if normalized else None,
                "assessment": payload(semantic),
                "analysis_feature": {"name": feature.name, "definition_version": feature.definition_version,
                                     "value": str(feature.value), "unit": feature.unit} if feature else None,
            }
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
                   source_coverage, development_only, started):
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
        "technical_context": technical_audit([r["e0"] for r in rows if r["profile_id"] == TECHNICAL_PROFILE],
                                             [r["e1"] for r in rows if r["profile_id"] == TECHNICAL_PROFILE]),
        "input_sha256": {str(path.relative_to(root)) if path.is_relative_to(root) else name: filehash(path)
                         for name, path in sorted(files.items())},
        "code_sha256": {name: filehash(Path(__file__).with_name(name)) for name in (
            "observation_ablation.py", "observation_shadow.py", "observation_pipeline.py", "observation_schema.py",
            "observation_semantics.py", "normalization.py", "ontology.py", "resource_use.py", "technical.py",
            "technical_tables.py", "semantic_resource.py", "semantic_technical.py", "document_processing.py", "nlp.py",
            "pdf_extract.py",
        )},
        "dependencies": {name: version(name) for name in ("PyMuPDF", "pypdf")},
        "canonical_payload_sha256": {"decisions": digest(rows), "relationship_candidates": digest(relations)},
    }
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


def _original_coverage(assets, seeds, technical_old, frozen, rows):
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
        }
    return report


def _run(root, output, originals, development_only, *, frozen_run=None, workspace=None):
    from . import nlp
    from .document_processing import PdfDocumentCache

    started = perf_counter()
    root, output = Path(root).resolve(), Path(output).resolve()
    # Protect the frozen release plus the historical review inputs from accidental overwrite.
    protected = (root / name for name in ("data", "config", STUDY, BASELINE, PORTFOLIO, RELEASE))
    if any(output.is_relative_to(path) for path in protected):
        raise ValueError("Write ablation output separately from frozen inputs")
    release, files = _shadow_settings(root)
    study, settings, policy = (json.loads(files[k].read_bytes()) for k in ("holdout", "profiles", "evidence_policy"))
    frozen = read_jsonl(files["captures"])
    seeds = _resource_seeds(files, frozen)
    if development_only:
        frozen = [r for r in frozen if partition(r, study) == "DEVELOPMENT_OR_REGRESSION"]
        seeds = [r for r in seeds if partition(r, study) == "DEVELOPMENT_OR_REGRESSION"]
    technical_old = {r["candidate_id"]: r["e0"] for r in frozen if r["profile_id"] == TECHNICAL_PROFILE}
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
    if originals is None:
        resource_new = {r["candidate_id"]: r["e1"] for r in frozen if r["profile_id"] == RESOURCE_PROFILE}
        technical_new = {r["candidate_id"]: r["e1"] for r in frozen if r["profile_id"] == TECHNICAL_PROFILE}
    else:
        if not Path(originals).is_dir():
            raise ValueError("Original source assets must be a directory")
        mode = "SUPPLIED_ORIGINALS_REPLAY"
        with PdfDocumentCache(originals) as documents:
            resources, technical = nlp.extract_bound_observations(seeds, list(technical_old.values()), documents)
            engineering["parser_operations"] = dict(documents.counts)
        resource_new, technical_new = by_id(resources), by_id(technical)
    engineering["capture_seconds"] = round(perf_counter() - extracted, 6)
    if set(resource_new) != {r["candidate_id"] for r in seeds} or set(technical_old) != set(technical_new):
        raise ValueError("Retain every candidate ID, including blocked or incomplete captures")
    contract = ResourceContract(root, release, settings["profiles"][RESOURCE_PROFILE])
    rows, relations = evaluate_captures(seeds, technical_old, technical_new, resource_new,
                                        old, portfolio, contract, policy, study, settings)
    _typed_assessments(rows, by_id(seeds), root, workspace)
    if originals is not None:
        source_coverage = _original_coverage(Path(originals), seeds, technical_old, frozen, rows)
    summary = _write_outputs(root, output, rows, relations, settings, study, files, frozen, mode, engineering,
                             source_coverage, development_only, started)
    if workspace is not None:
        summary["staged_e1_records"] = len(rows)
    return summary


def replay(root, output, *, originals=None, development_only=False, workspace=None):
    """Replay the fixed public capture frame, optionally re-reading supplied originals."""
    return _run(root, output, originals, development_only, workspace=workspace)


def replay_formal_projection(root, originals, frozen_run, output, *, development_only=False, workspace=None):
    """Read verified formal projections before the optional integrated side run."""
    return _run(root, output, originals, development_only, frozen_run=frozen_run, workspace=workspace)
