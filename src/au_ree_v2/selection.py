"""Source-bound selection shared by criteria, engineering cases and coverage.

Selection never ranks evidence from different scopes by publication date. A
dated disclosure is not certification of current plant performance or cash.
No derived candidate is written back over an original observation.
"""
import json
import math
from collections import defaultdict
from datetime import date
from .store import canonical, digest, filehash


def observation_visible(raw, selected_shas):
    """Extraction versions must be in the lock, as well as their original PDF."""
    return not raw.get('extraction_artifact_sha256') or raw['extraction_artifact_sha256'] in selected_shas


def evidence_domain(variable, raw):
    """Shared raw-domain taxonomy; a domain assignment never grants a score."""
    if raw.get('domain'):
        return raw['domain']
    v=variable
    if v in ('ore_mt','grade','contained_treo_kt') or v.startswith(('reported_resource_','reported_reserve_','reported_bulk_','reported_fine_fraction_')):return 'Resource'
    if v.startswith(('reported_technical_','uranium','thorium')) or 'recovery' in v:return 'Technical'
    if 'share_pct' in v or v.startswith(('reported_magnet','reported_dy','reported_tb','reported_nd','reported_pr')):return 'Strategic'
    if v=='study_maturity_ord':return 'Development'
    if v=='commercial_event' or any(w in v for w in ('equity','financ','offtake','debt','capex','convertible','note_')):return 'Commercial'
    return None


def date_end(value):
    """Conservative end of disclosed month/year, without inventing an exact day."""
    import calendar
    if len(value) == 4:
        return value + '-12-31'
    if len(value) == 7:
        year, month = map(int, value.split('-'))
        return f'{value}-{calendar.monthrange(year, month)[1]:02d}'
    date.fromisoformat(value)
    return value


def source_check(source, cutoff, root=None, acquired_through=None):
    if not source:
        return 'SOURCE_NOT_SELECTED'
    try:
        if any(date_end(source[k]) > (acquired_through or cutoff if k=='available_date' else cutoff) for k in ('publication_date', 'available_date') if source.get(k)):
            return 'SOURCE_AFTER_CUTOFF'
        if root is not None and filehash(root / source['path']) != source['sha256']:
            return 'SOURCE_HASH_MISMATCH'
    except (ValueError, KeyError, OSError):
        return 'INVALID_SOURCE_IDENTITY_OR_DATE'
    return None


def choose(options, dimensions=('scope', 'unit', 'basis', 'endpoint', 'scale', 'feed')):
    """Latest *within* a semantic scope; cross-scope choice requires a rule.

    Identical same-date evidence is corroboration, never an insertion-order tie
    break. Multiple studies are not corroboration unless their study ID agrees.
    """
    options = list({digest(o): o for o in options}.values())
    if not options:
        return None, 'NO_COMPATIBLE_EVIDENCE'
    groups = defaultdict(list)
    for o in options:
        groups[tuple(o.get(k) for k in dimensions)].append(o)
    active = []
    for group in groups.values():
        latest = max(date_end(o['effective_date']) for o in group)
        current = [o for o in group if date_end(o['effective_date']) == latest]
        if len({canonical(o.get('value')) for o in current}) != 1:
            return None, 'CONCURRENT_SOURCE_CONFLICT'
        merged = dict(sorted(current, key=canonical)[0])
        merged['evidence_ids'] = sorted({i for o in current for i in o.get('evidence_ids', [o['evidence_id']])})
        merged['sources'] = sorted({o['source_sha256'] for o in current})
        active.append(merged)
    if len(active) != 1:
        return None, 'MULTIPLE_SCOPES_REQUIRE_DEFINITION'
    return active[0], 'SELECTED'


