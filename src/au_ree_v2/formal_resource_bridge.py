"""Read a sealed formal R1/S1 selection into the existing composition panel."""
from collections import Counter, defaultdict
from contextlib import closing
import json
import math
from pathlib import Path
import shutil
import sqlite3
from tempfile import TemporaryDirectory

from .analysis import run_r
from .derived_cache import atomic_json, exclusive_lock
from .evidence import claim_evidence_ids, load_claims, resource_statement_metrics
from .evidence_model import compatible_resource_context, ensure_read_model
from .mcda import score
from .observation_pipeline import canonical_resource_observation
from .observation_schema import payload
from .selection_rules import date_end, observation_visible, source_check
from .store import canonical, digest, filehash
from .tabular import read_csv, write_csv


PANEL = "issuer_resource_composition"
PURPOSE = "FORMAL_RESEARCH_ISSUER_RESOURCE_COMPOSITION"
VERSION = "canonical-resource-panel-bridge-v1"
INTERCHANGE = ("matrix.csv", "criteria.csv", "weights.csv")
MATRIX_FIELDS = ["project_id", "canonical_project_id", "project_name", "scope", "deposit_type"]
GATES = ("ID", "ROLE", "WINDOW", "JORC", "PANEL", "GIS_RELEASE")


def cohort_policy_status(configuration):
    """An unmarked sealed configuration uses the historical cohort contract."""
    return configuration["research"].get("c1_cohort_policy", {}).get("status", "HISTORICAL")


class _Excluded(ValueError):
    """A local evidence problem that must remain explicit in the panel ledger."""


class _FormalInputs:
    def __init__(self, folder):
        self.folder = Path(folder)
        self.summary = json.loads((self.folder / "summary.json").read_bytes())
        if self.summary.get("status") != "COMPLETED":
            raise ValueError("FORMAL_RUN_NOT_COMPLETED")
        self.hashes = self.summary["output_hashes"]
        self.read_hashes = {}

    def path(self, name):
        path = self.folder / name
        if name not in self.hashes or not path.is_file() or filehash(path) != self.hashes[name]:
            raise ValueError("FORMAL_INPUT_HASH_MISMATCH: " + name)
        self.read_hashes[name] = self.hashes[name]
        return path

    def csv(self, name):
        return read_csv(self.path(name))

    def json(self, name):
        return json.loads(self.path(name).read_bytes())

    def optional_csv(self, name):
        return self.csv(name) if name in self.hashes else []


def _indexed(rows, key):
    rows = list(rows)
    items = {row[key]: row for row in rows}
    if len(items) != len(rows):
        raise ValueError("DUPLICATE_FORMAL_INTERCHANGE_ID: " + key)
    return items


