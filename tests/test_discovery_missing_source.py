import csv,json,subprocess,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from au_ree_v2.discovery import search_tasks
from au_ree_v2.store import canonical,filehash

ROOT=Path(__file__).resolve().parents[1]
class DiscoveryMissingSourceTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
  (self.root/'data').mkdir();(self.root/'config').mkdir()
  self.source=dict(key='registered',kind='pdf',url='https://www.asx.com.au/registered.pdf')
  self.claims=dict(projects=[dict(id='registered-project',name='Registered Project',identity_source='registered',observations=[])])
  (self.root/'data/claims.json').write_text(json.dumps(self.claims),encoding='utf8');self.config=dict(seeds=[],task_execution_version='bounded-registry-search-v1')
  self.write()
 def write(self,snapshots=()):
  (self.root/'data/manifest.json').write_text(json.dumps(dict(snapshots=list(snapshots))),encoding='utf8')
  (self.root/'config/sources.json').write_text(json.dumps(dict(sources=[self.source])),encoding='utf8')
 def test_unacquired_registered_source_is_retained_and_reported(self):
  for path in (None,'','missing.pdf'):
   with self.subTest(path=path):
    if path is not None:self.source['path']=path
    self.write();tasks=search_tasks(self.root,self.config)
    self.assertEqual(tasks[0]['source_key'],'registered')
    with (self.root/'work/discovery/acquisition_report.csv').open(encoding='utf8') as f:rows=list(csv.DictReader(f))
    self.assertEqual(len(rows),1);self.assertEqual(rows[0]['stop_reason'],'SOURCE_NOT_ACQUIRED');self.assertEqual(rows[0]['http_status'],'')
 def test_corrupt_or_wrong_sha_uses_existing_path_not_missing_guard(self):
  p=self.root/'bad.pdf';p.write_bytes(b'not-a-pdf');self.source.update(path='bad.pdf',sha256='0'*64);self.write([self.source])
  with patch('au_ree_v2.discovery.filehash',wraps=filehash) as checked:
   search_tasks(self.root,self.config)
  checked.assert_called_once_with(p)
  self.assertFalse((self.root/'work/discovery/acquisition_report.csv').exists())
 def test_existing_source_task_bytes_match_unmodified_base(self):
  import pymupdf
  p=self.root/'old.pdf'
  with pymupdf.open() as pdf:
   page=pdf.new_page();page.insert_text((40,40),'ASX: ABC');pdf.save(p)
  self.source.update(path='old.pdf',sha256=filehash(p));self.write([self.source])
  namespace={'__name__':'au_ree_v2._base_discovery_test','__package__':'au_ree_v2'}
  exec(subprocess.check_output(['git','show','b5e2a73:src/au_ree_v2/discovery.py'],cwd=ROOT),namespace)
  old=namespace['search_tasks'](self.root,self.config);new=search_tasks(self.root,self.config)
  self.assertEqual(canonical(old).encode(),canonical(new).encode());self.assertFalse((self.root/'work/discovery/acquisition_report.csv').exists())

if __name__=='__main__':unittest.main()
