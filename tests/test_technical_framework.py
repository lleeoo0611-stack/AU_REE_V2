"""Scientific boundaries for the shared Technical framework, not scoring gold."""
import copy
import csv
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from au_ree_v2.analysis import prepare_technical_panel, write_csv, interval_mcda
from au_ree_v2.technical import analyze_profiles, unified_observations, framework_fields, screening_utility, analyze_jorc_screening
from test_phase16_remediation import observation, POLICY, PROFILE, ROOT


class TechnicalFramework(unittest.TestCase):
    def view(self,selection,profile=PROFILE):
        rows=unified_observations(selection,profile)
        return [dict(r,**framework_fields(r,profile)) for r in rows]

    def selection(self, *items):
        return dict(inventory=list(items), policy=POLICY,
                    projects={r['project_id'] for r in items}, mapping={})

    def test_percentage_or_feed_assay_does_not_become_performance(self):
        values=[observation(variable='head_treo_min_ppm', unit='ppm', raw={'raw_text':'95% recovery claimed elsewhere'}),
                observation(variable='reported_tima_nd_secondary_phosphate_deportment_pct', role='MINERAL_HOST_DEPORTMENT'),
                observation(variable='hcl_concentration_pct')]
        for row in self.view(self.selection(*values)):
            self.assertEqual([],row['technical_axes'])
            self.assertEqual('CONTEXT_ONLY',row['technical_use'])

    def test_three_lines_share_axes_without_changing_values_or_eligibility(self):
        values=[observation(variable='whole_ore_concentrate_recovery_pct'),
                observation(variable='magnet_extraction_to_leach_pct',evidence_id='leach'),
                observation(variable='resource_to_final_mreo_recovery_pct',evidence_id='final'),
                observation(variable='acid_32pct_hcl_kg_per_t_feed',unit='kg/t feed',evidence_id='acid'),
                observation(variable='product_impurity_pct',evidence_id='impurity')]
        selection=self.selection(*values)
        legacy=copy.deepcopy(PROFILE);legacy.pop('framework')
        old=self.view(selection,legacy);new=self.view(selection)
        for before,after in zip(old,new):
            self.assertEqual(before,{k:v for k,v in after.items() if not k.startswith('technical_')})
        axes={r['variable']:r['technical_axes'] for r in new}
        self.assertEqual([['T-R']]*3,[axes[c['variable']] for c in values[:3]])
        self.assertEqual(['T-I'],axes[values[3]['variable']])
        self.assertEqual(['T-P'],axes[values[4]['variable']])

    def test_acid_text_never_counts_a_recovery_number_as_input_intensity(self):
        r=observation(variable='whole_ore_concentrate_recovery_pct',raw={'raw_text':'Acid consumption was measured on the selected composites.'})
        row=self.view(self.selection(r))[0]
        self.assertTrue(row['interpretations'])
        self.assertEqual(['T-R'],row['technical_axes'])
        text=dict(r,value=None,variable='reported_technical_disclosure',evidence_id='claim')
        row=self.view(self.selection(text))[0]
        self.assertEqual(['T-I'],row['technical_axes'])
        self.assertEqual('SOURCE_SCOPED_DESCRIPTION',row['technical_use'])

    def test_typed_input_uses_source_context_not_legacy_performance_taxonomy(self):
        r=observation(variable='reported_technical_acid_requirement',role='UNCLASSIFIED_PARAMETER',value=24,unit='kg/t ore',basis='SOURCE_ACID_PER_TONNE_ORE',raw={'quantity_role':'REAGENT_INTENSITY'})
        row=self.view(self.selection(r))[0]
        self.assertFalse(row['numeric_profile_eligible'])
        self.assertEqual(['T-I'],row['technical_axes'])
        self.assertEqual('SOURCE_SCOPED_NUMERIC',row['technical_use'])
        r['feed']=None
        self.assertEqual('NUMERIC_CONTEXT_INCOMPLETE',self.view(self.selection(r))[0]['technical_use'])

    def test_conflicts_and_unknowns_are_not_points_or_missing_axis_reweights(self):
        values=[observation(variable='whole_ore_concentrate_recovery_pct'),
                observation(variable='whole_ore_concentrate_recovery_pct',value=81,evidence_id='conflict')]
        selection=self.selection(*values);selection['projects'].add('no-evidence')
        observations=self.view(selection)
        self.assertTrue(all(r['technical_use']=='CONFLICT' for r in observations))
        with tempfile.TemporaryDirectory(dir=ROOT/'work') as tmp:
            with patch('au_ree_v2.technical.unified_observations',side_effect=AssertionError('must reuse shared view')):
                result=analyze_profiles(selection,PROFILE,Path(tmp),set(),observations=observations)
            self.assertFalse(result['framework']['project_scores_adopted'])
            with (Path(tmp)/'technical_framework_profiles.csv').open(newline='') as stream:
                profiles=list(csv.DictReader(stream))
            self.assertEqual(6,len(profiles))
            self.assertTrue(all(r['project_score']=='' for r in profiles))
            self.assertTrue(all(r['status']=='UNKNOWN' for r in profiles if r['project_id']=='no-evidence'))

    def panel(self,change=None,policy=POLICY):
        rec=observation(variable='whole_ore_concentrate_recovery_pct',value=84,basis='TREO_INCLUDING_Y',feed='WHOLE_ORE',endpoint='MINERAL_CONCENTRATE',scale='DFS_MODEL',origin='STUDY_PARAMETER')
        grade=dict(rec,variable='concentrate_treo_grade_pct',value=25,evidence_id='grade',raw={})
        if change:change(grade)
        selection=self.selection(rec,grade);selection['policy']=policy
        shared=unified_observations(selection,policy['technical_profile'])
        with tempfile.TemporaryDirectory(dir=ROOT/'work') as tmp:
            out=Path(tmp)
            write_csv(out/'reference/matrix.csv',[dict(project_id='p',project_name='p',D1=.6)],['project_id','project_name','D1'])
            with patch('au_ree_v2.technical.unified_observations',side_effect=AssertionError('must reuse shared view')):
                result=prepare_technical_panel(selection,{'panels':{'reference':1}},{'evidence_resolution':policy},out,observations=shared)
            with (out/'technical_process_concentrate_fixed/weights.csv').open() as stream:
                weights=list(csv.DictReader(stream))
        return result,weights

    def test_same_case_id_cannot_join_different_criterion_schemes(self):
        for change in [lambda r:r.update(scope='other ore'),
                       lambda r:r.update(effective_date='2026-01-01'),
                       lambda r:r['raw'].update(scenario='alternative'),
                       lambda r:r['raw'].update(date_role='TEST_DATE')]:
            result,_=self.panel(change)
            self.assertEqual(0,result['n'])
            self.assertIn('INCONSISTENT_CROSS_CRITERION_CASE_CONTEXT',result['cases'][0]['reasons'])

    def test_framework_does_not_change_existing_matrix_weights(self):
        current,weights=self.panel()
        policy=copy.deepcopy(POLICY);policy['technical_profile'].pop('framework')
        for criterion in policy['technical_profile']['numeric_model']['criteria'].values():criterion.pop('framework_axis')
        legacy,oldweights=self.panel(policy=policy)
        self.assertEqual(legacy,current);self.assertEqual(oldweights,weights)
        self.assertEqual(10,len({r['scenario'] for r in weights}))

    def test_bad_axis_configuration_cannot_admit_a_metric(self):
        policy=copy.deepcopy(POLICY)
        policy['technical_profile']['numeric_model']['criteria']['TPR']['framework_axis']='T-I'
        result,_=self.panel(policy=policy)
        self.assertEqual(0,result['n'])

    def test_serializing_configuration_cannot_swap_recovery_and_grade_weights(self):
        _,weights=self.panel()
        reordered=json.loads(json.dumps(POLICY,sort_keys=True))
        _,other=self.panel(policy=reordered)
        self.assertEqual(weights,other)
        recovery=next(r for r in other if r['scenario']=='technical_0.25_split_1' and r['criterion']=='TPR')
        self.assertAlmostEqual(.2,float(recovery['weight']))


