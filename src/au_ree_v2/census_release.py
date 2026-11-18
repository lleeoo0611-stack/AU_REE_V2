"""Provenance for a release produced by the integrated Census run."""
import csv
import json
import math
from collections import defaultdict
from pathlib import Path

from .analysis import write_csv
from .census import summary_settings
from .census_audit import date_precision
from .security import public_export
from .store import canonical, digest, filehash


def read_rows(path):
    if not path.is_file():
        return []
    limit = csv.field_size_limit()
    try:
        csv.field_size_limit(max(limit, 16 * 1024 * 1024))
        with path.open(encoding='utf-8-sig', newline='') as stream:
            return list(csv.DictReader(stream))
    finally:
        csv.field_size_limit(limit)


def source_dates(source):
    return {key: {'value': source.get(key),
                  'precision': ('TIMESTAMP' if 'T' in (source.get(key) or '') else date_precision(source.get(key)))}
            for key in ('publication_date', 'acquired_at', 'available_date')}


def identity_roles(out, trace, identity):
    rows = []
    for item in identity['accepted']:
        rows.append(dict(project_id=item['canonical_id'], related_id=item['alias_id'],
                         role='DOCUMENTED_CANONICAL_ALIAS', status=item['status'],
                         source_sha256=item['source_sha256'], locator=item['locator']))
    for field in trace:
        if field['column'] not in ('開發商', '未上市公司', 'ASX代碼') or not field['value']:
            continue
        role = {'未上市公司': 'LISTING_STATUS', 'ASX代碼': 'ASX_CODE',
                '開發商': 'SOURCE_COMPANY_OR_DEVELOPER_LABEL'}[field['column']]
        rows.append(dict(project_id=field['project_id'], role=role, label=field['value'],
                         status=field['method'], evidence_date=field['effective_date'],
                         source_sha256=field['source_sha256'], locator=field['locator'],
                         scope=field['scope'], observation_ids=field['observation_ids']))
    write_csv(out/'census_identity_roles.csv', rows, (
        'project_id', 'related_id', 'role', 'label', 'status', 'evidence_date', 'valid_from',
        'valid_to', 'source_sha256', 'locator', 'scope', 'observation_ids'))


def matching_traces(traces, score):
    return [r for r in traces if r.get('score') not in ('', None)
            and math.isclose(float(r['score']), float(score), abs_tol=1e-12, rel_tol=1e-12)]


def evidence_reference(value):
    """Retain lineage identifiers and locators without repeating extracted documents."""
    if isinstance(value, dict):
        return {k:evidence_reference(v) for k,v in value.items()
                if k not in ('raw','quote','raw_quote','original_text','source_text')}
    if isinstance(value, list):
        return [evidence_reference(v) for v in value]
    return value


def candidate_trace_inputs(traced, pid, canonical_id, code, row):
    matches = matching_traces(traced[pid, code], row[code])
    if not matches and canonical_id != pid:
        matches = matching_traces(traced[canonical_id, code], row[code])
    inputs = [dict(raw_value=r['raw_value'], evidence=json.loads(r['source']))
              for r in {r['source']: r for r in matches}.values()]
    if row.get('case_id') and any(r['evidence'].get('case_id') for r in inputs):
        inputs = [r for r in inputs if r['evidence'].get('case_id')==row['case_id']]
    case_signatures = {(r['evidence'].get('case_id'), r['evidence'].get('source_sha256'),
                        r['evidence'].get('scope'), float(r['raw_value'])) for r in inputs}
    if len(inputs)>1 and len(case_signatures)==1 and all(next(iter(case_signatures))[:3]):
        return [max(inputs, key=lambda r:len(r['evidence']))], 'SAME_CASE_AND_SOURCE'
    return inputs, ('SCORE_MATCHED_TRACE' if len(inputs)==1 else 'AMBIGUOUS_TRACE' if inputs
                    else 'TRACE_NOT_LOCATED')


