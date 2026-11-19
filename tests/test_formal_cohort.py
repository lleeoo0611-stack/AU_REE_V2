"""Formal C1 tests use synthetic, fully signed inputs only in this module."""
import json
import unittest
from pathlib import Path

from au_ree_v2.formal_cohort import (
    REQUIRED, assess_project, contracts, evidence_inventory, fixed_panel, release_result,
)

ROOT = Path(__file__).resolve().parents[1]


def approved_fixture():
    inputs = contracts(ROOT)
    review = inputs['review']
    policy = inputs['policy']
    cutoff = policy['source_asof']
    pid = 'fixture-project'
    group = 'fixture-review-group'
    signed_by = dict(reviewer_id='fixture-reviewer', reviewed_at='2026-11-02')
    panel = dict(candidate_id='PANEL_9_CANDIDATE', version='test-only-panel', policy_id=policy['policy_id'],
                 criteria_version=inputs['criteria_version'], source_asof=cutoff, status='APPROVED_BEFORE_RANKING',
                 approval_ref='fixture-panel', **signed_by)
    review['fixed_panel_decision'] = panel
    facts = {}
    meta = dict(review_group_id=group, verified_project_id='formal-project-id', project_identity_scope='Project perimeter',
                project_footprint_ref='project_footprint', ree_product_role_ref='planned_ree_product_role',
                resource_statement_id='dated-mre', resource_basis='TREO', original_jorc_ref='mineral_resource',
                approved_study_document_id='source-published_economic_study', study_published_asof='2026-06-16',
                approved_panel_version=panel['version'], approved_gis_evidence_id='distance_qa')
    inputs['metadata'] = [meta]
    inputs['crosswalk'] = [dict(upstream_review_group_id=group, v2_project_id=pid, verified_project_id='formal-project-id',
                                approval_ref='approved-id-mapping', native_id_evidence='project_identity')]
    for gate in policy['C1_required_gates']:
        keys = review['candidate_panels'][panel['candidate_id']] if gate=='PANEL' else REQUIRED[gate]
        for key in keys:
            criteria = inputs['criteria'].get(key, {})
            facts[key] = dict(project_id=pid, scope=meta['project_identity_scope'], source_sha='sha-'+key,
                source_key='source-'+key, date='2026-06-16', acquired_at='2026-11-01T12:00:00',
                effective_date='2026-06-01', source_url=None, locator='physical p.3; table 1',
                variable=criteria.get('variable',key), gate=gate, candidate_code=key if criteria else None,
                basis=criteria.get('basis'), unit=criteria.get('unit'), statement='dated-mre' if gate=='JORC' else None)
        ref = dict(project_id=pid, gate=gate, scope=meta['project_identity_scope'], source_asof=cutoff,
                   policy_id=policy['policy_id'], approval_ref='sign-'+gate, evidence={key:key for key in keys})
        if gate=='WINDOW':
            ref['window']=dict(asof=cutoff, country='AU', activity='ACTIVE', investment_status='PRE_FID',
                               study_level='PFS',study_status='PUBLISHED_COMPLETED')
        if gate=='ROLE':
            ref['product_role']='PLANNED_RECOVERED_BYPRODUCT_REE'
        review['gate_evidence_bindings'].append(ref)
        inputs['signatures'].append(dict(review_group_id=group, gate_id=gate, cohort='C1', decision_status='PASS',
            source_asof=cutoff, reason_code='fixture', document_id='source-'+keys[0],
            original_sha256_or_html_ref='sha-'+keys[0], approval_ref='sign-'+gate, **signed_by))
    return inputs, facts


