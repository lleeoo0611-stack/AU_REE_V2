"""Shared technical evidence semantics, contracts and source-bound case analysis.

Selection re-exports these functions for historical callers. This module owns
comparison and derivation; it neither acquires sources nor maintains a new store.
"""
import math
import json
import re
from collections import defaultdict, Counter
from pathlib import Path
from .store import canonical, digest


def technical_record(c, policy):
    """A view of existing evidence, never a second store or inferred recovery.

    Case identity excludes the oxide/parameter. Missing test conditions stay
    missing; an engineering design is explicitly distinguished from testwork.
    """
    raw=c.get('raw',{});variable=c['variable']
    role=policy.get('study_parameters',{}).get(variable,{}).get('role',c.get('role'))
    if raw.get('kind')=='LEACH_TABLE_ROW' or ('extraction' in variable and c.get('unit')=='%'):role='LEACH_EXTRACTION'
    if raw.get('kind')=='TECHNICAL_TABLE_CELL':role=policy.get('technical_analysis',{}).get('quantity_roles',{}).get(raw.get('quantity'),role)
    performance=role in policy['technical_comparability']['performance_roles'] or (raw.get('kind')=='TECHNICAL_TABLE_CELL' and role in policy.get('technical_analysis',{}).get('performance_roles',[]))
    quality=role in policy['technical_comparability']['quality_roles']
    category='B_PROCESS_PERFORMANCE' if performance else 'C_EVIDENCE_QUALITY' if quality else 'A_MINERALOGY_PROCESSING'
    model=c.get('scale') in ('DFS_MODEL','PFS_MODEL','SCOPING_MODEL') and (
        c.get('origin')=='STUDY_PARAMETER' or
        (raw.get('statistic')=='ENGINEERING_DESIGN' and raw.get('evidence_mode')=='ENGINEERING_MODEL'))
    case_id=c.get('case_id') or raw.get('case_id') or raw.get('statement_id') or c['evidence_id']
    parameters=raw.get('parameters',{})
    population=raw.get('sample_population') or raw.get('sample_id')
    count=parameters.get('selected_composites_n',parameters.get('composites_n'))
    if population is None and count is not None:population='SOURCE_COMPOSITES_N='+str(count)
    statistic=raw.get('statistic') or ('ENGINEERING_DESIGN' if model else None)
    if statistic is None and '_average_' in variable:statistic='SOURCE_REPORTED_MEAN'
    if statistic is None and '_max_' in variable:statistic='SOURCE_REPORTED_MAXIMUM'
    rep=raw.get('representativeness_evidence')
    bound_rep=isinstance(rep,dict) and rep.get('source_sha256')==c['source_sha256'] and rep.get('pdf_page') and rep.get('quote') and rep.get('sample_id')==raw.get('sample_id') and rep.get('target_population')
    return dict(project_id=c['project_id'],case_id=case_id,evidence_id=c['evidence_id'],
                source_sha256=c['source_sha256'],pdf_page=c.get('pdf_page'),locator=c.get('locator'),
                variable=variable,value=c.get('value'),unit=c.get('unit'),basis=c.get('basis'),
                scope=c.get('scope'),feed=c.get('feed'),endpoint=c.get('endpoint'),scale=c.get('scale'),
                process_stage=role,semantic_class=category,study_date=c.get('effective_date'),
                sample_population=population,
                sample_interval=raw.get('sample_interval'),statistic=statistic,
                reagent=raw.get('reagent') or ('HCl' if 'hcl_concentration_pct' in parameters else None),
                temperature_c=raw.get('temperature_c',parameters.get('temperature_c')),
                residence_hours=raw.get('residence_hours',parameters.get('leach_time_hours')),
                acid_concentration=raw.get('acid_concentration',parameters.get('hcl_concentration_pct')),
                pressure=raw.get('pressure'),evidence_reason=c.get('reason'),
                evidence_mode='ENGINEERING_MODEL' if model else raw.get('evidence_mode','TESTWORK_OR_DISCLOSURE'),
                scope_kind='CASE_MINE_PLAN' if model else 'SOURCE_SPECIFIC_SAMPLE_OR_DISCLOSURE',
                representativeness='MINE_PLAN_DESIGN_NOT_OPERATING_MEASUREMENT' if model else (raw.get('representativeness') if bound_rep else 'RESOURCE_REPRESENTATIVENESS_NOT_ESTABLISHED'),
                **({'representativeness_evidence':rep} if bound_rep else {}))


def technical_compare(record, contract, assumptions=()):
    """Single comparison gate used by criteria and the technical audit output.

    A contract describes a quantity, not merely a percentage. Design forecasts
    may compare only under explicit mine-plan/model assumptions; no sequence of
    recoveries is multiplied here. Conditions are compulsory for measured tests.
    """
    r=record;reasons=[]
    if r.get('evidence_reason'):reasons.append('EVIDENCE_NOT_VALIDATED')
    if r.get('variable') not in contract.get('variables',[]):reasons.append('QUANTITY_MISMATCH')
    if r.get('unit')!=contract.get('unit'):reasons.append('UNIT_MISMATCH')
    if contract.get('basis') and r.get('basis') not in contract['basis']:reasons.append('REO_BASIS_MISMATCH')
    labels={'endpoint':'ENDPOINT_MISMATCH','feed':'FEED_MISMATCH','scale':'TEST_SCALE_MISMATCH'}
    for key,value in contract.get('requires',{}).items():
        if r.get(key)!=value:reasons.append(labels.get(key,'SCOPE_MISMATCH'))
    if not r.get('scope') or not r.get('study_date') or not r.get('case_id'):reasons.append('SCOPE_MISMATCH')
    if r.get('evidence_mode')=='ENGINEERING_MODEL' and contract.get('version')!='technical-use-v2':
        if not assumptions:reasons.append('MODEL_ASSUMPTIONS_NOT_DEFINED')
    elif contract.get('version')=='technical-use-v2':
        if r.get('evidence_mode')=='ENGINEERING_MODEL' and not assumptions:reasons.append('MODEL_ASSUMPTIONS_NOT_DEFINED')
        if any(r.get(k) is None for k in contract.get('required_conditions',[])):reasons.append('MISSING_CONDITIONS')
        if contract.get('analysis_scope')=='PROJECT_EXTRAPOLATION':
            rep=r.get('representativeness_evidence',{})
            if not rep.get('target_population') or rep.get('qualification')!='TARGET_POPULATION_VALIDATED':reasons.append('SAMPLE_REPRESENTATIVENESS_LIMITATION')
    else:
        if r.get('representativeness')!='REPRESENTATIVE_WITH_SOURCE':reasons.append('SAMPLE_REPRESENTATIVENESS_LIMITATION')
        if any(r.get(k) is None for k in ('sample_population','statistic','reagent','temperature_c','residence_hours','acid_concentration','pressure')):
            reasons.append('MISSING_CONDITIONS')
    value=r.get('value')
    if not isinstance(value,(int,float)) or isinstance(value,bool) or not math.isfinite(value):reasons.append('NO_FINITE_NUMERIC_VALUE')
    elif r.get('unit')=='%' and not 0<=value<=100:reasons.append('PERCENT_OUT_OF_RANGE')
    return sorted(set(reasons))


def technical_comparability(inventory, policy):
    """One row per scientific observation; duplicates corroborate, not new cases."""
    definition=policy['technical_comparability'];rows=[]
    for c in inventory:
        if c.get('domain')!='Technical':continue
        r=technical_record(c,policy)
        matching=[code for code in definition['candidate_criteria'] if not technical_compare(r,policy['criteria'][code],definition['model_assumptions'])]
        if matching:
            group=matching[0];reasons=[];status='NUMERIC_COMPARABLE'
        elif r['value'] is None and not r['evidence_reason']:
            group='DESCRIPTIVE';reasons=['NO_NUMERIC_COMPARISON'];status='DESCRIPTIVE_ONLY'
        elif r['semantic_class']!='B_PROCESS_PERFORMANCE' and not r['evidence_reason']:
            group='DESCRIPTIVE';reasons=['NO_ADOPTED_NUMERIC_CONTRACT'];status='DESCRIPTIVE_ONLY'
        else:
            # Explain incompatibility relative to the declared recovery screen;
            # never relabel a source-specific assay as a comparable plant value.
            group='RAW-'+digest([r.get(k) for k in ('variable','endpoint','feed','basis','scale','sample_population','statistic','reagent','temperature_c','residence_hours','acid_concentration','pressure')])[:16]
            reasons=technical_compare(r,policy['criteria'][definition['reference_criterion']],definition['model_assumptions'])
            status='NOT_COMPARABLE'
        rows.append(dict(r,comparison_group=group,comparability_status=status,reason_codes=reasons,
                         assumptions=definition['model_assumptions'] if matching else [],
                         allowed_analysis='DESCRIPTIVE_ONLY',contract_version=definition['version']))
    # An observation version is not an independent replicate. Conflicting
    # values at the same case/quantity/date/conditions fail regardless of order.
    groups=defaultdict(list)
    identity_keys=('project_id','case_id','variable','unit','basis','scope','feed','endpoint','scale','sample_population','sample_interval','statistic','reagent','temperature_c','residence_hours','acid_concentration','pressure','study_date')
    for r in rows:groups[canonical([r.get(k) for k in identity_keys])].append(r)
    result=[]
    for group in groups.values():
        valid=[x for x in group if not x['evidence_reason']]
        r=dict(sorted(valid or group,key=canonical)[0]);r['evidence_ids']=sorted({x['evidence_id'] for x in group})
        r['source_shas']=sorted({x['source_sha256'] for x in group})
        r['source_locators']=sorted({canonical([x['source_sha256'],x['pdf_page'],x['locator']]) for x in group})
        if len({canonical(x['value']) for x in group if not x['evidence_reason']})>1:
            r.update(value=None,comparability_status='NOT_COMPARABLE',reason_codes=['CONFLICTING_EVIDENCE'])
        result.append(r)
    qualified_groups=defaultdict(list)
    for x in result:
        if x['comparability_status']=='NUMERIC_COMPARABLE':qualified_groups[x['comparison_group']].append(x)
    for r in result:
        qualified=qualified_groups[r['comparison_group']]
        r['independent_projects']=len({x['project_id'] for x in qualified})
        r['independent_cases']=len({(x['project_id'],x['case_id']) for x in qualified})
        if r['comparability_status']=='NUMERIC_COMPARABLE':
            # More than one study in a Project needs a scope choice, never an
            # arbitrary latest-case or highest-value selection.
            cases={x['case_id'] for x in qualified if x['project_id']==r['project_id']}
            if len(cases)>1:
                r.update(comparability_status='NOT_COMPARABLE',reason_codes=['SCOPE_MISMATCH','MULTIPLE_CASES_REQUIRE_DEFINITION'])
            elif r['independent_projects']>=2:r['allowed_analysis']='EXPLORATORY_CONTRACT_PANEL_NOT_FORMAL_C1'
            else:r['reason_codes']=['SINGLE_INDEPENDENT_PROJECT'];r['allowed_analysis']='WITHIN_CASE_DESCRIPTION_ONLY'
    return sorted(result,key=lambda r:canonical([r.get(k) for k in identity_keys]))



def ratio(numerator,denominator,mode):
    """Explicit cumulative quotients or connected serial-stage products."""
    a,b=numerator['value'],denominator['value']
    if a is None or b is None or not math.isfinite(a+b) or b<=0:return None
    if mode=='SAME_ORIGINAL_FEED_CUMULATIVE':
        if numerator.get('denominator') and numerator.get('denominator')==denominator.get('denominator'):return a/b
    if mode=='SERIAL_STAGE_FEEDS':
        if (numerator.get('from') and numerator.get('from')==denominator.get('to')
            and numerator.get('basis') and numerator.get('basis')==denominator.get('basis')
            and numerator.get('process_id') and numerator.get('process_id')==denominator.get('process_id')):return a*b/100
    return None


