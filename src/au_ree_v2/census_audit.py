"""Read-only diagnostics attached to the canonical Census projection."""
import json
from collections import Counter

from .analysis import write_csv
from .census import summary_observation
from .store import canonical, digest


def date_precision(text):
    return {4: 'YEAR', 7: 'MONTH', 10: 'DAY'}.get(len(text or ''), 'UNKNOWN')


def field_diagnosis(column, reason, field_issues, stage_issues, bundle, resource_reason, rules):
    """Retain machine-readable findings without changing legacy missing codes."""
    findings = [dict(kind='FIELD_REVIEW', **issue) for issue in field_issues]
    findings.extend(dict(kind='STAGE_REVIEW', **issue) for issue in stage_issues)
    if reason != 'RULE_INPUT_MISSING':
        return reason, findings
    codes = {entry['reason'] for entry in findings if entry.get('reason')}
    if any('CONFLICT' in code or 'AMBIGU' in code for code in codes):
        status = 'CONFLICT_OR_AMBIGUITY_REVIEW'
    elif codes & {'MISSING_PAGE_OR_TWO_MARKERS', 'EXTRACTION_PAGE_CHECK_FAILED'}:
        status = 'PAGE_EVIDENCE_UNVERIFIED'
    elif codes & {'SOURCE_SHA_CHANGED', 'SOURCE_HASH_MISMATCH'}:
        status = 'SOURCE_BINDING_MISMATCH'
    elif codes:
        status = 'EVIDENCE_REVIEW_REQUIRED'
    elif column in ('緯度', '經度'):
        status = 'REPRESENTATIVE_POINT_NOT_VERIFIED'
    elif column in ('開發階段代碼', '開發階段類別', '礦床型態代碼'):
        status = 'CLASSIFICATION_INPUT_NOT_VERIFIED'
    elif column in rules['annual_columns']:
        status = 'COMPATIBLE_FORECAST_INPUT_NOT_VERIFIED'
    elif column in rules['resource_columns']:
        status = ('PARTIAL_RESOURCE_BASIS_OR_COMPONENTS' if bundle and bundle.get('partial_resource_projection')
                  else 'SELECTED_STATEMENT_FIELD_INPUT_MISSING' if bundle
                  else 'RESOURCE_STATEMENT_NOT_VERIFIED')
    else:
        status = 'COMPATIBLE_INPUT_OR_DECISION_NOT_VERIFIED'
    if column in rules['resource_columns']:
        findings.append(dict(kind='RESOURCE_REVIEW', reason=resource_reason,
            statement={key: bundle[key] for key in
                       ('source_sha256', 'statement_id', 'scope', 'effective_date')} if bundle else None))
    return status, findings


def resource_statement_observations(db, observations, bundles):
    """Expose current observation groups at source/statement/scope/date grain.

    The temporary view leaves the frozen database schema and scientific selector intact.
    """
    db.execute('''CREATE TEMP VIEW IF NOT EXISTS census_resource_observation AS
        SELECT o.*, s.publication_date, s.acquired_at
        FROM observations o JOIN sources s ON s.sha=o.source_sha
        WHERE o.status='AUTO_VALIDATED' ''')
    observed_ids = {o['obs_id'] for rows in observations.values() for o in rows}
    for o in db.execute('SELECT * FROM census_resource_observation ORDER BY entity_id, source_sha, statement_id, scope, effective_date, obs_id'):
        if o['obs_id'] not in observed_ids:
            continue
        raw = summary_observation(o)
        variable = o['variable']
        if (variable not in ('ore_mt', 'grade', 'contained_treo_kt', 'magnet_reo_share_pct')
                and not variable.startswith('reported_resource_')
                and not (raw.get('material_basis') or '').startswith(('RESOURCE_', 'HEAVY_MINERAL_'))
                and not (raw.get('review_contract') and variable.startswith('reported_'))):
            continue
        pid = o['entity_id']
        key = (o['source_sha'], o['statement_id'], o['scope'], o['effective_date'])
        bundle = bundles.get(pid)
        selected = bool(bundle and key == tuple(bundle[k] for k in
                        ('source_sha256', 'statement_id', 'scope', 'effective_date')))
        contract = raw.get('review_contract') or {}
        yield dict(project_id=pid, statement_group_id=digest([pid, *key]), statement_id=o['statement_id'],
                   source_sha256=o['source_sha'], scope=o['scope'], category=o['category'],
                   reporting_standard=raw.get('reporting_standard') or contract.get('reporting_standard'),
                   cutoff=raw.get('cutoff') or contract.get('cutoff'),
                   effective_date=o['effective_date'], effective_date_precision=date_precision(o['effective_date']),
                   publication_date=o['publication_date'], publication_date_precision=date_precision(o['publication_date']),
                   acquired_at=o['acquired_at'], selected_for_census=int(selected),
                   observation_id=o['obs_id'], variable=variable, value=o['value'], unit=o['unit'],
                   basis=o['basis'], material_basis=raw.get('material_basis'), locator=o['locator'],
                   physical_page=raw.get('pdf_page'), transform_version=o['transform_version'])


