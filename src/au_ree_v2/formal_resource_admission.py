"""Admit source-bound bulk Mineral Resource facts to the existing evidence store."""

from collections import Counter, defaultdict
from datetime import date, datetime
from decimal import Decimal, DecimalException
import json
import math
from pathlib import Path
import re

from .derived_cache import code_fingerprint
from .evidence import claim_evidence_ids, ingest_sources, normalize, resource_statement_metrics
from .numeric_evidence import header_unit_issue, numeric_witness_issue, scalar_decimal
from .observation_schema import RawObservation, VALUE_EVIDENCE_ROLES, payload, value_evidence_issue
from .observation_semantics import SemanticEngine
from .pdf_extract import project_registry
from .resource_source import _effective_dates, discover
from .selection_rules import RESOURCE_ADMISSION_VERSION, date_end, source_check
from .store import canonical, digest


SCHEMA = "formal-resource-admission-receipt-v1"
ADMISSION_VERSION = RESOURCE_ADMISSION_VERSION
REQUIRED_QUANTITIES = frozenset({"ore_mt", "grade"})
RESOURCE_QUANTITIES = REQUIRED_QUANTITIES | {"contained_treo_kt"}
MATERIALS = frozenset({"WHOLE_ORE", "BULK_ORE", "RESOURCE_BULK_ORE"})
DENOMINATORS = MATERIALS | {"RESOURCE_BULK_ORE_MASS"}
QUANTITY_UNITS = {"ore_mt": "Mt", "grade": "ppm", "contained_treo_kt": "kt TREO"}


def _scope_conditions(raw):
    return dict(raw.context.conditions)


def _location(anchor):
    return anchor.sha256, anchor.page, anchor.table, anchor.row


def _source_metadata_issue(source, cutoff, root, acquired_through):
    if source is None:
        return "SOURCE_NOT_SELECTED"
    if source.get("kind") != "pdf":
        return "SOURCE_NOT_PINNED_PDF"
    if problem := source_check(source, cutoff, root, acquired_through):
        return problem
    try:
        publication = date_end(source["publication_date"])
        available = date_end(source["available_date"])
        acquisition = datetime.fromisoformat(source["acquired_at"])
        if acquisition.tzinfo is None or publication > available:
            return "SOURCE_TIMING_UNESTABLISHED"
    except (TypeError, ValueError, KeyError):
        return "SOURCE_TIMING_UNESTABLISHED"
    return None


def _authorized_projects(claims, projects, sources):
    """Use only already registered identities and source-edition declarations."""
    registered = {row["entity_id"] for row in projects}
    by_source = defaultdict(set)
    for project in claims["projects"]:
        if project.get("entity_kind", "PROJECT") != "PROJECT":
            continue
        pid = "AU-" + digest([project.get("entity_namespace", "project_registry_v1"), str(project["id"])])[:20]
        if pid not in registered:
            continue
        for observation in project.get("observations", ()):
            if observation.get("source_key") and observation.get("source_sha256"):
                by_source[observation["source_key"], observation["source_sha256"]].add(pid)
    return {
        sha: sorted(registered.intersection(source.get("summary_project_ids") or by_source[source["key"], sha]))
        for sha, source in sources.items()
    }


