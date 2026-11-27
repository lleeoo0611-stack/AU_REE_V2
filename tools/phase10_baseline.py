"""Recompute the sealed Census baseline and audit the Phase 10 program boundary."""

import argparse
import ast
from collections import Counter, defaultdict
from graphlib import CycleError, TopologicalSorter
from hashlib import sha256
import json
from pathlib import Path
import re
import subprocess

from au_ree_v2.census_gap_review import frozen_index
from au_ree_v2.derived_cache import FORMAT as CACHE_FORMAT, atomic_json
from au_ree_v2.evidence_model import SCHEMA_VERSION as SQLITE_SCHEMA_VERSION
from au_ree_v2.formal_resource_admission import SCHEMA as ADMISSION_RECEIPT_SCHEMA
from au_ree_v2.observation_schema import RAW_ID_VERSION, SCHEMA_VERSION as OBSERVATION_SCHEMA_VERSION
from au_ree_v2.observation_validation import SCHEMA as SOURCE_VALIDATION_SCHEMA
from au_ree_v2.source_recovery import VERSION as RECOVERY_SCHEMA, _manifest, _sha
from au_ree_v2.store import digest, filehash
from au_ree_v2.tabular import read_csv


RELEASE = Path("results/ree-project-census/coverage-locked-20261125")
BASELINE_REF = "dcda87e81e1250d443f73c1984faaa7beaa19930"
PACKAGE = "au_ree_v2"
CODE = Path("src") / PACKAGE
SHA256 = re.compile(r"[0-9a-f]{64}")
DUPLICATE_BODY_MIN_NODES = 16


def _read(path):
    return json.loads(path.read_bytes())


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _coordinates(rows, name):
    result = {(row["project_id"], row["column"]): row for row in rows}
    _require(len(result) == len(rows), "Duplicate cell in " + name)
    return result


def _git_blob(root, ref, name):
    return subprocess.check_output(["git", "show", f"{ref}:{name}"], cwd=root)


def census_inventory(root, release):
    """Cross-check the published table, reason ledger and prespecified denominator."""
    rows = read_csv(release / "REE project census.csv")
    _require(bool(rows), "Published Census is missing or empty")
    ids = [row["專案ID"] for row in rows]
    columns = list(rows[0])
    values = {(row["專案ID"], name): row[name] for row in rows for name in columns}
    states = _coordinates(read_csv(release / "field_status.csv"), "field_status.csv")
    gaps = _coordinates(read_csv(release / "gap_review.csv"), "gap_review.csv")
    provenance = _coordinates(read_csv(release / "field_provenance.csv"), "field_provenance.csv")
    receipt = _read(release / "census_release.json")
    _require(len(set(ids)) == len(ids) and set(ids) == set(receipt["selected_census_ids"]),
             "Published project IDs differ from the Census receipt")
    _require(values.keys() == states.keys(), "Field states do not enumerate the whole published Census")
    _require(all((value != "") == (states[cell]["status"] == "VALUE_PRESENT") for cell, value in values.items()),
             "Published values disagree with the field states")
    _require(values.keys() == provenance.keys() and all(value == provenance[key]["value"]
             for key, value in values.items()), "Published values disagree with the provenance ledger")
    _require(all(values[key] == row["current_value"] and states[key]["status"] == row["current_status"]
                 for key, row in gaps.items()), "Published gaps do not match field status and value")

    present = sum(bool(value) for value in values.values())
    inapplicable = sum(row["status"].startswith("NOT_APPLICABLE_") for row in states.values())
    missing = len(values) - present - inapplicable
    applicable = present + missing
    _require(missing >= 0 and applicable > 0, "Invalid Census accounting")
    config = root / "config/census_gap_review.json"
    config_bytes = config.read_bytes() if config.is_file() else b""
    expected = receipt["configuration_files"][config.name]
    if sha256(config_bytes).hexdigest() != expected:
        config_bytes = _git_blob(root, receipt["code"]["commit"], "config/" + config.name)
    _require(sha256(config_bytes).hexdigest() == expected,
             "Historical denominator policy differs from its recorded hash")
    frozen = frozen_index(root, json.loads(config_bytes)["baseline"])
    _require(frozen.keys() == states.keys(), "Historical denominator uses a different set of Census cells")
    frozen_applicable = {key for key, row in frozen.items() if not row["status"].startswith("NOT_APPLICABLE_")}
    frozen_filled = sum(bool(values[key]) for key in frozen_applicable)
    reclassified = sum(states[key]["status"].startswith("NOT_APPLICABLE_") for key in frozen_applicable)
    historical_missing = {cell for cell in frozen_applicable if frozen[cell]["status"] != "VALUE_PRESENT"}
    _require(gaps.keys() == historical_missing, "Gap review differs from its prespecified starting frame")

    groups = {}
    for label in ("P1", "P2"):
        selected = {key: row for key, row in gaps.items() if row["class"] == label}
        current = {key: row for key, row in selected.items() if not values[key]
                   and not states[key]["status"].startswith("NOT_APPLICABLE_")}
        groups[label] = {
            "historical_gap_rows": len(selected), "open_applicable_gaps": len(current),
            "projects": len({key[0] for key in current}),
            "actions": dict(Counter(row["action"] for row in selected.values())),
            "fields": dict(Counter(key[1] for key in current)),
            "coordinates_sha256": digest(sorted(current)),
        }
    return {
        "projects": len(ids), "project_ids_sha256": digest(sorted(ids)), "columns": len(columns),
        "column_names": columns, "total_cells": len(values), "present": present,
        "not_applicable": inapplicable, "missing_applicable": missing, "applicable": applicable,
        "current_coverage": present / applicable, "historical_frozen_denominator": len(frozen_applicable),
        "filled_in_historical_denominator": frozen_filled,
        "historical_fixed_coverage": frozen_filled / len(frozen_applicable),
        "historical_applicable_now_excluded": reclassified,
        "status_counts": dict(Counter(row["status"] for row in states.values())),
        "priority_classes": groups,
        "priority_gaps": sum(group["open_applicable_gaps"] for group in groups.values()),
        "provenance_coordinates": len(provenance),
        "present_cells_with_source_sha256": sum(bool(values[key] and row.get("source_sha256"))
                                                 for key, row in provenance.items()),
        "coverage_by_column": {name: dict(Counter(row["status"] for key, row in states.items() if key[1] == name))
                               for name in columns},
    }


