"""Review regressions that use immutable PDFs and the live canonical selector."""

from contextlib import closing
from dataclasses import replace
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest

import pymupdf

from au_ree_v2.evidence import claim_evidence_ids, ingest_claims, ingest_sources, resource_values
from au_ree_v2.formal_resource_admission import _group_context, admit
from au_ree_v2.observation_schema import raw_from_payload
from au_ree_v2.store import connect, digest, filehash


ROOT = Path(__file__).resolve().parents[1]
PROJECT = 'Synthetic Alpha Project'
PROJECT_ID = 'AU-' + digest(['project_registry_v1', 'alpha'])[:20]
FIXTURE_CLASS = 'SYNTHETIC_ENGINEERING_FIXTURE'
EFFECTIVE_DATE = '2025-05-01'
CUTOFF = '2026-11-05'
SCOPE_OPENING = (f'For the {PROJECT} Mineral Resource estimate in Table 2, '
                 f'50 Mt at 2,000 ppm TREO, effective {EFFECTIVE_DATE}.')
EARLIER_DRY_STATEMENT = 'For the earlier estimate, tonnages are reported on a dry basis.'
JORC_OPENING = 'The Mineral Resource estimate in Table 2 is JORC compliant. No change.'
JORC_DENIAL = 'It is not compliant.'

JORC_PROPOSITIONS = (
    ('negated_consideration', 'DENIED',
     'The Mineral Resource estimate in Table 2 is not considered JORC compliant.'),
    ('named_subject_with_negation', 'DENIED',
     'The JORC Mineral Resource estimate in Table 2 is not compliant.'),
    ('named_subject_no_longer', 'DENIED',
     'The JORC Mineral Resource estimate in Table 2 is no longer compliant.'),
    ('negated_modal_passive', 'DENIED',
     'The Mineral Resource estimate in Table 2 cannot be considered JORC compliant.'),
    ('negated_modal_contraction', 'DENIED',
     "The Mineral Resource estimate in Table 2 can't be considered JORC compliant."),
    ('affirmative_reporting_passive', 'AFFIRMED',
     'The Mineral Resource estimate in Table 2 was reported in accordance with JORC.'),
    ('denied_compliance_direct', 'DENIED',
     'The Mineral Resource estimate in Table 2 is not compliant with JORC.'),
    ('denied_reporting_passive', 'DENIED',
     'The Mineral Resource estimate in Table 2 was not reported in accordance with JORC.'),
    ('affirmative_consideration', 'AFFIRMED',
     'The Mineral Resource estimate in Table 2 is considered JORC compliant.'),
    ('negated_consideration_with_contraction_and_modifier', 'DENIED',
     "The Mineral Resource estimate in Table 2 isn't considered fully JORC-compliant."),
    ('negated_consideration_with_adverb', 'DENIED',
     'The Mineral Resource estimate in Table 2 is not independently considered JORC compliant.'),
    ('negated_predicate_with_parenthetical', 'DENIED',
     'The Mineral Resource estimate in Table 2 is not, in the report opinion, considered JORC compliant.'),
    ('affirmative_despite_unrelated_parenthetical_negation', 'AFFIRMED',
     'The Mineral Resource estimate in Table 2 is, despite not being audited, considered JORC compliant.'),
    ('negated_qualified_nominal_predicate', 'DENIED',
     'The Mineral Resource estimate in Table 2 is not a JORC-compliant estimate.'),
    ('affirmative_named_subject', 'AFFIRMED',
     'The JORC Mineral Resource estimate in Table 2 is fully compliant.'),
    ('name_mention_in_unrelated_proposition', 'WITHHOLD',
     'The JORC Mineral Resource estimate in Table 2 has not been converted to an Ore Reserve.'),
    ('modal_compliance', 'WITHHOLD',
     'The Mineral Resource estimate in Table 2 may be considered JORC compliant.'),
    ('conditional_compliance', 'WITHHOLD',
     'The Mineral Resource estimate in Table 2 would be JORC compliant if the work were completed.'),
    ('affirmative_cross_sentence_reference', 'AFFIRMED',
     'The report presents the Mineral Resource estimate in Table 2. It was reported in accordance with JORC.'),
    ('negated_cross_sentence_reference', 'DENIED',
     'The report presents the Mineral Resource estimate in Table 2. It cannot be considered JORC compliant.'),
    ('conflicting_after_neutral_sentence', 'CONFLICT',
     'The Mineral Resource estimate in Table 2 is JORC compliant. No change. It is not compliant.'),
    ('affirmative_after_neutral_sentence', 'AFFIRMED',
     'The report presents the Mineral Resource estimate in Table 2. Details remain unchanged. It is JORC compliant.'),
)


def resource_page(*, number=2, qualifier='JORC', date=EFFECTIVE_DATE, cutoff='500 ppm', notes=(),
                  total=('50', '2,000', '100,000'), grade_unit='ppm', material_header='Dry ore tonnage (Mt)',
                  chemical_header=None, competing_total=None):
    caption = f'Table {number}: {PROJECT} Total {qualifier} Mineral Resource estimate'
    if date:
        caption += f' effective {date}'
    if cutoff:
        caption += f' at {cutoff} TREO cut-off'
    chemical_header = chemical_header or f'Total Rare Earth Oxides (TREO) ({grade_unit})'
    return {'caption': ' '.join(caption.split()), 'notes': notes, 'total': total,
            'material_header': material_header, 'chemical_header': chemical_header, 'competing_total': competing_total}


def narrative_page(quote='Project infrastructure and site logistics update.'):
    return {'narrative': quote}


def external_estimate_context(*, date=EFFECTIVE_DATE, mass='50', grade='2,000'):
    return narrative_page(f'For the {PROJECT} Mineral Resource estimate in Table 2, {mass} Mt at {grade} ppm TREO, '
                          f'effective {date}. Tonnages are reported on a dry basis. TREO means Total Rare Earth Oxides. '
                          'The estimate uses a cut-off grade of 500 ppm TREO.')


