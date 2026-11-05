"""Scientific counterexamples, unified evidence and centralized original data."""
import copy
import io
import json
import sqlite3
import unittest
import zipfile
from pathlib import Path
from au_ree_v2.technical_tables import bind_semantics
from au_ree_v2.technical import burden_states,unified_observations
from au_ree_v2.store import SCHEMA,canonical,entity

ROOT=Path(__file__).resolve().parents[1]
POLICY=json.loads((ROOT/'results/phase16-2026-11-04/configuration.json').read_text())['research']['evidence_resolution']
PROFILE=POLICY['technical_profile']
V6='document-recognition-v6-context-bound'

def cell(**kw):
    return dict(kind='TECHNICAL_TABLE_CELL',physical_page=1,quantity='extraction_pct',
        scale='LAB_SCALE_UNSPECIFIED',feed='ZONE_COMPOSITE',sample_id='West',limitations=[],**kw)


class SemanticCounterexamples(unittest.TestCase):
    def test_table_shape_does_not_prove_composite_or_laboratory(self):
        r=bind_semantics(cell(),['West Final Extraction (%)'], 'sha')
        self.assertIsNone(r['feed']);self.assertIsNone(r['scale'])
        self.assertEqual([],r['semantic_evidence']['scale'])

    def test_identical_reagent_shape_in_dfs_is_not_scoping(self):
        r=cell();r.update(quantity='reagent_tpa',scale='SCOPING_MODEL',table_caption='Plant process design basis')
        r=bind_semantics(r,['Definitive Feasibility Study\nPlant process design basis'],'sha')
        self.assertEqual('DFS_MODEL',r['scale']);self.assertTrue(r['semantic_evidence']['scale'])
        self.assertTrue(all(e['source_sha256']=='sha' for e in r['semantic_evidence']['scale']))

    def test_study_stage_does_not_prove_test_scale(self):
        r=cell();r.update(quantity='recovery_pct',scale='LAB_FLOTATION')
        r=bind_semantics(r,['Definitive Feasibility Study\nF1 flotation pilot scale'],'sha')
        self.assertEqual('DFS_MODEL',r['study_stage']);self.assertEqual('PILOT_FLOTATION',r['scale'])

    def test_conflicting_scales_remain_unknown(self):
        r=cell();r.update(quantity='recovery_pct',scale='LAB_FLOTATION')
        r=bind_semantics(r,['laboratory flotation\npilot flotation'],'sha')
        self.assertIsNone(r['scale']);self.assertIn('TEST_SCALE_CONTEXT_CONFLICT',r['semantic_conflicts'])

    def test_positive_composite_requires_named_context(self):
        r=bind_semantics(cell(),['West composite bottle roll testing'],'sha')
        self.assertEqual('SOURCE_NAMED_COMPOSITE',r['feed']);self.assertEqual('BOTTLE_ROLL',r['scale'])

    def test_nolans_footnote_not_zero_or_all_scenarios(self):
        t='* La2O3 recovery to final product is only applicable if the lanthanum recovery circuit is included in the separation plant, where this circuit is excluded then there is no La2O3 recovery (as is the case for the base case of the Project)'
        r=cell();r.update(quantity='downstream_recovery_factor',basis='La2O3',value=.924)
        r=bind_semantics(r,[t],'sha')
        self.assertFalse(r['base_case_applicable']);self.assertEqual(.924,r['value']);self.assertEqual('LA_CIRCUIT_INCLUDED_ONLY',r['scenario'])
        self.assertEqual(t,r['scenario_evidence']['quote'])


