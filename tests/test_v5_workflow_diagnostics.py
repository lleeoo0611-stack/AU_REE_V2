"""Offline HTTP verification and execution of the actual CI receipt step."""
import csv
import hashlib
import json
import textwrap
import unittest
from pathlib import Path
from urllib.error import HTTPError

import test_same_sha_fallback as local_fixtures

ROOT = Path(__file__).resolve().parents[1]
GA = 'services.ga.gov.au'
VIC = 'reviewed_source_31a205168b6ae647'
MARKER = 'ROBOTS_HTTP_403_TREATED_AS_UNAVAILABLE'


def workflow_functions():
    text = (ROOT/'.github/workflows/automated-build.yml').read_text(encoding='utf8')
    step = text.split('      - name: Capture VIC response and annotate robots receipts\n', 1)[1]
    code = textwrap.dedent(step.split("python - <<'PY'\n", 1)[1].split('\n          PY', 1)[0])
    namespace = {'__name__': 'offline_workflow_test'}
    exec(compile(code, 'automated-build-v5-receipts', 'exec'), namespace)
    return namespace


class V5WorkflowDiagnostics(unittest.TestCase):
    def setUp(self):
        self.fixture = local_fixtures.LocalFallback(methodName='runTest')
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.primary, self.helper = self.fixture.make()
        self.primary.hosts[GA] = 'government-api'
        self.functions = workflow_functions()

    def receipt(self):
        return dict(key='ga', host=GA, stop_reason='', http_attempts=json.dumps(self.primary.attempts))

    def test_robots_403_allows_data_and_marks_existing_receipt_field(self):
        self.fixture.routes[GA, '/robots.txt'] = (403, b'CDN missing object', {})
        self.fixture.routes[GA, '/query'] = (200, b'{"features":[]}', {})
        raw, _ = self.primary('https://'+GA+'/query')
        self.assertEqual(raw, b'{"features":[]}')
        self.assertNotIn(GA, self.primary.stopped)
        rows = [self.receipt()]
        old_fields = set(rows[0])
        self.assertTrue(self.functions['annotate_robots'](rows))
        self.assertEqual(rows[0]['stop_reason'], MARKER)
        self.assertEqual(set(rows[0]), old_fields)
        self.assertEqual([403, 200], [e['http_status'] for e in self.primary.attempts])
        self.assertEqual(['/robots.txt', '/query'], [call[1] for call in self.fixture.calls])

    def test_robots_403_then_data_403_stops_for_the_data_endpoint(self):
        self.fixture.routes[GA, '/robots.txt'] = (403, b'CDN missing object', {})
        self.fixture.routes[GA, '/query'] = (403, b'data denied', {})
        with self.assertRaises(HTTPError) as error:
            self.primary('https://'+GA+'/query')
        self.assertTrue(error.exception.url.endswith('/query'))
        self.assertEqual(self.primary.stopped[GA], '403')
        with self.assertRaisesRegex(ValueError, 'HOST_STOPPED:403'):
            self.primary('https://'+GA+'/next')
        self.assertEqual(['/robots.txt', '/query'], [call[1] for call in self.fixture.calls])
        row = self.receipt()
        row['stop_reason'] = 'HOST_STOPPED:403'
        self.functions['annotate_robots']([row])
        self.assertEqual(row['stop_reason'], 'HOST_STOPPED:403; '+MARKER)

    def test_robots_401_and_429_still_stop_without_data_requests(self):
        for code in (401, 429):
            with self.subTest(code=code):
                self.primary.stopped.clear()
                self.primary.attempts.clear()
                self.helper.robots.clear()
                self.fixture.calls.clear()
                self.fixture.routes[GA, '/robots.txt'] = (code, b'denied', {})
                with self.assertRaises(HTTPError):
                    self.primary('https://'+GA+'/query')
                self.assertEqual(self.primary.stopped[GA], str(code))
                row = self.receipt()
                self.assertFalse(self.functions['annotate_robots']([row]))
                self.assertEqual(['/robots.txt'], [call[1] for call in self.fixture.calls])

    def test_robots_200_disallow_still_blocks_the_data_endpoint(self):
        self.fixture.routes[GA, '/robots.txt'] = (200, b'User-agent: *\nDisallow: /query\n', {})
        with self.assertRaisesRegex(ValueError, 'ROBOTS_DISALLOWED'):
            self.primary('https://'+GA+'/query')
        self.assertFalse(self.functions['annotate_robots']([self.receipt()]))
        self.assertEqual(['/robots.txt'], [call[1] for call in self.fixture.calls])

    def test_data_403_after_robots_200_is_not_labelled_missing_robots(self):
        self.fixture.routes[GA, '/query'] = (403, b'data denied', {})
        with self.assertRaises(HTTPError):
            self.primary('https://'+GA+'/query')
        self.assertEqual(self.primary.stopped[GA], '403')
        self.assertFalse(self.functions['annotate_robots']([self.receipt()]))

    def write_capture_fixture(self, raw, corrupt=False):
        root = self.fixture.root
        sha = hashlib.sha256(raw).hexdigest()
        cache = root/'work/clean/strict-test'
        cache.mkdir(parents=True)
        (cache/(sha+'.json')).write_bytes(b'changed' if corrupt else raw)
        output = root/'work/clean/runs/test'
        output.mkdir(parents=True)
        row = dict(key=VIC, host='opendata.maps.vic.gov.au', http_attempts='[]', stop_reason='SOURCE_SHA_CHANGED',
                   raw_sha256=sha, content_sha256='a'*64, expected_sha256='b'*64,
                   hash_policy='JSON_DROP_TOP_LEVEL_KEYS_V1', hash_drop_keys='["timeStamp"]', status='SOURCE_SHA_CHANGED')
        with (output/'acquisition_report.csv').open('w', encoding='utf8', newline='') as stream:
            writer = csv.DictWriter(stream, row)
            writer.writeheader()
            writer.writerow(row)
        return root, sha

    def test_capture_keeps_exact_raw_bytes_with_raw_sha_filename(self):
        raw = b'{"timeStamp":"keep this","features":[]}'
        root, sha = self.write_capture_fixture(raw)
        self.functions['capture'](root)
        self.assertEqual((root/'work/vic-raw'/(sha+'.json')).read_bytes(), raw)
        receipt = json.loads((root/'work/vic-raw/capture.json').read_text())
        self.assertEqual(receipt['raw_sha256'], sha)
        self.assertEqual(receipt['content_sha256'], 'a'*64)
        self.assertEqual(receipt['acquisition_status'], 'SOURCE_SHA_CHANGED')

    def test_capture_rejects_bytes_that_do_not_match_the_receipt(self):
        root, _ = self.write_capture_fixture(b'{"timeStamp":"x"}', corrupt=True)
        with self.assertRaisesRegex(RuntimeError, 'VIC_RAW_FILE_SHA_MISMATCH'):
            self.functions['capture'](root)

    def test_no_raw_response_records_unavailability_without_inventing_bytes(self):
        root = self.fixture.root
        self.functions['capture'](root)
        receipt = json.loads((root/'work/vic-raw/capture.json').read_text())
        self.assertEqual(receipt['status'], 'NO_RAW_RESPONSE_AVAILABLE')
        self.assertEqual([p.name for p in (root/'work/vic-raw').iterdir()], ['capture.json'])


if __name__ == '__main__':
    unittest.main()
