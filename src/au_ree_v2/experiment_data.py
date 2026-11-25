"""Read-only contracts for point-in-time experiments, not source re-verification.

Inputs must be exported from upstream, source-verified evidence. A valid hash and
locator here identify that evidence; this module never opens or validates a PDF.
Missing values and unknown outcomes remain missing. Formal selection is untouched.
"""
import copy
import json
import math
import re
from collections import Counter
from datetime import date, timedelta
from pathlib import Path


SCHEMA_VERSION = 'experiment-dataset-v1'
DATE_PATTERN = re.compile(r'\d{4}-\d{2}-\d{2}\Z')
SHA_PATTERN = re.compile(r'[a-fA-F0-9]{64}\Z')
COUNTRY_PATTERN = re.compile(r'[A-Z]{3}\Z')
KNOWN_AT_BASES = {'VERIFIED_PUBLICATION', 'ARCHIVED_CAPTURE'}
EVENT_STATUSES = {'OBSERVED', 'NO_EVENT_VERIFIED', 'UNKNOWN', 'CENSORED', 'PLANNED'}
VALIDATION_SCOPE = 'CONTRACT_AND_TEMPORAL_CHECKS_ONLY_NOT_PDF_REVERIFICATION'


def _text(value, field):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f'{field} must be a non-empty string')
    return value


def _date(value, field, *, optional=False):
    if value is None and optional:
        return None
    if not isinstance(value, str) or not DATE_PATTERN.fullmatch(value):
        raise ValueError(f'{field} must have exact YYYY-MM-DD precision')
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f'{field} is not a valid date') from exc


def _sha(value, field, *, optional=False):
    if value is None and optional:
        return
    if not isinstance(value, str) or not SHA_PATTERN.fullmatch(value):
        raise ValueError(f'{field} must be a 64-character hexadecimal SHA-256')


def _object(value, field):
    if not isinstance(value, dict):
        raise ValueError(f'{field} must be an object')
    return value


def _unique_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f'Duplicate JSON key: {key}')
        result[key] = value
    return result


def _invalid_constant(value):
    raise ValueError(f'Non-finite JSON number: {value}')


def load_dataset(path):
    """Load strict JSON and validate its contract without deriving labels."""
    with Path(path).open(encoding='utf-8') as stream:
        dataset = json.load(stream, object_pairs_hook=_unique_keys,
                            parse_constant=_invalid_constant)
    _validate_structure(dataset)
    return dataset


