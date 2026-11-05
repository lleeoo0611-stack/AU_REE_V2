"""Native candidate work, source/coding views and shared method draw contracts."""
import csv,json,shutil,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from au_ree_v2.store import connect,entity,canonical,digest,filehash
from au_ree_v2.discovery import official_query,search_tasks
from au_ree_v2.acquisition import arcgis,select_snapshots
from au_ree_v2.selection import current_evidence_view

ROOT=Path(__file__).resolve().parents[1]


class Phase22(unittest.TestCase):
    def test_current_aliases_and_derived_wa_rows_do_not_reuse_old_coding(self):
        db=connect(':memory:')
        try:
            db.execute('INSERT INTO sources VALUES(?,?,?,?,?,?,?,?)',('s','s','https://example.invalid',None,'2026-11-05','fixture','historical_e1_candidates','{}'))
            eid=entity(db,'SOURCE','1','SOURCE_RECORD');site=entity(db,'WA_MINDEX_SITE','S1','SITE')
            raw=dict(source_key='STATE_WA_MINDEX',original_attributes=dict(site_code='S1',short_name='Original site',proj_code='P1'))
            db.execute('INSERT INTO records VALUES(?,?,?,?,?,?,?,?,?)',(eid,'s','source','WA',None,None,None,None,canonical(raw)))
            db.execute('INSERT INTO records VALUES(?,?,?,?,?,?,?,?,?)',(site,'s','old placeholder','WA',None,None,None,None,canonical(dict(role='NATIVE_GOVERNMENT_RECORDED_LOCATION_NOT_MINING_FOOTPRINT'))))
            claims=dict(projects=[dict(id='p',name='Current project',aliases=['Current alias'])])
            v=current_evidence_view(db,[dict(sha256='s')],'2026-11-05',set(),claims_data=claims)
            self.assertIn((site,'s'),v['record_ids']);self.assertEqual('Original site',v['record_values'][site,'s']['name'])
            self.assertEqual(['Current project','Current alias'],v['project_aliases']['AU-'+digest(['project_registry_v1','p'])[:20]])
            self.assertEqual('old placeholder',db.execute('SELECT name FROM records WHERE entity_id=?',(site,)).fetchone()[0])
        finally:db.close()

    def test_current_records_exclude_old_native_placeholders_and_blank_parent(self):
        db=connect(':memory:')
        try:
            db.execute('INSERT INTO sources VALUES(?,?,?,?,?,?,?,?)',('s','s','https://example.invalid',None,'2026-11-05','fixture','historical_e1_candidates','{}'))
            old=entity(db,'OLD_NATIVE','1','SITE');blank=entity(db,'WA_MINDEX_PROJECT',' ','PROJECT_CANDIDATE')
            keep=entity(db,'SOURCE','1','SOURCE_RECORD')
            for eid,raw in [(old,dict(role='NATIVE_GOVERNMENT_RECORDED_LOCATION_NOT_MINING_FOOTPRINT')),
                (blank,dict(status='GOVERNMENT_PARENT_CODE_NOT_TECHNICALLY_VALIDATED',proj_code=' ')),
                (keep,dict(source_kind='LEGACY_NATIONAL_E1_SELECTED_FEATURE'))]:
                db.execute('INSERT INTO records VALUES(?,?,?,?,?,?,?,?,?)',(eid,'s','x','WA',None,None,None,None,canonical(raw)))
            v=current_evidence_view(db,[dict(sha256='s')],'2026-11-05',set())
            self.assertEqual({(keep,'s')},v['record_ids'])
            from au_ree_v2.hierarchy import link,rows
            link(db,blank,keep,'GOVERNMENT_PROJECT_SITE_MEMBERSHIP','s','blank native parent is not a Project')
            self.assertEqual([],rows(db,[dict(sha256='s',available_date='2026-11-05')],v))
            self.assertEqual(3,db.execute('SELECT COUNT(*) FROM records').fetchone()[0])
        finally:db.close()

    def test_parent_export_does_not_depend_on_first_inserted_child(self):
        from au_ree_v2.national import live_government_inventory
        db=connect(':memory:')
        try:
            db.execute('INSERT INTO sources VALUES(?,?,?,?,?,?,?,?)',('s','s','https://example.invalid',None,'2026-11-05','fixture','government_json','{}'))
            eid=entity(db,'WA_MINDEX_PROJECT','P1','PROJECT_CANDIDATE')
            for child in ('REE prospect','Sc deposit'):
                raw=dict(source_kind='LIVE_GOVERNMENT_PROJECT_PARENT',project_code='P1',original_attributes={'site_title':child})
                db.execute('INSERT OR REPLACE INTO records VALUES(?,?,?,?,?,?,?,?,?)',(eid,'s','Parent','WA',None,None,None,None,canonical(raw)))
                got=live_government_inventory(db,[dict(sha256='s',key='live',national_government=True)],dict(record_ids={(eid,'s')}))
                self.assertEqual({'project_code':'P1','project_name':'Parent'},json.loads(got[0]['original_attributes']))
        finally:db.close()

    def test_resource_rebinding_filters_old_source_even_when_scope_id_is_stable(self):
        from au_ree_v2.hierarchy import build,rows
        db=connect(':memory:')
        try:
            for sha in ('old','new'):
                db.execute('INSERT INTO sources VALUES(?,?,?,?,?,?,?,?)',(sha,sha,'https://example.invalid',None,'2026-11-05','fixture','pdf','{}'))
            pid=entity(db,'project_registry_v1','test','PROJECT')
            for sha in ('old','new'):
                db.execute('INSERT INTO observations VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(sha,pid,'ore_mt',1.,'Mt','TREO','Same scope','Same statement','INFERRED','2026-01-01',sha,'p1','AUTO_VALIDATED','[]','{}','normalization-v1'))
            snaps=[dict(sha256=s,available_date='2026-11-05') for s in ('old','new')]
            build(db,snaps)
            v=current_evidence_view(db,snaps,'2026-11-05',{'new'});scope='AU-'+digest(['PRIMARY_RESOURCE_SCOPE','Same statement|Same scope'])[:20]
            self.assertNotIn((scope,'old'),v['record_ids']);self.assertIn((scope,'new'),v['record_ids'])
            self.assertEqual(['new'],[r['source_sha'] for r in rows(db,snaps,v)])
            self.assertEqual(2,db.execute('SELECT COUNT(*) FROM relations').fetchone()[0])
        finally:db.close()

    def test_cited_foreign_dfs_is_not_kennedy_development_evidence(self):
        from au_ree_v2.pdf_extract import narrative_context_issues
        text='Kennedy testwork. Ionic Rare Earth Limited announcement dated20March2023 titled: “Makuutu Stage 1 DFS Confirms Technical Viability”.'
        candidate=dict(kind='SCOPED_TEXT_DISCLOSURE',domain='Development',raw_text=text)
        self.assertIn('CITED_STUDY_SCOPE_NOT_ESTABLISHED_FOR_THIS_PROJECT',narrative_context_issues(candidate,dict(text=text),'scientific-context-v5-peer-boundary',['Kennedy']))
        self.assertEqual([],narrative_context_issues(candidate,dict(text=text),'scientific-context-v4-column-binding',['Kennedy']))
        candidate['raw_text']='Issuer announcement titled: “Kennedy Scoping Study completed”.'
        self.assertEqual([],narrative_context_issues(candidate,dict(text=candidate['raw_text']),'scientific-context-v5-peer-boundary',['Kennedy']))

    def test_v3_sc_symbols_have_context_and_v2_is_replayable(self):
        from au_ree_v2.census import classify_ree
        self.assertEqual('SC_ONLY',classify_ree({'commodity':'Ni, Sc'},['commodity'])['role'])
        self.assertFalse(classify_ree({'commodity':'Ni, Sc'},['commodity'],'ree-candidate-v2')['include'])
        self.assertFalse(classify_ree({'description':'B Sc Hons thesis, copper mineralisation'})['include'])
        self.assertEqual('MENTION_ONLY',classify_ree({'description':'mineralisation with significant La, Y'})['role'])

    def test_explicit_page_artifact_precedes_unavailable_native_backend(self):
        from au_ree_v2.evidence import validate_pages
        with tempfile.TemporaryDirectory(dir=ROOT/'work') as tmp:
            root=Path(tmp);original=root/'original.pdf';original.write_bytes(b'%PDF retained test bytes')
            sha=filehash(original);page=root/'page.json'
            payload=dict(source_sha256=sha,physical_page=2,status='EXTRACTED_REQUIRES_SCOPE_VALIDATION',text='Total  7.3\n0.96')
            page.write_text(json.dumps(payload));artifact=dict(key='page',sha256=filehash(page),path=page.name)
            source=dict(sha256=sha,path=original.name,kind='pdf')
            evidence=dict(source_sha256=sha,pdf_page=2,page_markers=['Total 7.3 0.96'],page_extraction_key='page',page_extraction_sha256=artifact['sha256'],marker_normalization='WHITESPACE_ONLY_V1')
            with patch('pypdf.PdfReader',side_effect=AssertionError('Native backend must not be opened')):
                validate_pages(root,source,evidence,[artifact])
            payload['physical_page']=3;page.write_text(json.dumps(payload));artifact['sha256']=filehash(page);evidence['page_extraction_sha256']=artifact['sha256']
            with self.assertRaisesRegex(ValueError,'BINDING_FAILED'):validate_pages(root,source,evidence,[artifact])

    def test_percent_to_ppm_conversion_rejects_other_resource_scope(self):
        from au_ree_v2.evidence import transformation_issues
        common=dict(scope='Wolverine',statement_id='MRE',effective_date='2025-01-15',source_key='original',source_sha256='sha',locator='p5',category='INFERRED')
        grade=dict(common,variable='grade',value=.96,unit='%',basis='TREO')
        converted=dict(common,variable='normalized_resource_treo_ppm',value=9600,unit='ppm',basis='TREO',transform=dict(rule='REO_GRADE_PERCENT_TO_PPM',inputs=['grade']))
        self.assertEqual([],transformation_issues(converted,[grade,converted]))
        grade['scope']='Underground only'
        self.assertTrue(transformation_issues(converted,[grade,converted]))

    def test_same_source_different_candidate_rules_have_distinct_current_views(self):
        db=connect(':memory:')
        try:
            db.execute('INSERT INTO sources VALUES(?,?,?,?,?,?,?,?)',('s','native','https://example.invalid',None,'2026-11-05','fixture','government_csv','{}'))
            eid=entity(db,'WA_SITE','S1','SITE')
            raw=canonical(dict(source_kind='LIVE_GOVERNMENT_NATIVE_RECORD',original_attributes={'commodity':'Sc'}))
            db.execute('INSERT INTO records VALUES(?,?,?,?,?,?,?,?,?)',(eid,'s','Sc site','WA',None,None,None,None,raw))
            source=dict(sha256='s',national_government=True,commodity_fields=['commodity'])
            a=current_evidence_view(db,[source],'2026-11-05',set(),candidate_version='ree-candidate-v2')
            b=current_evidence_view(db,[source],'2026-11-05',set(),candidate_version='ree-candidate-v3')
            self.assertNotIn((eid,'s'),a['record_ids']);self.assertIn((eid,'s'),b['record_ids'])
            self.assertEqual(1,db.execute('SELECT COUNT(*) FROM records').fetchone()[0])
        finally:db.close()

    def test_ckan_resume_preserves_query_and_page_boundary(self):
        from au_ree_v2.acquisition import ckan
        starts=[]
        def fetch(url,params):
            starts.append(params['start']);ids=list(range(params['start'],min(params['start']+params['rows'],5)))
            return json.dumps(dict(success=True,result=dict(count=5,results=[dict(id=str(i)) for i in ids]))).encode(),{}
        first=ckan('https://example.invalid','REE',2,1,fetch,start_offset=0)
        self.assertFalse(first['inventory']['complete'])
        second=ckan('https://example.invalid','REE',2,2,fetch,start_offset=2)
        self.assertEqual([0,2,4],starts);self.assertTrue(second['inventory']['complete'])

    def test_missing_publication_date_is_not_crash_or_invented_date(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'work') as tmp:
            root=Path(tmp);(root/'data').mkdir();p=root/'original';p.write_text('retained')
            s=dict(key='html',kind='html',publication_date=None,available_date='2026-11-05',
                acquired_at='2026-11-05T00:00:00Z',path='original',sha256=filehash(p))
            (root/'data/manifest.json').write_text(json.dumps(dict(snapshots=[s])))
            self.assertEqual([s],select_snapshots(root,'2026-11-05'))
            self.assertEqual([],select_snapshots(root,'2026-11-04'))

    def test_workbook_uses_shared_context_classification_not_project_promotion(self):
        from openpyxl import Workbook
        from au_ree_v2.census import ingest_workbook,CANDIDATE_VERSION
        with tempfile.TemporaryDirectory(dir=ROOT/'work') as tmp:
            root=Path(tmp);p=root/'original.xlsx';w=Workbook();s=w.active
            s.append(['Project','State','Commodity']);s.append(['Cerium site','WA','Cerium'])
            s.append(['Mineral site','TAS','Monazite']);s.append(['False ticker','NSW','Iron'])
            w.save(p);db=connect(':memory:')
            source=dict(key='remp',path=p.name,sha256=filehash(p))
            db.execute('INSERT INTO sources VALUES(?,?,?,?,?,?,?,?)',(source['sha256'],'remp','https://example.invalid',None,'2026-11-05',p.name,'xlsx_census','{}'))
            try:
                self.assertEqual(2,ingest_workbook(db,root,source,CANDIDATE_VERSION))
                self.assertEqual(2,ingest_workbook(db,root,source,CANDIDATE_VERSION))
                self.assertEqual(2,db.execute('SELECT COUNT(*) FROM records').fetchone()[0])
                self.assertEqual(0,db.execute("SELECT COUNT(*) FROM entities WHERE kind='PROJECT'").fetchone()[0])
                roles=[json.loads(r[0])['candidate_classification']['role'] for r in db.execute('SELECT raw FROM records')]
                self.assertEqual(['REE_ELEMENT','MINERAL_ONLY'],roles)
            finally:db.close()

    def test_dynamic_query_uses_new_alias_and_requires_reason_for_year_floor(self):
        source=dict(dynamic_candidates=True)
        query=official_query(source,[dict(state='WA',aliases=["O'Brien New Prospect"])])
        self.assertIn("O''BRIEN NEW PROSPECT",query);self.assertNotIn('2015',query)
        self.assertIsNone(official_query(source,[dict(state='QLD',aliases=['Kennedy'])]))
        with self.assertRaisesRegex(ValueError,'RATIONALE'):official_query(dict(source,year_from=2020),[])

    def test_arcgis_resume_is_complete_only_after_remaining_ids_exhausted(self):
        def fetch(url,p):
            d={'objectIds':[1,2,3,4],'objectIdFieldName':'oid'} if p.get('returnIdsOnly') else dict(features=[dict(attributes={'oid':int(k)}) for k in p['objectIds'].split(',')])
            return json.dumps(d).encode(),{}
        a=arcgis('https://example.invalid',fetch=fetch,max_records=2,start_after=0)
        self.assertFalse(a['inventory']['complete']);self.assertEqual(2,a['inventory']['next_cursor'])
        b=arcgis('https://example.invalid',fetch=fetch,max_records=2,start_after=2)
        self.assertTrue(b['inventory']['complete']);self.assertIsNone(b['inventory']['next_cursor'])
        self.assertEqual([3,4],[f['attributes']['oid'] for f in b['features']])

    def test_source_coding_contract_excludes_obsolete_rows_without_deletion(self):
        db=connect(':memory:')
        try:
            db.execute('INSERT INTO sources VALUES(?,?,?,?,?,?,?,?)',('s','s','https://example.invalid',None,'2026-11-05','fixture','pdf','{}'))
            eid=entity(db,'project_registry_v1','test','PROJECT')
            for oid,scope in [('old','obsolete scope'),('new','current scope')]:
                db.execute('INSERT INTO observations VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(oid,eid,'ore_mt',1.,'Mt','TREO',scope,'statement','INFERRED','2026-01-01','s','p1','AUTO_VALIDATED','[]','{}','normalization-v1'))
                entity(db,'PRIMARY_RESOURCE_SCOPE','statement|'+scope,'DEPOSIT_SCOPE')
            v=current_evidence_view(db,[dict(sha256='s')],'2026-11-05',{'new'})
            self.assertEqual({'new'},v['observation_ids']);self.assertEqual(1,len(v['historical_scope_ids']))
            self.assertEqual(2,db.execute('SELECT COUNT(*) FROM observations').fetchone()[0])
        finally:db.close()

    def test_unregistered_native_entity_generates_stable_source_bound_task(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'work') as tmp:
            root=Path(tmp);(root/'data').mkdir();(root/'config').mkdir()
            source=dict(key='live',kind='government_csv',sha256='s',url='https://example.invalid',state='WA',national_government=True)
            (root/'data/manifest.json').write_text(json.dumps(dict(snapshots=[source])))
            (root/'config/sources.json').write_text('{"sources":[]}')
            row=dict(entity_id='CANDIDATE',native_id='P123',namespace='WA_SITE',name='New Reef',state='WA',
                source_key='live',source_sha256='s',source_role='LIVE_GOVERNMENT_NATIVE_RECORD',original_attributes='{}',locator='native P123')
            db=connect(':memory:')
            try:
                with patch('au_ree_v2.pdf_extract.project_registry',return_value=[]),patch('au_ree_v2.national.live_government_inventory',return_value=[row]):
                    a=search_tasks(root,dict(seeds=[],candidate_tasks=True),db=db,snapshots=[source])
                    b=search_tasks(root,dict(seeds=[],candidate_tasks=True),db=db,snapshots=[source])
                self.assertEqual(a,b);self.assertEqual('CANDIDATE',a[0]['candidate_id'])
                self.assertEqual('UNREGISTERED_NATIVE_CANDIDATE_NOT_PROJECT',a[0]['registry_status'])
                self.assertEqual(0,db.execute('SELECT COUNT(*) FROM entities').fetchone()[0])
            finally:db.close()

    def test_admission_rejects_name_only_and_reuses_candidate_identity(self):
        from au_ree_v2.evidence import register_candidate
        with tempfile.TemporaryDirectory(dir=ROOT/'work') as tmp:
            root=Path(tmp);p=root/'original.html';p.write_text('<p>Issuer owns the New Project in WA.</p>')
            sha=filehash(p);source=dict(key='issuer',sha256=sha,kind='html',publication_date='2026-01-01',available_date='2026-11-05',path=p.name)
            db=connect(':memory:');eid=entity(db,'WA_SITE','S1','SITE')
            db.execute('INSERT INTO sources VALUES(?,?,?,?,?,?,?,?)',('native','native','https://example.invalid',None,'2026-11-05','fixture','government_csv','{}'))
            db.execute('INSERT INTO records VALUES(?,?,?,?,?,?,?,?,?)',(eid,'native','New','WA',120.,-30.,None,None,'{}'))
            r=dict(candidate_id=eid,candidate_source_sha256='native',identity_source='issuer',name='New Project',state='WA',identity_basis='NAME_MATCH',declaration=dict(source_sha256=sha,page_markers=['Issuer owns the New Project'],scope_reason='Explicit named project; native crosswalk unknown'))
            claims={'projects':[]}
            try:
                with self.assertRaisesRegex(ValueError,'EXPLICIT_DECLARATION'):register_candidate(db,root,[source],'2026-11-05',r,claims)
                r['identity_basis']='EXPLICIT_NAMED_PROJECT_DECLARATION'
                a,relation=register_candidate(db,root,[source],'2026-11-05',r,claims)
                b,_=register_candidate(db,root,[source],'2026-11-05',r,claims)
                self.assertEqual(a['id'],b['id']);self.assertEqual(1,len(claims['projects']))
                self.assertIn('NOT_VERIFIED',relation['relation'])
                r['relation']='CONTAINS_ISSUER_DOCUMENTED_DEPOSIT_NOT_RESOURCE_SUM'
                with self.assertRaisesRegex(ValueError,'DOCUMENTED_NATIVE_ID'):register_candidate(db,root,[source],'2026-11-05',r,claims)
            finally:db.close()

    def test_shared_method_draws_preserve_promethee_and_split_cache_dependencies(self):
        from au_ree_v2.analysis import run_r
        from au_ree_v2.cli import research_configuration
        exe=shutil.which('Rscript') or 'C:/Program Files/R/R-4.5.2/bin/Rscript.exe'
        if not Path(exe).is_file():self.skipTest('R unavailable')
        with tempfile.TemporaryDirectory(dir=ROOT/'work') as tmp:
            root=Path(tmp);(root/'R').mkdir();out=root/'out'
            for name in ('methods.R','run_mcda.R'):shutil.copy2(ROOT/'R'/name,root/'R'/name)
            for panel in ('six_domain','peer'):
                (out/panel).mkdir(parents=True)
                for name in ('matrix.csv','criteria.csv','weights.csv'):shutil.copy2(ROOT/'results/phase21-2026-11-05/six_domain'/name,out/panel/name)
            c=research_configuration(ROOT);c['monte_carlo']=dict(c['monte_carlo'],reps=12)
            c.pop('shared_method_draws',None);c.pop('mcda_dependency_version',None)
            run_r(root,out,dict(panels={'six_domain':5,'peer':5}),c,exe)
            old=(out/'six_domain/weight_uncertainty.csv').read_bytes()
            c.update(shared_method_draws='shared-method-draws-v1',mcda_dependency_version='panel-core-and-cohort-v2')
            a=run_r(root,out,dict(panels={'six_domain':5,'peer':5}),c,exe)
            self.assertEqual(old,(out/'six_domain/weight_uncertainty.csv').read_bytes())
            with (out/'six_domain/shared_draw_ranks.csv').open() as stream:draws=list(csv.DictReader(stream))
            self.assertEqual({'SAW','PROMETHEE_II','TOPSIS'},{r['method'] for r in draws})
            self.assertEqual(3*12*2*3*5,len(draws))
            path=out/'peer/matrix.csv';text=path.read_text();path.write_text(text.replace('Jupiter','Changed metadata',1))
            b=run_r(root,out,dict(panels={'six_domain':5,'peer':5}),c,exe)
            self.assertEqual('REUSED_VERIFIED',b['six_domain']['cache_status'])
            self.assertEqual('COMPUTED_AND_CACHED',b['six_domain']['cohort_cache_status'])
            self.assertEqual('COMPUTED_AND_CACHED',b['peer']['cache_status'])


if __name__=='__main__':unittest.main()
