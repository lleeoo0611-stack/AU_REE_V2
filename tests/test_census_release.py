import csv
import sqlite3
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path

from au_ree_v2.acquisition import checked_snapshots
from au_ree_v2.census_audit import field_diagnosis, resource_statement_observations
from au_ree_v2.census_sensitivity import rank_variants
from au_ree_v2.cli import source_mode
from au_ree_v2.store import SCHEMA, canonical, filehash
from au_ree_v2.analysis import write_csv


class CensusReleaseTests(unittest.TestCase):
    def test_output_options_do_not_choose_source_mode(self):
        args = Namespace(module='all', refresh=False, snapshot_lock=None, out=None)
        self.assertEqual('legacy', source_mode(args))
        args.out = 'results/example'
        with self.assertRaisesRegex(ValueError, 'require an offline'):
            source_mode(args)
        args.static_pdfs = ['library']
        self.assertEqual('offline', source_mode(args))
        args.source_mode = 'live'
        with self.assertRaisesRegex(ValueError, 'cannot be combined'):
            source_mode(args)

    def test_replay_fallback_requires_exact_local_asset(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            originals = root/'originals'
            originals.mkdir()
            raw = originals/'input.pdf'
            raw.write_bytes(b'%PDF- example')
            sha = filehash(raw)
            asset = originals/sha
            raw.rename(asset)
            source = dict(key='sample', path='absent.pdf', sha256=sha, original_responses=[])
            restored = checked_snapshots(root, [source], '2026-11-13', replay_assets=originals)
            self.assertEqual(asset.resolve(), Path(restored[0]['path']))
            asset.write_bytes(b'wrong')
            with self.assertRaisesRegex(ValueError, 'checksum mismatch'):
                checked_snapshots(root, [source], '2026-11-13', replay_assets=originals)

    def test_rule_reason_distinguishes_partial_resource_and_page_verification(self):
        bundle = dict(source_sha256='a', statement_id='mre', scope='whole rock',
                      effective_date='2024-03-02', partial_resource_projection={'mode':'limited'})
        fields = {'resource_columns':['TREO'], 'annual_columns':[]}
        status, findings = field_diagnosis('TREO', 'RULE_INPUT_MISSING', [], [], bundle, '', fields)
        self.assertEqual('PARTIAL_RESOURCE_BASIS_OR_COMPONENTS', status)
        self.assertEqual('mre', findings[0]['statement']['statement_id'])
        status, _ = field_diagnosis('name', 'RULE_INPUT_MISSING',
                                    [{'reason':'MISSING_PAGE_OR_TWO_MARKERS'}], [], None, '', fields)
        self.assertEqual('PAGE_EVIDENCE_UNVERIFIED', status)

    def test_statement_view_distinguishes_source_scope_and_date(self):
        db = sqlite3.connect(':memory:')
        self.addCleanup(db.close)
        db.row_factory = sqlite3.Row
        db.executescript(SCHEMA)
        db.execute('INSERT INTO entities VALUES (?,?,?,?)', ('p','PROJECT','registry','one'))
        db.execute('INSERT INTO sources VALUES (?,?,?,?,?,?,?,?)',
                   ('sha','r','https://example.test','2025-05','2025-06-01','source','pdf','{}'))
        for oid, scope, basis in [('a','whole ore','TREO'),('b','whole ore','Nd2O3'),('c','concentrate','TREO')]:
            db.execute('INSERT INTO observations VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                (oid,'p','reported_resource_grades',1.,'ppm',basis,scope,'s','INDICATED','2025-05-01',
                 'sha','p2','AUTO_VALIDATED','[]',canonical({'material_basis':'RESOURCE_ORE_GRADE_OXIDE_PPM'}),'v1'))
        picked = dict(source_sha256='sha', statement_id='s', scope='whole ore', effective_date='2025-05-01')
        rows = {r['observation_id']:r for r in resource_statement_observations(
            db, {'p':[{'obs_id':c} for c in 'abc']}, {'p':picked})}
        self.assertEqual(rows['a']['statement_group_id'], rows['b']['statement_group_id'])
        self.assertNotEqual(rows['a']['statement_group_id'], rows['c']['statement_group_id'])
        self.assertEqual([1,1,0], [rows[c]['selected_for_census'] for c in 'abc'])
        self.assertEqual('MONTH', rows['a']['publication_date_precision'])
        self.assertFalse(db.execute("SELECT 1 FROM sqlite_master WHERE name='census_resource_observation'").fetchone())

    def test_gis_alternative_holds_cohort_and_reuses_scores(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            write_csv(out/'panel'/'criteria.csv', [{'code':'I4'}], ['code'])
            write_csv(out/'panel'/'weights.csv', [dict(scenario='base', criterion='I4', weight=1)],
                      ['scenario','criterion','weight'])
            write_csv(out/'panel'/'matrix.csv', [dict(project_id='x',I4=.8),dict(project_id='y',I4=.7)],
                      ['project_id','I4'])
            criterion = dict(code='I4', domain='Infrastructure', variable='port_distance_km',
                             low=0,high=100,direction='MIN',function='linear')
            config = dict(criteria=[criterion], promethee_threshold=.2)
            rank_variants(out, config, ['panel'], {('x','port_distance_km'):dict(
                status='COMPARED_ON_SAME_LAYER',baseline_km=20,alternative_km=40)})
            with (out/'census_gis_rank_sensitivity.csv').open(encoding='utf8',newline='') as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual(6, len(rows))
            self.assertEqual({('1','2')}, {(r['baseline_best'],r['alternative_best'])
                                          for r in rows if r['project_id']=='x'})
            self.assertEqual({'2'}, {r['cohort_size'] for r in rows})
