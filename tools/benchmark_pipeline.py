"""Same-environment, frozen-input pipeline benchmark; validation workspaces only."""
import argparse
import json
import pstats
import time
import os,sys,subprocess,shutil
from pathlib import Path


def live_descendants(inventory,root_pid,birth=None):
    """Re-root every sample: historical PIDs may now belong to unrelated apps."""
    owned={root_pid}
    while True:
        expanded=set(owned)
        for pid,parent,name in inventory:
            if parent not in owned:continue
            if birth is None:expanded.add(pid);continue
            child_born,parent_born=birth(pid),birth(parent)
            if child_born is not None and parent_born is not None and child_born>=parent_born:expanded.add(pid)
        if expanded==owned:return owned
        owned=expanded


def measure_process(command,log,root,environment=None):
    """Poll only this command's descendants; keep Python/R peaks separately.

    Windows exposes the process high-water mark, Linux /proc VmHWM. Short-lived
    children between polls may be missed; record cadence and process inventory.
    This measures offline compute/reuse, not network acquisition waiting time.
    """
    import ctypes
    if os.name=='nt':
        from ctypes import wintypes as w
        class Entry(ctypes.Structure):
            _fields_=[('size',w.DWORD),('usage',w.DWORD),('pid',w.DWORD),('heap',ctypes.c_size_t),('module',w.DWORD),('threads',w.DWORD),('ppid',w.DWORD),('priority',w.LONG),('flags',w.DWORD),('exe',w.WCHAR*260)]
        class Memory(ctypes.Structure):
            _fields_=[('cb',w.DWORD),('faults',w.DWORD)]+[(n,ctypes.c_size_t) for n in ('peak','working','paged_peak','paged','nonpaged_peak','nonpaged','pagefile','pagefile_peak')]
        kernel=ctypes.windll.kernel32
        kernel.CreateToolhelp32Snapshot.restype=w.HANDLE;kernel.CreateToolhelp32Snapshot.argtypes=[w.DWORD,w.DWORD]
        kernel.Process32FirstW.argtypes=[w.HANDLE,ctypes.POINTER(Entry)];kernel.Process32NextW.argtypes=[w.HANDLE,ctypes.POINTER(Entry)]
        kernel.OpenProcess.restype=w.HANDLE;kernel.OpenProcess.argtypes=[w.DWORD,w.BOOL,w.DWORD]
        kernel.CloseHandle.argtypes=[w.HANDLE]
        kernel.GetExitCodeProcess.argtypes=[w.HANDLE,ctypes.POINTER(w.DWORD)]
        kernel.GetProcessTimes.argtypes=[w.HANDLE]+[ctypes.POINTER(w.FILETIME)]*4
        query=ctypes.windll.psapi.GetProcessMemoryInfo;query.argtypes=[w.HANDLE,ctypes.POINTER(Memory),w.DWORD]
    process_births={}
    def processes():
        if os.name=='nt':
            handle=kernel.CreateToolhelp32Snapshot(2,0);entry=Entry();entry.size=ctypes.sizeof(entry);rows=[]
            try:
                more=kernel.Process32FirstW(handle,ctypes.byref(entry))
                while more:
                    rows.append((entry.pid,entry.ppid,entry.exe));more=kernel.Process32NextW(handle,ctypes.byref(entry))
            finally:kernel.CloseHandle(handle)
            return rows
        rows=[]
        for path in Path('/proc').iterdir():
            if not path.name.isdigit():continue
            try:
                stat=(path/'stat').read_text();end=stat.rfind(')')
                parts=stat[end+2:].split();pid=int(path.name);process_births[pid]=int(parts[19])
                rows.append((pid,int(parts[1]),stat[stat.find('(')+1:end]))
            except (OSError,ValueError,IndexError):pass
        return rows
    started=time.perf_counter();peaks=[];active_rows={};handles={};samples=0;maximum_combined=0
    def birth(pid):
        if os.name!='nt':return process_births.get(pid)
        if pid in handles:
            status=w.DWORD()
            if not handles[pid] or not kernel.GetExitCodeProcess(handles[pid],ctypes.byref(status)) or status.value!=259:
                if handles[pid]:kernel.CloseHandle(handles[pid])
                del handles[pid];active_rows.pop(pid,None);process_births.pop(pid,None)
        if pid not in handles:handles[pid]=kernel.OpenProcess(0x410,False,pid)
        if pid not in process_births:
            times=[w.FILETIME() for _ in range(4)]
            if not handles[pid] or not kernel.GetProcessTimes(handles[pid],*(ctypes.byref(t) for t in times)):return None
            process_births[pid]=(times[0].dwHighDateTime<<32)+times[0].dwLowDateTime
        return process_births[pid]
    with Path(log).open('w',encoding='utf8') as stream:
        process=subprocess.Popen(command,cwd=root,stdout=stream,stderr=subprocess.STDOUT,env=environment)
        try:
            while process.poll() is None:
                inventory=processes()
                owned=live_descendants(inventory,process.pid,birth)
                for pid in list(handles):
                    status=w.DWORD()
                    live=bool(handles[pid] and kernel.GetExitCodeProcess(handles[pid],ctypes.byref(status)) and status.value==259)
                    if pid not in owned or not live:
                        if handles[pid]:kernel.CloseHandle(handles[pid])
                        del handles[pid];active_rows.pop(pid,None);process_births.pop(pid,None)
                for pid in list(active_rows):
                    if pid not in owned:active_rows.pop(pid,None)
                combined=0
                for pid,parent,name in inventory:
                    if pid not in owned:continue
                    peak=current=0
                    if os.name=='nt':
                        handle=handles.setdefault(pid,kernel.OpenProcess(0x410,False,pid)) if pid not in handles else handles[pid]
                        memory=Memory();memory.cb=ctypes.sizeof(memory)
                        if handle and query(handle,ctypes.byref(memory),memory.cb):peak,current=memory.peak,memory.working
                    else:
                        try:
                            fields=dict(line.split(':',1) for line in (Path('/proc')/str(pid)/'status').read_text().splitlines() if ':' in line)
                            peak=int(fields.get('VmHWM','0 kB').split()[0])*1024;current=int(fields.get('VmRSS','0 kB').split()[0])*1024
                        except (OSError,ValueError):pass
                    if pid not in active_rows or active_rows[pid]['name']!=name:
                        row=dict(pid=pid,parent_pid=parent,name=name,lifetime_sequence=len(peaks)+1,peak_working_set_bytes=0)
                        peaks.append(row);active_rows[pid]=row
                    row=active_rows[pid]
                    row['peak_working_set_bytes']=max(row['peak_working_set_bytes'],peak);combined+=current
                maximum_combined=max(maximum_combined,combined);samples+=1;time.sleep(.1)
        finally:
            if os.name=='nt':
                for handle in handles.values():
                    if handle:kernel.CloseHandle(handle)
    rows=peaks
    maximum=lambda token:max((r['peak_working_set_bytes'] for r in rows if token in r['name'].casefold() and r['peak_working_set_bytes']>0),default=None)
    return dict(seconds=time.perf_counter()-started,exit_code=process.returncode,
        python_peak_working_set_bytes=maximum('python'),r_peak_working_set_bytes=max((r['peak_working_set_bytes'] for r in rows if r['name'].casefold() in ('r','r.exe','rscript','rscript.exe','rterm','rterm.exe') and r['peak_working_set_bytes']>0),default=None),
        sampled_combined_working_set_bytes=maximum_combined,poll_seconds=.1,samples=samples,processes=rows,
        tracker_version='birth-checked-live-ancestry-v3',
        scope='OFFLINE_COMMAND_AND_LIVE_DESCENDANTS; creation times reject reused parent PIDs, exited Windows handles retired; HWM observed while live; children missed between polls may be absent')