def _value_disposition(raw, source, selected_row):
    anchor = raw.evidence
    if _location(anchor) != (source["sha256"], *selected_row) or anchor.source_id != source["key"]:
        return "VALUE_SOURCE_OR_ROW_MISMATCH", False, False
    witnesses = tuple(item for item in raw.evidence_anchors if item.role in VALUE_EVIDENCE_ROLES)
    if (len(witnesses) != 1 or type(anchor.column) is not int or not anchor.text_span
            or not anchor.bbox or anchor.bbox[0] >= anchor.bbox[2] or anchor.bbox[1] >= anchor.bbox[3]):
        return "NUMERIC_EVIDENCE_LOCATION_INSUFFICIENT", False, False
    issue = numeric_witness_issue(anchor.quote, raw.original_value, raw.original_unit,
                                  span=anchor.text_span.in_quote, cell=True, token_state=raw.source_value_state)
    if issue:
        return issue, False, False
    headers = [header for header in raw.evidence_anchors if header.role in {"unit", "VALUE_UNIT_HEADER"}]
    if len(headers) != 1:
        return "UNIT_HEADER_NOT_UNIQUELY_BOUND", True, False
    header = headers[0]
    if (header.source_id != source["key"] or _location(header)[:3] != _location(anchor)[:3]
            or header.column != anchor.column or type(header.row) is not int or header.row >= anchor.row
            or not header.quote or not header.bbox or header.bbox[3] > anchor.bbox[1] + .01):
        return "UNIT_HEADER_SOURCE_OR_COLUMN_MISMATCH", True, False
    if issue := header_unit_issue(header.quote, raw.original_unit):
        return issue, True, False
    if issue := value_evidence_issue(raw, witnesses):
        return issue, True, False
    return None, True, True


def _group_context(observations, source, project_ids, cutoff, selected_row):
    first = observations[0]
    if first.project_id not in project_ids:
        return "PROJECT_SOURCE_BINDING_NOT_ESTABLISHED"
    keys = ("project_id", "deposit_id", "scope_id", "statement_id", "estimate_id", "effective_date",
            "chemical_basis", "denominator_basis")
    if any(any(getattr(item, key) != getattr(first, key) for key in keys) for item in observations):
        return "CROSS_PROJECT_SCOPE_STATEMENT_EDITION_OR_BASIS"
    if not all(getattr(first, key) for key in ("scope_id", "statement_id", "estimate_id", "effective_date")):
        return "RESOURCE_STATEMENT_SCOPE_OR_DATE_UNRESOLVED"
    context = _scope_conditions(first)
    shared = ("category", "resource_type", "scope_coverage", "cutoff_grade", "cutoff", "reporting_standard")
    if any(any(_scope_conditions(item).get(key) != context.get(key) for key in shared) for item in observations):
        return "RESOURCE_ROW_CONTEXT_CONFLICT"
    if (context.get("resource_type") != "MINERAL_RESOURCE" or context.get("reporting_standard") != "JORC"
            or context.get("scope_coverage") not in {"PROJECT_TOTAL", "DEPOSIT_TOTAL"}
            or not (context.get("cutoff_grade") or context.get("cutoff"))):
        return "RESOURCE_CLASSIFICATION_SCOPE_OR_CUTOFF_UNRESOLVED"
    if any(item.quantity_kind != "RESOURCE" or item.chemical_basis != "TREO" for item in observations):
        return "RESOURCE_QUANTITY_OR_CHEMICAL_BASIS_MISMATCH"
    if first.denominator_basis not in DENOMINATORS or any(
            item.material_basis not in MATERIALS and not (item.variable == "contained_treo_kt"
            and item.material_basis == "RESOURCE_CONTAINED_OXIDE_MASS_KT") for item in observations):
        return "RESOURCE_MATERIAL_OR_DENOMINATOR_MISMATCH"
    try:
        day = date.fromisoformat(first.effective_date)
        if str(day) != first.effective_date or first.effective_date > min(date_end(source["publication_date"]), cutoff):
            return "RESOURCE_EFFECTIVE_DATE_AFTER_DISCLOSURE_OR_CUTOFF"
    except ValueError:
        return "RESOURCE_EFFECTIVE_DATE_UNRESOLVED"
    if any((item.publication_date and item.publication_date != source["publication_date"])
           or (item.acquisition_date and item.acquisition_date != source["acquired_at"]) for item in observations):
        return "RESOURCE_SOURCE_TIMING_MISMATCH"
    for item in observations:
        anchors = [anchor for anchor in item.evidence_anchors
                   if anchor.source_id == source["key"] and _location(anchor)[:3] == (source["sha256"], *selected_row[:2])
                   and anchor.quote and anchor.bbox]
        roles = {anchor.role for anchor in anchors}
        if not {"scope", "row"} <= roles:
            return "RESOURCE_SCOPE_OR_ROW_EVIDENCE_MISSING"
        if not any(anchor.role == "row" and anchor.row == selected_row[2] for anchor in anchors):
            return "RESOURCE_ROW_EVIDENCE_MISMATCH"
        dates = _effective_dates(anchor.quote for anchor in anchors
                                 if anchor.role in {"scope", "estimate_reference", "resource_section"})
        if dates != {item.effective_date}:
            return "RESOURCE_EFFECTIVE_DATE_EVIDENCE_MISMATCH"
    return None


