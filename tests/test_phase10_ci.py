"""Regression checks for CI scope and reverse dependency selection."""

from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from tools.phase10_ci import changed_paths, python_receipt, route


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
        for paths in (None, ['data/snapshots/original.md'], ['config/sources.json'], ['tests/test_removed.py']):
            with self.subTest(paths=paths):
                result = route(self.root, paths)
                self.assertTrue(result['public'])
                self.assertTrue(result['full'])
                self.assertTrue(result['archive'])

    def test_test_only_changes_keep_the_selected_test(self):
        for name, tier in (('test_analysis.py', 'fast'), ('test_mcda_execution_cache.py', 'integration')):
            with self.subTest(name=name):
                path = self.root / 'tests' / name
                path.touch()
                plan = route(self.root, ['tests/' + name])
                self.assertIn(name, plan[tier + '_tests'])
                self.assertEqual(plan['integration'], tier == 'integration')
                self.assertFalse(plan['full'])
                self.assertFalse(plan['public'])

    def test_receipt_update_keeps_prior_scientific_change_in_complete_diff(self):
        def git(*args):
            return subprocess.check_output(['git', '-c', 'user.email=ci@example.invalid',
                                            '-c', 'user.name=CI Test', *args], cwd=self.root, text=True).strip()

        git('init', '-q')
        git('add', '.')
        git('commit', '-qm', 'Baseline')
        base = git('rev-parse', 'HEAD')
        (self.root / 'src/au_ree_v2/evidence.py').write_text('changed = True\n')
        git('commit', '-qam', 'Scientific change')
        receipt = self.root / 'results/integrated-rebuild-2026-11-15/專案總表.csv'
        receipt.parent.mkdir(parents=True)
        receipt.touch()
        git('add', '.')
        git('commit', '-qm', 'Receipt update')
        paths = changed_paths(self.root, base)
        self.assertIn(receipt.relative_to(self.root).as_posix(), paths)
        self.assertTrue(route(self.root, paths)['archive'])

    def test_release_and_missing_base_fail_closed(self):
        for event in ('push', 'workflow_dispatch', 'schedule', 'workflow_call'):
            with self.subTest(event=event):
                plan = route(self.root, ['README.md'], event=event)
                self.assertTrue(all(plan[tier] for tier in ('full', 'archive', 'public')))
        self.assertTrue(route(self.root, changed_paths(self.root, ''))['archive'])

    def test_shared_python_requires_matching_environment_and_xml(self):
        bundle = self.root / 'bundle'
        reports = bundle / 'test-xml'
        reports.mkdir(parents=True)
        original = '<testsuite tests="1" failures="0" errors="0"><testcase name="fixture"/></testsuite>'
        report = reports / 'TEST-fixture.xml'
        report.write_text(original)
        with patch('tools.phase10_ci.python_environment', return_value={'commit': 'a' * 40}):
            python_receipt(self.root, bundle)
            python_receipt(self.root, bundle, verify=True)
            report.write_text(original.replace('fixture', 'different'))
            with self.assertRaisesRegex(ValueError, 'fingerprint'):
                python_receipt(self.root, bundle, verify=True)
        report.write_text(original)
        with patch('tools.phase10_ci.python_environment', return_value={'commit': 'b' * 40}):
            with self.assertRaisesRegex(ValueError, 'execution contract'):
                python_receipt(self.root, bundle, verify=True)

    def test_shared_python_rejects_failed_and_all_skipped_reports(self):
        bundle = self.root / 'bundle'
        reports = bundle / 'test-xml'
        reports.mkdir(parents=True)
        report = reports / 'TEST-fixture.xml'
        with patch('tools.phase10_ci.python_environment', return_value={'commit': 'a' * 40}):
            for outcome in ('failure', 'error', 'skipped'):
                with self.subTest(outcome=outcome):
                    report.write_text(f'<testsuite tests="1"><testcase><{outcome}/></testcase></testsuite>')
                    with self.assertRaises(ValueError):
                        python_receipt(self.root, bundle)
        self.assertFalse((bundle / 'receipt.json').exists())


if __name__ == '__main__':
    unittest.main()
