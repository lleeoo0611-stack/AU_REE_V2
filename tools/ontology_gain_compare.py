"""Paired offline ablation over a frozen preselection manifest, not a Census writer."""
import argparse
import hashlib
import json
import re
from collections import Counter
from functools import lru_cache
from itertools import combinations
from pathlib import Path

from au_ree_v2.ontology import load_vocabulary, normalize_context
from au_ree_v2.tabular import read_csv
from tools import normalization_comparison as norm


ROOT = Path(__file__).resolve().parents[1]
RELEASE = ROOT / "results/ree-project-census/gap173-20261122"
OUTPUT = ROOT / "results/ontology-gain-20261126"
RULES = ROOT / "config/ontology/resource_gain_v1.json"
USE = "DIRECT_RESOURCE_UNIT_COMPARISON_V1"
ARMS = ("A0", "B0", "A1", "B1")
COLUMNS = {v[0]: k for k, v in norm.FIELDS.items()}


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def write_json(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                    encoding="utf-8", newline="\n")


def response(status, reason, lineage=()):
    return dict(status=status, reason=reason, lineage=list(lineage))


class FrozenSelection:
    def __init__(self, directory):
        observations = norm._keyed(read_csv(directory / "resource_statement_observations.csv"), "observation_id")
        census = norm._keyed(read_csv(directory / "REE project census.csv"), "專案ID")
        self.observations = observations
        self.approved = norm.selected_pdf_sources(directory)
        self.cells = {}
        for cell in read_csv(directory / "resource_statement_lineage.csv"):
            if cell["column"] not in norm.FIELDS:
                continue
            key = cell["project_id"], cell["column"]
            if key in self.cells:
                raise ValueError(f"Duplicate direct cell {key}")
            self.cells[key] = (cell, *norm.direct_cell(cell, census, observations))

    def inputs(self, row, obs, semantic, trace):
        entry = self.cells.get((row["project_id"], COLUMNS[row["target_variable"]]))
        if not entry:
            return None, response("INSUFFICIENT", "NO_PUBLISHED_DIRECT_CELL")
        cell, direct, published, reason = entry
        if reason and (not semantic or reason != "missing_or_ambiguous_direct_observation"):
            return None, response("INSUFFICIENT", reason)
        if obs["variable"] != row["target_variable"]:
            if re.search(r"(?:thm|ndpr|minus_ce|excluding_ce)", obs["variable"], re.I):
                return None, response("INCOMPATIBLE", "DIFFERENT_ANALYTE_OR_MATERIAL_QUANTITY", trace)
            return None, response("INSUFFICIENT", "NO_EXACT_QUANTITY_MAPPING_TO_REQUESTED_FIELD", trace)
        if obs["project_id"] != row["project_id"] or obs["source_sha256"] != row["source_sha256"]:
            return None, response("BLOCKED", "ENTITY_OR_SOURCE_JOIN_MISMATCH")
        if direct is None:
            support = set(json.loads(cell["selected_resource_observation_ids"])) & set(json.loads(cell["supporting_observation_ids"]))
            if obs["observation_id"] not in support or obs["selection_role"] != "MATCHED_SELECTED_STATEMENT":
                return None, response("INSUFFICIENT", "NO_VERIFIED_DIRECT_OBSERVATION_IN_SELECTED_LINEAGE", trace)
            # A literal alias can be the only source of a selected cell. Multiple
            # possible values in the same cell must remain a conflict.
            if sum(self.observations[i]["variable"] in (row["variable"], row["target_variable"]) for i in support) != 1:
                return None, response("INCOMPATIBLE", "AMBIGUOUS_DIRECT_SOURCE_VALUES", trace)
        elif direct["observation_id"] != obs["observation_id"]:
            if not semantic:
                return None, response("INCOMPATIBLE", "NOT_DIRECT_SUPPORT_OF_SELECTED_CELL")
            # The comparator may bind a different observation, but never by name,
            # geography, equal numerical value, or a shared PDF alone. Require the
            # current canonical claim, the full selected edition and the same literal
            # source cell (locator/page); later checks also require numeric identity.
            keys = ("project_id", "source_sha256", "statement_id", "scope", "effective_date", "category",
                    "statement_kind", "source_statement_key", "physical_page", "locator", "basis")
            if any(not obs.get(k) or not direct.get(k) for k in keys):
                return None, response("INSUFFICIENT", "INCOMPLETE_SELECTED_CELL_BINDING", trace)
            if any(obs[k] != direct[k] for k in keys):
                return None, response("INCOMPATIBLE", "DIFFERENT_SELECTED_SOURCE_CELL", trace)
            if (obs["observation_id"] in self.observations and
                    obs["selection_role"] != "MATCHED_SELECTED_STATEMENT"):
                return None, response("BLOCKED", "CANONICAL_SELECTION_REJECTED_CONTEXT", trace)
            obs = dict(obs, selected_for_census="1", selection_role="MATCHED_SELECTED_STATEMENT",
                       statement_group_id=direct["statement_group_id"])
            trace.append(dict(rule="direct-resource-comparison-gain-v1", action="BIND_SAME_REPORTED_CELL",
                              observation_id=obs["observation_id"], corroborates=direct["observation_id"],
                              source_sha256=obs["source_sha256"], page=obs["physical_page"],
                              statement_key=obs["source_statement_key"], locator=obs["locator"]))
        return (obs, cell, self.approved, published), None


