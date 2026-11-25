"""Source-bound candidate milestone review. This projection supplies no ranking scores."""
import json
import unicodedata
from collections import Counter, defaultdict
from functools import lru_cache
from pathlib import Path

import pymupdf

from .selection_rules import date_end
from .store import digest, filehash
from .tabular import write_csv


EVENT_FIELDS = (
    'project_id', 'event_id', 'codebook_version', 'event_type', 'status', 'scope_role',
    'scope', 'candidate_code', 'decision', 'reason', 'event_date', 'event_date_precision',
    'event_interval', 'disclosure_of_event_date', 'first_mre_publication_date',
    'reporting_standard', 'actual_product', 'source_sha256', 'source_url', 'physical_page',
    'project_marker', 'markers', 'publication_date', 'publication_date_precision',
    'selected_statement_id', 'observation_ids',
)
COMPARISON_FIELDS = (
    'project_id', 'project', 'cutoff', 'codebook_version', 'census_stage_code',
    'highest_confirmed_candidate', 'highest_scope_role', 'highest_scope', 'highest_event_ids',
    'highest_source_locators', 'highest_event_dates', 'interpretation', 'comparison_reason', 'mre_evidence',
    'first_mre_publication_date', 'latest_documented_operating_status', 'operating_status_evidence',
    'ongoing_work_as_reported', 'ongoing_work_evidence', 'unresolved_reasons',
)


def _norm(value):
    return ' '.join(unicodedata.normalize('NFKC', value).casefold().split())


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def _precision(value):
    return {0: 'UNKNOWN', 4: 'YEAR', 7: 'MONTH', 10: 'DAY'}[len(value)]


def evaluate_event(event, policy):
    """Return the strongest claim justified by a verified, attributed page."""
    kind, status = event['event_type'], event['status']
    if kind == 'OPERATING_STATUS':
        return '', 'STATUS_ONLY', 'DATED_OPERATOR_AND_SCOPE'
    rule = policy['by_type'][kind]
    if event['scope_role'] not in rule['scope_roles']:
        return '', 'OUT_OF_SCOPE', 'EVENT_OUTSIDE_ELIGIBLE_ASSET_SCOPE'
    if status != rule['required_status']:
        return '', 'NEXT_WORK' if status == 'IN_PROGRESS' else 'REVIEW', 'REQUIRED_EVENT_STATUS_NOT_ESTABLISHED'
    if kind in policy['deferred_boundaries']:
        return '', 'REVIEW', 'OPERATIONAL_BOUNDARY_NOT_ADOPTED'
    if kind == 'RECOGNIZED_MRE' and not (event.get('reporting_standard') and event.get('selected_statement_id')):
        return '', 'REVIEW', 'STANDARD_OR_SELECTED_RESOURCE_SCOPE_UNVERIFIED'
    if kind == 'RAMP_UP' and not (event.get('actual_product') and event.get('actual_output_marker') in event['markers']):
        return '', 'REVIEW', 'ACTUAL_PRODUCT_OUTPUT_NOT_VERIFIED'
    return rule['code'], 'CONFIRMED', 'SOURCE_SUPPORTS_EVENT_AT_STATED_SCOPE'