class FormalGateTests(unittest.TestCase):
    def setUp(self):
        self.inputs, self.facts = approved_fixture()

    def evaluate(self):
        panel = fixed_panel(self.inputs)
        rows = assess_project('fixture-project', self.facts, self.inputs, '2026-11-13', panel)
        return {r['gate']:r for r in rows}, release_result(self.inputs, rows, panel)

    def test_actual_upstream_snapshot_panels_and_empty_signed_ledgers(self):
        actual = contracts(ROOT)
        self.assertEqual(actual['policy']['source_asof'], '2026-10-29')
        self.assertEqual(actual['signatures'], [])
        self.assertEqual(actual['metadata'], [])
        self.assertIsNone(fixed_panel(actual))
        panels = actual['review']['candidate_panels']
        self.assertEqual(set(panels['PANEL_12_CANDIDATE']) - set(panels['PANEL_9_CANDIDATE']), {'T2','C1','C2'})
        self.assertEqual(actual['criteria']['T1']['variable'], 'processing_complexity_ord')

    def test_positive_requires_digest_of_actual_decisions_before_release(self):
        gates, report = self.evaluate()
        self.assertEqual({r['status'] for r in gates.values()}, {'PASS'})
        self.assertEqual(report['signed_eligible_projects'], ['fixture-project'])
        self.assertEqual(report['release_status'], 'NOT_RELEASED')
        self.inputs['review']['release_qa'] = dict(status='PASS', reviewer_id='release-reviewer', reviewed_at='2026-11-05',
            approval_ref='qa',decision_set_sha256=report['decision_set_sha256'])
        self.assertEqual(self.evaluate()[1]['formally_releasable'], ['fixture-project'])
        self.inputs['review']['release_qa']['status']='FAILED'
        self.assertEqual(self.evaluate()[1]['formally_releasable'], [])
        self.inputs['review']['release_qa']['status']='PASS'
        self.inputs['review']['release_qa']['decision_set_sha256']='old'
        self.assertEqual(self.evaluate()[1]['formally_releasable'], [])

    def test_scope_mismatch_cannot_be_overruled_by_signature(self):
        self.facts['tonnage']['scope']='Neighbouring deposit'
        gates, report = self.evaluate()
        self.assertEqual(gates['JORC']['objective'], 'EVIDENCE_SCOPE_MISMATCH')
        self.assertEqual(report['projects_with_all_gates'], 0)

    def test_different_statement_or_incompatible_basis(self):
        self.facts['grade']['statement']='old-mre'
        self.assertEqual(self.evaluate()[0]['JORC']['objective'], 'RESOURCE_STATEMENT_MISMATCH')
        self.facts['grade']['statement']='dated-mre'
        self.inputs['metadata'][0]['resource_basis']='THM'
        self.assertEqual(self.evaluate()[0]['JORC']['objective'], 'INCOMPATIBLE_RESOURCE_BASIS')

    def test_partial_period_or_later_publication_only_in_census(self):
        self.facts['grade']['date']='2026-10'
        gates, _ = self.evaluate()
        self.assertEqual(gates['JORC']['objective'], 'EVIDENCE_OUTSIDE_POLICY_WINDOW')
        self.assertEqual(gates['JORC']['census_only_candidates'], 1)
        self.assertIn('grade', json.loads(gates['JORC']['census_only_evidence_ids']))

    def test_completed_study_alone_is_insufficient(self):
        review = next(r for r in self.inputs['review']['gate_evidence_bindings'] if r['gate']=='WINDOW')
        review['window']['investment_status']='NO_FID_FOUND'
        self.assertEqual(self.evaluate()[0]['WINDOW']['objective'], 'NO_EXPLICIT_ACTIVE_PRE_FID_ECONOMIC_STUDY_WINDOW')
        del review['evidence']['active_at_cutoff']
        self.assertEqual(self.evaluate()[0]['WINDOW']['objective'], 'MISSING_LOCATED_GATE_EVIDENCE')

    def test_crosswalk_is_one_to_one_and_must_bind_native_source(self):
        link = self.inputs['crosswalk'][0]
        self.inputs['crosswalk'].append(dict(link, v2_project_id='other-entity'))
        self.assertEqual(self.evaluate()[0]['ID']['crosswalk'], 'MISSING_OR_AMBIGUOUS')
        self.inputs['crosswalk'].pop()
        link['native_id_evidence']='similar-name-only'
        self.assertEqual(self.evaluate()[1]['projects_with_all_gates'], 0)

    def test_unselected_panel_and_technical_disclosure_do_not_pass(self):
        self.facts['T1']['basis']='TECHNICAL_DISCLOSURE'
        self.assertEqual(self.evaluate()[0]['PANEL']['objective'], 'CRITERION_VARIABLE_UNIT_OR_BASIS_MISMATCH')
        self.inputs['review']['fixed_panel_decision']=None
        self.assertEqual(self.evaluate()[0]['PANEL']['objective'], 'FORMAL_PANEL_UNSELECTED')

    def test_signer_cutoff_conflicting_or_missing(self):
        signatures = self.inputs['signatures']
        one = signatures[0]
        one['reviewed_at']='2029-01-01'
        self.assertEqual(self.evaluate()[0]['ID']['signoff'], 'INVALID_SIGNATURE')
        signatures.append(dict(one, decision_status='HOLD'))
        self.assertEqual(self.evaluate()[0]['ID']['signoff'], 'CONFLICTING_SIGNATURES')
        self.inputs['signatures']=[]
        self.assertEqual(self.evaluate()[0]['ID']['signoff'], 'UNSIGNED')

    def test_signed_exclusion_requires_matching_project_source(self):
        self.inputs['signatures'][0]['decision_status']='EXCLUDE'
        self.assertEqual(self.evaluate()[0]['ID']['status'], 'EXCLUDE')
        self.facts['project_identity']['scope']='Other deposit'
        self.assertEqual(self.evaluate()[0]['ID']['status'], 'PENDING')

    def test_wrong_published_study_or_role_reference(self):
        self.inputs['metadata'][0]['approved_study_document_id']='unrelated-study'
        self.assertEqual(self.evaluate()[0]['WINDOW']['objective'], 'STUDY_DOCUMENT_OR_DATE_MISMATCH')
        self.inputs['metadata'][0]['ree_product_role_ref']='ore-assay'
        self.assertEqual(self.evaluate()[0]['ROLE']['objective'], 'UPSTREAM_METADATA_REFERENCE_MISMATCH')

    def test_uncited_and_composite_field_provenance_not_single_source_evidence(self):
        trace = {('p','專案名稱'):dict(value='P', locator='p.3', source_sha256='x;y')}
        self.assertFalse(evidence_inventory({'專案ID':'p'}, trace, {}, {}, self.inputs['criteria']))
