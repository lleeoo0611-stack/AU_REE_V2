import copy,csv,hashlib,json,sys,tempfile,unittest
from pathlib import Path
import pymupdf
from au_ree_v2.project_identity import ASX_COLUMN,merge_eligible,validate_identity,extend_summary
from au_ree_v2.store import filehash
from au_ree_v2.asx_validation import validate_reviews


class BoundedSourceHash(unittest.TestCase):
    def test_large_source_is_hashed_in_bounded_blocks(self):
        import io
        from unittest.mock import patch
        raw = b'original-source' * 180000
        class BoundedReader(io.BytesIO):
            def read(self, size=-1):
                if not 0 < size <= 1024 * 1024:
                    raise AssertionError('unbounded source read')
                return super().read(size)
        with patch.object(Path, 'open', return_value=BoundedReader(raw)):
            self.assertEqual(hashlib.sha256(raw).hexdigest(), filehash('source.pdf'))


class SameCodeSameName(unittest.TestCase):
    def row(self,name,code):return {'專案名稱':name,ASX_COLUMN:code}
    def test_normalized_same_name_and_same_verified_code(self):
        self.assertTrue(merge_eligible(self.row('Splinter Rock','OD6'),self.row('Splinter Rock Rare Earth Project','OD6')))
    def test_explicit_splinter_alias_can_merge_when_codes_match(self):
        pair=[['Splinter','Splinter Rock Rare Earth Project']]
        self.assertTrue(merge_eligible(self.row('Splinter','OD6'),self.row('Splinter Rock Rare Earth Project','OD6'),pair))
    def test_missing_different_or_non_codes_never_merge(self):
        for a,b in [('', ''),('', 'OD6'),('ABC','OD6'),('無','無'),('od6','od6')]:
            with self.subTest(a=a,b=b):self.assertFalse(merge_eligible(self.row('Splinter',a),self.row('Splinter',b)))
    def test_same_company_different_project_does_not_merge(self):
        self.assertFalse(merge_eligible(self.row('Splinter Rock','OD6'),self.row('Grass Patch','OD6')))
    def test_substring_is_not_an_alias(self):
        self.assertFalse(merge_eligible(self.row('Splinter','OD6'),self.row('Splinter Rock','OD6')))


