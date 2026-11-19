import copy
from pathlib import Path
import tempfile
import unittest

import pymupdf

from au_ree_v2.census import summary_settings
from au_ree_v2.store import filehash
from au_ree_v2.technical import NAMEPLATE_NDPR_METHOD, summary_forecasts


ROOT = Path(__file__).resolve().parents[1]
PARAMETER = 'average_annual_ndpr_product_t'
NDPR = '預估年產NdPr_t_per_year'


class NameplateNdPrForecast(unittest.TestCase):
    def setUp(self):
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as file:
            self.pdf = Path(file.name)
        self.addCleanup(self.pdf.unlink, missing_ok=True)
        self.rules, self.decisions = summary_settings(ROOT)

    def make_forecast(self, nameplate_period='tpa'):
        with pymupdf.open() as doc:
            annual = doc.new_page()
            annual.insert_text((70, 80), 'Annual Production - REO Contained in Mixed Carbonate')
            annual.insert_text((380, 80), '3,645')
            annual.insert_text((425, 80), 'tpa')
            capacity = doc.new_page()
            capacity.insert_text((70, 80), 'The plant has a nameplate production capacity of '
                                 + f'3,645 {nameplate_period} of REO as a high purity mixed rare earth carbonate.', fontsize=9)
            mix = doc.new_page()
            mix.insert_text((70, 50), 'The distribution of rare earths in mixed carbonate product is shown in Table 6.')
            mix.insert_text((70, 90), 'Table 6: Average REO Distribution and Basket Price.')
            mix.insert_text((160, 125), 'Distribution in Mixed REE Carbonate (%)')
            rows = {}
            for y, label, token in [(160, 'Pr6O11', '4.24%'), (185, 'Nd2O3', '14.93%'), (210, 'Total', '100%')]:
                mix.insert_text((70, y), label)
                mix.insert_text((220, y), token)
                mix.insert_text((450, y), '3.60')
                rows[label] = dict(row_bbox=[64, y - 14, 490, y + 5],
                                   label_bbox=[65, y - 14, 145, y + 5], original_token=token)
            doc.save(self.pdf)
        sha = filehash(self.pdf)
        review = dict(source_sha256=sha, effective_date='2013-04-15', statement_id='study',
                      scope='study nameplate for contained oxides in mixed carbonate', locator='forecast tables',
                      obs_id='study-observation', review_id='study-review')
        annual_evidence = dict(page=1, markers=['Annual Production', 'Mixed Carbonate', '3,645'])
        rate = dict(column=self.rules['annual_columns'][0], source_sha256=sha,
                    study_date=review['effective_date'], product_basis='REO_EQUIVALENT_IN_MIXED_CARBONATE',
                    annual_basis='EXPLICIT_TPA_NAMEPLATE_NOT_LOM_AVERAGE', scope_relation=review['scope'],
                    original_unit='tpa', original_token='3,645', value=3645, source_stated=True,
                    row_bbox=[65, 64, 448, 85], bbox=[375, 64, 413, 85], page=1,
                    row_text='Annual Production - REO Contained in Mixed Carbonate 3,645 tpa')
        spec = dict(
            **{key: review[key] for key in ('source_sha256', 'scope', 'statement_id', 'effective_date')},
            method=NAMEPLATE_NDPR_METHOD, assurance='MODEL_ASSUMPTION_DERIVED_NOT_DIRECT_REPORTED_OUTPUT',
            rate=rate, capacity=dict(evidence=dict(page=2, markers=['nameplate', '3,645']), bbox=[65, 64, 540, 85]),
            composition=dict(evidence=dict(page=3, markers=['Average REO Distribution', '14.93%']),
                             context_bbox=[65, 34, 525, 55], title_bbox=[65, 75, 420, 95],
                             header_bbox=[155, 110, 395, 130], column_bbox=[150, 109, 405, 220], rows=rows),
            rounding_interval_tpa=[698.2862, 699.2069],
        )
        review['engineering_forecast'] = dict(
            endpoint='MIXED_REE_CARBONATE', scale='SCOPING_MODEL', element='TREO',
            annual_basis_evidence=annual_evidence, parameters={PARAMETER: 698.7465},
            parameter_derivations={PARAMETER: spec},
        )
        return review, spec

    def project(self, review):
        audit = []
        fills = summary_forecasts('project', [], [review], {review['source_sha256']: {'resolved_path': self.pdf}},
                                  self.rules, self.decisions, '2026-11-13',
                                  row={'開發階段代碼': 'B1'}, audit=audit)
        return [fill for fill in fills if fill['column'] == NDPR], audit

    def test_projects_scoped_nameplate_ndpr(self):
        review, _ = self.make_forecast()
        fills, audit = self.project(review)
        self.assertFalse(audit)
        self.assertEqual([698.7465], [fill['value'] for fill in fills])
        self.assertEqual('MODEL_ASSUMPTION_DERIVED_NAMEPLATE_NDPR_NOT_OPERATING_OUTPUT', fills[0]['method'])

    def test_rejects_rate_fraction_and_period_changes(self):
        review, _ = self.make_forecast()
        for key, value, reason in [
            ('value', 3500, 'ANNUAL_TOKEN_VALUE_MISMATCH'),
            ('annual_basis', 'LOM_TOTAL_TONNES', 'NAMEPLATE_NDPR_ANNUAL_RATE_SCOPE_MISMATCH'),
        ]:
            with self.subTest(key=key):
                modified = copy.deepcopy(review)
                modified['engineering_forecast']['parameter_derivations'][PARAMETER]['rate'][key] = value
                fills, audit = self.project(modified)
                self.assertEqual([], fills)
                self.assertEqual(reason, audit[0]['detail'])
        modified = copy.deepcopy(review)
        modified['engineering_forecast']['parameter_derivations'][PARAMETER]['composition']['rows']['Pr6O11']['original_token'] = '3.60%'
        fills, audit = self.project(modified)
        self.assertEqual([], fills)
        self.assertEqual('NAMEPLATE_NDPR_OXIDE_SHARE_MISMATCH', audit[0]['detail'])

    def test_rejects_nonannual_capacity_text(self):
        review, _ = self.make_forecast(nameplate_period='t per month')
        fills, audit = self.project(review)
        self.assertEqual([], fills)
        self.assertEqual('NAMEPLATE_NDPR_CAPACITY_PERIOD_OR_PRODUCT_MISMATCH', audit[0]['detail'])
