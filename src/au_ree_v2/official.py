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

COMMODITY_VERSION = 'minedex-commodity-v2'
LANTHANIDES = 'lanthanum cerium praseodymium neodymium promethium samarium europium gadolinium terbium dysprosium holmium erbium thulium ytterbium lutetium'.split()


def commodity_classification(label):
    """Exact normalized source labels; mineral mass is never oxide mass."""
    normalized=' '.join((label or '').casefold().split())
    elements={x for x in LANTHANIDES+['yttrium']}
    if normalized in elements or normalized in {x+' oxide' for x in elements}:
        return dict(normalized=normalized,category='MAIN_ELEMENT_OR_OXIDE',include=True,reason='EXACT_LANTHANIDE_OR_Y_LABEL',version=COMMODITY_VERSION)
    if normalized in {'rare earth oxides','rare earth elements','heavy rare earth elements','light rare earth elements','heavy rare earth oxides','light rare earth oxides'}:
        return dict(normalized=normalized,category='MAIN_REE_AGGREGATE',include=True,reason='EXPLICIT_REE_AGGREGATE_Y_UNKNOWN',version=COMMODITY_VERSION)
    category=('RELATED_SCANDIUM' if normalized in {'scandium','scandium oxide'} else 'RELATED_MINERAL' if normalized in {'monazite','xenotime'} else 'UNKNOWN_EMPTY' if not normalized else 'OTHER_OR_UNRECOGNIZED')
    return dict(normalized=normalized,category=category,include=False,reason='SEPARATE_RELATED_SCOPE_NO_REO_CONVERSION' if category.startswith('RELATED') else 'NO_EXACT_REE_LABEL_NOT_IN_MAIN_COHORT',version=COMMODITY_VERSION)


def minedex_resource_rows(root, source, version=COMMODITY_VERSION):
    """Original ZIP and CSV member checked before interpreting resource totals."""
    import zipfile,io,hashlib
    path=Path(root)/source['path']
    if filehash(path)!=source['sha256']:raise ValueError('MINEDEX_BATCH_SHA_MISMATCH')
    with zipfile.ZipFile(path) as z:
        names=[n for n in z.namelist() if n.lower().endswith('.csv')]
        if len(names)!=1:raise ValueError('MINEDEX_BATCH_CSV_AMBIGUOUS')
        raw=z.read(names[0]);member_sha=hashlib.sha256(raw).hexdigest()
    reader=csv.DictReader(io.StringIO(raw.decode('utf-8-sig')))
    required={'PROJ_CODE','LOC_SITE','EST_COM','RES_QTY','RES_QTY_U','RES_CON','RES_CON_U','PROJ_NAME'}
    if not required.issubset(reader.fieldnames or []):raise ValueError('MINEDEX_RESOURCE_SCHEMA_MISMATCH')
    rows=list(reader);keys=[(r['PROJ_CODE'],r['EST_COM']) for r in rows]
    if len(keys)!=len(set(keys)):raise ValueError('MINEDEX_DUPLICATE_PROJECT_COMMODITY')
    result=[]
    for line,r in enumerate(rows,2):
        if version=='minedex-resource-batch-v1':
            included=bool(re.search(r'rare earth|yttrium|lanthanum|cerium|neodymium|praseodymium|dysprosium|terbium',r['EST_COM'],re.I))
        elif version==COMMODITY_VERSION:included=commodity_classification(r['EST_COM'])['include']
        else:raise ValueError('UNKNOWN_COMMODITY_VERSION')
        if not included:continue
        result.append(dict(source_sha256=source['sha256'],csv_sha256=member_sha,member=names[0],csv_line=line,raw=r))
    return rows,result


