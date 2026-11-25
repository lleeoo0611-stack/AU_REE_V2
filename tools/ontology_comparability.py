"""Offline resource-comparability experiment against frozen Phase 22 exports."""
import argparse
import csv
import hashlib
import json
from collections import Counter, defaultdict
from functools import lru_cache
from itertools import combinations
from pathlib import Path

import pymupdf

from au_ree_v2.tabular import read_csv
from tools import category_grades, normalization_comparison

MODEL = Path(__file__).with_name("ontology_resource_model.json")
DEFAULT_RELEASE = Path("results/ree-project-census/nlp-retrieval-20261126")
DEFAULT_ASSETS = Path("work/coverage-locked-kit/assets")
DEFAULT_OUTPUT = Path("results/ontology-comparability-20261126")


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def assert_facts(target, additions):
    for key, value in additions.items():
        if value in ("", None) or (key in target and target[key] != value):
            raise ValueError(f"Empty or conflicting assertion for {key}")
        target[key] = value


def enrich(rows, observations, model, assets):
    @lru_cache(maxsize=None)
    def pdf_path(sha):
        path = assets / sha
        if digest(path) != sha:
            raise ValueError(f"Source checksum mismatch {sha}")
        return path

    @lru_cache(maxsize=None)
    def page_text(sha, page):
        with pymupdf.open(pdf_path(sha)) as pdf:
            return " ".join(pdf[page - 1].get_text(sort=True).split())

    signatures = {}
    result = []
    for row in rows:
        obs = observations[row["observation_id"]]
        st, sha = obs["statement_id"], obs["source_sha256"]
        pdf_path(sha)
        rules = model["scope_assertions"].get(st)
        facets = {}
        if rules:
            if sha != rules["source_sha256"]:
                raise ValueError(f"Curated assertion points to a different document for {st}")
            for rule in rules["facts"]:
                if rule["scope_contains"] not in obs["scope"]:
                    raise ValueError(f"Curated assertion no longer matches the selected scope for {st}")
                assert_facts(facets, rule["set"])
            for rule in model["pdf_assertions"].get(st, []):
                if rule["contains"] not in page_text(sha, rule["page"]):
                    raise ValueError(f"Missing source anchor: {st}, p{rule['page']}")
                assert_facts(facets, rule["set"])
        duplicate = model["repeated_table"]
        if st in duplicate["statements"]:
            page = page_text(sha, duplicate["page"])
            if not all(fragment in page for fragment in duplicate["required_fragments"]):
                raise ValueError(f"Repeated table identifier missing from {st}")
            signatures[st] = hashlib.sha256(page.encode()).hexdigest()
        record = {**row, **{key: obs[key] for key in ("statement_id", "variable", "scope", "effective_date",
                      "date_role", "publication_date", "original_estimate_period", "locator", "physical_page")},
                  "facets": facets}
        result.append(record)
    if set(signatures) != set(model["repeated_table"]["statements"]) or len(set(signatures.values())) != 1:
        raise ValueError("Could not verify that both original pages reproduce the same identified MRE")
    for row in result:
        row["repeated_source_table"] = signatures.get(row["statement_id"])
    return result


def check_facets(keys, a, b):
    conflict, unknown = [], []
    for key in keys:
        if key == "cutoff_level" and a.get("cutoff_metric") != b.get("cutoff_metric"):
            # Numerical thresholds for different quantities/currencies cannot be subtracted.
            continue
        left, right = a.get(key), b.get(key)
        if left is None or right is None:
            unknown.append(key)
        elif left != right:
            conflict.append(key)
    return conflict, unknown


def verdict(conflicts, unknowns):
    if conflicts:
        return "CONFLICT"
    return "UNRESOLVED" if unknowns else "MATCH"


def compare_pair(left, right, model):
    """Compare one pair of observations for the same Census column at three claim levels."""
    if left["column"] != right["column"] or left["project_id"] == right["project_id"]:
        raise ValueError("A comparison requires two project IDs and the same field")
    a, b = left["facets"], right["facets"]
    variable = left["variable"]
    if variable != right["variable"]:
        raise ValueError("Different quantity kinds within one field")
    common = left["category"] == right["category"] and left["census_unit"] == right["census_unit"]
    repeated = bool(left["repeated_source_table"] and left["repeated_source_table"] == right["repeated_source_table"]
                    and left["effective_date"] == right["effective_date"])
    nominal_c, nominal_u = check_facets(model["nominal_required"][variable], a, b)
    if not common:
        nominal_c.append("resource_category_or_quantity_unit")
    extra = list(model["strict_extra"])
    if a.get("cutoff_metric") == b.get("cutoff_metric"):
        extra.extend(model["conditional_strict_facets"].get(a.get("cutoff_metric"), []))
    strict_c, strict_u = check_facets(extra, a, b)
    nominal = verdict(nominal_c, nominal_u)
    strict = verdict(nominal_c + strict_c, nominal_u + strict_u)
    result = {"column": left["column"], "baseline": "CANDIDATE" if common else "INCOMPATIBLE_CATEGORY_OR_UNIT",
              "descriptive_status": "DUPLICATE_SCOPE" if repeated else ("CANDIDATE" if common else "CONFLICT"),
              "nominal_status": "DUPLICATE_SCOPE" if repeated else nominal,
              "strict_status": "SAME_STATEMENT" if repeated else strict,
              "nominal_conflicts": "|".join(nominal_c), "nominal_unknowns": "|".join(nominal_u),
              "strict_extra_conflicts": "|".join(strict_c), "strict_extra_unknowns": "|".join(strict_u),
              "vintage": "SAME_RECORDED_DATE" if left["effective_date"] == right["effective_date"] else "DIFFERENT_RECORDED_DATES"}
    for side, row in (("left", left), ("right", right)):
        for key in ("project_id", "observation_id", "effective_date", "category"):
            result[f"{side}_{key}"] = row[key]
    return result


