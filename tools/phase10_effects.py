"""Audit frozen formal rebuilds for isolated factors and cache equivalence."""

import argparse
from collections import Counter
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
from zipfile import ZipFile

from au_ree_v2.derived_cache import atomic_json
from au_ree_v2.formal_resource_refresh import _FormalInputs, _panel_delta, compare
from au_ree_v2.store import digest, filehash


COMPARISONS = {
    'c1_cohort_policy': ('historical-baseline', 'disabled-baseline', 'policy_effect', 'c1_cohort_policy'),
    'resource_admission_enablement': ('disabled-baseline', 'current-fixed', 'admission_effect', 'admission_enabled'),
    'retrieval': ('current-fixed', 'current-full-off', 'retrieval_effect', 'admission_retrieval'),
    'joint_rule_and_normalization_release': (
        'old-historical-fixed', 'current-historical-fixed', 'rule_effect', 'code_or_admission_rules'),
}
PANEL_FIELDS = (
    'baseline_r_status', 'updated_r_status', 'baseline_projects', 'updated_projects', 'cohort_added',
    'cohort_removed', 'matrix_primary_criterion_cells_changed', 'ranking_score_cells_changed',
    'rank_position_cells_changed', 'affected_matrix_projects', 'affected_ranking_projects',
)
CHANGE_COUNTS = (
    'matrix_primary_criterion_cells_changed', 'ranking_score_cells_changed', 'rank_position_cells_changed',
)
REPLAY = ('current-full-off', 'current-full-cold', 'current-full-warm')
CORE_SCIENCE_FILES = {
    'canonical_membership.csv', 'resources.csv', 'criteria_resolution.csv', 'value_trace.csv',
    'resource_scope_selection.csv', 'cohort_coverage.csv', 'eligibility_cohorts.csv', 'eligibility_audit.json',
    'formal_gate_compatibility.csv', 'logical_database.json', 'snapshot_lock.json', 'configuration.json',
}
PANEL_EXECUTION_FILES = {'runtime.csv', 'R.log', 'R_cohort.log', 'r_cache.json', 'r_cohort_cache.json'}
REFERENCE = {
    'c1_cohort_policy': 'resource-admission-delta/c1-policy/resource_refresh.json',
    'resource_admission_enablement': 'resource-admission-delta/resource_refresh.json',
    'retrieval': 'resource-admission-delta/retrieval/supplement/resource_refresh.json',
}
NORMALIZERS = ('72ecc3fa1cfc43cacf2015d82b1f943dd38c16f2', 'dcda87e81e1250d443f73c1984faaa7beaa19930')


def read_json(path):
    return json.loads(path.read_bytes())


def panel_names(before, after):
    names = set(before.summary['r_results']) | set(after.summary['r_results'])
    if len(names) != 16:
        raise ValueError('Expected the 16-panel Phase 22 evaluation frame')
    return sorted(names)


def exact_projects(run):
    return {row['canonical_id'] for row in run.csv('canonical_membership.csv') if row['kind'] == 'PROJECT'}


def factor_effect(pair, runs, work):
    baseline, updated, mode, factor = pair
    if missing := sorted({baseline, updated} - runs.keys()):
        return {'status': 'UNMEASURED', 'missing_arms': missing}
    before, after = (_FormalInputs(runs[name]) for name in (baseline, updated))
    result = compare(before.folder, after.folder, work, mode=mode)
    if result['comparison']['changed_factors'] != [factor]:
        raise ValueError(f'Unexpected comparison factors for {baseline} to {updated}')
    old_ids, new_ids = exact_projects(before), exact_projects(after)
    panels = {}
    for name in panel_names(before, after):
        panel = result['panels'].get(name) or _panel_delta(before, after, name, set())
        panels[name] = {field: panel[field] for field in PANEL_FIELDS}
    changed_values = []
    for row in result['selection_differences']:
        entry = {'identity': row['identity'], 'kind': row['change_kind'], 'reason': row.get('reason')}
        if 'changed_fields' in row:
            entry['fields'] = sorted(row['changed_fields'])
            entry['value'] = row['changed_fields'].get('value')
        else:
            entry['value'] = {side: (row[side] or {}).get('value') for side in ('before', 'after')}
        changed_values.append(entry)
    return {
        'status': 'MEASURED', 'arms': {'baseline': baseline, 'updated': updated},
        'contract': result['comparison'], 'runs': result['runs'], 'eligible_cohort': result['formal_c1'],
        'project_ids': {'stable': len(old_ids & new_ids), 'added': sorted(new_ids - old_ids),
                        'removed': sorted(old_ids - new_ids)},
        'selection_counts': result['criterion_selection_counts'], 'selection_differences': changed_values,
        'new_canonical_storage_rows': result['new_canonical_observations'],
        'candidate_change_counts': result.get('numeric_candidate_changes', {}).get('counts', {}),
        'independent_evidence_gain': result['evidence_change_accounting']['independent_research_evidence_gain'],
        'panel_totals': {field: sum(panel[field] for panel in panels.values()) for field in CHANGE_COUNTS},
        'panels': panels,
    }


