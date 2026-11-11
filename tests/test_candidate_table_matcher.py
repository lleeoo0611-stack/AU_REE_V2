import copy,json,unittest
from decimal import Decimal
from pathlib import Path
from au_ree_v2.candidate_table_matcher import (
    OXIDES,closure_check,header_unit,infer_columns,match_rows,matches_rounded,
    numeric,oxide_name,ppm_value,rounding_half_width,same_row_band,verify_scope)

ROOT=Path(__file__).resolve().parents[1]


class CandidateMatcherTests(unittest.TestCase):
    def setUp(self):
        self.cells=[['Category','Tonnes (Mt)','TREO (ppm)','Nd2O3 (ppm)'],['Total','75.18','7400','1400']]
        self.columns,_=infer_columns(self.cells)
        self.scope=dict(source_sha256='a',statement_id='s',scope='global',category='INDICATED_INFERRED_TOTAL',cutoff='300ppm TREO-Ce',effective_date='2026-01-01',reo_basis='CANONICAL_INCLUDING_Y',ore_mt=75.18,grade_ppm=7400)

    def test_decimal_precision_not_percentage(self):
        self.assertEqual(Decimal('.005'),rounding_half_width('75.18'))
        self.assertTrue(matches_rounded('75.18','75.1849')[0])
        self.assertFalse(matches_rounded('75.18','75.186')[0])
        self.assertFalse(matches_rounded('75.18','75.2')[0])

    def test_printed_trailing_zero_precision_preserved(self):
        self.assertEqual(Decimal('.0005'),rounding_half_width('0.010'))
        self.assertEqual(Decimal('.5'),rounding_half_width('1,400'))

    def test_numeric_rejects_censored_ambiguous_and_negative(self):
        for token in ('<10','1-2','n/a','-1','nan','1e3'):
            with self.subTest(token=token),self.assertRaises(ValueError):numeric(token)
        self.assertEqual(0,numeric(0))

    def test_subscript_and_spaced_formulae(self):
        for text in ('Nd₂O₃ (ppm)','N d 2 O 3 (ppm)','Nd O\n2 3 (ppm)'):
            self.assertEqual('Nd2O3',oxide_name(text))
        self.assertIsNone(oxide_name('Ce2O3 (ppm)'))

    def test_units_and_conflicts(self):
        self.assertEqual('ppm',header_unit('Nd2O3 (ppm)'))
        self.assertEqual('%',header_unit('Nd2O3 (%)'))
        for text in ('Nd2O3','Nd2O3 % ppm','Nd2O3 %TREO'):
            with self.assertRaises(ValueError):header_unit(text)
        self.assertEqual(100,ppm_value('.01','%'))
        self.assertEqual(100,ppm_value('.1','kg/t'))
        self.assertEqual(100,ppm_value('7500','t',75))
        self.assertEqual(100,ppm_value('7.5','kt',75))

    def test_indicated_subset_same_numbers_rejected(self):
        self.cells[1][0]='Indicated'
        with self.assertRaisesRegex(ValueError,'CATEGORY_OR_SUBSET'):match_rows(self.cells,self.columns,75.18,7400)

    def test_two_numeric_matches_never_choose(self):
        self.cells.append(self.cells[1].copy())
        with self.assertRaisesRegex(ValueError,'MULTIPLE_MATCHING'):match_rows(self.cells,self.columns,75.18,7400)

    def test_both_ore_and_grade_required(self):
        self.cells[1][2]='7300'
        with self.assertRaisesRegex(ValueError,'NO_MATCH'):match_rows(self.cells,self.columns,75.18,7400)

    def test_cutoff_category_date_basis_and_statement_strict(self):
        for key in ('cutoff','category','effective_date','reo_basis','statement_id','scope'):
            changed=dict(self.scope);changed[key]='different'
            with self.subTest(key=key),self.assertRaisesRegex(ValueError,'SCOPE_MISMATCH'):verify_scope(self.scope,changed)

    def test_unknown_scope_never_passes(self):
        changed=dict(self.scope);changed.pop('cutoff')
        with self.assertRaisesRegex(ValueError,'EVIDENCE_MISSING'):verify_scope(self.scope,changed)

    def test_cross_document_claim_needs_verified_evidence(self):
        changed=dict(self.scope,source_sha256='b',same_mre_bridge=dict(verified=True,selected_sha256='a',candidate_sha256='b'))
        with self.assertRaisesRegex(ValueError,'CROSS_DOCUMENT'):verify_scope(self.scope,changed)

    def test_cummins_old_519_not_current_524(self):
        self.cells[1][1]='519'
        with self.assertRaisesRegex(ValueError,'NO_MATCH'):match_rows(self.cells,self.columns,524.3,7400)

    def test_jupiter_category_subset_not_global(self):
        self.cells[1]=['Indicated','1700','1700','100']
        with self.assertRaisesRegex(ValueError,'CATEGORY_OR_SUBSET'):match_rows(self.cells,self.columns,1700,1700)

    def test_goschen_no_ho_lu_invented(self):
        columns,_=infer_columns([['Class','Tonnes (Mt)','TREO (ppm)','Nd2O3 (%)'],['Total','94.2','800','0.1']])
        self.assertNotIn('Ho2O3',columns);self.assertNotIn('Lu2O3',columns)

    def test_ridley_ce2o3_not_renamed(self):
        columns,_=infer_columns([['Class','Tonnes (Mt)','TREO (ppm)','Ce2O3 (ppm)'],['Total','122.54','889','100']])
        self.assertNotIn('CeO2',columns)

    def test_full_closure_rejects_entire_composition(self):
        grades=dict.fromkeys(OXIDES,10);widths=dict.fromkeys(OXIDES,.5)
        self.assertIsNotNone(closure_check(grades,widths,150,.5))
        with self.assertRaisesRegex(ValueError,'CLOSURE_FAIL'):closure_check(grades,widths,200,.5)
        grades.pop('Y2O3');self.assertIsNone(closure_check(grades,widths,200,.5))

    def test_different_horizontal_extents_can_be_same_row(self):
        self.assertTrue(same_row_band([0,10,100,20],[1,10.1,200,19.9]))
        self.assertFalse(same_row_band([0,10,100,20],[0,30,100,40]))

    def test_archived_dubbo_table2_same_value(self):
        path=ROOT/'work/attachment-elements-20261111/extraction-v2/734d9ea35fd9617eb2bad21c48fec17cdae08a5c66fa3e3cf7857390d04218ab/page-26.json'
        # The committed fixture below is the exact archived native table, not
        # a dependency on private work files in CI.
        path=ROOT/'tests/fixtures/candidate_tables/dubbo_page26_table2.json'
        page=json.loads(path.read_text('utf8'));table=page['tables'][0]
        columns,_=infer_columns(table['cells'])
        match=match_rows(table['cells'],columns,75.18,7400)
        token=table['cells'][match['row']][columns['Y2O3']['column']]
        self.assertEqual('ppm',header_unit(columns['Y2O3']['header']))
        self.assertEqual(Decimal('105.252'),numeric('75.18')*numeric(token)*Decimal('.001'))
        self.assertEqual('Total',match['label'])


