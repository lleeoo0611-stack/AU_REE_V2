"""Test leakage boundaries and the different meanings of utilities/probabilities."""

import copy
import importlib.util
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import unittest

from au_ree_v2.experiment_models import fit_predict


def row(case_id, value, label=None, project_id=None, **features):
    return {'case_id': case_id, 'project_id': project_id or case_id,
            'features': {'x': value, **features}, 'label': label}


class ExperimentModelsTests(unittest.TestCase):
    def test_import_does_not_load_learning_dependencies(self):
        root = Path(__file__).resolve().parents[1]
        environment = dict(os.environ)
        environment['PYTHONPATH'] = str(root / 'src') + os.pathsep + environment.get('PYTHONPATH', '')
        result = subprocess.run([
            sys.executable, '-c',
            "import sys; import au_ree_v2.experiment_models; "
            "assert not any(n in sys.modules for n in ('numpy','scipy','sklearn'))",
        ], env=environment, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_prior_uses_training_prevalence_and_counts_projects(self):
        train = [row('t3', 3, 1, 'p2'), row('t1', 1, 0, 'p1'), row('t2', 2, 0, 'p1')]
        test = [row('e2', 200, 1), row('e1', None, 0)]
        result = fit_predict(train, test, ['x'], 'prior', 7)
        self.assertEqual([r['case_id'] for r in result['predictions']], ['e1', 'e2'])
        self.assertEqual([r['prediction'] for r in result['predictions']], [1 / 3, 1 / 3])
        self.assertEqual(result['metrics']['train']['rows'], 3)
        self.assertEqual(result['metrics']['train']['projects'], 2)
        self.assertEqual(result['metrics']['train']['class_counts'], {'0': 2, '1': 1})
        self.assertAlmostEqual(result['metrics']['brier_score'], 5 / 18)
        self.assertAlmostEqual(result['metrics']['log_loss'], -(math.log(1 / 3) + math.log(2 / 3)) / 2)
        self.assertEqual(result['metrics']['roc_auc'], .5)
        self.assertEqual(result, fit_predict(train[::-1], test[::-1], ['x'], 'prior', 7))
        json.dumps(result, allow_nan=False)

    def test_single_class_test_retains_brier_but_not_auc(self):
        result = fit_predict([row('t', None, 0)], [row('e', None, 1)], [], 'prior', 0)
        self.assertEqual(result['metrics']['brier_score'], 1)
        self.assertIsNone(result['metrics']['roc_auc'])
        self.assertEqual(result['metrics']['roc_auc_status'], 'UNDEFINED_SINGLE_TEST_CLASS')
        self.assertTrue(math.isfinite(result['metrics']['log_loss']))

    def test_invalid_values_labels_identifiers_and_seed_fail(self):
        train, test = [row('t', 1, 0)], [row('e', 2, 1)]
        for invalid in (float('nan'), float('inf'), True, '2'):
            with self.subTest(value=invalid), self.assertRaises(ValueError):
                fit_predict(train, [row('e', invalid, 1)], ['x'], 'prior', 0)
        for label in (None, 2, '1'):
            with self.subTest(label=label), self.assertRaises(ValueError):
                fit_predict(train, [row('e', 2, label)], ['x'], 'prior', 0)
        for bad_features in (['x', 'x'], 'x'):
            with self.assertRaises(ValueError):
                fit_predict(train, test, bad_features, 'prior', 0)
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            fit_predict(train + train, test, ['x'], 'prior', 0)
        with self.assertRaisesRegex(ValueError, 'overlap'):
            fit_predict(train, train, ['x'], 'prior', 0)
        with self.assertRaises(ValueError):
            fit_predict(train, test, ['x'], 'prior', -1)

    def test_mcda_missing_values_remain_bounds(self):
        criteria = {'x': {'low': 0, 'high': 100, 'function': 'linear', 'direction': 'MAX'}}
        test = [row('b', 80), row('a', None)]
        before = copy.deepcopy(test)
        result = fit_predict([], test, ['x'], 'fixed_mcda', 3, criteria, {'x': 1})
        unknown, known = result['predictions']
        self.assertEqual(unknown['kind'], 'mcda_intervals')
        self.assertEqual(unknown['unknown_features'], ['x'])
        self.assertEqual(unknown['prediction']['SAW'],
                         {'score_lower': 0, 'score_upper': 1, 'rank_best': 1, 'rank_worst': 2})
        self.assertAlmostEqual(known['prediction']['SAW']['score_lower'], .8)
        self.assertEqual(set(unknown['prediction']), {'SAW', 'TOPSIS', 'PROMETHEE_II'})
        self.assertNotIn('brier_score', result['metrics'])
        self.assertNotIn('log_loss', result['metrics'])
        self.assertEqual(test, before)
        self.assertEqual(result, fit_predict([], test[::-1], ['x'], 'fixed_mcda', 3, criteria, {'x': 1}))
        json.dumps(result, allow_nan=False)

    def test_mcda_reuses_fixed_direction_log_scale_and_normalized_weights(self):
        criteria = {
            'x': {'low': 0, 'high': 99, 'function': 'log1p', 'direction': 'MAX'},
            'distance': {'low': 0, 'high': 100, 'function': 'linear', 'direction': 'MIN'},
        }
        result = fit_predict([], [row('a', 9, distance=0), row('b', 99, distance=100)],
                             ['x', 'distance'], 'fixed_mcda', 0, criteria, {'x': 2, 'distance': 2})
        self.assertEqual(result['model']['feature_order'], ['distance', 'x'])
        self.assertEqual(result['model']['normalized_weights'], {'distance': .5, 'x': .5})
        self.assertAlmostEqual(result['predictions'][0]['prediction']['SAW']['score_lower'], .75)
        self.assertAlmostEqual(result['predictions'][1]['prediction']['SAW']['score_lower'], .5)

    def test_mcda_rejects_invalid_scales_and_weights(self):
        criterion = {'low': 0, 'high': 100, 'function': 'linear', 'direction': 'MAX'}
        for weights in ({'x': -1}, {'x': 0}, {'x': float('nan')}, {'y': 1}, {'x': 1, 'y': 1}):
            with self.subTest(weights=weights), self.assertRaises(ValueError):
                fit_predict([], [row('a', None)], ['x'], 'fixed_mcda', 0, {'x': criterion}, weights)
        for patch in ({'high': 0}, {'low': float('inf')}, {'direction': 'UP'},
                      {'function': 'learned'}, {'function': 'log1p', 'low': -1},
                      {'function': 'log1p', 'low': 1e100, 'high': math.nextafter(1e100, math.inf)},
                      {'low': -1e308, 'high': 1e308}):
            with self.subTest(patch=patch), self.assertRaises(ValueError):
                fit_predict([], [row('a', None)], ['x'], 'fixed_mcda', 0,
                            {'x': {**criterion, **patch}}, {'x': 1})
        with self.assertRaisesRegex(ValueError, 'finite positive sum'):
            fit_predict([], [row('a', 2, other=3)], ['x', 'other'], 'fixed_mcda', 0,
                        {'x': criterion, 'other': criterion}, {'x': 1e308, 'other': 1e308})


@unittest.skipUnless(importlib.util.find_spec('sklearn'), 'optional scikit-learn dependency absent')
class LogisticExperimentTests(unittest.TestCase):
    def test_test_extremes_do_not_change_fitted_preprocessing(self):
        train = [row('t1', -2, 0), row('t2', -1, 0), row('t3', 1, 1), row('t4', 2, 1)]
        before = copy.deepcopy(train)
        first = fit_predict(train, [row('e1', 0, 0), row('e2', 3, 1)], ['x'], 'logistic', 19)
        extreme = fit_predict(train, [row('e1', -1000000, 0), row('e2', 1000000, 1)], ['x'], 'logistic', 19)
        self.assertEqual(first['model'], extreme['model'])
        self.assertEqual(first['model']['imputer']['statistics'], {'x': 0})
        self.assertEqual(first['model']['scaler']['mean'], {'x': 0})
        self.assertAlmostEqual(first['model']['scaler']['scale']['x'], math.sqrt(2.5))
        self.assertEqual(train, before)
        json.dumps(first, allow_nan=False)

    def test_missing_train_values_use_only_train_median_and_indicator(self):
        train = [row('t1', -2, 0), row('t2', None, 0), row('t3', 1, 1), row('t4', 2, 1)]
        test = [row('e2', 1000, 1), row('e1', None, 0)]
        result = fit_predict(train, test, ['x'], 'logistic', 4)
        self.assertEqual(result['model']['imputer']['statistics'], {'x': 1})
        self.assertEqual(result['model']['imputer']['indicator_features'], ['x'])
        self.assertEqual(result['model']['transformed_feature_order'], ['x', 'missingindicator_x'])
        self.assertEqual(result['model']['scaler']['mean']['x'], .5)
        self.assertEqual(result['model']['scaler']['mean']['missingindicator_x'], .25)
        self.assertTrue(all(0 <= r['prediction'] <= 1 for r in result['predictions']))
        self.assertEqual(result, fit_predict(train[::-1], test[::-1], ['x'], 'logistic', 4))

    def test_all_missing_train_feature_and_one_class_training_are_blocked(self):
        with self.assertRaisesRegex(ValueError, 'ALL_MISSING_TRAIN_FEATURES'):
            fit_predict([row('t1', None, 0), row('t2', None, 1)],
                        [row('e1', 4, 1)], ['x'], 'logistic', 0)
        with self.assertRaisesRegex(ValueError, 'both observed label classes'):
            fit_predict([row('t1', 1, 0), row('t2', 2, 0)],
                        [row('e1', 4, 1)], ['x'], 'logistic', 0)


@unittest.skipUnless(importlib.util.find_spec('scipy'), 'optional scipy dependency absent')
class OutcomeMcdaTests(unittest.TestCase):
    def criterion(self, direction='MAX', function='linear', high=100):
        return {'low': 0, 'high': high, 'function': function, 'direction': direction}

    def test_nonnegative_weights_and_probability_decomposition(self):
        train = [row('t1', 0, 0, distance=100), row('t2', 10, 0, distance=90),
                 row('t3', 90, 1, distance=10), row('t4', 100, 1, distance=0)]
        test = [row('e2', 75, 1, distance=25), row('e1', 25, 0, distance=75)]
        criteria = {'x': self.criterion(), 'distance': self.criterion(direction='MIN')}
        before = copy.deepcopy((train, test, criteria))
        result = fit_predict(train, test, ['x', 'distance'], 'outcome_mcda', 8, criteria)
        fitted = result['model']
        self.assertTrue(all(value >= 0 for value in fitted['coefficients'].values()))
        self.assertAlmostEqual(sum(fitted['learned_mcda_weights'].values()), 1)
        self.assertGreater(fitted['strength'], 0)
        self.assertEqual(fitted['regularization']['lambda'], .01)
        self.assertEqual(fitted['interpretation'], 'OUTCOME_FITTED_MONOTONE_UTILITY_NOT_EXPERT_PREFERENCE')
        for prediction in result['predictions']:
            score_value = prediction['utility_score']
            self.assertTrue(0 <= score_value <= 1)
            self.assertAlmostEqual(score_value, sum(prediction['contributions'].values()))
            logit = fitted['intercept'] + fitted['strength'] * score_value
            self.assertAlmostEqual(logit, fitted['intercept'] + sum(prediction['logit_contributions'].values()))
            self.assertAlmostEqual(prediction['prediction'], 1 / (1 + math.exp(-logit)))
        self.assertEqual((train, test, criteria), before)
        reordered = fit_predict(train[::-1], test[::-1], ['distance', 'x'], 'outcome_mcda', 8, criteria)
        self.assertEqual(result, reordered)
        self.assertEqual(result, fit_predict(train, test, ['x', 'distance'], 'outcome_mcda', 8,
                                             criteria, weights={'x': -999}))
        json.dumps(result, allow_nan=False)

    def test_raw_train_median_precedes_fixed_log_scoring_and_ignores_test(self):
        train = [row('t1', 0, 0), row('t2', None, 0), row('t3', 9, 1), row('t4', 99, 1)]
        criteria = {'x': self.criterion(function='log1p', high=99)}
        result = fit_predict(train, [row('e1', None, 0), row('e2', 20, 1)],
                             ['x'], 'outcome_mcda', 0, criteria)
        changed = fit_predict(train, [row('e1', None, 1), row('e2', 1e6, 0)],
                              ['x'], 'outcome_mcda', 0, criteria)
        self.assertEqual(result['model'], changed['model'])
        self.assertEqual(result['model']['imputer']['statistics'], {'x': 9})
        self.assertFalse(result['model']['imputer']['add_indicator'])
        self.assertEqual(result['model']['imputer']['space'], 'RAW_FEATURE_VALUES_BEFORE_FIXED_UTILITY_SCORING')
        self.assertIsNone(result['model']['scaler'])
        self.assertEqual(result['predictions'][0]['imputed_features'], ['x'])
        self.assertAlmostEqual(result['predictions'][0]['utility_score'], .5)

    def test_min_direction_gives_monotone_decreasing_raw_predictions(self):
        train = [row('t1', 0, 1), row('t2', 10, 1), row('t3', 90, 0), row('t4', 100, 0)]
        result = fit_predict(train, [row('e1', 0, 1), row('e2', 100, 0)],
                             ['x'], 'outcome_mcda', 0, {'x': self.criterion(direction='MIN')})
        self.assertGreater(result['predictions'][0]['prediction'], result['predictions'][1]['prediction'])
        self.assertEqual(result['model']['learned_mcda_weights'], {'x': 1})

    def test_zero_directional_signal_does_not_invent_weights(self):
        cases = [
            [row('t1', 50, 0), row('t2', 50, 0), row('t3', 50, 1)],
            [row('t1', 0, 1), row('t2', 10, 1), row('t3', 90, 0), row('t4', 100, 0)],
        ]
        for train in cases:
            with self.subTest(train=train):
                result = fit_predict(train, [row('e1', 0, 0), row('e2', 100, 1)],
                                     ['x'], 'outcome_mcda', 0, {'x': self.criterion()})
                fitted = result['model']
                self.assertIsNone(fitted['learned_mcda_weights'])
                self.assertEqual(fitted['weight_status'], 'NO_DIRECTIONAL_SIGNAL')
                self.assertLessEqual(fitted['strength'], fitted['weight_normalization_tolerance'])
                for prediction in result['predictions']:
                    self.assertIsNone(prediction['utility_score'])
                    self.assertIsNone(prediction['contributions'])
                    self.assertAlmostEqual(prediction['prediction'], 1 / (1 + math.exp(-fitted['intercept'])))
                self.assertTrue(math.isfinite(result['metrics']['brier_score']))

    def test_missing_features_single_class_and_invalid_scale_are_blocked(self):
        criteria = {'x': self.criterion()}
        with self.assertRaisesRegex(ValueError, 'ALL_MISSING_TRAIN_FEATURES'):
            fit_predict([row('t1', None, 0), row('t2', None, 1)], [row('e1', 5, 1)],
                        ['x'], 'outcome_mcda', 0, criteria)
        with self.assertRaisesRegex(ValueError, 'both observed label classes'):
            fit_predict([row('t1', 0, 0), row('t2', 10, 0)], [row('e1', 5, 1)],
                        ['x'], 'outcome_mcda', 0, criteria)
        for invalid in ({}, {'x': {**self.criterion(), 'direction': 'UP'}}):
            with self.assertRaises(ValueError):
                fit_predict([row('t1', 0, 0), row('t2', 100, 1)], [row('e1', 5, 1)],
                            ['x'], 'outcome_mcda', 0, invalid)


if __name__ == '__main__':
    unittest.main()
