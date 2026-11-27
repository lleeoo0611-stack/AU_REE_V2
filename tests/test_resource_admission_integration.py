"""Synthetic PDF-to-R proof for the opt-in formal resource admission path."""

import argparse
from contextlib import closing
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

import pymupdf

from au_ree_v2.cli import research_configuration
from au_ree_v2.store import canonical, digest, filehash
from au_ree_v2.tabular import read_csv


ROOT = Path(__file__).resolve().parents[1]
PANEL = 'issuer_resource_study'
CUTOFF = '2026-11-05'
ASTER = 'Fictional Aster Project'
BEACON = 'Fictional Beacon Project'
FIXTURE_CLASS = 'SYNTHETIC_ENGINEERING_FIXTURE'
GATES = {'ID', 'ROLE', 'WINDOW', 'JORC', 'PANEL', 'GIS_RELEASE'}
MARKER = 'Definitive Feasibility Study completed.'
SCIENTIFIC = (
    'resources.csv', 'criteria_resolution.csv', 'cohort_coverage.csv', 'eligibility_cohorts.csv',
    'formal_gate_compatibility.csv', 'value_trace.csv', f'{PANEL}/matrix.csv',
    f'{PANEL}/criteria.csv', f'{PANEL}/weights.csv', f'{PANEL}/ranking.csv',
)


def write_json(path, content):
    path.write_text(canonical(content) + '\n', encoding='utf-8')


def project_id(name):
    return 'AU-' + digest(['project_registry_v1', name.split()[1].lower()])[:20]


def report(root, name, key, effective, published, ore_mt, *, grade_header='Total Rare Earth Oxides (TREO) (ppm)',
           value_page=1, context_page=None):
    path = root / 'data' / f'{key}.pdf'
    with pymupdf.open() as document:
        for number in range(1, value_page):
            page = document.new_page(width=710, height=500)
            if number == context_page:
                text = (f'For the {name} Mineral Resource estimate in Table 1, {ore_mt:.1f} Mt at 1000 ppm TREO, '
                        f'effective {effective}. Tonnages are reported on a dry basis. TREO means Total Rare Earth Oxides. '
                        'The estimate uses a cut-off grade of 500 ppm TREO.')
                page.insert_textbox((40, 95, 666, 335), text, fontsize=10)
            elif number != 4:
                page.insert_text((40, 68), f'Fictional infrastructure and transport memorandum {number}', fontsize=10)
        page = document.new_page(width=710, height=500)
        page.insert_text((40, 37), 'SYNTHETIC ENGINEERING TEST DOCUMENT', fontsize=12)
        caption = f'Table 1: {name} Total JORC Mineral Resource estimate'
        if context_page is None:
            caption += f' as at {effective} at 500 ppm TREO cut-off'
        page.insert_text((40, 92), caption, fontsize=10)
        header = ['Classification', 'Dry ore tonnage (Mt)' if context_page is None else 'Ore tonnage (Mt)',
                  grade_header if context_page is None else 'TREO grade (ppm)', 'Contained TREO (kt)']
        grid = [header, ['Indicated', f'{ore_mt * 0.4:.1f}', '1000', f'{ore_mt * 0.4:.1f}'],
                ['Inferred', f'{ore_mt * 0.6:.1f}', '1000', f'{ore_mt * 0.6:.1f}'],
                ['Total', f'{ore_mt:.1f}', '1000', f'{ore_mt:.1f}']]
        columns = [40, 159, 285, 533, 666]
        rows = [110, 135, 160, 185, 210]
        for x in columns:
            page.draw_line((x, rows[0]), (x, rows[-1]))
        for y in rows:
            page.draw_line((columns[0], y), (columns[-1], y))
        for y, cells in zip(rows, grid):
            for x, text in zip(columns, cells):
                page.insert_text((x + 5, y + 16), text, fontsize=10)
        page.insert_text((40, 253), MARKER, fontsize=10)
        document.set_metadata({'title': f'Synthetic engineering fixture {key}'})
        document.save(path, no_new_id=True)
    return {
        'key': key, 'kind': 'pdf', 'path': path.relative_to(root).as_posix(), 'sha256': filehash(path),
        'url': f'https://example.invalid/synthetic/{key}.pdf', 'publication_date': published,
        'available_date': published, 'acquired_at': published + 'T00:00:00+00:00',
        'summary_project_ids': [project_id(name)], 'case_classification': FIXTURE_CLASS,
    }


