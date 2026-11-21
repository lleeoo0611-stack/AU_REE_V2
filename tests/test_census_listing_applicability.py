import hashlib
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

from au_ree_v2.census import summary_missing
from au_ree_v2.evidence import validate_historical_proprietary_company


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

    def test_dated_proprietary_status_requires_unique_registered_entity_and_cutoff(self):
        company = 'Example Minerals Pty Ltd'
        header = 'Company Name\tACN\tABN\tType\tClass\tSub Class\tStatus\tDate of Registration\tCurrent Name Indicator'
        row = 'EXAMPLE MINERALS PTY LTD\t123456789\t99123456789\tAPTY\tLMSH\tPROP\tREGD\t23/09/2021\tY'
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / 'register.zip'
            member = 'companies.csv'
            with ZipFile(path, 'w') as archive:
                archive.writestr(member, '\n'.join([header, row, '']))
            sha = hashlib.sha256(path.read_bytes()).hexdigest()
            snapshot = dict(key='asic', kind='asic_company_register_zip', sha256=sha,
                            available_date='2026-11-02', path=path.name)
            markers = [company, 'EL123', '14th August 2025']
            proof = dict(source_key='asic', source_sha256=sha, archive_member=member,
                         physical_line=2, acn='123456789', abn='99123456789', company=company,
                         dated_marker=markers[2], project_marker=markers[1], register_date='2026-11-02')
            attribute = dict(column='未上市公司', value='是', page_markers=markers,
                             effective_date='2025-08-14', asic_proprietary_company=proof)
            validate_historical_proprietary_company(root, attribute, [snapshot], {}, '2026-11-13')
            for changes in (dict(abn='99123456788'), dict(physical_line=3), dict(project_marker='EL456')):
                with self.subTest(changes=changes), self.assertRaises(ValueError):
                    validate_historical_proprietary_company(root, dict(attribute, asic_proprietary_company=dict(proof, **changes)),
                                                           [snapshot], {}, '2026-11-13')
            with self.assertRaisesRegex(ValueError, 'REGISTER_VERSION'):
                validate_historical_proprietary_company(root, attribute, [snapshot], {}, '2025-08-14')
