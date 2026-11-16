"""Clean-checkout contracts; live network is exercised separately by CI."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import textwrap
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN = ('980bedb', 'asx-current', 'work/asx-', 'results/round', 'results/asx-',
             'asx_local_asset_roots', 'field_provenance')


class AutomatedBuildCleanTests(unittest.TestCase):
    def test_receipt_gate_runs_for_code_or_unknown_changes_and_handles_unicode_paths(self):
        for workflow in ('automated-build.yml','research.yml'):
            content=(ROOT/'.github/workflows'/workflow).read_text(encoding='utf8')
            code=textwrap.dedent(content.split("python - <<'PY'\n",1)[1].split('\n          PY',1)[0])
            cases=[('synchronize','a'*40,['results/integrated-rebuild-2026-11-15/專案總表.csv'],False),
                   ('synchronize','a'*40,['results/integrated-rebuild-2026-11-15/README.md','src/au_ree_v2/census.py'],True),
                   ('synchronize','a'*40,[],True),('synchronize','unknown',[],True),('opened','a'*40,[],True)]
            for action,before,paths,required in cases:
                with self.subTest(workflow=workflow,action=action,paths=paths),tempfile.TemporaryDirectory() as temp:
                    output=Path(temp)/'outputs'
                    env=dict(PREVIOUS_HEAD=before,EVENT_KIND='pull_request',EVENT_ACTION=action,GITHUB_OUTPUT=str(output))
                    raw=('\0'.join(paths)+'\0').encode('utf8')
                    with patch.dict(os.environ,env),patch('subprocess.check_output',return_value=raw):exec(compile(code,workflow,'exec'),{})
                    self.assertEqual(output.read_text().strip(),'run_pipeline='+str(required).lower())

    def test_runtime_and_registry_have_no_experiment_dependency(self):
        paths = sorted((ROOT / 'src').rglob('*.py')) + [ROOT / 'config/sources.json']
        for path in paths:
            content = path.read_text(encoding='utf-8').replace('\\\\', '/')
            for token in FORBIDDEN:
                with self.subTest(path=str(path.relative_to(ROOT)), token=token):
                    self.assertNotIn(token, content)

    def test_tracked_checkout_configuration_reads_stay_inside_checkout(self):
        self._probe_checkout(False)

    def test_ci_build_has_no_experiment_dependency(self):
        content=(ROOT/'.github/workflows/automated-build.yml').read_text(encoding='utf8')
        for token in FORBIDDEN:self.assertNotIn(token,content)

    def test_strict_empty_build_reads_stay_inside_checkout(self):
        self._probe_checkout(True)

    def _probe_checkout(self, full_build):
        # Copy tracked application inputs only. No pre-existing work or external
        # developer files are available. A separate process owns the audit hook.
        tracked = subprocess.check_output(['git', 'ls-files', '-z'], cwd=ROOT).decode().split('\0')
        with tempfile.TemporaryDirectory() as temp:
            checkout = Path(temp) / 'checkout'
            checkout.mkdir()
            for name in tracked:
                if not name or not name.startswith(('config/', 'data/', 'src/', 'R/', 'results/')):
                    continue
                if not full_build and name.startswith(('data/snapshots/', 'results/')):
                    continue
                source = ROOT / name
                if source.is_file():
                    target = checkout / name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(source, target)
            self.assertFalse((checkout / 'work').exists())
            probe = r'''
import json, os, pathlib, sys
from urllib.parse import urlsplit
from urllib.request import url2pathname
root = pathlib.Path(sys.argv[1]).resolve()
sys.dont_write_bytecode = True
sys.path.insert(0, str(root / 'src'))
from au_ree_v2.cli import research_configuration
from unittest.mock import patch
from au_ree_v2.evidence import load_claims
# Import dependency code before auditing application inputs. Interpreter and
# installed-package code reads remain permitted; arbitrary data does not.
libraries = [pathlib.Path(sys.base_prefix).resolve()]
for value in sys.path:
    if value and ('site-packages' in value or 'dist-packages' in value):
        libraries.append(pathlib.Path(value).resolve())
reads = []
def audit(event, args):
    if event == 'sqlite3.connect':
        value = str(args[0])
        if value.startswith('file:'):
            uri = urlsplit(value)
            if uri.netloc not in ('', 'localhost'):
                raise AssertionError('DATABASE_OUTSIDE_CHECKOUT: ' + value)
            value = url2pathname(uri.path)
        database = pathlib.Path(value).resolve()
        if database != root and root not in database.parents:
            raise AssertionError('DATABASE_OUTSIDE_CHECKOUT: ' + str(database))
        return
    if event != 'open' or not isinstance(args[0], (str, bytes, os.PathLike)):
        return
    path = pathlib.Path(os.fsdecode(args[0])).resolve()
    mode = args[1]
    if isinstance(mode, str) and any(c in mode for c in 'wax+'):
        return
    if path == root or root in path.parents:
        reads.append(path.relative_to(root).as_posix())
        return
    if path.suffix in ('.py', '.pyc', '.pyd', '.so', '.dll') and any(p == path or p in path.parents for p in libraries):
        return
    if path == pathlib.Path(os.devnull).resolve():
        return
    raise AssertionError('APPLICATION_INPUT_OUTSIDE_CHECKOUT: ' + str(path))
sys.addaudithook(audit)
research_configuration(root)
json.loads((root / 'config/sources.json').read_text(encoding='utf8'))
claims, sha = load_claims(root)
assert claims['projects']
# Prove the guard rejects an actual application-input attempt, not only that
# the successful path happened to return without reading anything.
try:
    open(root.parent / 'outside-input.json', 'r')
except AssertionError as exc:
    assert 'APPLICATION_INPUT_OUTSIDE_CHECKOUT' in str(exc)
else:
    raise AssertionError('outside-root read was not intercepted')
if sys.argv[2] == 'full':
    from au_ree_v2 import cli
    from contextlib import redirect_stdout
    import io
    with patch('au_ree_v2.acquisition.strict_refresh', return_value=([], [])) as fetch, patch('au_ree_v2.acquisition.strict_dns_preflight', return_value=[]), patch('au_ree_v2.acquisition.strict_asx_probe', return_value=[]), patch('socket.socket.connect', side_effect=AssertionError('NETWORK_FORBIDDEN')):
        sys.argv = ['au-ree-v2', 'all', '--refresh', '--as-of', '2026-11-13', '--work', str(root/'work/clean'), '--root', str(root), '--skip-r']
        with redirect_stdout(io.StringIO()):
            cli.main()
        assert fetch.call_count == 1
    assert (root/'work/clean/latest.json').is_file()
    summary=json.loads((root/'work/clean/latest.json').read_text(encoding='utf8'))
    out=pathlib.Path(summary['output_dir'])
    assert (root/'work/clean/databases'/out.name/'canonical.sqlite').is_file()
    assert not list(out.rglob('canonical.sqlite*'))
    assert not any('canonical.sqlite' in name for name in summary['output_hashes'])
print(json.dumps(dict(reads=reads, projects=len(claims['projects']), sha=sha)))
'''
            result = subprocess.run([sys.executable, '-c', probe, str(checkout), 'full' if full_build else 'config'], cwd=checkout,
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            receipt = json.loads(result.stdout.strip())
            self.assertIn('data/claims.json', receipt['reads'])
            self.assertIn('config/sources.json', receipt['reads'])


if __name__ == '__main__':
    unittest.main()