def project(name, source):
    return {
        'id': name.split()[1].lower(), 'name': name, 'aliases': [name], 'state': 'WA',
        'identity_source': source['key'],
        'observations': [{
            'variable': 'study_maturity_ord', 'value': 4, 'unit': 'ordinal', 'basis': 'DATED_DFS_REAFFIRMED',
            'scope': f'{name} completed feasibility study', 'statement_id': f'{source["key"]}-study',
            'effective_date': source['publication_date'], 'source_key': source['key'], 'source_sha256': source['sha256'],
            'locator': 'Physical page 1, completed study statement', 'pdf_page': 1, 'page_markers': [MARKER],
        }],
    }


def fixture(root):
    root.mkdir()
    for directory in ('config', 'docs', 'R', 'results', 'src'):
        (root / directory).symlink_to(ROOT / directory, target_is_directory=True)
    data = root / 'data'
    data.mkdir()
    for path in (ROOT / 'data').iterdir():
        if path.name not in {'claims.json', 'manifest.json'}:
            (data / path.name).symlink_to(path, target_is_directory=path.is_dir())
    older = report(root, ASTER, 'aster-established-resource', '2025-05-01', '2025-06-01', 50)
    comparator = report(root, BEACON, 'beacon-established-resource', '2025-05-01', '2025-06-01', 100)
    update = report(root, ASTER, 'aster-updated-resource', '2026-05-01', '2026-06-01', 150)
    decoy = report(root, ASTER, 'aster-reported-elemental-grade', '2026-06-01', '2026-07-01', 300,
                   grade_header='Total Rare Earth Elements (TREE) (ppm)')
    claims = {'projects': [project(ASTER, older), project(BEACON, comparator)]}
    write_json(data / 'claims.json', claims)
    configuration = research_configuration(ROOT)
    # The sealed technical disclosure review is for real registry identities.
    # The synthetic R1/D1 panel keeps the published criteria, weights and R inputs.
    configuration['evidence_resolution'].pop('technical_disclosure')
    write_json(root / 'configuration.json', {'research': configuration})
    return claims, [older, comparator], update, decoy


def inputs(root, label, snapshots, requests):
    lock = root / f'{label}-snapshot-lock.json'
    write_json(lock, snapshots)
    frame = root / f'{label}-frame.json'
    write_json(frame, {'schema': 'resource-admission-frame-v1', 'classification': FIXTURE_CLASS, 'sources': [
        {'source_key': s['key'], 'source_sha256': s['sha256'], 'pages': [1]} for s in requests
    ]})
    return lock, frame


def rows_hashes(folder):
    return {name: filehash(folder / name) for name in SCIENTIFIC}


def launch(output, root, label, lock, frame, working, rscript, *, cache='use', expect_failure=False,
           retrieval=None):
    command = [sys.executable, '-m', 'au_ree_v2', 'rebuild', '--root', str(root),
               '--snapshot-lock', str(lock), '--work', str(working), '--as-of', CUTOFF,
               '--resource-admission', str(frame), '--rscript', str(rscript),
               '--cache-dir', str(output / 'derived-cache'),
               '--cache-mode', cache, '--mcda-cache-mode', cache]
    if retrieval:
        command += ['--resource-retrieval', retrieval]
    env = {**os.environ, 'AU_REE_MCDA_CACHE': str(output / 'mcda-cache')}
    results = subprocess.run(command, capture_output=True, text=True, timeout=180, env=env)
    (output / f'{label}.log').write_text(results.stdout + results.stderr, encoding='utf-8')
    if results.returncode:
        if expect_failure and 'SYNTHETIC_GRADE_INSERT_FAILURE' in results.stderr:
            return None, None
        raise AssertionError(f'{label} exited {results.returncode}: {results.stderr[-2000:]}')
    result = json.loads((working / 'latest.json').read_text(encoding='utf-8'))
    return result, Path(result['output_dir'])


