"""Prioritize existing Census gaps without supplying values or changing admission."""

from collections import Counter, defaultdict
import json
from pathlib import Path
import re

from au_ree_v2.derived_cache import atomic_json
from au_ree_v2.store import digest, filehash
from au_ree_v2.tabular import read_csv, write_csv


BASELINE = Path('results/ree-project-census/coverage-locked-20261125')
VERSION = 'phase10-research-gap-priority-v1'
SHA = re.compile(r'(?<![a-f0-9])[a-f0-9]{64}(?![a-f0-9])')
MAGNET = frozenset(('Nd2O3', 'Pr6O11', 'Dy2O3', 'Tb4O7'))
FIELDS = {
    'R1': ('總TREO蘊藏量_kt', '礦石蘊藏量_Mt', 'TREO品位_pct'),
    'R2': ('TREO品位_pct',),
    'S1': ('磁鐵稀土佔TREO_pct', '磁鐵稀土氧化物蘊藏量_kt', '總TREO蘊藏量_kt'),
    'D1': ('開發階段', '開發階段代碼', '開發階段類別'),
    **{code: ('緯度', '經度') for code in ('I1', 'I2', 'I3', 'I4')},
}
CONVENTIONAL = frozenset(('issuer_resource_composition', 'issuer_resource_financing_milestone',
                          'issuer_resource_infrastructure', 'issuer_resource_study',
                          'resource_infrastructure_pilot', 'six_domain'))
CAUSE_ORDER = ('EXTRACTION_MISSED', 'SOURCE_MISSING', 'SEMANTIC_BINDING_INCOMPLETE',
               'NORMALIZATION_INCOMPATIBLE', 'SCIENTIFIC_BASIS_INCOMPATIBLE', 'NOT_DISCLOSED',
               'UNRESOLVED', 'NOT_APPLICABLE')
ELIGIBLE_LINEAGE = frozenset(('SCORE_MATCHED_TRACE', 'SAME_CASE_AND_SOURCE', 'TECHNICAL_CASE_SOURCE',
                              'DISCLOSURE_ITEMS', 'DISCLOSURE_BASELINE_SOURCE'))
CSV_FIELDS = ('priority', 'project_id', 'project_name', 'criterion', 'dimension', 'primary_cause',
              'causes', 'existing_valid_criterion', 'existing_valid_panel_inputs',
              'existing_comparable_observations', 'needed_evidence_slots', 'needed_evidence',
              'alternative_existing_rule_route_missing_fields',
              'conditional_additional_comparable_inputs', 'available_locked_sources', 'missing_locked_sources',
              'conditional_one_field_matrix_rows', 'conditional_multi_field_or_criterion_matrix_rows',
              'conditional_one_criterion_matrix_rows', 'conditional_multi_criterion_matrix_rows',
              'baseline_panel_samples', 'affected_panels', 'conditional_matrix_completion_panels', 'feasibility')


def _index(rows, keys):
    index = {tuple(row[k] for k in keys): row for row in rows}
    if len(index) != len(rows):
        raise ValueError(f'Duplicate historical key: {keys}')
    return index


def _baseline(root):
    folder = root / BASELINE
    release_path = folder / 'census_release.json'
    release = json.loads(release_path.read_bytes())
    declared = dict(release['evidence_outputs'])
    declared.update({'REE project census.csv': release['census_csv_sha256']})
    evidence = {}
    for name in ('REE project census.csv', 'field_status.csv', 'gap_review.csv', 'field_provenance.csv',
                 'census_selection.csv', 'mcda_panel_decisions.csv', 'mcda_criterion_lineage.csv',
                 'resource_statement_observations.csv', 'resource_statement_lineage.csv'):
        path = folder / name
        sha = filehash(path)
        if name in declared and sha != declared[name]:
            raise ValueError(f'Historical evidence digest mismatch: {name}')
        evidence[name] = sha
    evidence['census_release.json'] = filehash(release_path)
    panels = release['ranking_panels']
    for panel, contract in sorted(panels.items()):
        name = f'MCDA/{panel}/ranking.csv'
        evidence[name] = filehash(folder / name)
        if evidence[name] != contract['digests']['ranking.csv']:
            raise ValueError(f'Historical ranking digest mismatch: {panel}')
    if len(panels) != 16:
        raise ValueError('Expected the pinned sixteen historical research panels')
    return folder, release, evidence


