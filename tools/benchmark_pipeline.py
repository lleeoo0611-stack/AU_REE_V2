"""Same-environment, frozen-input pipeline benchmark; validation workspaces only."""
import argparse
import json
import pstats
import time
from pathlib import Path


def run():
    parser=argparse.ArgumentParser()
    parser.add_argument('--label',required=True)
    parser.add_argument('--rounds',type=int,default=3)
    parser.add_argument('--start',type=int,default=0)
    parser.add_argument('--runtime',help='Frozen source directory for before measurements')
    parser.add_argument('--resolution-only',action='store_true',help='Isolated same-database resolution diagnostic with SQL rows/peak memory')
    parser.add_argument('--r-only',action='store_true',help='Cold/warm R-stage benchmark on the actual current cohort')
    parser.add_argument('--run',default='work/phase5/latest.json')
    parser.add_argument('--skip-r',action='store_true')
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    output=root/'work/phase21'/args.label
    output.mkdir(parents=True,exist_ok=True)
    if args.r_only:
        import shutil
        from au_ree_v2.analysis import run_r,mcda_cache_contract
        from au_ree_v2.store import digest,filehash
        receipt=json.loads((root/args.run).read_text(encoding='utf8'));source=Path(receipt['output_dir'])
        config=json.loads((source/'configuration.json').read_text(encoding='utf8'))['research']
        panels={p:r['n'] for p,r in receipt['r_results'].items() if r['status']=='COMPLETED'}
        interchange=output/'interchange';interchange.mkdir(exist_ok=True)
        for p in panels:
            (interchange/p).mkdir(exist_ok=True)
            for name in ('matrix.csv','criteria.csv','weights.csv'):shutil.copy2(source/p/name,interchange/p/name)
        shutil.copy2(source/'commercial_project_coverage.csv',interchange/'commercial_project_coverage.csv')
        original={p:json.loads((source/p/'r_cache.json').read_text()) for p in panels};measurements=[]
        expected=None;cache_root=(root/'work/cache/mcda').resolve()
        for iteration in range(args.rounds):
            for p,metadata in original.items():
                contract=mcda_cache_contract(root,interchange,p,config,metadata['contract']['R'])
                if digest(contract)!=metadata['key']:raise ValueError('R benchmark differs from sealed inputs')
                cache=cache_root/metadata['key'];destination=output/'cold-cache-backups'/str(iteration)/metadata['key']
                if cache.is_dir():
                    if not cache.resolve().is_relative_to(cache_root) or not destination.resolve().is_relative_to(output.resolve()):raise ValueError('Unsafe cache archive path')
                    destination.parent.mkdir(parents=True,exist_ok=True);cache.rename(destination)
            for mode in ('cold','warm','unrelated_metadata_increment'):
                if mode=='unrelated_metadata_increment':(interchange/'unrelated-source-metadata.json').write_text('{"not_an_R_input":true}')
                started=time.perf_counter();result=run_r(root,interchange,dict(panels=panels),config,'C:/Program Files/R/R-4.5.2/bin/Rscript.exe')
                signature=digest({str(p.relative_to(interchange)):filehash(p) for p in sorted(interchange.glob('*/*.csv'))})
                if expected is None:expected=signature
                if expected!=signature:raise ValueError('R cache changed scientific output bytes')
                measurements.append(dict(iteration=iteration,mode=mode,seconds=time.perf_counter()-started,
                    computed=sum(r.get('cache_status')=='COMPUTED_AND_CACHED' for r in result.values()),
                    reused=sum(r.get('cache_status')=='REUSED_VERIFIED' for r in result.values()),scientific_sha256=signature))
                (output/'r_measurements.json').write_text(json.dumps(measurements,indent=2),encoding='utf8')
                print(json.dumps(measurements[-1]),flush=True)
        return
    if args.resolution_only:
        import sqlite3,shutil,ctypes,os
        from au_ree_v2.resolution import resolve
        from au_ree_v2.store import canonical,digest
        base=next((root/'work/phase21/before/0/runs').iterdir())
        snapshots=json.loads((base/'snapshot_lock.json').read_text(encoding='utf8'))
        target=output/'resolution-validation.sqlite'
        shutil.copyfile(base.parent.parent/'canonical.sqlite',target)
        counter=dict(selects=0,returned_rows=0)
        class Cursor(sqlite3.Cursor):
            def __iter__(self):
                while True:
                    row=super().fetchone()
                    if row is None:break
                    counter['returned_rows']+=1;yield row
            def fetchall(self):
                rows=super().fetchall();counter['returned_rows']+=len(rows);return rows
            def fetchone(self):
                row=super().fetchone();counter['returned_rows']+=row is not None;return row
        class Connection(sqlite3.Connection):
            def execute(self,sql,parameters=()):
                if sql.lstrip().upper().startswith('SELECT'):counter['selects']+=1
                return self.cursor(factory=Cursor).execute(sql,parameters)
        db=sqlite3.connect(target,factory=Connection);db.row_factory=sqlite3.Row
        measurements=[]
        for i in range(args.rounds):
            counter.update(selects=0,returned_rows=0);started=time.perf_counter()
            policy=json.loads((base/'configuration.json').read_text(encoding='utf8'))['research'].get('evidence_resolution',{})
            result=resolve(db,root,snapshots,'2026-11-05',policy.get('identity_rule_version'))
            measurements.append(dict(round=i,seconds=time.perf_counter()-started,**counter,result_sha256=digest(result)))
        db.close();peak=None
        if os.name=='nt':
            from ctypes import wintypes
            class Memory(ctypes.Structure):
                _fields_=[('cb',wintypes.DWORD),('faults',wintypes.DWORD)]+[(n,ctypes.c_size_t) for n in ('peak','working','paged_peak','paged','nonpaged_peak','nonpaged','pagefile','pagefile_peak')]
            memory=Memory();memory.cb=ctypes.sizeof(memory)
            current=ctypes.windll.kernel32.GetCurrentProcess;current.restype=wintypes.HANDLE
            query=ctypes.windll.psapi.GetProcessMemoryInfo;query.argtypes=[wintypes.HANDLE,ctypes.POINTER(Memory),wintypes.DWORD]
            if query(current(),ctypes.byref(memory),memory.cb):peak=memory.peak
        (output/'resolution_measurements.json').write_text(canonical(dict(measurements=measurements,
            python_peak_working_set_bytes=peak,scope='Isolated resolution; identical Phase20 store and source set; no R, no network; SQL rows returned not disk pages'))+'\n',encoding='utf8')
        print(canonical(measurements));return
    import subprocess,sys,os
    receipts=json.loads((output/'measurements.json').read_text()) if (output/'measurements.json').exists() else []
    environment=dict(os.environ)
    if args.runtime:environment['PYTHONPATH']=str((root/args.runtime).resolve())+';.;tests'
    for iteration in range(args.start,args.rounds):
        work=output/str(iteration)
        environment['AU_REE_NATIVE_CACHE']=str((output/f'{iteration}-page-cache').resolve())
        for mode in ('clean','warm'):
            command=[sys.executable,'-m','cProfile','-o',str(output/f'{iteration}-{mode}.prof'),
                '-m','au_ree_v2','rebuild','--as-of','2026-11-05','--snapshot-lock',
                'results/phase20-2026-11-05/snapshot_lock.json','--work',str(work),
                '--rscript','C:/Program Files/R/R-4.5.2/bin/Rscript.exe']
            if args.skip_r:command.append('--skip-r')
            started=time.perf_counter()
            with (output/f'{iteration}-{mode}.log').open('w',encoding='utf8') as stream:
                completed=subprocess.run(command,cwd=root,stdout=stream,stderr=subprocess.STDOUT,env=environment)
            stats=pstats.Stats(str(output/f'{iteration}-{mode}.prof'))
            names={'ingest_sources','resolve','run_gis','run_disclosure','prepare',
                'prepare_disclosure_analysis','research_readiness','run_r','unified_observations',
                'national_deposit_port_distances','analyze_profiles','government_features'}
            stages=[dict(file=k[0].replace(str(root),''),line=k[1],function=k[2],calls=v[1],
                         self_seconds=v[2],cumulative_seconds=v[3])
                    for k,v in stats.stats.items() if k[2] in names or 'execute' in k[2] or 'get_text' in k[2]]
            receipt=dict(iteration=iteration,mode=mode,seconds=time.perf_counter()-started,
                exit_code=completed.returncode,stages=stages,skip_r=args.skip_r)
            receipts.append(receipt)
            (output/'measurements.json').write_text(json.dumps(receipts,indent=2),encoding='utf8')
            print(json.dumps({k:v for k,v in receipt.items() if k!='stages'}),flush=True)
            if completed.returncode:raise SystemExit(completed.returncode)


if __name__=='__main__':run()
