import ast
import csv
import unittest
from decimal import Decimal, InvalidOperation, localcontext
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def functions():
    tree=ast.parse((ROOT/'tools/compare_ci_cells.py').read_text(encoding='utf8'))
    definitions=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in ('equal','equal15')]
    scope=dict(Decimal=Decimal,InvalidOperation=InvalidOperation,localcontext=localcontext)
    exec(compile(ast.Module(body=definitions,type_ignores=[]),'<comparison policy>','exec'),scope)
    return scope['equal'],scope['equal15']

class ComparisonPolicy(unittest.TestCase):
    def test_decimal_fifteen_digits_ignore_representation_trailing_zeros(self):
        _,equal15=functions()
        self.assertTrue(equal15('60.016000000000005','60.016'))
        self.assertTrue(equal15('1.0000000000000001','1'))
        self.assertTrue(equal15('1000000000000000','1e15'))

    def test_different_values_and_non_numeric_strings_stay_different(self):
        equal,equal15=functions()
        self.assertFalse(equal15('1.24','1.533207293212736471803786828'))
        self.assertFalse(equal('alpha','beta'))
        self.assertTrue(equal('same text','same text'))
        self.assertFalse(equal15('NaN','0'))

    def test_strict_fifteen_digits_exposes_legacy_presentation_same_loss(self):
        equal,equal15=functions()
        self.assertFalse(equal15('15.5','15.48922242604142347330153754'))
        self.assertFalse(equal('15.5','15.48922242604142347330153754'))

    def test_exactly_thirteen_baseline_cells_are_new_same(self):
        equal,equal15=functions()
        with (ROOT/'results/claims-locators-2026-11-16/v8/ci/cell_comparison.csv').open(encoding='utf-8-sig',newline='') as f:
            rows=list(csv.DictReader(f))
        changed=[r for r in rows if r['experiment_value'] and r['formal_value'] and
                 r['status'] not in ('SAME','KNOWN_STRUCTURAL_DIFFERENCE') and equal15(r['experiment_value'],r['formal_value'])]
        self.assertEqual(13,len(changed))
        self.assertEqual({'NUMERIC_TOLERANCE_SAME'},{r['status'] for r in changed})
        lost=[r for r in rows if r['status']=='SAME' and r['column']!='專案ID' and r['experiment_value'] and not equal(r['experiment_value'],r['formal_value'])]
        self.assertEqual([('AU-447261eed0e81eae88bf','Pr6O11_氧化鐠_kt')],[(r['project_id'],r['column']) for r in lost])

    def test_residual_relative_tolerance_still_has_a_distinct_domain(self):
        _,equal15=functions()
        a,b=Decimal('1'),Decimal('1.00000000000005')
        self.assertFalse(equal15(str(a),str(b)))
        self.assertLessEqual(abs(a-b),max(abs(a),abs(b))*Decimal('1e-12'))
