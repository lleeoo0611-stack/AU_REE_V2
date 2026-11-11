"""Audit a current summary without equating download counts with scientific coverage."""
import csv
import json
from pathlib import Path
from .store import filehash
from .convergence import POLICY, blocked_backlog, consecutive_rule

# Frozen 52-column contract: 10 resource/production and 15 oxide columns.
SCIENCE_INDEXES = tuple(range(15,25)) + tuple(range(37,52))

def audit_summary(folder):
    folder=Path(folder)
    def read(name):
        with (folder/name).open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
    rows=read('專案總表.csv')
    columns=json.loads((Path(__file__).resolve().parents[2]/'config/project_summary_columns.json').read_text('utf8'))
    summary=json.loads((folder/'summary.json').read_text('utf8'))
    from .presentation_notes import VERSION, OLD, NEW, validate_presentation
    canonical_columns = list(columns)
    presentation = summary.get('version') == VERSION
    if summary.get('version')=='census-project-summary-v3-asx-identity' or presentation:
        if summary.get('base_contract_columns')!=52 or not summary.get('identity_ledger_sha256'):
            raise ValueError('ITERATION_IDENTITY_CONTRACT_MISSING')
        columns=columns+['ASX代碼']
    if presentation:
        columns=[NEW if c == OLD else c for c in columns]
    if not rows or list(rows[0])!=columns:raise ValueError('ITERATION_SUMMARY_CONTRACT_MISMATCH')
    keys=[r['專案ID'] for r in rows]
    if len(set(keys))!=len(keys):raise ValueError('ITERATION_DUPLICATE_PROJECT')
    provenance=read('field_provenance.csv'); missing=read('missing_fields.csv')
    trace={(r['project_id'],r['column']):r for r in provenance}
    gaps={(r['project_id'],r['column']):r for r in missing}
    if len(trace)!=len(provenance) or len(gaps)!=len(missing):raise ValueError('ITERATION_DUPLICATE_CELL_RECORD')
    filled={(r['專案ID'],c):v for r in rows for c,v in r.items() if v!=''}
    blanks={(r['專案ID'],c) for r in rows for c,v in r.items() if v==''}
    if set(trace)!=set(filled) or any(trace[k]['value']!=v for k,v in filled.items()):raise ValueError('ITERATION_PROVENANCE_CELL_MISMATCH')
    if set(gaps)!=blanks:raise ValueError('ITERATION_MISSING_DIAGNOSTIC_MISMATCH')
    for name,sha in summary['output_hashes'].items():
        if filehash(folder/name)!=sha:raise ValueError('ITERATION_OUTPUT_HASH_MISMATCH')
    scientific=[columns[i] for i in SCIENCE_INDEXES]
    result = dict(projects=len(rows),columns=len(columns),filled_cells=len(filled),total_cells=len(rows)*len(columns),
                remaining_blank_cells=len(blanks),scientific_columns=scientific,
                scientific_filled_cells=sum(r[c]!='' for r in rows for c in scientific),
                scientific_total_cells=len(rows)*len(scientific),output_hashes=summary['output_hashes'],
                provenance_complete=True,missing_diagnostics_complete=True)
    if summary.get('blank_coverage') is not None:
        import copy
        from .blank_classification import load_blank_rules,classify_blanks
        rules=load_blank_rules(Path(__file__).resolve().parents[2]/'config/blank_classification.json')
        checked=copy.deepcopy(missing)
        coverage=classify_blanks(rows,checked,provenance,rules)
        if coverage!=summary['blank_coverage'] or any(
            (a.get('blank_class'),a.get('blank_rule_id'))!=(b['blank_class'],b['blank_rule_id']) for a,b in zip(missing,checked)):
            raise ValueError('ITERATION_BLANK_CLASSIFICATION_MISMATCH')
        result['blank_coverage']=coverage
    if presentation:
        result['coverage_metrics'] = validate_presentation(folder, summary, rows, provenance, canonical_columns)
    return result


