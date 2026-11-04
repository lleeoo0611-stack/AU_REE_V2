"""Fixed single-field scientific counterexamples and frozen-source completeness."""
import copy,csv,io,json,sqlite3,unittest,zipfile
from collections import Counter
from pathlib import Path
from au_ree_v2.technical import unified_observations,burden_states,target_applicability
from au_ree_v2.official import minedex_resource_rows,commodity_classification,ingest_minedex_resources
from au_ree_v2.store import SCHEMA,canonical,entity
ROOT=Path(__file__).resolve().parents[1]
POLICY=json.loads((ROOT/'config/evidence_policy.json').read_text())
PROFILE=POLICY['technical_profile']

def observation(**kw):
    r=dict(domain='Technical',variable='recovery_pct',value=80,unit='%',basis='TREO',project_id='p',evidence_id='e',source_sha256='sha',pdf_page=1,locator='p1',scope='same',effective_date='2025-01-01',feed='ORE',endpoint='CONCENTRATE',scale='LAB',origin='OBSERVATION',case_id='fixed-case',reason=None,raw={})
    r.update(kw);return r

def view(*items):return unified_observations({'inventory':list(items),'policy':POLICY},PROFILE)

class ScientificIdentity(unittest.TestCase):
    def test_single_field_semantic_changes_survive(self):
        base=observation()
        for field,value in [('feed','CONCENTRATE'),('endpoint','MREC'),('scale','PILOT'),('effective_date','2025-02-01'),('basis','Nd2O3'),('scope','zone')]:
            with self.subTest(field=field):
                changed=copy.deepcopy(base);changed.update({field:value,'evidence_id':'other'})
                self.assertEqual(2,len(view(base,changed)))
        for field in ['statistic','scenario','date_role','sample_id','test_id','fraction_scope','conditions','temperature_c','sample_population','process_stage','acid_unit','reagent_formulation','liquid_solid_ratio','stage','from_material','to_material']:
            with self.subTest(field=field):
                changed=copy.deepcopy(base);changed['raw'][field]='different';changed['evidence_id']='other'
                self.assertEqual(2,len(view(base,changed)))
    def test_same_measurement_different_value_conflicts(self):
        rows=view(observation(),observation(value=81,evidence_id='f'))
        self.assertEqual(2,len(rows));self.assertEqual(1,len({r['scientific_observation_identity'] for r in rows}))
        self.assertTrue(all(r['measurement_relation']=='CONFLICTING_VALUES_SAME_SCIENTIFIC_OBSERVATION' and not r['numeric_profile_eligible'] for r in rows))
    def test_equal_value_different_test_is_not_duplicate(self):
        self.assertEqual(2,len(view(observation(raw={'test_id':'A'}),observation(raw={'test_id':'B'},evidence_id='f'))))
    def test_exact_duplicates_retain_all_evidence(self):
        rows=view(observation(),observation(evidence_id='f'))
        self.assertEqual(1,len(rows));self.assertEqual(['e','f'],rows[0]['evidence_ids'])
    def test_source_versions_not_equal_without_measurement_link(self):
        self.assertEqual(2,len(view(observation(),observation(source_sha256='v2',evidence_id='f'))))
    def test_explicit_cross_document_link_has_same_scientific_identity(self):
        a=observation(raw={'measurement_identity_evidence':{'measurement_id':'M1','quote':'same trial','source_sha256':'sha','pdf_page':1}})
        b=observation(source_sha256='other',evidence_id='f',raw={'measurement_identity_evidence':{'measurement_id':'M1','quote':'same trial','source_sha256':'other','pdf_page':1}})
        rows=view(a,b);self.assertEqual(1,len(rows));self.assertEqual(2,len(rows[0]['source_locators']))
    def test_unit_whitespace_and_percent_alias_are_auditable(self):
        rows=view(observation(unit=' % '),observation(unit='percent',evidence_id='f'))
        self.assertEqual(1,len(rows));self.assertEqual({' % ','percent'},{r['unit'] for r in rows[0]['source_records']})
        self.assertEqual(2,len(view(observation(unit='g/L'),observation(unit='kg/t',evidence_id='f'))))