class _SelectedEvidence:
    def __init__(self, db, root, configuration, snapshots, cutoff, members):
        self.db = db
        self.root = root
        self.cutoff = cutoff
        self.members = members
        config = configuration["research"]
        self.validation_version = config["evidence_resolution"].get("document_pipeline", {}).get("validation_version")
        self.acquired_through = config.get("acquisition_through") if cutoff == config.get("research_evidence_cutoff") else None
        self.sources = {s["sha256"]: s for s in snapshots}
        self.keys = {s["key"]: s["sha256"] for s in snapshots}
        self.source_dispositions = {}
        active = configuration.get("verified_claim_ids")
        self.active = set(active) if active is not None else claim_evidence_ids(
            load_claims(root, configuration["claims_sha256"])[0])

    def fact(self, observation_id, project_id):
        result = self.db.execute("SELECT * FROM resource_statement_facts WHERE obs_id=?", (observation_id,)).fetchone()
        if result is None:
            raise _Excluded("CANONICAL_OBSERVATION_MISSING")
        row = dict(result)
        sha = row["source_sha"]
        source = self.sources.get(sha)
        if sha not in self.source_dispositions:
            reason = source_check(source, self.cutoff, self.root, self.acquired_through)
            if source and not (self.root / source["path"]).is_file():
                reason = "LOCKED_SOURCE_UNAVAILABLE"
            if source and source["kind"] not in {"pdf", "html"}:
                reason = "NON_PRIMARY_SOURCE_KIND"
            self.source_dispositions[sha] = reason
        if self.source_dispositions[sha]:
            raise _Excluded(self.source_dispositions[sha])
        if self.members.get(row["entity_id"]) != project_id:
            raise _Excluded("CANONICAL_PROJECT_OBSERVATION_IDENTITY_MISMATCH")
        if row["status"] != "AUTO_VALIDATED":
            raise _Excluded("SOURCE_OBSERVATION_NOT_VALIDATED")
        if (row["transform_version"] == "normalization-v1" and observation_id not in self.active):
            raise _Excluded("OBSERVATION_NOT_IN_FORMAL_CLAIMS_EDITION")
        raw = json.loads(row["raw"])
        if (not observation_visible(raw, self.sources, self.validation_version)
                or raw.get("page_extraction_key") and self.keys.get(raw["page_extraction_key"]) != raw.get("page_extraction_sha256")):
            raise _Excluded("EXTRACTION_OR_VALIDATION_EDITION_NOT_SELECTED")
        try:
            effective = date_end(row["effective_date"])
        except (ValueError, TypeError) as exc:
            raise _Excluded("INVALID_EFFECTIVE_DATE") from exc
        if effective > self.cutoff:
            raise _Excluded("EFFECTIVE_AFTER_CUTOFF")
        if not row["scope"] or not row["locator"] or source["kind"] == "pdf" and not raw.get("pdf_page"):
            raise _Excluded("FORMAL_SCOPE_OR_SOURCE_LOCATOR_MISSING")
        if (not isinstance(row["value"], (float, int)) or not math.isfinite(row["value"])
                or row["value"] < 0):
            raise _Excluded("INVALID_CANONICAL_VALUE")
        return row

    def trace(self, row):
        source = self.sources[row["source_sha"]]
        observation = canonical_resource_observation(self.db, row["obs_id"])
        return {
            "canonical_observation": payload(observation),
            "canonical_value": row["value"],
            "canonical_unit": row["unit"],
            "canonical_evidence_status": row["status"],
            "native_token_status": "CANONICAL_SOURCE_TOKEN_PRESENT" if observation.original_value is not None
                                   else "LEGACY_FORMAL_INPUT_WITHOUT_LITERAL_TOKEN",
            "normalization_version": row["transform_version"],
            "source_transform": row["source_transform"],
            "resource_class": row["category"],
            "statement_kind": row["statement_kind"],
            "cutoff_grade": row["cutoff_grade"],
            "source": {
                "key": source["key"], "sha256": source["sha256"], "kind": source["kind"],
                "publication_date": source.get("publication_date"), "available_date": source.get("available_date"),
                "acquired_at": source["acquired_at"], "acquired_through": self.acquired_through,
                "availability_basis": "PRE_CUTOFF_SOURCE_PROOF" if source.get("pre_cutoff_evidence") else
                "LOCKED_AVAILABLE_DATE" if source["available_date"] <= self.cutoff else "RETROSPECTIVE_DATED_SOURCE_WINDOW",
            },
        }

    def resource(self, entity, project, selected):
        rows = [self.fact(obs_id, project) for obs_id in selected["obs_ids"]]
        codes = _indexed(rows, "variable")
        if set(codes) not in ({"ore_mt", "grade"}, {"ore_mt", "grade", "contained_treo_kt"}):
            raise _Excluded("SELECTED_RESOURCE_INPUTS_INCOMPLETE")
        statement = (entity, selected["source_sha"], selected["scope"], selected["statement_id"], selected["date"], "TREO")
        if any(tuple(row[key] for key in ("entity_id", "source_sha", "scope", "statement_id", "effective_date", "basis"))
               != statement for row in rows):
            raise _Excluded("SELECTED_RESOURCE_STATEMENT_CONTEXT_CONFLICT")
        ore, grade, reported = codes["ore_mt"], codes["grade"], codes.get("contained_treo_kt")
        if (ore["unit"] != "Mt" or grade["unit"] not in {"ppm", "%"}
                or reported and reported["unit"] not in {"kt", "kt TREO"}
                or not compatible_resource_context(rows)):
            raise _Excluded("SELECTED_RESOURCE_UNITS_OR_BASIS_INCOMPATIBLE")
        values = resource_statement_metrics(ore, grade, reported)
        lower, upper = values["rounding_bounds_kt"]
        if (any(values[key] != selected[key] for key in values)
                or reported is not None and not lower <= values["contained_treo_kt"] <= upper):
            raise _Excluded("SELECTED_RESOURCE_VALUE_OR_ROUNDING_MISMATCH")
        return values, rows, "REPORTED_CONTAINED_TREO" if reported else "ROUNDED_ORE_AND_TREO_GRADE_PRODUCT"

    def composition(self, project, resource, decision, resolved, contract):
        if decision is None or decision["status"] != "SELECTED":
            raise _Excluded(decision["status"] if decision else "NO_FORMAL_COMPOSITION_SELECTION")
        provenance = json.loads(decision["provenance"])
        ids = json.loads(decision["evidence_ids"])
        if not ids or provenance["evidence_id"] not in ids:
            raise _Excluded("FORMAL_COMPOSITION_IDS_MISSING")
        rows = [self.fact(obs_id, project) for obs_id in ids]
        for row in rows:
            bound = resolved.get(row["obs_id"], {})
            if (bound.get("reason") != "VALID_RAW_EVIDENCE" or bound.get("project_id") != project
                    or bound.get("source_sha256") != row["source_sha"]
                    or bound.get("basis") not in contract["basis"] or row["unit"] != contract["unit"]
                    or row["variable"] not in contract["variables"]
                    or row["value"] != float(decision["value"])
                    or tuple(row[key] for key in ("scope", "statement_id", "effective_date", "source_sha")) !=
                    tuple(resource[key] for key in ("scope", "statement_id", "date", "source_sha"))):
                raise _Excluded("FORMAL_COMPOSITION_SCOPE_VALUE_OR_BASIS_MISMATCH")
        selected = next(row for row in rows if row["obs_id"] == provenance["evidence_id"])
        raw = json.loads(selected["raw"])
        value = selected["value"]
        half = raw.get("rounding_half_width", 0)
        return value, raw.get("rounding_bounds", [value - half, value + half]), rows


