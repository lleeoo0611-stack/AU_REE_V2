import copy,unittest
from au_ree_v2.reviewed_metadata import validate_metadata_issue_date


class LiteralMetadataIssueDate(unittest.TestCase):
    def test_exact_signed_date_and_release_do_not_admit_quantities(self):
        r=dict(effective_date_role='DATED_ISSUER_METADATA',observations=[],attributes=[dict(description_binding={'page':1})],
            publication_date='2023-09-06',document_issue_date='2023-09-05',date_evidence_role='DOCUMENT_ISSUE_DATE_WITH_ASX_URL_RELEASE_DATE',
            publication_date_role='ASX_DATED_URL',document_issue_evidence=dict(page=4,markers=['Signed 5 September 2023']),
            url='https://announcements.asx.com.au/asxpdf/20230906/pdf/abc.pdf')
        def evidence(p):
            self.assertEqual(4,p['page']);return 'signed 5 september 2023'
        validate_metadata_issue_date(r,evidence,'2026-11-05')
        listing=dict(copy.deepcopy(r),attributes=[dict(column='未上市公司',value='否',listing_proof={'exchange':'ASX'})])
        validate_metadata_issue_date(listing,evidence,'2026-11-05')
        for attr in [dict(column='未上市公司',value='是',listing_proof={'exchange':'ASX'}),dict(column='礦石蘊藏量_Mt',value=1,listing_proof={'exchange':'ASX'}),dict(column='未上市公司',value='否')]:
            with self.subTest(attribute=attr),self.assertRaises(ValueError):validate_metadata_issue_date(dict(listing,attributes=[attr]),evidence,'2026-11-05')
        for change in [dict(observations=[{'value':12}]),dict(study={'kind':'PFS'}),dict(attributes=[]),
                       dict(attributes=[{'column':'礦石蘊藏量_Mt'}]),dict(effective_date_role='RESOURCE_EFFECTIVE_DATE'),
                       dict(document_issue_date='2023-09-07'),dict(publication_date='2023-09-07'),
                       dict(url='https://issuer.example/report.pdf'),dict(publication_date_role='UNKNOWN')]:
            with self.subTest(change=change),self.assertRaises(ValueError):
                validate_metadata_issue_date(dict(copy.deepcopy(r),**change),evidence,'2026-11-05')
