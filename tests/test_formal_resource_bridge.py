"""Regression coverage for the read-only R1/S1 formal bridge."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from au_ree_v2.evidence import resource_statement_metrics
from au_ree_v2.formal_resource_bridge import PANEL, VERSION, _Excluded, _SelectedEvidence, _compare, _publish
from au_ree_v2.store import canonical, connect, filehash


class FormalBridgeTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        original = self.root / "report.html"
        original.write_text("<table><tr><td>5.0 Mt</td><td>1.0 % TREO</td></tr></table>", encoding="utf-8")
        self.source = {
            "key": "primary", "sha256": filehash(original), "path": original.name, "kind": "html",
            "publication_date": "2020-01-03", "available_date": "2020-01-04", "acquired_at": "2020-01-04T00:00:00Z",
        }
        self.db = connect(":memory:")
        self.addCleanup(self.db.close)
        self.db.execute("INSERT INTO sources VALUES(?,?,?,?,?,?,?,?)",
                        (self.source["sha256"], "primary", "https://example.test/report", self.source["publication_date"],
                         self.source["acquired_at"], original.name, "html", "{}"))
        self.db.execute("INSERT INTO entities VALUES(?,?,?,?)", ("project", "PROJECT", "p", "01"))
        self.db.execute("INSERT INTO entities VALUES(?,?,?,?)", ("other", "PROJECT", "p", "02"))
        self.configuration = {"verified_claim_ids": ["ore", "grade", "contained", "composition"],
                              "research": {"evidence_resolution": {"document_pipeline": {"validation_version": "test"}}}}
        self.scope = "Project resource in source report"
        self.effective_date = "2019-12-31"
        self.add_observation("ore", "ore_mt", 5, "Mt")
        self.add_observation("grade", "grade", 1, "%")
        self.add_observation("contained", "contained_treo_kt", 50, "kt TREO")
        self.add_observation("composition", "magnet_reo_share_pct", 25, "%",
                             basis="PrNdDyTb_OXIDES_OVER_TREO")

    def add_observation(self, identifier, variable, value, unit, *, basis="TREO"):
        raw = {"original_token": str(value), "original_unit": unit,
               "material_basis": "RESOURCE_BULK_ORE", "rounding_half_width": 0.05}
        self.db.execute(
            "INSERT INTO observations VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (identifier, "project", variable, value, unit, basis, self.scope, "statement", "INFERRED",
             self.effective_date, self.source["sha256"], "Source table", "AUTO_VALIDATED", "[]", canonical(raw),
             "normalization-v1"),
        )

    def evidence(self, cutoff="2020-02-01", snapshot=None):
        return _SelectedEvidence(self.db, self.root, self.configuration,
                                 [snapshot or self.source], cutoff, {"project": "project", "other": "other"})

    def selected(self, evidence):
        rows = [evidence.fact(identifier, "project") for identifier in ("ore", "grade", "contained")]
        return {"scope": self.scope, "date": self.effective_date, "source_sha": self.source["sha256"],
                "obs_ids": ["ore", "grade", "contained"], "statement_id": "statement",
                **resource_statement_metrics(*rows)}

    def test_existing_formal_inventory_and_canonical_provenance_remain_exact(self):
        evidence = self.evidence()
        selected = self.selected(evidence)
        values, rows, method = evidence.resource("project", "project", selected)
        self.assertEqual(values["contained_treo_kt"], 50)
        self.assertEqual(method, "REPORTED_CONTAINED_TREO")
        self.assertEqual(evidence.trace(rows[1])["canonical_observation"]["original_value"], "1")
        self.assertEqual(evidence.trace(rows[1])["source"]["available_date"], "2020-01-04")
        self.assertEqual(evidence.trace(rows[1])["canonical_observation"]["evidence"]["locator"], "Source table")
        with self.assertRaisesRegex(_Excluded, "SELECTED_RESOURCE_VALUE_OR_ROUNDING_MISMATCH"):
            evidence.resource("project", "project", {**selected, "contained_treo_kt": 51})
        self.db.execute("UPDATE observations SET scope='Other estimate' WHERE obs_id='grade'")
        with self.assertRaisesRegex(_Excluded, "SELECTED_RESOURCE_STATEMENT_CONTEXT_CONFLICT"):
            evidence.resource("project", "project", selected)

    def test_missing_mismatch_dates_identity_and_stale_approval_are_local(self):
        with self.assertRaisesRegex(_Excluded, "CANONICAL_PROJECT_OBSERVATION_IDENTITY_MISMATCH"):
            self.evidence().fact("ore", "other")
        with self.assertRaisesRegex(_Excluded, "SOURCE_AFTER_CUTOFF"):
            self.evidence(cutoff="2020-01-01").fact("ore", "project")
        with self.assertRaisesRegex(_Excluded, "LOCKED_SOURCE_UNAVAILABLE"):
            self.evidence(snapshot={**self.source, "path": "missing.html"}).fact("ore", "project")
        bad = self.root / "other.html"
        bad.write_text("Another edition.", encoding="utf-8")
        with self.assertRaisesRegex(_Excluded, "SOURCE_HASH_MISMATCH"):
            self.evidence(snapshot={**self.source, "path": bad.name}).fact("ore", "project")
        self.configuration["verified_claim_ids"].remove("ore")
        with self.assertRaisesRegex(_Excluded, "OBSERVATION_NOT_IN_FORMAL_CLAIMS_EDITION"):
            self.evidence().fact("ore", "project")
        self.assertEqual(self.evidence().fact("grade", "project")["value"], 1)

    def test_composition_requires_existing_selection_and_same_resource_scope(self):
        evidence = self.evidence()
        selected = self.selected(evidence)
        contract = {"variables": ["magnet_reo_share_pct"], "unit": "%", "basis": ["PrNdDyTb_REO_DIV_TREO"]}
        bound = {"composition": {"reason": "VALID_RAW_EVIDENCE", "project_id": "project",
                                 "source_sha256": self.source["sha256"], "basis": "PrNdDyTb_REO_DIV_TREO"}}
        decision = {"status": "SELECTED", "value": "25", "evidence_ids": '["composition"]',
                    "provenance": '{"evidence_id":"composition"}'}
        actual, _, _ = evidence.composition("project", selected, decision, bound, contract)
        self.assertEqual(actual, 25)
        with self.assertRaisesRegex(_Excluded, "NO_COMPATIBLE_EVIDENCE"):
            evidence.composition("project", selected, {"status": "NO_COMPATIBLE_EVIDENCE"}, bound, contract)
        with self.assertRaisesRegex(_Excluded, "FORMAL_COMPOSITION_SCOPE_VALUE_OR_BASIS_MISMATCH"):
            evidence.composition("project", {**selected, "scope": "Other resource"}, decision, bound, contract)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM observations").fetchone()[0], 4)

    def test_comparison_keeps_identifiers_text_and_extra_rows_exact(self):
        old = [{"project_id": "AU-A", "score": "0.5", "scope": "A"}]
        new = [{"project_id": "AU-A", "score": "0.5000000000001", "scope": "A"}]
        self.assertEqual(_compare(old, new, ("project_id",), ("score",)), [])
        new[0]["scope"] = "B"
        self.assertEqual(_compare(old, new, ("project_id",), ("score",))[0]["changed_fields"],
                         {"scope": {"before": "A", "after": "B"}})
        new.append({"project_id": "AU-B", "score": "1", "scope": "C"})
        self.assertEqual(len(_compare(old, new, ("project_id",), ("score",))), 2)

    def test_republication_replaces_its_derivatives_only(self):
        output = self.root / "output"
        staging = self.root / "stage"
        staging.mkdir()

        def products(value):
            result = staging / "result"
            result.mkdir()
            report = result / "science.json"
            report.write_text(value, encoding="utf8")
            (result / "bridge_receipt.json").write_text(canonical({
                "version": VERSION, "panel": PANEL, "artifact_sha256": {report.name: filehash(report)},
            }), encoding="utf8")
            return result

        _publish(output, products("old"), staging)
        _publish(output, products("new"), staging)
        self.assertEqual((output / "science.json").read_text(), "new")
        (output / "unrelated.txt").write_text("user-maintained output", encoding="utf8")
        with self.assertRaisesRegex(ValueError, "FORMAL_BRIDGE_TARGET_CONTAINS_UNTRACKED_FILES"):
            _publish(output, products("another"), staging)
        self.assertEqual((output / "science.json").read_text(), "new")
        self.assertEqual((output / "unrelated.txt").read_text(), "user-maintained output")
