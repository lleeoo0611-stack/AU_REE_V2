import json
from pathlib import Path
import tempfile
import unittest

import pymupdf
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
        with self.assertRaises(ValueError):
            standard_evidence(dict(case, pages={'6':['GB/T 40798-2021','soil fraction']},
                              adopted_standard='GB/T 40798-2021', standard_status='SOURCE_EXPLICIT_STANDARD'),catalog)

    def test_adoption_requires_same_subject_matrix_and_affirmative_located_sentence(self):
        edition='GB/T 40798-2021'
        catalog={edition:{'method':'ICP-MS','matrix':'ion-adsorption ore'}}
        prefix='Batch B (ion-adsorption ore)'
        quote=f'{prefix} was analysed in accordance with {edition}.'
        negative=f'{prefix} was not analysed in accordance with {edition}.'
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'methods.pdf'
            with pymupdf.open() as pdf:
                page=pdf.new_page()
                page.insert_textbox((30,30,560,400),
                    'Batch A (soil) was analysed using a different protocol. '+quote)
                pdf.save(path)
            case=dict(standard_status='SOURCE_EXPLICIT_STANDARD', adopted_standard=edition, sample='Batch B',
                      matrix='ion-adsorption ore', pages={'1':[quote,'Batch B']}, adoption_quote=quote,
                      adoption_scope=dict(physical_page=1,sample='Batch B',matrix='ion-adsorption ore'))
            supported=standard_evidence(case,catalog,path)
            self.assertEqual(supported['adopted_standard'],edition)
            self.assertEqual(json.loads(supported['standard_scope_review'])[0]['adoption_quote'],quote)
            changes=(
                dict(sample='Batch A'),dict(matrix='soil'),
                dict(adoption_scope=dict(case['adoption_scope'],physical_page=2)),
                dict(adoption_quote=negative,pages={'1':[negative,edition]}),
                dict(adoption_quote=f'{prefix} was compared to {edition}.',
                     pages={'1':[f'{prefix} was compared to {edition}.',edition]}),
                dict(adoption_quote=quote.replace('was analysed','may be analysed'),
                     pages={'1':[quote.replace('was analysed','may be analysed'),edition]}),
                dict(sample='Batch A',matrix='soil',adoption_scope=dict(physical_page=1,sample='Batch A',matrix='soil')),
            )
            for change in changes:
                with self.subTest(change=change), self.assertRaises(ValueError):
                    standard_evidence(dict(case,**change),catalog,path)
            quoted_only=Path(folder)/'non-affirmative.pdf'
            with pymupdf.open() as pdf:
                page=pdf.new_page()
                page.insert_textbox((30,30,560,400),'The authors do not agree that '+quote)
                pdf.save(quoted_only)
            with self.assertRaises(ValueError):
                standard_evidence(case,catalog,quoted_only)
            conflicting=Path(folder)/'conflict.pdf'
            with pymupdf.open() as pdf:
                page=pdf.new_page()
                page.insert_textbox((30,30,560,400),quote+' '+negative)
                pdf.save(conflicting)
            with self.assertRaises(ValueError):
                standard_evidence(case,catalog,conflicting)

    def test_unreported_quality_and_scope_have_no_numeric_defaults(self):
        self.assertEqual('NOT_REPORTED', standard_evidence(dict(standard_status='NOT_REPORTED'), {})['standard_status'])
