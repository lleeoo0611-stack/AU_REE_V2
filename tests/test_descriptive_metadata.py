import copy
import unittest
import pymupdf
from au_ree_v2.reviewed_metadata import validate_descriptive_attribute
from au_ree_v2.asx_validation import catalogue_month_proof


class DescriptiveMetadata(unittest.TestCase):
    def fixture(self):
        doc = pymupdf.open()
        self.addCleanup(doc.close)
        page = doc.new_page()
        page.insert_text((40, 40), 'Known Project', fontsize=10)
        page.insert_text((40, 70), 'Known Project has clay-hosted mineralisation.', fontsize=10)
        page.insert_text((40, 100), 'Other Project has carbonatite mineralisation.', fontsize=10)
        def box(token):
            b = page.search_for(token)[0]
            return [b.x0-.2, b.y0-.2, b.x1+.2, b.y1+.2]
        a = dict(column='礦床型態', value='clay-hosted', evidence=dict(page=1, markers=['clay-hosted']),
                 description_binding=dict(page=1, project_marker='Known Project', project_bbox=box('Known Project'),
                    value_bbox=box('Known Project has clay-hosted mineralisation.'),
                    statement='Known Project has clay-hosted mineralisation.', literal_value='clay-hosted'))
        def evidence(item):
            text = page.get_text().casefold()
            if not item['markers'] or any(m.casefold() not in text for m in item['markers']):
                raise ValueError('MARKER')
            return ' '.join(text.split())
        return doc, a, ['Known Project'], evidence, dict(publication_date='2026-02-28')

    def test_literal_project_description(self):
        self.assertIn('SOURCE_BOUND', validate_descriptive_attribute(*self.fixture()))

    def test_issuer_qualified_alias_requires_source_listing_and_ownership(self):
        args=list(self.fixture());doc,a,_,_,_=args;page=doc[0]
        page.insert_text((40,140),'Example Metals Limited (ASX: EXM)',fontsize=10)
        statement='Example Metals 100% owned Known Project'
        page.insert_text((40,170),statement,fontsize=10)
        b=page.search_for(statement)[0]
        proof=dict(exchange='ASX',ticker='EXM',issuer='Example Metals Limited',issuer_alias='Example Metals',
            project_marker='Known Project',listing_evidence=dict(page=1,markers=['Example Metals Limited','ASX: EXM']),
            ownership_evidence=dict(page=1,markers=['Known Project','100% owned']),
            ownership_bbox=[b.x0-.1,b.y0-.1,b.x1+.1,b.y1+.1],ownership_statement=statement)
        a['description_binding']['qualified_alias_proof']=proof;args[2]=['EXM Known Project']
        self.assertIn('SOURCE_BOUND',validate_descriptive_attribute(*args))
        for change in ['wrong_code','wrong_alias','wrong_ownership']:
            changed=copy.deepcopy(a);trial=list(args);trial[1]=changed
            if change=='wrong_code':changed['description_binding']['qualified_alias_proof']['ticker']='OTH'
            if change=='wrong_alias':trial[2]=['OTH Known Project']
            if change=='wrong_ownership':changed['description_binding']['qualified_alias_proof']['ownership_statement']=statement.replace('100%','1%')
            with self.subTest(change=change),self.assertRaises(ValueError):validate_descriptive_attribute(*trial)

    def test_ownership_region_digest_preserves_checks_without_publishing_full_text(self):
        import hashlib
        from au_ree_v2.reviewed_metadata import validate_listing_proof
        doc,a,aliases,evidence,review=self.fixture();page=doc[0]
        page.insert_text((40,140),'Example Metals Limited (ASX: EXM)',fontsize=10)
        statement='Example Metals 100% owned Known Project';page.insert_text((40,170),statement,fontsize=10)
        b=page.search_for(statement)[0]
        proof=dict(exchange='ASX',ticker='EXM',issuer='Example Metals Limited',issuer_alias='Example Metals',
            project_marker='Known Project',listing_evidence=dict(page=1,markers=['Example Metals Limited','ASX: EXM']),
            ownership_evidence=dict(page=1,markers=['Known Project','100% owned']),
            ownership_bbox=[b.x0-.1,b.y0-.1,b.x1+.1,b.y1+.1],
            ownership_statement_sha256=hashlib.sha256(statement.casefold().encode()).hexdigest())
        self.assertIn('SOURCE_BOUND',validate_listing_proof(doc,proof,evidence))
        for change in [dict(ownership_statement_sha256='0'*64),dict(ownership_statement=statement),dict(ownership_bbox=[39,160,50,175])]:
            with self.subTest(change=change),self.assertRaises(ValueError):validate_listing_proof(doc,dict(proof,**change),evidence)

    def test_exact_native_asx_code_and_share_listing_labels(self):
        import hashlib
        from au_ree_v2.reviewed_metadata import validate_listing_proof
        for label in ['ASX Code: EXM','ASX code Example Metals Limited is listed on the Australian Securities Exchange (Shares: EXM,']:
            with self.subTest(label=label):
                doc,a,aliases,evidence,review=self.fixture();page=doc[0]
                page.insert_textbox(pymupdf.Rect(40,130,560,190),'Example Metals Limited '+label,fontsize=8)
                statement='Example Metals 100% owned Known Project';page.insert_text((40,220),statement,fontsize=10)
                b=page.search_for(statement)[0]
                proof=dict(exchange='ASX',ticker='EXM',issuer='Example Metals Limited',issuer_alias='Example Metals',project_marker='Known Project',listing_evidence=dict(page=1,markers=['Example Metals Limited']),ownership_evidence=dict(page=1,markers=['100% owned']),ownership_bbox=[b.x0-.1,b.y0-.1,b.x1+.1,b.y1+.1],ownership_statement_sha256=hashlib.sha256(statement.casefold().encode()).hexdigest(),code_label=label)
                self.assertIn('SOURCE_BOUND',validate_listing_proof(doc,proof,evidence))
                for change in [dict(ticker='OTH'),dict(issuer='Other Metals Limited'),dict(ownership_statement_sha256='0'*64)]:
                    with self.subTest(change=change),self.assertRaises(ValueError):validate_listing_proof(doc,dict(proof,**change),evidence)
    def test_wrong_alias_statement_region_value_and_column_fail_closed(self):
        for key, value in [('project_marker', 'Other Project'), ('statement', 'Known Project has carbonatite mineralisation.'),
                           ('value_bbox', [-1, 0, 100, 100]), ('literal_value', 'carbonatite')]:
            with self.subTest(key=key):
                args = list(self.fixture())
                args[1]['description_binding'][key] = value
                with self.assertRaisesRegex(ValueError, 'REVIEW_DESCRIPTION_'):
                    validate_descriptive_attribute(*args)
        args = list(self.fixture()); args[1]['column'] = '礦石蘊藏量_Mt'
        with self.assertRaisesRegex(ValueError, 'COLUMN'):
            validate_descriptive_attribute(*args)

    def test_stage_must_keep_disclosure_date(self):
        args = list(self.fixture()); args[1]['column'] = '開發階段'
        with self.assertRaisesRegex(ValueError, 'VALUE_OR_DATE'):
            validate_descriptive_attribute(*args)

    def test_unlisted_requires_explicit_government_company_project_panel(self):
        args = list(self.fixture()); args[1].update(column='未上市公司', value='是')
        with self.assertRaisesRegex(ValueError, 'UNLISTED'):
            validate_descriptive_attribute(*args)

    def test_different_page_rejected(self):
        args = list(self.fixture()); args[1]['description_binding']['page'] = 2
        with self.assertRaisesRegex(ValueError, 'PAGE'):
            validate_descriptive_attribute(*args)

    def test_published_abbreviated_month_is_distinct_from_as_at_month(self):
        doc = pymupdf.open(); self.addCleanup(doc.close)
        doc.new_page().insert_text((40, 40), 'All data extracted as at January 2026. Published Feb2026')
        catalogue_month_proof(doc, '2026-02-28', 'published feb2026', 'PUBLISHER_ABBREVIATED_MONTH')
        for day, text in [('2026-01-31', 'published feb2026'), ('2026-02-28', 'data as at feb2026')]:
            with self.subTest(day=day), self.assertRaisesRegex(ValueError, 'LABEL_MONTH_MISMATCH'):
                catalogue_month_proof(doc, day, text, 'PUBLISHER_ABBREVIATED_MONTH')
