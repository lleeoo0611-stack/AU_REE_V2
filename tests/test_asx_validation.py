import copy,csv,hashlib,json,tempfile,unittest
from pathlib import Path
import pymupdf
from au_ree_v2.asx_validation import validate_reviews,compare_summaries
from au_ree_v2.pdf_extract import publication_date
from au_ree_v2.store import filehash


class SourceReviews(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        (self.root/'data').mkdir();self.pdf=self.root/'data/source.pdf'
        doc=pymupdf.open()
        for text in ['ASX Announcement\n16 January 2025\nMock Project\nIssuer (ASX: TST) 100%-owned Mock Project',
                     'Mineral Resource as at 15 January 2025\nGlobal Measured Indicated Inferred Total\nTonnes Mt TREO ppm\nTotal 10.0 1,000',
                     'PFS forecast\nAverage annual TREO production 100 tpa\nMineral concentrate']:
            page=doc.new_page();page.insert_text((50,50),text,fontsize=10)
        doc.save(self.pdf);doc.close()
        e=dict(page=2,markers=['Mineral Resource','Total 10.0 1,000'])
        self.review=dict(review_id='fixture',source_key='fixture',project_id='P',source_sha256=filehash(self.pdf),asset_set='fixture',
            path='data/source.pdf',url='https://announcements.asx.com.au/asxpdf/20250116/pdf/test.pdf',publication_date='2025-01-16',
            effective_date='2025-01-15',effective_date_role='RESOURCE_EFFECTIVE_DATE',date_precision='DAY',
            identity_evidence=dict(page=1,markers=['Mock Project']),date_evidence=dict(page=2,markers=['15 January 2025']),
            scope_evidence=[dict(page=2,markers=['Global Measured Indicated Inferred'])],scope='Global resource, not reserve',statement_id='fixture-statement',
            selection_reason='Explicit reviewed global total',observations=[
                dict(variable='ore_mt',value=10.,unit='Mt',basis='TREO',original_token='10.0',evidence=e),
                dict(variable='grade',value=1000.,unit='ppm',basis='TREO',original_token='1,000',evidence=e)])
        self.projects=[dict(entity_id='P',name='Mock Project',aliases=['Mock Project'])]
    def validate(self,review=None):
        # A test receipt independently binds the URL to the originally captured
        # fixture PDF; changing a review URL cannot rewrite this evidence.
        receipt=self.root/'downloads.json'
        if not receipt.exists():receipt.write_text(json.dumps([dict(url=self.review['url'],document_sha256=self.review['source_sha256'],status='PDF_ACQUIRED')]))
        path=self.root/'reviews.json';path.write_text(json.dumps(dict(version='asx-source-review-v1',acquired_through='2026-11-09',reviews=[review or self.review])))
        return validate_reviews(path,{'fixture':self.root},self.projects)
    def test_complete_source_bound_resource_passes(self):
        result=self.validate();self.assertEqual(2,len(result['observations']['P']))
        self.assertEqual('VALIDATED',result['receipts'][0]['status'])
    def test_file_tampering_fails(self):
        with self.pdf.open('ab') as f:f.write(b'tamper')
        with self.assertRaisesRegex(ValueError,'SOURCE_HASH_MISMATCH'):self.validate()
    def test_foreign_project_fails(self):
        r=copy.deepcopy(self.review);r['project_id']='UNREGISTERED'
        with self.assertRaisesRegex(ValueError,'PROJECT_NOT_IN_CENSUS'):self.validate(r)
    def test_peer_project_identity_fails(self):
        self.projects[0]['aliases']=['Another Project'];self.projects[0]['name']='Another Project'
        with self.assertRaisesRegex(ValueError,'PROJECT_NAME_NOT_IN_IDENTITY'):self.validate()
    def test_effective_date_cannot_be_borrowed_from_release(self):
        r=copy.deepcopy(self.review);r['effective_date']='2025-01-16'
        with self.assertRaisesRegex(ValueError,'EFFECTIVE_DATE_NOT_IN_SOURCE'):self.validate(r)
    def test_future_effective_date_fails(self):
        r=copy.deepcopy(self.review);r['effective_date']='2026-01-01'
        with self.assertRaisesRegex(ValueError,'DATE_OUTSIDE'):self.validate(r)
    def test_publication_date_mismatch_fails(self):
        r=copy.deepcopy(self.review);r['publication_date']='2025-01-17'
        with self.assertRaisesRegex(ValueError,'PUBLICATION_DATE_MISMATCH'):self.validate(r)
    def test_wrong_unit_conversion_fails(self):
        r=copy.deepcopy(self.review);r['observations'][0]['original_unit']='kt'
        with self.assertRaisesRegex(ValueError,'TOKEN_UNIT_TRANSFORM'):self.validate(r)
    def test_value_cannot_disagree_with_original_token(self):
        r=copy.deepcopy(self.review);r['observations'][0]['value']=20.
        with self.assertRaisesRegex(ValueError,'TOKEN_UNIT_TRANSFORM'):self.validate(r)
    def test_source_marker_cannot_be_invented(self):
        r=copy.deepcopy(self.review);r['observations'][0]['evidence']['markers'].append('Global Reserve')
        with self.assertRaisesRegex(ValueError,'PAGE_MARKER_MISMATCH'):self.validate(r)
    def test_render_binding_is_verified(self):
        r=copy.deepcopy(self.review)
        with pymupdf.open(self.pdf) as d:sha=hashlib.sha256(d[1].get_pixmap(matrix=pymupdf.Matrix(2,2)).tobytes('png')).hexdigest()
        r['observations'][0]['evidence']['render_sha256']=sha;self.validate(r)
        r['observations'][0]['evidence']['render_sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'RENDER_BINDING'):self.validate(r)
    def test_annual_forecast_needs_explicit_time_basis(self):
        r=copy.deepcopy(self.review);r['study']=dict(scale='PFS_MODEL',stage=3,endpoint='MINERAL_CONCENTRATE',element='TREO_INCLUDING_Y',
            parameters=dict(average_annual_treo_product_t=100),evidence=[dict(page=3,markers=['Average annual TREO production'])])
        with self.assertRaisesRegex(ValueError,'ANNUAL_TIME_BASIS_REQUIRED'):self.validate(r)
        r['study']['annual_basis_evidence']=dict(page=3,markers=['Average annual','tpa'])
        result=self.validate(r);self.assertEqual(100,json.loads(result['studies']['P'][0]['raw'])['parameters']['average_annual_treo_product_t'])
    def test_bench_is_not_annual_production(self):
        r=copy.deepcopy(self.review);r['study']=dict(scale='BENCH',parameters={},evidence=[])
        with self.assertRaisesRegex(ValueError,'STUDY_SCALE_NOT_FORECAST'):self.validate(r)
    def test_minor_resource_date_precision_is_not_fabricated(self):
        r=copy.deepcopy(self.review);r.update(effective_date='2025-01-16',effective_date_role='RESOURCE_REAFFIRMED_AT_PUBLICATION',date_precision='MONTH',effective_date_interval=['2025-01-01','2025-01-16'])
        result=self.validate(r);self.assertEqual('MONTH',result['receipts'][0]['date_precision'])
    def test_resource_scope_proof_is_required(self):
        r=copy.deepcopy(self.review);r['scope_evidence']=[]
        with self.assertRaisesRegex(ValueError,'RESOURCE_SCOPE_EVIDENCE_REQUIRED'):self.validate(r)
    def test_oxide_sum_conflict_is_not_promoted(self):
        from au_ree_v2.project_summary import ELEMENTS
        with pymupdf.open(self.pdf) as d:
            d[1].insert_text((50,180),' '.join(ELEMENTS),fontsize=6)
            target=self.root/'data/with-headers.pdf';d.save(target)
        r=copy.deepcopy(self.review);r.update(path='data/with-headers.pdf',source_sha256=filehash(target),oxide_sum_tolerance_ppm=8)
        (self.root/'downloads.json').write_text(json.dumps([dict(url=r['url'],document_sha256=r['source_sha256'],status='PDF_ACQUIRED')]))
        for oxide in ELEMENTS:r['observations'].append(dict(variable='reported_resource_'+oxide+'_ppm',value=1000,unit='ppm',basis=oxide,
            original_token='1,000',evidence=dict(page=2,markers=['Mineral Resource','Total 10.0 1,000'])))
        with self.assertRaisesRegex(ValueError,'OXIDE_SUM_CONFLICT'):self.validate(r)
    def test_review_url_must_match_the_actual_download_receipt(self):
        r=copy.deepcopy(self.review);r['url']='https://announcements.asx.com.au/asxpdf/20250116/pdf/other.pdf'
        with self.assertRaisesRegex(ValueError,'DOWNLOAD_RECEIPT_BINDING'):self.validate(r)
    def test_deferred_quantity_stays_a_gap_with_source_evidence(self):
        r=copy.deepcopy(self.review);r['deferred_fields']=[dict(column='預估年產重稀土_t_per_year',
            reason='HREE8_NOT_FULLY_SPECIFIED',evidence=dict(page=3,markers=['Average annual TREO production']))]
        result=self.validate(r)
        self.assertEqual('HREE8_NOT_FULLY_SPECIFIED',result['deferred_fields']['P']['預估年產重稀土_t_per_year']['reason'])
        self.assertFalse(result['studies'])


class DateHeaders(unittest.TestCase):
    def test_split_header_and_exchange_code(self):
        self.assertEqual('2025-01-16',publication_date('ASX Announcement\n16 January 2025\nBody'))
        self.assertEqual('2026-10-20',publication_date('ASX Announcement\n20 October 2026 | ASX: CRI\nBody'))
    def test_reference_body_is_not_a_header(self):
        self.assertIsNone(publication_date('Quarterly activities\nRefer to ASX Announcement\n20 October 2026\nfor earlier results'))


class IncrementAccounting(unittest.TestCase):
    def test_zero_fill_is_counted_but_number_format_is_not_new_data(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);before=root/'before';after=root/'after';before.mkdir();after.mkdir()
            for path,values in [(before,['P','Project','10.0','']),(after,['P','Project','10','0'])]:
                with (path/'專案總表.csv').open('w',encoding='utf-8-sig',newline='') as f:
                    w=csv.writer(f);w.writerow(['專案ID','專案名稱','A','B']);w.writerow(values)
            (after/'field_provenance.csv').write_text('project_id,column\nP,B\n')
            result=compare_summaries(before,after,root/'comparison')
            self.assertEqual(1,result['newly_filled_cells']);self.assertEqual(1,result['numeric_format_only_cells'])
            self.assertEqual(0,result['updated_value_cells'])


if __name__=='__main__':unittest.main()
