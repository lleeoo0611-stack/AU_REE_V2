"""Compare source-bound resource admission using two regular formal analyses."""

import ast
import json
from pathlib import Path

from .derived_cache import atomic_json
from .formal_resource_bridge import GATES, PANEL, _FormalInputs, _compare
from .selection_rules import RESOURCE_ADMISSION_VERSION
from .store import digest, filehash


VERSION = 'formal-resource-refresh-v1'
RANK_NUMBERS = ('promethee', 'saw', 'topsis', 'promethee_rank', 'saw_rank', 'topsis_rank')


def _checked_inputs(run):
    cfg = run.json('configuration.json')
    snapshots = run.json('snapshot_lock.json')
    summary = run.summary
    if (digest(cfg), digest(snapshots)) != (summary['configuration_sha256'], summary['snapshot_sha256']):
        raise ValueError('REFRESH_CONFIGURATION_OR_SNAPSHOT_NOT_SEALED')
    contract = cfg.get('resource_admission')
    receipt_name = 'resource_admission.json'
    if bool(contract) != (receipt_name in run.hashes):
        raise ValueError('REFRESH_ADMISSION_RECEIPT_PRESENCE_MISMATCH')
    receipt = run.json(receipt_name) if contract else None
    if receipt is not None:
        expected = {key: contract[key] for key in ('frame_sha256', 'rules_sha256', 'canonical_observation_ids')}
        if ('active_admission_observation_ids' in contract) != ('active_admission_observation_ids' in receipt):
            raise ValueError('REFRESH_ACTIVE_ADMISSION_IDS_NOT_BOUND_TO_RUN')
        if 'active_admission_observation_ids' in contract:
            expected['active_admission_observation_ids'] = contract['active_admission_observation_ids']
        expected.update(run_id=summary['run_id'], cutoff=summary['cutoff'], snapshot_sha256=summary['snapshot_sha256'])
        if any(receipt.get(key) != value for key, value in expected.items()):
            raise ValueError('REFRESH_ADMISSION_RECEIPT_NOT_BOUND_TO_RUN')
    return cfg, snapshots, receipt


def _selection(run):
    selected = []
    membership = {row['entity_id']: row['canonical_id'] for row in run.csv('canonical_membership.csv')}
    for row in run.csv('resources.csv'):
        raw_ids = ast.literal_eval(row['obs_ids'])
        selected.append({**row, 'criterion': 'R1', 'project_id': row['entity_id'],
                         'canonical_project_id': membership.get(row['entity_id'], row['entity_id']),
                         'observation_ids': raw_ids, 'unit': 'kt TREO', 'value': row['contained_treo_kt'],
                         'status': 'SELECTED_RESOURCE_STATEMENT'})
    for row in run.csv('criteria_resolution.csv'):
        if row['criterion'] != 'S1':
            continue
        selected.append({**row, 'project_id': row['canonical_project_id'],
                         'observation_ids': json.loads(row['evidence_ids']), 'unit': '% PrNdDyTb REO / TREO',
                         'provenance': json.loads(row['provenance'])})
    audited = run.optional_csv('resource_scope_selection.csv')
    return sorted(selected, key=lambda row: (row['project_id'], row['criterion'])), audited


def _value_traces(run):
    selected = []
    for row in run.csv('value_trace.csv'):
        criterion = row['criterion']
        if criterion not in ('R1', 'S1'):
            continue
        provenance = json.loads(row['source'])
        if criterion == 'R1' and not ('obs_ids' in provenance and 'contained_treo_kt' in provenance):
            continue  # Wa government screen has a separately defined R1 input.
        selected.append(row)
    return selected


def _panel(run, name):
    prefix = name + '/'
    matrices = run.optional_csv(prefix + 'matrix.csv')
    ranks = run.optional_csv(prefix + 'ranking.csv')
    criteria = run.optional_csv(prefix + 'criteria.csv')
    weights = run.optional_csv(prefix + 'weights.csv')
    status = run.summary.get('r_results', {}).get(name)
    if status and (status['n'] != len(matrices) or status['status'] == 'COMPLETED' and not ranks):
        raise ValueError('REFRESH_PANEL_OUTPUT_COUNT_MISMATCH: ' + name)
    return matrices, ranks, criteria, weights, status


