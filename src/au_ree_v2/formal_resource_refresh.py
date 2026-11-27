"""Compare source-bound resource admission using two regular formal analyses."""

import ast
from collections import Counter
from datetime import datetime
import json
from pathlib import Path

from .analysis import weight_calculation_version
from .derived_cache import atomic_json
from .formal_resource_bridge import GATES, PANEL, _FormalInputs, _compare, equivalent_weight_rows
from .selection_rules import is_automatic_resource_admission
from .store import digest, filehash


VERSION = 'formal-resource-refresh-v5'
RANK_NUMBERS = ('promethee', 'saw', 'topsis', 'promethee_rank', 'saw_rank', 'topsis_rank')
COMPARISON_MODES = frozenset({'auto', 'rule_effect', 'admission_effect', 'retrieval_effect', 'source_update', 'replay'})
SOURCE_TRANSPORT_FIELDS = frozenset({'path', 'url', 'acquired_at'})
MCDA_PROTOCOL_FIELDS = frozenset({'mcda_weight_calculation', 'mcda_trace_panel'})


def _mcda_protocol(config):
    research = config['research']
    return {'weight_calculation': weight_calculation_version(research),
            'additional_rank_trace_panel': research.get('mcda_trace_panel')}


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
        has_retrieval = 'retrieval' in contract
        if (has_retrieval != ('retrieval' in receipt) or
                has_retrieval != ('effective_frame_sources_sha256' in contract) or
                has_retrieval != ('effective_frame_sources' in receipt)):
            raise ValueError('REFRESH_RETRIEVAL_SCOPE_NOT_BOUND_TO_RUN')
        if has_retrieval:
            expected['retrieval'] = contract['retrieval']
            expected['effective_frame_sources_sha256'] = contract['effective_frame_sources_sha256']
            if digest(receipt['effective_frame_sources']) != contract['effective_frame_sources_sha256']:
                raise ValueError('REFRESH_RETRIEVAL_SCOPE_NOT_BOUND_TO_RUN')
        if contract.get('frame_validation') != receipt.get('frame_validation'):
            raise ValueError('REFRESH_FRAME_VALIDATION_NOT_BOUND_TO_RUN')
        expected.update(run_id=summary['run_id'], cutoff=summary['cutoff'], snapshot_sha256=summary['snapshot_sha256'])
        if any(receipt.get(key) != value for key, value in expected.items()):
            raise ValueError('REFRESH_ADMISSION_RECEIPT_NOT_BOUND_TO_RUN')
        reference_config = {key: value for key, value in cfg.items() if key != 'resource_admission'}
        if ('baseline_configuration_sha256' in contract and
                (contract['baseline_configuration_sha256'] != digest(reference_config)
                 or receipt.get('baseline_configuration_sha256') != contract['baseline_configuration_sha256'])):
            raise ValueError('REFRESH_ADMISSION_BASE_CONFIGURATION_NOT_BOUND_TO_RUN')
        if 'rules' in receipt and digest(receipt['rules']) != receipt['rules_sha256']:
            raise ValueError('REFRESH_RULES_FINGERPRINT_MISMATCH')
    return cfg, snapshots, receipt


def _source_binding(source):
    fields = {key: value for key, value in source.items() if key not in SOURCE_TRANSPORT_FIELDS}
    if 'acquired_at' in source:
        # The timestamp's presence and well-formedness are admission evidence.
        # Transport timestamps that pass the same guard do not alter the edition.
        try:
            fields['acquired_at_with_timezone'] = datetime.fromisoformat(source['acquired_at']).tzinfo is not None
        except (ValueError, TypeError):
            fields['acquired_at_with_timezone'] = False
    return fields


def _frame_scope(receipt):
    if 'frame_sources' not in receipt:
        return receipt['frame_sha256']
    return sorted((source['source_key'], tuple(sorted(source['pages'])), tuple(sorted(source.get('context_pages', ()))))
                  for source in receipt['frame_sources'])


