import copy,csv,json,tempfile,unittest
from pathlib import Path
import pymupdf
from au_ree_v2.asx_validation import compare_summaries,catalogue_month_proof
from au_ree_v2.reviewed_discovery import validate_discovery,project_id
from au_ree_v2.source_cells import validate_cell
from au_ree_v2.store import filehash


class ResourceShareRules(unittest.TestCase):
    def native_fixture(self):
        d=pymupdf.open();p=d.new_page();p.insert_text((40,30),'Table 12',fontsize=10)
        title='Percentage Proportion of TREO in the Mineral Resources'
        p.insert_text((40,50),title,fontsize=10);p.insert_text((420,80),'Total',fontsize=10)
        p.insert_text((330,80),'Measured',fontsize=10)
        p.insert_text((40,110),'Nd2O3',fontsize=10);p.insert_text((420,110),'20.5',fontsize=10);p.insert_text((330,110),'20.5',fontsize=10)
        def rect(text):return list(p.search_for(text)[0])
        b=dict(mode='native_cell',field='reported_resource_nd_ppm',basis='Nd2O3',scope='global total',page=1,original_unit='%TREO',resource_orientation='oxide_rows',
            table_bbox=[30,15,560,120],table_label='Table 12',table_label_bbox=rect('Table 12'),row_bbox=[35,98,550,115],row_label='Nd2O3',row_label_bbox=rect('Nd2O3'),
            column_bbox=[410,15,470,120],column_label='Total',column_label_bbox=rect('Total'),unit_scope_bbox=[30,15,560,120],unit_bbox=rect('Percentage'),unit_label='Percentage',
            scope_anchor='Total',scope_anchor_bbox=rect('Total'),metric_context=title,metric_context_bbox=rect(title),section_id='total')
        section={'total':dict(page=1,bbox=[30,15,560,120],anchor_bbox=rect('Total'),anchor='Total',row_label='Nd2O3')}
        return d,b,section
    def test_transposed_percent_table_uses_total_column_and_exact_oxide(self):
        d,b,s=self.native_fixture()
        with d:self.assertEqual('NATIVE_TABLE_ROW_COLUMN_CELL_BINDING',validate_cell(d,b,b['field'],'20.5','%TREO','global total',selected_sections=s))
    def test_same_number_in_measured_column_is_not_global_total(self):
        d,b,s=self.native_fixture();p=d[0]
        b.update(column_bbox=[320,15,380,120],column_label='Measured',column_label_bbox=list(p.search_for('Measured')[0]))
        with d,self.assertRaisesRegex(ValueError,'TOTAL_COLUMN|SEMANTICS'):validate_cell(d,b,b['field'],'20.5','%TREO','global total',selected_sections=s)
    def test_transposed_table_cannot_be_relabelled_as_bulk_percent(self):
        d,b,s=self.native_fixture()
        with d,self.assertRaisesRegex(ValueError,'UNIT'):validate_cell(d,b,b['field'],'20.5','%','global total',selected_sections=s)