class IntervalScreening(unittest.TestCase):
    def test_unknown_is_retained_and_ties_have_no_arbitrary_order(self):
        result=interval_mcda([[(0,1)],[(.8,.8)],[(.8,.8)]],[1])
        for method,rows in result.items():
            self.assertEqual((1,3),(rows[0]['rank_best'],rows[0]['rank_worst']))
            self.assertEqual(rows[1],rows[2])
            self.assertEqual((1,3),(rows[1]['rank_best'],rows[1]['rank_worst']))

    def test_dominance_and_missing_criterion_do_not_reweight(self):
        result=interval_mcda([[(.9,.9),(0,1)],[(.1,.1),(0,1)]],[.9,.1])
        for rows in result.values():
            self.assertEqual(1,rows[0]['rank_worst']);self.assertEqual(2,rows[1]['rank_best'])
        self.assertAlmostEqual(.81,result['SAW'][0]['score_lower'])
        self.assertAlmostEqual(.91,result['SAW'][0]['score_upper'])

    def test_interval_bounds_contain_exhaustive_corner_scores_and_ranks(self):
        import itertools
        matrix=[[(.2,.7),(.4,.9)],[(.5,.8),(.1,.6)],[(.3,.4),(.7,.8)]]
        result=interval_mcda(matrix,[.65,.35])
        for corner in itertools.product((0,1),repeat=6):
            points=[[(matrix[i][k][corner[i*2+k]],)*2 for k in range(2)] for i in range(3)]
            for method,rr in interval_mcda(points,[.65,.35]).items():
                for i,r in enumerate(rr):
                    bound=result[method][i]
                    self.assertLessEqual(bound['score_lower'],r['score_lower']+1e-12)
                    self.assertGreaterEqual(bound['score_upper']+1e-12,r['score_upper'])
                    self.assertLessEqual(bound['rank_best'],r['rank_best'])
                    self.assertGreaterEqual(bound['rank_worst'],r['rank_worst'])

    def test_invalid_bounds_and_weights_fail_loudly(self):
        for matrix,w in [([[(1,0)]],[1]),([[(0,float('nan'))]],[1]),([[(0,1)]],[-1]),([[(0,1)]],[0])]:
            with self.assertRaises(ValueError):interval_mcda(matrix,w)

    def test_relaxed_context_does_not_remove_a_valid_recovery(self):
        panel=PROFILE['jorc_screening']['panels']['concentrate_treo']
        row=dict(quantity='BENEFICIATION_RECOVERY',process_stage='BENEFICIATION_RECOVERY',
                 value=84,unit='%',basis='TREO_INCLUDING_Y',endpoint='MINERAL_CONCENTRATE',
                 technical_axes=['T-R'],supports_technical_interpretation=True,
                 feed=None,study_date=None,statistic=None,scale=None)
        self.assertEqual(.84,screening_utility(row,panel,'T-R')[0])
        for key,value in [('basis','THM'),('endpoint','LEACH_SOLUTION'),('unit','kg/t')]:
            self.assertIsNone(screening_utility(dict(row,**{key:value}),panel,'T-R')[0])
        self.assertIsNone(screening_utility(dict(row,evidence_reason='INVALID'),panel,'T-R')[0])

    def test_maturity_attributes_cannot_change_performance(self):
        policy=copy.deepcopy(PROFILE)
        policy['jorc_screening']['weight_grid_steps']=1
        policy['jorc_screening']['perturbation_percentage_points']=[0]
        policy['jorc_screening']['panels']={'concentrate_treo':policy['jorc_screening']['panels']['concentrate_treo']}
        selection=dict(projects={'a','b'},mapping={})
        row=dict(project_id='a',quantity='BENEFICIATION_RECOVERY',value=84,unit='%',
                 basis='TREO_INCLUDING_Y',endpoint='MINERAL_CONCENTRATE',technical_axes=['T-R'],
                 supports_technical_interpretation=True,case_id='case',analytical_identity='obs',
                 evidence_ids=['e'],source_sha256='sha',sample_population=None,project_extrapolation=False)
        outputs=[]
        with tempfile.TemporaryDirectory(dir=ROOT/'work') as tmp:
            for i,scale in enumerate((None,'DFS_MODEL')):
                out=Path(tmp)/str(i);out.mkdir()
                analyze_jorc_screening(selection,policy,[dict(row,scale=scale)],out)
                outputs.append((out/'technical_interval_ranking.csv').read_bytes())
                with (out/'technical_screening_matrix.csv').open() as stream:
                    cells=list(csv.DictReader(stream))
                self.assertEqual({'a','b'},{r['project_id'] for r in cells})
                self.assertTrue(all(r['utility_lower']=='0.0' and r['utility_upper']=='1.0' for r in cells if r['transfer']=='PROJECT_TRANSFER_STRESS'))
                self.assertTrue(all(r['utility_lower']=='0.0' and r['utility_upper']=='1.0' for r in cells if r['criterion']=='T-I'))
        self.assertEqual(*outputs)


if __name__=='__main__':unittest.main()