def _archive_panels(release, receipt):
    panels = {}
    for panel, recorded in sorted(receipt["ranking_panels"].items()):
        _require(Path(panel).name == panel, "Invalid archived panel name")
        directory = release / "MCDA" / panel
        local = {}
        for name, expected in sorted(recorded["digests"].items()):
            _require(Path(name).name == name and SHA256.fullmatch(expected), "Invalid archived panel file specification")
            path = directory / name
            if path.is_file():
                _require(filehash(path) == expected, f"Published panel file checksum mismatch: {panel}/{name}")
                local[name] = expected
        _require("ranking.csv" in local, "Missing archived ranking for " + panel)
        ranking = read_csv(directory / "ranking.csv")
        selected_ids = {row["project_id"] for row in ranking}
        _require(len(selected_ids) == recorded["ranked_projects"], "Ranked cohort disagrees with archival receipt")
        panels[panel] = {
            "ranked_projects": len(selected_ids), "matrix_projects_reported": recorded["matrix_projects"],
            "ranked_projects_sha256": digest(sorted(selected_ids)), "ranking_rows": len(ranking),
            "criteria": recorded["criteria"], "weight_scenarios": recorded["weight_scenarios"],
            "receipt_hashes": recorded["digests"], "locally_rehashed": local,
            "receipt_only": sorted(recorded["digests"].keys() - local.keys()),
        }
    return panels


def _archive_output_checks(release, receipt):
    expected_outputs = receipt["evidence_outputs"] | {
        "source_selection.csv": receipt["source_selection_sha256"],
        "eligibility_audit.json": receipt["eligibility_audit_sha256"],
        "aim_c_availability.csv": receipt["aim_c_availability_sha256"],
    }
    checks = {}
    for name, expected in sorted(expected_outputs.items()):
        path = release / name
        if path.is_file():
            _require(filehash(path) == expected, "Published output checksum mismatch: " + name)
            checks[name] = {"sha256": expected, "validation": "REHASHED_LOCAL_BYTES"}
        else:
            checks[name] = {"sha256": expected, "validation": "ARCHIVE_RECEIPT_ONLY"}
    return checks


