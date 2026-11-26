"""Freeze study membership, original evidence, component split and primary review identities."""
import argparse
import hashlib
import json
from pathlib import Path

FIELDS = ("observation_id", "project_id", "source_sha256", "physical_page", "statement_id", "scope",
          "category", "effective_date", "publication_date", "variable", "value", "unit", "basis",
          "original_token", "original_unit", "target_variable", "target_column", "target_unit",
          "material_basis", "denominator_basis", "use_id", "use_definition_version")


def freeze(directory):
    meta = json.loads((directory / "inventory_manifest.json").read_bytes())
    review_ids = {json.loads(line)["candidate_id"] for line in
                  (directory / "review_sample.jsonl").read_text(encoding="utf-8").splitlines()}
    entries = []
    for line in (directory / "candidates.jsonl").read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        data = json.dumps({f: row[f] for f in FIELDS}, ensure_ascii=False, sort_keys=True,
                          separators=(",", ":")).encode("utf-8")
        entries.append({"candidate_id": row["candidate_id"], "evidence_sha256": hashlib.sha256(data).hexdigest(),
                        "component": row["group_id"], "split": row["split"], "stratum": row["stratum"],
                        "primary_review": row["candidate_id"] in review_ids})
    ids = {r["candidate_id"] for r in entries}
    if len(ids) != len(entries) or not review_ids <= ids:
        raise ValueError("Duplicate observation use or unregistered primary review")
    return {"source_sha256": meta["sqlite_sha256"], "logical_sha256": meta["logical_sha256"],
            "identity_map_sha256": meta["project_identity_sha256"], "cutoff": meta["cutoff"],
            "seed": meta["seed"], "sampling": meta["sample_design"], "frozen_fields": FIELDS,
            "primary_analysis": "Raw and stratum-specific counts on the predeclared reviewed holdout only. "
                                "Review disagreements after first run separately. No population accuracy estimate.",
            "entries": sorted(entries, key=lambda r: r["candidate_id"])}


def verify(directory, create=False):
    file = directory / "preregistered_cohort.json"
    encoded = (json.dumps(freeze(directory), ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()
    if create and not file.exists():
        with file.open("xb") as stream:
            stream.write(encoded)
    if file.read_bytes() != encoded:
        raise ValueError("The frozen evidence, use, split or primary review IDs changed")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--create", action="store_true")
    args = parser.parse_args()
    verify(args.directory, args.create)
