import copy,hashlib,io,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from pypdf import PdfWriter
from au_ree_v2.asx_audit import historical_cases,retest,summary
from au_ree_v2.project_summary import resource_bundle,complete_sum,HEAVY,export_summary
from au_ree_v2.technical_tables import number_token,technical_numbers
from au_ree_v2.pdf_extract import candidate_value_issues
from au_ree_v2.store import connect,entity,filehash,canonical


def observation(variable,value,unit,**extra):
    return dict(variable=variable,value=value,unit=unit,status='AUTO_VALIDATED',basis='TREO',
        source_sha='source',statement_id='statement',scope='one scope',effective_date='2025-01-01',
        obs_id=variable,locator='p1',raw='{}',**extra)


class SummaryRules(unittest.TestCase):
    def setUp(self):self.rows=[observation('ore_mt',10,'Mt'),observation('grade',1000,'ppm')]
    def test_ppm_to_percent_and_declared_contained_derivation(self):
        value,reason=resource_bundle(self.rows)
        self.assertEqual('SELECTED',reason);self.assertEqual(.1,value['value']['grade_pct'])
        self.assertEqual(10,value['value']['contained_treo_kt'])
        self.assertEqual('ORE_MT_X_GRADE_PERCENT_X_10',value['contained_method'])
    def test_cross_source_pair_is_rejected(self):
        self.rows[1]['source_sha']='different'
        self.assertIsNone(resource_bundle(self.rows)[0])
    def test_nested_scopes_are_not_added_or_latest_selected(self):
        other=copy.deepcopy(self.rows)
        for r in other:r.update(scope='nested subset',effective_date='2026-01-01')
        self.assertEqual('MULTIPLE_SCOPES_REQUIRE_DEFINITION',resource_bundle(self.rows+other)[1])
    def test_duplicate_conflicting_variable_is_rejected(self):
        extra=copy.deepcopy(self.rows[0]);extra['value']=11
        self.assertIsNone(resource_bundle(self.rows+[extra])[0])
    def test_reported_contained_conflict_is_rejected(self):
        self.assertIsNone(resource_bundle(self.rows+[observation('contained_treo_kt',100,'kt')])[0])
    def test_reported_contained_respects_rounding(self):
        self.rows[0]['raw']=json.dumps(dict(rounding_half_width=.5))
        selected,_=resource_bundle(self.rows+[observation('contained_treo_kt',10.4,'kt')])
        self.assertEqual(10.4,selected['value']['contained_treo_kt'])
        self.assertEqual('REPORTED',selected['contained_method'])
    def test_partial_heavy_set_stays_unknown_and_explicit_zero_is_kept(self):
        d={k:0. for k in HEAVY}
        self.assertEqual(0,complete_sum(d,HEAVY))
        del d['Y2O3'];self.assertIsNone(complete_sum(d,HEAVY))
        self.assertNotIn('Gd2O3',HEAVY)
    def test_en_dash_keeps_negative_value_and_original_token(self):
        parsed=number_token('–90');self.assertEqual(-90,parsed['value']);self.assertEqual('–90',parsed['original_token'])
        self.assertEqual([60,70],number_token('60–70%')['bounds'])
        self.assertEqual(-1.5,number_token('–1.5')['value'])
        self.assertEqual([-2,-1],number_token('–2 to –1')['bounds'])
        self.assertEqual(-90,technical_numbers('recovery –90%')[0]['value'])
        c=dict(kind='TECHNICAL_TABLE_CELL',original_token='–90',value=-90,bounds=None,unit='%')
        self.assertEqual(['PERCENT_OUT_OF_RANGE'],candidate_value_issues(c))


class CohortRules(unittest.TestCase):
    def fixture(self,root):
        folder=root/'data/snapshots';folder.mkdir(parents=True)
        url='https://www.asx.com.au/asx/v2/statistics/displayAnnouncement.do?display=pdf&idsId=123'
        data=dict(documents=[dict(url=url,failure_status='TERMS_INTERSTITIAL_NOT_ACCEPTED',project_id='P',title='one',publication_date='2025-01-01')]*2)
        raw=(canonical(data)+'\n').encode();sha=hashlib.sha256(raw).hexdigest();p=folder/(sha+'.json');p.write_bytes(raw)
        (root/'data/manifest.json').write_text(json.dumps(dict(snapshots=[dict(kind='discovery_receipt',path=p.relative_to(root).as_posix(),sha256=sha)])))
        return p,url
    def test_repeated_failure_records_have_one_url_denominator(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);self.fixture(root);c=historical_cases(root)
            self.assertEqual(1,len(c['cases']));self.assertEqual(2,len(c['cases'][0]['history']))
    def test_corrupt_historical_receipt_fails_before_retesting(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);p,_=self.fixture(root);p.write_text('{}')
            with self.assertRaisesRegex(ValueError,'HASH_MISMATCH'):historical_cases(root)
    def test_deferred_cases_remain_in_all_url_denominator(self):
        c=dict(cases=[dict(history=[]),dict(history=[])])
        s=summary(c,[dict(status='PDF_ACQUIRED',document_sha256='a',already_in_manifest=False),dict(status='DEFERRED',failure_reason='LOCAL_DISK_RESERVE')])
        self.assertEqual(.5,s['success_rate_all_urls']);self.assertEqual(1,s['success_rate_attempted'])
    def test_resume_does_not_redownload_completed_urls(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t)/'reference';root.mkdir();_,url=self.fixture(root);out=Path(t)/'audit'
            writer=PdfWriter();writer.add_blank_page(width=100,height=100);buf=io.BytesIO();writer.write(buf)
            def fetch(target,**kwargs):return buf.getvalue(),{}
            first=retest(root,out,fetch,min_free_bytes=0)
            def fail(*args,**kwargs):raise AssertionError('must reuse completed audit')
            again=retest(root,out,fail,min_free_bytes=0)
            self.assertEqual(first['outcomes'],again['outcomes'])


