import copy
import csv
import json
import tempfile
import unittest
from pathlib import Path
from au_ree_v2.iteration_review import review_coverage_cycle
from au_ree_v2.store import filehash

ROOT = Path(__file__).resolve().parents[1]
COLUMNS = json.loads((ROOT/'config/project_summary_columns.json').read_text('utf8')) + ['ASX代碼']


class CoverageCycle(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.manifest = dict(cycle_id='test', tracks={name: dict(completed=True,
            records=[dict(query='Primary source search', disposition='Reviewed, no further admissible facts')])
            for name in ('candidates', 'numeric')}, validation={name: dict(passed=True, evidence='test evidence')
            for name in ('sources', 'tests', 'reproducibility')})
        self.manifest.update(search_scope=dict(columns=COLUMNS, all_blank_fields_reviewed=True),
                             unresolved_acquisition_actions=[])

    def row(self, pid='P', fills=0):
        row = dict.fromkeys(COLUMNS, '')
        row[COLUMNS[0]] = pid
        for column in COLUMNS[15:15+fills]:
            row[column] = '10'
        return row

    def write(self, name, rows, columns=None):
        columns = columns or COLUMNS
        folder = self.root/name
        folder.mkdir(exist_ok=True)
        def csvfile(filename, fields, items):
            with (folder/filename).open('w', encoding='utf-8-sig', newline='') as handle:
                writer = csv.DictWriter(handle, fields)
                writer.writeheader()
                writer.writerows(items)
        csvfile('專案總表.csv', columns, rows)
        provenance, missing = [], []
        for row in rows:
            for column, value in row.items():
                entry = dict(project_id=row['專案ID'], column=column)
                if value:
                    provenance.append(dict(entry, value=value))
                else:
                    missing.append(entry)
        csvfile('field_provenance.csv', ['project_id', 'column', 'value'], provenance)
        csvfile('missing_fields.csv', ['project_id', 'column'], missing)
        summary = dict(version='census-project-summary-v3-asx-identity', base_contract_columns=52,
            identity_ledger_sha256='verified-fixture', output_hashes={name:filehash(folder/name)
            for name in ('專案總表.csv', 'field_provenance.csv', 'missing_fields.csv')})
        (folder/'summary.json').write_text(json.dumps(summary), encoding='utf8')
        return folder

    def compare(self, old, new, manifest=None):
        return review_coverage_cycle(self.write('before', old), self.write('after', new), manifest or self.manifest)

    def test_only_zero_stops(self):
        for count, stop in [(0, True), (1, False), (2, False), (3, False)]:
            with self.subTest(count=count):
                report = self.compare([self.row()], [self.row(fills=count)])
                self.assertEqual(stop, report['stopping_rule']['stop'])
                self.assertEqual(count, report['existing_projects']['scientific_newly_filled_cells'])

    def test_all_fields_and_acquisition_must_be_complete(self):
        for key, value in [('search_scope', {}), ('unresolved_acquisition_actions', ['blocked PDF']),
                           ('unresolved_acquisition_actions', None)]:
            with self.subTest(key=key, value=value):
                manifest = copy.deepcopy(self.manifest)
                manifest[key] = value
                report = self.compare([self.row()], [self.row()], manifest)
                self.assertEqual('INCOMPLETE', report['stopping_rule']['decision'])

    def test_legacy_replay_requires_explicit_policy(self):
        self.manifest['stopping_policy'] = 'LEGACY_BELOW_THREE'
        self.assertTrue(self.compare([self.row()], [self.row(fills=2)])['stopping_rule']['stop'])
        self.manifest['stopping_policy'] = 'UNKNOWN'
        with self.assertRaisesRegex(ValueError, 'UNKNOWN_STOPPING_POLICY'):
            self.compare([self.row()], [self.row()], self.manifest)

    def test_complete_below_three_policy_has_strict_threshold(self):
        self.manifest['stopping_policy']='BELOW_THREE_COMPLETE_ROUND'
        for count,stop in [(0,True),(1,True),(2,True),(3,False)]:
            with self.subTest(count=count):
                report=self.compare([self.row()],[self.row(fills=count)])
                self.assertEqual(stop,report['stopping_rule']['stop'])
                self.assertEqual(3,report['stopping_rule']['threshold'])

    def test_complete_below_three_never_stops_with_unfinished_prerequisites(self):
        self.manifest['stopping_policy']='BELOW_THREE_COMPLETE_ROUND'
        for count in (0,1,2):
            for key,value in [('unresolved_acquisition_actions',['blocked PDF']),
                              ('unresolved_acquisition_actions',None),('search_scope',{}),
                              ('tracks',{}),('validation',{})]:
                with self.subTest(count=count,prerequisite=key):
                    manifest=copy.deepcopy(self.manifest);manifest[key]=value
                    report=self.compare([self.row()],[self.row(fills=count)],manifest)
                    self.assertEqual('INCOMPLETE',report['stopping_rule']['decision'])
                    self.assertFalse(report['stopping_rule']['stop'])

    def test_added_cells_are_separate_and_include_identity(self):
        report = self.compare([self.row()], [self.row(), self.row('Q', 2)])
        self.assertEqual(0, report['existing_projects']['newly_filled_cells'])
        self.assertEqual(3, report['added_projects']['filled_cells'])
        self.assertEqual(2, report['added_projects']['scientific_filled_cells'])
        self.assertEqual(1, report['added_projects']['identity_and_other_metadata_cells'])
        self.assertFalse(report['stopping_rule']['stop'])

    def full_manifest(self, old, new):
        manifest = copy.deepcopy(self.manifest)
        manifest['stopping_policy'] = 'FULL_SCOPE_ZERO_NEW_VERIFIED_CELLS'
        def reviewed(**identity):
            return dict(identity, completed=True, query_ids=['search-1'],
                        source_review_ids=['review-1'], disposition='Reviewed source scope')
        old_ids = {r[COLUMNS[0]] for r in old}
        cells = {(r[COLUMNS[0]], c) for r in old for c in COLUMNS if not r[c]}
        cells |= {(r[COLUMNS[0]], c) for r in new if r[COLUMNS[0]] not in old_ids
                  for c in COLUMNS if not r[c]}
        manifest['full_scope'] = dict(baseline_project_ids=sorted(old_ids),
            cell_reviews=[reviewed(project_id=p, column=c) for p, c in sorted(cells)],
            project_reviews=[reviewed(project_id=p) for p in sorted(old_ids|{r[COLUMNS[0]] for r in new})],
            expected_candidate_ids=['candidate'], candidate_reviews=[reviewed(lead_id='candidate')],
            expected_external_lead_ids=['external'], external_lead_reviews=[reviewed(lead_id='external')],
            source_actions=[dict(action_id='source-1', completed=True, evidence='hash + locator')])
        return manifest

    def test_whole_cohort_policy_stops_only_at_zero(self):
        for count, stop in [(0, True), (1, False), (2, False), (3, False)]:
            with self.subTest(count=count):
                old, new = [self.row()], [self.row(fills=count)]
                report = self.compare(old, new, self.full_manifest(old, new))
                self.assertEqual(stop, report['stopping_rule']['stop'])
                self.assertEqual(0, report['stopping_rule']['threshold'])

    def test_whole_cohort_omissions_and_unfinished_actions_never_stop(self):
        old = new = [self.row(), self.row('Q')]
        for collection in ('cell_reviews', 'project_reviews', 'candidate_reviews', 'external_lead_reviews', 'source_actions'):
            for mutation in ('omit', 'duplicate', 'unfinished', 'no_evidence'):
                with self.subTest(collection=collection, mutation=mutation):
                    manifest = self.full_manifest(old, new)
                    records = manifest['full_scope'][collection]
                    if mutation == 'omit': records.pop()
                    elif mutation == 'duplicate': records.append(copy.deepcopy(records[0]))
                    elif mutation == 'unfinished': records[0]['completed'] = False
                    elif collection == 'source_actions': records[0]['evidence'] = ''
                    else: records[0]['source_review_ids'] = []
                    result = self.compare(old, new, manifest)['stopping_rule']
                    self.assertEqual('INCOMPLETE', result['decision'])
                    self.assertFalse(result['stop'])

    def test_whole_cohort_new_project_gaps_join_same_round(self):
        old, new = [self.row()], [self.row(), self.row('Q', 2)]
        manifest = self.full_manifest(old, new)
        self.assertTrue(self.compare(old, new, manifest)['stopping_rule']['eligible'])
        manifest['full_scope']['cell_reviews'] = [r for r in manifest['full_scope']['cell_reviews'] if r['project_id'] != 'Q']
        self.assertFalse(self.compare(old, new, manifest)['stopping_rule']['eligible'])

    def test_whole_cohort_requires_frozen_lead_sets_and_baseline(self):
        old = new = [self.row()]
        for key in ('baseline_project_ids', 'expected_candidate_ids', 'expected_external_lead_ids'):
            manifest = self.full_manifest(old, new)
            manifest['full_scope'].pop(key)
            self.assertEqual('INCOMPLETE', self.compare(old, new, manifest)['stopping_rule']['decision'])

    def test_updates_withdrawals_not_new_fills(self):
        old = self.row(fills=3)
        new = self.row(fills=2)
        new[COLUMNS[15]] = '11'
        new[COLUMNS[16]] = '10.0'
        report = self.compare([old], [new])
        self.assertEqual(1, report['existing_projects']['withdrawn_cells'])
        self.assertFalse(report['stopping_rule']['eligible'])
        self.assertIn('validation:cell_withdrawals_require_separate_review',report['stopping_rule']['incomplete'])
        self.assertEqual(1, report['existing_projects']['updated_value_cells'])
        self.assertEqual(1, report['existing_projects']['numeric_format_only_cells'])
        self.assertEqual(-1, report['total_filled_cell_delta'])
        self.assertEqual(0, report['stopping_rule']['newly_filled_cells'])

    def test_incomplete_track_or_validation_never_stops(self):
        for kind, name in [('tracks', 'candidates'), ('tracks', 'numeric'),
                           ('validation', 'sources'), ('validation', 'tests'), ('validation', 'reproducibility')]:
            with self.subTest(name=name):
                manifest = copy.deepcopy(self.manifest)
                manifest[kind][name] = {}
                report = self.compare([self.row()], [self.row()], manifest)
                self.assertFalse(report['stopping_rule']['eligible'])
                self.assertFalse(report['stopping_rule']['stop'])
                self.assertEqual('INCOMPLETE', report['stopping_rule']['decision'])

    def test_empty_search_records_never_stop(self):
        self.manifest['tracks']['numeric']['records'] = []
        self.assertFalse(self.compare([self.row()], [self.row()])['stopping_rule']['stop'])

    def test_unexplained_deletion_rejected_and_explanation_counted(self):
        old, new = [self.row(), self.row('Q', 2)], [self.row()]
        with self.assertRaisesRegex(ValueError, 'UNEXPLAINED_PROJECT_REMOVAL'):
            self.compare(old, new)
        self.manifest['removed_projects'] = [dict(project_id='Q', reason='Verified same ASX and alias', merged_into='P')]
        report = self.compare(old, new)
        self.assertEqual(3, report['removed_projects']['filled_cells'])
        self.assertEqual(-3, report['total_filled_cell_delta'])

    def test_duplicate_project_rejected(self):
        with self.assertRaisesRegex(ValueError, 'DUPLICATE_PROJECT'):
            self.compare([self.row()], [self.row(), self.row()])

    def test_changed_schema_rejected(self):
        before = self.write('before', [self.row()])
        row = self.row()
        row['wrong'] = row.pop('ASX代碼')
        after = self.write('after', [row], COLUMNS[:-1]+['wrong'])
        with self.assertRaisesRegex(ValueError, 'CONTRACT_MISMATCH'):
            review_coverage_cycle(before, after, self.manifest)

    def test_valid_52_column_export_cannot_be_cycle_input(self):
        row = self.row()
        row.pop('ASX代碼')
        before = self.write('before', [row], COLUMNS[:-1])
        summary_path = before/'summary.json'
        summary = json.loads(summary_path.read_text('utf8'))
        summary['version'] = 'census-project-summary-v2'
        summary_path.write_text(json.dumps(summary), encoding='utf8')
        after = self.write('after', [self.row()])
        with self.assertRaisesRegex(ValueError, 'REQUIRES_53_COLUMNS'):
            review_coverage_cycle(before, after, self.manifest)

    def test_hash_tamper_rejected(self):
        before = self.write('before', [self.row()])
        after = self.write('after', [self.row()])
        with (after/'專案總表.csv').open('a') as handle:
            handle.write('\n')
        with self.assertRaisesRegex(ValueError, 'HASH_MISMATCH'):
            review_coverage_cycle(before, after, self.manifest)

    def test_missing_provenance_rejected(self):
        before = self.write('before', [self.row()])
        after = self.write('after', [self.row()])
        (after/'field_provenance.csv').write_text('project_id,column,value\n', encoding='utf8')
        with self.assertRaisesRegex(ValueError, 'PROVENANCE_CELL_MISMATCH'):
            review_coverage_cycle(before, after, self.manifest)


if __name__ == '__main__':
    unittest.main()
