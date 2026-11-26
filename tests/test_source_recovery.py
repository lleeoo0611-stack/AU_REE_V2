import csv
from hashlib import sha256
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile

from au_ree_v2.acquisition import declared_json_hash, wamex_report_documents
from au_ree_v2.source_recovery import LOCK, recover_census_assets
from au_ree_v2.store import filehash


URL = 'https://announcements.asx.com.au/original.pdf'
PDF = b'%PDF-1.7\nlocked fixture'
NEW_PDF = b'%PDF-1.7\na different observed edition'


def checksum(raw):
    return sha256(raw).hexdigest()


def source(key, raw, **fields):
    sha = checksum(raw)
    return {'key': key, 'kind': 'pdf', 'url': URL, 'sha256': sha, 'path': 'assets/' + sha,
            'publication_date': '2026-10-01', 'acquired_at': '2026-10-01T00:00:00+00:00', **fields}


class FakeTransport:
    documents = {}
    requested = []

    def __init__(self, hosts):
        self.hosts = hosts
        self.last = {}
        self.stopped = {}
        self.http = {}
        self.attempts = []

    def __call__(self, url, **kwargs):
        self.before_request(url)
        if url.endswith('/robots.txt'):
            return b'User-agent: *\nAllow: /', {}
        self.requested.append(url)
        self.resolved_url = url
        return self.documents[url], {'Content-Type': 'application/octet-stream'}


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.release = self.root / 'results/release'
        self.release.mkdir(parents=True)
        self.out = self.root / 'out'
        self.library = self.root / 'library'
        self.library.mkdir()
        (self.root / LOCK).parent.mkdir(parents=True)
        (self.root / LOCK).write_text('[]\n')
        FakeTransport.documents = {}
        FakeTransport.requested = []

    def seal(self, rows):
        receipt = self.release / 'source_acquisition.json'
        manifest = self.release / 'asset_manifest.json'
        receipt.write_text(json.dumps({'cutoff': '2026-11-13', 'snapshots': rows}))
        manifest.write_text(json.dumps([
            {'collection': 'receipt', 'role': 'snapshot', 'key': row['key'], 'asset': row['path'],
             'kind': row['kind'], 'owning_snapshot_sha256': row['sha256'], 'sha256': row['sha256']}
            for row in rows
        ]))
        seal = {'manifest_version': 2, 'references': len(rows), 'assets': len({r['sha256'] for r in rows}),
                'manifest_sha256': filehash(manifest), 'receipt_sha256': filehash(receipt),
                'lock_sha256': filehash(self.root / LOCK)}
        (self.release / 'bundle_verification.json').write_text(json.dumps(seal))

    def recover(self, **kwargs):
        return recover_census_assets(self.root, self.release, self.out, libraries=(self.library,), **kwargs)

    def write_csv(self, name, rows):
        with (self.release / name).open('w', encoding='utf8', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)

    def test_exact_local_resume_and_immutable_source_dates(self):
        locked = source('original', PDF)
        self.seal([locked])
        path = self.library / 'publisher-name.pdf'
        path.write_bytes(PDF)
        result = self.recover()
        self.assertEqual(result['status'], 'COMPLETE')
        self.assertEqual((result['verified'], result['missing']), (1, 0))
        self.assertEqual(Path(result['assets'], locked['sha256']).read_bytes(), PDF)
        reference = result['receipts'][0]['references'][0]
        self.assertEqual(reference['publication_date'], '2026-10-01')
        self.assertEqual(reference['url'], URL)
        self.assertEqual(reference['historical_acquired_at'], '2026-10-01T00:00:00+00:00')
        with patch('au_ree_v2.source_recovery.StrictTransport', FakeTransport):
            resumed = self.recover(online=True)
        self.assertEqual(FakeTransport.requested, [])
        self.assertTrue(resumed['receipts'][0]['reused'])
        self.assertEqual(resumed['receipts'][0]['local_path'], str(path))

    def test_single_explicit_original_is_verified_as_a_file(self):
        locked = source('original', PDF)
        self.seal([locked])
        path = self.root / 'publisher.pdf'
        path.write_bytes(PDF)
        result = recover_census_assets(self.root, self.release, self.out, libraries=(path,))
        self.assertEqual(result['status'], 'COMPLETE')
        self.assertEqual(result['receipts'][0]['local_path'], str(path))

    def test_zip_archive_members_are_sha_checked(self):
        locked = source('original', PDF)
        self.seal([locked])
        path = self.root / 'sealed.zip'
        with ZipFile(path, 'w') as archive:
            archive.writestr(f'../{locked["sha256"]}', PDF)
            archive.writestr(locked['path'], PDF)
        result = recover_census_assets(self.root, self.release, self.out, libraries=(path,))
        self.assertEqual(result['verified'], 1)
        self.assertEqual(Path(result['assets'], locked['sha256']).read_bytes(), PDF)
        self.assertTrue(result['receipts'][0]['local_path'].endswith('::' + locked['path']))

    def test_network_mismatch_kept_as_new_version_and_does_not_fill_locked_asset(self):
        updated = source('original', PDF)
        self.seal([updated])
        FakeTransport.documents[URL] = NEW_PDF
        with patch('au_ree_v2.source_recovery.StrictTransport', FakeTransport):
            result = self.recover(online=True)
        self.assertEqual(result['status'], 'BLOCKED_MISSING_ASSETS')
        self.assertEqual(result['missing_sha256'], [checksum(PDF)])
        self.assertFalse(Path(result['assets'], updated['sha256']).exists())
        new = result['receipts'][0]['attempts'][0]
        self.assertFalse(new['historical_eligible'])
        self.assertIsNone(new['candidate_publication_date'])
        self.assertTrue(new['observed_at'])
        self.assertEqual((self.out / new['version_path']).read_bytes(), NEW_PDF)
        with patch('au_ree_v2.source_recovery.StrictTransport', FakeTransport):
            FakeTransport.documents[URL] = PDF
            resumed = self.recover(online=True)
        self.assertEqual(resumed['status'], 'COMPLETE')
        self.assertEqual(Path(resumed['assets'], updated['sha256']).read_bytes(), PDF)
        self.assertEqual((self.out / new['version_path']).read_bytes(), NEW_PDF)

    def test_two_versions_sharing_a_url_are_not_both_admitted(self):
        ordered = sorted((source('first', PDF), source('second', NEW_PDF)), key=lambda row: row['sha256'])
        expected = ordered[0]['sha256']
        FakeTransport.documents[URL] = PDF if expected == checksum(PDF) else NEW_PDF
        self.seal(ordered)
        with patch('au_ree_v2.source_recovery.StrictTransport', FakeTransport):
            result = self.recover(online=True)
        self.assertEqual(FakeTransport.requested, [URL])
        self.assertEqual(result['verified'], 1)
        self.assertEqual(result['missing_sha256'], [ordered[1]['sha256']])
        self.assertEqual([p.name for p in Path(result['assets']).iterdir()], [expected])

    def test_content_policy_does_not_promote_different_raw_response(self):
        raw = b'{"timeStamp":"old","features":[1]}'
        new = b'{"timeStamp":"new","features":[1]}'
        fields = {'hash_policy': 'JSON_DROP_TOP_LEVEL_KEYS_V1', 'hash_drop_keys': ['timeStamp']}
        current = source('government', raw, kind='government_wfs', fixed_query=True,
                         url='https://services.ga.gov.au/query', **fields)
        current['content_sha256'] = declared_json_hash(raw, fields)[0]
        self.seal([current])
        FakeTransport.documents[current['url']] = new
        with patch('au_ree_v2.source_recovery.StrictTransport', FakeTransport):
            result = self.recover(online=True)
        attempt = result['receipts'][0]['attempts'][0]
        self.assertTrue(attempt['content_policy_match'])
        self.assertFalse(attempt['historical_eligible'])
        self.assertEqual(attempt['status'], 'DISTINCT_VERSION_RETAINED')
        self.assertEqual(result['verified'], 0)
        self.assertEqual(result['missing_sha256'], [checksum(raw)])

    def test_corruption_is_quarantined_then_recovered_from_local_bytes(self):
        locked = source('original', PDF)
        self.seal([locked])
        (self.library / locked['sha256']).write_bytes(PDF)
        result = self.recover()
        asset = Path(result['assets'], locked['sha256'])
        asset.write_bytes(NEW_PDF)
        again = self.recover()
        quarantine = again['receipts'][0]['attempts'][-1]
        self.assertEqual(quarantine['status'], 'CORRUPT_LOCAL_ASSET_QUARANTINED')
        self.assertEqual(asset.read_bytes(), PDF)
        self.assertEqual((self.out / quarantine['version_path']).read_bytes(), NEW_PDF)

    def test_impact_separates_direct_and_potential_panel_lineage(self):
        locked = source('original', PDF)
        self.seal([locked])
        self.write_csv('field_provenance.csv', [{'project_id': 'P', 'column': 'ore',
                                                 'source_sha256': locked['sha256']}])
        self.write_csv('mcda_criterion_lineage.csv', [
            {'project_id': 'P', 'panel': 'direct', 'criterion': 'R1',
             'evidence': json.dumps([{'evidence': {'source_sha256': locked['sha256']}}])}
        ])
        self.write_csv('mcda_panel_decisions.csv', [
            {'project_id': 'P', 'panel': label, 'canonical_project_id': 'P'} for label in ('direct', 'possible')
        ])
        result = self.recover()
        impact = json.loads(Path(result['impact_path']).read_bytes())['sources'][locked['sha256']]
        self.assertEqual(impact['census_fields'], [['P', 'ore']])
        self.assertEqual(impact['analysis_inputs'], [['P', 'direct', 'R1']])
        self.assertEqual(impact['direct_panels'], ['direct'])
        self.assertEqual(impact['potential_selection_panels'], ['possible'])

    def test_wamex_listing_reuses_registered_report_identity_and_document_bound(self):
        def emit(url, *args, **opts):
            if opts.get('method') == 'POST':
                self.assertEqual(args[0]['aNumber[0]'], 123)
                rows = [
                    {'ANumber': 123, 'Link': link, 'FileSize': '10 KB', 'FileType': '.pdf'}
                    for link in ['https://other.example/unapproved.pdf', *[
                        f'https://warsydprdstagsdspub.blob.core.windows.net/{index}.pdf'
                        for index in range(3)
                    ]]
                ]
                return json.dumps({'Errors': None, 'Total': len(rows), 'Data': rows}).encode(), {}
            return PDF, {}

        url = 'https://wamex.dmp.wa.gov.au/Wamex/Search/ReportDetails?ANumber=123'
        self.assertEqual([link.rsplit('/', 1)[-1] for _, _, link in wamex_report_documents(emit, url)],
                         ['0.pdf', '1.pdf'])
        with self.assertRaisesRegex(ValueError, 'INVALID_WAMEX_REPORT_REFERENCE'):
            list(wamex_report_documents(emit, url + '&ANumber=999'))

    def test_tampered_bundle_and_overlapping_outputs_are_rejected(self):
        self.seal([source('original', PDF)])
        with self.assertRaisesRegex(ValueError, 'separate'):
            recover_census_assets(self.root, self.release, self.library / 'child', libraries=(self.library,))
        self.assertFalse((self.library / 'child').exists())
        (self.release / 'asset_manifest.json').write_text('[]')
        with self.assertRaisesRegex(ValueError, 'checksum'):
            self.recover()
        self.assertFalse(self.out.exists())


if __name__ == '__main__':
    unittest.main()
