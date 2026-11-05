"""Phase19 source-bound disclosure coding, not a performance classifier."""
import copy
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from au_ree_v2.technical import (DISCLOSURE_FACETS,DISCLOSURE_VERSION,
    assess_disclosure,disclosure_score,apply_disclosure,run_disclosure)
from au_ree_v2.analysis import interval_mcda,prepare_disclosure_analysis
from au_ree_v2.store import filehash,connect
from au_ree_v2.cli import research_configuration

ROOT=Path(__file__).resolve().parents[1]

class Disclosure(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir=ROOT/'work')
        self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.path=self.root/'source.html'
        self.text='No experiments have been performed because the ore-host mineral phases have not yet been characterised. The proposed feed is sampled ore from Zone A. The intended endpoint is mixed carbonate. Sampling and preparation use quarter core, composited by geological domain. No project-wide extrapolation is justified because the samples only cover Zone A. '
        self.path.write_text('<p>'+self.text+'</p>',encoding='utf8')
        self.source=dict(key='s',kind='html',publication_date='2025-01-01',available_date='2025-01-02',
            path='source.html',sha256=filehash(self.path),url='https://example.test/original')
        cite=dict(source_key='s',page=1,quote=self.text.strip())
        self.group=dict(project_id='A',name='A',scope='Zone A only',documents=[dict(source_key='s',
            scope_reason='Explicit Zone A experimental plan',scope_evidence=cite)],search_complete=True,
            review_complete_items=list(DISCLOSURE_FACETS),stop_reason='Fixed source scope complete',items={})
        for code,facets in DISCLOSURE_FACETS.items():
            self.group['items'][code]=dict(status='UNVERIFIABLE',reason='Not assessed')
        self.review=dict(version=DISCLOSURE_VERSION,cutoff='2026-11-05',sources={'s':self.source},
            search_protocol='Test fixed original scope',groups=[self.group])
    def evaluate(self):return assess_disclosure(self.root,self.review,[self.source],'2026-11-05')
    def item(self,state='EXPLICIT_UNKNOWN'):
        return dict(status=state,reason='No test, explicit mineral-host limitation and experimental boundary.',
            facets={f:dict(interpretation='Scope and the lack of testing are explicitly disclosed in the original.',
                evidence=[dict(source_key='s',page=1,quote=self.text.strip())],
                explicit_unknown=state=='EXPLICIT_UNKNOWN',
                unknown_reason='Host mineral phases remain uncharacterised, so these planned tests are not performed.' if state=='EXPLICIT_UNKNOWN' else '') for f in DISCLOSURE_FACETS['TD6']})
    def test_fixed_denominator_and_missing_not_midpoint(self):
        items={c:dict(status='UNVERIFIABLE') for c in DISCLOSURE_FACETS}
        items['TD1']['status']='DISCLOSED';items['TD2']['status']='INSUFFICIENT'
        s=disclosure_score(items)
        self.assertAlmostEqual(100/7,s['confirmed_score']);self.assertAlmostEqual(600/7,s['score_upper'])
        self.assertEqual(5,s['unknown_items']);self.assertIsNone(s['score']);self.assertEqual(7,s['denominator'])
        with self.assertRaises(ValueError):disclosure_score({'TD1':items['TD1']})
    def test_no_experiment_but_explicit_limit_can_score(self):
        self.group['items']['TD6']=self.item();r=self.evaluate()
        self.assertEqual(1,next(x for x in r['items'] if x['item']=='TD6')['value'])
        self.assertEqual('EXPLICIT_UNKNOWN',next(x for x in r['items'] if x['item']=='TD6')['status'])
    def test_explicit_unknown_requires_specific_reason(self):
        self.group['items']['TD6']=self.item();self.group['items']['TD6']['facets']['scale']['unknown_reason']='pending'
        self.assertIsNone(next(x for x in self.evaluate()['items'] if x['item']=='TD6')['value'])
    def test_all_three_input_categories_required(self):
        self.group['items']['TD4']=dict(status='DISCLOSED',reason='Only acid provided',facets={
            'reagents':dict(interpretation='Detailed acid only, not water or energy.',evidence=[dict(source_key='s',page=1,quote=self.text)])})
        row=next(x for x in self.evaluate()['items'] if x['item']=='TD4')
        self.assertIsNone(row['value']);self.assertIn('MINIMUM_FACETS_NOT_MET',row['validation_issues'])
    def test_good_result_vague_disclosure_scores_zero_only_after_review(self):
        self.group['items']['TD3']=dict(status='INSUFFICIENT',reason='Excellent recovery lacks feed,product and numeric basis.',
            missing_facets=['feed','endpoint','data_basis'],evidence=[dict(source_key='s',page=1,quote=self.text)])
        self.assertEqual(0,next(x for x in self.evaluate()['items'] if x['item']=='TD3')['value'])
        self.group['search_complete']=False
        self.assertIsNone(next(x for x in self.evaluate()['items'] if x['item']=='TD3')['value'])
    def test_hash_quote_date_failures_are_unknown(self):
        self.group['items']['TD6']=self.item()
        for mutation in ('quote','hash','date'):
            original=copy.deepcopy(self.review);source=copy.deepcopy(self.source)
            if mutation=='quote':self.group['documents'][0]['scope_evidence']['quote']='This is not present in the source original.'
            elif mutation=='hash':self.source['sha256']='a'*64
            else:self.source['publication_date']='2027-01-01'
            self.assertTrue(all(x['value'] is None for x in self.evaluate()['items']))
            self.review=original;self.group=self.review['groups'][0];self.source=source
    def test_other_project_document_cannot_support_facet(self):
        self.group['items']['TD6']=self.item()
        self.group['items']['TD6']['facets']['scale']['evidence'][0]['source_key']='other'
        self.assertIsNone(next(x for x in self.evaluate()['items'] if x['item']=='TD6')['value'])
    def test_archived_public_html_does_not_invent_publication_date(self):
        self.source.pop('publication_date');self.source['acquired_at']='2025-01-02T00:00:00Z'
        self.group['items']['TD6']=self.item();r=self.evaluate()
        item=next(x for x in r['items'] if x['item']=='TD6')
        self.assertEqual(1,item['value']);cite=item['evidence']['scale'][0]
        self.assertIsNone(cite['publication_date']);self.assertEqual('2025-01-02',cite['available_date'])
        self.assertIn('PUBLIC_HTML_ARCHIVED',cite['date_basis'])
    def test_cutoff_version_and_duplicate_ids_fail_closed(self):
        with self.assertRaises(ValueError):assess_disclosure(self.root,self.review,[self.source],'2026-11-04')
        self.review['groups'].append(copy.deepcopy(self.group))
        with self.assertRaises(ValueError):self.evaluate()
    def test_new_T1_never_retains_recovery_score(self):
        selection={'values':{'A':{'T1':{'value':99},'T_RECOVERY_LEGACY':{'value':99}}}}
        r=self.evaluate();apply_disclosure(selection,r)
        self.assertNotIn('T1',selection['values']['A']);self.assertEqual(99,selection['values']['A']['T_RECOVERY_LEGACY']['value'])
    def test_ties_unknown_envelopes_and_order_independence(self):
        m=[[(3/7,3/7)],[(3/7,3/7)],[(0,1)]]
        a=interval_mcda(m,[1]);b=interval_mcda(m[::-1],[1])
        for method in a:
            self.assertEqual(a[method][0],a[method][1]);self.assertEqual(a[method],b[method][::-1])
            self.assertLessEqual(a[method][0]['rank_best'],a[method][0]['rank_worst'])
    def test_weights_are_fixed_across_groups_and_zero_domain_excluded(self):
        config=research_configuration(ROOT);baseline=dict(version='test',scores={})
        scores=[dict(project_id=x,project_name=x,scope='Zone',**disclosure_score({c:dict(status='UNVERIFIABLE') for c in DISCLOSURE_FACETS})) for x in ['A','B']]
        result=dict(scores=scores)
        prepare_disclosure_analysis(result,baseline,config,self.root)
        import csv
        rows=list(csv.DictReader((self.root/'disclosure_weights.csv').open()))
        for scenario,dw in config['scenarios'].items():
            group=[x for x in rows if x['scenario']==scenario and x['variant']=='baseline']
            self.assertAlmostEqual(1,sum(float(x['weight']) for x in group))
            self.assertAlmostEqual(dw['Technical'],float(next(x['weight'] for x in group if x['criterion']=='T1')))
            self.assertEqual(0,float(next(x['weight'] for x in rows if x['scenario']==scenario and x['variant']=='without_T' and x['criterion']=='T1')))
        # Frozen JSON sorts object keys; presentation/weights must not change.
        other=self.root/'sorted';other.mkdir()
        prepare_disclosure_analysis(result,baseline,json.loads(json.dumps(config,sort_keys=True)),other)
        for p in self.root.rglob('*.csv'):
            if other in p.parents:continue
            self.assertEqual(p.read_bytes(),(other/p.relative_to(self.root)).read_bytes(),str(p))

