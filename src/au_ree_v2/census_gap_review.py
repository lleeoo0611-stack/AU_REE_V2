"""Disposition of the frozen Census gap cohort against the current SQLite projection."""
import json
from collections import Counter

from .store import filehash
from .tabular import read_csv, write_csv


FIELDS = (
    'priority', 'project_id', 'project_name', 'column', 'class', 'baseline_status',
    'current_status', 'action', 'current_value', 'current_locator', 'current_value_sha256',
    'reason', 'required_components', 'still_missing_components', 'checked_source_shas',
    'unavailable_review_shas', 'review_source_url', 'review_pages', 'review_locator',
    'source_review', 'new_review', 'reopen_if',
)

RESOURCE_CLASSES = {
    'NO_MATCHING_COMPONENT_LOCATED_IN_FROZEN_SOURCES': 'P1',
    'GROUP_TOTAL_DOES_NOT_IDENTIFY_COMPONENT': 'P1',
    'DERIVATION_REQUIRES_MISSING_MATCHED_COMPONENTS': 'P2',
    'REJECTED_MATERIAL_OR_RESOURCE_SCOPE': 'D1',
    'INCOMPATIBLE_OXIDE_SUITE_DENOMINATOR': 'D1',
    'UNVERIFIED_CHEMICAL_FORM': 'D1',
    'HEAVY_MINERAL_DENOMINATOR_CANNOT_SUPPORT_BULK': 'D1',
}


def gap_class(status, reason, column):
    if reason in RESOURCE_CLASSES:
        return RESOURCE_CLASSES[reason]
    if status == 'COMPATIBLE_FORECAST_INPUT_NOT_VERIFIED':
        return 'D2' if reason == 'FROZEN_PRE_STUDY_SOURCE_NO_MATCHED_ANNUAL_MODEL' else 'E1'
    if status == 'REPRESENTATIVE_POINT_NOT_VERIFIED':
        return 'E2' if reason == 'NO_VERSIONED_REPRESENTATIVE_FEATURE' else 'E3'
    if status == 'CLASSIFICATION_INPUT_NOT_VERIFIED' or column == '礦床型態':
        return 'E4'
    if column in ('ASX代碼', '未上市公司'):
        return 'E5'
    if column == '產品/產出':
        return 'E6'
    raise ValueError(f'Unclassified baseline gap: {column} {status} {reason}')


def frozen_index(root, spec):
    path = root / spec['path']
    if filehash(path) != spec['sha256']:
        raise ValueError(f'Frozen Census review input changed: {path.name}')
    rows = read_csv(path)
    index = {(r['project_id'], r['column']): r for r in rows}
    if len(index) != len(rows):
        raise ValueError(f'Duplicate Census review key in {path.name}')
    return index


def source_refs(record):
    checks = json.loads(record.get('additional_source_checks') or '[]')
    refs = {item['sha256'] for item in checks if item.get('sha256')}
    if record.get('source_sha256'):
        refs.add(record['source_sha256'])
    return refs


def resource_context(findings):
    return [f.get('statement') for f in findings if f['kind'] == 'RESOURCE_REVIEW']


def action_for(group, before, status, context_changed, missing, required, remaining):
    if status == 'VALUE_PRESENT':
        return 'FILLED'
    if status.startswith('NOT_APPLICABLE_'):
        return 'RECLASSIFIED_NOT_APPLICABLE'
    if status != before or context_changed:
        return 'REVIEW_CHANGED_INPUT'
    if group == 'P2' and required and not remaining:
        return 'REVIEW_DERIVATION'
    if group in ('P1', 'P2', 'D2') and missing:
        return 'RECHECK_SOURCE_VERSION'
    return {'P1':'WAIT_MATCHING_DISCLOSURE', 'P2':'WAIT_COMPONENTS',
            'D2':'WAIT_ENGINEERING_STUDY', 'D1':'VERIFY_BASIS'}.get(group, 'REVIEW_CASE')


