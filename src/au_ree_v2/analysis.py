"""Frozen panels, anchored scoring, coverage and traceable R interchange."""
import csv
import json
import math
import shutil
import subprocess
from pathlib import Path
from .store import canonical

def write_csv(path, rows, columns):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(rows)


def compare_runs(before, after):
    """Compare frozen evidence coverage and ranks without pooling their cohorts."""
    from .store import filehash
    before,after=Path(before),Path(after)
    def read(folder,name):
        path=folder/name
        if not path.exists():return None
        with path.open(encoding='utf-8-sig',newline='') as stream:return list(csv.DictReader(stream))
    def measures(folder):
        result={}
        for key,name in [('unresolved_pairs','unresolved_identity_pairs.csv'),('primary_scope_gaps','primary_scope_gaps.csv'),('resource_defined','resources.csv')]:
            rows=read(folder,name);result[key]=None if rows is None else len(rows)
        path=folder/'snapshot_lock.json'
        snapshots=json.loads(path.read_text()) if path.exists() else None
        result['source_snapshots']=None if snapshots is None else len(snapshots)
        result['pdf_snapshots']=None if snapshots is None else sum(s['kind']=='pdf' for s in snapshots)
        database=folder/'logical_database.json'
        result['validated_statement_values']=None
        if database.exists() and snapshots is not None:
            locked={s['key']:s['sha256'] for s in snapshots};selected=set(locked.values());unique=set()
            for observation in json.loads(database.read_text(encoding='utf-8'))['observations']:
                if observation['status']!='AUTO_VALIDATED' or observation['source_sha'] not in selected:continue
                raw=json.loads(observation['raw'])
                if raw.get('page_extraction_key') and locked.get(raw['page_extraction_key'])!=raw.get('page_extraction_sha256'):continue
                unique.add(canonical({k:observation[k] for k in ('entity_id','variable','value','unit','basis','scope','statement_id','effective_date','source_sha')}))
            result['validated_statement_values']=len(unique)
        cov=read(folder,'cohort_coverage.csv')
        for key in ('development','full_evidence'):result[key]=None if cov is None else sum(int(r[key]) for r in cov)
        membership=read(folder,'canonical_membership.csv') or []
        canonical_ids={r['entity_id']:r['canonical_id'] for r in membership}
        result['canonical_registry_groups']=len({r['canonical_id'] for r in membership if r['kind']=='PROJECT'}) if membership else None
        domains=read(folder,'project_domain_evidence.csv')
        for domain in ('Resource','Strategic','Technical','Development','Infrastructure','Commercial'):
            result['scorable_'+domain]=None if domains is None else len({canonical_ids.get(r['project_id'],r['project_id']) for r in domains if r['domain']==domain and r['scorable']=='1'})
        return result
    a,b=measures(before),measures(after)
    metrics=[dict(metric=k,before=a[k],after=b[k],change=None if a[k] is None or b[k] is None else b[k]-a[k]) for k in a]
    cohorts=[];ranks=[];inputs={}
    for matrix in sorted(after.glob('*/matrix.csv')):
        panel=matrix.parent.name;old=read(before,panel+'/matrix.csv');new=read(after,panel+'/matrix.csv')
        cohorts.append(dict(panel=panel,before_n=None if old is None else len(old),after_n=len(new)))
        old_r=read(before,panel+'/ranking.csv');new_r=read(after,panel+'/ranking.csv')
        if old_r is None or new_r is None:continue
        for folder,label in ((before,'before'),(after,'after')):inputs[label+'/'+panel+'/ranking.csv']=filehash(folder/panel/'ranking.csv')
        old_by_key={(r['scenario'],r['project_id']):r for r in old_r}
        for row in new_r:
            prior=old_by_key.get((row['scenario'],row['project_id']))
            for method in ('promethee','saw','topsis'):
                rank=method+'_rank'
                ranks.append(dict(panel=panel,scenario=row['scenario'],project_id=row['project_id'],project_name=row['project_name'],method=method,before_rank=None if prior is None else prior[rank],after_rank=row[rank],rank_change=None if prior is None else float(row[rank])-float(prior[rank]),cohort_state='NEW_ALTERNATIVE' if prior is None else 'COMMON_ALTERNATIVE_COHORT_AND_EVIDENCE_MAY_CHANGE'))
    write_csv(after/'comparison_metrics.csv',metrics,['metric','before','after','change'])
    write_csv(after/'comparison_cohorts.csv',cohorts,['panel','before_n','after_n'])
    write_csv(after/'comparison_ranks.csv',ranks,['panel','scenario','project_id','project_name','method','before_rank','after_rank','rank_change','cohort_state'])
    for folder,label in ((before,'before'),(after,'after')):
        if (folder/'snapshot_lock.json').exists():inputs[label+'/snapshot_lock.json']=filehash(folder/'snapshot_lock.json')
    (after/'comparison_provenance.json').write_text(json.dumps({'inputs':inputs,'interpretation':'COHORT_AND_EVIDENCE_CHANGE_NOT_TEMPORAL_PROJECT_DEVELOPMENT_OR_CAUSAL_EFFECT'},indent=2)+'\n',encoding='utf-8')
    return {'before':a,'after':b,'cohorts':cohorts}

