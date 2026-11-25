"""Point-in-time evidence and outcome regressions for experiment exports."""
import copy
import json
import tempfile
import unittest
from pathlib import Path

from au_ree_v2.experiment_data import load_dataset, validate_cases


SHA = 'a' * 64


def case(case_id='case-1', project_id='project-1'):
    return {
        'case_id': case_id, 'project_id': project_id, 'country': 'AUS',
        'commodity': 'REE', 'scope': 'PROJECT', 'as_of': '2021-01-01',
        'at_risk': True, 'features': {'resource': 100.0},
        'lineage': {'resource': {
            'observation_ids': ['obs-1'], 'source_sha256': SHA,
            'locator': 'physical PDF p. 10', 'known_at': '2020-12-01',
            'known_at_basis': 'VERIFIED_PUBLICATION', 'effective_date': '2020-10-01',
            'unit': 'kt TREO', 'basis': 'WHOLE_ORE_TREO_INCLUDING_Y',
        }},
        'outcome': {
            'target': 'FID', 'event_status': 'OBSERVED', 'event_date': '2021-08-01',
            'known_at': '2021-08-03', 'followup_end': None,
            'source_sha256': SHA, 'locator': 'physical PDF p. 2',
        },
    }


def dataset(*cases):
    return {'schema_version': 'experiment-dataset-v1', 'synthetic': True,
            'identity_map_sha256': SHA, 'cases': list(cases or [case()])}


def validate(data=None, **kwargs):
    args = dict(target='FID', horizon_days=365, evaluation_as_of='2023-01-01',
                required_features=['resource'])
    args.update(kwargs)
    return validate_cases(data or dataset(), **args)


