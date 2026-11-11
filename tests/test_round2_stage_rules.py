"""Offline regression for the fifteen explicitly approved second-round rows."""
import copy
import csv
import json
from pathlib import Path
import unittest
from au_ree_v2.stage_rules import stage_rule_fills, ROUND2_STAGE_CASES, SCOPE

ROOT = Path(__file__).resolve().parents[1]

def decisions():
    return [dict(decision_id='test-'+r, rule=r, scope=SCOPE,
                 decided_by='USER_EXPLICIT_APPROVAL', decided_date='2026-11-11')
            for r in sorted({r for _, r in ROUND2_STAGE_CASES.values()})]

class Round2StageTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture = json.loads((ROOT / 'tests/fixtures/round2_stage_baseline.json').read_text(encoding='utf-8'))
        cls.rows = fixture['rows']
        cls.trace = fixture['trace']

    def test_fifteen_cases_thirty_cells(self):
        fills = []
        for row in self.rows:
            if row['專案ID'] not in ROUND2_STAGE_CASES: continue
            with self.subTest(project=row['專案ID']):
                result = stage_rule_fills(row, self.trace, decisions())
                self.assertEqual(len(result), 2)
                code, rule = ROUND2_STAGE_CASES[row['專案ID']]
                self.assertEqual(result[0]['value'], code)
                scope = json.loads(result[0]['scope'])
                self.assertEqual(scope['rule'], rule)
                if code in ('D', 'X'):
                    self.assertEqual(result[1]['value'], {'D':'生產','X':'退出'}[code])
                if code == 'D': self.assertIn('NOT_DESIGN_CAPACITY', scope['production_scope'])
                if rule == 'IN_PROGRESS_STUDY_IMPLIES_B1':
                    self.assertIn('IN_PROGRESS_STUDY', scope['qualifier'])
                if row['專案ID'] in ('AU-d9fb1b1e3e2ec9fa0851','AU-fb4e914f86102baa414a'):
                    self.assertIn('STAGE_SOURCE_DATED', scope['qualifier'])
                fills.extend(result)
        self.assertEqual(len(fills), 30)

    def test_each_missing_approval_leaves_its_rows_blank(self):
        for row in self.rows:
            case = ROUND2_STAGE_CASES.get(row['專案ID'])
            if not case: continue
            with self.subTest(project=row['專案ID']):
                self.assertEqual(stage_rule_fills(row, self.trace, [d for d in decisions() if d['rule'] != case[1]]), [])

    def test_existing_codes_and_inputs_unchanged(self):
        before = copy.deepcopy((self.rows, self.trace))
        existing = [r for r in self.rows if r.get('開發階段代碼')]
        self.assertEqual(len(existing), 39)  # Observed 877b4da published baseline.
        for row in existing:
            self.assertEqual(stage_rule_fills(row, self.trace, decisions()), [])
        self.assertEqual((self.rows, self.trace), before)

    def test_missing_text_and_unreviewed_ids_never_fill(self):
        for row in self.rows:
            if not row.get('開發階段'):
                self.assertEqual(stage_rule_fills(row, self.trace, decisions()), [])
        row = copy.deepcopy(next(r for r in self.rows if r['專案ID'] in ROUND2_STAGE_CASES))
        old = row['專案ID']; row['專案ID'] = 'unreviewed'
        trace = [dict(t, project_id='unreviewed') for t in self.trace if t['project_id'] == old]
        self.assertEqual(stage_rule_fills(row, trace, decisions()), [])

if __name__ == '__main__': unittest.main()
