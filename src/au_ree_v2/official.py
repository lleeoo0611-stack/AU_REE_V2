"""WA official REE resource inventory: strict source-record/PROJECT separation.

Values are faithful transcription of the government summary table, not
automatically accepted scope-comparable JORC observations. They NEVER enter C1
resource_defined or any MCDA panel without separate issuer evidence.
"""
import csv
import json
import math
import re
from datetime import datetime
from pathlib import Path
from .store import canonical, digest, entity, filehash, issue

CROSSWALK = {"mt-weld": "mt-weld", "browns-range": "browns-range"}
ALLOWED = {"Operating", "Exploration", "Scoping", "Feasibility"}
STATUS = "OFFICIAL_SUMMARY_SCOPE_UNVERIFIED"
COLUMNS = ("row", "project", "status", "owner", "ore_mt", "grade_pct",
           "contained_treo_kt", "resource_date")

def slug(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")

def ingest_official_table(db, root, source):
    path = Path(root) / source["path"]
    if filehash(path) != source["sha256"]:
        raise ValueError("Official table transcription checksum mismatch")
    with path.open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames is None or set(reader.fieldnames) != set(COLUMNS):
            raise ValueError("Official table transcription schema mismatch")
        seen = set()
        count = 0
        for line, row in enumerate(reader, start=2):
            key = slug(row["project"])
            try:
                if not key or key in seen or not row["owner"].strip():
                    raise ValueError("missing or duplicate project label")
                if row["status"] not in ALLOWED or int(row["row"]) != line - 1:
                    raise ValueError("unexpected source row or development label")
                effective = datetime.strptime(row["resource_date"], "%d/%m/%Y").date().isoformat()
                ore, grade, treo = (float(row[k]) for k in ("ore_mt","grade_pct","contained_treo_kt"))
                if not all(math.isfinite(x) and x > 0 for x in (ore, grade, treo)) or grade > 100:
                    raise ValueError("invalid REO quantity")
                # Government-published values are rounded; do not force an exact product.
                lower = max(ore - .005, 0) * max(grade - .005, 0) * 10 - .5
                upper = (ore + .005) * (grade + .005) * 10 + .5
                if not lower <= treo <= upper:
                    raise ValueError("reported contained TREO outside rounding envelope")
            except (TypeError, ValueError, OverflowError) as exc:
                issue(db, None, source["sha256"], "OFFICIAL_TABLE_ROW_INVALID",
                      canonical({"csv_line":line,"reason":str(exc),"row":row}))
                continue
            seen.add(key)
            record_id = entity(db, "WA_DMPE_REE_2026_ROW", key, "SOURCE_RECORD")
            if key in CROSSWALK:
                project_id = entity(db, "project_registry_v1", CROSSWALK[key], "PROJECT")
            else:
                project_id = entity(db, "WA_DMPE_REE_2026_PROJECT", key, "PROJECT")
            locator = "WA DMPE REE February 2026 flyer, physical PDF page 1, table row " + row["row"]
            payload = {"source_kind":"WA_OFFICIAL_REE_PROJECT_RESOURCE_TABLE",
                       "classification":"OFFICIAL_LISTED_PROJECT_NOT_FORMAL_C1",
                       "project_name":row["project"],"project_id":project_id,
                       "source_row":int(row["row"]),"locator":locator,
                       "pdf_url":source["url"],"status":row["status"],"owner":row["owner"],
                       "ore_mt":ore,"grade_pct":grade,"contained_treo_kt":treo,
                       "resource_date":effective,"basis":"TREO",
                       "category":"UNSPECIFIED_MINERAL_RESOURCE",
                       "scope":"WA government project-summary row; original JORC scope not confirmed",
                       "source_sha256":source["sha256"],
                       "transcription_status":"OFFICIAL_TABLE_TRANSCRIPTION_NOT_ORIGINAL_PDF"}
            for eid, kind in ((record_id,"SOURCE_RECORD"),(project_id,"PROJECT")):
                db.execute("INSERT OR IGNORE INTO records VALUES(?,?,?,?,?,?,?,?,?)",
                           (eid,source["sha256"],row["project"],"WA",None,None,
                            None,row["status"],canonical(payload)))
            db.execute("INSERT OR IGNORE INTO relations VALUES(?,?,?,?,?,?,?)",
                       (digest([project_id,record_id,"GOVERNMENT_PROJECT_LISTING"]),project_id,
                        record_id,"LISTED_AS_PROJECT_NOT_DEPOSIT_EQUIVALENCE",
                        "2026-01-31",source["sha256"],locator))
            for variable, value, unit in (
                ("ore_mt",ore,"Mt"),("grade",grade,"%"),("contained_treo_kt",treo,"kt TREO")
            ):
                raw = {**payload,"variable":variable,"value":value,"unit":unit}
                db.execute("INSERT OR IGNORE INTO observations VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                           (digest([project_id,source["sha256"],variable,locator]),
                            project_id,variable,value,unit,"TREO",payload["scope"],
                            "wa-2026-"+key,payload["category"],effective,source["sha256"],
                            locator,STATUS,canonical(["ORIGINAL_JORC_SCOPE_NOT_VERIFIED"]),
                            canonical(raw),"wa-government-summary-v1"))
            count += 1
    if not count:
        issue(db,None,source["sha256"],"OFFICIAL_TABLE_NO_VALID_ROWS",str(path))
    return count

