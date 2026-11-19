"""Read-only diagnostics attached to the canonical Census projection."""
import json
from collections import Counter

from .tabular import write_csv
from .census import summary_matching_resource_pdf, summary_observation
from .store import canonical, digest
from .evidence_model import compatible_resource_context, ensure_read_model


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

    Source edition and run selection identities are distinct. An explicitly matched
    PDF can support the selected edition without overwriting its own source key.
    """
    ensure_read_model(db)
    observed_ids = {o['obs_id'] for rows in observations.values() for o in rows}
    for o in db.execute("""SELECT * FROM resource_statement_facts WHERE status='AUTO_VALIDATED'
                           ORDER BY entity_id, source_sha, statement_id, scope, effective_date, obs_id"""):
        if o['obs_id'] not in observed_ids:
            continue
        raw = summary_observation(o)
        variable = o['variable']
        pid = o['entity_id']
        key = (o['source_sha'], o['statement_id'], o['scope'], o['effective_date'])
        bundle = bundles.get(pid)
        bundle_key = tuple(bundle[k] for k in ('source_sha256', 'statement_id', 'scope', 'effective_date')) if bundle else None
        equivalent = bool(bundle and summary_matching_resource_pdf(o, raw, bundle))
        selected = bool(bundle and (key == bundle_key or equivalent) and
                        o['obs_id'] not in bundle.get('incompatible_component_ids', ()) and
                        compatible_resource_context([*bundle.get('observations', []), dict(o)]))
        yield dict(project_id=pid, statement_group_id=digest([pid, *(bundle_key if equivalent else key)]), statement_id=o['statement_id'],
                   source_sha256=o['source_sha'], scope=o['scope'], category=o['category'],
                   reporting_standard=o['reporting_standard'], cutoff=o['cutoff_grade'],
                   effective_date=o['effective_date'], effective_date_precision=o['declared_date_precision'] or date_precision(o['effective_date']),
                   publication_date=o['publication_date'], publication_date_precision=date_precision(o['publication_date']),
                   acquired_at=o['acquired_at'], selected_for_census=int(selected),
                   observation_id=o['obs_id'], variable=variable, value=o['value'], unit=o['unit'],
                   basis=o['basis'], material_basis=raw.get('material_basis'), locator=o['locator'],
                   physical_page=raw.get('pdf_page') or raw.get('physical_page'), transform_version=o['transform_version'],
                   source_statement_key=o['source_statement_key'], statement_kind=o['statement_kind'],
                   date_role=o['date_role'], original_token=o['reported_token'], original_unit=o['reported_unit'],
                   denominator_basis=o['denominator_basis'], rounding_half_width=o['rounding_half_width'],
                   original_estimate_period=o['original_estimate_period'],
                   source_transform=o['source_transform'], referenced_statement_label=o['referenced_statement_label'],
                   selection_role=('VERIFIED_EQUIVALENT_SOURCE' if selected and equivalent else
                                   'MATCHED_SELECTED_STATEMENT' if selected else 'NOT_SELECTED'))


RESOURCE_FIELDS = ('project_id', 'statement_group_id', 'statement_id', 'source_sha256', 'scope', 'category',
                   'reporting_standard', 'cutoff', 'effective_date', 'effective_date_precision',
                   'publication_date', 'publication_date_precision', 'acquired_at', 'selected_for_census',
                   'observation_id', 'variable', 'value', 'unit', 'basis', 'material_basis', 'locator',
                   'physical_page', 'transform_version','source_statement_key','statement_kind',
                   'date_role','original_token','original_unit','denominator_basis','rounding_half_width',
                   'source_transform','referenced_statement_label','selection_role','original_estimate_period')

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


def resource_field_lineage(db, trace, resource_rows, bundles, resource_columns):
    """Link the actual field formula and its recorded supporting observations to the selector."""
    facts = {r['observation_id']: r for r in resource_rows}
    observation_projects = dict(db.execute('SELECT obs_id,entity_id FROM observations'))
    for (pid, column), field in trace.items():
        if column not in resource_columns or field['value'] == '' or not bundles.get(pid):
            continue
        bundle = bundles[pid]
        group = digest([pid, *(bundle[k] for k in ('source_sha256','statement_id','scope','effective_date'))])
        support = sorted(set(json.loads(field['observation_ids'])))
        editions = {facts[k]['source_statement_key'] for k in support if k in facts}
        context_ids = [k for k in support if k not in facts and observation_projects.get(k) == pid]
        selected_ids = [k for k in support if k in facts and facts[k]['project_id'] == pid
                        and facts[k]['statement_group_id'] == group and facts[k]['selected_for_census']]
        outside = sorted(set(support).difference(context_ids, selected_ids))
        yield dict(project_id=pid, column=column, value=field['value'], statement_group_id=group,
                   method=field['method'], source_sha256=field['source_sha256'], locator=field['locator'],
                   supporting_observation_ids=canonical(support), source_statement_keys=canonical(sorted(editions)),
                   selected_resource_observation_ids=canonical(selected_ids),context_observation_ids=canonical(context_ids),
                   unresolved_support_ids=canonical(outside))


def write_census_audit(db, out, rows, trace, diagnoses, observations, bundles, *, resource_columns=()):
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
    lineage = list(resource_field_lineage(db, trace, resource_rows, bundles, resource_columns))
    write_csv(out/'resource_statement_lineage.csv', lineage, ('project_id','column','value','statement_group_id',
              'method','source_sha256','locator','supporting_observation_ids','source_statement_keys',
              'selected_resource_observation_ids','context_observation_ids','unresolved_support_ids'))
    write_csv(out/'spatial_point_quality.csv', [spatial_quality(r, trace) for r in rows], SPATIAL_FIELDS)
    return dict(field_status_counts=dict(Counter(r['status'] for r in entries)),
                count_excluded_by_applicability=sum(r['legacy_reason'].startswith('NOT_APPLICABLE_')
                                                      for r in entries),
                selected_resource_statement_groups=len({r['statement_group_id'] for r in resource_rows
                                                        if r['selected_for_census']}),
                complete_treo_resource_projects=sum(bool(r['有TREO資源估計']) for r in rows))
