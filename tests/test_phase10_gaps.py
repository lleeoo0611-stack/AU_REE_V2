"""Exercise bounded evidence statuses and the pinned research priority queue."""

from collections import defaultdict
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from tools.phase10_gaps import BASELINE, _cause, _potential, _recovery, run


ROOT = Path(__file__).resolve().parents[1]


class Phase10GapsTests(unittest.TestCase):
    def test_no_value_from_a_group_total_a_bounded_search_or_unknown_chemistry(self):
        missing = {'status': 'SELECTED_STATEMENT_FIELD_INPUT_MISSING'}
        bounded = {'class': 'P1', 'reason': 'NO_MATCHING_COMPONENT_LOCATED_IN_FROZEN_SOURCES',
                   'source_review': 'Checked physical table', 'review_pages': '1'}
        group_total = {**bounded, 'reason': 'GROUP_TOTAL_DOES_NOT_IDENTIFY_COMPONENT'}
        self.assertEqual(_cause(missing, bounded, set(), [], [])[0], 'UNRESOLVED')
        self.assertEqual(_cause(missing, group_total, set(), [], [])[0], 'NOT_DISCLOSED')
        self.assertEqual(_cause(missing, {**bounded, 'reason': 'UNVERIFIED_CHEMICAL_FORM'}, set(), [], [])[0],
                         'SEMANTIC_BINDING_INCOMPLETE')
        self.assertEqual(_cause(missing, group_total, {'a' * 64}, [], [])[0], 'SOURCE_MISSING')

    def test_priority_requires_same_scope_and_panel_comparable_definition(self):
        composition, study = 'issuer_resource_composition', 'issuer_resource_study'
        r1 = {'code': 'R1', 'unit': 'kt'}
        panels = {composition: {'criteria': [r1, {'code': 'S1'}], 'matrix_projects': 10},
                  study: {'criteria': [r1, {'code': 'D1'}], 'matrix_projects': 7}}
        decisions = {('a', composition): {'status': 'NO_ELIGIBLE_INPUT_IN_PANEL_MATRIX'},
                     ('a', study): {'status': 'IN_PANEL_MATRIX'}}
        lines = defaultdict(list, {('a', 'R1'): [{'panel': study, 'scope': 'matched estimate'}]})
        self.assertEqual(_potential('a', 'S1', panels, decisions, lines)[0]['unmet_criteria'], ['S1'])
        panels[study]['criteria'][0] = {**r1, 'unit': 'ppm'}
        self.assertEqual(_potential('a', 'S1', panels, decisions, lines), [])

    def test_complete_verified_historical_recovery_is_required_for_source_availability(self):
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            sha = 'a' * 64
            (folder / 'asset_manifest.json').write_text(json.dumps([{'sha256': sha}]), encoding='utf-8')
            self.assertEqual(_recovery(folder, None)[:2], ({sha}, None))
            received = {'assets': [{'expected_sha256': sha, 'observed_sha256': sha,
                                    'status': 'AVAILABLE_EXACT_ORIGINAL'}], 'missing_assets': {}}
            self.assertEqual(_recovery(folder, received)[:2], ({sha}, set()))
            received['assets'][0]['observed_sha256'] = 'b' * 64
            with self.assertRaisesRegex(ValueError, 'availability and impact'):
                _recovery(folder, received)

    def test_pinned_real_grid_is_complete_and_priority_is_deterministic(self):
        with TemporaryDirectory() as directory:
            output = Path(directory)
            first = run(ROOT, output)
            second = run(ROOT, output)
            data = json.loads((output / 'project_criterion_blockers.json').read_bytes())
            self.assertEqual(first, second)
            self.assertEqual((first['historical_project_count'], first['historical_panel_count'], first['field_rows']),
                             (93, 16, 4743))
            self.assertEqual(sum(r['historical_class'] == 'P1' for r in data['field_blockers']
                                 if r.get('historical_class')), 271)
            self.assertEqual(sum(r['historical_class'] == 'P2' for r in data['field_blockers']
                                 if r.get('historical_class')), 79)
            self.assertEqual(sum(first['historical_field_causes'].values()), 2243)
            self.assertEqual(first['automatic_new_values'], 0)
            self.assertEqual(first['formal_c1_cohort'], 'DISABLED')
            self.assertGreater(sum(r['conditional_one_field_matrix_rows'] for r in data['project_criterion_blockers']), 0)
            self.assertNotIn(BASELINE.as_posix(), (output / 'research_gap_priority.csv').read_text(encoding='utf-8'))