def select_cases(cases, canonical_ids, group):
    """A case panel fixes feed, REO basis, endpoint and scale before selection."""
    by_project = defaultdict(list)
    for c in cases:
        key = '|'.join((c.get('recovery_feed', 'UNSPECIFIED'), c['element'], c['endpoint'], c['scale']))
        if key == group:
            by_project[canonical_ids.get(c['project_id'], c['project_id'])].append(c)
    selected, excluded = [], []
    for pid, options in sorted(by_project.items()):
        # Same study ID can have dated revisions; distinct studies never replace
        # one another just because one has a later date.
        records = [dict(c, evidence_id=c['case_id'], source_sha256=c['source_sha256'],
                        value=c['parameters'], study_identity=c['case_id']) for c in options]
        found, reason = choose(records, ('study_identity',))
        if found:
            selected.append(found)
        else:
            excluded.append(dict(canonical_project_id=pid, reason=reason,
                                 case_ids=canonical(sorted(c['case_id'] for c in options))))
    return selected, excluded


def technical_record(c, policy):
    """A view of existing evidence, never a second store or inferred recovery.

    Case identity excludes the oxide/parameter. Missing test conditions stay
    missing; an engineering design is explicitly distinguished from testwork.
    """
    raw=c.get('raw',{});variable=c['variable']
    role=policy.get('study_parameters',{}).get(variable,{}).get('role',c.get('role'))
    if raw.get('kind')=='LEACH_TABLE_ROW' or ('extraction' in variable and c.get('unit')=='%'):role='LEACH_EXTRACTION'
    performance=role in policy['technical_comparability']['performance_roles']
    quality=role in policy['technical_comparability']['quality_roles']
    category='B_PROCESS_PERFORMANCE' if performance else 'C_EVIDENCE_QUALITY' if quality else 'A_MINERALOGY_PROCESSING'
    model=c.get('origin')=='STUDY_PARAMETER' and c.get('scale') in ('DFS_MODEL','PFS_MODEL','SCOPING_MODEL')
    case_id=c.get('case_id') or raw.get('statement_id') or c['evidence_id']
    parameters=raw.get('parameters',{})
    population=raw.get('sample_population') or raw.get('sample_id')
    count=parameters.get('selected_composites_n',parameters.get('composites_n'))
    if population is None and count is not None:population='SOURCE_COMPOSITES_N='+str(count)
    statistic=raw.get('statistic') or ('ENGINEERING_DESIGN' if model else None)
    if statistic is None and '_average_' in variable:statistic='SOURCE_REPORTED_MEAN'
    if statistic is None and '_max_' in variable:statistic='SOURCE_REPORTED_MAXIMUM'
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
                evidence_mode='ENGINEERING_MODEL' if model else 'TESTWORK_OR_DISCLOSURE',
                scope_kind='CASE_MINE_PLAN' if model else 'SOURCE_SPECIFIC_SAMPLE_OR_DISCLOSURE',
                representativeness='MINE_PLAN_DESIGN_NOT_OPERATING_MEASUREMENT' if model else 'RESOURCE_REPRESENTATIVENESS_NOT_ESTABLISHED')


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
    if r.get('evidence_mode')=='ENGINEERING_MODEL':
        if not assumptions:reasons.append('MODEL_ASSUMPTIONS_NOT_DEFINED')
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


def _valid_candidate(c, sources, cutoff, root, acquired_through=None):
    reason = source_check(sources.get(c['source_sha256']), cutoff, root, acquired_through)
    if reason:
        return reason
    try:
        if date_end(c['effective_date']) > cutoff:
            return 'EFFECTIVE_AFTER_CUTOFF'
        if c.get('valid_from') and date_end(c['valid_from']) > cutoff:
            return 'EVENT_NOT_YET_EFFECTIVE'
        if c.get('valid_to') and date_end(c['valid_to']) < cutoff:
            return 'EVENT_EXPIRED'
    except (ValueError, TypeError):
        return 'INVALID_EFFECTIVE_DATE'
    if not c.get('scope') or not c.get('locator'):
        return 'MISSING_SCOPE_OR_LOCATOR'
    if sources[c['source_sha256']]['kind'] == 'pdf' and not c.get('pdf_page'):
        return 'MISSING_PHYSICAL_PAGE'
    if c.get('status') != 'AUTO_VALIDATED':
        return 'SOURCE_OBSERVATION_NOT_VALIDATED'
    return None


