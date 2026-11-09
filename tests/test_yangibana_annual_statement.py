import copy, unittest
import pymupdf
from au_ree_v2.source_cells import validate_cell

class YangibanaAnnualStatementTests(unittest.TestCase):
    def fixture(self, statement=None, context='100% Project basis; a 19-year mine life'):
        prefix=('approximately 31,570 tonnes per annum; and average annual contained '
                'production of approximately 8,524 tonnes of total rare earth oxides, including approximately')
        suffix='tonnes of neodymium and praseodymium.'
        text=statement or prefix+' 3,090 '+suffix
        doc=pymupdf.open();page=doc.new_page(width=700,height=500)
        page.insert_textbox(pymupdf.Rect(30,30,650,180),text,fontsize=10)
        page.insert_textbox(pymupdf.Rect(30,210,650,300),context,fontsize=10)
        exact=page.get_textbox(pymupdf.Rect(30,30,650,180))
        binding=dict(field='average_annual_ndpr_product_t',scope='same LOM project',page=1,
            mode='native_statement',semantic_profile='yangibana_annual_ndpr_in_treo',
            statement_bbox=[30,30,650,180],statement=exact,before=prefix,after=suffix,
            original_unit='tonnes',time_basis_bbox=[30,210,650,300])
        return doc,binding
    def validate(self,doc,b,token='3090',unit='tonnes'):
        return validate_cell(doc,b,'average_annual_ndpr_product_t',token,unit,'same LOM project')
    def test_direct_ndpr_in_annual_oxides(self):
        d,b=self.fixture()
        with d:self.assertEqual(self.validate(d,b),'NATIVE_SCOPED_STATEMENT_BINDING')
    def test_wrong_token_or_unit_or_profile_or_scope_fails(self):
        for change in ('token','unit','profile','scope','bbox'):
            with self.subTest(change=change):
                d,b=self.fixture()
                if change=='profile':b['semantic_profile']='anything'
                if change=='scope':b['scope']='different project'
                if change=='bbox':b['statement_bbox']=[30,30,200,60]
                with d,self.assertRaises(ValueError):self.validate(d,b,'3000' if change=='token' else '3090','tpa' if change=='unit' else 'tonnes')
    def test_annual_oxide_semantics_required(self):
        for before_change in [('annual','peak'),('rare earth oxides','rare earth metals')]:
            d,b=self.fixture();d.close()
            text=b['before'].replace(*before_change)+' 3,090 '+b['after']
            d,b=self.fixture(text);b['before']=b['before'].replace(*before_change)
            with d,self.assertRaisesRegex(ValueError,'SEMANTICS'):self.validate(d,b)
    def test_project_life_context_required(self):
        for context in ('100% Project basis','a 19-year mine life','40% Project basis; a 19-year mine life'):
            d,b=self.fixture(context=context)
            with d,self.assertRaisesRegex(ValueError,'ANNUAL_BASIS'):self.validate(d,b)

if __name__=='__main__':unittest.main()
