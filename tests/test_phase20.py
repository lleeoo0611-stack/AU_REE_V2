"""Current evidence refresh and selective-page disclosure regressions."""
import csv
import json
import tempfile
import unittest
from pathlib import Path
from au_ree_v2.analysis import current_disclosure_baseline,write_csv
from au_ree_v2.evidence import normalize,transformation_issues

ROOT=Path(__file__).resolve().parents[1]

class CurrentDisclosure(unittest.TestCase):
    def test_current_values_replace_frozen_baseline_and_conflicts_stay_missing(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'work') as tmp:
            out=Path(tmp)
            write_csv(out/'cohort_coverage.csv',[dict(entity_id='a',resource_defined=1)],['entity_id','resource_defined'])
            rows=[dict(entity_id='a',criterion='S1',score=.225,raw_value=22.5,source='{}',scoring='{}'),
                  dict(entity_id='a',criterion='C1',score=.25,raw_value=1,source='{}',scoring='{}'),
                  dict(entity_id='a',criterion='C1',score=.5,raw_value=2,source='{}',scoring='{}'),
                  dict(entity_id='a',criterion='R1',score=.8,raw_value=1000,source=json.dumps({'source_scope':'government_project_summary_not_JORC_harmonized'}),scoring='{}')]
            write_csv(out/'value_trace.csv',rows,list(rows[0]))
            actual=current_disclosure_baseline(out,{'a':'A'},['A'])
            self.assertEqual(.225,actual['scores']['A']['S1']['score'])
            self.assertNotIn('C1',actual['scores']['A']);self.assertNotIn('R1',actual['scores']['A'])
            self.assertEqual('C1',actual['conflicts'][0]['criterion'])
    def test_area1_four_oxide_ratio_contract(self):
        claims=json.loads((ROOT/'data/claims.json').read_text(encoding='utf8'))
        p=next(p for p in claims['projects'] if p['id']=='goschen')
        ratio=next(o for o in p['observations'] if o['variable']=='magnet_reo_share_pct')
        self.assertEqual(22.5,ratio['value']);self.assertEqual(12,ratio['pdf_page'])
        self.assertFalse(normalize(ratio));self.assertFalse(transformation_issues(ratio,p['observations']))
        self.assertIn('Area 1 ONLY',ratio['scope'])
        self.assertLess(ratio['rounding_bounds'][0],22.5);self.assertGreater(ratio['rounding_bounds'][1],22.5)
    def test_funding_plan_is_not_secured_funding(self):
        claims=json.loads((ROOT/'data/claims.json').read_text(encoding='utf8'))
        event=next(e for e in claims['events'] if e['event_id']=='koppamurra-project-funding-plan-20260625')
        self.assertEqual('PLANNED_OR_NONBINDING',event['finance_state'])
        self.assertEqual('PROJECT',event['attribution']);self.assertEqual(62,event['pdf_page'])

if __name__=='__main__':unittest.main()
