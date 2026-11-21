import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from au_ree_v2.acquisition import census_admission, replay_pdf_extensions, static_pdf_sources
from au_ree_v2.store import digest, filehash


class ASICRegisterAcquisitionTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.metadata = self.root / 'data' / 'snapshots'
        self.metadata.mkdir(parents=True)
        self.archive = self.root / 'company.zip'
        member = 'COMPANY_202611.csv'
        with zipfile.ZipFile(self.archive, 'w') as z:
            z.writestr(member, 'one test row')
        sha = filehash(self.archive)
        url = ('https://data.gov.au/data/dataset/7b8656f9-606d-4337-af29-66b89b2eeefb/'
               'resource/d6d03876-71a4-4e82-8c77-2e4df5da4236/download/company_202611.zip')
        self.source = dict(key='asic', kind='asic_company_register_zip', source_sha256=sha,
            reviewed_static_archive_sha256=sha, publication_date='2026-11-02', url=url, archive_member=member,
            archive_manifest_url='https://publicdata.au/d/asic-companies/v/2026-11-02/manifest.json',
            replay_extension_of=digest({'sources': []}))
        self.manifest = dict(dataset='asic-companies', version='2026-11-02', backfilled=False, tombstone=None,
            fetched_at='2026-11-02T19:28:14+00:00', encoding='zip', sha256=sha,
            bytes=self.archive.stat().st_size, filename='company_202611.zip',
            source=dict(url=url, resource_last_modified='2026-11-02T13:51:17.043135',
                        http_last_modified='Mon, 02 Nov 2026 13:51:17 GMT'))
        self.write_manifest()

    def write_manifest(self):
        path = self.metadata / 'manifest.tmp'
        path.write_text(json.dumps(self.manifest), encoding='utf-8')
        self.source['archive_manifest_sha256'] = filehash(path)
        path.replace(self.metadata / (filehash(path) + '.json'))

    def select(self):
        return static_pdf_sources({'sources':[self.source]}, {'projects':[]}, [self.root],
                                  '2026-11-13', set(), root=self.root)

    def test_single_ingress_preserves_original_acquisition_and_proves_availability(self):
        registry = {'sources':[self.source]}
        self.assertEqual(['asic'], replay_pdf_extensions(registry, self.source['replay_extension_of'], [self.root]))
        [entry] = self.select()
        self.assertEqual('2026-11-02', entry['available_date'])
        self.assertEqual('STATIC_ASIC_REGISTER_SHA_VERIFIED', entry['acquisition_method'])
        status = census_admission(self.root, entry, self.source, {}, '2026-11-13')
        self.assertEqual(('ARCHIVED_PUBLISHER_VERSION','WITHIN_CUTOFF','PINNED_SHA_VERIFIED'),
                         (status['date_basis'], status['cutoff_status'], status['version_status']))
        entry['available_date'] = '2026-01-01'
        self.assertEqual('SOURCE_PUBLICATION_DATE_MISMATCH',
                         census_admission(self.root, entry, self.source, {}, '2026-11-13')['cutoff_status'])

    def test_rejects_unverified_dates_and_altered_archive(self):
        self.manifest['fetched_at'] = '2026-11-14T19:28:14+00:00'
        self.write_manifest()
        self.assertEqual([], self.select())
        self.manifest['version'] = '2026-11-30'
        self.write_manifest()
        with self.assertRaisesRegex(ValueError, 'publisher date mismatch'):
            self.select()
        with zipfile.ZipFile(self.archive, 'a') as bundle:
            bundle.writestr('later.txt', 'changed')
        self.assertEqual([], self.select())

    def test_rejects_unchecked_metadata_and_unexpected_archive_member(self):
        self.source['archive_member'] = 'later.csv'
        with self.assertRaisesRegex(ValueError, 'member mismatch'):
            self.select()
        (self.metadata / (self.source['archive_manifest_sha256'] + '.json')).write_bytes(b'{}')
        with self.assertRaisesRegex(ValueError, 'manifest checksum'):
            self.select()