class ExperimentDataTests(unittest.TestCase):
    def test_observed_first_event_is_positive_and_input_unchanged(self):
        data = dataset()
        original = copy.deepcopy(data)
        result = validate(data)
        row = result['cases'][0]
        self.assertEqual((row['label'], row['label_status']), (1, 'POSITIVE'))
        self.assertEqual(row['horizon_end'], '2022-01-01')
        self.assertEqual(row['label_available_at'], '2021-08-03')
        self.assertEqual(data, original)
        self.assertFalse(result['summary']['source_documents_reverified'])
        self.assertEqual(result['summary']['input_projects'], 1)

    def test_observed_event_at_horizon_is_included(self):
        row = case()
        row['outcome'].update(event_date='2022-01-01', known_at='2022-01-01')
        self.assertEqual(validate(dataset(row))['cases'][0]['label'], 1)

    def test_negative_requires_explicit_full_followup(self):
        row = case()
        row['outcome'].update(event_status='NO_EVENT_VERIFIED', event_date=None,
                              followup_end='2022-01-01', known_at='2022-01-05')
        result = validate(dataset(row))['cases'][0]
        self.assertEqual((result['label'], result['label_status']), (0, 'NEGATIVE'))
        self.assertEqual(result['label_available_at'], '2022-01-05')
        for followup in [None, '2021-12-31']:
            with self.subTest(followup=followup):
                row['outcome']['followup_end'] = followup
                result = validate(dataset(row))['cases'][0]
                self.assertIsNone(result['label'])
                self.assertEqual(result['label_status'], 'CENSORED')

    def test_later_event_requires_followup_to_establish_negative(self):
        row = case()
        row['outcome'].update(event_date='2022-02-01', known_at='2022-02-02')
        self.assertEqual(validate(dataset(row))['cases'][0]['label_status'], 'CENSORED')
        row['outcome']['followup_end'] = '2022-01-01'
        result = validate(dataset(row))['cases'][0]
        self.assertEqual((result['label'], result['label_status']), (0, 'NEGATIVE'))

    def test_planned_unknown_and_censored_are_never_zero(self):
        for status in ['PLANNED', 'UNKNOWN', 'CENSORED']:
            with self.subTest(status=status):
                row = case()
                row['outcome'].update(event_status=status, event_date=None,
                                      followup_end='2022-01-01', known_at='2022-01-05')
                result = validate(dataset(row))['cases'][0]
                self.assertIsNone(result['label'])
                self.assertIsNone(result['label_available_at'])

    def test_outcome_disclosed_after_evaluation_is_unknown(self):
        row = case()
        row['outcome']['known_at'] = '2024-01-01'
        result = validate(dataset(row))['cases'][0]
        self.assertIsNone(result['label'])
        self.assertEqual(result['label_reason'], 'OUTCOME_NOT_KNOWN_AT_EVALUATION')

    def test_event_cannot_be_known_before_it_occurs(self):
        row = case()
        row['outcome']['known_at'] = '2021-07-01'
        result = validate(dataset(row))['cases'][0]
        self.assertIsNone(result['label'])
        self.assertEqual(result['label_reason'], 'OUTCOME_KNOWN_BEFORE_EVENT')

    def test_future_followup_cannot_support_a_negative(self):
        row = case()
        row['outcome'].update(event_status='NO_EVENT_VERIFIED', event_date=None,
                              followup_end='2022-06-01', known_at='2022-01-05')
        result = validate(dataset(row))['cases'][0]
        self.assertIsNone(result['label'])
        self.assertEqual(result['label_reason'], 'FOLLOWUP_AFTER_DISCLOSURE')

    def test_missing_outcome_source_never_creates_a_label(self):
        for key in ['source_sha256', 'locator', 'known_at']:
            with self.subTest(key=key):
                row = case()
                row['outcome'][key] = None
                result = validate(dataset(row))['cases'][0]
                self.assertIsNone(result['label'])
                self.assertEqual(result['label_reason'], 'OUTCOME_PROVENANCE_INCOMPLETE')

    def test_feature_availability_and_effective_time_exclude_case(self):
        for key, reason in [('known_at', 'FEATURE_KNOWN_AFTER_AS_OF'),
                            ('effective_date', 'FEATURE_EFFECTIVE_AFTER_AS_OF')]:
            with self.subTest(key=key):
                row = case()
                row['lineage']['resource'][key] = '2021-01-02'
                result = validate(dataset(row))
                self.assertEqual(result['cases'], [])
                self.assertEqual(result['exclusions'][0]['reason'], reason)
                self.assertEqual(result['exclusions'][0]['feature'], 'resource')

    def test_missing_feature_lineage_excludes_numeric_case(self):
        row = case()
        row['lineage'] = {}
        result = validate(dataset(row))
        self.assertEqual(result['exclusions'][0]['reason'], 'FEATURE_LINEAGE_MISSING')
        row = case()
        row['lineage']['resource']['observation_ids'] = []
        self.assertEqual(validate(dataset(row))['exclusions'][0]['reason'],
                         'FEATURE_LINEAGE_INCOMPLETE')

    def test_missing_numeric_values_remain_missing(self):
        row = case()
        row['features']['resource'] = None
        row['lineage'] = {}
        result = validate(dataset(row), required_features=['resource', 'distance'])
        self.assertEqual(result['cases'][0]['features'], {'resource': None, 'distance': None})
        self.assertEqual(result['summary']['missing_feature_values'], {'resource': 1, 'distance': 1})

    def test_already_occurred_and_non_risk_cases_are_excluded(self):
        for changes in [{'event_date': '2021-01-01'}, {'event_date': '2020-01-01'}]:
            row = case()
            row['outcome'].update(changes)
            self.assertEqual(validate(dataset(row))['exclusions'][0]['reason'], 'ALREADY_OCCURRED')
        row = case()
        row['at_risk'] = False
        self.assertEqual(validate(dataset(row))['exclusions'][0]['reason'], 'ALREADY_OCCURRED')

    def test_partial_invalid_and_noncanonical_dates_are_rejected(self):
        for value in ['2021', '2021-08', '2021-8-01', '2021-02-29', '2021-08-01T00:00:00']:
            with self.subTest(value=value):
                row = case()
                row['outcome']['event_date'] = value
                with self.assertRaises(ValueError):
                    validate(dataset(row))

    def test_duplicate_cases_and_project_identity_conflicts_raise(self):
        with self.assertRaisesRegex(ValueError, 'Duplicate case_id'):
            validate(dataset(case(), case()))
        for field, value in [('country', 'CAN'), ('commodity', 'GOLD')]:
            with self.subTest(field=field):
                other = case('case-2')
                other[field] = value
                with self.assertRaisesRegex(ValueError, 'Conflicting country or commodity'):
                    validate(dataset(case(), other))

    def test_different_case_ids_cannot_duplicate_a_project_snapshot(self):
        other = case('different-case-id')
        with self.assertRaisesRegex(ValueError, 'Duplicate project snapshot'):
            validate(dataset(case(), other))

    def test_distinct_snapshots_can_share_the_same_first_event(self):
        earlier = case('earlier-case')
        earlier['as_of'] = '2020-12-15'
        result = validate(dataset(earlier, case()))
        self.assertEqual([r['label'] for r in result['cases']], [1, 1])
        self.assertEqual(result['summary']['input_cases'], 2)
        self.assertEqual(result['summary']['input_projects'], 1)

    def test_first_event_dates_must_agree_across_snapshots(self):
        earlier = case('earlier-case')
        earlier['as_of'] = '2020-12-15'
        earlier['outcome'].update(event_date='2021-07-01', known_at='2021-07-03')
        for rows in [(earlier, case()), (case(), earlier)]:
            with self.subTest(order=rows[0]['case_id']):
                with self.assertRaisesRegex(ValueError, 'Conflicting first-event dates'):
                    validate(dataset(*rows))

    def test_known_first_event_excludes_a_later_unknown_snapshot(self):
        later = case('later-unknown')
        later['as_of'] = '2021-09-01'
        later['outcome'].update(event_status='UNKNOWN', event_date=None, known_at=None,
                                source_sha256=None, locator=None)
        for rows in [(case(), later), (later, case())]:
            with self.subTest(order=rows[0]['case_id']):
                result = validate(dataset(*rows))
                self.assertEqual([r['case_id'] for r in result['cases']], ['case-1'])
                self.assertEqual(result['exclusions'], [{'case_id': 'later-unknown',
                                 'project_id': 'project-1', 'reason': 'ALREADY_OCCURRED'}])

    def _assert_unqualified_event_cannot_affect_other_snapshots(self, changes, reason):
        observed = case()
        observed['outcome'].update(changes)
        later = case('later-unknown')
        later['as_of'] = '2021-09-01'
        later['outcome'].update(event_status='UNKNOWN', event_date=None, known_at=None,
                                source_sha256=None, locator=None)
        negative = case('earlier-negative')
        negative['as_of'] = '2020-12-15'
        negative['outcome'].update(event_status='NO_EVENT_VERIFIED', event_date=None,
                                   followup_end='2021-12-31', known_at='2022-01-05')
        for rows in [(observed, later, negative), (negative, later, observed)]:
            with self.subTest(order=rows[0]['case_id']):
                result = validate(dataset(*rows))
                by_id = {row['case_id']: row for row in result['cases']}
                self.assertEqual(result['exclusions'], [])
                self.assertEqual(len(by_id), 3)
                self.assertIsNone(by_id['case-1']['label'])
                self.assertEqual(by_id['case-1']['label_reason'], reason)
                self.assertIsNone(by_id['later-unknown']['label'])
                self.assertEqual(by_id['later-unknown']['label_status'], 'UNKNOWN')
                self.assertEqual(by_id['earlier-negative']['label'], 0)

    def test_missing_event_provenance_cannot_change_other_snapshots(self):
        for changes in [{'source_sha256': None}, {'locator': None},
                        {'locator': '  '}, {'known_at': None}]:
            with self.subTest(changes=changes):
                self._assert_unqualified_event_cannot_affect_other_snapshots(
                    changes, 'OUTCOME_PROVENANCE_INCOMPLETE')

    def test_event_disclosed_after_cutoff_cannot_change_other_snapshots(self):
        self._assert_unqualified_event_cannot_affect_other_snapshots(
            {'known_at': '2024-01-01'}, 'OUTCOME_NOT_KNOWN_AT_EVALUATION')

    def test_event_disclosed_before_occurrence_cannot_change_other_snapshots(self):
        self._assert_unqualified_event_cannot_affect_other_snapshots(
            {'known_at': '2021-07-01'}, 'OUTCOME_KNOWN_BEFORE_EVENT')

    def test_unqualified_raw_first_event_dates_must_still_agree(self):
        other = case('unqualified-other')
        other['as_of'] = '2020-12-15'
        other['outcome'].update(event_date='2021-07-01', source_sha256=None)
        with self.assertRaisesRegex(ValueError, 'Conflicting first-event dates'):
            validate(dataset(case(), other))

    def test_verified_no_event_before_later_first_event_is_compatible(self):
        earlier = case('earlier-negative')
        earlier['as_of'] = '2020-01-01'
        earlier['lineage']['resource'].update(known_at='2019-12-01',
                                               effective_date='2019-10-01')
        earlier['outcome'].update(event_status='NO_EVENT_VERIFIED', event_date=None,
                                  followup_end='2020-12-31', known_at='2021-01-05')
        result = validate(dataset(earlier, case()))
        self.assertEqual([r['label'] for r in result['cases']], [0, 1])

    def test_no_event_followup_cannot_cover_an_observed_first_event(self):
        for followup in ['2021-08-01', '2021-08-02']:
            with self.subTest(followup=followup):
                earlier = case('contradictory-negative')
                earlier['as_of'] = '2020-12-15'
                earlier['outcome'].update(event_status='NO_EVENT_VERIFIED', event_date=None,
                                          followup_end=followup, known_at='2021-09-01')
                with self.assertRaisesRegex(ValueError, 'No-event follow-up contradicts'):
                    validate(dataset(case(), earlier))

    def test_unqualified_no_event_claim_does_not_invalidate_observed_event(self):
        for changes in [{'source_sha256': None}, {'locator': None},
                        {'known_at': None}, {'known_at': '2024-01-01'},
                        {'known_at': '2021-08-01'}]:
            with self.subTest(changes=changes):
                earlier = case('unqualified-negative')
                earlier['as_of'] = '2020-12-15'
                earlier['outcome'].update(event_status='NO_EVENT_VERIFIED', event_date=None,
                                          followup_end='2021-12-31', known_at='2022-01-05')
                earlier['outcome'].update(changes)
                result = validate(dataset(case(), earlier))
                self.assertEqual(result['cases'][0]['label'], 1)
                self.assertIsNone(result['cases'][1]['label'])
                self.assertEqual(result['cases'][1]['label_status'], 'UNKNOWN')

    def test_risk_set_and_snapshot_identity_are_target_specific(self):
        production = case('production-case')
        production['outcome'].update(target='PRODUCTION', event_date='2022-01-01',
                                     known_at='2022-01-02')
        # The same project and as-of can legitimately have different targets.
        result = validate(dataset(case(), production), target='PRODUCTION')
        self.assertEqual([r['case_id'] for r in result['cases']], ['production-case'])
        production['as_of'] = '2021-09-01'
        production['outcome'].update(event_status='UNKNOWN', event_date=None, known_at=None)
        result = validate(dataset(case(), production), target='PRODUCTION')
        self.assertEqual(result['cases'][0]['case_id'], 'production-case')
        self.assertIsNone(result['cases'][0]['label'])

    def test_units_and_basis_cannot_be_pooled_by_feature_name(self):
        for field, value in [('unit', 't TREO'), ('basis', 'RESERVE_TREO_EXCLUDING_Y')]:
            with self.subTest(field=field):
                other = case('case-2', 'project-2')
                other['lineage']['resource'][field] = value
                with self.assertRaisesRegex(ValueError, 'Conflicting unit or basis'):
                    validate(dataset(case(), other))

    def test_nonfinite_boolean_and_string_features_raise(self):
        for value in [float('nan'), float('inf'), True, '100', 10 ** 1000]:
            with self.subTest(value_type=type(value).__name__):
                row = case()
                row['features']['resource'] = value
                with self.assertRaises(ValueError):
                    validate(dataset(row))

    def test_target_and_future_as_of_exclude_case(self):
        row = case()
        row['outcome']['target'] = 'PRODUCTION'
        self.assertEqual(validate(dataset(row))['exclusions'][0]['reason'], 'TARGET_MISMATCH')
        row = case()
        row['as_of'] = '2024-01-01'
        row['outcome'].update(event_status='UNKNOWN', event_date=None)
        self.assertEqual(validate(dataset(row))['exclusions'][0]['reason'], 'AS_OF_AFTER_EVALUATION')

    def test_required_contract_fields_and_arguments_are_checked(self):
        for key, value in [('synthetic', 1), ('schema_version', 'v0'),
                           ('identity_map_sha256', 'short')]:
            data = dataset()
            data[key] = value
            with self.assertRaises(ValueError):
                validate(data)
        for kwargs in [{'horizon_days': 0}, {'horizon_days': True},
                       {'required_features': 'resource'}, {'required_features': ['x', 'x']}]:
            with self.assertRaises(ValueError):
                validate(**kwargs)
        for field in ['known_at_basis', 'event_status']:
            row = case()
            parent = row['outcome'] if field == 'event_status' else row['lineage']['resource']
            parent[field] = []
            with self.assertRaises(ValueError):
                validate(dataset(row))

    def test_json_loader_rejects_duplicate_keys_and_nonfinite_literals(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'dataset.json'
            path.write_text(json.dumps(dataset()), encoding='utf8')
            self.assertEqual(load_dataset(path)['schema_version'], 'experiment-dataset-v1')
            for text in ['{"cases":[],"cases":[]}', '{"value":NaN}']:
                path.write_text(text, encoding='utf8')
                with self.assertRaises(ValueError):
                    load_dataset(path)


if __name__ == '__main__':
    unittest.main()
