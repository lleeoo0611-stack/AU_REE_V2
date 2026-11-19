"""Source changes, unavailable preferred evidence and text claims fail closed."""
import copy,csv,json,tempfile,unittest
from pathlib import Path
import pymupdf
from au_ree_v2.store import connect,canonical,digest,filehash
from au_ree_v2.evidence import ingest_sources,ingest_claims,normalize,transformation_issues,validate_project_attribute
from au_ree_v2.census import export_summary,summary_settings,summary_resource_fields,summary_decision,summary_missing,summary_matching_resource_pdf
from au_ree_v2.pdf_extract import summary_hit_priority,summary_parse_tsv

ROOT=Path(__file__).resolve().parents[1]


class SummaryContractTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);(self.root/'config').mkdir();(self.root/'data').mkdir()
        for name in ('summary_rules.json','project_summary_columns.json','researcher_rule_decisions.json'):
            (self.root/'config'/name).write_bytes((ROOT/'config'/name).read_bytes())
        book=json.loads((self.root/'config/summary_rules.json').read_text(encoding='utf8'))
        cohort=book['parameters']['cohort']['value'];p=cohort[0]
        book['parameters']['cohort']['value']=[p]
        book['parameters']['template.mappings']['value']['development_stage']={}
        (self.root/'config/summary_rules.json').write_text(canonical(book),encoding='utf8')
        doc=pymupdf.open();page=doc.new_page();page.insert_text((50,50),'Wudinna Project\nASX: TST\nResource estimate\nTotal 10 1000 100\nExploration')
        self.pdf=self.root/'data/original.pdf';doc.save(self.pdf);doc.close();sha=filehash(self.pdf)
        self.source=dict(key='doc',kind='pdf',url='https://example.invalid/doc.pdf',sha256=sha,
            source_sha256=sha,path='data/original.pdf',publication_date='2026-01-01',available_date='2026-01-02',acquired_at='2026-01-02')
        self.project=dict(id=p['native_id'],entity_namespace=p['namespace'],name='Wudinna Project',state='SA',identity_source='doc',observations=[],attributes=[])
        common=dict(source_key='doc',source_sha256=sha,pdf_page=1,page_markers=['Resource estimate','Total'],
            scope='Whole selected MRE; excludes reserves and nested subsets',statement_id='mre-1',effective_date='2026-01-01',category='INFERRED',locator='physical PDF p1')
        for variable,value,unit,basis in [('ore_mt',10,'Mt','TREO'),('grade',1000,'ppm','TREO'),('reported_la2o3_ppm',100,'ppm','La2O3')]:
            self.project['observations'].append(dict(common,variable=variable,value=value,unit=unit,basis=basis,
                material_basis='RESOURCE_ORE_GRADE_OXIDE_PPM'))
        for column,value in [('ASX代碼','TST'),('開發階段','Exploration')]:
            self.project['attributes'].append(dict(common,column=column,value=value,extraction_method='REVIEWED_FIXTURE',attribute_id=column))
        (self.root/'config/sources.json').write_text(canonical(dict(sources=[dict(self.source)])),encoding='utf8')
        self.database=self.root/'work/canonical.sqlite'
        self.db=connect(self.database);self.addCleanup(self.db.close)

    def build(self):
        claims=dict(projects=[self.project])
        (self.root/'data/claims.json').write_text(canonical(claims),encoding='utf8')
        ingest_sources(self.db,self.root,[self.source])
        ingest_claims(self.db,self.root,[self.source],'2026-11-13',claims_data=claims,conflict_selection=True)
        self.db.execute('INSERT INTO runs VALUES(?,?,?,?,?,?,?,?)',('run','2026-11-15','2026-11-13','{}','config','sources','COMPLETED',None));self.db.commit()

    def export(self):
        out=self.root/'export';coverage=export_summary(self.root,self.database,out)
        with (out/'專案總表.csv').open(encoding='utf8',newline='') as f:rows=list(csv.DictReader(f))
        with (out/'field_provenance.csv').open(encoding='utf8',newline='') as f:trace=list(csv.DictReader(f))
        with (out/'missing_fields.csv').open(encoding='utf8',newline='') as f:missing=list(csv.DictReader(f))
        return coverage,rows,trace,missing

    def test_every_cell_is_accounted_for_and_export_does_not_write_database(self):
        self.build();before=filehash(self.database)
        coverage,rows,trace,missing=self.export()
        self.assertEqual(filehash(self.database),before)
        self.assertEqual(len(rows[0]),51);self.assertEqual(len(trace),51)
        self.assertEqual(float(rows[0]['總TREO蘊藏量_kt']),10)
        self.assertEqual(float(rows[0]['La2O3_氧化鑭_kt']),1)
        self.assertEqual(rows[0]['ASX代碼'],'TST');self.assertEqual(rows[0]['開發階段代碼'],'A2')
        self.assertEqual(coverage['filled_cells']+len(missing),51)
        self.assertEqual(coverage['column_count'],51)
        self.assertEqual(set(coverage['columns']),set(rows[0]))
        self.assertEqual(sum(c['filled'] for c in coverage['columns'].values()),coverage['filled_cells'])
        for name,sha in coverage['export_contract_sha256'].items():self.assertEqual(sha,filehash(self.root/'config'/name))
        for t in trace:
            if t['value'] and t['column'] not in ('專案ID','國家'):
                self.assertEqual(t['source_sha256'],self.source['sha256'])
        listing=next(t for t in trace if t['column']=='ASX代碼')
        self.assertTrue(json.loads(listing['attribute_ids']));self.assertEqual(listing['pdf_page'],'1')

    def test_completed_integrated_export_restores_external_snapshot_and_audit(self):
        with tempfile.TemporaryDirectory() as outside:
            original=Path(outside)/'original.pdf'
            original.write_bytes(self.pdf.read_bytes())
            self.source['path']=str(original)
            self.build()
            run=self.root/'work/runs/run'
            run.mkdir(parents=True)
            config=dict(source_mode='offline',sources=dict(sources=[self.source]))
            lock=[self.source]
            (run/'configuration.json').write_text(canonical(config),encoding='utf8')
            (run/'snapshot_lock.json').write_text(canonical(lock),encoding='utf8')
            (run/'canonical_membership.csv').write_text('kind,canonical_id\n',encoding='utf8')
            self.db.execute('UPDATE runs SET config_sha=?,snapshot_sha=?',(digest(config),digest(lock)))
            self.db.commit()
            before=filehash(self.database)
            coverage,rows,_,_=self.export()
            self.assertEqual(rows[0]['ASX代碼'],'TST')
            self.assertIn('field_status_counts',coverage)
            self.assertTrue((self.root/'export/resource_statement_observations.csv').is_file())
            self.assertEqual(filehash(self.database),before)
            (run/'snapshot_lock.json').write_text('[]',encoding='utf8')
            with self.assertRaisesRegex(ValueError,'SUMMARY_RUN_SNAPSHOT_HASH_MISMATCH'):
                export_summary(self.root,self.database,self.root/'tampered')
            self.assertFalse((self.root/'tampered').exists())

    def test_reported_oxide_groups_fill_only_matching_group_totals(self):
        claim=self.project['observations'][0]
        ndpr=dict(claim,variable='reported_resource_ndpr_ppm',value=120,unit='ppm',
            basis='NdPr_OXIDES',material_basis='RESOURCE_ORE_GRADE_NDPR_OXIDE_GROUP_PPM')
        magnet=dict(claim,variable='reported_resource_magnet_ppm',value=200,unit='ppm',
            basis='PrNdDyTb_OXIDES',material_basis='RESOURCE_ORE_GRADE_MAGNET_OXIDE_GROUP_PPM')
        other=dict(ndpr,value=350,scope='A different cut-off',statement_id='mre-other')
        self.project['observations'].extend((ndpr,magnet,other))
        self.build()
        _,rows,_,_=self.export()
        row=rows[0]
        self.assertAlmostEqual(1.2,float(row['NdPr蘊藏量_kt_需兩者皆公布']))
        self.assertAlmostEqual(2,float(row['磁鐵稀土氧化物蘊藏量_kt']))
        self.assertAlmostEqual(20,float(row['磁鐵稀土佔TREO_pct']))
        self.assertFalse(row['磁性元素重算值_NdPrTbDy_kt'])
        self.assertFalse(row['四項磁性元素皆公布'])
        self.assertFalse(any(value for key,value in row.items() if key.startswith(('Nd2O3_','Pr6O11_'))))

    def test_pdf_supplement_pins_primary_scope_category_and_totals(self):
        key=dict(scope='Selected whole MRE',statement_id='mre-1',effective_date='2026-01-01')
        values=dict(ore_mt=10,grade_pct=0.1,contained_treo_kt=10)
        bundle=dict(key,source_sha256='primary',value=values,observations=[dict(variable='ore_mt',category='INFERRED')])
        obs=dict(key,source_sha='pdf',category='INFERRED')
        raw=dict(page_extraction_sha256='page',census_equivalent_resource_pdf=dict(values,source_sha256='primary'))
        self.assertTrue(summary_matching_resource_pdf(obs,raw,bundle))
        self.assertFalse(summary_matching_resource_pdf(dict(obs,category='INDICATED'),raw,bundle))
        self.assertFalse(summary_matching_resource_pdf(dict(obs,effective_date='2026-02-01'),raw,bundle))
        self.assertFalse(summary_matching_resource_pdf(obs,dict(raw,page_extraction_sha256=''),bundle))
        self.assertFalse(summary_matching_resource_pdf(obs,raw,dict(bundle,value=dict(values,contained_treo_kt=9.99))))

    def test_oxide_mass_requires_complete_reconciling_resource_blocks(self):
        ore=self.project['observations'][0]
        parts=[dict(block='A',ore_t=4000000,grade_ppm='100.0',contained_t=400),
               dict(block='B',ore_t=6000000,grade_ppm='120.0',contained_t=720)]
        claim=dict(ore,variable='reported_resource_contained_y2o3_kt',basis='Y2O3',unit='kt',value=1.12,
            material_basis='RESOURCE_CONTAINED_OXIDE_MASS_KT',
            transform=dict(rule='SUM_RECONCILED_RESOURCE_BLOCK_MASSES',reported_total_t=1120,blocks=parts))
        self.assertEqual([],transformation_issues(claim,[ore]))
        parts[1]['contained_t']=726
        self.assertEqual(['TRANSFORMATION_CONTRACT_FAILED'],transformation_issues(claim,[ore]))
        parts[1].update(contained_t=720,ore_t=5000000)
        self.assertEqual(['TRANSFORMATION_CONTRACT_FAILED'],transformation_issues(claim,[ore]))

    def test_category_oxide_mass_requires_both_categories_at_the_same_cutoff(self):
        parts=[dict(category='INDICATED',ore_mt=160,treo_ppm=1700,cutoff_treo_ppm=1000,oxide_ppm=84),
               dict(category='INFERRED',ore_mt=1500,treo_ppm=1700,cutoff_treo_ppm=1000,oxide_ppm=82)]
        claim=dict(category='INDICATED_INFERRED_TOTAL',value=136.44,unit='kt',
            material_basis='RESOURCE_CONTAINED_OXIDE_MASS_KT',
            census_equivalent_resource_pdf=dict(ore_mt=1700,grade_pct=0.17),
            transform=dict(rule='SUM_SAME_CUTOFF_CATEGORY_OXIDE_MASSES',categories=parts,
                cutoff_treo_ppm=1000,total_ore_rounding_half_width_mt=50))
        self.assertEqual([],transformation_issues(claim,[]))
        parts[1]['cutoff_treo_ppm']=1500
        self.assertEqual(['TRANSFORMATION_CONTRACT_FAILED'],transformation_issues(claim,[]))
        parts[1].update(cutoff_treo_ppm=1000,category='INDICATED')
        self.assertEqual(['TRANSFORMATION_CONTRACT_FAILED'],transformation_issues(claim,[]))

    def test_changed_original_withholds_all_source_bound_values(self):
        self.build();self.pdf.write_bytes(b'changed original')
        _,rows,_,missing=self.export()
        self.assertEqual(rows[0]['礦石蘊藏量_Mt'],'');self.assertEqual(rows[0]['ASX代碼'],'')
        gaps={r['column']:r for r in missing}
        self.assertEqual(gaps['礦石蘊藏量_Mt']['reason'],'SOURCE_SHA_CHANGED')
        self.assertEqual(gaps['ASX代碼']['reason'],'SOURCE_SHA_CHANGED')

    def test_text_marker_failure_queues_attribute_and_cannot_fill_cell(self):
        self.project['attributes'][0]['page_markers']=['Resource estimate','not on this page']
        self.build();_,rows,_,missing=self.export()
        self.assertEqual(rows[0]['ASX代碼'],'')
        issue=self.db.execute("SELECT * FROM review_queue WHERE reason='EXTRACTION_PAGE_CHECK_FAILED'").fetchone()
        self.assertIsNotNone(issue)
        self.assertIn(issue['issue_id'],next(r['details'] for r in missing if r['column']=='ASX代碼'))
        self.assertNotIn(issue['issue_id'],next(r['details'] for r in missing if r['column']=='Y2O3_氧化釔_kt'))
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM observations WHERE variable='project_attribute' AND value IS NOT NULL").fetchone()[0],0)

    def test_blank_researcher_approval_does_not_activate_native_stage_rule(self):
        path=self.root/'config/researcher_rule_decisions.json';d=json.loads(path.read_text(encoding='utf8'))
        for decision in d['decisions']:
            if decision['rule']=='EXPLORATION_WITH_SELECTED_MRE':decision['decided_by']=''
        path.write_text(canonical(d),encoding='utf8');self.build()
        _,rows,_,missing=self.export()
        self.assertEqual(rows[0]['開發階段代碼'],'')
        self.assertEqual(next(r['reason'] for r in missing if r['column']=='開發階段代碼'),'RULE_INPUT_MISSING')

    def test_preferred_mre_missing_cannot_fall_back_to_another_scope(self):
        self.build();rules,decisions=summary_settings(self.root)
        observations=[dict(o) for o in self.db.execute("SELECT * FROM observations WHERE variable!='project_attribute'")]
        wanted=dict(source_sha256='0'*64,statement_id='different-reviewed-mre',scope='Different resource',effective_date='2026-01-01')
        project=dict(observations=[dict(variable='ore_mt',raw=dict(review_contract=wanted))])
        row={c:'' for c in json.loads((self.root/'config/project_summary_columns.json').read_text(encoding='utf8'))}
        writes=[]
        bundle,_,_=summary_resource_fields(row,observations,{self.source['sha256']:self.source},rules,decisions,
            lambda *args,**kwargs:writes.append(args),project)
        self.assertIsNone(bundle);self.assertEqual(writes,[])

    def test_preferred_mre_accepts_matching_supplemental_oxide_pdf(self):
        ore = self.project['observations'][0]
        fields = ('source_sha256', 'statement_id', 'scope', 'effective_date')
        ore['raw'] = {'review_contract': {key: ore[key] for key in fields}}
        self.build()
        rules, decisions = summary_settings(self.root)
        observations = [dict(o) for o in self.db.execute(
            "SELECT * FROM observations WHERE variable!='project_attribute'")]
        primary = next(o for o in observations if o['variable'] == 'ore_mt')
        reference = dict(source_sha256=self.source['sha256'], ore_mt=10, grade_pct=0.1, contained_treo_kt=10)
        raw = dict(page_extraction_sha256='2'*64, census_equivalent_resource_pdf=reference,
                   material_basis='RESOURCE_ORE_GRADE_OXIDE_PPM')
        supplement = dict(primary, obs_id='supplement-ce', source_sha='1'*64, basis='CeO2',
                          variable='reported_ceo2_ppm', unit='ppm', value=120,
                          locator='supplemental PDF p2', raw=canonical(raw))
        wrong_scope = dict(supplement, obs_id='outside-dy', variable='reported_dy2o3_ppm',
                           basis='Dy2O3', scope='Nested higher-grade resource only')
        concentrate = dict(supplement, obs_id='concentrate-er', variable='reported_er2o3_ppm', basis='Er2O3',
                           raw=canonical(dict(raw, material_basis='CONCENTRATE_OXIDE_PPM')))
        observations.extend((supplement, wrong_scope, concentrate))
        row = dict.fromkeys(json.loads((self.root/'config/project_summary_columns.json').read_text(encoding='utf8')), '')
        trace = {}

        def put(column, value, source, *evidence):
            row[column] = value
            trace[column] = source

        bundle, _, _ = summary_resource_fields(row, observations, {self.source['sha256']: self.source},
                                                rules, decisions, put, self.project)
        self.assertEqual(self.source['sha256'], bundle['source_sha256'])
        self.assertEqual('doc', row['資料來源名稱'])
        self.assertAlmostEqual(1.2, row['CeO2_氧化鈰_kt'])
        self.assertEqual(supplement['source_sha'], trace['CeO2_氧化鈰_kt'])
        self.assertEqual('', row['Dy2O3_氧化鏑_kt'])
        self.assertEqual('', row['Er2O3_氧化鉺_kt'])
        self.assertEqual(2, row['已公布元素數_共15項'])

    def test_older_review_role_keeps_context_only_resource_out_of_preferred_scope(self):
        ore=self.project['observations'][0]
        fields=('source_sha256','statement_id','scope','effective_date')
        ore['raw']={'review_contract':{key:ore[key] for key in fields}}
        context=dict(ore,statement_id='context-only',scope='Separate context resource',value=20)
        context['raw']={'review_contract':{key:context[key] for key in fields}
            | {'resource_selection_role':'CONTEXT_ONLY'}}
        self.project['observations'].append(context)
        self.build()
        _,rows,_,_=self.export()
        self.assertEqual(float(rows[0]['礦石蘊藏量_Mt']),10)

    def test_archived_html_support_is_limited_to_exact_deposit_evidence(self):
        p=self.root/'data/host.html'
        p.write_text('<p>Pidinga and Garford</p><p>Clay adsorption</p>',encoding='utf8')
        sha=filehash(p)
        source=dict(self.source,key='host',kind='html',path='data/host.html',sha256=sha)
        a=dict(column='礦床型態',value='Reviewed host support',source_sha256=sha,
            locator='geological setting',effective_date='2026-01-01',support_only=True,
            extraction_method='REVIEWED_FIXTURE',deposit_host_review={'code':'iac'},
            source_markers=['Pidinga and Garford','Clay adsorption'])
        validate_project_attribute(self.root,source,a,[source])
        for change in [dict(column='ASX代碼'),dict(support_only=False),dict(source_markers=['Clay adsorption']),
                       dict(source_markers=['Pidinga and Garford','Missing original text'])]:
            with self.subTest(change=change),self.assertRaises(ValueError):
                validate_project_attribute(self.root,source,dict(a,**change),[source])

    def test_government_attribute_requires_exact_layer_feature_and_native_field(self):
        p=self.root/'data/layer.json';p.write_text(canonical(dict(features=[dict(attributes=dict(OBJECTID=17,owner='Reviewed developer'))])),encoding='utf8')
        sha=filehash(p);source=dict(kind='government_arcgis',sha256=sha,path='data/layer.json')
        a=dict(column='開發商',value='Reviewed developer',source_sha256=sha,layer_sha256=sha,feature_id=17,source_field='owner',
            locator='layer feature 17; owner',effective_date='2026-01-01',extraction_method='REVIEWED_NATIVE_FEATURE')
        validate_project_attribute(self.root,source,a,[source])
        for change in [dict(feature_id=18),dict(layer_sha256='0'*64),dict(value='other developer')]:
            with self.subTest(change=change),self.assertRaises(ValueError):validate_project_attribute(self.root,source,dict(a,**change),[source])

    def test_unrelated_metallurgy_sha_change_cannot_explain_missing_resource_oxide(self):
        rules,decisions=summary_settings(ROOT)
        project=copy.deepcopy(self.project)
        project['observations'].append(dict(variable='reported_technical_desorption_ndpr_pct',source_key='bench',source_sha256='0'*64))
        row={'專案名稱':'Wudinna Project','開發階段代碼':''}
        reason,detail=summary_missing('La2O3_氧化鑭_kt',project,row,{}, {'doc':self.source,'bench':dict(self.source,key='bench')},
            {self.source['sha256']:self.source},{'bench':'SOURCE_SHA_CHANGED'},{'bench':dict(status='SOURCE_SHA_CHANGED')},'2026-11-13',rules,decisions)
        self.assertEqual(reason,'RULE_INPUT_MISSING');self.assertNotIn('bench',detail)

    def test_rejected_identity_binding_is_rule_input_gap_even_when_source_is_acquired(self):
        rules,decisions=summary_settings(ROOT);project=dict(self.project,identity_declaration={'pdf_page':1})
        reason,_=summary_missing('專案名稱',project,{'專案名稱':'','開發階段代碼':''},None,{'doc':self.source},
            {self.source['sha256']:self.source},{},{},'2026-11-13',rules,decisions)
        self.assertEqual(reason,'RULE_INPUT_MISSING')

    def test_annual_gap_uses_declared_study_source_and_not_resource_or_other_product(self):
        rules,decisions=summary_settings(ROOT);project=copy.deepcopy(self.project)
        project['attributes'].append(dict(column='產品/產出',source_key='study',source_sha256='1'*64,
            engineering_forecast={'parameters':{'average_annual_treo_product_t':1000}}))
        registry={'doc':self.source,'study':dict(self.source,key='study',sha256='1'*64)}
        args=(project,{'專案名稱':'Wudinna Project','開發階段代碼':''},{},registry,{self.source['sha256']:self.source},{},
            {'study':dict(status='SOURCE_NOT_ACQUIRED')},'2026-11-13',rules,decisions)
        reason,detail=summary_missing('預估年產TREO_t_per_year',*args)
        self.assertEqual(reason,'SOURCE_NOT_ACQUIRED');self.assertIn('study',detail)
        reason,detail=summary_missing('預估年產NdPr_t_per_year',*args)
        self.assertEqual(reason,'RULE_INPUT_MISSING');self.assertNotIn('study',detail)

    def test_committed_same_sha_source_alias_is_acquired_even_under_another_key(self):
        rules,decisions=summary_settings(ROOT)
        project=dict(self.project,identity_source='alias',identity_declaration={'pdf_page':1})
        alias=dict(self.source,key='alias',committed_snapshot_sha256=self.source['sha256'])
        reason,_=summary_missing('專案名稱',project,{'專案名稱':'','開發階段代碼':''},None,{'alias':alias},
            {self.source['sha256']:self.source},{},{},'2026-11-13',rules,decisions)
        self.assertEqual(reason,'RULE_INPUT_MISSING')


