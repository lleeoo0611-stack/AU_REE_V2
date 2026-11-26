"""Freeze pre-selection resource observations from the existing Phase 22 canonical store."""
import argparse
import csv
import hashlib
import json
import sqlite3
from collections import Counter, defaultdict
from importlib.metadata import version
from pathlib import Path

import pymupdf

from au_ree_v2.selection_rules import date_end, observation_visible
from au_ree_v2.security import public_export
from au_ree_v2.store import digest, filehash, logical_dump
from tools.normalization_comparison import FIELDS


ROOT = Path(__file__).resolve().parents[1]
RELEASE = ROOT / "results/ree-project-census/gap173-20261122"
OUTPUT = ROOT / "results/ontology-gain-20261126"
USE = "DIRECT_RESOURCE_UNIT_COMPARISON_V1"
SEED = "AU-REE-ONTOLOGY-GAIN-20261126-v1"
# Enumerate plausible quantity families *before* consulting any admission result.
# A proposed target only poses the question, including explicitly different chemistry.
QUANTITIES = {
    "ore_mt": ("ore_mt", "reported_resource_ore_mt"),
    "grade": ("grade", "reported_resource_grade", "reported_resource_grade_pct", "reported_resource_treo_grade_pct",
              "reported_resource_treo_grade_ppm", "reported_resource_treo_ppm", "normalized_resource_treo_ppm",
              "reported_resource_thm_treo_pct", "reported_resource_treo_ex_ceo2_ppm",
              "reported_resource_ndpr_grade_pct", "reported_resource_y2o3_grade_pct"),
    "contained_treo_kt": ("contained_treo_kt", "reported_resource_contained_kt", "reported_resource_contained_treo_kt"),
}
TARGET = {v: target for target, choices in QUANTITIES.items() for v in choices}
COLUMNS = {definition[0]: (name, definition[1]) for name, definition in FIELDS.items()}
INPUTS = ("census_release.json", "coverage.json", "census_selection.csv", "source_selection.csv",
          "resource_statement_lineage.csv", "resource_statement_observations.csv", "acquisition_report.csv")


