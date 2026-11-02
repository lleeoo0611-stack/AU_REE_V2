import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from au_ree_v2.acquisition import select_snapshots
from au_ree_v2.evidence import ingest_sources, ingest_claims, resource_values
from au_ree_v2.official import ingest_official_table, official_inventory, exact_deposit_candidates, domain_evidence_coverage
from au_ree_v2.store import connect, digest, logical_dump

ROOT=Path(__file__).resolve().parents[1]
CUTOFF="2026-11-02"

class OfficialSourceTests(unittest.TestCase):
    def test_national_census_expanded_with_20_government_listed_wa_projects(self):
        with tempfile.TemporaryDirectory() as tmp:
            db=connect(Path(tmp)/"test.sqlite")
            try:
                snap=select_snapshots(ROOT,CUTOFF)
                ingest_sources(db,ROOT,snap)
                self.assertEqual(149,db.execute("SELECT COUNT(*) FROM entities WHERE kind='DEPOSIT'").fetchone()[0])
                self.assertEqual(25,db.execute("SELECT COUNT(*) FROM entities WHERE kind='PROJECT'").fetchone()[0])
                inventory=official_inventory(db,{s["sha256"] for s in snap})
                self.assertEqual(20,len(inventory))
                self.assertEqual(366,db.execute("SELECT COUNT(*) FROM entities WHERE kind='SOURCE_RECORD'").fetchone()[0])
                self.assertEqual(60,db.execute("SELECT COUNT(*) FROM observations WHERE status='OFFICIAL_SUMMARY_SCOPE_UNVERIFIED'").fetchone()[0])
                self.assertEqual({},resource_values(db,CUTOFF,{s["sha256"] for s in snap}))
                self.assertEqual(4649,next(r for r in inventory if r["project_name"]=="Mt Weld")["contained_treo_kt"])
                before=digest(logical_dump(db))
                ingest_sources(db,ROOT,snap)
                self.assertEqual(before,digest(logical_dump(db)))
                ingest_claims(db,ROOT,snap,CUTOFF)
                resources=resource_values(db,CUTOFF,{s["sha256"] for s in snap})
                self.assertEqual(2,len(resources))
                self.assertEqual([70.5,4389],sorted(x["contained_treo_kt"] for x in resources.values()))
                self.assertEqual(0,db.execute("SELECT COUNT(*) FROM observations WHERE status='AUTO_VALIDATED' AND transform_version='wa-government-summary-v1'").fetchone()[0])
                self.assertEqual(2,db.execute("SELECT COUNT(*) FROM relations WHERE relation='REPRESENTATIVE_POINT_NOT_ENTITY_EQUIVALENCE'").fetchone()[0])
                self.assertEqual(20,db.execute("SELECT COUNT(*) FROM relations WHERE relation='LISTED_AS_PROJECT_NOT_DEPOSIT_EQUIVALENCE'").fetchone()[0])
                coverage=domain_evidence_coverage(db,inventory,resources,{})
                self.assertEqual(150,len(coverage))
                self.assertEqual(0,sum(x["scorable"] for x in coverage if x["domain"] in ("Strategic","Technical","Development","Commercial")))
                self.assertEqual(18,sum(x["evidence_state"]=="OFFICIAL_SUMMARY_ONLY" for x in coverage))
                candidates=exact_deposit_candidates(db,inventory,{s["sha256"] for s in snap})
                self.assertGreaterEqual(len(candidates),5)
                self.assertTrue(all(x["status"]=="UNVERIFIED_LINK_NO_GIS_RELEASE" for x in candidates))
            finally:db.close()


    def test_national_official_profiles_cross_state_and_ownership(self):
        from au_ree_v2.official import national_prospectus_inventory
        with tempfile.TemporaryDirectory() as tmp:
            db=connect(Path(tmp)/"profiles.sqlite")
            try:
                snap=select_snapshots(ROOT,CUTOFF)
                ingest_sources(db,ROOT,snap)
                profiles=national_prospectus_inventory(db,{s["sha256"] for s in snap})
                self.assertEqual(7,len(profiles))
                self.assertEqual({"WA","VIC","NSW","NT"},{r["state"] for r in profiles})
                self.assertEqual(25,db.execute("SELECT COUNT(*) FROM entities WHERE kind='PROJECT'").fetchone()[0])
                self.assertEqual(7,db.execute("SELECT COUNT(*) FROM relations WHERE relation='LISTED_IN_NATIONAL_PROSPECTUS'").fetchone()[0])
                self.assertEqual(0,db.execute("SELECT COUNT(*) FROM observations WHERE transform_version='austrade-v1'").fetchone()[0])
                coverage=domain_evidence_coverage(db,official_inventory(db,{s["sha256"] for s in snap}),{}, {},profiles)
                self.assertTrue(any(r["domain"]=="Technical" and r["evidence_state"]=="AUSTRADE_DESCRIPTIVE_ONLY" for r in coverage))
                self.assertTrue(all(r["scorable"]==0 for r in coverage))
                self.assertEqual(0,db.execute("SELECT COUNT(*) FROM entities WHERE kind='PROJECT' AND native_id='browns-range-heavy-rare-earths-hre'").fetchone()[0])
            finally:db.close()


    def test_global_deposit_port_distances_are_not_project_scores(self):
        from au_ree_v2.gis import national_deposit_port_distances, deposit_type_port_summary
        with tempfile.TemporaryDirectory() as tmp:
            db=connect(Path(tmp)/"deposit_gis.sqlite")
            try:
                snapshots=select_snapshots(ROOT,CUTOFF)
                ingest_sources(db,ROOT,snapshots)
                db.execute("INSERT INTO runs VALUES(?,?,?,?,?,?,?,?)",
                           ("ga-descriptive","2026-11-02",CUTOFF,"{}","config","snapshot","RUNNING",None))
                rows=national_deposit_port_distances(db,ROOT,snapshots,"ga-descriptive")
                self.assertEqual(149,len(rows))
                self.assertTrue(all(r["distance_km"] is None or r["distance_km"]>=0 for r in rows))
                self.assertGreaterEqual(sum(r["distance_km"] is not None for r in rows),140)
                self.assertTrue(all(r["interpretation"].startswith("Deposit locality") for r in rows))
                categories=deposit_type_port_summary(rows)
                self.assertEqual(149,sum(g["deposits_total"] for g in categories))
                self.assertTrue(all(g["unit_of_analysis"]=="GA_DEPOSIT_NOT_MCDA_PROJECT" for g in categories))
                self.assertEqual(0,db.execute("SELECT COUNT(*) FROM derived WHERE variable='port_distance_km'").fetchone()[0])
                self.assertGreater(db.execute("SELECT COUNT(*) FROM derived WHERE variable='deposit_port_distance_km'").fetchone()[0],0)
                db.execute("DELETE FROM derived")
                missing=national_deposit_port_distances(db,ROOT,
                         [s for s in snapshots if s["key"]!="ga_ports"],"ga-descriptive")
                self.assertEqual([],missing)
            finally:db.close()

    def test_transcription_tamper_and_invalid_input_cannot_promote_resource(self):
        with tempfile.TemporaryDirectory() as tmp:
            db=connect(Path(tmp)/"test.sqlite")
            try:
                source=next(s for s in select_snapshots(ROOT,CUTOFF) if s["key"]=="wa_dmpe_ree_2026_table")
                data=(ROOT/source["path"]).read_bytes()
                p=Path(tmp)/"table.csv";p.write_bytes(data+b"\n")
                revised={**source,"path":"table.csv"}
                with self.assertRaisesRegex(ValueError,"checksum"):
                    ingest_official_table(db,tmp,revised)
                revised["sha256"]=hashlib.sha256(p.read_bytes()).hexdigest()
                db.execute("INSERT INTO sources VALUES(?,?,?,?,?,?,?,?)",
                           (revised["sha256"],revised["key"],revised["url"],revised["publication_date"],
                            revised["acquired_at"],revised["path"],revised["kind"],"{}"))
                p.write_text("row,project,status,owner,ore_mt,grade_pct,contained_treo_kt,resource_date\n1,Test,Feasibility,Owner,10,1,999,01/01/2025\n")
                revised["sha256"]=hashlib.sha256(p.read_bytes()).hexdigest()
                db.execute("INSERT INTO sources VALUES(?,?,?,?,?,?,?,?)",
                           (revised["sha256"],revised["key"],revised["url"],revised["publication_date"],
                            revised["acquired_at"],revised["path"],revised["kind"],"{}"))
                self.assertEqual(0,ingest_official_table(db,tmp,revised))
                self.assertEqual(0,db.execute("SELECT COUNT(*) FROM entities WHERE kind='PROJECT'").fetchone()[0])
                self.assertEqual(1,db.execute("SELECT COUNT(*) FROM review_queue WHERE reason='OFFICIAL_TABLE_ROW_INVALID'").fetchone()[0])
            finally:db.close()
