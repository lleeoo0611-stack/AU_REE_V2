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
        # Source-bound diagnostic cells can contain many scoped disclosures.
        # Keep a bounded reader limit and restore the caller's CSV contract.
        previous=csv.field_size_limit(16*1024*1024)
        try:
            with path.open(encoding='utf-8-sig',newline='') as stream:return list(csv.DictReader(stream))
        finally:csv.field_size_limit(previous)
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
        result['validated_structured_events']=None
        if database.exists() and snapshots is not None:
            locked={s['key']:s['sha256'] for s in snapshots};selected=set(locked.values());unique=set();events=set()
            configuration=folder/'configuration.json'
            validation=None
            if configuration.exists():validation=json.loads(configuration.read_text(encoding='utf-8'))['research'].get('evidence_resolution',{}).get('document_pipeline',{}).get('validation_version')
            for observation in json.loads(database.read_text(encoding='utf-8'))['observations']:
                if observation['status']!='AUTO_VALIDATED' or observation['source_sha'] not in selected:continue
                raw=json.loads(observation['raw'])
                from .selection import observation_visible
                if not observation_visible(raw,selected,validation):continue
                if raw.get('page_extraction_key') and locked.get(raw['page_extraction_key'])!=raw.get('page_extraction_sha256'):continue
                if observation['variable']=='commercial_event':events.add(observation['obs_id'])
                if observation['value'] is None:continue
                unique.add(canonical({k:observation[k] for k in ('entity_id','variable','value','unit','basis','scope','statement_id','effective_date','source_sha')}))
            result['validated_statement_values']=len(unique)
            result['validated_structured_events']=len(events)
        cov=read(folder,'cohort_coverage.csv')
        relations=read(folder,'government_identity_candidates.csv')
        result['government_unconfirmed_relation_candidates']=None if relations is None else sum(r['status'].startswith('CANDIDATE') for r in relations)
        result['government_confirmed_representative_site_relations']=None if relations is None else sum(r['status'].startswith('CONFIRMED_REPRESENTATIVE') for r in relations)
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
    # A larger source census can discover new candidates while resolving old ones.
    old_pairs=read(before,'unresolved_identity_pairs.csv');new_pairs=read(after,'unresolved_identity_pairs.csv')
    members=read(after,'canonical_membership.csv')
    if old_pairs is not None and new_pairs is not None and members is not None:
        mapping={r['entity_id']:r['canonical_id'] for r in members}
        pair_key=lambda r:tuple(sorted((r['a'],r['b'])))
        old_keys={pair_key(r) for r in old_pairs};current={pair_key(r):r for r in new_pairs}
        follow=[]
        for row in old_pairs:
            confirmed=row['a'] in mapping and row['b'] in mapping and mapping[row['a']]==mapping[row['b']]
            status='DOCUMENT_SUPPORTED_EQUIVALENCE' if confirmed else current.get(pair_key(row),{}).get('reason','UNRESOLVED_NOT_CURRENT_CANDIDATE')
            follow.append(dict(a=row['a'],b=row['b'],name=row['name'],state=row['state'],baseline_reason=row.get('reason'),current_status=status))
        write_csv(after/'comparison_identity_followup.csv',follow,['a','b','name','state','baseline_reason','current_status'])
        remaining=sum(r['current_status']!='DOCUMENT_SUPPORTED_EQUIVALENCE' for r in follow)
        metrics.extend([dict(metric='baseline_unresolved_pairs_remaining',before=len(old_pairs),after=remaining,change=remaining-len(old_pairs)),
                        dict(metric='new_unresolved_pairs_since_baseline',before=0,after=len(set(current)-old_keys),change=len(set(current)-old_keys))])
    old_gaps=read(before,'primary_scope_gaps.csv');new_gaps=read(after,'primary_scope_gaps.csv');technical=read(after,'technical_project_coverage.csv')
    if old_gaps is not None and new_gaps is not None and technical is not None:
        now={r['canonical_project_id']:r for r in technical};old_ids={r['canonical_project_id'] for r in old_gaps}
        follow=[dict(canonical_project_id=r['canonical_project_id'],project_names=r['project_names'],
                     current_status=now.get(r['canonical_project_id'],{}).get('status','NOT_PRESENT_UNKNOWN')) for r in old_gaps]
        write_csv(after/'comparison_primary_gap_followup.csv',follow,['canonical_project_id','project_names','current_status'])
        remaining=sum(r['current_status'] in ('NO_CONTROLLED_PRIMARY_TECHNICAL_SCOPE_YET','NOT_PRESENT_UNKNOWN') for r in follow)
        metrics.extend([dict(metric='baseline_primary_gaps_remaining',before=len(old_gaps),after=remaining,change=remaining-len(old_gaps)),
                        dict(metric='new_primary_gap_groups',before=0,after=sum(r['canonical_project_id'] not in old_ids for r in new_gaps),change=sum(r['canonical_project_id'] not in old_ids for r in new_gaps))])
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
        for name in ('snapshot_lock.json','unresolved_identity_pairs.csv','primary_scope_gaps.csv','technical_project_coverage.csv',
                     'canonical_membership.csv','resources.csv','cohort_coverage.csv','project_domain_evidence.csv','logical_database.json'):
            if (folder/name).exists():inputs[label+'/'+name]=filehash(folder/name)
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

