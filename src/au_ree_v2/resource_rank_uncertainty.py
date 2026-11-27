"""Compare the existing sealed R rank summaries and, when available, draw ranks."""

from array import array
from collections import Counter
import csv
import math

from .analysis import MCDA_TRACE_OUTPUTS, MCDA_TRACE_PANEL, MCDA_TRACE_PROFILE
from .store import digest


VERSION = 'resource-rank-uncertainty-v2'
SUMMARY_FILES = ('weight_uncertainty.csv', 'rounding_uncertainty.csv', 'uncertainty_by_method.csv')
METRICS = ('median', 'q05', 'q95', 'frequency_first', 'frequency_joint_first', 'frequency_top3', 'frequency_top5')
WEIGHTS = 'WEIGHTS_ONLY'
ROUNDING = 'SOURCE_ROUNDING_ONLY_NOT_MEASUREMENT_UNCERTAINTY'
NO_BOUNDS = 'NOT_QUANTIFIED_NO_SOURCE_BOUNDS'
METHODS = ('SAW', 'PROMETHEE_II', 'TOPSIS')
RNG_VERSION = 'entity-keyed-rng-v2'
SAMPLING_VERSION = 'shared-method-draws-v1'
DRAW_IDENTITY = 'version|seed|scenario|family|project_id|criterion_id|draw_index'
TOLERANCE = 1e-12


def _one(run, key):
    rows = run.optional_csv(key)
    if len(rows) > 1 or (key in run.hashes and not rows):
        raise ValueError('RANK_UNCERTAINTY_EXPECTED_ONE_CONTRACT_ROW: ' + key)
    return rows[0] if rows else None


def _project_semantics(matrix):
    indexed = {row['project_id']: (row.get('canonical_project_id') or row['project_id'], row.get('scope'),
                                  row.get('case_id') or '') for row in matrix}
    if len(indexed) != len(matrix):
        raise ValueError('RANK_UNCERTAINTY_DUPLICATE_PROJECT_ID')
    return indexed


def _cohorts(before, after):
    common = sorted(pid for pid in before.keys() & after.keys() if before[pid][1] and before[pid] == after[pid])
    added, removed = sorted(after.keys() - before.keys()), sorted(before.keys() - after.keys())
    changed = sorted((before.keys() & after.keys()) - set(common))
    return {'baseline_full_cohort': sorted(before), 'updated_full_cohort': sorted(after),
            'common_projects_same_semantics': common, 'entered_projects': added, 'exited_projects': removed,
            'shared_ids_with_unconfirmed_semantics': changed,
            'same_semantic_cohort': bool(common) and not (added or removed or changed)}


def _known_contract(row, runtime, panel):
    if row is None or runtime is None:
        return False
    expected = {'contract': SAMPLING_VERSION, 'cohort': panel, 'input_contract': RNG_VERSION,
                'methods': '|'.join(METHODS), 'draw_identity': DRAW_IDENTITY,
                'unknown': 'NO_PROBABILITY_DISTRIBUTION_ASSIGNED'}
    details = row.get('detail')
    required_profile = MCDA_TRACE_PROFILE if panel == MCDA_TRACE_PANEL and details == 'ALL_DRAW_RANKS' else None
    return (all(row.get(key) == value for key, value in expected.items())
            and details in {'ALL_DRAW_RANKS', 'RECONSTRUCT_FROM_KEYED_INPUTS'}
            and row.get('trace_profile') == required_profile
            and row.get('seed') == runtime.get('seed') and row.get('reps') == runtime.get('reps')
            and (row.get('seed') or '').isdigit() and (row.get('reps') or '').isdigit()
            and 1 <= int(row['reps']) <= 100000
            and runtime.get('method_version') == RNG_VERSION and runtime.get('identity') == DRAW_IDENTITY
            and runtime.get('RNG_kind') == "L'Ecuyer-CMRG" and runtime.get('normal_kind') == 'Inversion'
            and runtime.get('sample_kind') == 'Rejection' and runtime.get('R_version')
            and runtime.get('threshold') and runtime.get('concentration'))


