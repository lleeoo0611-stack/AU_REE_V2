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
        self.assertEqual(json.loads((ROOT/'data/claims.json').read_bytes()),expected)
        self.assertEqual(70,len(log))
        self.assertEqual(approvals.APPROVED_IDS,{r['proposal_id'] for r in log})

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
