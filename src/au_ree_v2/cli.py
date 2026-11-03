"""One entrypoint; independent stages share one database and run contract."""
import argparse
import json
import subprocess
import sys
import uuid
import platform
from datetime import date, datetime, timezone, timedelta
from .hierarchy import build as build_hierarchy
from .resolution import resolve,technical_coverage
from .studies import ingest as ingest_cases
from .screen_index import rows as screen_index_rows
from pathlib import Path
from . import __version__
from .acquisition import refresh, select_snapshots
from .analysis import prepare, run_r, write_csv
from .evidence import ingest_sources, ingest_claims, resource_values
from .gis import run as run_gis, national_deposit_port_distances, deposit_type_port_summary
from .official import official_inventory, exact_deposit_candidates, domain_evidence_coverage, national_prospectus_inventory
from .national import national_candidate_rows, national_source_coverage, candidate_port_distances
from .store import canonical, connect, digest, filehash, logical_dump

def code_version(root):
    try:
        commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True,stderr=subprocess.DEVNULL).strip()
    except (OSError,subprocess.CalledProcessError):
        commit='UNCOMMITTED'
    files=sorted([*Path(root).glob('src/**/*.py'),*Path(root).glob('R/*.R')])
    return {'package':__version__,'commit':commit,
            'content_sha256':digest({p.relative_to(root).as_posix():filehash(p) for p in files})}

def research_configuration(root, snapshot_lock=None):
    """Load current policy or the SHA-checked semantics accompanying a lock."""
    config=json.loads((root/'config/research.json').read_text(encoding='utf-8'))
    # A lock's adjacent configuration freezes research semantics as well as
    # source bytes. Old Phase5/6 locks retain their original selection policy.
    frozen_config=Path(snapshot_lock).parent/'configuration.json' if snapshot_lock else None
    if frozen_config and frozen_config.exists():
        summary=frozen_config.parent/'summary.json'
        if summary.exists():
            expected=json.loads(summary.read_text(encoding='utf-8')).get('output_hashes',{}).get('configuration.json')
            if expected and filehash(frozen_config)!=expected:
                raise ValueError('Locked research configuration checksum mismatch')
        config=json.loads(frozen_config.read_text(encoding='utf-8'))['research']
    elif not snapshot_lock:
        policy_path=root/'config/evidence_policy.json'
        if policy_path.exists():
            policy=json.loads(policy_path.read_text(encoding='utf-8'))
            config={**config,'evidence_resolution':policy,'version':config['version']+'+'+policy['version'],
                    'panels':{**config['panels'],**policy['panels']}}
    return config


