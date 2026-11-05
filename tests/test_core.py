import copy
import hashlib
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
from au_ree_v2.gis import nearest, representative_coordinate, run as run_gis
from au_ree_v2.spatial import bounding_window, project_windows, covered_project
from au_ree_v2.store import connect, digest, entity, logical_dump

ROOT=Path(__file__).resolve().parents[1]
CUTOFF='2026-11-02'

class CoreTests(unittest.TestCase):
    def setUp(self):
        self.work=ROOT/'work/tests'/uuid.uuid4().hex
        self.work.mkdir(parents=True)
        self.addCleanup(shutil.rmtree,self.work)

    def copy_data(self):
        # November2 fixtures do not need hundreds of MB of later government captures.
        manifest=json.loads((ROOT/'data/manifest.json').read_text(encoding='utf8'))
        allowed=set()
        for s in manifest['snapshots']:
            if s['available_date']<=CUTOFF and s.get('publication_date','')<=CUTOFF:
                allowed.add(Path(s['path']).name)
                allowed.update(Path(p['path']).name for p in s.get('original_responses',[]))
        def ignore(folder,names):
            return [n for n in names if n not in allowed] if Path(folder)==ROOT/'data/snapshots' else []
        shutil.copytree(ROOT/'data',self.work/'data',ignore=ignore)
        (self.work/'data/claims.json').write_text(json.dumps(self.frozen_claims()),encoding='utf8')

    def db(self):
        db=connect(self.work/'test.sqlite');self.addCleanup(db.close);return db

    def frozen_claims(self):
        from au_ree_v2.evidence import load_claims
        conf=json.loads((ROOT/'results/phase21-2026-11-05/configuration.json').read_text())
        return load_claims(ROOT,conf['claims_sha256'])[0]

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
        active=select_snapshots(ROOT,CUTOFF)
        self.assertTrue({'ga_aimr','ga_ports','mt_weld_2024','browns_range_2025'} <=
                        {s['key'] for s in active})

    def test_source_checksum_tampering_fails(self):
        self.copy_data()
        manifest=json.loads((self.work/'data/manifest.json').read_text())
        (self.work/manifest['snapshots'][0]['path']).write_text('corrupted')
        with self.assertRaisesRegex(ValueError,'checksum'):select_snapshots(self.work,CUTOFF)

    def test_incremental_replay_and_resource_rounding(self):
        db=self.db();snapshots=select_snapshots(ROOT,CUTOFF)
        ingest_sources(db,ROOT,snapshots);ingest_claims(db,ROOT,snapshots,CUTOFF,claims_data=self.frozen_claims())
        before=digest(logical_dump(db))
        ingest_sources(db,ROOT,snapshots);ingest_claims(db,ROOT,snapshots,CUTOFF,claims_data=self.frozen_claims())
        self.assertEqual(before,digest(logical_dump(db)))
        values=resource_values(db,CUTOFF,{s['sha256'] for s in snapshots})
        self.assertEqual(2,len(values))
        self.assertEqual([70.5,4389],sorted(r['contained_treo_kt'] for r in values.values()))
        self.assertEqual(2,db.execute("SELECT COUNT(*) FROM relations WHERE relation='REPRESENTATIVE_POINT_NOT_ENTITY_EQUIVALENCE'").fetchone()[0])
        # Explicit published totals are retained; rounded input products are not substituted.
        self.assertTrue(all(v['contained_treo_kt']!=v['calculated_from_rounded_inputs_kt'] for v in values.values()))

    def test_conflict_does_not_block_other_project(self):
        db=self.db();snapshots=select_snapshots(ROOT,CUTOFF)
        ingest_sources(db,ROOT,snapshots);ingest_claims(db,ROOT,snapshots,CUTOFF,claims_data=self.frozen_claims())
        row=dict(db.execute("SELECT * FROM observations WHERE variable='ore_mt' AND status='AUTO_VALIDATED' LIMIT 1").fetchone())
        original=row['entity_id'];row['obs_id']='conflict';row['value']+=2
        db.execute('INSERT INTO observations VALUES('+','.join('?'*16)+')',tuple(row.values()))
        ingest_claims(db,ROOT,snapshots,CUTOFF,claims_data=self.frozen_claims())
        result=resource_values(db,CUTOFF,{s['sha256'] for s in snapshots})
        self.assertEqual(1,len(result));self.assertNotIn(original,result)
        self.assertGreater(db.execute('SELECT COUNT(*) FROM review_queue').fetchone()[0],0)

    def test_new_document_version_retains_history_and_requires_new_extraction(self):
        self.copy_data()
        db=self.db();original=select_snapshots(self.work,CUTOFF)
        ingest_sources(db,self.work,original);ingest_claims(db,self.work,original,CUTOFF)
        before_ids={r[0] for r in db.execute('SELECT entity_id FROM entities')}
        path=self.work/'data/manifest.json';manifest=json.loads(path.read_text())
        source=next(s for s in manifest['snapshots'] if s['key']=='mt_weld_2024')
        revised=copy.deepcopy(source)
        raw=(self.work/source['path']).read_bytes()+b'\n% synthetic revised-byte test only\n'
        revised.update(path='data/snapshots/test-revised.pdf',sha256=hashlib.sha256(raw).hexdigest(),acquired_at='2026-11-02T23:59:59+00:00')
        (self.work/revised['path']).write_bytes(raw)
        manifest['snapshots'].append(revised);path.write_text(json.dumps(manifest))
        selected=select_snapshots(self.work,CUTOFF)
        ingest_sources(db,self.work,selected);ingest_claims(db,self.work,selected,CUTOFF)
        self.assertEqual(before_ids,{r[0] for r in db.execute('SELECT entity_id FROM entities')})
        self.assertEqual(len(original)+1,db.execute('SELECT COUNT(*) FROM sources').fetchone()[0])
        result=resource_values(db,CUTOFF,{s['sha256'] for s in selected})
        self.assertEqual(1,len(result))
        self.assertGreater(db.execute("SELECT COUNT(*) FROM review_queue WHERE reason='EXTRACTION_VERSION_MISMATCH'").fetchone()[0],0)

    def test_unreadable_one_pdf_does_not_block_other_project(self):
        db=self.db();snapshots=select_snapshots(ROOT,CUTOFF)
        ingest_sources(db,ROOT,snapshots)
        from pypdf import PdfReader
        def read(path):
            if 'mt_weld' in str(path):raise OSError('one unavailable document')
            return PdfReader(path)
        with patch.dict(os.environ,{'AU_REE_NATIVE_CACHE':str(self.work/'cold-native-pages')}),patch('pypdf.PdfReader',side_effect=read):
            ingest_claims(db,ROOT,snapshots,CUTOFF,claims_data=self.frozen_claims())
        result=resource_values(db,CUTOFF,{s['sha256'] for s in snapshots})
        self.assertEqual(1,len(result))
        self.assertGreater(db.execute("SELECT COUNT(*) FROM review_queue WHERE reason='EXTRACTION_READ_FAILED'").fetchone()[0],0)

    def test_arcgis_partial_or_duplicate_response_refused(self):
        replies=[{'objectIds':[1,2],'objectIdFieldName':'OBJECTID'},
                 {'features':[{'attributes':{'OBJECTID':1}}]}]
        with patch('au_ree_v2.acquisition.request',side_effect=[(json.dumps(r).encode(),{}) for r in replies]):
            with self.assertRaisesRegex(ValueError,'Incomplete'):arcgis('https://example.gov.au/0')

    def test_offline_update_failure_keeps_snapshots(self):
        self.copy_data()
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

    def test_project_aois_use_official_anchors_and_are_conservative(self):
        manifest=json.loads((ROOT/'data/manifest.json').read_text(encoding='utf-8'))
        windows=project_windows(ROOT,manifest,160)
        self.assertEqual(['2298466','browns-range','circle-valley','cowalinya','cummins-range','dubbo-project','goschen','jupiter','lyons','mangaroon','mons','mount-ridley-mia','mt-clere','mt-weld','narraburra','nolans-rare-earths-project','north-stanmore','redlings','salazar','splinter-rock','yangibana','yttria'],[w['project_id'] for w in windows])
        self.assertEqual(22,len(windows))
        for window in windows:
            self.assertEqual(160,window['radius_km'])
            lon,lat=window['longitude'],window['latitude']
            x1,y1,x2,y2=window['bbox']
            self.assertTrue(x1<lon<x2 and y1<lat<y2)
            self.assertEqual(window,covered_project({'queries':windows},window['project_id'],lon,lat))
            self.assertIsNone(covered_project({'queries':windows},window['project_id'],lon+.1,lat))
        with self.assertRaises(ValueError):bounding_window(0,0,160)

    def test_arcgis_scoped_inventories_and_deduplicated_union(self):
        windows=[{'project_id':'a','bbox':[119,-26,121,-24],'longitude':120,'latitude':-25,'radius_km':100},
                 {'project_id':'b','bbox':[120,-26,122,-24],'longitude':121,'latitude':-25,'radius_km':100}]
        feature=lambda oid:{'attributes':{'OBJECTID':oid},'geometry':{'x':120,'y':-25}}
        replies=[{'objectIds':[1,2],'objectIdFieldName':'OBJECTID'},
                 {'features':[feature(1),feature(2)]},
                 {'objectIds':[2,3],'objectIdFieldName':'OBJECTID'},
                 {'features':[feature(2),feature(3)]}]
        calls=[]
        def mocked(url,params=None,**kwargs):
            calls.append(params)
            return json.dumps(replies[len(calls)-1]).encode(),{}
        with patch('au_ree_v2.acquisition.request',side_effect=mocked):
            data=arcgis('https://example.gov.au/0',windows=windows)
        self.assertEqual(3,len(data['features']))
        self.assertEqual('registered_project_aoi',data['inventory']['scope'])
        self.assertEqual(2,len(data['inventory']['queries']))
        self.assertEqual([2,2],[q['id_count'] for q in data['inventory']['queries']])
        self.assertIn('geometry',calls[0]);self.assertIn('geometry',calls[2])

    def test_gis_refuses_uncovered_project_and_reused_future_coordinate(self):
        db=self.db();snapshots=select_snapshots(ROOT,CUTOFF)
        ingest_sources(db,ROOT,snapshots);ingest_claims(db,ROOT,snapshots,CUTOFF,claims_data=self.frozen_claims())
        resources=resource_values(db,CUTOFF,{s['sha256'] for s in snapshots})
        names={r['native_id']:r['entity_id'] for r in db.execute(
            "SELECT native_id,entity_id FROM entities WHERE kind='PROJECT'")}
        eid=names['mt-weld']
        real=representative_coordinate(db,eid,{s['sha256'] for s in snapshots})
        self.assertIsNotNone(real)
        db.execute('INSERT INTO sources VALUES(?,?,?,?,?,?,?,?)',
                   ('future','new','https://example.org','2027-01-01','2027-01-01','future.json','pdf','{}'))
        db.execute('INSERT INTO records VALUES(?,?,?,?,?,?,?,?,?)',
                   (eid,'future','Future relocation','WA',150,-10,None,None,'{}'))
        self.assertEqual(real,representative_coordinate(db,eid,{s['sha256'] for s in snapshots}))
        db.execute('INSERT INTO runs VALUES(?,?,?,?,?,?,?,?)',
                   ('scoped','2026-11-02',CUTOFF,'{}','x','y','RUNNING',None))
        data={'features':[{'geometry':{'x':real['longitude'],'y':real['latitude']}}],
              'spatialReference':{'wkid':4326},
              'inventory':{'complete':True,'where':'1=1','scope':'registered_project_aoi',
                           'queries':[{'project_id':'mt-weld','longitude':real['longitude'],
                                       'latitude':real['latitude'],'radius_km':100}]}}
        (self.work/'scoped.json').write_text(json.dumps(data),encoding='utf-8')
        live={'key':'scoped','kind':'arcgis_gis','sha256':'scope-sha','layer':'rail',
              'path':'scoped.json'}
        output=run_gis(db,self.work,[*filter(lambda s:s['kind']!='arcgis_gis',snapshots),live],
                       'scoped',resources)
        self.assertEqual([eid],list(output))
        self.assertAlmostEqual(0,output[eid]['rail_distance_km']['value'])
        self.assertEqual(1,db.execute(
            "SELECT COUNT(*) FROM review_queue WHERE reason='GIS_AOI_NOT_COVERED'").fetchone()[0])

    def test_official_workbook_discovery_does_not_fabricate_projects(self):
        from openpyxl import Workbook
        from au_ree_v2.census import ingest_workbook
        book=Workbook();sheet=book.active;sheet.title='Project listing'
        sheet.append(['Project','Commodity','State'])
        sheet.append(['Example REE Project','Rare earth elements','WA'])
        sheet.append(['Other metal','Iron ore','QLD'])
        loc=self.work/'official.xlsx';book.save(loc);book.close()
        snapshot={'key':'official','kind':'xlsx_census','url':'https://example.gov.au/off.xlsx',
                  'acquired_at':'2026-11-02T12:00:00+00:00','path':'official.xlsx',
                  'sha256':hashlib.sha256(loc.read_bytes()).hexdigest()}
        db=self.db();ingest_sources(db,self.work,[snapshot])
        self.assertEqual(1,db.execute("SELECT COUNT(*) FROM entities WHERE kind='SOURCE_RECORD'").fetchone()[0])
        self.assertEqual(0,db.execute("SELECT COUNT(*) FROM entities WHERE kind='PROJECT'").fetchone()[0])
        self.assertEqual(1,db.execute('SELECT COUNT(*) FROM records').fetchone()[0])
        original=digest(logical_dump(db))
        ingest_sources(db,self.work,[snapshot])
        self.assertEqual(original,digest(logical_dump(db)))

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
        frozen=self.work/'frozen-input';frozen.mkdir()
        (frozen/'snapshot_lock.json').write_text(json.dumps(select_snapshots(ROOT,CUTOFF)))
        shutil.copy2(ROOT/'results/phase21-2026-11-05/configuration.json',frozen/'configuration.json')
        outputs=[]
        for name in ('a','b'):
            command=[sys.executable,'-m','au_ree_v2','all','--root',str(ROOT),'--work',str(self.work/name),'--as-of',CUTOFF,'--snapshot-lock',str(frozen/'snapshot_lock.json')]
            command+=['--rscript',rscript] if rscript else ['--skip-r']
            result=subprocess.run(command,env=env,capture_output=True,text=True)
            self.assertEqual(0,result.returncode,result.stderr)
            outputs.append(json.loads(result.stdout))
        self.assertEqual(outputs[0]['logical_database_sha256'],outputs[1]['logical_database_sha256'])
        self.assertEqual(149,outputs[0]['census_by_kind']['DEPOSIT'])
        self.assertEqual(25,outputs[0]['census_by_kind']['PROJECT'])
        self.assertEqual(7,outputs[0]['national_advanced_ree_profile_rows'])
        self.assertEqual(20,outputs[0]['official_government_ree_resource_rows'])
        if rscript:
            self.assertEqual('COMPLETED',outputs[0]['r_results']['resource_infrastructure_pilot']['status'])
            execution=set(outputs[0].get('execution_artifacts',[]))
            self.assertEqual(execution,set(outputs[1].get('execution_artifacts',[])))
            for key,value in outputs[0]['output_hashes'].items():
                if key in execution:continue  # Actual execution/reuse differs, scientific CSVs must not.
                self.assertEqual(value,outputs[1]['output_hashes'][key],key)

if __name__=='__main__':unittest.main()
