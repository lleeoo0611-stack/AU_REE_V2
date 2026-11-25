import base64
import hashlib
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import Mock, patch
from urllib.parse import urlencode

from au_ree_v2.acquisition import (
    WA_TITLE_KIND, census_admission, refresh, replay_pdf_extensions,
    static_pdf_sources, strict_dns_preflight, strict_refresh,
)
from au_ree_v2.store import digest, filehash


class WATitleAcquisitionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.meta = self.root / 'data/snapshots'
        self.meta.mkdir(parents=True)
        (self.root / 'data/manifest.json').write_text('{"snapshots":[]}', encoding='utf8')
        self.library = self.root / 'library'
        self.library.mkdir()
        self.archive = self.library / 'government.zip'
        with zipfile.ZipFile(self.archive, 'w') as dataset:
            dataset.writestr('CurrentTenements.prj', 'test only')
        origin = ('https://warsydprdstadasc.blob.core.windows.net/downloads/dasc/Dynamic/Tenements/'
                  'CurrentTenements_GDA2020_shp.zip?ts=20260911085537')
        stamp = '20260911005540'
        sha = filehash(self.archive)
        archive_sha1 = base64.b32encode(hashlib.sha1(self.archive.read_bytes()).digest()).decode('ascii')
        self.records = [['original', 'timestamp', 'digest', 'mimetype', 'statuscode'],
                        [origin, stamp, archive_sha1, 'application/octet-stream', '200']]
        self.source = dict(key='wa', kind=WA_TITLE_KIND, archive_origin_url=origin,
                           archive_capture_timestamp=stamp, archive_sha1=archive_sha1,
                           url=f'https://web.archive.org/web/{stamp}id_/{origin}',
                           archive_index_url='https://web.archive.org/cdx/search/cdx?' + urlencode(dict(output='json', url=origin)),
                           source_sha256=sha, reviewed_static_archive_sha256=sha,
                           replay_extension_of=digest({'sources': []}))
        self.reg = {'sources':[self.source]}
        self.write_index()

    def write_index(self):
        binary = json.dumps(self.records).encode('utf8')
        sha = hashlib.sha256(binary).hexdigest()
        (self.meta / (sha + '.json')).write_bytes(binary)
        self.source['archive_index_sha256'] = sha

    def select(self, cutoff='2026-11-13'):
        return static_pdf_sources(self.reg, {}, [self.library], cutoff, set(), root=self.root)

    def test_static_replay_and_old_refresh_admission(self):
        self.assertEqual(['wa'], replay_pdf_extensions(self.reg, self.source['replay_extension_of'], [self.library]))
        self.assertFalse(self.select('2026-09-10'))
        [entry] = self.select()
        self.assertEqual(('2026-09-11', 'STATIC_WA_DASC_ZIP_SHA_VERIFIED'),
                         (entry['available_date'], entry['acquisition_method']))
        audit = census_admission(self.root, entry, self.source, {}, '2026-11-13')
        self.assertEqual(('ARCHIVED_HTTP_CAPTURE','WITHIN_CUTOFF','PINNED_SHA_VERIFIED',None),
                         (audit['date_basis'],audit['cutoff_status'],audit['version_status'],audit['publication_date']))
        entry['available_date'] = '2026-09-01'
        self.assertEqual('SOURCE_PUBLICATION_DATE_MISMATCH',
                         census_admission(self.root, entry, self.source, {}, '2026-11-13')['cutoff_status'])
        with self.assertRaisesRegex(ValueError, 'receipt kind'):
            census_admission(self.root, dict(entry,kind='pdf'), self.source, {}, '2026-11-13')
        with self.assertRaisesRegex(ValueError, 'receipt identity'):
            census_admission(self.root, dict(entry,url='changed'), self.source, {}, '2026-11-13')
        [outcome] = refresh(self.root, self.reg)
        self.assertEqual('MANAGED_BY_CENSUS_ACQUISITION', outcome['status'])

    def test_rejects_changed_cdx_payload_and_ambiguous_matches(self):
        path = self.meta / (self.source['archive_index_sha256'] + '.json')
        path.write_bytes(b'[]')
        with self.assertRaisesRegex(ValueError, 'index checksum'):
            self.select()
        self.records.append(self.records[1][:])
        self.write_index()
        with self.assertRaisesRegex(ValueError, 'index record'):
            self.select()
        self.records.pop()
        self.source['archive_sha1'] = self.records[1][2] = 'Z' * 32
        self.write_index()
        with self.assertRaisesRegex(ValueError, 'payload checksum'):
            self.select()
        self.records[1][-1] = '404'
        self.write_index()
        with self.assertRaisesRegex(ValueError, 'index record'):
            self.select()

    def test_network_only_refresh_requests_no_historical_archive(self):
        transport = Mock()
        transport.attempts = []
        transport.http = {}
        with patch('socket.getaddrinfo', side_effect=AssertionError('No DNS for a static archive')):
            self.assertEqual(strict_dns_preflight(self.reg), [])
        selected, outcomes = strict_refresh(self.root, self.reg, self.root / 'work', {}, '2026-11-13',
                                            transport, dns_rows=[])
        transport.assert_not_called()
        self.assertEqual([], selected)
        self.assertEqual('NEEDS_VERIFIED_STATIC_ARCHIVE', outcomes[0]['status'])
        report = json.loads((self.root / 'work/network_status.json').read_bytes())
        self.assertFalse(report['valid_for_delivery'])
        self.assertEqual(0, report['sources'])
        self.source['url'] = self.source['url'].replace('CurrentTenements_GDA2020', 'Unrelated')
        with self.assertRaisesRegex(ValueError, 'capture or version mismatch'):
            self.select()
