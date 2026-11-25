"""A native MinDep coordinate pair requires the same reviewed prospect in both originals."""
import csv
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import pymupdf

from au_ree_v2.spatial import summary_locations


class SarigProspectPointTests(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.folder = Path(directory.name)
        self.row = {'專案ID': 'project', '專案名稱': 'Named Prospect Project',
                    '州省地區': 'South Australia', '開發商': 'Issuer'}
        self.site = dict(MINERAL_DEPOSIT_NO='10098', SITE_NO='1982184', DEPOSIT_NAME='NAMED',
                         DEPOSIT_CLASS='Prospect', COMMODITIES='Kaolin', LONGITUDE_GDA2020='139.4657582',
                         LATITUDE_GDA2020='-33.2772965', EASTING_GDA2020='357120.69',
                         NORTHING_GDA2020='6316921.47', ZONE_GDA2020='54', HORIZ_ACCRCY_M='50')
        self.write_sites([self.site])
        self.sources = {'edition': dict(key='sa_mindep_live', kind='government_csv', state='SA',
                                       namespace='SA_MINDEP_SITE', encoding='utf-8',
                                       available_date='2026-11-03', resolved_path=self.folder/'sites.csv')}
        self.case = dict(census_project_name=self.row['專案名稱'], developer=self.row['開發商'],
                         source_sha256='edition', feature_id='10098', site_no='1982184',
                         feature_name='NAMED', feature_class='Prospect', native_commodity='Kaolin')
        for role, text in [('government', 'Named prospect (MinDep no. 10098) reports TREO.'),
                           ('issuer', 'Issuer reports kaolin and REEs from the named prospect.')]:
            path = self.folder / (role+'.pdf')
            with pymupdf.open() as document:
                document.new_page().insert_text((48, 48), text)
                document.save(path)
            self.sources[role] = dict(key=role, kind='pdf', publication_date='2024-08', resolved_path=path)
            self.case[role+'_proof'] = dict(source_key=role, sha256=role, page=1, markers=[text])
        self.rules = {'states': {'SA': 'South Australia'}, 'aliases.projects': [], 'point_display_digits': 10,
                      'reviewed_sarig_points': {'project': self.case}}
        self.decisions = [dict(rule='SELECT_OFFICIAL_LOCATION_DATASET',
                               scope=dict(dataset='SA_SARIG', layer='mines_and_mineral_deposits:all_mines_and_mineral_deposits')),
                          dict(rule='NORMALIZED_NAME_MATCH')]

    def write_sites(self, rows):
        with (self.folder/'sites.csv').open('w', newline='', encoding='utf-8') as stream:
            writer = csv.DictWriter(stream, fieldnames=self.site)
            writer.writeheader()
            writer.writerows(rows)

    def locations(self):
        return summary_locations(self.row, [self.row], [], self.sources, self.rules, self.decisions,
                                 cutoff='2026-11-06')

    def test_native_pair_includes_both_reviewed_pdf_pages(self):
        self.write_sites([self.site, dict(self.site, MINERAL_DEPOSIT_NO='10127', SITE_NO='other')])
        fills = self.locations()
        self.assertEqual({f['column']: f['value'] for f in fills}, {'經度':'139.4657582', '緯度':'-33.2772965'})
        for fill in fills:
            self.assertEqual(fill['sha'].split(';'), ['edition', 'government', 'issuer'])
            scope = json.loads(fill['scope'])
            self.assertEqual((scope['datum'], scope['horizontal_accuracy_m']), ('EPSG:7844', 50))
            self.assertEqual(len(scope['references']), 2)

    def test_wrong_native_row_or_inconsistent_pair_is_rejected(self):
        for override in [dict(MINERAL_DEPOSIT_NO='10127'), dict(SITE_NO='other'), dict(DEPOSIT_NAME='other'),
                         dict(COMMODITIES='Gold'), dict(DEPOSIT_CLASS='Mine'), dict(HORIZ_ACCRCY_M=''),
                         dict(LATITUDE_GDA2020=''), dict(EASTING_GDA2020='357999.00')]:
            with self.subTest(override=override):
                self.write_sites([dict(self.site, **override)])
                self.assertEqual(self.locations(), [])
        self.write_sites([self.site, self.site])
        self.assertEqual(self.locations(), [])

    def test_both_source_dates_identity_and_selected_layer_are_required(self):
        for obj, key, wrong in [(self.sources['edition'], 'available_date', '2026-11-07'),
                                (self.sources['government'], 'publication_date', '2026-11'),
                                (self.sources['issuer'], 'key', 'other'),
                                (self.case['issuer_proof'], 'page', 2),
                                (self.case['government_proof'], 'markers', ['Named prospect (MinDep no. 10127)']),
                                (self.case['issuer_proof'], 'markers', ['Other project']),
                                (self.row, '開發商', 'Different holder'),
                                (self.decisions[0]['scope'], 'layer', 'projects')]:
            with self.subTest(key=key, wrong=wrong):
                previous = obj[key]
                obj[key] = wrong
                self.assertEqual(self.locations(), [])
                obj[key] = previous