class SourceBoundIdentity(unittest.TestCase):
    def fixture(self,root):
        d=pymupdf.open();p=d.new_page()
        for y,text in [(30,'2 May 2024'),(60,'Example Mining Limited'),(90,'ASX: ABC'),(120,'Known Project in Western Australia'),(150,'Known Project also called Known Rare Earth Project')]:p.insert_text((30,y),text,fontsize=10)
        path=root/'source.pdf';d.save(path);d.close();sha=filehash(path)
        source=dict(asset_set='asset',path='source.pdf',sha256=sha,url='https://issuer.example/original.pdf')
        (root/'downloads.json').write_text(json.dumps([dict(url=source['url'],document_sha256=sha,path='source.pdf',status='PDF_ACQUIRED')]))
        def ev(marker):return dict(page=1,markers=[marker])
        e=dict(project_id='P',code='ABC',issuer_name='Example Mining Limited',source_key='s',review_id='codeP',evidence_date='2024-05-02',
            date_evidence=ev('2 May 2024'),project_evidence=ev('Known Project'),project_marker='Known Project',issuer_evidence=ev('Example Mining Limited'),
            code_evidence=ev('ASX: ABC'),code_label='ASX: ABC',scope='Known Project issuer at source date')
        cfg=dict(version='reviewed-project-identity-v1',cutoff='2026-11-05',acquired_through='2026-11-10',sources={'s':source},codes=[e],merges=[])
        return cfg
    def run_config(self,root,cfg,rows=None):
        path=root/'ledger.json';path.write_text(json.dumps(cfg));return validate_identity(path,{'asset':root},rows or [{'專案ID':'P','專案名稱':'Known Project'}],'2026-11-05')
    def test_code_requires_hash_receipt_and_all_four_proofs(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);r=self.run_config(root,self.fixture(root));self.assertEqual('ABC',r['entries']['P']['code'])
    def test_wrong_source_marker_date_issuer_code_and_project_rejected(self):
        for change in ['hash','url','marker','date','issuer','code','project','duplicate','path']:
            with self.subTest(change=change),tempfile.TemporaryDirectory() as t:
                root=Path(t);c=self.fixture(root);e=c['codes'][0]
                if change=='hash':c['sources']['s']['sha256']='0'*64
                elif change=='url':c['sources']['s']['url']='https://issuer.example/other.pdf'
                elif change=='marker':e['project_evidence']['markers']=['Different Project']
                elif change=='date':e['evidence_date']='2026-11-06'
                elif change=='issuer':e['issuer_name']='Other Company'
                elif change=='code':e['code']='XYZ'
                elif change=='project':e['project_id']='Other'
                elif change=='duplicate':c['codes'].append(copy.deepcopy(e))
                elif change=='path':c['sources']['s']['path']='../source.pdf'
                with self.assertRaises((ValueError,FileNotFoundError)):self.run_config(root,c)
    def test_same_issuer_does_not_authorize_a_merge_of_different_names(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);c=self.fixture(root);other=copy.deepcopy(c['codes'][0]);other['project_id']='Q';c['codes'].append(other)
            c['merges']=[dict(target_id='P',absorbed_id='Q',source_key='s',same_project_evidence=dict(page=1,markers=['Known Project']))]
            with self.assertRaisesRegex(ValueError,'PROJECT_NAME_BINDING|SAME_CODE_AND_NAME'):
                self.run_config(root,c,[{'專案ID':'P','專案名稱':'Known Project'},{'專案ID':'Q','專案名稱':'Different Project'}])
    def test_alias_merge_requires_both_aliases_in_captured_source(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);c=self.fixture(root);other=copy.deepcopy(c['codes'][0]);other['project_id']='Q';c['codes'].append(other)
            c['merges']=[dict(target_id='P',absorbed_id='Q',source_key='s',same_project_evidence=dict(page=1,markers=['Known Project']),alias_pairs=[['Known Project','Invented Alias']])]
            with self.assertRaisesRegex(ValueError,'PROJECT_NAME_BINDING|ALIAS_PROOF'):
                self.run_config(root,c,[{'專案ID':'P','專案名稱':'Known Project'},{'專案ID':'Q','專案名稱':'Invented Alias'}])
    def test_successful_summary_merge_preserves_target_and_does_not_add_resources(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);c=self.fixture(root);other=copy.deepcopy(c['codes'][0]);other['project_id']='Q';c['codes'].append(other)
            c['merges']=[dict(target_id='P',absorbed_id='Q',source_key='s',same_project_evidence=dict(page=1,markers=['Known Project','Known Rare Earth Project']))]
            baseline=root/'baseline';baseline.mkdir()
            columns=json.loads((Path(__file__).resolve().parents[1]/'config/project_summary_columns.json').read_text('utf8'))
            a=dict.fromkeys(columns,'');a.update({'專案ID':'P','專案名稱':'Known Project','礦石蘊藏量_Mt':'10'})
            b=dict.fromkeys(columns,'');b.update({'專案ID':'Q','專案名稱':'Known Rare Earth Project','礦石蘊藏量_Mt':'7','TREO品位_pct':'1'})
            def write(name,rows,fields):
                with (baseline/name).open('w',encoding='utf-8-sig',newline='') as f:
                    w=csv.DictWriter(f,fields);w.writeheader();w.writerows(rows)
            write('專案總表.csv',[a,b],columns)
            fields=['project_id','column','value','source_sha256','source_url','locator','method','scope','observation_ids']
            traces=[dict(project_id=r['專案ID'],column=k,value=v,source_sha256='',source_url='',locator='',method='fixture',scope='',observation_ids='[]') for r in [a,b] for k,v in r.items() if v]
            write('field_provenance.csv',traces,fields)
            write('missing_fields.csv',[dict(project_id=r['專案ID'],column=k,reason='unknown') for r in [a,b] for k,v in r.items() if not v],['project_id','column','reason'])
            write('census_inventory.csv',[dict(entity_id=r['專案ID'],kind='PROJECT',name=r['專案名稱'],included_in_project_summary=True,source_sha256='',unit_of_analysis='fixture') for r in [a,b]],['entity_id','kind','name','included_in_project_summary','source_sha256','unit_of_analysis'])
            (baseline/'summary.json').write_text(json.dumps(dict(version='census-project-summary-v1',cutoff='2026-11-05',output_hashes={p.name:filehash(p) for p in baseline.glob('*.csv')})))
            ledger=root/'identity.json';ledger.write_text(json.dumps(c));out=root/'extended'
            result=extend_summary(baseline,out,ledger,{'asset':root})
            with (out/'專案總表.csv').open(encoding='utf-8-sig') as f:rows=list(csv.DictReader(f))
            self.assertEqual((1,53),(len(rows),len(rows[0])));self.assertEqual('10',rows[0]['礦石蘊藏量_Mt'])
            self.assertEqual('',rows[0]['TREO品位_pct']);self.assertEqual('ABC',rows[0][ASX_COLUMN])
            self.assertEqual(0,result['identity_merges'][0]['numerical_fields_copied']);self.assertIn('礦石蘊藏量_Mt',result['identity_merges'][0]['conflicts'])
            self.assertEqual(2,len(list(csv.DictReader((out/'census_inventory.csv').open(encoding='utf-8-sig')))))


