"""Official report protocols, transport truth and native-table regression."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from au_ree_v2.acquisition import ckan,arcgis,request
from au_ree_v2.discovery import discover,live_status
from au_ree_v2.security import sensitive_reference
from tools.evaluate_documents import evaluate_phase13,evaluate_phase14
ROOT=Path(__file__).resolve().parents[1]

def encoded(data):return json.dumps(data).encode(),{}

class OfficialReportTests(unittest.TestCase):
    def test_ckan_bound_count_and_original_pages(self):
        pages=[];calls=[]
        def fetch(url,params):
            calls.append(params)
            return encoded(dict(success=True,result=dict(count=5,results=[dict(id=str(i)) for i in range(params['start'],min(5,params['start']+2))])))
        d=ckan('https://official.test/api','rare earth',2,2,fetch,pages.append)
        self.assertEqual(4,len(d['results']));self.assertFalse(d['inventory']['complete'])
        self.assertEqual(5,d['inventory']['matched_count']);self.assertEqual([0,2],[c['start'] for c in calls]);self.assertEqual(2,len(pages))

    def test_ckan_http200_errors_duplicate_and_count_drift_fail(self):
        for response in [dict(success=False),dict(success=True,result=dict(count=3,results=[dict(id='same'),dict(id='same')]))]:
            with self.assertRaises(ValueError):ckan('https://official.test','x',2,2,lambda *a:encoded(response))
        responses=iter([dict(success=True,result=dict(count=3,results=[dict(id='1'),dict(id='2')])),dict(success=True,result=dict(count=4,results=[dict(id='3')]))])
        with self.assertRaisesRegex(ValueError,'COUNT_CHANGED'):ckan('https://official.test','x',2,2,lambda *a:encoded(next(responses)))

    def test_arcgis_budget_retains_full_native_inventory_and_geometry(self):
        def fetch(url,params):
            if 'returnIdsOnly' in params:return encoded(dict(objectIdFieldName='oid',objectIds=[3,1,2]))
            return encoded(dict(features=[dict(attributes=dict(oid=int(i)),geometry=dict(x=1,y=2)) for i in params['objectIds'].split(',')]))
        d=arcgis('https://official.test',fetch=fetch,max_records=2)
        self.assertEqual([1,2],[r['attributes']['oid'] for r in d['features']]);self.assertFalse(d['inventory']['complete']);self.assertEqual(3,d['inventory']['matched_count'])

    def test_post_read_encodes_parameters_in_body(self):
        class Response:
            headers={}
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def read(self):return b'{}'
        with patch('urllib.request.urlopen',return_value=Response()) as op:
            request('https://official.test/read',{'aNumber[0]':5},method='POST')
        req=op.call_args.args[0];self.assertEqual('POST',req.method);self.assertEqual(b'aNumber%5B0%5D=5',req.data)

    def test_signed_wamex_is_transient_idempotent_and_candidate_only(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'work') as tmp:
            root=Path(tmp);(root/'data/snapshots').mkdir(parents=True);(root/'data/manifest.json').write_text('{"snapshots":[]}')
            signed='https://warsydprdstagsdspub.blob.core.windows.net/a.pdf'+'?'+'sig=DO_NOT_PUBLISH&se=2030'
            downloads=[];revision=[1]
            def fetch(url,params=None,**kw):
                if url==signed:downloads.append(url);return b'%PDF-test',{}
                if 'ReportDocuments_Read' in url:
                    self.assertEqual('POST',kw['method'])
                    return encoded(dict(Total=1,Data=[dict(ANumber=777,FileType='.pdf',BLTId=123,FileName='report.pdf',FileSize='1 MB',EditDate=str(revision[0]),Link=signed)]))
                if params.get('returnIdsOnly'):return encoded(dict(objectIdFieldName='objectid',objectIds=[1]))
                return encoded(dict(features=[dict(attributes=dict(objectid=1,anumber=777,title='Example Project metallurgy',project='Example',date_released=1609459200000,report_year=2020,dpxe_rep='https://wamex.dmp.wa.gov.au/Wamex/Search/ReportDetails?ANumber=777'),geometry=dict(rings=[]))]))
            config=dict(seeds=[],registry_tasks=True,task_execution_version='bounded',max_official_details=1,
                official_reports=[dict(key='wamex',protocol='arcgis',url='https://official.test',where='1=1',max_records=2)])
            tasks=[dict(project_id='stable',aliases=['Example'],company=None,seed_keys=[])]
            with patch('au_ree_v2.discovery.search_tasks',return_value=tasks):
                a=discover(root,config,fetch);b=discover(root,config,fetch)
            self.assertEqual(1,len(downloads));self.assertEqual('REUSED_VERIFIED_ORIGINAL',b['documents'][0]['status'])
            self.assertEqual('CANDIDATE_ONLY_NO_ENTITY_EQUIVALENCE',a['official_reports'][0]['relation_status'])
            public=(root/'data/manifest.json').read_text()+(root/'data/discovery_latest.json').read_text()+''.join(p.read_text() for p in (root/'data/snapshots').glob('*.json'))
            self.assertNotIn('DO_NOT_PUBLISH',public);self.assertFalse(sensitive_reference(public));self.assertIn('EPHEMERAL_SIGNED_URL_OMITTED',public)
            self.assertTrue(list((root/'work/retained_originals').glob('*.json')))
            revision[0]=2
            with patch('au_ree_v2.discovery.search_tasks',return_value=tasks):discover(root,config,fetch)
            self.assertEqual(2,len(downloads))
            versions=[s for s in json.loads((root/'data/manifest.json').read_text())['snapshots'] if s['kind']=='pdf']
            self.assertEqual(2,len(versions));self.assertEqual(1,len({s['sha256'] for s in versions}))

    def test_gsq_login_html_is_failed_download_not_pdf_or_search_success(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'work') as tmp:
            root=Path(tmp);(root/'data/snapshots').mkdir(parents=True);(root/'data/manifest.json').write_text('{"snapshots":[]}')
            package=dict(id='pkg',name='cr001',title='Rare earth report',open_file_date='2020-01-01',resources=[dict(id='r',format='PDF',download_url='https://official.test/file',name='report',**{'resource:size':'1 MB'})])
            def fetch(url,params=None,**kw):
                if url.endswith('package_search'):return encoded(dict(success=True,result=dict(count=1,results=[package])))
                if url.endswith('package_show'):return encoded(dict(success=True,result=package))
                return b'<html>Single Sign On</html>',{}
            config=dict(seeds=[],official_reports=[dict(key='gsq',protocol='ckan',url='https://official.test/',query='rare earth',document_hosts=['official.test'])])
            result=discover(root,config,fetch);status=live_status(result)
            self.assertEqual('PARTIAL_FAILURE',status['status']);self.assertEqual(1,status['download_failures']);self.assertEqual(0,status['downloaded_originals']);self.assertEqual(0,status['source_failures']);self.assertEqual({'NON_PDF_RESPONSE':1},status['failure_reasons']);self.assertIsNone(status['validated_numeric_observations'])

    def test_local_failure_does_not_stop_other_official_index(self):
        def fetch(url,params):
            if 'bad' in url:raise HTTPError(url,403,'',{},None)
            return encoded(dict(success=True,result=dict(count=0,results=[])))
        with tempfile.TemporaryDirectory(dir=ROOT/'work') as tmp:
            root=Path(tmp);(root/'data/snapshots').mkdir(parents=True);(root/'data/manifest.json').write_text('{"snapshots":[]}')
            config=dict(seeds=[],official_reports=[dict(key=k,protocol='ckan',url='https://'+k+'.test',query='rare earth') for k in ['bad','good']])
            r=discover(root,config,fetch);self.assertEqual(['UNAVAILABLE','PARSED'],[s['status'] for s in r['sources']])

    def test_package_show_failure_keeps_valid_search_metadata(self):
        def fetch(url,params=None,**kw):
            if url.endswith('package_show'):raise HTTPError(url,403,'',{},None)
            return encoded(dict(success=True,result=dict(count=1,results=[dict(id='pkg',name='cr001',resources=[])])))
        with tempfile.TemporaryDirectory(dir=ROOT/'work') as tmp:
            root=Path(tmp);(root/'data/snapshots').mkdir(parents=True);(root/'data/manifest.json').write_text('{"snapshots":[]}')
            r=discover(root,dict(seeds=[],official_reports=[dict(key='gsq',protocol='ckan',url='https://official.test',query='rare earth')]),fetch)
            self.assertEqual(1,len(r['official_reports']));self.assertEqual(['UNAVAILABLE','PARSED'],[x['status'] for x in r['sources']])

    def test_actual_document_bytes_are_bounded_before_persistence(self):
        class Response:
            headers={}
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def read(self,n):self.requested=n;return b'x'*n
        response=Response()
        with patch('urllib.request.urlopen',return_value=response):
            with self.assertRaisesRegex(ValueError,'BYTE_BUDGET'):request('https://public.test/report',max_bytes=10)
        self.assertEqual(11,response.requested)

    def test_live_parsing_is_not_blocked_by_frozen_study_cutoff(self):
        import argparse
        from datetime import datetime,timezone
        from au_ree_v2.cli import execute
        from au_ree_v2.acquisition import select_snapshots
        from au_ree_v2.store import filehash
        today=datetime.now(timezone.utc).date().isoformat()
        with tempfile.TemporaryDirectory(dir=ROOT/'work') as tmp:
            root=Path(tmp);(root/'config').mkdir();(root/'data/snapshots').mkdir(parents=True)
            for name,data in [('sources.json',dict(sources=[])),('discovery.json',dict(seeds=[])),('research.json',dict(research_evidence_cutoff='2020-01-01',acquisition_through='2020-01-02',evidence_resolution=dict(document_pipeline=True)))]:
                (root/'config'/name).write_text(json.dumps(data))
            original=root/'data/snapshots/live.pdf';original.write_bytes(b'%PDF-live-public-original')
            source=dict(key='new_report',kind='pdf',url='https://official.test/report',path='data/snapshots/live.pdf',sha256=filehash(original),publication_date=today,available_date=today,acquired_at=today)
            (root/'data/manifest.json').write_text(json.dumps(dict(snapshots=[source])))
            args=argparse.Namespace(root=str(root),snapshot_lock=None,as_of=today,module='acquire',refresh=False,dry_run=False,official_only=True,source_key=None,tessdata=None)
            discovery=dict(sources=[dict(seed_key='official',status='PARSED')],documents=[dict(document_sha256=source['sha256'],status='REUSED_VERIFIED_ORIGINAL')])
            seen=[]
            def capture(root,snapshots,**kw):seen.extend(snapshots);return [dict(status='CAPTURED')]
            with patch('au_ree_v2.discovery.discover',return_value=discovery),patch('au_ree_v2.pdf_extract.capture_documents',side_effect=capture):result=execute(args)
            self.assertEqual([source],seen);self.assertEqual('2020-01-01',result['research_cutoff']);self.assertEqual(today,result['recognition_cutoff'])
            self.assertEqual([],select_snapshots(root,'2020-01-01',acquired_through='2020-01-02'))
            self.assertFalse((root/'work/canonical.sqlite').exists())

    def test_signed_cloud_parameter_detection(self):
        for q in ['X-Amz-Signature=SECRET','X-Amz-Credential=SECRET','X-Goog-Signature=SECRET','sig=SECRET']:
            self.assertTrue(sensitive_reference('https://public.test/f?'+q))

    def test_frozen_phase13_benchmark_and_separate_untuned_documents(self):
        self.assertEqual(json.loads((ROOT/'data/phase13_document_benchmark.json').read_text()),evaluate_phase13(ROOT))
        r=evaluate_phase14(ROOT);self.assertEqual(json.loads((ROOT/'data/phase14_document_benchmark.json').read_text()),r)
        self.assertEqual(13,r['fixed_development_set']['numeric_metrics']['true_positive'])
        self.assertEqual(6,r['reused_salazar_development']['numeric_metrics']['true_positive'])
        self.assertEqual(0,r['document_disjoint_after']['numeric_metrics']['false_positive'])

if __name__=='__main__':unittest.main()