def scientific_signature(receipt):
    import csv,hashlib
    csv.field_size_limit(32*1024*1024)
    from au_ree_v2.store import digest
    run=Path(receipt['output_dir']);files={}
    current=('census.csv','entity_hierarchy.csv','project_domain_evidence.csv','database_domain_coverage.csv',
        'formal_gate_compatibility.csv','eligibility_objective_evidence.csv','technical_project_coverage.csv',
        'canonical_membership.csv','cohort_coverage.csv','value_trace.csv','disclosure_items.csv','disclosure_scores.csv',
        'resource_statement_quality.csv','government_native_entities.csv','government_identity_candidates.csv',
        'resolved_evidence.csv','criteria_resolution.csv','technical_observations.csv','commercial_project_coverage.csv',
        'technical_commercial_coverage.csv','disclosure_composite_matrix.csv')
    paths=[run/name for name in current if (run/name).is_file()]
    paths+=list(run.glob('*/*.csv'))
    for path in sorted(paths):
        with path.open(encoding='utf-8-sig',newline='') as stream:rows=list(csv.DictReader(stream))
        files[path.relative_to(run).as_posix()]=digest(sorted(json.dumps(r,sort_keys=True,ensure_ascii=False) for r in rows))
    return files


def current_suite(root,args,output):
    """Fixed final rules: three cold/warm rebuilds plus actual evidence increments.

    'Cold' means fresh SQLite and application caches, not a flushed OS cache.
    Before-increment uses actual published Phase21 sources/claims/review with
    the SAME final classifier, validation, three methods, seed and draw count.
    """
    import copy,statistics
    from au_ree_v2.store import filehash,canonical
    from au_ree_v2.cli import code_version
    lock=Path(args.snapshot_lock).resolve();configuration=json.loads(lock.with_name('configuration.json').read_text(encoding='utf8'))
    baseline=Path(args.baseline_lock).resolve();old=json.loads(baseline.with_name('configuration.json').read_text(encoding='utf8'))
    before=output/'pre-increment-input';before.mkdir(exist_ok=True)
    shutil.copy2(baseline,before/'snapshot_lock.json')
    config=copy.deepcopy(configuration);config['claims_sha256']=old['claims_sha256']
    settings=config['research']['evidence_resolution']['technical_disclosure']
    old_settings=old['research']['evidence_resolution']['technical_disclosure']
    for name in ('review_path','review_sha256'):
        if name in old_settings:settings[name]=old_settings[name]
    (before/'configuration.json').write_text(canonical(config)+'\n',encoding='utf8')
    expected=None;measurements=[];version=code_version(root)
    if args.resume and (output/'measurements.json').is_file():
        prior=json.loads((output/'measurements.json').read_text(encoding='utf8'))
        rejected=[]
        for m in prior:
            if m['mode']=='actual_source_and_coding_and_project_increment' and not m.get('isolated_old_input_cache'):
                rejected.append(dict(m,rejection='FINAL_INPUT_CACHE_ALREADY_PREPOPULATED;NOT_ACCEPTED_INCREMENT_MEASUREMENT'));continue
            run=Path(m['output_dir']);receipt=json.loads((run/'summary.json').read_text(encoding='utf8'))
            if receipt['code']['content_sha256']!=version['content_sha256'] or filehash(run/'snapshot_lock.json')!=filehash(lock):raise ValueError('Cannot resume a different scientific workload')
            signature=scientific_signature(dict(output_dir=str(run)))
            if expected is None:expected=signature
            if signature!=expected:raise ValueError('Resumed scientific outputs differ')
            measurements.append(m)
        if rejected:(output/'rejected_measurements.json').write_text(canonical(rejected)+'\n',encoding='utf8')
    cutoff=configuration['research']['research_evidence_cutoff']
    def execute(label,work,snapshot,environment):
        log=output/(label+'.log')
        command=[sys.executable,'-m','au_ree_v2','rebuild','--as-of',cutoff,
            '--snapshot-lock',str(snapshot),'--work',str(work),'--rscript',args.rscript]
        measured=measure_process(command,log,root,environment)
        if measured['exit_code']:raise RuntimeError('Benchmark command failed: '+str(log))
        receipt=json.loads((work/'latest.json').read_text(encoding='utf8'))
        if receipt['code']['content_sha256']!=version['content_sha256']:raise ValueError('Benchmark source changed')
        measured.update(label=label,run_id=receipt['run_id'],output_dir=receipt['output_dir'],
            groups=receipt['canonical_projects_n'],resource_cases=receipt['resource_defined_n'],full_six=receipt['full_evidence_n'],
            core_computed=sum(r.get('cache_status')=='COMPUTED_AND_CACHED' for r in receipt['r_results'].values()),
            core_reused=sum(r.get('cache_status')=='REUSED_VERIFIED' for r in receipt['r_results'].values()),
            cohort_computed=sum(r.get('cohort_cache_status')=='COMPUTED_AND_CACHED' for r in receipt['r_results'].values()),
            cohort_reused=sum(r.get('cohort_cache_status')=='REUSED_VERIFIED' for r in receipt['r_results'].values()))
        return measured,scientific_signature(receipt)
    for iteration in range(args.rounds):
        area=output/('isolated-round-'+str(iteration));area.mkdir(exist_ok=True)
        if (area/'after/canonical.sqlite').exists() or (area/'before/canonical.sqlite').exists():raise ValueError('Fresh benchmark round required; choose a new --out')
        environment={**os.environ,'AU_REE_MCDA_CACHE':str(area/'mcda-cache'),'AU_REE_NATIVE_CACHE':str(area/'page-cache')}
        for mode in ('cold','warm'):
            if any(m['mode']==mode and m['iteration']==iteration for m in measurements):continue
            measured,signature=execute(f'{iteration}-{mode}',area/'after',lock,environment)
            if expected is None:expected=signature
            changed=sorted(k for k in set(signature)|set(expected) if signature.get(k)!=expected.get(k))
            measured.update(mode=mode,iteration=iteration,science_files=len(signature),current_science_equal=not changed,different_files=changed)
            measurements.append(measured);(output/'measurements.json').write_text(canonical(measurements)+'\n',encoding='utf8')
            print(canonical({k:v for k,v in measured.items() if k not in ('processes',)}),flush=True)
            if changed:raise ValueError('Cold/warm current outputs differ: '+str(changed))
        # The increment must see ONLY caches of its old inputs. Sharing the
        # final cold-run cache would hide every affected-panel recomputation.
        increment_environment={**os.environ,'AU_REE_MCDA_CACHE':str(area/'increment-mcda-cache'),
            'AU_REE_NATIVE_CACHE':str(area/'increment-page-cache')}
        setup,_=execute(f'{iteration}-isolated-pre-increment-setup',area/'before',before/'snapshot_lock.json',increment_environment)
        (area/'setup.json').write_text(canonical(setup)+'\n',encoding='utf8')
        measured,signature=execute(f'{iteration}-isolated-actual-increment',area/'before',lock,increment_environment)
        changed=sorted(k for k in set(signature)|set(expected) if signature.get(k)!=expected.get(k))
        measured.update(mode='actual_source_and_coding_and_project_increment',iteration=iteration,science_files=len(signature),
            current_science_equal=not changed,different_files=changed,before_groups=setup['groups'],before_full_six=setup['full_six'],isolated_old_input_cache=True)
        if not measured['core_computed'] or not measured['core_reused']:raise ValueError('Real increment must demonstrate affected recomputation and unaffected reuse')
        measurements.append(measured);(output/'measurements.json').write_text(canonical(measurements)+'\n',encoding='utf8')
        print(canonical({k:v for k,v in measured.items() if k not in ('processes',)}),flush=True)
        if changed:raise ValueError('Increment current outputs differ from clean rebuild: '+str(changed))
    summaries={}
    for mode in sorted({r['mode'] for r in measurements}):
        rows=[r for r in measurements if r['mode']==mode];summaries[mode]={}
        for field in ('seconds','python_peak_working_set_bytes','r_peak_working_set_bytes'):
            values=[r[field] for r in rows if r[field] is not None]
            summaries[mode][field]=dict(n=len(values),median=statistics.median(values),minimum=min(values),maximum=max(values)) if values else None
    result=dict(version='phase22-fixed-workload-performance-v3-birth-checked-isolated-increment',code=version,source_lock_sha256=filehash(lock),
        baseline_lock_sha256=filehash(baseline),configuration_sha256=filehash(lock.with_name('configuration.json')),
        monte_carlo=configuration['research']['monte_carlo'],rounds=args.rounds,summary=summaries,measurements=measurements,
        interpretation='Same final code/rules, three methods and draws; app-cache cold vs verified reuse. No OS cache flush or network time in compute measurements. Setup cost retained separately. Not a speedup versus a smaller one-method/five-case workload.')
    (output/'performance.json').write_text(canonical(result)+'\n',encoding='utf8')


