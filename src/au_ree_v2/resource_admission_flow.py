"""Pin source discovery and describe the rules used by one formal resource run."""

from contextlib import nullcontext
from hashlib import sha256
import json
from pathlib import Path
import re

from .derived_cache import DerivedCache
from .document_processing import PdfDocumentCache
from .resource_retrieval import apply_parse_receipt, policy, retrieve
from .store import digest, filehash


FRAME_VERSION = "resource-admission-frame-v1"
ADMISSION_VERSION = "formal-resource-admission-run-v2"
_SHA = re.compile(r"[a-f0-9]{64}")
_RULES = (
    "resource_admission_flow.py", "resource_retrieval.py", "formal_resource_admission.py", "resource_source.py", "resource_estimate.py",
    "resource_jorc.py",
    "numeric_evidence.py", "observation_schema.py", "observation_pipeline.py", "observation_semantics.py",
    "normalization.py", "ontology.py", "resource_use.py", "semantic_resource.py", "technical_tables.py",
    "pdf_extract.py", "document_processing.py", "nlp.py", "store.py", "evidence.py", "evidence_model.py",
    "selection.py", "selection_rules.py", "hierarchy.py", "census.py", "analysis.py", "mcda.py", "cli.py",
)


def _physical_pages(pages):
    return (isinstance(pages, list) and all(type(page) is int and page >= 1 for page in pages)
            and len(set(pages)) == len(pages))


def load_frame(path, *, retrieval_mode=None):
    """Read pinned editions and their fixed pages or retrieval policy."""
    path = Path(path)
    data = path.read_bytes()
    frame = json.loads(data)
    version = frame.get("schema")
    if version == FRAME_VERSION:
        rows = frame["sources"]
    elif version == "observation-quality-frame-v1":
        rows = [row for partition in frame["partitions"].values() for row in partition]
    else:
        raise ValueError("UNKNOWN_RESOURCE_ADMISSION_FRAME_VERSION")
    classification = frame.get("classification", "PUBLIC_REAL_SOURCE_REPLAY")
    if classification not in {"PUBLIC_REAL_SOURCE_REPLAY", "SYNTHETIC_ENGINEERING_FIXTURE"}:
        raise ValueError("INVALID_RESOURCE_ADMISSION_CLASSIFICATION")
    pinned = {}
    for row in rows:
        key, sha, pages = row["source_key"], row["source_sha256"], row["pages"]
        context_pages = row.get("context_pages", [])
        if (not isinstance(key, str) or not key.strip() or not isinstance(sha, str) or not _SHA.fullmatch(sha)
                or not pages or not _physical_pages(pages) or not _physical_pages(context_pages)
                or set(pages).intersection(context_pages)):
            raise ValueError("INVALID_RESOURCE_ADMISSION_SOURCE_FRAME")
        if sha in pinned:
            raise ValueError("AMBIGUOUS_RESOURCE_ADMISSION_SOURCE_FRAME")
        pinned[sha] = {"source_key": key, "source_sha256": sha, "pages": sorted(pages)}
        if context_pages:
            pinned[sha]["context_pages"] = sorted(context_pages)
    if not pinned:
        raise ValueError("EMPTY_RESOURCE_ADMISSION_FRAME")
    retrieval = policy(frame.get("retrieval"), override_mode=retrieval_mode)
    result = {"schema": version, "sha256": sha256(data).hexdigest(), "classification": classification,
              "sources": sorted(pinned.values(), key=lambda row: (row["source_key"], row["source_sha256"]))}
    if retrieval["mode"] == "full-text":
        if any(len(row["pages"]) > retrieval["value_page_budget"]
               or len(row.get("context_pages", [])) > retrieval["context_page_budget"] for row in result["sources"]):
            raise ValueError("RESOURCE_RETRIEVAL_BUDGET_BELOW_FIXED_FRAME")
        result["retrieval"] = retrieval
    return result