class IntegratedRuleTests(unittest.TestCase):
    def test_contains_product_grade_and_correct_annual_mass_unit(self):
        from au_ree_v2.technical import summary_annual_hmc_card
        review=dict(scope='HMC',statement_id='hmc',source_sha256='a'*64,effective_date='2026-04-10',pdf_page=1)
        study=dict(endpoint='MINERAL_CONCENTRATE',annual_basis_evidence={'page':1})
        text='Product & Annual Production Rate • HMC (2.6% TREO in monazite and xenotime, 18.0% ZrO2+Hf02, 25.2% TiO2 in ilmenite; 7.5% TiO2 in rutile): 280ktpa'
        for statement,expected,valid in ((text,7280,True),(text,280000,False),(text.replace('280ktpa','280tpa'),7280,False),(text.replace('TREO','NdPr'),7280,False)):
            with self.subTest(statement=statement,expected=expected),pymupdf.open() as doc:
                page=doc.new_page(width=1000,height=100)
                # WinAnsi byte 0x95 maps to a native bullet in the built-in font.
                page.insert_text((10,28),statement.replace('•',chr(149)),fontsize=10)
                spec=dict(review,evidence={'page':1},bbox=[5,5,995,48],statement=statement)
                args=(doc,review,study,spec,'average_annual_treo_product_t',expected,lambda e:None)
                if valid:summary_annual_hmc_card(*args)
                else:
                    with self.assertRaises(ValueError):summary_annual_hmc_card(*args)

    def test_issuer_ndpr_output_needs_annual_hmc_context_and_oxide_label(self):
        from au_ree_v2.technical import summary_annual_cell
        field='average_annual_ndpr_product_t'
        heading='Once operational, the project will produce up to 280,000 tonnes per year of heavy mineral concentrate (HMC), including approximately:'
        unit_label='tonnes of light rare earth oxides (neodymium and praseodymium)'
        for context,label,valid in ((heading,unit_label,True),(heading.replace('per year','in total'),unit_label,False),(heading,unit_label.replace(' oxides',' minerals'),False)):
            with self.subTest(context=context,label=label),pymupdf.open() as doc:
                page=doc.new_page(width=850,height=100)
                page.insert_text((10,20),context,fontsize=9)
                statement='1,800 '+label
                page.insert_text((10,42),statement,fontsize=9)
                claim=dict(mode='native_statement',field=field,scope='HMC',page=1,original_unit='tonnes',
                    semantic_profile='annual_hmc_contained_ndpr_oxide',statement_bbox=[5,29,845,47],statement=statement,
                    before='',after=label,time_basis_bbox=[5,5,845,24])
                args=(doc,claim,field,'1800','tonnes','HMC')
                if valid:self.assertEqual(summary_annual_cell(*args),'NATIVE_SCOPED_STATEMENT_BINDING')
                else:
                    with self.assertRaises(ValueError):summary_annual_cell(*args)

    def test_new_individual_vocabulary_never_uses_total_variable(self):
        rules,_=summary_settings(ROOT);mapping={'La2O3':'la2o3','CeO2':'ceo2','Sm2O3':'sm2o3','Eu2O3':'eu2o3','Gd2O3':'gd2o3','Ho2O3':'ho2o3','Er2O3':'er2o3','Tm2O3':'tm2o3','Yb2O3':'yb2o3','Lu2O3':'lu2o3'}
        claims=json.loads((ROOT/'data/claims.json').read_text(encoding='utf8'))
        added=[o for p in claims['projects'] for o in p['observations']
            if o.get('extraction_method')=='INTEGRATED_REVIEW_MIGRATED_REVERIFIED_AT_BUILD'
            and o.get('basis') in mapping and o.get('raw',{}).get('reviewed_observation')]
        self.assertEqual(len(added),157)
        for o in added:
            original=o['raw']['reviewed_observation']
            self.assertEqual(o['variable'],'reported_'+mapping[o['basis']]+'_ppm')
            for field in ('value','unit','basis'):self.assertEqual(o[field],original[field])
            self.assertGreaterEqual(len(o['page_markers']),2)
            self.assertEqual(o['pdf_page'],original['evidence']['page'])

    def test_priority_fail_dominates_unclear_and_ocr_average_counts_all_words(self):
        self.assertEqual(summary_hit_priority('PASS','FAIL','UNCLEAR'),'FAIL')
        rules,_=summary_settings(ROOT);settings=rules['ocr_settings']
        header='level\tpage_num\tblock_num\tpar_num\tline_num\tconf\ttext\n'
        rows=''.join('5\t1\t1\t1\t1\t100\tword\n' for _ in range(20))+'5\t1\t1\t1\t2\t0\tbad\n'*30
        quality=summary_parse_tsv((header+rows).encode(),settings)
        self.assertEqual(quality['status'],'OCR_LOW_CONFIDENCE');self.assertEqual(quality['mean_word_confidence'],40)

    def test_unapproved_or_different_statement_cannot_trigger_scoped_cerium_rule(self):
        rules,decisions=summary_settings(ROOT)
        identity=next(v for v in rules['oxide_exception_identities'].values() if 'splinter' in v[1])
        bundle=dict(statement_id=identity[1],source_sha256='0'*64)
        self.assertIsNone(summary_decision(decisions,'CE2O3_TO_CEO2_STOICHIOMETRIC',identity[0],bundle))
        self.assertIsNone(summary_decision([],'CE2O3_TO_CEO2_STOICHIOMETRIC',identity[0],dict(bundle,source_sha256=identity[2])))


if __name__=='__main__':unittest.main()