def count_status(pairs):
    return {key: dict(sorted(Counter(r[key] for r in pairs).items()))
            for key in ("baseline", "descriptive_status", "nominal_status", "strict_status")}


def oxide_controls(release, assets, model, direct):
    # This existing verification re-parses both PDF tables, including the 1,000 ppm cutoff.
    original = category_grades.run(release, assets)
    peer = next(r for r in direct if r["statement_id"] == category_grades.SPLINTER_STATEMENT)
    results = []
    for row in original["pairs"]:
        left = {"project_id": category_grades.JUPITER_ID, "observation_id": row["jupiter_observation"],
                "column": row["oxide"], "variable": "oxide_grade", "category": original["category"],
                "census_unit": original["unit"], "effective_date": original["jupiter_statement_date"],
                "facets": {"scope_extent": "PROJECT", "cutoff_metric": "TREO", "cutoff_level": 1000,
                           "oxide": row["oxide"]}, "repeated_source_table": None}
        right = {**left, "project_id": category_grades.SPLINTER_ID, "observation_id": row["splinter_observation"],
                 "effective_date": original["splinter_statement_date"], "facets": {**peer["facets"], "oxide": row["oxide"]}}
        compared = compare_pair(left, right, model)
        results.append({**compared, "left_weighted_ppm": row["weighted_ppm"],
                        "right_reported_ppm": row["splinter_ppm"], "left_pdf_sha256": original["jupiter_sha256"],
                        "left_pages": "3|19", "right_pdf_sha256": original["splinter_sha256"], "right_pages": "2",
                        "source_note": original["limit"]})
    return results


def compare_release(release=DEFAULT_RELEASE, assets=DEFAULT_ASSETS, model_path=MODEL):
    release, assets, model_path = Path(release), Path(assets), Path(model_path)
    model = json.loads(model_path.read_text(encoding="utf-8-sig"))
    base = normalization_comparison.compare_release(release)
    observations = {r["observation_id"]: r for r in read_csv(release / "resource_statement_observations.csv")}
    enriched = enrich(base["observations"], observations, model, assets)
    pairs = []
    for left, right in combinations(sorted(enriched, key=lambda row: (row["column"], row["project_id"])), 2):
        if left["column"] == right["column"] and left["project_id"] != right["project_id"]:
            pairs.append(compare_pair(left, right, model))
    eligible = [r for r in pairs if r["baseline"] == "CANDIDATE"]
    distinct = {(r["left_project_id"], r["right_project_id"]) for r in eligible}
    if len(distinct) != base["distinct_project_pairs_any_field"]["census_unit"]:
        raise ValueError("The baseline cohort drifted from the unit-normalization experiment")
    by_field = defaultdict(list)
    for row in eligible:
        by_field[row["column"]].append(row)
    files = ["REE project census.csv","resource_statement_lineage.csv","resource_statement_observations.csv",
             "source_selection.csv","census_release.json"]
    oxide = oxide_controls(release, assets, model, enriched)
    return {"summary": {"experiment":"read-only-resource-comparability-v1","model_sha256":digest(model_path),
            "release_inputs_sha256": {name:digest(release / name) for name in files},
            "census_rows":len(read_csv(release / files[0])), "research_cutoff":json.loads((release/files[-1]).read_bytes())["cutoff"],
            "direct_observations":len(enriched),"projects":len({r["project_id"] for r in enriched}),
            "cross_project_field_pairs":len(pairs), "baseline_field_pairs":len(eligible),
            "baseline_distinct_project_pairs":len(distinct),"all_field_pairs":count_status(pairs),
            "among_baseline_candidates":count_status(eligible),"among_baseline_by_field":{k:count_status(v) for k,v in by_field.items()},
            "descriptive_distinct_project_pairs":len({(r["left_project_id"],r["right_project_id"]) for r in eligible
                                                       if r["descriptive_status"] == "CANDIDATE"}),
            "oxide_extension_preexisting_comparisons":len(oxide),"census_values_written":0},
            "observations":enriched, "pairs":pairs, "oxide_extension":oxide}


def write_results(report, directory=DEFAULT_OUTPUT):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    for key in ("summary", "observations"):
        (directory / f"resource_{key}.json").write_text(
            json.dumps(report[key], ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    for key in ("pairs", "oxide_extension"):
        rows = report[key]
        with (directory / f"resource_{key}.csv").open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release", type=Path, default=DEFAULT_RELEASE)
    parser.add_argument("--assets", type=Path, default=DEFAULT_ASSETS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    write_results(compare_release(args.release, args.assets), args.output)
