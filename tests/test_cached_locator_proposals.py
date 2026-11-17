import hashlib
import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('cached_locators',ROOT/'tools/locators_from_ci_cache.py')
locators=importlib.util.module_from_spec(spec)
spec.loader.exec_module(locators)

class CachedLocatorProposals(unittest.TestCase):
    def test_markers_exist_and_are_independent_of_existing_marker(self):
        text='Issuer Corporation Limited\nProject Alpha Mineral Resource\nExisting marker\n'
        result=locators.choose_markers(text,['Existing marker'],['Issuer Corporation Limited'])
        self.assertEqual(2,len(result))
        self.assertTrue(all(marker in locators.norm(text) for marker in result))
        self.assertNotIn(result[0],result[1])
        self.assertNotIn(result[1],result[0])
        self.assertTrue(all(marker not in 'Existing marker' for marker in result))

    def test_only_verified_receipt_and_exact_cached_bytes_are_accepted(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'work') as folder:
            root=Path(folder)
            raw=b'%PDF immutable source'
            (root/'source.pdf').write_bytes(raw)
            sha=hashlib.sha256(raw).hexdigest()
            source=dict(path='source.pdf',sha256=sha)
            receipt=dict(status='FETCHED_SHA_VERIFIED',sha_match='True')
            with patch.object(locators,'ROOT',root):
                self.assertEqual(root/'source.pdf',locators.verified_path(source,receipt,sha))
                self.assertIsNone(locators.verified_path(source,dict(receipt,status='UNAVAILABLE'),sha))
                self.assertIsNone(locators.verified_path(source,dict(receipt,sha_match='False'),sha))
                (root/'source.pdf').write_bytes(b'changed')
                self.assertIsNone(locators.verified_path(source,receipt,sha))