def panel_artifacts(out, prepared, results, selected, identity):
    traced = defaultdict(list)
    for row in prepared['traces']:
        traced[row['entity_id'], row['criterion']].append(row)
    technical = defaultdict(list)
    for row in read_rows(out/'technical_panel_inputs.csv'):
        technical[row['project_id'], row['case_id'], row['criterion']].append(row)
    disclosure = defaultdict(list)
    for row in read_rows(out/'disclosure_items.csv'):
        disclosure[row['project_id']].append(dict(row,evidence=json.loads(row['evidence'] or '{}')))
    baseline_path = out/'disclosure_baseline.json'
    disclosure_baseline = json.loads(baseline_path.read_text(encoding='utf8'))['scores'] if baseline_path.is_file() else {}
    gate = defaultdict(list)
    for row in read_rows(out/'mcda_census_gate.csv'):
        gate[row['panel']].append(row)
    cohort = {r['canonical_project_id']: r for r in read_rows(out/'eligibility_cohorts.csv')}
    decisions, lineage, panels = [], [], {}
    for panel, n in sorted(prepared['panels'].items()):
        folder = out/panel
        criteria = read_rows(folder/'criteria.csv')
        matrix = read_rows(folder/'matrix.csv')
        ranked = read_rows(folder/'ranking.csv')
        result = results.get(panel, {'status': 'R_NOT_RUN', 'n': n})
        hashes = {f.name: filehash(f) for f in folder.glob('*.csv') if f.name in (
            'matrix.csv', 'criteria.csv', 'weights.csv', 'ranking.csv', 'weight_uncertainty.csv',
            'method_comparison.csv', 'evidence_cohort_sensitivity.csv', 'cohort_sensitivity.csv',
            'function_sensitivity.csv', 'rounding_uncertainty.csv')}
        panels[panel] = dict(status=result['status'], matrix_projects=n,
            ranked_projects=len({r['project_id'] for r in ranked}), criteria=criteria,
            weight_scenarios=sorted({r['scenario'] for r in read_rows(folder/'weights.csv')}),
            digests=hashes, study_population='EXPLORATORY_PANEL', formal_c1=False)
        seen = set()
        for row in gate[panel]:
            pid = row['canonical_project_id']
            seen.add(pid)
            decisions.append(dict(panel=panel, project_id=row['project_id'], canonical_project_id=pid,
                status='IN_PANEL_MATRIX' if row['included']=='1' else 'EXCLUDED_BY_CENSUS_SELECTION',
                formal_c1_status=cohort.get(pid, {}).get('formal_c1_status')))
        for pid in sorted(selected-seen):
            decisions.append(dict(panel=panel, project_id=pid, canonical_project_id=pid,
                status='NO_ELIGIBLE_INPUT_IN_PANEL_MATRIX',
                formal_c1_status=cohort.get(pid, {}).get('formal_c1_status')))
        for row in matrix:
            pid = row['project_id']
            canonical_id = row.get('canonical_project_id') or identity['mapping'].get(pid, pid)
            for criterion in criteria:
                code = criterion['code']
                if row.get(code) in ('', None):
                    continue
                inputs = technical.get((canonical_id, row.get('case_id'), code))
                mode = 'TECHNICAL_CASE_SOURCE' if inputs else ''
                if not inputs and code == 'T1' and (
                        'disclosure' in panel or criterion.get('definition_version')=='technical-disclosure-transparency-v1'):
                    inputs = disclosure.get(canonical_id, [])
                    mode = 'DISCLOSURE_ITEMS' if inputs else ''
                if not inputs and 'disclosure' in panel:
                    base = disclosure_baseline.get(canonical_id, {}).get(code)
                    if base and math.isclose(base['score'], float(row[code]), abs_tol=1e-12):
                        inputs, mode = [base], 'DISCLOSURE_BASELINE_SOURCE'
                if not inputs:
                    inputs, mode = candidate_trace_inputs(traced, pid, canonical_id, code, row)
                lineage.append(dict(panel=panel, project_id=pid, canonical_project_id=canonical_id,
                    criterion=code, score=row[code], scope=row.get('scope'), case_id=row.get('case_id'),
                    evidence_status=mode, evidence=canonical(public_export(evidence_reference(inputs)))))
    write_csv(out/'mcda_panel_decisions.csv', decisions, (
        'panel', 'project_id', 'canonical_project_id', 'status', 'formal_c1_status'))
    write_csv(out/'mcda_criterion_lineage.csv', lineage, (
        'panel', 'project_id', 'canonical_project_id', 'criterion', 'score', 'scope', 'case_id',
        'evidence_status', 'evidence'))
    return panels


def write_release_contract(root, out, run_id, mode, cutoff, version, configuration,
                           snapshots, receipt, prepared, results, selected, identity):
    names = summary_settings(root)[0]['output_files']
    project_summary = out/'project-summary'
    trace = read_rows(project_summary/names['provenance'])
    identity_roles(out, trace, identity)
    panels = panel_artifacts(out, prepared, results, selected, identity)
    sources = [dict(key=s['key'], sha256=s['sha256'], kind=s['kind'], **source_dates(s),
                    original_response_shas=sorted(a['sha256'] for a in s.get('original_responses', [])))
               for s in sorted(snapshots, key=lambda s: s['key'])]
    research = configuration['research']
    source_selection = out/'source_selection.csv'
    identity_sha = configuration.get('identity_links.json_sha256')
    hashes = {f.name: filehash(f) for f in (root/'config').glob('*.json')}
    lock = root/'results/phase22-2026-11-06/snapshot_lock.json'
    eligibility = out/'eligibility_audit.json'
    release = dict(version='census-release-v1', run_id=run_id, mode=mode, cutoff=cutoff, code=version,
        configuration_sha256=digest(configuration), configuration_files=hashes,
        claims_sha256=configuration['claims_sha256'], identity_links_sha256=identity_sha,
        phase22_lock_sha256=filehash(lock) if lock.is_file() else None,
        source_receipt_sha256=filehash(receipt) if receipt else None,
        source_selection_sha256=filehash(source_selection) if source_selection.is_file() else None,
        sources=sources, selected_census_ids=sorted(selected), census_filter=configuration['census_filter'],
        census_csv_sha256=filehash(project_summary/names['summary']),
        eligibility_audit_sha256=filehash(eligibility) if eligibility.is_file() else None,
        methods=['SAW', 'TOPSIS', 'PROMETHEE II'], monte_carlo=research['monte_carlo'],
        scenarios=research['scenarios'], ranking_panels=panels,
        research_roles=dict(ranking_criteria=[c['code'] for c in research['criteria']],
                            external_predictor_candidates=['deposit_type', 'mineralogy'],
                            interpretation='DESCRIPTIVE_ASSOCIATIONS_NOT_CAUSAL'))
    (out/'census_release.json').write_text(canonical(release)+'\n', encoding='utf8')