def _recovery_inventory(path, planned, contract):
    if path is None:
        return {"status": "NOT_MEASURED", "reason": "NO_LOCAL_RECOVERY_RECEIPT_SUPPLIED"}
    path = Path(path)
    receipt = _read(path)
    _require(receipt.get("version") == RECOVERY_SCHEMA, "Unsupported source recovery receipt version")
    _require(receipt["contract"] == contract and receipt["expected"] == len(planned),
             "Recovery receipt uses a different source snapshot contract")
    receipts = {item["locked_sha256"]: item for item in receipt["receipts"]}
    _require(len(receipts) == len(receipt["receipts"]) and receipts.keys() == planned.keys(),
             "Recovery receipt does not enumerate the full locked SHA set")
    assets = Path(receipt["assets"])
    if not assets.is_absolute():
        assets = path.parent / assets
    verified, missing, invalid = [], [], []
    for sha in sorted(planned):
        asset = assets / sha
        if asset.is_symlink():
            invalid.append(sha)
        elif not asset.is_file():
            missing.append(sha)
        elif _sha(asset) != sha:
            invalid.append(sha)
        else:
            verified.append(sha)
    locked_references = {
        sha: sorted({item[0]["key"] for item in planned[sha]}) for sha in missing + invalid
    }
    return {
        "status": "INCOMPLETE_ORIGINALS" if missing or invalid else "ALL_PINNED_BYTES_LOCALLY_VERIFIED",
        "receipt_sha256": filehash(path), "reported_verified": receipt["verified"],
        "current_verified": len(verified), "current_missing": len(missing), "current_invalid": len(invalid),
        "verified_sha256": verified,
        "missing_or_invalid_by_sha256": locked_references,
        "missing_sha256": missing, "invalid_sha256": invalid,
    }


def _quality_inventory(root):
    quality_path = root / "config/ontology/quality_frame_v1.json"
    quality = _read(quality_path)
    for name, sha in quality["input_sha256"].items():
        _require(filehash(root / name) == sha, "Quality frame input changed: " + name)
    review_path = root / "results/observation-shadow-20261126/review_evaluation.json"
    review = _read(review_path)
    provisional_path = root / "results/ontology-gain-20261126/metrics.json"
    provisional = _read(provisional_path)
    labels_path = provisional_path.with_name("source_review_primary.jsonl")
    primary_labels = [json.loads(line) for line in labels_path.read_text(encoding="utf-8").splitlines()
                      if line.strip()]
    _require(len(primary_labels) == provisional["primary_sample"], "Presampled source review size differs")
    frames = {}
    for path in sorted((root / "config/ontology").glob("resource_admission*frame_v*.json")):
        frame = _read(path)
        frames[path.name] = {
            "sha256": filehash(path), "schema": frame["schema"], "classification": frame["classification"],
            "source_editions": len({row["source_sha256"] for row in frame["sources"]}),
            "manifest_value_pages": sum(len(row["pages"]) for row in frame["sources"]),
            "source_sha256": sorted(row["source_sha256"] for row in frame["sources"]),
            "design": frame["design"],
        }
    return {
        "quality_frame_sha256": filehash(quality_path),
        "quality_frame_cutoff": quality["cutoff"],
        "quality_frame": {name: {
            "source_editions": len({row["source_sha256"] for row in rows}),
            "physical_pages": sum(len(row["pages"]) for row in rows),
            "strata": dict(Counter(row["stratum"] for row in rows)),
        } for name, rows in quality["partitions"].items()},
        "independent_review_sha256": filehash(review_path), "gold_reference_status": "UNMEASURED",
        "independent_resource_pages_planned": review["page_count"],
        "independent_pages_annotated": review["pages_fully_annotated"],
        "accuracy": review["accuracy"],
        "provisional_source_review": {
            "status": provisional["review_status"], "source_review_sha256": filehash(labels_path),
            "metrics_sha256": filehash(provisional_path), "population": provisional["population"],
            "primary_sample": len(primary_labels),
            "extra_disagreement_reviews": provisional["additional_disagreement_reviews"],
            "reference_scope": "AI_ASSISTED_SOURCE_REVIEW; NOT_INDEPENDENT_HUMAN_GOLD",
        },
        "resource_admission_frames": frames,
        "classification": "SOURCE_BOUND_DEVELOPMENT_AND_REGRESSION_INVENTORY",
    }