def from_old_checks(obs, cell, approved, published, lineage):
    result, reason = norm.diagnose_admission(obs, cell, approved, published)
    if result is not None:
        return response("ACCEPT", "VERIFIED_DIRECT_UNIT_COMPARISON", lineage)
    if reason in {"NONPOSITIVE_OR_UNBOUND_NUMERIC_TOKEN", "MISSING_OR_UNSUPPORTED_UNIT",
                  "INCOMPLETE_STATEMENT_CONTEXT"}:
        status = "INSUFFICIENT"
    elif reason in {"SOURCE_NOT_VERIFIED_OR_MISMATCH", "PROJECT_OR_STATEMENT_GROUP_MISMATCH",
                    "RESOURCE_EFFECTIVE_AFTER_CUTOFF", "SOURCE_STATEMENT_KEY_MISMATCH"}:
        status = "BLOCKED"
    else:
        status = "INCOMPATIBLE"
    return response(status, reason, lineage)


def map_units(obs, rules):
    """Apply an exact, dimension-specific concept to a source label; never modify amount or basis."""
    fields = {"original_unit": obs["original_unit"], "unit": obs["unit"]}
    if obs["basis"] != "TREO" or obs["denominator_basis"] or obs["material_basis"]:
        return obs, []
    transformed, trace = dict(obs), []
    for field, value in fields.items():
        mapped = normalize_context({"unit": value}, rules["vocabulary"])
        label = mapped["context"]["unit"]
        if mapped["unresolved_mappings"] or not mapped["mappings"] or label not in norm.FIELDS[COLUMNS[obs["variable"]]][2]:
            continue
        transformed[field] = label
        trace.append(dict(rule=rules["version"], action="EXACT_UNIT_MAPPING", field=field,
                          source_value=value, mapped_value=label, mapping=mapped["mappings"]))
    return transformed, trace


def page_reader(assets):
    import pymupdf

    @lru_cache(maxsize=None)
    def verified_file(source_sha):
        path = assets / source_sha
        if not path.is_file() or sha(path) != source_sha:
            return None
        return path

    @lru_cache(maxsize=None)
    def read_page(source_sha, page):
        path = verified_file(source_sha)
        if path is None:
            return None
        with pymupdf.open(path) as pdf:
            if not 1 <= page <= len(pdf):
                return None
            return tuple(" ".join(pdf[page - 1].get_text(sort=sort).split()) for sort in (False, True))

    @lru_cache(maxsize=None)
    def tables(source_sha, page):
        path = verified_file(source_sha)
        if path is None:
            return []
        with pymupdf.open(path) as pdf:
            if not 1 <= page <= len(pdf):
                return []
            return [(t.header.names, t.extract(), t.bbox) for t in pdf[page - 1].find_tables().tables]

    read_page.tables = tables
    read_page.verified_file = verified_file
    return read_page


def load_rules():
    rules = json.loads(RULES.read_bytes())
    vocabulary = load_vocabulary(ROOT / "config/ontology/comparability_v1.json")
    rules["vocabulary"] = {**vocabulary, "mappings": [*vocabulary["mappings"], *rules["unit_mappings"],
                                                       *rules["quantity_mappings"]]}
    return rules