def resolve(db, snapshots, cutoff, resources, cases, mapping, policy, root=None, acquired_through=None):
    """One immutable input contract, one selection result for all consumers."""
    sources = {s['sha256']: s for s in snapshots}
    source_errors = {sha: source_check(s, cutoff, root, acquired_through) for sha, s in sources.items()}
    selected_by_key = {s['key']: s['sha256'] for s in snapshots}
    inventory, decisions, values = [], [], defaultdict(dict)
    names = {r['entity_id']: r['name'] for r in db.execute('SELECT * FROM records ORDER BY source_sha') if r['source_sha'] in sources}
    projects = {mapping.get(r[0], r[0]) for r in db.execute("SELECT entity_id FROM entities WHERE kind='PROJECT'")}
    for row in db.execute('SELECT * FROM observations ORDER BY obs_id'):
        if row['source_sha'] not in sources:
            continue
        raw = json.loads(row['raw'])
        if not observation_visible(raw,sources):continue
        validation=policy.get('document_pipeline',{}).get('validation_version')
        if raw.get('parser_version') and validation and raw.get('validation_version')!=validation:continue
        c = dict(raw, evidence_id=row['obs_id'], entity_id=row['entity_id'],
                 project_id=mapping.get(row['entity_id'], row['entity_id']),
                 variable=row['variable'], value=row['value'], unit=row['unit'], basis=row['basis'],
                 scope=row['scope'], effective_date=row['effective_date'], source_sha256=row['source_sha'],
                 locator=row['locator'], status=row['status'], origin='OBSERVATION', raw=raw)
        c['reason'] = source_errors[c['source_sha256']] or _valid_candidate(c, sources, cutoff, None, acquired_through)
        if c['variable'] == 'magnet_reo_share_pct':
            explicit = c['basis'] == 'PrNdDyTb_OXIDES_OVER_TREO'
            defined_legacy = c['basis'] == 'TREO' and (raw.get('composition_definition') or raw.get('transform', {}).get('rule') == 'RATIO_PPM_PERCENT')
            if explicit or defined_legacy:
                c['basis'] = 'PrNdDyTb_REO_DIV_TREO'
                c['basis_transform'] = 'EXPLICIT_FOUR_OXIDE_DEFINITION_ALIAS_ONLY_ORIGINAL_RAW_RETAINED'
        c['domain']=evidence_domain(c['variable'],raw)
        if raw.get('page_extraction_key') and selected_by_key.get(raw['page_extraction_key']) != raw.get('page_extraction_sha256'):
            c['reason'] = 'PAGE_EXTRACTION_VERSION_NOT_SELECTED'
        if c['project_id'] not in projects:
            c['reason'] = 'NOT_PROJECT_IDENTITY_NO_AUTOMATIC_DEPOSIT_ROLLUP'
        inventory.append(c)
    # Typed engineering parameters use their case's feed/endpoint/scale, not
    # the parent project's resource scope or an inferred overall recovery.
    for case in cases:
        for variable, value in case['parameters'].items():
            contract = policy['study_parameters'].get(variable, {})
            c = dict(evidence_id=digest([case, variable]),
                     entity_id=case['project_id'], project_id=mapping.get(case['project_id'], case['project_id']),
                     variable=variable, value=value, unit=contract.get('unit'), basis=case['element'],
                     scope=case['scope'], effective_date=case['effective_date'],
                     source_sha256=case['source_sha256'], locator=case['locator'], pdf_page=case['pdf_page'],
                     status='AUTO_VALIDATED', origin='STUDY_PARAMETER', case_id=case['case_id'],
                     endpoint=case['endpoint'], scale=case['scale'], feed=case.get('recovery_feed'),
                     role=contract.get('role', 'UNCLASSIFIED_PARAMETER'), domain=contract.get('domain', 'Technical'),
                     process=case['process'], raw=case)
            c['reason'] = source_errors.get(c['source_sha256']) or _valid_candidate(c, sources, cutoff, None, acquired_through)
            if not contract:
                c['reason'] = c['reason'] or 'PARAMETER_CONTRACT_NOT_DEFINED'
            inventory.append(c)
    inventory=list({digest(c):c for c in inventory}.values())
    technical=technical_comparability(inventory,policy) if policy.get('technical_comparability') else None
    compatible_ids=defaultdict(set)
    for r in technical or []:
        if r['comparability_status']=='NUMERIC_COMPARABLE':compatible_ids[r['comparison_group']].update(r['evidence_ids'])
    # Project-level commercial milestones are typed events, never inferred
    # from CAPEX, company cash or the numerical magnitude of a credit line.
    events = [c for c in inventory if c['variable'] == 'commercial_event']
    contracts=defaultdict(list)
    for c in events:
        if c.get('event_type')=='OFFTAKE' and c.get('contract_id') and not c['reason']:
            contracts[(c['project_id'],c['contract_id'])].append(c)
    for contract in contracts.values():
        current=[c for c in contract if date_end(c['effective_date'])==max(date_end(x['effective_date']) for x in contract)]
        if len({c['payment_terms'] for c in current if c.get('payment_terms')})>1:
            for c in current:c['comparison_status']='OFFTAKE_PAYMENT_TERMS_CONFLICT_NOT_FINANCING_STATUS'
    finance = defaultdict(list)
    for c in events:
        if c.get('event_type') != 'FINANCING':
            continue
        reason = c['reason']
        if c.get('attribution') != 'PROJECT':
            reason = reason or 'COMPANY_FUNDS_NOT_PROJECT_ATTRIBUTED'
        state = c.get('finance_state')
        code = policy['financing_codebook']['states'].get(state)
        if code is None:
            reason = reason or 'UNMAPPED_FINANCING_STATE'
        if not c.get('facility_id') or not c.get('conditions_status'):
            reason = reason or 'MISSING_EVENT_IDENTITY_OR_CONDITIONS'
        if state in ('CONDITIONAL_COMMITMENT',) and not c.get('conditions'):
            reason = reason or 'CONDITIONS_NOT_RECORDED'
        if state in ('FINANCIAL_CLOSE', 'DRAWN') and c.get('conditions_status') != 'SATISFIED':
            reason = reason or 'CLOSE_OR_DRAW_NOT_ESTABLISHED'
        if c.get('terms_conflict') and c.get('conflict_affects') == 'FINANCING_STATUS':
            reason = reason or 'FINANCING_TERMS_CONFLICT'
        c['finance_reason'] = reason
        # Select the latest reported instrument version BEFORE eligibility. An
        # expired/terminated latest version must not resurrect an older pledge.
        if c['reason'] not in ('SOURCE_NOT_SELECTED', 'SOURCE_AFTER_CUTOFF', 'EFFECTIVE_AFTER_CUTOFF', 'EVENT_NOT_YET_EFFECTIVE'):
            finance[c['project_id']].append(dict(c, value=code, unit='ordinal', basis=policy['financing_codebook']['version']))
    for pid in sorted(projects):
        for code, contract in policy['criteria'].items():
            options = []
            for c in inventory:
                if c['project_id'] != pid or c['variable'] not in contract.get('variables', []) or c['reason']:
                    continue
                if technical is not None and code in policy['technical_comparability']['candidate_criteria']:
                    if c['evidence_id'] not in compatible_ids[code]:
                        continue
                else:
                    # Frozen criteria, including T1/D1/C1, retain their original
                    # definitions. Candidate technical contracts were checked
                    # once above and are consumed without reinterpreting them.
                    if contract.get('unit') != c['unit']:
                        continue
                    if contract.get('basis') and c['basis'] not in contract['basis']:
                        continue
                    if any(c.get(k) != v for k, v in contract.get('requires', {}).items()):
                        continue
                # Composition must belong to the selected resource statement;
                # a study's product composition cannot substitute for it.
                rr = next((r for eid, r in resources.items() if mapping.get(eid, eid) == pid), None)
                if contract.get('resource_scope') and (not rr or c['scope'] != rr['scope'] or
                        c.get('statement_id') != rr['statement_id'] or c['effective_date'] != rr['date'] or
                        c['source_sha256'] != rr['source_sha']):
                    continue
                if not isinstance(c['value'], (int, float)) or isinstance(c['value'], bool) or not math.isfinite(c['value']):
                    continue
                if c['unit']=='ordinal' and (not float(c['value']).is_integer() or not 1<=c['value']<=6):
                    continue
                options.append(c)
            if code == 'C1':
                # Latest within each instrument only. A tranche does not replace
                # a different tranche. Concurrent contradictions fail locally.
                instruments = defaultdict(list)
                for c in finance.get(pid, []):
                    instruments[c['facility_id']].append(c)
                chosen = [choose(v, ('facility_id',)) for v in instruments.values()]
                if any(x is None for x, _ in chosen):
                    found, reason = None, 'CONCURRENT_FINANCING_CONFLICT'
                elif chosen and any(not x.get('finance_reason') for x, _ in chosen):
                    opts = [x for x, _ in chosen if not x.get('finance_reason')]
                    if any(x['value'] == 0 for x in opts) and any(x['value'] > 0 for x in opts):
                        found, reason = None, 'NO_FINANCING_VS_COMMITMENT_CONFLICT'
                    else:
                        found = dict(max(opts, key=lambda x: (x['value'], x['effective_date'], x['evidence_id'])))
                        found['evidence_ids'] = sorted({i for x in opts for i in x['evidence_ids']})
                        found['sources'] = sorted({s for x in opts for s in x['sources']})
                        found['raw'] = {'events': [x['raw'] for x in opts], 'codebook': policy['financing_codebook']}
                        reason = 'SELECTED_DATED_MILESTONE_NOT_AVAILABLE_FUNDS'
                else:
                    found, reason = None, ('LATEST_FINANCING_EVENT_NOT_QUALIFIED' if chosen else 'NO_QUALIFIED_PROJECT_FINANCING_EVENT')
            else:
                found, reason = choose(options, ('scope', 'unit', 'basis', 'endpoint', 'scale', 'feed', 'case_id'))
                if not options and any(c['project_id'] == pid and c['variable'] in contract.get('variables', []) for c in inventory):
                    reason = 'RAW_EVIDENCE_SCOPE_BASIS_ENDPOINT_SCALE_OR_VALIDITY_INCOMPATIBLE'
            if found:
                values[pid][code] = found
            decisions.append(dict(canonical_project_id=pid, project_name=names.get(pid, pid), criterion=code,
                                  value=None if found is None else found['value'], status=reason,
                                  evidence_ids=canonical([] if found is None else found['evidence_ids']),
                                  provenance=canonical(found), policy_version=policy['version']))
    result=dict(inventory=inventory, decisions=decisions, values=dict(values), policy=policy, mapping=mapping, projects=projects)
    if technical is not None:result['technical_comparability']=technical
    return result


