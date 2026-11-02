"""Regression tests for the legacy national selected source population."""
import tempfile
import unittest
from pathlib import Path
from au_ree_v2.acquisition import select_snapshots
from au_ree_v2.evidence import ingest_sources, resource_values
from au_ree_v2.national import national_candidate_rows, national_source_coverage, candidate_port_distances
from au_ree_v2.store import connect, digest, logical_dump

ROOT=Path(__file__).resolve().parents[1]
CUTOFF="2026-11-02"

class NationalSelectedTests(unittest.TestCase):
    def test_frozen_339_rows_do_not_auto_create_projects_or_duplicate_deposits(self):
        with tempfile.TemporaryDirectory() as tmp:
            db=connect(Path(tmp)/"national.sqlite")
            try:
                snaps=select_snapshots(ROOT,CUTOFF)
                ingest_sources(db,ROOT,snaps)
                source_shas={s["sha256"] for s in snaps}
                archive=next(s for s in snaps if s['key']=='legacy_national_e1_20261029')
                raw=(ROOT/archive['path']).read_text(encoding='utf-8')
                self.assertNotIn('access_token=',raw)
                self.assertEqual('714ae3649f1d7c9e5c9c0109241e7ebed5a7c83046fcc8d452c52b2e48b08643',archive['origin_selected_sha256'])
                rows=national_candidate_rows(db,source_shas)
                self.assertEqual(339,len(rows))
                self.assertEqual(2,db.execute("SELECT COUNT(*) FROM records WHERE raw LIKE '%NOT_SINGLE_LOCATION%'").fetchone()[0])
                self.assertEqual(317,sum(r["screening_status"]=="SCREENED_OFFICIAL_SOURCE_RECORD" for r in rows))
                self.assertEqual(22,sum(r["screening_status"]=="LEGACY_ONLY_NOT_OFFICIAL" for r in rows))
                self.assertEqual(366,db.execute("SELECT COUNT(*) FROM entities WHERE kind='SOURCE_RECORD'").fetchone()[0])
                self.assertEqual(149,db.execute("SELECT COUNT(*) FROM entities WHERE kind='DEPOSIT'").fetchone()[0])
                self.assertEqual(25,db.execute("SELECT COUNT(*) FROM entities WHERE kind='PROJECT'").fetchone()[0])
                self.assertEqual(0,len(resource_values(db,CUTOFF,source_shas)))
                self.assertTrue(all(r["record_kind"]=="SOURCE_RECORD" for r in rows))
                self.assertEqual(339,sum(r["source_records"] for r in national_source_coverage(rows)))
                self.assertGreaterEqual(db.execute("SELECT COUNT(*) FROM relations WHERE relation='SAME_NATIVE_GA_ENO_SOURCE_ONLY'").fetchone()[0],60)
                before=digest(logical_dump(db))
                ingest_sources(db,ROOT,snaps)
                self.assertEqual(before,digest(logical_dump(db)))
            finally:db.close()

    def test_nationwide_candidate_gis_never_populates_project_port_score(self):
        with tempfile.TemporaryDirectory() as tmp:
            db=connect(Path(tmp)/"national.sqlite")
            try:
                snaps=select_snapshots(ROOT,CUTOFF)
                ingest_sources(db,ROOT,snaps)
                db.execute("INSERT INTO runs VALUES(?,?,?,?,?,?,?,?)",
                           ("national-candidate","2026-11-02",CUTOFF,"{}","cfg","source","RUNNING",None))
                out=candidate_port_distances(db,ROOT,snaps,"national-candidate")
                self.assertEqual(339,len(out))
                n=sum(r["distance_km"] is not None for r in out)
                self.assertGreaterEqual(n,200)
                self.assertTrue(all(r["unit_of_analysis"]=="SOURCE_RECORD_NOT_PROJECT" for r in out))
                self.assertEqual(n,db.execute("SELECT COUNT(*) FROM derived WHERE variable='source_record_port_distance_km'").fetchone()[0])
                self.assertEqual(0,db.execute("SELECT COUNT(*) FROM derived WHERE variable='port_distance_km'").fetchone()[0])
                self.assertEqual([],candidate_port_distances(db,ROOT,
                    [s for s in snaps if s["key"]!="ga_ports"],"national-candidate"))
            finally:db.close()