def _recovery(folder, manifest):
    expected = {row['sha256'] for row in json.loads((folder / 'asset_manifest.json').read_bytes())}
    if manifest is None:
        return expected, None, {}
    if isinstance(manifest, (Path, str)):
        manifest = json.loads(Path(manifest).read_bytes())
    assets = {row['expected_sha256']: row for row in manifest['assets']}
    missing = manifest['missing_assets']
    if len(assets) != len(manifest['assets']) or assets.keys() != expected or not isinstance(missing, dict):
        raise ValueError('Recovery inventory differs from the pinned Census manifest')
    verified = {sha for sha, row in assets.items() if row['status'] == 'AVAILABLE_EXACT_ORIGINAL'
                and row['observed_sha256'] == sha}
    if missing.keys() != expected - verified or any(assets[key]['status'] != 'SOURCE_UNAVAILABLE' for key in missing):
        raise ValueError('Recovery availability and impact rows disagree')
    return expected, set(missing), missing


def _facts(folder):
    fields = _index(read_csv(folder / 'field_status.csv'), ('project_id', 'column'))
    gaps = _index(read_csv(folder / 'gap_review.csv'), ('project_id', 'column'))
    census = _index(read_csv(folder / 'REE project census.csv'), ('專案ID',))
    projects = {key[0]: value for key, value in census.items()}
    if len(projects) != 93 or any(len(row) != 51 for row in projects.values()) or len(fields) != 4743:
        raise ValueError('Expected the pinned 93 by 51 Census field grid')
    if fields.keys() != {(pid, column) for pid, row in projects.items() for column in row}:
        raise ValueError('Census values and field decisions name different cells')
    for (pid, col), row in fields.items():
        if bool(projects[pid][col]) != (row['status'] == 'VALUE_PRESENT'):
            raise ValueError(f'Census value and field status disagree: {(pid, col)}')
    return projects, fields, gaps


def _by_missing_reference(impacts, reference, fields):
    index = defaultdict(set)
    for sha, record in sorted(impacts.items()):
        for item in record.get(reference, ()):
            if isinstance(item, dict) and all(item.get(k) for k in fields):
                index[tuple(item[k] for k in fields)].add(sha)
    return index


def _scope_indexes(folder):
    observations = defaultdict(list)
    for row in read_csv(folder / 'resource_statement_observations.csv'):
        observations[row['project_id']].append(row)
    lineage = _index(read_csv(folder / 'resource_statement_lineage.csv'), ('project_id', 'column'))
    return observations, lineage


def _material_candidates(rows, column):
    oxide = column.partition('_')[0]
    if not re.fullmatch(r'[A-Z][a-z]?[0-9]*O[0-9]+', oxide):
        return [], []
    target = [r for r in rows if r['basis'] == oxide and r.get('physical_page') and r.get('locator')]
    external = [r for r in target if r['selected_for_census'] != '1']
    selected = [r for r in target if r['selected_for_census'] == '1']
    keys = ('observation_id', 'source_sha256', 'statement_group_id', 'statement_id', 'material_basis',
            'basis', 'denominator_basis', 'scope', 'physical_page', 'locator')
    return ([{k: r[k] for k in keys} for r in selected], [{k: r[k] for k in keys} for r in external])


