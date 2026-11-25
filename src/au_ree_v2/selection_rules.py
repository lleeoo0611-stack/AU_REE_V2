"""Source admissibility and scope-preserving evidence choice shared across layers."""

from collections import defaultdict
from datetime import date

from .store import canonical, digest, filehash


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