# Restrict extraction to one existing marker that explicitly relates a mass, grade
# and commodity, or names a contained mass. Two unbound cells never establish a join.
NUM = r"(?:[0-9]{1,3}(?:,[0-9]{3})+|[0-9]+)(?:\.[0-9]+)?"
BOUNDARY = r"(?<![\w.,/+%<>−–—-])"
CHEMICAL = r"(?:TREO|total rare earth oxides?)(?![\w+\-−])(?!\s*(?:[+−-]|excluding|including))"
RESOURCE_GRADE = re.compile(
    BOUNDARY + rf"(?P<mass>{NUM})\s*(?P<mass_unit>Mt|million tonnes|tonnes|kt|t)\s*"
    rf"(?:@|at|grading)\s*(?P<grade>{NUM})\s*(?P<grade_unit>ppm|%|percent)\s*{CHEMICAL}\b")
CONTAINED = re.compile(
    rf"\b(?:containing|contains|contained)\s+(?P<value>{NUM})\s*(?P<unit>tonnes|kt|t|kg)\s+(?:of\s+)?{CHEMICAL}\b")
EXCLUDED_MARKER = re.compile(
    r"\b(?:cut[ -]?off|exploration target|reserve|concentrate|heavy mineral|"
    r"production target|forecast|alternative|sensitivity|subset|resource increase)\b", re.I)


def table_witnesses(source_tables, markers, variable, rules):
    headers = rules["literal_table_headers"].get(variable, {})
    for table_index, (names, rows, bbox) in enumerate(source_tables):
        for index, cells in enumerate(rows):
            normalized = " ".join(" ".join(str(x or "").split()) for x in cells if x).strip()
            # A prefix of a row, isolated number or one matching its published
            # value is insufficient; locate a complete existing source marker.
            if normalized not in markers or not re.match(r"^total\b", normalized, re.I):
                continue
            for col, name in enumerate(names):
                name = " ".join((name or "").split())
                if name not in headers or col >= len(cells):
                    continue
                token = (cells[col] or "").strip()
                if not norm.NUMBER.fullmatch(token):
                    continue
                yield token, headers[name], dict(marker=normalized, header=name, table_index=table_index,
                                                  row=index, column=col, table_bbox=list(bbox))


def recover_token(obs, raw, read_page, rules):
    if obs["original_token"] or obs["original_unit"] or not raw.get("page_markers"):
        return obs, []
    page = raw.get("pdf_page")
    if (not isinstance(page, int) or isinstance(page, bool) or page <= 0
            or str(page) != str(obs["physical_page"]) or raw.get("source_sha256") != obs["source_sha256"]
            or raw.get("statement_id") != obs["statement_id"] or raw.get("scope") != obs["scope"]
            or raw.get("variable") != obs["variable"] or raw.get("category") != obs["category"]):
        return obs, []
    texts = read_page(obs["source_sha256"], page)
    if not texts:
        return obs, []
    found = []
    markers = {" ".join(m.split()) for m in raw["page_markers"] if isinstance(m, str)}
    if hasattr(read_page, "tables") and any(re.match(r"^total\b", m, re.I) for m in markers):
        found.extend(table_witnesses(read_page.tables(obs["source_sha256"], page), markers, obs["variable"], rules))
    for marker in sorted(markers):
        if not marker or EXCLUDED_MARKER.search(marker) or not any(marker in t for t in texts):
            continue
        pattern = CONTAINED if obs["variable"] == "contained_treo_kt" else RESOURCE_GRADE
        for match in pattern.finditer(marker):
            if obs["variable"] == "contained_treo_kt":
                token, unit = match.group("value", "unit")
            elif obs["variable"] == "ore_mt":
                token, unit = match.group("mass", "mass_unit")
            else:
                token, unit = match.group("grade", "grade_unit")
            found.append((token, unit, dict(marker=marker, expression=match.group())))
    if len(found) != 1:
        return obs, []
    token, unit, witness = found[0]
    trace = dict(action="RECOVER_NATIVE_FIELDS_FROM_EXISTING_MARKER", rule=rules["marker_recovery"]["version"],
                 observation_id=obs["observation_id"], source_sha256=obs["source_sha256"], page=page,
                 original_token=token, original_unit=unit, **witness,
                 statement_id=obs["statement_id"])
    return dict(obs, original_token=token, original_unit=unit), [trace]


