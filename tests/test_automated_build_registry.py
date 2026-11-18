"""Offline migrated-registry contracts; no assertion of live source acceptance."""
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
METHOD = 'EXPERIMENT_REVIEW_MIGRATED_REVERIFIED_AT_BUILD'


class MigratedRegistryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.claims = json.loads((ROOT/'data/claims.json').read_text(encoding='utf8'))
        cls.sources = json.loads((ROOT/'config/sources.json').read_text(encoding='utf8'))['sources']
        cls.by_key = {s['key']: s for s in cls.sources}
        cls.migrated = [o for p in cls.claims['projects'] for o in p['observations']
                        if o.get('extraction_method') == METHOD]

    def test_source_keys_unique_and_public(self):
        self.assertEqual(len(self.by_key), len(self.sources))
        for source in self.sources:
            self.assertNotIn('path', source)
            self.assertNotIn('asset_set', source)
            self.assertTrue(source['url'].startswith('https://'))

    def test_migrated_claim_contracts(self):
        self.assertEqual(len(self.migrated), 169)
        for claim in self.migrated:
            self.assertEqual(self.by_key[claim['source_key']]['source_sha256'], claim['source_sha256'])
            self.assertGreater(claim['pdf_page'], 0)
            self.assertGreaterEqual(len(claim['page_markers']), 2)
            self.assertTrue(all(isinstance(m, str) and m for m in claim['page_markers']))
            self.assertTrue(claim['scope'] and claim['statement_id'] and claim['locator'])

    def test_no_value_reinterpretation(self):
        for claim in self.migrated:
            original = claim['raw']['reviewed_observation']
            for field in ('value', 'unit', 'basis'):
                self.assertEqual(claim[field], original[field])
            expected = ('reported_y2o3_ppm' if original['variable'] == 'reported_resource_y_ppm'
                        else original['variable'])
            self.assertEqual(claim['variable'], expected)

    def test_review_cell_and_page_preserved(self):
        for claim in self.migrated:
            original = claim['raw']['reviewed_observation']
            self.assertEqual(claim['pdf_page'], original['evidence']['page'])
            self.assertEqual(claim['page_markers'], original['evidence']['markers'])
            self.assertIn('cell_binding', original)
            self.assertIn('ocr_clip=', claim['locator'])

    def test_unique_native_ids(self):
        identities = [(p.get('entity_namespace', 'project_registry_v1'), str(p['id']))
                      for p in self.claims['projects']]
        self.assertEqual(len(identities), 99)
        self.assertEqual(len(identities), len(set(identities)))


if __name__ == '__main__':
    unittest.main()
