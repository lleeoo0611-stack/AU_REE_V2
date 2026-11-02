import copy
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from au_ree_v2.acquisition import arcgis, select_snapshots, refresh
from au_ree_v2.analysis import score
from au_ree_v2.evidence import normalize, ingest_sources, ingest_claims, resource_values
from au_ree_v2.gis import nearest
from au_ree_v2.store import connect, digest, entity, logical_dump

ROOT=Path(__file__).resolve().parents[1]
CUTOFF='2026-11-02'

class CoreTests(unittest.TestCase):
    def setUp(self):
        self.work=ROOT/'work/tests'/uuid.uuid4().hex
        self.work.mkdir(parents=True)

    def db(self):
        db=connect(self.work/'test.sqlite');self.addCleanup(db.close);return db

    def claim(self):
        return json.loads((ROOT/'data/claims.json').read_text(encoding='utf-8'))['projects'][0]['observations'][0]

    def test_identity_stable_numeric_ids_and_entity_type(self):
        db=self.db()
        a=entity(db,'GA',123,'DEPOSIT')
        self.assertEqual(a,entity(db,'GA',123.0,'DEPOSIT'))
        self.assertNotEqual(a,entity(db,'OTHER',123,'DEPOSIT'))
        with self.assertRaises(ValueError):entity(db,'GA',123,'PROJECT')

    def test_no_missing_or_nonnumeric_imputation(self):
        for value in (None,'4.0',float('nan'),float('inf'),-1,True):
            c=self.claim();c['value']=value
            self.assertTrue(normalize(c))

    def test_basis_and_category_guards(self):
        for basis in ('THM','HM','MZEQ','REO','Y2O3'):
            c=self.claim();c['basis']=basis
            self.assertIn('NONCOMPARABLE_BASIS',normalize(c))
        for category in ('EXPLORATION_TARGET','RESERVE','UNVERIFIED'):
            c=self.claim();c['category']=category
            self.assertTrue(normalize(c))

    def test_grade_range_and_units(self):
        c=self.claim();c.update(variable='grade',value=101,unit='%')
        self.assertIn('GRADE_OUT_OF_RANGE',normalize(c))
        c.update(value=3,unit='kg/t')
        self.assertIn('UNSUPPORTED_GRADE_UNIT',normalize(c))

    def test_snapshot_cutoff_prevents_lookahead(self):
        self.assertEqual([],select_snapshots(ROOT,'2026-11-01'))
        self.assertEqual(4,len(select_snapshots(ROOT,CUTOFF)))

    def test_source_checksum_tampering_fails(self):
        shutil.copytree(ROOT/'data',self.work/'data')
        manifest=json.loads((self.work/'data/manifest.json').read_text())
        (self.work/manifest['snapshots'][0]['path']).write_text('corrupted')
        with self.assertRaisesRegex(ValueError,'checksum'):select_snapshots(self.work,CUTOFF)

    def test_incremental_replay_and_resource_rounding(self):
        db=self.db();snapshots=select_snapshots(ROOT,CUTOFF)
        ingest_sources(db,ROOT,snapshots);ingest_claims(db,ROOT,snapshots,CUTOFF)
        before=digest(logical_dump(db))
        ingest_sources(db,ROOT,snapshots);ingest_claims(db,ROOT,snapshots,CUTOFF)
        self.assertEqual(before,digest(logical_dump(db)))
        values=resource_values(db,CUTOFF,{s['sha256'] for s in snapshots})
        self.assertEqual(2,len(values))
        self.assertEqual([70.5,4389],sorted(r['contained_treo_kt'] for r in values.values()))
        self.assertEqual(2,db.execute('SELECT COUNT(*) FROM relations').fetchone()[0])
        # Explicit published totals are retained; rounded input products are not substituted.
        self.assertTrue(all(v['contained_treo_kt']!=v['calculated_from_rounded_inputs_kt'] for v in values.values()))

    def test_conflict_does_not_block_other_project(self):
        db=self.db();snapshots=select_snapshots(ROOT,CUTOFF)
        ingest_sources(db,ROOT,snapshots);ingest_claims(db,ROOT,snapshots,CUTOFF)
        row=dict(db.execute("SELECT * FROM observations WHERE variable='ore_mt' LIMIT 1").fetchone())
        original=row['entity_id'];row['obs_id']='conflict';row['value']+=2
        db.execute('INSERT INTO observations VALUES('+','.join('?'*16)+')',tuple(row.values()))
        ingest_claims(db,ROOT,snapshots,CUTOFF)
        result=resource_values(db,CUTOFF,{s['sha256'] for s in snapshots})
        self.assertEqual(1,len(result));self.assertNotIn(original,result)
        self.assertGreater(db.execute('SELECT COUNT(*) FROM review_queue').fetchone()[0],0)

    def test_arcgis_partial_or_duplicate_response_refused(self):
        replies=[{'objectIds':[1,2],'objectIdFieldName':'OBJECTID'},
                 {'features':[{'attributes':{'OBJECTID':1}}]}]
        with patch('au_ree_v2.acquisition.request',side_effect=[(json.dumps(r).encode(),{}) for r in replies]):
            with self.assertRaisesRegex(ValueError,'Incomplete'):arcgis('https://example.gov.au/0')

    def test_offline_update_failure_keeps_snapshots(self):
        shutil.copytree(ROOT/'data',self.work/'data')
        before=(self.work/'data/manifest.json').read_bytes()
        with patch('au_ree_v2.acquisition.request',side_effect=OSError('offline')):
            result=refresh(self.work,{'sources':[{'key':'test','url':'https://example.gov.au','kind':'pdf'}]})
        self.assertEqual('UNAVAILABLE',result[0]['status'])
        self.assertEqual(json.loads(before),json.loads((self.work/'data/manifest.json').read_text()))

    def test_projected_distance_and_invalid_geometry(self):
        point={'geometry':{'x':120,'y':-25}}
        self.assertAlmostEqual(0,nearest(120,-25,[point]))
        self.assertTrue(10<nearest(120.1,-25.1,[point])<20)
        with self.assertRaises(ValueError):nearest(120,-25,[])

    def test_fixed_anchors_no_cohort_rescaling(self):
        c=json.loads((ROOT/'config/research.json').read_text())['criteria'][0]
        self.assertEqual(0,score(0,c));self.assertEqual(1,score(5000,c))
        self.assertGreater(score(70,c),score(70,c,alternative=True))

    def test_dry_run_has_no_filesystem_side_effects(self):
        env={**os.environ,'PYTHONPATH':str(ROOT/'src')}
        result=subprocess.run([sys.executable,'-m','au_ree_v2','all','--root',str(ROOT),
              '--work',str(self.work/'absent'),'--as-of',CUTOFF,'--dry-run'],env=env,capture_output=True,text=True)
        self.assertEqual(0,result.returncode,result.stderr)
        self.assertFalse((self.work/'absent').exists())

    def test_clean_two_bootstraps_and_analysis_outputs_reproduce(self):
        env={**os.environ,'PYTHONPATH':str(ROOT/'src')}
        rscript=os.environ.get('RSCRIPT') or shutil.which('Rscript')
        windows=Path('C:/Program Files/R/R-4.5.2/bin/Rscript.exe')
        if not rscript and windows.exists():rscript=str(windows)
        outputs=[]
        for name in ('a','b'):
            command=[sys.executable,'-m','au_ree_v2','all','--root',str(ROOT),'--work',str(self.work/name),'--as-of',CUTOFF]
            command+=['--rscript',rscript] if rscript else ['--skip-r']
            result=subprocess.run(command,env=env,capture_output=True,text=True)
            self.assertEqual(0,result.returncode,result.stderr)
            outputs.append(json.loads(result.stdout))
        self.assertEqual(outputs[0]['logical_database_sha256'],outputs[1]['logical_database_sha256'])
        self.assertEqual({'DEPOSIT':149,'PROJECT':2},outputs[0]['census_by_kind'])
        if rscript:
            self.assertEqual('COMPLETED',outputs[0]['r_results']['resource_infrastructure_pilot']['status'])
            for key,value in outputs[0]['output_hashes'].items():
                self.assertEqual(value,outputs[1]['output_hashes'][key],key)

if __name__=='__main__':unittest.main()
