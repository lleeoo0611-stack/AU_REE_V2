"""One entrypoint; independent stages share one database and run contract."""
import argparse
import json
import subprocess
import sys
import uuid
import platform
from datetime import date, datetime, timezone
from pathlib import Path
from . import __version__
from .acquisition import refresh, select_snapshots
from .analysis import prepare, run_r, write_csv
from .evidence import ingest_sources, ingest_claims, resource_values
from .gis import run as run_gis
from .store import canonical, connect, digest, filehash, logical_dump

def code_version(root):
    try:
        commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True,stderr=subprocess.DEVNULL).strip()
    except (OSError,subprocess.CalledProcessError):
        commit='UNCOMMITTED'
    files=sorted([*Path(root).glob('src/**/*.py'),*Path(root).glob('R/*.R')])
    return {'package':__version__,'commit':commit,
            'content_sha256':digest({p.relative_to(root).as_posix():filehash(p) for p in files})}

def execute(args):
    root=Path(args.root).resolve()
    config=json.loads((root/'config/research.json').read_text(encoding='utf-8'))
    registry=json.loads((root/'config/sources.json').read_text(encoding='utf-8'))
    date.fromisoformat(args.as_of)
    if args.as_of > datetime.now(timezone.utc).date().isoformat():
        raise ValueError('Future cutoff is not supported')
    if args.snapshot_lock and args.refresh:
        raise ValueError('--snapshot-lock cannot be combined with --refresh')
    if args.dry_run:
        return {'status':'DRY_RUN','module':args.module,'cutoff':args.as_of,'root':str(root),
                'snapshot_count':len(select_snapshots(root,args.as_of)), 'writes':False}
    acquisition=[]
    if args.module=='acquire' or args.refresh:
        acquisition=refresh(root,registry)
        if args.module=='acquire':
            return {'status':'COMPLETED_WITH_SOURCE_STATUS','sources':acquisition}
    snapshots=select_snapshots(root,args.as_of)
    if args.snapshot_lock:
        snapshots=json.loads(Path(args.snapshot_lock).read_text(encoding='utf-8'))
        for s in snapshots:
            if s['available_date']>args.as_of or s.get('publication_date','')>args.as_of:
                raise ValueError('Snapshot lock contains evidence after cutoff')
            if filehash(root/s['path'])!=s['sha256']:
                raise ValueError('Locked snapshot checksum mismatch')
    work=Path(args.work).resolve() if args.work else root/'work'
    work.mkdir(parents=True,exist_ok=True)
    run_id=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')+'-'+uuid.uuid4().hex[:8]
    out=work/'runs'/run_id
    out.mkdir(parents=True)
    db=connect(work/'canonical.sqlite')
    version=code_version(root)
    configuration={'research':config,'sources':registry,'claims_sha256':filehash(root/'data/claims.json')}
    db.execute('INSERT INTO runs VALUES(?,?,?,?,?,?,?,?)',
        (run_id,datetime.now(timezone.utc).isoformat(),args.as_of,canonical(version),digest(configuration),
         digest(snapshots),'RUNNING',None))
    db.commit()
    try:
        ingest_sources(db,root,snapshots)
        if args.module!='bootstrap':
            ingest_claims(db,root,snapshots,args.as_of,args.project)
        resources=resource_values(db,args.as_of,{s['sha256'] for s in snapshots})
        gis_values={}
        if args.module in ('all','gis','analyze','rebuild'):
            gis_values=run_gis(db,root,snapshots,run_id,resources)
        results={};prepared={'panels':{},'coverage':[]}
        if args.module in ('all','analyze','rebuild'):
            prepared=prepare(db,args.as_of,snapshots,resources,gis_values,config,out,args.project)
            if not args.skip_r:
                results=run_r(root,out,prepared,config,args.rscript)
        source_shas={s['sha256'] for s in snapshots}
        census=[dict(r) for r in db.execute('''SELECT e.entity_id,e.kind,r.* FROM entities e
            JOIN records r USING(entity_id) ORDER BY e.entity_id,r.source_sha''') if r['source_sha'] in source_shas]
        write_csv(out/'census.csv',census,['entity_id','kind','name','state','longitude','latitude','deposit_type','activity','source_sha'])
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
        dump=logical_dump(db)
        (out/'logical_database.json').write_text(canonical(dump)+'\n',encoding='utf-8')
        (out/'snapshot_lock.json').write_text(canonical(snapshots)+'\n',encoding='utf-8')
        (out/'configuration.json').write_text(canonical(configuration)+'\n',encoding='utf-8')
        issues=[dict(r) for r in db.execute('SELECT * FROM review_queue ORDER BY issue_id')]
        write_csv(out/'review_queue.csv',issues,['issue_id','entity_id','source_sha','reason','details','status'])
        by_kind={}
        for eid in {r['entity_id'] for r in census}:
            kind=next(r['kind'] for r in census if r['entity_id']==eid)
            by_kind[kind]=by_kind.get(kind,0)+1
        summary={'run_id':run_id,'status':'COMPLETED','cutoff':args.as_of,'module':args.module,
            'code':version,'configuration_sha256':digest(configuration),'snapshot_sha256':digest(snapshots),
            'logical_database_sha256':digest(dump),'source_count':len(snapshots),'census_by_kind':by_kind,
            'resource_defined_n':len(resources),'development_n':sum(c['development'] for c in prepared['coverage']),
            'full_evidence_n':sum(c['full_evidence'] for c in prepared['coverage']),
            'r_results':results,'r_skipped':args.skip_r,'acquisition':acquisition,
            'aim_a': 'RESOURCE_INFRASTRUCTURE_PILOT_ONLY' if results else 'COVERAGE_ONLY',
            'aim_b': 'WEIGHTS_ROUNDING_METHOD_FUNCTION_PILOT' if results else 'NOT_RUN',
            'cohort_sensitivity': 'NOT_ESTIMABLE_AFTER_DELETION_N_LT_2' if len(resources)<3 else 'LEAVE_ONE_PROJECT_OUT',
            'aim_c': 'EXTERNAL_INFERENCE_NOT_COMPLETED_INSUFFICIENT_SAMPLE_AND_PREDICTORS',
            'open_review_issues':len(issues),'limitations':config['limitations'],
            'independent_human_approval':'NOT_CLAIMED','output_dir':str(out)}
        import shapely, pyproj, pypdf
        summary['environment']={'python':platform.python_version(),'shapely':shapely.__version__,
                                'pyproj':pyproj.__version__,'PROJ':pyproj.proj_version_str,
                                'pypdf':pypdf.__version__}
        output_hashes={p.relative_to(out).as_posix():filehash(p) for p in sorted(out.rglob('*')) if p.is_file()}
        summary['output_hashes']=output_hashes
        (out/'summary.json').write_text(json.dumps(summary,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
        report=['# AU_REE_V2 research run',f"Cutoff: {args.as_of}",f"Run: {run_id}",
                '## Verified coverage',canonical(by_kind),f'Resource-defined sample: {len(resources)}',
                f"Full-evidence sample: {summary['full_evidence_n']}",'## Research interpretation',
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
    parser.add_argument('module',choices=['all','bootstrap','acquire','evidence','gis','analyze','rebuild','diff'])
    parser.add_argument('--root',default='.')
    parser.add_argument('--work')
    parser.add_argument('--as-of',default=datetime.now(timezone.utc).date().isoformat())
    parser.add_argument('--project',help='Stable native project registry ID')
    parser.add_argument('--refresh',action='store_true')
    parser.add_argument('--dry-run',action='store_true')
    parser.add_argument('--skip-r',action='store_true')
    parser.add_argument('--rscript')
    parser.add_argument('--snapshot-lock',help='Exact immutable snapshot_lock.json from a prior run')
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