class BurdenAndView(unittest.TestCase):
    def test_predeclared_examples_and_no_development_or_norm_bonus(self):
        for text in PROFILE['examples']['negative']:self.assertEqual([],burden_states(text,PROFILE),text)
        for text in PROFILE['examples']['positive']:self.assertTrue(burden_states(text,PROFILE),text)

    def test_conflict_is_a_set_not_worst_or_latest_priority(self):
        states=burden_states('Tests demonstrated no grinding required. Acid consumption was measured on feed.',PROFILE)
        self.assertEqual({'SUPPORTED_LOWER_BURDEN','EXPLICIT_ADDITIONAL_REQUIREMENT'},{r['state'] for r in states})

    def test_study_and_text_without_cells_are_usable_and_missing_is_null(self):
        c=dict(domain='Technical',variable='resource_to_final_mreo_recovery_pct',value=68,unit='%',basis='TREO_INCLUDING_Y',
            project_id='p',evidence_id='e',source_sha256='sha',pdf_page=11,locator='p11',scope='mine plan',effective_date='2026-06-25',
            feed='WHOLE_ORE_PFS_MINE_PLAN',endpoint='CALCINED_MIXED_REO',scale='PFS_MODEL',origin='STUDY_PARAMETER',case_id='case',reason=None,
            raw={'process':'Impurity removal requires neutralisation.'})
        null=copy.deepcopy(c);null.update(variable='reported_technical_disclosure',value=None,evidence_id='f',origin='OBSERVATION')
        rows=unified_observations({'inventory':[c,null,c],'policy':POLICY},PROFILE)
        self.assertEqual(2,len(rows));self.assertTrue(all(r['supports_technical_interpretation'] for r in rows))
        self.assertEqual(1,sum(r['numeric_profile_eligible'] for r in rows));self.assertTrue(any(r['value'] is None for r in rows))
        self.assertTrue(all(not r['project_extrapolation'] for r in rows))
        self.assertTrue(any(r['interpretations'] for r in rows))

    def test_different_feed_endpoint_or_scope_never_deduplicated(self):
        base=dict(domain='Technical',variable='recovery_pct',value=80,unit='%',basis='TREO',project_id='p',evidence_id='e',source_sha256='sha',pdf_page=1,locator='p1',scope='a',effective_date='2025-01-01',feed='ORE',endpoint='CONCENTRATE',scale=None,origin='OBSERVATION',reason=None,raw={})
        changed=dict(base,scope='b',feed='CONCENTRATE',endpoint='MREC',evidence_id='f')
        self.assertEqual(2,len(unified_observations({'inventory':[base,changed],'policy':POLICY},PROFILE)))

    def test_no_common_ordinal_mapping_or_weight_expansion(self):
        self.assertEqual('PARTIAL_MCDA_PLUS_SCOPED_TECHNICAL_PROFILES',PROFILE['decision'])
        self.assertIsNone(PROFILE['ordinal_numeric_mapping']);self.assertFalse(PROFILE['common_score']);self.assertEqual(0,PROFILE['technical_weight_change'])
        self.assertNotIn('T-A',POLICY['criteria']);self.assertNotIn('T-B',POLICY['criteria'])

    def test_missing_and_not_applicable_cells_support_no_physical_judgment(self):
        base=dict(domain='Technical',variable='reported_technical_recovery_pct',value=None,unit='%',basis='TREO',project_id='p',evidence_id='e',source_sha256='sha',pdf_page=1,locator='p1',scope='table',effective_date='2025-01-01',feed=None,endpoint=None,scale=None,origin='OBSERVATION',reason=None)
        for token,reason in [('NOT_REPORTED','MISSING_SOURCE_VALUE'),('NOT_APPLICABLE','EXPLICIT_NOT_APPLICABLE')]:
            c=dict(base,raw=dict(kind='TECHNICAL_TABLE_CELL',quantity='recovery_pct',raw_text='-',token_state=token))
            r=unified_observations({'inventory':[c],'policy':POLICY},PROFILE)[0]
            self.assertIsNone(r['value']);self.assertFalse(r['supports_technical_interpretation']);self.assertFalse(r['numeric_profile_eligible']);self.assertEqual(reason,r['interpretation_reason'])


