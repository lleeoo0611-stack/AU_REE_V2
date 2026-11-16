"""Phase12 evidence yield, historical extraction contracts and comparability."""
import copy
import csv
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from au_ree_v2.evidence import load_claims,normalize,validate_pages
from au_ree_v2.discovery import search_tasks
from au_ree_v2.pdf_extract import narrative_candidates,narrative_context_issues,project_registry
from au_ree_v2.selection import technical_record,technical_compare
from au_ree_v2.store import filehash
ROOT=Path(__file__).resolve().parents[1]

class Phase12Tests(unittest.TestCase):
    def test_historical_claims_resolve_sha_instead_of_live_file(self):
        for phase in range(5,12):
            date='2026-11-04' if phase==11 else '2026-11-03'
            c=json.loads((ROOT/f'results/phase{phase}-{date}/configuration.json').read_text())
            claims,sha=load_claims(ROOT,c['claims_sha256'])
            self.assertEqual(c['claims_sha256'],sha)
            self.assertNotIn('north-stanmore-exim-loi-reaffirmed20261030',{e['event_id'] for e in claims.get('events',[])})
            j=next((p for p in claims['projects'] if p['id']=='jupiter'),None)
            if j:self.assertFalse(any(o['variable']=='magnet_reo_share_pct' for o in j['observations']))

    def test_absent_or_changed_frozen_claims_fail_locally(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'work') as tmp:
            root=Path(tmp);(root/'data/snapshots').mkdir(parents=True)
            (root/'data/claims.json').write_text('{"projects":[]}')
            with self.assertRaisesRegex(ValueError,'FROZEN_CLAIMS'):
                load_claims(root,'0'*64)
            data,sha=load_claims(root,freeze=True)
            target=root/'data/snapshots'/(sha+'.claims.json')
            self.assertEqual(sha,filehash(target))
            (root/'data/claims.json').write_text('{"projects":[{"id":"changed"}]}')
            self.assertEqual(data,load_claims(root,sha)[0])
            target.write_text('{}')
            with self.assertRaisesRegex(ValueError,'FROZEN_CLAIMS'):load_claims(root,sha)

    def test_gap_priority_has_cost_reuse_and_joint_sample_components(self):
        reg=json.loads((ROOT/'config/discovery.json').read_text())
        tasks=search_tasks(ROOT,reg,ROOT/'results/phase11-2026-11-04/evidence_pipeline_diagnostics.csv')
        self.assertTrue(tasks)
        for t in tasks:
            self.assertEqual(t['priority'],sum(t['priority_components'].values()))
            self.assertIn('repeated_failure_cost',t['priority_components'])
            self.assertIn(t['potential_joint_sample_gain'],(0,1))
            self.assertIn('NOT_PREDICTED_SUCCESS',t['priority_basis'])
        self.assertEqual(tasks,sorted(tasks,key=lambda t:(-t['priority'],t['project_id'],t['criterion'])))

    def test_versioned_context_retains_raw_not_hypothetical_project_event(self):
        c=dict(kind='SCOPED_TEXT_DISCLOSURE',domain='Commercial',raw_text='The terms of any future funding may also affect the Jupiter Project.')
        self.assertEqual([],narrative_context_issues(c,dict(text=c['raw_text'])))
        self.assertIn('CAUTION_OR_HYPOTHETICAL_TERMS_NOT_PROJECT_EVENT',narrative_context_issues(c,dict(text=c['raw_text']),version='scientific-context-v3'))
        c['raw_text']='The Company cash position supports North Stanmore studies.'
        self.assertIn('COMPANY_CASH_NOT_PROJECT_ATTRIBUTED',narrative_context_issues(c,dict(text=c['raw_text']),version='scientific-context-v3'))
        rows=narrative_candidates('North Stanmore secondary phosphates include churchite and rhabdophane in the pilot concentrate.',1,project_registry(ROOT),parser_version='document-recognition-v2-mineralogy')
        self.assertTrue(any(r['domain']=='Technical' for r in rows))
        self.assertFalse(any(r.get('values') for r in rows))

    def test_scoping_model_and_host_deportment_cannot_enter_dfs_recovery(self):
        policy=json.loads((ROOT/'config/evidence_policy.json').read_text())
        claims=json.loads((ROOT/'data/claims.json').read_text());new=[]
        for p in claims['projects']:
            for o in p['observations']:
                if o.get('source_key') in ('cummins_scoping2023','north_stanmore_quarter202610') and o.get('domain')=='Technical':
                    c=dict(o,raw=o,evidence_id='e',project_id=p['id'],origin='OBSERVATION',reason=None)
                    record=technical_record(c,policy);new.append(record)
                    if o.get('scale')=='SCOPING_MODEL':
                        self.assertEqual('ENGINEERING_MODEL',record['evidence_mode'])
                        self.assertEqual('CASE_MINE_PLAN',record['scope_kind'])
                    if 'deportment' in o['variable']:self.assertNotEqual('BENEFICIATION_RECOVERY',record['process_stage'])
                    reasons=technical_compare(record,policy['criteria']['TC1'])
                    self.assertTrue(reasons)
        self.assertTrue(new)

    def test_selected_claim_contract_excludes_prior_metadata_without_deleting_history(self):
        from au_ree_v2.evidence import claim_evidence_ids
        from au_ree_v2.selection import resolve
        from au_ree_v2.store import connect,canonical,digest,entity
        db=connect(':memory:');sha='a'*64
        source=dict(sha256=sha,key='source',kind='pdf',publication_date='2025-01-01',available_date='2025-01-01')
        db.execute('INSERT INTO sources VALUES(?,?,?,?,?,?,?,?)',(sha,'source','https://example.org/p.pdf','2025-01-01','2025-01-01','p.pdf','pdf','{}'))
        pid=entity(db,'project_registry_v1','example','PROJECT')
        old=dict(variable='study_maturity_ord',value=4,unit='ordinal',basis='DATED_DFS_REAFFIRMED',scope='same design',statement_id='s',effective_date='2025-01-01',source_sha256=sha,locator='p1',source_key='source',pdf_page=1,note='old metadata')
        new=dict(old,note='new checked metadata')
        for o in (old,new):
            db.execute('INSERT INTO observations VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(digest([pid,sha,o]),pid,o['variable'],o['value'],o['unit'],o['basis'],o['scope'],'s',None,o['effective_date'],sha,'p1','AUTO_VALIDATED','[]',canonical(o),'normalization-v1'))
        claims=dict(projects=[dict(id='example',observations=[new])])
        policy=json.loads((ROOT/'config/evidence_policy.json').read_text())
        selected=resolve(db,[source],'2026-11-03',{},[],{},policy,active_claim_ids=claim_evidence_ids(claims))
        self.assertEqual(2,db.execute('SELECT count(*) FROM observations').fetchone()[0])
        self.assertEqual([digest([pid,sha,new])],[r['evidence_id'] for r in selected['inventory']])
        self.assertEqual(4,selected['values'][pid]['D1']['value'])
        db.close()

    def test_primary_additions_verify_source_and_local_review(self):
        claims=json.loads((ROOT/'data/claims.json').read_text());sources={s['key']:s for s in json.loads((ROOT/'data/manifest.json').read_text())['snapshots']}
        cache={};held=[];valid=[]
        for p in claims['projects']:
            for o in p['observations']:
                if o['source_key'] not in ('cummins_scoping2023','north_stanmore_quarter202610'):continue
                validate_pages(ROOT,sources[o['source_key']],o,list(sources.values()),cache)
                (held if normalize(o) else valid).append(o)
        self.assertEqual(2,len(held));self.assertTrue(all(o['domain']=='Resource' and o['review_required'] for o in held))
        self.assertTrue(any(o['variable']=='study_maturity_ord' for o in valid))
        events=[e for e in claims['events'] if e['source_key'] in ('cummins_scoping2023','north_stanmore_quarter202610')]
        self.assertEqual(2,len(events))
        for e in events:
            validate_pages(ROOT,sources[e['source_key']],e,list(sources.values()),cache)
            self.assertEqual('PLANNED_OR_NONBINDING',e['finance_state'])
            self.assertNotEqual('SATISFIED',e['conditions_status'])

if __name__=='__main__':unittest.main()
