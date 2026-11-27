"""Review regressions that use immutable PDFs and the live canonical selector."""

from contextlib import closing
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import pymupdf

from au_ree_v2.evidence import claim_evidence_ids, ingest_claims, ingest_sources, resource_values
from au_ree_v2.formal_resource_admission import admit
from au_ree_v2.store import connect, digest, filehash


ROOT = Path(__file__).resolve().parents[1]
PROJECT = 'Synthetic Alpha Project'
PROJECT_ID = 'AU-' + digest(['project_registry_v1', 'alpha'])[:20]
FIXTURE_CLASS = 'SYNTHETIC_ENGINEERING_FIXTURE'
EFFECTIVE_DATE = '2025-05-01'
CUTOFF = '2026-11-05'


def resource_page(*, number=2, qualifier='JORC', date=EFFECTIVE_DATE, cutoff='500 ppm', notes=(),
                  total=('50', '2,000', '100,000'), grade_unit='ppm'):
    caption = f'Table {number}: {PROJECT} Total {qualifier} Mineral Resource estimate effective {date} at {cutoff} TREO cut-off'
    return {'caption': ' '.join(caption.split()), 'notes': notes, 'total': total, 'grade_unit': grade_unit}


def original(root, *pages):
    path = root / 'synthetic-review.pdf'
    with pymupdf.open() as document:
        for index, entry in enumerate(pages, 1):
            page = document.new_page(width=840, height=520)
            page.insert_text((42, 30), 'SYNTHETIC ENGINEERING REVIEW DOCUMENT', fontsize=11)
            page.insert_text((42, 102), entry['caption'], fontsize=9)
            # Single blocks model notes tied to a named table, rather than a PDF-wide
            # bag of keywords. All glyphs occupy physical coordinates outside the grid.
            for number, note in enumerate(entry['notes']):
                page.insert_text((42, 121 + 14 * number), note, fontsize=9)
            mass, grade, contained = entry['total']
            ore = float(mass.replace(',', ''))
            tonnes = float(contained.replace(',', ''))
            grid = (
                ('Classification', 'Dry ore tonnage (Mt)',
                 f'Total Rare Earth Oxides (TREO) ({entry["grade_unit"]})', 'Contained TREO (t)'),
                ('Indicated', f'{0.4 * ore:.2f}', grade, f'{0.4 * tonnes:,.0f}'),
                ('Inferred', f'{0.6 * ore:.2f}', grade, f'{0.6 * tonnes:,.0f}'),
                ('Total', *entry['total']),
            )
            columns = [40, 175, 335, 590, 775]
            rows = [142, 167, 192, 217, 242]
            for x in columns:
                page.draw_line((x, rows[0]), (x, rows[-1]))
            for y in rows:
                page.draw_line((columns[0], y), (columns[-1], y))
            for y, row in zip(rows, grid):
                for x, cell in zip(columns, row):
                    page.insert_text((x + 5, y + 16), cell, fontsize=10)
            page.insert_text((42, 480), f'{PROJECT} Mineral Resource Report Page {index} of {len(pages)}', fontsize=9)
        document.save(path, no_new_id=True)
    return {'path': path.name, 'sha256': filehash(path), 'key': 'synthetic-resource-review', 'kind': 'pdf',
            'url': 'https://example.invalid/synthetic-resource-review.pdf', 'summary_project_ids': [PROJECT_ID],
            'publication_date': '2025-06-01', 'available_date': '2025-06-01',
            'acquired_at': '2025-06-01T00:00:00+00:00', 'case_classification': FIXTURE_CLASS}


