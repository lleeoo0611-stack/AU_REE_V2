import copy
import json
import tempfile
import unittest
from pathlib import Path

from au_ree_v2.acquisition import replay_pdf_extensions
from au_ree_v2.census_gap_review import write_gap_review
from au_ree_v2.store import digest, filehash
from au_ree_v2.tabular import read_csv


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'results/ree-project-census/integrated-evidence-v1-20261120'


class GapReviewTests(unittest.TestCase):
    def test_frozen_cohort_and_resolution_do_not_change_denominator(self):
        rows = read_csv(BASE/'REE project census.csv')
        statuses = read_csv(BASE/'field_status.csv')
        trace = {(x['project_id'], x['column']):x for x in read_csv(BASE/'field_provenance.csv')}
        diagnoses = {(x['project_id'], x['column']):(x['status'], x['legacy_reason'], json.loads(x['findings']))
                     for x in statuses if x['value_state'] == 'BLANK'}
        sources = {s['source_sha256'] for s in read_csv(BASE/'source_selection.csv')}
        case = ('AU-430f216ca620b69af5f9', 'ASX代碼')
        diagnoses[case] = ('NOT_APPLICABLE_UNLISTED_DEVELOPER', '', [])
        with tempfile.TemporaryDirectory() as tmp:
            report = write_gap_review(ROOT, Path(tmp), rows, trace, diagnoses, sources, {}, '2026-11-13',
                                      filehash(ROOT/'config/census_gap_review.json'))['gap_review']
            self.assertEqual((report['baseline_gaps'], report['baseline_active_targets']), (577, 189))
            self.assertEqual((report['baseline_applicable'], report['filled_within_baseline']), (3034, 2457))
            self.assertEqual(report['classes'], {'P1':271,'P2':79,'D1':18,'D2':38,'E1':18,
                'E2':38,'E3':44,'E4':41,'E5':12,'E6':12,'R':6})
            self.assertEqual(report['active_target_outcomes']['RECLASSIFIED_NOT_APPLICABLE'], 1)
            ledger = read_csv(Path(tmp)/'gap_review.csv')
            goschen = next(x for x in ledger if x['project_id'] == 'AU-6d807eb7caec9db0f35e'
                           and x['column'].startswith('完整重稀土'))
            self.assertEqual(set(goschen['still_missing_components'].split('|')), {'Ho2O3','Lu2O3'})

    def test_pdf_extension_cannot_rewrite_old_registry(self):
        source = dict(key='base', kind='pdf', url='https://original.example/base.pdf')
        old = {'sources':[source]}
        parent = digest(old)
        extension = dict(key='addition', kind='pdf', source_sha256='a'*64, reviewed_static_pdf_sha256='a'*64,
                         publication_date='2026-10-15', replay_extension_of=parent)
        registry = {'sources':[source, extension]}
        self.assertEqual(replay_pdf_extensions(registry, parent, ['kit']), ['addition'])
        for edit in ('incumbent', 'duplicate', 'missing_pin', 'no_static_library'):
            with self.subTest(edit=edit):
                changed = copy.deepcopy(registry)
                if edit == 'incumbent':
                    changed['sources'][0]['url'] += 'x'
                if edit == 'duplicate':
                    changed['sources'][1]['key'] = 'base'
                if edit == 'missing_pin':
                    del changed['sources'][1]['reviewed_static_pdf_sha256']
                with self.assertRaisesRegex(ValueError, 'registry changed'):
                    replay_pdf_extensions(changed, parent, [] if edit == 'no_static_library' else ['kit'])