def _verified_r_inputs(run, panel, runtime, draw_contract):
    key = f'{panel}/r_cache.json'
    if key not in run.hashes:
        return None
    receipt = run.json(key)
    contract = receipt.get('contract', {})
    inputs = {f'{panel}/{name}': run.hashes.get(f'{panel}/{name}')
              for name in ('matrix.csv', 'criteria.csv', 'weights.csv')}
    if (receipt.get('status') not in {'COMPUTED_WITHOUT_CACHE', 'COMPUTED_AND_CACHED', 'REUSED_VERIFIED'}
            or receipt.get('key') != digest(contract) or contract.get('version') != 'mcda-input-cache-v2'
            or contract.get('panel') != panel or contract.get('stage') not in {None, 'core'}
            or not all(inputs.values()) or any(contract.get('inputs', {}).get(k) != v for k, v in inputs.items())
            or contract.get('sampling') != SAMPLING_VERSION or contract.get('vanilla') is not True):
        return None
    if contract.get('rank_trace') != draw_contract.get('trace_profile'):
        return None
    if contract.get('rank_trace') == MCDA_TRACE_PROFILE:
        sealed = {name: run.hashes.get(f'{panel}/{name}') for name in MCDA_TRACE_OUTPUTS}
        if not all(sealed.values()) or receipt.get('rank_trace_outputs') != sealed:
            return None
    programs = contract.get('programs', {})
    if set(programs) != {'run_mcda.R', 'methods.R'} or not all(programs.values()) or not contract.get('R'):
        return None
    settings = contract.get('monte_carlo', {})
    if (str(settings.get('seed')) != runtime.get('seed') or str(settings.get('reps')) != runtime.get('reps')
            or settings.get('method_version') != runtime.get('method_version')
            or _number(settings.get('dirichlet_concentration'), 'concentration') != _number(runtime.get('concentration'), 'concentration')
            or _number(contract.get('threshold'), 'threshold') != _number(runtime.get('threshold'), 'threshold')):
        return None
    return {key: contract.get(key) for key in ('R', 'programs', 'monte_carlo', 'threshold', 'sampling',
                                               'analysis', 'vanilla', 'weight_calculation')}


def _number(value, name):
    if value is None or value == '':
        return None
    result = float(value)
    if not math.isfinite(result) or (name.startswith('frequency_') and not 0 <= result <= 1):
        raise ValueError('RANK_UNCERTAINTY_INVALID_NUMERIC_VALUE: ' + name)
    return result


def _summary_rows(run, panel, name, projects, scenarios, contract):
    by_method = name == 'uncertainty_by_method.csv'
    rows = {}
    for row in run.optional_csv(f'{panel}/{name}'):
        project, scenario, uncertainty = row['project_id'], row['scenario'], row['uncertainty']
        method = row.get('method') if by_method else 'PROMETHEE_II'
        key = scenario, method, uncertainty, project
        if project not in projects or scenario not in scenarios or method not in METHODS or key in rows:
            raise ValueError('RANK_UNCERTAINTY_SUMMARY_IDENTITY_MISMATCH: ' + name)
        if by_method and contract is not None and (
                row.get('cohort') != panel or row.get('seed') != contract.get('seed')
                or row.get('draws') != contract.get('reps')
                or row.get('draw_contract') != f'{contract.get("input_contract")}/{contract.get("contract")}'):
            raise ValueError('RANK_UNCERTAINTY_SUMMARY_CONTRACT_MISMATCH: ' + name)
        metrics = {column: _number(row[column], column) for column in METRICS if column in row}
        if not {'median', 'q05', 'q95'} <= metrics.keys():
            raise ValueError('RANK_UNCERTAINTY_SUMMARY_METRICS_MISSING: ' + name)
        if uncertainty == NO_BOUNDS and any(value is not None for value in metrics.values()):
            raise ValueError('RANK_UNCERTAINTY_UNKNOWN_BOUNDS_HAVE_VALUES: ' + name)
        rows[key] = metrics
    return rows


def _summary_identity(key):
    return dict(zip(('scenario', 'method', 'uncertainty', 'project_id'), key, strict=True))


def _summary_result(old, new, cohort, comparable):
    common = set(cohort['common_projects_same_semantics'])
    result = {'baseline_full_cohort_rows': len(old), 'updated_full_cohort_rows': len(new),
              'common_project_metrics': [], 'baseline_other_project_metrics': [], 'updated_other_project_metrics': [],
              'unchanged_common_project_rows': 0, 'common_project_rows_without_both_summaries': 0}
    for key in sorted(old.keys() | new.keys()):
        left, right = old.get(key), new.get(key)
        identity = _summary_identity(key)
        if identity['project_id'] not in common:
            if left is not None:
                result['baseline_other_project_metrics'].append({**identity, 'metrics': left})
            if right is not None:
                result['updated_other_project_metrics'].append({**identity, 'metrics': right})
            continue
        if left is None or right is None:
            result['common_project_rows_without_both_summaries'] += 1
        if comparable and left == right:
            result['unchanged_common_project_rows'] += 1
            continue
        item = {**identity, 'baseline': left, 'updated': right}
        if comparable and left is not None and right is not None:
            item['marginal_summary_delta'] = {name: right[name] - left[name] for name in METRICS
                                               if left.get(name) is not None and right.get(name) is not None
                                               and abs(right[name] - left[name]) > TOLERANCE}
        result['common_project_metrics'].append(item)
    return result


class _DrawTraceIssue(ValueError):
    pass


