import unittest
from unittest.mock import patch

import pymupdf

from au_ree_v2.technical import verify_forecast_concentrate_share


class ConcentrateForecastShareTests(unittest.TestCase):
    def setUp(self):
        self.pdf = pymupdf.open()
        self.addCleanup(self.pdf.close)
        page = self.pdf.new_page()
        for x, y, text in [
            (60, 70, 'Praseodymium 0.3%'), (60, 90, 'Neodymium 1.7%'),
            (320, 70, 'Praseodymium 0.3%'), (320, 90, 'Neodymium 1.8%'),
            (60, 140, 'REO Assemblage1'), (320, 140, 'Basket Value2'),
            (40, 200, 'Figure 42 Browns Range concentrate expected REO assemblage and basket value'),
            (40, 250, 'Based on DFS expected process plant recoveries of individual REOs in concentrate.'),
        ]:
            page.insert_text((x, y), text, fontsize=10)
        self.study = dict(endpoint='MINERAL_CONCENTRATE', selected_scenario='Value1,2',
                          parameters={'average_annual_treo_product_t': 4350},
                          parameter_bindings={'average_annual_treo_product_t': {'original_unit': 'tpa'}})
        self.spec = dict(page=1, share_basis='DFS_EXPECTED_RECOVERED_REO_IN_CONCENTRATE',
                         composition_label_bbox=[55, 125, 160, 145], price_label_bbox=[315, 125, 425, 145],
                         shares_bbox=[55, 55, 164, 96], oxide_share_percent={'Pr': 0.3, 'Nd': 1.7},
                         contained_treo_tpa=4350)

    def verify(self, spec, value):
        with patch('au_ree_v2.technical.summary_annual_cell') as rate:
            verify_forecast_concentrate_share(self.pdf, {'scope': 'Wolverine'}, self.study, spec,
                                              'average_annual_ndpr_product_t', value)
            rate.assert_called_once()

    def test_concentrate_mass_shares(self):
        self.verify(self.spec, 87)

    def test_rejects_price_weights_and_gross_concentrate_tonnage(self):
        for changed, value, reason in [
            ({'shares_bbox': [315, 55, 424, 96]}, 91.35, 'MASS_OR_PRICE'),
            ({'contained_treo_tpa': 17500}, 350, 'CONTAINED_TREO_RATE'),
            ({'oxide_share_percent': {'Pr': 0.3, 'Nd': 1.8}}, 91.35, 'CALCULATION'),
        ]:
            with self.subTest(reason=reason), self.assertRaisesRegex(ValueError, reason):
                self.verify(dict(self.spec, **changed), value)