def _retrieval_scope(receipt, lock):
    if receipt is None:
        return None
    policy = receipt.get('retrieval', {'mode': 'fixed'})
    rows = receipt.get('effective_frame_sources')
    if rows is None and 'frame_sources' in receipt:
        selected = {(item['key'], item['sha256']) for item in lock}
        rows = [item for item in receipt['frame_sources'] if (item['source_key'], item['source_sha256']) in selected]
    return {'policy': policy, 'effective_frame_sources': rows}


def _comparison_contract(before, after, old_cfg, cfg, old_lock, lock, old_admit, admit, mode):
    if mode not in COMPARISON_MODES:
        raise ValueError('UNKNOWN_RESOURCE_REFRESH_COMPARISON_MODE')
    old_code, code = before.summary['code'], after.summary['code']
    if old_code.get('content_sha256') and code.get('content_sha256'):
        code_changed = old_code['content_sha256'] != code['content_sha256']
    else:
        code_changed = old_code != code
    raw_source_delta = _compare(old_lock, lock, ('key',))
    binding_delta = _compare([_source_binding(row) for row in old_lock],
                             [_source_binding(row) for row in lock], ('key',))
    edition_keys = {'sha256', 'source_document_version'}
    edition_delta = [row for row in binding_delta
                     if 'changed_fields' not in row or edition_keys & row['changed_fields'].keys()]
    registry_changed = old_cfg.get('sources') != cfg.get('sources')
    admission_changed = (old_admit is None) != (admit is None)
    both_admit = old_admit is not None and admit is not None
    rules_changed = both_admit and old_admit['rules_sha256'] != admit['rules_sha256']
    frame_changed = both_admit and (_frame_scope(old_admit) != _frame_scope(admit) or
                                    any(old_admit.get(key) != admit.get(key)
                                        for key in ('classification', 'acquired_through')))
    # A changed frame pin is an edition update only when both pins point to the
    # selected editions of the same source; a new inclusion/exclusion is separate.
    if both_admit and not frame_changed and 'frame_sources' in old_admit and 'frame_sources' in admit:
        old_frame, frame = old_admit['frame_sources'], admit['frame_sources']
        old_pins = {row['source_key']: row['source_sha256'] for row in old_frame}
        pins = {row['source_key']: row['source_sha256'] for row in frame}
        old_shas = {row['key']: row['sha256'] for row in old_lock}
        shas = {row['key']: row['sha256'] for row in lock}
        if len(old_pins) != len(old_frame) or len(pins) != len(frame):
            frame_changed = digest(old_frame) != digest(frame)
        else:
            frame_changed = any(old_pins[key] != pins[key] and (old_pins[key], pins[key]) !=
                                (old_shas.get(key), shas.get(key)) for key in old_pins)

    before_protocol, after_protocol = _mcda_protocol(old_cfg), _mcda_protocol(cfg)
    before_retrieval, after_retrieval = _retrieval_scope(old_admit, old_lock), _retrieval_scope(admit, lock)
    # Fixed-to-fixed changes are already attributed to configured pages and the
    # actual source edition. Search policy and its selected pages add a factor.
    retrieval_changed = (both_admit and before_retrieval != after_retrieval and
                         any(item['policy']['mode'] != 'fixed' for item in (before_retrieval, after_retrieval)))
    factors = {'code_or_admission_rules': code_changed or rules_changed,
               'mcda_execution_protocol': before_protocol != after_protocol,
               'admission_enabled': admission_changed, 'admission_frame': frame_changed,
               'admission_retrieval': retrieval_changed,
               'source_inputs': bool(binding_delta) or registry_changed,
               'analytical_runtime': (old_cfg.get('analytical_runtime') != cfg.get('analytical_runtime')
                                      or before.summary.get('environment') != after.summary.get('environment'))}
    active = [name for name, changed in factors.items() if changed]
    if not active:
        kind = 'replay'
    elif both_admit and set(active) <= {'code_or_admission_rules', 'mcda_execution_protocol'}:
        kind = 'rule_effect'
    elif active == ['admission_enabled']:
        kind = 'admission_effect'
    elif active == ['admission_retrieval']:
        kind = 'retrieval_effect'
    elif active == ['source_inputs']:
        kind = 'source_update' if edition_delta else 'source_binding_change'
    elif active == ['admission_frame']:
        kind = 'admission_frame_change'
    else:
        kind = 'mixed_effects'
    if mode != 'auto' and mode != kind:
        raise ValueError(f'REFRESH_COMPARISON_FACTORS_DO_NOT_MATCH: expected={mode}, observed={kind}')
    return {'kind': kind, 'requested_mode': mode, 'changed_factors': active,
            'code_content_changed': code_changed, 'code_commit_changed': old_code.get('commit') != code.get('commit'),
            'rules_changed': rules_changed, 'source_registry_changed': registry_changed,
            'mcda_execution_protocol': {'baseline': before_protocol, 'updated': after_protocol},
            'retrieval_scope': {'baseline': before_retrieval, 'updated': after_retrieval},
            'source_editions_changed': edition_delta,
            'admission_enabled': {'baseline': old_admit is not None, 'updated': admit is not None},
            'frame_sha256': {'baseline': old_admit.get('frame_sha256') if old_admit else None,
                             'updated': admit.get('frame_sha256') if admit else None},
            'rules_sha256': {'baseline': old_admit.get('rules_sha256') if old_admit else None,
                             'updated': admit.get('rules_sha256') if admit else None},
            'source_binding_differences': binding_delta, 'snapshot_record_differences': raw_source_delta}


