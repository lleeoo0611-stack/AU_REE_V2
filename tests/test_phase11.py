"""Phase11 identity RNG, gap execution, event semantics and cutoff boundaries."""
import copy
import csv
import json
import shutil
import subprocess
import unittest
import uuid
from pathlib import Path
from au_ree_v2.acquisition import select_snapshots
from au_ree_v2.cli import research_configuration
from au_ree_v2.discovery import search_tasks, discover
from au_ree_v2.selection import commercial_evidence, source_check
from au_ree_v2.store import filehash

ROOT=Path(__file__).resolve().parents[1]


class Phase11Tests(unittest.TestCase):
    def test_frozen_versions_stay_legacy(self):
        for phase in range(5,11):
            config=research_configuration(ROOT,ROOT/f'results/phase{phase}-2026-11-03/snapshot_lock.json')
            self.assertNotIn('method_version',config['monte_carlo'])
            self.assertNotIn('eligibility_evidence',config)
        self.assertEqual('entity-keyed-rng-v2',research_configuration(ROOT)['monte_carlo']['method_version'])

    def test_gap_tasks_carry_identity_and_prior_evidence(self):
        tasks=search_tasks(ROOT,json.loads((ROOT/'config/discovery.json').read_text()),ROOT/'results/phase10-2026-11-03/evidence_pipeline_diagnostics.csv')
        self.assertTrue(tasks)
        for t in tasks:
            self.assertTrue(t['project_id'].startswith('AU-'))
            self.assertIn('criterion',t);self.assertIn('expected_document_types',t)
            self.assertIn('prior_search_failures',t);self.assertIn('priority_basis',t)
            self.assertNotEqual('VALID_SCORABLE_EVIDENCE',t['gap_state'])
        self.assertEqual(sorted((t['priority'] for t in tasks),reverse=True),[t['priority'] for t in tasks])

    def test_retrieval_cutoff_is_not_publication_cutoff(self):
        source=dict(publication_date='2026-10-30',available_date='2026-11-04')
        self.assertEqual('SOURCE_AFTER_CUTOFF',source_check(source,'2026-10-29',acquired_through='2026-11-04'))
        self.assertIsNone(source_check(source,'2026-11-03',acquired_through='2026-11-04'))
        self.assertEqual('SOURCE_AFTER_CUTOFF',source_check(source,'2026-11-03'))

    def test_retrospective_documents_do_not_backdate_live_gis(self):
        old={s['key'] for s in select_snapshots(ROOT,'2026-11-03')}
        new=select_snapshots(ROOT,'2026-11-03',acquired_through='2026-11-04')
        for s in new:
            # A retrospective search receipt is unscored acquisition metadata.
            if s['key'] not in old:
                if s['kind']=='minedex_resource_batch':
                    # Phase16 adds a dated published ZIP, not a live GIS query.
                    from datetime import datetime
                    from email.utils import parsedate_to_datetime
                    self.assertEqual(s['publication_date'],datetime.strptime(s['source_update'],'%d/%m/%Y').date().isoformat())
                    self.assertLessEqual(s['publication_date'],'2026-11-03')
                    self.assertLessEqual(parsedate_to_datetime(s['last_modified']).date().isoformat(),'2026-11-03')
                else:self.assertIn(s['kind'],('pdf','html','document_extraction','pdf_page_extraction','discovery_receipt','source_documentation'))

    def test_upstream_ledger_bytes_and_unapproved_crosswalk(self):
        p=json.loads((ROOT/'config/eligibility_compatibility.json').read_text())
        for i in p['imports'].values():self.assertEqual(i['sha256'],filehash(ROOT/i['path']))
        self.assertEqual([],p['approved_crosswalk'])
        for k in ('gates','identity'):
            with (ROOT/p['imports'][k]['path']).open() as f:self.assertEqual([],list(csv.DictReader(f)))
        self.assertEqual('2026-10-29',p['upstream_policy']['source_asof'])

    def events(self):
        rows=[]
        with (ROOT/'results/phase10-2026-11-03/resolved_evidence.csv').open() as f:
            for r in csv.DictReader(f):
                if r['variable']!='commercial_event':continue
                raw=json.loads(r['raw']);c=dict(raw,**r);c['raw']=raw
                c['reason']=None if r['reason']=='VALID_RAW_EVIDENCE' else r['reason']
                rows.append(c)
        return rows

    def test_commercial_financing_is_not_close_or_payment(self):
        rows=commercial_evidence(dict(inventory=self.events()))
        self.assertTrue(rows)
        self.assertFalse(any(r['financial_close']=='EVIDENCED' or r['drawdown']=='EVIDENCED' for r in rows))
        self.assertTrue(any(r['instrument_type']=='JV_EARN_IN' for r in rows))
        self.assertTrue(any(r['instrument_type']=='CONVERTIBLE_NOTE' for r in rows))
        self.assertTrue(any(r['instrument_type']=='CREDIT_APPROVAL' for r in rows))
        self.assertTrue(any(r['event_type']=='OFFTAKE' for r in rows))

    def test_latest_expired_instrument_does_not_resurrect(self):
        base=self.events()[0];base.update(facility_id='same',effective_date='2025-01-01',attribution='PROJECT',event_type='FINANCING',reason=None)
        latest=copy.deepcopy(base);latest.update(effective_date='2026-01-01',reason='EVENT_EXPIRED')
        rows=commercial_evidence(dict(inventory=[base,latest]))
        self.assertFalse(any(r['qualified_project_event'] for r in rows))

    def test_company_and_historical_payment_are_not_project_draw(self):
        c=self.events()[0];c.update(attribution='COMPANY',finance_state='DRAWN',conditions_status='SATISFIED')
        r=commercial_evidence(dict(inventory=[c]))[0]
        self.assertEqual(0,r['qualified_project_event']);self.assertNotEqual('EVIDENCED',r['drawdown'])

    def test_identity_audit_ignores_unselected_claim_metadata(self):
        from au_ree_v2.eligibility import identity_fact
        a=dict(entity_id='p',native_namespace='official',native_id='1',kind='PROJECT',name='name',state='WA',longitude=120,latitude=-30,source_sha='source',raw='old historical extraction')
        b=dict(a,raw='future observation and revised extraction metadata')
        self.assertEqual(identity_fact(a),identity_fact(b))
        self.assertNotIn('raw',identity_fact(a))

    def test_glossary_is_not_development_event(self):
        from au_ree_v2.pdf_extract import narrative_context_issues
        c=dict(kind='SCOPED_TEXT_DISCLOSURE')
        self.assertEqual(['SOURCE_GLOSSARY_NOT_PROJECT_DISCLOSURE'],narrative_context_issues(c,dict(text='GLOSSARY OF ABBREVIATIONS AND DEFINED TERMS DFS Definitive Feasibility Study Donald')))
        self.assertEqual([],narrative_context_issues(c,dict(text='Donald Project Definitive Feasibility Study completed')))

    def test_r_panel_order_and_seed_exact_replay(self):
        exe=shutil.which('Rscript') or ('C:/Program Files/R/R-4.5.2/bin/Rscript.exe' if Path('C:/Program Files/R/R-4.5.2/bin/Rscript.exe').exists() else None)
        if not exe:self.skipTest('R unavailable')
        work=ROOT/'work/tests'/('phase11-'+uuid.uuid4().hex);work.mkdir(parents=True)
        original=ROOT/'results/phase10-2026-11-03/issuer_resource_composition'
        folders=[]
        for run in range(3):
            folder=work/str(run);folder.mkdir();folders.append(folder)
            for name in ('matrix.csv','criteria.csv','weights.csv'):
                with (original/name).open() as f:reader=csv.DictReader(f);fields=reader.fieldnames;rows=list(reader)
                if run==1:rows.reverse();fields=list(reversed(fields))
                with (folder/name).open('w',newline='') as f:w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
            p=subprocess.run([exe,str(ROOT/'R/run_mcda.R'),str(folder),'42','30','.2','30','entity-keyed-rng-v2'],capture_output=True,text=True)
            self.assertEqual(0,p.returncode,p.stderr)
        for f in folders[0].glob('*.csv'):
            if f.name in ('matrix.csv','criteria.csv','weights.csv'):continue
            self.assertEqual(f.read_bytes(),(folders[1]/f.name).read_bytes(),f.name)
            self.assertEqual(f.read_bytes(),(folders[2]/f.name).read_bytes(),f.name)


