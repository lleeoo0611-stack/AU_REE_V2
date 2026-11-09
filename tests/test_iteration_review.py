import csv,json,tempfile,unittest
from pathlib import Path
from au_ree_v2.iteration_review import audit_summary
from au_ree_v2.store import filehash

class IterationAuditTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.p=Path(self.tmp.name)
  self.cols=json.loads((Path(__file__).resolve().parents[1]/'config/project_summary_columns.json').read_text('utf8'))
  row={c:'' for c in self.cols};row['專案ID']='p';row[self.cols[15]]='0'
  self.write('專案總表.csv',self.cols,[row]);self.write('field_provenance.csv',['project_id','column','value'],[dict(project_id='p',column=c,value=v) for c,v in row.items() if v!=''])
  self.write('missing_fields.csv',['project_id','column','reason'],[dict(project_id='p',column=c,reason='UNKNOWN') for c,v in row.items() if v=='']);self.hashes()
 def write(self,n,fields,rows):
  with (self.p/n).open('w',encoding='utf-8-sig',newline='') as f:
   w=csv.DictWriter(f,fields);w.writeheader();w.writerows(rows)
 def hashes(self):
  (self.p/'summary.json').write_text(json.dumps(dict(output_hashes={n:filehash(self.p/n) for n in ['專案總表.csv','field_provenance.csv','missing_fields.csv']})))
 def test_zero_is_filled_not_missing(self):
  a=audit_summary(self.p);self.assertEqual(a['filled_cells'],2);self.assertEqual(a['scientific_filled_cells'],1);self.assertEqual(a['scientific_total_cells'],25)
 def test_stale_hash(self):
  with (self.p/'專案總表.csv').open('a') as f:f.write('\n')
  with self.assertRaisesRegex(ValueError,'HASH'):audit_summary(self.p)
 def test_missing_provenance(self):
  self.write('field_provenance.csv',['project_id','column','value'],[]);self.hashes()
  with self.assertRaisesRegex(ValueError,'PROVENANCE'):audit_summary(self.p)
 def test_missing_diagnostic(self):
  self.write('missing_fields.csv',['project_id','column','reason'],[]);self.hashes()
  with self.assertRaisesRegex(ValueError,'DIAGNOSTIC'):audit_summary(self.p)
