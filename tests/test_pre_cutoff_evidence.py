import ast
import hashlib
import importlib.util
import json
import tempfile
import unittest
import copy
import io
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch
from au_ree_v2.acquisition import evidenced_snapshot,select_snapshots

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('pre_cutoff_verifier',ROOT/'tools/verify_pre_cutoff_evidence.py')
verifier=importlib.util.module_from_spec(spec)
spec.loader.exec_module(verifier)
KEY='reviewed_source_521f635719be1686'
SHA=hashlib.sha256(b'{}').hexdigest()
COMMIT='a'*40
HEAD='b'*40

class DateEvidence(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory(dir=ROOT/'work')
        self.addCleanup(self.folder.cleanup)
        self.root=Path(self.folder.name)
        (self.root/'config').mkdir()
        (self.root/'config/sources.json').write_text('{}')
        (self.root/'work').mkdir()
        self.source=dict(key=KEY,sha256=SHA,kind='government_arcgis',available_date='2026-11-18',
                         acquired_at='2026-11-18T00:00:00+00:00')
        self.evidence=dict(ref=verifier.REF,commit=COMMIT,path='results/receipt.json',
                           recorded_sha256=SHA,kind='SHA_RECORD',evidence_date='2026-11-10')
        self.proof=dict(sources_sha256=hashlib.sha256((self.root/'config/sources.json').read_bytes()).hexdigest(),
                        sources={KEY:dict(valid=True,declaration=self.evidence)})

    def write(self):
        (self.root/'work/pre_cutoff_evidence_verified.json').write_text(json.dumps(self.proof))

    def test_valid_same_bytes_uses_minimum_date_and_keeps_retrieval(self):
        self.write()
        result=evidenced_snapshot(self.root,self.source,'2026-11-13')
        self.assertEqual('2026-11-10',result['available_date'])
        self.assertEqual(self.source['acquired_at'],result['acquired_at'])
        self.assertEqual('2026-11-18',self.source['available_date'])
        old=dict(self.source,available_date='2026-11-09')
        self.assertEqual('2026-11-09',evidenced_snapshot(self.root,old,'2026-11-13')['available_date'])

    def test_no_proof_or_other_source_behaves_exactly_as_before(self):
        self.assertIs(self.source,evidenced_snapshot(self.root,self.source,'2026-11-13'))
        self.write()
        other=dict(self.source,key='unrelated')
        self.assertIs(other,evidenced_snapshot(self.root,other,'2026-11-13'))

    def test_wrong_bytes_config_late_date_or_invalid_proof_never_backdates(self):
        for case in ('sha','config','date','invalid','string_valid'):
            with self.subTest(case=case):
                proof=json.loads(json.dumps(self.proof))
                if case=='sha':proof['sources'][KEY]['declaration']['recorded_sha256']='0'*64
                if case=='config':proof['sources_sha256']='0'*64
                if case=='date':proof['sources'][KEY]['declaration']['evidence_date']='2026-11-14'
                if case=='invalid':proof['sources'][KEY]['valid']=False
                if case=='string_valid':proof['sources'][KEY]['valid']='true'
                (self.root/'work/pre_cutoff_evidence_verified.json').write_text(json.dumps(proof))
                self.assertIs(self.source,evidenced_snapshot(self.root,self.source,'2026-11-13'))

    def test_bad_proof_json_is_unavailable_evidence(self):
        (self.root/'work/pre_cutoff_evidence_verified.json').write_text('{')
        self.assertIs(self.source,evidenced_snapshot(self.root,self.source,'2026-11-13'))

    def test_selected_historical_bytes_are_still_checksum_verified(self):
        self.write()
        (self.root/'data').mkdir()
        (self.root/'data/source.json').write_bytes(b'{}')
        source=dict(self.source,path='data/source.json',url='https://government.invalid/query')
        (self.root/'data/manifest.json').write_text(json.dumps(dict(snapshots=[source])))
        before=(self.root/'data/manifest.json').read_bytes()
        selected=select_snapshots(self.root,'2026-11-13')
        self.assertEqual('2026-11-10',selected[0]['available_date'])
        self.assertEqual(before,(self.root/'data/manifest.json').read_bytes())
        (self.root/'data/source.json').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'checksum mismatch'):
            select_snapshots(self.root,'2026-11-13')

