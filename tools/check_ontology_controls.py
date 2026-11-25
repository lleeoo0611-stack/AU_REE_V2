"""Score frozen source-page controls against exported field pairs without reading the PDF kit."""
import argparse
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT / "data/validation/ontology_reference_20261126.json"
RESULTS = ROOT / "results/ontology-comparability-20261126"


def pair_key(field, left_id, right_id):
    return field, *sorted((left_id, right_id))


def assess(reference, directory):
    index = {}
    for filename in ("resource_pairs.csv", "resource_oxide_extension.csv"):
        with (directory / filename).open(encoding="utf-8-sig", newline="") as stream:
            for row in csv.DictReader(stream):
                key = pair_key(row["column"], row["left_observation_id"], row["right_observation_id"])
                if key in index:
                    raise ValueError(f"Duplicate field pair {key}")
                index[key] = row
    outcomes = []
    seen = set()
    for control in json.loads(reference.read_bytes())["controls"]:
        left, right = control["left"], control["right"]
        key = pair_key(control["field"], left["observation_id"], right["observation_id"])
        if key in seen:
            raise ValueError(f"Duplicate control for {key}")
        seen.add(key)
        row = index[key]
        if {row["left_project_id"], row["right_project_id"]} != {left["project_id"], right["project_id"]}:
            raise ValueError(f"Project identifiers disagree for {control['id']}")
        if row["descriptive_status"] == "DUPLICATE_SCOPE":
            comparison = "DUPLICATE_SCOPE"
        elif row["descriptive_status"] != "CANDIDATE":
            comparison = "EXCLUDED"
        elif row["nominal_status"] == "MATCH":
            comparison = "QUALIFIED_REPORTING_BASIS"
        else:
            comparison = "DESCRIPTIVE_ONLY"
        expected = control["expected"]
        status = row["strict_status"]
        outcomes.append({
            "control_id": control["id"], "cohort": control["cohort"],
            "expected_comparison": expected["comparison"], "observed_comparison": comparison,
            "expected_strict": expected["operational_equivalence"], "observed_strict": status,
            "agrees": comparison == expected["comparison"] and status == expected["operational_equivalence"],
        })
    if not outcomes:
        raise ValueError("Empty source-control set")
    return outcomes


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", type=Path, default=REFERENCE)
    parser.add_argument("--results", type=Path, default=RESULTS)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    outcomes = assess(args.reference, args.results)
    if args.output:
        with args.output.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=outcomes[0].keys(), lineterminator="\n")
            writer.writeheader()
            writer.writerows(outcomes)
    matched = sum(r["agrees"] for r in outcomes)
    print(f"{matched}/{len(outcomes)} field-pair controls agree on both comparison levels.")
    raise SystemExit(int(matched != len(outcomes)))
