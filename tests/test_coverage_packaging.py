import json
import sys
import tempfile
import unittest
from pathlib import Path
from au_ree_v2.store import filehash

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
from package_coverage_cycle import compact_cycle


class CompactAuditSafety(unittest.TestCase):
    def fixture(self, root):
        outputs = ('專案總表.csv', 'field_provenance.csv', 'missing_fields.csv', 'census_inventory.csv')
        for name in (*outputs, 'summary.json', 'asx_source_reviews.json',
                     'asx_discovery_reviews.json', 'asx_project_identity_reviews.json',
                     'remaining_gap_reasons.csv', 'audit.json'):
            (root/name).write_text('generated evidence', encoding='utf8')
        value = dict(current_integrity=dict(output_hashes={name:filehash(root/name) for name in outputs}))
        (root/'validation.json').write_text(json.dumps(value), encoding='utf8')
        return value

    def test_current_data_removed_only_after_preserving_audit_hashes(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); original = self.fixture(root)
            compact_cycle(root, 'a'*40)
            value = json.loads((root/'validation.json').read_text('utf8'))
            self.assertEqual(original['current_integrity']['output_hashes'], value['exported_csv_hashes'])
            self.assertTrue((root/'audit.json').exists())
            self.assertFalse((root/'專案總表.csv').exists())
            self.assertEqual(3, len(value['source_configuration_hashes']))

    def test_external_filename_is_rejected_before_deletion(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); value = self.fixture(root)
            value['current_integrity']['output_hashes']['../reference.csv'] = 'x'
            (root/'validation.json').write_text(json.dumps(value), encoding='utf8')
            with self.assertRaisesRegex(ValueError, 'CONTRACT'):
                compact_cycle(root, 'a'*40)
            self.assertTrue((root/'專案總表.csv').exists())

    def test_changed_output_is_rejected_before_deletion(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); self.fixture(root)
            (root/'專案總表.csv').write_text('changed', encoding='utf8')
            with self.assertRaisesRegex(ValueError, 'HASH'):
                compact_cycle(root, 'a'*40)
            self.assertTrue((root/'asx_source_reviews.json').exists())
