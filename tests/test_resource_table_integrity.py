import hashlib
import tempfile
import unittest
from pathlib import Path

import pymupdf

from au_ree_v2.evidence import strict_claims, validate_pages
from au_ree_v2.store import connect


class ResourceTableIntegrity(unittest.TestCase):
    def setUp(self):
        work = Path(__file__).resolve().parents[1] / 'work'
        work.mkdir(exist_ok=True)
        folder = tempfile.TemporaryDirectory(dir=work)
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)

    def make_pdf(self, key, marker, image_color=None):
        path = self.root / f'{key}.pdf'
        with pymupdf.open() as pdf:
            pdf.new_page().insert_text((72, 72), marker)
            image_page = pdf.new_page()
            if image_color is not None:
                image = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 20, 30), False)
                image.clear_with(image_color)
                image_page.insert_image(pymupdf.Rect(72, 96, 132, 186), stream=image.tobytes('png'))
            pdf.save(path)
        return dict(key=key, kind='pdf', path=path.name, sha256=hashlib.sha256(path.read_bytes()).hexdigest())

    def table_image(self, source):
        with pymupdf.open(self.root / source['path']) as pdf:
            block, = [block for block in pdf[1].get_text('dict')['blocks'] if block['type'] == 1]
        return dict(page=2, sha256=hashlib.sha256(block['image']).hexdigest(),
                    size=[block['width'], block['height']], bbox=list(block['bbox']))

    def test_reviewed_image_must_match_selected_pdf_page_and_position(self):
        source = self.make_pdf('study', 'Studied mineral resource', image_color=32)
        different = self.make_pdf('alternate', 'Studied mineral resource', image_color=160)
        image = self.table_image(source)
        evidence = dict(source_sha256=source['sha256'], pdf_page=1,
                        page_markers=['Studied mineral resource'], reviewed_pdf_table_image=image)
        snapshots = [source, different]
        cache = {}
        validate_pages(self.root, source, evidence, snapshots, cache)

        changed_images = {
            'foreign image': self.table_image(different),
            'wrong size': dict(image, size=[image['size'][0] + 1, image['size'][1]]),
            'wrong position': dict(image, bbox=[coordinate + 1 for coordinate in image['bbox']]),
            'wrong page': dict(image, page=1),
        }
        for case, changed_image in changed_images.items():
            with self.subTest(case=case):
                changed_evidence = dict(evidence, reviewed_pdf_table_image=changed_image)
                with self.assertRaisesRegex(ValueError, 'REVIEWED_IMAGE_OR_POSITION_CHANGED|IMAGE_PHYSICAL_PAGE_UNVERIFIED'):
                    validate_pages(self.root, source, changed_evidence, snapshots, cache)

        (self.root / source['path']).write_bytes((self.root / different['path']).read_bytes())
        with self.assertRaisesRegex(ValueError, 'SOURCE_HASH_MISMATCH'):
            validate_pages(self.root, source, evidence, snapshots)

    def test_external_context_selects_exact_version_and_checks_original_bytes(self):
        primary = self.make_pdf('statement', 'Studied mineral resource')
        witness = self.make_pdf('context', 'Definitions in appended issuer release')
        context = dict(source_key=witness['key'], source_sha256=witness['sha256'], page=1,
                       markers=['Definitions in appended issuer release'])
        evidence = dict(source_sha256=primary['sha256'], pdf_page=1, page_markers=['Studied mineral resource'],
                        context_evidence=[context, dict(page=1, markers=['Studied mineral resource'])])
        snapshots = [primary, witness]
        validate_pages(self.root, primary, evidence, snapshots)

        wrong_version = dict(evidence, context_evidence=[dict(context, source_sha256=primary['sha256'])])
        with self.assertRaisesRegex(ValueError, 'CONTEXT_ORIGINAL_NOT_SELECTED_OR_CHANGED'):
            validate_pages(self.root, primary, wrong_version, snapshots)
        with self.assertRaisesRegex(ValueError, 'CONTEXT_ORIGINAL_NOT_SELECTED_OR_CHANGED'):
            validate_pages(self.root, primary, evidence, [primary])

        path = self.root / witness['path']
        path.write_bytes(path.read_bytes() + b'\nchanged PDF')
        with self.assertRaisesRegex(ValueError, 'SOURCE_HASH_MISMATCH'):
            validate_pages(self.root, primary, evidence, snapshots)

    def test_strict_attribute_captures_alias_page_from_its_own_source(self):
        primary = self.make_pdf('study', 'Original mine study: oxide products')
        witness = self.make_pdf('alias', 'New name was formerly Original mine')
        for source in (primary, witness):
            source.update(url='https://example.org/' + source['path'],
                          acquired_at='2026-01-02', available_date='2026-01-01')
        context = dict(source_key='alias', source_sha256=witness['sha256'], page=1,
                       markers=['New name', 'formerly Original mine'])
        attribute = dict(column='產品/產出', value='OXIDE', source_key='study',
                         source_sha256=primary['sha256'], pdf_page=1,
                         page_markers=['Original mine', 'oxide products'], context_evidence=[context],
                         locator='study p1', effective_date='2026-01-01', extraction_method='STATIC_PDF')
        project = dict(id='mine', identity_source='study', observations=[], attributes=[attribute])
        db = connect(self.root / 'alias.sqlite')
        self.addCleanup(db.close)
        snapshots = [primary, witness]
        claims = strict_claims(db, self.root, snapshots, {'projects':[project]}, [], self.root / 'pages')
        accepted, = claims['projects'][0]['attributes']
        binding, = accepted['context_evidence']
        proof = next(s for s in snapshots if s['key'] == binding['page_extraction_key'])
        self.assertEqual(proof['source_sha256'], witness['sha256'])
        for originals in ([primary], [primary, dict(witness, sha256=primary['sha256'])]):
            rejected = strict_claims(db, self.root, originals, {'projects':[project]}, [], self.root / 'pages')
            self.assertEqual(rejected['projects'][0]['attributes'], [])
            self.assertIn('CONTEXT_ORIGINAL_NOT_SELECTED_OR_CHANGED',
                          [row[0] for row in db.execute('SELECT reason FROM review_queue')])