def analyze_cells(selection,definition,db,run_id,out,resource_project_ids=()):
    """Use selected observations, with raw transcript and permitted use separated."""
    from .analysis import write_csv
    rows=[]
    for c in selection['inventory']:
        raw=c['raw']
        if raw.get('kind')!='TECHNICAL_TABLE_CELL':continue
        r=dict(raw,evidence_id=c['evidence_id'],project_id=c['project_id'],source_sha256=c['source_sha256'],
               value=c['value'],variable=c['variable'],study_date=c['effective_date'],evidence_reason=c['reason'],
               case_id=raw['case_id'],sample_population=raw.get('sample_population'))
        uses=[];reasons={}
        for name,contract in definition['contracts'].items():
            failures=technical_compare(r,contract,contract.get('model_assumptions',[]))
            reasons[name]=failures
            if not failures:uses.append(name)
        r.update(allowed_analysis=uses or ['SOURCE_TRANSCRIPT_ONLY'],contract_reasons=reasons,
                 selection_reason=c['reason'],transcription_status='TOKEN_BOUND',analysis_version=definition['version'])
        rows.append(r)
    profiles=[]
    for pid in sorted({r['project_id'] for r in selection.get('technical_comparability',[])}):
        rr=[r for r in selection['technical_comparability'] if r['project_id']==pid]
        performance=[r for r in rr if r['semantic_class']=='B_PROCESS_PERFORMANCE' and not r['evidence_reason'] and r['value'] is not None]
        cells_for_project=[r for r in rows if r['project_id']==pid]
        profiles.append(dict(project_id=pid,resource_defined=pid in resource_project_ids,raw_technical_records=len(rr),scoped_performance_observations=len(performance),historical_contract_comparable=sum(r['comparability_status']=='NUMERIC_COMPARABLE' for r in rr),source_cell_observations=len(cells_for_project),case_analysis_observations=sum(r['allowed_analysis']!=['SOURCE_TRANSCRIPT_ONLY'] for r in cells_for_project),case_ids=sorted({r['case_id'] for r in performance}),limits='SCOPE_SPECIFIC_NOT_PROJECT_AVERAGE; quality/maturity not a technical score'))
    write_csv(Path(out)/'technical_scope_profiles.csv',csvrows_local(profiles),['project_id','resource_defined','raw_technical_records','scoped_performance_observations','historical_contract_comparable','source_cell_observations','case_analysis_observations','case_ids','limits'])
    rows.sort(key=lambda r:(r['source_sha256'],r['physical_page'],r['table_index'],r['row_index'],r['column_index']))
    derived=[];plots=[];conflicts=[]
    def emit(name,value,unit,inputs,**labels):
        item=dict(variable=name,value=value,unit=unit,project_id=inputs[0]['project_id'],
                  source_sha256=inputs[0]['source_sha256'],table_scope_id=inputs[0]['table_scope_id'],
                  evidence_ids=[x['evidence_id'] for x in inputs],version=definition['version'],**labels)
        item['derived_id']=digest(item);derived.append(item)
        db.execute('INSERT OR REPLACE INTO derived VALUES(?,?,?,?,?)',(run_id,item['project_id'],name+'_'+item['derived_id'][:20],value,canonical(item)))
    groups=defaultdict(list)
    for r in rows:groups[r['table_scope_id']].append(r)
    for key,group in groups.items():plots.extend(_derive_table(key,group,emit))
    flows=flow_consistency(rows)
    write_csv(Path(out)/'technical_flow_consistency.csv',csvrows_local(flows),['source_sha256','project_id','basis','fraction_scope','path','stage_evidence_ids','reported_evidence_id','calculated_pct','calculated_lower_pct','calculated_upper_pct','reported_pct','reported_lower_pct','reported_upper_pct','rounding_consistent','endpoint_interpretation','limit'])
    for c in selection['inventory']:
        if not c['variable'].startswith('reported_technical_treo_upgrade_ratio_'):continue
        for claim in c['raw'].get('reported_ratios',[]):
            comparable=[d for d in derived if d['variable']=='treo_enrichment_ratio' and d['source_sha256']==c['source_sha256'] and d.get('test_id')==claim['test_id'] and '2nd Cleaner' in d.get('product','')]
            if len(comparable)==1 and abs(comparable[0]['value']-claim['value'])>.05:
                conflicts.append(dict(source_sha256=c['source_sha256'],type='UPGRADE_RATIO_DENOMINATOR_OR_SCOPE_UNRESOLVED',reported=claim['value'],calculated=comparable[0]['value'],evidence_id=c['evidence_id'],derived_id=comparable[0]['derived_id'],effect='Retain product/feed ratio; narrative multiple not reconciled, no forced correction'))
    write_csv(Path(out)/'technical_conflicts.csv',conflicts,['source_sha256','type','reported','calculated','evidence_id','derived_id','effect'])
    # Nominal dominance only at exactly the same product stage and composite.
    for r in plots:
        peers=[p for p in plots if p['sample']==r['sample'] and p['source_sha256']==r['source_sha256'] and p['product']==r['product']]
        r['nominally_dominated_by']=','.join(p['test_id'] for p in peers if p['grade_pct']>=r['grade_pct'] and p['recovery_pct']>=r['recovery_pct'] and (p['grade_pct']>r['grade_pct'] or p['recovery_pct']>r['recovery_pct']))
        r['uncertainty']='NOT_QUANTIFIED_NO_SIGNIFICANCE_CLAIM'
    fields=['evidence_id','project_id','source_sha256','source_key','physical_page','table_index','table_caption','row_index','column_index','bbox','header_path','original_token','value','bounds','token_state','quantity','basis','unit','scope','case_id','table_scope_id','sample_id','sample_binding','representativeness','representativeness_evidence','test_id','product','stage','source_column','grain_mm','acid_concentration','acid_unit','reagent','feed','endpoint','scale','from_material','to_material','fraction_scope','process_stage','raw_equation','evidence_mode','statistic','limitations','selection_reason','transcription_status','allowed_analysis','contract_reasons','analysis_version']
    def csvrows(items):return [{k:canonical(v) if isinstance(v,(dict,list)) else v for k,v in r.items()} for r in items]
    write_csv(Path(out)/'technical_cells.csv',csvrows(rows),fields)
    df=['derived_id','variable','value','unit','project_id','source_sha256','table_scope_id','evidence_ids','version','formula','interpretation','stage','reagent','test_id','product','element','grain_mm','sample']
    write_csv(Path(out)/'technical_derived.csv',csvrows(derived),df)
    write_csv(Path(out)/'technical_grade_recovery.csv',plots,['test_id','product','grade_pct','recovery_pct','sample','source_sha256','grade_evidence','recovery_evidence','nominally_dominated_by','uncertainty'])
    summary=dict(version=definition['version'],source_documents=len({r['source_sha256'] for r in rows}),source_cells=len(rows),
                 valid_numeric_cells=sum(not r['selection_reason'] and r['value'] is not None for r in rows),
                 projects=len({r['project_id'] for r in rows}),table_scopes=len(groups),
                 eligible_by_use={k:sum(k in r['allowed_analysis'] for r in rows) for k in definition['contracts']},
                 quantities=dict(Counter(r['quantity'] for r in rows)),feed_reference_cells=sum(r['statistic']=='FEED_REFERENCE' for r in rows),population_assertion_cells=sum(bool(r.get('representativeness_evidence')) for r in rows),derived=dict(Counter(r['variable'] for r in derived)),
                 formal_criteria_policy='UNCHANGED_NOT_PROMOTED_BY_CASE_ANALYSIS',flow_checks=len(flows),source_conflicts=len(conflicts),scoped_performance_projects=sum(p['scoped_performance_observations']>0 for p in profiles),resource_scoped_performance_projects=sum(p['resource_defined'] and p['scoped_performance_observations']>0 for p in profiles),
                 limits=['SOURCE_CELLS_NOT_INDEPENDENT_REPLICATES','SAMPLE_COMPARISON_NOT_PROJECT_PERFORMANCE','NO_COMMON_PERFORMANCE_BURDEN_SCORE','NO_2023_2026_PROCESS_JOIN'])
    (Path(out)/'technical_analysis.json').write_text(canonical(summary)+'\n',encoding='utf-8')
    return summary

def plot_cells(root,out,rscript=None):
    """Base R plots reuse the installed research runtime, with editable CSV inputs."""
    import shutil,subprocess
    executable=rscript or shutil.which('Rscript')
    if not executable:raise RuntimeError('Rscript required for technical figures')
    result=subprocess.run([str(executable),str(Path(root)/'R/technical_plots.R'),str(out)],capture_output=True,text=True,timeout=60)
    (Path(out)/'technical_plots.log').write_text(result.stdout+'\n'+result.stderr,encoding='utf-8')
    if result.returncode:raise RuntimeError('Technical plotting failed: '+result.stderr[-1200:])

def csvrows_local(items):
    return [{k:canonical(v) if isinstance(v,(dict,list)) else v for k,v in r.items()} for r in items]


def rounding_interval(token):
    value=float(token.replace(',',''));digits=len(token.split('.')[1]) if '.' in token else 0
    half=.5*10**(-digits)
    return value-half,value+half


def flow_consistency(rows):
    """Match From/To edges, oxide and fraction scope; never multiply branches."""
    output=[];groups=defaultdict(list)
    for r in rows:
        if r['quantity']=='stage_recovery_pct' and not r['selection_reason'] and r['value'] is not None:
            groups[(r['source_sha256'],r['basis'],r.get('fraction_scope'))].append(r)
    for (sha,basis,fraction),rr in groups.items():
        overall=[r for r in rr if 'Overall' in r.get('process_stage','')]
        edges=[r for r in rr if 'Overall' not in r.get('process_stage','')]
        if len(overall)!=1:continue
        report=overall[0]
        # Follow printed material identities; cycles and multiple paths remain explicit.
        paths=[]
        def visit(material,path):
            following=[r for r in edges if r['from_material']==material and r not in path]
            if not following and path:paths.append(path);return
            for edge in following:
                if len(path)<len(edges):visit(edge['to_material'],path+[edge])
        visit(report['from_material'],[])
        for path in paths:
            if len(path)<2:continue
            value=math.prod(r['value']/100 for r in path)*100
            intervals=[rounding_interval(r['original_token']) for r in path]
            lower=math.prod(v[0]/100 for v in intervals)*100;upper=math.prod(v[1]/100 for v in intervals)*100
            rlo,rhi=rounding_interval(report['original_token'])
            output.append(dict(source_sha256=sha,project_id=report['project_id'],basis=basis,fraction_scope=fraction,
                path=' -> '.join([path[0]['from_material']]+[p['to_material'] for p in path]),stage_evidence_ids=[p['evidence_id'] for p in path],reported_evidence_id=report['evidence_id'],
                calculated_pct=value,calculated_lower_pct=lower,calculated_upper_pct=upper,reported_pct=report['value'],reported_lower_pct=rlo,reported_upper_pct=rhi,
                rounding_consistent=lower<=rhi and upper>=rlo,endpoint_interpretation=path[-1]['to_material'],
                limit='Consistency diagnostic only: printed Overall heading and combined HMC / REEC destination are preserved; no TREO or project-average inference'))
    return output


def _derive_table(key,group,emit):
    """Scoped reagent, flotation and printed-condition calculations for one table."""
    plots=[]
    valid=[r for r in group if not r['selection_reason'] and r['value'] is not None]
    feeds=[r for r in valid if r['quantity']=='dry_feed_mtpa']
    for r in valid:
        if r['quantity']!='reagent_tpa' or 'DESIGN_DRY_FEED_REAGENT' not in r['allowed_analysis']:continue
        same=[f for f in feeds if f.get('stage')==r.get('stage') and f['value']>0]
        if len(same)==1:
            emit('reagent_intensity_kg_t_dry_feed',r['value']*1000/(same[0]['value']*1e6),'kg/t dry feed',[r,same[0]],
                 stage=r['stage'],reagent=r['reagent'],formula='reagent_tpa*1000/(dry_feed_mtpa*1000000)',
                 interpretation=('Source dated design; commercial formulation mass, active purity not established' if r.get('semantics_version') else 'Scoping design; commercial formulation mass, active purity not established'))
    flotation=[r for r in valid if (r['scale']=='LAB_FLOTATION' or r.get('semantics_version')=='technical-context-v1') and r['basis']=='TREO' and 'WITHIN_COMPOSITE_FLOTATION' in r['allowed_analysis'] and r.get('product') is not None]
    feed=[r for r in flotation if r['product']=='Feed' and r['quantity']=='grade_pct']
    for r in flotation:
        if r['product']=='Feed' or r['quantity']!='grade_pct':continue
        recoveries=[x for x in flotation if x.get('test_id')==r.get('test_id') and x['product']==r['product'] and x['quantity']=='recovery_pct']
        if len(recoveries)==1:
            plots.append(dict(test_id=r['test_id'],product=r['product'],grade_pct=r['value'],recovery_pct=recoveries[0]['value'],
                              sample=r['sample_id'],source_sha256=r['source_sha256'],grade_evidence=r['evidence_id'],recovery_evidence=recoveries[0]['evidence_id']))
        if len(feed)==1 and feed[0]['value']>0:
            emit('treo_enrichment_ratio',r['value']/feed[0]['value'],'ratio',[r,feed[0]],test_id=r['test_id'],product=r['product'],
                 formula='product_grade_pct/table_feed_grade_pct',interpretation='Selected composite only; same-table feed')
    recoveries=[r for r in flotation if r['quantity']=='recovery_pct' and r.get('test_id')]
    for r in recoveries:
        if not r['product'].lower().startswith('2nd cleaner'):continue
        rougher=[x for x in recoveries if x['test_id']==r['test_id'] and 'rougher' in x['product'].lower()]
        references=[x for x in flotation if x['product']=='Feed' and x['quantity']=='recovery_pct' and x['value']==100]
        # The table feed reference supports a CONDITIONAL cumulative denominator;
        # no assertion that all testwork in the report used this denominator.
        if len(rougher)==1 and len(references)==1:
            denominator='table_feed_'+key
            result=ratio(dict(value=r['value'],denominator=denominator),dict(value=rougher[0]['value'],denominator=denominator),'SAME_ORIGINAL_FEED_CUMULATIVE')
            if result is not None:emit('conditional_cleaner_retention',result,'ratio',[r,rougher[0],references[0]],test_id=r['test_id'],
                formula='cumulative_cleaner_recovery/cumulative_rougher_recovery',interpretation='Conditional on both recoveries being cumulative to the displayed feed; not an independent measurement')
    # Conditional contrasts of printed labels, only when grain groups are unique.
    leach=[r for r in valid if r['quantity']=='extraction_pct' and 'WITHIN_TABLE_ELEMENT_LEACH' in r['allowed_analysis']]
    byelement=defaultdict(list)
    for r in leach:byelement[r['basis']].append(r)
    for element,rr in byelement.items():
        bygrain=defaultdict(list)
        for r in rr:bygrain[r.get('grain_mm')].append(r)
        if any(len(g)!=2 for g in bygrain.values()):continue
        for grain,pair in bygrain.items():
            acid={r.get('acid_concentration') for r in pair}
            if len(acid)==2 and None not in acid:
                lo,hi=sorted(pair,key=lambda r:r['acid_concentration'])
                emit('printed_acid_contrast_pp',hi['value']-lo['value'],'percentage points',[hi,lo],element=element,grain_mm=grain,
                     sample=hi.get('sample_id'),formula='higher_printed_g_L - lower_printed_g_L',
                     interpretation='Conditional printed-label contrast only; narrative kg/t and table g/L are not reconciled; no causal or significance claim')
    return plots


def _burden_states_v1(text, definition):
    """Predeclared source-scope rules. Absence, maturity and geology are not scores."""
    import re
    result=[]
    for sentence in re.split(r'(?<=[.;])\s+|\n\s*\n',text):
        sentence=' '.join(sentence.split())
        for rule in definition['rules']:
            match=re.search(rule['pattern'],sentence,re.I)
            if not match:continue
            # Conservative negation/target isolation; do not interpret a disclosure
            # of absent data, or proposed future work, as an observed constraint.
            before=sentence[max(0,match.start()-35):match.start()]
            if re.search(r'\b(?:no|not|without|lack of)\b',before,re.I) or re.search(r'\b(?:will|may|could|potential|planned|not disclosed|no .{0,30}data)\b',sentence,re.I):continue
            result.append(dict(criterion=rule['criterion'],state=rule['state'],rule_id=rule['id'],quote=sentence,meaning=rule['meaning']))
    return sorted({canonical(r):r for r in result}.values(),key=canonical)


def _unified_observations_v1(selection, definition):
    """One view over Selection, including text, cells and study parameters.

    Technical interpretation, numerical comparability and Project extrapolation
    are separate decisions. A conservative analytical identity is not a claim
    that different publications are independent physical measurements.
    """
    records=[];policy=selection['policy']
    for c in selection['inventory']:
        if c.get('domain')!='Technical':continue
        r=technical_record(c,policy);raw=c['raw']
        kind=raw.get('kind') or c['origin']
        quote=raw.get('raw_text') or raw.get('process') or raw.get('technical_description') or ''
        bound=not r['evidence_reason'] and bool(r['source_sha256'] and r['locator'] and r['scope'] and r['study_date'])
        numeric=bound and isinstance(r['value'],(int,float)) and math.isfinite(r['value'])
        quantity=raw.get('quantity') or r['process_stage'] or c['variable']
        if raw.get('quantity_role'):
            quantity=raw['quantity_role']
            if any(word in quantity for word in ('RECOVERY','EXTRACTION')):r['semantic_class']='B_PROCESS_PERFORMANCE'
        uses=[];reasons={}
        # All representations pass through the same intended-use gate.
        for name,contract in policy.get('technical_analysis',{}).get('contracts',{}).items():
            rr=dict(r,**{k:v for k,v in raw.items() if k not in ('value','variable','unit','basis','project_id','case_id','evidence_reason')})
            failures=technical_compare(rr,contract,contract.get('model_assumptions',[]));reasons[name]=failures
            if not failures:uses.append(name)
        # Typed study roles also support within-source numerical profiles even
        # when they do not meet a cross-project recovery endpoint contract.
        profile_contract=dict(version='technical-use-v2',variables=[c['variable']],unit=r['unit'],basis=None,
            required_conditions=['feed','endpoint','basis'],analysis_scope='SOURCE_CASE',
            model_assumptions=['Dated source-case quantity, not observed operation or Project average'])
        profile_reasons=technical_compare(r,profile_contract,profile_contract['model_assumptions'])
        reasons['SOURCE_CASE_NUMERIC_PROFILE']=profile_reasons
        profile=not profile_reasons and r['semantic_class']=='B_PROCESS_PERFORMANCE'
        state_rows=_burden_states_v1(quote,definition) if bound else []
        missing=raw.get('token_state') in ('NOT_REPORTED','NOT_APPLICABLE')
        support=bound and not missing and (bool(quote) or numeric)
        identity=[r.get(k) for k in ('project_id','source_sha256','pdf_page','variable','basis','scope','case_id','value','unit')]
        identity+=[raw.get(k) for k in ('test_id','product','source_column','row_index','column_index')]
        r.update(observation_form=kind,quantity=quantity,raw_quote=quote,
            analytical_identity=digest(identity),supports_technical_interpretation=support,
            numeric_profile_eligible=profile,permitted_comparison_groups=uses,
            comparison_reasons=reasons,interpretations=state_rows,
            project_extrapolation=False,project_extrapolation_reason='TARGET_POPULATION_COVERAGE_NOT_VALIDATED',
            interpretation_reason=None if support else ('EXPLICIT_NOT_APPLICABLE' if raw.get('token_state')=='NOT_APPLICABLE' else 'MISSING_SOURCE_VALUE') if missing else r['evidence_reason'] or 'INSUFFICIENT_BOUND_CONTENT',
            token_state=raw.get('token_state'),
            semantic_evidence=raw.get('semantic_evidence'),semantic_conflicts=raw.get('semantic_conflicts',[]),
            scenario=raw.get('scenario'),scenario_evidence=raw.get('scenario_evidence'),
            base_case_applicable=raw.get('base_case_applicable'),rule_version=definition['version'])
        # Source-cell corroboration uses explicit curated row markers, not a
        # percentage coincidence or Project name. Preserve different scope/basis
        # statements even when they transcribe the same printed cell.
        r['source_cell_identity']=digest([r['source_sha256'],r['pdf_page'],raw.get('table_index'),raw.get('row_index'),raw.get('column_index')]) if kind=='TECHNICAL_TABLE_CELL' else None
        r['_markers']=raw.get('page_markers',[])
        r['_cell_labels']=[str(raw.get(k) or '') for k in ('test_id','product','original_token')]
        records.append(r)
    cells=[r for r in records if r['source_cell_identity']]
    for r in records:
        if r['source_cell_identity'] or len(r['_markers'])<3:continue
        hits=[t for t in cells if t['source_sha256']==r['source_sha256'] and t['pdf_page']==r['pdf_page'] and t['value']==r['value'] and t['unit']==r['unit']
              and all(any(marker.casefold()==label.casefold() or label.casefold().startswith(marker.casefold()) for label in t['_cell_labels']) for marker in r['_markers'])]
        if len(hits)==1:r['source_cell_identity']=hits[0]['source_cell_identity']
    for r in records:r.pop('_markers');r.pop('_cell_labels')
    # Exact analytical duplicates corroborate; retain every source evidence ID.
    groups=defaultdict(list)
    for r in records:groups[r['analytical_identity']].append(r)
    out=[]
    for group in groups.values():
        r=dict(sorted(group,key=canonical)[0]);r['evidence_ids']=sorted({x['evidence_id'] for x in group});r['corroborating_rows']=len(group)
        out.append(r)
    return sorted(out,key=lambda r:r['analytical_identity'])