def prepare(db, cutoff, snapshots, resources, gis_values, config, out, project=None, canonical_ids=None, cases=None, selection=None):
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
        if selection is not None:
            resolved=selection['values'].get(canonical_ids.get(eid,eid),{})
            for code,evidence in resolved.items():
                if code in criteria:
                    variable=criteria[code]['variable']
                    values[variable]=evidence['value'];provenance[variable]=evidence
        else:
            # Preserve the pre-Phase7 selection policy only for frozen runs.
            for r in db.execute("SELECT * FROM observations WHERE entity_id=? AND status='AUTO_VALIDATED' AND effective_date<=? ORDER BY effective_date",(eid,cutoff)):
                if r['source_sha'] in selected_shas and r['variable'] not in ('contained_treo_kt','ore_mt','grade'):
                    values[r['variable']] = r['value']
                    provenance[r['variable']] = {'obs_ids':[r['obs_id']], 'source_sha':r['source_sha'],'raw':json.loads(r['raw'])}
        for key, v in gis_values.get(eid,{}).items():
            values[key]=v['value'];provenance[key]=v
        scored={code:score(values[c['variable']],c) for code,c in criteria.items() if c['variable'] in values}
        dev_codes=selection['policy']['cohorts']['development']['requires'] if selection is not None else ['D1','T1']
        is_dev = all(code in scored for code in dev_codes)
        is_full = is_dev and all(code in scored for code in config['panels']['six_domain'])
        currentness={}
        if config.get('research_analysis_version')=='evidence-cohort-v1' and selection is not None:
            newer=[c for c in selection['inventory'] if c['project_id']==canonical_ids.get(eid,eid) and
                   c.get('domain')=='Resource' and c.get('basis')=='UNHARMONIZED_SOURCE_REPORTED_TREO' and
                   c.get('effective_date','')>resource['date']]
            currentness=dict(resource_currentness='NEWER_UNHARMONIZED_DISCLOSURE_EARLIER_VERIFIED_SCOPE_RETAINED' if newer else 'LATEST_COMPLETENESS_NOT_CERTIFIED',
                            newer_unharmonized_evidence_ids=canonical(sorted(c['evidence_id'] for c in newer)))
        coverage.append({'entity_id':eid,'canonical_project_id':canonical_ids.get(eid,eid),'project_name':name,'scope':resource['scope'],
                         'resource_defined':1,'development':int(is_dev),'full_evidence':int(is_full),
                         **{code:int(code in scored) for code in criteria},**currentness})
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
    case_panels,case_traces=prepare_cases(cases or [],config,out,canonical_ids,selection)
    traces.extend(case_traces)
    coverage_columns=['entity_id','canonical_project_id','project_name','scope','resource_defined','development','full_evidence',*criteria]
    if config.get('research_analysis_version')=='evidence-cohort-v1':
        coverage_columns+=['resource_currentness','newer_unharmonized_evidence_ids']
        coverage.sort(key=lambda r:r['canonical_project_id'])
    write_csv(out/'cohort_coverage.csv',coverage,coverage_columns)
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
        if config['monte_carlo'].get('method_version'):
            command.append(config['monte_carlo']['method_version'])
        if config.get('research_analysis_version'):
            if not config['monte_carlo'].get('method_version'):
                raise ValueError('Research analysis requires an explicit MCDA method version')
            command.append(config['research_analysis_version'])
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
        if panel.startswith('technical_process_concentrate_'):
            results[panel]['evidence_status']='NAMED_DESIGN_FORECAST_COMPARISON_NOT_OPERATING_OR_NATIONAL_RANK'
        if config.get('evidence_resolution'):
            results[panel]['formal_c1_eligibility']=False
            results[panel]['criteria_policy']=config['evidence_resolution']['version']
            if panel in config['evidence_resolution']['panels']:
                results[panel]['evidence_status']='EXPLORATORY_CANDIDATE_CRITERIA_NOT_FORMAL_C1'
    return results


