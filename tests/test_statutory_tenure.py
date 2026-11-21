import unittest

import pymupdf
from shapely.geometry import Point

from au_ree_v2.statutory_tenure import NOTICE_SHA, read_graticule, statutory_extent


class StatutoryTenureTests(unittest.TestCase):
    axes = (133 * 60, 23 * 60, 6, 3)
    grid = (80, 80, 380, 230)

    @staticmethod
    def map_image(boundaries):
        # Three rows of legal land. Single pixel line at x=4 models the map's graticule.
        pixels = bytearray(b'\xff') * (550 * 550 * 3)
        for row, crossings in enumerate(boundaries):
            y = 105 + row * 50
            for col, width in [(4, 1)] + [(c, 3) for c in crossings]:
                for offset in range(-(width // 2), width // 2 + 1):
                    start = 3 * (550 * y + 80 + col * 50 + offset)
                    pixels[start:start + 3] = b'\0\0\0'
        return pymupdf.Pixmap(pymupdf.csRGB, 550, 550, pixels, False)

    def test_hole_and_separate_part_survive_graticule_decoding(self):
        map_image = self.map_image([(0, 3, 5, 6), (0, 1, 2, 3), (0, 3)])
        shape, blocks = read_graticule(map_image, self.axes, self.grid)
        self.assertEqual(blocks, 9)
        self.assertEqual(shape.geom_type, 'MultiPolygon')
        self.assertEqual(len(shape.geoms), 2)
        self.assertEqual(sum(len(part.interiors) for part in shape.geoms), 1)
        self.assertFalse(shape.covers(Point(133 + 1.5 / 60, -23 - 1.5 / 60)))
        self.assertTrue(shape.covers(Point(133 + 5.5 / 60, -23 - .5 / 60)))

    def test_incomplete_boundary_fails_closed(self):
        with self.assertRaisesRegex(ValueError, 'OPEN_RING'):
            read_graticule(self.map_image([(0,), (), ()]), self.axes, self.grid)

    def test_wrong_scope_or_late_source_cannot_publish(self):
        binding = dict(licence='33006', project_id='id', project_name='URO EL33006', report_sha256='scope')
        row = {'專案名稱': binding['project_name'], '專案ID': 'id', '開發商': 'URO Corporation Pty Ltd'}
        source = dict(kind='pdf', sha256=NOTICE_SHA, publication_date='2024-08-22')
        documents = {'scope': dict(kind='pdf', publication_date='2024-11-30')}
        self.assertIsNone(statutory_extent(source, documents, binding, row, '2024-11-29', 25000))
        mismatch = dict(binding, licence='33004')
        self.assertIsNone(statutory_extent(source, documents, mismatch, row, '2024-11-30', 25000))
        self.assertIsNone(statutory_extent(dict(source, sha256='changed'), documents, binding, row, '2024-11-30', 25000))
