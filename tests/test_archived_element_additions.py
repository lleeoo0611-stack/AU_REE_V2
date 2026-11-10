import copy,json,sqlite3,unittest,hashlib,tempfile
from pathlib import Path
from unittest.mock import patch
from au_ree_v2.archived_element_additions import matching_resource,verify_single_oxide
from au_ree_v2.project_summary import ELEMENTS
from au_ree_v2.store import filehash


class SameResourceContractTests(unittest.TestCase):
    def setUp(self):
        self.db=sqlite3.connect(':memory:');self.db.row_factory=sqlite3.Row;self.addCleanup(self.db.close)
        self.db.execute('CREATE TABLE observations(obs_id TEXT,entity_id TEXT,variable TEXT,value REAL,unit TEXT,basis TEXT,scope TEXT,statement_id TEXT,category TEXT,effective_date TEXT,source_sha TEXT,status TEXT,raw TEXT)')
        self.entry=dict(project_id='P',selected_source_sha256='native',scope='Garford+Pidinga;Boland+Head;in situ',
            statement_id='mre-v1',category='INDICATED_INFERRED_TOTAL',effective_date='2026-10-22',
            raw_contract=dict(cutoff_grade='200ppm TREO-Ce;ISR US$5.27/t',reo_definition='15 oxides including Y'))
        for oid,var,value,unit in [('a','ore_mt',150,'Mt'),('b','grade',470,'ppm'),('c','contained_treo_kt',70.4,'kt')]:
            self.db.execute('INSERT INTO observations VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',
                (oid,'P',var,value,unit,'TREO',self.entry['scope'],'mre-v1','INDICATED_INFERRED_TOTAL','2026-10-22','native','AUTO_VALIDATED',json.dumps(self.entry['raw_contract'])))
        self.row={'礦石蘊藏量_Mt':'150','TREO品位_pct':'0.047','總TREO蘊藏量_kt':'70.4'}
        self.trace=[dict(project_id='P',column='礦石蘊藏量_Mt',source_sha256='native',observation_ids='["a","b","c"]')]

    def test_exact_resource_contract_passes(self):
        mt,ppm,ids,_=matching_resource(self.row,self.trace,self.db,self.entry)
        self.assertEqual((150,470,['a','b','c']),(mt,ppm,ids))

    def test_same_numbers_different_scope_version_category_or_date_rejected(self):
        for key in ['scope','statement_id','category','effective_date']:
            with self.subTest(key=key):
                e=dict(self.entry);e[key]='different'
                with self.assertRaisesRegex(ValueError,'SCOPE_VERSION_CATEGORY_DATE'):matching_resource(self.row,self.trace,self.db,e)

    def test_same_numbers_different_cutoff_or_reo_definition_rejected(self):
        for key in ['cutoff_grade','reo_definition']:
            with self.subTest(key=key):
                e=copy.deepcopy(self.entry);e['raw_contract'][key]='different'
                with self.assertRaisesRegex(ValueError,'CUTOFF_REO_BASIS'):matching_resource(self.row,self.trace,self.db,e)

    def test_unvalidated_or_elemental_basis_never_admitted(self):
        self.db.execute("UPDATE observations SET basis='TREE' WHERE variable='grade'")
        with self.assertRaisesRegex(ValueError,'RESOURCE_UNITS'):matching_resource(self.row,self.trace,self.db,self.entry)
        self.db.execute("UPDATE observations SET basis='TREO',status='PENDING' WHERE variable='grade'")
        with self.assertRaisesRegex(ValueError,'SCOPE_VERSION_CATEGORY_DATE'):matching_resource(self.row,self.trace,self.db,self.entry)

    def test_current_value_conflict_rejected(self):
        self.row['TREO品位_pct']='0.048'
        with self.assertRaisesRegex(ValueError,'CURRENT_VALUE_CONFLICT'):matching_resource(self.row,self.trace,self.db,self.entry)


class SingleOxidePDFTests(unittest.TestCase):
    def setUp(self):
        import pymupdf
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.path=self.root/'original.pdf'
        with pymupdf.open() as doc:
            p=doc.new_page();p.insert_text((100,80),'Y2O3 (ppm)');p.insert_text((30,150),'Total');p.insert_text((100,150),'1,400');doc.save(self.path)
        with pymupdf.open(self.path) as doc:
            p=doc[0];cell=p.search_for('1,400')[0];label=p.search_for('Total')[0]
            render=hashlib.sha256(p.get_pixmap(matrix=pymupdf.Matrix(1.5,1.5)).samples).hexdigest()
        self.entry=dict(review_id='synthetic-review',selected_source_sha256=filehash(self.path),scope='global total',statement_id='v1',category='MEASURED_INFERRED_TOTAL',effective_date='2017-09-19',
            pdf=dict(asset_set='fixture',path='original.pdf',sha256=filehash(self.path),page=1,render_sha256=render),same_version_markers=['Total','Y2O3 (ppm)'],
            cell_binding=dict(oxide='Y2O3',unit='ppm bulk ore',original_token='1,400',bbox=list(cell),header_bbox=[95,60,180,85],header_marker='Y2O3 (ppm)',row_label_bbox=list(label)))
        self.row={o+'_x':'' for o in ELEMENTS};self.row['Y2O3_氧化釔_kt']=self.row.pop('Y2O3_x')
        self.row.update({'總TREO蘊藏量_kt':'661.584','已公布元素數_共15項':'','已公布元素總和_kt':'','元素總和/TREO':'','元素數據一致性檢查':''})
        self.native=dict(source_url='https://example.test/original.pdf')

    def verify(self):
        with patch('au_ree_v2.archived_element_additions.matching_resource',return_value=(75.18,8800,['ore','grade'],self.native)):
            return verify_single_oxide(self.row,[],None,self.entry,{'fixture':self.root})

    def test_total_header_cell_binds_yield_and_partial_summaries(self):
        fills=self.verify();self.assertEqual(5,len(fills))
        y=next(f for f in fills if f['column']=='Y2O3_氧化釔_kt');self.assertAlmostEqual(105.252,y['value'])
        self.assertNotIn('Nd2O3_氧化釹_kt',{f['column'] for f in fills})

    def test_changed_column_or_row_binding_rejected(self):
        for key in ['header_marker','row_label_bbox']:
            with self.subTest(key=key):
                saved=copy.deepcopy(self.entry)
                self.entry['cell_binding'][key]='Nd2O3' if key=='header_marker' else [1,1,2,2]
                with self.assertRaises(ValueError):self.verify()
                self.entry=saved

    def test_existing_conflicting_oxide_or_unreviewed_other_oxide_holds(self):
        self.row['Y2O3_氧化釔_kt']='999'
        with self.assertRaisesRegex(ValueError,'EXISTING_OXIDE_CONFLICT'):self.verify()
        self.row['Y2O3_氧化釔_kt']='';self.row['Nd2O3_x']='3'
        with self.assertRaisesRegex(ValueError,'OTHER_ELEMENTS_REQUIRE_REVIEW'):self.verify()