class OriginalIntegration(unittest.TestCase):
    def test_cache_binds_code_dependencies_not_only_source_version(self):
        from au_ree_v2.pdf_extract import extraction_dependencies
        from unittest.mock import patch
        before=extraction_dependencies()
        with patch('au_ree_v2.pdf_extract.filehash',return_value='changed'):
            self.assertNotEqual(before,extraction_dependencies())

    def test_dated_batch_visible_only_in_explicit_acquisition_window(self):
        from au_ree_v2.acquisition import select_snapshots
        a=select_snapshots(ROOT,'2026-11-03',acquired_through='2026-11-04')
        b=select_snapshots(ROOT,'2026-11-03')
        self.assertTrue(any(s['kind']=='minedex_resource_batch' for s in a))
        self.assertFalse(any(s['kind']=='minedex_resource_batch' for s in b))

    def test_newer_batch_and_live_gis_never_backdated(self):
        from au_ree_v2.acquisition import select_snapshots
        from unittest.mock import patch
        base=dict(key='s',sha256='x',path='absent',kind='minedex_resource_batch',available_date='2026-11-04',publication_date='2026-11-03',source_update='03/11/2026',last_modified='Wed, 04 Nov 2026 19:14:10 GMT',acquired_at='2026-11-04')
        with patch('au_ree_v2.acquisition.json.loads',return_value={'snapshots':[base]}):
            self.assertEqual([],select_snapshots(ROOT,'2026-11-03',acquired_through='2026-11-04'))
        base.update(kind='government_arcgis',last_modified='Tue, 03 Nov 2026 19:14:10 GMT')
        with patch('au_ree_v2.acquisition.json.loads',return_value={'snapshots':[base]}):
            self.assertEqual([],select_snapshots(ROOT,'2026-11-03',acquired_through='2026-11-04'))

    def test_browns_repaired_is_now_development_regression(self):
        from au_ree_v2.pdf_extract import recognize_document,project_registry
        manifest=json.loads((ROOT/'data/manifest.json').read_text())['snapshots']
        source=next(s for s in manifest if s['key']=='browns_range_2025' and s['kind']=='pdf')
        rows=recognize_document(ROOT,source,project_registry(ROOT),parser_version=V6,page_numbers={116})['candidates']
        cells=[r for r in rows if r['kind']=='TECHNICAL_TABLE_CELL']
        self.assertEqual({('grade_pct',25),('recovery_pct',84)},{(r['quantity'],r['value']) for r in cells})
        self.assertTrue(all(r['bbox'] and r['header_path'] for r in cells))

    def test_actual_batch_source_ids_dates_missing_and_idempotence(self):
        from au_ree_v2.official import ingest_minedex_resources,minedex_resource_rows
        manifest=json.loads((ROOT/'data/manifest.json').read_text())['snapshots']
        source=next(s for s in manifest if s['kind']=='minedex_resource_batch')
        allrows,rows=minedex_resource_rows(ROOT,source,"minedex-resource-batch-v1")
        self.assertEqual(2666,len(allrows));self.assertEqual(68,len(rows))
        db=sqlite3.connect(':memory:');db.row_factory=sqlite3.Row;db.executescript(SCHEMA)
        db.execute('INSERT INTO sources VALUES(?,?,?,?,?,?,?,?)',(source['sha256'],source['key'],source['url'],source['publication_date'],source['acquired_at'],source['path'],source['kind'],canonical(source)))
        old=entity(db,'WA_MINDEX_PROJECT','J04481','PROJECT_CANDIDATE')
        ingest_minedex_resources(db,ROOT,source)
        count=db.execute('select count(*) from observations').fetchone()[0]
        ingest_minedex_resources(db,ROOT,source)
        self.assertEqual(count,db.execute('select count(*) from observations').fetchone()[0])
        self.assertEqual(old,entity(db,'WA_MINDEX_PROJECT','J04481','PROJECT_CANDIDATE'))
        self.assertEqual(0,db.execute("select count(*) from entities where kind='PROJECT'").fetchone()[0])
        self.assertTrue(db.execute('select count(*) from observations where value is null').fetchone()[0]>0)
        self.assertTrue(all(json.loads(r[0])['estimate_date'] is None for r in db.execute('select raw from observations')))
        self.assertEqual([],list(db.execute('pragma foreign_key_check')));db.close()

    def test_batch_directory_completeness_and_not_map_index(self):
        from au_ree_v2.acquisition import minedex_resource_batch
        calls=[];buf=io.BytesIO()
        with zipfile.ZipFile(buf,'w') as z:z.writestr('resource.csv','PROJ_CODE,EST_COM,RES_QTY,RES_CON,LOC_SITE\nJ1,REE,1,2,S1\n')
        def fetch(url,params=None):
            calls.append((url,params))
            if len(calls)==1:return b'var tabs = [{"Id":729}];',{}
            if len(calls)==2:return json.dumps([{'NodeType':'File','FileFormat':'CSV','Path':'Download/File/1','UpdatedDate':'03/11/2026'}]).encode(),{}
            return buf.getvalue(),{}
        body,headers=minedex_resource_batch('https://official.test/home?productAlias=a','a',fetch=fetch)
        self.assertEqual(buf.getvalue(),body);self.assertEqual('3',headers['X-DASC-Requests']);self.assertEqual(729,calls[1][1]['parentFolderId'])
        with self.assertRaises(ValueError):minedex_resource_batch('https://official.test/MapServer/0','a',fetch=lambda *a:(b'{"features":[]}',{}))

if __name__=='__main__':unittest.main()
