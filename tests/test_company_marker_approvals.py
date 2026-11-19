import copy
import importlib.util
import json
import subprocess
import sys
import hashlib
import os
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import company_marker_approvals as approvals
import check_company_markers_ci as audit


class CompanyMarkerApprovals(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.before=json.loads(subprocess.check_output(['git','show',approvals.BASELINE+':data/claims.json'],cwd=ROOT))
        cls.rows,cls.approved=approvals.load_ledger()

    def test_exact_approval_scope_and_current_claims_delta(self):
        self.assertEqual(70,len(self.approved))
        self.assertEqual(22,sum(r['approved']=='HOLD' for r in self.rows))
        self.assertEqual(135,sum(not r['approved'] for r in self.rows))
        expected,log=approvals.apply_rows(self.before,self.approved)
        published=subprocess.check_output(['git','show','6eeaeae:data/claims.json'],cwd=ROOT)
        self.assertEqual(json.loads(published),expected)
        self.assertEqual(70,len(log))
        self.assertEqual(approvals.APPROVED_IDS,{r['proposal_id'] for r in log})

    def test_frozen_whole_file_and_integrated_approval_locations(self):
        published=audit.revision_claims(ROOT,audit.V10)
        prior=audit.revision_claims(ROOT,audit.INTEGRATION_BASE)
        current=json.loads((ROOT/'data/claims.json').read_bytes())
        self.assertNotEqual(published,current)
        audit.check_contract(published,published,self.rows)
        with self.assertRaisesRegex(ValueError,'V10_CLAIMS'):
            audit.check_contract(current,published,self.rows)
        audit.check_contract(current,published,self.rows,prior)

    def project_fixture(self, row):
        published=audit.revision_claims(ROOT,audit.V10)
        project=approvals.project_map(published)[row['project_id']]
        return {'projects':[project]}

    def test_approved_target_rejects_removal_page_source_value_and_new_marker(self):
        row=self.approved[0]
        published=self.project_fixture(row)
        for change in ('delete','source','page','marker','remove_marker','value','column'):
            with self.subTest(change=change):
                current=copy.deepcopy(published)
                attribute=current['projects'][0]['attributes'][2]
                target=attribute['context_evidence'][0]
                if change=='delete':attribute['context_evidence'].pop(0)
                if change=='source':attribute['source_sha256']='0'*64
                if change=='page':target['page']+=1
                if change=='marker':target['markers'].append('Unapproved company marker')
                if change=='remove_marker':target['markers'].pop()
                if change=='value':attribute['value']='OTHER'
                if change=='column':attribute['column']='開發商'
                with self.assertRaisesRegex(ValueError,'APPROVED_COMPANY_BINDING_CHANGED'):
                    audit.check_contract(current,published,[row],published)

    def test_unapproved_and_cross_field_proposals_cannot_be_reused(self):
        for disposition in ('HOLD',''):
            row=next(r for r in self.rows if r['approved']==disposition and
                     r['declaration_pointer'].startswith('/attributes/'))
            published=self.project_fixture(row)
            current=copy.deepcopy(published)
            node=current['projects'][0]
            for part in row['declaration_pointer'].strip('/').split('/'):
                node=node[int(part)] if isinstance(node,list) else node[part]
            markers=node.get('markers',node.get('page_markers'))
            markers.extend([row['marker_1'],row['marker_2']])
            with self.subTest(disposition=disposition):
                with self.assertRaisesRegex(ValueError,'UNAPPROVED_PROPOSAL_MARKER_SCOPE'):
                    audit.check_contract(current,published,[row],published)
        row=self.approved[0]
        published=self.project_fixture(row)
        current=copy.deepcopy(published)
        current['projects'][0]['attributes'].append(dict(column='礦床型態',
            source_key=row['source_key'],source_sha256=row['source_sha256'],pdf_page=int(row['pdf_page']),
            page_markers=[row['marker_1'],row['marker_2']]))
        with self.assertRaisesRegex(ValueError,'UNAPPROVED_PROPOSAL_MARKER_SCOPE'):
            audit.check_contract(current,published,[row],published)

    def test_independent_evidence_can_be_added_without_v10_approval(self):
        row=self.approved[0]
        published=self.project_fixture(row)
        current=copy.deepcopy(published)
        for column in ('開發商','ASX代碼'):
            current['projects'][0]['attributes'].append(dict(column=column,source_key='new_report',
                source_sha256='3'*64,pdf_page=7,page_markers=['reviewed independently','new original']))
        current['projects'][0]['attributes'].append(dict(column='ASX代碼',source_key=row['source_key'],
            source_sha256=row['source_sha256'],pdf_page=7,
            page_markers=[row['marker_1'],'separately verified company evidence']))
        audit.check_contract(current,published,[row],published)
        self.assertEqual(('NO_SELECTED_CENSUS_SOURCE',''),audit.selected_binding(row,None,set()))

    def test_new_selected_source_or_same_source_distinct_attribute_requires_active_evidence(self):
        row=self.approved[0]
        for sha in ('2'*64,row['source_sha256']):
            selection=dict(source_sha256=sha,attribute_ids='["new-attribute"]',observation_ids='["new-observation"]')
            with self.subTest(sha=sha):
                self.assertEqual(('SUPERSEDED_BY_VERIFIED_CENSUS_SOURCE',sha),
                    audit.selected_binding(row,selection,{'new-observation'},'previous-attribute'))
                with self.assertRaisesRegex(ValueError,'UNVERIFIED_REPLACEMENT_COMPANY_SOURCE'):
                    audit.selected_binding(row,selection,{'unrelated-observation'},'previous-attribute')

    def test_changed_original_sha_is_a_failure(self):
        row=self.approved[0]
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            (root/'source.pdf').write_bytes(b'%PDF changed original')
            record=audit.check_row(root,row,{},dict(path='source.pdf'),[],{},root)
            self.assertEqual('FAILED_IN_CI',record['status'])

    def test_append_preserves_existing_marker_page_sha_and_unrelated_fields(self):
        original=copy.deepcopy(self.before)
        row=self.approved[0]
        result,_=approvals.apply_rows(original,[row])
        old=approvals.binding_for(approvals.project_map(original)[row['project_id']],row)
        new=approvals.binding_for(approvals.project_map(result)[row['project_id']],row)
        field='page_markers' if 'page_markers' in old else 'markers'
        self.assertEqual(old[field]+[row['marker_1'],row['marker_2']],new[field])
        restored=copy.deepcopy(result)
        approvals.binding_for(approvals.project_map(restored)[row['project_id']],row)[field]=old[field]
        self.assertEqual(original,restored)
        self.assertEqual(self.before,original)

    def test_page_or_source_conflict_does_not_mutate_input(self):
        for field in ('pdf_page','source_sha256'):
            with self.subTest(field=field):
                row=copy.deepcopy(self.approved[0])
                row[field]='99' if field=='pdf_page' else '0'*64
                before=copy.deepcopy(self.before)
                with self.assertRaises(approvals.MarkerConflict):approvals.apply_rows(before,[row])
                self.assertEqual(self.before,before)

    def test_hold_unknown_id_and_non_company_rows_never_apply(self):
        samples=[copy.deepcopy(next(r for r in self.rows if r['approved']=='HOLD')),
                 dict(self.approved[0],proposal_id='0'*20),
                 dict(self.approved[0],column='專案名稱')]
        for row in samples:
            with self.subTest(id=row['proposal_id']):
                row['approved']='Y'
                with self.assertRaisesRegex(ValueError,'UNAPPROVED'):
                    approvals.apply_rows(self.before,[row])

    def test_duplicate_approved_pointer_is_a_conflict(self):
        with self.assertRaisesRegex(approvals.MarkerConflict,'DUPLICATE_APPROVED_LOCATION'):
            approvals.apply_rows(self.before,[self.approved[0],self.approved[0]])

    def test_comparison_policy_and_src_unchanged_from_baseline(self):
        self.assertEqual(b'',subprocess.check_output(
            ['git','diff',approvals.BASELINE,'6eeaeae','--','src','tools/compare_ci_cells.py'],cwd=ROOT))
        self.assertEqual(b'',subprocess.check_output(
            ['git','diff','6eeaeae','--','tools/compare_ci_cells.py'],cwd=ROOT))

    def marker_audit(self,include_markers=True):
        import pymupdf
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);pdf=root/'original.pdf';doc=pymupdf.open();page=doc.new_page()
            words='27 October 2021\niTech Minerals Ltd\nASX: ITM' if include_markers else 'A different document without the approved company markers'
            page.insert_text((50,50),words);doc.save(pdf);doc.close()
            row=copy.deepcopy(self.approved[0]);project=copy.deepcopy(approvals.project_map(self.before)[row['project_id']])
            row['source_sha256']=hashlib.sha256(pdf.read_bytes()).hexdigest()
            parent=project['attributes'][2];parent['source_sha256']=row['source_sha256']
            parent['context_evidence'][0]['markers']+= [row['marker_1'],row['marker_2']]
            source=dict(key=row['source_key'],kind='pdf',path='original.pdf',sha256=row['source_sha256'])
            original=copy.deepcopy(project)
            with patch.dict(os.environ,{'TESSDATA_PREFIX':''}):
                result=audit.check_row(root,row,project,source,[source],{},root/'audit')
            self.assertEqual(original,project)
            return result

    def test_ci_audit_uses_real_pdf_and_evidence_contract(self):
        result=self.marker_audit()
        self.assertEqual('PASS',result['status'])
        self.assertEqual('EVIDENCE_PY_PAGE_AND_MARKERS_VERIFIED',result['reason'])

    def test_missing_markers_fail_without_repair_and_retain_page_snippet(self):
        result=self.marker_audit(False)
        self.assertEqual('FAILED_IN_CI',result['status'])
        self.assertIn('different document',result['page_text_first_300'])

    def test_unavailable_source_is_distinct_from_a_marker_failure(self):
        row=self.approved[0]
        result=audit.check_row(ROOT,row,{},None,[],{},ROOT/'work')
        self.assertEqual('NOT_CHECKED_SOURCE_UNAVAILABLE',result['status'])


if __name__=='__main__':unittest.main()
