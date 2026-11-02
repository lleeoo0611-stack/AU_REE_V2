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

def domain_evidence_coverage(db, inventory, resources, gis_values, prospectus=None):
    """Descriptive source facts must not silently become six-domain scored values."""
    project_ids={r[0] for r in db.execute("SELECT entity_id FROM entities WHERE kind='PROJECT'")}
    listed={r["project_id"]:r for r in inventory}
    profiles={r["project_id"]:r for r in (prospectus or [])}
    rows=[]
    for eid in sorted(project_ids):
        listed_row=listed.get(eid,{})
        profile=profiles.get(eid,{})
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
            description_key={"Strategic":"strategic_evidence", "Technical":"technical_evidence",
                             "Development":"development_evidence", "Commercial":"commercial_evidence"}.get(domain)
            if state=="MISSING" and description_key and profile.get(description_key):
                state="AUSTRADE_DESCRIPTIVE_ONLY"
                evidence=profile[description_key]
            rows.append({"project_id":eid,"project_name":listed_row.get("project_name") or profile.get("project_name"),
                         "domain":domain,"evidence_state":state,"evidence_reference":evidence,
                         "scorable":int((domain=="Resource" and state=="SCOPED_RESOURCE_VALIDATED") or
                                        (domain=="Infrastructure" and state=="OFFICIAL_DISTANCE_AVAILABLE"))})
    return rows

# National Austrade source records preserve distinct upstream PROJECT identities.
# The explicit aliases below only concern two already identified WA projects.
AUSTRADE_CROSSWALK = {
    "browns-range-heavy-rare-earths-hre": ("project_registry_v1","browns-range"),
    "yangibana-rare-earths-niobium-project": ("WA_DMPE_REE_2026_PROJECT","yangibana"),
}
AUSTRADE_STATES = {"WA","NSW","VIC","NT","SA","QLD","TAS","ACT"}
AUSTRADE_FIELDS = ("row","project","owner","state","printed_page",
                   "strategic_evidence","technical_evidence",
                   "development_evidence","commercial_evidence")

def ingest_prospectus(db, root, source):
    path=Path(root)/source["path"]
    if filehash(path) != source["sha256"]:
        raise ValueError("Austrade catalogue checksum mismatch")
    count=0
    seen=set()
    with path.open(encoding="utf-8",newline="") as f:
        reader=csv.DictReader(f,delimiter="\t")
        if reader.fieldnames is None or set(reader.fieldnames) != set(AUSTRADE_FIELDS):
            raise ValueError("Austrade catalogue schema mismatch")
        for csvline,row in enumerate(reader,start=2):
            key=slug(row["project"])
            try:
                if not key or key in seen or int(row["row"]) != csvline-1:
                    raise ValueError("duplicate or invalid source row")
                if row["state"] not in AUSTRADE_STATES or not row["owner"].strip():
                    raise ValueError("missing authoritative state/owner")
                page=int(row["printed_page"])
                if page < 1 or not all(row[f].strip() for f in AUSTRADE_FIELDS):
                    raise ValueError("missing page or descriptive evidence")
            except (TypeError,ValueError) as exc:
                issue(db,None,source["sha256"],"AUSTRADE_ROW_INVALID",
                      canonical({"line":csvline,"reason":str(exc),"row":row}))
                continue
            seen.add(key)
            namespace,native=AUSTRADE_CROSSWALK.get(key,("AUSTRADE_2026_REE_PROJECT",key))
            eid=entity(db,namespace,native,"PROJECT")
            record=entity(db,"AUSTRADE_2026_REE_ROW",key,"SOURCE_RECORD")
            locator="Austrade March 2026 Critical Minerals Prospectus, printed p. "+str(page)
            payload={"source_kind":"AUSTRADE_2026_NATIONAL_PROJECT_PROFILE",
                     "classification":"OFFICIAL_PROFILE_NOT_JORC_VERIFICATION",
                     "project_id":eid,"project_name":row["project"],
                     "state":row["state"],"owner":row["owner"],
                     "source_sha256":source["sha256"],"source_url":source["url"],
                     "index_locator":"Austrade Prospectus, printed p. 5",
                     "locator":locator,"printed_page":page,
                     "strategic_evidence":row["strategic_evidence"],
                     "technical_evidence":row["technical_evidence"],
                     "development_evidence":row["development_evidence"],
                     "commercial_evidence":row["commercial_evidence"],
                     "observation_class":"SOURCE_DESCRIPTIVE_UNVERIFIED_NOT_SCORED"}
            for target in (eid,record):
                db.execute("INSERT OR IGNORE INTO records VALUES(?,?,?,?,?,?,?,?,?)",
                           (target,source["sha256"],row["project"],row["state"],
                            None,None,None,None,canonical(payload)))
            db.execute("INSERT OR IGNORE INTO relations VALUES(?,?,?,?,?,?,?)",
                       (digest([eid,record,"AUSTRADE_LISTING"]),eid,record,
                        "LISTED_IN_NATIONAL_PROSPECTUS",
                        "2026-03-01",source["sha256"],locator))
            count+=1
    if count==0:
        issue(db,None,source["sha256"],"AUSTRADE_NO_VALID_ROWS",str(path))
    return count

def national_prospectus_inventory(db, selected_shas):
    rows=[]
    for r in db.execute("""SELECT r.raw,r.source_sha FROM records r JOIN entities e USING(entity_id)
                            WHERE e.kind='SOURCE_RECORD'"""):
        if r["source_sha"] not in selected_shas:
            continue
        d=json.loads(r["raw"])
        if d.get("source_kind")!="AUSTRADE_2026_NATIONAL_PROJECT_PROFILE":
            continue
        rows.append({"project_id":d["project_id"],"project_name":d["project_name"],
                     "state":d["state"],"owner":d["owner"],
                     "strategic_evidence":d["strategic_evidence"],
                     "technical_evidence":d["technical_evidence"],
                     "development_evidence":d["development_evidence"],
                     "commercial_evidence":d["commercial_evidence"],
                     "source_sha256":r["source_sha"],"locator":d["locator"],
                     "status":"DESCRIPTIVE_ONLY_NO_NUMERIC_C1_SCORING",
                     "source_url":d["source_url"]})
    return sorted(rows,key=lambda x:x["project_name"])
