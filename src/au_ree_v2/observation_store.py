"""Versioned shadow layers on an existing canonical SQLite connection."""

from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3

from .evidence_model import ensure_read_model
from .observation_schema import (
    AnalysisFeature, ManualDecision, RawObservation, SemanticAssessment, normalized_from_payload,
    payload, validate_assessment_binding, validate_normalized_binding,
)
from .store import canonical, digest


_TABLES = (
    """CREATE TEMP TABLE IF NOT EXISTS observation_raw_v1(
        raw_id TEXT PRIMARY KEY NOT NULL,
        canonical_observation_id TEXT,
        source_sha TEXT,
        project_id TEXT,
        payload TEXT NOT NULL
    )""",
    """CREATE TEMP TABLE IF NOT EXISTS observation_normalized_v1(
        raw_id TEXT NOT NULL REFERENCES observation_raw_v1,
        version TEXT NOT NULL,
        payload TEXT NOT NULL,
        PRIMARY KEY(raw_id, version)
    )""",
    """CREATE TEMP TABLE IF NOT EXISTS observation_assessment_v1(
        raw_id TEXT NOT NULL REFERENCES observation_raw_v1,
        purpose TEXT NOT NULL,
        rule_version TEXT NOT NULL,
        ontology_version TEXT NOT NULL,
        normalized_version TEXT,
        payload TEXT NOT NULL,
        PRIMARY KEY(raw_id, purpose, rule_version, ontology_version, normalized_version),
        FOREIGN KEY(raw_id, normalized_version) REFERENCES observation_normalized_v1(raw_id, version)
    )""",
    """CREATE TEMP TABLE IF NOT EXISTS observation_review_v1(
        raw_id TEXT NOT NULL REFERENCES observation_raw_v1,
        decision_id TEXT NOT NULL,
        payload TEXT NOT NULL,
        PRIMARY KEY(raw_id, decision_id)
    )""",
    """CREATE TEMP TABLE IF NOT EXISTS observation_feature_v1(
        feature_id TEXT PRIMARY KEY NOT NULL,
        raw_id TEXT NOT NULL REFERENCES observation_raw_v1,
        payload TEXT NOT NULL
    )""",
    """CREATE UNIQUE INDEX IF NOT EXISTS temp.observation_assessment_no_normalization_v1
        ON observation_assessment_v1(raw_id,purpose,rule_version,ontology_version)
        WHERE normalized_version IS NULL""",
)


@contextmanager
def open_observation_workspace(path):
    """Open the existing database read-only; shadow tables live for this connection."""
    db = sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True)
    try:
        db.execute("PRAGMA foreign_keys=ON")
        ensure_read_model(db)
        yield ObservationWorkspace(db)
    finally:
        db.close()


class ObservationWorkspace:
    """Stage replay rows without modifying the canonical evidence or its schema."""

    def __init__(self, db):
        if db.execute("PRAGMA foreign_keys").fetchone()[0] != 1:
            raise ValueError("Observation staging requires SQLite foreign-key enforcement")
        self.db = db
        # Check the canonical schema before creating connection-local layers.
        db.execute("SELECT obs_id, source_sha FROM main.observations LIMIT 0")
        for statement in _TABLES:
            db.execute(statement)

    def append(self, raw, *, normalized=(), assessments=(), features=()):
        """Append one atomic bundle. If a spec is reused, the payload must match."""
        if not isinstance(raw, RawObservation):
            raise TypeError("RawObservation is required")
        raw_id = raw.raw_id
        self.db.execute("SAVEPOINT stage_observation")
        try:
            self._append_raw(raw)
            for result in normalized:
                validate_normalized_binding(raw, result)
                self._insert("observation_normalized_v1", {"raw_id": raw_id, "version": result.version}, result)
            for decision in assessments:
                self._append_assessment(raw, decision)
            for feature in features:
                self._append_feature(raw, feature)
        except BaseException:
            self.db.execute("ROLLBACK TO stage_observation")
            raise
        finally:
            self.db.execute("RELEASE stage_observation")

    def record_review(self, raw_id, decision):
        """Append a new human decision, with an existing raw record as its subject."""
        if not isinstance(decision, ManualDecision):
            raise TypeError("ManualDecision is required")
        self._insert("observation_review_v1", {"raw_id": raw_id, "decision_id": decision.decision_id}, decision)

    def _append_raw(self, raw):
        source = raw.evidence.sha256
        candidates = self.db.execute(
            "SELECT obs_id FROM main.observations WHERE obs_id = ? AND source_sha = ?", (raw.observation_id, source)
        ).fetchone()
        self._insert("observation_raw_v1", {"raw_id": raw.raw_id}, raw, {
            "canonical_observation_id": candidates[0] if candidates else None,
            "source_sha": source, "project_id": raw.project_id,
        })

    def _append_assessment(self, raw, decision):
        if not isinstance(decision, SemanticAssessment):
            raise ValueError("A typed assessment is required")
        result = None
        if decision.normalized_version is not None:
            row = self.db.execute(
                "SELECT payload FROM temp.observation_normalized_v1 WHERE raw_id = ? AND version = ?",
                (raw.raw_id, decision.normalized_version),
            ).fetchone()
            if row is not None:
                result = normalized_from_payload(json.loads(row[0]), raw=raw)
        validate_assessment_binding(raw, decision, result)
        self._insert("observation_assessment_v1", {
            "raw_id": raw.raw_id, "purpose": decision.purpose, "rule_version": decision.rule_version,
            "ontology_version": decision.ontology_version, "normalized_version": decision.normalized_version,
        }, decision)

    def _append_feature(self, raw, feature):
        raw_id = raw.raw_id
        if not isinstance(feature, AnalysisFeature) or feature.observation.normalized.raw_id != raw_id:
            raise ValueError("Feature must reference the staged raw observation")
        normalized = feature.observation.normalized
        decision = feature.observation.assessment
        validate_normalized_binding(raw, normalized)
        self._insert("observation_normalized_v1", {"raw_id": raw_id, "version": normalized.version}, normalized)
        self._append_assessment(raw, decision)
        feature_id = digest([raw_id, normalized.version, decision.purpose, decision.rule_version,
                             decision.ontology_version, feature.name, feature.definition_version])
        self._insert("observation_feature_v1", {"feature_id": feature_id}, feature, {"raw_id": raw_id})

    def _insert(self, table, keys, record, values=None):
        # Table and column identifiers come from the static schema above.
        data = canonical(payload(record))
        where = " AND ".join(f"{key} IS ?" for key in keys)
        existing = self.db.execute(f"SELECT payload FROM temp.{table} WHERE {where}", tuple(keys.values())).fetchone()
        if existing:
            if existing[0] != data:
                raise ValueError(f"Observation version conflict in {table}")
            return
        row = {**keys, **(values or {}), "payload": data}
        placeholders = ", ".join("?" for _ in row)
        self.db.execute(f"INSERT INTO temp.{table} ({', '.join(row)}) VALUES ({placeholders})", tuple(row.values()))
