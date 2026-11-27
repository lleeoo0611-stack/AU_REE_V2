"""Formal selection checks for newly admitted canonical resource evidence."""

from pathlib import Path
from tempfile import TemporaryDirectory
import json
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
                    scope='Ore body', category='INFERRED', link=None, cutoff_grade='500 ppm TREO',
                    transform=None, deposit=None):
        raw = {'pdf_page': 3, 'resource_type': 'MINERAL_RESOURCE', 'reporting_standard':'JORC', 'material_basis': 'RESOURCE_ORE',
               'composition_denominator_basis': 'RESOURCE_BULK_ORE_MASS', 'scope_coverage': 'PROJECT_TOTAL',
               'rounding_half_width': 0.05, 'admission_bundle_id': bundle, 'cutoff_grade': cutoff_grade,
               'deposit_id': deposit}
        if link is not None:
            raw['resource_identity_link'] = {'rule': 'EXACT_SAME_SOURCE_TABLE_AND_STATEMENT',
                                             'canonical_observation_ids': link, 'reported_table_label':'1'}
        transform = transform or (RESOURCE_ADMISSION_VERSION if bundle or link else 'legacy')
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
        self.assertEqual({row['reason'] for row in audit},
                         {'CONCURRENT_SOURCE_CONFLICT', 'AUTOMATIC_RESOURCE_NOT_ACTIVATED_FOR_RUN'})

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

    def test_link_context_holds_a_wrong_cutoff_and_keeps_existing_value(self):
        self.observation('ore', 'ore_mt', 7.3, 'Mt', cutoff_grade='1,000 ppm TREO')
        self.observation('grade', 'grade', 0.96, '%', cutoff_grade='1,000 ppm TREO')
        self.observation('wrong', 'contained_treo_kt', 70.5, 'kt', link={'ore_mt':'ore','grade':'grade'})
        audit = []
        self.assertAlmostEqual(self.select({'wrong'}, audit)['project']['contained_treo_kt'], 70.08)
        [held] = audit
        self.assertEqual(held['reason'], 'AUTOMATIC_RESOURCE_LINK_CONTEXT_MISMATCH')
        self.assertEqual(set(json.loads(held['observation_ids'])), {'ore','grade','wrong'})
        self.assertTrue(all(row['physical_page'] == 3 for row in json.loads(held['evidence_locations'])))
        self.assertEqual({issue['dimension'] for check in json.loads(held['details'])['comparisons']
                          for issue in check['issues']}, {'cutoff_grade'})
        census, _ = summary_resource_bundle([dict(row) for row in self.db.execute('SELECT * FROM observations')])
        self.assertAlmostEqual(census['value']['contained_treo_kt'], 70.08)

    def test_equivalent_ppm_and_percent_support_verified_link(self):
        self.observation('ore', 'ore_mt', 7.3, 'Mt', cutoff_grade='1,000 ppm TREO')
        self.observation('grade', 'grade', 0.96, '%', cutoff_grade='1,000 ppm TREO')
        self.observation('reported', 'contained_treo_kt', 70.5, 'kt', cutoff_grade='0.1% TREO',
                         link={'ore_mt':'ore','grade':'grade'})
        self.assertEqual(self.select({'reported'})['project']['contained_treo_kt'], 70.5)
        census, _ = summary_resource_bundle([dict(row) for row in self.db.execute('SELECT * FROM observations')])
        self.assertEqual(census['value']['contained_treo_kt'], 70.5)

    def test_cutoff_basis_and_boundary_operator_are_scientific_dimensions(self):
        self.observation('ore', 'ore_mt', 7.3, 'Mt', cutoff_grade='>= 1,000 ppm TREO')
        self.observation('grade', 'grade', 0.96, '%', cutoff_grade='≥ 0.1% TREO')
        for name, threshold in (('chemistry', '>= 0.1% REO'), ('exclusive', '> 1000 ppm TREO'),
                                ('unqualified', '1000 ppm TREO')):
            self.observation(name, 'contained_treo_kt', 70.5, 'kt', cutoff_grade=threshold,
                             link={'ore_mt':'ore','grade':'grade'})
        for name in ('chemistry','exclusive','unqualified'):
            with self.subTest(name=name):
                audit = []
                selected = self.select({name}, audit)['project']
                self.assertAlmostEqual(selected['contained_treo_kt'], 70.08)
                [held] = [row for row in audit if row['reason'] != 'AUTOMATIC_RESOURCE_NOT_ACTIVATED_FOR_RUN']
                self.assertEqual(held['reason'], 'AUTOMATIC_RESOURCE_LINK_CONTEXT_MISMATCH')

    def test_equal_quantities_do_not_prove_the_printed_source_table(self):
        self.observation('ore', 'ore_mt', 7.3, 'Mt')
        self.observation('grade', 'grade', 0.96, '%')
        self.observation('reported', 'contained_treo_kt', 70.5, 'kt', link={'ore_mt':'ore','grade':'grade'})
        self.db.execute("UPDATE observations SET locator='Page 3 Table 11' WHERE obs_id='grade'")
        audit = []
        self.assertAlmostEqual(self.select({'reported'}, audit)['project']['contained_treo_kt'], 70.08)
        [held] = audit
        self.assertEqual(held['reason'], 'AUTOMATIC_RESOURCE_LINK_LOCATION_NOT_CURRENT')
        self.assertEqual(json.loads(held['details'])['legacy_locations'][1]['printed_table'], '11')

    def test_missing_link_context_and_unrelated_bundle_keep_existing_value(self):
        self.observation('ore', 'ore_mt', 7.3, 'Mt', cutoff_grade=None)
        self.observation('grade', 'grade', 0.96, '%', cutoff_grade=None)
        self.observation('unproved', 'contained_treo_kt', 70.5, 'kt', link={'ore_mt':'ore','grade':'grade'})
        self.observation('ore-other', 'ore_mt', 70, 'Mt', source='other', bundle='independent', deposit='different-id')
        self.observation('grade-other', 'grade', 0.96, '%', source='other', bundle='independent', deposit='different-id')
        audit = []
        self.assertAlmostEqual(self.select({'unproved','ore-other','grade-other'}, audit)['project']['contained_treo_kt'], 70.08)
        self.assertEqual({line['reason'] for line in audit},
                         {'AUTOMATIC_RESOURCE_LINK_CONTEXT_UNRESOLVED','AUTOMATIC_RESOURCE_SCOPE_MISMATCH'})

    def test_superseded_scope_does_not_authorize_replacing_the_incumbent(self):
        self.observation('ore-current', 'ore_mt', 7.3, 'Mt', cutoff_grade='1000 ppm TREO')
        self.observation('grade-current', 'grade', 0.96, '%', cutoff_grade='1000 ppm TREO')
        self.observation('ore-earlier', 'ore_mt', 4, 'Mt')
        self.observation('grade-earlier', 'grade', 0.96, '%')
        self.db.execute("UPDATE observations SET effective_date='2024-01-03' WHERE obs_id LIKE '%-earlier'")
        self.observation('ore-different', 'ore_mt', 20, 'Mt', source='other', bundle='different')
        self.observation('grade-different', 'grade', 0.96, '%', source='other', bundle='different')
        self.db.execute("UPDATE observations SET effective_date='2025-01-04' WHERE obs_id LIKE '%-different'")
        audit = []
        selected = self.select({'ore-different','grade-different'}, audit)['project']
        self.assertEqual(selected['obs_ids'], ['ore-current','grade-current'])
        [held] = audit
        self.assertEqual(held['reason'], 'AUTOMATIC_RESOURCE_SCOPE_MISMATCH')
        self.assertEqual({pair['observation_id'] for pair in json.loads(held['details'])['comparisons']},
                         {'ore-current','grade-current'})
        census, _ = summary_resource_bundle([dict(row) for row in self.db.execute('SELECT * FROM observations')])
        self.assertAlmostEqual(census['value']['contained_treo_kt'], 70.08)

    def test_explicit_non_jorc_context_cannot_be_reused(self):
        self.observation('ore', 'ore_mt', 7.3, 'Mt')
        self.observation('grade', 'grade', 0.96, '%')
        self.db.execute("UPDATE observations SET raw=json_set(raw,'$.reporting_standard','NON_JORC')")
        self.observation('reported', 'contained_treo_kt', 70.5, 'kt', link={'ore_mt':'ore','grade':'grade'})
        audit = []
        self.assertAlmostEqual(self.select({'reported'}, audit)['project']['contained_treo_kt'], 70.08)
        [held] = audit
        self.assertEqual(held['reason'], 'AUTOMATIC_RESOURCE_LINK_CONTEXT_MISMATCH')
        self.assertEqual({issue['dimension'] for check in json.loads(held['details'])['comparisons']
                          for issue in check['issues']}, {'reporting_standard'})

    def test_genuine_report_conflict_withdrawal_exposes_both_witnesses(self):
        self.observation('ore', 'ore_mt', 7.3, 'Mt')
        self.observation('grade', 'grade', 0.96, '%')
        self.observation('existing-report', 'contained_treo_kt', 70.0, 'kt')
        self.observation('new-report', 'contained_treo_kt', 70.5, 'kt', link={'ore_mt':'ore','grade':'grade'})
        self.assertEqual(self.select()['project']['contained_treo_kt'], 70.0)
        audit = []
        self.assertEqual(self.select({'new-report'}, audit), {})
        [conflict] = audit
        self.assertEqual(conflict['reason'], 'CONCURRENT_REPORTED_CONTAINED_CONFLICT')
        self.assertEqual(set(json.loads(conflict['observation_ids'])), {'ore','grade','existing-report','new-report'})
        self.assertEqual(json.loads(conflict['details'])['contained_treo_kt'], {'existing':70.0,'new':70.5})

    def test_obsolete_and_future_automatic_versions_require_activation(self):
        for transform in ('automatic-resource-admission-v1', 'automatic-resource-admission-v99'):
            self.observation(transform + '-ore', 'ore_mt', 10, 'Mt', bundle=transform, transform=transform)
            self.observation(transform + '-grade', 'grade', 1, '%', bundle=transform, transform=transform)
        audit = []
        self.assertEqual(self.select(audit=audit), {})
        self.assertEqual(len(audit), 4)
        self.assertEqual({row['reason'] for row in audit}, {'AUTOMATIC_RESOURCE_NOT_ACTIVATED_FOR_RUN'})
        self.assertFalse(current_evidence_view(self.db, self.snapshots, self.cutoff, set())['observation_ids'])
        policy = {'version':'test','criteria':{},'financing_codebook':{'states':{}}}
        self.assertEqual(resolve(self.db, self.snapshots, self.cutoff, {}, [], {}, policy)['inventory'], [])


