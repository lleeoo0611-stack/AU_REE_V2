import base64,gzip,hashlib,importlib.util,json,shutil,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from au_ree_v2 import round3_release as r

def packed(raw):return dict(encoding='gzip-base64',sha256=hashlib.sha256(raw).hexdigest(),data=base64.b64encode(gzip.compress(raw,mtime=0)).decode())
class ReleaseTests(unittest.TestCase):
 def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
 def tearDown(self):self.tmp.cleanup()
 def write(self,name,value):
  p=self.root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(value),encoding='utf8');return p
 def test_safe(self):
  self.write('a.json',dict(source='https://official.example/data?x=1'));self.assertEqual(r.verify_public_tree(self.root)['credential_query_references'],0)
 def test_literal_blocks(self):
  self.write('a.json',dict(source='https://official.example/data?token=TEST_ONLY'))
  with self.assertRaisesRegex(ValueError,'CREDENTIAL_REFERENCE'):r.verify_public_tree(self.root)
 def test_repeated_encoded_blocks(self):
  self.write('a.json',dict(source='https://official.example/data%253Fapi_key%253DTEST_ONLY'))
  with self.assertRaisesRegex(ValueError,'CREDENTIAL_REFERENCE'):r.verify_public_tree(self.root)
 def test_decoded_blocks(self):
  self.write('a.json',packed(b'url\nhttps://official.example/data?sig=TEST_ONLY'))
  with self.assertRaisesRegex(ValueError,'CREDENTIAL_REFERENCE'):r.verify_public_tree(self.root)
 def test_nested_decoded_blocks(self):
  inner=json.dumps(dict(files={'x':packed(b'https://official.example/data?access_token=TEST_ONLY')})).encode()
  self.write('a.json',packed(inner))
  with self.assertRaisesRegex(ValueError,'CREDENTIAL_REFERENCE'):r.verify_public_tree(self.root)
 def test_cloudflare_query_token_blocks(self):
  self.write('a.json',dict(source='https://official.example/?__cf_chl_f_tk=TEST_ONLY'))
  with self.assertRaisesRegex(ValueError,'CREDENTIAL_REFERENCE'):r.verify_public_tree(self.root)
 def test_nested_cloudflare_query_token_blocks(self):
  self.write('a.json',packed(b'https://official.example/%253F__cf_chl_tk%253DTEST_ONLY'))
  with self.assertRaisesRegex(ValueError,'CREDENTIAL_REFERENCE'):r.verify_public_tree(self.root)
 def test_decoded_count(self):
  inner=json.dumps(dict(files={'x':packed(b'a,b\n1,2')})).encode();self.write('a.json',packed(inner))
  self.assertEqual(r.verify_public_tree(self.root)['decoded_payloads_scanned'],2)
 def test_tampered_payload_blocks(self):
  p=packed(b'safe');p['sha256']='0'*64;self.write('a.json',p)
  with self.assertRaisesRegex(ValueError,'ARCHIVE_SHA'):r.verify_public_tree(self.root)
 def setup_release(self):
  repo=self.root;date='2026-11-11';work=repo/'work';work.mkdir();out=repo/'results/round3-5-2026-11-11';(out/'projection').mkdir(parents=True);summary=repo/'results/round3-summary-2026-11-11';summary.mkdir()
  metric=dict(filled=20,denominator=51,coverage=20/51);core=dict(original_53_columns=metric,all_retained_columns=metric,tiered_coverage=dict(combined=metric))
  (out/'projection/summary.json').write_text(json.dumps(core));(out/'projection/audit.json').write_text('{}')
  (out/'projection/專案總表.csv').write_text(','.join('c'+str(i) for i in range(51))+'\n'+','.join(['value','note']+['']*49)+'\n',encoding='utf8')
  current=repo/'results/asx-current';current.mkdir();(current/'old.txt').write_text('old current');(current/'validation.json').write_text('{"stale":true}');(current/'source_consistency.csv').write_text('historical notes')
  records=[]
  for i in range(6):
   (repo/f'results/round3-{i}-{date}').mkdir(exist_ok=True)
   records.append(dict(task=i,new_cells=i,tests=dict(tests=100,failures=0),independent_full_rebuilds=2,bitwise_identical_files={}))
  gates=dict(tasks=records,census_sha256='x'*64,nt_datum_controls=dict(accepted=True,controls=20))
  class Schema:
   @staticmethod
   def present(source,dest,repo):shutil.copytree(source,dest)
   @staticmethod
   def audit(folder):return dict(columns=51,valid=True)
  return (repo,date,work,out,summary,r.tree_hashes(current),Schema,lambda _:None,lambda:None),gates
 def test_complete_swap_fresh_metadata_and_backup(self):
  args,gates=self.setup_release()
  with patch.object(r,'check_task_receipts',return_value=gates):result=r.publish_round3(*args)
  current=self.root/'results/asx-current';backup=self.root/'results/asx-current.pre-round3-2026-11-11'
  self.assertEqual((backup/'old.txt').read_text(),'old current');self.assertFalse((current/'old.txt').exists());self.assertEqual((current/'source_consistency.csv').read_text(),'historical notes')
  v=json.loads((current/'validation.json').read_text());self.assertEqual(v['presentation_table_coverage']['filled'],2);self.assertEqual(v['all_retained_columns']['filled'],20);self.assertNotIn('stale',v);self.assertEqual(json.loads((current/'publication_status.json').read_text())['new_cells'],15)
  self.assertTrue((current/'README.md').is_file());self.assertTrue((current/'REVIEW.md').is_file());self.assertTrue(result['publication_audit']['security']['files_scanned']>0)
 def test_runner_baseline_change_blocks(self):
  args,gates=self.setup_release();(self.root/'results/asx-current/old.txt').write_text('changed')
  with self.assertRaisesRegex(ValueError,'CURRENT_CHANGED_DURING_REBUILD'):r.publish_round3(*args)
 def test_absent_baseline_blocks(self):
  args,gates=self.setup_release();args=list(args);args[5]=None
  with self.assertRaisesRegex(ValueError,'RUNNER_START_BASELINE_REQUIRED'):r.publish_round3(*args)
 def test_new_task_secret_blocks_before_swap(self):
  args,gates=self.setup_release();self.write('results/round3-2-2026-11-11/secret.json',packed(b'https://x.invalid/?token=TEST_ONLY'))
  with patch.object(r,'check_task_receipts',return_value=gates),self.assertRaisesRegex(ValueError,'CREDENTIAL_REFERENCE'):r.publish_round3(*args)
  self.assertTrue((self.root/'results/asx-current/old.txt').is_file());self.assertFalse((self.root/'results/asx-current.pre-round3-2026-11-11').exists())
if __name__=='__main__':unittest.main()
