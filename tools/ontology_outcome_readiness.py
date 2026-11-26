"""Check the existing event-prediction contract and the frozen milestone catalogue."""
import argparse
import json
from collections import Counter
from pathlib import Path

import pymupdf

from au_ree_v2.experiments import run_experiment
from au_ree_v2.milestones import _norm
from au_ree_v2.store import filehash
from au_ree_v2.tabular import read_csv

ROOT = Path(__file__).resolve().parents[1]
RELEASE = ROOT / "results/ree-project-census/gap173-20261122"
CONFIG = ROOT / "config/experiments/au_transfer.json"


def check(assets):
    config = json.loads(CONFIG.read_bytes())
    experiment = run_experiment(ROOT, CONFIG, dry_run=True)
    catalog = RELEASE / "milestone_events.csv"
    rows = read_csv(catalog)
    counts = Counter(row["event_type"] for row in rows)
    contexts = []
    for row in rows:
        if row["event_type"] not in {"FID", "MAIN_CONSTRUCTION", "COMMISSIONING",
                                     "RAMP_UP", "DESIGN_ACHIEVEMENT", "OPERATING_STATUS"}:
            continue
        sha = row["source_sha256"]
        path = assets / sha
        if not path.is_file() or filehash(path) != sha:
            raise ValueError(f"Missing or mismatched milestone source {sha}")
        page = int(row["physical_page"])
        with pymupdf.open(path) as document:
            text = _norm(document[page - 1].get_text())
        anchors = [row["project_marker"], *json.loads(row["markers"])]
        if not all(_norm(marker) in text for marker in anchors):
            raise ValueError(f"Could not verify source anchors {sha} p{page}")
        contexts.append({key: row[key] for key in (
            "event_id", "project_id", "event_type", "status", "scope_role", "scope", "actual_product",
            "event_date", "publication_date", "source_sha256", "source_url", "physical_page", "markers")})
    return {
        "scope": "Frozen milestone_events and the named input of the existing AU transfer experiment.",
        "release_sha256": filehash(catalog), "config_sha256": filehash(CONFIG),
        "experiment_contract_files": experiment["code"]["files"],
        "cutoff": config["evaluation_as_of"], "prediction_target": config["target"],
        "splits_requested": config["splits"], "splits_realized": len(experiment["splits"]),
        "configured_dataset": config["dataset"], "experiment_status": experiment["status"],
        "block_reason": experiment.get("block_reason"), "readiness": experiment["readiness"],
        "catalogue_records": len(rows), "catalogue_projects": len({r["project_id"] for r in rows}),
        "event_types": dict(sorted(counts.items())), "verified_context": contexts,
        "interpretation": (
            "A commissioning notice, a shipment of chloride ilmenite during ramp-up and operator withdrawal "
            "do not establish first commercial REE production. The frozen catalogue contains no dated "
            "FID or main construction start and no completed at-risk Project-by-date follow-up cohort. "
            "The existing outcome_mcda requires observed targets and historical features through each prediction "
            "time. No weights were fitted or used in production."),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assets", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = check(args.assets)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, sort_keys=True, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8", newline="\n")
