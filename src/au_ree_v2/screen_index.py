"""Complete historical discovery coverage without inventing raw evidence or Project identity."""
import csv,re,json
from pathlib import Path
from .store import entity,canonical,issue
from .hierarchy import link

def ingest(db,root,source):
    with (Path(root)/source['path']).open(encoding='utf-8-sig',newline='') as f:
        reader=csv.DictReader(f)
        required={'candidate_id','source_key','native_id','name','state','tier','source_record_ref','wa_project_code','parent_project_hint'}
        if not reader.fieldnames or not required<=set(reader.fieldnames):
            issue(db,None,source['sha256'],'SCREEN_INDEX_SCHEMA_INVALID','Required fields absent');return
        seen=set()
        for row in reader:
            cid=row['candidate_id']
            if not re.fullmatch(r'C-[a-f0-9]+',cid) or cid in seen or not row['source_key']:
                issue(db,None,source['sha256'],'SCREEN_INDEX_ROW_INVALID',canonical({'candidate_id':cid}));continue
            seen.add(cid)
            selected=db.execute("SELECT entity_id FROM entities WHERE native_namespace='LEGACY_E1_20261029_TARGET' AND native_id=?",('E1:'+cid,)).fetchone()
            parent=None
            if row['source_key']=='STATE_WA_MINDEX' and row['wa_project_code']:
                code=re.sub(r'\.0$','',row['wa_project_code'])
                parent=entity(db,'WA_MINDEX_PROJECT',code,'PROJECT_CANDIDATE')
                name=row['parent_project_hint'] or ('WA source project code '+code)
                db.execute('INSERT OR IGNORE INTO records VALUES(?,?,?,?,?,?,?,?,?)',(parent,source['sha256'],name,'WA',None,None,None,None,canonical({'status':'HISTORICAL_SCREEN_PARENT_CODE_NOT_TECHNICAL_IDENTITY','source_project_code':code,'original_raw_bytes_not_archived_by_this_index':True})))
                if selected:link(db,parent,selected['entity_id'],'INDEX_REPORTS_PARENT_CODE_NOT_TECHNICAL_IDENTITY',source['sha256'],'candidate_id='+cid+'; source project code='+code)
            db.execute('INSERT OR IGNORE INTO census_screen_index VALUES(?,?,?,?,?,?,?,?,?,?)',(cid,source['sha256'],row['source_key'],row['native_id'],row['state'],row['tier'],row['source_record_ref'],selected['entity_id'] if selected else None,parent,canonical(row)))
        if source.get('expected_rows') and len(seen)!=source['expected_rows']:
            issue(db,None,source['sha256'],'SCREEN_INDEX_ROW_COUNT_MISMATCH',canonical({'expected':source['expected_rows'],'actual':len(seen)}))

def rows(db,selected):
    return [dict(r,verification='UPSTREAM_SCREEN_INDEX_ONLY_NOT_RAW_OR_PROJECT_VERIFICATION',native_label_role='SOURCE_ADAPTER_LABEL_NOT_ASSUMED_DESIGNATED_NATIVE_ID') for r in db.execute('SELECT * FROM census_screen_index ORDER BY candidate_id,source_sha') if r['source_sha'] in selected]