def legacy_pair(source, cutoff, *, basis='TREO'):
    fields = {'basis': 'TREO', 'scope': PROJECT, 'statement_id': 'synthetic-reviewed-alpha-2025',
              'category': 'INDICATED_INFERRED_TOTAL', 'effective_date': EFFECTIVE_DATE,
              'source_key': source['key'], 'source_sha256': source['sha256'],
              'locator': 'Physical PDF page 1 Table 2, total row', 'pdf_page': 1,
              'page_markers': ['Table 2:', 'Total', '7.3', '0.96'],
              'scope_coverage': 'PROJECT_TOTAL', 'material_basis': 'RESOURCE_BULK_ORE',
              'composition_denominator_basis': 'RESOURCE_BULK_ORE_MASS',
              'resource_type': 'MINERAL_RESOURCE', 'reporting_standard': 'JORC',
              'cutoff_grade': f'{cutoff} {basis}'}
    return [dict(fields, variable='ore_mt', value=7.3, unit='Mt', rounding_half_width=0.05),
            dict(fields, variable='grade', value=0.96, unit='%', rounding_half_width=0.005)]


def run_fixture(root, pages, *, legacy_cutoff=None, legacy_cutoff_basis='TREO', tamper=False,
                previously_active_pages=()):
    (root / 'config').symlink_to(ROOT / 'config', target_is_directory=True)
    source = original(root, *pages)
    historical = legacy_pair(source, legacy_cutoff, basis=legacy_cutoff_basis) if legacy_cutoff is not None else []
    claims = {'projects': [{'id': 'alpha', 'name': PROJECT, 'aliases': [PROJECT], 'state': 'WA',
                            'identity_source': source['key'], 'observations': historical}]}
    selected_shas = {source['sha256']}
    with closing(connect(':memory:')) as db:
        ingest_sources(db, root, [source])
        ingest_claims(db, root, [source], CUTOFF, conflict_selection=True, claims_data=claims)
        active_claims = claim_evidence_ids(claims)
        prior = admit(db, root, [source], CUTOFF, {source['sha256']: previously_active_pages}, claims_data=claims,
                      classification=FIXTURE_CLASS) if previously_active_pages else {}
        before = resource_values(db, CUTOFF, selected_shas, strict=True, active_claim_ids=active_claims,
                                 admitted_resource_ids=prior.get('active_admission_observation_ids', []))
        if tamper:
            with (root / source['path']).open('ab') as stream:
                stream.write(b'\n% changed source edition\n')
        physical_pages = list(range(1, len(pages) + 1))
        receipt = admit(db, root, [source], CUTOFF, {source['sha256']: physical_pages}, claims_data=claims,
                        classification=FIXTURE_CLASS, context_pages_by_sha={source['sha256']: physical_pages})
        audit = []
        after = resource_values(db, CUTOFF, selected_shas, strict=True, active_claim_ids=active_claims,
                                scope_audit=audit, admitted_resource_ids=receipt['active_admission_observation_ids'])
        canonical = [dict(row) for row in db.execute('SELECT * FROM observations ORDER BY obs_id')]
    return source, receipt, before, after, audit, canonical


def total_disposition(receipt, page=1):
    rows = [row for row in receipt['dispositions'] if row['physical_page'] == page and row['row'] == 3]
    if len(rows) != 1:
        raise AssertionError(f'Expected one physical total row on page {page}: {rows!r}')
    return rows[0]