def research_readiness(selection,out,analysis_version=None):
    """Descriptive views reuse resolved evidence and ranks, without new scores."""
    from .selection import commercial_evidence
    from collections import Counter
    out=Path(out);events=commercial_evidence(selection)
    if events:write_csv(out/'commercial_event_semantics.csv',events,list(events[0]))
    projects=[];features=[]
    technical=selection.get('technical_comparability',[])
    ranks={}
    for file in sorted(out.glob('*/ranking.csv')):
        for r in csv.DictReader(file.open(encoding='utf-8')):
            ranks.setdefault(r['project_id'],[]).append(dict(panel=file.parent.name,scenario=r['scenario'],rank=r['promethee_rank']))
    for pid in sorted(selection['projects']):
        valid=[r for r in events if r['project_id']==pid and r['qualified_project_event']]
        finance=selection['values'].get(pid,{}).get('C1');offtake=[r for r in valid if r['event_type']=='OFFTAKE']
        projects.append(dict(project_id=pid,financing_milestone=None if not finance else finance['value'],
            offtake_evidence=len(offtake),conditions_known=sum(r['conditions_status']!='UNKNOWN' for r in valid),
            conditions_satisfied=sum(r['conditions_status']=='SATISFIED' for r in valid),
            financial_close_evidence=sum(r['financial_close']=='EVIDENCED' for r in valid),drawdown_evidence=sum(r['drawdown']=='EVIDENCED' for r in valid),
            joint_financing_offtake=int(finance is not None and bool(offtake)),
            commercial_complete=int(bool(finance) and bool(offtake) and all(r['counterparty'] and r['valid_to'] and r['conditions_status']!='UNKNOWN' for r in valid)),
            interpretation='DISCLOSURE_COVERAGE_NOT_ABSENCE_CURRENT_FUNDS_OR_FORMAL_C1'))
        tr=[r for r in technical if r['project_id']==pid]
        if tr:
            counts=Counter(r['comparability_status'] for r in tr)
            features.append(dict(project_id=pid,independent_projects=1,source_scope_keys_n=len({r['case_id'] for r in tr}),
                engineering_study_cases_n=len({c['case_id'] for c in selection['inventory'] if c['project_id']==pid and c['origin']=='STUDY_PARAMETER' and not c.get('reason')}),
                source_shas=canonical(sorted({r['source_sha256'] for r in tr})),
                process_descriptions=canonical(sorted({c['process'] for c in selection['inventory'] if c['project_id']==pid and c.get('process') and not c.get('reason')})),
                mineralogy_processing=sum(r['semantic_class']=='A_MINERALOGY_PROCESSING' for r in tr),
                performance=sum(r['semantic_class']=='B_PROCESS_PERFORMANCE' for r in tr),quality=sum(r['semantic_class']=='C_EVIDENCE_QUALITY' for r in tr),
                comparable=counts['NUMERIC_COMPARABLE'],descriptive=counts['DESCRIPTIVE_ONLY'],not_comparable=counts['NOT_COMPARABLE'],
                endpoints=canonical(sorted({r['endpoint'] for r in tr if r['endpoint']})),
                scales=canonical(sorted({r['scale'] for r in tr if r['scale']})),
                missingness_reasons=canonical(dict(sorted(Counter(reason for r in tr for reason in r['reason_codes']).items()))),
                rank_links=canonical(ranks.get(pid,[])),
                interpretation='PROJECT_UNIT_NOT_TEST_ROWS;SELECTED_DISCLOSURE_MISSINGNESS_NOT_MCAR_OR_CAUSAL_INFERENCE'))
    write_csv(out/'commercial_project_coverage.csv',projects,list(projects[0]) if projects else ['project_id'])
    if analysis_version=='evidence-cohort-v1':
        import re
        minerals=('monazite','xenotime','apatite','churchite','rhabdophane','kaolinite','bastnaesite','bastn\u00e4site')
        for row in features:
            observations=[c for c in selection['inventory'] if c['project_id']==row['project_id'] and
                          c.get('domain')=='Technical' and not c.get('reason')]
            mentions=[]
            for c in observations:
                text=' '.join(str(c.get('raw',{}).get(k,'')) for k in ('raw_text','process','scope'))
                found=[m for m in minerals if re.search(r'\b'+re.escape(m)+r'\b',text,re.I)]
                if found:mentions.append(dict(minerals=found,evidence_id=c['evidence_id'],source_sha256=c['source_sha256'],
                    locator=c.get('locator'),scope=c.get('scope'),feed=c.get('feed'),endpoint=c.get('endpoint'),
                    interpretation='LITERAL_SOURCE_MENTION_NOT_RESOURCE_WIDE_HOST_OR_MECHANISM_CERTIFICATION'))
            row['mineral_mentions']=canonical(mentions)
            row['scorable_criteria']=canonical(sorted(selection['values'].get(row['project_id'],{})))
        # Observable selection patterns only: one independent Project per row,
        # not a missing-data mechanism test or inferential model.
        coverage_file=out/'cohort_coverage.csv'
        if coverage_file.exists():
            coverage=list(csv.DictReader(coverage_file.open(encoding='utf-8')))
            if len({r['canonical_project_id'] for r in coverage})!=len(coverage):
                raise ValueError('Cohort description requires unique canonical Projects')
            resources={r['entity_id']:float(r['contained_treo_kt']) for r in csv.DictReader((out/'resources.csv').open(encoding='utf-8'))}
            import statistics
            patterns=[]
            for code in ('S1','T1','D1','I1','I2','I3','I4','C1','TC1','TC2'):
                for available in (0,1):
                    group=[r for r in coverage if int(r.get(code,0))==available]
                    vals=[resources[r['entity_id']] for r in group if r['entity_id'] in resources]
                    patterns.append(dict(criterion=code,scorable=available,projects=len(group),
                        median_contained_treo_kt=statistics.median(vals) if vals else None,
                        project_ids=canonical(sorted(r['canonical_project_id'] for r in group)),
                        interpretation='OBSERVED_RESOURCE_COHORT_SELECTION_PATTERN_NOT_MCAR_MAR_MNAR_OR_CAUSAL_TEST'))
            write_csv(out/'cohort_missingness_description.csv',patterns,list(patterns[0]))
    write_csv(out/'aim_c_technical_features.csv',features,list(features[0]) if features else ['project_id'])
    return projects


