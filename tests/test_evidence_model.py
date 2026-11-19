import json
import sqlite3
import unittest

from au_ree_v2.census import summary_resource_bundle
from au_ree_v2.evidence_model import SCHEMA_VERSION, ensure_read_model, migrate_evidence_model
from au_ree_v2.store import SCHEMA


class EvidenceModelMigrationTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(':memory:')
        self.addCleanup(self.db.close)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)
        self.db.execute("INSERT INTO entities VALUES ('p','PROJECT','registry','p')")
        self.db.execute("INSERT INTO entities VALUES ('q','DEPOSIT','registry','q')")
        self.db.execute("INSERT INTO sources VALUES ('sha','pdf','url','2024-02','2025','doc','pdf','{}')")
        self.db.execute("INSERT INTO relations VALUES ('pq','p','q','GOVERNMENT_PROJECT_CONTAINS_DEPOSIT','2026-11-03','sha','p3')")
        self.db.commit()

    def test_migration_repeated_preserves_dates_raw_ids_and_separates_reserves(self):
        for oid, kind in [('ore','MINERAL_RESOURCE'), ('reserve','ORE_RESERVE'), ('target','EXPLORATION_TARGET')]:
            raw = json.dumps(dict(resource_type=kind, cutoff_grade='400 ppm TREO', original_token='0.80',
                                  original_unit='%', effective_date_precision='MONTH', material_basis='RESOURCE_ORE_GRADE'))
            self.db.execute("INSERT INTO observations VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (oid,'p','reported_resource_grade',0.8,'%','TREO','deposit','table 1','TOTAL','2024-01',
                 'sha','p.4','AUTO_VALIDATED','[]',raw,'v0'))
        before = list(self.db.execute('SELECT obs_id,raw FROM observations ORDER BY obs_id'))
        self.db.commit()
        migrate_evidence_model(self.db)
        migrate_evidence_model(self.db)
        self.assertEqual(before,list(self.db.execute('SELECT obs_id,raw FROM observations ORDER BY obs_id')))
        self.assertEqual(SCHEMA_VERSION,self.db.execute('PRAGMA user_version').fetchone()[0])
        self.assertEqual(3,self.db.execute('SELECT COUNT(*) FROM resource_statement_editions').fetchone()[0])
        self.assertEqual([],self.db.execute('PRAGMA foreign_key_check').fetchall())
        rel = self.db.execute("SELECT * FROM relation_chronology").fetchone()
        self.assertIsNone(rel['relationship_effective_date'])
        self.assertEqual('2026-11-03', rel['legacy_reference_date'])
        self.assertEqual('0.80',self.db.execute('SELECT reported_token FROM resource_statement_facts LIMIT 1').fetchone()[0])

    def test_incomplete_migration_rolls_back_all_views_and_version(self):
        # A legacy user table conflicts with the second new model view.
        self.db.execute('CREATE TABLE resource_statement_editions (old_data TEXT)')
        self.db.execute("INSERT INTO resource_statement_editions VALUES ('keep')")
        self.db.commit()
        with self.assertRaises(sqlite3.OperationalError):
            migrate_evidence_model(self.db)
        self.assertEqual(0,self.db.execute('PRAGMA user_version').fetchone()[0])
        self.assertFalse(self.db.execute("SELECT name FROM sqlite_master WHERE name='resource_statement_facts'").fetchall())
        self.assertEqual('keep',self.db.execute('SELECT old_data FROM resource_statement_editions').fetchone()[0])

    def test_legacy_read_model_is_temporary(self):
        ensure_read_model(self.db)
        ensure_read_model(self.db)
        self.assertTrue(self.db.execute('SELECT count(*) FROM relation_chronology').fetchone()[0])
        self.assertEqual(0,self.db.execute('PRAGMA user_version').fetchone()[0])
        self.assertIsNone(self.db.execute("SELECT name FROM main.sqlite_schema WHERE name='relation_chronology'").fetchone())

    def test_census_does_not_pair_explicitly_different_classes_cutoffs_or_kinds(self):
        common = dict(source_sha='sha', statement_id='s', scope='ore', effective_date='2024',
                      category='INFERRED',status='AUTO_VALIDATED',basis='TREO',raw='{"cutoff_grade":"100 ppm TREO"}')
        ore = dict(common, variable='ore_mt', value=10,unit='Mt',obs_id='o')
        grade = dict(common, variable='grade', value=1,unit='%',obs_id='g')
        self.assertIsNotNone(summary_resource_bundle([ore,grade])[0])
        for replacement in [dict(raw='{"cutoff_grade":"300 ppm TREO"}'),dict(category='INDICATED'),
                            dict(raw='{"resource_type":"ORE_RESERVE"}'),dict(raw='{"resource_type":"EXPLORATION_TARGET"}'),
                            dict(raw='{"material_basis":"HEAVY_MINERAL_CONCENTRATE"}')]:
            with self.subTest(replacement=replacement):
                self.assertIsNone(summary_resource_bundle([ore,{**grade,**replacement}])[0])
