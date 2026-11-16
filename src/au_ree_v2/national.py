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
            if len(selected)>1 and not all(isinstance(f,dict) for f in selected):
                raise ValueError("unexpected multi-feature selection payload")
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
            # LEGACY target IDs can also have independently preserved government
            # source features; an ID prefix does not override source provenance.
            if not family and not target.startswith("LEGACY:"):
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
        # A selected target may reference multiple original native features.
        # Keep the bundle intact, and refuse a fabricated single coordinate.
        lon,lat=_coordinate(attrs,feature.get("geometry")) if len(selected)==1 else (None,None)
        category="LEGACY_ONLY_NOT_OFFICIAL" if not family else "SCREENED_OFFICIAL_SOURCE_RECORD"
        payload={"source_kind":"LEGACY_NATIONAL_E1_SELECTED_FEATURE",
                 "screening_status":category,"source_key":family,
                 "legacy_target_id":target,"original_native_id":native,
                 "original_chunk_sha256":feature.get("original_chunk_sha256"),
                 "original_locator":feature.get("locator"),
                 "original_source_path":feature.get("source_path"),
                 "original_selection_sha256":source["sha256"],
                 "original_attributes":attrs,
                 "original_geometry":feature.get("geometry") if len(selected)==1 else None,
                 "selected_feature_count":len(selected),
                 "all_selected_features":selected if len(selected)>1 else None,
                 "multi_feature_scope":"NOT_SINGLE_LOCATION" if len(selected)>1 else None,
                 "parent_project_hint":attrs.get("proj_code"),
                 "role":"SOURCE_RECORD_ONLY_NOT_PROJECT"}
        db.execute("INSERT OR IGNORE INTO records VALUES(?,?,?,?,?,?,?,?,?)",
                   (entity_id,source["sha256"],name,state,lon,lat,None,None,canonical(payload)))
        # Shared GA ENO is a verified *deposit source* native ID, not a Project identity.
        if family=="GA_AIMR_REE_2026" and len(selected)==1:
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

# Current official inventories share this evidence store with the historical index.
REE_TERMS = re.compile(r'(?<![A-Za-z])(?:REEs?|REO|TREO|HREE|LREE|NdPr|rare[\s-]*earths?(?:\s*elements?)?|neodymium|praseodymium|dysprosium|terbium|yttrium|monazite|xenotime)(?![A-Za-z])', re.I)


def government_features(root, source):
    """Read retained originals; filtering is applied only after completeness checks."""
    import csv, io
    path=Path(root)/source['path']
    if filehash(path)!=source['sha256']:raise ValueError('Government snapshot SHA mismatch')
    for page in source.get('original_responses',[]):
        if filehash(Path(root)/page['path'])!=page['sha256']:raise ValueError('Government original page SHA mismatch')
    if source['kind']=='government_csv':
        text=path.read_bytes().decode(source.get('encoding','utf-8-sig'),errors=source.get('encoding_errors','strict'))
        reader=csv.DictReader(io.StringIO(text))
        if not reader.fieldnames or source['id_field'] not in reader.fieldnames:
            raise ValueError('Government CSV missing native ID column')
        return [{'attributes':dict(row)} for row in reader]
    data=json.loads(path.read_text(encoding='utf-8'))
    inventory=data.get('inventory',{})
    if not inventory.get('complete') or inventory.get('count')!=len(data.get('features',[])):
        raise ValueError('Government inventory incomplete')
    return data['features']