def _observations(run):
    database = run.json('logical_database.json')
    if digest(database) != run.summary['logical_database_sha256']:
        raise ValueError('REFRESH_LOGICAL_DATABASE_NOT_SEALED')
    rows = {row['obs_id']: row for row in database['observations']}
    if len(rows) != len(database['observations']):
        raise ValueError('REFRESH_DUPLICATE_CANONICAL_OBSERVATION_ID')
    return rows


def _admission_ledger(run, receipt, rows):
    accepted = set(receipt['canonical_observation_ids']) if receipt else set()
    if receipt is not None and len(accepted) != len(receipt['canonical_observation_ids']):
        raise ValueError('REFRESH_DUPLICATE_ADMISSION_OBSERVATION_ID')
    if not accepted.issubset(rows):
        raise ValueError('REFRESH_ADMISSION_RECEIPT_DOES_NOT_MATCH_CANONICAL_ROWS')
    automatic = {identifier: row for identifier, row in rows.items() if is_automatic_resource_admission(row)}
    active = accepted & automatic.keys()
    if receipt is not None and ('active_admission_observation_ids' in receipt
                                and receipt['active_admission_observation_ids'] != sorted(active)):
        raise ValueError('REFRESH_ACTIVE_ADMISSION_IDS_DO_NOT_MATCH_CANONICAL_ROWS')
    ledger = {'enabled': receipt is not None, 'accepted_observation_ids': sorted(accepted),
              'enabled_automatic_observation_ids': sorted(active),
              'inactive_automatic_observation_ids': sorted(automatic.keys() - active),
              'reused_legacy_observation_ids': sorted(accepted - active)}
    if receipt is not None:
        ledger['receipt_sha256'] = run.hashes['resource_admission.json']
        for key in ('counts', 'frame_counts', 'source_dispositions', 'excluded_sources', 'observation_actions',
                    'source_counts', 'retrieval_sources', 'frame_validation'):
            if key in receipt:
                ledger[key] = receipt[key]
    return ledger, {identifier: automatic[identifier] for identifier in active}


def _observation_trace(row):
    raw = json.loads(row.get('raw', '{}'))
    return {key: row[key] for key in ('obs_id', 'entity_id', 'statement_id', 'scope', 'source_sha', 'locator', 'variable',
                                      'effective_date', 'unit', 'basis', 'value', 'transform_version') if key in row} | {
        key: raw[key] for key in ('admission_bundle_id', 'estimate_id', 'cutoff_grade', 'deposit_id',
                                  'resource_identity_link') if key in raw}