def score(value, criterion, alternative=False):
    low, high = criterion['low'], criterion['high']
    if not math.isfinite(value) or high <= low:
        raise ValueError('Invalid score value or anchors')
    if criterion['function']=='log1p' and not alternative:
        val = (math.log1p(max(low, min(value,high)))-math.log1p(low))/(math.log1p(high)-math.log1p(low))
    else:
        val = (value-low)/(high-low)
    val = max(0., min(1., val))
    return 1-val if criterion['direction']=='MIN' else val


def _official_wa_resource_screen(db,cutoff,snapshots,config,criteria,out,project):
    """Exploratory resource-only screen of one government source, never C1.

    Unknown JORC/resource scope remains explicit. Units and reported TREO basis
    must come from the same printed government table. No missing-value fill.
    """
    from .official import official_inventory
    selected_shas={s['sha256'] for s in snapshots}
    policy=config['screen_evidence_policy']
    rows=[];traces=[]
    codes=config['screen_panels']['official_wa_resource_screen']
    by_key={s['key']:s for s in snapshots}
    if policy['source_key'] not in by_key:
        return rows,traces
    source=by_key[policy['source_key']]
    from .evidence import resource_values
    from .store import issue
    primary=resource_values(db,cutoff,selected_shas) if 'wa_dmpe_ree2026_original' in by_key else {}
    excluded=[]
    for rec in official_inventory(db,selected_shas):
        if rec['source_sha256'] != source['sha256'] or rec['resource_date']>cutoff:
            continue
        if project:
            native=db.execute('SELECT native_id FROM entities WHERE entity_id=?',
                              (rec['project_id'],)).fetchone()
            if native is None or native['native_id']!=project:
                continue
        if rec['basis']!='TREO' or rec['category']!='UNSPECIFIED_MINERAL_RESOURCE' or rec['confidence']!='OFFICIAL_SUMMARY_ONLY_NOT_C1':
            raise ValueError('Government screen accidentally admitted verified C1 or incompatible basis')
        matched=primary.get(rec['project_id'])
        primary_source=next((s for s in snapshots if matched and s['sha256']==matched['source_sha']),{})
        same_statement=matched and (matched['date']==rec['resource_date'] or primary_source.get('publication_date')==rec['resource_date'])
        if matched and same_statement and abs(matched['ore_mt']-rec['ore_mt'])<=.001*rec['ore_mt']:
            ratio=rec['grade_pct']/matched['grade_pct']
            if ratio>2 or ratio<.5:
                detail=dict(project_id=rec['project_id'],project_name=rec['project_name'],government_original_pdf_sha256=by_key['wa_dmpe_ree2026_original']['sha256'],government_original_pdf_page=2,government_grade_pct=rec['grade_pct'],primary_grade_pct=matched['grade_pct'],grade_ratio=ratio,government_sha256=rec['source_sha256'],primary_sha256=matched['source_sha'],reason='SAME_DATE_TONNAGE_PRIMARY_GRADE_DISAGREEMENT_NOT_CORRECTED_BY_IMPUTATION')
                excluded.append(detail);issue(db,rec['project_id'],rec['source_sha256'],'OFFICIAL_PRIMARY_GRADE_CONFLICT',canonical(detail));continue
        variables={'R1':rec['contained_treo_kt'],'R2':rec['grade_pct']}
        row={'project_id':rec['project_id'],'project_name':rec['project_name'],
             'scope':'WA_GOVERNMENT_RESOURCE_SUMMARY_NOT_ISSUER_HARMONIZED',
             'official_status':rec['official_status'],
             'raw_contained_treo_kt':rec['contained_treo_kt'],
             'raw_grade_pct':rec['grade_pct'],
             'source_sha256':rec['source_sha256'],
             'source_locator':rec['locator'],'effective_date':rec['resource_date'],
             'evidence_status':policy['status']}
        for code in codes:
            val=variables[code]
            c=criteria[code]
            half=policy['rounding_half_width'][code]
            row[code]=score(val,c)
            row[code+'_alt']=score(val,c,alternative=True)
            row[code+'_lower']=score(max(val-half,0),c)
            row[code+'_upper']=score(val+half,c)
            traces.append({'entity_id':rec['project_id'],'criterion':code,
                           'raw_value':val,'score':row[code],
                           'config_version':config['version'],
                           'source':canonical({'source_sha256':rec['source_sha256'],
                                               'locator':rec['locator'],
                                               'evidence_status':policy['status'],
                                               'effective_date':rec['resource_date'],
                                               'source_scope':'government_project_summary_not_JORC_harmonized'}),
                           'scoring':canonical(c)})
        rows.append(row)
    write_csv(Path(out)/'official_summary_exclusions.csv',excluded,['project_id','project_name','government_original_pdf_sha256','government_original_pdf_page','government_grade_pct','primary_grade_pct','grade_ratio','government_sha256','primary_sha256','reason'])
    folder=Path(out)/'official_wa_resource_screen'
    write_csv(folder/'matrix.csv',rows,
              ['project_id','project_name','scope','official_status','raw_contained_treo_kt',
               'raw_grade_pct','source_sha256','source_locator','effective_date','evidence_status',
               *[key for code in codes for key in (code,code+'_alt',code+'_lower',code+'_upper')]])
    write_csv(folder/'criteria.csv',[criteria[c] for c in codes],
              ['code','domain','direction','low','high','function'])
    weights=[{'scenario':name,'criterion':code,'weight':w[code]}
             for name,w in config['screen_scenarios'].items() for code in codes]
    for name,w in config['screen_scenarios'].items():
        if set(w)!=set(codes) or not all(v>0 for v in w.values()) or abs(sum(w.values())-1)>1e-10:
            raise ValueError('Invalid frozen screen preference weights: '+name)
    write_csv(folder/'weights.csv',weights,['scenario','criterion','weight'])
    return rows,traces