def _project_values(engine, observations):
    facts = []
    for raw in observations:
        if raw.source_value_state not in {"SCALAR", "NUMBER"}:
            return None, "RESOURCE_VALUE_NOT_SCALAR"
        normalized = engine.normalize(raw, target_unit=QUANTITY_UNITS[raw.variable])
        if normalized is None:
            return None, "RESOURCE_NORMALIZATION_UNRESOLVED"
        original = scalar_decimal(raw.original_value, raw.original_unit)
        if original is None or original <= 0:
            return None, "RESOURCE_NORMALIZATION_OUT_OF_DOMAIN"
        try:
            # The printed resolution and the exact ratio follow the same existing
            # normalizer, so gapped or bounded values never supply a criterion.
            half = (Decimal(5).scaleb(original.as_tuple().exponent - 1) * normalized.value / original)
            value, half_width = float(normalized.value), float(half)
        except (DecimalException, ValueError, OverflowError):
            return None, "RESOURCE_NORMALIZATION_OUT_OF_DOMAIN"
        if not math.isfinite(value) or not math.isfinite(half_width):
            return None, "RESOURCE_NORMALIZATION_OUT_OF_DOMAIN"
        context = _scope_conditions(raw)
        fact = dict(variable=raw.variable, value=value,
                    unit="kt" if raw.variable == "contained_treo_kt" else normalized.unit, basis="TREO",
                    scope=raw.scope_id, statement_id=raw.statement_id, category=context.get("category"),
                    effective_date=raw.effective_date, source_sha=raw.evidence.sha256,
                    locator=f"physical page {raw.evidence.page}; table {raw.evidence.table}; "
                            f"row {raw.evidence.row}; column {raw.evidence.column}",
                    rounding_half_width=half_width, normalized=payload(normalized))
        if reasons := normalize(fact):
            return None, "+".join(reasons)
        facts.append(fact)
    by_variable = {fact["variable"]: {**fact, "raw": canonical(fact)} for fact in facts}
    reported = by_variable.get("contained_treo_kt")
    metrics = resource_statement_metrics(by_variable["ore_mt"], by_variable["grade"], reported)
    if not all(math.isfinite(x) for x in [metrics["calculated_from_rounded_inputs_kt"], *metrics["rounding_bounds_kt"]]):
        return None, "RESOURCE_NORMALIZATION_OUT_OF_DOMAIN"
    lower, upper = metrics["rounding_bounds_kt"]
    if reported and not lower <= reported["value"] <= upper:
        return None, "REPORTED_CONTAINED_CONFLICT"
    return facts, None


def _evaluate(candidate, source, project_ids, cutoff, engine):
    selected_row = candidate["physical_page"], candidate["table"], candidate["row"]
    observations = tuple(candidate["observations"])
    if not all(isinstance(raw, RawObservation) for raw in observations):
        raise TypeError("Resource extraction must return typed raw observations")
    issues = list(candidate.get("issues", ()))
    variables = [raw.variable for raw in observations]
    if not REQUIRED_QUANTITIES <= set(variables) <= RESOURCE_QUANTITIES or len(set(variables)) != len(variables):
        issues.append("RESOURCE_SAME_ROW_PAIR_NOT_UNIQUE")
    columns = [raw.evidence.column for raw in observations]
    if len(set(columns)) != len(columns):
        issues.append("RESOURCE_VALUE_COLUMNS_OVERLAP")
    details = []
    for raw in observations:
        issue, numeric, unit = _value_disposition(raw, source, selected_row)
        details.append(dict(raw_observation_id=raw.observation_id, raw_id=raw.raw_id,
                            numeric_located=numeric, numeric_and_unit_located=unit,
                            evidence_status="VERIFIED" if not issue else "UNVERIFIED", evidence_issue=issue,
                            raw=payload(raw)))
        if issue:
            issues.append(issue)
    if observations and (issue := _group_context(observations, source, project_ids, cutoff, selected_row)):
        issues.append(issue)
    facts = None
    if not issues:
        facts, issue = _project_values(engine, observations)
        if issue:
            issues.append(issue)
    return dict(source_sha256=source["sha256"], source_key=source["key"],
                physical_page=selected_row[0], table=selected_row[1], row=selected_row[2],
                project_id=observations[0].project_id if observations else None,
                status="CANONICAL_ELIGIBLE" if facts else "NOT_ADMITTED", reasons=sorted(set(issues)),
                observations=details, canonical_observation_ids=[]), facts, observations


