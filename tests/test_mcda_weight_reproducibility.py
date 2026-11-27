"""Exercise the formal Python and R analysis in separate hash-seeded processes."""

from contextlib import closing
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

from au_ree_v2.analysis import (DETERMINISTIC_WEIGHT_CALCULATION, LEGACY_WEIGHT_CALCULATION, MCDA_TRACE_PANEL,
                                mcda_cache_contract, prepare, run_r, weight_calculation_version)
from au_ree_v2.cli import research_configuration
from au_ree_v2.store import connect, digest, filehash


ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / 'results/phase22-2026-11-06/snapshot_lock.json'
PANELS = ('six_domain', 'issuer_resource_composition')
CUTOFF = '2026-11-05'


def render(output, rscript):
    config = research_configuration(ROOT, LOCK)
    config['mcda_weight_calculation'] = DETERMINISTIC_WEIGHT_CALCULATION
    config['mcda_trace_panel'] = MCDA_TRACE_PANEL
    config['panels'] = {name: config['panels'][name] for name in PANELS}
    config['monte_carlo'] = {**config['monte_carlo'], 'reps': 4}
    values, resources = {}, {}
    with closing(connect(':memory:')) as db:
        db.execute('INSERT INTO sources VALUES (?,?,?,?,?,?,?,?)',
                   ('src', 'fixture', '', CUTOFF, CUTOFF, '', 'pdf', '{}'))
        for i, pid in enumerate(('project-a', 'project-b'), 1):
            db.execute('INSERT INTO entities VALUES (?,?,?,?)', (pid, 'PROJECT', 'test', pid))
            db.execute('INSERT INTO records (entity_id,source_sha,name,raw) VALUES (?,?,?,?)',
                       (pid, 'src', pid, '{}'))
            values[pid] = {row['code']: {'value': row['low'] + i * (row['high'] - row['low']) / 4}
                           for row in config['criteria'] if row['code'] not in ('R1', 'R2', 'TC1', 'TC2')}
            amount = 50.0 * i
            resources[pid] = {'contained_treo_kt': amount, 'scope': 'named testing resource',
                              'rounding_bounds_kt': [amount - 0.5, amount + 0.5], 'date': CUTOFF}
        selection = {'values': values, 'inventory': [], 'policy': {'cohorts': {'development': {
            'requires': ['D1', 'T1']}}}}
        prepared = prepare(db, CUTOFF, [], resources, {}, config, output, selection=selection)
    if rscript:
        results = run_r(ROOT, output, prepared, config, rscript=rscript, cache_mode='off')
        for panel in PANELS:
            if results[panel]['status'] != 'COMPLETED':
                raise ValueError('Analysis failed for ' + panel)
    current = mcda_cache_contract(ROOT, output, 'six_domain', config, {}, 'core')
    historical = mcda_cache_contract(ROOT, output, 'six_domain',
                                    {key: value for key, value in config.items() if key != 'mcda_weight_calculation'},
                                    {}, 'core')
    return {'python_hash': hash('Commercial'), 'contracts': [digest(current), digest(historical)],
            'calculation': current['weight_calculation'],
            'outputs': {file.relative_to(output).as_posix(): filehash(file)
                        for panel in PANELS for file in (output / panel).glob('*.csv')}}


class WeightReproducibilityTests(unittest.TestCase):
    def test_current_settings_choose_v2_and_archived_config_keeps_v1(self):
        self.assertEqual(weight_calculation_version(research_configuration(ROOT)),
                         DETERMINISTIC_WEIGHT_CALCULATION)
        self.assertEqual(weight_calculation_version(research_configuration(ROOT, LOCK)),
                         LEGACY_WEIGHT_CALCULATION)
        with self.assertRaisesRegex(ValueError, 'UNKNOWN_MCDA_WEIGHT_CALCULATION'):
            weight_calculation_version({'mcda_weight_calculation': 'unrecognized'})

    def independent_analyses(self, rscript=None):
        with TemporaryDirectory() as tmp:
            outputs = []
            for seed in ('1', '2', '42'):
                command = [sys.executable, str(Path(__file__).resolve()), '--render', str(Path(tmp) / seed)]
                if rscript:
                    command.append(rscript)
                child = subprocess.run(command, cwd=ROOT, env={**os.environ, 'PYTHONHASHSEED': seed},
                                       capture_output=True, text=True, timeout=100)
                self.assertEqual(child.returncode, 0, child.stderr)
                outputs.append(json.loads(child.stdout))
            self.assertEqual(len({result['python_hash'] for result in outputs}), len(outputs))
            self.assertEqual(len(set(outputs[0]['contracts'])), 2)
            self.assertEqual(outputs[0]['calculation'], DETERMINISTIC_WEIGHT_CALCULATION)
            for result in outputs[1:]:
                self.assertEqual(result['contracts'], outputs[0]['contracts'])
                self.assertEqual(result['outputs'], outputs[0]['outputs'])
            return set(outputs[0]['outputs'])

    def test_prepare_emits_identical_weights_in_independent_processes(self):
        emitted = self.independent_analyses()
        for panel in PANELS:
            self.assertIn(f'{panel}/weights.csv', emitted)

    def test_r_scientific_outputs_are_identical_in_independent_processes(self):
        rscript = shutil.which('Rscript')
        if not rscript:
            self.skipTest('R unavailable')
        emitted = self.independent_analyses(rscript)
        for panel in PANELS:
            for artifact in ('ranking.csv', 'weight_uncertainty.csv', 'rounding_uncertainty.csv',
                             'shared_draw_ranks.csv'):
                self.assertIn(f'{panel}/{artifact}', emitted)


if __name__ == '__main__':
    if len(sys.argv) > 2 and sys.argv[1] == '--render':
        print(json.dumps(render(Path(sys.argv[2]), sys.argv[3] if len(sys.argv) > 3 else None)))
    else:
        unittest.main()
