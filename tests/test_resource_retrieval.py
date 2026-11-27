from contextlib import closing
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import pymupdf

from au_ree_v2.derived_cache import DerivedCache
from au_ree_v2.document_processing import PdfDocumentCache
from au_ree_v2.evidence import ingest_claims, ingest_sources
from au_ree_v2.resource_admission_flow import load_frame, run
from au_ree_v2.resource_retrieval import apply_parse_receipt, policy, retrieve
from au_ree_v2.store import connect, digest, filehash
from test_resource_admission_review_pdf import CUTOFF, FIXTURE_CLASS, PROJECT, ROOT, original, resource_page


class ResourceRetrievalTests(unittest.TestCase):
    def test_verified_pdf_index_keeps_fixed_pages_and_reuses_terms(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / 'original.pdf'
            with pymupdf.open() as pdf:
                for text in ('Issuer announcement',
                             'Caldera mineral resource estimate: 50 Mt, grade 2000 ppm TREO, Nd2O3',
                             'Table 1 effective date and dry basis: definition, cutoff and density', ''):
                    page = pdf.new_page()
                    if text:
                        page.insert_text((24, 50), text)
                pdf.save(path)
            sha = filehash(path)
            frame_path = root / 'frame.json'
            frame_path.write_text(json.dumps({'schema': 'resource-admission-frame-v1',
                'sources': [{'source_key': 'caldera', 'source_sha256': sha, 'pages': [1]}],
                'retrieval': {'value_page_budget': 2, 'context_page_budget': 1}}), encoding='utf-8')
            fixed = load_frame(frame_path)
            expanded = load_frame(frame_path, retrieval_mode='full-text')
            self.assertEqual(fixed['sources'], expanded['sources'])
            self.assertNotIn('retrieval', fixed)

            def search():
                cache = DerivedCache(root / 'cache')
                with PdfDocumentCache(root, source_paths={sha: path}, cache=cache) as documents:
                    result = retrieve(documents, expanded['sources'][0], ['Caldera Project'], expanded['retrieval'])
                return result, cache.receipt()['counts']

            cold, cold_cache = search()
            warm, warm_cache = search()
            self.assertEqual(cold, warm)
            self.assertEqual((cold['document_total_pages'], cold['indexed_page_count']), (4, 3))
            self.assertEqual(cold['unreadable_pages'], [4])
            self.assertEqual(cold['selected_pages'], [1, 2])
            self.assertEqual(cold['selected_context_pages'], [3])
            self.assertEqual(cold_cache['bm25-index'], {'COMPUTED': 2})
            self.assertEqual(warm_cache['bm25-index'], {'HIT': 1})
            self.assertEqual(warm_cache['bm25-query'], {'HIT': 3})
            path.unlink()
            blocked, _ = search()
            self.assertEqual((blocked['status'], blocked['reason']), ('SOURCE_BLOCKED', 'PDF_BYTES_UNAVAILABLE'))

    def test_page_errors_do_not_prevent_other_pages_from_being_indexed(self):
        sha = 'c' * 64

        class Source:
            def __len__(self):
                return 3

            def text(self, page, *, positioned):
                if page == 2:
                    raise RuntimeError('Positioned parser failed')
                return 'Caldera mineral resource estimate' if page == 1 else ''

        class Documents:
            cache = None

            def verify(self, sha256):
                self.open(sha256)

            def open(self, sha256):
                if sha256 != sha:
                    raise AssertionError(sha256)
                return Source()

        result = retrieve(Documents(), {'source_key': 'release', 'source_sha256': sha, 'pages': [1]},
                          ['Caldera'], policy(override_mode='full-text'))
        self.assertEqual((result['document_total_pages'], result['indexed_page_count']), (3, 1))
        self.assertEqual(result['candidate_pages']['resource'], [1])
        self.assertEqual(result['index_failures'], [{'physical_page': 2, 'reason': 'RuntimeError'}])
        self.assertEqual(result['unreadable_pages'], [3])
        apply_parse_receipt(result, {'pages': [{'physical_page': 1, 'status': 'NO_CANDIDATES'}]})
        self.assertEqual(result['parsed_pages'], [1])
        self.assertEqual(result['value_search_outcome'], 'PAGE_PARSE_FAILED')

    def test_full_text_flow_reports_missing_and_unreadable_originals_and_continues(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'config').symlink_to(ROOT / 'config', target_is_directory=True)
            valid = original(root, resource_page())
            missing = dict(valid, key='missing-source', path='missing.pdf', sha256='e' * 64)
            unreadable_path = root / 'invalid.pdf'
            unreadable_path.write_bytes(b'Invalid PDF bytes with a pinned checksum.')
            unreadable = dict(valid, key='unreadable-source', path=unreadable_path.name, sha256=filehash(unreadable_path))
            snapshots = [missing, unreadable, valid]
            claims = {'projects': [{'id': 'alpha', 'name': PROJECT, 'aliases': [PROJECT], 'state': 'WA',
                                    'identity_source': valid['key'], 'observations': []}]}
            frame_path = root / 'frame.json'
            frame_path.write_text(json.dumps({'schema': 'resource-admission-frame-v1', 'classification': FIXTURE_CLASS,
                'sources': [{'source_key': row['key'], 'source_sha256': row['sha256'], 'pages': [1]}
                            for row in snapshots]}), encoding='utf-8')
            configuration = {'claims_sha256': digest(claims), 'research': {}}
            with closing(connect(':memory:')) as db:
                ingest_sources(db, root, snapshots)
                ingest_claims(db, root, snapshots, CUTOFF, conflict_selection=True, claims_data=claims)
                contract, receipt = run(db, root, snapshots, CUTOFF, load_frame(frame_path, retrieval_mode='full-text'),
                                        run_id='fixture', configuration=configuration, acquired_through=CUTOFF,
                                        claims_data=claims, cache_dir=root / 'cache', cache_mode='off')
            editions = {row['source_key']: row for row in receipt['retrieval_sources']}
            self.assertEqual(editions[missing['key']]['reason'], 'PDF_BYTES_UNAVAILABLE')
            self.assertEqual(editions[unreadable['key']]['reason'], 'PDF_BYTES_UNREADABLE')
            self.assertEqual(editions[valid['key']]['parsed_pages'], [1])
            self.assertEqual(editions[valid['key']]['context_search_outcome'], 'CONTEXT_PAGES_PARSED')
            self.assertEqual(receipt['counts']['accepted_statements'], 1)
            self.assertEqual(receipt['counts']['source_blocked'], 2)
            self.assertEqual(contract['effective_frame_sources_sha256'], digest(receipt['effective_frame_sources']))


if __name__ == '__main__':
    unittest.main()