class ResourceAdmissionReviewPdfTests(unittest.TestCase):
    def run_pdf(self, *pages, **kwargs):
        with TemporaryDirectory(prefix='au-ree-review-pdf-') as temporary:
            return run_fixture(Path(temporary), pages, **kwargs)

    def check_jorc(self, row, source, status, *, required_polarities=()):
        assessment = row['jorc_assessment']
        self.assertEqual(assessment['status'], status, row['reasons'])
        subject = assessment['subject']
        for field in ('project_id', 'estimate_id', 'statement_id', 'physical_page', 'table', 'row'):
            self.assertEqual(subject[field], row[field])
        self.assertEqual(subject['project_id'], PROJECT_ID)
        witnesses = [entry for entry in assessment['evidence'] if entry['applicability'] == 'TARGET']
        self.assertTrue(set(required_polarities) <= {entry['polarity'] for entry in witnesses}, witnesses)
        for entry in witnesses:
            self.assertEqual(entry['source_sha256'], source['sha256'])
            self.assertTrue(entry['quote'])
            self.assertGreater(entry['physical_page'], 0)
            self.assertEqual(len(entry['bbox']), 4)
        return witnesses

    def test_explicit_current_denials_do_not_create_jorc_observations(self):
        cases = (
            resource_page(qualifier='non-JORC'),
            resource_page(qualifier='not JORC-compliant'),
            resource_page(qualifier='JORC (not compliant)'),
            resource_page(qualifier='no longer JORC-compliant'),
            resource_page(qualifier='not fully JORC-compliant'),
            resource_page(qualifier='', notes=(
                'The Mineral Resource estimate in Table 2 was not reported in accordance with the guidelines of JORC.',)),
            resource_page(qualifier='', notes=(
                'The Mineral Resource estimate in Table 2 does not meet the requirements of JORC.',)),
            resource_page(qualifier='', notes=(
                "The current Mineral Resource estimate in Table 2 doesn't comply with JORC.",)),
            resource_page(qualifier='', notes=(
                'The earlier Mineral Resource estimate in Table 1 was reported in accordance with JORC; '
                'the current estimate in Table 2 is not compliant.',)),
        )
        for page in cases:
            with self.subTest(page['caption'], notes=page['notes']):
                source, receipt, _, selected, _, canonical = self.run_pdf(page)
                row = total_disposition(receipt)
                self.assertEqual(receipt['source_dispositions'][0]['status'], 'SOURCE_CHECKED')
                self.assertEqual(len(row['observations']), 3)
                self.assertTrue(all(item['numeric_and_unit_located'] for item in row['observations']))
                self.assertEqual(row['status'], 'NOT_ADMITTED')
                self.assertIn('RESOURCE_JORC_NEGATED', row['reasons'])
                self.check_jorc(row, source, 'DENIED', required_polarities=('DENIED',))
                self.assertEqual(canonical, [])
                self.assertEqual(selected, {})

    def test_independent_current_jorc_passes_in_report_with_old_non_jorc(self):
        earlier = resource_page(number=1, qualifier='non-JORC', date='2024-05-01')
        current = resource_page()
        source, receipt, _, selected, _, canonical = self.run_pdf(earlier, current)
        self.check_jorc(total_disposition(receipt, 1), source, 'DENIED', required_polarities=('DENIED',))
        self.check_jorc(total_disposition(receipt, 2), source, 'AFFIRMED', required_polarities=('AFFIRMED',))
        self.assertTrue(canonical and len(canonical) == 3)
        self.assertTrue(all(json.loads(row['raw'])['pdf_page'] == 2 for row in canonical))
        self.assertEqual(selected[PROJECT_ID]['date'], EFFECTIVE_DATE)
        self.assertEqual(selected[PROJECT_ID]['contained_treo_kt'], 100)

    def test_future_reporting_statement_does_not_supply_current_jorc(self):
        page = resource_page(qualifier='', notes=(
            'The Mineral Resource estimate in Table 2 will be reported in accordance with the guidelines of JORC.',))
        _, receipt, _, selected, _, canonical = self.run_pdf(page)
        row = total_disposition(receipt)
        self.assertIn(row['jorc_assessment']['status'], ('UNESTABLISHED', 'UNRESOLVED_SCOPE'))
        self.assertEqual(canonical, [])
        self.assertEqual(selected, {})

    def test_current_estimate_does_not_borrow_earlier_declaration(self):
        earlier = resource_page(number=1, date='2024-05-01', notes=(
            'The Mineral Resource estimate in Table 1 was reported in accordance with the guidelines of JORC.',))
        current = resource_page(qualifier='')
        source, receipt, _, selected, _, canonical = self.run_pdf(earlier, current)
        self.check_jorc(total_disposition(receipt, 1), source, 'AFFIRMED', required_polarities=('AFFIRMED',))
        row = total_disposition(receipt, 2)
        self.assertEqual(row['status'], 'NOT_ADMITTED')
        self.assertIn(row['jorc_assessment']['status'], ('UNESTABLISHED', 'UNRESOLVED_SCOPE'))
        self.assertTrue(canonical and len(canonical) == 3)
        self.assertTrue(all(json.loads(record['raw'])['pdf_page'] == 1 for record in canonical))
        self.assertEqual(selected[PROJECT_ID]['date'], '2024-05-01')

    def test_conflicting_claims_retain_both_target_witnesses(self):
        page = resource_page(notes=('The Mineral Resource estimate in Table 2 is not JORC-compliant.',))
        source, receipt, _, selected, _, canonical = self.run_pdf(page)
        row = total_disposition(receipt)
        self.assertIn('RESOURCE_JORC_CONFLICT', row['reasons'])
        witnesses = self.check_jorc(row, source, 'CONFLICT', required_polarities=('AFFIRMED', 'DENIED'))
        self.assertEqual({item['physical_page'] for item in witnesses}, {1})
        self.assertEqual(len({tuple(item['bbox']) for item in witnesses}), 2)
        self.assertEqual(canonical, [])
        self.assertEqual(selected, {})

    def test_adjacent_denial_cannot_be_ignored_when_scope_is_ambiguous(self):
        for note in ('Not reported in accordance with the guidelines of JORC.',
                     'This Mineral Resource estimate does not comply with JORC.'):
            with self.subTest(note=note):
                source, receipt, _, selected, _, canonical = self.run_pdf(resource_page(notes=(note,)))
                row = total_disposition(receipt)
                assessment = row['jorc_assessment']
                self.assertIn(assessment['status'], ('UNRESOLVED_SCOPE', 'CONFLICT'))
                self.assertTrue(any(w['polarity'] == 'AFFIRMED' and w['applicability'] == 'TARGET'
                                    for w in assessment['evidence']))
                self.assertTrue(any(w['polarity'] == 'DENIED' and w['source_sha256'] == source['sha256']
                                    and w['quote'] == note and w['physical_page'] == 1 and w['bbox']
                                    for w in assessment['evidence']))
                self.assertEqual(row['status'], 'NOT_ADMITTED')
                self.assertEqual(canonical, [])
                self.assertEqual(selected, {})

    def test_negation_of_material_change_or_reserve_does_not_deny_jorc(self):
        for note in ('There has been no material change to the JORC Mineral Resource estimate in Table 2.',
                     'The JORC Mineral Resource estimate in Table 2 has not been converted to an Ore Reserve.'):
            with self.subTest(note=note):
                source, receipt, _, selected, _, canonical = self.run_pdf(resource_page(notes=(note,)))
                row = total_disposition(receipt)
                self.check_jorc(row, source, 'AFFIRMED', required_polarities=('AFFIRMED',))
                self.assertEqual(len(canonical), 3)
                self.assertEqual(selected[PROJECT_ID]['contained_treo_kt'], 100)

    def test_same_geometry_with_incompatible_cutoff_keeps_old_resource(self):
        incompatible = (('1,000 ppm', 'TREO', '500 ppm', 'value_ppm'),
                        ('500 ppm', 'TREO-CeO2', '500 ppm', 'basis'),
                        ('>=500 ppm', 'TREO', '>500 ppm', 'operator'))
        for legacy_cutoff, legacy_basis, new_cutoff, difference in incompatible:
            with self.subTest(difference=difference):
                page = resource_page(cutoff=new_cutoff, total=('7.3', '0.96', '70,500'), grade_unit='%')
                source, receipt, before, selected, _, canonical = self.run_pdf(
                    page, legacy_cutoff=legacy_cutoff, legacy_cutoff_basis=legacy_basis)
                row = total_disposition(receipt)
                self.assertAlmostEqual(before[PROJECT_ID]['contained_treo_kt'], 70.08)
                self.assertEqual(selected[PROJECT_ID], before[PROJECT_ID])
                self.assertEqual(row['status'], 'NOT_ADMITTED')
                self.assertNotIn('historical_link', row)
                rejected = row['historical_match_rejected']
                self.assertEqual(rejected['reason'], 'HISTORICAL_ESTIMATE_CONTEXT_MISMATCH')
                old_ids = set(before[PROJECT_ID]['obs_ids'])
                self.assertEqual({item['observation_id'] for item in rejected['historical_observations']}, old_ids)
                for item in rejected['historical_observations']:
                    self.assertEqual(item['source_sha256'], source['sha256'])
                    self.assertEqual(item['physical_page'], 1)
                    self.assertIn('Table 2', item['locator'])
                for check in rejected['equivalence']:
                    issues = [issue for issue in check['issues'] if issue['dimension'] == 'cutoff_grade']
                    self.assertEqual(len(issues), 1, check)
                    self.assertNotEqual(issues[0]['left'][difference], issues[0]['right'][difference])
                self.assertEqual({record['obs_id'] for record in canonical}, old_ids)

    def test_equivalent_cutoff_units_preserve_same_estimate_and_old_ids(self):
        page = resource_page(cutoff='0.1%', total=('7.3', '0.96', '70,500'), grade_unit='%')
        _, receipt, before, selected, audit, canonical = self.run_pdf(page, legacy_cutoff='1,000 ppm')
        self.assertEqual(receipt['counts']['canonical_added'], 1)
        row = total_disposition(receipt)
        link = row['historical_link']
        self.assertEqual(sorted(link['reused_observation_ids']), sorted(before[PROJECT_ID]['obs_ids']))
        for comparison in link['estimate_equivalence']:
            self.assertEqual(comparison['status'], 'EQUIVALENT')
            original, new = (comparison[side]['cutoff_grade'] for side in ('left', 'right'))
            self.assertEqual(original['value_ppm'], new['value_ppm'])
            self.assertEqual(new['conversion'], 'percent × 10000 = ppm')
        self.assertEqual(selected[PROJECT_ID]['statement_id'], before[PROJECT_ID]['statement_id'])
        self.assertEqual(selected[PROJECT_ID]['obs_ids'][:2], before[PROJECT_ID]['obs_ids'])
        self.assertEqual(selected[PROJECT_ID]['contained_treo_kt'], 70.5)
        self.assertEqual(len(canonical), 3)
        self.assertIn('SELECTED', {entry['reason'] for entry in audit})

    def test_genuine_same_scope_conflict_records_both_sides_on_selection_exit(self):
        conflicting = resource_page(number=3, total=('60', '2,000', '120,000'))
        source, receipt, before, selected, audit, canonical = self.run_pdf(
            resource_page(), conflicting, previously_active_pages=(1,))
        self.assertEqual(before[PROJECT_ID]['contained_treo_kt'], 100)
        self.assertNotIn(PROJECT_ID, selected)
        self.assertEqual(len(canonical), 6)
        self.assertEqual(receipt['counts']['canonical_reused'], 3)
        conflict = [entry for entry in audit if entry['reason'] == 'CONCURRENT_SOURCE_CONFLICT']
        self.assertTrue(conflict, audit)
        ids = {identity for entry in conflict for identity in json.loads(entry['observation_ids'])}
        self.assertEqual(ids, {row['obs_id'] for row in canonical})
        locations = {location['observation_id']: location for entry in conflict
                     for location in json.loads(entry['evidence_locations'])}
        self.assertEqual({loc['physical_page'] for loc in locations.values()}, {1, 2})
        for row in canonical:
            self.assertEqual(locations[row['obs_id']]['locator'], row['locator'])
            self.assertEqual(locations[row['obs_id']]['source_sha256'], source['sha256'])

    def test_pinned_source_sha_is_rechecked_before_admission(self):
        _, receipt, _, selected, _, canonical = self.run_pdf(resource_page(), tamper=True)
        self.assertEqual(receipt['source_dispositions'][0]['reason'], 'SOURCE_HASH_MISMATCH')
        self.assertEqual(receipt['dispositions'], [])
        self.assertEqual(canonical, [])
        self.assertEqual(selected, {})


if __name__ == '__main__':
    unittest.main()