def _cause(field, gap, missing, same, other):
    status, cls, reason = field['status'], gap.get('class'), gap.get('reason')
    if status.startswith('NOT_APPLICABLE_'):
        return 'NOT_APPLICABLE', status
    if missing:
        return 'SOURCE_MISSING', 'LOCKED_CELL_EVIDENCE_OR_REVIEW_COPY_UNAVAILABLE'
    for finding in json.loads(field.get('findings') or '[]'):
        if (finding.get('kind') == 'EXTRACTION_REVIEW' and finding.get('reason') == 'VERIFIED_SOURCE_FIELD_MISSED'
                and finding.get('source_sha256') and finding.get('locator')):
            return 'EXTRACTION_MISSED', finding['reason']
    if reason in {'INCOMPATIBLE_UNIT', 'UNSUPPORTED_EXPLICIT_CHEMICAL_FORM'}:
        return 'NORMALIZATION_INCOMPATIBLE', reason
    if reason == 'UNVERIFIED_CHEMICAL_FORM':
        return 'SEMANTIC_BINDING_INCOMPLETE', reason
    if cls == 'D1' or reason in {'NOT_SAME_MODEL_PRODUCT_BASIS', 'MIXED_OXIDE_COMPONENT_BASIS_NOT_EXPLICIT',
                                'OTHER_COMMODITY_OR_SCOPE', 'OTHER_OPERATOR_OR_SUBSCOPE'}:
        return 'SCIENTIFIC_BASIS_INCOMPATIBLE', reason
    if reason == 'GROUP_TOTAL_DOES_NOT_IDENTIFY_COMPONENT' and gap.get('review_pages') and gap.get('source_review'):
        return 'NOT_DISCLOSED', 'INDIVIDUAL_COMPONENT_NOT_DISCLOSED_IN_REVIEWED_GROUP_TOTAL'
    if same or other or cls in {'E3', 'E4', 'R'} or reason == 'NATIVE_ANNUAL_PERIOD_VALIDATION_REQUIRED':
        return 'SEMANTIC_BINDING_INCOMPLETE', reason or status
    return 'UNRESOLVED', reason or status


def _gap_review(fields, gaps, observations, lineage, missing, direct):
    reviewed = {}
    for (pid, column), field in sorted(fields.items()):
        if field['status'] == 'VALUE_PRESENT':
            continue
        gap = gaps.get((pid, column), {})
        hashes = set(SHA.findall('|'.join(gap.get(k, '') for k in ('checked_source_shas', 'unavailable_review_shas'))))
        hashes.update(SHA.findall(field['source_sha256']))
        hashes.update(direct.get((pid, column), ()))
        blocked = hashes & missing if missing is not None else set()
        same, other = _material_candidates(observations[pid], column)
        cause, reason = _cause(field, gap, blocked, same, other)
        underlying, interpretation = _cause(field, gap, set(), same, other)
        row = {'project_id': pid, 'field': column, 'cause': cause, 'reason': reason, 'historical_status': field['status'],
               'causes': [{"cause": cause, "reason": reason}]}
        if underlying != cause:
            row['causes'].append({'cause': underlying, 'reason': interpretation})
        if hashes:
            row.update(review_or_support_sha256=sorted(hashes), currently_missing_sha256=sorted(blocked))
        if not field['status'].startswith('NOT_APPLICABLE_'):
            row.update(historical_class=gap.get('class'), review_pages=gap.get('review_pages'),
                       historical_gap_reason=gap.get('reason'),
                       locator=gap.get('review_locator') or field.get('locator'), reopen_if=gap.get('reopen_if'),
                       machine_finding=json.loads(field['findings'] or '[]'))
        if gap.get('class') in {'P1', 'P2'}:
            if gap['class'] == 'P2':
                path = 'DERIVED_FIELD_REQUIRES_MATCHED_COMPONENTS'
            elif same:
                path = 'CANDIDATE_IN_SELECTED_ESTIMATE_REQUIRES_EXISTING_LINEAGE_RULE'
            elif other:
                path = 'RAW_COMPONENT_IN_OTHER_ESTIMATE_NOT_SUBSTITUTABLE'
            elif gap['reason'] == 'GROUP_TOTAL_DOES_NOT_IDENTIFY_COMPONENT':
                path = 'GROUP_TOTAL_CANNOT_IDENTIFY_INDIVIDUAL_COMPONENT'
            else:
                path = 'RAW_COMPONENT_NOT_LOCATED_IN_BOUNDED_REVIEW'
            row.update(p1_p2_path=path, same_estimate_raw_candidates=same, other_estimate_raw_candidates=other,
                       required_components=gap.get('required_components', '').split('|') if gap.get('required_components') else [],
                       missing_components=gap.get('still_missing_components', '').split('|') if gap.get('still_missing_components') else [],
                       existing_value_lineage=lineage.get((pid, column)), automatic_fill=False)
        reviewed[pid, column] = row
    return reviewed