def ingest_government(db,root,source,candidate_version=None):
    """Government native locations and explicit parent codes, never name-based Projects."""
    from .hierarchy import link
    seen=set();count=0
    features=government_features(root,source)
    # A local nonunique business ID must not block unrelated, valid native keys.
    from collections import Counter
    keys=[str(f.get('attributes',f.get('properties',{})).get(source['id_field']) or '').strip() for f in features]
    counts=Counter(keys)
    for index,f in enumerate(features):
        a=f.get('attributes',f.get('properties',{}));key=a.get(source['id_field'])
        native=str(int(key)) if isinstance(key,(float,int)) and float(key).is_integer() else str(key or '').strip()
        terms='; '.join(str(a.get(k) or '') for k in source['commodity_fields'])
        tenure=source.get('record_filter')=='ALL_TENURE_RECORDS' and source.get('entity_kind')=='TENEMENT'
        decision=None
        if candidate_version:
            from .census import classify_ree
            structured=[k for k in source['commodity_fields'] if not any(x in k.lower() for x in ('description','summary','ore_min','gangue','min_ass'))]
            decision=classify_ree({k:a.get(k) for k in source['commodity_fields']},structured,candidate_version)
        if not tenure and not (decision['include'] if decision else REE_TERMS.search(terms)):continue
        if not native or native in seen or counts[native]>1:
            issue(db,None,source['sha256'],'GOVERNMENT_NATIVE_ID_MISSING_OR_DUPLICATE',canonical({'row':index,'native':native}))
            continue
        seen.add(native)
        kind=source.get('entity_kind','SITE')
        eid=entity(db,source['namespace'],native,kind)
        name=str(a.get(source['name_field']) or native).strip()
        lon,lat=_coordinate(a,f.get('geometry'))
        if lon is None:
            lon,lat=_coordinate({'longitude':a.get('longda94'),'latitude':a.get('latgda94')},None)
        raw={'source_kind':'LIVE_GOVERNMENT_TENURE_RECORD' if tenure else 'LIVE_GOVERNMENT_NATIVE_RECORD','source_key':source['key'],
             'native_id':native,'original_attributes':a,'original_geometry':f.get('geometry'),
             'locator':('CSV physical row '+str(index+2)) if source['kind']=='government_csv' else 'features['+str(index)+']',
             'ree_rule':'ALL_TITLES_NO_REE_OR_PROJECT_INFERENCE' if tenure else candidate_version or 'REE_COMMODITY_FIELDS_V1','matched_commodity_text':terms,
             **({'candidate_classification':decision} if decision else {}),
             'interpretation':'GOVERNMENT_RECORDED_'+kind+'_NOT_INDEPENDENT_PHYSICAL_PROJECT_COUNT'}
        db.execute('INSERT OR IGNORE INTO records VALUES(?,?,?,?,?,?,?,?,?)',
                   (eid,source['sha256'],name,source['state'],lon,lat,
                    a.get('DEPOSIT_CLASS') or a.get('mineralDepositModel') or a.get('dep_ty_gen'),
                    a.get('site_stage') or a.get('OPERATIONAL_STATUS') or a.get('DEVELOPMENT_STATUS'),canonical(raw)))
        label=str(a.get(source.get('geological_kind_field','')) or '').strip().casefold()
        geo_kind={'deposit':'DEPOSIT','prospect':'PROSPECT','occurrence':'OCCURRENCE',
                  'mineral occurrence':'OCCURRENCE'}.get(label,source.get('documented_layer_kind'))
        if kind=='SITE' and geo_kind:
            gid=entity(db,source['namespace']+'_'+geo_kind,native,geo_kind)
            db.execute('INSERT OR IGNORE INTO records VALUES(?,?,?,?,?,?,?,?,?)',
                       (gid,source['sha256'],name,source['state'],lon,lat,
                        a.get(source.get('geological_kind_field','')),None,
                        canonical(dict(raw,source_kind='LIVE_GOVERNMENT_GEOLOGICAL_ENTITY',
                                       entity_level=geo_kind,entity_level_evidence=source.get('geological_kind_field') or 'official layer definition'))))
            link(db,gid,eid,'HAS_GOVERNMENT_REPRESENTATIVE_SITE_NOT_FOOTPRINT',source['sha256'],raw['locator']+'; source entity classification')
        fields=({'Commercial':['authorisedholdername','authorisedholderid','permitstatus','permitstate','approvedate','expirydate','previouspermits']} if tenure else {
            'Resource':['RESOURCE_SUMMARY','RESOURCES','resources'],
            'Technical':['LITHOLOGY','ORE_DESCRIPTION','hostGeologicUnit','hostrocks','host_lith','mineralDepositModel','DEPOSIT_CLASS','dep_ty_gen','dep_ty_sp','min_ass'],
            'Development':['site_stage','OPERATIONAL_STATUS','DEVELOPMENT_STATUS','mineralOccurrenceType','PROJECT_STATUS'],
            'Commercial':['OPERATING_COMPANY','ASX_CODE'],
            'Strategic':source['commodity_fields']})
        for domain,names in fields.items():
            for field in names:
                text=a.get(field)
                if text is None or not str(text).strip() or str(text).strip() in ('-999','Unknown','N/A'):continue
                variable='government_'+field.lower()
                payload={'domain':domain,'original_value':text,'original_field':field,
                         'original_unit':'SOURCE_TEXT_NOT_NORMALIZED','source_key':source['key'],
                         'effective_date_status':'NOT_DISCLOSED_UNLESS_PRESENT_IN_ORIGINAL_ATTRIBUTES',
                         'captured_on':source['available_date'],'scorable':False}
                db.execute('INSERT OR IGNORE INTO observations VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                    (digest([eid,source['sha256'],variable]),eid,variable,None,None,'GOVERNMENT_SOURCE_TEXT',
                     'Native '+source['namespace']+'/'+native,source['key']+'/'+native,None,
                     source['available_date'],source['sha256'],raw['locator']+' / '+field,
                     'DOCUMENTED_GOVERNMENT_RAW','[]',canonical(payload),'government-native-v1'))
        parent=a.get(source.get('parent_id_field',''))
        if parent and (candidate_version!='ree-candidate-v3' or str(parent).strip()):
            # Existing WA parent IDs and their established kind stay stable.
            namespace=source.get('parent_namespace') or ('WA_MINDEX_PROJECT' if source['namespace']=='WA_MINDEX_SITE' else source['namespace']+'_PROJECT')
            pid=entity(db,namespace,str(parent),source.get('parent_kind','PROJECT_CANDIDATE'))
            db.execute('INSERT OR IGNORE INTO records VALUES(?,?,?,?,?,?,?,?,?)',
                       (pid,source['sha256'],str(a.get(source['parent_name_field']) or parent),source['state'],
                        None,None,None,None,canonical({'source_kind':'LIVE_GOVERNMENT_PROJECT_PARENT',
                        'project_code':parent,'original_attributes':a,'role':'EXPLICIT_SOURCE_PARENT_NOT_TECHNICAL_SCOPE_EQUIVALENCE'})))
            link(db,pid,eid,'GOVERNMENT_PROJECT_SITE_MEMBERSHIP',source['sha256'],
                 source['parent_id_field']+'='+str(parent)+'; '+source['id_field']+'='+native)
            if geo_kind:
                link(db,pid,gid,'GOVERNMENT_PROJECT_CONTAINS_'+geo_kind,source['sha256'],
                     source['parent_id_field']+'='+str(parent)+'; '+source['id_field']+'='+native)
        count+=1
    return {'raw_records':len(features),'ree_native_records':count}