def method_expansion(root,args,output):
    """Separate method/output expansion from a five-to-six-case workload change."""
    import csv,statistics,math
    from au_ree_v2.store import canonical,filehash
    baseline=output/'baseline-R';baseline.mkdir(exist_ok=True)
    commit='bb7da099941eb222c3baa2537e34d137fe3fb208'
    for name in ('run_mcda.R','methods.R'):
        raw=subprocess.check_output(['git','show',commit+':R/'+name],cwd=root)
        (baseline/name).write_bytes(raw)
    measurements=[]
    for iteration in range(args.rounds):
        folders={}
        for label,release,program,expanded in (
            ('one_method_five_cases','phase21-2026-11-05',baseline/'run_mcda.R',False),
            ('three_methods_five_cases','phase21-2026-11-05',root/'R/run_mcda.R',True),
            ('three_methods_six_cases','phase22-2026-11-06',root/'R/run_mcda.R',True)):
            area=output/str(iteration)/label/'six_domain';area.mkdir(parents=True,exist_ok=True);folders[label]=area
            for name in ('matrix.csv','criteria.csv','weights.csv'):shutil.copy2(root/'results'/release/'six_domain'/name,area/name)
            command=[args.rscript,str(program),str(area),'20261102','1000','0.2','30','entity-keyed-rng-v2','evidence-cohort-v1']
            if expanded:command+=['shared-method-draws-v1','core']
            result=measure_process(command,output/(str(iteration)+'-'+label+'.log'),root)
            if result['exit_code']:raise RuntimeError('R method workload measurement failed')
            result.update(iteration=iteration,workload=label,source_sha256=filehash(program))
            measurements.append(result)
        for name in ('weight_uncertainty.csv','rounding_uncertainty.csv','ranking.csv'):
            rr=lambda label:list(csv.DictReader((folders[label]/name).open(encoding='utf-8-sig')))
            a,b=rr('one_method_five_cases'),rr('three_methods_five_cases')
            assert len(a)==len(b)
            for x,y in zip(a,b):
                assert x.keys()==y.keys()
                for k in x:
                    if x[k]==y[k]:continue
                    try:equal=math.isclose(float(x[k]),float(y[k]),rel_tol=1e-12,abs_tol=1e-12)
                    except ValueError:equal=False
                    if not equal:raise ValueError('Historical PROMETHEE/point replay changed: '+name+' '+k)
        (output/'measurements.json').write_text(canonical(measurements)+'\n',encoding='utf8')
        print('Verified R workload round '+str(iteration),flush=True)
    summaries={}
    for label in sorted({r['workload'] for r in measurements}):
        summaries[label]={}
        for field in ('seconds','r_peak_working_set_bytes'):
            values=[r[field] for r in measurements if r['workload']==label and r[field] is not None]
            summaries[label][field]=dict(median=statistics.median(values),minimum=min(values),maximum=max(values),n=len(values)) if values else None
    result=dict(baseline_commit=commit,rounds=args.rounds,promethee_legacy_distributions_preserved=True,
        point_scores_and_ranks_on_fixed_five_cases_preserved=True,summary=summaries,measurements=measurements,
        interpretation='One panel, same seed1000draws and fixed original5 inputs for method expansion; third workload adds sixth case. Three-method measurements include shared-draw export overhead; not a pipeline speedup.')
    (output/'method_expansion.json').write_text(canonical(result)+'\n',encoding='utf8')


