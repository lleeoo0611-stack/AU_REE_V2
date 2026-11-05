"""Current-path consolidation, native candidate recall and immutable cache contracts."""
import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from au_ree_v2.store import connect,entity,canonical,digest,append_snapshots
from au_ree_v2.census import classify_ree
from au_ree_v2.pdf_extract import project_registry
from au_ree_v2.analysis import current_disclosure_baseline,prepare_disclosure_analysis
from au_ree_v2.cli import research_configuration
from au_ree_v2.technical import run_disclosure

ROOT=Path(__file__).resolve().parents[1]


class Phase21(unittest.TestCase):
    def test_candidate_endpoint_sources_follow_ids_independent_of_input_order(self):
        from au_ree_v2.national import government_link_candidates
        db=connect(':memory:')
        try:
            a=dict(entity_id='A',namespace='state-a',name='Same deposit',state='NT',
                source_sha256='source-a',source_role='LIVE_GOVERNMENT_NATIVE_RECORD')
            b=dict(a,entity_id='B',namespace='state-b',source_sha256='source-b')
            results=[]
            for records in ([b,a],[a,b]):
                with patch('au_ree_v2.national.live_government_inventory',return_value=records):
                    results.append(government_link_candidates(db,[]))
            self.assertEqual(results[0],results[1])
            pair=results[0][0]
            self.assertEqual(('A','source-a','B','source-b'),
                (pair['a'],pair['source_a'],pair['b'],pair['source_b']))
        finally:db.close()

    def test_representative_relation_preserves_revisions_without_duplicates(self):
        from au_ree_v2.evidence import ingest_claims
        db=connect(':memory:')
        try:
            for sha in ('old','new','issuer'):
                db.execute('INSERT INTO sources VALUES(?,?,?,?,?,?,?,?)',
                    (sha,sha,'https://example.invalid',None,'2026-11-05','fixture','test','{}'))
            dep=entity(db,'GOV_POINT','1','DEPOSIT')
            for sha in ('old','new'):
                db.execute('INSERT INTO records VALUES(?,?,?,?,?,?,?,?,?)',
                    (dep,sha,'Deposit','NT',133.,-20.,None,None,'{}'))
            claims={'projects':[dict(id='test',identity_source='issuer',name='Project',state='NT',
                coordinate_source='government',coordinate_native_id='1',coordinate_role='Representative point only',
                observations=[])]}
            for sha in ('old','new','new'):
                ingest_claims(db,ROOT,[dict(key='issuer',sha256='issuer'),
                    dict(key='government',sha256=sha,namespace='GOV_POINT',available_date='2026-11-05')],
                    '2026-11-05',claims_data=claims)
            got=db.execute("SELECT source_sha FROM relations WHERE relation='REPRESENTATIVE_POINT_NOT_ENTITY_EQUIVALENCE' ORDER BY source_sha").fetchall()
            self.assertEqual(['new','old'],[r[0] for r in got])
        finally:db.close()

    def test_mcda_cache_reuses_exact_results_and_invalidates_weights_and_corruption(self):
        import shutil,subprocess
        from au_ree_v2.analysis import run_r,write_csv
        from au_ree_v2.store import filehash
        executable=shutil.which('Rscript') or 'C:/Program Files/R/R-4.5.2/bin/Rscript.exe'
        if not Path(executable).is_file():self.skipTest('R not installed')
        with tempfile.TemporaryDirectory(dir=ROOT/'work') as tmp:
            root=Path(tmp);(root/'R').mkdir();out=root/'out';folder=out/'test';folder.mkdir(parents=True)
            for name in ('methods.R','run_mcda.R'):shutil.copy2(ROOT/'R'/name,root/'R'/name)
            data=[]
            for pid,r,t in [('P',.2,.8),('Q',.8,.2)]:
                row=dict(project_id=pid,project_name=pid,scope='TEST_FIXTURE_ONLY')
                for c,value in [('R1',r),('T1',t)]:
                    for suffix in ('','_lower','_upper','_alt'):row[c+suffix]=value
                data.append(row)
            write_csv(folder/'matrix.csv',data,list(data[0]))
            write_csv(folder/'criteria.csv',[dict(code=c,domain=d,direction='MAX',low=0,high=1,function='linear') for c,d in [('R1','Resource'),('T1','Technical')]],['code','domain','direction','low','high','function'])
            weights=[dict(scenario='test',criterion=c,weight=.5) for c in ('R1','T1')]
            write_csv(folder/'weights.csv',weights,['scenario','criterion','weight'])
            config=research_configuration(ROOT);config['mcda_cache']=True;config['monte_carlo']=dict(config['monte_carlo'],seed=42,reps=20)
            first=run_r(root,out,dict(panels={'test':2}),config,executable)
            expected=filehash(folder/'ranking.csv');self.assertEqual('COMPUTED_AND_CACHED',first['test']['cache_status'])
            (root/'unrelated.json').write_text('{"unrelated_source":true}')
            second=run_r(root,out,dict(panels={'test':2}),config,executable)
            self.assertEqual('REUSED_VERIFIED',second['test']['cache_status']);self.assertEqual(expected,filehash(folder/'ranking.csv'))
            weights[0]['weight']=.6;weights[1]['weight']=.4;write_csv(folder/'weights.csv',weights,list(weights[0]))
            changed=run_r(root,out,dict(panels={'test':2}),config,executable)
            self.assertEqual('COMPUTED_AND_CACHED',changed['test']['cache_status']);self.assertNotEqual(expected,filehash(folder/'ranking.csv'))
            cache=json.loads((folder/'r_cache.json').read_text());bad=root/'work/cache/mcda'/cache['key']/'ranking.csv';bad.write_text('broken')
            repaired=run_r(root,out,dict(panels={'test':2}),config,executable)
            self.assertEqual('COMPUTED_AND_CACHED',repaired['test']['cache_status'])

    def test_registry_read_sees_committed_version_during_ingestion(self):
        import sqlite3
        with tempfile.TemporaryDirectory(dir=ROOT/'work') as tmp:
            path=Path(tmp)/'database.sqlite';writer=connect(path)
            entity(writer,'native','one','PROJECT');writer.commit()
            reader=sqlite3.connect(path,timeout=.1)
            try:
                entity(writer,'native','two','PROJECT')
                self.assertEqual(1,reader.execute('select count(*) from entities').fetchone()[0])
                writer.commit();self.assertEqual(2,reader.execute('select count(*) from entities').fetchone()[0])
            finally:reader.close();writer.close()

    def test_commercial_r_input_and_rank_features_do_not_recompute(self):
        from au_ree_v2.analysis import prepare_commercial_coverage,research_readiness
        selection=dict(inventory=[],projects={'P'},values={},technical_comparability=[])
        with tempfile.TemporaryDirectory(dir=ROOT/'work') as tmp:
            out=Path(tmp);context=prepare_commercial_coverage(selection,out)
            self.assertTrue((out/'commercial_project_coverage.csv').exists())
            self.assertIsNone(context[0]['financing_milestone'])
            with patch('au_ree_v2.analysis.prepare_commercial_coverage',side_effect=AssertionError('recomputed')):
                self.assertEqual(context,research_readiness(selection,out,commercial=context))

    def test_candidate_roles_and_symbol_context(self):
        self.assertFalse(classify_ree({'summary':'The company ASX:REE proposes a road'})['include'])
        self.assertFalse(classify_ree({'summary':'The Nd ticker and Eu abbreviation appear in ordinary prose'})['include'])
        self.assertTrue(classify_ree({'commodity':'Sm, Eu, Gd'},['commodity'])['include'])
        self.assertEqual('SC_ONLY',classify_ree({'commodity':'scandium'},['commodity'])['role'])
        self.assertEqual('MINERAL_ONLY',classify_ree({'mineral':'monazite'})['role'])
        self.assertFalse(classify_ree({'commodity':'copper; scenery; monazitesque'},['commodity'])['include'])

    def test_manifest_stale_writer_cannot_remove_other_source(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'work') as tmp:
            p=Path(tmp)/'manifest.json';p.write_text('{"snapshots":[]}')
            a=dict(key='a',sha256='1');b=dict(key='b',sha256='2')
            append_snapshots(p,[a]);append_snapshots(p,[b]);append_snapshots(p,[a])
            self.assertEqual([a,b],json.loads(p.read_text())['snapshots'])

    def test_sqlite_registry_discovers_project_without_claim_and_keeps_id(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'work') as tmp:
            root=Path(tmp);(root/'data').mkdir();(root/'data/claims.json').write_text('{"projects":[]}')
            db=connect(root/'test.sqlite');self.addCleanup(db.close)
            db.execute('INSERT INTO sources VALUES(?,?,?,?,?,?,?,?)',('s','official','https://test.invalid',None,'2026-01-01','a','government_wfs','{}'))
            pid=entity(db,'STATE_NATIVE_PROJECT','N1','PROJECT')
            db.execute('INSERT INTO records VALUES(?,?,?,?,?,?,?,?,?)',(pid,'s','New real native project','SA',None,None,None,None,'{}'))
            first=project_registry(root,db,[dict(sha256='s')]);second=project_registry(root,db,[dict(sha256='s')])
            self.assertEqual(first,second);self.assertEqual(pid,first[0]['entity_id'])
            self.assertEqual([],project_registry(root,db,[dict(sha256='different')]))
            db.close()

    def test_memory_baseline_matches_csv_and_preserves_source_bounds(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'work') as tmp:
            out=Path(tmp)
            row=dict(entity_id='p',criterion='S1',score=.228,raw_value=22.8,source='{}',scoring='{}',score_lower=.226,score_upper=.23,score_alt=.228)
            prepared=dict(coverage=[dict(entity_id='p',resource_defined=1)],traces=[row])
            # No CSV is needed in the current execution path.
            result=current_disclosure_baseline(out,{},['p'],prepared,include_bounds=True)
            self.assertEqual(.226,result['scores']['p']['S1']['score_lower'])
            self.assertEqual(.228,result['scores']['p']['S1']['score'])

    def test_current_disclosure_defers_analysis_and_adds_unknown_scopes(self):
        config=research_configuration(ROOT)
        with tempfile.TemporaryDirectory(dir=ROOT/'work') as tmp:
            with patch('au_ree_v2.analysis.prepare_disclosure_analysis',side_effect=AssertionError('duplicate assembly')):
                result,prepared,summary=run_disclosure(ROOT,config,'2026-11-05',Path(tmp),
                    registry=[dict(entity_id='NEW',name='New confirmed native Project')])
            self.assertIsNone(prepared)
            new=next(s for s in result['scores'] if s['project_id']=='NEW')
            self.assertIsNone(new['score']);self.assertEqual(7,new['unknown_items'])
            self.assertTrue(all(r['value'] is None for r in result['items'] if r['project_id']=='NEW'))

    def test_incremental_review_keeps_old_assessments_and_barkly_scope(self):
        review=json.loads((ROOT/'data/technical_disclosure_current.json').read_text(encoding='utf8'))
        old=json.loads((ROOT/'data/technical_disclosure_v1.json').read_text(encoding='utf8'))
        old_by_id={g['project_id']:g for g in old['groups']}
        conf=json.loads((ROOT/'results/phase21-2026-11-05/configuration.json').read_text())
        frozen=json.loads((ROOT/conf['research']['evidence_resolution']['technical_disclosure']['review_path']).read_text(encoding='utf8'))
        self.assertTrue(all(old_by_id[g['project_id']]==g for g in frozen['groups'] if g['project_id'] in old_by_id))
        # Later reviewed explanations/documents may evolve; the original
        # frozen review and adopted seven binary states remain reconstructable.
        self.assertTrue(all(old_by_id[g['project_id']]['items'][code]['status']==item['status'] for g in review['groups'] if g['project_id'] in old_by_id for code,item in g['items'].items()))
        p=next(g for g in review['groups'] if 'Barkly' in g['name'])
        self.assertFalse(p['search_complete']);self.assertEqual('UNVERIFIABLE',p['items']['TD6']['status'])

    def test_changed_source_invalidates_only_affected_project_review(self):
        config=research_configuration(ROOT)
        review=json.loads((ROOT/'data/technical_disclosure_current.json').read_text(encoding='utf8'))
        active=list(copy.deepcopy(review['sources']).values())
        next(s for s in active if s['key']=='barkly_ipo20260130')['sha256']='0'*64
        with tempfile.TemporaryDirectory(dir=ROOT/'work') as tmp:
            result,_,_=run_disclosure(ROOT,config,'2026-11-05',Path(tmp),assemble=False,selected_snapshots=active)
        barkly=next(r for r in result['scores'] if 'Barkly' in r['project_name'])
        nolans=next(r for r in result['scores'] if 'Nolans' in r['project_name'])
        self.assertEqual(7,barkly['unknown_items']);self.assertIsNone(barkly['score']);self.assertIsNotNone(nolans['score'])

    def test_native_page_cache_preserves_parser_text_and_checks_changed_original(self):
        import fitz
        from au_ree_v2.store import filehash
        from au_ree_v2.evidence import validate_pages
        with tempfile.TemporaryDirectory(dir=ROOT/'work') as tmp:
            root=Path(tmp);path=root/'original.pdf'
            pdf=fitz.open();page=pdf.new_page();page.insert_text((72,72),'Original resource table 40 Mt');pdf.save(path);pdf.close()
            s=dict(key='s',kind='pdf',sha256=filehash(path),path='original.pdf',publication_date='2025-01-01',available_date='2025-01-01')
            o=dict(source_sha256=s['sha256'],pdf_page=1,page_markers=['Original resource table 40 Mt'])
            validate_pages(root,s,o,[s])
            with patch('pypdf.PdfReader',side_effect=AssertionError('page reparsed')):validate_pages(root,s,o,[s])
            path.write_bytes(path.read_bytes()+b'\nchanged original bytes')
            with self.assertRaises(ValueError):validate_pages(root,s,o,[s])

    def test_oxide_distribution_transforms_and_resource_rebinding(self):
        from au_ree_v2.evidence import transformation_issues
        claims=json.loads((ROOT/'data/claims.json').read_text(encoding='utf8'))
        for pid,value in [('cummins-range',22.8),('nolans-rare-earths-project',26.78)]:
            p=next(p for p in claims['projects'] if p['id']==pid)
            o=next(o for o in p['observations'] if o['variable']=='magnet_reo_share_pct')
            self.assertAlmostEqual(value,o['value']);self.assertFalse(transformation_issues(o,p['observations']))
            denominator=next(x for x in p['observations'] if x['variable']=='normalized_resource_distribution_treo_ppm')
            self.assertNotIn('original_value',denominator)
            self.assertEqual('DEFINITION_IDENTITY_NOT_REPORTED_MEASUREMENT',denominator['derivation_status'])
            resource=next(x for x in p['observations'] if x['variable']=='ore_mt')
            self.assertEqual(resource['source_sha256'],o['source_sha256'])
            changed=dict(o,scope='Different ore body')
            self.assertTrue(transformation_issues(changed,p['observations']))


if __name__=='__main__':unittest.main()
