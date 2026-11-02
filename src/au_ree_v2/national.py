"""Auditable import of frozen multi-state official candidate selections from legacy AU_REE.

The 339 selected entries are *screened source rows* (317 government feature
selections + 22 historical legacy-only rows), NOT national Project IDs.
The selected-attributes export preserves pointers to source chunk hashes. It
is not a substitute for the original complete government raw API snapshots.
"""
import json
import math
import re
from pathlib import Path
from shapely.geometry import Point
from shapely.ops import transform
from .store import canonical, digest, entity, filehash, issue
from .gis import geometry, PROJECT

STATE_BY_SOURCE = {
 "STATE_WA_MINDEX":"WA","STATE_TAS_MRT":"TAS","STATE_QLD_MINOCC":"QLD",
 "NT_MODAT_WFS":"NT","NSW_METINDEX":"NSW","VIC_MINSITE":"VIC",
 "SA_CRITICAL_REE":"SA","SA_GEODATA_MINDEP":"SA",
}
NAME_FIELDS = {
 "GA_AIMR_REE_2026":("entity_id",),
 "GA_CRITICAL_DEPOSITS_2025":("projectname",),
 "STATE_WA_MINDEX":("short_name","proj_title","site_code"),
 "STATE_TAS_MRT":("DEPOSIT_NAME",),
 "STATE_QLD_MINOCC":("name","occ_name","deposit_name","site_name"),
 "SA_CRITICAL_REE":("DEPOSIT_NAME",),
 "SA_GEODATA_MINDEP":("DEPOSIT_NAME",),
 "NT_MODAT_WFS":("name",),
 "NSW_METINDEX":("deposit_name",),
 "VIC_MINSITE":("site_name","site_nm","min_name"),
 "":("canonical_name","project_id")
}
def _numeric(x):
    if x is None or isinstance(x,bool):
        return None
    try:
        value=float(x)
        return value if math.isfinite(value) else None
    except (ValueError,TypeError):
        return None

def _coordinate(attrs, geo):
    # The source's explicit latitude/longitude wins over geometry where valid.
    candidates=[
        (attrs.get("longitude"),attrs.get("latitude")),
        (attrs.get("LONGITUDE_GDA2020"),attrs.get("LATITUDE_GDA2020")),
        (attrs.get("LONGITUDE_GDA94"),attrs.get("LATITUDE_GDA94")),
        (attrs.get("LONGITUDE"),attrs.get("LATITUDE")),
    ]
    if isinstance(geo,dict):
        candidates.append((geo.get("x"),geo.get("y")))
        if geo.get("type")=="Point" and isinstance(geo.get("coordinates"),list) and len(geo["coordinates"])>=2:
            candidates.append(tuple(geo["coordinates"][:2]))
    for x,y in candidates:
        lon,lat=_numeric(x),_numeric(y)
        if lon is not None and lat is not None and 110<=lon<=155 and -45<=lat<=-9:
            return lon,lat
    return None,None

def ingest_legacy_e1(db,root,source):
    path=Path(root)/source["path"]
    if filehash(path)!=source["sha256"]:
        raise ValueError("Historical official-selection snapshot SHA mismatch")
    seen=set()
    count=0
    for line,raw in enumerate(path.read_text(encoding="utf-8").splitlines(),start=1):
        if not raw.strip():
            continue
        try:
            row=json.loads(raw)
            target=row["target_id"]
            if not isinstance(target,str) or not target or target in seen:
                raise ValueError("duplicate or missing frozen source row identity")
            selected=row.get("features") or []
            if len(selected)>1:
                raise ValueError("unexpected multi-feature original selection")
            feature=selected[0] if selected else {}
            attrs=feature.get("attributes",{}) or {}
            if not isinstance(attrs,dict):
                raise ValueError("invalid native attribute structure")
            family=row.get("source_key") or ""
            if not family and not target.startswith("LEGACY:"):
                raise ValueError("missing official source family")
            if family and (not row.get("native_id") or not feature.get("original_chunk_sha256")
                            or not feature.get("locator") or not feature.get("source_path")):
                raise ValueError("incomplete official original feature provenance")
            if target.startswith("LEGACY:") != (family==""):
                raise ValueError("historical legacy-only source family mismatch")
            if family and not re.fullmatch(r"[a-f0-9]{64}",feature["original_chunk_sha256"]):
                raise ValueError("invalid source chunk hash")
        except (ValueError,KeyError,TypeError) as exc:
            issue(db,None,source["sha256"],"NATIONAL_SELECTION_ROW_INVALID",
                  canonical({"line":line,"reason":str(exc)}))
            continue
        seen.add(target)
        entity_id=entity(db,"LEGACY_E1_20261029_TARGET",target,"SOURCE_RECORD")
        native=row.get("native_id")
        name=next((str(attrs[f]).strip() for f in NAME_FIELDS.get(family,("name","deposit_name","DEPOSIT_NAME"))
                   if attrs.get(f) is not None and str(attrs[f]).strip()),None)
        if not name:
            name=str(native).strip() if native else target
        state=str(attrs.get("state") or attrs.get("STATE") or STATE_BY_SOURCE.get(family) or "").strip().upper() or None
        lon,lat=_coordinate(attrs,feature.get("geometry"))
        category="LEGACY_ONLY_NOT_OFFICIAL" if not family else "SCREENED_OFFICIAL_SOURCE_RECORD"
        payload={"source_kind":"LEGACY_NATIONAL_E1_SELECTED_FEATURE",
                 "screening_status":category,"source_key":family,
                 "legacy_target_id":target,"original_native_id":native,
                 "original_chunk_sha256":feature.get("original_chunk_sha256"),
                 "original_locator":feature.get("locator"),
                 "original_source_path":feature.get("source_path"),
                 "original_selection_sha256":source["sha256"],
                 "original_attributes":attrs,
                 "original_geometry":feature.get("geometry"),
                 "parent_project_hint":attrs.get("proj_code"),
                 "role":"SOURCE_RECORD_ONLY_NOT_PROJECT"}
        db.execute("INSERT OR IGNORE INTO records VALUES(?,?,?,?,?,?,?,?,?)",
                   (entity_id,source["sha256"],name,state,lon,lat,None,None,canonical(payload)))
        # Shared GA ENO is a verified *deposit source* native ID, not a Project identity.
        if family=="GA_AIMR_REE_2026":
            eno=attrs.get("eno")
            if isinstance(eno,(int,float)) and float(eno).is_integer():
                dep=db.execute("""SELECT entity_id FROM entities
                                  WHERE kind='DEPOSIT' AND native_namespace='GA_ENO' AND native_id=?""",
                               (str(int(eno)),)).fetchone()
                if dep:
                    db.execute("INSERT OR IGNORE INTO relations VALUES(?,?,?,?,?,?,?)",
                               (digest([dep["entity_id"],entity_id,"SAME_NATIVE_GA_ENO"]),dep["entity_id"],
                                entity_id,"SAME_NATIVE_GA_ENO_SOURCE_ONLY","2026-10-29",
                                source["sha256"],str(feature.get("locator"))))
        count+=1
    if count==0:
        issue(db,None,source["sha256"],"NATIONAL_SELECTION_EMPTY",str(path))
    return count

