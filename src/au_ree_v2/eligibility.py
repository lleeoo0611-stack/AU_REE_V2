"""Rebuildable coverage and formal-policy compatibility audit; no gate invention."""
import json
from .analysis import write_csv
from .store import canonical, digest


def audit(db,out,identity,technical,prepared,config,cutoff,snapshots,root=None,current=None):
    mapping=identity['mapping']; selected={s['sha256'] for s in snapshots}
    names={r['entity_id']:r['name'] for r in db.execute('SELECT * FROM records ORDER BY source_sha') if r['source_sha'] in selected}
    coverage={r['canonical_project_id']:r for r in prepared['coverage']}
    pairs=[]
    for pair in identity['candidates']:
        if pair['status']=='DOCUMENT_SUPPORTED_EQUIVALENCE':continue
        # Accepted pairs may use a distinct status; test membership instead.
        if mapping.get(pair['a'],pair['a'])==mapping.get(pair['b'],pair['b']):continue
        pairs.append({**pair,'reason':pair['status'],'needed_evidence':'PRIMARY_IDENTITY_SCOPE_AND_LOCATION_RECONCILIATION','cutoff':cutoff})
    write_csv(out/'unresolved_identity_pairs.csv',pairs,['a','b','name','state','distance_m','source_a','source_b','reason','needed_evidence','cutoff'])
    gaps=[]; gates=[]; cohorts=[]
    for row in technical:
        eid=row['canonical_project_id']; members=json.loads(row['member_entity_ids']) if isinstance(row['member_entity_ids'],str) else row['member_entity_ids']
        name=' | '.join(sorted({names.get(m,m) for m in members})); c=coverage.get(eid,{})
        if row['status']=='NO_CONTROLLED_PRIMARY_TECHNICAL_SCOPE_YET':
            gaps.append({**row,'project_names':name,'reason':'NO_SELECTED_PRIMARY_RESOURCE_OR_STUDY_SCOPE','needed_evidence':'DATED_PRIMARY_PDF_WITH_PROJECT_SCOPE_AND_PAGE','cutoff':cutoff})
        for gate in ('ID','ROLE','WINDOW','JORC','PANEL','GIS_RELEASE'):
            objective={'ID':{'registered_member_ids':members,'controlled_primary_status':row['status']},'JORC':{'validated_resource_scopes':json.loads(row['resource_scopes'])},'GIS_RELEASE':{'available_infrastructure_criteria':[k for k,v in c.items() if k.startswith('I') and v==1]},'WINDOW':{'dated_stage_criterion_available':bool(c.get('D1')),'current_activity':'UNKNOWN_NOT_INFERRED_FROM_STUDY_COMPLETION'},'ROLE':{'primary_study_cases':json.loads(row['study_case_ids']),'economic_product_role':'NOT_INFERRED_FROM_ASSAY'},'PANEL':{'fixed_formal_panel':'NOT_IMPORTED'}}[gate]
            gates.append({'canonical_project_id':eid,'gate':gate,'status':'NOT_EVALUATED_NO_IMPORTED_GATE_EVIDENCE','cutoff':cutoff,'rule_version':'v2-compatibility-v1','reason':'COVERAGE_IS_NOT_A_FORMAL_GATE_SIGNOFF','objective_source_facts':canonical(objective)})
        cohorts.append({'canonical_project_id':eid,'project_names':name,'registry_group':1,'resource_defined':c.get('resource_defined',0),'development':c.get('development',0),'full_evidence':c.get('full_evidence',0),'formal_c1_status':'NOT_EVALUATED','exploratory_available':int(bool(c)),'cutoff':cutoff,'rule_version':'v2-compatibility-v1'})
    write_csv(out/'primary_scope_gaps.csv',gaps,['canonical_project_id','project_names','member_entity_ids','status','unverified_or_other_scope_claims','reason','needed_evidence','cutoff'])
    write_csv(out/'formal_gate_compatibility.csv',gates,['canonical_project_id','gate','status','objective_source_facts','reason','cutoff','rule_version'])
    write_csv(out/'eligibility_cohorts.csv',cohorts,['canonical_project_id','project_names','registry_group','resource_defined','development','full_evidence','formal_c1_status','exploratory_available','cutoff','rule_version'])
    stats={'unresolved_pairs':len(pairs),'primary_scope_gaps':len(gaps),'formal_c1_evaluated':0,'formal_c1_admitted':0,'formal_c1_reason':'UPSTREAM_GATE_LEDGER_AND_FIXED_PANEL_NOT_IMPORTED','registry_groups':len(cohorts),'source_snapshots':len(snapshots),'resource_defined':sum(c['resource_defined'] for c in cohorts),'development':sum(c['development'] for c in cohorts),'full_evidence':sum(c['full_evidence'] for c in cohorts)}
    if config.get('eligibility_evidence',{}).get('imports'):
        stats['formal_c1_reason']='IMPORTED_POLICY_EMPTY_SIGNOFF_LEDGERS_NO_APPROVED_CROSSWALK_OR_PANEL'
        stats['objective_evidence']=objective_evidence(db,out,mapping,technical,config['eligibility_evidence'],cutoff,snapshots,root,current)
    (out/'eligibility_audit.json').write_text(json.dumps(stats,indent=2)+'\n',encoding='utf-8')
    return stats