def _needed(code, related, oxide_fields):
    gaps = [r for r in related if r['cause'] != 'NOT_APPLICABLE']
    columns = {r['field'] for r in gaps}
    if code == 'S1':
        # A direct accession of a valid same-MRE share and a qualified four-oxide
        # derivation are alternatives. Never add both paths as requirements.
        components = sorted(oxide_fields[name] for name in MAGNET if oxide_fields.get(name) in columns)
        if '總TREO蘊藏量_kt' in columns:
            components += ['總TREO蘊藏量_kt']
        return ['SAME_MRE_EXPLICIT_FOUR_OXIDE_TREO_SHARE'], components
    if code == 'R1':
        return ['COMPLETE_SAME_MRE_TREO_INVENTORY'], sorted(columns)
    if code in {'I1', 'I2', 'I3', 'I4'}:
        return sorted(columns) + ([f'VERIFIED_{code}_INFRASTRUCTURE_DISTANCE'] if not columns else []), []
    if code == 'D1':
        return ['DATED_COMPLETED_SCOPE_COMPATIBLE_STUDY'], sorted(columns)
    return [f'VALIDATED_{code}_RESEARCH_INPUT'], sorted(columns)


def _criteria_inputs(folder, panels, project_map):
    decisions = _index(read_csv(folder / 'mcda_panel_decisions.csv'), ('canonical_project_id', 'panel'))
    expected = {(pid, panel) for pid in project_map for panel in panels}
    if decisions.keys() != expected:
        raise ValueError('Historical panel decisions must cover the fixed Project by panel grid')
    lines = defaultdict(list)
    matrix_keys = set()
    for row in read_csv(folder / 'mcda_criterion_lineage.csv'):
        pid, panel = row['canonical_project_id'], row['panel']
        codes = {r['code'] for r in panels[panel]['criteria']}
        if row['criterion'] not in codes or decisions[pid, panel]['status'] != 'IN_PANEL_MATRIX':
            raise ValueError('Criterion lineage is outside the sealed historical panel matrix')
        location = (pid, panel, row['criterion'])
        if location in matrix_keys:
            raise ValueError('Duplicate criterion lineage in the historical matrix')
        matrix_keys.add(location)
        if row['evidence_status'] in ELIGIBLE_LINEAGE and json.loads(row['evidence'] or '[]'):
            lines[pid, row['criterion']].append(row)
    for panel, spec in panels.items():
        seen = {pid for pid in project_map if decisions[pid, panel]['status'] == 'IN_PANEL_MATRIX'}
        if len(seen) != spec['matrix_projects']:
            raise ValueError(f'Matrix count differs from archived decisions: {panel}')
        if not {(pid, panel, c['code']) for pid in seen for c in spec['criteria']} <= matrix_keys:
            raise ValueError(f'Criterion lineage does not cover the complete archived matrix: {panel}')
    return decisions, lines


