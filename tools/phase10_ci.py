"""Route CI conservatively and select fast tests from static Python imports."""

import argparse
import ast
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys


AUDIT_PREFIXES = ('src/au_ree_v2/phase10_', 'tools/phase10_', 'tools/run_phase10',
                  'results/phase10-2026-11-27/', 'config/ontology/phase10_')
PUBLIC_MODULES = {'acquisition', 'cli', 'census', 'census_audit', 'census_policy', 'census_release',
                  'census_replay', 'official', 'source_discovery', 'source_recovery', 'store',
                  'check_company_markers_ci', 'locators_from_ci_cache', 'verify_pre_cutoff_evidence'}
INTEGRATION_TESTS = {'test_automated_build_clean.py', 'test_mcda_execution_cache.py',
                     'test_mcda_weight_reproducibility.py', 'test_resource_admission_integration.py'}
SHA = re.compile(r'[0-9a-fA-F]{40}')


def imports(path):
    """Return direct module names, including relative package imports."""
    found = set()
    for node in ast.walk(ast.parse(path.read_bytes(), filename=str(path))):
        if isinstance(node, ast.Import):
            found.update(alias.name.split('.')[-1] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.module != 'au_ree_v2':
                found.add(node.module.split('.')[-1])
            else:
                found.update(alias.name for alias in node.names)
    return found


def route(root, paths):
    """Unknown changes receive full coverage. Phase 10 auditing has its own tier."""
    root = Path(root)
    paths = None if paths is None else sorted(set(paths))
    audit, production, unknown, direct_tests = set(), set(), set(), set()
    public = paths is None
    for path in paths or ():
        file = PurePosixPath(path)
        if path.startswith(AUDIT_PREFIXES) or path.startswith('tests/test_phase10_'):
            audit.add(path)
        elif path.startswith('docs/') or (len(file.parts) == 1 and file.suffix == '.md'):
            continue
        elif path.startswith('tests/') and file.suffix == '.py':
            direct_tests.add(path)
        elif path.startswith(('src/', 'R/', 'config/', 'data/', 'results/', 'tools/', '.github/workflows/')):
            production.add(path)
            if (path.startswith(('config/', 'data/', 'results/')) or file.stem in PUBLIC_MODULES
                    or path == '.github/workflows/automated-build.yml'):
                public = True
        else:
            unknown.add(path)

    affected = {PurePosixPath(path).stem for path in audit | production | unknown if path.endswith('.py')}
    modules = {p.stem: imports(p) for p in sorted((root / 'src/au_ree_v2').glob('*.py'))}
    while True:
        dependents = {name for name, deps in modules.items() if deps & affected} - affected
        if not dependents:
            break
        affected.update(dependents)

    tests = {p.name for p in (root / 'tests').glob('test_*.py')
             if p.relative_to(root).as_posix() in direct_tests | audit or imports(p) & affected}
    if audit or any(path.startswith('.github/workflows/') for path in production):
        tests.update(p.name for p in (root / 'tests').glob('test_phase10_*.py'))
    full = bool(production or unknown or paths is None)
    if full:
        tests.update({'test_module_dependencies.py', 'test_observation_schema.py'})
    tests -= INTEGRATION_TESTS
    if not tests:
        tests.add('test_module_dependencies.py')
    return {'version': 'phase10-ci-routing-v1', 'changed_paths': paths,
            'fast': True, 'integration': bool(audit or direct_tests or full), 'full': full,
            'public': public or bool(unknown), 'phase10': bool(audit),
            'affected_modules': sorted(affected), 'fast_tests': sorted(tests)}


def changed_paths(root, base):
    if not base or not SHA.fullmatch(base):
        return None
    try:
        data = subprocess.check_output(['git', 'diff', '--name-only', '--no-renames', '-z', base, 'HEAD'], cwd=root)
    except subprocess.CalledProcessError:
        return None
    return [part for part in data.decode().split('\0') if part]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('route', 'test'))
    parser.add_argument('--base')
    parser.add_argument('--root', type=Path, default=Path.cwd())
    parser.add_argument('--receipt', type=Path)
    args = parser.parse_args()
    plan = route(args.root, changed_paths(args.root, args.base))
    if args.receipt:
        args.receipt.parent.mkdir(parents=True, exist_ok=True)
        args.receipt.write_text(json.dumps(plan, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(plan, ensure_ascii=False), flush=True)
    if args.action == 'test':
        for name in plan['fast_tests']:
            subprocess.run([sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-p', name],
                           cwd=args.root, check=True)
    elif output := os.environ.get('GITHUB_OUTPUT'):
        with open(output, 'a', encoding='utf-8') as stream:
            for name in ('fast', 'integration', 'full', 'public', 'phase10'):
                stream.write(f'{name}={str(plan[name]).lower()}\n')


if __name__ == '__main__':
    main()