def science_hashes(run):
    panels = run.summary['r_results']
    selected = CORE_SCIENCE_FILES & run.hashes.keys()
    selected |= {name for name in run.hashes if name.split('/')[0] in panels
                 and Path(name).name not in PANEL_EXECUTION_FILES}
    for name in sorted(selected):
        run.path(name)
    admission = run.json('resource_admission.json')
    return {name: run.hashes[name] for name in sorted(selected)} | {
        'resource_admission.json/scientific_payload': digest({key: value for key, value in admission.items()
                                                               if key not in {'run_id', 'cache'}}),
    }


def replay_effect(runs, work):
    if missing := sorted(set(REPLAY) - runs.keys()):
        return {'status': 'UNMEASURED', 'missing_arms': missing}
    before = _FormalInputs(runs[REPLAY[0]])
    reference = science_hashes(before)
    comparisons = {}
    for name in REPLAY[1:]:
        after = _FormalInputs(runs[name])
        contract = compare(before.folder, after.folder, work / name, mode='replay')
        hashes = science_hashes(after)
        differences = sorted(key for key in reference.keys() | hashes.keys() if reference.get(key) != hashes.get(key))
        comparisons[name] = {'differences': differences, 'scientific_artifacts': len(hashes),
                             'scientific_manifest_sha256': digest(hashes), 'comparison': contract['comparison']['kind']}
    equal = all(not comparison['differences'] for comparison in comparisons.values())
    return {'status': 'EQUAL' if equal else 'DIFFERENT', 'baseline': REPLAY[0],
            'baseline_scientific_artifacts': len(reference), 'baseline_scientific_manifest_sha256': digest(reference),
            'comparisons': comparisons, 'scientific_manifest_fields': sorted(reference),
            'excluded_panel_execution_files': sorted(PANEL_EXECUTION_FILES),
            'excluded_admission_execution_fields': ['cache', 'run_id']}


def run_performance(name, run, measured):
    result = {field: measured[field] for field in (
        'proc_wall_seconds', 'max_rss_kib', 'sqlite_integrity', 'cache_sizes_bytes', 'cache_mode', 'cache_status',
        'cohort_cache_status', 'command', 'source_lock_sha256', 'seed_database_sha256',
    )}
    r_receipts = [run.json(file) for file in sorted(run.hashes)
                  if Path(file).name in ('r_cache.json', 'r_cohort_cache.json')]
    r_states = Counter(item['status'] for item in r_receipts)
    result['r_execution'] = {'receipts': len(r_receipts), 'states': dict(r_states),
                             'elapsed_seconds': sum(item['elapsed_seconds'] for item in r_receipts),
                             'bundle_keys_sha256': digest(sorted(item['key'] for item in r_receipts))}
    if 'resource_admission.json' in run.hashes:
        admission = run.json('resource_admission.json')
        cache = admission.get('cache', {})
        computed = Counter((row['stage'], row['key']) for row in cache.get('events', ())
                           if row['state'] == 'COMPUTED')
        result['document_and_retrieval_execution'] = {
            'admission_counts': admission['counts'], 'frame_counts': admission.get('frame_counts'),
            'cache_counts': cache.get('counts'), 'stage_seconds': cache.get('stage_seconds'),
            'repeated_computations_same_stage_and_key': sum(total - 1 for total in computed.values()),
        }
    result['case'] = name
    result['cutoff'] = run.summary['cutoff']
    result['code'] = run.summary['code']
    result['scientific_environment'] = run.summary['environment']
    result['sqlite_foreign_key_violations'] = measured.get('sqlite_foreign_key_violations', 0)
    return result