def original(root, *pages):
    path = root / 'synthetic-review.pdf'
    with pymupdf.open() as document:
        for index, entry in enumerate(pages, 1):
            page = document.new_page(width=840, height=520)
            page.insert_text((42, 30), 'SYNTHETIC ENGINEERING REVIEW DOCUMENT', fontsize=11)
            page_footer = f'{PROJECT} Mineral Resource Report Page {index} of {len(pages)}'
            if 'narrative' in entry:
                page.insert_textbox((42, 102, 790, 400), entry['narrative'], fontsize=9)
                page.insert_text((42, 480), page_footer, fontsize=9)
                continue
            page.insert_text((42, 102), entry['caption'], fontsize=9)
            # Single blocks model notes tied to a named table, rather than a PDF-wide
            # bag of keywords. All glyphs occupy physical coordinates outside the grid.
            for number, note in enumerate(entry['notes']):
                page.insert_text((42, 121 + 14 * number), note, fontsize=9)
            grid = entry.get('native_grid')
            if grid is None:
                mass, grade, contained = entry['total']
                ore = float(mass.replace(',', ''))
                tonnes = float(contained.replace(',', ''))
                grid = (
                    ('Classification', entry['material_header'], entry['chemical_header'], 'Contained TREO (t)'),
                    ('Indicated', f'{0.4 * ore:.2f}', grade, f'{0.4 * tonnes:,.0f}'),
                    ('Inferred', f'{0.6 * ore:.2f}', grade, f'{0.6 * tonnes:,.0f}'),
                    ('Total', *entry['total']),
                )
                if entry['competing_total']:
                    grid += (('Total', *entry['competing_total']),)
            columns = [40, 175, 335, 590, 775]
            rows = [142 + 25 * number for number in range(len(grid) + 1)]
            for column, x in enumerate(columns):
                top = rows[1] if entry.get('merged_first_row') and 0 < column < len(columns) - 1 else rows[0]
                page.draw_line((x, top), (x, rows[-1]))
            for y in rows:
                page.draw_line((columns[0], y), (columns[-1], y))
            for y, row in zip(rows, grid):
                for x, cell in zip(columns, row):
                    page.insert_text((x + 5, y + 16), cell, fontsize=10)
            for number, note in enumerate(entry.get('notes_below_table', ())):
                page.insert_text((43, rows[-1] + 17 + 14 * number), note, fontsize=9)
            page.insert_text((42, 480), page_footer, fontsize=9)
        document.save(path, no_new_id=True)
    return fixture_source(path.name, filehash(path))


def fixture_source(path, sha256):
    return {'path': str(path), 'sha256': sha256, 'key': 'synthetic-resource-review', 'kind': 'pdf',
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
                previously_active_pages=(), value_pages=None, context_pages=None, other_project=None,
                pinned_source=None, historical_automatic=()):
    (root / 'config').symlink_to(ROOT / 'config', target_is_directory=True)
    source = pinned_source if pinned_source is not None else original(root, *pages)
    historical = legacy_pair(source, legacy_cutoff, basis=legacy_cutoff_basis) if legacy_cutoff is not None else []
    claims = {'projects': [{'id': 'alpha', 'name': PROJECT, 'aliases': [PROJECT], 'state': 'WA',
                            'identity_source': source['key'], 'observations': historical}]}
    if other_project:
        claims['projects'].append({'id': 'beta', 'name': other_project, 'aliases': [other_project], 'state': 'WA',
                                   'identity_source': source['key'], 'observations': []})
    selected_shas = {source['sha256']}
    with closing(connect(':memory:')) as db:
        ingest_sources(db, root, [source])
        ingest_claims(db, root, [source], CUTOFF, conflict_selection=True, claims_data=claims)
        if historical_automatic:
            if any(row['source_sha'] != source['sha256'] or row['entity_id'] != PROJECT_ID
                   or not row['transform_version'].startswith('automatic-resource-admission-v')
                   for row in historical_automatic):
                raise ValueError('Historical observations do not belong to the pinned fixture')
            db.executemany('''INSERT INTO observations (obs_id, entity_id, variable, value, unit, basis,
                              scope, statement_id, category, effective_date, source_sha, locator, status, issues,
                              raw, transform_version) VALUES (:obs_id, :entity_id, :variable, :value, :unit, :basis,
                              :scope, :statement_id, :category, :effective_date, :source_sha, :locator, :status,
                              :issues, :raw, :transform_version)''', historical_automatic)
        active_claims = claim_evidence_ids(claims)
        prior = admit(db, root, [source], CUTOFF, {source['sha256']: previously_active_pages}, claims_data=claims,
                      classification=FIXTURE_CLASS) if previously_active_pages else {}
        before = resource_values(db, CUTOFF, selected_shas, strict=True, active_claim_ids=active_claims,
                                 admitted_resource_ids=prior.get('active_admission_observation_ids', []))
        if tamper:
            with (root / source['path']).open('ab') as stream:
                stream.write(b'\n% changed source edition\n')
        physical_pages = value_pages if value_pages is not None else list(range(1, len(pages) + 1))
        supporting_pages = context_pages if context_pages is not None else physical_pages
        receipt = admit(db, root, [source], CUTOFF, {source['sha256']: physical_pages}, claims_data=claims,
                        classification=FIXTURE_CLASS, context_pages_by_sha={source['sha256']: supporting_pages})
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


