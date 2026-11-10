import copy
import unittest
from pathlib import Path
from au_ree_v2.blank_classification import classify_blanks,load_blank_rules

ROOT=Path(__file__).resolve().parents[1]


class BlankClasses(unittest.TestCase):
    def setUp(self):
        self.rules=load_blank_rules(ROOT/'config/blank_classification.json')
        self.row={'專案ID':'P','開發階段':'Exploration（來源揭露：2026-02，月精度）',
            **{c:'' for c in ['礦石蘊藏量_Mt','TREO品位_pct','總TREO蘊藏量_kt','有TREO資源估計','產品/產出',
                             '預估年產TREO_t_per_year','預估年產NdPr_t_per_year','預估年產重稀土_t_per_year',
                             '礦床型態代碼','重算磁性元素-HTML磁性稀土_kt']}}
        self.trace=[dict(project_id='P',column='開發階段',value=self.row['開發階段'],source_sha256='verified-native-source')]
        self.gaps=[dict(project_id='P',column=c,reason='NO_COMPATIBLE_VERIFIED_FIELD; BLANK_IS_UNKNOWN') for c,v in self.row.items() if v=='']
        for g in self.gaps:
            if g['column']=='礦床型態代碼':g['reason']='NO_APPROVED_TEMPLATE_CLASSIFICATION_CODEBOOK'
            if g['column']=='重算磁性元素-HTML磁性稀土_kt':g['reason']='NO_INDEPENDENT_HTML_COMPARATOR'

    def test_four_classes_and_denominator_without_cell_changes(self):
        before=copy.deepcopy(self.row);trace=copy.deepcopy(self.trace)
        result=classify_blanks([self.row],self.gaps,self.trace,self.rules)
        labels={g['column']:g['blank_class'] for g in self.gaps}
        self.assertEqual('UNKNOWN',labels['礦石蘊藏量_Mt'])
        self.assertEqual('NOT_APPLICABLE_STAGE',labels['預估年產TREO_t_per_year'])
        self.assertEqual('NO_COMPARATOR_SOURCE',labels['重算磁性元素-HTML磁性稀土_kt'])
        self.assertEqual('PENDING_CODEBOOK',labels['礦床型態代碼'])
        self.assertEqual(4,result['excluded_structural_blanks'])
        self.assertEqual(len(self.row)-4,result['adjusted_denominator'])
        self.assertEqual(before,self.row);self.assertEqual(trace,self.trace)

    def test_blank_or_unknown_stage_is_not_inapplicable(self):
        for stage in ('','unknown','planned and prepared for its Phase 1 drilling programme（來源揭露：2026-05-18）'):
            with self.subTest(stage=stage):
                self.row['開發階段']=stage
                classify_blanks([self.row],self.gaps,self.trace,self.rules)
                self.assertEqual('UNKNOWN',next(g for g in self.gaps if g['column']=='預估年產TREO_t_per_year')['blank_class'])

    def test_resource_product_or_unproven_stage_does_not_exclude_forecast(self):
        for key in ('礦石蘊藏量_Mt','產品/產出','source'):
            with self.subTest(key=key):
                row=copy.deepcopy(self.row);trace=copy.deepcopy(self.trace);gaps=copy.deepcopy(self.gaps)
                if key=='source':trace[0]['source_sha256']=''
                else:
                    row[key]='present';gaps=[g for g in gaps if g['column']!=key]
                result=classify_blanks([row],gaps,trace,self.rules)
                self.assertEqual(0,result['blank_class_counts']['NOT_APPLICABLE_STAGE'])

    def test_config_controls_rules_and_exclusion_set(self):
        rules=copy.deepcopy(self.rules);rules['config']['rules']=[]
        result=classify_blanks([self.row],self.gaps,self.trace,rules)
        self.assertEqual(0,result['excluded_structural_blanks'])
        self.assertEqual(len(self.gaps),result['blank_class_counts']['UNKNOWN'])

    def test_filled_target_rejected(self):
        self.row['預估年產TREO_t_per_year']='0'
        with self.assertRaisesRegex(ValueError,'TARGET_IS_FILLED'):
            classify_blanks([self.row],self.gaps,self.trace,self.rules)
