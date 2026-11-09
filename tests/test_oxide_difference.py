import copy,unittest
import pymupdf
from au_ree_v2.source_cells import validate_cell


class OxideDifference(unittest.TestCase):
    def fixture(self):
        d=pymupdf.open();self.addCleanup(d.close);p=d.new_page()
        for x,y,text in [(40,30,'Table 1 - Known Mineral Resource'),(40,65,'Classification'),(180,65,'Tonnes'),
            (300,65,'TREO'),(420,65,'TREO-CeO2'),(180,80,'(Mt)'),(300,80,'(ppm)'),(420,80,'(ppm)'),
            (40,110,'Inferred'),(180,110,'98'),(300,110,'890'),(420,110,'660'),
            (40,140,'Total'),(180,140,'98'),(300,140,'890'),(420,140,'660'),
            (40,175,'TREO-CeO2 = TREO grade minus CeO2')]:p.insert_text((x,y),text,fontsize=10)
        def box(text,occ=0):
            b=p.search_for(text)[occ];return [b.x0-.1,b.y0-.1,b.x1+.1,b.y1+.1]
        table=[30,15,550,150];row=[35,128,540,146]
        s=dict(page=1,bbox=table,anchor='TREO',anchor_bbox=box('TREO'),row_label='Total')
        b=dict(mode='native_cell',field='grade',basis='TREO',scope='global',page=1,original_unit='ppm',section_id='total',
            table_bbox=table,table_label='Table 1 - Known Mineral Resource',table_label_bbox=box('Table 1 - Known Mineral Resource'),
            row_bbox=row,row_label='Total',row_label_bbox=box('Total'),column_bbox=[280,50,360,148],column_label='TREO',column_label_bbox=box('TREO'),
            unit_bbox=box('(ppm)'),unit_label='(ppm)',scope_anchor='TREO',scope_anchor_bbox=box('TREO'))
        derived=dict(mode='native_oxide_difference',field='reported_resource_ce_ppm',basis='CeO2',scope='global',page=1,section_id='total',
            table_bbox=table,row_bbox=row,row_label='Total',row_label_bbox=box('Total'),derivation_method='TREO_PPM_MINUS_TREO_EX_CEO2_PPM',
            definition_bbox=box('TREO-CeO2 = TREO grade minus CeO2'),input_treo=b,treo_token='890',
            input_treo_ex_ceo2=dict(column_bbox=[400,50,500,148],column_label_bbox=box('TREO-CeO2'),unit_bbox=box('(ppm)',1),token='660'))
        return d,derived,{'total':s}

    def check(self,args,token='230',unit='ppm',field='reported_resource_ce_ppm'):
        d,b,s=args;return validate_cell(d,b,field,token,unit,'global',selected_sections=s)

    def test_exact_definition_same_selected_total_row(self):
        self.assertIn('DERIVED_SAME_ROW',self.check(self.fixture()))

    def test_wrong_values_units_scope_basis_definition_and_rows_rejected(self):
        for change in ['result','unit','field','basis','scope','method','definition','nested_row','input_row',
                       'header','wrong_oxide','overlap','input_value','missing_section','nonfinite']:
            with self.subTest(change=change):
                args=self.fixture();d,b,s=args;token='230';unit='ppm';field='reported_resource_ce_ppm'
                if change=='result':token='220'
                if change=='unit':unit='%'
                if change=='field':field='reported_resource_nd_ppm'
                if change=='basis':b['basis']='Ce2O3'
                if change=='scope':b['scope']='nested high-grade subset'
                if change=='method':b['derivation_method']='PEER_SUBTRACTION'
                if change=='definition':b['definition_bbox']=[30,15,550,35]
                if change=='nested_row':b['row_label']='Inferred'
                if change=='input_row':b['input_treo']['row_bbox']=[35,98,540,116]
                if change=='header':b['input_treo_ex_ceo2']['column_label_bbox']=b['input_treo']['column_label_bbox']
                if change=='wrong_oxide':b['input_treo_ex_ceo2']['column_label_bbox']=[175,50,230,70]
                if change=='overlap':b['input_treo_ex_ceo2']['column_bbox']=b['input_treo']['column_bbox']
                if change=='input_value':b['input_treo_ex_ceo2']['token']='220'
                if change=='missing_section':s.clear()
                if change=='nonfinite':b['input_treo_ex_ceo2']['unit_bbox']=[0,0,float('nan'),10]
                with self.assertRaises(ValueError):self.check(args,token,unit,field)
