import hashlib,json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import pymupdf
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import capture_research_sources as capture_tool


class PublisherOriginalCapture(unittest.TestCase):
    def fixture(self,root,**options):
        d=pymupdf.open();p=d.new_page();p.insert_text((30,40),'Published government original');raw=d.tobytes();d.close()
        spec=dict(key='report',kind='pdf',url='https://publisher.test/report.pdf',**options)
        path=root/'requests.json';path.write_text(json.dumps(dict(documents=[spec])),encoding='utf8')
        return path,raw

    def test_explicit_large_public_original_limit_and_publisher_checksum(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);path,raw=self.fixture(root,max_bytes=64*1024*1024)
            cfg=json.loads(path.read_text());cfg['documents'][0].update(expected_bytes=len(raw),expected_md5=hashlib.md5(raw).hexdigest());path.write_text(json.dumps(cfg))
            with patch.object(capture_tool,'request',return_value=(raw,{})) as fetch:
                rows=capture_tool.capture(path,root/'out')
            self.assertEqual(64*1024*1024,fetch.call_args.kwargs['max_bytes'])
            self.assertTrue(rows[0]['publisher_checksum_verified']);self.assertEqual('PDF_ACQUIRED',rows[0]['status'])
            self.assertEqual(hashlib.sha256(raw).hexdigest(),rows[0]['document_sha256'])

    def test_publisher_length_or_checksum_mismatch_is_not_admitted(self):
        for options in [dict(expected_bytes=1),dict(expected_md5='0'*32)]:
            with self.subTest(options=options),tempfile.TemporaryDirectory() as t:
                root=Path(t);path,raw=self.fixture(root,**options)
                with patch.object(capture_tool,'request',return_value=(raw,{})):
                    row=capture_tool.capture(path,root/'out')[0]
                self.assertEqual('UNAVAILABLE',row['status']);self.assertNotIn('path',row)

    def test_invalid_limits_never_issue_a_request(self):
        for size in [0,-1,True,64*1024*1024+1]:
            with self.subTest(size=size),tempfile.TemporaryDirectory() as t:
                root=Path(t);path,raw=self.fixture(root,max_bytes=size)
                with patch.object(capture_tool,'request') as fetch,self.assertRaisesRegex(ValueError,'INVALID_SIZE_LIMIT'):
                    capture_tool.capture(path,root/'out')
                fetch.assert_not_called()
