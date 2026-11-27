"""Regression checks for CI scope and reverse dependency selection."""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from tools.phase10_ci import route


class Phase10CIRoutingTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        tree = {'src/au_ree_v2/evidence.py': '',
                'src/au_ree_v2/analysis.py': 'from . import evidence\n',
                'tests/test_analysis.py': 'from au_ree_v2.analysis import prepare\n',
                'tests/test_phase10_ci.py': 'from tools.phase10_ci import route\n'}
        for path, content in tree.items():
            file = self.root / path
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_text(content, encoding='utf-8')

    def test_scientific_changes_select_full_and_transitive_tests(self):
        plan = route(self.root, ['src/au_ree_v2/evidence.py'])
        self.assertTrue(plan['full'])
        self.assertTrue(plan['integration'])
        self.assertIn('analysis', plan['affected_modules'])
        self.assertIn('test_analysis.py', plan['fast_tests'])

    def test_audit_and_docs_have_distinct_tiers(self):
        audit = route(self.root, ['tools/phase10_quality.py'])
        self.assertFalse(audit['full'])
        self.assertFalse(audit['public'])
        self.assertTrue(audit['integration'])
        self.assertIn('test_phase10_ci.py', audit['fast_tests'])
        docs = route(self.root, ['docs/方法.md'])
        self.assertTrue(docs['fast'])
        self.assertFalse(docs['full'])
        self.assertFalse(docs['integration'])

    def test_source_update_and_unknown_base_select_full_public(self):
        for paths in (None, ['data/snapshots/original.md'], ['config/sources.json']):
            with self.subTest(paths=paths):
                result = route(self.root, paths)
                self.assertTrue(result['public'])
                self.assertTrue(result['full'])


if __name__ == '__main__':
    unittest.main()