def live_government_inventory(db,snapshots,current=None):
    """Separate current source records, native entities, parents and registry Projects."""
    selected={s['sha256']:s for s in snapshots if s.get('national_government')}
    rows=[]
    for r in db.execute('SELECT e.*,r.* FROM entities e JOIN records r USING(entity_id) ORDER BY e.entity_id,r.source_sha'):
        if r['source_sha'] not in selected:continue
        if current is not None and (r['entity_id'],r['source_sha']) not in current['record_ids']:continue
        raw=json.loads(r['raw']);s=selected[r['source_sha']]
        attrs=raw.get('original_attributes',{})
        if current is not None and raw.get('source_kind')=='LIVE_GOVERNMENT_PROJECT_PARENT':
            # A parent's first inserted child may differ by classifier/history.
            # Child geology/tenure is not a property of the whole parent.
            attrs={'project_code':raw.get('project_code'),'project_name':r['name']}
        rows.append({'entity_id':r['entity_id'],'kind':r['kind'],'namespace':r['native_namespace'],
                     'native_id':r['native_id'],'name':r['name'],'state':r['state'],
                     'longitude':r['longitude'],'latitude':r['latitude'],'source_key':s['key'],
                     'source_sha256':r['source_sha'],'locator':raw.get('locator'),
                     'source_role':raw.get('source_kind'),'original_attributes':canonical(attrs)})
    return rows