def _potential(pid, code, panels, decisions, lines):
    definitions = {panel: {row['code']: row for row in spec['criteria']} for panel, spec in panels.items()}
    result = []
    for name in sorted(panels.keys() & CONVENTIONAL):
        if decisions[pid, name]['status'] != 'NO_ELIGIBLE_INPUT_IN_PANEL_MATRIX':
            continue
        spec = panels[name]
        codes = definitions[name].keys()
        if code not in codes:
            continue
        # The ordinary issuer panels take the same selected resource and scorable
        # inputs from analysis.prepare. Do not transfer case or disclosure rows.
        def scopes(criterion):
            return {r['scope'] for r in lines[pid, criterion] if r['panel'] in CONVENTIONAL and r['scope']
                    and definitions[r['panel']].get(criterion) == definitions[name].get(criterion)}
        resources = scopes('R1')
        if len(resources) != 1:
            continue
        supported = {c for c in codes if scopes(c) == resources}
        unmet = sorted(codes - supported)
        if code not in unmet:
            continue
        result.append({'panel': name, 'current_samples': spec['matrix_projects'], 'unmet_criteria': unmet,
                       'required_existing_scope': next(iter(resources)), 'hypothetical_row_upper_bound': 1,
                       'basis': 'SAME_SCOPE_ISSUER_CRITERIA_STRUCTURAL_BOUND_ONLY'})
    return result


def _priorities(folder, projects, release, reviewed, expected, missing, impacts):
    panels = release['ranking_panels']
    membership = _index(read_csv(folder / 'census_selection.csv'), ('project_id',))
    member_to_canonical = {k[0]: r['canonical_project_id'] for k, r in membership.items() if r['status'] == 'SELECTED'}
    if set(member_to_canonical) != set(projects) or len(set(member_to_canonical.values())) != len(projects):
        raise ValueError('Expected one distinct selected canonical Project per Census row')
    pid_by_canonical = {v: k for k, v in member_to_canonical.items()}
    decisions, lines = _criteria_inputs(folder, panels, pid_by_canonical)
    direct = _by_missing_reference(impacts, 'analysis_inputs', ('project_id', 'criterion'))
    known = defaultdict(set)
    for row in read_csv(folder / 'field_provenance.csv'):
        if row['value']:
            known[row['project_id']].update(SHA.findall(row['source_sha256']))
    definitions = defaultdict(set)
    for spec in panels.values():
        for row in spec['criteria']:
            definitions[row['code']].add(row['domain'])
    result = []
    for pid, canonical in sorted(member_to_canonical.items()):
        oxide_fields = {col.partition('_')[0]: col for col in projects[pid] if col.partition('_')[0] in MAGNET}
        for code, dimensions in sorted(definitions.items()):
            columns = set(FIELDS.get(code, ()))
            if code == 'S1':
                columns.update(oxide_fields.values())
            relevant = [reviewed[pid, col] for col in sorted(columns) if (pid, col) in reviewed]
            supported = lines[canonical, code]
            blocked = direct[pid, code] | direct[canonical, code]
            blocked |= {sha for row in relevant for sha in row.get('currently_missing_sha256', ())}
            sources = known[pid] | set(SHA.findall('|'.join(r['evidence'] for r in supported))) | blocked
            sources |= {sha for row in relevant for sha in row.get('review_or_support_sha256', ())}
            affected = sorted(p for p, spec in panels.items() if code in {c['code'] for c in spec['criteria']})
            causes = {state['cause'] for r in relevant for state in r['causes']}
            if blocked:
                causes.add('SOURCE_MISSING')
            active_causes = sorted(causes - {'NOT_APPLICABLE'}, key=CAUSE_ORDER.index)
            if not active_causes:
                active_causes = ['NOT_APPLICABLE'] if causes and not supported else (['UNRESOLVED'] if not supported else [])
            if supported and not blocked:
                active_causes = []  # An unrelated blank does not block an observed criterion.
            observations = {obs for row in supported for obs in _observation_ids(json.loads(row['evidence']))}
            needed, alternative = _needed(code, relevant, oxide_fields)
            if active_causes == ['NOT_APPLICABLE']:
                needed, alternative = [], []
            options = _potential(canonical, code, panels, decisions, lines) if needed else []
            if supported and not options:
                needed, alternative = (['RESTORE_LOCKED_EXISTING_INPUT_EVIDENCE'] if blocked else []), []
            if options and not active_causes:
                active_causes = ['UNRESOLVED']  # Support in another scope/panel does not transfer.
            rows = [r for r in options if len(r['unmet_criteria']) == 1]
            one_field = rows if len(needed) == 1 else []
            potential = int(bool(needed and (options or (not supported and any(r.get('same_estimate_raw_candidates') for r in relevant)))))
            status = active_causes[0] if active_causes else 'ALREADY_ESTABLISHED'
            result.append(dict(project_id=pid, project_name=projects[pid]['專案名稱'], criterion=code,
                dimension='|'.join(sorted(dimensions)), primary_cause=status, causes=active_causes,
                existing_valid_criterion=int(bool(supported)), existing_valid_panel_inputs=len(supported),
                existing_comparable_observations=len(observations), existing_observation_ids=sorted(observations),
                existing_input_panels=sorted({r['panel'] for r in supported}), needed_evidence_slots=len(needed),
                needed_evidence=needed, alternative_existing_rule_route_missing_fields=alternative,
                conditional_additional_comparable_inputs=potential,
                available_locked_sources=(len((sources & expected) - missing) if missing is not None else None),
                missing_locked_sources=len(blocked), missing_sha256=sorted(blocked),
                conditional_one_field_matrix_rows=len(one_field),
                conditional_multi_field_or_criterion_matrix_rows=len(options) - len(one_field),
                conditional_one_criterion_matrix_rows=len(rows), conditional_multi_criterion_matrix_rows=len(options) - len(rows),
                baseline_panel_samples={p: panels[p]['matrix_projects'] for p in affected}, affected_panels=affected,
                conditional_matrix_completion_panels=options, field_evidence_keys=[r['field'] for r in relevant],
                feasibility=('VERIFIABLE_SCOPE_CONDITIONAL' if rows else 'MULTI_CRITERION_CONDITIONAL' if options else
                             'NOT_APPLICABLE' if status == 'NOT_APPLICABLE' else 'VERIFIED_CURRENT_INPUT' if not needed else
                             'LOCKED_INPUT_RESTORE' if blocked else 'INSUFFICIENT_PANEL_ADMISSIBILITY_PROOF')))
    result.sort(key=lambda r: (not bool(r['needed_evidence']), -r['conditional_one_criterion_matrix_rows'],
                              -r['conditional_additional_comparable_inputs'], r['needed_evidence_slots'],
                              -r['existing_comparable_observations'], -(r['available_locked_sources'] or 0),
                              CAUSE_ORDER.index(r['primary_cause']) if r['primary_cause'] in CAUSE_ORDER else len(CAUSE_ORDER),
                              r['project_id'], r['criterion']))
    for i, row in enumerate(result, 1):
        row['priority'] = i
    return result