def _table_label(text):
    """Report-local printed table numbers retain their exact subtable suffix."""
    labels = {match.casefold() for match in re.findall(r"\btable\s*(\d+(?:\.\d+)*[a-z]?)\b", text or "", re.I)}
    return next(iter(labels)) if len(labels) == 1 else None


def _same_reported_quantity(legacy, fact):
    if legacy["basis"] != fact["basis"] or legacy["category"] != fact["category"]:
        return False
    if fact["variable"] == "grade" and legacy["unit"] == "%":
        value = Decimal(str(legacy["value"])) * 10000
    elif legacy["unit"] == fact["unit"] or fact["variable"] == "contained_treo_kt" and legacy["unit"] == "kt TREO":
        value = Decimal(str(legacy["value"]))
    else:
        return False
    return value == Decimal(str(fact["value"]))


def _historical_statement(db, source, observations, facts, active_claim_ids):
    """Reuse an exact selected source table and statement, never infer scope equivalence."""
    raw = observations[0]
    labels = {_table_label(anchor.quote) for anchor in raw.evidence_anchors if anchor.role == "scope"}
    if len(labels) != 1 or None in labels:
        return None
    label = next(iter(labels))
    facts_by_variable = {fact["variable"]: fact for fact in facts}
    groups = defaultdict(lambda: defaultdict(list))
    for legacy in db.execute("""SELECT * FROM observations WHERE entity_id=? AND source_sha=?
            AND effective_date=? AND status='AUTO_VALIDATED' AND transform_version='normalization-v1'
            AND variable IN ('ore_mt','grade','contained_treo_kt')""",
            (raw.project_id, source["sha256"], raw.effective_date)):
        if legacy["obs_id"] not in active_claim_ids or legacy["variable"] not in facts_by_variable:
            continue
        reported = json.loads(legacy["raw"])
        if (reported.get("pdf_page") != raw.evidence.page
                or reported.get("source_key") != source["key"]
                or _table_label(legacy["locator"]) != label
                or legacy["category"] != facts_by_variable[legacy["variable"]]["category"]
                or legacy["basis"] != "TREO"):
            continue
        groups[legacy["scope"], legacy["statement_id"]][legacy["variable"]].append(legacy)
    paired = [(key, variables) for key, variables in groups.items() if REQUIRED_QUANTITIES <= variables.keys()]
    if not paired:
        return None
    if len(paired) != 1:
        raise ValueError("HISTORICAL_SOURCE_TABLE_STATEMENT_AMBIGUOUS")
    (scope, statement_id), variables = paired[0]
    if any(len(options) != 1 for options in variables.values()):
        raise ValueError("HISTORICAL_SOURCE_TABLE_STATEMENT_AMBIGUOUS")
    reused = {variable: options[0] for variable, options in variables.items()}
    if not all(_same_reported_quantity(row, facts_by_variable[variable]) for variable, row in reused.items()):
        raise ValueError("HISTORICAL_SOURCE_TABLE_READING_CONFLICT")
    return dict(scope=scope, statement_id=statement_id, reported_table_label=label, reused=reused)


