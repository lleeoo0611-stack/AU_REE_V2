from dataclasses import replace
from decimal import Decimal
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest

from au_ree_v2.observation_pipeline import canonical_resource_observation, raw_from_candidate
from au_ree_v2.observation_schema import (
    AnalysisFeature, EvidenceAnchor, ManualDecision, NormalizedObservation, RawObservation, SemanticAssessment,
    ValidatedObservation, assessment_from_payload, normalized_from_payload, payload, raw_from_payload,
)
from au_ree_v2.observation_store import ObservationWorkspace, open_observation_workspace
from au_ree_v2.store import canonical, connect, filehash


SHA = "a" * 64


class ObservationSchemaTests(unittest.TestCase):
    def test_typed_layers_and_science_context_are_independent(self):
        anchor = EvidenceAnchor("report", SHA, 2, table=0, row=0, column=2, quote="1000")
        raw = RawObservation("obs", "project", "grade", "RESOURCE", anchor, "parser-v1", "1000", "ppm")
        norm = NormalizedObservation(raw.raw_id, "unit-v1", Decimal("0.1000"), "%", "original_value × 0.0001",
                                     raw_fingerprint=raw.normalization_fingerprint)
        self.assertEqual(payload(norm)["value"], "0.1000")
        compared = SemanticAssessment(raw.raw_id, "resource descriptive comparison", "r1", "concepts1",
                                      "VERIFIED", "COMPARABLE", "test", supporting_evidence=(anchor,),
                                      normalized_version=norm.version, raw=raw, normalized=norm)
        feature = AnalysisFeature(ValidatedObservation(norm, compared), "grade", "f1", norm.value, norm.unit)
        self.assertEqual(feature.observation.normalized.raw_id, raw.raw_id)
        descriptive = replace(compared, comparability="DESCRIPTIVE_ONLY", raw=raw, normalized=norm)
        with self.assertRaises(ValueError):
            replace(feature, observation=ValidatedObservation(norm, descriptive))
        with self.assertRaises(ValueError):
            replace(compared, supporting_evidence=(EvidenceAnchor("report", SHA),), raw=raw, normalized=norm)
        with self.assertRaises(ValueError):
            replace(norm, value=Decimal("NaN"))
        with self.assertRaises(ValueError):
            replace(anchor, page=True)

    def test_verified_serialization_binds_exact_original_and_normalized_contents(self):
        anchor = EvidenceAnchor("report", SHA, 2, table=0, row=1, column=2, quote="1000", role="NUMERIC_VALUE")
        raw = RawObservation("obs", "project", "grade", "RESOURCE", anchor, "parser-v1", "1000", "ppm")
        norm = NormalizedObservation(raw.raw_id, "unit-v1", Decimal("0.1000"), "%", "original_value × 0.0001",
                                     raw_fingerprint=raw.normalization_fingerprint)
        checked = SemanticAssessment(raw.raw_id, "direct", "r1", "o1", "VERIFIED", "COMPARABLE", "source",
                                     supporting_evidence=(anchor,), normalized_version=norm.version,
                                     raw=raw, normalized=norm)
        again = raw_from_payload(json.loads(canonical(payload(raw))))
        result = normalized_from_payload(json.loads(canonical(payload(norm))), raw=again)
        self.assertEqual(assessment_from_payload(payload(checked), raw=again, normalized=result), checked)
        with self.assertRaisesRegex(ValueError, "schema"):
            raw_from_payload({**payload(raw), "schema_version": "observation-v0"})
        with self.assertRaisesRegex(ValueError, "observation contents"):
            normalized_from_payload(payload(norm), raw=replace(raw, original_value="2000"))
        for altered in (replace(norm, version="unit-v2"), replace(norm, value=Decimal("99"))):
            with self.subTest(altered=altered), self.assertRaisesRegex(ValueError, "normalization"):
                assessment_from_payload(payload(checked), raw=raw, normalized=altered)
            with self.assertRaisesRegex(ValueError, "normalization"):
                ValidatedObservation(altered, checked)

    def test_direct_verified_construction_and_staging_reject_conflicting_numeric_evidence(self):
        anchor = EvidenceAnchor("report", SHA, 2, table=0, row=1, column=2, quote="1000",
                                bbox=(10, 20, 30, 40), role="NUMERIC_VALUE", offset=5)
        raw = RawObservation("obs", "project", "grade", "RESOURCE", anchor, "parser-v1", "1000", "ppm")
        supplement = EvidenceAnchor("report", SHA, 3, quote="The bore samples were processed...", role="SAMPLE_CONTEXT")
        other_anchors = (
            replace(anchor, sha256="b" * 64), replace(anchor, row=2), replace(anchor, column=3),
            replace(anchor, table=1), replace(anchor, bbox=(40, 40, 50, 50)), replace(anchor, offset=6),
            replace(anchor, quote="10000"), EvidenceAnchor("report", SHA, 2, quote="1000"),
        )
        with self.assertRaisesRegex(ValueError, "original observation"):
            SemanticAssessment(raw.raw_id, "direct", "r1", "o1", "VERIFIED", "COMPARABLE", "caller assertion",
                               supporting_evidence=(anchor,))
        checked = SemanticAssessment(raw.raw_id, "direct", "r1", "o1", "VERIFIED", "COMPARABLE", "source",
                                     supporting_evidence=(anchor, supplement), raw=raw)
        db = connect(":memory:")
        try:
            workspace = ObservationWorkspace(db)
            for bad in other_anchors:
                with self.subTest(bad=bad):
                    with self.assertRaisesRegex(ValueError, "bind the original"):
                        replace(checked, supporting_evidence=(bad, supplement), raw=raw)
                    # Simulate a stale object reaching storage without executing its constructor.
                    stale = replace(checked, raw=raw)
                    object.__setattr__(stale, "supporting_evidence", (bad, supplement))
                    with self.assertRaisesRegex(ValueError, "bind the original"):
                        workspace.append(raw, assessments=(stale,))
                    self.assertEqual(db.execute("SELECT count(*) FROM temp.observation_raw_v1").fetchone()[0], 0)
            workspace.append(raw, assessments=(checked,))
            self.assertEqual(db.execute("SELECT count(*) FROM temp.observation_assessment_v1").fetchone()[0], 1)
            changed = replace(raw, observation_id="another", original_value="2,000")
            wrong = NormalizedObservation(changed.raw_id, "unit-v1", Decimal("0.1000"), "%",
                                          "original_value × 0.0001", raw_fingerprint=raw.normalization_fingerprint)
            with self.assertRaisesRegex(ValueError, "observation contents"):
                workspace.append(changed, normalized=(wrong,))
            self.assertEqual(db.execute("SELECT count(*) FROM temp.observation_raw_v1").fetchone()[0], 1)
        finally:
            db.close()

    def test_raw_adapter_keeps_original_values_and_coordinates(self):
        raw = raw_from_candidate({
            "observation_id": "obs", "project_id": "project", "target_quantity": "grade",
            "profile_id": "DIRECT_RESOURCE_UNIT_COMPARISON_V1", "physical_page": 3, "source_sha256": SHA,
            "native": {"quantity": "grade", "token": "1,000", "unit": "ppm", "token_state": "NUMBER"},
            "context": {"scope": "reported zone", "chemical_basis": "TREO"},
            "anchors": [{"field": "token", "page": 3, "source_sha256": SHA, "row": 0, "table_index": -1,
                         "column": 0, "quote": "Earlier 1200. Inferred 1,000 ppm", "offset": 23}],
        }, extractor_version="parser-v1", metadata={"source_key": "source"})
        self.assertEqual(raw.original_value, "1,000")
        self.assertEqual(raw.evidence.source_id, "source")
        self.assertEqual(raw.evidence.row, 0)
        self.assertIsNone(raw.evidence.table)
        self.assertEqual(raw.evidence.offset, 23)
        self.assertEqual(raw.scope_id, "reported zone")
        self.assertEqual(raw.chemical_basis, "TREO")
        self.assertNotEqual(raw.raw_id, replace(raw, extractor_version="parser-v2").raw_id)

    def test_existing_database_stays_read_only_and_retries_are_atomic(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "canonical.sqlite"
            db = connect(path)
            with db:
                db.execute("INSERT INTO sources VALUES(?,?,?,?,?,?,?,?)",
                           (SHA, "report", "url", "2023-10", "2026-01-02T08:30:00Z", "original", "pdf", "{}"))
                db.execute("INSERT INTO entities VALUES(?,?,?,?)", ("project", "PROJECT", "id", "1"))
                db.execute("INSERT INTO observations VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                           ("obs", "project", "grade", 1000, "ppm", "TREO", "scope", "statement", "INFERRED",
                            "2023-09-24", SHA, "original page 2", "AUTO_VALIDATED", "[]",
                            canonical({"original_token": "1,000", "original_unit": "ppm", "pdf_page": 2}), "legacy"))
            db.close()
            before = filehash(path)
            with open_observation_workspace(path) as workspace:
                db = workspace.db
                raw = canonical_resource_observation(db, "obs")
                self.assertEqual((raw.project_id, raw.evidence.page, raw.original_value), ("project", 2, "1,000"))
                norm = NormalizedObservation(raw.raw_id, "unit-v1", Decimal("0.1"), "%", "original_value × 0.0001",
                                             raw_fingerprint=raw.normalization_fingerprint)
                newest = replace(norm, version="unit-v2")
                decision = SemanticAssessment(raw.raw_id, "profile-a", "r1", "o1", "UNVERIFIED",
                                              "INSUFFICIENT_CONTEXT", "independent review pending")
                workspace.append(raw, normalized=(norm,), assessments=(decision,))
                workspace.append(raw, normalized=(norm, newest), assessments=(
                    decision, replace(decision, purpose="profile-b", normalized_version=newest.version)))
                self.assertEqual(db.execute("SELECT canonical_observation_id FROM temp.observation_raw_v1").fetchone(),
                                 ("obs",))
                self.assertEqual(db.execute("SELECT count(*) FROM temp.observation_normalized_v1").fetchone(), (2,))
                self.assertEqual(db.execute("SELECT count(*) FROM temp.observation_assessment_v1").fetchone(), (2,))
                workspace.record_review(raw.raw_id, ManualDecision("review-1", "reviewer", "REVIEWED", "checked",
                                                                   "2026-11-26T00:00:00Z"))
                with self.assertRaisesRegex(ValueError, "version conflict"):
                    workspace.append(replace(raw, original_value="999"))
                another = replace(raw, observation_id="another")
                with self.assertRaises(sqlite3.IntegrityError):
                    workspace.append(another, assessments=(replace(decision, raw_id=another.raw_id,
                                                                    normalized_version="missing"),))
                self.assertEqual(db.execute("SELECT count(*) FROM temp.observation_raw_v1").fetchone(), (1,))
                self.assertEqual(db.execute("PRAGMA temp.foreign_key_check").fetchall(), [])
            self.assertEqual(filehash(path), before)
