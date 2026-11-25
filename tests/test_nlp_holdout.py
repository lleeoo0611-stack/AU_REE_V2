import csv
import hashlib
import tempfile
import unittest
from pathlib import Path

import pymupdf

from tools.nlp_census_experiment import document_splits


class NlpHoldoutTest(unittest.TestCase):
    def test_same_bytes_shared_families_and_late_editions_stay_out_of_holdout(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder=Path(temporary)
            assets=folder/'assets'
            assets.mkdir()
            rows=[]
            def add(key,text,cutoff='WITHIN_CUTOFF'):
                with pymupdf.open() as document:
                    document.new_page().insert_text((32,32),text)
                    raw=document.tobytes()
                sha=hashlib.sha256(raw).hexdigest()
                (assets/sha).write_bytes(raw)
                rows.append([key,sha,'pdf',cutoff,'ASX_SOURCE_ADDED','PINNED_SHA_VERIFIED'])
                return sha
            dev=add('browns_range_2025','Northern Minerals - Browns Range')
            rows.append(['alternate-key',*rows[-1][1:]])
            mixed=add('different-title','Project report has an appendix referring to Northern Minerals.')
            mixed_project=add('mt_weld_2024','Lynas - Mt Weld and Green Valley')
            held=add('target-only','Green Valley deposit geology')
            late=add('late','Green Valley deposit after cutoff','SOURCE_AFTER_CUTOFF')
            with (folder/'source_selection.csv').open('w',newline='',encoding='utf-8') as f:
                writer=csv.writer(f)
                writer.writerow(['key','source_sha256','kind','cutoff_status','action','version_status'])
                writer.writerows(rows)
            documents,sets=document_splits(folder,assets,[{'project_name':'Green Valley REE Project'}],folder/'cache')
            self.assertEqual({r['sha256']:r['split'] for r in documents},
                             {dev:'development',mixed:'quarantine',mixed_project:'quarantine',held:'holdout'})
            self.assertEqual([r[0] for r in sets['holdout']],[held])
            self.assertEqual([r[0] for r in sets['development']],[dev])
            self.assertFalse((folder/'cache'/(late+'.json')).exists())
