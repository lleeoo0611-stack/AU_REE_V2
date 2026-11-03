"""Study-case evidence, separate from resource inventory and actual operating performance."""
import json,math
from pathlib import Path
from collections import defaultdict
from .store import entity,canonical,issue,digest
from .analysis import write_csv,score
from .hierarchy import link

def ingest(db,root,snapshots,cutoff):
    from .evidence import validate_pages
    path=Path(root)/'data/study_cases.json'
    if not path.exists():return []
    sources={s['key']:s for s in snapshots};rows=[];cache={}
    for c in json.loads(path.read_text(encoding='utf8'))['cases']:
        source=sources.get(c['source_key'])
        if not source or c['effective_date']>cutoff:continue
        try:
            assert c['source_sha256']==source['sha256'] and c['stage'] in (1,2,3,4,5,6)
            validate_pages(root,source,c,snapshots,cache)
            for key,val in c['parameters'].items():
                assert isinstance(val,(int,float)) and not isinstance(val,bool) and math.isfinite(val) and val>=0
                if key.endswith('_pct'):assert val<=100
            pid=entity(db,c['project_namespace'],c['project_native_id'],'PROJECT')
            db.execute('INSERT OR IGNORE INTO study_cases VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                       (c['case_id']+'@'+digest(c)[:16],pid,source['sha256'],c['effective_date'],c['scope'],c['stage'],c['endpoint'],c['element'],c['scale'],'PRIMARY_SCOPED_CASE_NOT_OPERATING_OUTCOME',canonical(c)))
            rows.append(dict(c,project_id=pid,status='PRIMARY_SCOPED_CASE_NOT_OPERATING_OUTCOME',
                             currentness=c.get('currentness','DATED_SOURCE_NOT_LATEST_EVENT_CERTIFICATION')))
            if c['project_native_id']=='jupiter':
                p=entity(db,'CRITICA_PROJECT_PROGRAM','brothers','PROJECT_PROGRAM')
                db.execute('INSERT OR IGNORE INTO records VALUES(?,?,?,?,?,?,?,?,?)',(p,source['sha256'],'Brothers Project program','WA',None,None,None,None,canonical({'scope':'Wider Brothers landholding; not Jupiter Mineral Resource','status':'ISSUER_DOCUMENTED_PROGRAM'})))
                link(db,p,pid,'CONTAINS_STUDY_PROJECT_NOT_IDENTITY_EQUIVALENCE',source['sha256'],'PDF p25: Jupiter deposit within Brothers; granted E59/2463')
            if c['project_native_id']=='donald-rare-earth-mineral-sands-project':
                for name in ('Donald','Jackson'):
                    dep=entity(db,'ASTRON_DOCUMENTED_DEPOSIT',name.lower(),'DEPOSIT_SCOPE')
                    db.execute('INSERT OR IGNORE INTO records VALUES(?,?,?,?,?,?,?,?,?)',(dep,source['sha256'],name,'VIC',None,None,None,None,canonical({'kind':'ISSUER_DOCUMENTED_DEPOSIT','not_resource_total':True})))
                    link(db,pid,dep,'CONTAINS_DOCUMENTED_DEPOSIT_NOT_RESOURCE_SUM',source['sha256'],'Annual Report 2024 p20: Donald and Jackson deposits; phases1/2 on Donald')
                    for lease in (('MIN5532','RL2002') if name=='Donald' else ('RL2003',)):
                        tenure=entity(db,'VIC_ISSUER_TENEMENT_REFERENCE',lease,'TENEMENT')
                        db.execute('INSERT OR IGNORE INTO records VALUES(?,?,?,?,?,?,?,?,?)',(tenure,source['sha256'],lease,'VIC',None,None,None,None,canonical({'status':'ISSUER_DOCUMENT_REFERENCE_NOT_CURRENT_TITLE_VERIFICATION'})))
                        link(db,dep,tenure,'REPORTED_TENEMENT_REFERENCE_NOT_TITLE_VERIFICATION',source['sha256'],'Annual Report 2024 pp18,20,24; Donald vs Jackson separated')
        except (AssertionError,KeyError,TypeError,ValueError,IndexError,OSError) as exc:
            issue(db,None,source['sha256'],'STUDY_CASE_REVIEW',canonical({'case_id':c.get('case_id'),'reason':type(exc).__name__}))
    return sorted(rows,key=lambda x:x['case_id'])

def prepare(cases,config,out,canonical_ids,selection=None):
    """Only frozen, explicitly compatible endpoints enter a shared numerical panel."""
    out=Path(out);rows=[];parameters=[];groups=defaultdict(list)
    for c in cases:
        key='|'.join((c.get('recovery_feed','UNSPECIFIED'),c['element'],c['endpoint'],c['scale']))
        groups[key].append(c)
        rows.append(dict(case_id=c['case_id'],project_id=c['project_id'],canonical_project_id=canonical_ids.get(c['project_id'],c['project_id']),
                         scope=c['scope'],stage=c['stage'],process=c['process'],finance_state=c['finance_state'],currentness=c['currentness'],
                         endpoint=c['endpoint'],element=c['element'],scale=c['scale'],activity=c.get('activity'),comparability_group=key,
                         source_sha256=c['source_sha256'],locator=c['locator'],parameters=canonical(c['parameters'])))
        for variable,value in c['parameters'].items():
            parameters.append(dict(case_id=c['case_id'],project_id=c['project_id'],variable=variable,value=value,
                                   scope=c['scope'],endpoint=c['endpoint'],element=c['element'],scale=c['scale'],
                                   source_sha256=c['source_sha256'],locator=c['locator']))
    write_csv(out/'study_cases.csv',rows,['case_id','project_id','canonical_project_id','scope','stage','process','finance_state','currentness','activity','endpoint','element','scale','comparability_group','source_sha256','locator','parameters'])
    write_csv(out/'study_parameter_evidence.csv',parameters,['case_id','project_id','variable','value','scope','endpoint','element','scale','source_sha256','locator'])
    write_csv(out/'recovery_comparability.csv',[dict(group=k,case_count=len(v),cases=canonical([c['case_id'] for c in v]),status='MATCHED_ENDPOINT_SCREEN_ONLY' if len(v)>1 else 'SINGLE_CASE_NO_CROSS_PROJECT_RECOVERY_RANK') for k,v in sorted(groups.items())],['group','case_count','cases','status'])
    # Candidate endpoint cohort is frozen before execution, independent of the outcome.
    definition=config.get('case_panels',{}).get('beneficiation_concentrate_screen')
    if not definition:return {},[]
    codes=definition['codes'];criteria={c['code']:c for c in config['criteria']};matrix=[];trace=[]
    candidates={};excluded=[]
    for c in groups.get(definition['comparability_group'],[]):candidates.setdefault(canonical_ids.get(c['project_id'],c['project_id']),[]).append(c)
    selected=[]
    if selection is not None:
        from .selection import select_cases
        selected,excluded=select_cases(cases,canonical_ids,definition['comparability_group'])
        selected=[c for c in selected if all(selection['values'].get(canonical_ids.get(c['project_id'],c['project_id']),{}).get(k,{}).get('case_id')==c['case_id'] for k in codes)]
    else:
        # Frozen pre-Phase7 policy retained for historical reconstruction.
        for pid,options in candidates.items():
            date=max(c['effective_date'] for c in options);latest=[c for c in options if c['effective_date']==date]
            if len(latest)!=1:excluded.append(dict(canonical_project_id=pid,reason='CONCURRENT_CASES_REQUIRE_SCOPE_DECISION',case_ids=canonical([c['case_id'] for c in latest])))
            else:selected.append(latest[0])
    write_csv(out/'study_cohort_exclusions.csv',excluded,['canonical_project_id','reason','case_ids'])
    for c in selected:
        if not all(criteria[k]['variable'] in c['parameters'] for k in codes):continue
        row=dict(project_id=c['project_id'],project_name=c['project_native_id'],scope=c['scope'],case_id=c['case_id'],uncertainty_kind='NO_SOURCE_BOUNDS')
        for code in codes:
            criterion=criteria[code];value=c['parameters'][criterion['variable']];v=score(value,criterion)
            row.update({code:v,code+'_lower':v,code+'_upper':v,code+'_alt':v})
            trace.append(dict(entity_id=c['project_id'],criterion=code,raw_value=value,score=v,config_version=config['version'],source=canonical({'case_id':c['case_id'],'source_sha256':c['source_sha256'],'scope':c['scope'],'locator':c['locator']}),scoring=canonical(criterion)))
        matrix.append(row)
    if matrix:
        folder=out/'beneficiation_concentrate_screen'
        write_csv(folder/'matrix.csv',matrix,['project_id','project_name','scope','case_id','uncertainty_kind',*[k for c in codes for k in (c,c+'_lower',c+'_upper',c+'_alt')]])
        write_csv(folder/'criteria.csv',[criteria[c] for c in codes],['code','domain','direction','low','high','function'])
        write_csv(folder/'weights.csv',[dict(scenario=s,criterion=c,weight=v[c]) for s,v in definition['scenarios'].items() for c in codes],['scenario','criterion','weight'])
    # No invented probability distribution for three Dubbo mining-zone model inputs.
    ranges=[]
    for c in cases:
        values=[v for k,v in c['parameters'].items() if k.startswith('nd_') and k.endswith('_leach_pct')]
        if values:ranges.append(dict(case_id=c['case_id'],element='Nd',endpoint='LEACH_SOLUTION',min_pct=min(values),max_pct=max(values),n_zones=len(values),interpretation='MODEL_ZONE_RANGE_NOT_STATISTICAL_UNCERTAINTY_OR_OVERALL_PLANT_RECOVERY'))
    write_csv(out/'recovery_zone_ranges.csv',ranges,['case_id','element','endpoint','min_pct','max_pct','n_zones','interpretation'])
    return ({'beneficiation_concentrate_screen':len(matrix)} if matrix else {}),trace
