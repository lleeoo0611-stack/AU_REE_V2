"""Check the Aim B comparison against small sealed R-style interchange fixtures."""

import csv
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from au_ree_v2.formal_resource_bridge import _FormalInputs
from au_ree_v2.resource_rank_uncertainty import (
    DRAW_IDENTITY, METHODS, NO_BOUNDS, RNG_VERSION, ROUNDING, SAMPLING_VERSION, WEIGHTS, compare_panel,
)
from au_ree_v2.store import digest, filehash


PANEL = 'six_domain'
SCENARIO = 'equal'


class RankUncertaintyTests(unittest.TestCase):
    def setUp(self):
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.directory = Path(tmp.name)

    def _run(self, name, projects=('a', 'b'), *, reversed_ranks=False, traces=True, seed=32, no_bounds=False,
             scope='shared scope', method_hash='a' * 64, bad_draw=False, weight_value=1):
        root = self.directory / name
        folder = root / PANEL
        folder.mkdir(parents=True)

        def csv_file(filename, rows):
            with (folder / filename).open('w', encoding='utf-8', newline='') as stream:
                writer = csv.DictWriter(stream, rows[0])
                writer.writeheader()
                writer.writerows(rows)

        matrix = [{'project_id': pid, 'scope': scope, 'R1': 0.7 if i else 0.2}
                  for i, pid in enumerate(projects)]
        criteria = [{'code': 'R1', 'direction': 'MAX'}]
        weights = [{'scenario': SCENARIO, 'criterion': 'R1', 'weight': weight_value}]
        csv_file('matrix.csv', matrix)
        csv_file('criteria.csv', criteria)
        csv_file('weights.csv', weights)
        csv_file('runtime.csv', [{'R_version': 'R version 4.5.0', 'seed': seed, 'reps': 3, 'threshold': 0.2,
                                 'concentration': 30, 'method_version': RNG_VERSION, 'identity': DRAW_IDENTITY,
                                 'RNG_kind': "L'Ecuyer-CMRG", 'normal_kind': 'Inversion', 'sample_kind': 'Rejection'}])
        csv_file('shared_draw_contract.csv', [{'contract': SAMPLING_VERSION, 'cohort': PANEL, 'seed': seed, 'reps': 3,
                                             'input_contract': RNG_VERSION, 'methods': '|'.join(METHODS),
                                             'draw_identity': DRAW_IDENTITY, 'unknown': 'NO_PROBABILITY_DISTRIBUTION_ASSIGNED',
                                             'detail': 'ALL_DRAW_RANKS' if traces else 'RECONSTRUCT_FROM_KEYED_INPUTS'}])

        summaries, weights_only, rounding_only, records = [], [], [], []
        for method in METHODS:
            for family in (WEIGHTS, ROUNDING):
                for i, project in enumerate(projects):
                    drawn = (2, 1, 2) if (i == 1) != reversed_ranks else (1, 2, 1)
                    for draw_id, rank in enumerate(drawn, 1):
                        records.append({'cohort': PANEL, 'scenario': SCENARIO, 'method': method,
                                        'uncertainty': family, 'project_id': project, 'draw_id': draw_id, 'rank': rank})
                    unquantified = family == ROUNDING and no_bounds
                    row = {'scenario': SCENARIO, 'project_id': project, 'uncertainty': NO_BOUNDS if unquantified else family,
                           'median': None if unquantified else drawn[0], 'q05': None if unquantified else (1.1 if drawn[0] == 2 else 1),
                           'q95': None if unquantified else (2 if drawn[0] == 2 else 1.9),
                           'frequency_first': None if unquantified else drawn.count(1) / 3,
                           'frequency_top3': None, 'frequency_top5': None}
                    summaries.append({**row, 'cohort': PANEL, 'method': method, 'seed': seed, 'draws': 3,
                                      'draw_contract': f'{RNG_VERSION}/{SAMPLING_VERSION}'})
                    if method == 'PROMETHEE_II':
                        (weights_only if family == WEIGHTS else rounding_only).append(row)
        csv_file('uncertainty_by_method.csv', summaries)
        csv_file('weight_uncertainty.csv', weights_only)
        csv_file('rounding_uncertainty.csv', rounding_only)
        if traces:
            # The persisted row order is immaterial to the draw identity.
            if bad_draw:
                records[-1] = records[-2]
            csv_file('shared_draw_ranks.csv', records if not reversed_ranks else list(reversed(records)))

        def hashes():
            return {path.relative_to(root).as_posix(): filehash(path) for path in folder.iterdir()}

        contract = {'version': 'mcda-input-cache-v2', 'panel': PANEL, 'stage': 'core',
                    'vanilla': True, 'analysis': 'evidence-cohort-v1', 'sampling': SAMPLING_VERSION,
                    'R': {'executable_sha256': 'b' * 64},
                    'programs': {'methods.R': method_hash, 'run_mcda.R': 'c' * 64},
                    'inputs': {key: sha for key, sha in hashes().items()
                               if key.endswith(('matrix.csv', 'criteria.csv', 'weights.csv'))},
                    'threshold': 0.2, 'monte_carlo': {'dirichlet_concentration': 30.0, 'seed': seed,
                                                     'reps': 3, 'method_version': RNG_VERSION}}
        receipt = {'contract': contract, 'key': digest(contract), 'status': 'REUSED_VERIFIED'}
        (folder / 'r_cache.json').write_text(json.dumps(receipt), encoding='utf-8')
        (root / 'summary.json').write_text(json.dumps({'status': 'COMPLETED', 'output_hashes': hashes()}), encoding='utf-8')
        return _FormalInputs(root)

    @staticmethod
    def _compare(before, after):
        inputs = [run.csv(f'{PANEL}/{kind}.csv') for kind in ('matrix', 'criteria', 'weights') for run in (before, after)]
        return compare_panel(before, after, PANEL, *inputs)

    def test_matches_reordered_saved_draw_keys_and_uses_r_quantiles(self):
        report = self._compare(self._run('old'), self._run('new', reversed_ranks=True))
        paired = report['draw_pairing']
        self.assertEqual(paired['status'], 'PAIRED_VERIFIED_DRAW_RANKS')
        self.assertEqual(paired['paired_groups'], 12)
        a = next(item for item in paired['paired_rank_differences'] if item['project_id'] == 'a')
        self.assertEqual(a['rank_delta_counts'], [{'rank_delta': -1, 'draws': 1}, {'rank_delta': 1, 'draws': 2}])
        self.assertAlmostEqual(a['q05_rank_delta'], -0.8)
        self.assertEqual(a['median_rank_delta'], 1)

    def test_pairing_withheld_when_the_actual_weight_vector_differs(self):
        old = self._run('old')
        for name, weight in (('one-ulp', 1.0000000000000002), ('different', 0.9)):
            with self.subTest(name=name):
                invalid = self._compare(old, self._run(name, weight_value=weight))
                self.assertFalse(invalid['draw_contracts']['weight_rows_identical'])
                self.assertEqual(invalid['draw_pairing'], {
                    'status': 'RESEARCH_OR_DRAW_CONTRACT_UNVERIFIED_OR_CHANGED',
                    'reason': 'ACTUAL_WEIGHT_ROWS_DIFFER',
                })
                levels = invalid['summaries']['weight_uncertainty.csv']['common_project_metrics']
                self.assertNotIn('marginal_summary_delta', levels[0])

    def test_missing_detailed_ranks_uses_marginal_summaries_only(self):
        report = self._compare(self._run('old', traces=False), self._run('new', traces=False, reversed_ranks=True))
        self.assertEqual(report['draw_pairing']['status'], 'KEYED_CONTRACT_MATCHES_ACTUAL_DRAW_RANKS_NOT_AVAILABLE')
        self.assertNotIn('paired_rank_differences', report['draw_pairing'])
        a = report['summaries']['weight_uncertainty.csv']['common_project_metrics'][0]
        self.assertEqual(a['marginal_summary_delta']['median'], 1)
        self.assertNotIn('frequency_top3', a['marginal_summary_delta'])

    def test_cohort_turnover_keeps_shared_levels_and_separate_entry_exit(self):
        report = self._compare(self._run('old'), self._run('new', projects=('a', 'c'), reversed_ranks=True))
        self.assertEqual(report['draw_pairing']['status'], 'WITHHELD_COHORT_OR_SCOPE_CHANGED')
        self.assertEqual(report['cohorts']['common_projects_same_semantics'], ['a'])
        weight = report['summaries']['weight_uncertainty.csv']
        self.assertEqual(weight['baseline_full_cohort_rows'], 2)
        self.assertEqual(weight['updated_full_cohort_rows'], 2)
        self.assertEqual(weight['baseline_other_project_metrics'][0]['project_id'], 'b')
        self.assertEqual(weight['updated_other_project_metrics'][0]['project_id'], 'c')
        self.assertNotIn('marginal_summary_delta', weight['common_project_metrics'][0])

    def test_changed_scope_seed_and_r_program_withhold_rank_deltas(self):
        before = self._run('old')
        cases = {'changed scope': ({'scope': 'different scope'}, 'WITHHELD_COHORT_OR_SCOPE_CHANGED'),
                 'changed seed': ({'seed': 40}, 'RESEARCH_OR_DRAW_CONTRACT_UNVERIFIED_OR_CHANGED'),
                 'changed program': ({'method_hash': 'd' * 64}, 'R_PROGRAMS_RUNTIME_OR_INPUT_SEALS_UNVERIFIED_OR_CHANGED')}
        for name, (settings, status) in cases.items():
            with self.subTest(name=name):
                report = self._compare(before, self._run(name, **settings))
                self.assertEqual(report['draw_pairing']['status'], status)
                self.assertTrue(all('marginal_summary_delta' not in row for group in report['summaries'].values()
                                    for row in group['common_project_metrics']))

    def test_source_bounds_unavailable_means_no_paired_rounding_deltas(self):
        report = self._compare(self._run('old', no_bounds=True), self._run('new', no_bounds=True))
        paired = report['draw_pairing']
        self.assertEqual(paired['source_rounding_groups_without_reported_bounds'], 6)
        self.assertEqual(paired['paired_groups'], 6)
        self.assertTrue(all(row['uncertainty'] == WEIGHTS for row in paired['paired_rank_differences']))

    def test_duplicate_saved_draw_is_rejected_even_if_its_file_is_sealed(self):
        with self.assertRaisesRegex(ValueError, 'RANK_UNCERTAINTY_DUPLICATE_DRAW_KEY'):
            self._compare(self._run('old'), self._run('new', bad_draw=True))
