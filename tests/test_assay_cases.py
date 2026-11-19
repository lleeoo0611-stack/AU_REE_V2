"""Per-sample assay regression, especially laboratory QC versus field pXRF control."""
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

import pymupdf

from au_ree_v2.assays import verify_pages, write_assay_evidence
from au_ree_v2.tabular import read_csv


class AssayCaseTests(unittest.TestCase):
    def test_superseded_anchor_cannot_authorize_verified_qc_or_numeric_value(self):
        with tempfile.TemporaryDirectory() as folder, closing(sqlite3.connect(':memory:')) as db:
            root=Path(folder)
            (root/'config').mkdir()
            case=dict(project_id='A',source_sha256='sha',source_key='soil',sample='soil batch 1',
                      project_link_observation='archived-anchor', pages={'1':['Duke','soil']},
                      crm='batch CRM',value=42)
            (root/'config/assay_evidence.json').write_text(json.dumps(dict(version='v',standards=[],cases=[case])))
            db.execute('create table observations(obs_id,entity_id,source_sha,status,effective_date)')
            db.execute("insert into observations values ('archived-anchor','A','sha','AUTO_VALIDATED','2026-01-01')")
            counts=write_assay_evidence(root,root,[{'專案ID':'A'}],{'sha':{'publication_date':'2026-01-02'}},
                                        db,'2026-11-13',{'other-anchor'})
            self.assertEqual(counts['assay_cases_verified'],0)
            row=read_csv(root/'assay_method_evidence.csv')[0]
            self.assertEqual(row['verification'],'SOURCE_OR_PROJECT_LINK_UNVERIFIED')
            self.assertEqual((row['crm'],row['value']),('',''))

    def test_empty_or_non_distinct_witnesses_cannot_validate_an_unrelated_page(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'two-labs.pdf'
            with pymupdf.open() as pdf:
                page=pdf.new_page()
                page.insert_text((30,50),'pXRF: field instrument blank.')
                page=pdf.new_page()
                page.insert_text((30,50),'LabWest: ICP-MS of soil.')
                pdf.save(path)
            for pages in ({},{'1':['','']},{'1':['   ','  ']},{'1':['pXRF','pXRF']}):
                with self.subTest(pages=pages):
                    self.assertFalse(verify_pages(path,pages))
            self.assertFalse(verify_pages(path,{'2':['LabWest','field instrument blank']}))
            self.assertTrue(verify_pages(path,{'2':['LabWest','ICP-MS of soil']}))

    def test_separate_bases_and_qa_in_four_reviewed_sources(self):
        root=Path(__file__).resolve().parents[1]
        cases={c['source_key']:c for c in json.loads((root/'config/assay_evidence.json').read_bytes())['cases']}
        duke=cases['hre_duke_targets_20231113']
        self.assertIn('ultrafine',duke['matrix'].lower())
        self.assertEqual(duke['laboratory'],'LabWest')
        # Duke p.8's blank is attached to the Olympus Vanta field pXRF paragraph.
        self.assertFalse(duke.get('blank'))
        self.assertIn('20',duke['duplicates'])
        self.assertIn('acid-leachable',cases['itech_franklyn_ree_assays_20220729']['basis'])
        self.assertIn('fusion',cases['nutgrove_rhyolite_20260303']['method'])
        self.assertEqual(cases['goschen_central_mre2024']['unit'],'% HM')
        self.assertFalse(cases['goschen_central_mre2024'].get('crm'))
        self.assertTrue(all(not c.get('adopted_standard') for c in (duke,cases['goschen_central_mre2024'])))
