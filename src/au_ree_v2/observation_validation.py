"""Unattended recovery, quality checks and existing-panel validation."""

import csv
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

from .derived_cache import DerivedCache, atomic_json
from .store import filehash


CENSUS_RELEASE = Path("results/ree-project-census/coverage-locked-20261125")
PHASE22_LOCK = Path("results/phase22-2026-11-06/snapshot_lock.json")
ASSET_NAME = re.compile(r"([a-f0-9]{64})(?:\.pdf)?")
SCHEMA = "unattended-observation-validation-v1"


def _disjoint(candidate, protected):
    return all(not candidate.is_relative_to(path) and not path.is_relative_to(candidate) for path in protected)


def _stage_originals(root, destination, libraries):
    """Build a disposable SHA-named view across local libraries and frozen snapshots."""
    destination.mkdir(parents=True, exist_ok=True)
    catalog = json.loads((root / "data/manifest.json").read_bytes())
    candidates = {}
    for library in libraries:
        if not library.is_dir() or library == destination:
            continue
        for path in sorted(library.iterdir()):
            if (name := ASSET_NAME.fullmatch(path.name)) and path.is_file():
                candidates.setdefault(name[1], []).append(path)
    for source in catalog["snapshots"]:
        if source["kind"] == "pdf":
            candidates.setdefault(source["sha256"], []).append(root / source["path"])
    staged = set()
    for sha, options in sorted(candidates.items()):
        for path in options:
            try:
                with path.open("rb") as stream:
                    if stream.read(5) != b"%PDF-":
                        continue
                    stream.seek(0)
                    if hashlib.file_digest(stream, "sha256").hexdigest() != sha:
                        continue
            except OSError:
                continue
            alias = destination / sha
            source = path.resolve()
            if alias.is_symlink() and alias.resolve() != source:
                alias.unlink()
            if not alias.is_symlink():
                if alias.exists():
                    raise ValueError("A disposable original view already contains a regular file")
                alias.symlink_to(source)
            staged.add(sha)
            break
    for alias in destination.iterdir():
        if alias.is_symlink() and ASSET_NAME.fullmatch(alias.name) and alias.name not in staged:
            alias.unlink()
    return {"status": "COMPLETE", "verified_pdfs": len(staged), "originals": str(destination)}


def _run_formal(root, work, arguments, rscript):
    """Run the existing formal entrypoint and preserve its original terminal log."""
    work.mkdir(parents=True, exist_ok=True)
    command = [sys.executable, "-m", "au_ree_v2", *arguments, "--root", str(root), "--work", str(work)]
    if rscript:
        command.extend(("--rscript", str(rscript)))
    log = work / "validation_rebuild.log"
    with log.open("wb") as stream:
        process = subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT, check=False, timeout=1800)
    if process.returncode:
        return {"status": "FAILED", "reason": "FORMAL_REBUILD_EXITED", "returncode": process.returncode,
                "log": str(log)}
    summary_path = work / "latest.json"
    summary = json.loads(summary_path.read_bytes())
    return {"status": "COMPLETE", "cutoff": summary["cutoff"], "summary": str(summary_path),
            "run": summary["output_dir"], "run_id": summary["run_id"], "log": str(log),
            "published_census": summary.get("project_census_csv")}


def _compare_census(release, replay, published):
    """Verify the pinned scientific artifacts and census identities after a full run."""
    reference = json.loads((release / "census_release.json").read_bytes())
    expected = {
        published: reference["census_csv_sha256"],
        replay / "eligibility_audit.json": reference["eligibility_audit_sha256"],
        replay / "source_selection.csv": reference["source_selection_sha256"],
    }
    expected.update({replay / "project-summary" / name: sha
                     for name, sha in reference["evidence_outputs"].items()})
    expected.update({replay / panel / name: sha for panel, row in reference["ranking_panels"].items()
                     for name, sha in row["digests"].items()})
    differences = []
    for path, sha in expected.items():
        if sha is None:
            continue
        actual = filehash(path) if path.is_file() else None
        if actual != sha:
            differences.append({"output": path.relative_to(replay).as_posix()
                                if path.is_relative_to(replay) else path.name,
                                "expected": sha, "actual": actual})
    with published.open(encoding="utf-8-sig", newline="") as stream:
        # The published table uses this stable identifier independently of report row order.
        actual_ids = [row["專案ID"] for row in csv.DictReader(stream)]
    ids_match = sorted(actual_ids) == sorted(reference["selected_census_ids"])
    return {"status": "COMPLETE" if ids_match and not differences else "DIFFERENCES",
            "cutoff": reference["cutoff"], "compared": len(expected), "project_ids_match": ids_match,
            "projects": len(actual_ids), "differences": differences}


