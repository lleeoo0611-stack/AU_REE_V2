"""Non-destructive, cutoff-bound national identity resolution and candidate census."""
import json,re,unicodedata,math
from pathlib import Path
from pyproj import Geod
from pypdf import PdfReader
from .store import entity,digest,canonical,issue
from .hierarchy import link
from .national import NAME_FIELDS

SITE_FIELDS={'STATE_WA_MINDEX':('site_code','WA_MINDEX_SITE'),
 'STATE_QLD_MINOCC':('site_no','QLD_MINOCC_SITE'),'STATE_TAS_MRT':('DEPOSIT_ID','TAS_MRT_SITE'),
 'NT_MODAT_WFS':('identifier','NT_MODAT_SITE'),'NSW_METINDEX':('occurrence_id','NSW_METINDEX_SITE'),
 'VIC_MINSITE':('siteid','VIC_MINSITE_SITE'),'SA_GEODATA_MINDEP':('MINERAL_DEPOSIT_NO','SA_MINDEP_SITE'),
 'SA_CRITICAL_REE':('MINERAL_DEPOSIT_NO','SA_CRITICAL_SITE')}
GEO=Geod(ellps='GRS80')
def native(value):
    return str(int(value)) if isinstance(value,(float,int)) and not isinstance(value,bool) and float(value).is_integer() else str(value)
def normalized(name):
    return re.sub(r'\W+',' ',unicodedata.normalize('NFKC',name).casefold().replace('mt.','mount ').replace('mt ','mount ')).strip()


def document_relations(db, root, snapshots, cutoff):
    """An explicit deposit-within-project sentence adds hierarchy, never identity.

    Both endpoints must already be registered uniquely. Representative points,
    fuzzy names and proximity cannot satisfy this rule.
    """
    from .selection import source_check
    from .pdf_extract import project_registry, _matches
    sources={s['sha256']:s for s in snapshots};registry=project_registry(root);decisions=[]
    names={}
    for r in db.execute("SELECT r.name,e.entity_id FROM records r JOIN entities e USING(entity_id) WHERE e.kind='PROJECT' AND r.source_sha IN ("+','.join('?' for _ in sources)+')',tuple(sources)):
        name=re.sub(r'\s+(?:REE|Project)$','',r['name'],flags=re.I)
        names.setdefault(normalized(name),set()).add(r['entity_id'])
    for artifact in snapshots:
        if artifact['kind']!='document_extraction':continue
        if source_check(artifact,cutoff,Path(root)):continue
        data=json.loads((Path(root)/artifact['path']).read_text(encoding='utf-8'))
        source=sources.get(data['source_sha256'])
        if source_check(source,cutoff,Path(root)):continue
        for page in data['pages']:
            text=re.sub(r'\s+',' ',page['text'])
            pattern=r'\b([A-Z][A-Za-z]+)\s+Rare Earth Elements?\s*\(REE\)\s+[Dd]eposit,?\s+located on its\s+([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+){0,2})\s+Project'
            for m in re.finditer(pattern,text):
                children=_matches(m.group(1),registry);parents=names.get(normalized(m.group(2)),set())
                if len(children)!=1 or len(parents)!=1:continue
                child=children[0]['entity_id'];parent=next(iter(parents))
                if child==parent:continue
                relation='CONTAINS_DOCUMENTED_DEPOSIT_PROJECT_CASE_NOT_IDENTITY'
                locator='physical page '+str(page['physical_page'])+'; '+m.group(0)
                link(db,parent,child,relation,source['sha256'],locator)
                decisions.append(dict(parent_id=parent,child_id=child,relation=relation,source_sha256=source['sha256'],locator=locator,
                                      rule='EXPLICIT_LOCATED_ON_ITS_PROJECT_V1',status='CONFIRMED_HIERARCHY_NOT_CANONICAL_MERGE'))
    return decisions

