import unittest
import pymupdf
from au_ree_v2.reviewed_metadata import validate_descriptive_attribute


class NativeLegend(unittest.TestCase):
    def fixture(self):
        doc=pymupdf.open();self.addCleanup(doc.close);p=doc.new_page()
        p.draw_rect([40,38,50,52],fill=(1,.5,0));p.insert_text((60,50),'Known Project',fontsize=10)
        p.draw_rect([40,88,50,102],fill=(1,.5,0));p.insert_text((60,100),'Trachytic tuff',fontsize=10)
        def box(text):
            b=p.search_for(text)[0];return [b.x0-.1,b.y0-.1,b.x1+.1,b.y1+.1]
        a=dict(column='礦床型態',value='Trachytic tuff',evidence=dict(page=1,markers=['Known Project','Trachytic tuff']),
            description_binding=dict(page=1,project_marker='Known Project',project_bbox=box('Known Project'),value_bbox=box('Trachytic tuff'),
                statement='trachytic tuff',literal_value='Trachytic tuff',legend_binding=dict(row_swatch_bbox=[40,38,50,52],legend_swatch_bbox=[40,88,50,102])))
        return doc,a,['Known Project'],lambda e:None,dict(source_kind='GOVERNMENT_PROJECT_CATALOGUE',url='https://agency.gov.au/flyer.pdf')

    def test_exact_row_and_native_legend_colour(self):
        self.assertIn('NATIVE_VECTOR',validate_descriptive_attribute(*self.fixture()))

    def test_wrong_swatch_label_project_and_source_are_rejected(self):
        for change in ['colour','row','label','project','source','quantity','literal']:
            with self.subTest(change=change):
                args=list(self.fixture());doc,a,aliases,evidence,review=args;b=a['description_binding']
                if change=='colour':doc[0].draw_rect([40,88,50,102],fill=(0,0,1))
                if change=='row':b['legend_binding']['row_swatch_bbox']=[40,88,50,102]
                if change=='label':b['legend_binding']['legend_swatch_bbox']=[140,88,150,102]
                if change=='project':args[2]=['Different Project']
                if change=='source':review['url']='https://example.org/flyer.pdf'
                if change=='quantity':a['column']='礦石蘊藏量_Mt'
                if change=='literal':a['value']='Carbonatite'
                with self.assertRaises(ValueError):validate_descriptive_attribute(*args)