def snapshot_observations(database):
    with closing(sqlite3.connect(database)) as db:
        return dict(db.execute('SELECT obs_id, source_sha FROM observations ORDER BY obs_id'))


def selected(path):
    return {row['entity_id']: row for row in read_csv(path / 'resources.csv')}


def rankings(path):
    return {(row['scenario'], row['project_id']): row for row in read_csv(path / PANEL / 'ranking.csv')}


def assert_scientific_update(before, after, original_id, peer_id):
    previous, updated = selected(before), selected(after)
    assert set(previous) == set(updated) == {original_id, peer_id}
    assert float(previous[original_id]['contained_treo_kt']) == 50
    assert float(updated[original_id]['contained_treo_kt']) == 150
    assert previous[peer_id] == updated[peer_id]
    assert previous[original_id]['scope'] == updated[original_id]['scope']
    assert previous[original_id]['obs_ids'] != updated[original_id]['obs_ids']
    assert previous[original_id]['date'] == '2025-05-01'
    assert updated[original_id]['date'] == '2026-05-01'
    old_matrix, new_matrix = ({row['project_id']: row for row in read_csv(folder / PANEL / 'matrix.csv')}
                              for folder in (before, after))
    assert old_matrix.keys() == new_matrix.keys() == {original_id, peer_id}
    assert old_matrix[peer_id] == new_matrix[peer_id]
    assert old_matrix[original_id]['D1'] == new_matrix[original_id]['D1']
    assert float(old_matrix[original_id]['R1']) < float(old_matrix[peer_id]['R1']) < float(new_matrix[original_id]['R1'])
    old, new = rankings(before), rankings(after)
    assert old.keys() == new.keys() and len(old) >= 2
    changed = []
    for scenario, project_id_ in sorted(old):
        pair = (old[scenario, project_id_], new[scenario, project_id_])
        expected = [2, 1] if project_id_ == original_id else [1, 2]
        observed = {method: [float(row[f'{method}_rank']) for row in pair]
                    for method in ('saw', 'topsis', 'promethee')}
        assert all(value == expected for value in observed.values()), (scenario, observed)
        changed.append({'scenario': scenario, 'project_id': project_id_, 'ranks': observed})
    expected_gates = {(pid, gate) for pid in (original_id, peer_id) for gate in GATES}
    for path in (before, after):
        rows = read_csv(path / 'formal_gate_compatibility.csv')
        assert {(r['canonical_project_id'], r['gate']) for r in rows} == expected_gates
        audit = json.loads((path / 'eligibility_audit.json').read_bytes())
        assert audit['formal_c1_admitted'] == 0
    return changed