def _validate_structure(dataset):
    _object(dataset, 'dataset')
    if dataset.get('schema_version') != SCHEMA_VERSION:
        raise ValueError(f'Unsupported dataset schema; expected {SCHEMA_VERSION}')
    if type(dataset.get('synthetic')) is not bool:
        raise ValueError('synthetic must be explicitly true or false')
    _sha(dataset.get('identity_map_sha256'), 'identity_map_sha256')
    cases = dataset.get('cases')
    if not isinstance(cases, list):
        raise ValueError('cases must be an array')
    case_ids, snapshots, projects, feature_contracts = set(), set(), {}, {}
    reported_first_events = {}
    for case in cases:
        _object(case, 'case')
        cid = _text(case.get('case_id'), 'case_id')
        if cid in case_ids:
            raise ValueError(f'Duplicate case_id: {cid}')
        case_ids.add(cid)
        pid = _text(case.get('project_id'), f'{cid}.project_id')
        country = _text(case.get('country'), f'{cid}.country')
        if not COUNTRY_PATTERN.fullmatch(country):
            raise ValueError(f'{cid}.country must use uppercase ISO3 syntax')
        commodity = _text(case.get('commodity'), f'{cid}.commodity')
        identity = (country, commodity)
        if pid in projects and projects[pid] != identity:
            raise ValueError(f'Conflicting country or commodity for project_id: {pid}')
        projects[pid] = identity
        if case.get('scope') != 'PROJECT':
            raise ValueError(f'{cid}.scope must be PROJECT')
        _date(case.get('as_of'), f'{cid}.as_of')
        if type(case.get('at_risk')) is not bool:
            raise ValueError(f'{cid}.at_risk must be explicitly true or false')
        features = _object(case.get('features'), f'{cid}.features')
        # An absent lineage object is missing evidence, not a malformed number.
        lineage = _object(case.get('lineage', {}), f'{cid}.lineage')
        for name, value in features.items():
            _text(name, f'{cid}.feature name')
            if value is None:
                continue
            try:
                finite = (not isinstance(value, bool) and isinstance(value, (int, float))
                          and math.isfinite(value))
            except (ValueError, OverflowError):
                finite = False
            if not finite:
                raise ValueError(f'{cid}.{name} must be a finite number or null')
        for name, evidence in lineage.items():
            _text(name, f'{cid}.lineage feature name')
            _object(evidence, f'{cid}.lineage.{name}')
            for key in ('known_at', 'effective_date'):
                _date(evidence.get(key), f'{cid}.lineage.{name}.{key}', optional=True)
            _sha(evidence.get('source_sha256'), f'{cid}.lineage.{name}.source_sha256', optional=True)
            if evidence.get('known_at_basis') is not None:
                if (not isinstance(evidence['known_at_basis'], str)
                        or evidence['known_at_basis'] not in KNOWN_AT_BASES):
                    raise ValueError(f'{cid}.{name}: unsupported known_at_basis')
            ids = evidence.get('observation_ids')
            if ids is not None and (not isinstance(ids, list)
                                    or any(not isinstance(x, str) or not x.strip() for x in ids)):
                raise ValueError(f'{cid}.{name}.observation_ids must be an array of non-empty strings')
            for key in ('locator', 'unit', 'basis'):
                if evidence.get(key) is not None and not isinstance(evidence[key], str):
                    raise ValueError(f'{cid}.{name}.{key} must be a string or null')
            if (features.get(name) is not None and evidence.get('unit')
                    and evidence.get('basis')):
                contract = (evidence['unit'], evidence['basis'])
                if name in feature_contracts and feature_contracts[name] != contract:
                    raise ValueError(f'Conflicting unit or basis for feature: {name}')
                feature_contracts[name] = contract
        outcome = _object(case.get('outcome'), f'{cid}.outcome')
        _text(outcome.get('target'), f'{cid}.outcome.target')
        if (not isinstance(outcome.get('event_status'), str)
                or outcome['event_status'] not in EVENT_STATUSES):
            raise ValueError(f'{cid}: unsupported outcome event_status')
        for key in ('event_date', 'known_at', 'followup_end'):
            _date(outcome.get(key), f'{cid}.outcome.{key}', optional=True)
        _sha(outcome.get('source_sha256'), f'{cid}.outcome.source_sha256', optional=True)
        if outcome.get('locator') is not None and not isinstance(outcome['locator'], str):
            raise ValueError(f'{cid}.outcome.locator must be a string or null')
        if outcome['event_status'] == 'NO_EVENT_VERIFIED' and outcome.get('event_date') is not None:
            raise ValueError(f'{cid}: NO_EVENT_VERIFIED cannot contain an event_date')
        snapshot = (pid, case['as_of'], case['scope'], outcome['target'])
        if snapshot in snapshots:
            raise ValueError(f'Duplicate project snapshot for project_id: {pid}')
        snapshots.add(snapshot)
        if outcome['event_status'] == 'OBSERVED' and outcome.get('event_date'):
            endpoint = (pid, outcome['target'])
            if (endpoint in reported_first_events
                    and reported_first_events[endpoint] != outcome['event_date']):
                raise ValueError(f'Conflicting first-event dates for project_id: {pid}, target: {outcome["target"]}')
            # Raw dates must agree as an export contract, but a reported date
            # alone cannot establish an event or alter another snapshot.
            reported_first_events[endpoint] = outcome['event_date']


