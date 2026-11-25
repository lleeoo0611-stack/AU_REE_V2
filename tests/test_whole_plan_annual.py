import unittest
from contextlib import nullcontext
from unittest.mock import Mock, patch

from au_ree_v2.technical import verified_whole_plan_average


def pages(*texts):
    return [Mock(get_text=Mock(return_value=text)) for text in texts]


class WholePlanAnnualTests(unittest.TestCase):
    def setUp(self):
        self.study = {'annual_period_confirmation': {
            'production_table_page': 1, 'schedule_page': 2, 'annual_model_page': 3,
            'confirmation_source_key': 'presentation', 'confirmation_source_sha256': 'sha',
            'study_reference_page': 1, 'annual_table_page': 2}}
        self.sources = {'sha': {'key': 'presentation', 'publication_date': '2026-09-14',
                                'resolved_path': 'presentation.pdf'}}
        self.doc = pages(
            'Table 2: Production by contained oxide. Production target is based entirely on the '
            '47.0 Mt Probable Ore Reserve. Production - Contained Oxide Unit Total High Grade Low Grade '
            'Average LoM Average LoM Average LoM Production - TREO dt 1,156 23,692 1,868 19,155 '
            '221 4,537 Production - TREO Hf',
            'Initial ~10 years mining and processing high-grade ore. Following ~10.5 years stockpile '
            'processing processing of stockpiled ore',
            'Life-of-Mine production schedule provides the basis for annual ore tonnes, head grades, '
            'recovered product and revenue')
        self.presentation = pages(
            'North Stanmore. Maiden Ore Reserve, Updated Mineral Resource And Pre-Feasibility '
            'Study "dated 18th August 2026".',
            'Scheduled Annual Mineral Concentrate Production. Production - Contained Oxide Unit '
            'Initial 10 Years Avera ge LoM Production - TREO dt 1,868 19,155 Production - TREO Hf')

    def verify(self, value=1156, cutoff='2026-11-13'):
        with patch('pymupdf.open', return_value=nullcontext(self.presentation)):
            verified_whole_plan_average(self.doc, self.study, 'average_annual_treo_product_t',
                                        value, self.sources, cutoff)

    def test_accepts_published_total_average_only(self):
        self.verify()
        for wrong_column in (1868, 23692, 221):
            with self.subTest(value=wrong_column), self.assertRaisesRegex(ValueError, 'WHOLE_PLAN_AVERAGE'):
                self.verify(wrong_column)

    def test_requires_both_time_bases_and_matching_schedule(self):
        with self.assertRaisesRegex(ValueError, 'SOURCE_UNAVAILABLE'):
            self.verify(cutoff='2026-09-13')
        for page, text, reason in (
            (self.presentation[1], 'Scheduled Monthly Mineral Concentrate Production', 'CONFIRMATION_TITLE'),
            (self.doc[2], 'Annual cash flow and forecast revenues', 'WHOLE_PLAN'),
            (self.doc[1], '10 years processing followed by idle years', 'OPERATING_SCHEDULE'),
            (self.presentation[1], self.presentation[1].get_text().replace('1,868', '1,867'),
             'STUDY_TABLE_MISMATCH'),
        ):
            with self.subTest(reason=reason), patch.object(page, 'get_text', return_value=text):
                with self.assertRaisesRegex(ValueError, reason):
                    self.verify()