RESOURCE_FIELDS = ('project_id', 'statement_group_id', 'statement_id', 'source_sha256', 'scope', 'category',
                   'reporting_standard', 'cutoff', 'effective_date', 'effective_date_precision',
                   'publication_date', 'publication_date_precision', 'acquired_at', 'selected_for_census',
                   'observation_id', 'variable', 'value', 'unit', 'basis', 'material_basis', 'locator',
                   'physical_page', 'transform_version')

SPATIAL_FIELDS = ('project_id', 'status', 'longitude', 'latitude', 'point_role', 'native_feature_id',
                  'origin_crs', 'export_crs', 'precision_m', 'source_sha256', 'locator', 'dataset',
                  'method', 'distance_use', 'review_details')


def spatial_quality(row, trace):
    pid = row['專案ID']
    point = trace[pid, '緯度']
    lon, lat = row['經度'], row['緯度']
    if not (lon and lat):
        return dict(project_id=pid, status=point['method'], distance_use='NO_POINT')
    try:
        scope = json.loads(point['scope'])
    except (TypeError, ValueError):
        scope = {}
    dataset = scope.get('dataset', '')
    if scope.get('tenement_ids'):
        role = 'TENEMENT_REPRESENTATIVE_POINT'
    elif dataset:
        role = 'OFFICIAL_FEATURE_REPRESENTATIVE_POINT'
    else:
        role = 'SOURCE_RECORD_REPRESENTATIVE_POINT'
    origin = scope.get('input_crs') or scope.get('datum') or (scope.get('datum_control') or {}).get('datum', '')
    exported = scope.get('output_crs') or ('EPSG:7844' if dataset == 'NT_STRIKE' else origin)
    # NT STRIKE stored points are transformed to geographic GDA2020 by summary_locations.
    return dict(project_id=pid, status='REVIEWED_CENSUS_POINT', longitude=lon, latitude=lat,
                point_role=role, native_feature_id=scope.get('feature_id'), origin_crs=origin,
                export_crs=exported, precision_m=scope.get('precision_m'), source_sha256=point['source_sha256'],
                locator=point['locator'], dataset=dataset, method=point['method'],
                distance_use='REQUIRES_SCOPE_CRS_AND_LAYER_REVIEW', review_details=point['scope'])


def write_census_audit(db, out, rows, trace, diagnoses, observations, bundles):
    fields = ('project_id', 'column', 'value_state', 'legacy_reason', 'status', 'findings',
              'source_sha256', 'observation_ids', 'locator')
    entries = []
    for (pid, column), value in trace.items():
        if value['value'] != '':
            status, legacy, findings = 'VALUE_PRESENT', '', []
        else:
            status, legacy, findings = diagnoses[pid, column]
        entries.append(dict(project_id=pid, column=column, value_state='PRESENT' if value['value'] != '' else 'BLANK',
                            status=status, legacy_reason=legacy, findings=canonical(findings),
                            source_sha256=value['source_sha256'], observation_ids=value['observation_ids'],
                            locator=value['locator']))
    write_csv(out/'field_status.csv', entries, fields)
    resource_rows = list(resource_statement_observations(db, observations, bundles))
    write_csv(out/'resource_statement_observations.csv', resource_rows, RESOURCE_FIELDS)
    write_csv(out/'spatial_point_quality.csv', [spatial_quality(r, trace) for r in rows], SPATIAL_FIELDS)
    return dict(field_status_counts=dict(Counter(r['status'] for r in entries)),
                count_excluded_by_applicability=sum(r['legacy_reason'] in ('NOT_APPLICABLE_NO_MRE','NOT_APPLICABLE_STAGE')
                                                      for r in entries),
                selected_resource_statement_groups=len({r['statement_group_id'] for r in resource_rows
                                                        if r['selected_for_census']}),
                complete_treo_resource_projects=sum(bool(r['有TREO資源估計']) for r in rows))
