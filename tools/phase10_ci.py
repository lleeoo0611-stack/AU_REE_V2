"""Route CI conservatively and select fast tests from static Python imports."""

import argparse
import ast
from hashlib import sha256
from importlib.metadata import distributions
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET


AUDIT_PREFIXES = ('src/au_ree_v2/phase10_', 'tools/phase10_', 'tools/run_phase10',
                  'results/phase10-2026-11-27/', 'config/ontology/phase10_')
PUBLIC_MODULES = {'acquisition', 'cli', 'census', 'census_audit', 'census_policy', 'census_release',
                  'census_replay', 'official', 'source_discovery', 'source_recovery', 'store',
                  'check_company_markers_ci', 'locators_from_ci_cache', 'verify_pre_cutoff_evidence'}
INTEGRATION_TESTS = {'test_automated_build_clean.py', 'test_mcda_execution_cache.py',
                     'test_mcda_weight_reproducibility.py', 'test_resource_admission_integration.py'}
SOURCE_AUDIT_PREFIXES = ('src/au_ree_v2/phase10_', 'tools/phase10_shadow.py', 'tools/run_phase10.py',
                         'results/phase10-2026-11-27/holdout_manifest.json',
                         'results/phase10-2026-11-27/source_recovery_manifest.json')
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


def route(root, paths, *, event='pull_request', validation='archive'):
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
            (direct_tests if (root / path).is_file() else unknown).add(path)
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
    full = bool(production or unknown or paths is None or event != 'pull_request')
    archive = (paths is None or bool(unknown) or event != 'pull_request' and validation != 'pr'
               or any(path.startswith(('src/', 'R/', 'config/', 'data/', 'results/', 'tools/check_',
                                       'tools/evaluate_')) for path in production))
    if full:
        tests.update({'test_module_dependencies.py', 'test_observation_schema.py'})
    integration_tests = tests & INTEGRATION_TESTS
    tests -= integration_tests
    if not tests:
        tests.add('test_module_dependencies.py')
    return {'version': 'phase10-ci-routing-v2', 'changed_paths': paths,
            'fast': True, 'integration': bool(audit or integration_tests or full), 'full': full, 'archive': archive,
            'public': public or bool(unknown) or event != 'pull_request',
            'phase10': any(path.startswith(SOURCE_AUDIT_PREFIXES) for path in audit),
            'affected_modules': sorted(affected), 'fast_tests': sorted(tests),
            'integration_tests': sorted(integration_tests)}


def changed_paths(root, base):
    if not base or not SHA.fullmatch(base):
        return None
    try:
        data = subprocess.check_output(['git', 'diff', '--name-only', '--no-renames', '-z', base, 'HEAD'], cwd=root)
        return [part for part in data.decode().split('\0') if part]
    except (subprocess.CalledProcessError, UnicodeDecodeError):
        return None


def _sha(path):
    return sha256(path.read_bytes()).hexdigest()


def python_environment(root):
    """Bind reuse to the tested merge commit and tools available to the suite."""
    image = {key: os.environ.get(key) for key in ('ImageOS', 'ImageVersion')}
    if not all(image.values()):
        raise ValueError('Unidentified GitHub runner image')
    if subprocess.run(['git', 'diff', '--quiet', 'HEAD', '--'], cwd=root).returncode:
        raise ValueError('The test checkout has tracked modifications')
    if not (rscript := shutil.which('Rscript')):
        raise ValueError('Missing R runtime for the shared test suite')
    from au_ree_v2.analysis import _r_runtime

    tools = {'R': _r_runtime(rscript)}
    if executable := shutil.which('tesseract'):
        result = subprocess.check_output([executable, '--version'], stderr=subprocess.STDOUT, text=True, timeout=15)
        tools['tesseract'] = {'sha256': _sha(Path(executable)), 'version': result.strip()}
    proof = json.loads((root / 'work/pre_cutoff_evidence_verified.json').read_bytes())
    proof.pop('retrieved_at', None)
    return {'schema': 'phase10-shared-python-v1', 'image': image,
            'commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip(),
            'python': sys.version, 'architecture': platform.machine(), 'libc': list(platform.libc_ver()),
            'packages': sorted([item.metadata['Name'], item.version] for item in distributions()),
            'tools': tools, 'pre_cutoff_evidence_sha256': sha256(json.dumps(proof, sort_keys=True).encode()).hexdigest(),
            'environment': {key: os.environ.get(key) for key in (
                'LANG', 'LC_ALL', 'TZ', 'PYTHONHASHSEED', 'TESSDATA_PREFIX')}}