def assert_retrieval_reaches_formal_outputs(output, stages, *, source, lock, fixed, searched, warm):
    from au_ree_v2.formal_resource_refresh import compare

    before, after, repeated = (stages[label] for label in (fixed, searched, warm))
    assert before['summary']['snapshot_sha256'] == after['summary']['snapshot_sha256']
    assert before['intake']['frame_sha256'] == after['intake']['frame_sha256']
    assert after['intake']['retrieval']['mode'] == 'full-text'
    sha = source['sha256']
    retrieval = next(item for item in after['intake']['retrieval_sources'] if item['source_sha256'] == sha)
    effective = next(item for item in after['intake']['effective_frame_sources'] if item['source_sha256'] == sha)
    assert retrieval['document_total_pages'] == 7 and retrieval['indexed_page_count'] == 6
    assert retrieval['unreadable_pages'] == [4] and not retrieval['index_failures']
    assert 7 in retrieval['candidate_pages']['resource'] and 3 in retrieval['candidate_pages']['resource_context']
    assert 7 in effective['pages'] and 3 in effective['context_pages'], retrieval
    assert 7 in retrieval['parsed_pages'] and 3 in retrieval['parsed_context_pages'], retrieval
    assert retrieval['value_search_outcome'] == 'VALUE_CANDIDATES_PARSED'
    assert any(item['status'] == 'SOURCE_BLOCKED' and item['reason'] == 'PINNED_SOURCE_EDITION_NOT_SELECTED'
               for item in after['intake']['retrieval_sources'])
    admitted = [row for row in after['intake']['dispositions'] if row['source_sha256'] == sha
                and row['status'] == 'SOURCE_BOUND_CANONICAL']
    assert len(admitted) == 1 and admitted[0]['physical_page'] == 7 and admitted[0]['row'] == 3
    assert not any(row['source_sha256'] == sha and row['status'] == 'SOURCE_BOUND_CANONICAL'
                   for row in before['intake']['dispositions'])
    assert len(admitted[0]['canonical_observation_ids']) == 3
    assert after['hashes'] == repeated['hashes']
    assert after['intake']['effective_frame_sources'] == repeated['intake']['effective_frame_sources']
    assert set(after['intake']['canonical_observation_ids']) == set(repeated['intake']['canonical_observation_ids'])
    assert repeated['intake']['counts']['canonical_added'] == 0
    ranks = assert_scientific_update(before['path'], after['path'], project_id(ASTER), project_id(BEACON))
    delta = compare(before['path'], after['path'], output / 'retrieval-differences', mode='retrieval_effect')
    assert delta['comparison']['kind'] == 'retrieval_effect'
    assert delta['comparison']['changed_factors'] == ['admission_retrieval']
    assert not delta['comparison']['source_editions_changed']
    assert delta['criterion_selection_counts']['updated'] == 1
    assert delta['panels'][PANEL]['matrix_primary_criterion_cells_changed'] == 1
    assert len(delta['panels'][PANEL]['ranking_differences']) == len(ranks)
    return {'snapshot_lock_sha256': filehash(lock), 'new_source_sha256': sha, 'retrieval': retrieval,
            'new_canonical_observation_ids': admitted[0]['canonical_observation_ids'],
            'same_source_scope_comparison': delta, 'point_rank_changes': ranks,
            'repeat_science_and_selected_pages_identical': True}