def canonicalize_interchange(out):
    """Stable interchange for v2 only; legacy frozen CSV order is untouched."""
    for name,keys in [('matrix.csv',('project_id',)),('criteria.csv',('code',)),('weights.csv',('scenario','criterion'))]:
        for path in sorted(Path(out).glob('*/'+name)):
            with path.open(encoding='utf-8',newline='') as stream:
                reader=csv.DictReader(stream);fields=reader.fieldnames;rows=list(reader)
            write_csv(path,sorted(rows,key=lambda r:tuple(r[k] for k in keys)),fields)


def prepare_technical_panel(selection,prepared,config,out):
    """Additional source-qualified interchange, consumed by the existing R engine.

    No resource scope is copied onto a different mine plan. The configured
    reference stays fixed; scientific conflicts use the same unified view.
    """
    from .technical import technical_record,technical_compare,csvrows_local,unified_observations
    policy=config['evidence_resolution'];model=policy['technical_profile']['numeric_model']
    contract=model['contract'];eligibility=[];candidates={};options={}
    shared=unified_observations(selection,policy['technical_profile'])
    by_evidence={eid:r for r in shared for eid in r['evidence_ids']}
    for c in selection['inventory']:
        if c.get('domain')!='Technical':continue
        r=technical_record(c,policy);reasons=technical_compare(r,contract,contract['model_assumptions'])
        if c.get('origin')!='STUDY_PARAMETER':reasons.append('NOT_TYPED_NAMED_ENGINEERING_CASE_RETAIN_AS_RAW_OR_CORROBORATION')
        scientific=by_evidence.get(r['evidence_id'])
        if c.get('origin')=='STUDY_PARAMETER':
            if scientific is None:reasons.append('SCIENTIFIC_IDENTITY_NOT_ESTABLISHED')
            elif scientific['measurement_relation']=='CONFLICTING_VALUES_SAME_SCIENTIFIC_OBSERVATION':reasons.append('SCIENTIFIC_OBSERVATION_VALUE_CONFLICT')
        codes=[code for code,item in model['criteria'].items() if item['variable']==r['variable']]
        entry=dict(project_id=r['project_id'],case_id=r['case_id'],evidence_id=r['evidence_id'],source_sha256=r['source_sha256'],pdf_page=r['pdf_page'],scope=r['scope'],value=r['value'],basis=r['basis'],feed=r['feed'],endpoint=r['endpoint'],scale=r['scale'],quantity=r['variable'],criteria=codes,reasons=sorted(set(reasons)),eligible=not reasons,model_version=model['version'])
        eligibility.append(entry)
        if reasons or not codes:continue
        key=(r['project_id'],r['case_id'],codes[0]);options.setdefault(key,[]).append((r,entry,scientific))
    for (pid,case,code),group in options.items():
        # Equal values alone do not establish equal scope or measurement.
        if len({x[2]['scientific_observation_identity'] for x in group})>1 or len({canonical(x[0]['value']) for x in group})>1:
            for _,entry,_ in group:
                entry['reasons']=sorted(set(entry['reasons']+['AMBIGUOUS_COMPATIBLE_OBSERVATIONS_FOR_CASE_CRITERION']));entry['eligible']=False
            continue
        # Exact semantic corroboration is already linked by unified_observations;
        # all evidence IDs/locators remain in that view, never extra experiments.
        candidates.setdefault((pid,case),{})[code]=min((x[0] for x in group),key=canonical)
    # The reference comes from the current shared matrix, never a frozen rank.
    reference={};reference_code=model['reference_criterion']
    for panel in sorted(prepared['panels']):
        file=Path(out)/panel/'matrix.csv'
        if not file.exists():continue
        with file.open(encoding='utf8',newline='') as f:
            for r in csv.DictReader(f):
                if reference_code in r:reference.setdefault(r.get('canonical_project_id',r['project_id']),r)
    project_cases={pid:{case for p,case in candidates if p==pid} for pid,case in candidates}
    rows=[];raw=[];decisions=[]
    for (pid,case),values in sorted(candidates.items()):
        why=[]
        if len(project_cases[pid])!=1:why.append('MULTIPLE_CASES_REQUIRE_SCOPE_CHOICE')
        if set(values)!=set(model['criteria']):why.append('INCOMPLETE_COMMON_CRITERIA')
        if pid not in reference:why.append('NO_SHARED_REFERENCE_CRITERION')
        decisions.append(dict(project_id=pid,case_id=case,eligible=not why,reasons=why))
        if why:continue
        rr=reference[pid];first=next(iter(values.values()))
        r=dict(project_id=pid,canonical_project_id=pid,project_name=rr['project_name'],scope=first['scope'],case_id=case,uncertainty_kind='NO_SOURCE_BOUNDS')
        ref=float(rr[reference_code]);r.update({reference_code:ref,reference_code+'_alt':ref,reference_code+'_lower':ref,reference_code+'_upper':ref})
        for code,v in values.items():
            x=v['value']/100
            r.update({code:x,code+'_alt':x,code+'_lower':x,code+'_upper':x})
            raw.append(dict(project_id=pid,case_id=case,criterion=code,value=v['value'],unit=v['unit'],basis=v['basis'],feed=v['feed'],endpoint=v['endpoint'],scope=v['scope'],source_sha256=v['source_sha256'],pdf_page=v['pdf_page'],locator=v['locator'],evidence_id=v['evidence_id'],evidence_mode=v['evidence_mode']))
        rows.append(r)
    write_csv(Path(out)/'technical_panel_eligibility.csv',csvrows_local(eligibility),list(eligibility[0]) if eligibility else ['project_id','reasons'])
    write_csv(Path(out)/'technical_panel_cases.csv',csvrows_local(decisions),['project_id','case_id','eligible','reasons'])
    write_csv(Path(out)/'technical_panel_inputs.csv',raw,list(raw[0]) if raw else ['project_id'])
    criteria=[dict(code=code,domain=x['domain'],direction=x['direction'],low=x['low'],high=x['high'],function=x['function']) for code,x in model['criteria'].items()]
    criteria+=[dict(code=reference_code,domain='Development',direction='MAX',low=1,high=6,function='linear')]
    weights=[]
    for total in model['weights']['technical_totals']:
        for i,(recovery,grade) in enumerate(model['weights']['technical_subweights']):
            if total==0 and i>0:continue
            scenario='technical_'+str(total)+'_split_'+str(i+1)
            for code,weight in [(reference_code,1-total),('TPR',total*recovery),('TPG',total*grade)]:weights.append(dict(scenario=scenario,criterion=code,weight=weight,group='Technical' if code in model['criteria'] else 'Reference',group_weight=total if code in model['criteria'] else 1-total))
    for variant in ('fixed','sample_minmax'):
        panel='technical_process_concentrate_'+variant;folder=Path(out)/panel
        matrix=[dict(r) for r in rows]
        if variant=='sample_minmax' and len(rows)>1:
            for code in model['criteria']:
                lo=min(r[code] for r in rows);hi=max(r[code] for r in rows)
                for r in matrix:
                    x=(r[code]-lo)/(hi-lo) if hi>lo else .5
                    for suffix in ('','_alt','_lower','_upper'):r[code+suffix]=x
        write_csv(folder/'matrix.csv',matrix,list(matrix[0]) if matrix else ['project_id','project_name','scope'])
        write_csv(folder/'criteria.csv',criteria,['code','domain','direction','low','high','function'])
        write_csv(folder/'weights.csv',weights,['scenario','criterion','weight','group','group_weight'])
        prepared['panels'][panel]=len(rows)
    # Scope scenario cannot turn forecasts into operating measurements.
    write_csv(Path(out)/'technical_scope_sensitivity.csv',[dict(scenario='ENGINEERING_DESIGN',n=len(rows),reason='Explicit forecast comparison only'),dict(scenario='OPERATING_ONLY',n=0,reason='No demonstrated operating observations in admitted design cases')],['scenario','n','reason'])
    return dict(version=model['version'],n=len(rows),cases=decisions,rank_scope='TWO_NAMED_DESIGN_CASES_NOT_NATIONAL_RANKING')
