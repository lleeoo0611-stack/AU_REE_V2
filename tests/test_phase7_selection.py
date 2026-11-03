"""Real-document integration and adversarial scope/event selection contracts."""
import copy
import csv
import json
import unittest
import uuid
from pathlib import Path
from au_ree_v2.store import connect, digest, logical_dump, canonical
from au_ree_v2.evidence import ingest_sources, ingest_claims, ingest_events, resource_values
from au_ree_v2.studies import ingest, prepare as prepare_cases
from au_ree_v2.resolution import resolve as resolve_identity
from au_ree_v2.selection import resolve, choose, select_cases, date_end, source_check
from au_ree_v2.analysis import prepare
from au_ree_v2.official import domain_evidence_coverage
from au_ree_v2.hierarchy import build
from au_ree_v2.acquisition import select_snapshots

ROOT = Path(__file__).resolve().parents[1]


class SelectionRulesTests(unittest.TestCase):
    def candidate(self, **kw):
        return dict(evidence_id='a', source_sha256='s', effective_date='2025-01-01',
                    value=70, scope='ore-body-A', unit='%', basis='TREO', **kw)

    def test_newer_other_scope_never_replaces_existing_scope(self):
        a = self.candidate()
        b = dict(a, evidence_id='b', scope='ore-body-B', effective_date='2026-01-01')
        self.assertEqual((None, 'MULTIPLE_SCOPES_REQUIRE_DEFINITION'), choose([b, a]))

    def test_same_scope_revision_and_same_date_corroboration(self):
        a = self.candidate()
        b = dict(a, evidence_id='b', value=75, effective_date='2026-01-01')
        c = dict(b, evidence_id='c', source_sha256='s2')
        chosen, reason = choose([c, a, b, b])
        self.assertEqual('SELECTED', reason)
        self.assertEqual(75, chosen['value'])
        self.assertEqual(['b', 'c'], chosen['evidence_ids'])
        self.assertEqual(['s', 's2'], chosen['sources'])

    def test_concurrent_conflicting_values_are_missing_independent_of_order(self):
        a = self.candidate()
        b = dict(a, evidence_id='b', value=80)
        self.assertEqual((None, 'CONCURRENT_SOURCE_CONFLICT'), choose([a, b]))
        self.assertEqual(choose([a, b]), choose([b, a]))

    def test_endpoint_scale_and_units_remain_separate(self):
        a = self.candidate(endpoint='MREC', scale='PFS_MODEL')
        for field, value in [('endpoint', 'MINERAL_CONCENTRATE'), ('scale', 'BENCH'), ('unit', 'fraction')]:
            self.assertIsNone(choose([a, dict(a, **{field: value})])[0])

    def test_month_precision_uses_conservative_end_and_invalid_date_fails(self):
        self.assertEqual('2024-02-29', date_end('2024-02'))
        self.assertEqual('2024-12-31', date_end('2024'))
        self.assertIsNotNone(source_check(dict(publication_date='2024-02', available_date='2024-01-01'), '2024-02-01'))
        self.assertIsNotNone(source_check(dict(publication_date='2024-02-31'), '2025-01-01'))

    def test_qld_full_inventory_reuses_native_ids_without_promoting_projects(self):
        snapshots=select_snapshots(ROOT,'2026-11-03')
        source=next(s for s in snapshots if s['key']=='qld_minocc_status_live')
        data=json.loads((ROOT/source['path']).read_text())
        self.assertTrue(data['inventory']['complete'])
        self.assertEqual(21380,len(data['features']))
        self.assertEqual(44,len(source['original_responses']))
        folder=ROOT/'work/tests'/uuid.uuid4().hex;folder.mkdir(parents=True)
        db=connect(folder/'canonical.sqlite')
        try:
            old=next(s for s in snapshots if s['key']=='qld_minocc_live')
            ingest_sources(db,ROOT,[old])
            original={r['entity_id']:dict(r) for r in db.execute('SELECT * FROM entities')}
            ingest_sources(db,ROOT,[source])
            for eid,record in original.items():
                self.assertEqual(record,dict(db.execute('SELECT * FROM entities WHERE entity_id=?',(eid,)).fetchone()))
            sites=db.execute("SELECT count(*) FROM entities WHERE kind='SITE'").fetchone()[0]
            self.assertEqual(20,sites)
            self.assertEqual(0,db.execute("SELECT count(*) FROM entities WHERE kind='PROJECT'").fetchone()[0])
            before=digest(logical_dump(db));ingest_sources(db,ROOT,[source]);self.assertEqual(before,digest(logical_dump(db)))
        finally:db.close()