def export(selection, out):
    from .analysis import write_csv
    if 'technical_comparability' in selection:
        fields=['project_id','case_id','evidence_id','evidence_ids','source_sha256','source_shas','pdf_page','locator','source_locators',
                'variable','value','unit','basis','scope','feed','endpoint','scale','process_stage','semantic_class',
                'study_date','sample_population','sample_interval','statistic','reagent','temperature_c','residence_hours',
                'acid_concentration','pressure','evidence_mode','scope_kind','representativeness','evidence_reason',
                'comparison_group','comparability_status','reason_codes','assumptions','allowed_analysis',
                'independent_projects','independent_cases','contract_version']
        write_csv(out/'technical_comparability.csv',
                  [{k:canonical(v) if isinstance(v,(dict,list)) else v for k,v in r.items()} for r in selection['technical_comparability']],fields)
    rows = []
    for c in selection['inventory']:
        rows.append(dict(c, reason=c['reason'] or c.get('finance_reason') or 'VALID_RAW_EVIDENCE',
                         raw=canonical(c['raw'])))
    write_csv(out / 'resolved_evidence.csv', rows,
              ['evidence_id', 'entity_id', 'project_id', 'origin', 'variable', 'domain', 'role', 'value',
               'unit', 'basis', 'scope', 'effective_date', 'valid_from', 'valid_to', 'case_id', 'endpoint',
               'scale', 'feed', 'event_type', 'facility_id', 'attribution', 'finance_state', 'conditions_status',
               'source_sha256', 'pdf_page', 'locator', 'reason', 'comparison_status', 'raw'])
    write_csv(out / 'criteria_resolution.csv', selection['decisions'],
              ['canonical_project_id', 'project_name', 'criterion', 'value', 'status', 'evidence_ids', 'provenance', 'policy_version'])
    coverage = []
    for domain in ('Technical', 'Commercial'):
        versions = [c for c in selection['inventory'] if c.get('domain') == domain]
        # Extraction metadata revisions remain queryable, but must not inflate
        # the scientific evidence count or label SITE/ISSUER rows as Projects.
        identity=lambda c:canonical([c.get(k) for k in ('origin','entity_id','variable','value','unit','basis','scope','statement_id','case_id','event_id','facility_id','contract_id','effective_date','source_sha256')])
        raw=list({identity(c):c for c in versions}.values())
        codes = [k for k, v in selection['policy']['criteria'].items() if v['domain'] == domain]
        for code in codes:
            qualified = [d for d in selection['decisions'] if d['criterion'] == code and d['value'] is not None]
            coverage.append(dict(domain=domain, criterion=code, raw_evidence=len(raw),
                                 raw_versions=len(versions),raw_entities=len({c['entity_id'] for c in raw}),
                                 raw_project_groups=len({c['project_id'] for c in raw}&selection['projects']),
                                 raw_observations=sum(c['origin']=='OBSERVATION' for c in raw),
                                 study_parameters=sum(c['origin']=='STUDY_PARAMETER' for c in raw),
                                 validated_events=sum(c['variable']=='commercial_event' and not c['reason'] for c in raw),
                                 qualified_projects=len(qualified),
                                 role='EXPLORATORY_CANDIDATE_NOT_FORMAL_C1',
                                 missing_reasons=canonical({s: sum(d['status'] == s for d in selection['decisions'] if d['criterion'] == code)
                                                           for s in sorted({d['status'] for d in selection['decisions'] if d['criterion'] == code and d['value'] is None})})))
    write_csv(out / 'technical_commercial_coverage.csv', coverage,
              ['domain', 'criterion', 'raw_evidence', 'raw_versions', 'raw_entities', 'raw_project_groups', 'raw_observations', 'study_parameters', 'validated_events', 'qualified_projects', 'role', 'missing_reasons'])