def _imports(tree, modules):
    targets = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith(PACKAGE + "."):
                    targets.add(alias.name.split(".")[1])
        elif isinstance(node, ast.ImportFrom):
            if node.level == 1 and node.module is not None:
                targets.add(node.module.split(".")[0])
            elif (node.level == 1 and node.module is None) or (node.level == 0 and node.module == PACKAGE):
                targets.update(alias.name for alias in node.names)
            elif node.level == 0 and node.module and node.module.startswith(PACKAGE + "."):
                targets.add(node.module.split(".")[1])
    return sorted(targets.intersection(modules))


def _without_nested_scopes(body):
    stack = list(body)
    while stack:
        node = stack.pop()
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
            continue
        yield node
        stack.extend(ast.iter_child_nodes(node))


def _complexity(node):
    count = 1
    for statement in _without_nested_scopes(node.body):
        if isinstance(statement, (ast.If, ast.For, ast.AsyncFor, ast.While, ast.IfExp, ast.ExceptHandler)):
            count += 1
        elif isinstance(statement, ast.BoolOp):
            count += len(statement.values) - 1
        elif isinstance(statement, ast.comprehension):
            count += 1 + len(statement.ifs)
        elif isinstance(statement, ast.Match):
            count += len(statement.cases) - 1 + sum(case.guard is not None for case in statement.cases)
    return count


def _code_files(root, ref):
    if ref is None:
        return {path.relative_to(root).as_posix(): path.read_bytes()
                for path in sorted((root / CODE).glob("*.py"))}
    paths = subprocess.check_output(
        ["git", "ls-tree", "-rz", "--name-only", ref, "--", CODE.as_posix()], cwd=root,
    ).decode().split("\0")
    return {name: _git_blob(root, ref, name)
            for name in paths if name and Path(name).suffix == ".py" and Path(name).parent == CODE}