def stable_id(*parts):
    message = json.dumps(parts, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(message.encode()).hexdigest()


def rows(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def jsonl(path, items):
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        for item in items:
            stream.write(json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")


def report(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


def connected_split(records, development_projects):
    """Shared project, SHA, repeated physical page or statement family travels together."""
    parents = {}

    def root(item):
        parents.setdefault(item, item)
        while parents[item] != item:
            parents[item] = parents[parents[item]]
            item = parents[item]
        return item

    for r in records:
        project = "p:" + r["project_id"]
        for family in r["report_families"]:
            a, b = root(project), root(family)
            parents[max(a, b)] = min(a, b)
    components = defaultdict(list)
    for r in records:
        components[root("p:" + r["project_id"])].append(r)
    eligible = []
    for group in components.values():
        projects = sorted({r["project_id"] for r in group})
        families = sorted({f for r in group for f in r["report_families"]})
        key = stable_id(projects, families)
        for r in group:
            r.update(group_id=key, split="DEVELOPMENT")
        if not set(projects).intersection(development_projects):
            eligible.append((stable_id(SEED, key), group))
    # A seed-ordered third of wholly new source/project components is quarantined.
    for _, group in sorted(eligible, key=lambda x: x[0])[:(len(eligible) + 2) // 3]:
        for r in group:
            r["split"] = "HOLDOUT"


def group_and_sample(records):
    strata = defaultdict(list)
    for r in records:
        # No status, old decision, B decision or manual reference label in sampling.
        kind = "core" if r["variable"] == r["target_variable"] else "related"
        r["stratum"] = f'{r["target_variable"]}/{kind}/{r["source_kind"]}'
        if r["split"] == "HOLDOUT":
            strata[r["stratum"]].append(r)
    sample = []
    for candidates in strata.values():
        ordered = sorted(candidates, key=lambda r:stable_id(SEED, r["candidate_id"]))
        sample.extend(ordered[:3])
    return sorted(sample, key=lambda r:r["candidate_id"])


def page_context(path, n):
    with pymupdf.open(path) as doc:
        if not 1 <= n <= len(doc):
            return "", None
        text = " ".join(doc[n - 1].get_text(sort=True).split())
        return text, hashlib.sha256(text.encode()).hexdigest() if len(text) >= 160 else None


def quote(text, raw):
    markers = raw.get("page_markers") or raw.get("source_markers") or []
    if isinstance(markers, dict):
        markers = [v for values in markers.values() if isinstance(values,list) for v in values]
    if not isinstance(markers, list):
        markers = [markers]
    for token in [raw.get("raw_text"), *markers, raw.get("original_token")]:
        if token is None or isinstance(token, (dict,list)):
            continue
        query = " ".join(str(token).split())
        if len(query) >= 2 and (offset := text.find(query)) >= 0:
            return text[max(0, offset - 35):offset + min(len(query), 95) + 55]
    return None


YTTRIA_TABLE = {
    ("AU-ee5ca893d12883df35f1", "73936d124c5ce52038f968db521713ba86e72b92c847fb391254ebc47c0f0d51", "r3-yttria_202404"),
    ("AU-d0ce731e1d8198ffaf58", "bb46f35ad584143bdf7915b53b84c7ff55b6e8dc2aa23bab52f45eb0da057726", "yttria-table1-total-20240416"),
}


def evidence_identity(record, projected, page):
    """Use verified statement / row identity; a matching value on a page is insufficient."""
    r = record
    key = (r["entity_id"],r["source_sha256"],r["statement_id"])
    if (key in YTTRIA_TABLE and r["variable"] in ("ore_mt","grade") and r["effective_date"]=="2024-04-16"
            and r["category"]=="INDICATED_INFERRED_TOTAL" and r["physical_page"]==2 and "Total" in r["locator"]
            and "Table 1: Yttria REE MRE and Exploration Target" in page and "Total 15.0 490" in page):
        identity = ("verified_reprinted_yttria_total_20240416",r["source_page_sha256"])
    elif projected.get("selected_for_census")=="1" and r["group_statement"]:
        identity = ("same_selected_statement",r["project_id"],r["group_statement"])
    elif r["statement_id"] and r["scope"] and r["effective_date"] and r["category"]:
        identity = ("same_project_edition_scope",r["project_id"],r["source_sha256"],r["statement_id"],r["scope"],r["effective_date"],r["locator"])
    else:
        identity = ("individual_observation",r["observation_id"])
    return identity[0],stable_id(identity,r["variable"],r["value"],r["unit"],r["basis"],r["category"],
                                 r["material_basis"],r["denominator_basis"])


def blind_projection(r):
    """Reproduce the sealed, pre-adjudication packet. Its initial ID is a blocking key only."""
    hidden = {"raw","source_gates","original_issues","inherited_selection_role","status","group_statement",
              "deduplication_basis","production_resolution_reason","selection_role",
              "selected_for_census","statement_group_id","entity_verified","active_extraction"}
    item = {k:v for k,v in r.items() if k not in hidden}
    if r["source_page_sha256"]:
        block = ("same_physical_table",r["source_page_sha256"],r["effective_date"])
    elif r["selected_for_census"]=="1":
        block = ("selected",r["project_id"],r["group_statement"])
    else:
        block = ("project_edition",r["project_id"],r["source_sha256"],r["statement_id"],r["scope"],r["effective_date"])
    item["independent_observation_id"]=stable_id(block,r["target_variable"],r["value"],r["unit"],r["basis"],
                                                  r["category"],r["material_basis"],r["denominator_basis"])
    return item


def upstream_audit(db, run, release, out):
    """Report independent source, entity and technical denominators outside the scored use."""
    sources = rows(release/"acquisition_report.csv")
    excluded = {"REPLAY_ORIGINAL_BYTES_UNAVAILABLE","UNAVAILABLE","HOST_STOPPED","SOURCE_NOT_ACQUIRED","NETWORK_ERROR",
                "SOURCE_SHA_CHANGED","CACHED_UNBOUND_SOURCE_NOT_ADOPTED","FETCHED_UNBOUND_GOVERNMENT_OR_SOURCE","NO_FIXED_QUERY_NOT_EXPANDED"}
    blockers = []
    for s in sources:
        if s["admission_status"] or s["status"] in excluded:
            blockers.append({k:s[k] for k in ("key","host","status","admission_status","expected_sha256","actual_sha256")})
    jsonl(out/"upstream_source_blocks.jsonl",blockers)
    technical = rows(run/"technical_cells.csv")
    comparisons = rows(run/"technical_comparability.csv")
    cells = db.execute("select count(*),count(distinct entity_id) from observations where json_valid(raw) and json_extract(raw,'$.kind')='TECHNICAL_TABLE_CELL'").fetchone()
    audit = dict(acquisition_rows=len(sources), upstream_receipts_with_block=len(blockers),
                 upstream_status=dict(Counter(x["admission_status"] or x["status"] for x in blockers)),
                 source_denominator="Acquisition receipts; a missing document supplies no observation or number of would-be values.",
                 technical_db_table_cells=cells[0],technical_db_table_projects=cells[1],
                 technical_study_context_rows=db.execute("select count(*) from technical_study_context").fetchone()[0],
                 technical_export_cells=len(technical), technical_export_projects=len({r["project_id"] for r in technical}),
                 missing_cell_fields={f:sum(not r.get(f) for r in technical) for f in ("quantity","basis","feed","endpoint","scale","process_stage","case_id","sample_id","test_id","reagent","acid_concentration")},
                 technical_cell_uses=dict(Counter(use for r in technical for use in json.loads(r["allowed_analysis"]))),
                 technical_comparability_rows=len(comparisons),
                 technical_existing_dispositions=dict(Counter(r["comparability_status"] for r in comparisons)),
                 run_outputs_sha256={f:filehash(run/f) for f in ("resolved_evidence.csv","technical_cells.csv","technical_comparability.csv")},
                 scope="Existing technical records and contracts summarized at their own grain; no technical A/B or new admission measured.")
    report(out/"upstream_audit.json",audit)


def freeze(db_path, run, assets, out, release=RELEASE):
    release_data = json.loads((release/"census_release.json").read_bytes())
    coverage = json.loads((release/"coverage.json").read_bytes())
    cutoff = release_data["cutoff"]
    latest = json.loads((run.parent.parent/"latest.json").read_bytes())
    if (latest["run_id"] != release_data["run_id"] or latest["logical_database_sha256"] != coverage["logical_database_sha256"]
            or db_path.parent.name != release_data["run_id"] or run.name != release_data["run_id"]):
        raise ValueError("Canonical source run must match the released run and logical database fingerprint")
    wal = Path(str(db_path) + "-wal")
    if wal.exists() and wal.stat().st_size:
        raise ValueError("Freeze a consistent checkpoint or a backup copy before reading a live WAL")
    db = sqlite3.connect(db_path.resolve().as_uri() + "?mode=ro&immutable=1", uri=True)
    db.row_factory = sqlite3.Row
    if db.execute("select count(*) from runs where run_id=? and cutoff=? and status='COMPLETED'",
                  (release_data["run_id"],cutoff)).fetchone()[0] != 1:
        raise ValueError("Run boundary disagrees with SQLite")
    if digest(public_export(logical_dump(db))) != coverage["logical_database_sha256"]:
        raise ValueError("The actual canonical content disagrees with the released logical fingerprint")
    out.mkdir(parents=True,exist_ok=True)
    selection = {r["source_sha256"]:r for r in rows(release/"source_selection.csv")}
    membership = {r["project_id"]:r["canonical_project_id"] for r in rows(release/"census_selection.csv")}
    observations = {r["observation_id"]:r for r in rows(release/"resource_statement_observations.csv")}
    targets = defaultdict(list)
    for line in rows(release/"resource_statement_lineage.csv"):
        if line["column"] in FIELDS:
            keys = sorted(set(json.loads(line["source_statement_keys"])))
            targets[line["project_id"],line["column"]].extend(json.loads(k) for k in keys)
    study = json.loads((ROOT/"tests/fixtures/ontology_review_cases.json").read_bytes())
    dev = {membership.get(x["project_id"],x["project_id"]) for x in study["cases"]}
    policy_path = ROOT/"config/evidence_policy.json"
    if filehash(policy_path) != release_data["configuration_files"]["evidence_policy.json"]:
        raise ValueError("Run requires matching extraction and validation policy")
    validation = json.loads(policy_path.read_bytes())["document_pipeline"]["validation_version"]
    locked_sources = {s["sha256"] for s in release_data["sources"]}
    locked_by_key = {s["key"]:s["sha256"] for s in release_data["sources"]}
    # The production export contains the *complete* resolve() inventory, before criterion choice.
    resolved = {}
    with (run/"resolved_evidence.csv").open(encoding="utf-8-sig", newline="") as stream:
        for r in csv.DictReader(stream):
            if r["origin"]=="OBSERVATION" and r["variable"] in TARGET:
                resolved[r["evidence_id"]]=r["reason"]
    pdf_pages, checks = {}, {}
    records = []
    query = """select o.*,s.kind source_kind,e.kind entity_kind from resource_statement_facts o
               left join sources s on s.sha=o.source_sha left join entities e on e.entity_id=o.entity_id
               order by o.obs_id"""
    facts = list(db.execute(query))
    for o in facts:
        variable = o["variable"]
        if variable not in TARGET:
            continue
        obs_id, pid, sha = o["obs_id"],o["entity_id"],o["source_sha"]
        raw = json.loads(o["raw"])
        target = TARGET[variable]
        col, unit = COLUMNS[target]
        projected = observations.get(obs_id, {})
        source = selection.get(sha,{})
        physical = raw.get("pdf_page") or raw.get("physical_page")
        physical = int(physical) if str(physical).isdigit() else None
        gates = []
        asset = assets / sha
        if sha not in checks:
            checks[sha] = "MISSING" if not asset.is_file() else ("VERIFIED" if filehash(asset)==sha else "MISMATCH")
        if checks[sha] != "VERIFIED":
            gates.append("SOURCE_BYTES_" + checks[sha])
        if not source:
            gates.append("SOURCE_NOT_IN_SELECTION_RECEIPT")
        elif source.get("cutoff_status") != "WITHIN_CUTOFF" or not source.get("date_used") or date_end(source["date_used"]) > cutoff:
            gates.append("SOURCE_DATE_NOT_VERIFIED_AT_CUTOFF")
        if source.get("version_status") != "PINNED_SHA_VERIFIED":
            gates.append("SOURCE_VERSION_NOT_VERIFIED")
        visible = observation_visible(raw,locked_sources,validation)
        if raw.get("page_extraction_key") and locked_by_key.get(raw["page_extraction_key"]) != raw.get("page_extraction_sha256"):
            visible = False
        if not visible:
            gates.append("EXTRACTION_VERSION_OUTSIDE_LOCK")
        if obs_id not in resolved:
            gates.append("OBSERVATION_NOT_IN_ACTIVE_SELECTION_INVENTORY")
        if not o["effective_date"] or date_end(o["effective_date"]) > cutoff:
            gates.append("EFFECTIVE_DATE_NOT_VERIFIED_AT_CUTOFF")
        if o["entity_kind"] != "PROJECT" or pid not in membership:
            gates.append("PROJECT_OUTSIDE_CONFIRMED_CENSUS_MEMBERSHIP")
        if o["source_kind"] != "pdf":
            gates.append("SOURCE_NOT_STATIC_PDF")
        if o["source_kind"] == "pdf" and not physical:
            gates.append("NO_PHYSICAL_PDF_PAGE")
        page, page_hash = "", None
        if physical and o["source_kind"] == "pdf" and checks[sha] == "VERIFIED":
            if (sha,physical) not in pdf_pages:
                pdf_pages[sha,physical] = page_context(asset,physical)
            page,page_hash = pdf_pages[sha,physical]
            if not page:
                gates.append("NO_READABLE_PAGE_TEXT")
        project = membership.get(pid,pid)
        families = ["source:"+sha]
        if o["statement_id"]:
            families.append("statement:"+o["statement_id"])
        if page_hash:
            families.append("page:"+page_hash)
        record = dict(candidate_id=stable_id(USE,obs_id),observation_id=obs_id,entity_id=pid,project_id=project,
                      use_id=USE,target_variable=target,target_column=col,target_unit=unit,variable=variable,
                      source_sha256=sha,source_key=o["source_key"],source_kind=o["source_kind"],source_gates=gates,
                      source_byte_check=checks[sha],cutoff=cutoff,publication_date=o["publication_date"],
                      available_date=source.get("available_date"),source_date_basis=source.get("date_basis"),
                      source_date_used=source.get("date_used"),source_version=source.get("version_status"),
                      physical_page=physical,source_page_sha256=page_hash,source_excerpt=quote(page,raw),
                      original_token=o["reported_token"],original_unit=o["reported_unit"],use_definition_version=USE,
                      report_families=families,raw=raw,parser_version=raw.get("parser_version"),
                      validation_version=raw.get("validation_version"),target_statements=targets[pid,col],
                      inherited_selection_role=projected.get("selection_role","NOT_PRESENT_IN_RELEASE_EXPORT"),
                      group_statement=projected.get("statement_group_id"),original_issues=json.loads(o["issues"]))
        for k in ("value","unit","basis","scope","locator","statement_id","status","category","effective_date","transform_version",
                  "material_basis","denominator_basis","statement_kind","date_role","cutoff_grade","source_transform","source_statement_key"):
            record[k]=o[k]
        record["deduplication_basis"],record["independent_observation_id"] = evidence_identity(record,projected,page)
        record.update(active_extraction=visible and obs_id in resolved,entity_verified=o["entity_kind"]=="PROJECT" and pid in membership,
                      production_resolution_reason=resolved.get(obs_id),selection_role=record["inherited_selection_role"],
                      selected_for_census=projected.get("selected_for_census"),statement_group_id=record["group_statement"])
        records.append(record)
    connected_split(records,dev)
    sample = group_and_sample(records)
    jsonl(out/"candidates.jsonl",records)
    jsonl(out/"review_sample.jsonl",[blind_projection(r) for r in sample])
    manifest = dict(seed=SEED,use=USE,cutoff=cutoff,run_id=latest["run_id"],sqlite_sha256=filehash(db_path),
                    logical_sha256=latest["logical_database_sha256"],project_identity_sha256=release_data["identity_links_sha256"],
                    release_inputs_sha256={f:filehash(release/f) for f in INPUTS},code_sha256=filehash(Path(__file__)),
                    candidate_sha256=filehash(out/"candidates.jsonl"),sample_sha256=filehash(out/"review_sample.jsonl"),
                    sample_design="Within each holdout target/native quantity family/source kind stratum, first three salted candidate hashes without replacement; groups linked by projects, statement IDs, source SHA or equal full PDF page. Previous fixture projects quarantined in development. No issuer-generalization claim.",
                    use_assignment=QUANTITIES,candidate_counts=dict(Counter(r["split"] for r in records)),
                    source_byte_checks=dict(Counter(checks.values())),sample_counts=dict(Counter(r["stratum"] for r in sample)),
                    holdout_counts=dict(Counter(r["stratum"] for r in records if r["split"]=="HOLDOUT")),
                    project_count=len({r["project_id"] for r in records}),candidate_count=len(records),
                    excluded_resource_variables=dict(Counter(r["variable"] for r in facts if r["variable"] not in TARGET)),
                    sqlite_observation_count=db.execute("select count(*) from observations").fetchone()[0],
                    resource_fact_count=len(facts))
    manifest["sole_use_scope"] = "Pre-selection source observations for three existing resource quantity kinds and named related or incompatible measures. Other resource facts and technical records are not scored."
    manifest["raw_gate_counts"] = dict(Counter(g for r in records for g in r["source_gates"]))
    manifest["resolved_inventory_reason_counts"] = dict(Counter(r["production_resolution_reason"] for r in records))
    manifest["unique_evidence_count"] = len({r["independent_observation_id"] for r in records})
    manifest["deduplication_limit"] = "Candidates use verified same-statement or explicit same-cell identity where available. Scientific units with unresolved corroboration can still recur; this automatic count is an upper bound. The original blind packet's independent_observation_id is a retrieval blocking key, not an equivalence decision. For reviewed units use source adjudications."
    manifest["candidate_id_set_sha256"] = stable_id(sorted(r["candidate_id"] for r in records))
    manifest["sample_id_set_sha256"] = stable_id(sorted(r["candidate_id"] for r in sample))
    manifest["source_id_count"] = len(checks)
    manifest["page_text_extractor"] = {"library":"PyMuPDF","version":version("PyMuPDF"),"operation":"native get_text(sort=True); whitespace collapsed; original PDF bytes bound by SHA-256"}
    upstream_audit(db,run,release,out)
    report(out/"inventory_manifest.json",manifest)
    db.close()
    return manifest


if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database",type=Path,required=True)
    parser.add_argument("--run",type=Path,required=True)
    parser.add_argument("--assets",type=Path,required=True)
    parser.add_argument("--release",type=Path,default=RELEASE)
    parser.add_argument("--output",type=Path,default=OUTPUT)
    a=parser.parse_args()
    freeze(a.database,a.run,a.assets,a.output,a.release)
