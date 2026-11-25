"""One entrypoint; independent stages share one database and run contract."""
import argparse
import json
import subprocess
import sys
import uuid
import platform
from datetime import date, datetime, timezone, timedelta
from .hierarchy import build as build_hierarchy, rows as hierarchy_rows
from .resolution import resolve,technical_coverage
from .studies import ingest as ingest_cases
from .screen_index import rows as screen_index_rows
from pathlib import Path
from . import __version__
from .acquisition import select_snapshots
from .analysis import prepare, run_r
from .tabular import write_csv
from .evidence import ingest_sources, ingest_claims, resource_values, strict_claims
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
    if not snapshot_lock and (root/'config/eligibility_compatibility.json').exists():
        config['eligibility_evidence']=json.loads((root/'config/eligibility_compatibility.json').read_text())
    if config.get('evidence_resolution',{}).get('technical_disclosure'):
        config['criteria']=[dict(c,variable='technical_disclosure_pct',
            interpretation='Technical Disclosure Transparency; not technical feasibility/performance',
            definition_version='technical-disclosure-transparency-v1') if c['code']=='T1' else c for c in config['criteria']]
    return config


def recognition_registry(root, work, snapshots, config):
    """Current recognition and acquisition share the committed SQLite registry."""
    import sqlite3
    from .pdf_extract import project_registry
    store=(Path(work).resolve() if work else root/'work/phase5')/'canonical.sqlite'
    if not config.get('candidate_version') or not store.is_file():return None
    db=sqlite3.connect(store.as_uri()+'?mode=ro',uri=True,timeout=30);db.row_factory=sqlite3.Row
    try:return project_registry(root,db,snapshots)
    finally:db.close()


def source_mode(args):
    """Resolve mutually exclusive input modes independently of output options."""
    offline=bool(getattr(args,'source_replay',None) or getattr(args,'static_pdfs',()))
    requested=getattr(args,'source_mode',None)
    if (offline or getattr(args,'census_filter',[]) or requested) and args.module!='all':
        raise ValueError('Census source modes and filters require all')
    if args.refresh and args.module not in ('all','acquire'):
        raise ValueError('Use all --refresh for the shared acquisition stage')
    supplied=[mode for present,mode in ((offline,'offline'),(args.refresh,'live'),
                                        (bool(args.snapshot_lock),'frozen')) if present]
    if len(supplied)>1 or (requested and supplied and requested!=supplied[0]):
        raise ValueError('Live, offline and frozen sources cannot be combined')
    mode=requested or (supplied[0] if supplied else 'legacy')
    if mode in ('offline','frozen') and not supplied:
        raise ValueError(f'{mode} mode requires its source replay, static library or snapshot lock')
    if args.module=='acquire' and args.snapshot_lock:
        raise ValueError('Acquisition cannot use a frozen snapshot lock')
    if args.module=='all' and not requested and not supplied and (
            getattr(args,'out',None) or getattr(args,'census_filter',[])):
        raise ValueError('Census output and filters require an offline, live or frozen source mode')
    return mode