def live_government_coverage(root,snapshots,rows):
    out=[]
    for s in snapshots:
        if not s.get('national_government'):continue
        current=[r for r in rows if r['source_sha256']==s['sha256']]
        try:
            total=len(government_features(root,s));status='COMPLETE_SOURCE_INVENTORY_NOT_COMPLETE_NATIONAL_PROJECT_CENSUS'
        except Exception as exc:
            total=None;status='SOURCE_INVALID: '+str(exc)
        out.append({'state':s['state'],'source_key':s['key'],'raw_records':total,
                    'ree_native_entities':len({r['entity_id'] for r in current if r['source_role']=='LIVE_GOVERNMENT_NATIVE_RECORD'}),
                    'tenement_entities':len({r['entity_id'] for r in current if r['kind']=='TENEMENT'}),
                    'explicit_project_parents':len({r['entity_id'] for r in current if r['source_role']=='LIVE_GOVERNMENT_PROJECT_PARENT'}),
                    'project_records':len({r['entity_id'] for r in current if r['kind']=='PROJECT'}),
                    'source_sha256':s['sha256'],'status':status})
    return out


def government_link_candidates(db,snapshots,mapping=None,version=None,current=None):
    """Source-location hints only; a name or proximity can never confirm identity."""
    from .resolution import normalized,GEO
    shas={s['sha256'] for s in snapshots};live=live_government_inventory(db,snapshots,current)
    groups={}
    for r in live:
        if r['source_role']=='LIVE_GOVERNMENT_NATIVE_RECORD':groups.setdefault((r['state'],normalized(r['name'])),[]).append(r)
    for r in db.execute("SELECT e.entity_id,e.kind,e.native_namespace namespace,r.* FROM entities e JOIN records r USING(entity_id) WHERE e.kind IN ('DEPOSIT','PROJECT')"):
        if r['source_sha'] in shas:
            if current is not None and (r['entity_id'],r['source_sha']) not in current['record_ids']:continue
            groups.setdefault((r['state'],normalized(r['name'])),[]).append(dict(r,source_sha256=r['source_sha']))
    pairs={}
    for (state,name),members in groups.items():
        # Stable endpoint order also binds each source to the advertised ID.
        # Sorting IDs after choosing sources swapped provenance on some pairs.
        members=sorted(members,key=lambda r:(r['entity_id'],r['source_sha256']))
        for i,a in enumerate(members):
            for b in members[i+1:]:
                if a['entity_id']==b['entity_id'] or a['namespace']==b['namespace'] or a['source_sha256']==b['source_sha256']:continue
                key=tuple(sorted((a['entity_id'],b['entity_id'])))
                distance=None
                if all(r.get('longitude') is not None and r.get('latitude') is not None for r in (a,b)):
                    distance=GEO.inv(a['longitude'],a['latitude'],b['longitude'],b['latitude'])[2]
                pairs.setdefault(key,dict(a=key[0],b=key[1],name=name,state=state,distance_m=distance,
                    status='CANDIDATE_NAME_STATE_ONLY_NO_IDENTITY_EQUIVALENCE',source_a=a['source_sha256'],source_b=b['source_sha256']))
    if mapping is not None:
        represented={(mapping.get(r['parent_id'],r['parent_id']),r['child_id']) for r in db.execute(
            "SELECT parent_id,child_id,source_sha FROM relations WHERE relation='HAS_GOVERNMENT_REPRESENTATIVE_SITE_NOT_FOOTPRINT'") if r['source_sha'] in shas}
        for row in pairs.values():
            a,b=row['a'],row['b']
            if (mapping.get(a,a),b) in represented or (mapping.get(b,b),a) in represented:
                row['status']='CONFIRMED_REPRESENTATIVE_SITE_RELATION_NOT_IDENTITY'
    if version=='multi-evidence-candidates-v2':
        # Inverted indices widen discovery without changing canonical identity.
        # Bare native numbers, ownership, distance and tenure are not merge rules.
        nodes={r['entity_id']:r for r in live};tokens={}
        for r in db.execute("SELECT e.entity_id,e.native_namespace namespace,e.native_id,e.kind,r.* FROM entities e JOIN records r USING(entity_id) WHERE e.kind IN ('DEPOSIT','PROJECT') ORDER BY r.source_sha"):
            if r['source_sha'] in shas and (current is None or (r['entity_id'],r['source_sha']) in current['record_ids']):nodes.setdefault(r['entity_id'],dict(r,source_sha256=r['source_sha']))
        for eid,r in sorted(nodes.items()):
            raw=json.loads(r.get('raw') or '{}');attrs=json.loads(r.get('original_attributes') or '{}') or raw.get('original_attributes',{})
            current_aliases=current.get('project_aliases',{}) if current is not None else {}
            keys={('name',normalized(current_aliases[eid][0] if eid in current_aliases else r.get('name') or ''))}
            for field in ('former_name','alternativeName','other_names','aliases','project_name','proj_title'):
                value=(current_aliases[eid] if field=='aliases' else None) if eid in current_aliases else attrs.get(field) or raw.get(field)
                for name in (value if isinstance(value,list) else re.split(r'[;|]',str(value or ''))):
                    if len(str(name).strip())>=4:keys.add(('alias',normalized(str(name))))
            for field in ('tenement','tenements','TENEMENTS','permit','LEASE_NO'):
                for title in re.findall(r'\b[EMLRPS]\s*\d+\s*/\s*\d+\b',str(attrs.get(field) or ''),re.I):keys.add(('tenement',re.sub(r'\s','',title).upper()))
            # Explicit foreign code fields retain their namespace. Never equate
            # unrelated sources solely because they both have a row numbered 1.
            for field,namespace in [('ga_eno','GA_ENO'),('MINERAL_DEPOSIT_NO','SA_MINDEP'),('deposit_no','SA_MINDEP')]:
                if attrs.get(field):keys.add(('official_id',namespace+':'+str(attrs[field])))
            if str(r.get('namespace','')).startswith('GA_') and r.get('native_id'):keys.add(('official_id','GA_ENO:'+str(r['native_id'])))
            if str(r.get('namespace','')).startswith('SA_MINDEP') and r.get('native_id'):keys.add(('official_id','SA_MINDEP:'+str(r['native_id'])))
            r['_holder_dates']={k:attrs[k] for k in ('authorisedholdername','approvedate','expirydate','OPERATING_COMPANY') if attrs.get(k)}
            for kind,key in keys:
                if key:tokens.setdefault((r.get('state'),('name_or_alias' if kind in ('name','alias') else kind),key),set()).add(eid)
        for (state,kind,token),ids in sorted(tokens.items(),key=str):
            members=sorted(ids)
            for i,a in enumerate(members):
                for b in members[i+1:]:
                    ra,rb=nodes[a],nodes[b]
                    if ra.get('namespace')==rb.get('namespace') or ra['source_sha256']==rb['source_sha256']:continue
                    pair=pairs.setdefault((a,b),dict(a=a,b=b,name=ra.get('name'),state=state,distance_m=None,
                        status='CANDIDATE_MULTI_EVIDENCE_NOT_IDENTITY_EQUIVALENCE',source_a=ra['source_sha256'],source_b=rb['source_sha256']))
                    evidence=set(json.loads(pair.get('evidence_keys','[]')));evidence.add(kind+':'+token)
                    pair['evidence_keys']=canonical(sorted(evidence));pair['holder_dates']=canonical({a:ra.get('_holder_dates',{}),b:rb.get('_holder_dates',{})})
        for rel in db.execute('SELECT * FROM relations ORDER BY relation_id'):
            if rel['source_sha'] not in shas:continue
            if current is not None and {rel['parent_id'],rel['child_id']}&current.get('invalid_native_ids',set()):continue
            if current is not None and rel['relation']=='HAS_TECHNICALLY_DOCUMENTED_RESOURCE_SCOPE' and (rel['child_id'],rel['source_sha']) not in current['record_ids']:continue
            for eid in (rel['parent_id'],rel['child_id']):
                if eid in nodes:continue
                row=db.execute('''SELECT e.entity_id,e.native_namespace namespace,e.native_id,e.kind,r.*
                    FROM entities e JOIN records r USING(entity_id) WHERE e.entity_id=? AND r.source_sha=?''',(eid,rel['source_sha'])).fetchone()
                if row is not None and (current is None or (eid,rel['source_sha']) in current['record_ids']):nodes[eid]=dict(row,source_sha256=row['source_sha'])
            if rel['parent_id'] not in nodes or rel['child_id'] not in nodes:continue
            if current is not None and (rel['parent_id'] in current['historical_scope_ids'] or rel['child_id'] in current['historical_scope_ids']):continue
            a,b=sorted((rel['parent_id'],rel['child_id']));ra,rb=nodes[a],nodes[b]
            pair=pairs.setdefault((a,b),dict(a=a,b=b,name=ra.get('name'),state=ra.get('state'),distance_m=None,
                status='SOURCE_BOUND_TYPED_RELATION_NOT_IDENTITY_EQUIVALENCE',source_a=ra['source_sha256'],source_b=rb['source_sha256']))
            pair['relation_evidence']=canonical(dict(parent_id=rel['parent_id'],child_id=rel['child_id'],relation=rel['relation'],source_sha256=rel['source_sha'],locator=rel['locator']))
    return [pairs[k] for k in sorted(pairs)]


