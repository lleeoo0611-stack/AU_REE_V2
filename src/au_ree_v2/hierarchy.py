"""Evidence-qualified relationships; names alone never establish equivalence."""
import json
from .store import entity,digest,canonical
from .analysis import write_csv

def build(db,snapshots,collect=True):
    if not snapshots or max(s['available_date'] for s in snapshots)<'2026-11-03':
        return []  # Versioned hierarchy policy; preserve earlier frozen replay.
    selected={s['sha256'] for s in snapshots}
    for row in db.execute('SELECT r.*,e.kind FROM records r JOIN entities e USING(entity_id)').fetchall():
        if row['source_sha'] not in selected:continue
        raw=json.loads(row['raw'])
        # Source-advertised WA project codes are parent grouping evidence, not legal ownership.
        if raw.get('source_key')=='STATE_WA_MINDEX':
            features=raw.get('all_selected_features') or [{'attributes':raw.get('original_attributes',{})}]
            for f in features:
                a=f.get('attributes',{});site=a.get('site_code');code=a.get('proj_code')
                if not site:continue
                sid=entity(db,'WA_MINDEX_SITE',site,'SITE')
                db.execute('INSERT OR IGNORE INTO records VALUES(?,?,?,?,?,?,?,?,?)',(sid,row['source_sha'],a.get('short_name') or str(site),'WA',None,None,None,None,canonical(a)))
                link(db,sid,row['entity_id'],'DOCUMENTED_BY_SOURCE_RECORD',row['source_sha'],'native site_code '+str(site))
                if code:
                    pid=entity(db,'WA_MINDEX_PROJECT',code,'PROJECT_CANDIDATE')
                    db.execute('INSERT OR IGNORE INTO records VALUES(?,?,?,?,?,?,?,?,?)',(pid,row['source_sha'],a.get('proj_title') or str(code),'WA',None,None,None,None,canonical({'status':'GOVERNMENT_PARENT_CODE_NOT_TECHNICALLY_VALIDATED',**a})))
                    link(db,pid,sid,'GOVERNMENT_PROJECT_SITE_MEMBERSHIP',row['source_sha'],'proj_code='+str(code)+'; site_code='+str(site))
    # Explicit technical scope from hash-bound primary claims gives deposit relation.
    for row in db.execute("SELECT * FROM observations WHERE status='AUTO_VALIDATED' AND variable='ore_mt'").fetchall():
        if row['source_sha'] not in selected:continue
        dep=entity(db,'PRIMARY_RESOURCE_SCOPE',row['statement_id']+'|'+row['scope'],'DEPOSIT_SCOPE')
        db.execute('INSERT OR IGNORE INTO records VALUES(?,?,?,?,?,?,?,?,?)',(dep,row['source_sha'],row['scope'],None,None,None,None,None,row['raw']))
        link(db,row['entity_id'],dep,'HAS_TECHNICALLY_DOCUMENTED_RESOURCE_SCOPE',row['source_sha'],row['locator'])
    return rows(db,snapshots) if collect else []


def rows(db,snapshots):
    """Read relationships after all source and identity rules have run."""
    if not snapshots or max(s['available_date'] for s in snapshots)<'2026-11-03':return []
    selected={s['sha256'] for s in snapshots}
    return [dict(r) for r in db.execute('''SELECT rel.*,p.kind parent_kind,c.kind child_kind
        FROM relations rel JOIN entities p ON p.entity_id=rel.parent_id JOIN entities c ON c.entity_id=rel.child_id
        ORDER BY relation_id''') if r['source_sha'] in selected]

def link(db,parent,child,relation,sha,locator):
    db.execute('INSERT OR IGNORE INTO relations VALUES(?,?,?,?,?,?,?)',
               (digest([parent,child,relation,sha]),parent,child,relation,'2026-11-03',sha,locator))