def module_audit(root, ref=None):
    """Measure package-local edges, identical AST bodies and structural branches."""
    sources = _code_files(root, ref)
    trees = {Path(name).stem: ast.parse(content, filename=name) for name, content in sources.items()}
    dependencies = {name: _imports(tree, trees) for name, tree in trees.items()}
    comparison = defaultdict(list)
    complexity = []
    for module, tree in trees.items():
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            label = {"module": module, "function": node.name, "line": node.lineno}
            complexity.append({**label, "score": _complexity(node)})
            body = node.body[1:] if ast.get_docstring(node) is not None else node.body
            normal = ast.Module(body=body, type_ignores=[])
            nodes = sum(1 for _ in ast.walk(normal))
            if nodes >= DUPLICATE_BODY_MIN_NODES:
                comparison[digest(ast.dump(normal))].append({**label, "ast_nodes": nodes})
    try:
        list(TopologicalSorter(dependencies).static_order())
        cycle = None
    except CycleError as exc:
        cycle = exc.args[1]
    duplicates = {key: members for key, members in comparison.items() if len(members) > 1}
    cross_module = {key: members for key, members in duplicates.items()
                    if len({item["module"] for item in members}) > 1}
    scores = sorted(record["score"] for record in complexity)
    return {
        "source_ref": ref or "WORKTREE", "module_count": len(trees),
        "internal_edges": sum(len(targets) for targets in dependencies.values()),
        "graph": dependencies, "cycle_witness": cycle,
        "source_sha256": {name: sha256(content).hexdigest() for name, content in sources.items()},
        "duplicate_minimum_ast_nodes": DUPLICATE_BODY_MIN_NODES,
        "duplicate_body_groups": duplicates, "cross_module_duplicate_groups": cross_module,
        "cyclomatic_estimate": {
            "functions": len(scores), "p90": scores[(len(scores) * 9 - 1) // 10],
            "max": scores[-1], "top": sorted(complexity, key=lambda row: (
                -row["score"], row["module"], row["function"], row["line"]))[:15],
        },
    }


def run(root, output, *, recovery_manifest=None, baseline_ref=BASELINE_REF):
    root, output = Path(root).resolve(), Path(output).resolve()
    release = root / RELEASE
    _require(not output.is_relative_to(release), "Write audit receipts outside the sealed Census inputs")
    receipt = _read(release / "census_release.json")
    _require(filehash(release / "REE project census.csv") == receipt["census_csv_sha256"],
             "Published Census differs from the archived receipt")
    planned, contract = _manifest(root, release)
    _require(contract["cutoff"] == receipt["cutoff"], "Census and source cutoffs disagree")
    census = census_inventory(root, release)
    panels = _archive_panels(release, receipt)
    local_hashes = {name: filehash(release / name) for name in (
        "REE project census.csv", "coverage.json", "field_status.csv", "field_provenance.csv", "gap_review.csv", "source_selection.csv",
        "asset_manifest.json", "bundle_verification.json", "census_release.json", "verification.json",
    )}
    archive_configs = receipt["configuration_files"]
    current_configs = {name: filehash(root / "config" / name) for name in archive_configs
                       if (root / "config" / name).is_file()}
    git_configs = {name: sha256(_git_blob(root, receipt["code"]["commit"], "config/" + name)).hexdigest()
                   for name in archive_configs}
    report = {
        "schema": "phase10-baseline-v1", "baseline_reference": str(RELEASE), "cutoff": receipt["cutoff"],
        "separation": "ARCHIVED_CENSUS_REHASHED; NO_NEW_FULL_CENSUS_REPLAY",
        "archive_run": {key: receipt[key] for key in (
            "run_id", "code", "mode", "configuration_sha256", "configuration_files", "claims_sha256",
            "identity_links_sha256", "methods", "monte_carlo", "formal_cohort", "analytical_runtime",
            "source_receipt_sha256", "source_selection_sha256", "evidence_outputs",
        )},
        "archive_logical_database_sha256": _read(release / "coverage.json")["logical_database_sha256"],
        "current_interchanges": {
            "canonical_sqlite_schema": SQLITE_SCHEMA_VERSION, "observation_schema": OBSERVATION_SCHEMA_VERSION,
            "raw_identity_schema": RAW_ID_VERSION, "derived_cache_format": CACHE_FORMAT,
            "resource_admission_receipt": ADMISSION_RECEIPT_SCHEMA, "source_recovery_receipt": RECOVERY_SCHEMA,
            "source_validation_receipt": SOURCE_VALIDATION_SCHEMA,
            "compatibility": {
                "canonical_sqlite": "A version 0 database has a transactional migration or read-only TEMP views."
                                    " SQLite rejects unsupported schema versions.",
                "observation": "Typed projections require the current schema on load. Raw content IDs retain"
                               " the independent v1 identity contract.",
                "derived_cache": "Version and product content are verified on read. An incompatible derived"
                                 " entry is quarantined and recomputed when used.",
            },
        },
        "current_config_sha256": current_configs, "archive_file_sha256": local_hashes,
        "archive_output_checks": _archive_output_checks(release, receipt),
        "config_comparison": {
            "worktree_matched": sorted(name for name, value in current_configs.items() if value == archive_configs[name]),
            "worktree_changed": sorted(name for name, value in current_configs.items() if value != archive_configs[name]),
            "worktree_missing": sorted(archive_configs.keys() - current_configs.keys()),
            "archive_commit_config_sha256": git_configs,
            "archive_commit_mismatch": sorted(name for name, value in git_configs.items() if value != archive_configs[name]),
        },
        "census": census,
        "source_lock": {"assets": len(planned), "unique_sha256": sorted(planned),
                        **_read(release / "bundle_verification.json"), "contract": contract},
        "current_local_source_recovery": _recovery_inventory(recovery_manifest, planned, contract),
        "archive_mcda": {
            "panel_count": len(panels), "panels": panels,
            "panel_files_rehashed": sum(len(panel["locally_rehashed"]) for panel in panels.values()),
            "panel_fingerprints_receipt_only": sum(len(panel["receipt_only"]) for panel in panels.values()),
        },
        "quality_references": _quality_inventory(root),
    }
    audit = {
        "schema": "phase10-module-audit-v1",
        "scope": "Package-local Python module imports including nested import statements.",
        "duplicates": "Exact AST body groups, excluding leading function docstrings, with at least 16 AST nodes.",
        "cyclomatic_method": "One plus control-flow branches, Boolean short-circuits, comprehension loops and guards.",
        "baseline": module_audit(root, baseline_ref), "worktree": module_audit(root),
    }
    atomic_json(output / "phase10_baseline.json", report)
    atomic_json(output / "phase10_module_audit.json", audit)
    (output / "phase10_baseline.md").write_text(_markdown(report, audit), encoding="utf-8")
    return report


def _markdown(report, audit):
    census = report["census"]
    recovery = report["current_local_source_recovery"]
    mcda = report["archive_mcda"]
    modules = [audit[key] for key in ("baseline", "worktree")]
    lines = [
        "# Phase 10 封存基準核對", "",
        f"以 2026-11-13 的 Census 封存為比較基準，當時的程式提交為 `{report['archive_run']['code']['commit']}`。",
        f"逐格比對 {census['projects']} 個穩定 Project ID、{census['columns']} 欄與 {census['total_cells']} 格狀態。",
        f"有值 {census['present']} 格，不適用 {census['not_applicable']} 格，適用但缺值 {census['missing_applicable']} 格。",
        f"當前適用分母為 {census['applicable']}，涵蓋率為 {census['current_coverage']:.2%}。",
        f"原比較分母為 {census['historical_frozen_denominator']}，涵蓋率為 {census['historical_fixed_coverage']:.2%}，"
        f"包含 {census['historical_applicable_now_excluded']} 格後來改判為不適用。", "",
        f"P1 待補公開值 {census['priority_classes']['P1']['open_applicable_gaps']} 格，"
        f"P2 待補衍生組分 {census['priority_classes']['P2']['open_applicable_gaps']} 格。",
        "兩組欄位均以原始座標與缺值理由核對。", "",
        f"來源鎖含 {report['source_lock']['assets']} 個唯一 SHA 及 {report['source_lock']['references']} 筆參照。",
        f"重新雜湊 {mcda['panel_count']} 組封存排名。其餘 {mcda['panel_fingerprints_receipt_only']} 份矩陣、準則、"
        "權重及敏感度產物的指紋由封存收據提供。這組資料是既有成果的核對基準。", "",
    ]
    if "current_verified" in recovery:
        lines += [f"本機逐份核驗 {recovery['current_verified']} 份原件。缺件 "
                  f"{recovery['current_missing']} 份，指紋不符 {recovery['current_invalid']} 份。", ""]
    changed = report["config_comparison"]["worktree_changed"]
    if changed:
        lines += ["現行設定與封存設定有差異的檔案為 " + "、".join(f"`{name}`" for name in changed) + "。"]
    historical_mismatch = report["config_comparison"]["archive_commit_mismatch"]
    if historical_mismatch:
        lines += ["封存收據所列提交中的 " + "、".join(f"`{name}`" for name in historical_mismatch)
                  + " 指紋也與收據相異。精確重播仍需要該次實際設定。"]
    lines.append("")
    hotspots = modules[1]["cyclomatic_estimate"]["top"][:3]
    hotspot_labels = "、".join(f"`{row['module']}.{row['function']}` ({row['score']})" for row in hotspots)
    lines.extend([
        "| 模組掃描 | 模組數 | 內部依賴邊 | 循環 | 跨模組相同函式群 | 分支複雜度第 90 百分位 | 最大分支複雜度 |",
        "|---|---:|---:|---:|---:|---:|---:|",
        *[
            f"| {label} | {graph['module_count']} | {graph['internal_edges']} | {int(bool(graph['cycle_witness']))} "
            f"| {len(graph['cross_module_duplicate_groups'])} | {graph['cyclomatic_estimate']['p90']} "
            f"| {graph['cyclomatic_estimate']['max']} |"
            for label, graph in zip(("開發基準", "稽核時的工作樹"), modules, strict=True)
        ],
        "", "匯入圖包含函式內相依。複雜度是 Python AST 的結構估計，計入短路判定。重複程式形狀用於定位候選，科學等價性由固定輸入重播驗證。",
        f"目前分支最多的函式為 {hotspot_labels}。",
        "", "Canonical SQLite 可由 v0 遷移至 v1，唯讀的 v0 仍可透過 TEMP View 查詢。觀測型別讀取檢查 v3，原始觀測 ID 仍由 v1 產生。",
        "", "既有盲審參照仍缺獨立已完成標註。來源綁定測試與資料重播維持各自的評估口徑。",
        "", "[機器可讀基準與檔案指紋](phase10_baseline.json) · [模組圖與相同函式](phase10_module_audit.json)", "",
    ])
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--recovery-manifest", type=Path)
    parser.add_argument("--baseline-ref", default=BASELINE_REF)
    args = parser.parse_args()
    run(args.root, args.out, recovery_manifest=args.recovery_manifest, baseline_ref=args.baseline_ref)


if __name__ == "__main__":
    main()