def proposition_replay():
    """Run the same SHA-pinned fixtures with whichever package PYTHONPATH selects."""
    cases = {}
    for name, expected, note in JORC_PROPOSITIONS:
        with TemporaryDirectory(prefix='au-ree-proposition-replay-') as temporary:
            source, receipt, _, selected, audit, canonical = run_fixture(
                Path(temporary), (resource_page(qualifier='', notes=(note,)),))
        row = total_disposition(receipt)
        cases[name] = {'text': note, 'expected': expected, 'source_sha256': source['sha256'],
                       'source_check': receipt['source_dispositions'][0], 'admission_rules_sha256': receipt['rules_sha256'],
                       'admission_status': row['status'], 'reasons': row['reasons'], 'jorc_assessment': row['jorc_assessment'],
                       'new_canonical_observations': receipt['counts']['canonical_added'],
                       'canonical_observations': [
                           {**{key: value[key] for key in ('obs_id', 'value', 'unit', 'variable', 'locator', 'source_sha')},
                            'reporting_standard': json.loads(value['raw']).get('reporting_standard')}
                           for value in canonical],
                       'selected_resource': selected.get(PROJECT_ID), 'selection_audit': audit}
    return {'classification': FIXTURE_CLASS, 'cutoff': CUTOFF, 'project_id': PROJECT_ID, 'cases': cases}


def prep_scope_replay(directory):
    """Generate each original once. Both code revisions replay this manifest."""
    directory.mkdir(parents=True)
    fixtures = {
        'earlier_estimate_dry_basis': (resource_page(material_header='Ore tonnage (Mt)'),
                                      narrative_page(), narrative_page(), narrative_page(),
                                      narrative_page(f'{SCOPE_OPENING} {EARLIER_DRY_STATEMENT}')),
        'jorc_denial_in_next_block': (resource_page(qualifier='', notes=(JORC_OPENING, JORC_DENIAL)),),
    }
    cases = {}
    for name, pages in fixtures.items():
        folder = directory / name
        folder.mkdir()
        source = original(folder, *pages)
        cases[name] = {'path': f'{name}/{source["path"]}', 'sha256': source['sha256'],
                       'value_pages': [1], 'context_pages': [5] if len(pages) > 1 else []}
    manifest = directory / 'scope-fixtures.json'
    manifest.write_text(json.dumps(cases, indent=2) + '\n', encoding='utf-8')