def observation(row, selection):
    # Keep every row in the frame. The published projection supplies exact legacy
    # field serializations when available, but is not the source of the frame.
    prior = selection.observations.get(row["observation_id"])
    if prior:
        if prior["source_sha256"] != row["source_sha256"] or prior["project_id"] != row["project_id"]:
            raise ValueError("Frozen resource observation identity changed")
        return dict(prior)
    fields = ("project_id", "source_sha256", "statement_id", "scope", "category", "effective_date",
              "observation_id", "variable", "value", "unit", "basis", "material_basis", "denominator_basis",
              "locator", "statement_kind", "source_transform", "original_token", "original_unit",
              "source_statement_key", "physical_page")
    data = {k: "" if row[k] is None else str(row[k]) for k in fields}
    return dict(data, statement_group_id=row["group_statement"] or "",
                selection_role=row["inherited_selection_role"] or "UNKNOWN",
                selected_for_census="1" if row["inherited_selection_role"] == "MATCHED_SELECTED_STATEMENT" else "0")


def decide(row, selection, read_page, rules):
    result = {k: row[k] for k in ("candidate_id", "independent_observation_id", "observation_id", "project_id",
                                   "variable", "target_variable", "use_id", "use_definition_version", "split")}
    if row["use_id"] != USE:
        return {**result, **{arm: response("NOT_EVALUABLE", "USE_NOT_IMPLEMENTED") for arm in ARMS}}
    blockers = list(row["source_gates"])
    if not blockers and hasattr(read_page, "verified_file") and read_page.verified_file(row["source_sha256"]) is None:
        blockers.append("FROZEN_SOURCE_BYTES_UNAVAILABLE_AT_REPLAY")
    if row["status"] != "AUTO_VALIDATED":
        blockers.append("CANONICAL_OBSERVATION_NOT_AUTO_VALIDATED")
    if blockers:
        return {**result, **{arm: response("BLOCKED", "|".join(sorted(set(blockers)))) for arm in ARMS}}
    obs = observation(row, selection)
    extracted, recovered = recover_token(obs, row["raw"], read_page, rules)
    for arm in ARMS:
        semantic = arm.startswith("B")
        projected = dict(extracted if arm.endswith("1") else obs)
        trace = list(recovered) if arm.endswith("1") else []
        if semantic:
            quantity = normalize_context({"quantity_kind": obs["variable"]}, rules["vocabulary"])
            if quantity["mappings"] and quantity["context"]["quantity_kind"] == row["target_variable"]:
                trace.append(dict(rule=rules["version"], action="EXACT_QUANTITY_MAPPING", mapping=quantity["mappings"]))
                projected["variable"] = row["target_variable"]
            if projected["variable"] in COLUMNS:
                projected, unit_trace = map_units(projected, rules)
                trace.extend(unit_trace)
        inputs, failure = selection.inputs(row, projected, semantic, trace)
        result[arm] = failure or from_old_checks(*inputs, trace)
        if failure and trace and not result[arm]["lineage"]:
            result[arm]["lineage"] = trace
        if result[arm]["status"] == "ACCEPT":
            admitted, _, _, published = inputs
            result[arm].update(field=COLUMNS[row["target_variable"]], resource_category=admitted["category"],
                               normalized_value=str(published), normalized_unit=norm.FIELDS[COLUMNS[row["target_variable"]]][1],
                               source_sha256=admitted["source_sha256"], page=admitted["physical_page"],
                               source_statement_key=admitted["source_statement_key"])
    return result


def pair_list(decisions):
    grouped = {}
    for row in decisions:
        for arm in ARMS:
            outcome = row[arm]
            if outcome["status"] == "ACCEPT":
                key = arm, outcome["field"], outcome["resource_category"]
                grouped.setdefault(key, {}).setdefault(row["project_id"], []).append(row)
    records = []
    for (arm, field, category), projects in sorted(grouped.items()):
        for a, b in combinations(sorted(projects), 2):
            shared = {r["independent_observation_id"] for r in projects[a]} & {
                r["independent_observation_id"] for r in projects[b]}
            records.append(dict(arm=arm, field=field, category=category, left=a, right=b,
                                status="SHARED_OBSERVATION_NOT_INDEPENDENT" if shared else "DISTINCT_OBSERVATIONS",
                                shared_observation_ids=sorted(shared),
                                left_candidates=sorted(r["candidate_id"] for r in projects[a]),
                                right_candidates=sorted(r["candidate_id"] for r in projects[b])))
    return records