class BulkOxidePercentAndContainedKg(unittest.TestCase):
    def fixture(self,root):
        d=pymupdf.open();p=d.new_page();p.insert_text((30,30),'ASX Announcement\n16 January 2025\nKnown Project',fontsize=10)
        p=d.new_page()
        for x,y,text in [(30,40,'Mineral Resource'),(30,60,'Global Measured Indicated Inferred Total'),(95,85,'Tonnes'),(195,85,'TREO'),(295,85,'Y2O3'),(405,85,'Contained TREO'),(95,100,'Mt'),(195,100,'%'),(295,100,'%'),(405,100,'kg'),(30,120,'Total'),(95,120,'10'),(195,120,'0.2'),(295,120,'0.11'),(405,120,'20,000,000')]:p.insert_text((x,y),text,fontsize=8)
        path=root/'source.pdf';d.save(path);d.close();sha=filehash(path)
        r=dict(review_id='R',source_key='s',project_id='P',source_sha256=sha,asset_set='asset',path='source.pdf',url='https://issuer.example/source.pdf',publication_date='2025-01-16',effective_date='2025-01-16',effective_date_role='RESOURCE_REAFFIRMED_AT_PUBLICATION',date_precision='DAY',identity_evidence=dict(page=1,markers=['Known Project']),date_evidence=dict(page=1,markers=['16 January 2025']),scope='Global resource',statement_id='global',selection_reason='Explicit total',scope_evidence=[dict(page=2,markers=['Mineral Resource','Global Measured Indicated Inferred Total'])],observations=[])
        with pymupdf.open(path) as d:
            p=d[1]
            def box(text,x,y):
                rs=[h for h in p.search_for(text) if x[0]<=h.x0<=x[1] and y[0]<=h.y0<=y[1]]
                return list(rs[0])
            table=[20,25,540,135];anchor=box('Global Measured Indicated Inferred Total',(20,40),(45,65))
            r['selected_resource_sections']={'global':dict(page=2,bbox=table,anchor='Global Measured Indicated Inferred Total',anchor_bbox=anchor)}
            for field,value,unit,original,token,x,label,basis in [('ore_mt',10,'Mt','Mt','10',95,'Tonnes','TREO'),('grade',.2,'%','%','0.2',195,'TREO','TREO'),('reported_resource_y_ppm',1100,'ppm','%','0.11',295,'Y2O3','Y2O3'),('contained_treo_kt',20,'kt TREO','kg','20,000,000',405,'Contained TREO','TREO')]:
                b=dict(mode='native_cell',field=field,basis=basis,scope=r['scope'],page=2,original_unit=original,table_bbox=table,table_label='Mineral Resource',table_label_bbox=box('Mineral Resource',(20,40),(25,45)),scope_anchor='Global Measured Indicated Inferred Total',scope_anchor_bbox=anchor,row_bbox=[20,109,540,125],row_label='Total',row_label_bbox=box('Total',(20,40),(105,125)),column_bbox=[x-4,25,x+(125 if x==405 else 60),135],column_label=label,column_label_bbox=box(label,(x-2,x+2),(70,87)),unit_bbox=box(original,(x-2,x+2),(87,102)),section_id='global')
                r['observations'].append(dict(variable=field,value=value,unit=unit,basis=basis,original_token=token,original_unit=original,cell_binding=b,evidence=dict(page=2,markers=['Mineral Resource'])))
        (root/'downloads.json').write_text(json.dumps([dict(url=r['url'],document_sha256=sha,status='PDF_ACQUIRED')]))
        return r
    def run_review(self,root,r):
        path=root/'reviews.json';path.write_text(json.dumps(dict(version='asx-source-review-v2',acquired_through='2026-11-10',reviews=[r])))
        return validate_reviews(path,{'asset':root},[dict(entity_id='P',name='Known Project',aliases=[])])
    def test_bulk_percent_and_kg_convert_to_ppm_and_kt(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);r=self.run_review(root,self.fixture(root));obs={o['variable']:o for o in r['observations']['P']}
            self.assertEqual(1100,obs['reported_resource_y_ppm']['value']);self.assertEqual(20,obs['contained_treo_kt']['value'])
            self.assertEqual('RESOURCE_ORE_GRADE_OXIDE_PPM',json.loads(obs['reported_resource_y_ppm']['raw'])['material_basis'])
    def test_incorrect_percent_or_kg_conversion_cannot_pass(self):
        for field in ['reported_resource_y_ppm','contained_treo_kt']:
            with self.subTest(field=field),tempfile.TemporaryDirectory() as t:
                root=Path(t);r=self.fixture(root);next(o for o in r['observations'] if o['variable']==field)['value']*=10
                with self.assertRaisesRegex(ValueError,'TOKEN_UNIT_TRANSFORM'):self.run_review(root,r)
    def test_hm_and_treo_product_proportions_cannot_be_bulk_percent(self):
        for unit in ['%HM','%TREO']:
            with self.subTest(unit=unit),tempfile.TemporaryDirectory() as t:
                root=Path(t);r=self.fixture(root);o=r['observations'][2];o['original_unit']=unit;o['cell_binding']['original_unit']=unit
                with self.assertRaises(ValueError):self.run_review(root,r)
    def test_neighbouring_oxide_column_cannot_supply_yttrium(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);r=self.fixture(root);o=r['observations'][2];o['basis']='Dy2O3';o['cell_binding']['basis']='Dy2O3'
            with self.assertRaisesRegex(ValueError,'OXIDE_FIELD_BASIS|OXIDE_HEADER_NOT_ON_PAGE'):self.run_review(root,r)