def _insert_bundle(db, root, source, facts, observations, active_claim_ids):
    first = observations[0]
    scope_context = _scope_conditions(first)
    historical = _historical_statement(db, source, observations, facts, active_claim_ids)
    scope, statement = (historical["scope"], historical["statement_id"]) if historical else (first.scope_id, first.statement_id)
    reuse = historical["reused"] if historical else {}
    bundle = digest(["source-bound-resource-statement-v1", first.project_id, source["sha256"],
                     scope, statement, first.effective_date,
                     first.evidence.page, first.evidence.table, first.evidence.row])
    db.execute("SAVEPOINT automatic_resource_bundle")
    try:
        ingest_sources(db, root, [source])
        stored = db.execute("SELECT source_key,publication_date FROM sources WHERE sha=?", (source["sha256"],)).fetchone()
        if tuple(stored) != (source["key"], source["publication_date"]):
            raise ValueError("CANONICAL_SOURCE_METADATA_CONFLICT")
        results = []
        for fact, raw in zip(facts, observations, strict=True):
            if fact["variable"] in reuse:
                results.append((reuse[fact["variable"]]["obs_id"], False))
                continue
            identity = digest(["automatic-resource-fact-v1", bundle, fact["variable"], raw.evidence.column,
                               raw.original_value, raw.original_unit, fact["value"], fact["unit"], fact["basis"],
                               fact["category"], raw.deposit_id, raw.material_basis, raw.denominator_basis,
                               scope_context.get("cutoff_grade") or scope_context.get("cutoff")])
            record = dict(fact, domain="Resource", scope=scope, statement_id=statement, admission_bundle_id=bundle,
                          automation_method=ADMISSION_VERSION, decision_mode="AUTOMATIC",
                          source_key=source["key"], source_sha256=source["sha256"], source_kind=source["kind"],
                          publication_date=source["publication_date"], available_date=source["available_date"],
                          source_acquisition_date=source["acquired_at"],
                          source_document_version=source.get("source_document_version") or source["sha256"],
                          pdf_page=raw.evidence.page, material_basis=raw.material_basis,
                          composition_denominator_basis=raw.denominator_basis, deposit_id=raw.deposit_id,
                          estimate_id=raw.estimate_id, resource_type="MINERAL_RESOURCE",
                          reporting_standard="JORC", scope_coverage=scope_context["scope_coverage"],
                          cutoff_grade=scope_context.get("cutoff_grade") or scope_context.get("cutoff"),
                          effective_date_precision="DAY", effective_date_role="STATEMENT_EFFECTIVE_DATE",
                          original_reported_unit=raw.original_unit, original_token=raw.original_value,
                          source_bound_observation=payload(raw))
            if historical:
                record["resource_identity_link"] = {
                    "rule": "EXACT_SAME_SOURCE_TABLE_AND_STATEMENT",
                    "reported_table_label": historical["reported_table_label"],
                    "canonical_observation_ids": {variable: row["obs_id"] for variable, row in reuse.items()
                                                  if variable in REQUIRED_QUANTITIES},
                }
            values = (identity, raw.project_id, fact["variable"], fact["value"], fact["unit"], fact["basis"],
                      scope, statement, fact["category"], fact["effective_date"], source["sha256"],
                      fact["locator"], "AUTO_VALIDATED", "[]", canonical(record), ADMISSION_VERSION)
            existing = db.execute("SELECT * FROM observations WHERE obs_id=?", (identity,)).fetchone()
            if existing is not None and tuple(existing)[:14] != values[:14]:
                raise ValueError("CANONICAL_OBSERVATION_ID_COLLISION")
            if existing is None:
                db.execute("INSERT INTO observations VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", values)
            results.append((identity, existing is None))
    except BaseException:
        db.execute("ROLLBACK TO automatic_resource_bundle")
        db.execute("RELEASE automatic_resource_bundle")
        raise
    db.execute("RELEASE automatic_resource_bundle")
    return results, historical


def _scientific_group(first, facts):
    """Coalesce equal presentations of the same declared estimate in one edition."""
    context = _scope_conditions(first)
    return digest([first.project_id, first.evidence.sha256, first.scope_id, first.estimate_id,
                   first.effective_date, first.deposit_id, context.get("category"),
                   context.get("cutoff_grade") or context.get("cutoff"), first.denominator_basis,
                   sorted((f["variable"], f["value"], f["unit"], f["rounding_half_width"]) for f in facts)])