def _panel_delta(before, after, name, changed_inputs):
    old, old_ranks, old_criteria, old_weights, old_status = _panel(before, name)
    new, new_ranks, new_criteria, new_weights, new_status = _panel(after, name)
    if old_criteria and new_criteria and (old_criteria != new_criteria or old_weights != new_weights):
        raise ValueError('REFRESH_COMPARISON_CHANGED_CRITERIA_OR_WEIGHTS: ' + name)
    codes = {row['code'] for row in old_criteria + new_criteria}
    numeric = {code + suffix for code in codes for suffix in ('', '_alt', '_lower', '_upper')}
    matrix = _compare(old, new, ('project_id',), numeric)
    ranking = _compare(old_ranks, new_ranks, ('scenario', 'project_id'), RANK_NUMBERS)
    prior_ids = {r['project_id'] for r in old}
    current_ids = {r['project_id'] for r in new}
    cohort_changed = prior_ids != current_ids
    changed_matrix_ids = {row['identity'][0] for row in matrix}
    for row in matrix:
        pid = row['identity'][0]
        row['cause'] = ('COHORT_MEMBERSHIP' if pid not in prior_ids & current_ids else
                        'DIRECT_CRITERION_INPUT_CHANGE' if pid in changed_inputs else 'INDIRECT_MATRIX_OR_SCOPE_CHANGE')
    for row in ranking:
        pid = row['identity'][1]
        row['cause'] = ('COHORT_MEMBERSHIP' if pid not in prior_ids & current_ids else
                        'DIRECT_INPUT_AND_COHORT' if pid in changed_matrix_ids and cohort_changed else
                        'DIRECT_MATRIX_OR_METADATA_CHANGE' if pid in changed_matrix_ids else
                        'COHORT_AND_SHARED_NORMALIZATION' if cohort_changed else
                        'PEER_VALUE_OR_SHARED_NORMALIZATION')
    def cells(row):
        if 'changed_fields' in row:
            return row['changed_fields'].keys()
        return {key for key, value in (row['before'] or row['after']).items() if value not in ('', None)}

    return {'criteria': sorted(codes),
            'research_panel': True, 'formal_c1_admission': False,
            'baseline_projects': len(prior_ids), 'updated_projects': len(current_ids),
            'cohort_added': sorted(current_ids - prior_ids), 'cohort_removed': sorted(prior_ids - current_ids),
            'affected_matrix_projects': sorted(changed_matrix_ids),
            'affected_ranking_projects': sorted({row['identity'][1] for row in ranking}),
            'baseline_r_status': old_status['status'] if old_status else 'NOT_RUN',
            'updated_r_status': new_status['status'] if new_status else 'NOT_RUN',
            'matrix_cells_changed': sum(len(cells(row) & numeric) for row in matrix),
            'matrix_primary_criterion_cells_changed': sum(len(cells(row) & codes) for row in matrix),
            'ranking_score_cells_changed': sum(len(cells(row) & {'promethee', 'saw', 'topsis'}) for row in ranking),
            'rank_position_cells_changed': sum(len(cells(row) & {'promethee_rank', 'saw_rank', 'topsis_rank'})
                                               for row in ranking),
            'matrix_differences': matrix, 'ranking_differences': ranking}


def _identity(run, cfg):
    return {key: run.summary[key] for key in
            ('run_id', 'cutoff', 'code', 'configuration_sha256', 'snapshot_sha256', 'logical_database_sha256')} | {
        'research_config_sha256': digest(cfg['research']), 'monte_carlo': cfg['research']['monte_carlo']}