def _review(binding, source, page_text, bundle, observations, cutoff, policy):
    event = dict(binding)
    sha = binding['source_sha256']
    page = binding['physical_page']
    publication = (source or {}).get('publication_date') or ''
    precision = (source or {}).get('publication_date_precision', '').upper()
    publication = publication[:{'MONTH': 7, 'YEAR': 4}.get(precision, len(publication))]
    event.update(event_id=digest([policy['version'], binding]), codebook_version=policy['version'],
                 source_url=(source or {}).get('url', ''), publication_date=publication,
                 publication_date_precision=_precision(publication), event_date_precision=_precision(event.get('event_date', '')),
                 selected_statement_id='', observation_ids='[]')
    problem = ''
    if source is None:
        problem = 'SOURCE_NOT_SELECTED_OR_NOT_ACQUIRED'
    elif not publication or date_end(publication) > cutoff:
        problem = 'PUBLICATION_DATE_UNVERIFIED_OR_AFTER_CUTOFF'
    elif any(date_end(event[key]) > cutoff for key in ('event_date', 'first_mre_publication_date',
                                                        'disclosure_of_event_date') if event.get(key)):
        problem = 'EVENT_AFTER_CUTOFF'
    elif not (text := page_text(sha, page)):
        problem = 'ORIGINAL_OR_PAGE_UNVERIFIED'
    elif not all(_norm(marker) in text for marker in [binding['project_marker'], *binding['markers']]):
        problem = 'PROJECT_OR_EVENT_PAGE_MARKER_UNVERIFIED'
    if not problem and event['event_type'] == 'RECOGNIZED_MRE' and bundle and bundle['source_sha256'] == sha:
        ids = sorted(o['obs_id'] for o in observations if o['variable'] == 'ore_mt' and o['source_sha'] == sha
                     and o['scope'] == bundle['scope'] and o['effective_date'] == bundle['effective_date']
                     and o['statement_id'] == bundle['statement_id'])
        if ids:
            event.update(selected_statement_id=bundle['statement_id'], observation_ids=_json(ids))
    code, decision, reason = ('', 'REVIEW', problem) if problem else evaluate_event(event, policy)
    event.update(candidate_code=code, decision=decision, reason=reason, markers=_json(event['markers']))
    return event


def _comparison(row, events, bundle, scan_reasons, cutoff, policy):
    confirmed = [e for e in events if e['decision'] == 'CONFIRMED']
    highest = max((e['candidate_code'] for e in confirmed), key=policy['order'].index, default='')
    selected = [e for e in confirmed if e['candidate_code'] == highest]
    mre = [e for e in confirmed if e['event_type'] == 'RECOGNIZED_MRE']
    first = sorted({e['first_mre_publication_date'] for e in mre if e.get('first_mre_publication_date')})
    reasons = {e['reason'] for e in events if e['decision'] == 'REVIEW'} | set(scan_reasons)
    if len(first) > 1:
        reasons.add('CONFLICTING_FIRST_RELEASE_DATES')
    if bundle and not mre:
        reasons.add('SELECTED_RESOURCE_REQUIRES_STANDARD_AND_SCOPE_REVIEW')
    if not selected:
        reasons.add('NO_CONFIRMED_MILESTONE_IN_REVIEWED_EVIDENCE')
    statuses = [e for e in events if e['decision'] == 'STATUS_ONLY']
    latest = max((date_end(e['publication_date']) for e in statuses), default='')
    statuses = [e for e in statuses if date_end(e['publication_date']) == latest]
    ongoing = [e for e in events if e['decision'] == 'NEXT_WORK']
    # A subsequently confirmed completion of the same undertaking supersedes an older progress report.
    ongoing = [e for e in ongoing if not any(c['event_type'] == e['event_type'] and c['scope'] == e['scope']
               and date_end(c['publication_date']) >= date_end(e['publication_date']) for c in confirmed)]
    if highest:
        basis = ','.join(sorted({e['event_type'] + '/' + e['status'] for e in selected}))
        comparison_reason = 'Attributed original supports ' + basis + ' at the recorded scope.'
        if highest == 'A3':
            comparison_reason += ' A3 records the resource threshold separately from the date of first publication.'
        elif highest in ('B1', 'B2', 'B3'):
            comparison_reason += ' Scoping, PFS and FS completion are separate candidate milestones.'
        elif highest == 'D2':
            comparison_reason += ' Ramp-up applies to the documented product and facility.'
    elif statuses:
        comparison_reason = 'Operator status is documented; the highest historical milestone still needs evidence.'
    else:
        comparison_reason = 'Reviewed evidence does not yet establish a candidate milestone for this project.'
    def values(records, key):
        return ';'.join(sorted({str(r[key]) for r in records if r.get(key)}))
    return dict(project_id=row['專案ID'], project=row['專案名稱'], cutoff=cutoff, codebook_version=policy['version'],
                census_stage_code=row['開發階段代碼'], highest_confirmed_candidate=highest,
                highest_scope_role=values(selected,'scope_role'), highest_scope=values(selected,'scope'),
                highest_event_ids=values(selected,'event_id'), highest_event_dates=values(selected,'event_date'),
                highest_source_locators=_json([{'sha':e['source_sha256'], 'page':e['physical_page']} for e in selected]),
                comparison_reason=comparison_reason,
                interpretation='HIGHEST_OF_SOURCE_REVIEWED_EVENTS' if selected else 'PENDING_EVIDENCE',
                mre_evidence='RECOGNIZED_MRE_CONFIRMED' if mre else ('SELECTED_ESTIMATE_STANDARD_PENDING' if bundle else 'UNVERIFIED'),
                first_mre_publication_date=first[0] if len(first)==1 else '',
                latest_documented_operating_status=values(statuses,'status') or 'UNKNOWN',
                operating_status_evidence=values(statuses,'event_id'), ongoing_work_as_reported=values(ongoing,'event_type'),
                ongoing_work_evidence=values(ongoing,'event_id'), unresolved_reasons=';'.join(sorted(reasons)))


