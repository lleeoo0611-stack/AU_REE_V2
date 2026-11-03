"""Rebuildable coverage and formal-policy compatibility audit; no gate invention."""
import json
from .analysis import write_csv
from .store import canonical, digest


def audit(db,out,identity,technical,prepared,config,cutoff,snapshots):
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
    (out/'eligibility_audit.json').write_text(json.dumps(stats,indent=2)+'\n',encoding='utf-8')
    return stats
