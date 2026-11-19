import unittest

from au_ree_v2.assays import standard_evidence


class AssayEvidenceTests(unittest.TestCase):
    def test_instrument_or_scope_match_does_not_establish_adoption(self):
        catalog = {'GB/T 40798-2021': {'method': 'ICP-MS', 'matrix': 'ion adsorption ore'}}
        case = dict(standard_status='METHOD_ONLY_NO_STANDARD_CITED', method='ICP-MS',
                    pages={'6': ['mass spectrometry', 'soil fraction']}, standard_comparisons={})
        self.assertIsNone(standard_evidence(case, catalog)['adopted_standard'])
        with self.assertRaises(ValueError):
            standard_evidence(dict(case, adopted_standard='GB/T 40798-2021'), catalog)
        with self.assertRaises(ValueError):
            standard_evidence(dict(case, adopted_standard='GB/T 40798-2021',
                                   standard_status='SOURCE_EXPLICIT_STANDARD'), catalog)
        explicit = dict(case, pages={'6':['GB/T 40798-2021','soil fraction']},
                        adopted_standard='GB/T 40798-2021', standard_status='SOURCE_EXPLICIT_STANDARD')
        self.assertEqual('GB/T 40798-2021', standard_evidence(explicit, catalog)['adopted_standard'])

    def test_unreported_quality_and_scope_have_no_numeric_defaults(self):
        self.assertEqual('NOT_REPORTED', standard_evidence(dict(standard_status='NOT_REPORTED'), {})['standard_status'])