def _outcome_provenance_complete(outcome):
    return bool(outcome.get('known_at') and outcome.get('source_sha256')
                and isinstance(outcome.get('locator'), str) and outcome['locator'].strip())


def _qualified_first_events(dataset, evaluation_as_of):
    """Collect only event evidence usable at the evaluation cutoff.

    Structure and raw date consistency have already been checked. Qualification
    must precede cross-snapshot decisions: an unavailable or unsupported claim
    must not remove another row from the risk set or invalidate its follow-up.
    """
    first_events = {}
    for case in dataset['cases']:
        outcome = case['outcome']
        event = outcome.get('event_date')
        if (outcome['event_status'] == 'OBSERVED' and event
                and _outcome_provenance_complete(outcome)
                and event <= outcome['known_at'] <= evaluation_as_of):
            first_events[(case['project_id'], outcome['target'])] = event
    # Compare after collecting every qualified event, independently of order.
    # A no-event statement is usable only through follow-up already disclosed
    # by the cutoff; incomplete evidence must remain unknown in _label.
    for case in dataset['cases']:
        outcome = case['outcome']
        event = first_events.get((case['project_id'], outcome['target']))
        if (event and outcome['event_status'] == 'NO_EVENT_VERIFIED'
                and _outcome_provenance_complete(outcome)
                and outcome.get('followup_end')
                and event <= outcome['followup_end'] <= outcome['known_at'] <= evaluation_as_of):
            raise ValueError(f'No-event follow-up contradicts observed first event for project_id: {case["project_id"]}')
    return first_events


def _feature_problem(case):
    lineage = case.get('lineage', {})
    for name, value in sorted(case['features'].items()):
        if value is None:
            continue
        proof = lineage.get(name)
        if proof is None:
            return 'FEATURE_LINEAGE_MISSING', name
        fields = ('observation_ids', 'source_sha256', 'locator', 'known_at',
                  'known_at_basis', 'effective_date', 'unit', 'basis')
        if any(not proof.get(key) or isinstance(proof[key], str) and not proof[key].strip()
               for key in fields):
            return 'FEATURE_LINEAGE_INCOMPLETE', name
        if proof['known_at'] > case['as_of']:
            return 'FEATURE_KNOWN_AFTER_AS_OF', name
        if proof['effective_date'] > case['as_of']:
            return 'FEATURE_EFFECTIVE_AFTER_AS_OF', name
    return None, None


def _label(case, horizon_end, evaluation_as_of):
    """Return label, status, available-at and reason for a first-event target."""
    outcome = case['outcome']
    status = outcome['event_status']
    known = outcome.get('known_at')
    event = outcome.get('event_date')
    followup = outcome.get('followup_end')
    if status in ('UNKNOWN', 'PLANNED'):
        return None, status, None, 'OUTCOME_NOT_OBSERVED'
    if known and known > evaluation_as_of:
        return None, 'UNKNOWN', None, 'OUTCOME_NOT_KNOWN_AT_EVALUATION'
    if status == 'CENSORED':
        return None, 'CENSORED', None, 'FOLLOWUP_INCOMPLETE'
    if not _outcome_provenance_complete(outcome):
        return None, 'UNKNOWN', None, 'OUTCOME_PROVENANCE_INCOMPLETE'
    if status == 'OBSERVED':
        if not event:
            return None, 'UNKNOWN', None, 'EVENT_DATE_UNVERIFIED'
        if known < event:
            return None, 'UNKNOWN', None, 'OUTCOME_KNOWN_BEFORE_EVENT'
        if event <= horizon_end:
            return 1, 'POSITIVE', known, 'OBSERVED_WITHIN_HORIZON'
    # A later first event is not enough by itself: verified follow-up must cover
    # the full interval, as it must for an explicit no-event statement.
    if followup and followup > known:
        return None, 'UNKNOWN', None, 'FOLLOWUP_AFTER_DISCLOSURE'
    if not followup or followup < horizon_end or known < horizon_end:
        return None, 'CENSORED', None, 'FOLLOWUP_INCOMPLETE'
    return 0, 'NEGATIVE', known, ('OBSERVED_AFTER_HORIZON_WITH_FOLLOWUP'
                                if status == 'OBSERVED' else 'NO_EVENT_THROUGH_HORIZON')