def raw_domain_coverage(db,snapshot_shas,validation_version=None,active_claim_ids=None,current=None):
    """Validated numeric statements and typed government text are separate evidence classes."""
    from .selection import evidence_domain,observation_visible
    groups={}
    for r in db.execute('SELECT o.*,e.kind FROM observations o JOIN entities e USING(entity_id)'):
        if r['source_sha'] not in snapshot_shas:continue
        if current is not None and r['obs_id'] not in current['observation_ids']:continue
        if active_claim_ids is not None and r['transform_version'] in ('normalization-v1','commercial-event-v1') and r['obs_id'] not in active_claim_ids:continue
        raw=json.loads(r['raw'])
        if validation_version and not observation_visible(raw,snapshot_shas,validation_version):continue
        v=r['variable'];domain=evidence_domain(v,raw)
        if domain not in ('Resource','Strategic','Technical','Development','Infrastructure','Commercial'):continue
        key=(domain,r['status']);g=groups.setdefault(key,{'observations':set(),'entities':set(),'sources':set(),'numeric':set()})
        ident=(r['entity_id'],r['variable'],r['source_sha'],r['statement_id'],r['scope'],r['value'])
        g['observations'].add(ident);g['entities'].add(r['entity_id']);g['sources'].add(r['source_sha'])
        if r['value'] is not None:g['numeric'].add(ident)
    return [dict(domain=d,evidence_status=s,distinct_statement_values=len(g['observations']),
                 entities=len(g['entities']),sources=len(g['sources']),numeric_values=len(g['numeric']),
                 interpretation='RAW_EVIDENCE_COUNTS_NOT_COMMON_SCORABLE_PROJECTS') for (d,s),g in sorted(groups.items())]