def _score_fields(code, value, bounds, criteria):
    criterion = criteria[code]
    scores = [score(edge, criterion) for edge in bounds]
    return {code: score(value, criterion), f"{code}_alt": score(value, criterion, alternative=True),
            f"{code}_lower": min(scores), f"{code}_upper": max(scores)}


def _panel_rows(db, evidence, inputs, config):
    membership = _indexed((r for r in inputs.csv("canonical_membership.csv") if r["kind"] == "PROJECT"), "entity_id")
    coverage = _indexed(inputs.csv("cohort_coverage.csv"), "entity_id")
    resources = _indexed(inputs.csv("resources.csv"), "entity_id")
    traces = _indexed((
        trace for row in inputs.csv("value_trace.csv") if row["criterion"] == "R1"
        and (trace := json.loads(row["source"])).get("interpretation") == "IN_SITU_RESOURCE_NOT_RECOVERABLE_PRODUCT"
    ), "entity_id")
    composition = _indexed((r for r in inputs.csv("criteria_resolution.csv") if r["criterion"] == "S1"), "canonical_project_id")
    eligibility = _indexed(inputs.csv("eligibility_cohorts.csv"), "canonical_project_id")
    c1_disabled = cohort_policy_status({"research": config}) == "DISABLED"
    gates = defaultdict(dict)
    if not c1_disabled:
        for row in inputs.csv("formal_gate_compatibility.csv"):
            pid, gate = row["canonical_project_id"], row["gate"]
            if gate in gates[pid]:
                raise ValueError("DUPLICATE_FORMAL_GATE: " + pid + "/" + gate)
            gates[pid][gate] = {"status": row["status"], "reason": row["reason"]}
    excluded = _indexed(inputs.csv("cohort_exclusions.csv"), "entity_id")
    filtered = _indexed((r for r in inputs.optional_csv("mcda_census_gate.csv") if r["panel"] == PANEL), "project_id")
    scope_selection = _indexed(inputs.optional_csv("resource_scope_selection.csv"), "project_id")
    issues = defaultdict(set)
    for row in inputs.csv("review_queue.csv"):
        if row["reason"] in {"RESOURCE_SCOPE_AMBIGUITY", "REPORTED_CONTAINED_CONFLICT"}:
            issues[row["entity_id"]].add(row["reason"])
    criteria = {c["code"]: c for c in config["criteria"]}
    if config["panels"].get(PANEL) != ["R1", "S1"]:
        raise ValueError("UNSUPPORTED_FORMAL_PANEL_DEFINITION")
    policy = config["evidence_resolution"]
    contract = policy["criteria"]["S1"]
    resolved = _indexed((r for r in inputs.csv("resolved_evidence.csv") if r["variable"] in contract["variables"]),
                        "evidence_id")
    rows, ledger, provenance = [], [], []
    for project_id in sorted({r["canonical_id"] for r in membership.values()}):
        entities = sorted(key for key, row in membership.items() if row["canonical_id"] == project_id)
        selected_ids = [key for key in entities if key in resources]
        record = {
            "canonical_project_id": project_id, "member_project_ids": entities, "purpose": PURPOSE,
            "cutoff": evidence.cutoff, "version": VERSION,
            "formal_c1_status": "DISABLED" if c1_disabled else eligibility.get(project_id, {}).get(
                "formal_c1_status", "NO_FORMAL_C1_COHORT_ROW"),
            "c1_gates": {gate: gates.get(project_id, {}).get(gate, {"status": "NO_FORMAL_GATE_ROW", "reason": None})
                         for gate in (() if c1_disabled else GATES)},
        }
        ledger.append(record)
        try:
            if not selected_ids:
                reasons = sorted({reason for key in entities for reason in issues[key]})
                record["selection_issues"] = reasons
                raise _Excluded(reasons[0] if reasons else "NO_FORMALLY_SELECTED_RESOURCE")
            if len(selected_ids) != 1 or selected_ids[0] in excluded:
                raise _Excluded("MULTIPLE_RESOURCE_SCOPES_REQUIRE_COHORT_DECISION_NOT_AUTOMATIC_SUM")
            entity = selected_ids[0]
            cohort = coverage.get(entity)
            if not cohort:
                raise _Excluded("OUTSIDE_EXISTING_FORMAL_COHORT")
            if cohort["canonical_project_id"] != project_id or cohort["resource_defined"] != "1":
                raise _Excluded("FORMAL_COHORT_IDENTITY_OR_RESOURCE_MISMATCH")
            if filtered and filtered.get(entity, {}).get("included") != "1":
                raise _Excluded("CENSUS_FILTER_EXCLUDED")
            selected = traces[entity]
            frozen = resources[entity]
            if any(str(selected[key]) != frozen[key] for key in frozen):
                raise _Excluded("FORMAL_RESOURCE_EXPORT_AND_TRACE_DISAGREE")
            record.update(
                project_id=entity, scope=selected["scope"], statement_id=selected["statement_id"],
                selected_r1_obs_ids=selected["obs_ids"], selected_sha256=selected["source_sha"],
            )
            s1 = composition.get(project_id)
            if s1:
                record["selected_s1_obs_ids"] = json.loads(s1["evidence_ids"])
            values, resource_rows, method = evidence.resource(entity, project_id, selected)
            grade_unit = next(fact["unit"] for fact in resource_rows if fact["variable"] == "grade")
            formula = (
                "reported_contained_treo_kt" if method == "REPORTED_CONTAINED_TREO"
                else "ore_mt * grade_pct * 10" if grade_unit == "%" else "ore_mt * grade_ppm * 0.001"
            )
            provenance.append({
                "project_id": entity, "canonical_project_id": project_id, "panel": PANEL, "purpose": PURPOSE,
                "criterion": "R1", "value": values["contained_treo_kt"], "unit": "kt TREO",
                "rounding_bounds": values["rounding_bounds_kt"], "chemical_basis": "TREO",
                "material_basis": "IN_SITU_RESOURCE", "denominator_basis": None, "scope": selected["scope"],
                "statement_id": selected["statement_id"], "cutoff": evidence.cutoff,
                "selected_reason": scope_selection.get(entity, {}).get("reason", "EXISTING_FORMAL_RESOURCE_SELECTION"),
                "derivation": method, "formula": formula, "rule_version": policy["version"],
                "feature_definition_sha256": digest(criteria["R1"]), "analysis_config_version": config["version"],
                "obs_ids": selected["obs_ids"], "evidence": [evidence.trace(fact) for fact in resource_rows],
            })
            value, bounds, s1_rows = evidence.composition(project_id, selected, s1, resolved, contract)
            if cohort["S1"] != "1":
                raise _Excluded("FORMAL_COHORT_COMPOSITION_NOT_AVAILABLE")
            provenance.append({
                "project_id": entity, "canonical_project_id": project_id, "panel": PANEL, "purpose": PURPOSE,
                "criterion": "S1", "value": value, "unit": "%", "rounding_bounds": bounds,
                "chemical_basis": "PrNdDyTb_REO_DIV_TREO", "denominator_basis": "TREO",
                "scope": selected["scope"], "statement_id": selected["statement_id"], "cutoff": evidence.cutoff,
                "selected_reason": s1["status"], "rule_version": s1["policy_version"],
                "feature_definition_sha256": digest(criteria["S1"]), "analysis_config_version": config["version"],
                "obs_ids": [fact["obs_id"] for fact in s1_rows], "evidence": [evidence.trace(fact) for fact in s1_rows],
            })
            host = next((r["deposit_type"] for r in db.execute(
                """SELECT r.deposit_type,r.source_sha FROM relations rel JOIN records r
                   ON r.entity_id=rel.child_id AND r.source_sha=rel.source_sha WHERE rel.parent_id=?
                   AND rel.relation='REPRESENTATIVE_POINT_NOT_ENTITY_EQUIVALENCE' ORDER BY r.source_sha""",
                (entity,)) if r["deposit_type"] and r["source_sha"] in evidence.sources), None)
            name = db.execute("SELECT name FROM records WHERE entity_id=? ORDER BY source_sha LIMIT 1", (entity,)).fetchone()[0]
            rows.append({
                "project_id": entity, "canonical_project_id": project_id, "project_name": name,
                "scope": selected["scope"], "deposit_type": host,
                **_score_fields("R1", values["contained_treo_kt"], values["rounding_bounds_kt"], criteria),
                **_score_fields("S1", value, bounds, criteria),
            })
            record.update(status="ADMITTED_EXISTING_RESEARCH_PANEL", reason="SELECTED_FORMAL_R1_AND_S1")
        except _Excluded as exc:
            record.update(status="NOT_ADMITTED", reason=str(exc))
    admitted = {row["canonical_project_id"] for row in rows}
    for feature in provenance:
        feature["panel_admitted"] = feature["canonical_project_id"] in admitted
    return sorted(rows, key=lambda row: row["project_id"]), ledger, provenance


