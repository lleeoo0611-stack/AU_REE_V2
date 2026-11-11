import hashlib,importlib.util,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
from au_ree_v2 import round3_schema as m
from au_ree_v2.round3_schema import unpack
class FrozenTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.repo=Path(self.tmp.name);self.frozen=self.repo/m.FROZEN_PRESENTATION_PATH;self.frozen.mkdir(parents=True)
  self.raw={'field_provenance.csv':b'project,column,value\r\nx,y,z\r\n','專案總表.csv':'專案ID,專案名稱\r\nx,測試\r\n'.encode('utf8')}
  for n,b in self.raw.items():(self.frozen/n).write_bytes(b)
  self.hashes={n:hashlib.sha256(b).hexdigest() for n,b in self.raw.items()};self.patch=patch.object(m,'FROZEN_PRESENTATION_SHA256',self.hashes);self.patch.start()
 def tearDown(self):self.patch.stop();self.tmp.cleanup()
 def test_exact_bytes(self):
  records=m.frozen_presentation_files(self.repo)
  self.assertEqual({n:unpack(r) for n,r in records.items()},self.raw)
 def test_current_never_required(self):self.assertEqual(len(m.frozen_presentation_files(self.repo)),2)
 def test_published_current_does_not_change_output(self):
  a=m.frozen_presentation_files(self.repo);current=self.repo/'results/asx-current';current.mkdir()
  for n in self.raw:(current/n).write_text('new51-column presentation with new cells')
  self.assertEqual(m.frozen_presentation_files(self.repo),a)
 def test_missing_original_no_fallback(self):
  (self.frozen/'field_provenance.csv').unlink();current=self.repo/'results/asx-current';current.mkdir();(current/'field_provenance.csv').write_bytes(self.raw['field_provenance.csv'])
  with self.assertRaisesRegex(ValueError,'FILE_MISSING_OR_LINKED'):m.frozen_presentation_files(self.repo)
 def test_mutated_original_blocks(self):
  (self.frozen/'field_provenance.csv').write_bytes(b'changed')
  with self.assertRaisesRegex(ValueError,'SHA_MISMATCH'):m.frozen_presentation_files(self.repo)
 def test_read_once_digest_checked_after_pack(self):
  real=m.pack
  def modify_then_pack(root,names):
   (root/'field_provenance.csv').write_bytes(b'changed between path check and read');return real(root,names)
  with patch.object(m,'pack',side_effect=modify_then_pack),self.assertRaisesRegex(ValueError,'SHA_MISMATCH'):m.frozen_presentation_files(self.repo)
 def test_real_repository_matches_accepted_archive(self):
  import json
  self.patch.stop()
  try:
   expected=json.loads((ROOT/'results/round3-1-2026-11-11/projection/retired_columns_trace.json').read_text())['presentation_files']
   self.assertEqual(m.frozen_presentation_files(ROOT),expected)
  finally:self.patch.start()
if __name__=='__main__':unittest.main()
