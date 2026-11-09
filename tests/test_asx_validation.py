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
            page=doc.new_page()
            if text.startswith('Mineral Resource'):
                for xy,t in [((50,50),'Mineral Resource as at 15 January 2025'),((50,65),'Global Measured Indicated Inferred Total'),
                             ((100,90),'Tonnes'),((200,90),'TREO'),((100,105),'Mt'),((200,105),'ppm'),
                             ((50,125),'Total'),((100,125),'10.0'),((200,125),'1,000')]:page.insert_text(xy,t,fontsize=10)
            elif text.startswith('PFS forecast'):
                for xy,t in [((50,50),'PFS forecast'),((300,75),'Base Case'),((50,100),'Average annual TREO production'),
                             ((250,100),'tpa'),((300,100),'100'),((400,75),'Design Basis'),((400,100),'200'),((50,130),'Mineral concentrate')]:page.insert_text(xy,t,fontsize=10)
            else:page.insert_text((50,50),text,fontsize=10)
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
        with pymupdf.open(self.pdf) as d:
            def bbox(page,label):
                r=page.search_for(label)[0]
                return [r.x0-.2,r.y0-.2,r.x1+.2,r.y1+.2]
            p=d[1]
            for o,x,label in [(self.review['observations'][0],100,'Tonnes'),(self.review['observations'][1],200,'TREO')]:
                o['cell_binding']=dict(mode='native_cell',field=o['variable'],scope=self.review['scope'],page=2,
                    original_unit=o['unit'],table_bbox=[40,35,280,140],table_label='Mineral Resource as at 15 January 2025',
                    table_label_bbox=bbox(p,'Mineral Resource as at 15 January 2025'),
                    scope_anchor='Global Measured Indicated Inferred Total',scope_anchor_bbox=bbox(p,'Global Measured Indicated Inferred Total'),
                    row_bbox=[40,112,280,130],row_label='Total',row_label_bbox=[49,114,74,129],
                    column_bbox=[x-5,35,x+45,140],column_label=label,column_label_bbox=bbox(p,label),unit_bbox=bbox(p,o['unit']))
            self.review['selected_resource_sections']={'global':dict(mode='native_section',page=2,bbox=[40,52,280,140],anchor='Global Measured Indicated Inferred Total',anchor_bbox=bbox(p,'Global Measured Indicated Inferred Total'))}
            for o in self.review['observations']:o['cell_binding']['section_id']='global'
            p=d[2]
            self.forecast_binding=dict(mode='native_cell',field='average_annual_treo_product_t',scope=self.review['scope'],page=3,
                original_unit='tpa',table_bbox=[40,35,480,120],table_label='PFS forecast',table_label_bbox=bbox(p,'PFS forecast'),
                row_bbox=[40,87,480,105],row_label='Average annual TREO production',row_label_bbox=bbox(p,'Average annual TREO production'),
                column_bbox=[295,35,370,120],column_label='Base Case',column_label_bbox=bbox(p,'Base Case'),unit_bbox=bbox(p,'tpa'))
        self.projects=[dict(entity_id='P',name='Mock Project',aliases=['Mock Project'])]
    def validate(self,review=None):
        # A test receipt independently binds the URL to the originally captured
        # fixture PDF; changing a review URL cannot rewrite this evidence.
        receipt=self.root/'downloads.json'
        if not receipt.exists():receipt.write_text(json.dumps([dict(url=self.review['url'],document_sha256=self.review['source_sha256'],status='PDF_ACQUIRED')]))
        path=self.root/'reviews.json';path.write_text(json.dumps(dict(version='asx-source-review-v2',acquired_through='2026-11-09',reviews=[review or self.review])))
        return validate_reviews(path,{'fixture':self.root},self.projects)
    def test_dated_metadata_role_does_not_claim_resource_effective_date(self):
        r=copy.deepcopy(self.review);r.update(observations=[],effective_date_role='DATED_ISSUER_METADATA',effective_date=r['publication_date'],date_evidence=dict(page=1,markers=['16 January 2025']),attributes=[dict(column='開發商',value='Issuer',evidence=dict(page=1,markers=['Issuer']))])
        result=self.validate(r)
        self.assertEqual('DATED_ISSUER_METADATA',result['receipts'][0]['effective_date_role'])
        self.assertEqual({},result['observations'])
    def test_metadata_role_cannot_admit_resource_observations(self):
        r=copy.deepcopy(self.review);r['effective_date_role']='DATED_ISSUER_METADATA'
        with self.assertRaisesRegex(ValueError,'METADATA_ROLE_REQUIRES_ATTRIBUTES_ONLY'):self.validate(r)

    def test_context_resource_does_not_replace_selected_contract(self):
        self.validate()
        context=copy.deepcopy(self.review);context.update(review_id='context',statement_id='other-scope',resource_selection_role='CONTEXT_ONLY',context_selection_reason='Distinct alternative scope, not additive')
        p=self.root/'reviews.json';ledger=json.loads(p.read_text());ledger['reviews']=[context,self.review];p.write_text(json.dumps(ledger))
        result=validate_reviews(p,{'fixture':self.root},self.projects)
        self.assertEqual('fixture-statement',result['resource_contracts']['P'][2])
        self.assertEqual('CONTEXT_ONLY',result['receipts'][0]['resource_selection_role'])
        self.assertEqual(2,len(result['observations']['P']))
    def test_context_only_cannot_become_fallback_resource(self):
        r=copy.deepcopy(self.review);r.update(resource_selection_role='CONTEXT_ONLY',context_selection_reason='Evidence only')
        result=self.validate(r)
        self.assertEqual({},result['observations']);self.assertEqual({},result['resource_preferences'])
    def test_context_resource_requires_explicit_reason(self):
        r=copy.deepcopy(self.review);r['resource_selection_role']='CONTEXT_ONLY'
        with self.assertRaisesRegex(ValueError,'CONTEXT_SELECTION_REASON'):self.validate(r)
    def test_unknown_selection_role_rejected(self):
        r=copy.deepcopy(self.review);r['resource_selection_role']='IGNORE'
        with self.assertRaisesRegex(ValueError,'SELECTION_ROLE_INVALID'):self.validate(r)

    def parenthesized_grade_review(self, label='(TREO'):
        r=copy.deepcopy(self.review);target=self.root/'data/paren.pdf'
        with pymupdf.open(self.pdf) as d:
            p=d[1];p.add_redact_annot(p.search_for('TREO')[0]);p.apply_redactions()
            p.insert_text((200,90),label,fontsize=10)
            a=p.search_for(label)[0]
            r['observations'][1]['cell_binding'].update(column_label=label,column_label_bbox=[a.x0-.2,a.y0-.2,a.x1+.2,a.y1+.2])
            d.save(target)
        r.update(path='data/paren.pdf',source_sha256=filehash(target))
        (self.root/'downloads.json').write_text(json.dumps([dict(url=r['url'],document_sha256=r['source_sha256'],status='PDF_ACQUIRED')]))
        return r
    def test_parenthesized_treo_header_keeps_exact_anchor(self):
        self.assertEqual('VALIDATED',self.validate(self.parenthesized_grade_review())['receipts'][0]['status'])
    def test_parenthesized_non_treo_header_rejected(self):
        with self.assertRaisesRegex(ValueError,'HEADER_SEMANTICS'):
            self.validate(self.parenthesized_grade_review('(HREO'))

    def treo_proportion_review(self):
        r=copy.deepcopy(self.review)
        target=self.root/'data/proportions.pdf'
        with pymupdf.open(self.pdf) as d:
            p=d[1]
            for term in ['ppm','1,000']:p.add_redact_annot(p.search_for(term)[0])
            p.apply_redactions()
            p.insert_text((200,105),'%',fontsize=10);p.insert_text((200,125),'0.1',fontsize=10)
            p=d.new_page()
            for xy,t in [((50,50),'Table 12'),((50,70),'Percentage Proportion of TREO in the Mineral Resources'),
                         ((200,95),'Measured'),((300,95),'Total'),((50,115),'Nd2O3'),((200,115),'30.0'),((300,115),'20.0'),
                         ((50,135),'Pr6O11'),((200,135),'6.0'),((300,135),'5.0')]:p.insert_text(xy,t,fontsize=10)
            def bbox(term):
                a=p.search_for(term)[0];return [a.x0-.2,a.y0-.2,a.x1+.2,a.y1+.2]
            tb=[40,35,400,145];hb=bbox('Total');ub=bbox('Percentage Proportion of TREO in the Mineral Resources')
            r['selected_resource_sections']['proportions']=dict(page=4,bbox=tb,anchor='Total',anchor_bbox=hb,category_label='Total')
            b=dict(mode='native_cell',resource_orientation='oxide_rows',field='reported_resource_nd_ppm',basis='Nd2O3',scope=r['scope'],page=4,
                original_unit='%TREO',table_bbox=tb,table_label='Table 12',table_label_bbox=bbox('Table 12'),
                row_bbox=[40,103,400,119],row_label='Nd2O3',row_label_bbox=bbox('Nd2O3'),column_bbox=[290,35,340,145],column_label='Total',column_label_bbox=hb,
                unit_bbox=ub,unit_label='Percentage Proportion of TREO in the Mineral Resources',unit_scope_bbox=tb,
                scope_anchor='Total',scope_anchor_bbox=hb,section_id='proportions')
            d.save(target)
        r.update(path='data/proportions.pdf',source_sha256=filehash(target))
        (self.root/'downloads.json').write_text(json.dumps([dict(url=r['url'],document_sha256=r['source_sha256'],status='PDF_ACQUIRED')]))
        for o in r['observations']:o['evidence']=dict(page=2,markers=['Mineral Resource','Total'])
        g=r['observations'][1];g.update(value=.1,original_token='0.1',unit='%');g['cell_binding'].update(original_unit='%',unit_bbox=[199,94,210,108])
        r['bulk_treo_grade_pct']=dict(value=.1,original_token='0.1',evidence=g['evidence'],cell_binding=copy.deepcopy(g['cell_binding']))
        r['observations'].append(dict(variable='reported_resource_nd_ppm',basis='Nd2O3',value=200.,unit='ppm',original_token='20.0',original_unit='%TREO',
                                      evidence=dict(page=4,markers=['Table 12','Nd2O3']),cell_binding=b))
        return r
    def test_transposed_treo_proportion_converts_with_selected_grade(self):
        result=self.validate(self.treo_proportion_review())
        row=next(x for x in result['observations']['P'] if x['variable']=='reported_resource_nd_ppm')
        self.assertEqual(200.,row['value']);self.assertEqual('TREO_PROPORTION_TO_BULK_PPM',json.loads(row['raw'])['basis_transform'])
    def test_treo_proportion_missing_factor_rejected(self):
        r=self.treo_proportion_review();r.pop('bulk_treo_grade_pct')
        with self.assertRaisesRegex(ValueError,'REQUIRES_SELECTED_GRADE'):self.validate(r)
    def test_treo_proportion_wrong_factor_rejected(self):
        r=self.treo_proportion_review();r['bulk_treo_grade_pct'].update(value=.2,original_token='0.2')
        with self.assertRaisesRegex(ValueError,'REQUIRES_SELECTED_RESOURCE_GRADE'):self.validate(r)
    def test_treo_proportion_wrong_conversion_rejected(self):
        r=self.treo_proportion_review();r['observations'][-1]['value']=20.
        with self.assertRaisesRegex(ValueError,'UNIT_TRANSFORM'):self.validate(r)
    def test_treo_proportion_wrong_category_column_rejected(self):
        r=self.treo_proportion_review();r['observations'][-1]['cell_binding']['column_label']='Measured'
        with self.assertRaisesRegex(ValueError,'TOTAL_COLUMN'):self.validate(r)
    def test_treo_proportion_wrong_oxide_row_rejected(self):
        r=self.treo_proportion_review();b=r['observations'][-1]['cell_binding'];b['row_bbox']=[40,123,400,138]
        with self.assertRaisesRegex(ValueError,'ANCHOR_OUTSIDE_REGION'):self.validate(r)
    def test_treo_proportion_over100_rejected(self):
        r=self.treo_proportion_review();r['observations'][-1]['original_token']='150';r['observations'][-1]['evidence']['markers']=['Table 12']
        # Arithmetic guard is tested separately from the page token check.
        with pymupdf.open(self.root/r['path']) as d:
            d[3].insert_text((50,170),'150',fontsize=10);q=self.root/'data/over100.pdf';d.save(q)
        r.update(path='data/over100.pdf',source_sha256=filehash(q));(self.root/'downloads.json').write_text(json.dumps([dict(url=r['url'],document_sha256=r['source_sha256'],status='PDF_ACQUIRED')]))
        with self.assertRaisesRegex(ValueError,'PROPORTION_OUT_OF_RANGE'):self.validate(r)

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
        r['study'].update(selected_scenario='Base Case',parameter_bindings={'average_annual_treo_product_t':self.forecast_binding})
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
        # Isolate the existing aggregate sum check from the new cell-binding layer.
        from unittest.mock import patch
        with patch('au_ree_v2.source_cells.validate_cell',return_value='TEST_AGGREGATE_ONLY'):
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
    def test_inferred_only_resource_does_not_require_other_categories(self):
        r=copy.deepcopy(self.review);r['resource_categories']=['INFERRED']
        result=self.validate(r)
        self.assertEqual('INFERRED_TOTAL',result['observations']['P'][0]['category'])
        r['resource_categories']=['PROVED']
        with self.assertRaisesRegex(ValueError,'CATEGORY_INVALID'):self.validate(r)
    def test_hm_grade_is_normalized_to_bulk_ore(self):
        r=copy.deepcopy(self.review)
        with pymupdf.open(self.pdf) as d:
            d[1].insert_text((50,200),'Total HM 4.0 percent total material\nTREO 1.4 percent total HM component',fontsize=10)
            target=self.root/'data/hm.pdf';d.save(target)
        r.update(path='data/hm.pdf',source_sha256=filehash(target))
        (self.root/'downloads.json').write_text(json.dumps([dict(url=r['url'],document_sha256=r['source_sha256'],status='PDF_ACQUIRED')]))
        r['bulk_hm_percent']=dict(value=4.,original_token='4.0',basis_markers=['Total HM','percent total material','percent total HM component'],evidence=dict(page=2,markers=['Total HM']))
        r['observations'][1].update(value=.056,unit='%',original_token='1.4',original_unit='%HM')
        # This fixture isolates HM arithmetic; real source cell geometry is covered separately.
        from unittest.mock import patch
        with patch('au_ree_v2.source_cells.validate_cell',return_value='TEST_HM_TRANSFORM_ONLY'):
            result=self.validate(r)
        self.assertAlmostEqual(.056,result['observations']['P'][1]['value'])
        r['observations'][1]['value']=1.4
        with patch('au_ree_v2.source_cells.validate_cell',return_value='TEST_HM_TRANSFORM_ONLY'):
            with self.assertRaisesRegex(ValueError,'TOKEN_UNIT_TRANSFORM'):self.validate(r)
        r['observations'][1]['value']=.056;r.pop('bulk_hm_percent')
        with self.assertRaisesRegex(ValueError,'HM_NORMALIZATION'):self.validate(r)
    def test_source_must_be_in_canonical_manifest_when_no_download_receipt(self):
        (self.root/'data/manifest.json').write_text(json.dumps(dict(snapshots=[dict(kind='pdf',url=self.review['url'],sha256=self.review['source_sha256'],path='data/source.pdf')])))
        # Suppress creation of fixture download receipt, then test the manifest path.
        ledger=self.root/'ledger.json';ledger.write_text(json.dumps(dict(version='asx-source-review-v2',acquired_through='2026-11-09',reviews=[self.review])))
        self.assertEqual('VALIDATED',validate_reviews(ledger,{'fixture':self.root},self.projects)['receipts'][0]['status'])
        bad=json.loads((self.root/'data/manifest.json').read_text());bad['snapshots'][0]['url']='https://example.test/other.pdf'
        (self.root/'data/manifest.json').write_text(json.dumps(bad))
        with self.assertRaisesRegex(ValueError,'RECEIPT_BINDING'):validate_reviews(ledger,{'fixture':self.root},self.projects)
    def test_malformed_render_hash_is_rejected_before_rendering(self):
        r=copy.deepcopy(self.review);r['observations'][0]['evidence']['render_sha256']='a'*65
        with self.assertRaisesRegex(ValueError,'INVALID_RENDER_SHA256'):self.validate(r)
    def test_scope_display_label_must_be_present_in_reviewed_source(self):
        r=copy.deepcopy(self.review);r['summary_resource_scope_label']='Another licence'
        with self.assertRaisesRegex(ValueError,'SCOPE_LABEL_NOT_IN_SOURCE'):self.validate(r)
    def test_exact_reviewed_statement_contract_is_retained(self):
        result=self.validate()
        self.assertEqual((self.review['source_sha256'],self.review['scope'],self.review['statement_id'],self.review['effective_date']),result['resource_contracts']['P'])
    def test_prospectus_publication_is_bound_to_archive_not_issue_date(self):
        r=copy.deepcopy(self.review);target=self.root/'data/prospectus.pdf'
        with pymupdf.open(self.pdf) as original:
            d=pymupdf.open();p=d.new_page();p.insert_text((50,50),'PROSPECTUS\nMock Project\nThis document is dated 15 January 2025')
            d.insert_pdf(original,from_page=1);d.save(target);d.close()
        r.update(path='data/prospectus.pdf',source_sha256=filehash(target),document_issue_date='2025-01-15',
            document_issue_evidence=dict(page=1,markers=['This document is dated 15 January 2025']))
        (self.root/'downloads.json').write_text(json.dumps([dict(url=r['url'],document_sha256=r['source_sha256'],status='PDF_ACQUIRED')]))
        html='<table><tr><td>16/01/2025</td><td><a href="'+r['url']+'">Prospectus</a></td></tr></table>'
        index=self.root/'data/archive.html';index.write_text(html)
        r['publication_archive_evidence']=dict(asset_set='fixture',path='data/archive.html',sha256=filehash(index),url='https://www.asx.com.au/archive')
        result=self.validate(r);self.assertEqual('2025-01-15',result['sources'][r['source_sha256']]['document_issue_date'])
        index.write_text(html.replace('16/01/2025','17/01/2025'));r['publication_archive_evidence']['sha256']=filehash(index)
        with self.assertRaisesRegex(ValueError,'ARCHIVE_DATE_BINDING'):self.validate(r)

    def test_unit_label_cannot_change_source_unit_semantics(self):
        r=copy.deepcopy(self.review);b=r['observations'][1]['cell_binding']
        b['unit_label']='ppm';b['original_unit']='%'
        from au_ree_v2.source_cells import validate_cell
        with pymupdf.open(self.pdf) as doc:
            with self.assertRaisesRegex(ValueError,'SOURCE_UNIT_SEMANTICS'):
                validate_cell(doc,b,'grade','1,000','%',r['scope'],selected_sections=r['selected_resource_sections'])
    def test_declared_resource_row_label_cannot_move_to_another_row(self):
        r=copy.deepcopy(self.review);r['selected_resource_sections']['global']['row_label']='Inferred'
        with self.assertRaisesRegex(ValueError,'RESOURCE_TOTAL_ROW'):self.validate(r)
    def test_native_coordinates_survive_page_rotation(self):
        r=copy.deepcopy(self.review)
        with pymupdf.open(self.pdf) as d:
            d[1].set_rotation(90);p=self.root/'data/rotated.pdf';d.save(p)
        r.update(path='data/rotated.pdf',source_sha256=filehash(p))
        (self.root/'downloads.json').write_text(json.dumps([dict(url=r['url'],document_sha256=r['source_sha256'],status='PDF_ACQUIRED')]))
        self.assertEqual(2,len(self.validate(r)['observations']['P']))

    def test_same_page_ore_grade_swap_rejected(self):
        r=copy.deepcopy(self.review)
        r['observations'][0].update(value=1000.,original_token='1,000')
        r['observations'][1].update(value=10.,original_token='10.0')
        with self.assertRaisesRegex(ValueError,'CELL_TOKEN_MISMATCH'):self.validate(r)

    def test_same_page_column_relocation_rejected(self):
        r=copy.deepcopy(self.review);o=r['observations'][0]
        o.update(value=1000.,original_token='1,000')
        o['cell_binding']['column_bbox']=[195,35,245,140]
        with self.assertRaisesRegex(ValueError,'CELL_ANCHOR_OUTSIDE_REGION'):self.validate(r)

    def test_whole_binding_swap_rejected(self):
        r=copy.deepcopy(self.review)
        r['observations'][0]['cell_binding']=r['observations'][1]['cell_binding']
        with self.assertRaisesRegex(ValueError,'CELL_FIELD_OR_SCOPE_MISMATCH'):self.validate(r)

    def test_header_semantics_cannot_be_changed_to_wrong_field(self):
        r=copy.deepcopy(self.review);o=r['observations'][0]
        o.update(value=1000.,original_token='1,000')
        o['cell_binding']=copy.deepcopy(r['observations'][1]['cell_binding'])
        o['cell_binding'].update(field='ore_mt',original_unit='Mt')
        with self.assertRaisesRegex(ValueError,'CELL_ANCHOR_MISMATCH'):self.validate(r)

    def test_page_render_does_not_bypass_missing_cell_binding(self):
        r=copy.deepcopy(self.review)
        with pymupdf.open(self.pdf) as d:sha=hashlib.sha256(d[1].get_pixmap(matrix=pymupdf.Matrix(2,2)).tobytes('png')).hexdigest()
        r['observations'][0]['evidence']['render_sha256']=sha
        del r['observations'][0]['cell_binding']
        with self.assertRaisesRegex(ValueError,'CELL_BINDING_REQUIRED'):self.validate(r)

    def test_forecast_scenario_number_swap_rejected(self):
        r=copy.deepcopy(self.review)
        r['study']=dict(scale='PFS_MODEL',stage=3,endpoint='MINERAL_CONCENTRATE',element='TREO_INCLUDING_Y',
            parameters=dict(average_annual_treo_product_t=200),evidence=[dict(page=3,markers=['Average annual TREO production'])],
            annual_basis_evidence=dict(page=3,markers=['Average annual','tpa']),selected_scenario='Base Case',
            parameter_bindings={'average_annual_treo_product_t':self.forecast_binding})
        with self.assertRaisesRegex(ValueError,'CELL_TOKEN_MISMATCH'):self.validate(r)
        b=copy.deepcopy(self.forecast_binding)
        with pymupdf.open(self.pdf) as d:
            box=d[2].search_for('Design Basis')[0]
        b.update(column_bbox=[395,35,470,120],column_label='Design Basis',column_label_bbox=list(box))
        r['study']['parameter_bindings']['average_annual_treo_product_t']=b
        with self.assertRaisesRegex(ValueError,'CELL_FORECAST_SCENARIO_MISMATCH'):self.validate(r)

    def test_resource_non_total_row_rejected(self):
        r=copy.deepcopy(self.review);r['observations'][0]['cell_binding']['row_label']='Inferred'
        with self.assertRaisesRegex(ValueError,'CELL_RESOURCE_TOTAL_ROW_REQUIRED'):self.validate(r)

    def test_resource_row_cannot_precede_selected_scope(self):
        r=copy.deepcopy(self.review);r['observations'][0]['cell_binding']['row_bbox']=[40,35,280,55]
        with self.assertRaisesRegex(ValueError,'CELL_ROW_OUTSIDE_SELECTED_SECTION'):self.validate(r)

    def test_scope_cannot_be_borrowed_from_other_review(self):
        r=copy.deepcopy(self.review);r['observations'][0]['cell_binding']['scope']='High grade subset'
        with self.assertRaisesRegex(ValueError,'CELL_FIELD_OR_SCOPE_MISMATCH'):self.validate(r)

    def test_wide_multi_value_region_rejected(self):
        r=copy.deepcopy(self.review);r['observations'][0]['cell_binding']['column_bbox']=[40,35,280,140]
        with self.assertRaisesRegex(ValueError,'CELL_AMBIGUOUS_REGION'):self.validate(r)

    def test_image_cell_transcription_is_distinct_assurance(self):
        from au_ree_v2.source_cells import image_crop_hash
        r=copy.deepcopy(self.review);o=r['observations'][0];b=o['cell_binding']
        b.update(mode='reviewed_image_cell',reviewed_token='10.0',review_note='Fixture visual transcript')
        r['selected_resource_sections']['global']['mode']='reviewed_image_section'
        with pymupdf.open(self.pdf) as d:b['cell_render_sha256']=image_crop_hash(d[1],pymupdf.Rect(b['row_bbox'])&pymupdf.Rect(b['column_bbox']))
        result=self.validate(r)
        self.assertIn('NOT_INDEPENDENT_OCR',json.loads(result['observations']['P'][0]['raw'])['review_method'])
        o.update(value=1000.,original_token='1,000')
        with self.assertRaisesRegex(ValueError,'CELL_IMAGE_TRANSCRIPTION_MISMATCH'):self.validate(r)
        o.update(value=10.,original_token='10.0');b['column_bbox']=[195,35,245,140]
        with self.assertRaisesRegex(ValueError,'CELL_IMAGE_CROP_MISMATCH'):self.validate(r)

    def test_native_forecast_statement_binds_contained_not_concentrate_mass(self):
        from au_ree_v2.source_cells import validate_cell
        statement='Anticipated annual concentrate production is 31,570 tpa at 27% TREO grade or 8,524 tpa of contained TREO in concentrate.'
        with pymupdf.open() as d:
            p=d.new_page(width=1000,height=200);p.insert_text((20,50),statement,fontsize=10)
            b=dict(mode='native_statement',field='average_annual_treo_product_t',scope='DFS annual concentrate',page=1,
                   statement_bbox=[10,30,990,60],statement=statement,
                   before=statement.split('8,524')[0],after=statement.split('8,524')[1],original_unit='tpa')
            args=(d,b,'average_annual_treo_product_t')
            self.assertEqual('NATIVE_SCOPED_STATEMENT_BINDING',validate_cell(*args,'8524','tpa',b['scope']))
            with self.assertRaisesRegex(ValueError,'STATEMENT_TOKEN_MISMATCH'):validate_cell(*args,'31570','tpa',b['scope'])
            b.update(before=statement.split('31,570')[0],after=statement.split('31,570')[1])
            with self.assertRaisesRegex(ValueError,'STATEMENT_SEMANTICS_MISMATCH'):validate_cell(*args,'31570','tpa',b['scope'])

    def test_oxide_variable_has_fixed_stoichiometric_basis(self):
        from au_ree_v2.source_cells import validate_cell
        b=copy.deepcopy(self.review['observations'][1]['cell_binding'])
        b.update(field='reported_resource_nd_ppm',basis='Pr6O11')
        with pymupdf.open(self.pdf) as d:
            with self.assertRaisesRegex(ValueError,'CELL_OXIDE_FIELD_BASIS_MISMATCH'):
                validate_cell(d,b,'reported_resource_nd_ppm','1000','ppm',self.review['scope'],selected_sections=self.review['selected_resource_sections'])

    def test_forecast_grade_or_percentage_is_not_annual_mass(self):
        from au_ree_v2.source_cells import validate_cell
        for label in ['Average annual TREO grade','Average annual TREO production']:
            with self.subTest(label=label),pymupdf.open() as d:
                p=d.new_page()
                for xy,t in [((50,50),'PFS forecast'),((300,75),'Base Case'),((50,100),label),((250,100),'%'),((300,100),'27')]:p.insert_text(xy,t,fontsize=10)
                b=copy.deepcopy(self.forecast_binding);b['page']=1;b['row_label']=label;b['original_unit']='%'
                b['row_label_bbox']=list(p.search_for(label)[0]);b['unit_bbox']=list(p.search_for('%')[0])
                with self.assertRaisesRegex(ValueError,'CELL_HEADER_SEMANTICS_MISMATCH'):
                    validate_cell(d,b,b['field'],'27','%',b['scope'],'Base Case')

    def test_forecast_unit_cannot_be_borrowed_from_prior_row(self):
        from au_ree_v2.source_cells import validate_cell
        with pymupdf.open() as d:
            p=d.new_page()
            for xy,t in [((50,50),'PFS forecast'),((300,75),'Base Case'),((250,75),'tpa'),
                         ((50,100),'Average annual TREO production'),((300,100),'100')]:p.insert_text(xy,t,fontsize=10)
            b=copy.deepcopy(self.forecast_binding);b['page']=1
            b['unit_bbox']=list(p.search_for('tpa')[0]);b['unit_bbox'][3]=88
            with self.assertRaisesRegex(ValueError,'CELL_UNIT_OUTSIDE_FORECAST_ROW'):
                validate_cell(d,b,b['field'],'100','tpa',b['scope'],'Base Case')

    def test_alternate_resource_section_not_selected(self):
        r=copy.deepcopy(self.review)
        b=r['observations'][0]['cell_binding'];b['section_id']='high-grade-subset'
        with self.assertRaisesRegex(ValueError,'CELL_SELECTED_SECTION_REQUIRED'):self.validate(r)

    def test_forecast_assurance_is_preserved_in_result(self):
        r=copy.deepcopy(self.review)
        r['study']=dict(scale='PFS_MODEL',stage=3,endpoint='MINERAL_CONCENTRATE',element='TREO_INCLUDING_Y',
            parameters=dict(average_annual_treo_product_t=100),evidence=[dict(page=3,markers=['Average annual TREO production'])],
            annual_basis_evidence=dict(page=3,markers=['Average annual','tpa']),selected_scenario='Base Case',
            parameter_bindings={'average_annual_treo_product_t':self.forecast_binding})
        result=self.validate(r);raw=json.loads(result['studies']['P'][0]['raw'])
        self.assertEqual('NATIVE_TABLE_ROW_COLUMN_CELL_BINDING',raw['parameter_review_methods']['average_annual_treo_product_t'])


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
    def test_withdrawn_values_count_against_net_increase_and_keep_reason(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);before=root/'before';after=root/'after';before.mkdir();after.mkdir()
            for path,values in [(before,['P','Project','1','']),(after,['P','Project','','2'])]:
                with (path/'專案總表.csv').open('w',encoding='utf-8-sig',newline='') as f:
                    w=csv.writer(f);w.writerow(['專案ID','專案名稱','A','B']);w.writerow(values)
            (after/'field_provenance.csv').write_text('project_id,column\nP,B\n')
            (after/'missing_fields.csv').write_text('project_id,column,reason\nP,A,OLDER_SCOPE_NOT_TRANSFERRED\n')
            r=compare_summaries(before,after,root/'comparison');self.assertEqual(1,r['became_unknown_cells']);self.assertEqual(0,r['net_filled_cell_increase'])
            with (root/'comparison/field_changes.csv').open(encoding='utf-8-sig') as f:changes=list(csv.DictReader(f))
            self.assertEqual('OLDER_SCOPE_NOT_TRANSFERRED',next(c for c in changes if c['status']=='BECAME_UNKNOWN')['withdrawal_reason'])


class ArchiveAccounting(unittest.TestCase):
    def test_http200_rejection_is_not_an_empty_archive(self):
        from tools.expand_asx_technical import archive_rejected
        self.assertTrue(archive_rejected(b'<title>Request Rejected</title>'))
        self.assertTrue(archive_rejected(b'<h1>Access Denied</h1>'))
        self.assertFalse(archive_rejected(b'<h2>Search results: Company announcements</h2>'))


if __name__=='__main__':unittest.main()
