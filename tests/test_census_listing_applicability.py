import unittest

from au_ree_v2.census import summary_missing


class ListingApplicabilityTests(unittest.TestCase):
    def test_ticker_exclusion_requires_validated_named_company_and_listing(self):
        operator = 'Example Minerals Ltd'
        row = {'未上市公司': '是', '開發商': operator}
        source = {'column': '未上市公司', 'value': '是',
                  'page_markers': [operator, 'Unlisted Public Company'],
                  'source_sha256': 'abc', 'pdf_page': 4, 'effective_date': '2026-03-31'}
        rules = dict(resource_columns=[], annual_columns=[], identity_columns=[])
        def reason(verified):
            return summary_missing('ASX代碼', {}, row, None, {}, {}, {}, {}, '2026-11-13',
                                   rules, [], verified_attributes=verified)[0]
        self.assertEqual(reason([source]), 'NOT_APPLICABLE_UNLISTED_DEVELOPER')
        self.assertEqual(reason([]), 'NO_SOURCE_VALUE')
        self.assertEqual(reason([dict(source, page_markers=[operator, 'Pty Ltd'])]), 'NO_SOURCE_VALUE')
        row['開發商'] = 'Other operator Ltd'
        self.assertEqual(reason([source]), 'NO_SOURCE_VALUE')