def claim_purpose(text):
    """A conservative clause classifier, not an assertion of operating truth."""
    import re
    t=' '.join(text.split())
    if not t:return 'EMPTY'
    if re.search(r'\.{3,}\s*\d+|table of contents',t,re.I):return 'NAVIGATION_OR_HEADER'
    # Short nominal headings have no scientific predicate. Words such as
    # "removal" describe a topic, not an established treatment requirement.
    predicate=r'\b(?:is|are|was|were|requires?|required|uses?|used|consumed|measured|demonstrated|showed|confirmed|contains?|produced|achieved|exceeded|failed|reported|removed|reduced|designed|assumed|estimated|modelled)\b'
    if not re.search(predicate,t,re.I):return 'NAVIGATION_OR_HEADER'
    if re.search(r'\b(?:not disclosed|not reported|no .{0,35}(?:data|information)|not measured)\b',t,re.I):return 'ABSENCE_OF_DISCLOSURE'
    if re.search(r'\b(?:designed to|aims? to|objective|to validate|to optimise|to optimize|will evaluate|will test|planned|proposed test)\b',t,re.I):return 'PLAN_OR_TEST_OBJECTIVE'
    if re.search(r'\b(?:if|unless|conditional on|subject to)\b',t,re.I):return 'CONDITIONAL'
    if re.search(r'\b(?:assumed|design|model|estimated)\b',t,re.I) and re.search(r'\d',t):return 'DESIGN_MODEL'
    if re.search(r'\b(?:tests?|testwork|measured|observed|produced|achieved|confirmed|demonstrated|consumed|exceeded)\b',t,re.I):return 'TEST_RESULT_OR_DISCLOSURE'
    return 'PROCESS_DESCRIPTION'


def burden_states(text, definition):
    if definition.get('version')!='technical-profile-remediation-v2':return _burden_states_v1(text,definition)
    import re
    result=[]
    # Scope future/negation to clauses; an unrelated future sentence cannot
    # erase an established result. Decimal points are not sentence boundaries.
    clauses=re.split(r'(?<=[.;])\s+(?=[A-Za-z])|\n\s*\n|\s+but\s+',text)
    for clause in clauses:
        sentence=' '.join(clause.split());purpose=claim_purpose(sentence)
        if purpose in ('EMPTY','NAVIGATION_OR_HEADER','ABSENCE_OF_DISCLOSURE','PLAN_OR_TEST_OBJECTIVE'):continue
        if re.search(r'\bwill\b',sentence,re.I) and purpose!='DESIGN_MODEL':continue
        for rule in definition['rules']:
            match=re.search(rule['pattern'],sentence,re.I)
            if not match:continue
            lower=rule['state']=='SUPPORTED_LOWER_BURDEN'
            before=sentence[max(0,match.start()-40):match.start()]
            if not lower and re.search(r'\b(?:no|not|without|lack of)\b',before,re.I):continue
            if not lower and re.search(r'\b(?:no|not|without)\b.{0,25}(?:required|consum|remov|treatment)',sentence,re.I):continue
            if re.search(r'\b(?:lower|higher|less|more) than\b',sentence,re.I) and not re.search(r'\d',sentence):continue
            # A mention of acid consumption does not establish a high burden.
            # Explicit generic requirements may be recorded as process facts.
            if purpose=='PROCESS_DESCRIPTION' and not re.search(r'\b(?:requires?|required|used|uses?|is removed|are removed)\b',sentence,re.I):continue
            quantities=[dict(token=m.group(0),value=float(m.group(1)),unit=m.group(2)) for m in re.finditer(r'(\d+(?:\.\d+)?)\s*(kg/t|g/L|kWh/t|m3/t|%|ppm)',sentence,re.I)]
            material=re.search(r'\b(?:hydrochloric acid|sulphuric acid|sulfuric acid|acid|reagent|grinding|impurit(?:y|ies)|residue|tailings|thorium|uranium)\b',sentence,re.I)
            result.append(dict(criterion=rule['criterion'],state='CONDITIONAL_REQUIREMENT' if purpose=='CONDITIONAL' else rule['state'],rule_id=rule['id'],quote=sentence,meaning=rule['meaning'],
                evidence_nature=purpose,material=material.group(0) if material else None,quantities=quantities,
                requirement_existence='CONDITIONAL' if purpose=='CONDITIONAL' else 'SUPPORTED_AT_QUOTED_SCOPE',
                intensity_order='NOT_ESTABLISHED',missing_conditions=['NO_COMMON_INTENSITY_UTILITY'],allowed_use='NOMINAL_REQUIREMENT_ATTRIBUTE_NOT_ORDINAL_SCORE'))
    return sorted({canonical(r):r for r in result}.values(),key=canonical)


def target_applicability(record, raw):
    """Source-bound coverage evidence changes the result; signatures do not."""
    evidence=raw.get('representativeness_evidence') or {}
    target=raw.get('target_scope') or evidence.get('target_population') or record.get('scope')
    missing=[]
    for field in ('source_sha256','pdf_page','quote','sample_id','target_population','coverage_basis','qualification'):
        if not evidence.get(field):missing.append(field)
    if record.get('evidence_reason'):missing.append('VALID_SOURCE_OBSERVATION')
    if raw.get('semantic_conflicts') or evidence.get('conflict'):status='CONFLICT'
    elif not missing and evidence['source_sha256']==record['source_sha256'] and evidence['sample_id']==raw.get('sample_id') and evidence['target_population']==target and evidence['qualification']=='TARGET_POPULATION_VALIDATED':status='SUPPORTED_FOR_NAMED_TARGET'
    elif not missing:status='TARGET_OR_SOURCE_MISMATCH'
    else:status='NOT_ESTABLISHED'
    return dict(version='target-applicability-v2',target_scope=target,target_scope_kind=raw.get('target_scope_kind','SOURCE_CASE'),
        status=status,reason='BOUND_TARGET_COVERAGE' if status=='SUPPORTED_FOR_NAMED_TARGET' else status+':'+','.join(missing),
        evidence=evidence or None,evidence_mode=record.get('evidence_mode'),project_extrapolation=status=='SUPPORTED_FOR_NAMED_TARGET' and raw.get('target_scope_kind')=='PROJECT')


def framework_fields(row, definition):
    """Classify a final shared observation; never grant scoring or extrapolation.

    Quantity roles come from policy, not project names or percentage tokens.
    Feed assays, mineral deportment, study maturity and throughput stay context.
    """
    framework=definition.get('framework')
    if not framework:return {}
    roles={row.get('quantity'),row.get('process_stage')}
    axes={axis for axis,allowed in framework['roles'].items() if roles.intersection(allowed)}
    supported=row.get('supports_technical_interpretation') and not row.get('evidence_reason')
    value=row.get('value');numeric=isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value)
    # A recovery number in a paragraph mentioning acid is not an acid amount.
    # Text requirements may inform several axes; numeric quantities may not.
    if supported and not numeric:
        axes.update(framework['interpretation_axes'][j['criterion']] for j in row.get('interpretations',[])
                    if j.get('criterion') in framework['interpretation_axes'])
    missing=[key for key in framework['context_fields'] if row.get(key) in (None,'')]
    conflict=row.get('measurement_relation')=='CONFLICTING_VALUES_SAME_SCIENTIFIC_OBSERVATION'
    # The legacy performance flag excludes non-performance roles such as
    # input intensity. Reuse its source-context contract, not that taxonomy.
    source_numeric=row.get('numeric_profile_eligible') or row.get('comparison_reasons',{}).get('SOURCE_CASE_NUMERIC_PROFILE')==[]
    if not axes:status='CONTEXT_ONLY'
    elif numeric and len(axes)>1:status='CONFLICT'
    elif conflict:status='CONFLICT'
    elif not supported:status='UNSUPPORTED'
    elif numeric and source_numeric:status='SOURCE_SCOPED_NUMERIC'
    elif numeric:status='NUMERIC_CONTEXT_INCOMPLETE'
    else:status='SOURCE_SCOPED_DESCRIPTION'
    return dict(technical_axes=sorted(axes),technical_use=status,technical_missing_context=missing,
                technical_framework_version=framework['version'])


def unified_observations(selection, definition):
    if definition.get('version')!='technical-profile-remediation-v2':return _unified_observations_v1(selection,definition)
    import re
    records=[];policy=selection['policy']
    # Process one input at a time: legacy dedup cannot erase semantic differences
    # before the corrected identity has a chance to inspect them.
    for c in selection['inventory']:
        if c.get('domain')!='Technical':continue
        row=_unified_observations_v1(dict(selection,inventory=[c]),definition)[0];raw=c['raw']
        row['legacy_analytical_identity']=row['analytical_identity']
        fields=('process_stage','sample_interval','reagent','temperature_c','residence_hours','acid_concentration','pressure','scenario','statistic')
        for k in fields:
            if k in raw:row[k]=raw[k]
        row['date_role']=raw.get('date_role') or raw.get('effective_date_role') or 'DISCLOSURE_OR_CASE_EFFECTIVE_DATE_NOT_TEST_DATE'
        row['sample_id']=raw.get('sample_id');row['test_id']=raw.get('test_id');row['material_branch']=raw.get('fraction_scope') or raw.get('product')
        for k in ('acid_unit','reagent_formulation','liquid_solid_ratio','stage','from_material','to_material'):
            row[k]=raw.get(k)
        row['conditions']=raw.get('conditions');row['population']=raw.get('target_population') or row.get('sample_population')
        row['source_record_identity']=c['evidence_id']
        # Without an explicit cross-document measurement ID, preserve source
        # version, locator and test anchor; equal values alone prove nothing.
        measurement=raw.get('measurement_identity_evidence',{})
        cross=bool(measurement.get('measurement_id') and measurement.get('quote') and measurement.get('source_sha256')==row['source_sha256'] and measurement.get('pdf_page'))
        anchor=measurement['measurement_id'] if cross else [row['source_sha256'],row['pdf_page'],row['locator'],raw.get('table_index'),raw.get('row_index'),raw.get('column_index')]
        semantics=('project_id','case_id','variable','quantity','basis','scope','feed','endpoint','scale','process_stage','sample_population','sample_id','test_id','sample_interval','study_date','date_role','statistic','scenario','material_branch','reagent','temperature_c','residence_hours','acid_concentration','pressure','conditions','population','base_case_applicable','acid_unit','reagent_formulation','liquid_solid_ratio','stage','from_material','to_material')
        unit=' '.join((row.get('unit') or '').split()) or None
        unit={'percent':'%','pct':'%'}.get(unit,unit);row['normalized_unit']=unit
        row['scientific_observation_identity']=digest([anchor,[(k,row.get(k)) for k in semantics],unit])
        row['analytical_identity']=digest(['technical-identity-v2',row['scientific_observation_identity'],row['value'],row['observation_form'],row['raw_quote'],row.get('token_state')])
        row['identity_version']='technical-identity-v2';row['dedup_reason']='EXACT_SCIENTIFIC_SEMANTICS_AND_REPRESENTATION_ONLY'
        row['cross_document_relation']='EXPLICIT_MEASUREMENT_LINK' if cross else 'NO_INDEPENDENT_EQUIVALENCE_EVIDENCE'
        row['claim_purpose']=claim_purpose(row['raw_quote'])
        row['interpretations']=burden_states(row['raw_quote'],definition) if not row['evidence_reason'] else []
        if not row['evidence_reason'] and raw.get('kind')=='SOURCE_BOUND_SCIENTIFIC_CLAIM':
            for judgment in raw.get('reviewed_interpretations',[]):
                row['interpretations'].append(dict(judgment,quote=row['raw_quote'],origin='AI_ASSISTED_ORIGINAL_PAGE_REVIEW_NOT_EXPERT',evidence_nature=raw.get('evidence_mode'),intensity_order='NOT_ESTABLISHED',allowed_use='NOMINAL_SOURCE_CLAIM_ONLY'))
        if row['observation_form']!='TECHNICAL_TABLE_CELL' and row['claim_purpose'] in ('NAVIGATION_OR_HEADER','PLAN_OR_TEST_OBJECTIVE','ABSENCE_OF_DISCLOSURE','EMPTY') and row['value'] is None:
            row.update(supports_technical_interpretation=False,interpretation_reason=row['claim_purpose'])
        applicability=target_applicability(row,raw);row['target_applicability']=applicability
        row['project_extrapolation']=applicability['project_extrapolation'];row['project_extrapolation_reason']=applicability['reason']
        records.append(row)
    grouped=defaultdict(list);scientific=defaultdict(list)
    for r in records:grouped[r['analytical_identity']].append(r);scientific[r['scientific_observation_identity']].append(r)
    out=[]
    for group in grouped.values():
        r=dict(sorted(group,key=canonical)[0]);r['evidence_ids']=sorted({x['evidence_id'] for x in group});r['corroborating_rows']=len(group)
        r['source_record_identities']=sorted({x['source_record_identity'] for x in group})
        r['source_records']=[dict(evidence_id=x['evidence_id'],source_sha256=x['source_sha256'],pdf_page=x['pdf_page'],locator=x['locator'],unit=x['unit'],value=x['value']) for x in sorted(group,key=canonical)]
        r['source_locators']=sorted({canonical([x['source_sha256'],x['pdf_page'],x['locator']]) for x in group})
        peers=scientific[r['scientific_observation_identity']]
        conflict=len({canonical(x['value']) for x in peers if not x['evidence_reason'] and x['value'] is not None})>1
        r['measurement_relation']='CONFLICTING_VALUES_SAME_SCIENTIFIC_OBSERVATION' if conflict else 'CORROBORATING_RECORDS' if len(group)>1 else 'SINGLE_RECORD_INDEPENDENCE_UNKNOWN'
        r['related_analytical_ids']=sorted({x['analytical_identity'] for x in peers})
        if conflict:r.update(numeric_profile_eligible=False,interpretation_reason='CONFLICTING_VALUES_NOT_INDEPENDENT_EXPERIMENTS')
        out.append(r)
    return sorted(out,key=lambda r:r['analytical_identity'])