def _selection_evidence(project, selected, scope, observations, receipt):
    identifiers = (selected or {}).get('observation_ids', ())
    candidate_keys = ('source_key', 'source_sha256', 'physical_page', 'table', 'row', 'status', 'reasons',
                      'canonical_observation_ids', 'historical_link', 'historical_conflict',
                      'estimate_id', 'statement_id', 'admission_bundle_id', 'context_field_gains')
    return {'selected_observations': [_observation_trace(observations[i]) for i in identifiers if i in observations],
            'scope_decisions': [row for row in scope if row['project_id'] == project],
            'admission_dispositions': [{key: row[key] for key in candidate_keys if key in row}
                                       for row in (receipt or {}).get('dispositions', ())
                                       if row.get('project_id') == project]}


def _context_field_improvements(old, new):
    """Track located context fields separately from observations and research gains."""
    def located_fields(receipt):
        for row in (receipt or {}).get('dispositions', ()):
            for field, binding in row.get('context_field_gains', {}).items():
                if binding.get('decision') == 'BOUND_SAME_ESTIMATE' and binding.get('evidence'):
                    locator = tuple(row[key] for key in ('source_sha256', 'physical_page', 'table', 'row'))
                    yield (locator, field), row, binding

    prior = {key: binding['value'] for key, _, binding in located_fields(old)}
    found = {}
    for (locator, field), row, binding in located_fields(new):
        if (locator, field) in prior and prior[locator, field] == binding['value']:
            continue
        estimate = row.get('estimate_id') or locator
        identity = locator[0], row.get('project_id'), estimate, field, digest(binding['value'])
        group = found.setdefault(identity, {'source_key': row['source_key'], 'source_sha256': locator[0],
                                           'project_id': row.get('project_id'), 'estimate_id': row.get('estimate_id'),
                                           'field': field, 'value': binding['value'], 'occurrences': []})
        group['occurrences'].append({'physical_page': locator[1], 'table': locator[2], 'row': locator[3],
                                     'admission_status': row['status'], 'evidence': binding['evidence']})
    return list(found.values())


def _numeric_candidate_changes(old, new):
    """Compare verified physical cells independently of admission IDs and research values."""
    conditions = ('category', 'estimate_period', 'cutoff_grade', 'product_role', 'particle_size_um', 'particle_size')

    def by_cell(receipt):
        result = {}
        for row in (receipt or {}).get('dispositions', ()):
            for item in (*row.get('observations', ()), *row.get('material_observations', ())):
                if not (item.get('numeric_and_unit_located') and item.get('evidence_status') == 'VERIFIED'):
                    continue
                raw = item['raw']
                anchor = raw['evidence']
                key = tuple(anchor[field] for field in ('sha256', 'page', 'table', 'row', 'column'))
                if key[0] != row['source_sha256'] or any(type(index) is not int for index in key[1:]):
                    continue
                labels = dict(raw.get('context', {}).get('conditions', ()))
                detail = {'variable': raw['variable'], 'value': raw['original_value'],
                          'unit': raw['original_unit'], 'source_key': row['source_key'],
                          'project_id': raw.get('project_id'), 'scope': raw.get('scope_id'),
                          'effective_date': raw.get('effective_date'), 'material_basis': raw.get('material_basis'),
                          'denominator_basis': raw.get('denominator_basis'), 'chemical_basis': raw.get('chemical_basis'),
                          'reported_context': {field: labels[field] for field in conditions if field in labels},
                          'original_quote': anchor['quote'], 'bbox': anchor['bbox']}
                result.setdefault(key, {})[digest(detail)] = detail
        return result

    before, after = by_cell(old), by_cell(new)
    changes = []
    for cell in sorted(before.keys() | after.keys()):
        previous, current = before.get(cell, {}), after.get(cell, {})
        if previous != current:
            kind = 'newly_verified_cell' if not previous else 'no_longer_verified_cell' if not current else 'changed_mapping'
            changes.append({'kind': kind,
                            **dict(zip(('source_sha256', 'physical_page', 'table', 'row', 'column'), cell, strict=True)),
                            'baseline': [previous[key] for key in sorted(previous)],
                            'updated': [current[key] for key in sorted(current)]})
    return {'unit': 'PHYSICAL_PDF_CELL_NOT_AN_INDEPENDENT_RESEARCH_FACT',
            'counts': dict(Counter(row['kind'] for row in changes)), 'differences': changes}