def _observation_ids(value, key=''):
    if isinstance(value, dict):
        return {identifier for k, v in value.items() for identifier in _observation_ids(v, k)}
    if isinstance(value, list):
        return {identifier for item in value for identifier in _observation_ids(item, key)}
    return set(SHA.findall(value)) if isinstance(value, str) and key in {
        'obs_ids', 'observation_ids', 'evidence_ids', 'obs_id', 'observation_id', 'evidence_id'} else set()


def _panel_yield(priorities, panels):
    one, multi = defaultdict(set), defaultdict(set)
    for row in priorities:
        for target in row['conditional_matrix_completion_panels']:
            selected = one if len(target['unmet_criteria']) == row['needed_evidence_slots'] == 1 else multi
            selected[target['panel']].add(row['project_id'])
    return {
        name: {'observed_matrix_projects': panel['matrix_projects'], 'observed_ranked_projects': panel['ranked_projects'],
               'one_validated_field_conditional_projects': sorted(one[name]),
               'multiple_fields_or_criteria_conditional_projects': sorted(multi[name] - one[name]),
               'conditional_unique_project_upper_bound': len(one[name] | multi[name]),
               'assessment': 'SAME_SCOPE_STRUCTURAL_ONLY' if name in CONVENTIONAL else 'SPECIALIZED_ADMISSION_NOT_INFERRED',
               'actual_new_samples': 0}
        for name, panel in sorted(panels.items())
    }


