import copy
import json
import unittest
from pathlib import Path
from unittest.mock import patch
from au_ree_v2.scoped_oxide_exceptions import (SPLINTER,CIRCLE,RULES,cerium_factors,approved_decision,scoped_exception_fills,decision_rows)
import au_ree_v2.scoped_oxide_exceptions as exception_module
ROOT=Path(exception_module.__file__).resolve().parents[2]


def decision(identity, approved=True):
    return dict(decision_id='test-'+identity[1],project_id=identity[0],rule=RULES[identity[0]],scope={'statement_id':identity[1],'source_sha256':identity[2]},decided_by='fixture researcher' if approved else None,decided_date='2026-11-11',notes='Test fixture only')


class ScopedOxideTests(unittest.TestCase):
    def test_null_decisions_export_is_byte_identical(self):
        from test_partial_resource import PartialResourceRules
        from au_ree_v2.project_summary import export_summary
        fixture=PartialResourceRules('test_export_partial_never_promotes_treo_pair_and_ratios')
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        fixture.export(fixture.technical_report())
        out=fixture.root/'null-export'
        path=fixture.root/'null-decisions.json'
        path.write_text(json.dumps({'decisions':[decision(SPLINTER,False),decision(CIRCLE,False)]}),'utf8')
        export_summary(fixture.root,fixture.root/'canonical.sqlite',fixture.root/'run',out,
                       review_ledger=fixture.root/'reviews.json',asset_roots={'fixture':fixture.root},researcher_decisions=path)
        for original in (fixture.root/'export').iterdir():
            self.assertEqual(original.read_bytes(),(out/original.name).read_bytes(),original.name)

    def test_constants_are_stoichiometric(self):
        f=cerium_factors()
        self.assertAlmostEqual(f['ce2o3_to_ceo2'],2*(140.116+2*15.999)/(2*140.116+3*15.999))
        self.assertLess(abs(f['ce2o3_element_ratio']-1.171),.0005)

    def test_missing_null_or_empty_decision_disabled(self):
        for value in (None,[],{'decisions':[]},[decision(SPLINTER,False)]):
            self.assertIsNone(approved_decision(value,SPLINTER))
        d=decision(SPLINTER);d['decided_by']='  '
        self.assertIsNone(approved_decision([d],SPLINTER))

    def test_no_file_reads_when_disabled(self):
        with patch('au_ree_v2.store.filehash',side_effect=AssertionError('read forbidden')):
            self.assertEqual(scoped_exception_fills({'project_id':SPLINTER[0]},Path('nonexistent'),{}, {},{},[decision(SPLINTER,False)]),[])

    def test_decision_statement_exact(self):
        d=decision(SPLINTER);d['scope']['statement_id']='mount-ridley'
        with self.assertRaisesRegex(ValueError,'EXACT_DECISION_SCOPE'):approved_decision([d],SPLINTER)

    def test_other_project_cannot_activate(self):
        d=decision(SPLINTER);d['project_id']='other'
        self.assertIsNone(approved_decision([d],SPLINTER))

    def test_ambiguous_decision(self):
        d=decision(SPLINTER)
        with self.assertRaisesRegex(ValueError,'AMBIGUOUS'):approved_decision([d,d],SPLINTER)

    def test_decision_wrong_sha(self):
        d=decision(SPLINTER);d['scope']['source_sha256']='wrong'
        with self.assertRaisesRegex(ValueError,'SHA_MISMATCH'):approved_decision([d],SPLINTER)

    @classmethod
    def setUpClass(cls):
        cls.reviews=json.loads((ROOT/'config/asx_source_reviews.json').read_text('utf8'))['reviews']
        cls.roots=json.loads((ROOT/'config/asx_local_asset_roots.json').read_text('utf8'))['roots']

    def fixture(self,identity):
        r=next(r for r in self.reviews if r['statement_id']==identity[1])
        path=ROOT/self.roots[r['asset_set']]/r['path']
        self.assertTrue(path.is_file(), 'Required archived local source missing: '+str(path))
        ore=next(o['value'] for o in r['observations'] if o['variable']=='ore_mt')
        bundle={k:r[k] for k in ('source_sha256','statement_id','scope','effective_date')}
        bundle.update(value={'ore_mt':ore},observations=[dict(o,status='AUTO_VALIDATED') for o in r['observations']])
        elements={o['basis']:ore*o['value']*.001 for o in r['observations'] if o['variable'].startswith('reported_resource_')}
        return r,path,bundle,elements

    def test_splinter_native_cells_and_closure(self):
        r,p,b,e=self.fixture(SPLINTER)
        fills=scoped_exception_fills(r,p,b,e,{'已公布元素數_共15項':14},[decision(SPLINTER)])
        values={f['column']:f['value'] for f in fills}
        factor=cerium_factors()['ce2o3_to_ceo2']
        self.assertAlmostEqual(values['CeO2_氧化鈰_kt'],22.849*397*factor*.001)
        self.assertAlmostEqual(values['總TREO蘊藏量_kt'],22.849*(1056-397+397*factor)*.001)
        self.assertEqual(values['已公布元素數_共15項'],15)
        self.assertIn('一致',values['元素數據一致性檢查'])
        self.assertEqual(fills[0]['provenance']['native_ce2o3']['original_token'],'397')
        self.assertTrue(all(f['provenance']['decision_id'] for f in fills))
        closure=fills[-1]['provenance']
        self.assertEqual(closure['source_15_oxide_sum_ppm'],1056)
        self.assertEqual(closure['closure_difference_kt'],0)
        self.assertEqual(closure['closure_rounding_half_width_ppm'],8)
        self.assertAlmostEqual(closure['closure_rounding_tolerance_kt'],.182792)

    def test_circle_combined_without_individual_fabrication(self):
        r,p,b,e=self.fixture(CIRCLE)
        fills=scoped_exception_fills(r,p,b,e,{},[decision(CIRCLE)])
        self.assertEqual({f['column'] for f in fills},{'NdPr蘊藏量_kt_需兩者皆公布','元素數據一致性檢查'})
        self.assertAlmostEqual(fills[0]['value'],21.56)
        self.assertEqual(fills[0]['provenance']['native_ndpr']['original_token'],'220')

    def test_wrong_resource_scope_rejected(self):
        r,p,b,e=self.fixture(SPLINTER);b['scope']='wrong'
        with self.assertRaisesRegex(ValueError,'SELECTED_CONTRACT'):scoped_exception_fills(r,p,b,e,{},[decision(SPLINTER)])

    def test_unvalidated_bundle_rejected(self):
        r,p,b,e=self.fixture(SPLINTER);b['observations'][0]['status']='CANDIDATE'
        with self.assertRaisesRegex(ValueError,'VALIDATED_BUNDLE'):scoped_exception_fills(r,p,b,e,{},[decision(SPLINTER)])

    def test_existing_ndpr_protected(self):
        r,p,b,e=self.fixture(CIRCLE)
        with self.assertRaisesRegex(ValueError,'EXISTING_VALUE_PROTECTED'):scoped_exception_fills(r,p,b,e,{'NdPr蘊藏量_kt_需兩者皆公布':1},[decision(CIRCLE)])

    def test_cutoff_tamper_rejected_by_existing_cell_validator(self):
        r,p,b,e=self.fixture(SPLINTER);r=copy.deepcopy(r)
        r['selected_resource_sections']['splinter_table35_500_inferred']['cutoff_group']['label']='600'
        with self.assertRaisesRegex(ValueError,'CUTOFF_GROUP_LABEL'):scoped_exception_fills(r,p,b,e,{},[decision(SPLINTER)])

if __name__=='__main__':unittest.main()