def _compare(before, after, ids, numeric=()):
    prior = {tuple(row[key] for key in ids): row for row in before}
    current = {tuple(row[key] for key in ids): row for row in after}
    if len(prior) != len(before) or len(current) != len(after):
        raise ValueError("DUPLICATE_PANEL_RESULT_ID")
    differences = []
    for identity in sorted(prior.keys() | current.keys()):
        old, new = prior.get(identity), current.get(identity)
        if old is None or new is None:
            differences.append({"identity": identity, "before": old, "after": new})
            continue
        fields = {}
        for field in sorted(old.keys() | new.keys()):
            a, b = old.get(field), new.get(field)
            if a == b:
                continue
            if field in numeric and a not in (None, "") and b not in (None, ""):
                x, y = float(a), float(b)
                if math.isfinite(x) and math.isfinite(y) and math.isclose(x, y, abs_tol=1e-12, rel_tol=1e-12):
                    continue
            fields[field] = {"before": a, "after": b}
        if fields:
            differences.append({"identity": identity, "changed_fields": fields})
    return differences


def equivalent_weight_rows(before, after):
    """Compare sealed weight values without relaxing row identity, order or other fields."""
    keys = ('scenario', 'criterion')
    if len(before) != len(after):
        return False
    if any(old.keys() != new.keys() or any(old[key] != new[key] for key in keys)
           for old, new in zip(before, after, strict=True)):
        return False
    return not _compare(before, after, keys, numeric=('weight',))