class Purpose(unittest.TestCase):
    def test_toc_and_objective_never_burden(self):
        for text in ['17 MREO Product Quality and Impurity Removal .................... 19','The MREOH circuit is designed to validate production, optimise reagent consumption and evaluate filtration.','Acid consumption','Acid consumption will be measured.','No acid consumption data were disclosed.']:
            self.assertEqual([],burden_states(text,PROFILE),text)
    def test_design_numeric_positive(self):
        r=burden_states('The design assumed acid consumption of 24 kg/t dry feed.',PROFILE)[0]
        self.assertEqual('DESIGN_MODEL',r['evidence_nature']);self.assertEqual(24,r['quantities'][0]['value']);self.assertEqual('NOT_ESTABLISHED',r['intensity_order'])
    def test_future_elsewhere_does_not_erase_result(self):
        self.assertTrue(burden_states('Acid consumption was measured on feed. The company will complete a DFS.',PROFILE))
    def test_negated_requirement_and_unquantified_comparison(self):
        for t in ['Impurity removal is not required.','Acid consumption was lower than Sample B.','No treatment of impurities was required.']:
            self.assertEqual([],burden_states(t,PROFILE),t)
    def test_conditional_is_not_unconditional_result(self):
        rows=burden_states('If feed contains uranium, impurity removal requires treatment.',PROFILE)
        self.assertTrue(rows);self.assertTrue(all(r['state']=='CONDITIONAL_REQUIREMENT' for r in rows))
    def test_named_lower_requirement_not_whole_process(self):
        rows=burden_states('Tests demonstrated no grinding required.',PROFILE)
        self.assertEqual('grinding',rows[0]['material']);self.assertEqual('NOMINAL_REQUIREMENT_ATTRIBUTE_NOT_ORDINAL_SCORE',rows[0]['allowed_use'])

class Applicability(unittest.TestCase):
    def test_evidence_can_support_named_target(self):
        r=observation();raw={'target_scope':'project P','target_scope_kind':'PROJECT','sample_id':'S','representativeness_evidence':{'source_sha256':'sha','pdf_page':1,'quote':'Stratified samples cover all mapped ore domains and scheduled feed','sample_id':'S','target_population':'project P','coverage_basis':'DOMAIN_MASS_WEIGHTED_SAMPLING_AND_VARIABILITY_TESTS','qualification':'TARGET_POPULATION_VALIDATED'}}
        self.assertTrue(target_applicability(r,raw)['project_extrapolation'])
        raw['representativeness_evidence']['target_population']='other';self.assertFalse(target_applicability(r,raw)['project_extrapolation'])
        raw['representativeness_evidence']['conflict']=True;self.assertEqual('CONFLICT',target_applicability(r,raw)['status'])
        self.assertFalse(target_applicability(r,{'representativeness':'representative'})['project_extrapolation'])

class CommodityCompleteness(unittest.TestCase):
    def source(self):return next(s for s in json.loads((ROOT/'data/manifest.json').read_text())['snapshots'] if s['kind']=='minedex_resource_batch')
    def test_every_missing_frozen_source_row_and_values(self):
        s=self.source();allrows,rows=minedex_resource_rows(ROOT,s);_,old=minedex_resource_rows(ROOT,s,'minedex-resource-batch-v1')
        expected_lines=[280,811,812,813,815,817,821,824,1766,1767,1768,1771,1774,1778,1780]
        oldkeys={(r['raw']['PROJ_CODE'],r['raw']['EST_COM']) for r in old}
        added=[r for r in rows if (r['raw']['PROJ_CODE'],r['raw']['EST_COM']) not in oldkeys]
        self.assertEqual(expected_lines,sorted(r['csv_line'] for r in added));self.assertEqual(83,len(rows))
        self.assertEqual({'J06723','J06523','J06272'},{r['raw']['PROJ_CODE'] for r in added})
        self.assertEqual(Counter({'Samarium oxide':3,'Erbium oxide':2,'Europium oxide':2,'Gadolinium oxide':2,'Holmium oxide':2,'Lutetium oxide':2,'Thulium oxide':2}),Counter(r['raw']['EST_COM'] for r in added))
        for r in added:self.assertEqual(allrows[r['csv_line']-2],r['raw']);self.assertEqual(s['sha256'],r['source_sha256'])
        self.assertTrue(oldkeys.issubset({(r['raw']['PROJ_CODE'],r['raw']['EST_COM']) for r in rows}))
    def test_exact_normalization_related_and_unknown(self):
        self.assertTrue(commodity_classification('  ERBIUM   oxide  ')['include'])
        self.assertTrue(commodity_classification('Ytterbium oxide')['include'])
        for t in [None,'','Terbium-like rock','mystery','Scandium','Monazite','Xenotime']:
            self.assertFalse(commodity_classification(t)['include'],t)
    def test_ingest_preserves_native_ids_and_is_idempotent(self):
        source=self.source();db=sqlite3.connect(':memory:');db.row_factory=sqlite3.Row;db.executescript(SCHEMA)
        db.execute('INSERT INTO sources VALUES(?,?,?,?,?,?,?,?)',(source['sha256'],source['key'],source['url'],source['publication_date'],source['acquired_at'],source['path'],source['kind'],canonical(source)))
        old=entity(db,'WA_MINDEX_PROJECT','J06523','PROJECT_CANDIDATE')
        ingest_minedex_resources(db,ROOT,source);n=db.execute('select count(*) from observations').fetchone()[0]
        self.assertEqual(498,n);ingest_minedex_resources(db,ROOT,source)
        self.assertEqual(n,db.execute('select count(*) from observations').fetchone()[0]);self.assertEqual(old,entity(db,'WA_MINDEX_PROJECT','J06523','PROJECT_CANDIDATE'))
        self.assertFalse(db.execute("select 1 from entities where kind='PROJECT'").fetchall());self.assertFalse(db.execute('pragma foreign_key_check').fetchall());db.close()