def resource_quality_checks(db,snapshot_shas,current=None):
    """Same-statement arithmetic, preserving reported basis and rounding intervals."""
    from .store import issue
    statements={}
    aliases={'ore_mt':'ore','grade':'grade','contained_treo_kt':'contained',
             'reported_resource_ore_mt':'ore','reported_resource_grade_pct':'grade',
             'reported_resource_contained_kt':'contained'}
    for r in db.execute("SELECT * FROM observations WHERE status='AUTO_VALIDATED'"):
        if r['source_sha'] not in snapshot_shas or r['variable'] not in aliases:continue
        if current is not None and r['obs_id'] not in current['observation_ids']:continue
        key=tuple(r[k] for k in ('entity_id','statement_id','scope','effective_date','source_sha','basis'))
        statements.setdefault(key,{})[aliases[r['variable']]]=dict(r)
    output=[]
    for key,values in statements.items():
        if not {'ore','grade','contained'}<=values.keys():continue
        ore,grade,contained=[values[k] for k in ('ore','grade','contained')]
        if ore['unit']!='Mt' or grade['unit'] not in ('%','ppm') or contained['unit']!='kt':continue
        factor=10 if grade['unit']=='%' else .001
        oh=json.loads(ore['raw']).get('rounding_half_width',0);gh=json.loads(grade['raw']).get('rounding_half_width',0);ch=json.loads(contained['raw']).get('rounding_half_width',0)
        lo=(ore['value']-oh)*(grade['value']-gh)*factor;hi=(ore['value']+oh)*(grade['value']+gh)*factor
        reported=contained['value'];bad=reported+ch<lo or reported-ch>hi
        row=dict(entity_id=key[0],statement_id=key[1],scope=key[2],effective_date=key[3],source_sha256=key[4],basis=key[5],
                 calculated_contained_kt=ore['value']*grade['value']*factor,reported_contained_kt=reported,
                 rounding_lower_kt=lo,rounding_upper_kt=hi,status='SOURCE_ARITHMETIC_CONFLICT' if bad else 'ROUNDING_COMPATIBLE',
                 interpretation='SOURCE_INTERNAL_ARITHMETIC_ONLY_NOT_BASIS_HARMONIZATION')
        output.append(row)
        if bad:issue(db,key[0],key[4],'SOURCE_RESOURCE_ARITHMETIC_CONFLICT',canonical(row))
    return sorted(output,key=canonical)


