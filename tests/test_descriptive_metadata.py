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
        return doc, a, ['Known Project'], evidence, dict(publication_date='2026-02-28')

    def test_literal_project_description(self):
        self.assertIn('SOURCE_BOUND', validate_descriptive_attribute(*self.fixture()))

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