class Phase7IntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.work = ROOT/'work/tests'/uuid.uuid4().hex
        cls.work.mkdir(parents=True)
        cls.db = connect(cls.work/'canonical.sqlite')
        cls.snaps = json.loads((ROOT/'results/phase6-2026-11-03/snapshot_lock.json').read_text())
        cls.policy = json.loads((ROOT/'config/evidence_policy.json').read_text())
        ingest_sources(cls.db, ROOT, cls.snaps)
        ingest_claims(cls.db, ROOT, cls.snaps, '2026-11-03')
        cls.cases = ingest(cls.db, ROOT, cls.snaps, '2026-11-03')
        ingest_events(cls.db, ROOT, cls.snaps, '2026-11-03')
        build(cls.db, cls.snaps)
        cls.identity = resolve_identity(cls.db, ROOT, cls.snaps)
        cls.resources = resource_values(cls.db, '2026-11-03', {s['sha256'] for s in cls.snaps})
        cls.selection = cls.select()

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    @classmethod
    def select(cls, cutoff='2026-11-03', cases=None, policy=None):
        return resolve(cls.db, cls.snaps, cutoff, cls.resources,
                       cls.cases if cases is None else cases, cls.identity['mapping'],
                       cls.policy if policy is None else policy, ROOT)

    def pid(self, native):
        return self.db.execute('SELECT entity_id FROM entities WHERE native_id=? AND kind=?', (native, 'PROJECT')).fetchone()[0]

    def test_all_twelve_events_are_valid_null_numeric_originals(self):
        rows = self.db.execute("SELECT * FROM observations WHERE variable='commercial_event'").fetchall()
        self.assertEqual(12, len(rows))
        self.assertTrue(all(r['value'] is None and r['status'] == 'AUTO_VALIDATED' for r in rows), [dict(r) for r in rows if r['status'] != 'AUTO_VALIDATED'])
        self.assertEqual(0, self.db.execute("SELECT count(*) FROM observations WHERE variable IN ('financing_ord','recovery_pct')").fetchone()[0])

    def test_events_idempotent_and_original_ids_unchanged(self):
        before = digest(logical_dump(self.db))
        ingest_events(self.db, ROOT, self.snaps, '2026-11-03')
        self.assertEqual(before, digest(logical_dump(self.db)))
        original = json.loads((ROOT/'results/phase6-2026-11-03/logical_database.json').read_text(encoding='utf8'))
        self.assertEqual(original['entities'], logical_dump(self.db)['entities'])

    def test_all_nine_real_engineering_cases_have_scoped_queryable_parameters(self):
        raw = [c for c in self.selection['inventory'] if c['origin'] == 'STUDY_PARAMETER']
        self.assertEqual(40, len(raw))
        self.assertTrue(all(not c['reason'] for c in raw))
        self.assertEqual(9, len({c['case_id'] for c in raw}))
        for c in raw:
            self.assertTrue(c['unit'] and c['role'] and c['endpoint'] and c['scale'] and c['feed'])

    def test_only_browns_and_yangibana_share_concentrate_criteria(self):
        selected = self.selection['values']
        actual = {pid: c['TC1']['value'] for pid, c in selected.items() if 'TC1' in c}
        self.assertEqual({self.pid('browns-range'): 84, self.pid('yangibana'): 85.7}, actual)
        self.assertFalse(any('T1' in c for c in selected.values()))
        for native in ('jupiter', 'dubbo-project', 'cowalinya', 'circle-valley', '2298466'):
            self.assertNotIn('TC1', selected.get(self.pid(native), {}))
        self.assertTrue(any(c.get('role') == 'OVERALL_TO_CALCINED_MIXED_REO' and c['value'] == 68 for c in self.selection['inventory']))

    def test_finance_milestones_do_not_imply_cash_or_total_funding(self):
        expected = {'jupiter':0, 'yangibana':0, 'dubbo-project':1, 'nolans-rare-earths-project':2,
                    'goschen':2, 'donald-rare-earth-mineral-sands-project':2}
        for native, value in expected.items():
            self.assertEqual(value, self.selection['values'][self.pid(native)]['C1']['value'])
        self.assertFalse(any(c['C1']['value'] >= 3 for c in self.selection['values'].values() if 'C1' in c))
        goschen = self.selection['values'][self.pid('goschen')]['C1']
        self.assertEqual(2, len(goschen['evidence_ids']))
        offtake = [c for c in self.selection['inventory'] if c.get('contract_id') == 'goschen-iluka-rec']
        self.assertEqual({'TAKE_OR_PAY','TAKE_AND_PAY'}, {c['payment_terms'] for c in offtake})
        self.assertTrue(all(c['terms_conflict'] for c in offtake))
        self.assertTrue(all(c['comparison_status']=='OFFTAKE_PAYMENT_TERMS_CONFLICT_NOT_FINANCING_STATUS' for c in offtake))

    def _mutated_event(self, native, mutate):
        """Rollback a scientific fixture mutation after resolving actual data."""
        pid = self.pid(native)
        row = self.db.execute("SELECT * FROM observations WHERE entity_id=? AND variable='commercial_event' ORDER BY obs_id", (pid,)).fetchone()
        raw = json.loads(row['raw']); mutate(raw)
        self.db.execute('SAVEPOINT fixture')
        try:
            self.db.execute('UPDATE observations SET raw=? WHERE obs_id=?', (canonical(raw), row['obs_id']))
            return self.select()
        finally:
            self.db.execute('ROLLBACK TO fixture'); self.db.execute('RELEASE fixture')

    def test_company_funds_do_not_become_project_finance(self):
        result = self._mutated_event('dubbo-project', lambda r: r.update(attribution='COMPANY'))
        self.assertNotIn('C1', result['values'].get(self.pid('dubbo-project'), {}))
        self.assertIn('C1', result['values'][self.pid('goschen')])

    def test_expiry_and_unsupported_close_block_only_related_project(self):
        for mutation in (dict(valid_to='2025-01-01'), dict(finance_state='FINANCIAL_CLOSE', conditions_status='UNKNOWN')):
            result = self._mutated_event('dubbo-project', lambda r: r.update(mutation))
            self.assertNotIn('C1', result['values'].get(self.pid('dubbo-project'), {}))
            self.assertEqual(2, result['values'][self.pid('goschen')]['C1']['value'])

    def test_terminated_latest_instrument_does_not_resurrect_old_commitment(self):
        pid=self.pid('dubbo-project')
        row=dict(self.db.execute("SELECT * FROM observations WHERE entity_id=? AND variable='commercial_event'",(pid,)).fetchone())
        raw=json.loads(row['raw']);raw.update(finance_state='TERMINATED',effective_date='2026-01-01',event_id='test-termination')
        row.update(obs_id='test-termination',effective_date='2026-01-01',raw=canonical(raw))
        self.db.execute('SAVEPOINT fixture')
        try:
            self.db.execute('INSERT INTO observations VALUES('+','.join('?' for _ in row)+')',tuple(row.values()))
            result=self.select()
            self.assertNotIn('C1',result['values'].get(pid,{}))
            self.assertEqual(2,result['values'][self.pid('goschen')]['C1']['value'])
        finally:
            self.db.execute('ROLLBACK TO fixture');self.db.execute('RELEASE fixture')

    def test_strict_resource_selection_and_duplicate_evidence_are_stable(self):
        strict=resource_values(self.db,'2026-11-03',{s['sha256'] for s in self.snaps},strict=True)
        self.assertEqual(self.resources,strict)
        result=self.select(cases=self.cases+self.cases)
        self.assertEqual(self.selection['decisions'],result['decisions'])

    def test_bad_source_page_and_cross_entity_scope_are_local(self):
        pid=self.pid('dubbo-project')
        result=self._mutated_event('dubbo-project',lambda r:r.update(pdf_page=None))
        self.assertNotIn('C1',result['values'].get(pid,{}))
        self.assertEqual(2,result['values'][self.pid('goschen')]['C1']['value'])
        # No implicit roll-up from a deposit's or site's observations to a
        # PROJECT, even though their names or coordinates may agree.
        self.assertTrue(any(c['reason']=='NOT_PROJECT_IDENTITY_NO_AUTOMATIC_DEPOSIT_ROLLUP' for c in self.selection['inventory']))

    def test_documented_event_date_and_cutoff_are_independent(self):
        result = self.select('2026-07-01')
        self.assertNotIn('C1', result['values'].get(self.pid('goschen'), {}))
        self.assertNotIn('C1', result['values'].get(self.pid('jupiter'), {}))
        self.assertFalse(any('C1' in c for c in result['values'].values()))
        self.assertTrue(any(c['reason']=='SOURCE_AFTER_CUTOFF' for c in result['inventory']))

    def test_later_distinct_study_cannot_replace_earlier_scope(self):
        c = copy.deepcopy(next(c for c in self.cases if c['case_id'] == 'browns-dfs2025'))
        c.update(case_id='other-alternative', effective_date='2026-01-01')
        cases, excluded = select_cases(self.cases+[c], self.identity['mapping'], 'WHOLE_ORE|TREO_INCLUDING_Y|MINERAL_CONCENTRATE|DFS_MODEL')
        self.assertEqual(['yangibana-stage1-dfs2026'], [x['case_id'] for x in cases])
        self.assertEqual('MULTIPLE_SCOPES_REQUIRE_DEFINITION', excluded[0]['reason'])

    def test_no_new_data_keeps_all_legacy_panel_values_and_shared_coverage(self):
        cfg = json.loads((ROOT/'config/research.json').read_text())
        # Reuse frozen GIS values exactly; the test isolates evidence selection.
        with (ROOT/'results/phase6-2026-11-03/gis_metrics.csv').open() as f:
            gis = {}
            for r in csv.DictReader(f):
                gis.setdefault(r['entity_id'], {})[r['variable']] = dict(value=float(r['distance_km']))
        cfg['panels'].update(self.policy['panels'])
        result = prepare(self.db, '2026-11-03', self.snaps, self.resources, gis, cfg, self.work/'matrix',
                         canonical_ids=self.identity['mapping'], cases=self.cases, selection=self.selection)
        for panel in ('resource_infrastructure_pilot','issuer_resource_infrastructure','issuer_resource_composition','issuer_resource_study'):
            with (ROOT/f'results/phase6-2026-11-03/{panel}/matrix.csv').open() as f:before = list(csv.DictReader(f))
            with (self.work/f'matrix/{panel}/matrix.csv').open() as f:after = list(csv.DictReader(f))
            self.assertEqual(sorted(before,key=canonical), sorted(after,key=canonical), panel)
        self.assertEqual(1, result['panels']['issuer_resource_concentrate'])
        self.assertEqual(4, result['panels']['issuer_resource_financing_milestone'])
        rows = domain_evidence_coverage(self.db, [], self.resources, gis, selected_shas={s['sha256'] for s in self.snaps},
                                        selection=self.selection, prepared=result, criteria=cfg['criteria'])
        self.assertEqual(0, sum(r['scorable'] for r in rows if r['domain']=='Technical'))
        self.assertEqual(2, sum(r['exploratory_scorable'] for r in rows if r['domain']=='Technical'))
        self.assertEqual(6, sum(r['scorable'] for r in rows if r['domain']=='Commercial'))
        self.assertEqual(0, sum(r['development'] for r in result['coverage']))

    def test_legacy_configuration_keeps_old_semantics_and_no_events(self):
        # An explicit frozen configuration does not silently opt into new codes.
        config = json.loads((ROOT/'results/phase6-2026-11-03/configuration.json').read_text())['research']
        self.assertNotIn('evidence_resolution', config)
        self.assertNotIn('issuer_resource_financing_milestone', config['panels'])
        self.assertEqual(['ID','ROLE','WINDOW','JORC','PANEL','GIS_RELEASE'], json.loads((ROOT/'config/eligibility_compatibility.json').read_text())['upstream_policy']['C1_required_gates'])
        from au_ree_v2.cli import research_configuration
        from au_ree_v2.store import filehash
        folder=self.work/'tampered-policy';folder.mkdir(exist_ok=True)
        f=folder/'configuration.json';f.write_text(json.dumps({'research':config}))
        (folder/'summary.json').write_text(json.dumps({'output_hashes':{'configuration.json':filehash(f)}}))
        self.assertEqual(config,research_configuration(ROOT,folder/'snapshot_lock.json'))
        f.write_text('{}')
        with self.assertRaisesRegex(ValueError,'configuration checksum'):
            research_configuration(ROOT,folder/'snapshot_lock.json')


if __name__ == '__main__':
    unittest.main()