def diagnostics(selection, prepared, snapshots, criteria, root, out):
    """Separate acquisition/extraction/semantic failures from scoring eligibility.

    A bounded search is never evidence of absence. Not-disclosed and
    not-applicable require explicit checked-scope/stage rules, which this
    release does not invent.
    """
    from .analysis import write_csv
    from .pdf_extract import project_registry
    from pathlib import Path
    by_project=defaultdict(list)
    for c in selection['inventory']:by_project[c['project_id']].append(c)
    by_coverage={r['canonical_project_id']:r for r in prepared['coverage']}
    registry=project_registry(root);sources={s['key']:s for s in snapshots}
    identity_sources={selection['mapping'].get(p['entity_id'],p['entity_id']):sources.get(p['identity_source']) for p in registry}
    rows=[]
    for pid in sorted(selection['projects']):
        raw=by_project[pid];source=identity_sources.get(pid)
        for criterion in criteria:
            code=criterion['code'];domain=criterion['domain'];evidence=[c for c in raw if c.get('domain')==domain]
            scored=bool(by_coverage.get(pid,{}).get(code)) or code in selection['values'].get(pid,{})
            automatic=[c for c in evidence if c['raw'].get('parser_version')]
            decision=next((d for d in selection['decisions'] if d['canonical_project_id']==pid and d['criterion']==code),None)
            if scored:state='VALID_SCORABLE_EVIDENCE'
            elif automatic and all(c.get('reason') for c in automatic):state='OBSERVATION_EXTRACTED_NOT_VALIDATED'
            elif decision and 'INCOMPATIBLE' in decision['status']:state='SCOPE_OR_BASIS_INCOMPATIBLE'
            elif evidence:state='SCOPED_RAW_EVIDENCE_CRITERION_NOT_ESTABLISHED'
            elif source:state='SOURCE_ACQUIRED_EXTRACTION_OR_SEARCH_INCOMPLETE'
            else:state='SOURCE_NOT_DISCOVERED'
            rows.append(dict(project_id=pid,domain=domain,criterion=code,status=state,
                             raw_evidence=len(evidence),automatic_evidence=len(automatic),
                             selection_reason=decision['status'] if decision else None,
                             source_shas=canonical(sorted({c['source_sha256'] for c in evidence}|({source['sha256']} if source else set()))),
                             exclusion_reasons=canonical(sorted({c['reason'] for c in evidence if c.get('reason')})),
                             search_completeness='BOUNDED_NOT_EXHAUSTIVE_UNKNOWN',confirmed_stage=None,
                             interpretation='NO_ABSENCE_OR_STAGE_INAPPLICABILITY_INFERRED'))
    write_csv(Path(out)/'evidence_pipeline_diagnostics.csv',rows,
              ['project_id','domain','criterion','status','raw_evidence','automatic_evidence','selection_reason','source_shas','exclusion_reasons','search_completeness','confirmed_stage','interpretation'])
    return rows


