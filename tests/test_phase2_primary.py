import json,unittest,uuid
from pathlib import Path
from au_ree_v2.store import connect,digest,logical_dump
from au_ree_v2.evidence import ingest_sources,ingest_claims,resource_values
from au_ree_v2.acquisition import select_snapshots
from au_ree_v2.hierarchy import build
from au_ree_v2.gis import run
from au_ree_v2.official import domain_evidence_coverage,official_inventory,national_prospectus_inventory

ROOT=Path(__file__).resolve().parents[1]
class PrimaryExpansionTests(unittest.TestCase):
    def test_primary_expansion_hierarchy_and_four_layer_gis(self):
        work=ROOT/'work/tests'/uuid.uuid4().hex;work.mkdir(parents=True)
        db=connect(work/'canonical.sqlite')
        try:
            snaps=select_snapshots(ROOT,'2026-11-03');shas={s['sha256'] for s in snaps}
            ingest_sources(db,ROOT,snaps);ingest_claims(db,ROOT,snaps,'2026-11-03')
            values=resource_values(db,'2026-11-03',shas)
            self.assertEqual(5,len(values))
            for expected,actual in zip([7.35,70.5,201.768,1456.,4389.],sorted(v['contained_treo_kt'] for v in values.values())):
                self.assertAlmostEqual(expected,actual)
            rows=build(db,snaps)
            self.assertEqual(5,sum(r['relation']=='HAS_TECHNICALLY_DOCUMENTED_RESOURCE_SCOPE' for r in rows))
            self.assertTrue(any(r['child_kind']=='SITE' for r in rows))
            self.assertFalse(any(r['relation']=='HAS_TECHNICALLY_DOCUMENTED_RESOURCE_SCOPE' and r['parent_kind']=='PROJECT_CANDIDATE' for r in rows))
            before=digest(logical_dump(db));build(db,snaps);self.assertEqual(before,digest(logical_dump(db)))
            db.execute('INSERT INTO runs VALUES(?,?,?,?,?,?,?,?)',('test','now','2026-11-03','test','test','test','RUNNING',None))
            gis=run(db,ROOT,snaps,'test',values)
            self.assertEqual(5,len(gis))
            for metrics in gis.values():
                self.assertTrue({'road_distance_km','rail_distance_km','power_distance_km','port_distance_km'}<=metrics.keys())
                self.assertTrue(all(v['value']>=0 for v in metrics.values()))
            # NdPr is not the complete PrNdDyTb criterion; conditional credit is not financing maturity.
            rows=db.execute("SELECT variable,status FROM observations WHERE variable IN ('ndpr_share_pct','conditional_senior_debt_usd_m')").fetchall()
            self.assertEqual(2,len(rows));self.assertTrue(all(r['status']=='AUTO_VALIDATED' for r in rows))
            self.assertEqual(0,db.execute("SELECT COUNT(*) FROM observations WHERE variable='financing_ord'").fetchone()[0])
            self.assertEqual(54,db.execute("SELECT COUNT(*) FROM records WHERE source_sha=(SELECT sha FROM sources WHERE source_key='ga_critical')").fetchone()[0])
            coverage=domain_evidence_coverage(db,official_inventory(db,shas),values,gis,national_prospectus_inventory(db,shas),shas)
            self.assertTrue(all(r['project_name'] for r in coverage))
            self.assertEqual(2,sum(r['scorable'] for r in coverage if r['domain']=='Strategic'))
            self.assertEqual([],domain_evidence_coverage(db,[],{}, {},[],set()))
        finally:db.close()