def _draw_ranks(run, key, panel, projects, scenarios, reps):
    expected = {(scenario, method, family, pid) for scenario in scenarios for method in METHODS
                for family in (WEIGHTS, ROUNDING) for pid in projects}
    ranks = {}
    required = {'cohort', 'scenario', 'method', 'uncertainty', 'project_id', 'draw_id', 'rank'}
    with run.path(key).open(encoding='utf-8-sig', newline='') as stream:
        reader = csv.DictReader(stream)
        fields = reader.fieldnames or []
        if not required <= set(fields) or len(fields) != len(set(fields)):
            raise _DrawTraceIssue('RANK_UNCERTAINTY_INVALID_DRAW_COLUMNS')
        for row in reader:
            identity = (row['scenario'], row['method'], row['uncertainty'], row['project_id'])
            try:
                index, rank = int(row['draw_id']) - 1, _number(row['rank'], 'rank')
            except (TypeError, ValueError) as exc:
                raise _DrawTraceIssue('RANK_UNCERTAINTY_INVALID_DRAW_VALUES') from exc
            if (row['cohort'] != panel or identity not in expected or not 0 <= index < reps
                    or rank is None or not 1 <= rank <= len(projects) or (2 * rank) % 1):
                raise _DrawTraceIssue('RANK_UNCERTAINTY_DRAW_IDENTITY_MISMATCH')
            if identity not in ranks:
                ranks[identity] = array('d', [math.nan]) * reps
            if not math.isnan(ranks[identity][index]):
                raise _DrawTraceIssue('RANK_UNCERTAINTY_DUPLICATE_DRAW_KEY')
            ranks[identity][index] = rank
    if ranks.keys() != expected or any(math.isnan(value) for values in ranks.values() for value in values):
        raise _DrawTraceIssue('RANK_UNCERTAINTY_INCOMPLETE_DRAW_GRID')
    return ranks


def _quantile(ordered, p):
    # R's default quantile convention (type 7).
    offset = (len(ordered) - 1) * p
    low, high = math.floor(offset), math.ceil(offset)
    return ordered[low] + (ordered[high] - ordered[low]) * (offset - low)


def _paired_differences(left, right, old_summaries, new_summaries):
    results = []
    omitted = 0
    for identity in sorted(left):
        scenario, method, family, project = identity
        # The R trace may contain ranks at fixed point scores even when its source
        # bounds summary explicitly withholds rounding inference.
        unavailable = (scenario, method, NO_BOUNDS, project)
        if family == ROUNDING and (unavailable in old_summaries or unavailable in new_summaries):
            omitted += 1
            continue
        if any(not any((scenario, method, label, project) in summaries for label in (
                (WEIGHTS, 'WITHIN_GROUP_WEIGHTS_FIXED_DOMAIN_TOTALS') if family == WEIGHTS else (ROUNDING,)))
                for summaries in (old_summaries, new_summaries)):
            raise _DrawTraceIssue('RANK_UNCERTAINTY_DRAW_WITHOUT_MATCHING_SUMMARY')
        diffs = sorted(new - old for old, new in zip(left[identity], right[identity], strict=True))
        distribution = Counter(diffs)
        results.append({**_summary_identity(identity), 'draws': len(diffs),
                        'median_rank_delta': _quantile(diffs, .5), 'q05_rank_delta': _quantile(diffs, .05),
                        'q95_rank_delta': _quantile(diffs, .95),
                        'rank_delta_counts': [{'rank_delta': value, 'draws': count}
                                              for value, count in sorted(distribution.items())]})
    return {'status': 'PAIRED_VERIFIED_DRAW_RANKS', 'rank_delta_direction': 'UPDATED_MINUS_BASELINE',
            'draw_identity': DRAW_IDENTITY, 'paired_groups': len(results),
            'source_rounding_groups_without_reported_bounds': omitted, 'paired_rank_differences': results}