def admit(db, root, snapshots, cutoff, page_requests, *, acquired_through=None, claims_data=None,
          cache=None, classification="PUBLIC_REAL_SOURCE_REPLAY", context_pages_by_sha=None,
          preferred_source_keys=None):
    """Re-extract selected immutable PDF editions and save complete same-row witnesses.

    The caller owns the database transaction and current-run visibility. Historical
    observations are append-only. A receipt describes evidence verification and
    canonical storage; the formal selector independently admits criterion inputs.
    """
    root = Path(root)
    claims = claims_data if claims_data is not None else json.loads((root / "data/claims.json").read_bytes())
    active_claim_ids = claim_evidence_ids(claims)
    engine = SemanticEngine(root)
    registry = project_registry(root, db, snapshots, mapping={}, claims_data=claims)
    context_pages_by_sha = context_pages_by_sha or {}
    preferred_source_keys = preferred_source_keys or {}
    sources = {}
    ambiguous = set()
    for source in snapshots:
        sha = source["sha256"]
        if sha in preferred_source_keys and source["key"] != preferred_source_keys[sha]:
            continue
        if sha in sources and sources[sha] != source:
            ambiguous.add(sha)
        sources[sha] = source
    allowed = _authorized_projects(claims, registry, sources)
    source_reasons, dispositions, accepted, active_automatic = [], [], {}, set()
    grouped = defaultdict(list)
    counts = Counter(source_requests=len(page_requests))
    for sha, pages in sorted(page_requests.items()):
        context_pages = context_pages_by_sha.get(sha, ())
        if (not re.fullmatch(r"[a-f0-9]{64}", sha) or not pages
                or any(type(page) is not int or page < 1 for page in (*pages, *context_pages))):
            raise ValueError("Admission requests require a pinned SHA and positive physical pages")
        source = sources.get(sha)
        counts["pages_requested"] += len(set(pages))
        reason = ("SOURCE_EDITION_METADATA_AMBIGUOUS" if sha in ambiguous else
                  _source_metadata_issue(source, cutoff, root, acquired_through))
        if not reason and source.get("case_classification", "PUBLIC_REAL_SOURCE_REPLAY") != classification:
            reason = "SOURCE_CLASSIFICATION_MISMATCH"
        if reason:
            source_reasons.append(dict(source_sha256=sha, status="SOURCE_BLOCKED", reason=reason, pages=sorted(set(pages))))
            continue
        context_options = {"context_pages": tuple(sorted(set(context_pages)))} if context_pages else {}
        discovery = discover(root, dict(source, summary_project_ids=allowed[sha]), registry,
                             page_numbers=sorted(set(pages)), cache=cache, **context_options)
        page_statuses = {row["status"] for row in discovery["pages"]}
        gaps = page_statuses - {"NO_CANDIDATES", "DISCOVERED"}
        source_status = ("SOURCE_BLOCKED" if page_statuses == {"SOURCE_BLOCKED"} else
                         "SOURCE_CHECKED_WITH_GAPS" if gaps else "SOURCE_CHECKED")
        source_reasons.append(dict(source_sha256=sha, source_key=source["key"], status=source_status,
                                   source_timing={k: source[k] for k in ("publication_date", "available_date", "acquired_at")},
                                   authorized_projects=allowed[sha], pages=discovery["pages"],
                                   context_pages=sorted(set(context_pages))))
        for candidate in discovery["candidates"]:
            summary, facts, raws = _evaluate(candidate, source, allowed[sha], cutoff, engine)
            dispositions.append(summary)
            if facts:
                grouped[_scientific_group(raws[0], facts)].append((summary, source, facts, raws))
    # Start the transaction explicitly so a released savepoint never publishes
    # facts before the caller's encompassing formal build commits or rolls back.
    if grouped and not db.in_transaction:
        db.execute("BEGIN IMMEDIATE")
    for key in sorted(grouped):
        entries = sorted(grouped[key], key=lambda entry: tuple(entry[0][field] for field in ("physical_page", "table", "row")))
        summary, source, facts, raws = entries[0]
        try:
            rows, historical = _insert_bundle(db, root, source, facts, raws, active_claim_ids)
        except ValueError as exc:
            for disposition, *_ in entries:
                disposition.update(status="NOT_ADMITTED", reasons=[str(exc)])
            continue
        identifiers = [identity for identity, _ in rows]
        legacy_ids = {row["obs_id"] for row in historical["reused"].values()} if historical else set()
        active_automatic.update(set(identifiers) - legacy_ids)
        for identity, created in rows:
            accepted[identity] = accepted.get(identity, False) or created
        for index, (disposition, _, _, observations) in enumerate(entries):
            disposition.update(status="SOURCE_BOUND_CANONICAL" if index == 0 else "CORROBORATING_PRESENTATION",
                               canonical_observation_ids=identifiers,
                               reasons=["MATCHING_ESTIMATE_PRESENTATION"] if index else ["COMPLETE_SAME_ROW_RESOURCE_STATEMENT"])
            if historical:
                disposition["historical_link"] = {"scope": historical["scope"], "statement_id": historical["statement_id"],
                                                  "reported_table_label": historical["reported_table_label"],
                                                  "reused_observation_ids": sorted(row["obs_id"] for row in historical["reused"].values())}
            by_quantity = {fact["variable"]: identity for fact, identity in zip(facts, identifiers, strict=True)}
            for raw, detail in zip(observations, disposition["observations"], strict=True):
                detail["canonical_observation_id"] = by_quantity[raw.variable]
    raw_candidates = [item for disposition in dispositions for item in disposition["observations"]]
    unique = {item["raw_id"]: item for item in raw_candidates}
    counts.update(candidate_rows=len(dispositions), candidate_observations=len(raw_candidates),
                  deduplicated_observations=len(unique), numeric_located=sum(x["numeric_located"] for x in unique.values()),
                  numeric_and_unit_located=sum(x["numeric_and_unit_located"] for x in unique.values()),
                  evidence_verified=sum(x["evidence_status"] == "VERIFIED" for x in unique.values()),
                  canonical_added=sum(accepted.values()), canonical_reused=sum(not x for x in accepted.values()),
                  canonical_stored=len(accepted), accepted_statements=sum(x["status"] == "SOURCE_BOUND_CANONICAL" for x in dispositions),
                  rejected_statements=sum(x["status"] == "NOT_ADMITTED" for x in dispositions),
                  accepted_projects=len({x["project_id"] for x in dispositions if x["canonical_observation_ids"]}),
                  source_blocked=sum(x["status"] == "SOURCE_BLOCKED" for x in source_reasons),
                  sources_with_incomplete_pages=sum(x["status"] == "SOURCE_CHECKED_WITH_GAPS" for x in source_reasons))
    rules = code_fingerprint(discover, SemanticEngine, value_evidence_issue, source_check, resource_statement_metrics,
                             files=[Path(__file__), root / "config/ontology/observation_v1.json",
                                    root / "config/ontology/comparability_v1.json"])
    inputs = digest([cutoff, acquired_through, page_requests, context_pages_by_sha, preferred_source_keys,
                     allowed, classification, sorted(active_claim_ids),
                     [entry for entry in source_reasons if entry.get("source_timing")]])
    return dict(schema=SCHEMA, version=ADMISSION_VERSION, classification=classification,
                cutoff=cutoff, acquired_through=acquired_through, input_sha256=inputs, rules_sha256=rules,
                status="COMPLETE_WITH_GAPS" if counts["source_blocked"] or counts["sources_with_incomplete_pages"] else "COMPLETE",
                counts=dict(counts),
                canonical_observation_ids=sorted(accepted), active_admission_observation_ids=sorted(active_automatic),
                source_dispositions=source_reasons, dispositions=dispositions,
                scientific_sha256=digest([inputs, rules, source_reasons, dispositions, sorted(accepted)]))
