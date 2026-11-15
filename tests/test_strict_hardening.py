import unittest, tempfile, pathlib, json, hashlib
from unittest.mock import patch
import test_strict_acquisition as fixtures
from au_ree_v2 import acquisition as a
class HardeningTests(unittest.TestCase):
    fixture=fixtures.StrictAcquisitionTests.fixture
    def test_alias_changed_propagates_and_no_original_selected(self):
        with tempfile.TemporaryDirectory() as folder:
            root=pathlib.Path(folder);registry,raw=self.fixture(root)
            registry['sources'].append(dict(key='alias',kind='pdf',url=registry['sources'][0]['url']))
            with patch.object(a.StrictTransport,'__call__',return_value=(b'%PDF changed',{})):
                selected,rows=a.strict_refresh(root,registry,root/'work',{},'2026-11-13')
            self.assertFalse(selected);self.assertEqual([r['status'] for r in rows],['SOURCE_SHA_CHANGED']*2)
    def test_unbound_commercial_cache_only(self):
        with tempfile.TemporaryDirectory() as folder:
            root=pathlib.Path(folder);registry,raw=self.fixture(root);del registry['sources'][0]['source_sha256']
            with patch.object(a.StrictTransport,'__call__',return_value=(raw,{})):
                selected,rows=a.strict_refresh(root,registry,root/'work',{},'2026-11-13')
            self.assertFalse(selected);self.assertEqual(rows[0]['status'],'CACHED_UNBOUND_SOURCE_NOT_ADOPTED')
            self.assertTrue(list((root/'work').glob('strict-*/*.pdf')))
    def derived(self,root,kind,parent=None):
        registry,raw=self.fixture(root);m=json.loads((root/'data/manifest.json').read_text());old=m['snapshots'][0]
        derivative=dict(old,key='derived',kind=kind);derivative.pop('source_sha256',None)
        if parent:derivative['source_sha256']=parent
        m['snapshots'].append(derivative);(root/'data/manifest.json').write_text(json.dumps(m))
        registry['sources'].append(dict(key='derived',kind=kind,url=old['url']))
        return registry,raw,old['sha256']
    def test_official_transcription_without_explicit_parent_rejected(self):
        for kind in ('official_table_transcription','official_project_catalogue_transcription'):
            with tempfile.TemporaryDirectory() as folder:
                root=pathlib.Path(folder);registry,raw,sha=self.derived(root,kind)
                with patch.object(a.StrictTransport,'__call__',return_value=(raw,{})):
                    selected,rows=a.strict_refresh(root,registry,root/'work',{},'2026-11-13')
                self.assertEqual([s['key'] for s in selected],['pdf']);self.assertEqual(rows[1]['status'],'SOURCE_NOT_ACQUIRED')
    def test_changed_propagates_to_official_derivative(self):
        with tempfile.TemporaryDirectory() as folder:
            root=pathlib.Path(folder);registry,raw,sha=self.derived(root,'official_table_transcription')
            with patch.object(a.StrictTransport,'__call__',return_value=(b'%PDF changed',{})):
                selected,rows=a.strict_refresh(root,registry,root/'work',{},'2026-11-13')
            self.assertFalse(selected);self.assertEqual(rows[1]['status'],'SOURCE_SHA_CHANGED')

    def test_conflicting_sha_cannot_fallback(self):
        with tempfile.TemporaryDirectory() as folder:
            root=pathlib.Path(folder);registry,raw=self.fixture(root)
            claims={'source_key':'pdf','source_sha256':'0'*64}
            with patch.object(a.StrictTransport,'__call__') as fetch:
                selected,rows=a.strict_refresh(root,registry,root/'work',claims,'2026-11-13')
            fetch.assert_not_called();self.assertFalse(selected)
            self.assertEqual(rows[0]['status'],'CONFLICTING_DECLARED_SOURCE_SHA')
    def test_wamex_mismatch_then_failure_cannot_fallback(self):
        from urllib.error import HTTPError
        with tempfile.TemporaryDirectory() as folder:
            root=pathlib.Path(folder);registry,raw=self.fixture(root)
            registry['sources'][0]['url']='https://wamex.dmp.wa.gov.au/Wamex/ReportDetails?ANumber=109432'
            listing={'Total':2,'Data':[{'ANumber':109432,'FileType':'.pdf','FileSize':'1 KB','Link':'https://warsydprdstagsdspub.blob.core.windows.net/'+str(i)+'.pdf'} for i in range(2)]}
            error=HTTPError(listing['Data'][1]['Link'],403,'forbidden',{},None)
            with patch.object(a.StrictTransport,'__call__',side_effect=[(json.dumps(listing).encode(),{}),(b'%PDF changed',{}),error]) as fetch:
                selected,rows=a.strict_refresh(root,registry,root/'work',{},'2026-11-13')
            self.assertEqual(fetch.call_count,3);self.assertFalse(selected)
            self.assertEqual(rows[0]['status'],'SOURCE_SHA_CHANGED')


    def test_landing_disabled_without_fetch_or_fallback(self):
        with tempfile.TemporaryDirectory() as folder:
            root=pathlib.Path(folder);registry,raw=self.fixture(root)
            registry['sources'][0].update(kind='html',url='https://www.gippslandcriticalminerals.com/project-overview/')
            with patch.object(a.StrictTransport,'__call__') as fetch:
                selected,rows=a.strict_refresh(root,registry,root/'work',{},'2026-11-13')
            fetch.assert_not_called();self.assertFalse(selected)
            self.assertEqual(rows[0]['status'],'SOURCE_NOT_ACQUIRED')
            self.assertEqual(rows[0]['stop_reason'],'INDEX_LANDING_DISABLED')

if __name__=='__main__':unittest.main()