class IntegratedModels(unittest.TestCase):
    def test_reviewed_text_is_null_and_source_quote_is_required(self):
        from au_ree_v2.evidence import normalize
        r=dict(kind='SOURCE_BOUND_SCIENTIFIC_CLAIM',variable='reported_technical_scientific_claim',value=None,scope='sample',statement_id='s',locator='p1',raw_text='Tested sample required impurity removal.',reviewed_interpretations=[{'criterion':'T-B'}])
        self.assertEqual([],normalize(r));self.assertIn('INVALID_TEXTUAL_SCIENTIFIC_CLAIM',normalize(dict(r,raw_text='')))
        self.assertIn('MISSING_OR_NONFINITE',normalize(dict(r,kind='NUMERIC')))
    def test_original_26_dispositions_and_shared_coverage_are_exported(self):
        from au_ree_v2.technical import export_remediation
        import tempfile
        # Real frozen source inventory, not fabricated burden examples.
        with tempfile.TemporaryDirectory(dir=ROOT/'work') as tmp:
            out=Path(tmp);manifest=json.loads((ROOT/'results/phase16-2026-11-04/snapshot_lock.json').read_text())
            export_remediation({'projects':set(),'mapping':{},'inventory':[]},PROFILE,[],out,set(),ROOT,manifest)
            audit=list(csv.DictReader((out/'technical_burden_remediation.csv').open(encoding='utf8')))
            self.assertEqual(26,len(audit));self.assertTrue(all(r['source_selected']=='True' for r in audit))
            toc=[r for r in audit if r['pdf_page']=='21' and r['source_sha256'].startswith('c14ed919')]
            self.assertEqual(1,len(toc));self.assertTrue(toc[0]['disposition'].startswith('REMOVE_'))
    def test_source_contracts_and_common_weight_budget(self):
        from au_ree_v2.analysis import prepare_technical_panel,write_csv
        import tempfile
        cases=json.loads((ROOT/'data/study_cases.json').read_text())['cases'];inventory=[]
        for c in cases:
            for v,value in c['parameters'].items():
                if v not in ('whole_ore_concentrate_recovery_pct','concentrate_treo_grade_pct'):continue
                inventory.append(observation(variable=v,value=value,unit='%',basis=c['element'],project_id=c['project_native_id'],evidence_id=c['case_id']+v,source_sha256=c['source_sha256'],pdf_page=c['pdf_page'],locator=c['locator'],scope=c['scope'],effective_date=c['effective_date'],feed=c['recovery_feed'],endpoint=c['endpoint'],scale=c['scale'],origin='STUDY_PARAMETER',case_id=c['case_id'],raw=c))
        selection={'policy':POLICY,'inventory':inventory}
        with tempfile.TemporaryDirectory(dir=ROOT/'work') as tmp:
            out=Path(tmp);reference=[dict(project_id=c['project_id'],project_name=c['project_id'],D1=.6) for c in inventory]
            write_csv(out/'reference/matrix.csv',reference,['project_id','project_name','D1'])
            prepared={'panels':{'reference':2}};config={'evidence_resolution':POLICY}
            r=prepare_technical_panel(selection,prepared,config,out);self.assertEqual(2,r['n'])
            weights=list(csv.DictReader((out/'technical_process_concentrate_fixed/weights.csv').open()))
            scenarios={r['scenario'] for r in weights};self.assertEqual(10,len(scenarios))
            for scenario in scenarios:
                rows=[r for r in weights if r['scenario']==scenario]
                self.assertAlmostEqual(1,sum(float(r['weight']) for r in rows))
                technical=[r for r in rows if r['group']=='Technical']
                self.assertAlmostEqual(float(technical[0]['group_weight']),sum(float(r['weight']) for r in technical))
            matrix=list(csv.DictReader((out/'technical_process_concentrate_fixed/matrix.csv').open()))
            self.assertTrue(all('R1' not in r for r in matrix));self.assertEqual({'0.84','0.857'},{r['TPR'] for r in matrix})
    def test_duplicate_batch_keys_rejected_and_new_versions_do_not_change_ids(self):
        import tempfile,hashlib
        source=CommodityCompleteness().source();_,rows=minedex_resource_rows(ROOT,source);r=rows[0]['raw'];stream=io.StringIO();writer=csv.DictWriter(stream,fieldnames=list(r));writer.writeheader();writer.writerow(r);writer.writerow(r)
        with tempfile.TemporaryDirectory(dir=ROOT/'work') as tmp:
            root=Path(tmp);file=root/'batch.zip'
            with zipfile.ZipFile(file,'w') as z:z.writestr('resource.csv',stream.getvalue())
            sha=hashlib.sha256(file.read_bytes()).hexdigest()
            with self.assertRaisesRegex(ValueError,'DUPLICATE_PROJECT_COMMODITY'):minedex_resource_rows(root,{'path':'batch.zip','sha256':sha})
            with self.assertRaisesRegex(ValueError,'SHA_MISMATCH'):minedex_resource_rows(root,{'path':'batch.zip','sha256':'wrong'})
    def test_product_diagnostic_reads_same_case_metric_and_source_benchmark(self):
        from au_ree_v2.technical import export_remediation
        import tempfile
        raw={'kind':'SOURCE_BOUND_SCIENTIFIC_CLAIM','case_id':'scoped','raw_text':'Measured impurity was 12%; source benchmark below 3%.','reviewed_interpretations':[{'state':'OBSERVED_SPECIFICATION_OBSTACLE'}],'product_constraint':{'actual_variable':'product_impurity_pct','product':'Named product','benchmark_value':3,'benchmark_unit':'%','operator':'LESS_THAN','benchmark_role':'SOURCE_TYPICAL_ONLY'}}
        claim=observation(variable='reported_technical_scientific_claim',case_id='scoped',value=None,raw=raw)
        metric=observation(variable='product_impurity_pct',case_id='scoped',value=12,evidence_id='metric')
        other=observation(variable='product_impurity_pct',case_id='different-feed',value=1,evidence_id='other')
        with tempfile.TemporaryDirectory(dir=ROOT/'work') as tmp:
            out=Path(tmp);export_remediation({'projects':set(),'mapping':{},'inventory':[claim,metric,other]},PROFILE,[],out,set(),ROOT,[])
            result=list(csv.DictReader((out/'technical_product_constraints.csv').open()))[0]
            self.assertEqual('12',result['actual_value']);self.assertEqual('3',result['benchmark_value']);self.assertEqual(4,float(result['diagnostic_c_over_L']))
            self.assertNotIn('other',result['metric_evidence_ids'])

    def test_batch_source_versions_preserve_record_and_observation_history(self):
        import tempfile,hashlib
        source=CommodityCompleteness().source();_,rows=minedex_resource_rows(ROOT,source);original=rows[0]['raw']
        with tempfile.TemporaryDirectory(dir=ROOT/'work') as tmp:
            root=Path(tmp);db=sqlite3.connect(':memory:');db.row_factory=sqlite3.Row;db.executescript(SCHEMA);ids=[]
            for version in (1,2):
                r=dict(original);r['RES_QTY']=str(float(r['RES_QTY'])+version)
                stream=io.StringIO();writer=csv.DictWriter(stream,fieldnames=list(r));writer.writeheader();writer.writerow(r)
                file=root/f'batch{version}.zip'
                with zipfile.ZipFile(file,'w') as z:z.writestr('resources.csv',stream.getvalue())
                sha=hashlib.sha256(file.read_bytes()).hexdigest();entry=dict(key='official',path=file.name,sha256=sha,publication_date='2026-11-03')
                db.execute('INSERT INTO sources VALUES(?,?,?,?,?,?,?,?)',(sha,'official','https://official.test/batch','2026-11-03','2026-11-05',file.name,'minedex_resource_batch',canonical(entry)))
                ingest_minedex_resources(db,root,entry);ids.append(db.execute("select entity_id from entities where native_namespace='WA_MINEDEX_RESOURCE_PROJECT_COMMODITY'").fetchone()[0])
            self.assertEqual(ids[0],ids[1]);self.assertEqual(12,db.execute('select count(*) from observations').fetchone()[0])
            self.assertEqual(2,db.execute('select count(distinct source_sha) from observations').fetchone()[0]);self.assertEqual([],db.execute('pragma foreign_key_check').fetchall());db.close()

    def test_held_component_hashes_still_fixed(self):
        from tools.evaluate_phase16_remediation import run
        r=run(ROOT);self.assertEqual(3,r['documents']);self.assertTrue(r['rule_freeze_verified']);self.assertTrue(r['no_retuning'])
        self.assertEqual(0,r['quantity_binding_metrics']['TP']);self.assertEqual(3,r['acceptance_metrics']['TN']);self.assertTrue(all(x['attempts'] for x in r['acceptance_results']))

if __name__=='__main__':unittest.main()
