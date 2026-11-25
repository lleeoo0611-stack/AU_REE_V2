"""Regression cases for transitions and incomplete publication evidence."""
import json
import unittest
from pathlib import Path

from tools.compare_census_release import (cell_changes, followup_rows, index, panel_result, records_delta,
                                           release, state, transition)


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT/'results/ree-project-census/plan620-20261119'


class CensusComparisonTests(unittest.TestCase):
    def test_followup_rechecks_exact_prior_targets_and_reads_values_from_release(self):
        key = ('P1', '緯度')
        old = dict(states={key:'UNKNOWN'}, status={key:{'status':'LOCATION_PENDING'}})
        new = dict(states={key:'PRESENT'}, status={key:{'status':'VALUE_PRESENT'}},
                   trace={key:{'source_sha256':'s', 'locator':'p3'}}, cells={key:'-23.5'},
                   population={('P1',):{'專案名稱':'Project 1'}})
        prior = [{'project_id':'P1', 'column':'緯度', 'class':'E2', 'current_status':'LOCATION_PENDING'}]
        note = dict(prior[0], finding='Reviewed dated boundary', reviewed_evidence='survey p3',
                    reopen_if='Boundary revision', current_value='999', outcome='HELD')
        row, = followup_rows(old, new, prior, [note])
        self.assertEqual((row['outcome'],row['current_value']),('FILLED','-23.5'))
        for bad in ([], [note,note], [dict(note, **{'class':'E1'})]):
            with self.assertRaises(ValueError):
                followup_rows(old, new, prior, bad)

    def test_missing_and_inapplicable_are_not_counted_as_additions(self):
        self.assertEqual(transition('','','NOT_APPLICABLE','UNKNOWN'),'REOPENED')
        self.assertEqual(transition('','','UNKNOWN','NOT_APPLICABLE'),'RECLASSIFIED_NOT_APPLICABLE')
        self.assertEqual(transition('12','','PRESENT','NOT_APPLICABLE'),'WITHDRAWN')
        self.assertEqual(transition('','0','UNKNOWN','PRESENT'),'FILLED')
        self.assertEqual(transition('12','11','PRESENT','PRESENT'),'UPDATED')
        with self.assertRaises(ValueError):
            state('0',dict(value_state='BLANK',status='NO_SOURCE_VALUE',project_id='P1',column='grade'))

    def test_locked_baseline_and_source_only_change(self):
        snap = release(BASE)
        self.assertEqual(cell_changes(snap,snap),[])
        k = next(k for k,v in snap['cells'].items() if v and k[1]=='礦床型態')
        new = dict(snap,trace=dict(snap['trace']))
        new['trace'][k] = dict(new['trace'][k], locator='Newly reviewed page in same original')
        changed = cell_changes(snap,new)
        self.assertEqual(len(changed),1)
        self.assertEqual((changed[0]['change'], changed[0]['field_family']),
                         ('EVIDENCE_OR_REASON_CHANGED','SCIENTIFIC_DESCRIPTION'))
        self.assertEqual(changed[0]['old_value'],changed[0]['new_value'])

    def test_criteria_and_panel_changes_are_keyed_per_member_and_scenario(self):
        a=[dict(scenario='balanced',project_id='P1',saw_rank='1'),
           dict(scenario='balanced',project_id='P2',saw_rank='2')]
        b=[dict(scenario='balanced',project_id='P2',saw_rank='1'),
           dict(scenario='balanced',project_id='P3',saw_rank='2')]
        diff=records_delta(a,b,('scenario','project_id'),('saw_rank',))
        self.assertEqual((diff['removed'],diff['added']),([('balanced','P1')],[('balanced','P3')]))
        self.assertEqual(diff['changed'][0]['changes'],{'saw_rank':['2','1']})
        with self.assertRaises(ValueError):
            index(a*2,('scenario','project_id'))

    def test_missing_sensitivity_hash_is_reported_and_altered_rank_hash_rejected(self):
        a=json.loads((BASE/'census_release.json').read_bytes())
        b=json.loads((BASE/'census_release.json').read_bytes())
        digests=b['ranking_panels']['six_domain']['digests']
        del digests['weight_uncertainty.csv']
        args=(dict(folder=BASE,manifest=a),dict(folder=BASE,manifest=b))
        result=panel_result('six_domain',*args)
        self.assertEqual(result['comparison_by_file']['weight_uncertainty.csv'],'UNAVAILABLE')
        self.assertEqual(result['rank_changes'],[])
        digests['ranking.csv']='0'*64
        with self.assertRaises(ValueError):
            panel_result('six_domain',*args)