def scope_replay(manifest, prior_receipt=None):
    """Run the actual canonical/selection workflow against a saved original."""
    prior = json.loads(prior_receipt.read_text(encoding='utf-8'))['cases'] if prior_receipt else {}
    cases = {}
    for name, case in json.loads(manifest.read_text(encoding='utf-8')).items():
        pinned = fixture_source((manifest.parent / case['path']).resolve(), case['sha256'])
        history = prior[name]['canonical_observations'] if prior else []
        with TemporaryDirectory(prefix='au-ree-scope-replay-') as temporary:
            source, receipt, _, selected, audit, canonical = run_fixture(
                Path(temporary), (), pinned_source=pinned, value_pages=case['value_pages'],
                context_pages=case['context_pages'], historical_automatic=history)
        row = total_disposition(receipt)
        stored = {value['obs_id']: value for value in canonical}
        cases[name] = {'source_sha256': source['sha256'], 'source_check': receipt['source_dispositions'][0],
                       'admission_rules_sha256': receipt['rules_sha256'], 'disposition': row,
                       'new_canonical_observations': receipt['counts']['canonical_added'],
                       'canonical_observation_ids': sorted(stored), 'canonical_observations': canonical,
                       'historical_observations_retained': [value['obs_id'] for value in history
                                                            if stored.get(value['obs_id']) == value],
                       'active_admission_observation_ids': receipt['active_admission_observation_ids'],
                       'selected_resource': selected.get(PROJECT_ID), 'selection_audit': audit}
    return {'classification': FIXTURE_CLASS, 'cutoff': CUTOFF, 'project_id': PROJECT_ID, 'cases': cases}


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

    def test_jorc_propositions_use_predicates_instead_of_named_subjects(self):
        for name, expected, note in JORC_PROPOSITIONS:
            with self.subTest(name):
                source, receipt, _, selected, _, canonical = self.run_pdf(resource_page(qualifier='', notes=(note,)))
                row = total_disposition(receipt)
                source_receipt = receipt['source_dispositions'][0]
                self.assertEqual(source_receipt['status'], 'SOURCE_CHECKED')
                self.assertTrue(source_receipt['sha_verified'])
                self.assertEqual(len(row['observations']), 3)
                self.assertTrue(all(item['numeric_and_unit_located'] for item in row['observations']))
                if expected == 'WITHHOLD':
                    self.assertIn(row['jorc_assessment']['status'], ('UNESTABLISHED', 'UNRESOLVED_SCOPE'))
                elif expected == 'CONFLICT':
                    witnesses = self.check_jorc(row, source, expected, required_polarities=('AFFIRMED', 'DENIED'))
                    denial = next(item for item in witnesses if item['polarity'] == 'DENIED')
                    self.assertTrue(denial['anaphoric'])
                    self.assertIn('Table 2', note[denial['subject_start']:denial['subject_end']])
                    self.assertEqual(note[denial['predicate_start']:denial['predicate_end']], 'is not compliant')
                else:
                    witnesses = self.check_jorc(row, source, expected, required_polarities=(expected,))
                    statement = next(item for item in witnesses if item['quote'] == note and item['polarity'] == expected)
                    for role in ('subject', 'predicate', 'code'):
                        left, right = (statement[f'{role}_{end}'] for end in ('start', 'end'))
                        self.assertLess(left, right, statement)
                        self.assertTrue(0 <= left < right <= len(note), statement)
                    subject = note[statement['subject_start']:statement['subject_end']]
                    code = note[statement['code_start']:statement['code_end']]
                    self.assertIn('Mineral Resource estimate', subject)
                    self.assertIn('JORC', code)
                    if 'cross_sentence' in name or 'after_neutral_sentence' in name:
                        self.assertTrue(statement['anaphoric'])
                        self.assertLess(statement['subject_end'], statement['predicate_start'])
                if expected == 'AFFIRMED':
                    self.assertEqual(row['status'], 'SOURCE_BOUND_CANONICAL')
                    self.assertEqual(receipt['counts']['canonical_added'], 3)
                    self.assertEqual({json.loads(item['raw'])['reporting_standard'] for item in canonical}, {'JORC'})
                    self.assertEqual(selected[PROJECT_ID]['contained_treo_kt'], 100)
                else:
                    self.assertEqual(row['status'], 'NOT_ADMITTED')
                    if expected == 'DENIED':
                        self.assertIn('RESOURCE_JORC_NEGATED', row['reasons'])
                    self.assertEqual(receipt['counts']['canonical_added'], 0)
                    self.assertEqual(canonical, [])
                    self.assertEqual(selected, {})

    def test_current_proposition_does_not_borrow_earlier_cross_sentence_reference(self):
        earlier = resource_page(number=1, qualifier='', date='2024-05-01', notes=(
            'The report presents the earlier Mineral Resource estimate in Table 1. It was not considered JORC compliant.',))
        current = resource_page(qualifier='', notes=(
            'Table 2 presents the current Mineral Resource estimate. It was reported in accordance with JORC.',))
        source, receipt, _, selected, _, canonical = self.run_pdf(earlier, current)
        self.check_jorc(total_disposition(receipt, 1), source, 'DENIED', required_polarities=('DENIED',))
        self.check_jorc(total_disposition(receipt, 2), source, 'AFFIRMED', required_polarities=('AFFIRMED',))
        self.assertEqual(len(canonical), 3)
        self.assertTrue(all(json.loads(item['raw'])['pdf_page'] == 2 for item in canonical))
        self.assertEqual(selected[PROJECT_ID]['date'], EFFECTIVE_DATE)

    def test_jorc_subject_switch_after_neutral_prose_keeps_other_table_denial_separate(self):
        note = ('The Mineral Resource estimate in Table 2 is JORC compliant. The prior estimate is in Table 1. '
                'Details remain unchanged. It is not compliant with JORC.')
        source, receipt, _, selected, _, canonical = self.run_pdf(resource_page(qualifier='', notes=(note,)))
        row = total_disposition(receipt)
        self.check_jorc(row, source, 'AFFIRMED', required_polarities=('AFFIRMED',))
        denial = next(evidence for evidence in row['jorc_assessment']['evidence'] if evidence['polarity'] == 'DENIED')
        self.assertEqual(denial['applicability'], 'OTHER_ESTIMATE')
        self.assertIn('Table 1', note[denial['subject_start']:denial['subject_end']])
        self.assertTrue(denial['anaphoric'])
        self.assertEqual(len(canonical), 3)
        self.assertEqual(selected[PROJECT_ID]['contained_treo_kt'], 100)

    def test_ambiguous_antecedent_is_not_used_as_definitive_support_or_denial(self):
        note = ('Table 1 and Table 2 describe different Mineral Resource estimates. '
                'It is not compliant with JORC.')
        _, receipt, _, selected, _, canonical = self.run_pdf(resource_page(notes=(note,)))
        row = total_disposition(receipt)
        self.assertEqual(row['jorc_assessment']['status'], 'UNRESOLVED_SCOPE')
        self.assertTrue(any(item['polarity'] == 'DENIED' and item['quote'] == note
                            for item in row['jorc_assessment']['evidence']))
        self.assertEqual(row['status'], 'NOT_ADMITTED')
        self.assertEqual(canonical, [])
        self.assertEqual(selected, {})

    def test_nonadjacent_context_completes_only_a_located_same_estimate(self):
        resource = resource_page(date=None, cutoff=None, material_header='Ore tonnage (Mt)',
                                 chemical_header='TREO grade (ppm)')
        pages = (resource, narrative_page(), narrative_page(), narrative_page(), external_estimate_context())
        original_source, without_context, _, missing, _, _ = self.run_pdf(*pages, value_pages=(1,), context_pages=())
        self.assertEqual(missing, {})
        self.assertIn('RESOURCE_ESTIMATE_DATE_UNRESOLVED', total_disposition(without_context)['reasons'])

        source, receipt, _, selected, _, canonical = self.run_pdf(*pages, value_pages=(1,), context_pages=(5,))
        self.assertEqual(source['sha256'], original_source['sha256'])
        row = total_disposition(receipt)
        self.assertEqual(row['status'], 'SOURCE_BOUND_CANONICAL', row['reasons'])
        gains = set(row['context_field_gains'])
        self.assertTrue({'effective_date', 'material_basis', 'denominator_basis', 'chemical_basis', 'cutoff_grade'}
                        <= gains, gains)
        self.assertEqual(selected[PROJECT_ID]['contained_treo_kt'], 100)
        self.assertEqual(selected[PROJECT_ID]['date'], EFFECTIVE_DATE)
        self.assertEqual(len(canonical), 3)
        for observation in canonical:
            raw = json.loads(observation['raw'])
            self.assertEqual(raw['material_basis'], 'RESOURCE_BULK_ORE')
            self.assertEqual(observation['basis'], 'TREO')
            typed = raw['source_bound_observation']
            self.assertEqual(typed['evidence']['page'], 1)
            remote = [anchor for anchor in typed['evidence_anchors'] if anchor['page'] == 5]
            self.assertTrue(remote)
            roles = {anchor['role'] for anchor in remote}
            self.assertTrue({'estimate_identity_reference', 'estimate_effective_date', 'estimate_material_basis',
                             'estimate_denominator_basis', 'estimate_chemical_basis', 'estimate_cutoff'}
                            <= roles, roles)
            self.assertTrue(all(anchor['sha256'] == source['sha256'] and anchor['quote'] and anchor['bbox']
                                and anchor['locator'] and anchor['text_span'] for anchor in remote))
            context = ' '.join(anchor['quote'] for anchor in remote)
            for marker in ('Table 2', EFFECTIVE_DATE, 'dry basis', 'Total Rare Earth Oxides', '500 ppm TREO'):
                self.assertIn(marker, context)

    def test_repeated_table_label_and_other_year_do_not_supply_context(self):
        incomplete = resource_page(date=None, cutoff=None, material_header='Ore tonnage (Mt)',
                                   chemical_header='TREO grade (ppm)')
        # Both tables intentionally use the same printed quantity pair. An
        # older dated quotation cannot supply an undated estimate's date.
        other = resource_page(date='2024-05-01')
        source, receipt, _, selected, _, canonical = self.run_pdf(
            incomplete, other, narrative_page(), narrative_page(),
            external_estimate_context(date='2024-05-01'),
            value_pages=(1, 2), context_pages=(5,))
        row = total_disposition(receipt)
        self.assertEqual(row['status'], 'NOT_ADMITTED')
        self.assertIn('RESOURCE_ESTIMATE_DATE_UNRESOLVED', row['reasons'])
        self.assertEqual(total_disposition(receipt, 2)['status'], 'SOURCE_BOUND_CANONICAL')
        self.assertEqual(len(canonical), 3)
        self.assertTrue(all(observation['source_sha'] == source['sha256'] and
                            json.loads(observation['raw'])['pdf_page'] == 2 for observation in canonical))
        self.assertEqual(selected[PROJECT_ID]['date'], '2024-05-01')

    def test_other_estimates_dry_basis_does_not_bind_by_report_footer(self):
        note = narrative_page(f'For the earlier {PROJECT} Mineral Resource estimate in Table 1, '
                              'effective 2024-05-01, tonnages are reported on a dry basis.')
        _, receipt, _, selected, _, canonical = self.run_pdf(
            resource_page(material_header='Ore tonnage (Mt)'), narrative_page(), narrative_page(),
            narrative_page(), note, value_pages=(1,), context_pages=(5,))
        row = total_disposition(receipt)
        self.assertEqual(row['status'], 'NOT_ADMITTED')
        self.assertIn('DRY_BULK_ORE_BASIS_UNRESOLVED', row['reasons'])
        self.assertEqual(canonical, [])
        self.assertEqual(selected, {})

    def test_earlier_estimate_dry_statement_cannot_bind_within_target_block(self):
        note = narrative_page(f'{SCOPE_OPENING} {EARLIER_DRY_STATEMENT}')
        _, receipt, _, selected, _, canonical = self.run_pdf(
            resource_page(material_header='Ore tonnage (Mt)'), narrative_page(), narrative_page(),
            narrative_page(), note, value_pages=(1,), context_pages=(5,))
        row = total_disposition(receipt)
        self.assertEqual(row['status'], 'NOT_ADMITTED', row['reasons'])
        self.assertIn('DRY_BULK_ORE_BASIS_UNRESOLVED', row['reasons'])
        self.assertFalse({'material_basis', 'denominator_basis'} & set(row['context_field_gains']))
        self.assertEqual(canonical, [])
        self.assertEqual(selected, {})

    def test_physical_table_note_cannot_override_an_explicit_estimate_switch(self):
        cases = (
            ('another estimate', False),
            ('a different Mineral Resource estimate in Table 2', False),
            ('the current Mineral Resource estimate', True),
        )
        for subject, expected in cases:
            with self.subTest(subject=subject):
                page = resource_page(material_header='Ore tonnage (Mt)')
                page['notes_below_table'] = (f'For {subject}, tonnages are reported on a dry basis.',)
                _, receipt, _, selected, _, canonical = self.run_pdf(page)
                row = total_disposition(receipt)
                self.assertEqual(len(canonical), 3 if expected else 0, row['reasons'])
                if expected:
                    self.assertEqual(selected[PROJECT_ID]['contained_treo_kt'], 100)
                else:
                    self.assertIn('DRY_BULK_ORE_BASIS_UNRESOLVED', row['reasons'])
                    self.assertEqual(selected, {})

    def test_current_dry_witness_survives_explicit_switch_to_earlier_estimate(self):
        current = 'Tonnages are reported on a dry basis.'
        earlier = ('For the earlier estimate, tonnages are reported on a wet basis. '
                   'The estimate uses a cut-off grade of 1,000 ppm TREO. TREO excludes CeO2.')
        note = narrative_page(f'{SCOPE_OPENING} {current} {earlier}')
        source, receipt, _, selected, _, canonical = self.run_pdf(
            resource_page(material_header='Ore tonnage (Mt)'), narrative_page(), narrative_page(),
            narrative_page(), note, value_pages=(1,), context_pages=(5,))
        row = total_disposition(receipt)
        self.assertEqual(row['status'], 'SOURCE_BOUND_CANONICAL', row['reasons'])
        self.assertEqual(len(canonical), 3)
        self.assertEqual(selected[PROJECT_ID]['contained_treo_kt'], 100)
        for field in ('material_basis', 'denominator_basis'):
            anchor, = row['context_field_gains'][field]['evidence']
            self.assertEqual(anchor['source_sha256'], source['sha256'])
            self.assertEqual(anchor['page'], 5)
            self.assertTrue(anchor['bbox'])
            span = anchor['text_span']
            self.assertIn('dry basis', anchor['quote'][span['start']:span['end']])

    def test_admission_revalidates_the_field_span_after_earlier_estimate_switch(self):
        note = narrative_page(f'{SCOPE_OPENING} Tonnages are reported on a dry basis. {EARLIER_DRY_STATEMENT}')
        source, receipt, _, _, _, _ = self.run_pdf(
            resource_page(material_header='Ore tonnage (Mt)'), narrative_page(), narrative_page(),
            narrative_page(), note, value_pages=(1,), context_pages=(5,))
        row = total_disposition(receipt)
        self.assertEqual(row['status'], 'SOURCE_BOUND_CANONICAL', row['reasons'])
        observations = [raw_from_payload(item['raw']) for item in row['observations']]
        position = (row['physical_page'], row['table'], row['row'])
        self.assertIsNone(_group_context(observations, source, [PROJECT_ID], CUTOFF, position))

        def move_span(anchor):
            if anchor.role not in {'estimate_material_basis', 'estimate_denominator_basis'}:
                return anchor
            span = anchor.text_span
            start, end = span.in_quote
            earlier_start = anchor.quote.casefold().rindex(anchor.quote[start:end].casefold())
            self.assertGreater(earlier_start, start)
            offset = earlier_start - start
            return replace(anchor, text_span=replace(span, start=span.start + offset, end=span.end + offset))

        moved = [replace(item, evidence_anchors=tuple(map(move_span, item.evidence_anchors)))
                 for item in observations]
        self.assertEqual(_group_context(moved, source, [PROJECT_ID], CUTOFF, position),
                         'RESOURCE_CONTEXT_EVIDENCE_BINDING_MISMATCH')

    def test_other_project_quantity_cannot_bind_in_same_physical_block(self):
        other = 'Synthetic Beta Project'
        note = narrative_page(f'Table 2 presents the {PROJECT} Mineral Resource estimate. '
                              f'The {other} Mineral Resource estimate is 50 Mt at 2,000 ppm TREO '
                              f'effective {EFFECTIVE_DATE}. Tonnages are reported on a dry basis. '
                              'TREO means Total Rare Earth Oxides. The estimate uses 500 ppm TREO cut-off.')
        target = resource_page(date=None, cutoff=None, material_header='Ore tonnage (Mt)',
                               chemical_header='TREO grade (ppm)')
        _, receipt, _, selected, _, canonical = self.run_pdf(
            target, narrative_page(), narrative_page(), narrative_page(), note,
            value_pages=(1,), context_pages=(5,), other_project=other)
        row = total_disposition(receipt)
        self.assertEqual(row['status'], 'NOT_ADMITTED')
        self.assertEqual(row['context_field_gains'], {})
        self.assertEqual(canonical, [])
        self.assertEqual(selected, {})

    def test_bound_context_conflicts_keep_incompatible_estimate_out_of_selection(self):
        template = external_estimate_context()['narrative']
        for original, replacement, reason in (
            ('dry basis', 'wet basis', 'DRY_BULK_ORE_BASIS_UNRESOLVED'),
            ('500 ppm', '1,000 ppm', 'RESOURCE_CUTOFF_BASIS_OR_VALUE_CONFLICT'),
            ('TREO means Total Rare Earth Oxides', 'TREO excludes CeO2', 'TREO_EXCLUDED_OXIDE_BASIS'),
        ):
            with self.subTest(reason=reason):
                note = narrative_page(template.replace(original, replacement))
                _, receipt, _, selected, _, canonical = self.run_pdf(
                    resource_page(), narrative_page(), narrative_page(), narrative_page(), note,
                    value_pages=(1,), context_pages=(5,))
                row = total_disposition(receipt)
                self.assertEqual(row['status'], 'NOT_ADMITTED', row['reasons'])
                self.assertIn(reason, row['reasons'])
                self.assertEqual(canonical, [])
                self.assertEqual(selected, {})

    def test_cross_page_denial_needs_a_located_subject_relation(self):
        denial = 'It is not compliant with JORC.'
        unbound = narrative_page(denial)
        bound = external_estimate_context()
        bound['narrative'] += f' Details remain unchanged. {denial}'
        cases = ((unbound, 'AFFIRMED'), (bound, 'CONFLICT'))
        for note, expected in cases:
            with self.subTest(expected=expected):
                source, receipt, _, selected, _, canonical = self.run_pdf(
                    resource_page(), narrative_page(), narrative_page(), narrative_page(), note,
                    value_pages=(1,), context_pages=(5,))
                row = total_disposition(receipt)
                witnesses = self.check_jorc(row, source, expected, required_polarities=('AFFIRMED',))
                negative = next(item for item in row['jorc_assessment']['evidence'] if item['polarity'] == 'DENIED')
                self.assertEqual(negative['physical_page'], 5)
                self.assertEqual(negative['source_sha256'], source['sha256'])
                if expected == 'CONFLICT':
                    self.assertIn(negative, witnesses)
                    self.assertTrue(negative['anaphoric'])
                    self.assertIn('Table 2', negative['quote'][negative['subject_start']:negative['subject_end']])
                    self.assertEqual(row['status'], 'NOT_ADMITTED')
                    self.assertEqual(selected, {})
                    self.assertEqual(canonical, [])
                else:
                    self.assertNotIn(negative, witnesses)
                    self.assertEqual(row['status'], 'SOURCE_BOUND_CANONICAL', row['reasons'])
                    self.assertEqual(selected[PROJECT_ID]['contained_treo_kt'], 100)
                    self.assertEqual(len(canonical), 3)

    def test_component_exclusions_are_distinct_from_unresolved_competing_totals(self):
        _, receipt, _, selected, _, canonical = self.run_pdf(resource_page())
        components = [row for row in receipt['dispositions'] if row['row'] in (1, 2)]
        self.assertEqual(len(components), 2)
        self.assertTrue(all(row['row_role'] == 'COMPONENT' and 'RESOURCE_COMPONENT_EXCLUDED' in row['reasons']
                            for row in components))
        self.assertEqual(total_disposition(receipt)['status'], 'SOURCE_BOUND_CANONICAL')
        self.assertEqual(len(canonical), 3)
        self.assertEqual(selected[PROJECT_ID]['contained_treo_kt'], 100)

        _, receipt, _, selected, _, canonical = self.run_pdf(resource_page(competing_total=('60', '2,000', '120,000')))
        totals = [row for row in receipt['dispositions'] if row['row'] in (3, 4)]
        self.assertEqual(len(totals), 2)
        self.assertEqual({row['status'] for row in totals}, {'NOT_ADMITTED'})
        self.assertTrue(all(row['row_role'] == 'COMPETING_TOTAL' and
                            'RESOURCE_COMPETING_TOTALS_UNRESOLVED' in row['reasons'] for row in totals))
        self.assertEqual(canonical, [])
        self.assertEqual(selected, {})

    def test_caption_classification_is_used_for_a_single_unlabelled_row(self):
        page = resource_page(qualifier='Inferred JORC')
        page['native_grid'] = (
            ('Estimate', page['material_header'], page['chemical_header'], 'Contained TREO (t)'),
            ('', '50', '2,000', '100,000'),
        )
        source, receipt, _, selected, _, canonical = self.run_pdf(page)
        candidate, = receipt['dispositions']
        self.assertEqual(candidate['row'], 1)
        self.assertEqual(candidate['row_role'], 'SOLE_CLASSIFIED_ESTIMATE')
        self.assertEqual(candidate['status'], 'SOURCE_BOUND_CANONICAL', candidate['reasons'])
        self.assertEqual(len(canonical), 3)
        self.assertEqual(selected[PROJECT_ID]['contained_treo_kt'], 100)
        self.assertEqual(len(candidate['observations']), 3)
        for item in candidate['observations']:
            self.assertTrue(item['numeric_and_unit_located'])
            raw = item['raw']
            self.assertEqual(dict(raw['context']['conditions'])['category'], 'INFERRED')
            self.assertTrue(any(anchor['role'] == 'classification' and anchor['page'] == 1
                                and anchor['sha256'] == source['sha256']
                                and 'Inferred JORC Mineral Resource estimate' in (anchor['quote'] or '')
                                for anchor in raw['evidence_anchors']))

    def test_conflicting_caption_and_row_classification_cannot_be_selected(self):
        page = resource_page(qualifier='Inferred JORC')
        page['native_grid'] = (
            ('Classification', page['material_header'], page['chemical_header'], 'Contained TREO (t)'),
            ('Indicated', '50', '2,000', '100,000'),
        )
        _, receipt, _, selected, _, canonical = self.run_pdf(page)
        candidate, = receipt['dispositions']
        self.assertEqual(candidate['status'], 'NOT_ADMITTED')
        self.assertIn('RESOURCE_CLASSIFICATION_EVIDENCE_CONFLICT', candidate['reasons'])
        self.assertEqual(canonical, [])
        self.assertEqual(selected, {})

    def test_single_row_can_inherit_classification_from_section_or_linked_note(self):
        note = 'The Mineral Resource estimate in Table 2 is classified as Inferred.'
        section_title = f'{PROJECT} Total Inferred Mineral Resource estimate'
        for heading in (None, section_title):
            with self.subTest(heading=heading):
                page = resource_page(notes=() if heading else (note,))
                grid = (('Estimate', page['material_header'], page['chemical_header'], 'Contained TREO (t)'),
                        ('', '50', '2,000', '100,000'))
                page['native_grid'] = ((heading, '', '', ''), *grid) if heading else grid
                page['merged_first_row'] = bool(heading)
                source, receipt, _, selected, _, canonical = self.run_pdf(page)
                candidate, = receipt['dispositions']
                self.assertEqual(candidate['status'], 'SOURCE_BOUND_CANONICAL', candidate['reasons'])
                self.assertEqual(len(canonical), 3)
                self.assertEqual(selected[PROJECT_ID]['contained_treo_kt'], 100)
                raw = candidate['observations'][0]['raw']
                self.assertEqual(dict(raw['context']['conditions'])['category'], 'INFERRED')
                self.assertTrue(any(anchor['role'] == ('resource_section' if heading else 'classification')
                                    and anchor['quote'] == (heading or note) and anchor['page'] == 1
                                    and anchor['sha256'] == source['sha256'] and anchor['bbox']
                                    for anchor in raw['evidence_anchors']))

    def test_note_classification_stays_with_its_own_project_and_estimate(self):
        other = 'Synthetic Beta Project'
        cases = (
            (f'For the {other}, the Mineral Resource estimate is classified as Inferred.', False),
            ('The Mineral Resource estimate in Table 2 is classified as Inferred. '
             'An earlier estimate was classified as Indicated.', True),
        )
        for note, expected in cases:
            with self.subTest(note=note):
                page = resource_page()
                page['notes_below_table'] = (note,)
                page['native_grid'] = (
                    ('Estimate', page['material_header'], page['chemical_header'], 'Contained TREO (t)'),
                    ('', '50', '2,000', '100,000'),
                )
                _, receipt, _, selected, _, canonical = self.run_pdf(page, other_project=other)
                self.assertEqual(len(canonical), 3 if expected else 0, receipt['dispositions'])
                if not expected:
                    self.assertEqual(selected, {})
                    continue
                self.assertEqual(selected[PROJECT_ID]['contained_treo_kt'], 100)
                item = receipt['dispositions'][0]['observations'][0]['raw']
                self.assertEqual(dict(item['context']['conditions'])['category'], 'INFERRED')
                witness, = [anchor for anchor in item['evidence_anchors']
                            if anchor['locator'] == 'TABLE_NOTE_CLASSIFICATION']
                span = witness['text_span']
                self.assertIn('earlier estimate', witness['quote'])
                self.assertNotIn('earlier estimate', witness['quote'][span['start']:span['end']])

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
        for note in ('The Mineral Resource estimate in Table 2 is not JORC-compliant.',
                     'The report presents the Mineral Resource estimate in Table 2. It cannot be considered JORC compliant.'):
            with self.subTest(note=note):
                source, receipt, _, selected, _, canonical = self.run_pdf(resource_page(notes=(note,)))
                row = total_disposition(receipt)
                self.assertIn('RESOURCE_JORC_CONFLICT', row['reasons'])
                witnesses = self.check_jorc(row, source, 'CONFLICT', required_polarities=('AFFIRMED', 'DENIED'))
                self.assertEqual({item['physical_page'] for item in witnesses}, {1})
                self.assertEqual(len({tuple(item['bbox']) for item in witnesses}), 2)
                self.assertEqual(canonical, [])
                self.assertEqual(selected, {})

    def test_jorc_denial_in_next_physical_block_retains_both_locations(self):
        source, receipt, _, selected, _, canonical = self.run_pdf(
            resource_page(qualifier='', notes=(JORC_OPENING, JORC_DENIAL)))
        row = total_disposition(receipt)
        witnesses = self.check_jorc(row, source, 'CONFLICT', required_polarities=('AFFIRMED', 'DENIED'))
        positive, = [item for item in witnesses if item['quote'] == JORC_OPENING]
        negative, = [item for item in witnesses if item['quote'] == JORC_DENIAL]
        self.assertEqual(negative['physical_page'], positive['physical_page'])
        self.assertNotEqual(negative['bbox'], positive['bbox'])
        for reference in ('antecedent', 'reporting_reference'):
            self.assertEqual(negative[reference]['quote'], positive['quote'])
            self.assertEqual(negative[reference]['bbox'], positive['bbox'])
            self.assertEqual(negative[reference]['source_sha256'], source['sha256'])
        self.assertIn('RESOURCE_JORC_CONFLICT', row['reasons'])
        self.assertEqual(canonical, [])
        self.assertEqual(selected, {})

    def test_admission_revalidates_an_affirmation_in_the_next_physical_block(self):
        subject = 'The report presents the Mineral Resource estimate in Table 2.'
        statement = resource_page(qualifier='', notes=(subject, 'It is JORC compliant.'))
        source, receipt, _, selected, _, canonical = self.run_pdf(statement)
        row = total_disposition(receipt)
        self.assertEqual(len(canonical), 3)
        self.assertEqual(selected[PROJECT_ID]['contained_treo_kt'], 100)
        observations = [raw_from_payload(item['raw']) for item in row['observations']]
        position = (row['physical_page'], row['table'], row['row'])
        self.assertIsNone(_group_context(observations, source, [PROJECT_ID], CUTOFF, position))
        self.assertTrue(all(any(anchor.role == 'jorc_discourse_context' and anchor.quote == subject
                                for anchor in item.evidence_anchors) for item in observations))
        no_antecedent = [replace(item, evidence_anchors=tuple(anchor for anchor in item.evidence_anchors
                                                             if anchor.role != 'jorc_discourse_context'))
                         for item in observations]
        self.assertEqual(_group_context(no_antecedent, source, [PROJECT_ID], CUTOFF, position),
                         'RESOURCE_JORC_SCOPE_UNRESOLVED')

    def test_other_estimate_denial_in_next_physical_block_keeps_target_eligible(self):
        other = 'The earlier Mineral Resource estimate in Table 1 is not compliant with JORC.'
        source, receipt, _, selected, _, canonical = self.run_pdf(
            resource_page(qualifier='', notes=(JORC_OPENING, other)))
        row = total_disposition(receipt)
        self.check_jorc(row, source, 'AFFIRMED', required_polarities=('AFFIRMED',))
        evidence, = [item for item in row['jorc_assessment']['evidence'] if item['quote'] == other]
        self.assertEqual(evidence['applicability'], 'OTHER_ESTIMATE')
        self.assertEqual(evidence['polarity'], 'DENIED')
        self.assertEqual(len(canonical), 3)
        self.assertEqual(selected[PROJECT_ID]['contained_treo_kt'], 100)

    def test_other_estimate_cannot_lend_its_jorc_statement_through_repeated_table_label(self):
        for effective, applicability in (('', 'TARGET_SCOPE_AMBIGUOUS'),
                                         (' effective 2024-05-01', 'OTHER_ESTIMATE')):
            with self.subTest(effective=effective):
                other = f'Another Mineral Resource estimate in Table 2{effective} is JORC compliant.'
                source, receipt, _, selected, _, canonical = self.run_pdf(resource_page(qualifier='', notes=(other,)))
                row = total_disposition(receipt)
                evidence, = [item for item in row['jorc_assessment']['evidence'] if item['quote'] == other]
                self.assertEqual(evidence['source_sha256'], source['sha256'])
                self.assertEqual(evidence['applicability'], applicability)
                self.assertEqual(evidence['polarity'], 'AFFIRMED')
                self.assertEqual(row['status'], 'NOT_ADMITTED')
                self.assertEqual(canonical, [])
                self.assertEqual(selected, {})

    def test_ambiguous_block_reference_retains_unresolved_denial(self):
        ambiguous = ('The discussion mentions Table 1 and Table 2 as distinct Mineral Resource estimates. '
                     'It is not compliant.')
        source, receipt, _, selected, _, canonical = self.run_pdf(
            resource_page(qualifier='', notes=(JORC_OPENING, ambiguous)))
        row = total_disposition(receipt)
        self.assertEqual(row['jorc_assessment']['subject']['reported_table_label'], '2')
        self.assertEqual(row['jorc_assessment']['status'], 'UNRESOLVED_SCOPE')
        evidence, = [item for item in row['jorc_assessment']['evidence']
                     if item['quote'] == ambiguous and item['polarity'] == 'DENIED']
        self.assertIn(evidence['applicability'], ('UNRESOLVED_SCOPE', 'TARGET_SCOPE_AMBIGUOUS', 'UNRESOLVED'))
        self.assertEqual(evidence['source_sha256'], source['sha256'])
        self.assertEqual(row['status'], 'NOT_ADMITTED')
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
    if len(sys.argv) == 3 and sys.argv[1] == '--proposition-receipt':
        output = Path(sys.argv[2])
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(proposition_replay(), indent=2) + '\n', encoding='utf-8')
    elif len(sys.argv) == 3 and sys.argv[1] == '--prepare-scope-replay':
        prep_scope_replay(Path(sys.argv[2]))
    elif len(sys.argv) in (4, 5) and sys.argv[1] == '--scope-replay':
        output = Path(sys.argv[3])
        output.parent.mkdir(parents=True, exist_ok=True)
        baseline = Path(sys.argv[4]) if len(sys.argv) == 5 else None
        output.write_text(json.dumps(scope_replay(Path(sys.argv[2]), baseline), indent=2) + '\n', encoding='utf-8')
    else:
        unittest.main()