def compare_panel(before, after, panel, before_matrix, after_matrix, before_criteria, after_criteria,
                  before_weights, after_weights):
    """Keep full-cohort summaries separate and pair actual ranks only on a verified draw grid."""
    old_scope, scope = _project_semantics(before_matrix), _project_semantics(after_matrix)
    cohort = _cohorts(old_scope, scope)
    old_scenarios, scenarios = ({row['scenario'] for row in weights} for weights in (before_weights, after_weights))
    runtime_key = f'{panel}/runtime.csv'
    contract_key = f'{panel}/shared_draw_contract.csv'
    trace_key = f'{panel}/shared_draw_ranks.csv'
    old_runtime, runtime = _one(before, runtime_key), _one(after, runtime_key)
    old_contract, contract = _one(before, contract_key), _one(after, contract_key)
    weights_identical = before_weights == after_weights
    trace_descriptors = {'detail', 'trace_profile'}
    settings_match = (bool(before_criteria and before_weights) and before_criteria == after_criteria
                      and weights_identical and old_runtime == runtime
                      and _known_contract(old_contract, old_runtime, panel) and _known_contract(contract, runtime, panel)
                      and ({key: value for key, value in old_contract.items() if key not in trace_descriptors}
                           == {key: value for key, value in contract.items() if key not in trace_descriptors}))
    r_inputs = _verified_r_inputs(before, panel, old_runtime, old_contract) if settings_match else None
    new_r_inputs = _verified_r_inputs(after, panel, runtime, contract) if settings_match else None
    r_match = r_inputs is not None and r_inputs == new_r_inputs
    comparable = bool(settings_match and r_match and cohort['same_semantic_cohort'])
    summaries = {}
    old_method, new_method = None, None
    for name in SUMMARY_FILES:
        old_rows = _summary_rows(before, panel, name, old_scope, old_scenarios, old_contract)
        new_rows = _summary_rows(after, panel, name, scope, scenarios, contract)
        if name == 'uncertainty_by_method.csv':
            old_method, new_method = old_rows, new_rows
        summaries[name] = {'baseline_sha256': before.hashes.get(f'{panel}/{name}'),
                           'updated_sha256': after.hashes.get(f'{panel}/{name}'),
                           **_summary_result(old_rows, new_rows, cohort, comparable)}

    if not settings_match:
        paired = {'status': 'RESEARCH_OR_DRAW_CONTRACT_UNVERIFIED_OR_CHANGED'}
        if not weights_identical:
            paired['reason'] = 'ACTUAL_WEIGHT_ROWS_DIFFER'
    elif not r_match:
        paired = {'status': 'R_PROGRAMS_RUNTIME_OR_INPUT_SEALS_UNVERIFIED_OR_CHANGED'}
        if r_inputs is not None and new_r_inputs is not None and (
                r_inputs['weight_calculation'] != new_r_inputs['weight_calculation']):
            paired['reason'] = 'WEIGHT_CALCULATION_VERSION_DIFFERS'
    elif not cohort['same_semantic_cohort']:
        paired = {'status': 'WITHHELD_COHORT_OR_SCOPE_CHANGED'}
    elif (old_contract['detail'] != 'ALL_DRAW_RANKS' or contract['detail'] != 'ALL_DRAW_RANKS'
            or trace_key not in before.hashes or trace_key not in after.hashes):
        paired = {'status': 'KEYED_CONTRACT_MATCHES_ACTUAL_DRAW_RANKS_NOT_AVAILABLE'}
    elif not old_method or not new_method:
        paired = {'status': 'VERIFYING_SOURCE_BOUNDS_REQUIRES_METHOD_SUMMARIES'}
    else:
        reps = int(contract['reps'])
        side = 'baseline'
        try:
            old_ranks = _draw_ranks(before, trace_key, panel, old_scope, old_scenarios, reps)
            side = 'updated'
            ranks = _draw_ranks(after, trace_key, panel, scope, scenarios, reps)
            side = 'comparison'
            paired = _paired_differences(old_ranks, ranks, old_method, new_method)
        except _DrawTraceIssue as exc:
            paired = {'status': 'ACTUAL_DRAW_RANKS_INVALID', 'reason': str(exc), 'side': side}
        else:
            paired.update(verified_r_program_sha256=r_inputs['programs'],
                          verified_r_runtime_sha256=digest(r_inputs['R']),
                          baseline_trace_sha256=before.hashes[trace_key], updated_trace_sha256=after.hashes[trace_key])

    return {'version': VERSION, 'cohorts': cohort,
            'comparison_basis': ('SAME_COHORT_MARGINAL_SUMMARY_DELTAS' if comparable
                                 else 'SEPARATE_ORIGINAL_COHORT_LEVELS_NO_ISOLATED_VALUE_EFFECT'),
            'draw_contracts': {'baseline': old_contract, 'updated': contract,
                               'matching_settings': bool(settings_match), 'matching_sealed_r_protocol': bool(r_match),
                               'weight_rows_identical': weights_identical,
                               'baseline_contract_sha256': before.hashes.get(contract_key),
                               'updated_contract_sha256': after.hashes.get(contract_key),
                               'baseline_runtime_sha256': before.hashes.get(runtime_key),
                               'updated_runtime_sha256': after.hashes.get(runtime_key)},
            'summaries': summaries, 'draw_pairing': paired,
            'interpretation': {'source_rounding': 'REPORTING_PRECISION_ONLY',
                               'geological_uncertainty': 'NOT_INFERRED_FROM_WEIGHT_OR_ROUNDING_DRAWS',
                               'rank_frequencies': 'PREFERENCE_AND_MODEL_FREQUENCIES_ONLY',
                               'common_project_levels': 'FROM_EACH_FULL_COHORT_WITHOUT_COMMON_COHORT_REFIT'}}
