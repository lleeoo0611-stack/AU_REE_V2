"""Historical acquisition hints are always narrower than the source registry."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from au_ree_v2.phase10_recovery import (
    RELEASE, SCHEMA, _approved_asx_hint, _archived_asx_hints, _failure, _verify_receipts, stage_recovered_batch,
)
from au_ree_v2.source_recovery import _manifest
from au_ree_v2.store import filehash


ROOT = Path(__file__).resolve().parents[1]
POLICY = {'same_sha_fallback': {'approved_hosts': ['announcements.asx.com.au']}}


class Phase10RecoveryTests(unittest.TestCase):
    def test_only_approved_public_official_pdf_addresses_can_be_leads(self):
        url = 'https://announcements.asx.com.au/asxpdf/20240502/pdf/0634x8c70tcj45.pdf'
        self.assertTrue(_approved_asx_hint(url, POLICY))
        for address in (url + '?encoded-token=ignored', url.replace('https:', 'http:'),
                        url.replace('://', '://viewer@'), url.replace('.au/', '.au.example/'),
                        'https://[invalid', url[:-4] + '.html'):
            with self.subTest(address=address):
                self.assertFalse(_approved_asx_hint(address, POLICY))
        self.assertFalse(_approved_asx_hint(url, {'same_sha_fallback': {'approved_hosts': []}}))

    def test_archived_leads_need_same_key_sha_and_enabled_locked_source(self):
        planned, _ = _manifest(ROOT, ROOT / RELEASE)
        published = '075a54f0b388184f869ea1a9f0aec59119405b46661cbe7173d78be7f05f3ce0'
        # This pending source was pinned in the historical lock but disabled for public retrieval.
        disabled = next(sha for sha, rows in planned.items()
                        if any(item['key'] == 'pending_source_7c39273cc15b4e56' for item, _, _ in rows))
        leads, source_proof = _archived_asx_hints(ROOT, planned, {published, disabled})
        self.assertEqual({sha for sha, _ in leads}, {published})
        self.assertEqual(len(source_proof), 2)
        source, item, role = planned[published][0]
        renamed = {published: [(dict(source, key='wrong-source-key'), item, role)]}
        self.assertEqual(_archived_asx_hints(ROOT, renamed, {published})[0], {})

    def test_different_edition_stays_unavailable_and_bytes_are_reopened(self):
        bindings = [{'download_enabled': True, 'original_url': 'original'}]
        self.assertEqual(_failure([{'url': 'approved', 'status': 'DISTINCT_VERSION_RETAINED'}], bindings, None),
                         ('DIFFERENT_EDITION_SHA', 'approved'))
        with TemporaryDirectory() as directory:
            root = Path(directory)
            assets = root / 'assets'
            assets.mkdir()
            source = assets / 'seed'
            source.write_bytes(b'exact historical bytes')
            sha = filehash(source)
            path = source.rename(assets / sha)
            receipt = {'receipts': [{'locked_sha256': sha, 'status': 'VERIFIED'}], 'expected': 1,
                       'verified': 1, 'missing': 0, 'missing_sha256': []}
            self.assertEqual(_verify_receipts(receipt, {sha: []}, root)[1], {sha})
            path.write_bytes(b'different bytes')
            with self.assertRaisesRegex(ValueError, 'REOPENED_HISTORICAL_ORIGINAL_SHA_MISMATCH'):
                _verify_receipts(receipt, {sha: []}, root)

    def test_artifact_batch_uses_only_explicit_previously_verified_urls(self):
        url = 'https://announcements.asx.com.au/asxpdf/20240502/pdf/0634x8c70tcj45.pdf'
        contract = {'cutoff': '2026-11-13'}
        with TemporaryDirectory() as directory:
            root = Path(directory)
            manifest, out = root / 'manifest.json', root / 'output'
            assets = out / 'assets'
            assets.mkdir(parents=True)
            source = assets / 'sample'
            source.write_bytes(b'%PDF synthetic original')
            sha = filehash(source)
            source.rename(assets / sha)
            audit = {'schema': SCHEMA, 'contract': contract, 'fresh_asx_asset_sha256': [sha],
                     'fresh_asx_exact_assets': 1, 'assets': [
                         {'expected_sha256': sha, 'observed_sha256': sha, 'status': 'AVAILABLE_EXACT_ORIGINAL',
                          'exact_download': {'url': url, 'status': 'EXACT_LOCKED_BYTES', 'actual_sha256': sha}},
                     ]}
            manifest.write_text(json.dumps(audit), encoding='utf8')
            planned = {sha: [], 'another-locked-edition': []}
            with patch('au_ree_v2.phase10_recovery._manifest', return_value=(planned, contract)), patch(
                    'au_ree_v2.phase10_recovery._fetch_archived_asx', return_value={'attempts': {}, 'request_slots_used': 0}) as fetch:
                result = stage_recovered_batch(root, manifest, out)
                self.assertEqual((result['status'], result['verified']), ('COMPLETE', 1))
                self.assertEqual(fetch.call_args.args[2], {sha})
                self.assertEqual(fetch.call_args.kwargs['exact_urls'], {sha: url})
                self.assertEqual(result['entries'][0]['observed_sha256'], sha)
                (assets / 'injected-other-original').write_bytes(b'not approved for this artifact')
                with self.assertRaisesRegex(ValueError, 'ARCHIVED_ASX_BATCH_DIRECTORY_HAS_UNEXPECTED_ASSETS'):
                    stage_recovered_batch(root, manifest, out)
                self.assertEqual(fetch.call_count, 1)


if __name__ == '__main__':
    unittest.main()