def review_coverage_cycle(before, after, manifest):
    """Compare validated 53-column outputs; never treat an incomplete pass as convergence.

    The caller performs acquisition, source review and tests. The manifest records
    those results; this function checks integrity and counts only exported cells.
    It does not claim to independently validate PDF interpretation or run tests.
    """
    if isinstance(manifest, (str, Path)):
        manifest = json.loads(Path(manifest).read_text(encoding='utf-8-sig'))
    previous = audit_summary(before)
    current = audit_summary(after)
    if 'coverage_metrics' in previous or 'coverage_metrics' in current:
        raise ValueError('CYCLE_REQUIRES_CANONICAL_EVIDENCE_NOT_PRESENTATION_NOTES')
    if previous['columns'] != 53 or current['columns'] != 53:
        raise ValueError('CYCLE_REQUIRES_53_COLUMNS')

    def rows(folder):
        with (Path(folder) / '專案總表.csv').open(encoding='utf-8-sig', newline='') as handle:
            reader = csv.DictReader(handle)
            data = list(reader)
            return reader.fieldnames, {row['專案ID']: row for row in data}

    columns, old = rows(before)
    new_columns, new = rows(after)
    if columns != new_columns:
        raise ValueError('CYCLE_COLUMN_CONTRACT_CHANGED')
    removed = sorted(set(old) - set(new))
    removals = manifest.get('removed_projects', [])
    explanations = {entry.get('project_id'): entry for entry in removals}
    if len(explanations) != len(removals) or set(explanations) != set(removed):
        raise ValueError('CYCLE_UNEXPLAINED_PROJECT_REMOVAL')
    for entry in removals:
        if not str(entry.get('reason', '')).strip():
            raise ValueError('CYCLE_UNEXPLAINED_PROJECT_REMOVAL')
        if entry.get('merged_into') is not None and entry['merged_into'] not in new:
            raise ValueError('CYCLE_INVALID_MERGE_TARGET')
    scientific = set(current['scientific_columns'])
    counts = dict(newly_filled_cells=0, scientific_newly_filled_cells=0,
                  updated_value_cells=0, withdrawn_cells=0,
                  scientific_withdrawn_cells=0, numeric_format_only_cells=0)
    import math
    for pid in sorted(set(old) & set(new)):
        for column in columns:
            a, b = old[pid][column], new[pid][column]
            if a == b:
                continue
            if not a and b:
                counts['newly_filled_cells'] += 1
                counts['scientific_newly_filled_cells'] += column in scientific
            elif a and not b:
                counts['withdrawn_cells'] += 1
                counts['scientific_withdrawn_cells'] += column in scientific
            else:
                try:
                    equal = math.isclose(float(a), float(b), rel_tol=1e-12, abs_tol=1e-12)
                except ValueError:
                    equal = False
                counts['numeric_format_only_cells' if equal else 'updated_value_cells'] += 1
    added_ids = sorted(set(new) - set(old))
    added_filled = sum(value != '' for pid in added_ids for value in new[pid].values())
    added_scientific = sum(new[pid][column] != '' for pid in added_ids for column in scientific)
    removed_filled = sum(value != '' for pid in removed for value in old[pid].values())
    gain = counts['newly_filled_cells'] + added_filled
    incomplete = []
    if counts['withdrawn_cells']:
        incomplete.append('validation:cell_withdrawals_require_separate_review')
    for track in ('candidates', 'numeric'):
        item = manifest.get('tracks', {}).get(track, {})
        records = item.get('records', [])
        complete_records = (isinstance(records, list) and bool(records) and all(
            isinstance(record, dict) and str(record.get('query', '')).strip()
            and str(record.get('disposition', '')).strip() for record in records))
        if item.get('completed') is not True or not complete_records:
            incomplete.append('track:' + track)
    for check in ('sources', 'tests', 'reproducibility'):
        item = manifest.get('validation', {}).get(check, {})
        if item.get('passed') is not True or not str(item.get('evidence', '')).strip():
            incomplete.append('validation:' + check)
    # Historical policies stay replayable. The new below-three policy keeps
    # the same full-scope and acquisition checks as the default zero policy.
    policy = manifest.get('stopping_policy', 'ZERO_NEW_VERIFIED_CELLS')
    if policy not in ('ZERO_NEW_VERIFIED_CELLS', 'LEGACY_BELOW_THREE', 'BELOW_THREE_COMPLETE_ROUND',
                       'FULL_SCOPE_ZERO_NEW_VERIFIED_CELLS', POLICY):
        raise ValueError('CYCLE_UNKNOWN_STOPPING_POLICY')
    if policy in ('ZERO_NEW_VERIFIED_CELLS', 'BELOW_THREE_COMPLETE_ROUND', 'FULL_SCOPE_ZERO_NEW_VERIFIED_CELLS', POLICY):
        scope = manifest.get('search_scope', {})
        if scope.get('columns') != columns or scope.get('all_blank_fields_reviewed') is not True:
            incomplete.append('search_scope:all_53_columns')
        if policy != POLICY and manifest.get('unresolved_acquisition_actions') != []:
            incomplete.append('acquisition:unresolved_or_undeclared')
    blocked=[]
    if policy == POLICY:
        blocked, problems=blocked_backlog(manifest,columns,new)
        incomplete.extend(problems)
    if policy in ('FULL_SCOPE_ZERO_NEW_VERIFIED_CELLS', POLICY):
        from .full_scope_review import review_full_scope
        incomplete.extend(review_full_scope(old, new, columns, manifest,
                          blocked_action_ids=[b['action_id'] for b in blocked]))
    eligible = not incomplete
    zero_policy = policy in ('ZERO_NEW_VERIFIED_CELLS', 'FULL_SCOPE_ZERO_NEW_VERIFIED_CELLS', POLICY)
    stopped = eligible and (gain == 0 if zero_policy else gain < 3)
    convergence={}
    if policy == POLICY:
        convergence,problems=consecutive_rule(manifest,gain,eligible,filehash(Path(before)/'專案總表.csv'))
        incomplete.extend(problems);eligible=not incomplete
        stopped=eligible and convergence['consecutive_zero_rounds']>=convergence['required_zero_rounds']
    decision='INCOMPLETE' if not eligible else ('STOP_WITH_BLOCKED_BACKLOG' if blocked else 'STOP') if stopped else 'CONTINUE'
    counts['net_filled_cell_increase'] = counts['newly_filled_cells'] - counts['withdrawn_cells']
    result = dict(
        version='coverage-cycle-review-v2',
        cycle_id=manifest.get('cycle_id', ''),
        current=current,
        existing_projects=counts,
        added_projects=dict(project_ids=added_ids, count=len(added_ids), filled_cells=added_filled,
                            scientific_filled_cells=added_scientific,
                            identity_and_other_metadata_cells=added_filled-added_scientific),
        removed_projects=dict(project_ids=removed, filled_cells=removed_filled, explanations=removals),
        total_filled_cell_delta=current['filled_cells']-previous['filled_cells'],
        stopping_rule=dict(policy=policy, threshold=0 if zero_policy else 3,
                           operator='==' if zero_policy else '<', newly_filled_cells=gain,
                           scientific_newly_filled_cells=counts['scientific_newly_filled_cells']+added_scientific,
                           counting_scope='EXISTING_BLANK_FILLS_PLUS_ALL_NEW_PROJECT_FILLED_CELLS_INCLUDING_IDENTITY_METADATA',
                           eligible=eligible, stop=stopped, incomplete=incomplete,
                           decision=decision, **convergence),
        baseline_csv_sha256=filehash(Path(before)/'專案總表.csv'),
        current_csv_sha256=filehash(Path(after)/'專案總表.csv'),
        review_manifest=manifest,
        limitations='Search/source/test completion is declared by the reviewer manifest; table integrity is independently checked. STOP means the selected threshold was met in the completed documented search round, not national completeness or proof of absence.',
    )
    if policy == POLICY:
        result.update(round_number=manifest['round_number'],blocked_acquisitions=blocked,
                      limitations=result['limitations']+' STOP_WITH_BLOCKED_BACKLOG is operational convergence, NOT source exhaustion. Blocked originals remain unavailable and require the documented manual route.')
    return result