def analyze_profiles(selection, definition, out, resource_ids, root=None, snapshots=(), observations=None, claims_data=None):
    """Executed model decision: existing partial MCDA + technical case profiles.

    No universal ordinal utility is established. Therefore no numeric mapping,
    new weight, imputed unknown, or maturity-based Technical rank is generated.
    """
    from .analysis import write_csv
    out=Path(out);rows=unified_observations(selection,definition) if observations is None else observations
    for r in rows:r.update(framework_fields(r,definition))
    if definition.get('version')=='technical-profile-remediation-v2':
        # Explicit same-page curated cell markers corroborate source records,
        # independently of scientific measurement identity or value conflicts.
        links={e:r['source_cell_identity'] for r in _unified_observations_v1(selection,definition) if r['source_cell_identity'] for e in r['evidence_ids']}
        for r in rows:
            targets={links[e] for e in r['evidence_ids'] if e in links}
            if not r['source_cell_identity'] and len(targets)==1:r['source_cell_identity']=next(iter(targets))
    fields=['analytical_identity','source_cell_identity','project_id','case_id','evidence_ids','source_sha256','pdf_page','locator','study_date','observation_form','variable','quantity','value','unit','basis','feed','endpoint','scale','scope','sample_population','statistic','raw_quote','token_state','supports_technical_interpretation','interpretation_reason','numeric_profile_eligible','permitted_comparison_groups','comparison_reasons','interpretations','project_extrapolation','project_extrapolation_reason','semantic_evidence','semantic_conflicts','scenario','scenario_evidence','base_case_applicable','corroborating_rows','rule_version']
    if definition.get('version')=='technical-profile-remediation-v2':fields+=['legacy_analytical_identity','source_record_identities','source_records','scientific_observation_identity','identity_version','dedup_reason','cross_document_relation','source_locators','date_role','process_stage','sample_id','test_id','sample_interval','material_branch','reagent','temperature_c','residence_hours','acid_concentration','pressure','conditions','population','acid_unit','reagent_formulation','liquid_solid_ratio','stage','from_material','to_material','measurement_relation','related_analytical_ids','claim_purpose','target_applicability']
    if definition.get('framework'):fields+=['technical_axes','technical_use','technical_missing_context','technical_framework_version']
    write_csv(out/'technical_observations.csv',csvrows_local(rows),fields)
    profiles=[];judgments=[];groups=defaultdict(list)
    pids=sorted(selection['projects'])
    for pid in pids:
        rr=[r for r in rows if r['project_id']==pid]
        for criterion in ('T-A','T-B'):
            matches=[dict(j,project_id=pid,case_id=r['case_id'],analytical_identity=r['analytical_identity'],evidence_ids=r['evidence_ids'],source_sha256=r['source_sha256'],pdf_page=r['pdf_page'],locator=r['locator'],scope=r['scope'],rule_version=definition['version']) for r in rr for j in r['interpretations'] if j['criterion']==criterion]
            judgments.extend(matches);states=sorted({j['state'] for j in matches})
            profiles.append(dict(project_id=pid,criterion=criterion,resource_defined=pid in resource_ids,
                source_scoped_states=states or ['UNKNOWN'],status='CONFLICT_OR_SCOPE_VARIATION' if len(states)>1 else 'SCOPED_EVIDENCE_ONLY' if states else 'UNKNOWN',
                scoped_interpretations=len(matches),evidence_ids=sorted({e for j in matches for e in j['evidence_ids']}),
                project_score=None,project_extrapolation=any(r['project_extrapolation'] for r in rr),rule_version=definition['version'],
                missing_reason='NO_BOUND_RULE_MATCH' if not matches else 'NO_CALIBRATED_COMMON_UTILITY_OR_TARGET_POPULATION_COVERAGE'))
        for r in rr:
            if not r['numeric_profile_eligible']:continue
            # Within-source design/sample groups, preserving date, feed and
            # endpoint. Differences in reagent/temperature remain burden/context.
            group=digest([pid,r['source_sha256'],r['case_id'],r['quantity'],r['basis'],r['unit'],r['feed'],r['endpoint'],r['scale']])[:20]
            groups[group].append(r)
    group_rows=[dict(group_id=g,project_ids=sorted({r['project_id'] for r in rr}),case_ids=sorted({r['case_id'] for r in rr}),quantity=rr[0]['quantity'],basis=rr[0]['basis'],unit=rr[0]['unit'],feed=rr[0]['feed'],endpoint=rr[0]['endpoint'],scale=rr[0]['scale'],source_sha256=rr[0]['source_sha256'],values=[r['value'] for r in rr],evidence_ids=sorted({e for r in rr for e in r['evidence_ids']}),analysis_scope='SOURCE_CASE_PROFILE_NOT_CROSS_PROJECT_ORDER',uncertainty='NOT_QUANTIFIED_NO_INVENTED_ERROR') for g,rr in sorted(groups.items())]
    write_csv(out/'technical_project_profiles.csv',csvrows_local(profiles),['project_id','criterion','resource_defined','source_scoped_states','status','scoped_interpretations','evidence_ids','project_score','project_extrapolation','rule_version','missing_reason'])
    burden_fields=['project_id','criterion','state','rule_id','case_id','analytical_identity','source_sha256','pdf_page','locator','scope','quote','meaning','evidence_ids','rule_version']
    if definition.get('version')=='technical-profile-remediation-v2':burden_fields+=['origin','evidence_nature','material','quantities','requirement_existence','intensity_order','missing_conditions','allowed_use']
    write_csv(out/'technical_burden_evidence.csv',csvrows_local(judgments),burden_fields)
    write_csv(out/'technical_comparison_groups.csv',csvrows_local(group_rows),['group_id','project_ids','case_ids','quantity','basis','unit','feed','endpoint','scale','source_sha256','values','evidence_ids','analysis_scope','uncertainty'])
    summary=dict(version=definition['version'],decision=definition['decision'],common_score_adopted=False,
        ordinal_mapping=None,technical_weight_change=0,formal_eligibility_change=False,
        source_rows=sum(r['corroborating_rows'] for r in rows),analytical_records=len(rows),
        distinct_transcribed_source_cells=len({r['source_cell_identity'] for r in rows if r['source_cell_identity']}),
        linked_cell_corroborations=sum(bool(r['source_cell_identity']) and r['observation_form']!='TECHNICAL_TABLE_CELL' for r in rows),
        independent_physical_measurements=None,measurement_count_reason='Reports do not establish independent replicate identities; source-cell groups and analytical records reported separately',
        observation_forms=dict(Counter(r['observation_form'] for r in rows)),
        technically_interpretable=sum(r['supports_technical_interpretation'] for r in rows),
        source_scoped_numeric=sum(r['numeric_profile_eligible'] for r in rows),
        projects_with_source_scoped_numeric=len({r['project_id'] for r in rows if r['numeric_profile_eligible']}),
        resource_projects_with_source_scoped_numeric=len({r['project_id'] for r in rows if r['numeric_profile_eligible']} & set(resource_ids)),
        source_scoped_criterion_projects={c:sum(p['criterion']==c and p['scoped_interpretations']>0 for p in profiles) for c in ('T-A','T-B')},
        comparable_case_groups=len(groups),project_extrapolatable=sum(r['project_extrapolation'] for r in rows),
        aim_a='Existing partial MCDA plus source-scoped T-A/T-B evidence and numerical groups; no six-domain rank',
        aim_b='No ordinal utility adopted: mapping/weight sensitivity is NOT_APPLICABLE; prior partial-MCDA Monte Carlo and method sensitivity rerun; no probability of success',
        aim_c='Mechanism-oriented source-case comparison; no deposit-label-derived score or causal inference',
        limitation='Analytical identity deduplicates records only, not independent experiments; different versions may corroborate. AI consistency is not independent expert validation.')
    if definition.get('version')=='technical-profile-remediation-v2':
        summary.update(scoped_numeric_model_adopted=True,aim_a='Executed process-specific design panel via existing R engine; nominal burdens kept separate',aim_b='Same two design cases: Technical total/subweight, scoring, method and operating-only scope scenarios',project_extrapolatable=sum(r['project_extrapolation'] for r in rows))
        if root is not None:summary['remediation']=export_remediation(selection,definition,rows,out,resource_ids,Path(root),snapshots,claims_data=claims_data)
    if definition.get('framework'):
        # One row per Project/axis reports evidence availability, never averages
        # incompatible cases or treats source records as independent experiments.
        framework=definition['framework'];coverage=[]
        for pid in pids:
            for axis in framework['axes']:
                rr=[r for r in rows if r['project_id']==pid and axis in r['technical_axes']]
                numeric=[r for r in rr if r['technical_use']=='SOURCE_SCOPED_NUMERIC']
                coverage.append(dict(project_id=pid,axis=axis,
                    status='SOURCE_SCOPED_NUMERIC' if numeric else 'SOURCE_SCOPED_DESCRIPTION' if any(r['technical_use']=='SOURCE_SCOPED_DESCRIPTION' for r in rr) else 'UNRESOLVED' if rr else 'UNKNOWN',
                    source_records=len(rr),numeric_records=len(numeric),
                    case_ids=sorted({r['case_id'] for r in rr}),
                    evidence_ids=sorted({e for r in rr for e in r['evidence_ids']}),
                    missing_context=sorted({key for r in rr for key in r['technical_missing_context']}),
                    project_score=None,score_status='NO_COMMON_UTILITY_ADOPTED',
                    framework_version=framework['version']))
        write_csv(out/'technical_framework_profiles.csv',csvrows_local(coverage),['project_id','axis','status','source_records','numeric_records','case_ids','evidence_ids','missing_context','project_score','score_status','framework_version'])
        summary['framework']=dict(version=framework['version'],axes=list(framework['axes']),
            projects=len(pids),profiles=len(coverage),project_scores_adopted=False,
            source_scoped_numeric_projects={axis:sum(r['axis']==axis and r['numeric_records']>0 for r in coverage) for axis in framework['axes']})
    if definition.get('jorc_screening') and not definition.get('disclosure_supersedes_screening'):
        summary['jorc_screening']=analyze_jorc_screening(selection,definition,rows,out,root,claims_data=claims_data)
    if definition.get('disclosure_supersedes_screening'):
        summary['current_T1_definition']='technical-disclosure-transparency-v1'
        summary['performance_profile_interpretation']='SUPPLEMENTARY_SOURCE_CONTENT_NOT_DISCLOSURE_SCORES'
    (out/'technical_model_decision.json').write_text(canonical(summary)+'\n',encoding='utf8')
    return summary


DISCLOSURE_VERSION = 'technical-disclosure-transparency-v1'
DISCLOSURE_STATES = {'DISCLOSED':1,'EXPLICIT_UNKNOWN':1,'INSUFFICIENT':0,'UNVERIFIABLE':None}
DISCLOSURE_FACETS = {
    'TD1': ('origin', 'sampling', 'preparation'),
    'TD2': ('route', 'selection_reason'),
    'TD3': ('element_basis', 'feed', 'endpoint', 'number_or_unknown', 'data_basis'),
    'TD4': ('reagents', 'energy', 'water'),
    'TD5': ('product', 'specification', 'impurities'),
    'TD6': ('scale', 'data_nature'),
    'TD7': ('population', 'coverage', 'limits'),
}


def disclosure_score(items):
    """Fixed seven binary items; a lower bound is never a known point score."""
    if set(items) != set(DISCLOSURE_FACETS):
        raise ValueError('Require exactly the seven versioned disclosure items')
    values = [DISCLOSURE_STATES[r['status']] for r in items.values()]
    n = sum(v == 1 for v in values); u = sum(v is None for v in values)
    return dict(confirmed_items=n, unknown_items=u, insufficient_items=7-n-u,
                confirmed_score=n/7*100, score_lower=n/7*100,
                score_upper=(n+u)/7*100, score=None if u else n/7*100,
                denominator=7, version=DISCLOSURE_VERSION)


def assess_disclosure(root, review, snapshots, cutoff):
    """Validate source-bound content coding, not keyword-derived adequacy.

    Human/agent content judgments live in the versioned review input. This
    function checks their explicit facets, scope, dates and original quotes.
    Any local provenance failure becomes unknown; it cannot become zero.
    """
    from .selection import source_check, date_end
    from .store import filehash
    root=Path(root);sources={s['key']:s for s in snapshots};pages={};errors={}
    if review['version'] != DISCLOSURE_VERSION or cutoff != review['cutoff']:
        raise ValueError('Disclosure review version/cutoff mismatch; recoding required')
    def normalized(text):return re.sub(r'\s+', ' ', text.replace('ﬁ','fi').replace('ﬂ','fl')).strip()
    class CitedPages:
        """Read only cited pages, after the original hash/date checks.

        Invocation-local caching cannot outlive validation or hide a changed
        original. Search completeness still comes from the bounded review.
        """
        def __init__(self, path, count):
            self.path=path;self.count=count;self.cache={}
        def __len__(self):return self.count
        def __getitem__(self, index):
            if index not in self.cache:
                import fitz
                with fitz.open(self.path) as pdf:
                    self.cache[index]=normalized(pdf[index].get_text())
            return self.cache[index]
    def document(key):
        if key not in pages and key not in errors:
            s=sources.get(key)
            try:
                problem=source_check(s,cutoff,root)
                if problem:raise ValueError(problem)
                if not s.get('publication_date') and not (s['kind']=='html' and s.get('available_date') and s.get('acquired_at')):
                    raise ValueError('UNDATED_SOURCE_NO_DATED_PUBLIC_ARCHIVE')
                if s['sha256']!=review['sources'][key]['sha256']:
                    raise ValueError('REVIEW_SOURCE_VERSION_MISMATCH')
                if s['kind']=='pdf':
                    import fitz
                    with fitz.open(root/s['path']) as pdf:
                        pages[key]=CitedPages(root/s['path'], len(pdf))
                elif s['kind']=='html':
                    from .evidence import html_text
                    pages[key]=[normalized(html_text(root,s))]
                else:raise ValueError('NOT_PRIMARY_DOCUMENT')
            except Exception as exc:errors[key]=str(exc)
        return pages.get(key,[])
    def cite(c,allowed):
        key=c.get('source_key');page=c.get('page');quote=normalized(c.get('quote',''))
        pp=document(key)
        if key not in allowed:raise ValueError('OUTSIDE_PROJECT_DOCUMENT_SCOPE')
        if not isinstance(page,int) or isinstance(page,bool) or not 1<=page<=len(pp):
            raise ValueError(errors.get(key,'INVALID_PAGE'))
        if len(quote)<16 or quote not in pp[page-1]:raise ValueError('QUOTE_NOT_IN_ORIGINAL_PAGE')
        return dict(c,source_sha256=sources[key]['sha256'],
                    publication_date=sources[key].get('publication_date'),url=sources[key]['url'],
                    available_date=sources[key].get('available_date'),
                    date_basis='PUBLISHED_DATE' if sources[key].get('publication_date') else 'PUBLIC_HTML_ARCHIVED_BEFORE_CUTOFF_PUBLICATION_DATE_UNKNOWN',
                    locator=('physical PDF page ' if sources[key]['kind']=='pdf' else 'HTML text block page ')+str(page))
    rows=[];scores=[];audits=[]
    for group in review['groups']:
        pid=group['project_id'];allowed={x['source_key'] for x in group['documents']}
        scope_errors=[];scope_proofs=[]
        for binding in group['documents']:
            try:
                if not binding.get('scope_reason'):raise ValueError('NO_EXPLICIT_SCOPE_REASON')
                scope_proofs.append(cite(binding['scope_evidence'],allowed))
            except Exception as exc:scope_errors.append(binding['source_key']+':'+str(exc))
        # Every audit records what was actually readable, not a claim of global
        # absence. Search hits are navigation; only reviewed facets can score.
        audit=dict(project_id=pid,project_name=group['name'],scope=group['scope'],
                   cutoff=cutoff,search_protocol=review['search_protocol'],
                   document_keys=sorted(allowed),scope_proofs=scope_proofs,
                   excluded_documents=group.get('excluded_documents',[]),
                   search_complete=group['search_complete'] and not scope_errors,
                   review_complete_items=group.get('review_complete_items',[]),
                   failures=scope_errors,stop_reason=group['stop_reason'],
                   conflicts_updates=group.get('conflicts_updates',[]))
        audit['search_navigation']=group.get('search',{})
        audits.append(audit);assessments={}
        for code,facets in DISCLOSURE_FACETS.items():
            assessment=group['items'].get(code,dict(status='UNVERIFIABLE',reason='CONTENT_REVIEW_NOT_COMPLETE'))
            state=assessment['status'];issues=[];proofs={}
            try:
                if scope_errors:raise ValueError('PROJECT_SOURCE_SCOPE_NOT_VALIDATED')
                if state in ('DISCLOSED','EXPLICIT_UNKNOWN'):
                    if set(assessment.get('facets',{}))!=set(facets):raise ValueError('MINIMUM_FACETS_NOT_MET')
                    explicit=False
                    for facet,value in assessment['facets'].items():
                        if len(value.get('interpretation','').strip())<20:raise ValueError('NO_CONTENT_JUDGMENT')
                        if not value.get('evidence'):raise ValueError('NO_FACET_EVIDENCE')
                        proofs[facet]=[cite(c,allowed) for c in value['evidence']]
                        if value.get('explicit_unknown'):
                            explicit=True
                            if len(value.get('unknown_reason','').strip())<20:raise ValueError('UNKNOWN_WITHOUT_SPECIFIC_REASON')
                    if (state=='EXPLICIT_UNKNOWN') != explicit:raise ValueError('EXPLICIT_UNKNOWN_STATE_MISMATCH')
                elif state=='INSUFFICIENT':
                    if not audit['search_complete'] or code not in audit['review_complete_items']:
                        raise ValueError('ZERO_REQUIRES_COMPLETED_BOUNDED_REVIEW')
                    if not assessment.get('missing_facets'):raise ValueError('ZERO_WITHOUT_SPECIFIC_MISSING_CONTENT')
                    if not set(assessment['missing_facets'])<=set(facets):raise ValueError('UNKNOWN_MINIMUM_FACET')
                    proofs['review_context']=[cite(c,allowed) for c in assessment.get('evidence',[])]
                    if not proofs['review_context']:raise ValueError('ZERO_WITHOUT_REVIEW_CONTEXT')
                elif state=='UNVERIFIABLE':
                    proofs['available_context']=[cite(c,allowed) for c in assessment.get('evidence',[])]
                else:raise ValueError('INVALID_DISCLOSURE_STATE')
                if not assessment.get('reason'):raise ValueError('NO_SCORING_REASON')
            except Exception as exc:issues.append(str(exc));state='UNVERIFIABLE'
            assessments[code]=dict(status=state)
            rows.append(dict(assessment_id='TD-'+digest([DISCLOSURE_VERSION,pid,group['scope'],code,state,assessment,proofs])[:24],
                project_id=pid,project_name=group['name'],scope=group['scope'],item=code,
                status=state,value=DISCLOSURE_STATES[state],
                reason=assessment.get('reason',''),missing_facets=assessment.get('missing_facets',[]),
                facet_interpretations=assessment.get('facets',{}),evidence=proofs,validation_issues=issues,
                conflicts_updates=group.get('conflicts_updates',[]),version=DISCLOSURE_VERSION,
                review_type='SOURCE_BOUND_AGENT_CONTENT_CODING_NOT_INDEPENDENT_DUAL_REVIEW'))
        scores.append(dict(project_id=pid,project_name=group['name'],scope=group['scope'],**disclosure_score(assessments)))
    if len({s['project_id'] for s in scores})!=len(scores):raise ValueError('Duplicate canonical group')
    return dict(items=rows,scores=scores,audits=audits,review_identity=digest(review))


