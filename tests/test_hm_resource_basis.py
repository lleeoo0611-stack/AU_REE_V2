"""HM-only projection rejects unbound, wrong-scope and false-total inputs."""
import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import pymupdf
from au_ree_v2.partial_resource import validate_hm_projection,hm_resource_bundle,HM_MODE,HM_REASON
from au_ree_v2.project_summary import resource_bundle,ELEMENTS

class HeavyMineralProjection(unittest.TestCase):
    def setUp(self):
        self.doc=pymupdf.open();self.addCleanup(self.doc.close)
        for _ in range(2):self.doc.new_page()
        cutoff='Mineral Resources are reported at a cut-off grade of 1.0% HM.'
        denom='The rare earth element oxide is reported as a percentage of the HM content from the reported Mineral Resource.'
        for p in self.doc:p.insert_text((20,30),cutoff,fontsize=8)
        self.doc[1].insert_text((20,60),denom,fontsize=7)
        def proof(page,text,y):return dict(page=page,bbox=[19,y-10,590,y+3],text=text,evidence={'page':page,'markers':[text]})
        def binding(field,page):return dict(mode='native_cell',field=field,page=page,scope='same scope',section_id='mass' if page==1 else 'oxides',table_bbox=[1,1,500,400],row_bbox=[1,300,500,310],row_label='Total')
        ore=dict(variable='ore_mt',basis='TREO',unit='Mt',value=540,original_token='540',rounding_half_width=5,evidence={'page':1},cell_binding=binding('ore_mt',1))
        hm=dict(unit='Mt',value=25,original_token='25',rounding_half_width=.5,evidence={'page':1},cell_binding=binding('hm_mass_mt',1))
        oxide=dict(variable='reported_resource_ce_ppm',basis='CeO2',unit='ppm',original_unit='%HM',value=.67*25/540*10000,original_token='0.67',evidence={'page':2},cell_binding=binding('reported_resource_ce_ppm',2))
        self.review=dict(identity_evidence={'page':1},selected_resource_sections={'mass':{'anchor':'mine 2026'},'oxides':{'anchor':'mine oxide content'}},source_sha256='a'*64,statement_id='statement',scope='same scope',effective_date='2026-01-29',review_id='r',observations=[ore,oxide])
        for basis in ELEMENTS:
            if basis == 'CeO2':continue
            o=copy.deepcopy(oxide);o['basis']=basis;o['original_token']='0.001';o['value']=.001*25/540*10000;self.review['observations'].append(o)
        self.review['partial_resource_projection']=dict(resource_name='mine',mode=HM_MODE,withholding_reason=HM_REASON,**{k:self.review[k] for k in ('source_sha256','statement_id','scope','effective_date')},mass_inputs={'ore_mt':copy.deepcopy(ore),'hm_mass_mt':hm},denominator_proof=proof(2,denom,60),mass_cutoff_proof=proof(1,cutoff,30),oxide_cutoff_proof=proof(2,cutoff,30))
    def validate(self,r=None):
        # Cell geometry/token semantics have dedicated source_cells tests;
        # these unit cases isolate the cross-table mass/scope contract.
        with patch('au_ree_v2.source_cells.validate_cell',return_value='NATIVE_TABLE_ROW_COLUMN_CELL_BINDING'):
            return validate_hm_projection(r or self.review,self.doc,lambda e:'mine verified markers')
    def rows(self,c):
        rows=[]
        for v in self.review['observations']:
            raw=dict(partial_resource_projection=c,original_unit=v.get('original_unit',v['unit']),normalization='REPORTED_HM_MASS_X_OXIDE_PERCENT_DIVIDED_BY_BULK_ORE',material_basis='RESOURCE_ORE_GRADE_OXIDE_PPM')
            rows.append(dict(v,source_sha=self.review['source_sha256'],statement_id='statement',scope='same scope',effective_date='2026-01-29',status='AUTO_VALIDATED',raw=json.dumps(raw)))
        return rows
    def test_mass_not_ore_and_rounding_retained(self):
        c=self.validate();b,_=hm_resource_bundle(self.rows(c),c)
        self.assertEqual(b['value'],{'ore_mt':540})
        self.assertAlmostEqual(c['oxide_rounding']['CeO2']['contained_kt'],167.5)
        lo,hi=c['oxide_rounding']['CeO2']['rounding_interval_kt'];self.assertLess(lo,167.5);self.assertGreater(hi,167.5)
        self.assertNotIn('grade_pct',b['value']);self.assertNotIn('contained_treo_kt',b['value'])
    def test_reject_missing_source_contract(self):
        r=copy.deepcopy(self.review);del r['partial_resource_projection']['source_sha256']
        with self.assertRaisesRegex(ValueError,'CONTRACT'):self.validate(r)
    def test_reject_wrong_denominator(self):
        r=copy.deepcopy(self.review);r['partial_resource_projection']['denominator_proof']['text']='percentage of ore'
        with self.assertRaisesRegex(ValueError,'SEMANTICS'):self.validate(r)
    def test_reject_cross_scope(self):
        for field in ('scope','statement_id','source_sha256','effective_date'):
            with self.subTest(field=field):
                r=copy.deepcopy(self.review);r['partial_resource_projection'][field]='other'
                with self.assertRaises(ValueError):self.validate(r)
    def test_reject_oxide_other_page_or_row(self):
        for key,val in [('page',1),('row_label','Measured'),('scope','other')]:
            with self.subTest(key=key):
                r=copy.deepcopy(self.review);r['observations'][1]['cell_binding'][key]=val
                with self.assertRaisesRegex(ValueError,'SCOPE'):self.validate(r)
    def test_reject_mass_other_section(self):
        r=copy.deepcopy(self.review);r['partial_resource_projection']['mass_inputs']['hm_mass_mt']['cell_binding']['section_id']='old'
        with self.assertRaisesRegex(ValueError,'SCOPE'):self.validate(r)
    def test_reject_scandium_and_grade(self):
        for basis in ('Sc2O3','TREO','Ce2O3'):
            r=copy.deepcopy(self.review);r['observations'][1]['basis']=basis
            with self.assertRaisesRegex(ValueError,'CANONICAL|COMPLETE_15'):self.validate(r)
    def test_reject_precision_inflation(self):
        for h in (None,0,.01,True,float('nan')):
            r=copy.deepcopy(self.review);r['partial_resource_projection']['mass_inputs']['hm_mass_mt']['rounding_half_width']=h
            with self.assertRaisesRegex(ValueError,'ROUNDING'):self.validate(r)
    def test_reject_incompatible_unit(self):
        r=copy.deepcopy(self.review);r['partial_resource_projection']['mass_inputs']['hm_mass_mt']['unit']='t'
        with self.assertRaisesRegex(ValueError,'UNIT'):self.validate(r)
    def test_reject_hm_mass_greater_than_ore(self):
        r=copy.deepcopy(self.review);h=r['partial_resource_projection']['mass_inputs']['hm_mass_mt'];h['value']=600;h['original_token']='600'
        with self.assertRaisesRegex(ValueError,'EXCEEDS'):self.validate(r)
    def test_reject_wrong_bulk_ore_projection(self):
        r=copy.deepcopy(self.review);r['observations'][0]['value']=25
        with self.assertRaisesRegex(ValueError,'SELECTED_ORE'):self.validate(r)
    def test_reject_mixed_normalization(self):
        r=copy.deepcopy(self.review);r['bulk_hm_percent']={'value':4.6}
        with self.assertRaisesRegex(ValueError,'CONTRACT'):self.validate(r)
    def test_bundle_requires_explicit_opt_in(self):
        c=self.validate();b,reason=resource_bundle(self.rows(c));self.assertIsNone(b);self.assertEqual(reason,'PARTIAL_RESOURCE_OPT_IN_REQUIRED')
    def test_bundle_rejects_tampered_transform(self):
        c=self.validate();rows=self.rows(c);rows[1]['value']*=2
        b,reason=hm_resource_bundle(rows,c);self.assertIsNone(b);self.assertIn('TRANSFORM',reason)
    def test_bundle_rejects_forged_total(self):
        c=self.validate();rows=self.rows(c);rows.append(dict(rows[0],variable='grade',value=1,unit='%'))
        b,reason=hm_resource_bundle(rows,c);self.assertIsNone(b);self.assertIn('UNSUPPORTED',reason)
    def test_missing_one_oxide_rejected(self):
        r=copy.deepcopy(self.review);r['observations'].pop()
        with self.assertRaisesRegex(ValueError,'COMPLETE_15'):self.validate(r)
    def test_native_cell_failure_is_not_ignored(self):
        with patch('au_ree_v2.source_cells.validate_cell',side_effect=ValueError('REVIEW_CELL_TOKEN_MISMATCH')):
            with self.assertRaisesRegex(ValueError,'CELL_TOKEN'):validate_hm_projection(self.review,self.doc,lambda e:'verified')

if __name__=='__main__':unittest.main()