class ExportIntegration(unittest.TestCase):
    def test_missing_publication_date_readonly_export_and_candidate_separation(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t)/'ref';(root/'data/snapshots').mkdir(parents=True);run=Path(t)/'run';run.mkdir()
            pdf=root/'data/snapshots/fixture.pdf';pdf.write_bytes(b'%PDF-fixture-immutable')
            sha=filehash(pdf);source=dict(key='fixture',kind='pdf',path='data/snapshots/fixture.pdf',sha256=sha,
                url='https://example.test/a.pdf',publication_date=None,available_date='2025-01-01')
            claims=dict(projects=[dict(id='demo',name='Demo Project',identity_source='fixture',observations=[])])
            cp=root/'data/claims.json';cp.write_text(canonical(claims))
            (run/'snapshot_lock.json').write_text(canonical([source]));(run/'configuration.json').write_text(canonical(dict(claims_sha256=filehash(cp),research={})))
            path=Path(t)/'canonical.sqlite';db=connect(path)
            db.execute('INSERT INTO sources VALUES(?,?,?,?,?,?,?,?)',(sha,'fixture',source['url'],None,'2025-01-01',source['path'],'pdf','{}'))
            pid=entity(db,'project_registry_v1','demo','PROJECT');cid=entity(db,'government','candidate','PROJECT_CANDIDATE')
            for eid,name in [(pid,'Demo Project'),(cid,'Candidate')]:
                db.execute('INSERT INTO records VALUES(?,?,?,?,?,?,?,?,?)',(eid,sha,name,'WA',0.,0.,None,None,'{}'))
            for o in [observation('ore_mt',10,'Mt'),observation('grade',.1,'%')]:
                db.execute('INSERT INTO observations VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                    (o['obs_id'],pid,o['variable'],o['value'],o['unit'],o['basis'],o['scope'],o['statement_id'],None,o['effective_date'],sha,o['locator'],'AUTO_VALIDATED','[]','{}','fixture'))
            db.commit();db.close();before=filehash(path)
            result=export_summary(root,path,run,Path(t)/'export')
            self.assertEqual(1,result['rows']);self.assertEqual(52,result['columns'])
            self.assertEqual(1,result['filled_counts']['緯度']);self.assertEqual(0,result['filled_counts']['預估年產TREO_t_per_year'])
            self.assertEqual(1,result['census_by_kind']['PROJECT_CANDIDATE'])
            self.assertEqual(before,filehash(path))
            # A forecast is taken from its frozen engineering case, never from
            # an unrelated bench result or the global Mineral Resource scope.
            forecast=dict(case_id='forecast',source_sha256=sha,scope='12 year mine plan',effective_date='2025-01-01',
                endpoint='CALCINED_MIXED_REO',element='TREO_INCLUDING_Y',scale='PFS_MODEL',locator='p3',parameters=dict(average_annual_treo_product_t=1860))
            bench=dict(forecast,case_id='bench',scale='BENCH_CONCEPT_ONE_KG',parameters=dict(average_annual_treo_product_t=9999))
            sf=root/'data/study_cases.json';sf.write_text(canonical(dict(cases=[forecast,bench])))
            cf=json.loads((run/'configuration.json').read_text());cf['study_cases.json_sha256']=filehash(sf)
            (run/'configuration.json').write_text(canonical(cf));db=connect(path)
            for s in (forecast,bench):db.execute('INSERT INTO study_cases VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                (s['case_id'],pid,sha,s['effective_date'],s['scope'],3,s['endpoint'],s['element'],s['scale'],'PRIMARY_SCOPED_CASE_NOT_OPERATING_OUTCOME',canonical(s)))
            db.commit();db.close()
            second=export_summary(root,path,run,Path(t)/'with-forecast')
            self.assertEqual(1,second['filled_counts']['預估年產TREO_t_per_year'])
            import csv
            with (Path(t)/'with-forecast/專案總表.csv').open(encoding='utf-8-sig') as stream:row=next(csv.DictReader(stream))
            self.assertEqual('1860',row['預估年產TREO_t_per_year'])
            sf.write_text('{}')
            with self.assertRaisesRegex(ValueError,'FROZEN_STUDY_CASES_DIFFER'):export_summary(root,path,run,Path(t)/'rejected')


if __name__=='__main__':unittest.main()