def apply_disclosure(selection,result):
    """One criterion, new semantics: never retain an old recovery T1 value."""
    for pid,values in selection['values'].items():values.pop('T1',None)
    for s in result['scores']:
        if s['score'] is not None:
            selection['values'].setdefault(s['project_id'],{})['T1']=dict(
                value=s['score'],variable='technical_disclosure_pct',unit='%',
                basis=DISCLOSURE_VERSION,scope=s['scope'],raw=dict(s),
                evidence_ids=[r['assessment_id'] for r in result['items'] if r['project_id']==s['project_id']],
                review_identity=result['review_identity'],
                interpretation='TECHNICAL_DISCLOSURE_NOT_TECHNICAL_PERFORMANCE')
    return selection


def run_disclosure(root, config, cutoff, out, db=None, run_id=None, selection=None, assemble=None, registry=None, selected_snapshots=None):
    """Existing evidence store + versioned review + existing MCDA machinery."""
    from .analysis import write_csv,prepare_disclosure_analysis
    from .store import filehash
    if assemble is None:assemble=not config.get('disclosure_current_baseline')
    settings=config['evidence_resolution']['technical_disclosure']
    path=Path(root)/settings['review_path'];review=json.loads(path.read_text(encoding='utf8'))
    if settings.get('review_sha256') and filehash(path)!=settings['review_sha256']:
        raise ValueError('Frozen disclosure review checksum mismatch')
    if settings['denominator']!=7:raise ValueError('Disclosure denominator must remain seven')
    if settings['states']!=DISCLOSURE_STATES:raise ValueError('Disclosure state coding differs from versioned contract')
    if review.get('codebook_sha256')!=filehash(Path(root)/settings['codebook']):
        raise ValueError('Disclosure codebook checksum mismatch; recoding/versioning required')
    if not settings.get('incremental_registry') and set(g['project_id'] for g in review['groups'])!=set(review['baseline']['canonical_group_ids']):
        raise ValueError('Disclosure canonical cohort differs from frozen baseline')
    if settings.get('incremental_registry') and registry is not None:
        import copy
        review=copy.deepcopy(review)
        known={g['project_id'] for g in review['groups']}
        for p in registry:
            if p['entity_id'] in known:continue
            review['groups'].append(dict(project_id=p['entity_id'],name=p['name'],scope=p.get('scope',p['name']),
                documents=[],search_complete=False,review_complete_items=[],stop_reason='NEW_REGISTRY_SCOPE_REVIEW_NOT_COMPLETE',
                items={code:dict(status='UNVERIFIABLE',reason='New registered scope has no completed source-bound content review') for code in DISCLOSURE_FACETS}))
    active_sources=selected_snapshots if settings.get('incremental_registry') and selected_snapshots is not None else list(review['sources'].values())
    result=assess_disclosure(root,review,active_sources,cutoff)
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    for key,name in [('items','disclosure_items.csv'),('scores','disclosure_scores.csv'),('audits','disclosure_search_audit.csv')]:
        rows=csvrows_local(result[key]);write_csv(out/name,rows,list(rows[0]))
    prepared,summary=prepare_disclosure_analysis(result,review['baseline'],config,out) if assemble else (None,{})
    if selection is not None:apply_disclosure(selection,result)
    if db is not None:
        if run_id is None:raise ValueError('A run identity is required for persisted disclosure')
        for s in result['scores']:
            if not db.execute('SELECT 1 FROM entities WHERE entity_id=?',(s['project_id'],)).fetchone():
                raise ValueError('Unknown stable project group')
        for s in result['scores']:
            items=[r for r in result['items'] if r['project_id']==s['project_id']]
            for variable,value,provenance in [
                ('technical_disclosure_pct',s['score'],dict(score=s,items=items)),
                *[('technical_disclosure_'+r['item'],r['value'],r) for r in items]]:
                db.execute('INSERT OR REPLACE INTO derived VALUES(?,?,?,?,?)',
                    (run_id,s['project_id'],variable,value,canonical(provenance)))
    summary.update(review_sha256=filehash(path),states={state:sum(r['status']==state for r in result['items'])
        for state in ('DISCLOSED','EXPLICIT_UNKNOWN','INSUFFICIENT','UNVERIFIABLE')},
        validation_issue_items=sum(bool(r['validation_issues']) for r in result['items']),
        source_originals=len(review['sources']),cutoff=cutoff)
    if settings.get('incremental_registry'):
        summary['review_dependencies_sha256']=digest(dict(review=result['review_identity'],cutoff=cutoff,
            projects=registry,sources={s['key']:s['sha256'] for s in active_sources}))
    summary['status']='COMPLETED_WITH_VALIDATION_GAPS' if summary['validation_issue_items'] else 'COMPLETED_WITH_SOURCE_GAPS' if summary['states']['UNVERIFIABLE'] else 'COMPLETED_BOUNDED_REVIEW'
    (out/'disclosure_analysis.json').write_text(canonical(summary)+'\n',encoding='utf8')
    return result,prepared,summary


def screening_utility(row, panel, axis):
    """Explicit boundary/value-function contract, independent of maturity gates.

    Missing date, scale, sample count or statistic never veto a numerical
    observation. Invalid provenance, semantic conflicts and wrong physical
    quantities still cannot establish a utility. Return None means unknown,
    never exclusion of the project from MCDA.
    """
    contract=panel.get('criteria',{}).get(axis)
    if not contract:return None,'NO_COMMON_VALUE_FUNCTION'
    value=row.get('value')
    if (row.get('evidence_reason') or not row.get('supports_technical_interpretation')
            or row.get('semantic_conflicts') or row.get('measurement_relation')=='CONFLICTING_VALUES_SAME_SCIENTIFIC_OBSERVATION'):
        return None,'INVALID_OR_CONFLICTING_SOURCE'
    if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value):
        return None,'NO_FINITE_VALUE'
    if axis not in row.get('technical_axes',[]):return None,'DIFFERENT_QUANTITY_ROLE'
    if row.get('quantity') not in contract['quantities'] and row.get('process_stage') not in contract['quantities']:
        return None,'DIFFERENT_QUANTITY_ROLE'
    if row.get('basis') not in contract['bases']:return None,'DIFFERENT_OR_UNKNOWN_ELEMENT_BASIS'
    if row.get('endpoint') not in contract['endpoints']:return None,'DIFFERENT_OR_UNKNOWN_PROCESS_BOUNDARY'
    divisor=contract['unit_divisors'].get(row.get('normalized_unit') or row.get('unit'))
    if divisor is None:return None,'INCOMPATIBLE_UNIT'
    score=value/divisor
    if not 0<=score<=1:return None,'OUTSIDE_PHYSICAL_FRACTION'
    return score,'SOURCE_BOUNDARY_PROXY_NOT_PROJECT_ESTIMATE'


def analyze_jorc_screening(selection, definition, rows, out, root=None, claims_data=None):
    """JORC Table 1 evidence crosswalk + all-group interval screening.

    This is a research operationalisation, not a JORC compliance assessment.
    Source-case ranges condition on the listed boundary/oxide equivalence and
    on reported outcomes representing the screening alternatives. A separate
    project-transfer stress restores [0,1] where extrapolation is unproved.
    No midpoint, probability distribution, maturity bonus or case splicing.
    """
    from .analysis import write_csv, interval_mcda
    policy=definition['jorc_screening'];out=Path(out)
    pids=sorted(selection['projects']);names={pid:pid for pid in pids}
    if root is not None:
        from .pdf_extract import project_registry
        for item in project_registry(root,claims_data=claims_data):
            pid=selection['mapping'].get(item['entity_id'],item['entity_id'])
            if pid in names:names[pid]=item['name']
    byproject={pid:[r for r in rows if r['project_id']==pid] for pid in pids}
    crosswalk=[];maturity=[]
    for pid,rr in byproject.items():
        valid=[r for r in rr if not r.get('evidence_reason') and r.get('supports_technical_interpretation')]
        tests=sorted({r['scale'] for r in valid if r.get('scale') and r['scale'] not in policy['design_scales']})
        designs=sorted({r['scale'] for r in valid if r.get('scale') in policy['design_scales']})
        maturity.append(dict(project_id=pid,project_name=names[pid],test_scales=tests,design_scales=designs,
            sample_population_labels=sorted({r['sample_population'] for r in valid if r.get('sample_population')}),
            representative_project_observations=sum(bool(r.get('project_extrapolation')) for r in valid),
            missing_context=sorted({k for r in valid for k in policy['maturity_context'] if r.get(k) in (None,'')}),
            evidence_status='SCOPED_DISCLOSURE_PRESENT' if valid else 'NOT_ESTABLISHED_IN_SELECTED_EVIDENCE',
            maturity_score=None,performance_weight=0,
            interpretation='Nominal evidence attributes; no project-wide maturity or compliance inferred from a document label'))
        for code,item in policy['table1_items'].items():
            hits=[r for r in valid if (any(r.get(k) not in (None,'',[]) for k in item.get('fields',[]))
                  or any(a in r.get('technical_axes',[]) for a in item.get('axes',[])))]
            crosswalk.append(dict(project_id=pid,item=code,jorc_reference=item['reference'],topic=item['topic'],
                status='SCOPED_METADATA_OR_CLAIM_PRESENT' if hits else 'NOT_ESTABLISHED_IN_SELECTED_EVIDENCE',
                evidence_ids=sorted({e for r in hits for e in r['evidence_ids']}),
                analytical_ids=sorted({r['analytical_identity'] for r in hits}),
                interpretation='Evidence navigation only; neither JORC compliance nor adequacy is certified'))
    write_csv(out/'technical_evidence_maturity.csv',csvrows_local(maturity),list(maturity[0]))
    write_csv(out/'technical_jorc_table1.csv',csvrows_local(crosswalk),list(crosswalk[0]))
    matrices=[];trace=[];bounds=[];pairs=[];envelopes=[];coverage={}
    weight_vectors=list(policy['weight_scenarios'].items())
    # Enumerated simplex is a preference sensitivity grid, not a distribution.
    steps=policy['weight_grid_steps']
    grid=[('grid_'+str(i)+'_'+str(j),[i/steps,j/steps,(steps-i-j)/steps])
          for i in range(steps+1) for j in range(steps-i+1)]
    for panel_name,panel in policy['panels'].items():
        source={};supported=set()
        for pid,rr in byproject.items():
            for axis in policy['criteria_order']:
                accepted=[]
                for r in rr:
                    score,reason=screening_utility(r,panel,axis)
                    # Keep scored cells and relevant non-scoring quantities for
                    # audit; an excluded cell never excludes its project.
                    if axis in r.get('technical_axes',[]):
                        trace.append(dict(panel=panel_name,project_id=pid,criterion=axis,
                            analytical_identity=r['analytical_identity'],case_id=r['case_id'],
                            evidence_ids=r['evidence_ids'],source_sha256=r['source_sha256'],pdf_page=r.get('pdf_page'),
                            value=r.get('value'),unit=r.get('unit'),basis=r.get('basis'),feed=r.get('feed'),
                            endpoint=r.get('endpoint'),scale=r.get('scale'),statistic=r.get('statistic'),
                            admitted=score is not None,utility=score,reason=reason))
                    if score is not None:accepted.append((score,r))
                source[pid,axis]=accepted
                if accepted:supported.add(pid)
        coverage[panel_name]=len(supported)
        for transfer in ('REPORTED_CASE_PROXY','PROJECT_TRANSFER_STRESS'):
            for delta in policy['perturbation_percentage_points']:
                matrix=[];scenario_key=f'{panel_name}/{transfer}/plusminus_{delta}pp'
                for pid in pids:
                    cells=[]
                    for axis in policy['criteria_order']:
                        accepted=source[pid,axis]
                        if transfer=='PROJECT_TRANSFER_STRESS':
                            # Unbound cases cannot narrow project-target bounds.
                            # Even if some are bound, unbound cases are not
                            # silently treated as representative observations.
                            accepted=[v for v in accepted if v[1].get('project_extrapolation')]
                        values=[v for v,r in accepted]
                        lo=max(0,min(values)-delta/100) if values else 0.
                        hi=min(1,max(values)+delta/100) if values else 1.
                        cells.append((lo,hi))
                        matrices.append(dict(panel=panel_name,transfer=transfer,perturbation_pp=delta,
                            project_id=pid,project_name=names[pid],criterion=axis,utility_lower=lo,utility_upper=hi,
                            status='CONDITIONAL_REPORTED_OUTCOME_ENVELOPE' if values else 'UNKNOWN_FULL_UTILITY_DOMAIN',
                            case_ids=sorted({r['case_id'] for v,r in accepted}),
                            analytical_ids=sorted({r['analytical_identity'] for v,r in accepted}),
                            interpretation='Outer box, not a joint process estimate or confidence interval'))
                    matrix.append(cells)
                results=[]
                for weight_name,w in weight_vectors+grid:
                    methods=interval_mcda(matrix,w,policy['promethee_threshold'])
                    for method,rr in methods.items():
                        for pid,r in zip(pids,rr):
                            row=dict(panel=panel_name,transfer=transfer,perturbation_pp=delta,weight=weight_name,
                                     method=method,project_id=pid,project_name=names[pid],**r)
                            results.append(row)
                            if not weight_name.startswith('grid_'):bounds.append(row)
                        if not weight_name.startswith('grid_'):
                            for i,a in enumerate(rr):
                                for j,b in enumerate(rr):
                                    if i!=j and a['score_lower']>b['score_upper']+1e-12:
                                        pairs.append(dict(scenario=scenario_key,weight=weight_name,method=method,
                                                          ahead=pids[i],behind=pids[j],
                                                          interpretation='Sufficient robust order within stated scenario only'))
                for method in ('SAW','TOPSIS','PROMETHEE_II'):
                    for pid in pids:
                        rr=[r for r in results if r['project_id']==pid and r['method']==method]
                        envelopes.append(dict(panel=panel_name,transfer=transfer,perturbation_pp=delta,method=method,
                            project_id=pid,project_name=names[pid],rank_best=min(r['rank_best'] for r in rr),
                            rank_worst=max(r['rank_worst'] for r in rr),
                            preference_vectors=len(weight_vectors+grid),
                            interpretation='Outer rank range over enumerated preference grid; not a probability or exact attainable set'))
    for filename,items in [('technical_screening_matrix.csv',matrices),('technical_screening_trace.csv',trace),
                            ('technical_interval_ranking.csv',bounds),('technical_robust_pairs.csv',pairs),
                            ('technical_rank_envelopes.csv',envelopes)]:
        write_csv(out/filename,csvrows_local(items),list(items[0]) if items else ['scenario','weight','method','ahead','behind'])
    summary=dict(version=policy['version'],project_groups=len(pids),excluded_projects=0,
        axes=policy['criteria_order'],conditional_boundary_coverage=coverage,
        interval_ranking_rows=len(bounds),rank_envelope_rows=len(envelopes),robust_pair_rows=len(pairs),
        methods=['SAW','TOPSIS','PROMETHEE_II'],preference_vectors=len(weight_vectors+grid),
        maturity_in_performance=False,unknown_distribution=None,point_ranking_adopted=False,
        uncertainty='Outer possibility bounds + explicit source-transfer and percentage-point stress, not confidence intervals',
        policy=policy)
    (out/'technical_jorc_screening.json').write_text(canonical(summary)+'\n',encoding='utf8')
    return {k:v for k,v in summary.items() if k!='policy'}


