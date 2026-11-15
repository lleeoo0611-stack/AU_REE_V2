"""Source changes, unavailable preferred evidence and text claims fail closed."""
import copy,csv,json,tempfile,unittest
from pathlib import Path
import pymupdf
from au_ree_v2.store import connect,canonical,digest,filehash
from au_ree_v2.evidence import ingest_sources,ingest_claims,normalize,validate_project_attribute
from au_ree_v2.census import export_summary,summary_settings,summary_resource_fields,summary_decision
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
        for t in trace:
            if t['value'] and t['column'] not in ('專案ID','國家'):
                self.assertEqual(t['source_sha256'],self.source['sha256'])
        listing=next(t for t in trace if t['column']=='ASX代碼')
        self.assertTrue(json.loads(listing['attribute_ids']));self.assertEqual(listing['pdf_page'],'1')

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

    def test_government_attribute_requires_exact_layer_feature_and_native_field(self):
        p=self.root/'data/layer.json';p.write_text(canonical(dict(features=[dict(attributes=dict(OBJECTID=17,owner='Reviewed developer'))])),encoding='utf8')
        sha=filehash(p);source=dict(kind='government_arcgis',sha256=sha,path='data/layer.json')
        a=dict(column='開發商',value='Reviewed developer',source_sha256=sha,layer_sha256=sha,feature_id=17,source_field='owner',
            locator='layer feature 17; owner',effective_date='2026-01-01',extraction_method='REVIEWED_NATIVE_FEATURE')
        validate_project_attribute(self.root,source,a,[source])
        for change in [dict(feature_id=18),dict(layer_sha256='0'*64),dict(value='other developer')]:
            with self.subTest(change=change),self.assertRaises(ValueError):validate_project_attribute(self.root,source,dict(a,**change),[source])


class IntegratedRuleTests(unittest.TestCase):
    def test_new_individual_vocabulary_never_uses_total_variable(self):
        rules,_=summary_settings(ROOT);mapping={'La2O3':'la2o3','CeO2':'ceo2','Sm2O3':'sm2o3','Eu2O3':'eu2o3','Gd2O3':'gd2o3','Ho2O3':'ho2o3','Er2O3':'er2o3','Tm2O3':'tm2o3','Yb2O3':'yb2o3','Lu2O3':'lu2o3'}
        claims=json.loads((ROOT/'data/claims.json').read_text(encoding='utf8'))
        added=[o for p in claims['projects'] for o in p['observations'] if o.get('extraction_method')=='INTEGRATED_REVIEW_MIGRATED_REVERIFIED_AT_BUILD' and o.get('basis') in mapping]
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
