"""Replay a source-bound development review through a small SKOS/SHACL profile.

Run from the repository root with python -m tools.evaluate_ontology.
This is a comparison of representations/constraints, not a blind NLP benchmark.
"""

import argparse
import json
from collections import Counter
from importlib.metadata import version
from pathlib import Path

from au_ree_v2.ontology import assess_context, load_vocabulary, stable_ntriples, vocabulary_graph
from au_ree_v2.store import filehash
from au_ree_v2.tabular import read_csv
from tools.compare_census_release import release
from tools.evaluate_normalization import check_cases, check_controls, document_pages
from tools.normalization_comparison import FIELDS, _pair_report, compare_release


ROOT = Path(__file__).resolve().parents[1]
RELEASE = "results/ree-project-census/gap173-20261122"
REVIEW = "results/normalization-pilot-20261125/case_review.json"
FIXTURE = "tests/fixtures/ontology_review_cases.json"
VOCABULARY = "config/ontology/comparability_v1.json"


def verify_fixture(fixture, review, review_sha):
    if fixture.get("schema_version") != "ontology-review-cases-v1" or fixture.get("source_review_sha256") != review_sha:
        raise ValueError("Semantic annotations must bind the exact original review")
    seen_ids, seen_refs = set(), set()
    for case in fixture["cases"]:
        if case["case_id"] in seen_ids:
            raise ValueError("Duplicate ontology case_id")
        seen_ids.add(case["case_id"])
        control = "control_index" in case
        key = "control_index" if control else "original_review_index"
        if ("original_review_index" in case) == control:
            raise ValueError("Cases need exactly one review or control index")
        index = case[key]
        source = review["controls" if control else "cases"][index]
        reference = (control, index)
        if reference in seen_refs:
            raise ValueError("Duplicate review group; do not inflate independent samples")
        seen_refs.add(reference)
        if (case["project_id"] != source["project_id"] or case["source_pages"] != source["pages"]
                or case["evidence_note"] != source["review"]
                or case["expected_admissible"] is not control
                or case["affected_cells"] != (1 if control else len(source["columns"]))):
            raise ValueError("Fixture lost original source/index/review binding")
        if case["annotation_status"] != "DEVELOPMENT_REVIEW_DERIVED_NOT_BLIND":
            raise ValueError("Development annotations cannot be relabelled as blind gold")
    expected = {(False, i) for i in range(len(review["cases"]))} | {(True, i) for i in range(len(review["controls"]))}
    if seen_refs != expected:
        raise ValueError("Fixture omitted reviewed groups or controls")