class RepositoryEvidenceVerifier(unittest.TestCase):
    def source(self):
        return dict(key=KEY,kind='government_arcgis',source_sha256=SHA,pre_cutoff_evidence=dict(
            ref=verifier.REF,commit=COMMIT,path='results/receipt.json',recorded_sha256=SHA,
            kind='SHA_RECORD',evidence_date='2026-11-10'))

    def run_case(self,source,events,fetched=True,raw=None,commit_time=b'2026-11-10T09:00:00+00:00'):
        def git(*args):
            return commit_time if args[0]=='show' else raw if raw is not None else SHA.encode()
        with patch.object(verifier,'git',side_effect=git),patch.object(verifier,'ancestor',return_value=True):
            return verifier.validate(source,events,'2026-11-13',fetched)

    def event(self,day='2026-11-10'):
        return dict(id='proof',type='PushEvent',created_at=day+'T10:00:00Z',payload=dict(head=HEAD))

    def test_record_with_commit_and_bound_push_event_passes(self):
        result=self.run_case(self.source(),[self.event()])
        self.assertTrue(result['valid'])
        self.assertEqual('2026-11-10',result['computed_evidence_date'])

    def test_create_event_alone_is_not_a_commit_push_proof(self):
        result=self.run_case(self.source(),[dict(type='CreateEvent',created_at='2026-11-10T10:00:00Z',
                         payload=dict(ref=verifier.REF))])
        self.assertFalse(result['valid'])
        self.assertIn('PUSH_TIME_NOT_PROVEN_FOR_COMMIT',result['reasons'])

    def test_missing_fetch_record_or_after_cutoff_is_not_accepted(self):
        self.assertFalse(self.run_case(self.source(),[self.event()],False)['valid'])
        self.assertFalse(self.run_case(self.source(),[self.event()],raw=b'no SHA')['valid'])
        source=self.source()
        source['pre_cutoff_evidence']['evidence_date']='2026-11-14'
        self.assertFalse(self.run_case(source,[self.event('2026-11-14')])['valid'])

    def test_raw_file_must_match_and_source_must_adopt_that_sha(self):
        source=self.source()
        source['pre_cutoff_evidence']['kind']='RAW_FILE'
        self.assertTrue(self.run_case(source,[self.event()],raw=b'{}')['valid'])
        self.assertFalse(self.run_case(source,[self.event()],raw=b'wrong')['valid'])
        source['source_sha256']='0'*64
        self.assertFalse(self.run_case(source,[self.event()],raw=b'{}')['valid'])

    def test_unapproved_source_or_path_is_rejected(self):
        source=self.source()
        source['key']='unapproved'
        self.assertFalse(self.run_case(source,[self.event()])['valid'])
        source=self.source()
        source['pre_cutoff_evidence']['path']='../outside'
        self.assertFalse(self.run_case(source,[self.event()])['valid'])

    def test_transport_class_and_b1_order_unchanged(self):
        import subprocess
        before=ast.parse(subprocess.check_output(['git','show','1e0b833:src/au_ree_v2/acquisition.py']).decode())
        after=ast.parse((ROOT/'src/au_ree_v2/acquisition.py').read_text(encoding='utf8'))
        left=next(n for n in before.body if isinstance(n,ast.ClassDef) and n.name=='StrictTransport')
        right=next(n for n in after.body if isinstance(n,ast.ClassDef) and n.name=='StrictTransport')
        self.assertEqual(ast.dump(left),ast.dump(right))
        source=(ROOT/'src/au_ree_v2/acquisition.py').read_text(encoding='utf8')
        self.assertLess(source.index("if host in transport.stopped:raise ValueError('HOST_STOPPED:'+transport.stopped[host])",source.index('def strict_refresh')),
                        source.index("if source.get('committed_snapshot_sha256')",source.index('def strict_refresh')))