def execute(args):
    root=Path(args.root).resolve()
    config=research_configuration(root,args.snapshot_lock)
    registry=json.loads((root/'config/sources.json').read_text(encoding='utf-8'))
    date.fromisoformat(args.as_of)
    if args.as_of > datetime.now(timezone(timedelta(hours=8))).date().isoformat():
        raise ValueError('Future cutoff is not supported')
    if args.snapshot_lock and args.refresh:
        raise ValueError('--snapshot-lock cannot be combined with --refresh')
    if args.dry_run:
        return {'status':'DRY_RUN','module':args.module,'cutoff':args.as_of,'root':str(root),
                'snapshot_count':len(select_snapshots(root,args.as_of)), 'writes':False}
    if args.module=='pdf-extract':
        from .pdf_extract import capture_pages
        source=next(s for s in select_snapshots(root,args.as_of) if s['key']==args.source_key)
        return {'pages':capture_pages(root,source,[int(p) for p in args.pages.split(',')],args.tessdata)}
    acquisition=[]
    if args.module=='discover':
        from .discovery import discover
        return discover(root,json.loads((root/'config/discovery.json').read_text(encoding='utf-8')))
    if args.module=='acquire' or args.refresh:
        from .discovery import discover
        if args.source_key:
            keys=set(args.source_key.split(','))
            chosen=[s for s in registry['sources'] if s['key'] in keys]
            if keys!={s['key'] for s in chosen}:raise ValueError('Unknown acquisition source key')
            discovery={'status':'TARGETED_SOURCE_UPDATE'}
        else:
            chosen=registry['sources']
            discovery=discover(root,json.loads((root/'config/discovery.json').read_text(encoding='utf-8')))
        acquisition=refresh(root,dict(registry,sources=chosen))
        if args.module=='acquire':
            return {'status':'COMPLETED_WITH_SOURCE_STATUS','sources':acquisition,'discovery':discovery}
    snapshots=select_snapshots(root,args.as_of)
    if args.snapshot_lock:
        snapshots=json.loads(Path(args.snapshot_lock).read_text(encoding='utf-8'))
        for s in snapshots:
            if s['available_date']>args.as_of or s.get('publication_date','')>args.as_of:
                raise ValueError('Snapshot lock contains evidence after cutoff')
            if filehash(root/s['path'])!=s['sha256']:
                raise ValueError('Locked snapshot checksum mismatch')
            for page in s.get('original_responses',[]):
                if filehash(root/page['path'])!=page['sha256']:raise ValueError('Locked original response checksum mismatch')
    work=Path(args.work).resolve() if args.work else root/'work'
    work.mkdir(parents=True,exist_ok=True)
    run_id=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')+'-'+uuid.uuid4().hex[:8]
    out=work/'runs'/run_id
    out.mkdir(parents=True)
    db=connect(work/'canonical.sqlite')
    version=code_version(root)
    configuration={'research':config,'sources':registry,'claims_sha256':filehash(root/'data/claims.json')}
    for name in ('identity_links.json','study_cases.json'):
        if (root/'data'/name).exists():configuration[name+'_sha256']=filehash(root/'data'/name)
    configuration['eligibility_policy_sha256']=filehash(root/'config/eligibility_compatibility.json')
    db.execute('INSERT INTO runs VALUES(?,?,?,?,?,?,?,?)',
        (run_id,datetime.now(timezone.utc).isoformat(),args.as_of,canonical(version),digest(configuration),
         digest(snapshots),'RUNNING',None))
    db.commit()
    try:
        ingest_sources(db,root,snapshots)
        from .national import government_explicit_relations
        government_explicit_relations(db,snapshots)
        from .national import live_government_inventory,live_government_coverage,government_link_candidates
        live_rows=live_government_inventory(db,snapshots)
        live_coverage=live_government_coverage(root,snapshots,live_rows)
        write_csv(out/'government_native_entities.csv',live_rows,
                  ['entity_id','kind','namespace','native_id','name','state','longitude','latitude',
                   'source_key','source_sha256','locator','source_role','original_attributes'])
        write_csv(out/'government_source_coverage.csv',live_coverage,
                  ['state','source_key','raw_records','ree_native_entities','tenement_entities','explicit_project_parents',
                   'project_records','source_sha256','status'])
        screen_rows=screen_index_rows(db,{s['sha256'] for s in snapshots})
        write_csv(out/'national_screen_index.csv',screen_rows,['candidate_id','source_key','native_label','native_label_role','state','tier','source_ref','selection_entity_id','parent_candidate_id','source_sha','verification','raw'])
        if args.module!='bootstrap':
            ingest_claims(db,root,snapshots,args.as_of,args.project,conflict_selection=bool(config.get('evidence_resolution')))
        resources=resource_values(db,args.as_of,{s['sha256'] for s in snapshots},strict=bool(config.get('evidence_resolution')))
        from .national import resource_quality_checks
        resource_qa=resource_quality_checks(db,{s['sha256'] for s in snapshots})
        write_csv(out/'resource_statement_quality.csv',resource_qa,
                  ['entity_id','statement_id','scope','effective_date','source_sha256','basis',
                   'calculated_contained_kt','reported_contained_kt','rounding_lower_kt','rounding_upper_kt','status','interpretation'])
        cases=ingest_cases(db,root,snapshots,args.as_of) if args.module!='bootstrap' else []
        if config.get('evidence_resolution') and args.module!='bootstrap':
            from .evidence import ingest_events
            ingest_events(db,root,snapshots,args.as_of)
        hierarchy=build_hierarchy(db,snapshots)
        identity=resolve(db,root,snapshots,args.as_of,config.get('evidence_resolution',{}).get('identity_rule_version'))
        live_candidates=government_link_candidates(db,snapshots,identity['mapping'] if config.get('evidence_resolution',{}).get('identity_rule_version') else None)
        write_csv(out/'government_identity_candidates.csv',live_candidates,
                  ['a','b','name','state','distance_m','status','source_a','source_b'])
        technical_rows=technical_coverage(db,identity,resources,cases,{s['sha256'] for s in snapshots})
        write_csv(out/'technical_project_coverage.csv',technical_rows,['canonical_project_id','member_entity_ids','status','resource_scopes','study_case_ids','other_stage_evidence','shared_resource_context','unverified_or_other_scope_claims','interpretation'])
        hierarchy=build_hierarchy(db,snapshots)
        write_csv(out/'native_identity_ledger.csv',identity['ledger'],['source_record_id','target_id','state','source_key','native_id','resolved_entities','status','source_sha256'])
        write_csv(out/'canonical_membership.csv',identity['membership'],['entity_id','kind','canonical_id','status'])
        write_csv(out/'identity_decisions.csv',identity['accepted'],['alias_id','canonical_id','kind','status','source_sha256','locator'])
        write_csv(out/'deposit_identity_review.csv',identity['candidates'],['a','b','name','state','distance_m','status','source_a','source_b'])
        write_csv(out/'entity_hierarchy.csv',hierarchy,['parent_id','parent_kind','child_id','child_kind','relation','effective_date','source_sha','locator'])
        gis_values={}
        if args.module in ('all','gis','analyze','rebuild'):
            gis_values=run_gis(db,root,snapshots,run_id,resources)
        deposit_gis=[]
        if args.module in ('all','gis','analyze','rebuild'):
            deposit_gis=national_deposit_port_distances(db,root,snapshots,run_id)
        write_csv(out/'deposit_port_distances.csv',deposit_gis,
                  ['deposit_id','deposit_name','state','deposit_type','longitude','latitude',
                   'deposit_source_sha256','port_source_sha256','distance_km','status',
                   'method','interpretation'])
        deposit_by_type=deposit_type_port_summary(deposit_gis)
        write_csv(out/'aim_c_deposit_type_port_summary.csv',deposit_by_type,
                  ['state','deposit_type','deposits_total','deposits_with_port_distance',
                   'median_port_distance_km','min_port_distance_km','max_port_distance_km',
                   'unit_of_analysis','inference'])
        legacy_candidates=national_candidate_rows(db,{s['sha256'] for s in snapshots})
        write_csv(out/'national_e1_candidates.csv',legacy_candidates,
                  ['entity_id','source_key','native_id','legacy_target_id','name','state','longitude','latitude',
                   'source_sha256','original_chunk_sha256','original_locator','original_source_path',
                   'screening_status','record_kind','project_parent_hint'])
        national_coverage=national_source_coverage(legacy_candidates)
        write_csv(out/'national_e1_coverage.csv',national_coverage,
                  ['state','source_key','source_records','coordinate_records','source_record_not_project'])
        candidate_ports=[]
        if args.module in ('all','gis','analyze','rebuild'):
            candidate_ports=candidate_port_distances(db,root,snapshots,run_id)
        write_csv(out/'national_e1_port_distances.csv',candidate_ports,
                  ['entity_id','source_key','state','name','distance_km','coordinate_source_sha256',
                   'port_source_sha256','status','unit_of_analysis','limitation'])
        gis_rows=[]
        for eid,metrics in sorted(gis_values.items()):
            for variable,v in sorted(metrics.items()):
                gis_rows.append({'entity_id':eid,'variable':variable,'distance_km':v['value'],
                                 'layer_sha256':v['layer_sha256'],
                                 'coordinate_source_sha256':v['coordinate_source_sha256'],
                                 'method':v['method'],
                                 'coverage_scope':v['coverage_scope'],
                                 'radius_km':v['radius_km'],
                                 'source_where':v['source_where'],
                                 'limitation':v['limitation']})
        write_csv(out/'gis_metrics.csv',gis_rows,
                  ['entity_id','variable','distance_km','layer_sha256',
                   'coordinate_source_sha256','method','coverage_scope',
                   'radius_km','source_where','limitation'])
        results={};prepared={'panels':{},'coverage':[]};selection=None
        if args.module in ('all','analyze','rebuild'):
            if config.get('evidence_resolution'):
                from .selection import resolve as select_evidence,export as export_selection
                selection=select_evidence(db,snapshots,args.as_of,resources,cases,identity['mapping'],config['evidence_resolution'],root)
                export_selection(selection,out)
            prepared=prepare(db,args.as_of,snapshots,resources,gis_values,config,out,args.project,identity['mapping'],cases,selection)
            if not args.skip_r:
                results=run_r(root,out,prepared,config,args.rscript)
        source_shas={s['sha256'] for s in snapshots}
        from .national import raw_domain_coverage
        raw_domains=raw_domain_coverage(db,source_shas)
        write_csv(out/'database_domain_coverage.csv',raw_domains,
                  ['domain','evidence_status','distinct_statement_values','entities','sources','numeric_values','interpretation'])
        census=[dict(r) for r in db.execute('''SELECT e.entity_id,e.kind,r.* FROM entities e
            JOIN records r USING(entity_id) ORDER BY e.entity_id,r.source_sha''') if r['source_sha'] in source_shas]
        write_csv(out/'census.csv',census,['entity_id','kind','name','state','longitude','latitude','deposit_type','activity','source_sha'])
        inventory=official_inventory(db,source_shas)
        write_csv(out/'official_resource_inventory.csv',inventory,
                  ['project_id','project_name','state','official_status','listed_owner','ore_mt',
                   'grade_pct','contained_treo_kt','resource_date','basis','category',
                   'source_sha256','locator','confidence','pdf_url'])
        candidate_links=exact_deposit_candidates(db,inventory,source_shas)
        write_csv(out/'census_link_candidates.csv',candidate_links,
                  ['project_id','project_name','deposit_id','deposit_source_sha256',
                   'project_source_sha256','candidate_count','match_rule','status'])
        national_inventory=national_prospectus_inventory(db,source_shas)
        write_csv(out/'national_prospectus_evidence.csv',national_inventory,
                  ['project_id','project_name','state','owner','strategic_evidence',
                   'technical_evidence','development_evidence','commercial_evidence',
                   'source_sha256','locator','status','source_url'])
        dimension_rows=domain_evidence_coverage(db,inventory,resources,gis_values,national_inventory,source_shas,selection,prepared,config['criteria'])
        write_csv(out/'project_domain_evidence.csv',dimension_rows,
                  ['project_id','project_name','domain','evidence_state','evidence_reference','scorable']+(['exploratory_scorable','selection_policy'] if selection else []))
        candidates=[]
        for row in census:
            if row['kind']!='SOURCE_RECORD':
                continue
            detail=json.loads(row['raw'])
            candidates.append({'entity_id':row['entity_id'],'source_sha256':row['source_sha'],
                               'sheet':detail.get('sheet'),'source_row':detail.get('row_number'),
                               'cells':canonical(detail.get('cells',[])),
                               'classification':detail.get('classification'),
                               'rule':detail.get('match_rule'),
                               'project_name':detail.get('project_name'),
                               'matched_project_id':detail.get('project_id'),
                               'source_locator':detail.get('locator')})
        write_csv(out/'census_candidates.csv',candidates,
                  ['entity_id','source_sha256','sheet','source_row','cells','classification','rule',
                   'project_name','matched_project_id','source_locator'])
        deposit_summary={}
        for row in census:
            if row['kind']!='DEPOSIT':
                continue
            key=(row.get('state') or 'UNKNOWN',row.get('deposit_type') or 'UNKNOWN')
            deposit_summary.setdefault(key,set()).add(row['entity_id'])
        write_csv(out/'deposit_type_summary.csv',
                  [{'state':state,'deposit_type':dtype,'deposit_records':len(ids)}
                   for (state,dtype),ids in sorted(deposit_summary.items())],
                  ['state','deposit_type','deposit_records'])
        # Export points with evidence, suitable for QGIS without proprietary software.
        points=[]
        seen=set()
        for r in census:
            if r['entity_id'] in seen or r['longitude'] is None:
                continue
            seen.add(r['entity_id'])
            points.append({'type':'Feature','geometry':{'type':'Point','coordinates':[r['longitude'],r['latitude']]},
                           'properties':{k:r[k] for k in ('entity_id','kind','name','state','source_sha')}})
        (out/'census.geojson').write_text(canonical({'type':'FeatureCollection','features':points})+'\n',encoding='utf-8')
        from .eligibility import audit
        audit_summary=audit(db,out,identity,technical_rows,prepared,config,args.as_of,snapshots)
        from .security import public_export
        dump=public_export(logical_dump(db))
        (out/'logical_database.json').write_text(canonical(dump)+'\n',encoding='utf-8')
        (out/'snapshot_lock.json').write_text(canonical(snapshots)+'\n',encoding='utf-8')
        (out/'configuration.json').write_text(canonical(configuration)+'\n',encoding='utf-8')
        issues=[dict(r) for r in db.execute('SELECT * FROM review_queue ORDER BY issue_id')]
        write_csv(out/'review_queue.csv',issues,['issue_id','entity_id','source_sha','reason','details','status'])
        by_kind={}
        for eid in {r['entity_id'] for r in census}:
            kind=next(r['kind'] for r in census if r['entity_id']==eid)
            by_kind[kind]=by_kind.get(kind,0)+1
        registered_keys={source['key'] for source in registry['sources']}
        selected_keys={snapshot['key'] for snapshot in snapshots}
        summary={'run_id':run_id,'status':'COMPLETED','cutoff':args.as_of,'module':args.module,
            'live_government_sources_n':len(live_coverage),
            'live_government_raw_records_n':sum(r['raw_records'] for r in live_coverage if r['raw_records'] is not None),
            'live_government_native_entities_n':len({r['entity_id'] for r in live_rows if r['source_role']=='LIVE_GOVERNMENT_NATIVE_RECORD'}),
            'live_government_project_parents_n':len({r['entity_id'] for r in live_rows if r['source_role']=='LIVE_GOVERNMENT_PROJECT_PARENT'}),
            'live_government_project_records_n':len({r['entity_id'] for r in live_rows if r['kind']=='PROJECT'}),
            'live_government_candidate_pairs_n':len(live_candidates),
            'logical_database_export':'PUBLIC_DERIVATIVE_CREDENTIAL_REFERENCES_REMOVED_ORIGINAL_CANONICAL_DB_RETAINED_LOCALLY',
            'database_domain_evidence':raw_domains,
            'code':version,'configuration_sha256':digest(configuration),'snapshot_sha256':digest(snapshots),
            'logical_database_sha256':digest(dump),'eligibility_audit':audit_summary,'source_count':len(snapshots),'census_by_kind':by_kind,
            'unresolved_census_candidate_records':sum(c['classification']=='UNRESOLVED_PROJECT_CANDIDATE_SOURCE_RECORD' for c in candidates),
            'unresolved_census_candidate_records_scope':'REMP_WORKBOOK_ONLY_NOT_GLOBAL_CENSUS',
            'official_government_ree_resource_rows':len(inventory),
            'national_advanced_ree_profile_rows':len(national_inventory),
            'national_selected_e1_source_rows':len(legacy_candidates),
            'national_selected_e1_coordinate_rows':sum(r['longitude'] is not None and r['latitude'] is not None for r in legacy_candidates),
            'national_selected_e1_port_distances_n':sum(r['distance_km'] is not None for r in candidate_ports),
            'national_e1_coverage_groups':len(national_coverage),
            'provisional_deposit_link_candidates':len(candidate_links),
            'project_domain_evidence_states':{state:sum(r['evidence_state']==state for r in dimension_rows)
                                               for state in sorted({r['evidence_state'] for r in dimension_rows})},
            'source_registry_coverage':{'registered_count':len(registered_keys),
                                        'selected_snapshot_count':len(selected_keys),
                                        'missing_or_cutoff_excluded':sorted(registered_keys-selected_keys)},
            'gis_validated_distances':{kind:sum(r['variable']==kind for r in gis_rows) for kind in sorted({r['variable'] for r in gis_rows})},
            'national_ga_deposit_port_distances_n':sum(r['distance_km'] is not None for r in deposit_gis),
            'national_ga_deposit_port_scope_n':len(deposit_gis),
            'aim_c_deposit_type_groups_n':len(deposit_by_type),
            'official_summary_screen_n':prepared.get('government_screen_n',0),
            'resource_defined_n':len(resources),'development_n':sum(c['development'] for c in prepared['coverage']),
            'canonical_projects_n':len({r['canonical_id'] for r in identity['membership'] if r['kind']=='PROJECT'}),
            'canonical_project_count_interpretation':'REGISTRY_GROUPS_AFTER_DOCUMENT_SUPPORTED_ALIASES_NOT_CERTIFIED_NATIONAL_PHYSICAL_PROJECT_COUNT',
            'fully_verified_national_census':False,
            'national_screen_index_n':len(screen_rows),'screen_index_linked_selections_n':sum(r['selection_entity_id'] is not None for r in screen_rows),
            'native_identity_statuses':{s:sum(r['status']==s for r in identity['ledger']) for s in sorted({r['status'] for r in identity['ledger']})},
            'document_supported_identity_links':len(identity['accepted']),'primary_study_cases_n':len(cases),
            'full_evidence_n':sum(c['full_evidence'] for c in prepared['coverage']),
            'r_results':results,'r_skipped':args.skip_r,'acquisition':acquisition,
            'aim_a': ('SEPARATE_RESOURCE_INFRASTRUCTURE_STUDY_AND_ENDPOINT_CASE_PANELS_NOT_SIX_DOMAIN' if results else 'COVERAGE_ONLY'),
            'aim_b': ('SCENARIO_METHOD_WEIGHT_ROUNDING_COHORT_SCREEN_20_AND_PILOT' if results.get('official_wa_resource_screen',{}).get('status')=='COMPLETED' else 'NOT_RUN'),
            'cohort_sensitivity': 'NOT_ESTIMABLE_AFTER_DELETION_N_LT_2' if len(resources)<3 else 'LEAVE_ONE_PROJECT_OUT',
            'aim_c': ('NATIONAL_DEPOSIT_GEOGRAPHY_AND_WA_STATUS_SCORE_ASSOCIATION_DESCRIPTIVE_NOT_CAUSAL'
                      if deposit_gis else 'EXTERNAL_INFERENCE_NOT_COMPLETED_INSUFFICIENT_SAMPLE_AND_PREDICTORS'),
            'open_review_issues':sum(r['status']=='OPEN' for r in issues),'limitations':config['limitations'],
            'independent_human_approval':'NOT_CLAIMED','output_dir':str(out)}
        import shapely, pyproj, pypdf
        summary['environment']={'python':platform.python_version(),'shapely':shapely.__version__,
                                'pyproj':pyproj.__version__,'PROJ':pyproj.proj_version_str,
                                'pypdf':pypdf.__version__}
        if args.compare_to:
            from .analysis import compare_runs
            summary['comparison']=compare_runs(args.compare_to,out)
        output_hashes={p.relative_to(out).as_posix():filehash(p) for p in sorted(out.rglob('*')) if p.is_file()}
        summary['output_hashes']=output_hashes
        (out/'summary.json').write_text(json.dumps(summary,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
        report=['# AU_REE_V2 research run',f"Cutoff: {args.as_of}",f"Run: {run_id}",
                '## Verified coverage',canonical(by_kind),f'Resource-defined sample: {len(resources)}',
                f"Full-evidence sample: {summary['full_evidence_n']}",
                f"WA government resource screen (exploratory): {summary['official_summary_screen_n']}",
                'The WA government screen uses two related resource variables, not a six-domain C1 ranking.',
                '## Research interpretation',
                summary['aim_a'],summary['aim_b'],summary['aim_c'],
                'Weight scenarios are researcher assumptions. Rank frequencies are not development success probabilities.',
                'Each compared resource scope is explicit. The pilot does not establish latest project totals or a national ranking.',
                '## Limitations',*['- '+s for s in config['limitations']]]
        (out/'REPORT.md').write_text('\n\n'.join(report)+'\n',encoding='utf-8')
        db.execute("UPDATE runs SET status='COMPLETED' WHERE run_id=?",(run_id,))
        db.commit()
        (work/'latest.json').write_text(json.dumps(summary,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
        return summary
    except Exception as exc:
        db.rollback()
        db.execute("UPDATE runs SET status='FAILED',error=? WHERE run_id=?",(str(exc),run_id))
        db.commit()
        (out/'failure.json').write_text(json.dumps({'run_id':run_id,'error':str(exc)},indent=2),encoding='utf-8')
        raise
    finally:
        db.close()

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('module',choices=['all','bootstrap','acquire','evidence','gis','analyze','rebuild','diff','discover','pdf-extract'])
    parser.add_argument('--root',default='.')
    parser.add_argument('--work')
    parser.add_argument('--as-of',default=datetime.now(timezone.utc).date().isoformat())
    parser.add_argument('--project',help='Stable native project registry ID')
    parser.add_argument('--refresh',action='store_true')
    parser.add_argument('--dry-run',action='store_true')
    parser.add_argument('--skip-r',action='store_true')
    parser.add_argument('--rscript')
    parser.add_argument('--snapshot-lock',help='Exact immutable snapshot_lock.json from a prior run')
    parser.add_argument('--compare-to',help='Frozen prior run/results folder for coverage and rank comparison')
    parser.add_argument('--source-key');parser.add_argument('--pages',default='1');parser.add_argument('--tessdata')
    parser.add_argument('--before');parser.add_argument('--after')
    args=parser.parse_args()
    try:
        if args.module=='diff':
            if not args.before or not args.after:
                parser.error('diff requires --before and --after logical_database.json')
            before=json.loads(Path(args.before).read_text(encoding='utf-8'));after=json.loads(Path(args.after).read_text(encoding='utf-8'))
            result={table:{'added':[json.loads(v) for v in sorted({canonical(r) for r in after[table]}-{canonical(r) for r in before[table]})],
                           'removed':[json.loads(v) for v in sorted({canonical(r) for r in before[table]}-{canonical(r) for r in after[table]})]} for table in before}
        else:
            result=execute(args)
        print(json.dumps(result,ensure_ascii=False,indent=2))
    except Exception as exc:
        print(str(exc),file=sys.stderr)
        sys.exit(1)