def observation_suite(root, args, output):
    """Measure cross-process reuse and check complete shadow artifacts on fixed inputs."""
    from collections import Counter
    from statistics import median

    from au_ree_v2.store import canonical, filehash

    originals = Path(args.originals).resolve()
    if not originals.is_dir() or args.rounds < 2:
        raise ValueError('Provide a SHA-named original directory and at least two benchmark rounds')
    scoped_root = output / 'changed-use-policy'
    if any((output / name).exists() for name in ('round-0', scoped_root.name)):
        raise ValueError('Use a new output directory for an isolated benchmark')
    runtime = output / 'runtime'
    shutil.copytree(root / 'src/au_ree_v2', runtime / 'au_ree_v2', ignore=shutil.ignore_patterns('__pycache__'))
    base_environment = {**os.environ, 'PYTHONPATH': str(runtime) + os.pathsep + os.environ.get('PYTHONPATH', '')}
    # Only the synthetic policy changes. Source inputs and application code are shared.
    config = scoped_root / 'config'
    ontology = config / 'ontology'
    ontology.mkdir(parents=True)
    (scoped_root / 'results').symlink_to(root / 'results', target_is_directory=True)
    (config / 'evidence_policy.json').symlink_to(root / 'config/evidence_policy.json')
    profile_path = 'shadow_profiles_v1.json'
    for path in (root / 'config/ontology').iterdir():
        if path.name != profile_path:
            (ontology / path.name).symlink_to(path, target_is_directory=path.is_dir())
    profiles = json.loads((root / 'config/ontology' / profile_path).read_bytes())
    profiles['profiles']['WITHIN_TABLE_ELEMENT_LEACH']['required_context'].append('deposit_id')
    (ontology / profile_path).write_text(canonical(profiles) + '\n', encoding='utf-8')

    files = ('decisions.jsonl', 'relationship_candidates.jsonl', 'comparison.json')
    measurements = []

    def execute(area, mode, *, chosen_root=root, asset_root=originals, cache=None, cache_mode='use', extra=(),
                environment=None):
        dest = area / mode
        if cache is None:
            cache = area / 'disabled-cache'
        command = [sys.executable, '-m', 'au_ree_v2', 'semantic-ablation', '--root', str(chosen_root),
                   '--shadow-originals', str(asset_root), '--shadow-output', str(dest),
                   '--cache-dir', str(cache), '--cache-mode', cache_mode, *extra]
        run = measure_process(command, area / f'{mode}.log', root, environment or base_environment)
        if run['exit_code']:
            raise RuntimeError(f'Observation benchmark failed, see {area / (mode + ".log")}')
        cache_files = [path.stat() for path in cache.rglob('*') if path.is_file()]
        cache_bytes = sum(file.st_size for file in cache_files)
        allocated_bytes = sum(getattr(file, 'st_blocks', 0) * 512 or file.st_size for file in cache_files)
        signature = {name: filehash(dest / name) for name in files}
        engineering = json.loads((dest / 'engineering.json').read_bytes())
        cache_receipt = dest / 'cache_run.json'
        log = (area / f'{mode}.log').read_text(encoding='utf-8').strip()
        summary = json.loads(log[log.rfind('\n{') + 1:])
        measurement = {'mode': mode, 'science_sha256': signature, 'cache_bytes': cache_bytes,
                       'cache_allocated_bytes': allocated_bytes, 'cache_files': len(cache_files),
                       'engineering': engineering, 'cache_counts': summary.get('cache_counts'),
                       'command': command, 'output_dir': str(dest), **run}
        if cache_receipt.is_file():
            receipt = json.loads(cache_receipt.read_bytes())
            measurement['cache_receipt_sha256'] = filehash(cache_receipt)
            measurement['stage_seconds'] = receipt['stage_seconds']
            measurement['cache_reasons'] = dict(Counter(
                event['reason'] for event in receipt['events'] if 'reason' in event))
        measurements.append(measurement)
        (output / 'measurements.json').write_text(canonical(measurements) + '\n', encoding='utf-8')
        print(f'{area.name} {mode}: {run["seconds"]:.2f}s; cache bytes {cache_bytes}', flush=True)
        return signature

    baseline = None
    changed = None
    for iteration in range(args.rounds):
        area = output / f'round-{iteration}'
        area.mkdir()
        cache = area / 'cache'
        signatures = {
            'disabled': execute(area, 'disabled', cache_mode='off'),
            'cold': execute(area, 'cold', cache=cache),
            'warm': execute(area, 'warm', cache=cache),
            'rule_increment': execute(area, 'rule_increment', chosen_root=scoped_root, cache=cache),
            'rule_full': execute(area, 'rule_full', chosen_root=scoped_root, cache_mode='off'),
        }
        baseline = baseline or signatures['disabled']
        changed = changed or signatures['rule_full']
        if any(signatures[mode] != baseline for mode in ('disabled', 'cold', 'warm')):
            raise ValueError('Disabled, cold and warm observation outputs differ')
        if any(signatures[mode] != changed for mode in ('rule_increment', 'rule_full')):
            raise ValueError('Incremental use-policy outputs differ from a disabled-cache rebuild')
        if changed['decisions.jsonl'] == baseline['decisions.jsonl']:
            raise ValueError('Use-policy probe did not change any decisions')

    probes = output / 'additional-probes'
    probes.mkdir()
    restored_cache = output / 'round-0/cache'
    moved_root = probes / 'relocated-inputs'
    moved_root.mkdir()
    for folder in ('config', 'results'):
        (moved_root / folder).symlink_to(root / folder, target_is_directory=True)
    (moved_root / 'README.md').write_text('Benchmark probe with unrelated documentation edit.\n', encoding='utf-8')
    moved_originals = probes / 'relocated-originals'
    moved_originals.symlink_to(originals, target_is_directory=True)
    if execute(probes, 'relocation_and_documentation', chosen_root=moved_root,
               asset_root=moved_originals, cache=restored_cache) != baseline:
        raise ValueError('Relocation or unrelated documentation changed the science artifacts')
    if execute(probes, 'force_assessment', cache=restored_cache, extra=('--force-stage', 'assessment')) != baseline:
        raise ValueError('Forced assessment changed the science artifacts')

    masked_originals = probes / 'masked-originals'
    masked_originals.mkdir()
    captures = root / 'results/observation-shadow-20261126/decisions.jsonl'
    with captures.open(encoding='utf-8') as stream:
        captured_shas = {row['source_sha256'] for line in stream if
                         (row := json.loads(line))['e1']['status'] in ('EXTRACTED', 'SOURCE_VERIFIED_CANDIDATE')}
    files_by_size = sorted((asset.stat().st_size, asset.name, asset) for asset in originals.iterdir() if asset.is_file())
    eligible_assets = [asset for _, _, asset in files_by_size if asset.stem in captured_shas]
    if not eligible_assets:
        raise ValueError('At least one original must support a source-bound candidate for the source-change probe')
    withheld = eligible_assets[0]
    for _, _, asset in files_by_size:
        if asset != withheld:
            (masked_originals / asset.name).symlink_to(asset)
    source_cache = probes / 'source-cache'
    masked_rebuild = execute(probes, 'missing_original_full', asset_root=masked_originals, cache_mode='off')
    if masked_rebuild['decisions.jsonl'] == baseline['decisions.jsonl']:
        raise ValueError('Withheld source did not change the science artifacts')
    if execute(probes, 'missing_original_cold', asset_root=masked_originals, cache=source_cache) != masked_rebuild:
        raise ValueError('Missing-original cold output differs from a disabled-cache rebuild')
    if execute(probes, 'added_original', cache=source_cache) != baseline:
        raise ValueError('Added-original increment differs from a disabled-cache rebuild')
    if execute(probes, 'missing_original_after_cache', asset_root=masked_originals, cache=source_cache) != masked_rebuild:
        raise ValueError('Removed-original increment differs from a disabled-cache rebuild')

    # Load the same code from an isolated Python path with a legitimate alternate
    # unit representation. The explicit normalization rule remains outside formal runs.
    alternate = probes / 'alternate-normalization'
    alternate.mkdir()
    shutil.copytree(runtime / 'au_ree_v2', alternate / 'au_ree_v2', ignore=shutil.ignore_patterns('__pycache__'))
    semantics = alternate / 'au_ree_v2/observation_semantics.py'
    old = 'RESOURCE_UNITS = {variable: unit for variable, unit, _ in resource_use.FIELDS.values()}'
    program = semantics.read_text(encoding='utf-8')
    if program.count(old) != 1:
        raise ValueError('Update the normalization probe for the current target-unit rule')
    semantics.write_text(program.replace(old, old + '\nRESOURCE_UNITS["ore_mt"] = "kt"'), encoding='utf-8')
    environment = {**os.environ, 'PYTHONPATH': str(alternate) + os.pathsep + os.environ.get('PYTHONPATH', '')}
    conversion = execute(probes, 'normalization_increment', cache=restored_cache, environment=environment)
    conversion_full = execute(probes, 'normalization_full', environment=environment, cache_mode='off')
    if conversion != conversion_full or conversion['decisions.jsonl'] == baseline['decisions.jsonl']:
        raise ValueError('Target-unit increment must change decisions and match a disabled-cache rebuild')

    summary = {}
    for mode in sorted({row['mode'] for row in measurements}):
        rows = [row for row in measurements if row['mode'] == mode]
        measurements_for_mode = {'wall_seconds': [row['seconds'] for row in rows],
                                 'cache_bytes': [row['cache_bytes'] for row in rows],
                                 'cache_allocated_bytes': [row['cache_allocated_bytes'] for row in rows],
                                 'peak_rss_bytes': [row['engineering'].get('process_peak_rss_bytes')
                                                    or row['python_peak_working_set_bytes'] for row in rows]}
        for stage in sorted({stage for row in rows for stage in row['engineering'] if stage.endswith('_seconds')}):
            measurements_for_mode[stage] = [row['engineering'].get(stage) for row in rows]
        for stage in sorted({stage for row in rows for stage in row.get('stage_seconds', {})}):
            measurements_for_mode['cached_stage_seconds/' + stage] = [row.get('stage_seconds', {}).get(stage)
                                                                      for row in rows]
        summary[mode] = {field: {'median': median(values), 'minimum': min(values), 'maximum': max(values)}
                         for field, observed in measurements_for_mode.items()
                         if (values := [value for value in observed if value is not None])}
    result = {'rounds': args.rounds, 'scope': 'Frozen 351 resource and 381 technical shadow candidates',
              'peak_memory': 'Process-reported RSS high-water mark, sampled Python peak as fallback',
              'cold_definition': 'Fresh application cache; OS page cache and no acquisition network are shared',
              'science_equal': ['disabled=cold=warm=relocation_and_documentation=force_assessment=added_original',
                                'rule_increment=rule_full',
                                'missing_original_full=missing_original_cold=missing_original_after_cache',
                                'normalization_increment=normalization_full'],
              'baseline_science_sha256': baseline, 'changed_use_policy_science_sha256': changed,
              'policy_change': 'Require deposit_id for the technical use, in an isolated input overlay',
              'withheld_original_sha256': withheld.stem,
              'normalization_change': 'Report normalized ore mass in kt in an isolated code overlay',
              'summary': summary}
    (output / 'observation_performance.json').write_text(canonical(result) + '\n', encoding='utf-8')