def jsonlines(path, rows):
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")


def run(candidates_path, release, assets, output, development_only=False):
    rules = load_rules()
    selection = FrozenSelection(release)
    read_page = page_reader(assets)
    with candidates_path.open(encoding="utf-8") as stream:
        rows = [json.loads(line) for line in stream if line.strip()]
    if development_only:
        rows = [r for r in rows if r["split"] == "DEVELOPMENT"]
    decisions = []
    for row in rows:
        try:
            decisions.append(decide(row, selection, read_page, rules))
        except (ValueError, TypeError, KeyError, ArithmeticError) as err:
            # Preserve an error as an error, and fail the run after diagnostics
            # are saved. A broken decoder must not appear as a scientific hold.
            result = {k: row[k] for k in ("candidate_id", "independent_observation_id", "observation_id",
                                          "project_id", "variable", "target_variable", "use_id", "split")}
            decisions.append({**result, **{arm:response("ERROR", f"{type(err).__name__}: {err}") for arm in ARMS}})
    ids = [r["candidate_id"] for r in decisions]
    if len(ids) != len(set(ids)) or not ids:
        raise ValueError("Empty or duplicate candidate cohort")
    baseline_ids = {r["observation_id"] for r in norm.compare_release(release)["observations"]}
    frame = {r["observation_id"] for r in rows}
    if not development_only and not baseline_ids <= frame:
        raise ValueError("The preselection census frame dropped legacy admitted observations")
    old_in_frame = baseline_ids & frame
    a0 = {r["observation_id"] for r in decisions if r["A0"]["status"] == "ACCEPT"}
    by_arm = {arm: dict(sorted(Counter(r[arm]["status"] for r in decisions).items())) for arm in ARMS}
    differences = [r["candidate_id"] for r in decisions if len({r[arm]["status"] == "ACCEPT" for arm in ARMS}) > 1]
    artifacts = [Path(__file__), ROOT / "tools/normalization_comparison.py", ROOT / "src/au_ree_v2/ontology.py",
                 ROOT / "src/au_ree_v2/selection_rules.py", RULES, ROOT / "config/ontology/comparability_v1.json"]
    report = dict(scope=USE, research_status="DEVELOPMENT_OR_PROVISIONAL", candidates=len(ids),
                  run_subset="DEVELOPMENT" if development_only else "FULL_FROZEN_FRAME",
                  candidate_file_sha256=sha(candidates_path), code_and_rules_sha256={
                      p.resolve().relative_to(ROOT).as_posix(): sha(p) for p in artifacts},
                  interpretation=dict(A0="legacy evidence + full frozen prior rule",
                                      B0="same evidence + exact concept or same-source-cell relation",
                                      A1="common same-page native token recovery + full prior rule",
                                      B1="identical recovered native inputs + ontology rule"),
                  legacy_accepted_ids_in_frame=sorted(old_in_frame), A0_matches_legacy_ids=old_in_frame == a0,
                  reason_counts={a:dict(sorted(Counter(r[a]["reason"] for r in decisions).items())) for a in ARMS},
                  decision_counts=by_arm, new_source_documents=0)
    output.mkdir(parents=True, exist_ok=True)
    jsonlines(output / "decisions.jsonl", decisions)
    jsonlines(output / "project_pairs.jsonl", pair_list(decisions))
    write_json(output / "decision_audit.json", report)
    write_json(output / "disagreement_ids.json", differences)
    if old_in_frame != a0 or any("ERROR" in counts for counts in by_arm.values()):
        raise ValueError("A/B replay integrity error: inspect decision_audit.json and row-level decisions")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidates", type=Path, default=OUTPUT / "candidates.jsonl")
    parser.add_argument("--release", type=Path, default=RELEASE)
    parser.add_argument("--assets", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--development-only", action="store_true")
    args = parser.parse_args()
    run(args.candidates, args.release, args.assets, args.output, args.development_only)
