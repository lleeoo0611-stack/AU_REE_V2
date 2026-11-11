import csv
import shutil
import tempfile
import unittest
from pathlib import Path
from au_ree_v2.coverage_task_audit import compare_projections,identical_replays,FILES


class CoverageAuditTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.a=Path(self.temp.name)/'a';self.b=Path(self.temp.name)/'b';self.a.mkdir()
        self.row={'專案ID':'p','專案名稱':'Project','總TREO蘊藏量_kt':'2','CeO2_氧化鈰_kt':'','已公布元素數_共15項':'1'}
        self.write(self.a,self.row)
        for name in FILES:
            if not (self.a/name).exists():(self.a/name).write_text('{}')
        shutil.copytree(self.a,self.b)

    def write(self,path,row,method='original'):
        with (path/'專案總表.csv').open('w',encoding='utf8',newline='') as h:
            w=csv.DictWriter(h,list(row));w.writeheader();w.writerow(row)
        with (path/'field_provenance.csv').open('w',encoding='utf8',newline='') as h:
            w=csv.DictWriter(h,['project_id','column','value','method']);w.writeheader()
            w.writerows(dict(project_id='p',column=k,value=v,method=method) for k,v in row.items() if v)

    def test_null_outputs_are_byte_identical(self):
        self.assertEqual(len(identical_replays(self.a,self.b)),6)
        self.assertEqual(compare_projections(self.a,self.b),([],[]))

    def test_existing_value_rejected(self):
        self.write(self.b,dict(self.row,總TREO蘊藏量_kt='3'))
        with self.assertRaisesRegex(ValueError,'EXISTING_VALUE'):compare_projections(self.a,self.b)

    def test_provenance_rewrite_rejected(self):
        self.write(self.b,self.row,'replacement')
        with self.assertRaisesRegex(ValueError,'PROVENANCE'):compare_projections(self.a,self.b)

    def test_derived_change_explicit(self):
        row=dict(self.row);row['已公布元素數_共15項']='2';self.write(self.b,row)
        with self.assertRaisesRegex(ValueError,'EXISTING_VALUE'):compare_projections(self.a,self.b)
        with self.assertRaisesRegex(ValueError,'WITHOUT_NEW_SOURCE_VALUE'):compare_projections(self.a,self.b,True)
        row['CeO2_氧化鈰_kt']='1';self.write(self.b,row)
        added,changed=compare_projections(self.a,self.b,True)
        self.assertEqual(len(changed),1);self.assertEqual(len(added),1)

    def test_blank_only_addition(self):
        row=dict(self.row);row['CeO2_氧化鈰_kt']='1';self.write(self.b,row)
        added,changed=compare_projections(self.a,self.b)
        self.assertEqual(len(added),1);self.assertEqual(changed,[])

    def test_inventory_immutable(self):
        (self.b/'census_inventory.csv').write_text('changed')
        with self.assertRaisesRegex(ValueError,'INVENTORY'):compare_projections(self.a,self.b)

    def test_summary_must_reproduce(self):
        (self.b/'summary.json').write_text('changed')
        with self.assertRaisesRegex(ValueError,'REBUILD_MISMATCH'):identical_replays(self.a,self.b)