def evaluate(root=ROOT):
    root = Path(root)
    folder = root / RELEASE
    review = json.loads((root / REVIEW).read_bytes())
    fixture = json.loads((root / FIXTURE).read_bytes())
    vocabulary = load_vocabulary(root / VOCABULARY)
    verify_fixture(fixture, review, filehash(root / REVIEW))
    current = release(folder)
    refs, _ = document_pages(folder, review, assets=None)
    baseline_review = check_cases(folder, current, review, refs)
    observations = read_csv(folder / "resource_statement_observations.csv")
    observations_by_id = {row["observation_id"]: row for row in observations}
    baseline_controls = check_controls(current, observations, review, refs)
    baseline_units = compare_release(folder)
    data_graph = vocabulary_graph(vocabulary)
    shapes_graph = type(data_graph)()
    assessments = []
    for case in fixture["cases"]:
        assessed = assess_context(case["observed_context"], case["target_context"], vocabulary,
                                  case_id=case["case_id"], source_pages=case["source_pages"])
        data_graph += assessed["data_graph"]
        shapes_graph += assessed["shapes_graph"]
        # Existing review and control checks above validate the frozen baseline.
        # No gold label, reason text or case name enters assess_context().
        baseline_admissible = "control_index" in case
        assessments.append({**assessed["assessment"], "project_id": case["project_id"],
                            "expected_admissible": case["expected_admissible"],
                            "baseline_admissible": baseline_admissible,
                            "agrees_with_baseline": assessed["assessment"]["admissible"] == baseline_admissible,
                            "affected_cells": case["affected_cells"],
                            "original_review_index": case.get("original_review_index"),
                            "control_index": case.get("control_index")})

    # Reuse existing source/numeric/unit admission. The ontology representation
    # neither creates extra accepted resource values nor relaxes those gates.
    unit_rows = []
    for row in baseline_units["observations"]:
        variable, unit, _ = FIELDS[row["column"]]
        original = observations_by_id[row["observation_id"]]
        page = original["physical_page"]
        if original["source_sha256"] != row["source_sha256"] or not page.isdigit() or int(page) < 1:
            raise ValueError("Unit ontology export requires the original source/page binding")
        context = {"quantity_kind": variable, "resource_category": row["category"], "unit": row["census_unit"]}
        assessed = assess_context(context, {"quantity_kind": variable, "unit": unit}, vocabulary,
                                  case_id="unit-" + row["observation_id"],
                                  source_pages=[row["source_sha256"] + ":" + page])
        if not assessed["assessment"]["admissible"]:
            raise ValueError("Ontology representation rejected an already-verified unit contract")
        data_graph += assessed["data_graph"]
        shapes_graph += assessed["shapes_graph"]
        unit_rows.append(row)
    ontology_units = _pair_report(unit_rows)

    probes = []
    for index, mapping in enumerate(vocabulary["mappings"]):
        observed = {mapping["dimension"]: mapping["label"]}
        target = {mapping["dimension"]: mapping["concept"]}
        assessed = assess_context(observed, target, vocabulary, case_id=f"constructed-alias-{index}")
        expected = mapping["relation"] == "exactMatch"
        probes.append({"label": mapping["label"], "dimension": mapping["dimension"],
                       "declared_relation": mapping["relation"], "expected": expected,
                       "raw_literal_equal": observed == target,
                       "ontology_admissible": assessed["assessment"]["admissible"],
                       "status": assessed["assessment"]["status"]})
    paths = [REVIEW, FIXTURE, VOCABULARY] + [RELEASE + "/" + n for n in
             ("REE project census.csv", "field_status.csv", "field_provenance.csv", "followup_review.csv",
              "census_release.json", "source_selection.csv", "resource_statement_observations.csv",
              "resource_statement_lineage.csv")]
    code = ["src/au_ree_v2/ontology.py", "src/au_ree_v2/store.py", "src/au_ree_v2/tabular.py",
            "src/au_ree_v2/selection_rules.py", "tools/evaluate_ontology.py",
            "tools/evaluate_normalization.py", "tools/normalization_comparison.py", "tools/compare_census_release.py"]
    rejected = [a for a in assessments if not a["expected_admissible"]]
    positive = [a for a in assessments if a["expected_admissible"]]
    report = {
        "schema_version": "ontology-pilot-report-v1", "cutoff": review["cutoff"],
        "research_status": "DEVELOPMENT_REGRESSION_NOT_BLIND_VALIDATION",
        "input_sha256": {p: filehash(root / p) for p in paths},
        "code_sha256": {p: filehash(root / p) for p in code},
        "runtime": {p: version(p) for p in ("rdflib", "pyshacl")},
        "source_verification": {"census_manifest_verified": True, "review_source_selection_verified": True,
                                "pdf_bytes_reverified": False, "fresh_nlp_extraction": False},
        "comparison": {"review_groups": len(rejected), "positive_controls": len(positive),
                       "distinct_review_projects": len({a["project_id"] for a in assessments}),
                       "affected_original_held_cells": sum(a["affected_cells"] for a in rejected),
                       "existing_held_by_class": baseline_review["held_by_class"],
                       "existing_positive_controls_passed": baseline_controls,
                       "ontology_false_admissions": sum(a["admissible"] for a in rejected),
                       "ontology_positive_controls_passed": sum(a["admissible"] for a in positive),
                       "baseline_disagreements": sum(not a["agrees_with_baseline"] for a in assessments),
                       "ontology_status_counts": dict(sorted(Counter(a["status"] for a in assessments).items())),
                       "new_validated_census_cells": 0,
                       "scope": "One representative semantic check per known review group; not 32 independent tests"},
        "unit_compatibility": {
            "admitted_cells": len(unit_rows),
            "existing_pairs": baseline_units["distinct_project_pairs_any_field"],
            "ontology_pairs": ontology_units["distinct_project_pairs_any_field"],
            "increment_over_existing_census": ontology_units["distinct_project_pairs_any_field"]["census_unit"] - baseline_units["distinct_project_pairs_any_field"]["census_unit"],
            "scope": baseline_units["scope"],
            "conversion_owner": "EXISTING_VERIFIED_NORMALIZATION_RULES_NOT_NEW_ONTOLOGY_INFERENCE"},
        "constructed_mapping_probes": {"synthetic": True,
            "scope": "Vocabulary contract exercise, not measured real-document recall gain",
            "exact_aliases": sum(p["expected"] for p in probes),
            "exact_aliases_resolved": sum(p["expected"] and p["ontology_admissible"] for p in probes),
            "nonexact_relations_blocked": sum(not p["expected"] and not p["ontology_admissible"] for p in probes),
            "probes": probes},
        "assessments": assessments,
        "limitations": ["Semantic annotations are AI-assisted projections of an existing development review",
                        "No independent annotator, new company holdout or end-to-end NLP performance test",
                        "Context contracts are local use profiles, not full cross-project equivalence",
                        "No OWL sameAs merging, inferred missing values, or Resource-to-Reserve conversion",
                        "SHACL conformance checks declared constraints; it does not authenticate source truth"],
    }
    return report, {"evidence.nt": stable_ntriples(data_graph),
                    "shapes.nt": stable_ntriples(shapes_graph),
                    "vocabulary.nt": stable_ntriples(vocabulary_graph(vocabulary))}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    report, artifacts = evaluate(args.root)
    artifacts["ontology_report.json"] = json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    out = args.output_dir
    if out.exists():
        if not out.is_dir() or set(p.name for p in out.iterdir()) != set(artifacts) or any(
                (out / name).read_text(encoding="utf-8") != content for name, content in artifacts.items()):
            raise ValueError("Select a new output directory; previous experiment artifacts are immutable")
    else:
        out.mkdir(parents=True)
        for name, content in artifacts.items():
            (out / name).write_text(content, encoding="utf-8")
    print(json.dumps({"status": "COMPLETED", "comparison": report["comparison"],
                      "unit_compatibility": report["unit_compatibility"],
                      "output_dir": str(out)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