def prepare(db, cutoff, snapshots, resources, gis_values, config, out, project=None, canonical_ids=None, cases=None):
    out = Path(out)
    criteria = {c['code']:c for c in config['criteria']}
    selected_shas = {s['sha256'] for s in snapshots}
    coverage, traces, matrices = [], [], {}
    project_ids = list(resources)
    canonical_ids=canonical_ids or {}
    groups={}
    for eid in project_ids:groups.setdefault(canonical_ids.get(eid,eid),[]).append(eid)
    exclusions=[]
    for canonical_id,ids in groups.items():
        if len(ids)>1:
            for eid in ids:exclusions.append(dict(entity_id=eid,canonical_project_id=canonical_id,reason='MULTIPLE_RESOURCE_SCOPES_REQUIRE_COHORT_DECISION_NOT_AUTOMATIC_SUM'))
    project_ids=[eid for eid in project_ids if not any(r['entity_id']==eid for r in exclusions)]
    write_csv(out/'cohort_exclusions.csv',exclusions,['entity_id','canonical_project_id','reason'])
    if project:
        project_ids = [eid for eid in project_ids if db.execute('SELECT native_id FROM entities WHERE entity_id=?',(eid,)).fetchone()[0]==project]
    for eid in project_ids:
        resource = resources[eid]
        name = db.execute('SELECT name FROM records WHERE entity_id=? ORDER BY source_sha LIMIT 1',(eid,)).fetchone()[0]
        values = {'contained_treo_kt':resource['contained_treo_kt']}
        provenance = {'contained_treo_kt':resource}
        for r in db.execute("SELECT * FROM observations WHERE entity_id=? AND status='AUTO_VALIDATED' AND effective_date<=? ORDER BY effective_date",(eid,cutoff)):
            if r['source_sha'] in selected_shas and r['variable'] not in ('contained_treo_kt','ore_mt','grade'):
                values[r['variable']] = r['value']
                provenance[r['variable']] = {'obs_ids':[r['obs_id']], 'source_sha':r['source_sha'],'raw':json.loads(r['raw'])}
        for key, v in gis_values.get(eid,{}).items():
            values[key]=v['value'];provenance[key]=v
        scored={code:score(values[c['variable']],c) for code,c in criteria.items() if c['variable'] in values}
        is_dev = all(v in values for v in ('study_maturity_ord','recovery_pct'))
        is_full = is_dev and all(code in scored for code in config['panels']['six_domain'])
        coverage.append({'entity_id':eid,'canonical_project_id':canonical_ids.get(eid,eid),'project_name':name,'scope':resource['scope'],
                         'resource_defined':1,'development':int(is_dev),'full_evidence':int(is_full),
                         **{code:int(code in scored) for code in criteria}})
        for code, val in scored.items():
            c=criteria[code]
            traces.append({'entity_id':eid,'criterion':code,'raw_value':values[c['variable']],
                           'score':val,'config_version':config['version'],
                           'source':canonical(provenance[c['variable']]),'scoring':canonical(c)})
        for panel, codes in config['panels'].items():
            if not all(c in scored for c in codes) or (panel=='six_domain' and not is_full):
                continue
            host=next((r for r in db.execute('''SELECT r.deposit_type,r.source_sha FROM relations rel JOIN records r
                ON r.entity_id=rel.child_id AND r.source_sha=rel.source_sha WHERE rel.parent_id=?
                AND rel.relation='REPRESENTATIVE_POINT_NOT_ENTITY_EQUIVALENCE' ORDER BY r.source_sha''',(eid,)) if r['deposit_type'] and r['source_sha'] in selected_shas),None)
            row={'project_id':eid,'canonical_project_id':canonical_ids.get(eid,eid),'project_name':name,'scope':resource['scope'],'deposit_type':host[0] if host else None}
            for code in codes:
                c=criteria[code]; raw=values[c['variable']]
                row[code]=scored[code]
                row[code+'_alt']=score(raw,c,alternative=True)
                # These are source rounding intervals, not geological uncertainty.
                evidence=provenance.get(c['variable'],{}).get('raw',{})
                half=evidence.get('rounding_half_width',0)
                bounds=resource['rounding_bounds_kt'] if code=='R1' else evidence.get('rounding_bounds',[raw-half,raw+half])
                row[code+'_lower']=min(score(v,c) for v in bounds)
                row[code+'_upper']=max(score(v,c) for v in bounds)
            matrices.setdefault(panel,[]).append(row)
    screen_rows,screen_traces=_official_wa_resource_screen(db,cutoff,snapshots,config,criteria,out,project)
    traces.extend(screen_traces)
    matrices['official_wa_resource_screen']=screen_rows
    from .studies import prepare as prepare_cases
    case_panels,case_traces=prepare_cases(cases or [],config,out,canonical_ids)
    traces.extend(case_traces)
    write_csv(out/'cohort_coverage.csv',coverage,['entity_id','canonical_project_id','project_name','scope','resource_defined','development','full_evidence',*criteria])
    write_csv(out/'value_trace.csv',traces,['entity_id','criterion','raw_value','score','config_version','source','scoring'])
    write_csv(out/'resources.csv',list(resources.values()),['entity_id','scope','date','ore_mt','grade_pct','contained_treo_kt','calculated_from_rounded_inputs_kt','rounding_bounds_kt','source_sha','obs_ids','interpretation'])
    for panel, rows in matrices.items():
        if panel in config.get('screen_panels', {}):
            # Screen matrices and scenario weights are generated separately.
            continue
        codes=config['panels'][panel]
        folder=out/panel
        write_csv(folder/'matrix.csv',rows,['project_id','canonical_project_id','project_name','scope','deposit_type',*[key for code in codes for key in (code,code+'_alt',code+'_lower',code+'_upper')]])
        write_csv(folder/'criteria.csv',[criteria[c] for c in codes],['code','domain','direction','low','high','function'])
        weights=[]
        for scenario, domain_weights in config['scenarios'].items():
            domains={criteria[c]['domain'] for c in codes}
            total=sum(domain_weights[d] for d in domains)
            for code in codes:
                domain=criteria[code]['domain']
                count=sum(criteria[c]['domain']==domain for c in codes)
                weights.append({'scenario':scenario,'criterion':code,'weight':domain_weights[domain]/total/count})
        write_csv(folder/'weights.csv',weights,['scenario','criterion','weight'])
    return {'coverage':coverage,'panels':{**{p:len(v) for p,v in matrices.items()},**case_panels},
            'trace_values':len(traces),'government_screen_n':len(screen_rows)}