class ActualDisclosure(unittest.TestCase):
    def test_actual_31_source_quotes_and_coding_integrate(self):
        config=research_configuration(ROOT);review=json.loads((ROOT/'data/technical_disclosure_v1.json').read_text())
        r=assess_disclosure(ROOT,review,list(review['sources'].values()),review['cutoff'])
        self.assertEqual(31,len(r['scores']));self.assertEqual(217,len(r['items']))
        self.assertFalse(any(x['validation_issues'] for x in r['items']))
        selection={'values':{}};apply_disclosure(selection,r)
        ids={x['assessment_id'] for x in r['items']}
        self.assertEqual(217,len(ids))
        self.assertTrue(all(set(x['T1']['evidence_ids'])<=ids for x in selection['values'].values()))
        # This source honestly reports an over-specification product; it is a
        # transparent disclosure, not evidence of better technical performance.
        cow=next(x for x in r['items'] if x['project_id']=='AU-4ec1fb08563b42352d29' and x['item']=='TD5')
        self.assertEqual(1,cow['value']);self.assertIn('8.4%',json.dumps(cow['evidence']))
        # Different/native nested groups retain unknowns rather than borrowing.
        for pid in ['AU-47d12ebe6b66df8e5936','AU-574465211976ec57b1ef','AU-d0ce731e1d8198ffaf58']:
            self.assertEqual(7,next(x for x in r['scores'] if x['project_id']==pid)['unknown_items'])
    def test_same_store_derived_only_idempotent_and_NULL_preserved(self):
        config=research_configuration(ROOT)
        with tempfile.TemporaryDirectory(dir=ROOT/'work') as tmp:
            db=connect(Path(tmp)/'test.sqlite');review=json.loads((ROOT/'data/technical_disclosure_v1.json').read_text())
            for g in review['groups']:db.execute('INSERT INTO entities VALUES(?,?,?,?)',(g['project_id'],'PROJECT','test',g['project_id']))
            db.execute('INSERT INTO runs VALUES(?,?,?,?,?,?,?,?)',('test','now',review['cutoff'],'test','sha','sha','RUNNING',None))
            a=run_disclosure(ROOT,config,review['cutoff'],Path(tmp)/'out',db,'test')
            first=[tuple(x) for x in db.execute('select * from derived order by entity_id,variable')]
            b=run_disclosure(ROOT,config,review['cutoff'],Path(tmp)/'out',db,'test')
            self.assertEqual(first,[tuple(x) for x in db.execute('select * from derived order by entity_id,variable')])
            self.assertEqual(0,db.execute('select count(*) from observations').fetchone()[0])
            self.assertEqual(31*8,len(first));self.assertTrue(any(x[3] is None for x in first))
            self.assertEqual(a[2],b[2]);db.close()

if __name__=='__main__':unittest.main()
