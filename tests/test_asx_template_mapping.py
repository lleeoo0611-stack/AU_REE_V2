import csv
import json
import tempfile
import unittest
from pathlib import Path
from au_ree_v2.template_mapping import load_template_mapping,template_mapping_fills
from au_ree_v2.store import filehash
from au_ree_v2.element_reextraction import oxide_hints,derivation_gaps


class TemplateMappingTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);(self.root/'config').mkdir();(self.root/'work').mkdir()
        self.raw=self.root/'work/original.csv'
        with self.raw.open('w',encoding='utf-8-sig',newline='') as f:
            w=csv.DictWriter(f,['礦床型態代碼','礦床型態','開發階段代碼','開發階段類別','開發階段']);w.writeheader()
            w.writerow(dict(zip(w.fieldnames,['placer','砂礦型','A1','探勘','初期探索階段'])))
        self.cfg=dict(version='user-template-mapping-v1',status='USER_PROVIDED_SCOPED_MAPPING',
            source=dict(local_path='work/original.csv',sha256=filehash(self.raw),bytes=self.raw.stat().st_size,rows=1,columns=5),
            mappings=dict(deposit_type={'mineral sands':dict(code='placer',template_label='砂礦型',rationale='Explicit sands')},development_stage={}))
        self.path=self.root/'config/map.json'
        self.row={'專案ID':'P','礦床型態':'mineral sands','礦床型態代碼':'','開發階段':'Exploration','開發階段代碼':'','開發階段類別':''}
        self.provenance=[dict(project_id='P',column='礦床型態',source_sha256='native-sha',value='mineral sands',locator='PDF p3')]

    def book(self):
        self.path.write_text(json.dumps(self.cfg,ensure_ascii=False),encoding='utf8')
        return load_template_mapping(self.path)

    def test_scoped_mapping_preserves_both_native_and_vocabulary_provenance(self):
        fill=template_mapping_fills(self.row,self.provenance,self.book())[0]
        self.assertEqual('placer',fill['value']);self.assertEqual('native-sha',fill['sha'])
        scope=json.loads(fill['scope']);self.assertEqual(filehash(self.raw),scope['vocabulary_source_sha256'])
        self.assertEqual('PDF p3',scope['source_provenance']['locator'])
        self.assertIn('UNCHANGED_DRAFT',scope['codebook_approval'])

    def test_existing_value_never_overwritten_and_no_fuzzy_mapping(self):
        book=self.book();self.row['礦床型態代碼']='existing'
        self.assertEqual([],template_mapping_fills(self.row,self.provenance,book))
        self.row.update(礦床型態代碼='',礦床型態='mineral sands?')
        self.assertEqual([],template_mapping_fills(self.row,self.provenance,book))

    def test_unknown_clay_and_generic_stage_remain_blank(self):
        self.row['礦床型態']='Clay hosted'
        self.assertEqual([],template_mapping_fills(self.row,self.provenance,self.book()))

    def test_source_tamper_and_fabricated_tuple_rejected(self):
        self.raw.write_bytes(self.raw.read_bytes()+b'\n')
        with self.assertRaisesRegex(ValueError,'SOURCE_HASH'):self.book()
        self.cfg['source'].update(sha256=filehash(self.raw),bytes=self.raw.stat().st_size)
        self.cfg['mappings']['deposit_type']['mineral sands']['code']='made-up'
        with self.assertRaisesRegex(ValueError,'TUPLE_NOT_IN_SOURCE'):self.book()

    def test_native_evidence_required(self):
        with self.assertRaisesRegex(ValueError,'NATIVE_PROVENANCE'):template_mapping_fills(self.row,[],self.book())


class ElementDiscoveryTests(unittest.TestCase):
    def test_unicode_spaced_formula_and_jorc_hints(self):
        h=oxide_hints('Nd₂O₃   D y 2 O 3   JORC Table 1')
        self.assertEqual(['Nd2O3','Dy2O3'],h['oxides']);self.assertTrue(h['extract_tables'])
        self.assertTrue(oxide_hints('oxide distribution')['extract_tables'])

    def test_conversion_factors_are_only_candidates(self):
        h=oxide_hints('Element Conversion Factor Nd2O3 1.1664 Dy2O3 1.1477')
        self.assertTrue(h['extract_tables']);self.assertNotIn('value',h)

    def test_missing_component_never_zero_and_complete_set_only(self):
        row={'Nd2O3_x':'2','Pr6O11_x':'','NdPr蘊藏量_kt_需兩者皆公布':'','完整重稀土組合蘊藏量_kt_需8元素皆公布':'','磁性元素重算值_NdPrTbDy_kt':''}
        self.assertEqual([],derivation_gaps(row));row['Pr6O11_x']='0'
        gaps=derivation_gaps(row);self.assertEqual(1,len(gaps));self.assertEqual(2,gaps[0]['value'])
        self.assertIn('REQUIRES_EXISTING_SAME_SCOPE',gaps[0]['decision'])