def compare(baseline_run, updated_run, output):
    """Publish an auditable selection snapshot and pre/post scientific differences."""
    baseline_run, updated_run, output = map(lambda path: Path(path).resolve(), (baseline_run, updated_run, output))
    if (baseline_run == updated_run or any(output.is_relative_to(folder) or folder.is_relative_to(output)
                                           for folder in (baseline_run, updated_run))):
        raise ValueError('REFRESH_REQUIRES_SEPARATE_RUN_AND_DIFF_OUTPUTS')
    before, after = _FormalInputs(baseline_run), _FormalInputs(updated_run)
    old_cfg, old_lock, old_admit = _checked_inputs(before)
    cfg, lock, admit = _checked_inputs(after)
    if admit is None:
        raise ValueError('REFRESH_REQUIRES_ACTUAL_ADMISSION_RUN')
    fixed = ('research', 'claims_sha256', 'identity_links.json_sha256', 'study_cases.json_sha256',
             'eligibility_policy_sha256', 'census_filter', 'source_mode')
    if (before.summary['cutoff'] != after.summary['cutoff'] or any(old_cfg.get(k) != cfg.get(k) for k in fixed)):
        raise ValueError('REFRESH_COMPARISON_REQUIRES_SAME_RESEARCH_CONTRACT')
    old_selection, old_scope = _selection(before)
    selection, scope = _selection(after)
    selection_numeric = ('value', 'contained_treo_kt', 'ore_mt', 'grade_pct', 'calculated_from_rounded_inputs_kt')
    selected_delta = _compare(old_selection, selection, ('project_id', 'criterion'), selection_numeric)
    traces = _compare(_value_traces(before), _value_traces(after), ('entity_id', 'criterion'), ('raw_value', 'score'))
    raw_changed = [r for r in traces if 'changed_fields' not in r or 'raw_value' in r['changed_fields']]
    scope_delta = {'before': old_scope, 'after': scope} if scope != old_scope else None
    direct_projects = {r['identity'][0] for r in raw_changed}
    panels = {name for name, codes in cfg['research']['panels'].items() if {'R1', 'S1'} & set(codes)}
    for name in before.summary.get('r_results', {}).keys() | after.summary.get('r_results', {}).keys():
        criteria = before.optional_csv(name + '/criteria.csv') + after.optional_csv(name + '/criteria.csv')
        if any(r['code'] in ('R1', 'S1') for r in criteria):
            panels.add(name)
    panel_diffs = {name: _panel_delta(before, after, name, direct_projects) for name in sorted(panels)}
    panel_diffs = {name: value for name, value in panel_diffs.items() if name == PANEL or 'R1' in value['criteria']
                   or 'S1' in value['criteria']}
    gate_diffs = _compare(before.csv('formal_gate_compatibility.csv'), after.csv('formal_gate_compatibility.csv'),
                         ('canonical_project_id', 'gate'))
    eligibility_diffs = _compare(before.csv('eligibility_cohorts.csv'), after.csv('eligibility_cohorts.csv'),
                                ('canonical_project_id',))
    old_eligibility, eligibility = before.json('eligibility_audit.json'), after.json('eligibility_audit.json')
    old_ids = {row['obs_id'] for row in before.json('logical_database.json')['observations']}
    admitted_ids = set(admit['canonical_observation_ids'])
    if len(admitted_ids) != len(admit['canonical_observation_ids']):
        raise ValueError('REFRESH_DUPLICATE_ADMISSION_OBSERVATION_ID')
    accepted_rows = {row['obs_id']: row for row in after.json('logical_database.json')['observations']
                     if row['obs_id'] in admitted_ids}
    if set(accepted_rows) != admitted_ids:
        raise ValueError('REFRESH_ADMISSION_RECEIPT_DOES_NOT_MATCH_CANONICAL_ROWS')
    active_rows = {identifier: row for identifier, row in accepted_rows.items()
                   if row['transform_version'] == RESOURCE_ADMISSION_VERSION}
    if ('active_admission_observation_ids' in admit
            and admit['active_admission_observation_ids'] != sorted(active_rows)):
        raise ValueError('REFRESH_ACTIVE_ADMISSION_IDS_DO_NOT_MATCH_CANONICAL_ROWS')
    new_ids = active_rows.keys() - old_ids
    selection_counters = {'added': 0, 'updated': 0, 'removed': 0, 'provenance_or_disposition_only': 0}
    input_changes = set()
    for entry in selected_delta:
        fields = entry.get('changed_fields')
        if fields is None:
            old_val, new_val = ((entry.get(side) or {}).get('value') for side in ('before', 'after'))
        else:
            old_val, new_val = ((fields.get('value') or {}).get(side) for side in ('before', 'after'))
        if old_val in ('', None) and new_val not in ('', None):
            change = 'added'
        elif new_val in ('', None) and old_val not in ('', None):
            change = 'removed'
        elif old_val not in ('', None) and new_val not in ('', None):
            change = 'updated'
        else:
            change = 'provenance_or_disposition_only'
        entry['change_kind'] = change
        selection_counters[change] += 1
        if change != 'provenance_or_disposition_only':
            input_changes.add(entry['identity'][0])
    consumed = sorted({obs for row in selection for obs in row['observation_ids']} & active_rows.keys())
    identities = {'baseline': _identity(before, old_cfg), 'updated': _identity(after, cfg)}
    selection_snapshot = {'version': VERSION, 'run': identities['updated'], 'criteria': selection,
                          'resource_scope_decisions': scope, 'active_admission_observation_ids': sorted(active_rows),
                          'selected_admission_provenance': [dict(active_rows[obs], raw=json.loads(active_rows[obs]['raw']))
                                                            for obs in consumed],
                          'criteria_sha256': digest(selection), 'scope_decisions_sha256': digest(scope)}
    atomic_json(output / 'selection_snapshot.json', selection_snapshot)
    observed = old_admit.get('canonical_observation_ids', []) if old_admit else []
    snapshot_delta = _compare(old_lock, lock, ('key',))
    receipt = {'version': VERSION, 'status': 'COMPLETE', 'runs': identities,
               'admission_receipt_sha256': after.hashes['resource_admission.json'],
               'selection_snapshot_sha256': filehash(output / 'selection_snapshot.json'),
               'admitted_observation_ids': sorted(admitted_ids), 'previous_admission_observation_ids': observed,
               'new_canonical_observation_ids': sorted(new_ids), 'new_canonical_observations': len(new_ids),
               'new_canonical_projects': sorted({active_rows[obs]['entity_id'] for obs in new_ids}),
               'active_admission_ids_in_selected_inputs': consumed,
               'sources_changed': snapshot_delta, 'scope_decisions_changed': scope_delta,
               'selection_differences': selected_delta, 'criterion_selection_counts': selection_counters,
               'criterion_trace_differences': traces,
               'numeric_selection_projects': sorted(input_changes), 'changed_raw_input_projects': sorted(direct_projects),
               'formal_c1': {'required_gates': GATES, 'baseline': old_eligibility, 'updated': eligibility,
                             'gate_differences': gate_diffs, 'project_eligibility_differences': eligibility_diffs},
               'panels': panel_diffs, 'input_artifact_sha256': {'baseline': before.read_hashes, 'updated': after.read_hashes}}
    atomic_json(output / 'resource_refresh.json', receipt)
    return receipt