def government_explicit_relations(db,snapshots):
    """Cross-layer relations require an advertised foreign native ID, never proximity."""
    from .hierarchy import link
    shas={s['sha256'] for s in snapshots}
    for r in db.execute("SELECT r.* FROM records r JOIN entities e USING(entity_id) WHERE e.native_namespace='SA_MINING_PROJECT_SITE_NO'").fetchall():
        if r['source_sha'] not in shas:continue
        data=json.loads(r['raw']);attrs=data.get('original_attributes',{})
        native=attrs.get('MINERAL_DEPOSIT_NUMBER')
        if not native:continue
        for target in db.execute("SELECT e.entity_id,r.source_sha FROM entities e JOIN records r USING(entity_id) WHERE e.native_namespace IN ('SA_MINDEP_SITE','SA_MINDEP_SITE_DEPOSIT','SA_MINDEP_SITE_PROSPECT','SA_MINDEP_SITE_OCCURRENCE') AND e.native_id=?",(str(native),)).fetchall():
            if target['source_sha'] in shas:
                link(db,r['entity_id'],target['entity_id'],'OFFICIAL_PROJECT_REFERENCES_MINERAL_DEPOSIT_NATIVE_ID',r['source_sha'],
                     'MINERAL_DEPOSIT_NUMBER='+str(native)+'; target_source_sha256='+target['source_sha'])
