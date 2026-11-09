import copy,json,re,tempfile,unittest
from pathlib import Path
import pymupdf
from au_ree_v2.asx_validation import validate_reviews,annual_product_derivation
from au_ree_v2.pdf_extract import publication_date
from au_ree_v2.store import filehash

class MonthlyCatalogue(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.pdf=self.root/'source.pdf'
        self.make_pdf(['Official Project Catalogue\nJanuary 2025 edition\nMock Project',
            'Mineral Resources as at Aug-24\nMeasured Indicated Inferred Total\nTonnes Mt TREO ppm\nTotal 10.0 1,000'])
        e=dict(page=2,markers=['Mineral Resources','Total 10.0 1,000'])
        self.review=dict(review_id='month',project_id='P',source_key='catalogue',asset_set='fixture',path='source.pdf',
            url='https://example.gov.au/catalogue.pdf',source_sha256=filehash(self.pdf),source_kind='GOVERNMENT_PROJECT_CATALOGUE',
            publication_date='2025-01-31',publication_date_precision='MONTH',publication_date_interval=['2025-01-01','2025-01-31'],
            publication_month_evidence=dict(page=1,markers=['January 2025 edition']),effective_date='2024-08-31',
            effective_date_role='RESOURCE_EFFECTIVE_DATE',date_precision='MONTH',effective_date_interval=['2024-08-01','2024-08-31'],
            identity_evidence=dict(page=1,markers=['Mock Project']),date_evidence=e,scope='Global',statement_id='one',
            scope_evidence=[e],selection_reason='Explicit total',observations=[
                dict(variable='ore_mt',value=10.,unit='Mt',basis='TREO',original_token='10.0',evidence=e),
                dict(variable='grade',value=1000.,unit='ppm',basis='TREO',original_token='1,000',evidence=e)])
    def make_pdf(self,texts):
        d=pymupdf.open()
        for t in texts:p=d.new_page();p.insert_text((50,50),t,fontsize=10)
        d.save(self.pdf);d.close()
    def validate(self,r=None):
        r=r or self.review
        (self.root/'downloads.json').write_text(json.dumps([dict(url=r['url'],document_sha256=r['source_sha256'],status='PDF_ACQUIRED')]))
        p=self.root/'reviews.json';p.write_text(json.dumps(dict(version='asx-source-review-v1',acquired_through='2026-11-10',reviews=[r])))
        return validate_reviews(p,{'fixture':self.root},[dict(entity_id='P',name='Mock Project',aliases=['Mock Project'])])
    def test_real_edition_and_resource_months_keep_full_intervals(self):
        result=self.validate();s=result['sources'][self.review['source_sha256']]
        self.assertEqual(['2025-01-01','2025-01-31'],s['publication_date_interval'])
        self.assertEqual(['2024-08-01','2024-08-31'],result['receipts'][0]['effective_date_interval'])
    def test_month_is_not_a_fabricated_day(self):
        r=copy.deepcopy(self.review);r['publication_date']='2025-01-16'
        with self.assertRaisesRegex(ValueError,'PUBLICATION_MONTH_INTERVAL'):self.validate(r)
    def test_edition_cannot_be_selected_from_url_month(self):
        r=copy.deepcopy(self.review);r.update(publication_date='2025-02-28',publication_date_interval=['2025-02-01','2025-02-28'])
        with self.assertRaisesRegex(ValueError,'EDITION_MONTH_MISMATCH'):self.validate(r)
    def test_resource_month_requires_interval(self):
        r=copy.deepcopy(self.review);r.pop('effective_date_interval')
        with self.assertRaisesRegex(ValueError,'RESOURCE_MONTH_INTERVAL'):self.validate(r)
    def test_resource_month_cannot_be_moved(self):
        r=copy.deepcopy(self.review);r.update(effective_date='2024-09-30',effective_date_interval=['2024-09-01','2024-09-30'])
        with self.assertRaisesRegex(ValueError,'EFFECTIVE_DATE_NOT_IN_SOURCE'):self.validate(r)
    def test_issuer_url_cannot_claim_government_catalogue(self):
        r=copy.deepcopy(self.review);r['url']='https://issuer.test/catalogue.pdf'
        with self.assertRaisesRegex(ValueError,'GOVERNMENT_CATALOGUE_HOST'):self.validate(r)
    def test_ordinal_header_requires_title_and_date(self):
        self.pdf.unlink();self.make_pdf(['16th January 2025\nMock Project resource',
            'Mineral Resources as at Aug-24\nMeasured Indicated Inferred Total\nTonnes Mt TREO ppm\nTotal 10.0 1,000'])
        r=copy.deepcopy(self.review);r.update(source_sha256=filehash(self.pdf),publication_date='2025-01-16',
            publication_header_evidence=dict(page=1,markers=['16th January 2025'],header_title='Mock Project resource'))
        for k in ['publication_month_evidence','publication_date_interval','publication_date_precision']:r.pop(k)
        self.validate(r)
        r['publication_header_evidence']['header_title']='Different resource'
        with self.assertRaisesRegex(ValueError,'HEADER_TITLE_MISMATCH'):self.validate(r)

class PeriodDates(unittest.TestCase):
    def test_period_end_is_not_publication_date(self):
        for word in ['QUARTER ENDING','YEAR ENDED','PERIOD TO']:
            with self.subTest(word=word):
                self.assertIsNone(publication_date('ASX RELEASE | FOR THE '+word+' 30 JUNE 2025\nQuarterly Report'))
        self.assertEqual('2025-07-31',publication_date('ASX Announcement\n31 July 2025\nQuarter ending 30 June 2025'))

class AnnualConversions(unittest.TestCase):
    def setUp(self):
        self.page='Annual Forecast REEC Production (t) TREO (%) As a % of TREO Pr6O11 Nd2O3\n2025 REEC Product 7,100 60.6 3.9 13.9'
        e=dict(page=3,markers=['2025 REEC Product'],table_row='2025 REEC Product',render_sha256='a'*64)
        self.d=dict(method='ANNUAL_PRODUCT_MASS_X_TREO_FRACTION_X_NDPR_SHARE',inputs=[
            dict(name=n,value=v,original_token=t,unit=u,evidence=copy.deepcopy(e)) for n,v,t,u in
            [('annual_product_t',7100,'7,100','t/year'),('treo_percent',60.6,'60.6','%'),
             ('nd_percent_of_treo',13.9,'13.9','%TREO'),('pr_percent_of_treo',3.9,'3.9','%TREO')]])
    def evidence(self,e):
        self.assertTrue(all(m.lower() in self.page.lower() for m in e['markers']))
        return re.sub(r'\s+',' ',self.page).lower()
    def run_value(self,d=None,value=765.8628):return annual_product_derivation(d or self.d,value,3,self.evidence)
    def test_contained_mass_uses_grade_and_oxide_fraction(self):
        self.assertAlmostEqual(765.8628,self.run_value())
        d=copy.deepcopy(self.d);d['method']='ANNUAL_PRODUCT_MASS_X_TREO_FRACTION';d['inputs']=d['inputs'][:2]
        self.assertAlmostEqual(4302.6,self.run_value(d,4302.6))
    def test_concentrate_mass_cannot_be_treo(self):
        with self.assertRaisesRegex(ValueError,'RESULT_MISMATCH'):self.run_value(value=7100)
    def test_wrong_percent_denominator_fails(self):
        d=copy.deepcopy(self.d);d['inputs'][2]['unit']='%'
        with self.assertRaisesRegex(ValueError,'UNIT_OR_RANGE'):self.run_value(d)
    def test_missing_pr_and_wrong_source_table_fail(self):
        d=copy.deepcopy(self.d);d['inputs'].pop()
        with self.assertRaisesRegex(ValueError,'INPUT_CONTRACT'):self.run_value(d)
        d=copy.deepcopy(self.d);d['inputs'][0]['evidence']['page']=4
        with self.assertRaisesRegex(ValueError,'SAME_TABLE'):self.run_value(d)
    def test_wrong_token_and_nonannual_basis_fail(self):
        d=copy.deepcopy(self.d);d['inputs'][0]['value']=7200
        with self.assertRaisesRegex(ValueError,'TOKEN_MISMATCH'):self.run_value(d)
        self.page=self.page.replace('Annual Forecast','Total Forecast')
        with self.assertRaisesRegex(ValueError,'BASIS_MISSING'):self.run_value()
    def test_unreviewed_or_mismatched_rows_fail(self):
        d=copy.deepcopy(self.d);d['inputs'][0]['evidence'].pop('render_sha256')
        with self.assertRaisesRegex(ValueError,'RENDERED_ROW_REQUIRED'):self.run_value(d)
        self.page+=' 2023 REEC Product'
        d=copy.deepcopy(self.d);d['inputs'][0]['evidence']['table_row']='2023 REEC Product'
        with self.assertRaisesRegex(ValueError,'ROW_CONFLICT'):self.run_value(d)

class ExplicitArchiveSearch(unittest.TestCase):
    def test_denial_and_empty_pages_are_distinct_and_resume_checks_hash(self):
        from tools.discover_asx_archives import discover
        with tempfile.TemporaryDirectory() as t:
            def fetch(url,**kwargs):return (b'<h1>Request Rejected</h1>' if '2023' in url else b'<h1>Archive</h1>'),{}
            r=discover(['FUN'],[2023,2024],t,fetch)
            self.assertEqual(['UNAVAILABLE','PARSED'],[x['status'] for x in r['receipts']])
            def no_fetch(*a,**k):raise AssertionError('resume must reuse receipts')
            self.assertEqual(r,discover(['FUN'],[2023,2024],t,no_fetch))
            p=Path(t)/'data/snapshots'/(r['receipts'][0]['sha256']+'.html');p.write_text('tampered')
            with self.assertRaisesRegex(ValueError,'ARCHIVE_HASH_MISMATCH'):discover(['FUN'],[2023,2024],t,no_fetch)
    def test_only_explicit_dated_asx_links_before_cutoff_are_selected(self):
        from tools.discover_asx_archives import discover
        with tempfile.TemporaryDirectory() as t:
            url='https://www.asx.com.au/asx/v2/statistics/displayAnnouncement.do?display=pdf&idsId=123'
            html='<table><tr><td>01/01/2025</td><td><a href="'+url+'">Ordinary resource title</a></td></tr></table>'
            r=discover(['FUN'],[2025],t,lambda *a,**k:(html.encode(),{}))
            self.assertEqual([url],[d['url'] for d in r['documents']])
            self.assertEqual('FUN',r['documents'][0]['issuer_code_context'])
            self.assertNotIn('project_id',r['documents'][0])

class SearchEvidenceBinding(unittest.TestCase):
    def test_gap_reason_requires_captured_url_hash_and_real_page_markers(self):
        from tools.audit_asx_gap_sources import audit
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);pdf=root/'source.pdf';doc=pymupdf.open();p=doc.new_page();p.insert_text((50,50),'Mock Project resource discrepancy');doc.save(pdf);doc.close()
            source=dict(asset_set='fixture',path='source.pdf',url='https://issuer.test/original.pdf',sha256=filehash(pdf),evidence=[dict(page=1,markers=['resource discrepancy'])])
            (root/'downloads.json').write_text(json.dumps([dict(url=source['url'],document_sha256=source['sha256'],status='PDF_ACQUIRED')]))
            cfg=dict(reviews=[dict(review_id='audit',project_id='P',priority='RESOURCE',decision='WITHHELD',reason='CONFLICT',sources=[source])]);config=root/'config.json'
            config.write_text(json.dumps(cfg));result=audit(config,{'fixture':root},root/'out');self.assertTrue(result['all_bindings_verified'])
            source['url']='https://issuer.test/not-captured.pdf';config.write_text(json.dumps(cfg))
            with self.assertRaisesRegex(ValueError,'RECEIPT_BINDING'):audit(config,{'fixture':root},root/'out')
            source['url']='https://issuer.test/original.pdf';source['evidence'][0]['markers']=['imagined corrected resource'];config.write_text(json.dumps(cfg))
            with self.assertRaisesRegex(ValueError,'MARKER_MISMATCH'):audit(config,{'fixture':root},root/'out')

if __name__=='__main__':unittest.main()