def ingest_minedex_resources(db, root, source, version=COMMODITY_VERSION):
    """Native-ID relations, not issuer Project equivalence or JORC promotion."""
    _,rows=minedex_resource_rows(root,source,version)
    for item in rows:
        r=item['raw'];native=r['PROJ_CODE']
        project=entity(db,'WA_MINDEX_PROJECT',native,'PROJECT_CANDIDATE')
        record=entity(db,'WA_MINEDEX_RESOURCE_PROJECT_COMMODITY',native+'|'+r['EST_COM'],'SOURCE_RECORD')
        locator=item['member']+':'+str(item['csv_line'])
        payload=dict(item,source_kind='MINEDEX_RESOURCE_BATCH',project_candidate_id=project,
            basis=r['EST_COM'],basis_note='Commodity label only; Y inclusion in total REO not disclosed',
            estimate_date=None,jorc_classes='Measured+Indicated+Inferred combined; no class split',
            limitations=['PRODUCT_DATE_NOT_ESTIMATE_DATE','NO_DEPOSIT_ALLOCATION','NO_RESOURCE_RESERVE_SUM','NOT_ORIGINAL_JORC_DOCUMENT'])
        db.execute('INSERT OR IGNORE INTO records VALUES(?,?,?,?,?,?,?,?,?)',(record,source['sha256'],r['PROJ_NAME']+' | '+r['EST_COM'],'WA',float(r['LONGITUDE']),float(r['LATITUDE']),None,None,canonical(payload)))
        db.execute('INSERT OR IGNORE INTO relations VALUES(?,?,?,?,?,?,?)',(digest([project,record,source['sha256']]),project,record,'RESOURCE_SUMMARY_FOR_NATIVE_PROJECT',source['publication_date'],source['sha256'],locator))
        site=db.execute("SELECT entity_id FROM entities WHERE native_namespace='WA_MINDEX_SITE' AND native_id=?",(r['LOC_SITE'],)).fetchone()
        if site:
            db.execute('INSERT OR IGNORE INTO relations VALUES(?,?,?,?,?,?,?)',(digest([record,site[0],source['sha256']]),record,site[0],'REPRESENTATIVE_RESOURCE_LOCATION_SITE_NOT_RESOURCE_EXTENT',source['publication_date'],source['sha256'],locator))
        for field,unitfield in [('RES_QTY','RES_QTY_U'),('RES_QTY_G','RES_QTY_GU'),('RES_CON','RES_CON_U'),('RV_QTY','RV_QTY_U'),('RV_QTY_G','RV_QTY_GU'),('RV_CON','RV_CON_U')]:
            value=float(r[field]) if r[field].strip() else None
            issues=['ESTIMATE_DATE_AND_REO_BASIS_UNVERIFIED']
            if value is not None and (not math.isfinite(value) or value<0):issues.append('INVALID_VALUE')
            raw=dict(payload,domain='Resource',variable='official_batch_'+field.lower(),original_value=r[field],original_unit=r[unitfield],value=value,unit=r[unitfield] or None,date_role='PRODUCT_UPDATE_NOT_RESOURCE_ESTIMATE')
            db.execute('INSERT OR IGNORE INTO observations VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(digest([record,source['sha256'],field]),record,raw['variable'],value,raw['unit'],r['EST_COM'],native+' | '+r['EST_COM'],native+'|'+r['EST_COM'],raw['jorc_classes'] if field.startswith('RES_') else 'Proven+Probable combined',source['publication_date'],source['sha256'],locator,'OFFICIAL_SUMMARY_SCOPE_UNVERIFIED',canonical(issues),canonical(raw),'minedex-resource-batch-v1'))
    return len(rows)


def minedex_resource_report(db,root,snapshots,out,version=COMMODITY_VERSION):
    from .analysis import write_csv
    reports=[];inventory=[]
    for source in snapshots:
        if source['kind']!='minedex_resource_batch':continue
        allrows,rr=minedex_resource_rows(root,source,version)
        for item in rr:
            r=item['raw'];native=db.execute("SELECT entity_id FROM entities WHERE native_namespace='WA_MINDEX_PROJECT' AND native_id=?",(r['PROJ_CODE'],)).fetchone()
            site=db.execute("SELECT entity_id FROM entities WHERE native_namespace='WA_MINDEX_SITE' AND native_id=?",(r['LOC_SITE'],)).fetchone()
            inventory.append(dict(project_code=r['PROJ_CODE'],project_name=r['PROJ_NAME'],native_project_candidate_id=native[0] if native else None,location_site_code=r['LOC_SITE'],site_id=site[0] if site else None,commodity=r['EST_COM'],resource_qty=r['RES_QTY'] or None,resource_qty_unit=r['RES_QTY_U'] or None,resource_grade=r['RES_QTY_G'] or None,resource_grade_unit=r['RES_QTY_GU'] or None,resource_contained=r['RES_CON'] or None,resource_contained_unit=r['RES_CON_U'] or None,reserve_qty=r['RV_QTY'] or None,estimate_date=None,extract_date=r.get('EXTRACT_DA') or None,source_sha256=item['source_sha256'],csv_sha256=item['csv_sha256'],locator=item['member']+':'+str(item['csv_line']),mapping_status='NATIVE_ID_ONLY_NOT_CANONICAL_PROJECT_EQUIVALENCE',reo_basis_status='Y_INCLUSION_NOT_DISCLOSED',date_status='PRODUCT_DATE_ONLY_NOT_ESTIMATE_DATE'))
        reports.append(dict(source_sha256=source['sha256'],csv_sha256=rr[0]['csv_sha256'] if rr else None,all_commodity_rows=len(allrows),ree_commodity_rows=len(rr),ree_native_project_codes=len({r['raw']['PROJ_CODE'] for r in rr}),source_update=source.get('source_update'),fields=list(allrows[0]) if allrows else [],mapped_location_site_rows=sum(bool(r['site_id']) for r in inventory),distinct_mapped_sites=len({r['site_id'] for r in inventory if r['site_id']}),unmatched_location_site_codes=sorted({r['location_site_code'] for r in inventory if not r['site_id']}),estimate_dates=sum(bool(r.get('EXTRACT_DA')) for r in allrows),jurisdiction='WA_ONLY_NOT_NATIONAL',resource_aggregation='NO_SUM_ACROSS_COMMODITIES_RESOURCE_RESERVE_OR_YEARS'))
    if version==COMMODITY_VERSION:
        labels=sorted({r['EST_COM'] for source in snapshots if source['kind']=='minedex_resource_batch' for r in minedex_resource_rows(root,source,version)[0]})
        write_csv(Path(out)/'minedex_commodity_decisions.csv',[dict(source_label=x,**commodity_classification(x)) for x in labels],['source_label','normalized','category','include','reason','version'])
    if version==COMMODITY_VERSION:
        for report in reports:
            source=next(s for s in snapshots if s['sha256']==report['source_sha256'])
            allrows,current=minedex_resource_rows(root,source,version);_,legacy=minedex_resource_rows(root,source,'minedex-resource-batch-v1')
            from collections import Counter
            report['commodity_version']=version;report['all_source_label_category_counts']=dict(Counter(commodity_classification(r['EST_COM'])['category'] for r in allrows))
            oldkeys={(r['raw']['PROJ_CODE'],r['raw']['EST_COM']) for r in legacy}
            report['recovered_rows']=[r for r in current if (r['raw']['PROJ_CODE'],r['raw']['EST_COM']) not in oldkeys]
    write_csv(Path(out)/'minedex_resource_batch.csv',inventory,list(inventory[0]) if inventory else ['project_code','commodity','source_sha256'])
    (Path(out)/'minedex_resource_batch.json').write_text(canonical(reports)+'\n',encoding='utf8')
    return reports

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
    original=next((r for r in db.execute("SELECT sha FROM sources WHERE source_key='wa_dmpe_ree2026_original'") if selected_shas is None or r['sha'] in selected_shas),None)
    if original:
        for row in output:row['locator']=row['locator'].replace('physical PDF page 1','original physical PDF page 2')+'; original PDF SHA256='+original['sha']+'; legacy transcription retained'
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

def domain_evidence_coverage(db, inventory, resources, gis_values, prospectus=None, selected_shas=None, selection=None, prepared=None, criteria=None):
    """Descriptive source facts must not silently become six-domain scored values."""
    project_ids={r[0] for r in db.execute("SELECT entity_id FROM entities WHERE kind='PROJECT'")}
    if selected_shas is not None:
        project_ids &= {r['entity_id'] for r in db.execute('SELECT entity_id,source_sha FROM records') if r['source_sha'] in selected_shas}
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
            variables={'Strategic':('magnet_reo_share_pct','ndpr_share_pct'),
                       'Technical':('recovery_pct','uranium_ppm','thorium_ppm'),
                       'Development':('study_maturity_ord',),
                       'Commercial':('conditional_senior_debt_usd_m','offtake_nameplate_pct','financing_ord')}.get(domain,())
            observations=[dict(o) for o in db.execute("SELECT variable,source_sha,locator FROM observations WHERE entity_id=? AND status='AUTO_VALIDATED'",(eid,)) if o['variable'] in variables and (selected_shas is None or o['source_sha'] in selected_shas)]
            if observations:
                state='PRIMARY_SCOPED_OBSERVATIONS';evidence=canonical(observations)
            name=db.execute('SELECT name FROM records WHERE entity_id=? ORDER BY source_sha LIMIT 1',(eid,)).fetchone()[0]
            rows.append({"project_id":eid,"project_name":listed_row.get("project_name") or profile.get("project_name") or name,
                         "domain":domain,"evidence_state":state,"evidence_reference":evidence,
                         "scorable":int(any(o['variable'] in {'Strategic':('magnet_reo_share_pct',),'Technical':('recovery_pct',),'Development':('study_maturity_ord',),'Commercial':('financing_ord',)}.get(domain,()) for o in observations) or (domain=="Resource" and state=="SCOPED_RESOURCE_VALIDATED") or
                                        (domain=="Infrastructure" and state=="OFFICIAL_DISTANCE_AVAILABLE"))})
    if selection is not None:
        # Scorability comes from the exact matrix selection, rather than an
        # independent list of raw variable names. Raw descriptions stay intact.
        definitions={c['code']:c for c in criteria}
        main=set(selection['policy']['main_codes'])
        for row in rows:
            codes=[k for k,c in definitions.items() if c['domain']==row['domain']]
            eid=row['project_id'];pid=selection['mapping'].get(eid,eid)
            selected=set(selection['values'].get(pid,{}))
            if eid in resources:selected.add('R1')
            selected.update(k for k,c in definitions.items() if c['variable'] in gis_values.get(eid,{}))
            row['scorable']=int(any(k in selected for k in codes if k in main))
            row['exploratory_scorable']=int(any(k in selected for k in codes))
            row['selection_policy']=selection['policy']['version']
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