class FormalRefreshReceiptTests(unittest.TestCase):
    def setUp(self):
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)

    def sealed_run(self, name, *, value, cohort, admitted=False, bad_receipt=False,
                   code=None, rules='rules', source_sha='test', path='archive/report.pdf',
                   frame_sha='frame', frame_pin=None, automatic_id='contained',
                   admission_version=RESOURCE_ADMISSION_VERSION, retained_observations=(),
                   selected_ids=None, scope_decisions=(), weight_rows=()):
        root = self.root / name
        root.mkdir()
        cutoff = '2026-11-05'
        research = {'panels': {PANEL: ['R1', 'S1']}, 'monte_carlo': {'seed': 4}}
        config = {'research': research}
        snapshots = [{'key': 'source', 'sha256': source_sha, 'path': path}]
        observations = [{'obs_id': 'ore', 'transform_version': 'legacy', 'variable': 'ore_mt'},
                        {'obs_id': 'grade', 'transform_version': 'legacy', 'variable': 'grade'},
                        *retained_observations]
        if admitted:
            config['resource_admission'] = dict(frame_sha256=frame_sha, rules_sha256=rules,
                                                canonical_observation_ids=sorted([automatic_id, 'ore', 'grade']),
                                                active_admission_observation_ids=[automatic_id])
            observations.append(dict(obs_id=automatic_id, entity_id='p', variable='contained_treo_kt',
                                     source_sha=source_sha, locator='physical page 5; row 2',
                                     raw=canonical({'admission_bundle_id': 'bundle', 'resource_identity_link': {
                                         'canonical_observation_ids': {'ore_mt': 'ore', 'grade': 'grade'},
                                     }}), transform_version=admission_version))
        if selected_ids is None:
            selected_ids = ['ore', 'grade'] + ([automatic_id] if admitted else [])
        resources = [dict(entity_id='p', obs_ids=selected_ids, contained_treo_kt=value)] if selected_ids else []
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
            if frame_pin is not None:
                json_files['resource_admission.json']['frame_sources'] = [
                    dict(source_key='source', source_sha256=frame_pin, pages=[5])]
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
            f'{PANEL}/weights.csv': (weight_rows, ('scenario', 'criterion', 'weight')),
            f'{PANEL}/ranking.csv': (ranking, ('project_id', 'scenario', 'saw')),
        }
        if scope_decisions:
            csv_files['resource_scope_selection.csv'] = (scope_decisions, ('project_id', 'reason', 'locators'))
        for rel, (rows, fields) in csv_files.items():
            write_csv(root / rel, rows, fields)
        hashes = {p.relative_to(root).as_posix(): filehash(p) for p in root.rglob('*') if p.is_file()}
        summary = {'status': 'COMPLETED', 'run_id': name, 'cutoff': cutoff, 'code': code or {'commit': 'test'},
                   'configuration_sha256': digest(config), 'snapshot_sha256': digest(snapshots),
                   'logical_database_sha256': digest(json_files['logical_database.json']), 'output_hashes': hashes,
                   'r_results': {PANEL: {'status': 'COMPLETED', 'n': len(cohort)}}}
        (root / 'summary.json').write_text(canonical(summary) + '\n')
        return root

    def test_compares_and_classifies_criterion_and_cohort_changes(self):
        old = self.sealed_run('old', value=0.2, cohort=['p', 'q'])
        new = self.sealed_run('new', value=0.3, cohort=['p', 'q', 'r'], admitted=True)
        out = self.root / 'diff'
        result = compare(old, new, out, mode='admission_effect')
        self.assertEqual(result['comparison']['kind'], 'admission_effect')
        self.assertEqual(result['aim_b_rank_uncertainty'], {'status': 'NOT_RUN'})
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
        self.assertEqual(result['selection_differences'][0]['reason'],
                         'SAME_ESTIMATE_REPORTED_CONTAINED_REPLACES_CALCULATED')
        evidence = result['selection_differences'][0]['evidence']['updated']['selected_observations'][-1]
        self.assertEqual((evidence['source_sha'], evidence['locator']), ('test', 'physical page 5; row 2'))

    def test_rules_only_reports_retained_inactive_legacy_automatic_id(self):
        old_code = {'commit': 'old', 'content_sha256': 'old code'}
        new_code = {'commit': 'new', 'content_sha256': 'new code'}
        prior = {'obs_id': 'v1', 'entity_id': 'p', 'transform_version': 'automatic-resource-admission-v1'}
        old = self.sealed_run('old', value=0.3, cohort=['p', 'q'], admitted=True, automatic_id='v1',
                              admission_version=prior['transform_version'], code=old_code)
        new = self.sealed_run('new', value=0.3, cohort=['p', 'q'], admitted=True, automatic_id='v2',
                              admission_version='automatic-resource-admission-v2',
                              code=new_code, retained_observations=[prior], rules='new rules', path='after/only.pdf')
        result = compare(old, new, self.root / 'diff', mode='rule_effect')
        self.assertEqual(result['sources_changed'], [])
        self.assertEqual(result['comparison']['source_editions_changed'], [])
        self.assertEqual(result['comparison']['snapshot_record_differences'][0]['changed_fields'],
                         {'path': {'before': 'archive/report.pdf', 'after': 'after/only.pdf'}})
        self.assertEqual(result['comparison']['changed_factors'], ['code_or_admission_rules'])
        self.assertEqual(result['new_canonical_observation_ids'], ['v2'])
        ledger = result['admission']['updated']
        self.assertEqual(ledger['reused_legacy_observation_ids'], ['grade', 'ore'])
        self.assertEqual(ledger['inactive_automatic_observation_ids'], ['v1'])
        self.assertEqual(ledger['previously_enabled_not_current_ids'], ['v1'])
        self.assertEqual(ledger['previously_enabled_absent_from_updated_store_ids'], [])
        self.assertEqual(result['criterion_selection_counts']['provenance_or_disposition_only'], 1)

    def test_source_edition_change_requires_actual_editions_and_isolates_other_factors(self):
        code = {'commit': 'before', 'content_sha256': 'same code'}
        old = self.sealed_run('old', value=0.2, cohort=['p', 'q'], admitted=True,
                              code=code, source_sha='old edition', frame_pin='old edition')
        new = self.sealed_run('new', value=0.3, cohort=['p', 'q'], admitted=True,
                              code={**code, 'commit': 'after'}, source_sha='new edition',
                              frame_sha='second pin', frame_pin='new edition')
        result = compare(old, new, self.root / 'source-diff', mode='source_update')
        self.assertTrue(result['comparison']['code_commit_changed'])
        self.assertFalse(result['comparison']['code_content_changed'])
        self.assertEqual(result['comparison']['changed_factors'], ['source_inputs'])
        self.assertEqual(result['comparison']['source_editions_changed'][0]['changed_fields']['sha256'],
                         {'before': 'old edition', 'after': 'new edition'})
        mixed = self.sealed_run('mixed', value=0.3, cohort=['p', 'q'], admitted=True, source_sha='other edition',
                                code={**code, 'content_sha256': 'other code'},
                                frame_sha='other pin', frame_pin='other edition')
        with self.assertRaisesRegex(ValueError, 'REFRESH_COMPARISON_FACTORS_DO_NOT_MATCH'):
            compare(old, mixed, self.root / 'invalid', mode='source_update')
        result = compare(old, mixed, self.root / 'mixed-diff')
        self.assertEqual(result['comparison']['kind'], 'mixed_effects')
        self.assertEqual(result['comparison']['changed_factors'], ['code_or_admission_rules', 'source_inputs'])

    def test_unselected_repin_is_a_frame_change_with_no_source_edition_change(self):
        old = self.sealed_run('old', value=0.2, cohort=['p', 'q'], admitted=True, frame_pin='test')
        new = self.sealed_run('new', value=0.2, cohort=['p', 'q'], admitted=True,
                              frame_sha='second pin', frame_pin='other edition')
        result = compare(old, new, self.root / 'diff')
        self.assertEqual(result['comparison']['kind'], 'admission_frame_change')
        self.assertEqual(result['comparison']['source_editions_changed'], [])

    def test_inactive_prior_automatic_id_must_not_be_selected(self):
        old = self.sealed_run('old', value=0.2, cohort=['p', 'q'])
        new = self.sealed_run('new', value=0.2, cohort=['p', 'q'], admitted=True,
                              retained_observations=[{'obs_id': 'v1', 'transform_version': 'automatic-resource-admission-v1'}],
                              selected_ids=['ore', 'grade', 'v1'])
        with self.assertRaisesRegex(ValueError, 'REFRESH_INACTIVE_AUTOMATIC_OBSERVATION_SELECTED'):
            compare(old, new, self.root / 'diff')

    def test_rank_uncertainty_records_missing_draw_evidence_without_deltas(self):
        old = self.sealed_run('old', value=0.2, cohort=['p', 'q'])
        new = self.sealed_run('new', value=0.3, cohort=['p', 'q'], admitted=True)
        result = compare(old, new, self.root / 'diff', include_uncertainty=True)
        label = 'RESEARCH_OR_DRAW_CONTRACT_UNVERIFIED_OR_CHANGED'
        self.assertEqual(result['aim_b_rank_uncertainty']['draw_pairing_status_counts'], {label: 1})
        self.assertEqual(result['panels'][PANEL]['rank_uncertainty']['draw_pairing'], {'status': label})

    def test_weight_roundoff_is_equivalent_but_actual_values_and_row_order_are_not(self):
        rows = [{'scenario': 'x', 'criterion': 'R1', 'weight': 0.2},
                {'scenario': 'x', 'criterion': 'S1', 'weight': 0.8}]
        baseline = self.sealed_run('old', value=0.2, cohort=['p', 'q'], weight_rows=rows)
        new = self.sealed_run('new', value=0.3, cohort=['p', 'q'], admitted=True,
                              weight_rows=[{**rows[0], 'weight': 0.20000000000000004}, rows[1]])
        result = compare(baseline, new, self.root / 'equivalent', mode='admission_effect')
        self.assertFalse(result['panels'][PANEL]['weight_rows_identical'])
        weight = f'{PANEL}/weights.csv'
        self.assertNotEqual(result['input_artifact_sha256']['baseline'][weight],
                            result['input_artifact_sha256']['updated'][weight])
        for name, changed in (('values', [{**rows[0], 'weight': 0.3}, {**rows[1], 'weight': 0.7}]),
                              ('order', rows[::-1])):
            with self.subTest(name=name):
                invalid = self.sealed_run(name, value=0.3, cohort=['p', 'q'], admitted=True, weight_rows=changed)
                with self.assertRaisesRegex(ValueError, 'REFRESH_COMPARISON_CHANGED_CRITERIA_OR_WEIGHTS'):
                    compare(baseline, invalid, self.root / ('invalid-' + name), mode='admission_effect')

    def test_selection_exit_keeps_conflict_audit_and_previously_selected_observations(self):
        old = self.sealed_run('old', value=0.2, cohort=['p', 'q'])
        new = self.sealed_run('new', value=0.2, cohort=['p', 'q'], admitted=True, selected_ids=[], scope_decisions=[
            {'project_id': 'p', 'reason': 'CONCURRENT_SOURCE_CONFLICT', 'locators': 'p5 Table 1 and p6 Table 2'},
        ])
        result = compare(old, new, self.root / 'diff')
        change = result['selection_differences'][0]
        self.assertEqual(change['change_kind'], 'removed')
        self.assertEqual(change['reason'], 'RESOURCE_SCOPE_OR_ADMISSION_DECISION')
        self.assertEqual([row['obs_id'] for row in change['evidence']['baseline']['selected_observations']],
                         ['ore', 'grade'])
        self.assertEqual(change['evidence']['updated']['scope_decisions'][0]['reason'], 'CONCURRENT_SOURCE_CONFLICT')

    def test_rejects_receipt_from_another_run(self):
        old = self.sealed_run('old', value=0.2, cohort=['p', 'q'])
        new = self.sealed_run('new', value=0.3, cohort=['p', 'q'], admitted=True, bad_receipt=True)
        with self.assertRaisesRegex(ValueError, 'REFRESH_ADMISSION_RECEIPT_NOT_BOUND_TO_RUN'):
            compare(old, new, self.root / 'diff')