def formal_replay_evidence(run, measured):
    project_ids = sorted(exact_projects(run))
    census_files = [name for name in sorted(run.hashes) if name.startswith('project-summary/') and name.endswith('.csv')]
    panels = {}
    for name, details in run.summary['r_results'].items():
        outputs = {}
        if details['status'] == 'COMPLETED':
            for filename in ('matrix.csv', 'ranking.csv'):
                relative = f'{name}/{filename}'
                run.path(relative)
                outputs[relative] = run.hashes[relative]
        panels[name] = {'status': details['status'], 'projects': details['n'], 'sha256': outputs}
    return {
        'run_id': run.summary['run_id'], 'status': run.summary['status'], 'code': run.summary['code'],
        'cutoff': run.summary['cutoff'], 'command': measured['command'],
        'source_count': run.summary['source_count'], 'snapshot_sha256': run.summary['snapshot_sha256'],
        'locked_input_file_sha256': measured['source_lock_sha256'],
        'logical_database_sha256': run.summary['logical_database_sha256'],
        'sqlite_integrity': measured['sqlite_integrity'],
        'sqlite_foreign_key_violations': measured.get('sqlite_foreign_key_violations', 0),
        'projects': {'count': len(project_ids), 'sha256': digest(project_ids)},
        'census_csv': {name: {'sha256': run.hashes[name], 'rows': len(run.csv(name))} for name in census_files},
        'selected_input_sha256': {name: run.hashes[name] for name in ('resources.csv', 'criteria_resolution.csv',
                                                                     'value_trace.csv') if run.path(name)},
        'eligibility': run.json('eligibility_audit.json'), 'panel_results': panels,
    }


def reference_effect(report):
    panels = report['panels']
    return {
        'runs': report['runs'], 'contract': report['comparison'],
        'selection_counts': report['criterion_selection_counts'],
        'candidate_counts': report.get('numeric_candidate_changes', {}).get('counts', {}),
        'new_canonical_storage_rows': report['new_canonical_observations'],
        'changed_selection': [{'id': row['identity'], 'kind': row['change_kind'], 'reason': row.get('reason')}
                              for row in report['selection_differences']],
        'panel_count_in_comparator': len(panels),
        'panels': {name: {key: panel[key] for key in PANEL_FIELDS} for name, panel in sorted(panels.items())},
        'panel_totals': {field: sum(panel[field] for panel in panels.values()) for field in CHANGE_COUNTS},
    }


def _normalizer(root, commit):
    path = 'src/au_ree_v2/normalization.py'
    code = subprocess.check_output(['git', 'show', f'{commit}:{path}'], cwd=root)
    scope = {'__name__': f'cutoff_normalization_{commit[:8]}'}
    exec(compile(code, f'{commit}:{path}', 'exec'), scope)
    blob = subprocess.check_output(['git', 'rev-parse', f'{commit}:{path}'], cwd=root, text=True).strip()
    return scope['normalize_cutoff'], blob


def normalization_component(root, snapshot, admission):
    """Run both tagged normalizers on the same source-bound cutoff input."""
    locks = read_json(snapshot)
    locks = locks['sources'] if isinstance(locks, dict) else locks
    bindings = {row['sha256']: row for row in locks}
    baseline, baseline_blob = _normalizer(root, NORMALIZERS[0])
    current, current_blob = _normalizer(root, NORMALIZERS[1])
    checks = {}
    for candidate in admission['dispositions']:
        for observation in candidate['observations']:
            raw = observation['raw']
            cutoff = dict(raw['context']['conditions']).get('cutoff_grade')
            if not cutoff:
                continue
            value = json.loads(cutoff)
            for anchor in raw['evidence_anchors']:
                if anchor['role'] != 'reported_cutoff' or anchor['sha256'] != candidate['source_sha256']:
                    continue
                key = (anchor['sha256'], anchor['page'], cutoff)
                if key in checks:
                    continue
                checks[key] = {'source_sha256': anchor['sha256'], 'page': anchor['page'],
                               'source_key': candidate['source_key'], 'reported': value,
                               'anchor_view': anchor.get('locator'),
                               'baseline': baseline(value), 'current': current(value)}
    for sha in {key[0] for key in checks}:
        if filehash(root / bindings[sha]['path']) != sha:
            raise ValueError(f'Normalization component requires original {sha}')
    rows = [checks[key] for key in sorted(checks)]
    return {'status': 'MEASURED_COMPONENT', 'input': 'Archived reported cutoffs checked against locked original SHAs',
            'versions': {'baseline': {'commit': NORMALIZERS[0], 'blob': baseline_blob},
                         'current': {'commit': NORMALIZERS[1], 'blob': current_blob}},
            'inputs': len(rows), 'changed': sum(row['baseline'] != row['current'] for row in rows),
            'distinct_source_values': len({(sha, cutoff) for sha, _, cutoff in checks}),
            'rows': rows, 'isolated_end_to_end_selection_and_rank_effect': 'UNMEASURED'}