def run(root, output, recovery_manifest=None):
    """Write the reproducible gap queue and underlying evidence without changing scientific data."""
    root, output = Path(root), Path(output)
    folder, release, evidence = _baseline(root)
    if output.resolve() == folder.resolve() or output.resolve().is_relative_to(folder.resolve()):
        raise ValueError('Priority receipts must remain separate from the historical release')
    expected, missing, impacts = _recovery(folder, recovery_manifest)
    evidence['asset_manifest.json'] = filehash(folder / 'asset_manifest.json')
    if recovery_manifest is not None:
        evidence['source_recovery_manifest.json'] = (filehash(recovery_manifest) if isinstance(recovery_manifest, (str, Path))
                                                     else digest(recovery_manifest))
    projects, fields, gaps = _facts(folder)
    observations, lineage = _scope_indexes(folder)
    direct = _by_missing_reference(impacts, 'census_fields', ('project_id', 'column'))
    reviewed = _gap_review(fields, gaps, observations, lineage, missing, direct)
    priorities = _priorities(folder, projects, release, reviewed, expected, missing, impacts)
    output.mkdir(parents=True, exist_ok=True)
    csv_rows = [{k: json.dumps(r[k], ensure_ascii=False, sort_keys=True, separators=(',', ':'))
                 if isinstance(r[k], (dict, list)) else r[k] for k in CSV_FIELDS} for r in priorities]
    write_csv(output / 'research_gap_priority.csv', csv_rows, CSV_FIELDS)
    receipt = {'version': VERSION, 'status': 'COMPLETE', 'historical_cutoff': release['cutoff'],
               'priority_unit': 'SELECTED_CANONICAL_PROJECT_AND_EXISTING_CRITERION',
               'field_rows': len(fields), 'historical_project_count': len(projects), 'historical_panel_count': len(release['ranking_panels']),
               'historical_panel_samples': {k: p['matrix_projects'] for k, p in sorted(release['ranking_panels'].items())},
               'conditional_panel_yield': _panel_yield(priorities, release['ranking_panels']),
               'historical_field_causes': dict(Counter(r['cause'] for r in reviewed.values())),
               'gap_cause_types': list(CAUSE_ORDER),
               'p1_p2_path_counts': dict(Counter(r['p1_p2_path'] for r in reviewed.values() if 'p1_p2_path' in r)),
               'priority_row_count': len(priorities), 'automatic_new_values': 0, 'formal_c1_cohort': 'DISABLED',
               'locked_sources_missing': len(missing) if missing is not None else None,
               'locked_sources_available_sha_verified': len(expected - missing) if missing is not None else None,
               'ranking_order': ['needed_evidence_present', 'one_criterion_matrix_opportunities_desc',
                   'conditional_additional_comparable_inputs_desc', 'needed_evidence_slots_asc',
                   'existing_comparable_observations_desc', 'available_locked_sources_desc', 'cause_index', 'project_id', 'criterion'],
               'limits': ['Source recovery supports replay only and does not establish disclosures or panel membership.',
                          'A one-criterion opportunity is conditional on validating that input for the indicated scope.',
                          'A multi-criterion opportunity needs every listed admissible input. Bounds are not additive across gaps.',
                          'An existing Census formula route must pass the ordinary research admission checks before it can supply a criterion.',
                          'Absence under a bounded search remains unresolved; only specific reviewed group totals support a scoped nondisclosure.',
                          'Official WA, disclosure and engineering-case samples are recorded without extrapolating admission rules.'],
               'input_sha256': evidence, 'priority_csv_sha256': filehash(output / 'research_gap_priority.csv'),
               'project_criterion_blockers': priorities, 'field_blockers': list(reviewed.values())}
    atomic_json(output / 'project_criterion_blockers.json', receipt)
    return {k: v for k, v in receipt.items() if k not in {'project_criterion_blockers', 'field_blockers'}}