def official_inventory(db, selected_shas):
    output = []
    for r in db.execute("""SELECT r.raw,r.source_sha FROM records r
                           JOIN entities e USING(entity_id)
                           WHERE e.kind='SOURCE_RECORD' ORDER BY e.entity_id"""):
        if r["source_sha"] not in selected_shas:
            continue
        payload = json.loads(r["raw"])
        if payload.get("source_kind") != "WA_OFFICIAL_REE_PROJECT_RESOURCE_TABLE":
            continue
        output.append({"project_id":payload["project_id"],
                       "project_name":payload["project_name"],"state":"WA",
                       "official_status":payload["status"],"listed_owner":payload["owner"],
                       "ore_mt":payload["ore_mt"],"grade_pct":payload["grade_pct"],
                       "contained_treo_kt":payload["contained_treo_kt"],
                       "resource_date":payload["resource_date"],
                       "basis":payload["basis"],"category":payload["category"],
                       "source_sha256":r["source_sha"],"locator":payload["locator"],
                       "confidence":"OFFICIAL_SUMMARY_ONLY_NOT_C1",
                       "pdf_url":payload["pdf_url"]})
    return sorted(output,key=lambda r:r["project_name"])

def exact_deposit_candidates(db, inventory, selected_shas):
    """Two official records with identical names/state produce only a LINK CANDIDATE."""
    deposits = {}
    for r in db.execute("""SELECT e.entity_id,r.name,r.state,r.source_sha
                           FROM records r JOIN entities e USING(entity_id)
                           WHERE e.kind='DEPOSIT'"""):
        if r["source_sha"] in selected_shas and r["state"] == "WA":
            deposits.setdefault(slug(r["name"]),set()).add((r["entity_id"],r["source_sha"]))
    out=[]
    for project in inventory:
        hits=sorted(deposits.get(slug(project["project_name"]),set()))
        for eid,sha in hits:
            out.append({"project_id":project["project_id"],
                        "project_name":project["project_name"],"deposit_id":eid,
                        "deposit_source_sha256":sha,
                        "project_source_sha256":project["source_sha256"],
                        "candidate_count":len(hits),
                        "match_rule":"EXACT_CANONICAL_NAME_PLUS_STATE_V1",
                        "status":"UNVERIFIED_LINK_NO_GIS_RELEASE"})
    return out

def domain_evidence_coverage(db, inventory, resources, gis_values):
    """Descriptive source facts must not silently become six-domain scored values."""
    project_ids={r[0] for r in db.execute("SELECT entity_id FROM entities WHERE kind='PROJECT'")}
    listed={r["project_id"]:r for r in inventory}
    rows=[]
    for eid in sorted(project_ids):
        listed_row=listed.get(eid,{})
        for domain in ("Resource","Strategic","Technical","Development","Infrastructure","Commercial"):
            state="MISSING"
            evidence=None
            if domain=="Resource":
                if eid in resources:
                    state="SCOPED_RESOURCE_VALIDATED";evidence=resources[eid]["source_sha"]
                elif eid in listed:
                    state="OFFICIAL_SUMMARY_ONLY";evidence=listed_row["source_sha256"]
            elif domain=="Infrastructure" and gis_values.get(eid):
                state="OFFICIAL_DISTANCE_AVAILABLE";evidence=canonical(sorted(gis_values[eid]))
            elif domain=="Development" and listed_row.get("official_status"):
                state="DESCRIPTIVE_STATUS_ONLY";evidence=listed_row["official_status"]
            elif domain=="Commercial" and listed_row.get("listed_owner"):
                state="DESCRIPTIVE_OWNER_ONLY";evidence=listed_row["listed_owner"]
            rows.append({"project_id":eid,"project_name":listed_row.get("project_name"),
                         "domain":domain,"evidence_state":state,"evidence_reference":evidence,
                         "scorable":int((domain=="Resource" and state=="SCOPED_RESOURCE_VALIDATED") or
                                        (domain=="Infrastructure" and state=="OFFICIAL_DISTANCE_AVAILABLE"))})
    return rows
