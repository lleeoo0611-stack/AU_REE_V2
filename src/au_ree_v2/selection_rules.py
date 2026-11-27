"""Source admissibility and scope-preserving evidence choice shared across layers."""

from collections import defaultdict
from datetime import date

from .resource_estimate import (compare_resource_estimates, cutoff_signature, is_jorc_mineral_resource,
                               resource_estimate_context, resource_location_context)
from .store import canonical, digest, filehash


RESOURCE_ADMISSION_VERSION_PREFIX = 'automatic-resource-admission-v'
RESOURCE_ADMISSION_VERSION_GLOB = RESOURCE_ADMISSION_VERSION_PREFIX + '*'
RESOURCE_ADMISSION_VERSION = RESOURCE_ADMISSION_VERSION_PREFIX + '5'


def is_automatic_resource_admission(observation):
    """All generations of automatic resource observations need run activation."""
    try:
        version = observation['transform_version']
    except (IndexError, KeyError):
        return False
    return isinstance(version, str) and version.startswith(RESOURCE_ADMISSION_VERSION_PREFIX)


def resource_admission_visible(observation, admitted_resource_ids):
    """A historical canonical row is current only when this run re-admits it."""
    return not is_automatic_resource_admission(observation) or observation['obs_id'] in admitted_resource_ids


def resource_admission_link_assessment(candidate, link, ore, grade, reported=None):
    """Verify an automatic contained-TREO supplement against its active pair."""
    if (not ore or not grade or not isinstance(link, dict)
            or candidate['variable'] != 'contained_treo_kt' or link.get('rule') != 'EXACT_SAME_SOURCE_TABLE_AND_STATEMENT'
            or link.get('canonical_observation_ids') != {'ore_mt': ore['obs_id'], 'grade': grade['obs_id']}):
        return {'reason': 'AUTOMATIC_RESOURCE_LINK_NOT_CURRENT', 'comparisons': []}
    dimensions = ('entity_id', 'source_sha', 'statement_id', 'scope', 'effective_date', 'category', 'basis')
    if any(is_automatic_resource_admission(row) or any(row[k] != candidate[k] for k in dimensions)
           for row in (ore, grade)):
        return {'reason': 'AUTOMATIC_RESOURCE_LINK_NOT_CURRENT', 'comparisons': []}
    if not is_jorc_mineral_resource(candidate):
        return {'reason': 'AUTOMATIC_RESOURCE_NOT_JORC_MINERAL_RESOURCE', 'comparisons': []}
    location = resource_location_context(candidate)
    original = [resource_location_context(row) for row in (ore, grade)]
    if (type(location['physical_page']) is not int or location['physical_page'] < 1
            or str(link.get('reported_table_label', '')).casefold() != location['printed_table']
            or any(item != location for item in original)):
        return {'reason': 'AUTOMATIC_RESOURCE_LINK_LOCATION_NOT_CURRENT', 'comparisons': [],
                'candidate_location': location, 'legacy_locations': original}
    completion = link.get('legacy_completion')
    if completion is not None and not isinstance(completion, dict):
        return {'reason': 'AUTOMATIC_RESOURCE_LINK_CONTEXT_UNRESOLVED', 'comparisons': []}
    prior_rows = (ore, grade, reported) if reported else (ore, grade)
    comparisons = [{'observation_id': row['obs_id'], **compare_resource_estimates(
        candidate, row, right_completion=(completion or {}).get(row['obs_id']))} for row in prior_rows]
    reason = ('AUTOMATIC_RESOURCE_LINK_CONTEXT_MISMATCH' if any(item['status'] == 'INCOMPATIBLE' for item in comparisons)
              else 'AUTOMATIC_RESOURCE_LINK_CONTEXT_UNRESOLVED' if any(item['status'] == 'UNRESOLVED' for item in comparisons)
              else None)
    return {'reason': reason, 'comparisons': comparisons}


def resource_admission_link_matches(candidate, link, ore, grade, reported=None):
    return resource_admission_link_assessment(candidate, link, ore, grade, reported)['reason'] is None


def automatic_resource_scope(observation):
    """An independently admitted scope is defined by more than its name."""
    if not is_automatic_resource_admission(observation):
        return None
    context = resource_estimate_context(observation)
    return canonical([context['category'], context['deposit'], context['scope_coverage'],
                      context['resource_type'], context['reporting_standard'],
                      cutoff_signature(context['cutoff_grade']), context['material_basis'], context['denominator_basis']])


