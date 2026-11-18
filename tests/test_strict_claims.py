import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from au_ree_v2.cli import strict_claims
from au_ree_v2.store import connect, filehash

class StrictClaimTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.db=connect(self.root/'db.sqlite');self.addCleanup(self.db.close)
        self.source=dict(key='doc',kind='pdf',sha256='a'*64,path='a.pdf',url='https://www.asx.com.au/a.pdf',acquired_at='2026-11-13',available_date='2026-11-13')
        self.claim=dict(variable='ore_mt',value=2,unit='Mt',basis='TREO',source_key='doc',source_sha256='a'*64,pdf_page=1,page_markers=['one','two'],locator='ocr_clip=[0, 0, 20, 20]',scope='scope',statement_id='s',effective_date='2026-01-01',extraction_method='EXPERIMENT_REVIEW_MIGRATED_REVERIFIED_AT_BUILD')
        self.project=dict(id='project',name='Project',state='WA',identity_source='doc',observations=[self.claim])
    def run_claims(self,snapshots,outcomes=(),project=None):
        return strict_claims(self.db,self.root,snapshots,dict(projects=[project or self.project]),outcomes,self.root/'pages')
    def reasons(self):return [r[0] for r in self.db.execute('SELECT reason FROM review_queue')]
    def test_missing_identity_queues_every_claim(self):
        result=self.run_claims([])
        self.assertFalse(result['projects']);self.assertIn('SOURCE_NOT_ACQUIRED',self.reasons())
        self.assertGreaterEqual(self.db.execute('SELECT COUNT(*) FROM review_queue').fetchone()[0],2)
    def test_changed_source_queues_without_read_or_fallback(self):
        with patch('au_ree_v2.pdf_extract.extract_page') as extract:
            result=self.run_claims([], [dict(key='doc',status='SOURCE_SHA_CHANGED')])
        extract.assert_not_called();self.assertFalse(result['projects']);self.assertIn('SOURCE_SHA_CHANGED',self.reasons())
    def test_success_keeps_numeric_value_and_adds_runtime_page_binding(self):
        data=dict(source_sha256='a'*64,physical_page=1,text='one two',status='EXTRACTED_REQUIRES_SCOPE_VALIDATION')
        snapshots=[self.source]
        with patch('au_ree_v2.pdf_extract.extract_page',return_value=data) as extract:
            result=self.run_claims(snapshots)
        obs=result['projects'][0]['observations'][0]
        self.assertEqual(obs['value'],2);self.assertIn('page_extraction_key',obs)
        self.assertEqual(extract.call_args.kwargs['ocr_clip'],[0,0,20,20])
        self.assertEqual(len(snapshots),2);self.assertFalse((self.root/'data/snapshots').exists())
        artifact=snapshots[-1]
        self.assertEqual(filehash(Path(artifact['path'])),artifact['sha256'])
        self.assertNotIn(b'\r\n',Path(artifact['path']).read_bytes())
        self.assertNotIn('page_extraction_key',self.claim)
    def test_failed_markers_do_not_enter_observations(self):
        with patch('au_ree_v2.pdf_extract.extract_page',return_value=dict(status='UNREADABLE')):
            result=self.run_claims([self.source])
        self.assertFalse(result['projects'][0]['observations']);self.assertIn('EXTRACTION_PAGE_CHECK_FAILED',self.reasons())
    def test_unverified_deposit_identity_is_not_published(self):
        p=copy.deepcopy(self.project);p.update(deposit_type='clay',identity_locator='Migrated identity; review test',identity_declaration=dict(source_sha256='a'*64,pdf_page=1,page_markers=['one','two']))
        with patch('au_ree_v2.pdf_extract.extract_page',return_value=dict(status='UNREADABLE')):
            result=self.run_claims([self.source],project=p)
        self.assertFalse(result['projects']);self.assertIn('EXTRACTION_PAGE_CHECK_FAILED',self.reasons())

if __name__=='__main__':unittest.main()
