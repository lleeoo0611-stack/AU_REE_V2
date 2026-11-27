"""Formal selection checks for newly admitted canonical resource evidence."""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from au_ree_v2.census import summary_resource_bundle
from au_ree_v2.evidence import resource_values
from au_ree_v2.formal_resource_refresh import PANEL, compare
from au_ree_v2.selection import current_evidence_view, resolve
from au_ree_v2.selection_rules import RESOURCE_ADMISSION_VERSION
from au_ree_v2.store import canonical, connect, digest, filehash
from au_ree_v2.tabular import write_csv


class ResourceSelectionTests(unittest.TestCase):
    cutoff = '2026-11-05'
    effective = '2025-01-02'

    def setUp(self):
        self.db = connect(':memory:')
        self.addCleanup(self.db.close)
        self.db.execute('INSERT INTO entities VALUES(?,?,?,?)', ('project', 'PROJECT', 'p', '01'))
        self.snapshots = []
        for source in ('existing', 'other'):
            self.snapshots.append(dict(key=source, sha256=source, kind='pdf',
                                       publication_date='2025-01-04', available_date='2025-01-05'))
            self.db.execute('INSERT INTO sources VALUES(?,?,?,?,?,?,?,?)',
                            (source, source, 'https://example.test/report', '2025-01-04',
                             '2025-01-05T00:00:00Z', 'source.pdf', 'pdf', '{}'))

    def observation(self, obs, variable, value, unit, *, source='existing', bundle=None,
                    scope='Ore body', category='INFERRED', link=None, cutoff_grade=None):
        raw = {'pdf_page': 3, 'resource_type': 'MINERAL_RESOURCE', 'material_basis': 'RESOURCE_ORE',
               'rounding_half_width': 0.05, 'admission_bundle_id': bundle, 'cutoff_grade': cutoff_grade}
        if link is not None:
            raw['resource_identity_link'] = {'rule': 'EXACT_SAME_SOURCE_TABLE_AND_STATEMENT',
                                             'canonical_observation_ids': link}
        transform = RESOURCE_ADMISSION_VERSION if bundle or link else 'legacy'
        self.db.execute('INSERT INTO observations VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                        (obs, 'project', variable, value, unit, 'TREO', scope, 'statement', category,
                         self.effective, source, 'Table 1', 'AUTO_VALIDATED', '[]', canonical(raw), transform))

    def select(self, ids=(), audit=None):
        return resource_values(self.db, self.cutoff, {'existing', 'other'}, strict=True,
                               scope_audit=audit, admitted_resource_ids=ids)

    def test_admission_isolation_and_explicit_same_statement_link(self):
        self.observation('ore', 'ore_mt', 5, 'Mt')
        self.observation('grade', 'grade', 1, '%')
        self.observation('contained', 'contained_treo_kt', 50.3, 'kt', link={'ore_mt': 'ore', 'grade': 'grade'})
        self.observation('wrong', 'contained_treo_kt', 50.4, 'kt', link={'ore_mt': 'ore', 'grade': 'wrong'})
        audit = []
        self.assertEqual(self.select()['project']['contained_treo_kt'], 50)
        selected = self.select({'contained', 'wrong'}, audit)['project']
        self.assertEqual(selected['contained_treo_kt'], 50.3)
        self.assertEqual(selected['obs_ids'], ['ore', 'grade', 'contained'])
        self.assertEqual({row['reason'] for row in audit}, {'SELECTED', 'AUTOMATIC_RESOURCE_LINK_NOT_CURRENT'})
        current = current_evidence_view(self.db, self.snapshots, self.cutoff, set(), admitted_resource_ids={'contained'})
        self.assertEqual(current['observation_ids'], {'ore', 'grade', 'contained'})
        policy = {'version': 'test', 'criteria': {}, 'financing_codebook': {'states': {}}}
        inventory = resolve(self.db, self.snapshots, self.cutoff, {}, [], {}, policy)['inventory']
        self.assertEqual({r['evidence_id'] for r in inventory}, {'ore', 'grade'})
        inventory = resolve(self.db, self.snapshots, self.cutoff, {}, [], {}, policy,
                            admitted_resource_ids={'contained'})['inventory']
        self.assertEqual({r['evidence_id'] for r in inventory}, {'ore', 'grade', 'contained'})
        matching = [dict(row) for row in self.db.execute('SELECT * FROM observations')]
        census, _ = summary_resource_bundle(matching)
        self.assertEqual(census['value']['contained_treo_kt'], 50.3)

    def test_rejects_cross_bundle_join_wrong_source_and_competing_values(self):
        self.observation('ore', 'ore_mt', 5, 'Mt', bundle='ore-only')
        self.observation('grade', 'grade', 1, '%', bundle='grade-only')
        self.assertEqual(self.select({'ore', 'grade'}), {})
        self.observation('ore-a', 'ore_mt', 5, 'Mt', bundle='complete')
        self.observation('grade-a', 'grade', 1, '%', bundle='complete')
        self.observation('ore-b', 'ore_mt', 65, 'Mt', source='other', bundle='different')
        self.observation('grade-b', 'grade', 1, '%', source='other', bundle='different')
        self.assertEqual(self.select({'ore-a', 'grade-a'})['project']['contained_treo_kt'], 50)
        audit = []
        self.assertEqual(self.select({'ore-a', 'grade-a', 'ore-b', 'grade-b'}, audit), {})
        self.assertEqual({row['reason'] for row in audit}, {'CONCURRENT_SOURCE_CONFLICT'})

    def test_corroborating_resources_retain_both_sources(self):
        self.observation('ore-a', 'ore_mt', 5, 'Mt', bundle='a')
        self.observation('grade-a', 'grade', 1, '%', bundle='a')
        self.observation('ore-b', 'ore_mt', 5, 'Mt', source='other', bundle='b')
        self.observation('grade-b', 'grade', 1, '%', source='other', bundle='b')
        obs_ids = {'ore-a', 'grade-a', 'ore-b', 'grade-b'}
        selected = self.select(obs_ids)['project']
        self.assertEqual(set(selected['obs_ids'] + selected['corroborating_obs_ids']), obs_ids)
        self.assertEqual(set(selected['corroborating_sources']), {'existing', 'other'})

    def test_identical_scope_names_cannot_hide_different_cutoffs(self):
        for idx, source, cutoff in (('a', 'existing', '1000 ppm TREO'), ('b', 'other', '2000 ppm TREO')):
            self.observation('ore-' + idx, 'ore_mt', 5, 'Mt', source=source, bundle=idx, cutoff_grade=cutoff)
            self.observation('grade-' + idx, 'grade', 1, '%', source=source, bundle=idx, cutoff_grade=cutoff)
        obs_ids = {'ore-a', 'grade-a', 'ore-b', 'grade-b'}
        audit = []
        self.assertEqual(self.select(obs_ids, audit), {})
        self.assertEqual({row['reason'] for row in audit}, {'MULTIPLE_SCOPES_REQUIRE_DEFINITION'})
        selected, reason = summary_resource_bundle([dict(row) for row in self.db.execute('SELECT * FROM observations')])
        self.assertIsNone(selected)
        self.assertEqual(reason, 'MULTIPLE_SCOPES_REQUIRE_DEFINITION')