class PositiveValidatorIntegrationTests(unittest.TestCase):
    def create_fixture(self,root,oxide_unit="ppm",oxide_token="100"):
        import pymupdf
        from au_ree_v2.store import filehash
        from au_ree_v2.candidate_table_matcher import make_native_observation
        pdf=root/'resource.pdf'
        doc=pymupdf.open();page=doc.new_page(width=500,height=300)
        for x,y,text in [(50,30,'1 January 2025'),(50,50,'Test Quarry Mineral Resource Indicated Inferred'),(50,95,'Table 1 Mineral Resource'),(55,125,'Category'),(155,125,'Tonnes'),(255,125,'TREO'),(355,125,'Nd2O3'),(155,140,'(Mt)'),(255,140,'(ppm)'),(355,140,'('+oxide_unit+')'),(55,170,'Total'),(155,170,'75.18'),(255,170,'7400'),(355,170,oxide_token)]:
            page.insert_text((x,y),text,fontsize=10)
        for x in (50,150,250,350,450):page.draw_line((x,110),(x,180))
        for y in (110,150,180):page.draw_line((50,y),(450,y))
        doc.save(pdf);doc.close();doc=pymupdf.open(stream=pdf.read_bytes(),filetype="pdf");self.addCleanup(doc.close)
        page=doc[0]
        def box(text,index=0):return list(page.search_for(text)[index])
        scope='Test Quarry global Indicated+Inferred resource'
        section=dict(page=1,bbox=[40,80,480,185],anchor_bbox=box('Tonnes'),anchor='Tonnes',row_label='Total')
        base=dict(mode='native_cell',scope=scope,page=1,table_bbox=[40,80,480,185],table_label='Table 1 Mineral Resource',table_label_bbox=box('Table 1 Mineral Resource'),row_bbox=[50,150,450,180],row_label='Total',row_label_bbox=box('Total'),scope_anchor='Tonnes',scope_anchor_bbox=box('Tonnes'),section_id='resource')
        ore_binding=dict(base,field='ore_mt',basis='TREO',original_unit='Mt',unit_label='(Mt)',unit_bbox=box('(Mt)'),column_bbox=[150,80,250,185],column_label='Tonnes',column_label_bbox=box('Tonnes'))
        grade_binding=dict(base,field='grade',basis='TREO',original_unit='ppm',unit_label='(ppm)',unit_bbox=box('(ppm)'),column_bbox=[250,80,350,185],column_label='TREO',column_label_bbox=box('TREO'))
        ore=dict(variable='ore_mt',value=75.18,unit='Mt',basis='TREO',original_token='75.18',evidence=dict(page=1,markers=['Total','75.18']),cell_binding=ore_binding)
        grade=dict(variable='grade',value=7400,unit='ppm',basis='TREO',original_token='7400',evidence=dict(page=1,markers=['Total','7400']),cell_binding=grade_binding)
        sha=filehash(pdf);url='https://example.test/resource.pdf'
        review=dict(review_id='fixture',project_id='P',source_key='fixture',source_sha256=sha,asset_set='fixture',path='resource.pdf',url=url,publication_date='2025-01-01',effective_date='2025-01-01',effective_date_role='RESOURCE_EFFECTIVE_DATE',date_precision='DAY',identity_evidence=dict(page=1,markers=['Test Quarry']),date_evidence=dict(page=1,markers=['1 January 2025']),scope=scope,statement_id='test-global',resource_categories=['INDICATED','INFERRED'],scope_evidence=[dict(page=1,markers=['Mineral Resource','Indicated','Inferred'])],selected_resource_sections={'resource':section},selection_reason='Selected global source resource',observations=[ore,grade])
        table=page.find_tables().tables[0];cols,_=infer_columns(table.extract());match=match_rows(table.extract(),cols,75.18,7400)
        obs=make_native_observation(page,table,match['row'],cols['Nd2O3']['column'],'Nd2O3',oxide_token,oxide_unit,review,ore)
        obs['candidate_match']['tolerances']=match
        (root/'downloads.json').write_text(json.dumps([dict(url=url,document_sha256=sha,status='PDF_ACQUIRED')]),encoding='utf8')
        return review,obs,doc

    def test_generated_review_reaches_existing_validator_and_preserves_old_raw(self):
        import tempfile
        from au_ree_v2.asx_validation import validate_reviews
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);review,obs,_=self.create_fixture(root)
            ledger=root/'ledger.json'
            def validate(r):
                ledger.write_text(json.dumps(dict(version='asx-source-review-v2',acquired_through='2025-01-01',reviews=[r])),encoding='utf8')
                return validate_reviews(ledger,{'fixture':root},[dict(entity_id='P',name='Test Quarry',aliases=[])])['observations']['P']
            original=validate(review)
            expanded=copy.deepcopy(review);expanded['observations'].append(obs)
            result=validate(expanded)
            self.assertEqual([r['raw'] for r in original],[r['raw'] for r in result[:2]])
            raw=json.loads(result[2]['raw'])
            self.assertEqual('AUTO_MATCHED_SAME_SCOPE_TABLE',raw['review_method'])
            self.assertEqual('RESOURCE_ORE_GRADE_OXIDE_PPM',raw['material_basis'])
            self.assertEqual('AUTO_VALIDATED',result[2]['status'])
            self.assertEqual(100,result[2]['value'])
            for key,bad in [('row',0),('column',1),('original_token','101'),('unit','%')]:
                damaged=copy.deepcopy(expanded);damaged['observations'][-1]['candidate_match'][key]=bad
                with self.subTest(key=key),self.assertRaises(ValueError):validate(damaged)

    def test_equivalent_units_use_same_native_row_and_existing_validator(self):
        import tempfile
        from au_ree_v2.asx_validation import validate_reviews
        for unit,token in [('kg/t','0.1'),('t','7518'),('kt','7.518'),('%','0.01')]:
            with self.subTest(unit=unit),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);review,obs,_=self.create_fixture(root,unit,token)
                review['observations'].append(obs)
                ledger=root/'ledger.json';ledger.write_text(json.dumps(dict(version='asx-source-review-v2',acquired_through='2025-01-01',reviews=[review])),encoding='utf8')
                result=validate_reviews(ledger,{'fixture':root},[dict(entity_id='P',name='Test Quarry',aliases=[])])['observations']['P']
                self.assertAlmostEqual(100,result[-1]['value'])
                raw=json.loads(result[-1]['raw'])
                self.assertEqual(unit,raw['original_unit'])
                self.assertEqual(75.18,raw['candidate_match']['ore_mt'])
                self.assertEqual('NATIVE_TABLE_ROW_COLUMN_CELL_BINDING',raw['validated_cell_method'])

    def test_source_header_ppm_cannot_be_declared_percent(self):
        import tempfile
        from au_ree_v2.candidate_table_matcher import make_native_observation
        with tempfile.TemporaryDirectory() as tmp:
            review,_,doc=self.create_fixture(Path(tmp));table=doc[0].find_tables().tables[0]
            with self.assertRaisesRegex(ValueError,'HEADER_OR_UNIT'):
                make_native_observation(doc[0],table,1,3,'Nd2O3','100','%',review,review['observations'][0])


if __name__=='__main__':unittest.main()