def write_gap_review(root, out, rows, trace, diagnoses, sources, associations, cutoff, policy_sha):
    """Project a bounded historical work list. Never supplies a Census value or an N/A."""
    policy_path = root / 'config/census_gap_review.json'
    if filehash(policy_path) != policy_sha:
        raise ValueError('Census gap review policy differs from the run configuration')
    policy = json.loads(policy_path.read_bytes())
    if cutoff != policy['cutoff']:
        return {}
    baseline = frozen_index(root, policy['baseline'])
    earlier = frozen_index(root, policy['dispositions'])
    current = {r['專案ID']: r for r in rows}
    # A different population (e.g. a historical pilot) cannot use this denominator.
    if baseline.keys() != trace.keys():
        return {'gap_review': {'status':'DIFFERENT_CELL_POPULATION', 'policy':policy['version']}}
    extra = {(n['project_id'], c): n for n in policy['case_reviews'] for c in n['columns']}
    priorities = {pid:i for i,pid in enumerate(policy['priority_projects'], 1)}
    report = []
    applicable = set()
    for key, old in baseline.items():
        pid, column = key
        before = old['status']
        if before.startswith('NOT_APPLICABLE_'):
            continue
        applicable.add(key)
        if before == 'VALUE_PRESENT':
            continue
        record = earlier.get(key, {})
        reason = record.get('review_reason', '')
        reopening = record.get('reopen_if', '')
        if not record:
            if pid not in policy['withdrawn_projects'] or column not in policy['withdrawn_columns']:
                raise ValueError(f'Missing historical Census disposition: {key}')
            group = 'R'
            reason = 'PREVIOUS_VALUE_WITHDRAWN'
            reopening = ('Dated evidence of the project product at its release point.' if column == '產品/產出'
                         else 'Dated completed milestone for this project, with operator status recorded separately.')
        else:
            group = gap_class(before, reason, column)
        value = trace[key]
        status, _, findings = diagnoses[key] if value['value'] == '' else ('VALUE_PRESENT', '', [])
        old_context = resource_context(json.loads(old['findings']))
        changed = bool(old_context and old_context != resource_context(findings))
        refs = source_refs(record)
        note = extra.get(key, {})
        if note:
            refs.add(note['source_sha256'])
        # Report actual selected, version-checked originals of this case separately
        # from expected-but-unavailable historical sources.
        verified = refs.intersection(sources)
        if not refs:
            verified = set(associations.get(pid, ())).intersection(sources)
        required = record.get('required_components', '').split('|') if record.get('required_components') else []
        oxide_values = {name.partition('_')[0]: v for name,v in current[pid].items() if name.endswith('_kt')}
        remaining = [oxide for oxide in required if not oxide_values.get(oxide)]
        action = action_for(group, before, status, changed, refs.difference(sources), required, remaining)
        review_note = ''
        if note and note['source_sha256'] in sources:
            review_note = note['locator'] + ' ' + note['finding']
        report.append(dict(priority=priorities.get(pid, ''), project_id=pid,
            project_name=current[pid]['專案名稱'], column=column, baseline_status=before,
            current_status=status, action=action, current_value=value['value'],
            current_locator=value['locator'], current_value_sha256=value['source_sha256'],
            reason=reason, required_components='|'.join(required), still_missing_components='|'.join(remaining),
            checked_source_shas='|'.join(sorted(verified)), unavailable_review_shas='|'.join(sorted(refs.difference(sources))),
            review_source_url=record.get('source_url', ''), review_pages=record.get('physical_pages', ''),
            review_locator=record.get('locator', ''),
            source_review=record.get('source_review', ''), new_review=review_note,
            reopen_if=reopening, **{'class':group}))
    report.sort(key=lambda r:(r['priority'] or 999, r['project_id'], r['column']))
    write_csv(out / 'gap_review.csv', report, FIELDS)
    active = [r for r in report if r['class'] not in ('P1', 'P2', 'D2')]
    filled = sum(trace[key]['value'] != '' for key in applicable)
    return {'gap_review': dict(policy=policy['version'], baseline_applicable=len(applicable),
        filled_within_baseline=filled, fixed_denominator_coverage=filled / len(applicable),
        baseline_gaps=len(report), baseline_active_targets=len(active),
        classes=dict(Counter(r['class'] for r in report)), actions=dict(Counter(r['action'] for r in report)),
        active_target_outcomes=dict(Counter(r['action'] for r in active)))}