def write_references(bundle, rule_receipt, recovery, destination):
    root = Path(__file__).resolve().parents[1]
    snapshot = root / 'results/phase22-2026-11-06/snapshot_lock.json'
    with ZipFile(bundle) as archive:
        effects = {name: reference_effect(json.loads(archive.read(entry))) | {'archive_entry': entry}
                   for name, entry in REFERENCE.items()}
        fulltext, = [name for name in archive.namelist() if name.startswith('resource-admission-validation-frame/runs/')
                     and name.endswith('/resource_admission.json')]
        component = normalization_component(root, snapshot, json.loads(archive.read(fulltext)))
    source_update = read_json(recovery)
    result = {
        'schema': 'phase10-reference-effects-v1',
        'historical_phase22': {'cutoff': '2026-11-05', 'scope': 'Archived eight-source release validation',
                               'snapshot_file_sha256': filehash(snapshot),
                               'reference_archive_sha256': filehash(bundle), 'effects': effects,
                               'normalization_component': component | {'archive_entry': fulltext}},
        'source_recovery': {'cutoff': '2026-11-13', 'recovery_manifest_sha256': filehash(recovery),
                            'availability_effect': {key: source_update[key] for key in (
                                'locked_assets', 'verified_assets', 'prior_verified_assets_same_contract',
                                'net_new_exact_vs_prior', 'source_unavailable')},
                            'selection_matrix_and_rank_effect': source_update['historical_93']},
    }
    if rule_receipt:
        reference = read_json(rule_receipt)
        revisions = [reference['runs'][side]['code']['commit'] for side in ('baseline', 'updated')]
        changed_modules = subprocess.check_output(['git', 'diff', '--name-only', *revisions, '--', 'src', 'R'],
                                                  cwd=root, text=True).splitlines()
        result['historical_phase22']['joint_rule_release'] = reference_effect(reference) | {
            'release_receipt_sha256': filehash(rule_receipt),
            'changed_modules': changed_modules,
            'interpretation': 'Together: admission, normalization, reporting-date, resource layout and evidence binding changes.',
        }
    atomic_json(destination, result)


def write_reference_performance(folder, destination):
    runs = {}
    witness = folder / 'cache-seed-replay-check.json'
    reference = read_json(witness)
    for mode, label in (('off', 'final-disabled'), ('cold', 'final-disabled-cold'),
                        ('warm', 'final-disabled-warm')):
        summary_path = folder / 'formal-runs' / label / 'summary.json'
        admission_path = summary_path.with_name('resource_admission.json')
        measurement_path = folder / 'run-metadata' / f'{label}.json'
        summary = read_json(summary_path)
        admission = read_json(admission_path)
        measured = read_json(measurement_path)
        cache = admission['cache']
        computed = Counter((event['stage'], event['key']) for event in cache['events'] if event['state'] == 'COMPUTED')
        runs[mode] = {
            'wall_seconds': measured['runtime_seconds'], 'peak_rss_kib': None,
            'sqlite_integrity': measured['sqlite_integrity'], 'sqlite_foreign_key_violations': measured['sqlite_foreign_key_violations'],
            'code': summary['code'], 'cutoff': summary['cutoff'], 'run_id': summary['run_id'],
            'logical_database_sha256': summary['logical_database_sha256'], 'snapshot_sha256': summary['snapshot_sha256'],
            'admission_science_sha256': admission['scientific_sha256'],
            'r_core_cache': dict(Counter(item['cache_status'] for item in summary['r_results'].values())),
            'r_cohort_cache': dict(Counter(item['cohort_cache_status'] for item in summary['r_results'].values())),
            'derived_cache_counts': cache['counts'], 'stage_seconds': cache['stage_seconds'],
            'computed_again_same_stage_and_key': sum(count - 1 for count in computed.values()),
            'run_metadata_sha256': filehash(measurement_path), 'summary_sha256': filehash(summary_path),
            'admission_receipt_sha256': filehash(admission_path),
            'analytical_environment': summary['environment'], 'python_hash_seed': measured['python_hash_seed'],
        }
    same = all(len({run[key] for run in runs.values()}) == 1 for key in (
        'admission_science_sha256', 'logical_database_sha256', 'snapshot_sha256'))
    atomic_json(destination, {'schema': 'phase10-reference-performance-v1', 'runs': runs,
                'scope': 'Eight locked original PDFs, Phase 22 analytical baseline, Round 9 exact sealed controls.',
                'reference_scientific_status': reference['status'],
                'reference_scientific_artifacts_checked': len(reference['scientific_artifact_sha256']),
                'source_admission_and_database_identity_equal': same, 'reference_witness_sha256': filehash(witness),
                'limitations': ['One run per mode', 'Peak RSS and cache bytes were unrecorded on these runs',
                                'The PDF stage counts processed cache units, including different parsing profiles']})


