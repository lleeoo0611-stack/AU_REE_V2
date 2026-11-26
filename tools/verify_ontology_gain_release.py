"""Verify a separately regenerated experimental run against the sealed publication."""
import argparse
import json
import subprocess
from pathlib import Path

from au_ree_v2.store import filehash
from tools.ontology_gain_freeze import verify as verify_cohort
from tools.verify_ontology_gain_review import verify as verify_review

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "results/ontology-gain-20261126"
HISTORICAL_HEAD = "cc36d77bcb7891a03b51b7e6111ca72d1dc2b382"
GENERATED = ("candidates.jsonl", "inventory_manifest.json", "review_sample.jsonl", "upstream_audit.json",
             "upstream_source_blocks.jsonl", "decisions.jsonl", "project_pairs.jsonl", "decision_audit.json",
             "disagreement_ids.json", "outcome_readiness.json", "metrics.json", "review_dispositions.jsonl")
EXPERIMENT_FILES = ("ontology_gain_compare", "ontology_gain_inventory", "ontology_gain_metrics",
                    "ontology_gain_freeze", "ontology_outcome_readiness", "verify_ontology_gain_review",
                    "verify_ontology_gain_release")


def check(directory, repeat, assets):
    verify_cohort(directory)
    files = {name: filehash(directory / name) for name in GENERATED}
    for name, checksum in files.items():
        if checksum != filehash(repeat / name):
            raise ValueError(f"Independent replay differs for {name}")
    review = {}
    for group, sample, refs in [
        ("presampled", "review_sample.jsonl", "source_review_primary.jsonl"),
        ("changed_admission", "review_additional.jsonl", "source_review_additional.jsonl"),
        ("changed_disposition", "review_dispositions.jsonl", "source_review_dispositions.jsonl"),
    ]:
        review[group] = {"sample_sha256": filehash(directory / sample), "reference_sha256": filehash(directory / refs),
                         **verify_review(directory / sample, directory / refs, assets)}
    legacy = ROOT / "results/ontology-pilot-20261126"
    protected = ["src", "R", "config/research.json", "config/eligibility_compatibility.json",
                 "results/ontology-pilot-20261126", "results/ree-project-census/gap173-20261122",
                 "tests/fixtures/ontology_review_cases.json"]
    subprocess.run(["git", "diff", "--quiet", HISTORICAL_HEAD, "--", *protected], check=True, cwd=ROOT)
    return {
        "reference_base": HISTORICAL_HEAD, "registration_commit": "2169f16",
        "presampled_review_commit": "e5d3a2d", "frozen_comparator_commit": "c0844e5",
        "byte_identical_replay_sha256": files, "source_review_verification": review,
        "experiment_code_sha256": {name: filehash(ROOT / "tools" / (name + ".py")) for name in EXPERIMENT_FILES},
        "historical_output_sha256": {p.name: filehash(p) for p in sorted(legacy.iterdir()) if p.is_file()},
        "unchanged_vs_parent": protected, "source": "same canonical frozen database and static original kit",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, default=OUTPUT)
    parser.add_argument("--repeat", type=Path, required=True)
    parser.add_argument("--assets", type=Path, required=True)
    args = parser.parse_args()
    report = check(args.results, args.repeat, args.assets)
    (args.results / "verification.json").write_text(json.dumps(report, sort_keys=True, indent=2) + "\n",
                                                   encoding="utf-8", newline="\n")
