import copy
import csv
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from au_ree_v2.stage_rules import (classify_stage, proposed_decisions, stage_rule_fills,
    selected_mre, deposit_decision_sheet, approved_decision, RULES)


class StageRulesTest(unittest.TestCase):
    def fixture(self, text='Exploration', ore=''):
        row = {'專案ID':'p', '開發階段':text, '礦石蘊藏量_Mt':ore, 'TREO品位_pct':'',
               '總TREO蘊藏量_kt':'', '開發階段代碼':'', '開發階段類別':''}
        trace = [dict(project_id='p', column='開發階段', value=text, source_sha256='a'*64,
                      locator='physical PDF p1', publication_date='2026-01-01')]
        if ore:
            trace.append(dict(project_id='p', column='礦石蘊藏量_Mt', value=ore, source_sha256='b'*64,
                              locator='physical PDF p2', publication_date='2026-01-01'))
        decisions = proposed_decisions()
        return row, trace, decisions

    def test_default_null_has_no_fills_or_mutation(self):
        row, trace, decisions = self.fixture()
        before = copy.deepcopy((row, trace, decisions))
        self.assertEqual(stage_rule_fills(row, trace, decisions), [])
        self.assertEqual((row, trace, decisions), before)
        self.assertTrue(all(d['decided_by'] is None for d in decisions))

    def test_exploration_mre_split_and_provenance(self):
        for ore, code in [('', 'A1'), ('12.3', 'A2')]:
            with self.subTest(ore=ore):
                row, trace, decisions = self.fixture(ore=ore)
                for d in decisions: d['decided_by']='test researcher'
                fills = stage_rule_fills(row, trace, decisions)
                self.assertEqual([f['value'] for f in fills], [code, '探勘'])
                scope = json.loads(fills[0]['scope'])
                self.assertTrue(scope['decision_id'])
                self.assertEqual(scope['source_value'], 'Exploration')
                self.assertIn('mre_basis', scope)

    def test_blank_or_false_approver_not_approval(self):
        for value in [None, '', '  ', False, 123]:
            row, trace, decisions = self.fixture()
            for d in decisions: d['decided_by']=value
            self.assertEqual(stage_rule_fills(row, trace, decisions), [])

    def test_scope_and_rule_restricted(self):
        row, trace, decisions = self.fixture()
        for d in decisions:
            d['decided_by']='researcher'; d['scope']='OTHER'
        self.assertEqual(stage_rule_fills(row, trace, decisions), [])

    def test_no_inference_from_study_name(self):
        for text in ['Scoping', 'Scoping Study', 'PFS', 'DFS', 'Bankable Feasibility Study',
                     'Feasibility Study', 'Preliminary feasibility study work was progressed in 2022',
                     'completed drilling for DFS']:
            with self.subTest(text=text): self.assertIsNone(classify_stage(text, True)['code'])

    def test_explicit_study_completion(self):
        for text, expected in [('已揭露完成 Scoping Study（2025-01-01）','B1'),
                               ('completed pre-feasibility study','B1'),
                               ('已揭露完成 PFS','B1'), ('completed DFS','B2'),
                               ('completed BFS','B2'), ('completed Feasibility Study','B2'),
                               ('completed Scoping Study and completed DFS','B2')]:
            with self.subTest(text=text): self.assertEqual(classify_stage(text, True)['code'], expected)

    def test_in_progress_uses_only_explicit_previous(self):
        self.assertIsNone(classify_stage('currently the subject of a definitive feasibility study (DFS)', True)['code'])
        self.assertEqual(classify_stage('completed PFS; DFS in progress', True)['code'], 'B1')
        self.assertIsNone(classify_stage('PFS and DFS in progress', True)['code'])
        self.assertIsNone(classify_stage('DFS completed and currently DFS in progress', True)['code'])

    def test_progress_needs_separate_decision(self):
        row, trace, decisions = self.fixture('completed PFS; DFS in progress')
        next(d for d in decisions if d['rule']==RULES['B1'])['decided_by']='researcher'
        self.assertEqual(stage_rule_fills(row, trace, decisions), [])
        next(d for d in decisions if d['rule']=='IN_PROGRESS_STUDY_USE_HIGHEST_EXPLICIT_COMPLETED')['decided_by']='researcher'
        self.assertEqual(len(stage_rule_fills(row, trace, decisions)), 2)

    def test_operating_withdrawal_not_automatic(self):
        for text in ['Operating','started production','Mining has now commenced and heavy mineral concentrate has been produced',
                     'decided to withdraw from the option to acquire agreement','已完成 DFS，但中止', 'not completed DFS']:
            with self.subTest(text=text): self.assertIsNone(classify_stage(text, True)['code'])

    def test_capital_decisions(self):
        self.assertEqual(classify_stage('announced final investment decision', True)['code'], 'C1')
        self.assertEqual(classify_stage('under construction', True)['code'], 'C2')
        self.assertIsNone(classify_stage('construction planned', True)['code'])

    def test_study_status_binds_only_to_specific_mention(self):
        for text in ['completed PFS before DFS', 'completed PFS followed by DFS',
                     'completed drilling for DFS', 'will have completed DFS in 2027']:
            with self.subTest(text=text): self.assertIsNone(classify_stage(text, True)['code'])
        for text in ['completed PFS before ongoing DFS', 'PFS completed before DFS planned for 2027',
                     'completed PFS; currently the subject of a definitive feasibility study (DFS)',
                     'completed PFS while DFS in progress', 'completed PFS and planned DFS']:
            with self.subTest(text=text):
                proposal=classify_stage(text, True)
                self.assertEqual(proposal['code'],'B1')
                self.assertTrue(proposal['ongoing_study'])
        self.assertEqual(classify_stage('completed definitive feasibility study (DFS)',True)['code'],'B2')

    def test_planned_or_conditional_fid_never_maps(self):
        for text in ['announced final investment decision planned for 2027',
                     'final investment decision expected to be announced in 2027',
                     'will announce a final investment decision',
                     'announced planned final investment decision',
                     '已公布最終投資決定，預計2027年',
                     'will be under construction in 2027',
                     'expected to be under construction in 2027']:
            with self.subTest(text=text): self.assertIsNone(classify_stage(text,True)['code'])
        self.assertEqual(classify_stage('final investment decision was announced in 2025',True)['code'],'C1')

    def test_existing_values_not_changed(self):
        row, trace, decisions = self.fixture()
        for d in decisions: d['decided_by']='researcher'
        row['開發階段代碼']='A1'
        self.assertEqual([f['column'] for f in stage_rule_fills(row, trace, decisions)], ['開發階段類別'])
        row['開發階段代碼']='A3'
        self.assertEqual(stage_rule_fills(row, trace, decisions), [])

    def test_missing_or_duplicate_provenance_rejected(self):
        row, trace, decisions = self.fixture(ore='12')
        for d in decisions: d['decided_by']='researcher'
        self.assertEqual(stage_rule_fills(row, trace[:1], decisions), [])
        self.assertEqual(stage_rule_fills(row, trace+trace, decisions), [])
        trace[0]['value']='other'
        self.assertEqual(stage_rule_fills(row, trace, decisions), [])

    def test_missing_date_or_locator_rejected(self):
        for key in ('publication_date', 'locator'):
            row, trace, decisions = self.fixture()
            for d in decisions: d['decided_by']='researcher'
            trace[0][key]=''
            self.assertEqual(stage_rule_fills(row, trace, decisions), [])
        row, trace, decisions = self.fixture()
        for d in decisions: d['decided_by']='researcher'
        trace[0]['publication_date']='2026-99-99'
        self.assertEqual(stage_rule_fills(row, trace, decisions), [])

    def test_deposit_sheet_preserves_unmapped(self):
        rows=[{'礦床型態':'clay','礦床型態代碼':''}]*2+[{'礦床型態':'','礦床型態代碼':''}]
        result=deposit_decision_sheet(rows)
        self.assertEqual(sum(r['project_count'] for r in result),3)
        self.assertIn('NOT_ION_ADSORPTION',result[1]['reason'])

    def test_duplicate_decision_is_error(self):
        decisions=proposed_decisions()
        with self.assertRaisesRegex(ValueError,'DUPLICATE'):
            approved_decision(decisions+[decisions[0]], RULES['A1'])

    def test_cli_unapproved_copies_all_six_bytes(self):
        script=Path(__file__).resolve().parents[1]/'tools/review_stage_rules.py'
        spec=importlib.util.spec_from_file_location('review_stage_rules',script)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); baseline=root/'baseline';baseline.mkdir()
            row, trace, _=self.fixture()
            for name, records in [('專案總表.csv',[row]),('field_provenance.csv',trace)]:
                with (baseline/name).open('w',encoding='utf-8-sig',newline='') as f:
                    w=csv.DictWriter(f,fieldnames=records[0].keys());w.writeheader();w.writerows(records)
            for name in ['missing_fields.csv','census_inventory.csv','summary.json','audit.json']:
                (baseline/name).write_bytes(b'unchanged\r\n')
            result=module.run(baseline,root/'out')
            self.assertEqual(result['new_cells'],0)
            self.assertTrue(result['disabled_outputs_byte_identical'])
            for path in baseline.iterdir():
                self.assertEqual(path.read_bytes(),(root/'out/projection'/path.name).read_bytes())


if __name__ == '__main__': unittest.main()