def _selected_value_reason(before, after):
    """Identify an actual reported-value replacement through selected canonical IDs."""
    old = before['selected_observations']
    new = after['selected_observations']
    old_reported = [row for row in old if row.get('variable') == 'contained_treo_kt']
    prior_ids = {row['obs_id'] for row in old}
    for row in new:
        link = row.get('resource_identity_link', {})
        linked = set(link.get('canonical_observation_ids', {}).values())
        if row.get('variable') == 'contained_treo_kt':
            if not old_reported and linked and linked <= prior_ids:
                return 'SAME_ESTIMATE_REPORTED_CONTAINED_REPLACES_CALCULATED'
            if (len(old_reported) == 1 and row['obs_id'] != old_reported[0]['obs_id']
                    and row['transform_version'] != old_reported[0]['transform_version']
                    and all(row.get(field) == old_reported[0].get(field) for field in
                            ('source_sha', 'locator', 'statement_id', 'scope', 'value', 'unit', 'basis'))):
                return 'SAME_SOURCE_VALUE_REVALIDATED_IN_ANOTHER_ADMISSION_VERSION'
    return None


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


def _panel_delta(before, after, name, changed_inputs, include_uncertainty=False):
    old, old_ranks, old_criteria, old_weights, old_status = _panel(before, name)
    new, new_ranks, new_criteria, new_weights, new_status = _panel(after, name)
    if old_criteria and new_criteria and (old_criteria != new_criteria
                                         or not equivalent_weight_rows(old_weights, new_weights)):
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

    result = {'criteria': sorted(codes), 'weight_rows_identical': old_weights == new_weights,
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
    if include_uncertainty:
        from .resource_rank_uncertainty import compare_panel

        result['rank_uncertainty'] = compare_panel(before, after, name, old, new, old_criteria, new_criteria,
                                                   old_weights, new_weights)
    return result


def _identity(run, cfg):
    return {key: run.summary[key] for key in
            ('run_id', 'cutoff', 'code', 'configuration_sha256', 'snapshot_sha256', 'logical_database_sha256')} | {
        'research_config_sha256': digest(cfg['research']), 'monte_carlo': cfg['research']['monte_carlo'],
        'mcda_execution_protocol': _mcda_protocol(cfg)}


def compare(baseline_run, updated_run, output, *, mode='auto', include_uncertainty=False):
    """Publish an auditable selection snapshot and pre/post scientific differences."""
    baseline_run, updated_run, output = map(lambda path: Path(path).resolve(), (baseline_run, updated_run, output))
    if (baseline_run == updated_run or any(output.is_relative_to(folder) or folder.is_relative_to(output)
                                           for folder in (baseline_run, updated_run))):
        raise ValueError('REFRESH_REQUIRES_SEPARATE_RUN_AND_DIFF_OUTPUTS')
    before, after = _FormalInputs(baseline_run), _FormalInputs(updated_run)
    old_cfg, old_lock, old_admit = _checked_inputs(before)
    cfg, lock, admit = _checked_inputs(after)
    if old_admit is None and admit is None:
        raise ValueError('REFRESH_REQUIRES_ACTUAL_ADMISSION_RUN')
    fixed = ('claims_sha256', 'identity_links.json_sha256', 'study_cases.json_sha256',
             'eligibility_policy_sha256', 'census_filter', 'source_mode')
    old_research, research = ({key: value for key, value in item['research'].items() if key not in MCDA_PROTOCOL_FIELDS}
                              for item in (old_cfg, cfg))
    if (before.summary['cutoff'] != after.summary['cutoff'] or old_research != research
            or any(old_cfg.get(k) != cfg.get(k) for k in fixed)):
        raise ValueError('REFRESH_COMPARISON_REQUIRES_SAME_RESEARCH_CONTRACT')
    contract = _comparison_contract(before, after, old_cfg, cfg, old_lock, lock, old_admit, admit, mode)
    old_observations, observations = _observations(before), _observations(after)
    old_ledger, old_active = _admission_ledger(before, old_admit, old_observations)
    ledger, active_rows = _admission_ledger(after, admit, observations)
    old_selection, old_scope = _selection(before)
    selection, scope = _selection(after)
    for rows, current_ledger in ((old_selection, old_ledger), (selection, ledger)):
        selected_ids = {obs for row in rows for obs in row['observation_ids']}
        current_ledger['inactive_automatic_ids_in_selected_inputs'] = sorted(
            selected_ids.intersection(current_ledger['inactive_automatic_observation_ids']))
    if ledger['inactive_automatic_ids_in_selected_inputs']:
        raise ValueError('REFRESH_INACTIVE_AUTOMATIC_OBSERVATION_SELECTED')
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
    panel_diffs = {name: _panel_delta(before, after, name, direct_projects, include_uncertainty)
                   for name in sorted(panels)}
    panel_diffs = {name: value for name, value in panel_diffs.items() if name == PANEL or 'R1' in value['criteria']
                   or 'S1' in value['criteria']}
    gate_diffs = _compare(before.csv('formal_gate_compatibility.csv'), after.csv('formal_gate_compatibility.csv'),
                         ('canonical_project_id', 'gate'))
    old_cohorts, cohorts = (run.csv('eligibility_cohorts.csv') for run in (before, after))
    eligibility_diffs = _compare(old_cohorts, cohorts, ('canonical_project_id',))
    c1_status_counts = {side: dict(Counter(row.get('formal_c1_status', 'UNREPORTED') for row in rows))
                        for side, rows in (('baseline', old_cohorts), ('updated', cohorts))}
    old_eligibility, eligibility = before.json('eligibility_audit.json'), after.json('eligibility_audit.json')
    new_ids = active_rows.keys() - old_observations.keys()
    no_longer_active = old_active.keys() - active_rows.keys()
    projects_with_new_observations = sorted({active_rows[obs]['entity_id'] for obs in new_ids})
    # Report existing admission decisions only for IDs present in this comparison.
    # A rule-edition replacement does not establish scientific independence.
    revalidation_reported = admit is not None and 'inactive_admissions' in admit
    revalidation_pairs = sorted({(row.get('observation_id'), row.get('current_observation_id'))
                                for row in (admit or {}).get('inactive_admissions', ())
                                if row.get('reason') == 'REVALIDATED_AS_NEW_RULE_EDITION'
                                and row.get('observation_id') in old_observations
                                and row.get('observation_id') in ledger['inactive_automatic_observation_ids']
                                and row.get('current_observation_id') in new_ids})
    revalidated_ids = {current for _, current in revalidation_pairs}
    evidence_accounting = {
        'baseline_run_id': before.summary['run_id'],
        'new_canonical_observations_definition':
            'Active automatic observation IDs absent from the baseline store; a storage count, not independent evidence.',
        'revalidation': {
            'status': 'RECEIPT_REPORTED' if revalidation_reported else 'UNMEASURED',
            'new_observation_count': len(revalidated_ids) if revalidation_reported else None,
            'pairs': [{'baseline_observation_id': prior, 'updated_observation_id': current}
                      for prior, current in revalidation_pairs]},
        'unclassified_new_observation_ids': sorted(new_ids - revalidated_ids),
        'independent_research_evidence_gain': {
            'status': 'UNMEASURED', 'count': None,
            'reason': 'Observation IDs, source SHA changes and rule-edition pairs do not establish scientific independence.'}}
    ledger['previously_enabled_not_current_ids'] = sorted(no_longer_active)
    ledger['previously_enabled_absent_from_updated_store_ids'] = sorted(no_longer_active - observations.keys())
    selection_counters = {'added': 0, 'updated': 0, 'removed': 0, 'provenance_or_disposition_only': 0}
    input_changes = set()
    selected_before = {(row['project_id'], row['criterion']): row for row in old_selection}
    selected_after = {(row['project_id'], row['criterion']): row for row in selection}
    current_source_shas = {source['sha256'] for source in lock}
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
        identity = tuple(entry['identity'])
        prior_evidence = _selection_evidence(identity[0], selected_before.get(identity), old_scope, old_observations, old_admit)
        current_evidence = _selection_evidence(identity[0], selected_after.get(identity), scope, observations, admit)
        entry['evidence'] = {'baseline': prior_evidence, 'updated': current_evidence}
        if reason := _selected_value_reason(prior_evidence, current_evidence):
            entry['reason'] = reason
        elif change == 'removed' and identity[1] == 'R1':
            explains = current_evidence['scope_decisions'] + current_evidence['admission_dispositions']
            entry['reason'] = ('RESOURCE_SCOPE_OR_ADMISSION_DECISION' if explains else
                               'PREVIOUS_SOURCE_EDITION_NOT_SELECTED' if any(
                                   row.get('source_sha') not in current_source_shas
                                   for row in prior_evidence['selected_observations'] if row.get('source_sha')) else
                               'NO_RESOURCE_SELECTION_REASON_RECORDED')
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
    aim_b = {'status': 'NOT_RUN'}
    if include_uncertainty:
        pairing = {name: panel['rank_uncertainty']['draw_pairing'] for name, panel in panel_diffs.items()}
        aim_b = {'status': 'COMPLETE', 'panels_compared': sorted(pairing),
                 'draw_pairing_status_counts': dict(Counter(item['status'] for item in pairing.values())),
                 'paired_project_scenario_method_family_groups': sum(item.get('paired_groups', 0)
                                                                     for item in pairing.values())}
    receipt = {'version': VERSION, 'status': 'COMPLETE', 'runs': identities,
               'comparison': contract, 'admission': {'baseline': old_ledger, 'updated': ledger},
               'admission_receipt_sha256': ledger.get('receipt_sha256'),
               'selection_snapshot_sha256': filehash(output / 'selection_snapshot.json'),
               'admitted_observation_ids': ledger['accepted_observation_ids'],
               'previous_admission_observation_ids': old_ledger['accepted_observation_ids'],
               'new_canonical_observation_ids': sorted(new_ids), 'new_canonical_observations': len(new_ids),
               'projects_with_new_canonical_observations': projects_with_new_observations,
               'new_canonical_projects': projects_with_new_observations,
               'new_canonical_projects_definition':
                   'Compatibility alias of projects_with_new_canonical_observations; does not count newly created Projects.',
               'evidence_change_accounting': evidence_accounting,
               'context_field_improvements': _context_field_improvements(old_admit, admit),
               'numeric_candidate_changes': _numeric_candidate_changes(old_admit, admit),
               'automatic_observation_transitions': {
                   'newly_present': [_observation_trace(active_rows[obs]) for obs in sorted(new_ids)],
                   'no_longer_enabled': [_observation_trace(old_active[obs]) | {
                       'retained_in_updated_store': obs in observations} for obs in sorted(no_longer_active)],
               },
               'active_admission_ids_in_selected_inputs': consumed,
               'sources_changed': contract['source_binding_differences'], 'scope_decisions_changed': scope_delta,
               'selection_differences': selected_delta, 'criterion_selection_counts': selection_counters,
               'criterion_trace_differences': traces,
               'numeric_selection_projects': sorted(input_changes), 'changed_raw_input_projects': sorted(direct_projects),
               'formal_c1': {'required_gates': GATES, 'baseline': old_eligibility, 'updated': eligibility,
                             'project_status_counts': c1_status_counts,
                             'gate_differences': gate_diffs, 'project_eligibility_differences': eligibility_diffs},
               'panels': panel_diffs, 'aim_b_rank_uncertainty': aim_b,
               'input_artifact_sha256': {'baseline': before.read_hashes, 'updated': after.read_hashes}}
    atomic_json(output / 'resource_refresh.json', receipt)
    return receipt
