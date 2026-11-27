"""Run fixed-input Phase 22 factor and cache replays in isolated checkouts."""

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tarfile
from time import perf_counter

from au_ree_v2.derived_cache import atomic_json
from au_ree_v2.store import filehash
if __package__:
    from .phase10_effects import main as summarize
else:
    from phase10_effects import main as summarize


def checkout(repo, source_root, folder, revision):
    commit = subprocess.check_output(['git', 'rev-parse', f'{revision}^{{commit}}'], cwd=repo, text=True).strip()
    subprocess.run(['git', 'worktree', 'add', '--detach', '--no-checkout', '--lock', '--reason',
                    'Sealed Phase 10 replay', str(folder), commit], cwd=repo, check=True)
    files = ('src', 'config', 'R', 'docs', 'tools', 'tests', 'pyproject.toml', 'requirements-constraints.txt')
    with subprocess.Popen(['git', 'archive', commit, *files], cwd=repo, stdout=subprocess.PIPE) as process:
        with tarfile.open(fileobj=process.stdout, mode='r|') as archive:
            archive.extractall(folder, filter='data')
        if process.wait():
            raise RuntimeError(f'Could not read archived code {commit}')
    for name in ('data', 'results'):
        (folder / name).symlink_to(source_root / name, target_is_directory=True)
    return commit


def run_case(args, metadata, name, folder, commit, *, mode='off', admission=False, retrieval='fixed', historical=False):
    run_dir = args.work / name
    run_dir.mkdir()
    database = run_dir / 'canonical.sqlite'
    if args.seed_database:
        with sqlite3.connect(args.seed_database.as_uri() + '?mode=ro&immutable=1', uri=True) as seed:
            with sqlite3.connect(database) as target:
                seed.backup(target)
    document_cache = args.work / 'document-cache'
    r_cache = args.work / 'r-cache'
    command = [sys.executable, '-m', 'au_ree_v2', 'rebuild', '--root', str(folder), '--as-of', '2026-11-05',
               '--snapshot-lock', str(args.snapshot_lock), '--work', str(run_dir), '--rscript', str(args.rscript),
               '--mcda-weight-calculation', 'ordered-domain-fsum-v2',
               '--mcda-trace-panel', 'issuer_resource_composition', '--mcda-cache-mode', mode]
    if admission:
        command.extend(('--resource-admission', str(args.frame), '--resource-retrieval', retrieval,
                        '--cache-mode', mode, '--cache-dir', str(document_cache)))
    if historical and '--c1-cohort-policy' in (folder / 'src/au_ree_v2/cli.py').read_text():
        command.extend(('--c1-cohort-policy', 'historical'))
    environment = {**os.environ, 'PYTHONPATH': str(folder / 'src'), 'PYTHONHASHSEED': '17',
                   'PYTHONDONTWRITEBYTECODE': '1', 'TMPDIR': str(args.work), 'AU_REE_MCDA_CACHE': str(r_cache)}
    log = run_dir / 'rebuild.log'
    started = perf_counter()
    with log.open('w', encoding='utf8') as stdout:
        with subprocess.Popen(command, cwd=folder, env=environment, stdout=stdout, stderr=subprocess.STDOUT) as process:
            _, exit_status, usage = os.wait4(process.pid, 0)
            process.returncode = os.waitstatus_to_exitcode(exit_status)
    elapsed = perf_counter() - started
    if process.returncode:
        raise RuntimeError(f'{name} exited with {process.returncode}. See {log}')
    summary = json.loads((run_dir / 'latest.json').read_bytes())
    if summary['status'] != 'COMPLETED' or summary['code']['commit'] != commit:
        raise RuntimeError(f'{name} has unexpected rebuild status or code receipt: {summary["status"]}, {summary["code"]}')
    with sqlite3.connect(database.as_uri() + '?mode=ro', uri=True) as stored:
        integrity = stored.execute('PRAGMA integrity_check').fetchall()
        violations = stored.execute('PRAGMA foreign_key_check').fetchall()
    if integrity != [('ok',)] or violations:
        raise RuntimeError(f'{name} SQLite integrity: {integrity}; foreign key violations: {violations}')
    r_results = summary['r_results'].values()
    measured = {'case': name, 'cache_mode': mode, 'command': command, 'code': summary['code'],
                'proc_wall_seconds': elapsed, 'max_rss_kib': usage.ru_maxrss, 'sqlite_integrity': 'ok',
                'sqlite_foreign_key_violations': len(violations),
                'cache_status': dict(Counter(item.get('cache_status', 'UNRECORDED') for item in r_results)),
                'cohort_cache_status': dict(Counter(item.get('cohort_cache_status', 'UNRECORDED') for item in r_results)),
                'cache_sizes_bytes': {cache.name: sum(path.stat().st_size for path in cache.rglob('*') if path.is_file())
                                     for cache in (r_cache, document_cache)}, **metadata}
    atomic_json(args.work / f'{name}.json', measured)
    print(f'{name}: {elapsed:.3f}s, {usage.ru_maxrss} KiB peak RSS', flush=True)
    return summary['output_dir']