def run(db, root, snapshots, cutoff, frame, *, run_id, configuration, acquired_through, claims_data,
        cache_dir, cache_mode):
    """Use only exact editions selected by the ordinary source acquisition path."""
    from .formal_resource_admission import _authorized_projects, _source_metadata_issue, admit
    from .pdf_extract import project_registry

    root = Path(root)
    package = Path(__file__).parent
    config_inputs = ("config/evidence_policy.json", "config/eligibility_compatibility.json",
                     "config/ontology/observation_v1.json", "config/ontology/comparability_v1.json")
    rules = {name: filehash(package / name) for name in _RULES}
    rules.update({name: filehash(root / name) for name in config_inputs if (root / name).is_file()})
    file_rows, ambiguous = {}, set()
    for source in snapshots:
        if source["kind"] != "pdf":
            continue
        identity = source["key"], source["sha256"]
        if identity in file_rows and source != file_rows[identity]:
            ambiguous.add(identity)
        file_rows[identity] = source
    preferred = {}
    requests = {}
    context_pages = {}
    excluded = []
    for row in frame["sources"]:
        key, sha = row["source_key"], row["source_sha256"]
        if (key, sha) in file_rows:
            preferred[sha] = key
            requests[sha] = row["pages"]
            if row.get("context_pages"):
                context_pages[sha] = row["context_pages"]
        else:
            excluded.append({**row, "status": "SOURCE_BLOCKED", "reason": "PINNED_SOURCE_EDITION_NOT_SELECTED"})

    cache = DerivedCache(cache_dir, mode=cache_mode)
    retrieval = frame.get("retrieval")
    searches, effective = {}, []
    if retrieval:
        selected = {sha: file_rows[key, sha] for sha, key in preferred.items()}
        paths = {sha: root / source["path"] for sha, source in selected.items() if source.get("path")}
        reader = PdfDocumentCache(root, source_paths=paths, cache=cache)
    else:
        reader = nullcontext(None)
    with reader as documents:
        if documents is not None:
            claims = claims_data if claims_data is not None else json.loads((root / "data/claims.json").read_bytes())
            registry = project_registry(root, db, snapshots, mapping={}, claims_data=claims)
            projects = _authorized_projects(claims, registry, selected)
            names = {project["entity_id"]: [project["name"], *project["aliases"]] for project in registry}
            for row in frame["sources"]:
                key, sha = row["source_key"], row["source_sha256"]
                source = selected.get(sha)
                problem = ("PINNED_SOURCE_EDITION_NOT_SELECTED" if source is None
                           else "SOURCE_EDITION_METADATA_AMBIGUOUS" if (key, sha) in ambiguous
                           else "SOURCE_ARTIFACT_PATH_MISSING" if not source.get("path")
                           else _source_metadata_issue(source, cutoff, None, acquired_through))
                if not problem and source.get("case_classification", "PUBLIC_REAL_SOURCE_REPLAY") != frame["classification"]:
                    problem = "SOURCE_CLASSIFICATION_MISMATCH"
                aliases = [alias for project in projects.get(sha, []) for alias in names[project]]
                search = searches[sha] = retrieve(documents, row, aliases, retrieval, blocked_reason=problem)
                if source is None:
                    continue
                requests[sha], context_pages[sha] = search["selected_pages"], search["selected_context_pages"]
                effective.append({"source_key": key, "source_sha256": sha, "pages": requests[sha],
                                  "context_pages": context_pages[sha]})
        shared_reader = {"document_cache": documents} if documents is not None else {}
        result = admit(db, root, snapshots, cutoff, requests, acquired_through=acquired_through,
                       claims_data=claims_data, cache=cache, classification=frame["classification"],
                       context_pages_by_sha=context_pages, preferred_source_keys=preferred, **shared_reader)
    ids = sorted(set(result["canonical_observation_ids"]))
    active_ids = sorted(set(result["active_admission_observation_ids"]))
    contract = {"schema": ADMISSION_VERSION, "cutoff": cutoff, "acquired_through": acquired_through,
                "snapshot_sha256": digest(snapshots), "frame_sha256": frame["sha256"],
                "rules_sha256": digest(rules), "baseline_configuration_sha256": digest(configuration),
                "claims_sha256": configuration["claims_sha256"],
                "identity_mapping_sha256": configuration.get("identity_links.json_sha256"),
                "monte_carlo": configuration["research"].get("monte_carlo"),
                "canonical_observation_ids": ids, "active_admission_observation_ids": active_ids,
                "classification": frame["classification"]}
    frame_counts = {"sources_planned": len(frame["sources"]), "sources_selected": len(requests),
                    "sources_not_selected": len(excluded),
                    "pages_planned": sum(len(row["pages"]) for row in frame["sources"]),
                    "pages_source_not_selected": sum(len(row["pages"]) for row in excluded)}
    retrieval_receipt = {}
    if retrieval:
        contract.update(retrieval=retrieval, effective_frame_sources_sha256=digest(effective))
        dispositions = {source["source_sha256"]: source for source in result["source_dispositions"]}
        for sha, search in searches.items():
            apply_parse_receipt(search, dispositions.get(sha, {}))
        retrieval_receipt = {"effective_frame_sources": effective, "retrieval_sources": list(searches.values())}
        frame_counts.update(value_pages_selected=sum(len(pages) for pages in requests.values()),
                            context_pages_selected=sum(len(pages) for pages in context_pages.values()))
    receipt = {**result, **contract, "run_id": run_id, "rules": rules, "frame_sources": frame["sources"],
               "admission_engine_rules_sha256": result["rules_sha256"], "frame_counts": frame_counts,
               "excluded_sources": excluded, "cache": cache.receipt(), **retrieval_receipt}
    if excluded and receipt["status"] == "COMPLETE":
        receipt["status"] = "COMPLETE_WITH_GAPS"
    return contract, receipt
