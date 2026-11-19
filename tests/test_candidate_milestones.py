"""Research candidate classifications and project-page attribution regressions."""
import copy
import json
import unittest
from pathlib import Path

from au_ree_v2.census import summary_settings, summary_stage_fields
from au_ree_v2.milestones import _comparison, _review, evaluate_event
from au_ree_v2.pdf_extract import summary_review_hit
from au_ree_v2.tabular import read_csv


ROOT = Path(__file__).resolve().parents[1]
RELEASE = ROOT/'results/ree-project-census/plan620-20261119'
AUSTRADE = 'af0a8ff9a1b194a45f16dc56dd3b71c04c5f426f15dd23d0511de087f9ec8ac5'
AVONBANK = 'AU-329908ab8d4c1d1d3e03'
COPI = 'AU-fe65cb1bd28eacb7a67f'


class MilestoneTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.policy = json.loads((ROOT/'config/candidate_milestones.json').read_text(encoding='utf8'))
        cls.policy['by_type'] = {r['event_type']:r for r in cls.policy['stages']}
        cls.policy['order'] = [r['code'] for r in cls.policy['stages']]
        cls.bindings = json.loads((ROOT/'data/candidate_milestone_evidence.json').read_text(encoding='utf8'))['events']
        cls.rules, cls.decisions = summary_settings(ROOT)

    def test_three_historical_cases_and_precision(self):
        rows = {r['專案ID']:r for r in read_csv(RELEASE/'REE project census.csv')}
        for pid, precision in [(AVONBANK,'YEAR'), (COPI,'MONTH'), ('AU-fb4e914f86102baa414a','UNKNOWN')]:
            with self.subTest(pid=pid):
                b = next(b for b in self.bindings if b['project_id']==pid)
                event = self.review(b)
                self.assertEqual(rows[pid]['開發階段代碼'], 'B2')
                self.assertEqual((event['candidate_code'], event['event_date_precision']), ('B3',precision))

    def review(self, b, **kwargs):
        source = dict(url='test',publication_date='2026-03-01',publication_date_precision='month')
        page = lambda sha,number: ' '.join([b['project_marker'], *b['markers']]).casefold()
        args = dict(source=source, page_text=page, bundle=None, observations=[], cutoff='2026-11-13', policy=self.policy)
        return _review(b, **dict(args,**kwargs))

    def test_unverified_sources_future_partial_dates_and_wrong_page_hold(self):
        b = self.bindings[0]
        self.assertEqual(self.review(b,source=None)['decision'], 'REVIEW')
        self.assertEqual(self.review(b,cutoff='2026-03-04')['decision'], 'REVIEW')
        e = self.review(b,page_text=lambda sha,page:'different project')
        self.assertEqual((e['decision'],e['reason']), ('REVIEW','PROJECT_OR_EVENT_PAGE_MARKER_UNVERIFIED'))

    def test_same_estimate_and_first_release_are_separate(self):
        b = next(b for b in self.bindings if b.get('reporting_standard') and not b.get('first_mre_publication_date'))
        sha = b['source_sha256']
        bundle = dict(source_sha256=sha,scope='ore',statement_id='MRE2',effective_date='2022')
        obs = dict(variable='ore_mt',scope='ore',statement_id='MRE2',source_sha=sha,effective_date='2022',obs_id='input')
        good = self.review(b,bundle=bundle,observations=[obs])
        self.assertEqual((good['candidate_code'], good['observation_ids']), ('A3','["input"]'))
        self.assertFalse(good.get('first_mre_publication_date'))
        self.assertEqual(self.review(b,bundle=bundle,observations=[dict(obs,scope='reserve')])['decision'],'REVIEW')

    def test_evidence_required_at_each_boundary(self):
        cases = [('SCOPING','COMPLETED','PROJECT','B1'), ('PFS','IN_PROGRESS','PROJECT',''),
                 ('PFS','NAMED_ONLY','PROJECT',''), ('FS','COMPLETED','STUDY_SCENARIO','B3'),
                 ('FID','PLANNED','PROJECT',''), ('FID','DECIDED','PROJECT','C1'),
                 ('MAIN_CONSTRUCTION','SITE_PREPARATION','PROJECT',''), ('MAIN_CONSTRUCTION','STARTED','PROJECT','C2'),
                 ('MECHANICAL_COMPLETION','COMPLETED','COMMERCIAL_FACILITY','C3'),
                 ('COMMISSIONING','STARTED','PILOT',''), ('COMMISSIONING','STARTED','COMMERCIAL_FACILITY','D1'),
                 ('RAMP_UP','FIRST_PRODUCT','PROJECT',''), ('RAMP_UP','IN_PROGRESS','PROJECT',''),
                 ('DESIGN_ACHIEVEMENT','SUSTAINED','PROJECT',''), ('SYSTEMATIC_DELINEATION','OBSERVED','PROJECT','')]
        for kind, status, role, code in cases:
            with self.subTest(kind=kind,status=status,role=role):
                b = dict(event_type=kind,status=status,scope_role=role,markers=['nameplate 2020','revised 2023'])
                self.assertEqual(evaluate_event(b,self.policy)[0],code)

    def test_status_and_future_study_do_not_erase_confirmed_stage(self):
        baseline = self.review(self.bindings[0])
        evidence = [dict(baseline,event_type='SCOPING',candidate_code='B1'),
                    dict(baseline,event_type='PFS',candidate_code='',decision='NEXT_WORK'),
                    dict(baseline,event_type='OPERATING_STATUS',status='SUSPENDED',candidate_code='',
                         decision='STATUS_ONLY',publication_date='2025-10-01'),
                    dict(baseline,event_type='OPERATING_STATUS',status='RESTART_REPORTED',candidate_code='',
                         decision='STATUS_ONLY',publication_date='2026-09-01')]
        c = _comparison({'專案ID':AVONBANK,'專案名稱':'Avonbank','開發階段代碼':'B1'},
                        evidence,None,[],'2026-11-13',self.policy)
        self.assertEqual((c['highest_confirmed_candidate'], c['ongoing_work_as_reported'],
                          c['latest_documented_operating_status']),('B1','PFS','RESTART_REPORTED'))

    def hit(self, sentence, page=46, rules=None, project=AVONBANK):
        row = {'專案ID':project, '專案名稱':'Avonbank Mineral Sands Project' if project==AVONBANK else 'Copi Mineral Sands Project'}
        return summary_review_hit(dict(sentence=sentence,physical_page=page,keyword='DFS'),row,
                                  dict(sha256=AUSTRADE,url=''),rules or self.rules)

    def test_page_bound_short_names_and_unattributed_positive(self):
        avon = self.hit('Avonbank Project Definitive Feasibility Study completed in 2021.')
        copi = self.hit('The Copi DFS completed in January 2024.',47,project=COPI)
        self.assertEqual((avon['point2'],copi['point2']),('PASS','PASS'))
        self.assertNotEqual(self.hit('Avonbank DFS completed in 2021.',47)['point2'],'PASS')
        self.assertEqual(self.hit('The DFS was completed in January 2024.')['outcome'],'UNCLEAR')
        other = self.hit('The Copi Mineral Sands Project DFS was completed in January 2024.')
        self.assertEqual((other['point2'],other['reason2']), ('FAIL','OTHER_NAMED_PROJECT'))
        rules = copy.copy(self.rules)
        rules['aliases.projects'] = [dict(project_id=p,aliases=[dict(alias='Shared Project')]) for p in [AVONBANK,COPI]]
        self.assertEqual(self.hit('Shared Project DFS completed.',rules=rules)['reason2'],'AMBIGUOUS_ALIAS')

    def test_missing_source_inventory_does_not_support_an_early_stage(self):
        row = {'專案ID':AVONBANK,'礦石蘊藏量_Mt':'','開發階段':'','開發階段代碼':''}
        writes, audit = [], []
        summary_stage_fields(row,{}, {}, {}, self.rules,self.decisions,lambda *args:writes.append(args),audit,{})
        self.assertFalse(writes)
        self.assertEqual(audit[0]['reason'],'STAGE_SOURCE_INVENTORY_UNVERIFIED')
        audit.clear()
        entry = dict(source_sha256='a'*64,url='https://example.org/file.pdf')
        summary_stage_fields(row,{}, {}, {}, self.rules,self.decisions,lambda *args:writes.append(args),audit,{},inventory=[entry])
        self.assertFalse(writes)
        self.assertEqual(audit[0]['reason'],'SOURCE_NOT_ACQUIRED')