def main(argv=None):
    argp = argparse.ArgumentParser(description=__doc__)
    mode = argp.add_mutually_exclusive_group(required=True)
    mode.add_argument('--runs', type=Path, help='Measured run paths and failures JSON')
    mode.add_argument('--r9-review-zip', type=Path, help='Archive supplied with the Round 9 CI review')
    argp.add_argument('--r9-rule-receipt', type=Path, help='Separately sealed Round 9 code/rule release comparison')
    argp.add_argument('--r9-performance-directory', type=Path, help='Prior exact benchmark receipts directory')
    argp.add_argument('--recovery', type=Path, help='Historical 2026-11-13 source recovery manifest')
    argp.add_argument('--out', type=Path, required=True, help='Output receipt directory')
    args = argp.parse_args(argv)
    if args.r9_review_zip:
        if not args.recovery:
            argp.error('--r9-review-zip requires --recovery')
        write_references(args.r9_review_zip, args.r9_rule_receipt, args.recovery, args.out / 'reference-effects.json')
        if args.r9_performance_directory:
            write_reference_performance(args.r9_performance_directory, args.out / 'reference-performance.json')
        return 0
    inventory = read_json(args.runs)
    runs = {name: Path(path) for name, path in inventory['runs'].items()}
    args.out.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=inventory.get('area')) as scratch:
        work = Path(scratch)
        effects = {name: factor_effect(pair, runs, work / name) for name, pair in COMPARISONS.items()}
        replay = replay_effect(runs, work / 'replay')
    effects.update({
        'resource_admission_rule_revision': {'status': 'UNMEASURED',
                                             'reason': 'Released comparisons combine the rule and normalization revisions.'},
        'normalization': {'status': 'UNMEASURED',
                          'reason': 'The sealed runs lack a selective old/current normalization switch.'},
        'source_recovery': {'status': 'UNMEASURED',
                            'reason': 'The Phase 22 replay keeps the source availability manifest fixed.'},
    })
    atomic_json(args.out / 'factor-effects.json', {'schema': 'phase10-factor-effects-v1',
                'scope': {'cutoff': '2026-11-05', 'historical_phase': 'Phase 22',
                          'admission_frame': 'resource_admission_frame_v1.json'},
                'effects': effects, 'failed_arms': inventory['failures']})
    performance = {name: run_performance(name, _FormalInputs(path), read_json(args.runs.parent / f'{name}.json'))
                   for name, path in runs.items()}
    atomic_json(args.out / 'performance.json', {'schema': 'phase10-replay-performance-v1', 'runs': performance,
                'equivalence': replay,
                'timing_boundary': 'Complete rebuild subprocess on the same machine, excluding database seed copy.',
                'peak_rss_basis': 'Linux wait4 ru_maxrss, maximum of the measured process and reaped descendants.',
                'unmeasured_operations': ['Physical PDF opens outside the derived cache', 'OCR and table parser subprocess counts']})
    subset = 'current-fixed' if 'current-fixed' in runs else 'current-full-off'
    if fixed := runs.get(subset):
        known_run = formal_replay_evidence(_FormalInputs(fixed), read_json(args.runs.parent / f'{subset}.json'))
        atomic_json(args.out / 'verified-subset.json', {'schema': 'phase10-verified-subset-v1', **known_run})
    return int(replay['status'] == 'DIFFERENT')


if __name__ == '__main__':
    raise SystemExit(main())