def national_candidate_rows(db,source_shas):
    out=[]
    for r in db.execute("""SELECT e.entity_id,r.source_sha,r.name,r.state,r.longitude,r.latitude,r.raw
                           FROM entities e JOIN records r USING(entity_id)
                           WHERE e.kind='SOURCE_RECORD' ORDER BY e.entity_id"""):
        if r["source_sha"] not in source_shas:
            continue
        d=json.loads(r["raw"])
        if d.get("source_kind")!="LEGACY_NATIONAL_E1_SELECTED_FEATURE":
            continue
        out.append({"entity_id":r["entity_id"],"source_key":d["source_key"],
                    "native_id":d["original_native_id"],"legacy_target_id":d["legacy_target_id"],
                    "name":r["name"],"state":r["state"],"longitude":r["longitude"],
                    "latitude":r["latitude"],"source_sha256":r["source_sha"],
                    "original_chunk_sha256":d["original_chunk_sha256"],
                    "original_locator":d["original_locator"],
                    "original_source_path":d["original_source_path"],
                    "screening_status":d["screening_status"],"record_kind":"SOURCE_RECORD",
                    "project_parent_hint":d.get("parent_project_hint")})
    return out

def national_source_coverage(rows):
    grouped={}
    for r in rows:
        key=(r["state"] or "UNKNOWN",r["source_key"] or "LEGACY_ONLY")
        grouped.setdefault(key,[]).append(r)
    return [{"state":state,"source_key":key,"source_records":len(group),
             "coordinate_records":sum(r["longitude"] is not None and r["latitude"] is not None for r in group),
             "source_record_not_project":True}
            for (state,key),group in sorted(grouped.items())]

def candidate_port_distances(db,root,snapshots,run_id):
    """GIS coverage for source-record points only; no Project GIS score release."""
    by_key={s["key"]:s for s in snapshots}
    ports=by_key.get("ga_ports")
    if not ports:
        return []
    data=json.loads((Path(root)/ports["path"]).read_text(encoding="utf-8"))
    inv=data.get("inventory",{})
    if not inv.get("complete") or inv.get("scope","global")!="global" or data.get("spatialReference",{}).get("wkid")!=4326:
        issue(db,None,ports["sha256"],"NATIONAL_SOURCE_PORT_LAYER_INCOMPLETE","global inventory required")
        return []
    try:
        geometries=[transform(PROJECT,geometry(f)) for f in data["features"]]
        if not geometries or any(g.is_empty or not g.is_valid for g in geometries):
            raise ValueError("Empty/invalid port geometries")
    except Exception as exc:
        issue(db,None,ports["sha256"],"NATIONAL_SOURCE_PORT_GEOMETRY",str(exc))
        return []
    rows=national_candidate_rows(db,{s["sha256"] for s in snapshots})
    output=[]
    for r in rows:
        value=None
        status="MISSING_COORDINATE"
        if r["longitude"] is not None and r["latitude"] is not None:
            point=transform(PROJECT,Point(r["longitude"],r["latitude"]))
            value=min(point.distance(g)/1000 for g in geometries)
            status="SCREENED_SOURCE_COORDINATE_NOT_PROJECT"
            db.execute("INSERT OR REPLACE INTO derived VALUES(?,?,?,?,?)",
                       (run_id,r["entity_id"],"source_record_port_distance_km",value,
                        canonical({"source_sha256":r["source_sha256"],
                                   "original_chunk_sha256":r["original_chunk_sha256"],
                                   "ports_sha256":ports["sha256"],"unit":"SOURCE_RECORD",
                                   "method":"EPSG:3577 Euclidean","status":status})))
        output.append({"entity_id":r["entity_id"],"source_key":r["source_key"],
                       "state":r["state"],"name":r["name"],"distance_km":value,
                       "coordinate_source_sha256":r["source_sha256"],"port_source_sha256":ports["sha256"],
                       "status":status,"unit_of_analysis":"SOURCE_RECORD_NOT_PROJECT",
                       "limitation":"Geological source locality; no confirmed Project boundary/route"})
    return output