def exercise(output, rscript):
    with TemporaryDirectory(prefix='au-ree-resource-originals-') as temporary:
        root = Path(temporary) / 'registry'
        _, established, update, decoy = fixture(root)
        discovered_update = report(root, ASTER, 'aster-full-text-resource', '2026-05-01', '2026-06-01', 150,
                                   value_page=7, context_page=3)
        missing = {'key': 'synthetic-unavailable', 'sha256': digest('synthetic original intentionally missing')}
        snapshots = [*established, update, decoy]
        searchable_snapshots = [*established, discovered_update, decoy]
        locks = {
            'before': inputs(root, 'before', established, established),
            'after': inputs(root, 'after', snapshots, [*snapshots, missing]),
            'scope_change': inputs(root, 'scope-change', snapshots, established),
            'retrieval': inputs(root, 'retrieval', searchable_snapshots, [*searchable_snapshots, missing]),
        }
        retained = output / 'inputs'
        (retained / 'data').mkdir(parents=True)
        for path in (root / 'data').glob('*.pdf'):
            shutil.copy2(path, retained / 'data' / path.name)
        for path in (root / 'data' / 'claims.json', root / 'configuration.json',
                     *(path for files in locks.values() for path in files)):
            shutil.copy2(path, retained / path.relative_to(root))

        work = output / 'canonical-runs'
        database = work / 'canonical.sqlite'
        stages = {}

        def run_stage(label, lock_key, *, directory=work, cache='use', expect_failure=False, retrieval=None):
            lock, frame = locks[lock_key]
            result, folder = launch(output, root, label, lock, frame, directory, rscript,
                                    cache=cache, expect_failure=expect_failure, retrieval=retrieval)
            if result is not None:
                assert result['status'] == 'COMPLETED'
                assert result['r_results'][PANEL]['status'] == 'COMPLETED'
                receipt = json.loads((folder / 'resource_admission.json').read_bytes())
                assert receipt['run_id'] == result['run_id']
                assert receipt['frame_sha256'] == filehash(frame)
                assert receipt['classification'] == FIXTURE_CLASS
                stages[label] = {'summary': result, 'path': folder, 'intake': receipt,
                                 'hashes': rows_hashes(folder)}
            return result, folder

        _, before = run_stage('baseline-cache-disabled', 'before', cache='off')
        base_observations = snapshot_observations(database)
        # Force an actual SQLite write failure on the second value of one group.
        # The apparent ore half of the estimate must never become canonical.
        with closing(sqlite3.connect(database)) as db:
            db.executescript(f'''CREATE TRIGGER synthetic_grade_insert_failure
                BEFORE INSERT ON observations WHEN NEW.source_sha='{update['sha256']}' AND NEW.variable='grade'
                BEGIN SELECT RAISE(ABORT, 'SYNTHETIC_GRADE_INSERT_FAILURE'); END;''')
        try:
            failure, _ = run_stage('interrupted-transaction', 'after', cache='off', expect_failure=True)
            assert failure is None
            assert snapshot_observations(database) == base_observations
        finally:
            with closing(sqlite3.connect(database)) as db:
                db.executescript('DROP TRIGGER synthetic_grade_insert_failure;')

        _, after = run_stage('updated-cold-cache', 'after')
        updates = snapshot_observations(database)
        assert base_observations.items() <= updates.items()
        added = sorted(updates.keys() - base_observations.keys())
        assert len(added) == 3 and {updates[obs_id] for obs_id in added} == {update['sha256']}
        with closing(sqlite3.connect(database)) as db:
            assert db.execute('PRAGMA integrity_check').fetchone() == ('ok',)
            assert not db.execute('PRAGMA foreign_key_check').fetchall()
            fetched = db.execute('SELECT variable,value,raw FROM observations WHERE source_sha=?', (update['sha256'],))
            new_values = {}
            for variable, value, raw_json in fetched:
                new_values[variable] = value
                raw = json.loads(raw_json)
                bound = raw['source_bound_observation']
                assert raw['original_token'] == ('1000' if variable == 'grade' else '150.0')
                assert bound['evidence']['sha256'] == update['sha256'] and bound['evidence']['page'] == 1
                headers = [w for w in bound['evidence_anchors'] if w['role'] == 'unit']
                assert len(headers) == 1 and headers[0]['row'] == 0
                assert bound['evidence']['row'] == 3 and headers[0]['column'] == bound['evidence']['column']
        assert new_values == {'ore_mt': 150.0, 'grade': 1000.0, 'contained_treo_kt': 150.0}

        run_stage('updated-warm-cache', 'after')
        assert snapshot_observations(database) == updates
        clean_dir = output / 'independent-runs'
        run_stage('updated-cache-disabled', 'after', directory=clean_dir, cache='off')
        assert snapshot_observations(clean_dir / 'canonical.sqlite') == updates
        comparison = [stages[label]['hashes'] for label in ('updated-cold-cache', 'updated-warm-cache', 'updated-cache-disabled')]
        assert comparison[0] == comparison[1] == comparison[2]
        run_stage('changed-source-frame-warm-cache', 'scope_change')
        run_stage('changed-source-frame-cache-disabled', 'scope_change', directory=output / 'independent-scope', cache='off')
        assert snapshot_observations(database) == updates
        assert stages['changed-source-frame-warm-cache']['hashes'] == stages['changed-source-frame-cache-disabled']['hashes']
        assert selected(stages['changed-source-frame-warm-cache']['path']) == selected(before)

        cold, warm = (stages[k] for k in ('updated-cold-cache', 'updated-warm-cache'))
        assert cold['intake']['cache']['mode'] == warm['intake']['cache']['mode'] == 'use'
        assert any(counts.get('COMPUTED', 0) for counts in cold['intake']['cache']['counts'].values())
        assert any(counts.get('HIT', 0) for counts in warm['intake']['cache']['counts'].values())
        assert any(row['source_sha256'] == missing['sha256'] and row['status'] == 'SOURCE_BLOCKED'
                   for row in cold['intake']['excluded_sources'])
        decoy_rows = [row for row in cold['intake']['dispositions'] if row['source_sha256'] == decoy['sha256']]
        assert decoy_rows and all('RESOURCE_COLUMN_UNBOUND:grade' in row['reasons'] for row in decoy_rows)
        assert set(added) <= set(cold['intake']['canonical_observation_ids'])
        assert cold['intake']['canonical_observation_ids'] == warm['intake']['canonical_observation_ids']
        ranks = assert_scientific_update(before, after, project_id(ASTER), project_id(BEACON))

        from au_ree_v2.formal_resource_refresh import compare

        differences = compare(before, after, output / 'formal-differences')
        panel_change = differences['panels'][PANEL]
        assert differences['new_canonical_observation_ids'] == added
        assert differences['criterion_selection_counts']['updated'] == 1
        assert panel_change['matrix_primary_criterion_cells_changed'] == 1
        assert len(panel_change['ranking_differences']) == len(ranks)
        assert differences['formal_c1']['updated']['formal_c1_admitted'] == 0
        retrieval_work = output / 'retrieval-runs'
        fixed_label, full_label, warm_label = 'retrieval-fixed', 'retrieval-full-text', 'retrieval-full-text-warm'
        run_stage(fixed_label, 'retrieval', directory=retrieval_work, retrieval='fixed')
        run_stage(full_label, 'retrieval', directory=retrieval_work, retrieval='full-text')
        run_stage(warm_label, 'retrieval', directory=retrieval_work, retrieval='full-text')
        retrieval_proof = assert_retrieval_reaches_formal_outputs(output, stages, source=discovered_update,
                                                               lock=locks['retrieval'][0], fixed=fixed_label,
                                                               searched=full_label, warm=warm_label)
        receipt = {
            'schema': 'resource-admission-engineering-proof-v1', 'classification': FIXTURE_CLASS,
            'status': 'COMPLETE', 'cutoff': CUTOFF, 'source_sha256': {row['key']: row['sha256'] for row in snapshots},
            'panel': PANEL, 'reference_code': stages['updated-cold-cache']['summary']['code'],
            'configuration_sha256': filehash(retained / 'configuration.json'),
            'rscript_version': subprocess.check_output([str(rscript), '--version'], stderr=subprocess.STDOUT, text=True).strip(),
            'assertions': {
                'fault_left_existing_canonical_unchanged': True,
                'disabled_cold_warm_science_identical': True,
                'changed_frame_incremental_and_full_science_identical': True,
                'repeat_same_canonical_observation_ids': True,
                'research_panel_count': 2, 'formal_c1_admitted': 0,
            },
            'new_canonical_observation_ids': added, 'new_canonical_values': new_values,
            'criterion_update': {'project_id': project_id(ASTER), 'criterion': 'R1', 'unit': 'kt TREO',
                                 'before': 50, 'after': 150},
            'r_rank_changes': ranks, 'formal_differences': differences,
            'full_text_retrieval': retrieval_proof,
            'runs': {label: {'run_id': stage['summary']['run_id'],
                             'path': stage['path'].relative_to(output).as_posix(),
                             'scientific_sha256': stage['hashes'], 'admission_cache': stage['intake']['cache']['counts'],
                             'r_result': stage['summary']['r_results'][PANEL]} for label, stage in stages.items()},
        }
        write_json(output / 'engineering_proof.json', receipt)
        return receipt


class ResourceAdmissionIntegrationTests(unittest.TestCase):
    def test_new_source_transaction_selection_and_r_mcda(self):
        rscript = os.environ.get('RSCRIPT') or shutil.which('Rscript')
        if not rscript:
            self.skipTest('Rscript is unavailable for the engineering integration proof')
        with TemporaryDirectory(prefix='au-ree-admission-engineering-') as temporary:
            self.assertEqual(exercise(Path(temporary), rscript)['status'], 'COMPLETE')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--rscript', default=os.environ.get('RSCRIPT') or shutil.which('Rscript'))
    args = parser.parse_args()
    if not args.rscript:
        parser.error('Rscript is required to run the engineering integration proof')
    args.output.mkdir(parents=True, exist_ok=True)
    proof = exercise(args.output.resolve(), args.rscript)
    print(canonical({'status': proof['status'], 'classification': proof['classification'],
                     'receipt': str(args.output / 'engineering_proof.json')}))


if __name__ == '__main__':
    main()