def run():
    parser=argparse.ArgumentParser()
    parser.add_argument('--label',default='phase22')
    parser.add_argument('--measure-command',help='JSON argv list; no shell evaluation')
    parser.add_argument('--out',help='Measurement receipt directory')
    parser.add_argument('--rscript',default=os.environ.get('AU_REE_RSCRIPT') or shutil.which('Rscript'))
    parser.add_argument('--current-suite',action='store_true')
    parser.add_argument('--method-expansion',action='store_true')
    parser.add_argument('--observation-suite', action='store_true', help='Cold, warm, disabled and rule-change shadow benchmark')
    parser.add_argument('--originals', help='SHA-named PDF directory for the observation benchmark')
    parser.add_argument('--resume',action='store_true',help='Reuse only completed identical-workload measurements; reject increments with prepopulated final caches')
    parser.add_argument('--snapshot-lock',default='results/phase22-2026-11-06/snapshot_lock.json')
    parser.add_argument('--baseline-lock',default='results/phase21-2026-11-05/snapshot_lock.json')
    parser.add_argument('--rounds',type=int,default=3)
    parser.add_argument('--start',type=int,default=0)
    parser.add_argument('--runtime',help='Frozen source directory for before measurements')
    parser.add_argument('--resolution-only',action='store_true',help='Isolated same-database resolution diagnostic with SQL rows/peak memory')
    parser.add_argument('--r-only', action='store_true', help='Disabled/cold/warm/incremental R on a sealed interchange')
    parser.add_argument('--r-benchmark-panel', action='append', default=[], help='Limit R benchmark to selected panels')
    parser.add_argument('--r-benchmark-draws', type=int, help='Override draw count in isolated benchmark only')
    parser.add_argument('--run',default='work/phase5/latest.json')
    parser.add_argument('--skip-r',action='store_true')
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    output=(root/args.out) if args.out else root/'work/phase21'/args.label
    output.mkdir(parents=True,exist_ok=True)
    if args.observation_suite:
        if not args.originals or not args.out:
            parser.error('--observation-suite requires --originals and --out')
        observation_suite(root, args, output.resolve());return
    if args.method_expansion:
        if not args.rscript:parser.error('--rscript required when not on PATH')
        method_expansion(root,args,output);return
    if args.current_suite:
        if not args.rscript:parser.error('--rscript required when not on PATH')
        current_suite(root,args,output);return
    if args.measure_command:
        command=json.loads(Path(args.measure_command).read_text(encoding='utf8'))
        result=measure_process(command,output/'command.log',root)
        (output/'measurement.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf8')
        print(json.dumps(result));return
    if args.r_only:
        from au_ree_v2.store import canonical, digest, filehash
        from au_ree_v2.tabular import read_csv, write_csv
        from statistics import median

        receipt = json.loads((root / args.run).read_bytes())
        source = Path(receipt['output_dir'])
        config = json.loads((source / 'configuration.json').read_bytes())['research']
        panels = {panel: record['n'] for panel, record in receipt['r_results'].items()
                  if record['status'] == 'COMPLETED'}
        if args.r_benchmark_panel:
            panels = {panel: panels[panel] for panel in args.r_benchmark_panel}
        if not panels or not config.get('mcda_cache'):
            raise ValueError('R benchmark requires a completed cache-enabled interchange')
        if args.r_benchmark_draws is not None:
            config['monte_carlo']['reps'] = args.r_benchmark_draws
        target = 'six_domain' if 'six_domain' in panels else next(iter(panels))
        inputs = ('matrix.csv', 'criteria.csv', 'weights.csv')
        benchmark_config = output / 'r_benchmark_inputs.json'
        benchmark_config.write_text(canonical({'config': config, 'panels': panels}) + '\n', encoding='utf-8')
        runner = """
import json, sys
from pathlib import Path
from au_ree_v2.analysis import run_r
root, out, contract, executable, mode = sys.argv[1:]
settings = json.loads(Path(contract).read_bytes())
run_r(root, out, {'panels': settings['panels']}, settings['config'], executable or None, cache_mode=mode)
"""
        measurements = []
        signatures = {}

        def execute(stage, area, cache, *, change_weights=False, disable=False):
            interchange = area / stage
            interchange.mkdir(parents=True)
            # The cohort stage considers sibling interchange even for panels that
            # are not themselves submitted to R.
            for folder in sorted(p for p in source.iterdir() if p.is_dir()):
                paths = [folder / name for name in inputs]
                if not all(path.is_file() for path in paths):
                    continue
                destination = interchange / folder.name
                destination.mkdir()
                for path in paths:
                    expected = receipt['output_hashes'].get(path.relative_to(source).as_posix())
                    if expected is None or filehash(path) != expected:
                        raise ValueError(f'R benchmark interchange is not receipt-bound: {path}')
                    shutil.copyfile(path, destination / path.name)
            coverage = source / 'commercial_project_coverage.csv'
            if coverage.is_file():
                if filehash(coverage) != receipt['output_hashes'].get(coverage.name):
                    raise ValueError('R benchmark commercial evidence differs from its receipt')
                shutil.copyfile(coverage, interchange / coverage.name)
            if change_weights:
                weights_path = interchange / target / 'weights.csv'
                weights = read_csv(weights_path)
                scenario = weights[0]['scenario']
                weighted = [row for row in weights if row['scenario'] == scenario and float(row['weight']) > 0]
                if len(weighted) < 2:
                    raise ValueError('R weight intervention requires at least two nonzero criteria')
                first, second = weighted[:2]
                delta = min(float(second['weight']) / 2, 0.01)
                first['weight'] = float(first['weight']) + delta
                second['weight'] = float(second['weight']) - delta
                write_csv(weights_path, weights, list(weights[0]))
            command = [sys.executable, '-c', runner, str(root), str(interchange), str(benchmark_config),
                       args.rscript or '', 'off' if disable else 'use']
            execution = measure_process(command, area / f'{stage}.log', root,
                                        {**os.environ, 'AU_REE_MCDA_CACHE': str(cache)})
            if execution['exit_code']:
                raise RuntimeError(f'R benchmark failed, see {area / (stage + ".log")}')
            hashes = {p.relative_to(interchange).as_posix(): filehash(p)
                      for p in sorted(interchange.glob('*/*.csv'))}
            group = 'changed' if change_weights else 'baseline'
            expected = signatures.setdefault(group, hashes)
            if expected != hashes:
                raise ValueError(f'R {stage} benchmark differs from its complete rebuild')
            receipts = [json.loads(p.read_bytes()) for p in sorted(interchange.glob('*/r*cache.json'))]
            stages = {r['status'] for r in receipts}
            return {'mode': stage, 'science_sha256': digest(hashes), 'cache_bytes': sum(
                        p.stat().st_size for p in cache.rglob('*') if p.is_file()),
                    'stages': {status: sum(r['status'] == status for r in receipts) for status in stages},
                    'core_seconds': sum(r['elapsed_seconds'] for r in receipts if r['contract']['stage'] != 'cohort'),
                    'cohort_seconds': sum(r['elapsed_seconds'] for r in receipts if r['contract']['stage'] == 'cohort'),
                    **execution}

        for iteration in range(args.rounds):
            area = output / f'r-round-{iteration}'
            cache = area / 'cache'
            for stage, change, disable in (
                ('disabled', False, True), ('cold', False, False), ('warm', False, False),
                ('weight_full', True, True), ('weight_increment', True, False),
            ):
                row = execute(stage, area, cache, change_weights=change, disable=disable)
                measurements.append(row)
                (output / 'r_measurements.json').write_text(canonical(measurements) + '\n', encoding='utf8')
                print(canonical({'stage': stage, 'seconds': row['seconds'], 'stages': row['stages']}), flush=True)
        if signatures['baseline'] == signatures['changed']:
            raise ValueError('R weight intervention did not alter the interchange')
        summary = {
            mode: {field: {'minimum': min(values), 'median': median(values), 'maximum': max(values)}
                   for field in ('seconds', 'core_seconds', 'cohort_seconds', 'sampled_combined_working_set_bytes',
                                 'r_peak_working_set_bytes', 'cache_bytes')
                   if (values := [row[field] for row in measurements if row['mode'] == mode and row.get(field) is not None])}
            for mode in sorted({row['mode'] for row in measurements})
        }
        (output / 'r_performance.json').write_text(canonical({
            'rounds': args.rounds, 'panels': panels, 'draws': config['monte_carlo']['reps'],
            'weight_intervention_panel': target, 'summary': summary,
            'science_equal': ['disabled=cold=warm', 'weight_full=weight_increment'],
            'scope': 'R stage only on frozen matrix, criteria, and weights',
        }) + '\n', encoding='utf-8')
        return
    if args.resolution_only:
        import sqlite3,ctypes
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
                '--rscript',args.rscript]
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