def resolve(db,root,snapshots,cutoff=None,rule_version=None):
    selected={s['sha256'] for s in snapshots};by_key={s['key']:s for s in snapshots}
    path=Path(root)/'data/identity_links.json'
    cutoff=cutoff or max((s['available_date'] for s in snapshots),default='0001-01-01')
    if not snapshots or max(s['available_date'] for s in snapshots)<'2026-11-03':
        members={r['entity_id']:dict(entity_id=r['entity_id'],kind=r['kind'],canonical_id=r['entity_id'],status='EARLIER_POLICY_RETAINED_SOURCE_ID') for r in db.execute('SELECT e.entity_id,e.kind,r.source_sha FROM entities e JOIN records r USING(entity_id)') if r['source_sha'] in selected}
        return dict(ledger=[],accepted=[],membership=list(members.values()),candidates=[],mapping={k:k for k in members})
    ledger=[];accepted=[]
    native_labels={}
    for row in db.execute("SELECT raw,name,source_sha FROM records r JOIN entities e USING(entity_id) WHERE e.kind='SOURCE_RECORD'"):
        if row['source_sha'] not in selected:continue
        raw=json.loads(row['raw']);family=raw.get('source_key')
        if raw.get('source_kind')!='LEGACY_NATIONAL_E1_SELECTED_FEATURE' or family not in SITE_FIELDS:continue
        field,_=SITE_FIELDS[family]
        for f in raw.get('all_selected_features') or [{'attributes':raw.get('original_attributes',{})}]:
            a=f.get('attributes',{});value=a.get(field)
            if value is None:continue
            label=next((str(a[k]) for k in NAME_FIELDS.get(family,()) if a.get(k)),row['name'])
            native_labels.setdefault((family,native(value)),set()).add(normalized(label))
    for r in db.execute("SELECT r.* FROM records r JOIN entities e USING(entity_id) WHERE e.kind='SOURCE_RECORD' ORDER BY entity_id").fetchall():
        if r['source_sha'] not in selected:continue
        payload=json.loads(r['raw'])
        if payload.get('source_kind')!='LEGACY_NATIONAL_E1_SELECTED_FEATURE':continue
        family=payload['source_key'];attrs=payload['original_attributes'];targets=[];status='UNRESOLVED_NATIVE_ID'
        if family in SITE_FIELDS:
            field,namespace=SITE_FIELDS[family]
            features=payload.get('all_selected_features') or [{'attributes':attrs}]
            for f in features:
                a=f.get('attributes',{});value=a.get(field)
                if value is None:continue  # Never search arbitrary attributes for a matching ID.
                if len(native_labels.get((family,native(value)),set()))>1:
                    issue(db,r['entity_id'],r['source_sha'],'DESIGNATED_NATIVE_ID_NONUNIQUE',canonical({'source':family,'native_id':native(value),'labels':sorted(native_labels[(family,native(value))])}))
                    continue
                sid=entity(db,namespace,native(value),'SITE')
                db.execute('INSERT OR IGNORE INTO records VALUES(?,?,?,?,?,?,?,?,?)',(sid,r['source_sha'],r['name'],r['state'],None,None,None,None,canonical({'role':'NATIVE_GOVERNMENT_RECORDED_LOCATION_NOT_MINING_FOOTPRINT','source':family,'native_field':field,'native_id':value})))
                link(db,sid,r['entity_id'],'SAME_NATIVE_SITE_SOURCE_RECORD',r['source_sha'],field+'='+native(value))
                targets.append(sid)
            ambiguous=any(len(native_labels.get((family,native(f.get('attributes',{}).get(field))),set()))>1 for f in features)
            status='NATIVE_ID_NONUNIQUE_REVIEW' if ambiguous else 'NATIVE_SITE_LINKED_NOT_PROJECT' if targets else 'DESIGNATED_NATIVE_FIELD_MISSING'
        elif family in ('GA_AIMR_REE_2026','GA_CRITICAL_DEPOSITS_2025'):
            namespace,field=('GA_ENO','eno') if family=='GA_AIMR_REE_2026' else ('GA_CRITICAL_OBJECTID_2025','objectid')
            value=attrs.get(field)
            candidates=[] if value is None else db.execute('''SELECT e.entity_id,r.name,r.state FROM entities e JOIN records r USING(entity_id)
                WHERE e.native_namespace=? AND e.native_id=?''',(namespace,native(value))).fetchall()
            for candidate in candidates:
                if candidate['entity_id'] in targets:continue
                # Native ID plus consistent advertised name/state prevents accidental OID reuse.
                if candidate['state']==r['state'] and normalized(candidate['name'])==normalized(r['name']):
                    targets.append(candidate['entity_id'])
                    link(db,candidate['entity_id'],r['entity_id'],'SAME_NATIVE_DEPOSIT_SOURCE_RECORD',r['source_sha'],field+'='+native(value))
            status='EXACT_NATIVE_DEPOSIT_LINK' if targets else 'NATIVE_ID_OR_VERSION_CONFLICT_REVIEW'
        elif not family:status='LEGACY_ONLY_NO_OFFICIAL_ID'
        ledger.append(dict(source_record_id=r['entity_id'],target_id=payload['legacy_target_id'],state=r['state'],source_key=family,
                           native_id=payload['original_native_id'],resolved_entities=canonical(sorted(set(targets))),status=status,source_sha256=r['source_sha']))
    # Explicit primary-supported equivalences. Invalid links are isolated in Review Queue.
    for decision in (json.loads(path.read_text(encoding='utf8'))['links'] if path.exists() else []):
        if decision.get('rule_version') and decision['rule_version']!=rule_version:continue
        if decision['effective_date']>cutoff:continue
        source=by_key.get(decision['source_key'])
        if not source or source['sha256']!=decision['source_sha256']:continue
        try:
            nodes=[]
            for namespace,identifier in (decision['left'],decision['right'],decision['canonical']):
                row=db.execute('SELECT * FROM entities WHERE native_namespace=? AND native_id=?',(namespace,identifier)).fetchone()
                if row is None:raise ValueError('SOURCE_NATIVE_ENTITY_NOT_FOUND')
                nodes.append(dict(row))
            a,b,c=nodes
            if not (a['kind']==b['kind']==c['kind'] and c['entity_id'] in (a['entity_id'],b['entity_id'])):raise ValueError('ENTITY_KIND_OR_CANONICAL_ENDPOINT_MISMATCH')
            if a['kind'] not in ('PROJECT','DEPOSIT','SITE'):raise ValueError('UNSUPPORTED_EQUIVALENCE_KIND')
            text=PdfReader(Path(root)/source['path']).pages[decision['pdf_page']-1].extract_text()
            if not all(marker in text for marker in decision['page_markers']):raise ValueError('PRIMARY_PAGE_MARKER_MISMATCH')
            states=[{r['state'] for r in db.execute('SELECT state,source_sha FROM records WHERE entity_id=?',(n['entity_id'],)) if r['source_sha'] in selected and r['state']} for n in (a,b)]
            if not states[0] or states[0]!=states[1]:raise ValueError('OFFICIAL_STATE_MISMATCH_OR_MISSING')
            if a['kind']=='DEPOSIT':
                positions=[]
                for n in (a,b):
                    position=next(r for r in db.execute('SELECT longitude,latitude,source_sha,name FROM records WHERE entity_id=?',(n['entity_id'],)) if r['source_sha'] in selected and r['longitude'] is not None)
                    positions.append(position)
                if normalized(positions[0]['name'])!=normalized(positions[1]['name']):raise ValueError('OFFICIAL_DEPOSIT_NAMES_DIFFER')
                distance=GEO.inv(positions[0]['longitude'],positions[0]['latitude'],positions[1]['longitude'],positions[1]['latitude'])[2]
                if distance>500:raise ValueError('DEPOSIT_REPRESENTATIVE_POINTS_DIFFER_'+format(distance,'.3f')+'_METRES_EXCEEDS_500M_NO_FOOTPRINT_RECONCILIATION')
            alias=b['entity_id'] if c['entity_id']==a['entity_id'] else a['entity_id']
            for previous in db.execute("SELECT issue_id,details FROM review_queue WHERE reason='IDENTITY_DECISION_REVIEW' AND status='OPEN'").fetchall():
                detail=json.loads(previous['details']);old=detail.get('decision',{})
                if old.get('left')==decision['left'] and old.get('right')==decision['right'] and old.get('source_key')==decision['source_key']:
                    db.execute("UPDATE review_queue SET status='RESOLVED_BY_CURRENT_DOCUMENT_RULE' WHERE issue_id=?",(previous['issue_id'],))
            accepted.append(dict(alias_id=alias,canonical_id=c['entity_id'],kind=a['kind'],status='DOCUMENT_SUPPORTED_RULE_NOT_INDEPENDENT_APPROVAL',source_sha256=source['sha256'],locator=decision['locator']))
        except (AssertionError,KeyError,TypeError,ValueError,IndexError,StopIteration,OSError) as exc:
            for previous in db.execute("SELECT issue_id,details FROM review_queue WHERE reason='IDENTITY_DECISION_REVIEW' AND status='OPEN'").fetchall():
                detail=json.loads(previous['details']);old=detail.get('decision',{})
                if detail.get('reason')=='AssertionError' and old.get('left')==decision['left'] and old.get('right')==decision['right']:
                    db.execute("UPDATE review_queue SET status='SUPERSEDED_BY_SPECIFIC_DIAGNOSTIC' WHERE issue_id=?",(previous['issue_id'],))
            issue(db,None,source['sha256'],'IDENTITY_DECISION_REVIEW',canonical({'decision':decision,'reason':str(exc) or type(exc).__name__}))
    # Typed document relations retain both source Project IDs and never imply equivalence.
    for relation in (json.loads(path.read_text(encoding='utf8')).get('relations',[]) if path.exists() else []):
        if any(k not in by_key for k in relation.get('required_source_keys',[])):continue
        source=by_key.get(relation['source_key'])
        if not source or source['sha256']!=relation['source_sha256'] or relation['effective_date']>cutoff:continue
        try:
            from .pdf_extract import extract_page
            if source['kind']=='html':
                from .evidence import html_text
                text=html_text(root,source)
            else:text=extract_page(Path(root)/source['path'],relation['pdf_page'])['text']
            text=re.sub(r'\s+',' ',text)
            if not all(x in text for x in relation['page_markers']):raise ValueError('RELATION_PRIMARY_PAGE_MARKER_MISMATCH')
            nodes=[db.execute('SELECT * FROM entities WHERE native_namespace=? AND native_id=?',tuple(relation[k])).fetchone() for k in ('left','right')]
            contracts={'CONTAINS_DOCUMENTED_REE_SCOPE_NOT_IDENTITY_EQUIVALENCE':('PROJECT','PROJECT'),
                       'CONTAINS_ISSUER_DOCUMENTED_PROSPECT_NOT_RESOURCE_SUM':('PROJECT','PROSPECT')}
            kinds=contracts.get(relation['relation'])
            if not kinds:raise ValueError('UNSUPPORTED_TYPED_RELATION')
            if any(n is None or n['kind']!=kind for n,kind in zip(nodes,kinds)):raise ValueError('RELATION_ENTITY_KIND_OR_NATIVE_ID_MISMATCH')
            link(db,nodes[0]['entity_id'],nodes[1]['entity_id'],relation['relation'],source['sha256'],relation['locator'])
        except Exception as exc:issue(db,None,source['sha256'],'DOCUMENTED_RELATION_REVIEW',canonical({'relation':relation,'reason':str(exc)}))
    # Conflicting canonical anchors and cycles are rejected rather than resolved by row order.
    proposals={}
    for a in accepted:proposals.setdefault(a['alias_id'],set()).add(a['canonical_id'])
    mapping={k:next(iter(v)) for k,v in proposals.items() if len(v)==1}
    invalid=set(k for k,v in proposals.items() if len(v)!=1)
    for start in mapping:
        seen=set();cursor=start
        while cursor in mapping:
            if cursor in seen:invalid.update(seen);break
            seen.add(cursor);cursor=mapping[cursor]
    for key in invalid:
        mapping.pop(key,None);issue(db,key,None,'CANONICAL_ID_CONFLICT_OR_CYCLE','Equivalence excluded')
    valid=[]
    for a in accepted:
        if a['alias_id'] not in mapping:continue
        link(db,a['canonical_id'],a['alias_id'],'DOCUMENT_SUPPORTED_SAME_'+a['kind'],a['source_sha256'],a['locator']);valid.append(a)
    membership=[];member_ids=set()
    for r in db.execute('SELECT e.*,r.source_sha FROM entities e JOIN records r USING(entity_id) ORDER BY e.entity_id'):
        if r['source_sha'] not in selected or r['entity_id'] in member_ids:continue
        target=r['entity_id'];seen=set()
        while target in mapping and target not in seen:seen.add(target);target=mapping[target]
        membership.append(dict(entity_id=r['entity_id'],kind=r['kind'],canonical_id=target,status='DOCUMENT_SUPPORTED_ALIAS' if seen else 'RETAINED_SOURCE_ID_NOT_ASSUMED_UNIQUE_PHYSICAL_ENTITY'))
        member_ids.add(r['entity_id'])
    # A complete candidate ledger: proximity/name is a review lead, never automatic equivalence.
    deposits=[];deposit_ids=set()
    for r in db.execute("SELECT e.entity_id,e.native_namespace,r.* FROM entities e JOIN records r USING(entity_id) WHERE e.kind='DEPOSIT' ORDER BY e.entity_id,r.source_sha"):
        if r['source_sha'] in selected and r['entity_id'] not in deposit_ids:
            deposits.append(dict(r));deposit_ids.add(r['entity_id'])
    pairs=[]
    buckets={};canonical_ids={x['entity_id']:x['canonical_id'] for x in membership}
    for r in deposits:buckets.setdefault((r['state'],normalized(r['name'])),[]).append(r)
    for i,a in enumerate(deposits):
        for b in buckets[a['state'],normalized(a['name'])]:
            if b['entity_id']<=a['entity_id']:continue
            if a['native_namespace']==b['native_namespace'] or a['state']!=b['state'] or normalized(a['name'])!=normalized(b['name']):continue
            dist=None if any(r[k] is None for r in (a,b) for k in ('longitude','latitude')) else GEO.inv(a['longitude'],a['latitude'],b['longitude'],b['latitude'])[2]
            ca=canonical_ids[a['entity_id']];cb=canonical_ids[b['entity_id']]
            pairs.append(dict(a=a['entity_id'],b=b['entity_id'],name=a['name'],state=a['state'],distance_m=dist,status='DOCUMENT_SUPPORTED_EQUIVALENCE' if ca==cb else 'LOCATION_CONFLICT_REVIEW' if dist is not None and dist>500 else 'TECHNICAL_IDENTITY_REVIEW_REQUIRED',source_a=a['source_sha'],source_b=b['source_sha']))
    return dict(ledger=ledger,accepted=valid,membership=membership,candidates=pairs,mapping={x['entity_id']:x['canonical_id'] for x in membership})

