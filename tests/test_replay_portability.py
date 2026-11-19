"""Selected receipts must resolve immutable sources within a declared checkout or asset library."""
import json
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from au_ree_v2.acquisition import census_acquisition, checked_snapshots
from au_ree_v2.census import export_summary
from au_ree_v2.store import connect, digest, filehash
from tools.bundle_census_replay import bundle


class ReplayPortabilityTests(unittest.TestCase):
    def test_orphaned_integrated_database_cannot_export_checkout_defaults(self):
        repository=Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            (root/'config').mkdir()
            for name in ('project_summary_columns.json','summary_rules.json','researcher_rule_decisions.json'):
                (root/'config'/name).write_bytes((repository/'config'/name).read_bytes())
            database=root/'work/databases/lost-run/canonical.sqlite'
            with closing(connect(database)) as db, db:
                db.execute("INSERT INTO runs VALUES (?,?,?,?,?,?,?,?)",
                    ('lost-run','2026-11-16','2026-11-13','{}','lost-configuration','lost-corpus','COMPLETED',None))
            with self.assertRaisesRegex(ValueError,'SUMMARY_RUN_METADATA_REQUIRED'):
                export_summary(root,database,root/'invalid-export')
            self.assertFalse((root/'invalid-export').exists())

    def test_receipt_replay_refuses_undesignated_neighbour_even_with_matching_hash(self):
        with tempfile.TemporaryDirectory() as folder:
            here = Path(folder)
            root = here/'checkout'
            root.mkdir()
            neighbour = here/'previous-run'
            neighbour.mkdir()
            blob = neighbour/'source.pdf'
            blob.write_bytes(b'original bytes')
            registry = dict(sources=[dict(key='original',kind='pdf')])
            path = root/'receipt.json'
            source = dict(key='original', kind='pdf', publication_date='2026-10-01', sha256=filehash(blob))
            for outside in (str(blob.resolve()), '../previous-run/source.pdf'):
                with self.subTest(outside=outside):
                    path.write_text(json.dumps(dict(cutoff='2026-11-13',registry_sha256=digest(registry),
                        snapshots=[dict(source,path=outside)],outcomes=[])),encoding='utf8')
                    with self.assertRaises(ValueError):
                        census_acquisition(root,registry,root/'run',{},'2026-11-13',replay=path)

    def test_relocated_receipt_and_raw_attachment_resolve_by_sha_without_old_host(self):
        with tempfile.TemporaryDirectory() as folder:
            here = Path(folder)
            checkout, assets = here/'fresh', here/'portable-assets'
            checkout.mkdir(); assets.mkdir()
            # Original and its raw response must both exist with exactly the declared bytes.
            entries = []
            for content in (b'reproducible projection', b'upstream raw response'):
                blob = assets/'blob'
                blob.write_bytes(content)
                sha = filehash(blob)
                blob.rename(assets/sha)
                entries.append(dict(path=str(here/'old-drive'/sha),sha256=sha))
            entry = dict(entries[0], key='source', original_responses=[entries[1]])
            result = checked_snapshots(checkout,[entry],'2026-11-13',replay_assets=assets)
            for item in (result[0],result[0]['original_responses'][0]):
                self.assertEqual(Path(item['path']),assets/item['sha256'])
            (assets/entries[1]['sha256']).write_bytes(b'wrong original')
            with self.assertRaisesRegex(ValueError,'checksum'):
                checked_snapshots(checkout,[entry],'2026-11-13',replay_assets=assets)

    def test_bundle_refuses_missing_raw_attachment_and_leaves_no_partial_destination(self):
        with tempfile.TemporaryDirectory() as folder:
            here = Path(folder)
            lock = here/'results/phase22-2026-11-06/snapshot_lock.json'
            lock.parent.mkdir(parents=True)
            lock.write_text('[]',encoding='utf8')
            p = here/'original'
            p.write_bytes(b'known bytes')
            source = dict(key='version',sha256=filehash(p),path='original',
                          original_responses=[dict(sha256='a'*64,path='missing')])
            receipt = here/'receipt.json'
            receipt.write_text(json.dumps(dict(snapshots=[source])),encoding='utf8')
            with self.assertRaises((ValueError,FileNotFoundError)):
                bundle(here,receipt,here/'deliverable')
            self.assertFalse((here/'deliverable').exists())