def run_r(root, out, prepared, config, rscript=None):
    executable = rscript or shutil.which('Rscript')
    if not executable:
        raise RuntimeError('Rscript is required. Supply --rscript or explicitly use --skip-r for coverage only.')
    results={}
    for panel,n in prepared['panels'].items():
        if n<2:
            results[panel]={'status':'INSUFFICIENT_SAMPLE','n':n};continue
        folder=Path(out)/panel
        command=[str(executable),str(Path(root)/'R/run_mcda.R'),str(folder),
                 str(config['monte_carlo']['seed']),str(config['monte_carlo']['reps']),str(config['promethee_threshold']),
                 str(config['monte_carlo']['dirichlet_concentration'])]
        result=subprocess.run(command,capture_output=True,text=True,timeout=300)
        (folder/'R.log').write_text(result.stdout+'\n'+result.stderr,encoding='utf-8')
        if result.returncode:
            raise RuntimeError('R MCDA failed: '+result.stderr[-2000:])
        expected=('ranking.csv','weight_uncertainty.csv','rounding_uncertainty.csv','leave_out.csv',
                  'method_comparison.csv','function_sensitivity.csv','cohort_sensitivity.csv','ahp_audit.csv')
        if not all((folder/p).is_file() for p in expected):
            raise RuntimeError('R output contract incomplete')
        results[panel]={'status':'COMPLETED','n':n,'weight_status':config['weight_status'],
                        'evidence_status':('PRIMARY_ENDPOINT_MATCHED_DFS_CASES_NOT_OPERATING_RESULTS' if panel in config.get('case_panels',{}) else config['screen_evidence_policy']['status'] if panel=='official_wa_resource_screen' else 'ISSUER_SCOPE_VALIDATED'),
                        'full_evidence_eligibility':panel=='six_domain'}
    return results