def commercial_evidence(selection):
    """Typed dated events remain distinct even when their milestone is equal.

    Only the latest version of each explicit instrument/contract is current in
    this evidence set. Unknown expiry/counterparties/CPs stay Unknown, not cash.
    """
    events=[dict(c) for c in selection['inventory'] if c['variable']=='commercial_event']
    latest={}
    for c in events:
        key=(c['project_id'],c.get('facility_id') or c.get('contract_id') or c.get('event_id'))
        latest[key]=max(latest.get(key,''),date_end(c['effective_date']))
    rows=[]
    for c in sorted(events,key=lambda c:(c['project_id'],c['effective_date'],c['evidence_id'])):
        key=(c['project_id'],c.get('facility_id') or c.get('contract_id') or c.get('event_id'))
        current=date_end(c['effective_date'])==latest[key]
        valid=not c.get('reason') and c.get('attribution')=='PROJECT' and current
        rows.append(dict(project_id=c['project_id'],evidence_id=c['evidence_id'],event_id=c.get('event_id'),event_type=c.get('event_type'),
            instrument_id=key[-1],instrument_type=c.get('instrument_type') or _instrument_type(c),finance_state=c.get('finance_state'),
            agreement_state=c.get('agreement_state'),conditions=c.get('conditions'),conditions_status=c.get('conditions_status','UNKNOWN'),
            counterparty=c.get('counterparty'),attribution=c.get('attribution'),scope=c['scope'],
            financial_close='EVIDENCED' if valid and not c.get('finance_reason') and c.get('finance_state')=='FINANCIAL_CLOSE' else 'NOT_ESTABLISHED_BY_THIS_EVENT',
            drawdown='EVIDENCED' if valid and not c.get('finance_reason') and c.get('finance_state')=='DRAWN' else 'NOT_ESTABLISHED_BY_THIS_EVENT',
            effective_date=c['effective_date'],valid_from=c.get('valid_from'),valid_to=c.get('valid_to'),expiry_status=c.get('expiry_status','UNKNOWN'),
            current_version=int(current),qualified_project_event=int(valid),reason=c.get('reason') or c.get('finance_reason') or 'VALID_DATED_EVENT_NOT_CASH',
            terms_status=c.get('comparison_status') or c.get('terms_conflict') or 'NO_CONFLICT_RECORDED_NOT_LEGAL_CERTIFICATION',
            source_sha256=c['source_sha256'],pdf_page=c.get('pdf_page'),locator=c['locator'],currentness=c.get('currentness'),
            original_event=canonical(c['raw'])))
    return rows


def _instrument_type(event):
    """Descriptive literal classification, independently of ordinal maturity."""
    text=' '.join(str(event.get(k) or '') for k in ('agreement_state','scope','conditions')).lower()
    for words,label in [(('convertible','note'),'CONVERTIBLE_NOTE'),(('earn-in',),'JV_EARN_IN'),(('credit approval',),'CREDIT_APPROVAL'),(('subscription',),'SUBSCRIPTION'),(('equity',),'EQUITY'),(('loan',),'LOAN')]:
        if all(w in text for w in words):return label
    return 'OFFTAKE' if event.get('event_type')=='OFFTAKE' else 'UNKNOWN_NOT_INFERRED_FROM_ORDINAL'
