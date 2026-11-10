import json
import csv
import sys
import tempfile
import unittest
from pathlib import Path
from au_ree_v2.store import filehash

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
from package_coverage_cycle import compact_cycle,package
from au_ree_v2.review_storage import restore_review


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


class PackageDeltaIntegration(unittest.TestCase):
    def test_existing_historical_output_is_rejected_before_mutation(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);sentinel=root/'history.json';sentinel.write_text('immutable',encoding='utf8')
            with self.assertRaisesRegex(ValueError,'REQUIRES_EMPTY_OUTPUT'):
                package(root,root,root,root,root,root,root)
            self.assertEqual('immutable',sentinel.read_text('utf8'))

    def test_package_writes_delta_and_compressed_full_then_compacts_safely(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);snapshots=root/'snapshots';snapshots.mkdir()
            names=['asx_source_reviews.json','asx_discovery_reviews.json','asx_project_identity_reviews.json']
            for name in names:(snapshots/name).write_text('{}',encoding='utf8')
            columns=json.loads((Path(__file__).resolve().parents[1]/'config/project_summary_columns.json').read_text('utf8'))+['ASX代碼']
            def export(name):
                folder=root/name;folder.mkdir()
                row=dict.fromkeys(columns,'');row['專案ID']='P'
                for file,fields,rows in [
                    ('專案總表.csv',columns,[row]),
                    ('field_provenance.csv',['project_id','column','value'],[dict(project_id='P',column='專案ID',value='P')]),
                    ('missing_fields.csv',['project_id','column','reason'],[dict(project_id='P',column=c,reason='unknown') for c in columns if c!='專案ID']),
                    ('census_inventory.csv',['entity_id'],[dict(entity_id='P')])]:
                    with (folder/file).open('w',encoding='utf-8-sig',newline='') as f:
                        writer=csv.DictWriter(f,fields);writer.writeheader();writer.writerows(rows)
                summary=dict(version='census-project-summary-v3-asx-identity',base_contract_columns=52,
                    database_modified=False,database_sha256='frozen',
                    **{key:filehash(snapshots/name) for key,name in zip(
                        ['review_ledger_sha256','discovery_ledger_sha256','identity_ledger_sha256'],names)},
                    output_hashes={p.name:filehash(p) for p in folder.glob('*.csv')})
                (folder/'summary.json').write_text(json.dumps(summary),encoding='utf8')
                return folder
            before,after,repeat=[export(n) for n in ('before','after','repeat')]
            manifest=root/'manifest.json'
            manifest.write_text(json.dumps(dict(cycle_id='synthetic',stopping_policy='LEGACY_BELOW_THREE',
                tracks={n:dict(completed=True,records=[dict(query='synthetic public source',disposition='reviewed')]) for n in ('candidates','numeric')})),encoding='utf8')
            tests=root/'tests.xml';tests.write_text('<testsuites><testsuite tests="1" failures="0" errors="0"/></testsuites>',encoding='utf8')
            prior=None
            for n in (1,2):
                out=root/f'package-{n}'
                result=package(before,after,repeat,manifest,snapshots,tests,out,prior)
                self.assertEqual('STOP',result['decision'])
                index=out/'cycle_review.json'
                full=json.loads(restore_review(index))
                self.assertEqual('synthetic',full['cycle_id'])
                self.assertNotIn('review_manifest',json.loads(index.read_text('utf8')))
                self.assertEqual(prior is None,json.loads(index.read_text('utf8'))['base'] is None)
                compact_cycle(out,'a'*40)
                self.assertEqual(full,json.loads(restore_review(index)))
                prior=index