def _publish(output, result, stage):
    # Only replace a directory identified by an existing bridge receipt.
    # The previous completed derivative survives a publication failure.
    with exclusive_lock(output.parent / ("." + output.name + ".lock")):
        if not output.exists():
            result.rename(output)
            return
        try:
            previous = json.loads((output / "bridge_receipt.json").read_bytes())
        except (OSError, ValueError) as exc:
            raise ValueError("FORMAL_BRIDGE_TARGET_IS_NOT_AN_EXISTING_BRIDGE") from exc
        if previous.get("version") != VERSION or previous.get("panel") != PANEL:
            raise ValueError("FORMAL_BRIDGE_TARGET_IS_NOT_AN_EXISTING_BRIDGE")
        prior_files = previous.get("artifact_sha256")
        if not isinstance(prior_files, dict) or {
            p.relative_to(output).as_posix() for p in output.rglob("*") if p.is_file()
        } != set(prior_files) | {"bridge_receipt.json"}:
            raise ValueError("FORMAL_BRIDGE_TARGET_CONTAINS_UNTRACKED_FILES")
        backup = stage / "previous"
        output.rename(backup)
        try:
            result.rename(output)
        except BaseException:
            backup.rename(output)
            raise


def run(root, database, formal_run, output, *, rscript=None):
    """Rebuild one panel from canonical observations and the pinned formal run's choices."""
    root, database, formal_run, output = (Path(path).resolve() for path in (root, database, formal_run, output))
    if output.is_relative_to(formal_run) or output.is_relative_to(root / "data"):
        raise ValueError("FORMAL_BRIDGE_OUTPUT_MUST_BE_SEPARATE")
    inputs = _FormalInputs(formal_run)
    configuration = inputs.json("configuration.json")
    snapshots = inputs.json("snapshot_lock.json")
    config = configuration["research"]
    summary = inputs.summary
    cutoff = summary["cutoff"]
    run_id = summary["run_id"]
    hashes = (digest(configuration), digest(snapshots))
    if hashes != (summary["configuration_sha256"], summary["snapshot_sha256"]):
        raise ValueError("FORMAL_RUN_CONFIGURATION_OR_SNAPSHOT_MISMATCH")
    with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)) as db:
        db.row_factory = sqlite3.Row
        ensure_read_model(db)
        db.execute("BEGIN")
        recorded = db.execute("SELECT status,cutoff,config_sha,snapshot_sha FROM runs WHERE run_id=?", (run_id,)).fetchone()
        if recorded is None or tuple(recorded) != ("COMPLETED", cutoff, *hashes):
            raise ValueError("CANONICAL_DATABASE_DOES_NOT_CONTAIN_FORMAL_RUN")
        members = {r["entity_id"]: r["canonical_id"] for r in inputs.csv("canonical_membership.csv") if r["kind"] == "PROJECT"}
        evidence = _SelectedEvidence(db, root, configuration, snapshots, cutoff, members)
        rows, ledger, traces = _panel_rows(db, evidence, inputs, config)
    baseline_matrix = inputs.csv(f"{PANEL}/matrix.csv")
    baseline_ranks = inputs.csv(f"{PANEL}/ranking.csv")
    if len(baseline_matrix) != summary["r_results"][PANEL]["n"]:
        raise ValueError("FORMAL_PANEL_COUNT_MISMATCH")
    eligibility = inputs.json("eligibility_audit.json")
    release_file = "project-summary/formal_c1_release.json"
    c1_status = cohort_policy_status(configuration)
    if c1_status != "DISABLED" and release_file in inputs.hashes:
        inputs.path(release_file)
    output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=".formal-bridge-", dir=output.parent) as name:
        stage = Path(name)
        interchange, result = stage / "interchange", stage / "result"
        panel = interchange / PANEL
        for folder in sorted(p for p in formal_run.iterdir() if p.is_dir()):
            paths = [f"{folder.name}/{file}" for file in INTERCHANGE]
            if all(path in inputs.hashes for path in paths):
                for path in paths:
                    original = inputs.path(path)
                    target = interchange / path
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(original, target)
        commercial = "commercial_project_coverage.csv"
        if commercial in inputs.hashes:
            shutil.copyfile(inputs.path(commercial), interchange / commercial)
        fields = MATRIX_FIELDS + [code + suffix for code in ("R1", "S1") for suffix in ("", "_alt", "_lower", "_upper")]
        write_csv(panel / "matrix.csv", rows, fields)
        actual_matrix = read_csv(panel / "matrix.csv")
        matrix_delta = _compare(baseline_matrix, actual_matrix, ("project_id",), fields[len(MATRIX_FIELDS):])
        r_status = run_r(root, interchange, {"panels": {PANEL: len(rows)}}, config, rscript,
                         cache_mode="off")[PANEL] if len(rows) >= 2 else {"status": "INSUFFICIENT_SAMPLE", "n": len(rows)}
        actual_ranks = read_csv(panel / "ranking.csv")
        rank_delta = _compare(baseline_ranks, actual_ranks, ("scenario", "project_id"),
                              ("promethee", "saw", "topsis", "promethee_rank", "saw_rank", "topsis_rank"))
        result.mkdir()
        panel.rename(result / PANEL)
        for file, records in (("project_dispositions.jsonl", ledger), ("feature_provenance.jsonl", traces)):
            (result / file).write_text("".join(canonical(record) + "\n" for record in records), encoding="utf-8", newline="\n")
        panel_digests = {name: filehash(path) for name in (*INTERCHANGE, "ranking.csv")
                         if (path := result / PANEL / name).is_file()}
        status = "MATCHED" if not matrix_delta and not rank_delta else "PANEL_DIFFERENCES"
        receipt = {
            "status": status, "version": VERSION, "purpose": PURPOSE, "panel": PANEL,
            "cutoff": cutoff, "formal_run_id": run_id, "formal_run_configuration_sha256": hashes[0],
            "formal_snapshot_sha256": hashes[1], "formal_logical_database_sha256": summary["logical_database_sha256"],
            "baseline_projects": len(baseline_matrix), "admitted_projects": len(rows),
            "project_count": len(ledger), "feature_count": len(traces),
            "feature_counts": dict(Counter(r["criterion"] for r in traces)),
            "dispositions": dict(Counter(r["reason"] for r in ledger)),
            "source_dispositions": dict(sorted(evidence.source_dispositions.items())),
            "sources_checked": len(evidence.source_dispositions),
            "sources_verified": sum(reason is None for reason in evidence.source_dispositions.values()),
            "distinct_observations_in_admitted_panel": len({
                obs_id for feature in traces if feature["panel_admitted"] for obs_id in feature["obs_ids"]
            }),
            "formal_c1_admitted": eligibility["formal_c1_admitted"], "formal_c1_modified": False,
            "formal_c1_policy_status": c1_status,
            "matrix_equal": not matrix_delta, "ranking_equal": not rank_delta,
            "matrix_bytes_equal": panel_digests["matrix.csv"] == inputs.hashes[f"{PANEL}/matrix.csv"],
            "ranking_bytes_equal": panel_digests.get("ranking.csv") == inputs.hashes[f"{PANEL}/ranking.csv"],
            "matrix_differences": matrix_delta, "ranking_differences": rank_delta,
            "formal_input_sha256": inputs.read_hashes, "panel_output_sha256": panel_digests,
            "r_status": r_status["status"], "numeric_tolerance": "1e-12 relative or absolute; identifiers and text exact",
        }
        receipt["artifact_sha256"] = {
            path.relative_to(result).as_posix(): filehash(path)
            for path in sorted(result.rglob("*")) if path.is_file()
        }
        atomic_json(result / "bridge_receipt.json", receipt)
        _publish(output, result, stage)
    return {**receipt, "output": str(output)}
