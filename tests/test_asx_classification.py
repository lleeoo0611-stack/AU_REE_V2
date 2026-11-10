import copy
import json
import tempfile
import unittest
from pathlib import Path
from au_ree_v2.classification import classification_fills, draft_codebook, load_codebook


class ClassificationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/'book.json'
        self.row={'專案ID':'P','礦床型態':'mineral sands','礦床型態代碼':'',
                  '開發階段':'Exploration（來源揭露：2026-02，月精度）','開發階段代碼':'','開發階段類別':''}
        self.cfg=draft_codebook([self.row,self.row])
        self.provenance=[dict(project_id='P',column=c,value=self.row[c],source_sha256='native-sha',
                            locator='native page2',method='SOURCE_REPORTED') for c in ('礦床型態','開發階段')]

    def book(self,approved=False):
        if approved:self.cfg.update(status='APPROVED',approved_by='Synthetic test researcher',approved_date='2026-11-10')
        self.path.write_text(json.dumps(self.cfg,ensure_ascii=False),encoding='utf8')
        return load_codebook(self.path)

    def test_draft_never_fills_even_with_suggestions(self):
        self.assertEqual([],classification_fills(self.row,self.provenance,self.book()))
        self.assertEqual(2,self.cfg['deposit_type']['mineral sands']['count'])
        self.assertIsNone(self.cfg['approved_by'])

    def test_approved_exact_mapping_has_version_and_original_provenance(self):
        fills=classification_fills(self.row,self.provenance,self.book(True))
        self.assertEqual({'礦床型態代碼','開發階段代碼','開發階段類別'},{f['column'] for f in fills})
        for f in fills:
            self.assertIn('v1',f['method']);scope=json.loads(f['scope'])
            self.assertEqual(self.row[scope['source_column']],scope['source_value'])
            self.assertEqual('native-sha',f['sha'])
            self.assertEqual('native page2',scope['source_provenance']['locator'])
            self.assertEqual(64,len(scope['codebook_sha256']))

    def test_unmapped_and_unlisted_text_remain_blank(self):
        self.cfg['deposit_type']['mineral sands'].update(status='UNMAPPED',code=None)
        self.row['開發階段']='Exploration（來源揭露：2025-01-01）'
        self.assertEqual([],classification_fills(self.row,self.provenance,self.book(True)))

    def test_existing_code_or_category_is_never_overwritten(self):
        original=copy.deepcopy(self.provenance)
        self.row.update(礦床型態代碼='existing',開發階段代碼='old-stage',開發階段類別='old-category')
        self.assertEqual([],classification_fills(self.row,self.provenance,self.book(True)))
        self.assertEqual(original,self.provenance)

    def test_incomplete_approval_and_missing_source_are_rejected(self):
        for key,value in [('approved_by',None),('approved_date','not-a-date')]:
            self.book(True);self.cfg[key]=value
            with self.assertRaises(ValueError):self.book()
        book=self.book(True)
        with self.assertRaisesRegex(ValueError,'SOURCE_PROVENANCE_REQUIRED'):
            classification_fills(self.row,[],book)

    def test_inventory_keeps_ambiguous_native_text_unmapped(self):
        row=dict(self.row,礦床型態='potential for large scale, clay-hosted REE mineralisation',開發階段='currently the subject of DFS')
        cfg=draft_codebook([row])
        self.assertEqual('UNMAPPED',next(iter(cfg['deposit_type'].values()))['status'])
        self.assertEqual('UNMAPPED',next(iter(cfg['development_stage'].values()))['status'])