class DiscoveryRules(unittest.TestCase):
    def fixture(self,root):
        pdf=root/'source.pdf';d=pymupdf.open();p=d.new_page()
        p.insert_text((40,40),'2 May 2024');p.insert_text((40,70),'Deep Leads in Tasmania. ABx Group.');d.save(pdf);d.close()
        sha=filehash(pdf);url='https://issuer.example/source.pdf'
        (root/'downloads.json').write_text(json.dumps([dict(url=url,path='source.pdf',document_sha256=sha,status='PDF_ACQUIRED')]))
        s=dict(asset_set='source',path='source.pdf',sha256=sha,url=url,kind='pdf',evidence=[dict(page=1,markers=['Deep Leads','Tasmania'])])
        r=dict(candidate_key='deep-leads',name='Deep Leads',aliases=['Deep Leads'],country='AU',scope='One combined mining project',
            decision='ADMIT_PROJECT',reason='Dated original',sources=[s],identity=dict(source_index=0,source_key='deep',publication_date='2024-05-02',
                date_evidence=dict(page=1,markers=['2 May 2024']),project_evidence=dict(page=1,markers=['Deep Leads','Tasmania']),name_marker='Deep Leads',state='TAS',state_marker='Tasmania'))
        cfg=dict(version='reviewed-project-discovery-v1',cutoff='2026-11-05',acquired_through='2026-11-10',candidates=[r])
        return cfg
    def run_config(self,root,cfg,existing=()):
        path=root/'review.json';path.write_text(json.dumps(cfg));return validate_discovery(path,{'source':root},list(existing),'2026-11-05')
    def test_admission_does_not_invent_resource_observations(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);r=self.run_config(root,self.fixture(root));self.assertEqual(project_id('deep-leads'),r['projects'][0]['entity_id'])
            self.assertNotIn('observations',r);self.assertEqual('TAS',r['records'][0]['state'])
    def test_candidate_only_cannot_enter_summary(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);c=self.fixture(root);c['candidates'][0]['decision']='CANDIDATE_ONLY'
            self.assertEqual([],self.run_config(root,c)['projects'])
    def test_alias_collision_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);c=self.fixture(root)
            with self.assertRaisesRegex(ValueError,'DUPLICATE_PROJECT'):self.run_config(root,c,[dict(entity_id='old',name='Another name',aliases=['Deep Leads'])])
    def test_date_state_country_and_scope_fail_closed(self):
        for change in ['date','state','country','scope','cutoff']:
            with self.subTest(change=change),tempfile.TemporaryDirectory() as t:
                root=Path(t);c=self.fixture(root);r=c['candidates'][0]
                if change=='date':r['identity']['publication_date']='2026-11-06'
                elif change=='state':r['identity']['state']='WA'
                elif change=='country':r['country']='BR'
                elif change=='scope':r['scope']=''
                else:c['cutoff']='2026-11-10'
                with self.assertRaises(ValueError):self.run_config(root,c)
    def test_hash_receipt_and_page_cannot_be_borrowed(self):
        for change in ['hash','url','marker','page','path']:
            with self.subTest(change=change),tempfile.TemporaryDirectory() as t:
                root=Path(t);c=self.fixture(root);s=c['candidates'][0]['sources'][0]
                if change=='hash':s['sha256']='0'*64
                elif change=='url':s['url']='https://issuer.example/other.pdf'
                elif change=='marker':s['evidence'][0]['markers']=['Other project']
                elif change=='page':s['evidence'][0]['page']=2
                else:s['path']='../source.pdf'
                with self.assertRaises((ValueError,FileNotFoundError)):self.run_config(root,c)

    def test_month_precision_requires_government_edition_and_month_bounds(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);c=self.fixture(root);r=c['candidates'][0]
            r['identity'].update(publication_date_precision='MONTH',publication_date_interval=['2024-05-01','2024-05-31'],publication_date='2024-05-31',source_kind='GOVERNMENT_PROJECT_CATALOGUE')
            with self.assertRaisesRegex(ValueError,'EDITION_MONTH'):self.run_config(root,c)


class CatalogueMonthRules(unittest.TestCase):
    def document(self):
        d=pymupdf.open();p=d.new_page();p.insert_text((40,40),'This February 2026 edition profiles projects.')
        p=d.new_page();p.insert_text((40,40),'Publication date: March 2026');return d
    def test_earlier_edition_cannot_override_explicit_publication_month(self):
        d=self.document()
        with d,self.assertRaisesRegex(ValueError,'EDITION_CANNOT_OVERRIDE'):
            catalogue_month_proof(d,'2026-02-28','this february 2026 edition profiles projects.')
    def test_publisher_label_preserves_month_precision(self):
        d=self.document()
        with d:catalogue_month_proof(d,'2026-03-31','publication date: march 2026','PUBLISHER_PUBLICATION_MONTH')
    def test_url_or_unlabelled_month_cannot_supply_publication_month(self):
        d=self.document()
        with d,self.assertRaisesRegex(ValueError,'LABEL_MONTH'):
            catalogue_month_proof(d,'2026-03-31','march 2026','PUBLISHER_PUBLICATION_MONTH')


