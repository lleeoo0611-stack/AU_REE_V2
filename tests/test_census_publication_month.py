import unittest
from pathlib import Path

from au_ree_v2.acquisition import census_admission


class PublicationMonthTests(unittest.TestCase):
    def test_month_precision_uses_last_day_even_when_snapshot_records_first_day(self):
        source = dict(key='march', kind='pdf', sha256='sha', publication_date='2026-03-01')
        registered = dict(source_sha256='sha', publication_date='2026-03-01',
                          publication_date_precision='month', publication_date_interval=['2026-03-01', '2026-03-31'])
        def admit(cutoff, registry=registered):
            return census_admission(Path('.'), source, registry, {}, cutoff)
        self.assertEqual(admit('2026-03-15')['cutoff_status'], 'SOURCE_AFTER_CUTOFF')
        self.assertEqual(admit('2026-03-31')['cutoff_status'], 'WITHIN_CUTOFF')
        self.assertEqual(admit('2026-11-13')['date_used'], '2026-03-31')
        wrong = dict(registered, publication_date_interval=['2026-02-01', '2026-02-28'])
        self.assertEqual(admit('2026-11-13', wrong)['cutoff_status'], 'SOURCE_PUBLICATION_DATE_MISMATCH')

