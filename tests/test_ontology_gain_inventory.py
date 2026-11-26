"""Sampling and evidence identities for the frozen pre-selection pilot."""
import json
import unittest
from collections import Counter
from pathlib import Path

from tools.ontology_gain_inventory import OUTPUT, connected_split, evidence_identity, group_and_sample, stable_id


class FreezeTests(unittest.TestCase):
    def test_family_components_block_projects_and_shared_sources(self):
        records = [{"project_id":p,"report_families":f} for p,f in [
            ("A",["sha1"]),("A",["sha2"]),("B",["sha2","reprint"]),("C",["reprint"]),("D",["sha4"])]]
        connected_split(records, {"A"})
        self.assertEqual(len({r["group_id"] for r in records[:4]}), 1)
        self.assertEqual({r["split"] for r in records[:4]}, {"DEVELOPMENT"})
        self.assertEqual(records[-1]["split"], "HOLDOUT")

    def test_registry_can_assign_a_target_without_an_equivalence_decision(self):
        rows = [dict(candidate_id=str(i), variable="reported_resource_thm_treo_pct",target_variable="grade",
                     source_kind="pdf",split="HOLDOUT") for i in range(7)]
        first = group_and_sample(rows)
        self.assertEqual(first, group_and_sample(rows[::-1]))
        self.assertEqual(len(first), 3)
        self.assertEqual(first[0]["stratum"], "grade/related/pdf")

    def test_same_page_and_number_do_not_establish_independent_observation_identity(self):
        r=dict(entity_id="A",project_id="A",source_sha256="source",statement_id="statement",variable="grade",
               value=0.11,unit="%",basis="TREO",category="INFERRED",effective_date="2025-07-12",
               physical_page=2,source_page_sha256="common_page",scope="south",locator="Table 1, row 3",
               material_basis=None,denominator_basis=None,observation_id="observation")
        for changed in (dict(project_id="B",entity_id="B"),dict(locator="Table 1, row 4")):
            self.assertNotEqual(evidence_identity(r,{}, "page"),evidence_identity({**r,**changed}, {}, "page"))

    def test_checked_in_freeze_and_source_packet(self):
        m = json.loads((OUTPUT/"inventory_manifest.json").read_bytes())
        def contents(name):
            return [json.loads(s) for s in (OUTPUT/name).read_text(encoding="utf-8").splitlines()]
        records, sample = contents("candidates.jsonl"),contents("review_sample.jsonl")
        ids = [r["candidate_id"] for r in records]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(m["candidate_id_set_sha256"],stable_id(sorted(ids)))
        self.assertEqual(m["sample_id_set_sha256"],stable_id(sorted(r["candidate_id"] for r in sample)))
        self.assertFalse(any("selection_role" in r or "source_gates" in r or "status" in r for r in sample))
        expected=group_and_sample(records)
        self.assertEqual([r["candidate_id"] for r in expected],[r["candidate_id"] for r in sample])
        self.assertEqual(dict(Counter(r["split"] for r in records)),m["candidate_counts"])
        self.assertTrue(any(r["inherited_selection_role"]=="NOT_PRESENT_IN_RELEASE_EXPORT" for r in records))
        def split_set(split,key):
            return {r[key] for r in records if r["split"]==split}
        for key in ("project_id","group_id","source_sha256"):
            self.assertFalse(split_set("DEVELOPMENT",key)&split_set("HOLDOUT",key))