def xml_report_set(folder):
    """Require nonempty, successful JUnit results and bind the exact report bytes."""
    reports = {}
    for path in sorted(folder.iterdir()):
        if not path.is_file() or path.suffix != '.xml' or path.is_symlink():
            raise ValueError('Unexpected test report payload: ' + path.name)
        data = path.read_bytes()
        node = ET.fromstring(data)
        if node.tag != 'testsuite' or any(int(node.get(field, '0')) for field in ('failures', 'errors')):
            raise ValueError('Unsuccessful test report: ' + path.name)
        cases = node.findall('testcase')
        if len(cases) != int(node.get('tests', '-1')) or node.find('.//failure') is not None or node.find('.//error') is not None:
            raise ValueError('Incomplete test report: ' + path.name)
        reports[path.name] = {'sha256': sha256(data).hexdigest(), 'tests': len(cases),
                              'skipped': sum(case.find('skipped') is not None for case in cases)}
    if not sum(item['tests'] - item['skipped'] for item in reports.values()):
        raise ValueError('No executed Python tests')
    return reports


def python_receipt(root, bundle, *, verify=False):
    expected = {'environment': python_environment(root), 'reports': xml_report_set(bundle / 'test-xml')}
    path = bundle / 'receipt.json'
    if verify:
        if json.loads(path.read_bytes()) != expected:
            raise ValueError('Python test report fingerprint or execution contract mismatch')
    else:
        path.write_text(json.dumps(expected, sort_keys=True) + '\n', encoding='utf-8')
    print(json.dumps({'verified': verify, 'tests': sum(r['tests'] for r in expected['reports'].values()),
                      'skipped': sum(r['skipped'] for r in expected['reports'].values()),
                      'commit': expected['environment']['commit']}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('route', 'test', 'seal-python', 'verify-python'))
    parser.add_argument('--base')
    parser.add_argument('--root', type=Path, default=Path.cwd())
    parser.add_argument('--receipt', type=Path)
    parser.add_argument('--bundle', type=Path)
    parser.add_argument('--tier', choices=('fast', 'integration'), default='fast')
    parser.add_argument('--event', default='pull_request')
    parser.add_argument('--validation', choices=('pr', 'archive'), default='archive')
    args = parser.parse_args()
    if args.action in ('seal-python', 'verify-python'):
        if not args.bundle:
            parser.error('Shared Python regression evidence requires --bundle')
        python_receipt(args.root, args.bundle, verify=args.action == 'verify-python')
        return
    plan = route(args.root, changed_paths(args.root, args.base), event=args.event, validation=args.validation)
    if args.receipt:
        args.receipt.parent.mkdir(parents=True, exist_ok=True)
        args.receipt.write_text(json.dumps(plan, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(plan, ensure_ascii=False), flush=True)
    if args.action == 'test':
        for name in plan[args.tier + '_tests']:
            subprocess.run([sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-p', name],
                           cwd=args.root, check=True)
    elif output := os.environ.get('GITHUB_OUTPUT'):
        with open(output, 'a', encoding='utf-8') as stream:
            for name in ('fast', 'integration', 'full', 'archive', 'public', 'phase10'):
                stream.write(f'{name}={str(plan[name]).lower()}\n')


if __name__ == '__main__':
    main()
