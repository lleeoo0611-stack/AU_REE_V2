"""Research-risk checks for explicit semantic contracts, not extraction accuracy."""

import copy
import json
import tempfile
import unittest
from pathlib import Path

from au_ree_v2.ontology import assess_context, load_vocabulary, normalize_context, stable_ntriples
from au_ree_v2.store import filehash
from tools.evaluate_ontology import FIXTURE, REVIEW, ROOT, VOCABULARY, evaluate, verify_fixture


class OntologyContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.vocabulary = load_vocabulary(ROOT / VOCABULARY)
        cls.fixture = json.loads((ROOT / FIXTURE).read_bytes())
        cls.review = json.loads((ROOT / REVIEW).read_bytes())

    def check(self, observed, target):
        return assess_context(observed, target, self.vocabulary)["assessment"]

    def test_review_projection_preserves_original_uses_without_false_admission(self):
        verify_fixture(self.fixture, self.review, filehash(ROOT / REVIEW))
        for case in self.fixture["cases"]:
            with self.subTest(case=case["case_id"]):
                result = self.check(case["observed_context"], case["target_context"])
                self.assertEqual(case["expected_admissible"], result["admissible"])

    def test_known_missing_chemical_basis_is_unknown_not_false_or_imputed(self):
        case = next(c for c in self.fixture["cases"] if c["case_id"] == "review-02")
        before = copy.deepcopy(case["observed_context"])
        result = self.check(before, case["target_context"])
        self.assertEqual("INSUFFICIENT_CONTEXT", result["status"])
        self.assertEqual(["chemical_basis"], result["missing_context"])
        self.assertEqual(before, case["observed_context"])

    def test_documented_exact_aliases_normalize_with_a_trace(self):
        result = self.check({"resource_kind": "Mineral Resource"}, {"resource_kind": "MINERAL_RESOURCE"})
        self.assertTrue(result["admissible"])
        self.assertEqual("DOCUMENTED_EXACT_LABEL", result["mapping_trace"][0]["rule"])
        result = self.check({"chemical_basis": "Nd₂O₃ + Pr₆O₁₁"}, {"chemical_basis": "ND2O3_PLUS_PR6O11"})
        self.assertTrue(result["admissible"])

    def test_close_broad_and_related_matches_never_promote_to_equivalence(self):
        for relation in ("closeMatch", "broadMatch", "relatedMatch"):
            vocabulary = copy.deepcopy(self.vocabulary)
            item = next(m for m in vocabulary["mappings"] if m["label"] == "NdPr")
            item["relation"] = relation
            result = assess_context({"chemical_basis": "NdPr"}, {"chemical_basis": "ND2O3_PLUS_PR6O11"}, vocabulary)["assessment"]
            self.assertEqual("INSUFFICIENT_CONTEXT", result["status"])
            self.assertFalse(result["admissible"])

    def test_same_percent_unit_does_not_merge_distinct_process_quantities(self):
        result = self.check({"unit": "%", "quantity_kind": "Leach extraction"},
                            {"unit": "%", "quantity_kind": "OVERALL_PROCESS_RECOVERY"})
        self.assertFalse(result["admissible"])
        self.assertEqual(["quantity_kind"], result["mismatched_context"])

    def test_case_sensitive_units_and_formulas_are_preserved(self):
        for dimension, left, right in [("unit", "Mt", "mt"), ("chemical_basis", "Co", "CO")]:
            self.assertFalse(self.check({dimension: left}, {dimension: right})["admissible"])

    def test_boolean_is_not_the_same_rdf_term_as_numeric_one(self):
        result = self.check({"mass_balance": True}, {"mass_balance": 1})
        self.assertEqual("CONTEXT_MISMATCH", result["status"])

    def test_empty_or_unknown_target_contract_cannot_pass_vacuously(self):
        for target in ({}, {"chemical_basis": None}, {"chemical_basis": "NdPr"}):
            with self.assertRaises(ValueError):
                self.check({}, target)

    def test_fixture_rejects_omitted_group_changed_label_and_changed_source(self):
        for mutation in ("omit", "label", "source"):
            fixture = copy.deepcopy(self.fixture)
            if mutation == "omit":
                fixture["cases"].pop()
            elif mutation == "label":
                fixture["cases"][0]["expected_admissible"] = True
            else:
                fixture["cases"][0]["source_pages"] = ["0" * 64 + ":1"]
            with self.assertRaises(ValueError):
                verify_fixture(fixture, self.review, filehash(ROOT / REVIEW))

    def test_duplicate_and_chained_mapping_requires_review(self):
        for chained in (False, True):
            vocabulary = copy.deepcopy(self.vocabulary)
            first = vocabulary["mappings"][0]
            new = dict(first, label=first["concept"] if chained else first["label"], concept="OTHER")
            vocabulary["mappings"].append(new)
            with tempfile.TemporaryDirectory() as temp:
                path = Path(temp) / "vocabulary.json"
                path.write_text(json.dumps(vocabulary))
                with self.assertRaises(ValueError):
                    load_vocabulary(path)

    def test_evidence_locators_and_graphs_are_stable_and_round_trip(self):
        from rdflib import Graph
        observed = {"period": "FIRST_FIVE_YEARS", "note": "line one\nline two"}
        first = assess_context(observed, {"period": "WHOLE_PLAN"}, self.vocabulary,
                               source_pages=["a" * 64 + ":4"])
        second = assess_context(dict(reversed(list(observed.items()))), {"period": "WHOLE_PLAN"}, self.vocabulary,
                                source_pages=["a" * 64 + ":4"])
        self.assertEqual(first["assessment"], second["assessment"])
        for key in ("data_graph", "shapes_graph"):
            text = stable_ntriples(first[key])
            self.assertEqual(text, stable_ntriples(second[key]))
            self.assertEqual(len(first[key]), len(Graph().parse(data=text, format="nt")))
        with self.assertRaises(ValueError):
            assess_context(observed, {"period": "WHOLE_PLAN"}, self.vocabulary, source_pages=["a:4"])

    def test_unrecognized_context_type_cannot_be_silently_coerced(self):
        for value in (["Nd", "Pr"], {"value": "Nd"}, float("nan")):
            with self.assertRaises(ValueError):
                normalize_context({"chemical_basis": value}, self.vocabulary)

    def test_all_exported_review_and_unit_nodes_keep_source_provenance(self):
        from rdflib import Graph, Namespace
        from rdflib.namespace import RDF
        report, artifacts = evaluate(ROOT)
        graph = Graph().parse(data=artifacts["evidence.nt"], format="nt")
        ns = Namespace(self.vocabulary["namespace"])
        prov = Namespace("http://www.w3.org/ns/prov#")
        nodes = list(graph.subjects(RDF.type, ns.EvidenceContext))
        self.assertEqual(80, len(nodes))
        self.assertTrue(all(list(graph.objects(node, prov.wasDerivedFrom)) for node in nodes))
        self.assertEqual(0, report["comparison"]["baseline_disagreements"])
        self.assertEqual(0, report["unit_compatibility"]["increment_over_existing_census"])


if __name__ == "__main__":
    unittest.main()