def export_remediation(selection,definition,rows,out,resource_ids,root,snapshots,claims_data=None):
    """Use existing inventory for coverage, provenance bridge and model decisions."""
    import csv
    from .analysis import write_csv
    from .pdf_extract import project_registry
    from .store import filehash
    sources={s['sha256']:s for s in snapshots};byproject=defaultdict(list)
    for r in rows:byproject[r['project_id']].append(r)
    registry=project_registry(root,claims_data=claims_data);mapping=selection['mapping'];bykey={s['key']:s for s in snapshots}
    coverage=[]
    for pid in sorted(selection['projects']):
        rr=byproject[pid];members=[p for p in registry if mapping.get(p['entity_id'],p['entity_id'])==pid]
        originals={s['sha256']:s for r in rr if (s:=sources.get(r['source_sha256'])) and s['kind']=='pdf'}
        for p in members:
            if (s:=bykey.get(p['identity_source'])) and s['kind']=='pdf':originals[s['sha256']]=s
        original_state=[]
        for sha,source in sorted(originals.items()):
            valid=(root/source['path']).exists() and filehash(root/source['path'])==sha
            original_state.append(dict(sha256=sha,key=source['key'],sha_verified=valid,readable_source_observations=any(r['source_sha256']==sha and r['supports_technical_interpretation'] for r in rr)))
        selected=[r for r in rr if not r['evidence_reason']]
        numeric=[r for r in selected if isinstance(r['value'],(int,float))]
        fields=('feed','basis','endpoint','scale','study_date','scenario','statistic','sample_population')
        states=[]
        if not original_state:states.append('NO_PROJECT_BOUND_ORIGINAL_IN_THIS_SELECTION_NOT_PROOF_OF_EXTERNAL_ABSENCE')
        elif not rr:states.append('ORIGINAL_ACQUIRED_NO_SELECTED_TECHNICAL_OBSERVATION')
        if rr and not selected:states.append('PARSED_NOT_VALIDATED_OR_NOT_SELECTED')
        if selected and not numeric:states.append('TEXT_ONLY_NO_FINITE_NUMERIC')
        if any(r['measurement_relation'].startswith('CONFLICT') for r in rr):states.append('SOURCE_VALUE_CONFLICT')
        if selected and not any(r['numeric_profile_eligible'] for r in rr):states.append('NUMERIC_OR_SCOPE_INSUFFICIENT_FOR_PROFILE')
        if selected:states.append('VALID_SOURCE_OBSERVATIONS_SPECIFIC_CONTRACTS_STILL_REQUIRED')
        coverage.append(dict(project_id=pid,project_names=sorted({p['name'] for p in members}),resource_defined=pid in resource_ids,originals=original_state,technical_rows=len(rr),validated_rows=len(selected),numeric_records=len(numeric),numeric_profiles=sum(r['numeric_profile_eligible'] for r in rr),study_cases=sorted({r['case_id'] for r in rr if r['observation_form']=='STUDY_PARAMETER'}),field_coverage={k:sum(bool(r.get(k)) for r in rr) for k in fields},reagent_energy_water_residue_records=sum(bool(r.get('reagent')) or any(q in r['variable'].lower() for q in ('acid','reagent','energy','water','residue')) for r in rr),representative_targets=sum(r['target_applicability']['status']=='SUPPORTED_FOR_NAMED_TARGET' for r in rr),uncertainty='MEASUREMENT_ERROR_AND_REPLICATE_COUNTS_NOT_ESTABLISHED',states=states,exclusion_reasons=sorted({r['evidence_reason'] for r in rr if r['evidence_reason']}),comparison_failures=sorted({reason for r in rr for rr2 in r['comparison_reasons'].values() for reason in rr2})))
    write_csv(out/'technical_coverage_gaps.csv',csvrows_local(coverage),list(coverage[0]) if coverage else ['project_id'])
    bridge=[dict(old_analytical_identity=r['legacy_analytical_identity'],new_analytical_identity=r['analytical_identity'],scientific_observation_identity=r['scientific_observation_identity'],evidence_ids=r['evidence_ids'],relation=r['measurement_relation'],reason=r['dedup_reason']) for r in rows]
    write_csv(out/'technical_identity_bridge.csv',csvrows_local(bridge),list(bridge[0]) if bridge else ['old_analytical_identity'])
    # Every previously published rule hit receives a reproducible disposition.
    old=root/'results/phase16-2026-11-04/technical_burden_evidence.csv';audit=[]
    with old.open(encoding='utf8',newline='') as stream:
        for index,r in enumerate(csv.DictReader(stream),1):
            matches=burden_states(r['quote'],definition);purpose=claim_purpose(r['quote'])
            status='RETAIN_SCOPED_REQUIREMENT_NOT_INTENSITY_ORDER' if matches else 'DOWNGRADE_DISCOVERY_OR_PROCESS_CONTEXT'
            if purpose in ('PLAN_OR_TEST_OBJECTIVE','NAVIGATION_OR_HEADER'):status='REMOVE_ESTABLISHED_BURDEN_'+purpose
            audit.append(dict(prior_hit=index,prior_analytical_identity=r['analytical_identity'],project_id=r['project_id'],criterion=r['criterion'],source_sha256=r['source_sha256'],pdf_page=r['pdf_page'],locator=r['locator'],quote=r['quote'],purpose=purpose,disposition=status,new_claims=matches,source_selected=r['source_sha256'] in sources,reason='Clause purpose and explicit predicate checked; existence and intensity are distinct; structured case summaries are navigation/context unless backed by a direct reviewed claim',review_status='AI_ASSISTED_SOURCE_CONTEXT_CHECK_NOT_INDEPENDENT_EXPERT'))
    write_csv(out/'technical_burden_remediation.csv',csvrows_local(audit),list(audit[0]))
    inputs=[]
    # Existing derived reagent intensities retain table_scope/source chain.
    f=out/'technical_derived.csv'
    if f.exists():
        with f.open(encoding='utf8',newline='') as stream:
            for r in csv.DictReader(stream):
                if r['variable']=='reagent_intensity_kg_t_dry_feed':inputs.append(dict(project_id=r['project_id'],case_id=r['table_scope_id'],stage=r['stage'],value=float(r['value']),unit=r['unit'],reagent=r['reagent'],material_basis='COMMERCIAL_FORMULATION_PURITY_UNESTABLISHED',nature='DATED_DESIGN_MODEL',source_sha256=r['source_sha256'],evidence_ids=r['evidence_ids'],formula=r['formula'],decision='WITHIN_CASE_NOT_COMMON_ACTIVE_INGREDIENT_SCORE'))
    # Typed source case carries 24.8 kg/t formulation, not an invented feed assay.
    for c in selection['inventory']:
        if c['variable']!='acid_32pct_hcl_kg_per_t_feed' or c['reason']:continue
        inputs.append(dict(project_id=c['project_id'],case_id=c['case_id'],value=c['value'],unit=c['unit'],reagent='32% HCl source formulation',material_basis='SOURCE_32_PERCENT_HCL_FORMULATION_PER_LEACH_FEED',nature='SELECTED_COMPOSITE_DIAGNOSTIC_NOT_OPERATING',source_sha256=c['source_sha256'],evidence_ids=[c['evidence_id']],formula='Source case value; hypothetical active equivalent = q*0.32 only if concentration is mass fraction',conditional_active_kg_t=c['value']*.32,active_conversion_status='CONDITIONAL_MASS_FRACTION_ASSUMPTION_NOT_ADOPTED_MEASUREMENT',decision='WITHIN_CASE; feed moisture and net consumption balance not independently established'))
    write_csv(out/'technical_input_intensities.csv',csvrows_local(inputs),['project_id','case_id','value','unit','reagent','material_basis','nature','stage','source_sha256','evidence_ids','formula','conditional_active_kg_t','active_conversion_status','decision'])
    products=[]
    for c in selection['inventory']:
        raw=c['raw']
        if raw.get('kind')!='SOURCE_BOUND_SCIENTIFIC_CLAIM' or c['reason']:continue
        for claim in raw.get('reviewed_interpretations',[]):
            if claim['state']!='OBSERVED_SPECIFICATION_OBSTACLE':continue
            constraint=raw.get('product_constraint',{})
            peers=[x for x in selection['inventory'] if x['variable']==constraint.get('actual_variable') and x.get('case_id')==raw['case_id'] and x['source_sha256']==c['source_sha256'] and not x['reason']]
            values={x['value'] for x in peers};actual=next(iter(values)) if len(values)==1 else None
            limit=constraint.get('benchmark_value');unit=constraint.get('benchmark_unit')
            compatible=actual is not None and isinstance(limit,(int,float)) and limit>0 and all(x['unit']==unit for x in peers) and constraint.get('operator') in ('LESS_THAN','LESS_THAN_OR_EQUAL')
            diagnostic=actual/limit if compatible else None
            failed=(actual>=limit if constraint.get('operator')=='LESS_THAN' else actual>limit) if compatible else None
            status=('DOES_NOT_MEET_SINGLE_REPORTED_BENCHMARK' if failed else 'MEETS_SINGLE_REPORTED_BENCHMARK') if compatible else 'MISSING_OR_CONFLICTING_METRIC_OR_BENCHMARK'
            products.append(dict(project_id=c['project_id'],case_id=raw['case_id'],source_sha256=c['source_sha256'],pdf_page=c['pdf_page'],evidence_id=c['evidence_id'],metric_evidence_ids=[x['evidence_id'] for x in peers],quote=raw['raw_text'],product=constraint.get('product'),metric=constraint.get('actual_variable'),actual_value=actual,benchmark_value=limit,unit=unit,operator=constraint.get('operator'),diagnostic_c_over_L=diagnostic,status=status,benchmark_role=constraint.get('benchmark_role'),decision='SOURCE_DIAGNOSTIC_ONLY; typical reported benchmark is not a binding buyer specification; no common ordinal grade; full specification items not disclosed'))
    write_csv(out/'technical_product_constraints.csv',products,list(products[0]) if products else ['project_id','status'])
    # Functional unit cannot splice preferred45 extraction onto the four-blend.
    functional=[dict(project_id=c['project_id'],case_id=c['case_id'],source_sha256=c['source_sha256'],pdf_page=c['pdf_page'],candidate='kg reagent / kg recovered TREO in specified MREC',formula='q/(1000*g*R)',feed_grade_fraction=c['value']/1e6,reagent_kg_t=None,endpoint_recovery_fraction=None,functional_intensity=None,decision='NOT_CALCULABLE',missing=['Same-case reagent requirement','Same-case whole-feed-to-MREC recovery','Buyer product specification','Coproduct allocation and outsourced boundary'],prohibited_link='Other same-Project cases are not joined: q, grade and endpoint recovery must belong to this same feed and scenario') for c in selection['inventory'] if c['variable']=='feed_treo_ppm' and c.get('endpoint')=='MREC' and not c['reason']]
    write_csv(out/'technical_functional_unit_check.csv',csvrows_local(functional),['project_id','case_id','source_sha256','pdf_page','candidate','formula','feed_grade_fraction','reagent_kg_t','endpoint_recovery_fraction','functional_intensity','decision','missing','prohibited_link'])
    sensitivity=[];membership=[]
    for variant in ('fixed','sample_minmax'):
        folder=out/('technical_process_concentrate_'+variant)
        if (folder/'ranking.csv').exists():
            with (folder/'ranking.csv').open(encoding='utf8',newline='') as stream:ranks=list(csv.DictReader(stream))
            baseline={r['project_id']:r for r in ranks if r['scenario']=='technical_0_split_1'}
            for r in ranks:
                for method in ('saw','promethee','topsis'):
                    base=baseline[r['project_id']]
                    sensitivity.append(dict(normalization=variant,scenario=r['scenario'],project_id=r['project_id'],project_name=r['project_name'],method=method,score=float(r[method]),baseline_score=float(base[method]),score_change=float(r[method])-float(base[method]),rank=float(r[method+'_rank']),baseline_rank=float(base[method+'_rank']),rank_change=float(r[method+'_rank'])-float(base[method+'_rank']),cohort_change=False,data_change=False,interpretation='Fixed cases and background; explicit criterion/weight effect, not measurement significance or national rank'))
        if variant=='fixed' and (folder/'matrix.csv').exists():
            with (folder/'matrix.csv').open(encoding='utf8',newline='') as stream:matrix=list(csv.DictReader(stream))
            for r in matrix:
                if len(matrix)==2:membership.append(dict(retained_project=r['project_id'],removed_project=next(x['project_id'] for x in matrix if x['project_id']!=r['project_id']),n=1,TPR_fixed=r['TPR'],TPG_fixed=r['TPG'],local_minmax=None,rank=None,reason='Single retained case: physical fraction remains defined; sample minmax and cross-case ranking undefined, no midpoint imputation'))
    write_csv(out/'technical_definition_sensitivity.csv',sensitivity,['normalization','scenario','project_id','project_name','method','score','baseline_score','score_change','rank','baseline_rank','rank_change','cohort_change','data_change','interpretation'])
    write_csv(out/'technical_membership_sensitivity.csv',membership,['retained_project','removed_project','n','TPR_fixed','TPG_fixed','local_minmax','rank','reason'])
    decisions=dict(definition['numeric_model'],burden_ordinal_adopted=False,missing_never_zero=True)
    (out/'technical_analysis_decisions.json').write_text(canonical(decisions)+'\n',encoding='utf8')
    return dict(coverage_projects=len(coverage),resource_projects=sum(r['resource_defined'] for r in coverage),old_hits_dispositioned=len(audit),intensity_records=len(inputs),product_constraint_cases=len(products),functional_checks=len(functional))


