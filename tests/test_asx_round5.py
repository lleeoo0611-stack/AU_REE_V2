import copy,csv,json,tempfile,unittest
from pathlib import Path
import sys
import pymupdf
from au_ree_v2.project_summary import reported_magnet_group,complete_sum,MAGNET,HEAVY
from au_ree_v2.source_cells import validate_cell


class ReportedMagnetGroup(unittest.TestCase):
    def fixture(self):
        bundle=dict(source_sha256='s',statement_id='global',scope='global300cutoff',effective_date='2023-04-19',value=dict(ore_mt=94.9,grade_pct=.073895))
        obs=dict(source_sha='s',statement_id='global',scope='global300cutoff',effective_date='2023-04-19',variable='reported_resource_magnet_ppm',unit='ppm',basis='PrNdDyTb_OXIDES',value=130.79,raw=json.dumps(dict(material_basis='RESOURCE_ORE_GRADE_MAGNET_OXIDE_GROUP_PPM')))
        return bundle,obs
    def test_group_is_matched_to_ore_grade_not_treo_contained_mass(self):
        b,o=self.fixture();r=reported_magnet_group([o],b)
        self.assertAlmostEqual(12.411971,r['contained_kt'])
        self.assertAlmostEqual(130.79/738.95*100,r['share_percent'])
        self.assertEqual({'observation','contained_kt','share_percent'},set(r))
        self.assertIsNone(complete_sum({},MAGNET));self.assertIsNone(complete_sum({},HEAVY))
    def test_other_dates_scopes_sources_or_statements_cannot_supply_group(self):
        for key in ['source_sha','statement_id','scope','effective_date']:
            with self.subTest(key=key):
                b,o=self.fixture();o[key]='other';self.assertIsNone(reported_magnet_group([o],b))
    def test_sample_group_wrong_units_and_wrong_element_sets_cannot_fill(self):
        for change in ['basis','unit','material','variable']:
            with self.subTest(change=change):
                b,o=self.fixture()
                if change=='basis':o['basis']='DyTb_OXIDES'
                if change=='unit':o['unit']='%'
                if change=='material':o['raw']=json.dumps(dict(material_basis='SAMPLE_OR_PRODUCT_GRADE'))
                if change=='variable':o['variable']='reported_resource_nd_ppm'
                self.assertIsNone(reported_magnet_group([o],b))
    def test_group_above_total_negative_and_conflicts_remain_unknown(self):
        for value in [-1,739,float('nan'),float('inf')]:
            with self.subTest(value=value):
                b,o=self.fixture();o['value']=value;self.assertIsNone(reported_magnet_group([o],b))
        b,o=self.fixture();other=copy.deepcopy(o);other['value']=131
        self.assertIsNone(reported_magnet_group([o,other],b))
    def test_reported_zero_is_not_missing(self):
        b,o=self.fixture();o['value']=0;r=reported_magnet_group([o],b)
        self.assertEqual(0,r['contained_kt']);self.assertEqual(0,r['share_percent'])
    def test_zero_total_grade_is_not_a_valid_denominator(self):
        b,o=self.fixture();b['value']['grade_pct']=0;o['value']=0
        self.assertIsNone(reported_magnet_group([o],b))


class MagnetGroupSourceCells(unittest.TestCase):
    def fixture(self,definition=None):
        d=pymupdf.open();p=d.new_page()
        definition=definition or 'Total permanent magnet REO (MREO) = Total permanent magnet REOs (Pr6O11 + Nd2O3 + Tb4O7 + Dy2O3)'
        for xy,t in [((30,30),'Resource'),((30,50),'Global total'),((200,75),'MREO'),((200,90),'ppm'),((30,115),'Total'),((200,115),'130.79')]:p.insert_text(xy,t,fontsize=8)
        p.insert_text((30,150),definition,fontsize=6)
        def rect(t):
            r=next(r for r in p.search_for(t) if 100<r.y0<120) if t=='Total' else p.search_for(t)[0];return [r.x0-.1,r.y0-.1,r.x1+.1,r.y1+.1]
        b=dict(mode='native_cell',field='reported_resource_magnet_ppm',basis='PrNdDyTb_OXIDES',scope='global',page=1,original_unit='ppm',
            table_bbox=[20,15,300,130],row_bbox=[20,103,300,120],column_bbox=[195,15,250,130],row_label='Total',row_label_bbox=rect('Total'),
            column_label='MREO',column_label_bbox=rect('MREO'),unit_bbox=rect('ppm'),unit_label='ppm',table_label='Resource',table_label_bbox=rect('Resource'),
            scope_anchor='Global total',scope_anchor_bbox=rect('Global total'),section_id='global',group_definition_bbox=[25,140,560,155])
        sections={'global':dict(page=1,bbox=b['table_bbox'],anchor='Global total',anchor_bbox=b['scope_anchor_bbox'])}
        return d,b,sections
    def test_exact_source_four_oxide_definition_is_required(self):
        d,b,s=self.fixture()
        with d:self.assertEqual('NATIVE_TABLE_ROW_COLUMN_CELL_BINDING',validate_cell(d,b,b['field'],'130.79','ppm','global',selected_sections=s))
    def test_group_cannot_be_relabelled_as_individual_oxide(self):
        d,b,s=self.fixture();b.update(field='reported_resource_nd_ppm',basis='PrNdDyTb_OXIDES')
        with d,self.assertRaisesRegex(ValueError,'OXIDE_FIELD_BASIS'):validate_cell(d,b,b['field'],'130.79','ppm','global',selected_sections=s)
    def test_dytb_or_hreo_definition_rejected(self):
        for definition in ['Total heavy REO (HREO) = Eu2O3 + Gd2O3 + Tb4O7 + Dy2O3','Total permanent magnet REO (MREO) = Dy2O3 + Tb4O7']:
            with self.subTest(definition=definition):
                d,b,s=self.fixture(definition)
                with d,self.assertRaisesRegex(ValueError,'MAGNET_GROUP_DEFINITION'):validate_cell(d,b,b['field'],'130.79','ppm','global',selected_sections=s)


class ExternalNameTriage(unittest.TestCase):
    def test_ticker_company_and_near_spelling_cannot_create_project_matches(self):
        sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
        from screen_external_project_names import screen
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);(root/'data').mkdir()
            (root/'data/claims.json').write_text(json.dumps(dict(projects=[])))
            (root/'discovery.json').write_text(json.dumps(dict(candidates=[])))
            with (root/'master.csv').open('w',newline='',encoding='utf8') as f:
                w=csv.DictWriter(f,['專案ID','專案名稱']);w.writeheader();w.writerow({'專案ID':'P','專案名稱':'Known Project'})
            with (root/'input.csv').open('w',newline='',encoding='utf8') as f:
                w=csv.writer(f);w.writerow(['Name','Developer','Ticker']);w.writerows([['Known Project','False Company','ZZZ'],['Knonw Project','Real Company','ABC'],['Unrelated','Real Company','ABC']])
            r=screen(root/'input.csv',root,root/'master.csv',root/'discovery.json',root/'out')
            self.assertEqual(0,r['projects_admitted_from_external_list_alone']);self.assertEqual(0,r['numeric_values_imported'])
            self.assertEqual(0,r['companies_or_tickers_overwritten'])
            self.assertEqual(1,r['status_counts']['EXACT_REGISTERED_NAME_MATCH;DEVELOPER_TICKER_STILL_UNVERIFIED'])
            self.assertEqual(2,r['status_counts']['UNVERIFIED_EXTERNAL_LEAD;NOT_AUTOMATIC_PROJECT_ADMISSION'])