def write_milestones(root, out, rows, sources, observations, bundles, stage_audit, cutoff):
    codebook = root/'config/candidate_milestones.json'
    catalog_path = root/'data/candidate_milestone_evidence.json'
    if not codebook.exists() and not catalog_path.exists():
        return {'candidate_milestones': {'status':'NO_CANDIDATE_PROFILE_IN_CHECKOUT'}}
    policy = json.loads(codebook.read_text(encoding='utf8'))
    catalog = json.loads(catalog_path.read_text(encoding='utf8'))
    if catalog['version'] != policy['version']:
        raise ValueError('MILESTONE_EVIDENCE_CODEBOOK_VERSION_MISMATCH')
    policy['by_type'] = {r['event_type']:r for r in policy['stages']}
    policy['order'] = [r['code'] for r in policy['stages']]
    members = {r['專案ID'] for r in rows}
    by_project = defaultdict(list)
    scan_reasons = defaultdict(set)
    for item in stage_audit:
        if item.get('reason'):
            scan_reasons[item['project_id']].add(item['reason'])

    @lru_cache(maxsize=None)
    def verified_original(sha):
        path = Path(sources[sha]['resolved_path'])
        return path if path.is_file() and filehash(path) == sha else None

    @lru_cache(maxsize=None)
    def page_text(sha, page):
        path = verified_original(sha)
        if path and sources[sha].get('kind') == 'pdf':
            try:
                with pymupdf.open(path) as doc:
                    if 1 <= page <= len(doc):
                        return _norm(doc[page-1].get_text())
            except (OSError, ValueError, pymupdf.FileDataError):
                pass
        return ''

    events = []
    for binding in catalog['events']:
        pid = binding['project_id']
        if pid not in members:
            continue
        event = _review(binding, sources.get(binding['source_sha256']), page_text, bundles.get(pid),
                        observations.get(pid, []), cutoff, policy)
        events.append(event)
        by_project[pid].append(event)
    events.sort(key=lambda e:(e['project_id'], e['source_sha256'], e['physical_page'], e['event_id']))
    comparisons = [_comparison(row, by_project[pid], bundles.get(pid), scan_reasons[pid], cutoff, policy)
                   for row in rows for pid in [row['專案ID']]]
    write_csv(out/'milestone_events.csv', events, EVENT_FIELDS)
    write_csv(out/'milestone_comparison.csv', comparisons, COMPARISON_FIELDS)
    return dict(candidate_milestones=dict(codebook_version=policy['version'],
                source_cutoff=cutoff, evidence_catalog_sha256=filehash(catalog_path),
                codebook_sha256=filehash(codebook), rows=len(comparisons),
                stages=dict(Counter(r['highest_confirmed_candidate'] or 'PENDING' for r in comparisons)),
                events=dict(Counter(e['decision'] for e in events)), applied_to_mcda=False))