# Integrated summary rules: reviewed functions, canonical evidence only.
from decimal import Decimal, InvalidOperation


def summary_select_first_full(stages):
    for stage in stages:
        if stage.get('annual_treo_t') is None:continue
        if stage.get('full_design_throughput') is True and stage.get('ramp_up') is False:return stage
        if stage.get('full_design_throughput') is None or (stage.get('full_design_throughput') is True and stage.get('ramp_up') is None):return None
    return None

def summary_annual_candidate(item, rules):
    """Validate an explicitly transcribed annual oxide value, never calculate one."""
    if item.get('source_stated') is not True or item.get('derivation'):
        raise ValueError('ANNUAL_SOURCE_STATED_REQUIRED')
    if item.get('column') not in rules['annual_columns']:
        raise ValueError('ANNUAL_COLUMN_REQUIRED')
    if item.get('product_basis') not in {'TOTAL_RARE_EARTH_OXIDE', 'MIXED_RARE_EARTH_OXIDE',
            'NDPR_OXIDE', 'HREO_8_ELEMENT', 'REO_EQUIVALENT_IN_MIXED_CARBONATE', 'REO_EQUIVALENT_IN_CONCENTRATE'}:
        raise ValueError('ANNUAL_OXIDE_EQUIVALENT_REQUIRED')
    if item['column'] == rules['annual_columns'][2] and (item.get('product_basis') != 'HREO_8_ELEMENT'
            or set(item.get('hre_elements', [])) != set(rules["heavy"])):
        raise ValueError('ANNUAL_HREO_8_ELEMENT_DEFINITION_REQUIRED')
    if item['column'] == rules['annual_columns'][1] and item.get('product_basis') != 'NDPR_OXIDE':
        raise ValueError('ANNUAL_NDPR_OXIDE_REQUIRED')
    if not item.get('annual_basis') or not item.get('scope_relation'):
        raise ValueError('ANNUAL_BASIS_AND_SCOPE_REQUIRED')
    units = {'tpa': Decimal(1), 't/a': Decimal(1), 't per annum': Decimal(1), 'ktpa': Decimal(1000)}
    if item.get('original_unit') not in units:
        raise ValueError('ANNUAL_EXPLICIT_UNIT_REQUIRED')
    token = str(item.get('original_token', '')).replace(',', '')
    if not re.fullmatch(r'\d+(?:\.\d+)?', token):
        raise ValueError('ANNUAL_NUMERIC_TOKEN_REQUIRED')
    try:
        value = Decimal(token) * units[item['original_unit']]
        expected = Decimal(str(item.get('value')))
    except InvalidOperation:
        raise ValueError('ANNUAL_NUMERIC_VALUE_REQUIRED') from None
    if not expected.is_finite() or expected <= 0 or expected != value:
        raise ValueError('ANNUAL_TOKEN_VALUE_MISMATCH')
    return format(value, 'f').rstrip('0').rstrip('.') if '.' in format(value, 'f') else format(value, 'f')

def summary_verify_annual_cell(item, source, rules):
    import pymupdf
    value = summary_annual_candidate(item,rules)
    with pymupdf.open(source) as doc:
        page = doc[item['page'] - 1]
        box = pymupdf.Rect(item['bbox'])
        row = pymupdf.Rect(item['row_bbox'])
        if box.is_empty or not row.contains(box) or not page.rect.contains(row):
            raise ValueError('ANNUAL_BBOX_OUTSIDE_ROW')
        if summary_annual_norm(page.get_textbox(box)) != summary_annual_norm(item['original_token']):
            raise ValueError('ANNUAL_SOURCE_TOKEN_MISMATCH')
        actual = summary_annual_norm(page.get_textbox(row))
        if actual != summary_annual_norm(item['row_text']):
            raise ValueError('ANNUAL_SOURCE_ROW_MISMATCH')
        if not re.search(r'\btpa\b|per annum', actual):
            raise ValueError('ANNUAL_SOURCE_UNIT_MISSING')
        if not any(s in actual for s in ('mixed rare earth oxide', 'reo contained in mixed carbonate')):
            raise ValueError('ANNUAL_SOURCE_OXIDE_LABEL_MISSING')
        for proof in item.get('context_proofs', []):
            pg = doc[proof['page']-1]
            if summary_annual_norm(pg.get_textbox(pymupdf.Rect(proof['bbox']))) != summary_annual_norm(proof['text']):
                raise ValueError('ANNUAL_CONTEXT_PROOF_MISMATCH')
    return value

def summary_model_annual(doc,review,study,spec,result,evidence,rules):
    from .technical_tables import number_token
    METHOD=rules['model_annual_method']
    PROFILE=rules['model_annual_profile']
    import pymupdf
    def fail(code):raise ValueError('REVIEW_MODEL_ANNUAL_'+code)
    def number(v):return not isinstance(v,bool) and isinstance(v,(int,float)) and math.isfinite(v)
    if (spec.get('method')!=METHOD or spec.get('profile')!=PROFILE or study.get('selected_scenario')!='Base Case'
        or study.get('endpoint')!='MREC' or study.get('scale')!='SCOPING_MODEL' or
        spec.get('assurance')!='MODEL_ASSUMPTION_DERIVED_NOT_DIRECT_REPORTED_OUTPUT'):
        fail('PROFILE_PRODUCT_SCENARIO_REQUIRED')
    contract={k:review[k] for k in ('source_sha256','statement_id','scope','effective_date')}
    if any(spec.get(k)!=v for k,v in contract.items()):fail('SOURCE_SCOPE_DATE_MISMATCH')
    inputs=spec.get('inputs',[])
    if len(inputs)!=3 or {i.get('name') for i in inputs}!={'annual_treo_t','nd_percent_of_treo','pr_percent_of_treo'}:fail('THREE_INPUTS_REQUIRED')
    items={i['name']:i for i in inputs}
    def rect(page,raw):
        if not isinstance(raw,list) or len(raw)!=4 or not all(number(v) for v in raw):fail('RECT_REQUIRED')
        box=pymupdf.Rect(raw)
        if box.is_empty or not page.rect.contains(box):fail('RECT_OUTSIDE_PAGE')
        return box
    def proof(name):
        p=spec.get(name,{})
        pn=p.get('page')
        if isinstance(pn,bool) or not isinstance(pn,int) or not 1<=pn<=len(doc):fail('PROOF_PAGE_REQUIRED')
        if p.get('evidence',{}).get('page')!=pn:fail('EVIDENCE_PAGE_MISMATCH')
        evidence(p['evidence']);actual=summary_annual_norm(summary_annual_region(doc[pn-1],rect(doc[pn-1],p.get('bbox'))))
        if actual!=summary_annual_norm(p.get('text','')):fail('PROOF_TEXT_MISMATCH')
        return pn,actual
    annual_page,annual_text=proof('annual_model_proof')
    if not all(t in annual_text for t in ('the base case reflects the metallurgical recovery and production assumptions adopted in the scoping study financial model','base case annual production represents the life-of-mine annual average and includes ramp-up and scheduling effects')):fail('LOM_MODEL_PROOF_REQUIRED')
    comp_page,comp_text=proof('composition_model_proof')
    if not all(t in comp_text for t in ('the distribution of the four principal magnet rare earth oxides and yttrium in the base case mrec is','presented in table 5.3.')):fail('COMPOSITION_MODEL_PROOF_REQUIRED')
    origin_page,origin_text=proof('composition_origin_proof')
    if origin_page!=comp_page or not origin_text.startswith('the base case mrec composition is based on the high-grade mrec produced by'):fail('COMPOSITION_ORIGIN_REQUIRED')
    if annual_page!=study.get('annual_basis_evidence',{}).get('page') or comp_page!=annual_page+1:fail('MODEL_TABLE_SEQUENCE_MISMATCH')
    tables=[];values={};widths={}
    for name,item in items.items():
        if any(item.get(k)!=v for k,v in contract.items()):fail('INPUT_SOURCE_SCOPE_DATE_MISMATCH')
        v=item.get('value');token=item.get('original_token');parsed=number_token(token)
        if not number(v) or v<=0 or not parsed or parsed.get('value')!=v:fail('TOKEN_VALUE_MISMATCH')
        e=item.get('evidence',{});evidence(e)
        b=item.get('cell_binding',{})
        if b.get('mode')!='native_cell' or b.get('scope')!=review['scope'] or b.get('page')!=e.get('page'):fail('INPUT_NATIVE_BINDING_REQUIRED')
        width=item.get('rounding_half_width');t=str(token).replace(',','');minwidth=.5*10**(-len(t.split('.')[1]) if '.' in t else 0)
        if not number(width) or width<minwidth or width>=v:fail('ROUNDING_INTERVAL_REQUIRED')
        if name=='annual_treo_t':
            if item.get('unit')!='tpa' or b.get('page')!=annual_page or b.get('column_label')!='Base Case' or b.get('row_label')!='Average annual contained TREO in MREC':fail('ANNUAL_PRODUCT_SCENARIO_MISMATCH')
            if study.get('parameters',{}).get('average_annual_treo_product_t')!=v or study.get('parameter_bindings',{}).get('average_annual_treo_product_t')!=b:fail('SELECTED_ANNUAL_TREO_MISMATCH')
            summary_annual_cell(doc,b,'average_annual_treo_product_t',token,'tpa',review['scope'],'Base Case')
        else:
            oxide='Nd2O3' if name=='nd_percent_of_treo' else 'Pr6O11'
            if item.get('basis')!=oxide or item.get('unit')!='%TREO' or v>100 or b.get('page')!=comp_page:fail('OXIDE_SHARE_BASIS_MISMATCH')
            page=doc[comp_page-1];table=rect(page,b.get('table_bbox'));row=rect(page,b.get('row_bbox'));column=rect(page,b.get('column_bbox'))
            cell=row&column
            if not table.contains(row) or not table.contains(column) or cell.is_empty or row.height>=table.height or column.width>=table.width:fail('SHARE_REGION_MISMATCH')
            def anchor(key,label,container):
                box=rect(page,b.get(key));actual=summary_annual_norm(summary_annual_region(page,box))
                if not container.contains(box) or actual.translate(str.maketrans('₀₁₂₃₄₅₆₇₈₉','0123456789'))!=summary_annual_norm(label).translate(str.maketrans('₀₁₂₃₄₅₆₇₈₉','0123456789')):fail('SHARE_ANCHOR_MISMATCH')
                return box
            anchor('table_label_bbox','Table 5.3 | Key Rare Earth Distribution in MREC',table)
            head=anchor('column_label_bbox','% of contained TREO',column)
            label='Neodymium (Nd₂O₃)' if oxide=='Nd2O3' else 'Praseodymium (Pr₆O₁₁)'
            anchor('row_label_bbox',label,row)
            if head.y1>row.y0:fail('SHARE_ROW_OUTSIDE_HEADER')
            actual=summary_annual_norm(summary_annual_region(page,cell));p=number_token(actual)
            if not re.fullmatch(r'\d+(?:\.\d+)?',actual) or not p or p['value']!=v:fail('SHARE_CELL_TOKEN_MISMATCH')
            tables.append((tuple(b['table_bbox']),tuple(b['column_bbox'])))
        values[name]=v;widths[name]=width
    if len(set(tables))!=1:fail('SHARE_TABLE_MISMATCH')
    share=values['nd_percent_of_treo']+values['pr_percent_of_treo']
    if share>100:fail('SHARE_SUM_EXCEEDS_100')
    expected=values['annual_treo_t']*share/100
    if not number(result) or not math.isclose(expected,result,rel_tol=1e-12,abs_tol=1e-9):fail('RESULT_MISMATCH')
    half=widths['nd_percent_of_treo']+widths['pr_percent_of_treo']
    interval=[(values['annual_treo_t']-widths['annual_treo_t'])*(share-half)/100,(values['annual_treo_t']+widths['annual_treo_t'])*(share+half)/100]
    if len(spec.get('rounding_interval_tpa',[]))!=2 or any(not number(a) or not math.isclose(a,b,rel_tol=1e-12) for a,b in zip(spec['rounding_interval_tpa'],interval)):fail('RESULT_ROUNDING_INTERVAL_MISMATCH')
    return expected

def summary_product_annual(derivation,value,annual_page,evidence):
    """Only same-table, explicitly annual, oxide-based product conversions."""
    from .technical_tables import number_token
    methods={'ANNUAL_PRODUCT_MASS_X_TREO_FRACTION':{'annual_product_t','treo_percent'},
             'ANNUAL_PRODUCT_MASS_X_TREO_FRACTION_X_NDPR_SHARE':{'annual_product_t','treo_percent','nd_percent_of_treo','pr_percent_of_treo'}}
    method=derivation.get('method');inputs=derivation.get('inputs',[])
    if method not in methods or {i['name'] for i in inputs}!=methods[method] or len(inputs)!=len(methods[method]):
        raise ValueError('REVIEW_ANNUAL_DERIVATION_INPUT_CONTRACT')
    values={};table_rows=set()
    for item in inputs:
        if item['evidence']['page']!=annual_page:raise ValueError('REVIEW_ANNUAL_DERIVATION_REQUIRES_SAME_TABLE')
        row=item['evidence'].get('table_row');render=item['evidence'].get('render_sha256','')
        if not row or not re.fullmatch('[0-9a-f]{64}',render):raise ValueError('REVIEW_ANNUAL_DERIVATION_RENDERED_ROW_REQUIRED')
        table_rows.add((summary_annual_norm(row),render))
        content=evidence(item['evidence']);parsed=number_token(item['original_token'])
        if summary_annual_norm(row) not in content:raise ValueError('REVIEW_ANNUAL_DERIVATION_ROW_NOT_IN_SOURCE')
        v=item['value'];name=item['name']
        if (isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or v<=0 or not parsed or
            parsed['value']!=v or not re.search(r'(?<![\d.])'+re.escape(summary_annual_norm(item['original_token']))+r'(?![\d.])',content)):
            raise ValueError('REVIEW_ANNUAL_DERIVATION_TOKEN_MISMATCH')
        expected='t/year' if name=='annual_product_t' else '%' if name=='treo_percent' else '%TREO'
        if item['unit']!=expected or name!='annual_product_t' and v>100:raise ValueError('REVIEW_ANNUAL_DERIVATION_UNIT_OR_RANGE')
        if not re.search(r'\bannual\b',content) or not re.search(r'\btreo\b',content):raise ValueError('REVIEW_ANNUAL_DERIVATION_BASIS_MISSING')
        if name.startswith(('nd_','pr_')) and not all(summary_annual_norm(m) in content for m in ['As a % of TREO','Nd2O3','Pr6O11']):
            raise ValueError('REVIEW_ANNUAL_DERIVATION_NDPR_OXIDE_BASIS_MISSING')
        values[name]=v
    if len(table_rows)!=1:raise ValueError('REVIEW_ANNUAL_DERIVATION_ROW_CONFLICT')
    result=values['annual_product_t']*values['treo_percent']/100
    if method.endswith('_X_NDPR_SHARE'):
        share=values['nd_percent_of_treo']+values['pr_percent_of_treo']
        if share>100:raise ValueError('REVIEW_ANNUAL_DERIVATION_NDPR_SHARE_OUT_OF_RANGE')
        result*=share/100
    if not math.isclose(result,value,rel_tol=1e-12,abs_tol=1e-9):raise ValueError('REVIEW_ANNUAL_DERIVATION_RESULT_MISMATCH')
    return result