def run(args):
    args.work.mkdir(parents=True, exist_ok=False)
    args.out.mkdir(parents=True, exist_ok=True)
    current, legacy = (args.work / label for label in ('code-current', 'code-legacy'))
    metadata = {'source_lock_sha256': filehash(args.snapshot_lock), 'frame_file_sha256': filehash(args.frame),
                'seed_database_sha256': filehash(args.seed_database) if args.seed_database else None}
    results, failures = {}, {}
    try:
        research = checkout(args.root, args.source_root, current, args.research_commit)
        def finish(name, future):
            try:
                results[name] = future.result()
            except (OSError, ValueError, RuntimeError, KeyError, sqlite3.Error) as error:
                failures[name] = str(error)
                print(f'{name}: {error}', file=sys.stderr, flush=True)

        if not args.cache_only:
            baseline = checkout(args.root, args.source_root, legacy, args.legacy_commit)
            if research == baseline:
                raise ValueError('The joint rule-release comparison requires distinct revisions')
            factors = {
                'disabled-baseline': (current, research, {}),
                'historical-baseline': (current, research, {'historical': True}),
                'current-fixed': (current, research, {'admission': True}),
                'current-historical-fixed': (current, research, {'admission': True, 'historical': True}),
                'old-historical-fixed': (legacy, baseline, {'admission': True, 'historical': True}),
            }
            with ThreadPoolExecutor(max_workers=args.factor_workers) as pool:
                tasks = {name: pool.submit(run_case, args, metadata, name, folder, commit, **options)
                         for name, (folder, commit, options) in factors.items()}
                for name, task in tasks.items():
                    finish(name, task)
        # All timed cache modes are sequential and use the same inputs.
        with ThreadPoolExecutor(max_workers=1) as pool:
            for label, mode in (('off', 'off'), ('cold', 'use'), ('warm', 'use')):
                name = f'current-full-{label}'
                finish(name, pool.submit(run_case, args, metadata, name, current, research,
                                         mode=mode, admission=True, retrieval='full-text'))
        inventory = args.work / 'completed.json'
        atomic_json(inventory, {'runs': results, 'failures': failures, 'area': str(args.work)})
        report_status = summarize(['--runs', str(inventory), '--out', str(args.out)])
        return report_status or int(bool(failures))
    finally:
        for folder in (current, legacy):
            if (folder / '.git').is_file():
                subprocess.run(['git', 'worktree', 'remove', '--force', '--force', str(folder)], cwd=args.root, check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    root = Path(__file__).resolve().parents[1]
    parser.add_argument('--root', type=Path, default=root)
    parser.add_argument('--source-root', type=Path, help='Root of the original data/ and results/ directories')
    parser.add_argument('--research-commit', default='dcda87e81e1250d443f73c1984faaa7beaa19930')
    parser.add_argument('--legacy-commit', default='1c0794e23864875aca73845e4aedf493041887e7')
    parser.add_argument('--snapshot-lock', type=Path, default=root / 'results/phase22-2026-11-06/snapshot_lock.json')
    parser.add_argument('--frame', type=Path, default=root / 'config/ontology/resource_admission_frame_v1.json')
    parser.add_argument('--seed-database', type=Path, help='Optional canonical baseline copied read-only into each run')
    parser.add_argument('--rscript', default='Rscript')
    parser.add_argument('--work', type=Path, required=True, help='New directory for raw sealed run artifacts')
    parser.add_argument('--out', type=Path, required=True, help='Directory for compact replay receipts')
    parser.add_argument('--factor-workers', type=int, choices=(1, 2), default=1)
    parser.add_argument('--cache-only', action='store_true', help='Benchmark cold, warm, and disabled cache without the other factor arms')
    args = parser.parse_args()
    for field in ('root', 'source_root', 'snapshot_lock', 'frame', 'seed_database', 'work', 'out'):
        value = getattr(args, field)
        if value is not None:
            setattr(args, field, value.resolve())
    args.source_root = args.source_root or args.root
    if '/' in args.rscript:
        args.rscript = str(Path(args.rscript).resolve())
    return run(args)


if __name__ == '__main__':
    raise SystemExit(main())