class ExternalQueueReview(unittest.TestCase):
    def fixture(self,root):
        sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
        from review_external_project_names import review
        source=root/'external.csv'
        source.write_text('Name,Company,Ticker\nKnown input,Wrong Company,ZZZ\nUnsupported Raw Name,Wrong Company,ZZZ\n',encoding='utf8')
        master=root/'master';master.mkdir();(master/'專案總表.csv').write_text('專案ID,專案名稱,ASX代碼\nP,Known Project,ABC\n',encoding='utf8')
        (master/'field_provenance.csv').write_text('project_id,column,source_sha256,source_url\nP,ASX代碼,hash,https://issuer.example/a.pdf\n',encoding='utf8')
        cfg=dict(version='external-name-reviews-v1',input_sha256=filehash(source),input_rows=2,reviews=[
            dict(input_row=2,input_name_sha256=hashlib.sha256(b'Known input').hexdigest(),status='SOURCE_REVIEWED_EXISTING_PROJECT',matched_project_ids=['P'],reason='source proof',source_references=[dict(source_sha256='hash',source_url='https://issuer.example/a.pdf')]),
            dict(input_row=3,input_name_sha256=hashlib.sha256(b'Unsupported Raw Name').hexdigest(),status='UNVERIFIED_EXTERNAL_LEAD',matched_project_ids=[],reason='pending')])
        path=root/'reviews.json'
        def run():
            path.write_text(json.dumps(cfg));return review(source,path,master,root/'out')
        return cfg,run,source
    def test_input_ticker_and_company_never_replace_reviewed_master(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);c,run,_=self.fixture(root);r=run();self.assertEqual(0,r['numeric_values_imported']);self.assertEqual(2,r['queue_reviewed_rows'])
            public=(root/'out/external_name_reviews.csv').read_text('utf-8-sig')
            self.assertIn('ABC',public);self.assertNotIn('ZZZ',public);self.assertNotIn('Wrong Company',public);self.assertNotIn('Unsupported Raw Name',public)
            self.assertIn('Unsupported Raw Name',(root/'out/Gemini_逐項核對.csv').read_text('utf-8-sig'))
    def test_cross_project_or_unverified_source_cannot_be_a_source_reviewed_match(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);c,run,_=self.fixture(root);c['reviews'][0]['source_references'][0]['source_sha256']='other'
            with self.assertRaisesRegex(ValueError,'PROJECT_SOURCE_BINDING'):run()
    def test_unreviewed_input_changes_and_missing_queue_rows_are_rejected(self):
        for change in ['input','queue','project']:
            with self.subTest(change=change),tempfile.TemporaryDirectory() as t:
                root=Path(t);c,run,source=self.fixture(root)
                if change=='input':source.write_text(source.read_text()+'Additional,Company,TST\n')
                elif change=='queue':c['reviews'].pop()
                else:c['reviews'][0]['matched_project_ids']=['invented']
                with self.assertRaises(ValueError):run()
