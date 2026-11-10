import copy
import gzip
import json
import tempfile
import unittest
from pathlib import Path
from au_ree_v2.review_storage import apply_delta,delta,encoded,restore_review,sha,write_review


class ReviewStorageTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)

    def test_delta_roundtrip_types_order_additions_and_removals(self):
        pairs=[({'a':1,'b':2},{'b':2,'c':3,'a':1}),({'a':1,'b':2},{'b':2,'a':1}),
               ({'a':{'value':1}},{'a':{'value':1.0}}),({'a':[1]},{'a':[True]}),([1,2,3],[True,4]),([],['x']),
               ({'x':[None,False,{'ü':'中'}]}, {'x':[0,True,{'ü':'字'}]}),
               ([{'project_id':'P','column':'a','value':1},{'project_id':'P','column':'b','value':2}],
                [{'project_id':'P','column':'b','value':3},{'project_id':'Q','column':'c','value':4}])]
        for before,after in pairs:
            with self.subTest(before=before):
                self.assertEqual(encoded(after),encoded(apply_delta(before,delta(before,after))))

    def test_chain_restores_exact_original_hash_and_snapshot_is_deterministic(self):
        reports=[{'round':n,'data':[dict(project_id='P',column=str(i),value='unchanged'*50) for i in range(100)]} for n in range(3)]
        reports[1]['data'][50]['value']='new';reports[2]['data'].pop(20)
        prior=None
        for n,report in enumerate(reports):
            path=self.root/f'{n}/cycle_review.json'
            receipt=write_review(report,path,prior)
            self.assertEqual(sha(encoded(report)),sha(restore_review(path)))
            self.assertEqual(encoded(report),restore_review(path))
            self.assertTrue(receipt['restored_byte_identical'])
            index=json.loads(path.read_text('utf8'))
            self.assertNotIn('review_manifest',index)
            self.assertEqual(gzip.compress(encoded(report),mtime=0),(path.parent/index['full_gzip']).read_bytes())
            prior=path
        self.assertLess(prior.stat().st_size,len(encoded(reports[-1]))//2)
        # The delta chain itself restores without intermediate/current gzip snapshots.
        for n in (1,2):(self.root/f'{n}/cycle_review.full.json.gz').unlink()
        self.assertEqual(encoded(reports[-1]),restore_review(prior,verify_snapshot=False))

    def test_legacy_full_base_unchanged_and_tampered_delta_rejected(self):
        legacy=self.root/'legacy.json';legacy.write_bytes(encoded({'old':1}))
        baseline=legacy.read_bytes();new=self.root/'new/cycle_review.json'
        write_review({'old':2},new,legacy)
        self.assertEqual(baseline,legacy.read_bytes())
        index=json.loads(new.read_text('utf8'));index['delta']['changes']['old']['value']=999
        new.write_text(json.dumps(index),encoding='utf8')
        with self.assertRaisesRegex(ValueError,'RESTORED_HASH'):restore_review(new)

    def test_tampered_base_or_snapshot_and_overwrite_rejected(self):
        path=self.root/'a/cycle_review.json';write_review({'value':1},path)
        with self.assertRaisesRegex(ValueError,'REFUSES_OVERWRITE'):write_review({'value':2},path)
        second=self.root/'b/cycle_review.json';write_review({'value':2},second,path)
        raw=path.read_bytes();path.write_bytes(raw+b' ')
        with self.assertRaisesRegex(ValueError,'BASE_INDEX_HASH'):restore_review(second)
        path.write_bytes(raw)
        (second.parent/'cycle_review.full.json.gz').write_bytes(gzip.compress(encoded({'value':3}),mtime=0))
        with self.assertRaisesRegex(ValueError,'SNAPSHOT_MISMATCH'):restore_review(second)

    def test_actual_historical_rounds_restore_byte_identically(self):
        root=Path(__file__).resolve().parents[1]/'results/asx-full-scope-2026-11-10'
        prior=None
        for number in (19,20):
            original=(root/f'round-{number}-report/audit/cycle_review.json').read_bytes()
            report=json.loads(original)
            path=self.root/f'{number}/cycle_review.json'
            write_review(report,path,prior,original_bytes=original)
            self.assertEqual(sha(original),sha(restore_review(path)))
            prior=path