def execute(args):
    root=Path(args.root).resolve()
    if args.module=='experiment':
        from .experiments import run_experiment
        if not getattr(args,'experiment_config',None):
            raise ValueError('experiment requires --experiment-config')
        return run_experiment(root,args.experiment_config,getattr(args,'out',None),
                              dry_run=getattr(args,'dry_run',False))
    if args.module=='export-summary':
        from .census import export_summary
        if not args.database or not args.out:raise ValueError('export-summary requires --database and --out')
        return export_summary(root,args.database,args.out,replay_assets=getattr(args,'replay_assets',None))
    source_replay=getattr(args,'source_replay',None)
    static_pdfs=getattr(args,'static_pdfs',())
    census_filters=getattr(args,'census_filter',[])
    mode=source_mode(args)
    replay_assets=getattr(args,'replay_assets',None)
    if replay_assets and not source_replay:
        raise ValueError('--replay-assets requires --source-replay')
    integration=args.module=='all' and (
        mode in ('offline','live') or (mode=='frozen' and getattr(args,'source_mode',None)=='frozen'))
    if args.module=='all' and mode=='frozen' and not integration and (getattr(args,'out',None) or census_filters):
        raise ValueError('Use --source-mode frozen to publish or filter Census from a frozen lock')
    config=research_configuration(root,args.snapshot_lock)
    strict=integration and mode in ('offline','live')
    if not (strict or args.module=='acquire') and config.get('research_evidence_cutoff'):
        args.as_of=min(args.as_of,config['research_evidence_cutoff'])
    acquired_through=config.get('acquisition_through') if args.as_of==config.get('research_evidence_cutoff') else None
    registry=json.loads((root/'config/sources.json').read_text(encoding='utf-8'))
    date.fromisoformat(args.as_of)
    if args.as_of > datetime.now(timezone(timedelta(hours=8))).date().isoformat():
        raise ValueError('Future cutoff is not supported')
    if args.dry_run:
        return {'status':'DRY_RUN','module':args.module,'cutoff':args.as_of,'root':str(root),
                'source_mode':mode,'strict_census_validation':strict,'writes':False}
    if args.module=='register-candidate':
        from .evidence import load_claims,register_candidate
        if not args.registration:raise ValueError('register-candidate requires --registration')
        snapshots=select_snapshots(root,args.as_of)
        work=Path(args.work or root/'work/phase5');db=connect(work/'canonical.sqlite')
        try:
            claims,old_sha=load_claims(root,freeze=True)
            registration=json.loads(Path(args.registration).read_text(encoding='utf8'))
            project,relation=register_candidate(db,root,snapshots,args.as_of,registration,claims)
            path=root/'data/identity_links.json';links=json.loads(path.read_text(encoding='utf8'))
            if relation not in links.setdefault('relations',[]):links['relations'].append(relation)
            # Existing versioned inputs; SQLite is populated by the same normal
            # ingest. No second registry, automatic C1 or eager resource scoring.
            path.write_text(json.dumps(links,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
            (root/'data/claims.json').write_text(json.dumps(claims,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
            return dict(status='SOURCE_VERIFIED_PROJECT_DECLARATION_ADOPTED',project_id='AU-'+digest([project.get('entity_namespace','project_registry_v1'),project['id']])[:20],
                candidate_id=registration['candidate_id'],relation_status=relation['relation'],
                previous_claims_sha256=old_sha,claims_sha256=filehash(root/'data/claims.json'),formal_C1=False)
        finally:db.close()
    disclosure_settings=config.get('evidence_resolution',{}).get('technical_disclosure',{})
    if not strict and not args.snapshot_lock and disclosure_settings.get('incremental_registry') and args.module in ('all','analyze','disclosure'):
        # Like the existing claims contract: active coding may grow, whereas
        # a published run must always resolve its exact adopted coding bytes.
        live=root/disclosure_settings['review_path'];sha=filehash(live)
        archive=root/'data/snapshots'/(sha+'.disclosure.json')
        if not archive.exists():archive.write_bytes(live.read_bytes())
        if filehash(archive)!=sha:raise ValueError('IMMUTABLE_DISCLOSURE_REVIEW_MISMATCH')
        disclosure_settings.update(review_path=archive.relative_to(root).as_posix(),review_sha256=sha)
    if args.module=='disclosure' and config.get('disclosure_current_baseline'):
        # Current disclosure needs current non-Technical selection as well.
        # Historical locks without this flag keep the frozen Phase19 baseline.
        args.work=args.work or str(root/'work/phase5')
        if not (Path(args.work).resolve()/'canonical.sqlite').is_file():
            raise ValueError('Require an existing canonical.sqlite')
        args.module='analyze'
    if args.module=='disclosure':
        # Deliberately reuse the current canonical store; never bootstrap a
        # second formal database for a content-analysis revision.
        work=Path(args.work).resolve() if args.work else root/'work/phase5'
        if not (work/'canonical.sqlite').is_file():raise ValueError('Require an existing canonical.sqlite')
        review_path=root/config['evidence_resolution']['technical_disclosure']['review_path']
        version=code_version(root);run_id='phase19-'+digest([filehash(review_path),config,version['content_sha256'],args.as_of])[:16]
        out=work/'runs'/run_id;out.mkdir(parents=True,exist_ok=True)
        db=connect(work/'canonical.sqlite')
        try:
            from .technical import run_disclosure
            db.execute('INSERT OR IGNORE INTO runs VALUES(?,?,?,?,?,?,?,?)',
                (run_id,datetime.now(timezone.utc).isoformat(),args.as_of,canonical(version),digest(config),filehash(review_path),'RUNNING',None))
            result,prepared,summary=run_disclosure(root,config,args.as_of,out,db,run_id)
            r_results={} if args.skip_r else run_r(root,out,prepared,config,args.rscript)
            summary.update(run_id=run_id,output_dir=str(out),R=r_results,code=version)
            (out/'summary.json').write_text(canonical(summary)+'\n',encoding='utf8')
            (out/'configuration.json').write_text(canonical({'research':config})+'\n',encoding='utf8')
            db.execute("UPDATE runs SET status='COMPLETED',error=NULL WHERE run_id=?",(run_id,));db.commit()
            return summary
        except Exception:
            db.rollback();raise
        finally:db.close()
    if args.module=='pdf-extract':
        from .pdf_extract import capture_pages
        source=next(s for s in select_snapshots(root,args.as_of) if s['key']==args.source_key)
        return {'pages':capture_pages(root,source,[int(p) for p in args.pages.split(',')],args.tessdata)}
    if args.module=='recognize':
        from .pdf_extract import capture_documents
        keys=set(args.source_key.split(',')) if args.source_key else None
        selected=select_snapshots(root,args.as_of,acquired_through=acquired_through)
        return {'documents':capture_documents(root,selected,keys,args.tessdata,
            registry=recognition_registry(root,args.work,selected,config))}
    acquisition=[];acquisition_selection=[]
    work=Path(args.work).resolve() if args.work else root/'work'
    run_id=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')+'-'+uuid.uuid4().hex[:8]
    receipt=work/'acquisition'/run_id/'source_acquisition.json' if strict else None
    acquisition_work=receipt.parent if strict and mode=='offline' else work
    if args.module=='discover':
        from .discovery import search_tasks, strict_search_plan
        discovery_config=json.loads((root/'config/discovery.json').read_text(encoding='utf-8'))
        fixed,deferred=strict_search_plan(root)
        tasks=search_tasks(root,discovery_config,diagnostics=getattr(args,'gap_report',None),record_missing=False)
        return dict(status='SEARCH_PLAN',tasks=tasks[:args.task_limit],
                    fixed_reports=[r['key'] for r in fixed['official_reports']],
                    deferred_reports=[r['key'] for r in deferred],live_entry='all --refresh',writes=False)
    if strict or args.module=='acquire':
        from .acquisition import census_acquisition
        from .evidence import load_claims
        live_claims,_=load_claims(root)
        if any(getattr(args,k,None) for k in ('source_key','gap_report')):
            raise ValueError('Use discover for targeted search planning and all --refresh for acquisition')
        snapshots,acquisition,acquisition_selection=census_acquisition(
            root,registry,acquisition_work,live_claims,args.as_of,source_replay,static_pdfs=static_pdfs,
            replay_assets=replay_assets,receipt_path=receipt)
        if args.module=='acquire':
            return dict(status='COMPLETED_WITH_SOURCE_STATUS',sources=acquisition,
                        source_selection=acquisition_selection,receipt=str(acquisition_work/'source_acquisition.json'))
    elif args.snapshot_lock:
        from .acquisition import checked_snapshots
        snapshots=json.loads(Path(args.snapshot_lock).read_text(encoding='utf-8'))
        checked_snapshots(root,snapshots,args.as_of,acquired_through or args.as_of)
    else:
        snapshots=select_snapshots(root,args.as_of,acquired_through=acquired_through)
    work.mkdir(parents=True,exist_ok=True)
    out=work/'runs'/run_id
    out.mkdir(parents=True)
    db=connect(work/'databases'/run_id/'canonical.sqlite' if integration else work/'canonical.sqlite')
    if integration:
        from .census_replay import INTEGRATED_APPLICATION_ID
        db.execute(f'PRAGMA application_id={INTEGRATED_APPLICATION_ID}')
    if strict:
        import os
        previous_cache=os.environ.get('AU_REE_NATIVE_CACHE');os.environ['AU_REE_NATIVE_CACHE']=str(out/'native-pages')
        fields=sorted({k for row in acquisition for k in row})
        write_csv(out/'acquisition_report.csv',sorted(acquisition,key=lambda r:(r['host'],r['key'])),fields)
        from .acquisition import SOURCE_SELECTION_FIELDS
        write_csv(out/'source_selection.csv',acquisition_selection,SOURCE_SELECTION_FIELDS)
        from .acquisition import STRICT_HOSTS
        from collections import Counter
        groups={}
        for row in acquisition:
            group=STRICT_HOSTS.get(row['host'],'unapproved');groups.setdefault(group,{}).setdefault(row['host'],Counter())[row['status']]+=1
        lines=['# Acquisition by host class (source attempts, not independent documents)']
        for group,hosts in sorted(groups.items()):
            lines += ['\n## '+group]+['- '+host+': '+canonical(counts) for host,counts in sorted(hosts.items())]
        (out/'acquisition_hosts.md').write_text('\n'.join(lines)+'\n',encoding='utf8')
    version=code_version(root)
    from .evidence import load_claims,claim_evidence_ids
    frozen_claims_sha=None
    if args.snapshot_lock:
        frozen_configuration=Path(args.snapshot_lock).parent/'configuration.json'
        if frozen_configuration.exists():
            frozen_claims_sha=json.loads(frozen_configuration.read_text(encoding='utf-8')).get('claims_sha256')
    claim_declarations,claims_sha=load_claims(root,frozen_claims_sha,freeze=not args.snapshot_lock and not strict)
    claims_data=claim_declarations
    if strict:claims_data=strict_claims(db,root,snapshots,claim_declarations,acquisition,out/'verified-pages',args.tessdata)
    active_claim_ids=claim_evidence_ids(claims_data)
    configuration={'research':config,'sources':registry,'claims_sha256':claims_sha}
    if integration:
        from .runtime import analytical_runtime
        configuration.update(census_filter=list(census_filters),source_mode=mode,
                             analytical_runtime=analytical_runtime(root,args.tessdata,args.rscript))
        gap_policy = root/'config/census_gap_review.json'
        if gap_policy.is_file() and args.as_of == json.loads(gap_policy.read_bytes())['cutoff']:
            configuration['census_gap_review_sha256'] = filehash(gap_policy)
    if strict:configuration['verified_claim_ids']=sorted(active_claim_ids)
    for name in ('identity_links.json','study_cases.json'):
        if (root/'data'/name).exists():configuration[name+'_sha256']=filehash(root/'data'/name)
    configuration['eligibility_policy_sha256']=filehash(root/'config/eligibility_compatibility.json')
    db.execute('INSERT INTO runs VALUES(?,?,?,?,?,?,?,?)',
        (run_id,datetime.now(timezone.utc).isoformat(),args.as_of,canonical(version),digest(configuration),
         digest(snapshots),'RUNNING',None))
    db.commit()
    try:
        ingest_sources(db,root,snapshots,config.get("commodity_version","minedex-resource-batch-v1"),config.get('candidate_version'))
        from .national import government_explicit_relations
        government_explicit_relations(db,snapshots)
        from .national import live_government_inventory,live_government_coverage,government_link_candidates
        native_current=None
        if config.get('current_view_version'):
            from .selection import current_evidence_view
            native_current=current_evidence_view(db,snapshots,args.as_of,active_claim_ids,candidate_version=config.get('candidate_version'),claims_data=claims_data)
        live_rows=live_government_inventory(db,snapshots,native_current)
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
            ingest_claims(db,root,snapshots,args.as_of,args.project,conflict_selection=bool(config.get('evidence_resolution')),claims_data=claims_data)
        recognition=[]
        if config.get('evidence_resolution',{}).get('document_pipeline') and args.module!='bootstrap':
            from .evidence import ingest_recognized
            recognition=ingest_recognized(db,root,snapshots,args.as_of,config['evidence_resolution']['document_pipeline'],acquired_through)
            (out/'document_ingestion.json').write_text(canonical(recognition)+'\n',encoding='utf-8')
            from .evidence import document_report
            document_report(root,snapshots,recognition,out,shared_comparability=bool(config['evidence_resolution'].get('technical_comparability')))
            from .resolution import document_relations
            write_csv(out/'document_entity_relations.csv',document_relations(db,root,snapshots,args.as_of),
                      ['parent_id','child_id','relation','source_sha256','locator','rule','status'])
        scope_audit=[]
        phase22_bindings=None
        if strict:
            from .evidence import phase22_resource_bindings
            phase22_bindings=phase22_resource_bindings(root)
        resources=resource_values(db,args.as_of,{s['sha256'] for s in snapshots},
            strict=bool(config.get('evidence_resolution')),active_claim_ids=active_claim_ids,
            phase22_bindings=phase22_bindings,scope_audit=scope_audit)
        if strict:
            write_csv(out/'resource_scope_selection.csv',scope_audit,
                      ['project_id','source_sha256','reason','scope','alternative_scopes'])
        from .national import resource_quality_checks
        cases=ingest_cases(db,root,snapshots,args.as_of) if args.module!='bootstrap' else []
        if config.get('evidence_resolution') and args.module!='bootstrap':
            from .evidence import ingest_events
            ingest_events(db,root,snapshots,args.as_of,claims_data=claims_data)
        current=None
        if config.get('current_view_version'):
            from .selection import current_evidence_view
            current=current_evidence_view(db,snapshots,args.as_of,active_claim_ids,config.get('evidence_resolution',{}).get('document_pipeline',{}).get('validation_version'),config.get('candidate_version'),claims_data=claims_data)
        resource_qa=resource_quality_checks(db,{s['sha256'] for s in snapshots},current)
        write_csv(out/'resource_statement_quality.csv',resource_qa,
                  ['entity_id','statement_id','scope','effective_date','source_sha256','basis',
                   'calculated_contained_kt','reported_contained_kt','rounding_lower_kt','rounding_upper_kt','status','interpretation'])
        # Register source-bound resource scopes before producing membership.
        # Otherwise fresh runs omit scopes which appear only on the next run.
        build_hierarchy(db,snapshots,collect=False,current=current)
        identity=resolve(db,root,snapshots,args.as_of,config.get('evidence_resolution',{}).get('identity_rule_version'),current=current)
        hierarchy=hierarchy_rows(db,snapshots,current)
        live_candidates=government_link_candidates(db,snapshots,identity['mapping'] if config.get('evidence_resolution',{}).get('identity_rule_version') else None,config.get('government_pairing_version'),current)
        write_csv(out/'government_identity_candidates.csv',live_candidates,
                  ['a','b','name','state','distance_m','status','source_a','source_b']+(['evidence_keys','relation_evidence','holder_dates'] if config.get('government_pairing_version') else []))
        technical_rows=technical_coverage(db,identity,resources,cases,{s['sha256'] for s in snapshots},current)
        write_csv(out/'technical_project_coverage.csv',technical_rows,['canonical_project_id','member_entity_ids','status','resource_scopes','study_case_ids','other_stage_evidence','shared_resource_context','unverified_or_other_scope_claims','interpretation'])
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
        census_coverage=None;selected_census=None
        if integration and (root/'config/summary_rules.json').is_file():
            from .census import census_selection, export_summary
            census_coverage=export_summary(root,db.execute('PRAGMA database_list').fetchone()[2],out/'project-summary',
                connection=db,run_id=run_id,configuration=configuration,snapshots=snapshots,membership=identity['membership'],
                acquisition_rows=acquisition, audit=True, claim_declarations=claim_declarations)
            selected_census=census_selection(out/'project-summary'/'專案總表.csv',identity['membership'],census_filters,out)
        results={};prepared={'panels':{},'coverage':[]};selection=None;technical_observations=None;disclosure_prepared=None;disclosure_result=None
        if args.module in ('all','analyze','rebuild'):
            if config.get('evidence_resolution'):
                from .selection import resolve as select_evidence,export as export_selection
                selection=select_evidence(db,snapshots,args.as_of,resources,cases,identity['mapping'],config['evidence_resolution'],root,acquired_through,active_claim_ids=active_claim_ids)
                export_selection(selection,out)
                if config['evidence_resolution'].get('technical_profile'):
                    from .technical import unified_observations
                    technical_observations=unified_observations(selection,config['evidence_resolution']['technical_profile'])
                disclosure_settings=config['evidence_resolution'].get('technical_disclosure')
                if disclosure_settings and (args.as_of==disclosure_settings['review_cutoff'] or
                        integration and args.as_of>disclosure_settings['review_cutoff']):
                    from .technical import run_disclosure
                    from .pdf_extract import project_registry
                    current_registry=project_registry(root,db,snapshots,identity['mapping']) if disclosure_settings.get('incremental_registry') else None
                    disclosure_result,disclosure_prepared,disclosure_summary=run_disclosure(root,config,disclosure_settings['review_cutoff'],out,db,run_id,selection,
                        assemble=not config.get('disclosure_current_baseline'),registry=current_registry,selected_snapshots=snapshots)
                elif disclosure_settings:
                    (out/'disclosure_status.json').write_text(canonical(dict(
                        status='NOT_EVALUATED_REVIEW_CUTOFF_DIFFERS',cutoff=args.as_of,
                        review_cutoff=disclosure_settings['review_cutoff'],
                        interpretation='No later disclosure coding backdated; other research continues'))+'\n',encoding='utf8')
            prepared=prepare(db,args.as_of,snapshots,resources,gis_values,config,out,args.project,identity['mapping'],cases,selection)
            if disclosure_result and config.get('disclosure_current_baseline'):
                from .analysis import current_disclosure_baseline,prepare_disclosure_analysis
                if selected_census is not None:
                    disclosure_result=dict(disclosure_result,scores=[s for s in disclosure_result['scores']
                        if identity['mapping'].get(s['project_id'],s['project_id']) in selected_census])
                baseline=current_disclosure_baseline(out,identity['mapping'],[s['project_id'] for s in disclosure_result['scores']],prepared,
                    include_bounds=bool(config.get('disclosure_source_rounding')))
                if disclosure_result['scores']:
                    disclosure_prepared,current_summary=prepare_disclosure_analysis(disclosure_result,baseline,config,out)
                else:
                    current_summary=dict(census_status='NO_SELECTED_DISCLOSURE_PROJECTS')
                disclosure_summary.update(current_summary)
                (out/'disclosure_analysis.json').write_text(canonical(disclosure_summary)+'\n',encoding='utf8')
            if disclosure_prepared:prepared['panels'].update(disclosure_prepared['panels'])
            if selection and config.get('evidence_resolution',{}).get('technical_profile',{}).get('numeric_model'):
                from .analysis import prepare_technical_panel
                prepare_technical_panel(selection,prepared,config,out,observations=technical_observations)
            if selected_census is not None:
                from .analysis import apply_census_cohort
                apply_census_cohort(out,prepared,selected_census,identity['mapping'])
            if config['monte_carlo'].get('method_version')=='entity-keyed-rng-v2':
                from .analysis import canonicalize_interchange
                canonicalize_interchange(out)
            if config.get('evidence_resolution',{}).get('document_pipeline') and selection:
                from .selection import diagnostics
                diagnostics(selection,prepared,snapshots,config['criteria'],root,out)
                if config.get('source_coverage_version')=='bounded-document-stages-v1':
                    from .discovery import source_coverage
                    source_coverage(root,snapshots,selection,prepared,out,claims_data=claims_data)
            commercial=None
            if config.get('research_utilization') and selection:
                from .analysis import prepare_commercial_coverage
                commercial=prepare_commercial_coverage(selection,out)
            if not args.skip_r:
                results=run_r(root,out,prepared,config,args.rscript)
            if config.get('research_utilization') and selection:
                from .analysis import research_readiness
                research_readiness(selection,out,config.get('research_analysis_version'),commercial)
            if selection and config.get('evidence_resolution',{}).get('technical_analysis'):
                from .technical import analyze_cells
                analyze_cells(selection,config['evidence_resolution']['technical_analysis'],db,run_id,out,{identity['mapping'].get(pid,pid) for pid in resources})
                if not args.skip_r:
                    from .technical import plot_cells
                    plot_cells(root,out,args.rscript)

        if selection and config.get('evidence_resolution',{}).get('technical_profile'):
            from .technical import analyze_profiles
            from .official import minedex_resource_report
            analyze_profiles(selection,config['evidence_resolution']['technical_profile'],out,{identity['mapping'].get(pid,pid) for pid in resources},root,snapshots,observations=technical_observations,claims_data=claims_data)
            minedex_resource_report(db,root,snapshots,out,config.get("commodity_version","minedex-resource-batch-v1"))
        source_shas={s['sha256'] for s in snapshots}
        from .national import raw_domain_coverage
        if config.get('research_analysis_version')=='evidence-cohort-v1':
            raw_domains=raw_domain_coverage(db,source_shas,config['evidence_resolution']['document_pipeline'].get('validation_version'),active_claim_ids,current)
        else:raw_domains=raw_domain_coverage(db,source_shas)
        write_csv(out/'database_domain_coverage.csv',raw_domains,
                  ['domain','evidence_status','distinct_statement_values','entities','sources','numeric_values','interpretation'])
        census=[dict(r) for r in db.execute('''SELECT e.entity_id,e.kind,r.* FROM entities e
            JOIN records r USING(entity_id) ORDER BY e.entity_id,r.source_sha''') if r['source_sha'] in source_shas and (current is None or r['entity_id'] not in current['historical_scope_ids'] and (r['entity_id'],r['source_sha']) in current['record_ids'])]
        if current is not None:
            for r in census:r.update(current.get('record_values',{}).get((r['entity_id'],r['source_sha']),{}))
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
        dimension_rows=domain_evidence_coverage(db,inventory,resources,gis_values,national_inventory,source_shas,selection,prepared,config['criteria'],current)
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
        audit_summary=audit(db,out,identity,technical_rows,prepared,config,args.as_of,snapshots,root,current,
                            integrated_census=census_coverage is not None)
        from .security import public_export
        dump=public_export(logical_dump(db))
        (out/'logical_database.json').write_text(canonical(dump)+'\n',encoding='utf-8')
        (out/'snapshot_lock.json').write_text(canonical(snapshots)+'\n',encoding='utf-8')
        (out/'configuration.json').write_text(canonical(configuration)+'\n',encoding='utf-8')
        issues=[dict(r) for r in db.execute('SELECT * FROM review_queue ORDER BY issue_id')]
        write_csv(out/'review_queue.csv',issues,['issue_id','entity_id','source_sha','reason','details','status'])
        by_kind={}
        for kind in {r['entity_id']:r['kind'] for r in census}.values():
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
        if census_coverage is not None:
            from .census_release import write_release_contract
            from .census_sensitivity import compare_gis_points
            census_coverage.update(database_run_id=run_id,logical_database_sha256=summary['logical_database_sha256'])
            (out/'project-summary'/'coverage.json').write_text(canonical(census_coverage)+'\n',encoding='utf8')
            summary['project_summary']=census_coverage
            summary['census_filter']=list(census_filters)
            summary['census_mcda_candidates']=len(selected_census)
            compare_gis_points(db,root,out,run_id,snapshots,gis_values,identity,config,prepared['panels'])
            write_release_contract(root,out,run_id,mode,args.as_of,version,configuration,
                snapshots,receipt,prepared,results,selected_census,identity)
            if receipt:summary['source_acquisition_receipt']=str(receipt)
        elif args.module=='all' and (root/'config/summary_rules.json').is_file():
            from .census import export_summary
            summary['project_summary']=export_summary(root,db.execute('PRAGMA database_list').fetchone()[2],
                out/'project-summary',connection=db,run_id=run_id,configuration=configuration,snapshots=snapshots)
        if args.compare_to:
            from .analysis import compare_runs
            summary['comparison']=compare_runs(args.compare_to,out)
        output_hashes={p.relative_to(out).as_posix():filehash(p) for p in sorted(out.rglob('*')) if p.is_file()}
        summary['output_hashes']=output_hashes
        summary['execution_artifacts']=[name for name in output_hashes if Path(name).name in ('R.log','r_cache.json','R_cohort.log','r_cohort_cache.json')]
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
        if census_coverage is not None:
            from .census import publish_census
            published=publish_census(root,out,run_id,getattr(args,'out',None))
            summary['project_census_csv']=str(published)
        (out/'summary.json').write_text(json.dumps(summary,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
        db.execute("UPDATE runs SET status='COMPLETED' WHERE run_id=?",(run_id,))
        db.commit()
        if census_coverage is not None and strict:
            alias=work/f'.source_acquisition-{run_id}.json'
            alias.write_bytes(receipt.read_bytes())
            alias.replace(work/'source_acquisition.json')
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
        if strict:
            if previous_cache is None:os.environ.pop('AU_REE_NATIVE_CACHE',None)
            else:os.environ['AU_REE_NATIVE_CACHE']=previous_cache

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('module',choices=['all','bootstrap','acquire','evidence','gis','analyze','rebuild','diff','discover','pdf-extract','recognize','disclosure','register-candidate','export-summary','experiment'])
    parser.add_argument('--root',default='.')
    parser.add_argument('--work')
    parser.add_argument('--database');parser.add_argument('--out')
    parser.add_argument('--experiment-config',help='Versioned research experiment definition; independent of formal source modes')
    parser.add_argument('--as-of',default=datetime.now(timezone.utc).date().isoformat())
    parser.add_argument('--project',help='Stable native project registry ID')
    parser.add_argument('--refresh',action='store_true')
    parser.add_argument('--source-mode',choices=['offline','live','frozen'],
                        help='Census source mode; legacy --refresh/replay/lock options also select it')
    parser.add_argument('--dry-run',action='store_true')
    parser.add_argument('--skip-r',action='store_true')
    parser.add_argument('--rscript')
    parser.add_argument('--snapshot-lock',help='Exact immutable snapshot_lock.json from a prior run')
    parser.add_argument('--source-replay',help='Replay a saved source_acquisition.json and its SHA-verified originals')
    parser.add_argument('--replay-assets',help='Local SHA-named asset directory for missing replay inputs')
    parser.add_argument('--static-pdfs',action='append',default=[],metavar='DIRECTORY',
                        help='Read registered PDF originals from a local library by SHA, with no network')
    parser.add_argument('--census-filter',action='append',default=[],metavar='COLUMN=VALUE',
                        help='Filter MCDA through the census, with OR within a column and AND across columns')
    parser.add_argument('--compare-to',help='Frozen prior run/results folder for coverage and rank comparison')
    parser.add_argument('--source-key');parser.add_argument('--pages',default='1');parser.add_argument('--tessdata')
    parser.add_argument('--registration',help='Source-bound native candidate Project declaration in existing claims format')
    parser.add_argument('--gap-report',help='Existing evidence_pipeline_diagnostics.csv for bounded acquisition')
    parser.add_argument('--task-limit',type=int,default=3)
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
        if args.module=='experiment' and result.get('status')=='BLOCKED' and not args.dry_run:
            sys.exit(2)
    except Exception as exc:
        print(str(exc),file=sys.stderr)
        sys.exit(1)
