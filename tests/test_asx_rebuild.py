"""Protect the immutable Census and include non-primary evidence dependencies."""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location('rebuild_asx_census', Path(__file__).resolve().parents[1] / 'tools/rebuild_asx_census.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class RebuildBoundary(unittest.TestCase):
    def test_source_review_v2_without_cutoff_uses_frozen_identity_and_discovery(self):
        ledgers = [{'version': 'asx-source-review-v2', 'acquired_through': '2026-11-10'},
                   {'cutoff': '2026-11-05'}, {'cutoff': '2026-11-05'}]
        self.assertEqual('2026-11-05', module.review_cutoff(ledgers))

    def test_conflicting_frozen_cutoffs_are_rejected(self):
        with self.assertRaisesRegex(ValueError, 'CUTOFF_MISMATCH'):
            module.review_cutoff([{'cutoff': '2026-11-05'}, {'cutoff': '2026-11-04'}])

    def test_acquisition_date_cannot_silently_replace_cutoff(self):
        with self.assertRaisesRegex(ValueError, 'CUTOFF_MISMATCH'):
            module.review_cutoff([{'cutoff': '2026-11-05', 'acquired_through': '2026-11-10'}], '2026-11-10')

    def test_cannot_export_inside_census(self):
        with tempfile.TemporaryDirectory() as temp:
            census = Path(temp) / 'census'; census.mkdir()
            with self.assertRaisesRegex(ValueError, 'OUTSIDE_CENSUS'):
                module.output_paths(census / 'results/new', census)
            self.assertEqual([], list(census.iterdir()))

    def test_existing_replay_cannot_be_overwritten(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); prefix = root / 'run'
            paths = module.output_paths(prefix, root / 'census')
            paths['a-53'].mkdir(); sentinel = paths['a-53'] / 'reviewed.csv'
            sentinel.write_text('retained', encoding='utf8')
            with self.assertRaisesRegex(ValueError, 'FRESH_OUTPUT'):
                module.output_paths(prefix, root / 'census')
            self.assertEqual('retained', sentinel.read_text())

    def test_nested_archive_dependency_cannot_be_omitted(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); (root / 'pdf').mkdir(); cfg = root / 'map.json'
            cfg.write_text(json.dumps(dict(version='asx-local-assets-v1', roots={'pdf': str(root / 'pdf')})))
            ledger = {'reviews': [{'asset_set': 'pdf', 'publication_archive_evidence': {'asset_set': 'archive'}}]}
            with self.assertRaisesRegex(ValueError, 'LOCAL_ASSETS_MISSING:archive'):
                module.load_assets(cfg, root / 'census', [ledger])

    def test_canonical_root_override_uses_requested_census(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); census = root / 'census'; census.mkdir(); cfg = root / 'map.json'
            cfg.write_text(json.dumps(dict(version='asx-local-assets-v1', roots={'canonical': 'unrelated-old-store'})))
            self.assertEqual(census.resolve(), module.load_assets(cfg, census, [{'asset_set': 'canonical'}])['canonical'])