def validate_cases(dataset, target, horizon_days, evaluation_as_of, required_features):
    """Validate an upstream export and derive fixed-horizon first-event labels.

    Invalid structures raise ValueError. Cases with unusable feature evidence or
    outside the target risk set are excluded with reasons. Other unlabelled cases
    remain present; consumers must not interpret their null labels as negatives.
    The caller must still filter label_available_at at each training cutoff.
    """
    _validate_structure(dataset)
    _text(target, 'target')
    if type(horizon_days) is not int or horizon_days <= 0:
        raise ValueError('horizon_days must be a positive integer')
    _date(evaluation_as_of, 'evaluation_as_of')
    if not isinstance(required_features, (list, tuple)):
        raise ValueError('required_features must be a list or tuple')
    for feature in required_features:
        _text(feature, 'required_features item')
    if len(set(required_features)) != len(required_features):
        raise ValueError('required_features must not contain duplicates')
    first_events = _qualified_first_events(dataset, evaluation_as_of)
    cases, exclusions = [], []
    for original in dataset['cases']:
        row = copy.deepcopy(original)
        row.setdefault('lineage', {})
        for feature in required_features:
            row['features'].setdefault(feature, None)
        try:
            end = (_date(row['as_of'], 'as_of') + timedelta(days=horizon_days)).isoformat()
        except OverflowError as exc:
            raise ValueError(f"{row['case_id']}: horizon extends beyond supported dates") from exc
        row['horizon_end'] = end
        reason, feature = _feature_problem(row)
        outcome = row['outcome']
        first_event = first_events.get((row['project_id'], outcome['target']))
        if outcome['target'] != target:
            reason, feature = 'TARGET_MISMATCH', None
        elif not row['at_risk'] or (first_event and first_event <= row['as_of']):
            reason, feature = 'ALREADY_OCCURRED', None
        elif row['as_of'] > evaluation_as_of:
            reason, feature = 'AS_OF_AFTER_EVALUATION', None
        if reason:
            item = {'case_id': row['case_id'], 'project_id': row['project_id'], 'reason': reason}
            if feature:
                item['feature'] = feature
            exclusions.append(item)
            continue
        label, status, available, explanation = _label(row, end, evaluation_as_of)
        row.update(label=label, label_status=status, label_available_at=available,
                   label_reason=explanation)
        cases.append(row)
    statuses = Counter(row['label_status'] for row in cases)
    summary = {
        'schema_version': SCHEMA_VERSION,
        'synthetic': dataset['synthetic'],
        'identity_map_sha256': dataset['identity_map_sha256'],
        'target': target,
        'horizon_days': horizon_days,
        'evaluation_as_of': evaluation_as_of,
        'required_features': list(required_features),
        'input_cases': len(dataset['cases']),
        'input_projects': len({c['project_id'] for c in dataset['cases']}),
        'included_cases': len(cases),
        'included_projects': len({c['project_id'] for c in cases}),
        'excluded_cases': len(exclusions),
        'labeled_cases': sum(c['label'] is not None for c in cases),
        'positive_cases': statuses.get('POSITIVE', 0),
        'negative_cases': statuses.get('NEGATIVE', 0),
        'unlabeled_cases': sum(c['label'] is None for c in cases),
        'label_status_counts': dict(sorted(statuses.items())),
        'exclusion_reason_counts': dict(sorted(Counter(c['reason'] for c in exclusions).items())),
        'missing_feature_values': {f: sum(c['features'][f] is None for c in cases)
                                   for f in required_features},
        'validation_scope': VALIDATION_SCOPE,
        'source_documents_reverified': False,
    }
    return {'cases': cases, 'exclusions': exclusions, 'summary': summary}
