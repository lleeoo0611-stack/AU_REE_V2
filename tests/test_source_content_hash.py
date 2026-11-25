"""Explicit content identity never replaces immutable byte provenance."""
import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from au_ree_v2.acquisition import StrictTransport, declared_json_hash, strict_refresh
from au_ree_v2.spatial import summary_locations


class SourceContentHashTests(unittest.TestCase):
    policy = {'hash_policy': 'JSON_DROP_TOP_LEVEL_KEYS_V1', 'hash_drop_keys': ['timeStamp']}

    def document(self):
        return {'timeStamp': 'first', 'features': [
            {'properties': {'tno': 'EL1', 'value': 3}, 'geometry': {'coordinates': [140, -35]}},
            {'properties': {'tno': 'EL2'}, 'geometry': {'coordinates': [141, -36]}},
        ], 'nested': {'timeStamp': 'preserved'}}

    def encode(self, document):
        return json.dumps(document, ensure_ascii=False).encode('utf8')

    def digest(self, document):
        return declared_json_hash(self.encode(document), self.policy)[0]

    def test_top_level_timestamp_only_is_ignored(self):
        first = self.document()
        other = copy.deepcopy(first)
        other['timeStamp'] = 'second'
        self.assertNotEqual(hashlib.sha256(self.encode(first)).digest(), hashlib.sha256(self.encode(other)).digest())
        self.assertEqual(self.digest(first), self.digest(other))

    def test_attributes_geometry_order_and_nested_timestamp_remain_significant(self):
        document = self.document()
        changes = []
        changed = copy.deepcopy(document)
        changed['features'][0]['properties']['value'] = 4
        changes.append(changed)
        changed = copy.deepcopy(document)
        changed['features'][0]['geometry']['coordinates'][0] = 142
        changes.append(changed)
        changed = copy.deepcopy(document)
        changed['features'].reverse()
        changes.append(changed)
        changed = copy.deepcopy(document)
        changed['nested']['timeStamp'] = 'different'
        changes.append(changed)
        for changed in changes:
            with self.subTest(changed=changed):
                self.assertNotEqual(self.digest(document), self.digest(changed))

    def test_canonical_utf8_key_order_and_spacing(self):
        raw = '{ "timeStamp": "a", "z": "稀土", "a": 1 }'.encode('utf8')
        expected = hashlib.sha256('{"a":1,"z":"稀土"}'.encode('utf8')).hexdigest()
        actual, receipt = declared_json_hash(raw, self.policy)
        self.assertEqual(actual, expected)
        self.assertEqual(receipt['raw_sha256'], hashlib.sha256(raw).hexdigest())
        self.assertEqual(receipt['hash_drop_keys'], ['timeStamp'])

    def test_invalid_json_and_missing_top_level_key_fail_closed(self):
        for raw, reason in [(b'<html>unavailable</html>', 'HASH_POLICY_INVALID_JSON'),
                            (b'{"nested":{"timeStamp":"x"}}', 'HASH_POLICY_TOP_LEVEL_KEY_MISSING'),
                            (b'[]', 'HASH_POLICY_TOP_LEVEL_OBJECT_REQUIRED')]:
            with self.subTest(raw=raw), self.assertRaisesRegex(ValueError, reason):
                declared_json_hash(raw, self.policy)

    def test_invalid_policy_and_drop_key_declarations_are_rejected(self):
        for declaration in [dict(self.policy, hash_policy='UNKNOWN'),
                            dict(self.policy, hash_drop_keys=[]),
                            dict(self.policy, hash_drop_keys=['timeStamp', 'timeStamp']),
                            dict(self.policy, hash_drop_keys=[3])]:
            with self.subTest(declaration=declaration), self.assertRaises(ValueError):
                declared_json_hash(self.encode(self.document()), declaration)

    def acquire(self, root, raw, source):
        (root/'data').mkdir(exist_ok=True)
        (root/'data/manifest.json').write_text('{"snapshots":[]}', encoding='utf8')
        transport = StrictTransport({'example.invalid': 'government-api'})
        def fetch(*args, **kwargs):
            transport.http['example.invalid'] = 200
            return raw, {}
        with patch.object(StrictTransport, '__call__', side_effect=fetch):
            return strict_refresh(root, {'sources': [source]}, root/'work', {}, '2026-11-17',
                                  transport=transport, dns_rows=[{'host': 'example.invalid', 'status': 'DNS_OK'}])

    def source(self, sha, policy=True):
        result = dict(key='vic', kind='government_wfs', url='https://example.invalid/fixed',
                      fixed_query=True, source_sha256=sha)
        if policy:
            result.update(self.policy)
        return result

    def test_refresh_preserves_raw_snapshot_and_records_both_hashes(self):
        raw = self.encode(self.document())
        expected = self.digest(self.document())
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            selected, outcomes = self.acquire(root, raw, self.source(expected))
            self.assertEqual(len(selected), 1)
            snapshot = selected[0]
            raw_sha = hashlib.sha256(raw).hexdigest()
            self.assertEqual(snapshot['sha256'], raw_sha)
            self.assertEqual(snapshot['raw_sha256'], raw_sha)
            self.assertEqual(snapshot['content_sha256'], expected)
            self.assertEqual(Path(snapshot['path']).name, raw_sha+'.json')
            self.assertEqual(Path(snapshot['path']).read_bytes(), raw)
            self.assertEqual(outcomes[0]['status'], 'FETCHED_SHA_VERIFIED')
            self.assertTrue(outcomes[0]['sha_match'])
            self.assertEqual(outcomes[0]['content_sha256'], expected)
            self.assertEqual(json.loads(outcomes[0]['hash_drop_keys']), ['timeStamp'])
            self.assertIn(expected, (root/'work/acquisition_report.csv').read_text())

    def test_refresh_policy_failure_keeps_raw_but_cannot_use_byte_sha(self):
        for raw in (b'not json', b'{"nested":{"timeStamp":"x"}}'):
            with self.subTest(raw=raw), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                raw_sha = hashlib.sha256(raw).hexdigest()
                selected, outcomes = self.acquire(root, raw, self.source(raw_sha))
                self.assertEqual(selected, [])
                self.assertFalse(outcomes[0]['sha_match'])
                self.assertTrue(outcomes[0]['stop_reason'].startswith('HASH_POLICY_'))
                self.assertEqual(next((root/'work').rglob(raw_sha+'.json')).read_bytes(), raw)

    def test_refresh_content_change_is_rejected(self):
        raw = self.encode(self.document())
        with tempfile.TemporaryDirectory() as folder:
            selected, outcomes = self.acquire(Path(folder), raw, self.source('0'*64))
            self.assertEqual(selected, [])
            self.assertEqual(outcomes[0]['status'], 'SOURCE_SHA_CHANGED')

    def test_declared_policy_cannot_skip_validation_via_committed_snapshot_or_alternate(self):
        raw = b'not json'
        source = self.source(hashlib.sha256(raw).hexdigest())
        source['committed_snapshot_sha256'] = source['source_sha256']
        with tempfile.TemporaryDirectory() as folder, \
             patch('au_ree_v2.acquisition.SameSHAAlternates.find') as alternate:
            selected, outcomes = self.acquire(Path(folder), raw, source)
            self.assertEqual(selected, [])
            self.assertEqual(outcomes[0]['stop_reason'], 'HASH_POLICY_INVALID_JSON')
            alternate.assert_not_called()

    def test_unconfigured_source_retains_original_byte_hash_behavior(self):
        raw = self.encode(self.document())
        with tempfile.TemporaryDirectory() as folder:
            selected, outcomes = self.acquire(Path(folder), raw, self.source(hashlib.sha256(raw).hexdigest(), False))
            self.assertEqual(len(selected), 1)
            self.assertNotIn('content_sha256', selected[0])
            self.assertNotIn('raw_sha256', outcomes[0])
            self.assertEqual(outcomes[0]['status'], 'FETCHED_SHA_VERIFIED')
        with tempfile.TemporaryDirectory() as folder:
            selected, outcomes = self.acquire(Path(folder), raw, self.source(self.digest(self.document()), False))
            self.assertEqual(selected, [])
            self.assertEqual(outcomes[0]['status'], 'SOURCE_SHA_CHANGED')

    def test_spatial_content_alias_retains_raw_provenance(self):
        content_sha, raw_sha = 'c'*64, 'b'*64
        binding = dict(project_id='project', complete_project_scope=True, original_references=[],
                       tenement_ids=['EL1'], source_crs='EPSG:7844')
        registered = dict(self.source(content_sha), summary_tenements=[binding])
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'snapshot.json'
            path.write_text(json.dumps({'numberMatched': 1, 'features': [
                {'properties': {'tno': 'EL1'}, 'geometry': {'type': 'Point', 'coordinates': [140, -35]}}]}))
            snapshot = dict(registered, sha256=raw_sha, raw_sha256=raw_sha,
                            content_sha256=content_sha, resolved_path=str(path))
            row = {'專案ID': 'project', '經度': '', '緯度': '', '專案名稱': 'Example', '州省地區': 'VIC'}
            rules = {'tenement_precision_m': 25000, 'government_datasets': {}, 'aliases.projects': [], 'states': {'VIC': 'VIC'}}
            result = dict(accepted=True, longitude=140.0, latitude=-35.0)
            with patch('au_ree_v2.census_policy.summary_decision', return_value=True), \
                 patch('au_ree_v2.spatial.summary_tenement_centroid', return_value=result):
                fills = summary_locations(row, [], [registered], {raw_sha: snapshot}, rules, [])
            self.assertEqual(len(fills), 2)
            self.assertTrue(all(fill['sha']==raw_sha for fill in fills))


if __name__ == '__main__':
    unittest.main()