def objective_evidence(db,out,mapping,technical,policy,cutoff,snapshots,root,current=None):
    """Evidence availability and formal decisions are independent axes.

    No name-based upstream crosswalk. Post-cutoff acquisitions may establish a
    published historical fact; publication/effectivity must still precede the
    upstream cutoff. Source retrieval dates are exported, never backdated.
    """
    import csv,io
    from pathlib import Path
    from .store import filehash
    from .selection import date_end,observation_visible
    root=Path(root);imports=policy['imports'];contents={}
    for key,entry in imports.items():
        if filehash(root/entry['path'])!=entry['sha256']:raise ValueError('UPSTREAM_POLICY_SHA_MISMATCH')
        contents[key]=(root/entry['path']).read_text(encoding='utf-8')
    upstream=json.loads(contents['policy']);formal_cutoff=upstream['source_asof']
    signed=list(csv.DictReader(io.StringIO(contents['gates'])))
    metadata=list(csv.DictReader(io.StringIO(contents['identity'])))
    approved=policy.get('approved_crosswalk',[])
    sources={s['sha256']:s for s in snapshots};facts={};rows=[]
    for obs in db.execute('SELECT * FROM observations ORDER BY obs_id'):
        if obs['source_sha'] not in sources:continue
        if current is not None and obs['obs_id'] not in current['observation_ids']:continue
        raw=json.loads(obs['raw']);source=sources[obs['source_sha']]
        if not observation_visible(raw,sources):continue
        if obs['status']!='AUTO_VALIDATED':continue
        try:
            if not source.get('publication_date') or date_end(source['publication_date'])>formal_cutoff or date_end(obs['effective_date'])>formal_cutoff:continue
        except (TypeError,ValueError):continue
        pid=mapping.get(obs['entity_id'],obs['entity_id'])
        facts.setdefault(pid,[]).append(dict(evidence_id=obs['obs_id'],variable=obs['variable'],value=obs['value'],basis=obs['basis'],scope=obs['scope'],effective_date=obs['effective_date'],source_sha256=obs['source_sha'],source_publication=source['publication_date'],acquired_at=source['acquired_at'],locator=obs['locator'],pdf_page=raw.get('pdf_page'),raw=raw))
    for rec in db.execute('SELECT e.native_namespace,e.native_id,e.kind,r.* FROM entities e JOIN records r USING(entity_id) ORDER BY e.entity_id,r.source_sha'):
        if current is not None and rec['entity_id'] in current['historical_scope_ids']:continue
        if current is not None and (rec['entity_id'],rec['source_sha']) not in current['record_ids']:continue
        source=sources.get(rec['source_sha'])
        if not source or not source.get('publication_date') or date_end(source['publication_date'])>formal_cutoff:continue
        pid=mapping.get(rec['entity_id'],rec['entity_id'])
        identity_record=identity_fact(rec)
        facts.setdefault(pid,[]).append(dict(evidence_id=digest(identity_record),variable='native_identity_record',value=None,basis=None,scope=rec['name'],effective_date=source['publication_date'],source_sha256=rec['source_sha'],source_publication=source['publication_date'],acquired_at=source['acquired_at'],locator='native record '+rec['native_namespace']+':'+rec['native_id'],pdf_page=None,raw=identity_record))
    for case in db.execute('SELECT * FROM study_cases ORDER BY case_id'):
        source=sources.get(case['source_sha'])
        if not source or not source.get('publication_date') or date_end(source['publication_date'])>formal_cutoff or date_end(case['effective_date'])>formal_cutoff:continue
        pid=mapping.get(case['project_id'],case['project_id'])
        facts.setdefault(pid,[]).append(dict(evidence_id=case['case_id'],variable='study_case',value=case['stage'],basis=case['element'],scope=case['scope'],effective_date=case['effective_date'],source_sha256=case['source_sha'],source_publication=source['publication_date'],acquired_at=source['acquired_at'],locator=json.loads(case['raw']).get('locator'),pdf_page=json.loads(case['raw']).get('pdf_page'),raw=json.loads(case['raw'])))
    gis_path=out/'gis_metrics.csv'
    gis_rows=list(csv.DictReader(gis_path.open(encoding='utf-8'))) if gis_path.exists() else []
    for project in technical:
        pid=project['canonical_project_id'];evidence=facts.get(pid,[])
        cross=[x for x in approved if x.get('v2_project_id')==pid and x.get('approval_ref') and x.get('native_id_evidence')]
        group=cross[0]['upstream_review_group_id'] if len(cross)==1 else None
        for gate in upstream['C1_required_gates']:
            relevant={'ID':lambda r:r['variable']=='native_identity_record','ROLE':lambda r:(r['variable']=='commercial_event' and r['raw'].get('event_type')=='OFFTAKE') or r['variable']=='study_case',
                'WINDOW':lambda r:r['variable'] in ('study_maturity_ord','study_case'),
                'JORC':lambda r:r['variable'] in ('ore_mt','grade','contained_treo_kt'),
                'PANEL':lambda r:False,'GIS_RELEASE':lambda r:False}[gate]
            selected=[r for r in evidence if relevant(r)]
            if gate=='GIS_RELEASE':
                selected=[dict(r,source_sha256=r['layer_sha256']) for r in gis_rows if mapping.get(r['entity_id'],r['entity_id'])==pid and r['layer_sha256'] in sources and sources[r['layer_sha256']].get('publication_date') and date_end(sources[r['layer_sha256']]['publication_date'])<=formal_cutoff]
            state='PARTIAL_SOURCE_FACTS_AVAILABLE' if selected else 'UNKNOWN_NO_COMPLETE_OBJECTIVE_EVIDENCE'
            reason={'ID':'PROJECT_SCOPE_FOOTPRINT_AND_APPROVED_CROSSWALK_REQUIRED','ROLE':'PRODUCT_ROLE_REQUIRES_EXPLICIT_DEVELOPMENT_SCOPE_NOT_ASSAY','WINDOW':'DATED_STUDY_DOES_NOT_ESTABLISH_CURRENT_ACTIVITY_OR_PRE_FID','JORC':'REE_SCOPE_CLASSIFICATION_CUTOFF_EDITION_AND_BASIS_REQUIRE_RECONCILIATION','PANEL':'UPSTREAM_9_OR_12_PANEL_NOT_SELECTED','GIS_RELEASE':'REPRESENTATIVE_POINT_AND_LAYER_RELEASE_QA_NOT_APPROVED'}[gate]
            if gate=='PANEL':state='UNKNOWN_FORMAL_PANEL_NOT_SELECTED'
            decisions=[d for d in signed if group and d['review_group_id']==group and d['gate_id']==gate]
            rows.append(dict(canonical_project_id=pid,gate=gate,upstream_review_group_id=group,
                upstream_cutoff=formal_cutoff,v2_cutoff=cutoff,objective_status=state,
                objective_reason=reason,objective_evidence=canonical(selected),source_count=len({r['source_sha256'] for r in selected}),
                crosswalk_status='APPROVED_SOURCE_ID_CROSSWALK' if group else 'NO_APPROVED_CROSSWALK_NO_NAME_JOIN',
                formal_status='IMPORTED_DECISION_REQUIRES_FULL_RELEASE_VALIDATION' if decisions else 'UNSIGNED_NOT_ADMITTED',
                formal_decisions=canonical(decisions),policy_id=upstream['policy_id'],policy_sha256=imports['policy']['sha256']))
    for row in rows:row.update(status=row['formal_status'],objective_source_facts=row['objective_evidence'],reason=row['objective_reason'],cutoff=row['v2_cutoff'],rule_version=policy['version'])
    write_csv(out/'formal_gate_compatibility.csv',rows,['status','objective_source_facts','reason','cutoff','rule_version','canonical_project_id','gate','upstream_review_group_id','upstream_cutoff','v2_cutoff','objective_status','objective_reason','source_count','objective_evidence','crosswalk_status','formal_status','formal_decisions','policy_id','policy_sha256'])
    return dict(rows=len(rows),with_source_facts=sum(r['source_count']>0 for r in rows),upstream_signed_rows=len(signed),upstream_identity_rows=len(metadata),approved_crosswalks=len(approved),formal_admitted=0,upstream_cutoff=formal_cutoff,v2_cutoff=cutoff)


def identity_fact(record):
    """Native identity fields only: historical claim payloads contain other
    variables/editions and must not leak into a dated identity audit.
    """
    return {k:record[k] for k in ('entity_id','native_namespace','native_id','kind','name','state','longitude','latitude','source_sha')}
