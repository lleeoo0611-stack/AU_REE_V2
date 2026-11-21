import json
import unittest
from pathlib import Path

from au_ree_v2.census import summary_deposit_fields, summary_settings


class DepositHostTests(unittest.TestCase):
    def test_prospective_host_requires_its_separate_permission_and_retains_scope(self):
        rules, decisions = summary_settings(Path(__file__).resolve().parents[1])
        row = {'專案ID': 'site', '礦床型態': 'Possible clay-hosted REE mineralisation', '礦床型態代碼': ''}
        evidence = dict(source_sha256='report', obs_id='attribute', scope='Single licence, desktop target.',
                        locator='physical PDF p6', deposit_host_review=dict(
                            selected_mre_required=False, code='iac', host_style='CLAY_HOSTED_REE', evidence_level='EXPLORATION_MODEL_ONLY'))
        potential = rules['deposit_rules']['potential']
        without_potential = [d for d in decisions if d['rule'] != potential]
        results = []
        def record(*args):
            results.append(args)
        summary_deposit_fields(row, {}, [evidence], rules, without_potential, record)
        self.assertEqual(results, [])
        summary_deposit_fields(row, {}, [evidence], rules, decisions, record)
        self.assertEqual(results[0][:5], ('礦床型態代碼', 'iac', 'report', 'physical PDF p6', rules['deposit_rules']['clay']))
        scope = json.loads(results[0][5])
        self.assertEqual(scope['qualifier'], 'IONIC_NOT_CONFIRMED')
        self.assertEqual(scope['evidence_level'], 'EXPLORATION_MODEL_ONLY')
        self.assertEqual(scope['host_scope'], evidence['scope'])
        self.assertIn('potential_decision', scope)
        results.clear()
        evidence['deposit_host_review']['evidence_level'] = 'DRILL_CONFIRMED_HOST'
        summary_deposit_fields(row, {}, [evidence], rules, without_potential, record)
        self.assertEqual(json.loads(results[0][5])['evidence_level'], 'DRILL_CONFIRMED_HOST')
        results.clear()
        evidence['deposit_host_review']['evidence_level'] = 'UNKNOWN'
        summary_deposit_fields(row, {}, [evidence], rules, decisions, record)
        self.assertEqual(results, [])
        evidence['deposit_host_review'].update(evidence_level='EXPLORATION_MODEL_ONLY', code='hard', host_style='KIMBERLITE')
        summary_deposit_fields(row, {}, [evidence], rules, decisions, record)
        self.assertEqual(results, [])