def technical_coverage(db,resolution,resources,cases,snapshot_shas):
    from .selection import observation_visible
    def active_raw(sql,eid):
        rows=[]
        for record in db.execute(sql,(eid,)):
            r=dict(record);raw=json.loads(r.pop('raw'))
            if r['source_sha'] in snapshot_shas and observation_visible(raw,snapshot_shas):rows.append(r)
        return rows
    groups={}
    for row in resolution['membership']:
        if row['kind']=='PROJECT':groups.setdefault(row['canonical_id'],[]).append(row['entity_id'])
    output=[]
    for cid,members in sorted(groups.items()):
        scopes=[dict(source_entity_id=eid,scope=r['scope'],date=r['date'],source_sha256=r['source_sha']) for eid,r in resources.items() if eid in members]
        studies=[c['case_id'] for c in cases if c['project_id'] in members]
        stages=[dict(r) for eid in members for r in db.execute("SELECT obs_id,source_sha,locator FROM observations WHERE entity_id=? AND variable='study_maturity_ord' AND status='AUTO_VALIDATED'",(eid,)) if r['source_sha'] in snapshot_shas]
        shared=[dict(r) for eid in members for r in db.execute("SELECT child_id,source_sha,locator FROM relations WHERE parent_id=? AND relation='CONTAINS_DOCUMENTED_REE_SCOPE_NOT_IDENTITY_EQUIVALENCE'",(eid,)) if r['source_sha'] in snapshot_shas]
        status=('PRIMARY_RESOURCE_AND_STUDY_EVIDENCE' if scopes and (studies or stages) else 'PRIMARY_RESOURCE_SCOPE_ONLY' if scopes else 'PRIMARY_STUDY_CASE_ONLY' if studies else 'PRIMARY_SHARED_RESOURCE_CONTEXT_ONLY_NO_ADDITIVE_RESOURCE' if shared else 'NO_CONTROLLED_PRIMARY_TECHNICAL_SCOPE_YET')
        scoped_obs={obs for eid,r in resources.items() if eid in members for obs in r['obs_ids']}
        other=[dict(r) for eid in members for r in db.execute("SELECT obs_id,variable,value,basis,scope,effective_date,source_sha,status FROM observations WHERE entity_id=? AND variable IN ('ore_mt','grade','contained_treo_kt')",(eid,)) if r['source_sha'] in snapshot_shas and r['obs_id'] not in scoped_obs]
        primary_raw=[r for eid in members for r in active_raw("SELECT o.obs_id,o.variable,o.value,o.basis,o.scope,o.effective_date,o.source_sha,o.status,o.raw FROM observations o JOIN sources s ON o.source_sha=s.sha WHERE o.entity_id=? AND o.status='AUTO_VALIDATED' AND s.kind='pdf' AND (o.variable LIKE 'reported_fine_fraction_%' OR o.variable LIKE 'reported_resource_%' OR o.variable='reported_bulk_ore_mt')",eid)]
        if status=='NO_CONTROLLED_PRIMARY_TECHNICAL_SCOPE_YET' and primary_raw:status='PRIMARY_RESOURCE_BASIS_OR_FRACTION_NOT_COMPARABLE'
        raw_process=[r for eid in members for r in active_raw("SELECT o.obs_id,o.variable,o.value,o.basis,o.scope,o.effective_date,o.source_sha,o.status,o.raw FROM observations o JOIN sources s ON o.source_sha=s.sha WHERE o.entity_id=? AND o.status='AUTO_VALIDATED' AND s.kind IN ('pdf','html','discovery_html') AND o.variable LIKE 'reported_technical_%'",eid)]
        if status=='NO_CONTROLLED_PRIMARY_TECHNICAL_SCOPE_YET' and raw_process:status='PRIMARY_PROCESS_EVIDENCE_ONLY_NOT_COMPARABLE_RESOURCE'
        other.extend(primary_raw)
        other.extend(raw_process)
        output.append(dict(canonical_project_id=cid,member_entity_ids=canonical(sorted(members)),status=status,resource_scopes=canonical(scopes),study_case_ids=canonical(studies),other_stage_evidence=canonical(stages),shared_resource_context=canonical(shared),unverified_or_other_scope_claims=canonical(other),interpretation='SOURCE_DEFINED_SCOPES_NOT_LATEST_PROJECT_TOTAL_CERTIFICATION'))
    return output