def automatic_resource_scope_assessment(observation, legacy_pairs):
    """Check an independent automatic estimate against existing scientific scopes."""
    pairs = [[{'observation_id': prior['obs_id'], **compare_resource_estimates(
        observation, prior, compare_date=False)} for prior in pair] for pair in legacy_pairs]
    comparisons = [item for pair in pairs for item in pair]
    if not comparisons or any(all(item['status'] == 'EQUIVALENT' for item in pair) for pair in pairs):
        return {'reason': None, 'comparisons': comparisons}
    reason = ('AUTOMATIC_RESOURCE_SCOPE_MISMATCH' if all(item['status'] == 'INCOMPATIBLE' for item in comparisons)
              else 'AUTOMATIC_RESOURCE_SCOPE_UNRESOLVED')
    return {'reason': reason, 'comparisons': comparisons}


def observation_visible(raw, selected_shas, validation_version=None):
    """Extraction versions must be in the lock, as well as their original PDF."""
    return (not raw.get('extraction_artifact_sha256') or raw['extraction_artifact_sha256'] in selected_shas) and (
        not validation_version or not raw.get('parser_version') or raw.get('validation_version')==validation_version)


def evidence_domain(variable, raw):
    """Shared raw-domain taxonomy; a domain assignment never grants a score."""
    if raw.get('domain'):
        return raw['domain']
    v=variable
    if v in ('ore_mt','grade','contained_treo_kt') or v.startswith(('reported_resource_','reported_reserve_','reported_bulk_','reported_fine_fraction_')):return 'Resource'
    if v.startswith(('reported_technical_','uranium','thorium')) or 'recovery' in v:return 'Technical'
    if 'share_pct' in v or v.startswith(('reported_magnet','reported_dy','reported_tb','reported_nd','reported_pr')):return 'Strategic'
    if v=='study_maturity_ord':return 'Development'
    if v=='commercial_event' or any(w in v for w in ('equity','financ','offtake','debt','capex','convertible','note_')):return 'Commercial'
    return None


def date_end(value):
    """Conservative end of disclosed month/year, without inventing an exact day."""
    import calendar
    if len(value) == 4:
        return value + '-12-31'
    if len(value) == 7:
        year, month = map(int, value.split('-'))
        return f'{value}-{calendar.monthrange(year, month)[1]:02d}'
    date.fromisoformat(value)
    return value


def source_check(source, cutoff, root=None, acquired_through=None):
    if not source:
        return 'SOURCE_NOT_SELECTED'
    try:
        if any(date_end(source[k]) > (acquired_through or cutoff if k=='available_date' else cutoff) for k in ('publication_date', 'available_date') if source.get(k)):
            return 'SOURCE_AFTER_CUTOFF'
        if root is not None and filehash(root / source['path']) != source['sha256']:
            return 'SOURCE_HASH_MISMATCH'
    except (ValueError, KeyError, OSError):
        return 'INVALID_SOURCE_IDENTITY_OR_DATE'
    return None


def choose(options, dimensions=('scope', 'unit', 'basis', 'endpoint', 'scale', 'feed')):
    """Latest *within* a semantic scope; cross-scope choice requires a rule.

    Identical same-date evidence is corroboration, never an insertion-order tie
    break. Multiple studies are not corroboration unless their study ID agrees.
    """
    options = list({digest(o): o for o in options}.values())
    if not options:
        return None, 'NO_COMPATIBLE_EVIDENCE'
    groups = defaultdict(list)
    for o in options:
        groups[tuple(o.get(k) for k in dimensions)].append(o)
    active = []
    for group in groups.values():
        latest = max(date_end(o['effective_date']) for o in group)
        current = [o for o in group if date_end(o['effective_date']) == latest]
        if len({canonical(o.get('value')) for o in current}) != 1:
            return None, 'CONCURRENT_SOURCE_CONFLICT'
        merged = dict(sorted(current, key=canonical)[0])
        merged['evidence_ids'] = sorted({i for o in current for i in o.get('evidence_ids', [o['evidence_id']])})
        merged['sources'] = sorted({o['source_sha256'] for o in current})
        active.append(merged)
    if len(active) != 1:
        return None, 'MULTIPLE_SCOPES_REQUIRE_DEFINITION'
    return active[0], 'SELECTED'