def summary_annual_norm(value):
    return ' '.join(str(value).replace('\xa0',' ').split()).casefold()


def summary_annual_region(page, rect):
    return ' '.join(w[4] for w in page.get_text('words',sort=True)
        if rect.x0<=(w[0]+w[2])/2<=rect.x1 and rect.y0<=(w[1]+w[3])/2<=rect.y1)


def summary_annual_cell(doc,binding,field,token,unit,scope,selected_scenario=None,selected_sections=None):
    """Annual-only native branches of the reviewed cell validator, with no image fallback."""
    import pymupdf
    from .technical_tables import number_token
    def fail(code):raise ValueError('ANNUAL_CELL_'+code)
    if not binding or binding.get('field')!=field or binding.get('scope')!=scope:fail('SCOPE_OR_FIELD')
    pn=binding.get('page')
    if type(pn) is not int or not 1<=pn<=len(doc):fail('PAGE')
    page=doc[pn-1];mode=binding.get('mode')
    def rect(key):
        raw=binding.get(key)
        if not isinstance(raw,list) or len(raw)!=4 or any(type(v) not in (int,float) or not math.isfinite(v) for v in raw):fail('RECT')
        box=pymupdf.Rect(raw)
        if box.is_empty or not (page.rect*page.derotation_matrix).contains(box):fail('RECT_OUTSIDE_PAGE')
        return box
    if mode == 'native_statement':
        statement = summary_annual_norm(page.get_textbox(rect('statement_bbox')))
        if statement != summary_annual_norm(binding.get('statement', '')):
            fail('STATEMENT_MISMATCH')
        prefix, suffix = summary_annual_norm(binding.get('before', '')), summary_annual_norm(binding.get('after', ''))
        match = re.fullmatch(re.escape(prefix) + r'\s*([\d,]+(?:\.\d+)?)\s*' + re.escape(suffix), statement)
        wanted = number_token(str(token))
        if not match or not wanted or number_token(match[1])['value'] != wanted['value']:
            fail('STATEMENT_TOKEN_MISMATCH')
        if field=='average_annual_ndpr_product_t' and binding.get('semantic_profile')=='yangibana_annual_ndpr_in_treo':
            # A separately constrained disclosure profile: the NdPr amount is
            # explicitly included in average annual contained rare-earth oxides.
            pattern=(r'approximately [\d,]+(?:\.\d+)? tonnes per annum; and average annual contained '
                     r'production of approximately [\d,]+(?:\.\d+)? tonnes of total rare earth oxides, '
                     r'including approximately')
            if (not re.fullmatch(pattern,prefix) or suffix!='tonnes of neodymium and praseodymium.'
                    or unit!='tonnes' or binding.get('original_unit')!=unit):
                fail('STATEMENT_SEMANTICS_MISMATCH')
            context=summary_annual_norm(summary_annual_region(page,rect('time_basis_bbox')))
            if '19-year mine life' not in context or '100% project basis' not in context:
                fail('STATEMENT_ANNUAL_BASIS_MISMATCH')
        elif field=='average_annual_ndpr_product_t':
            if binding.get('semantic_profile') not in (None,'goschen_ndpr_rec'):
                fail('STATEMENT_SEMANTICS_MISMATCH')
            if prefix!='nd-pr contained in rec' or suffix!='tpa' or unit!='tpa':fail('STATEMENT_SEMANTICS_MISMATCH')
            time_basis=summary_annual_norm(summary_annual_region(page,rect('time_basis_bbox')))
            if time_basis!='operations metrics (life-of-mine annual average)':fail('STATEMENT_ANNUAL_BASIS_MISMATCH')
            proof=binding.get('oxide_basis_proof',{})
            pn=proof.get('page');box=proof.get('bbox')
            if not isinstance(pn,int) or not 1<=pn<=len(doc) or not isinstance(box,list) or len(box)!=4:
                fail('STATEMENT_OXIDE_BASIS_REQUIRED')
            region=pymupdf.Rect(box)
            if not doc[pn-1].rect.contains(region):fail('STATEMENT_OXIDE_BASIS_REQUIRED')
            exact='Nd-Pr, Dy and Tb production figures are life-of-mine annual average calculated by multiplying REC production by TREO grade and its respective rare earth oxide composition as a % of TREO'
            if summary_annual_norm(summary_annual_region(doc[pn-1],region))!=summary_annual_norm(exact):fail('STATEMENT_OXIDE_BASIS_REQUIRED')
        elif (field != 'average_annual_treo_product_t' or 'annual' not in prefix or
              not suffix.startswith('tpa of contained treo in concentrate') or unit != 'tpa'):
            fail('STATEMENT_SEMANTICS_MISMATCH')
        return 'NATIVE_SCOPED_STATEMENT_BINDING'
    if mode!='native_cell':fail('NATIVE_MODE_REQUIRED')
    table,row,column=rect('table_bbox'),rect('row_bbox'),rect('column_bbox');cell=row&column
    if not table.contains(row) or not table.contains(column) or cell.is_empty or row.height>=table.height or column.width>=table.width:fail('REGION')
    def anchor(box_key,text_key,container):
        box=rect(box_key);text=summary_annual_norm(summary_annual_region(page,box))
        if not container.contains(box) or not binding.get(text_key) or text!=summary_annual_norm(binding[text_key]):fail('ANCHOR')
        return text
    anchor('table_label_bbox','table_label',table)
    label=anchor('column_label_bbox','column_label',column);anchor('row_label_bbox','row_label',row)
    forecast=field.startswith('average_annual_')
    container=table if forecast else column
    if binding.get('unit_scope_bbox'):
        container=rect('unit_scope_bbox')
        if not table.contains(container) or not container.contains(column):fail('SHARED_UNIT_SCOPE')
    actual_unit=anchor('unit_bbox','unit_label' if 'unit_label' in binding else 'original_unit',container).strip('()')
    if binding.get('original_unit')!=unit or actual_unit!=summary_annual_norm(unit):fail('UNIT')
    context=anchor('metric_context_bbox','metric_context',table) if binding.get('metric_context_bbox') else ''
    metric=summary_annual_norm(binding['row_label'])
    if forecast:
        if not selected_scenario or label!=summary_annual_norm(selected_scenario):fail('SCENARIO')
        if binding.get('forecast_orientation')=='product_rows':
            target='total' if field=='average_annual_treo_product_t' else 'ndpr oxide'
            if metric!=target or label!='average reo*' or actual_unit!='t' or not context.startswith('* average production is calculated as the arithmetic annual average') or 'ramp up' not in context or 'low grade stockpiles' not in context:fail('PRODUCT_SEMANTICS')
            if not column.contains(rect('unit_bbox')):fail('PRODUCT_UNIT_SCOPE')
            metric='average annual production '+('treo' if target=='total' else 'ndpr')
        else:
            if not row.contains(rect('unit_bbox')):fail('ANNUAL_UNIT_SCOPE')
            if context and context!='average annual production target':fail('ANNUAL_CONTEXT')
            if context:metric+=' '+context
        target={'average_annual_treo_product_t':'treo','average_annual_ndpr_product_t':'ndpr','average_annual_hreo_product_t':'hreo'}.get(field)
        if not target or not re.search(r'\b'+target+r'\b',metric) or not re.search(r'annual|average',metric) or not re.search(r'production|output|contained',metric) or re.search(r'grade|recovery|feed|price|cost',metric) or actual_unit not in ('t','tpa'):fail('METRIC')
    else:
        section=(selected_sections or {}).get(binding.get('section_id'))
        if not section or section.get('page')!=pn or not pymupdf.Rect(section['bbox']).contains(row):fail('SELECTED_SECTION')
        anchor('scope_anchor_bbox','scope_anchor',table)
        if rect('scope_anchor_bbox').y1>row.y0 or not re.fullmatch(r'\d{4} reec product',metric):fail('SELECTED_ROW')
        expected={'annual_input_annual_product_t':('annual forecast reec production','t'),'annual_input_treo_percent':('treo','%'),
                  'annual_input_nd_percent_of_treo':('nd2o3','%'),'annual_input_pr_percent_of_treo':('pr6o11','%')}.get(field)
        if expected!=(label,actual_unit) or field.endswith(('nd_percent_of_treo','pr_percent_of_treo')) and context!='as a % of treo':fail('PRODUCT_INPUT_METRIC')
    actual=summary_annual_norm(summary_annual_region(page,cell))
    if actual_unit=='%' and re.fullmatch(r'\d[\d,]*(?:\.\d+)?%',actual):actual=actual[:-1]
    parsed=number_token(actual);wanted=number_token(str(token))
    if not parsed or not wanted or not re.fullmatch(r'[+\-]?\d[\d,]*(?:\.\d+)?',actual) or parsed['value']!=wanted['value']:fail('TOKEN')
    return 'NATIVE_TABLE_ROW_COLUMN_CELL_BINDING'


def summary_forecasts(pid, studies, attributes, sources, rules, decisions, cutoff, row=None, audit=None):
    """Study output is scoped separately from MREs and never operating production."""
    from .selection import choose
    from .census import summary_decision
    import pymupdf
    models=[];fills=[];audit=audit if audit is not None else []
    for a in attributes:
        study=a.get('engineering_forecast')
        if not study or study['scale'] not in rules['forecast_scales']:continue
        s=sources[a['source_sha256']];accepted={}
        try:
            with pymupdf.open(s['resolved_path']) as doc:
                def evidence(e):
                    text=' '.join(doc[e['page']-1].get_text().split())
                    if not e.get('markers') or any(summary_annual_norm(m) not in summary_annual_norm(text) for m in e['markers']):raise ValueError('FORECAST_PAGE_MARKER')
                    return summary_annual_norm(text)
                for parameter,value in study['parameters'].items():
                    if type(value) not in (int,float) or not math.isfinite(value) or value<0:raise ValueError('FORECAST_VALUE')
                    spec=study.get('parameter_derivations',{}).get(parameter)
                    if spec and spec.get('method')==rules['model_annual_method']:
                        summary_model_annual(doc,a,study,spec,value,evidence,rules)
                    elif spec:
                        summary_product_annual(spec,value,study['annual_basis_evidence']['page'],evidence)
                        for item in spec['inputs']:
                            b=item['cell_binding'];summary_annual_cell(doc,b,'annual_input_'+item['name'],item['original_token'],b['original_unit'],a['scope'],selected_sections=study.get('selected_input_sections'))
                    else:
                        b=study.get('parameter_bindings',{}).get(parameter)
                        if not b:raise ValueError('FORECAST_NATIVE_BINDING_MISSING')
                        evidence(study['annual_basis_evidence'])
                        summary_annual_cell(doc,b,parameter,str(value),b['original_unit'],a['scope'],study.get('selected_scenario'))
                    accepted[parameter]=value
        except (ValueError,KeyError,IndexError,OSError) as exc:
            audit.append(dict(project_id=pid,source_sha256=a['source_sha256'],reason='FORECAST_INPUT_INVALID',detail=str(exc)))
            accepted={}
        models.append(dict(source_sha=a['source_sha256'],effective_date=a['effective_date'],scope=a['scope'],case_id=a['review_id'],
            endpoint=study['endpoint'],element=study['element'],scale=study['scale'],raw=canonical(dict(parameters=accepted,locator=a['locator'],parameter_derivations=study.get('parameter_derivations',{}))),obs_id=a['obs_id']))
    if not models:models=[s for s in studies if s['scale'] in rules['forecast_scales']]
    for column,parameter in rules['annual_parameters'].items():
        options=[]
        for s in models:
            d=json.loads(s['raw']);value=d.get('parameters',{}).get(parameter)
            if type(value) in (int,float) and math.isfinite(value) and value>=0:
                spec=d.get('parameter_derivations',{}).get(parameter) or {}
                options.append(dict(evidence_id=s['case_id'],source_sha256=s['source_sha'],effective_date=s['effective_date'],
                    scope=s['scope'],endpoint=s['endpoint'],element=s['element'],scale=s['scale'],value=value,locator=d['locator'],spec=spec,
                    ids=[s.get('obs_id',s['case_id'])]))
        chosen,_=choose(options,('scope','endpoint','element','scale'))
        if chosen:
            method='MODEL_ASSUMPTION_DERIVED_ANNUAL_NDPR_NOT_DIRECT_REPORTED_OUTPUT' if chosen['spec'].get('method')==rules['model_annual_method'] else 'DATED_ENGINEERING_FORECAST_T_PER_YEAR_NOT_OPERATING_OUTPUT'
            fills.append(dict(column=column,value=chosen['value'],sha=chosen['source_sha256'],locator=chosen['locator'],method=method,scope=canonical(dict(study_scope=chosen['scope'],derivation=chosen['spec'])),obs_ids=chosen['ids']))
    products=[dict(evidence_id=s['case_id'],source_sha256=s['source_sha'],effective_date=s['effective_date'],scope=s['scope'],
        endpoint=s['endpoint'],scale=s['scale'],value=s['endpoint'],locator=json.loads(s['raw'])['locator'],ids=[s.get('obs_id',s['case_id'])]) for s in models]
    product,_=choose(products,('scope','endpoint','scale'))
    if product:fills.append(dict(column='產品/產出',value=rules['product_labels'].get(product['value'],product['value'])+'（'+product['scale']+'）',
        sha=product['source_sha256'],locator=product['locator'],method='DATED_ENGINEERING_PRODUCT_ENDPOINT_NOT_OPERATING_OUTPUT',scope=product['scope'],obs_ids=product['ids']))
    filled={f['column'] for f in fills}
    for a in attributes:
        item=a.get('source_stated_annual')
        if not item or item['column'] in filled or not row or row['開發階段代碼'] not in ('B1','B2'):continue
        if not summary_decision(decisions,'SOURCE_STATED_ANNUAL_PRODUCTION'):continue
        if not any(x['column']=='開發階段' and x['source_sha256']==a['source_sha256'] for x in attributes):continue
        try:value=summary_verify_annual_cell(item,sources[a['source_sha256']]['resolved_path'],rules)
        except (ValueError,KeyError,OSError):continue
        fills.append(dict(column=item['column'],value=value,sha=a['source_sha256'],locator=a['locator'],method='SOURCE_STATED_ANNUAL_PRODUCTION',scope=canonical(item),obs_ids=[a['obs_id']]))
    cfg=rules['cummins_staged_rule'];sha=cfg['source_sha256']
    if pid==cfg['project_id'] and sha in sources and '預估年產TREO_t_per_year' not in filled and summary_decision(decisions,'STAGED_ANNUAL_USE_FIRST_FULL_PRODUCTION_STAGE'):
        with pymupdf.open(sources[sha]['resolved_path']) as doc:
            text={p:' '.join(doc[p-1].get_text(sort=True).split()) for p in (60,76,77)}
        if all(quote in text[page] for page,quote in rules['cummins_checks']) and re.search(rules['cummins_production_pattern'],text[77]) and not re.search(r'stage 2a.{0,80}ramp|ramp.{0,80}stage 2a',text[76],re.I):
            selected=summary_select_first_full(rules['cummins_stages'])
            if selected:fills.append(dict(column='預估年產TREO_t_per_year',value=selected['annual_treo_t'],sha=sha,
                locator='physical PDF p60 design basis; p76 phase definitions; p77 annual schedule',method='STAGED_ANNUAL_USE_FIRST_FULL_PRODUCTION_STAGE',scope=canonical(dict(selected_stage=selected,meaning='SOURCE_STUDY_FORECAST_NOT_OPERATING_OUTPUT'))))
    return fills