class SealedEventEvidence(unittest.TestCase):
    def setUp(self):
        self.path=ROOT/'config/pre_cutoff_evidence_events.json'
        self.events=json.loads(self.path.read_bytes())
        self.sources=[copy.deepcopy(s) for s in json.loads((ROOT/'config/sources.json').read_bytes())['sources']
                      if s.get('pre_cutoff_evidence')]
        self.vic=next(s for s in self.sources if s['key'].endswith('31a205168b6ae647'))
        self.vic['pre_cutoff_evidence']['recorded_sha256']=SHA
        self.vic['pre_cutoff_evidence']['kind']='RAW_FILE'

    def run_case(self,live=None,error=None,path=None):
        def fake_git(*args):
            if args[0]=='show':return b'2026-11-10T11:30:14+00:00'
            if args[2].startswith(self.vic['pre_cutoff_evidence']['commit']):return b'{}'
            return '\n'.join(s['pre_cutoff_evidence']['recorded_sha256'] for s in self.sources).encode()
        def ancestor(left,right):
            return right==verifier.REF or left!=self.vic['pre_cutoff_evidence']['commit']
        with patch.object(verifier,'git',side_effect=fake_git),patch.object(verifier,'ancestor',side_effect=ancestor),\
             patch.object(verifier,'events_from_api',side_effect=error,return_value=(live or [],[])) as api:
            result,_=verifier.verify_sources(self.sources,path or self.path,'2026-11-13')
            return result,api.call_count

    def assert_ga_valid(self,result,crosscheck):
        self.assertTrue(result['events_file_sha_match'])
        for source in self.sources:
            if source is self.vic:continue
            record=result['sources'][source['key']]
            self.assertTrue(record['valid'],record)
            self.assertEqual(crosscheck,record['api_crosscheck'])

    def test_empty_live_window_keeps_three_ga_proofs_valid(self):
        result,_=self.run_case()
        self.assert_ga_valid(result,'EVENT_NOT_IN_API_WINDOW')

    def test_unavailable_live_api_keeps_three_ga_proofs_valid(self):
        result,_=self.run_case(error=OSError('offline'))
        self.assert_ga_valid(result,'API_UNAVAILABLE')

    def test_matching_live_event_crosschecks_without_replacing_archive(self):
        result,_=self.run_case(copy.deepcopy(self.events))
        self.assert_ga_valid(result,'MATCHED')

    def test_conflicting_live_timestamp_or_head_is_invalid(self):
        for field in ('time','head'):
            with self.subTest(field=field):
                events=copy.deepcopy(self.events)
                if field=='time':events[0]['created_at']='2026-11-11T11:42:29Z'
                else:events[0]['payload']['head']='f'*40
                result,_=self.run_case(events)
                self.assertTrue(all(not r['valid'] and 'EVENT_RECORD_CONFLICT' in r['reasons']
                                    for r in result['sources'].values()))

    def test_one_byte_change_invalidates_every_source_before_api(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'events.json';path.write_bytes(self.path.read_bytes()+b' ')
            result,calls=self.run_case(path=path)
        self.assertEqual(0,calls)
        self.assertFalse(result['events_file_sha_match'])
        self.assertTrue(all(r['reasons']==['EVENTS_FILE_SHA_MISMATCH'] and not r['valid']
                            for r in result['sources'].values()))

    def test_vic_has_no_committed_push_proof(self):
        result,_=self.run_case()
        record=result['sources'][self.vic['key']]
        self.assertFalse(record['valid'])
        self.assertEqual(['PUSH_TIME_NOT_PROVEN_FOR_COMMIT'],record['reasons'])

    def test_warning_includes_keys_when_proof_is_missing_and_when_invalid(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'proof.json';output=io.StringIO()
            with redirect_stdout(output):verifier.warn_invalid(path,self.sources)
            for source in self.sources:self.assertIn(source['key'],output.getvalue())
            result,_=self.run_case();path.write_text(json.dumps(result))
            output=io.StringIO()
            with redirect_stdout(output):verifier.warn_invalid(path,self.sources)
            self.assertIn('::warning::'+self.vic['key'],output.getvalue())
            self.assertIn('PUSH_TIME_NOT_PROVEN_FOR_COMMIT',output.getvalue())
            self.assertNotIn('::warning::'+KEY,output.getvalue())