class ReplayReferenceTests(unittest.TestCase):
    def fixture(self):
        root=ROOT/'work/tests'/('reference-'+uuid.uuid4().hex)
        for name in ('a','b'):
            folder=root/name;(folder/'panel').mkdir(parents=True)
            (folder/'panel/ranking.csv').write_text('scenario,project_id,saw,saw_rank\ns,p,0.5,1\n')
            (folder/'panel/weight_uncertainty.csv').write_text('scenario,project_id,frequency_first\ns,p,0.5\n')
            for file in ('technical_comparability.csv','commercial_project_coverage.csv','aim_c_technical_features.csv','formal_gate_compatibility.csv'):
                (folder/file).write_text('project_id\np\n')
        return root

    def check(self,root,reference):
        import sys
        return subprocess.run([sys.executable,str(ROOT/'tools/check_phase11.py'),str(root/'a'),str(root/'b'),*(['--reference'] if reference else [])],capture_output=True,text=True)

    def test_reference_records_float_drift_without_modifying_inputs(self):
        root=self.fixture();file=root/'b/panel/ranking.csv'
        file.write_text(file.read_text().replace('0.5,1','0.5000000000000001,1'));before=file.read_bytes()
        self.assertNotEqual(0,self.check(root,False).returncode)
        p=self.check(root,True);self.assertEqual(0,p.returncode,p.stderr)
        report=json.loads(p.stdout);self.assertEqual(1,len(report['platform_differences']))
        self.assertEqual(before,file.read_bytes())

    def test_reference_rejects_rank_and_even_tiny_frequency_changes(self):
        root=self.fixture();file=root/'b/panel/weight_uncertainty.csv'
        file.write_text(file.read_text().replace('0.5','0.5000000000000001'))
        self.assertNotEqual(0,self.check(root,True).returncode)
        file.write_text((root/'a/panel/weight_uncertainty.csv').read_text())
        rank=root/'b/panel/ranking.csv';rank.write_text(rank.read_text().replace('0.5,1','0.5,2'))
        self.assertNotEqual(0,self.check(root,True).returncode)