class FormalRefreshReceiptTests(unittest.TestCase):
    def setUp(self):
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)

    def sealed_run(self, name, *, value, cohort, admitted=False, bad_receipt=False):
        root = self.root / name
        root.mkdir()
        cutoff = '2026-11-05'
        research = {'panels': {PANEL: ['R1', 'S1']}, 'monte_carlo': {'seed': 4}}
        config = {'research': research}
        snapshots = [{'key': 'source', 'sha256': 'test'}]
        observations = [{'obs_id': 'ore', 'transform_version': 'legacy'},
                        {'obs_id': 'grade', 'transform_version': 'legacy'}]
        if admitted:
            config['resource_admission'] = dict(frame_sha256='frame', rules_sha256='rules',
                                                canonical_observation_ids=['contained', 'ore'],
                                                active_admission_observation_ids=['contained'])
            observations.append(dict(obs_id='contained', entity_id='p', raw='{}',
                                     transform_version=RESOURCE_ADMISSION_VERSION))
        resources = [dict(entity_id='p', obs_ids=['ore', 'grade'] + (['contained'] if admitted else []),
                          contained_treo_kt=value)]
        matrices = [{'project_id': pid, 'R1': value if pid == 'p' else 0.5, 'S1': 0.6} for pid in cohort]
        ranking = [dict(project_id=pid, scenario='x', saw=(0.7 if admitted else 0.5) if pid != 'p' else value)
                   for pid in cohort]
        traces = [dict(entity_id='p', criterion='R1', raw_value=value, score=value,
                       source=canonical({'obs_ids': ['ore', 'grade'], 'contained_treo_kt': value}))]
        json_files = {'configuration.json': config, 'snapshot_lock.json': snapshots,
                      'eligibility_audit.json': {'formal_c1_admitted': 0},
                      'logical_database.json': {'observations': observations}}
        if admitted:
            json_files['resource_admission.json'] = dict(config['resource_admission'], run_id=('wrong' if bad_receipt else name),
                                                        cutoff=cutoff, snapshot_sha256=digest(snapshots))
        for rel, body in json_files.items():
            (root / rel).write_text(canonical(body) + '\n')
        csv_files = {
            'canonical_membership.csv': ([{'entity_id': 'p', 'canonical_id': 'p'}], ('entity_id', 'canonical_id')),
            'resources.csv': (resources, ('entity_id', 'obs_ids', 'contained_treo_kt')),
            'criteria_resolution.csv': ([], ('criterion',)),
            'value_trace.csv': (traces, ('entity_id', 'criterion', 'raw_value', 'score', 'source')),
            'formal_gate_compatibility.csv': ([], ('canonical_project_id', 'gate')),
            'eligibility_cohorts.csv': ([], ('canonical_project_id',)),
            f'{PANEL}/matrix.csv': (matrices, ('project_id', 'R1', 'S1')),
            f'{PANEL}/criteria.csv': ([{'code': 'R1'}, {'code': 'S1'}], ('code',)),
            f'{PANEL}/weights.csv': ([], ('code', 'weight')),
            f'{PANEL}/ranking.csv': (ranking, ('project_id', 'scenario', 'saw')),
        }
        for rel, (rows, fields) in csv_files.items():
            write_csv(root / rel, rows, fields)
        hashes = {p.relative_to(root).as_posix(): filehash(p) for p in root.rglob('*') if p.is_file()}
        summary = {'status': 'COMPLETED', 'run_id': name, 'cutoff': cutoff, 'code': {'commit': 'test'},
                   'configuration_sha256': digest(config), 'snapshot_sha256': digest(snapshots),
                   'logical_database_sha256': digest(json_files['logical_database.json']), 'output_hashes': hashes,
                   'r_results': {PANEL: {'status': 'COMPLETED', 'n': len(cohort)}}}
        (root / 'summary.json').write_text(canonical(summary) + '\n')
        return root

    def test_compares_and_classifies_criterion_and_cohort_changes(self):
        old = self.sealed_run('old', value=0.2, cohort=['p', 'q'])
        new = self.sealed_run('new', value=0.3, cohort=['p', 'q', 'r'], admitted=True)
        out = self.root / 'diff'
        result = compare(old, new, out)
        self.assertEqual(result['new_canonical_observations'], 1)
        self.assertEqual(result['criterion_selection_counts']['updated'], 1)
        self.assertEqual(result['changed_raw_input_projects'], ['p'])
        panel = result['panels'][PANEL]
        self.assertEqual(panel['cohort_added'], ['r'])
        self.assertEqual(panel['matrix_primary_criterion_cells_changed'], 3)
        self.assertEqual({r['identity'][1]: r['cause'] for r in panel['ranking_differences']}['q'],
                         'COHORT_AND_SHARED_NORMALIZATION')
        self.assertEqual(result['formal_c1']['updated']['formal_c1_admitted'], 0)
        self.assertEqual(result['selection_snapshot_sha256'], filehash(out / 'selection_snapshot.json'))

    def test_rejects_receipt_from_another_run(self):
        old = self.sealed_run('old', value=0.2, cohort=['p', 'q'])
        new = self.sealed_run('new', value=0.3, cohort=['p', 'q'], admitted=True, bad_receipt=True)
        with self.assertRaisesRegex(ValueError, 'REFRESH_ADMISSION_RECEIPT_NOT_BOUND_TO_RUN'):
            compare(old, new, self.root / 'diff')