class ExpansionComparisonRules(unittest.TestCase):
    def write(self,folder,rows):
        folder.mkdir()
        for name,fields,data in [('專案總表.csv',['專案ID','專案名稱','value'],rows),('field_provenance.csv',['project_id','column'],[]),('missing_fields.csv',['project_id','column'],[])]:
            with (folder/name).open('w',encoding='utf-8-sig',newline='') as f:
                w=csv.DictWriter(f,fields);w.writeheader();w.writerows(data)
    def test_new_project_blanks_separate_from_original_gap_reduction(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t);self.write(p/'before',[dict(專案ID='A',專案名稱='a',value='')]);self.write(p/'after',[dict(專案ID='A',專案名稱='a',value='1'),dict(專案ID='B',專案名稱='b',value='')])
            with self.assertRaisesRegex(ValueError,'COHORT'):compare_summaries(p/'before',p/'after',p/'out')
            r=compare_summaries(p/'before',p/'after',p/'out',allow_expansion=True)
            self.assertEqual(1,r['newly_filled_cells']);self.assertEqual(0,r['remaining_blank_cells']);self.assertEqual(1,r['expanded_remaining_blank_cells'])
            self.assertEqual(2,r['added_project_filled_cells']);self.assertEqual(1,r['added_project_blank_cells'])
    def test_expansion_cannot_remove_original_project(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t);self.write(p/'before',[dict(專案ID='A',專案名稱='a',value='')]);self.write(p/'after',[dict(專案ID='B',專案名稱='b',value='')])
            with self.assertRaisesRegex(ValueError,'COHORT'):compare_summaries(p/'before',p/'after',p/'out',allow_expansion=True)


class AnnualOxideDefinitionRules(unittest.TestCase):
    def fixture(self):
        d=pymupdf.open();p=d.new_page();p.insert_text((40,50),'Operations metrics (life-of-mine annual average)')
        p.insert_text((40,90),'Nd-Pr contained in REC 990 tpa')
        p=d.new_page();definition='Nd-Pr, Dy and Tb production figures are life-of-mine annual average calculated by multiplying REC production by TREO grade and its respective rare earth oxide composition as a % of TREO'
        p.insert_textbox(pymupdf.Rect(40,40,550,130),definition,fontsize=10)
        b=dict(mode='native_statement',field='average_annual_ndpr_product_t',scope='one study',page=1,statement_bbox=[39,77,350,96],statement='Nd-Pr contained in REC 990 tpa',before='Nd-Pr contained in REC',after='tpa',time_basis_bbox=[39,37,400,54],oxide_basis_proof=dict(page=2,bbox=[39,39,551,131]))
        return d,b
    def test_exact_annual_row_and_separate_oxide_definition(self):
        d,b=self.fixture()
        with d:self.assertEqual('NATIVE_SCOPED_STATEMENT_BINDING',validate_cell(d,b,b['field'],'990','tpa','one study'))
    def test_wrong_product_or_missing_oxide_proof_rejected(self):
        for change in ['product','time','definition','value']:
            with self.subTest(change=change):
                d,b=self.fixture()
                if change=='product':b['before']='Rare earth concentrate'
                elif change=='time':b['time_basis_bbox']=[40,140,400,160]
                elif change=='definition':b['oxide_basis_proof']['bbox']=[40,200,500,230]
                with d,self.assertRaises(ValueError):validate_cell(d,b,b['field'],'991' if change=='value' else '990','tpa','one study')


if __name__=='__main__':unittest.main()
