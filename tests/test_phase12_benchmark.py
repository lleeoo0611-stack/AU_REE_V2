"""Original-page evaluation stays separate from observations and frozen metrics."""
import importlib.util
import json
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
SPEC=importlib.util.spec_from_file_location('phase12_document_evaluation',ROOT/'tools/evaluate_documents.py')
EVALUATION=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(EVALUATION)


class Phase12BenchmarkTests(unittest.TestCase):
    def test_historical_benchmarks_are_snapshot_bound(self):
        for phase,legacy in ((9,True),(10,False)):
            expected=json.loads((ROOT/f'data/phase{phase}_document_benchmark.json').read_text())
            self.assertEqual(expected,EVALUATION.evaluate(ROOT,legacy=legacy))

    def test_changed_original_is_rejected_before_evaluation(self):
        with patch('au_ree_v2.store.filehash',return_value='changed'):
            with self.assertRaisesRegex(ValueError,'BENCHMARK_ORIGINAL_SHA_MISMATCH'):
                EVALUATION.evaluate_phase12(ROOT)

    def test_selected_original_page_metrics_and_provenance(self):
        from au_ree_v2.store import filehash
        before=filehash(ROOT/'data/manifest.json')
        result=EVALUATION.evaluate_phase12(ROOT)
        self.assertEqual(before,filehash(ROOT/'data/manifest.json'))
        self.assertEqual(8,result['documents'])
        self.assertEqual(13,result['physical_pages'])
        self.assertEqual(22,result['numeric_cells'])
        self.assertEqual(23,result['acceptance_cases'])
        numeric=result['numeric_metrics']
        self.assertEqual(result['numeric_cells'],numeric['true_positive']+numeric['false_negative'])
        c=result['acceptance_metrics']
        self.assertEqual(result['acceptance_cases'],sum(c[k] for k in ('true_positive','false_positive','false_negative','true_negative')))
        self.assertIn('NOT_BLIND',result['scope'])
        for r in result['sources']:
            self.assertEqual(64,len(r['source_sha256']))
            self.assertTrue(r['source_url'].startswith('https://'))
            self.assertTrue(r['physical_pages'])
        controls={r['label']:r for r in result['acceptance_results']}
        for label in ('cross_page_same_headers_reserve_not_resource','THM_resource_not_TREO','glossary_not_completed_DFS','company_cash_not_project_funds','future_funding_terms_not_completed_event','Nb2O5_not_TREO'):
            self.assertFalse(controls[label]['actual_acceptance'],label)
        for label in ('Rare_Dyke','Phos_Dyke','Combined'):
            control=controls['Cummins_'+label+'_P2O5_not_TREO']
            self.assertFalse(control['actual_acceptance'],label)
            self.assertIn('RESOURCE_NUMERIC_COLUMN_BINDING_NOT_ESTABLISHED',control['issues'])
        # A conservative miss is retained in recall rather than removed from gold.
        self.assertTrue(any(r['expected_scope'].startswith('Global') for r in result['numeric_results']))


if __name__=='__main__':unittest.main()