def run(root, output, *, libraries=(), online=True, request_budget=80, cache_dir=None, cache_mode="use",
        database=None, formal_run=None, rscript=None, tessdata=None):
    """Continue independent validation when originals or specific stages are unavailable."""
    from .formal_resource_bridge import run as bridge
    from .observation_ablation import replay
    from .observation_quality import run as quality
    from .source_recovery import recover_census_assets

    root, output = Path(root).resolve(), Path(output).resolve()
    release = root / CENSUS_RELEASE
    libraries = tuple(Path(path).resolve() for path in libraries)
    protected = [root / name for name in ("data", "config", "results", "src", "docs", "R", "tests", ".git")]
    protected.extend(libraries)
    protected.extend(Path(path).resolve() for path in (database, formal_run) if path is not None)
    if not _disjoint(output, protected):
        raise ValueError("Keep validation output separate from originals, source files and prior formal runs")
    cache_path = Path(cache_dir).resolve() if cache_dir is not None else output / "derived-cache"
    if not _disjoint(cache_path, [*protected, *(output / name for name in (
        "source-recovery", "originals", "quality", "shadow", "formal-93", "formal-phase22", "resource-panel",
    ))]):
        raise ValueError("Keep disposable cache separate from validation inputs and stage reports")
    if (database is None) != (formal_run is None):
        raise ValueError("Supply both canonical SQLite and its formal run, or rebuild the frozen reference")
    if any(not (path.is_dir() or path.is_file() and path.suffix.lower() == ".zip") for path in libraries):
        raise ValueError("A source library must be an existing directory or ZIP archive")
    tessdata = Path(tessdata).resolve() if tessdata is not None else root / "data/ocr"
    output.mkdir(parents=True, exist_ok=True)
    stages = {}
    report = {"schema": SCHEMA, "status": "RUNNING", "stages": stages}

    def record(name, stage):
        stages[name] = stage
        atomic_json(output / "validation.json", report)
        return stage

    def attempt(name, action):
        try:
            stage = action()
        except Exception as exc:
            stage = {"status": "FAILED", "reason": type(exc).__name__, "detail": str(exc)}
        return record(name, stage)

    recovered = attempt("source_recovery", lambda: recover_census_assets(
        root, release, output / "source-recovery", libraries=libraries, online=online,
        request_budget=request_budget,
    ))
    source_libraries = (Path(recovered["assets"]), *libraries) if recovered.get("assets") else libraries
    originals = attempt("document_inputs", lambda: _stage_originals(root, output / "originals", source_libraries))
    if originals["status"] == "COMPLETE":
        attempt("automated_quality", lambda: quality(
            root, output / "originals", output / "quality", tessdata=tessdata,
            cache=DerivedCache(cache_path, mode=cache_mode),
        ))
        attempt("shadow_replay", lambda: replay(
            root, output / "shadow", originals=output / "originals", cache=DerivedCache(cache_path, mode=cache_mode),
        ))
    else:
        for name in ("automated_quality", "shadow_replay"):
            record(name, {"status": "BLOCKED", "reason": "DOCUMENT_INPUTS_UNAVAILABLE"})

    if recovered["status"] == "COMPLETE" and recovered.get("missing") == 0:
        work = output / "formal-93"

        def rebuild_census():
            cutoff = json.loads((release / "census_release.json").read_bytes())["cutoff"]
            result = _run_formal(root, work, [
                "all", "--source-mode", "offline", "--as-of", cutoff,
                "--source-replay", str(release / "source_acquisition.json"),
                "--replay-assets", recovered["assets"], "--tessdata", str(tessdata),
            ], rscript)
            if result["status"] == "COMPLETE":
                verification = _compare_census(release, Path(result["run"]), Path(result["published_census"]))
                result.update(status=verification["status"], verification=verification)
            return result

        attempt("formal_93", rebuild_census)
    else:
        record("formal_93", {"status": "BLOCKED", "reason": recovered["status"],
                             "expected": recovered.get("expected"), "verified": recovered.get("verified"),
                             "missing": recovered.get("missing"), "impact": recovered.get("impact_path")})

    if database is None:
        work = output / "formal-phase22"
        phase22 = attempt("formal_phase22", lambda: _run_formal(root, work, [
            "rebuild", "--as-of", "2026-11-05", "--snapshot-lock", str(root / PHASE22_LOCK),
        ], rscript))
        if phase22["status"] == "COMPLETE":
            database, formal_run = work / "canonical.sqlite", Path(phase22["run"])
    else:
        record("formal_phase22", {"status": "SUPPLIED_REFERENCE", "run": str(Path(formal_run).resolve()),
                                  "database": str(Path(database).resolve())})
    if database is not None:
        panel_output = output / "resource-panel" / Path(formal_run).resolve().name
        attempt("formal_resource_panel", lambda: bridge(root, database, formal_run, panel_output, rscript=rscript))
    else:
        record("formal_resource_panel", {"status": "BLOCKED", "reason": "FORMAL_REFERENCE_UNAVAILABLE"})

    failures = [name for name, result in stages.items()
                if result["status"] == "FAILED" or result["status"].endswith("DIFFERENCES")]
    blocked = [name for name, result in stages.items() if result["status"].startswith("BLOCKED")]
    report.update(status="FAILED" if failures else "COMPLETE_WITH_GAPS" if blocked else "COMPLETE",
                  failed_stages=failures, blocked_stages=blocked)
    atomic_json(output / "validation.json", report)
    return report
