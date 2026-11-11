"""Deterministic, source-grounded presentation notes; the canonical core is immutable."""
import argparse
import copy
import csv
import hashlib
import io
import json
import shutil
from pathlib import Path

from .store import filehash, digest

VERSION = 'census-project-summary-v4-total-notes'
OLD = '元素數據一致性檢查'
NEW = '總說明'
ARCHIVE = 'retired_consistency_trace.json'
METHOD = 'DETERMINISTIC_SOURCE_GROUNDED_PRESENTATION_NOTES_V1'


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def _read(path):
    with Path(path).open(encoding='utf-8-sig', newline='') as handle:
        reader = csv.DictReader(handle)
        return reader.fieldnames, list(reader)


def _write(path, fields, rows):
    with Path(path).open('w', encoding='utf-8-sig', newline='') as handle:
        writer = csv.DictWriter(handle, fields)
        writer.writeheader()
        writer.writerows(rows)


def _csv_hash(fields, rows):
    stream = io.StringIO(newline='')
    writer = csv.DictWriter(stream, fields)
    writer.writeheader()
    writer.writerows(rows)
    return hashlib.sha256(stream.getvalue().encode('utf-8-sig')).hexdigest()


def _coverage(filled, rows, columns):
    total = rows * columns
    return dict(filled_cells=filled, total_cells=total, columns=columns,
                raw_coverage=filled / total if total else None)


def build_note(row, trace):
    """Compose only applicable caveats, binding every fragment to exact core records."""
    pid = row['專案ID']
    parts, records = [], []

    def add(text, columns):
        parts.append(text)
        for column in columns:
            record = trace.get((pid, column))
            if record is not None and record not in records:
                records.append(record)

    if row[OLD]:
        add(row[OLD], [OLD])
    stage = trace.get((pid, '開發階段'))
    if stage and row['開發階段']:
        stage_columns = ['開發階段', '開發階段代碼', '開發階段類別']
        add('開發階段依來源原文及其揭露日期：' + row['開發階段'] + '；分類僅對應該來源時點，不代表目前營運、法律或許可狀態。', stage_columns)
    location = trace.get((pid, '緯度'), {})
    if location.get('source_kind') == 'GOVERNMENT_SPATIAL_CATALOGUE':
        scope = json.loads(location.get('scope') or '{}')
        text = '政府座標為來源資料集代表點（' + str(scope.get('dataset', '')) + '），不是礦權或資源邊界；資料集日期不是資源估計有效日。'
        if scope.get('distance_check') == 'NO_VERIFIED_DISTANCE_COMPARATOR':
            text += '缺乏經核實的距離比較基準（NO_VERIFIED_DISTANCE_COMPARATOR），不宣稱已通過距離交叉驗證。'
        add(text, ['緯度', '經度'])
    if not parts:
        return '', None
    value = '；'.join(parts)
    record = {key: '' for key in next(iter(trace.values()))}
    record.update(project_id=pid, column=NEW, value=value, method=METHOD,
                  source_sha256=';'.join(sorted({r.get('source_sha256', '') for r in records if r.get('source_sha256')})),
                  source_url=';'.join(sorted({r.get('source_url', '') for r in records if r.get('source_url')})),
                  locator='Source records in scope; retired consistency records in ' + ARCHIVE,
                  scope=_json(dict(note_rule_version=1, source_records=records,
                                   limitation='PRESENTATION_TEXT_NOT_NEW_SCIENTIFIC_EVIDENCE')))
    return value, record


def convert_summary(source, destination):
    from .iteration_review import audit_summary
    from .blank_classification import classify_blanks, load_blank_rules
    source, destination = Path(source), Path(destination)
    detected=json.loads((source/'summary.json').read_text('utf8'))
    if detected.get('version')=='census-project-summary-round3-v1':
        from .round3_schema import present, audit
        present(source,destination,Path(__file__).resolve().parents[2])
        return audit(destination)
    if source.resolve() == destination.resolve() or source.resolve() in destination.resolve().parents:
        raise ValueError('PRESENTATION_REQUIRES_SEPARATE_OUTPUT')
    if destination.exists():
        raise ValueError('PRESENTATION_REQUIRES_FRESH_OUTPUT')
    audited = audit_summary(source)
    summary = json.loads((source / 'summary.json').read_text('utf8'))
    if summary.get('version') != 'census-project-summary-v3-asx-identity':
        raise ValueError('PRESENTATION_REQUIRES_CANONICAL_53_COLUMN_CORE')
    columns, rows = _read(source / '專案總表.csv')
    pfields, provenance = _read(source / 'field_provenance.csv')
    mfields, missing = _read(source / 'missing_fields.csv')
    trace = {(r['project_id'], r['column']): r for r in provenance}
    for name, fields, records in [('專案總表.csv', columns, rows), ('field_provenance.csv', pfields, provenance), ('missing_fields.csv', mfields, missing)]:
        if _csv_hash(fields, records) != summary['output_hashes'][name]:
            raise ValueError('PRESENTATION_UNSUPPORTED_CORE_SERIALIZATION')
    index = columns.index(OLD)
    presented = [NEW if c == OLD else c for c in columns]
    archive = dict(version='retired-consistency-trace-v1',
                   core_summary=copy.deepcopy(summary),
                   serialization=dict(provenance_fields=pfields, missing_fields=mfields,
                       provenance_order=[[r['project_id'], r['column']] for r in provenance],
                       missing_order=[[r['project_id'], r['column']] for r in missing],
                       blank_annotations=[[r['project_id'], r['column'], r.get('blank_class', ''), r.get('blank_rule_id', '')] for r in missing]),
                   core_provenance_semantic_sha256=digest(sorted(provenance, key=lambda r: (r['project_id'], r['column']))),
                   values={r['專案ID']: r[OLD] for r in rows},
                   provenance=[r for r in provenance if r['column'] == OLD],
                   missing=[r for r in missing if r['column'] == OLD])
    new_provenance = [r for r in provenance if r['column'] != OLD]
    new_missing = [r for r in missing if r['column'] != OLD]
    output_rows = []
    for row in rows:
        note, record = build_note(row, trace)
        output_rows.append({c: note if c == NEW else row[c] for c in presented})
        if record:
            new_provenance.append(record)
        else:
            gap = {c: '' for c in mfields}
            gap.update(project_id=row['專案ID'], column=NEW, reason='NO_APPLICABLE_SOURCE_GROUNDED_PRESENTATION_NOTE')
            new_missing.append(gap)
    order = {c: i for i, c in enumerate(presented)}
    row_order = {r['專案ID']: i for i, r in enumerate(rows)}
    for records in (new_provenance, new_missing):
        records.sort(key=lambda r: (row_order[r['project_id']], order[r['column']]))
    rules = load_blank_rules(Path(__file__).resolve().parents[2] / 'config/blank_classification_legacy53.json')
    summary['blank_coverage'] = classify_blanks(output_rows, new_missing, new_provenance, rules)
    old_count = sum(bool(r[OLD]) for r in rows)
    note_count = sum(bool(r[NEW]) for r in output_rows)
    summary.update(version=VERSION, columns_sha256=digest(presented),
        filled_counts={c: sum(r[c] != '' for r in output_rows) for c in presented},
        presentation_mapping=dict(version=1, core_version=archive['core_summary']['version'],
            core_columns=columns, presentation_columns=presented, replaced_index=index,
            retired_column=OLD, presentation_column=NEW, archive=ARCHIVE,
            core_output_hashes=archive['core_summary']['output_hashes']),
        coverage_metrics=dict(
            original_53_column_evidence=_coverage(audited['filled_cells'], len(rows), 53),
            remaining_52_columns=_coverage(audited['filled_cells'] - old_count, len(rows), 52),
            final_53_column_presentation=_coverage(audited['filled_cells'] - old_count + note_count, len(rows), 53),
            retired_consistency_cells=old_count, total_note_cells=note_count,
            note_cells_are_scientific_evidence_gain=False))
    destination.mkdir(parents=True, exist_ok=False)
    _write(destination / '專案總表.csv', presented, output_rows)
    _write(destination / 'field_provenance.csv', pfields, new_provenance)
    _write(destination / 'missing_fields.csv', mfields, new_missing)
    (destination / ARCHIVE).write_text(_json(archive) + '\n', encoding='utf8')
    names = ['專案總表.csv', 'field_provenance.csv', 'missing_fields.csv', ARCHIVE]
    if (source / 'census_inventory.csv').exists():
        shutil.copyfile(source / 'census_inventory.csv', destination / 'census_inventory.csv')
        names.append('census_inventory.csv')
    summary['output_hashes'] = {name: filehash(destination / name) for name in names}
    (destination / 'summary.json').write_text(_json(summary) + '\n', encoding='utf8')
    result = audit_summary(destination)
    (destination / 'audit.json').write_text(_json(result) + '\n', encoding='utf8')
    return result


def validate_presentation(folder, summary, rows, provenance, canonical_columns):
    """Reconstruct core coverage and regenerate all note text and source bindings."""
    mapping = summary.get('presentation_mapping', {})
    core_columns = canonical_columns + ['ASX代碼']
    expected = [NEW if c == OLD else c for c in core_columns]
    if (mapping.get('core_columns') != core_columns or mapping.get('presentation_columns') != expected
        or mapping.get('replaced_index') != core_columns.index(OLD)
        or mapping.get('retired_column') != OLD or mapping.get('presentation_column') != NEW
        or mapping.get('archive') != ARCHIVE or mapping.get('version') != 1):
        raise ValueError('ITERATION_PRESENTATION_MAPPING_MISMATCH')
    archive = json.loads((Path(folder) / ARCHIVE).read_text('utf8'))
    if (archive.get('version') != 'retired-consistency-trace-v1'
        or mapping.get('core_version') != archive['core_summary']['version']
        or mapping.get('core_output_hashes') != archive['core_summary']['output_hashes']
        or set(archive['values']) != {r['專案ID'] for r in rows}):
        raise ValueError('ITERATION_PRESENTATION_ARCHIVE_MISMATCH')
    if summary.get('columns_sha256') != digest(expected):
        raise ValueError('ITERATION_PRESENTATION_COLUMNS_HASH_MISMATCH')
    original = [{c: archive['values'][r['專案ID']] if c == OLD else r[c] for c in core_columns} for r in rows]
    if _csv_hash(core_columns, original) != mapping['core_output_hashes']['專案總表.csv']:
        raise ValueError('ITERATION_PRESENTATION_CORE_CONTENT_MISMATCH')
    restored = [r for r in provenance if r['column'] != NEW] + archive['provenance']
    if digest(sorted(restored, key=lambda r: (r['project_id'], r['column']))) != archive.get('core_provenance_semantic_sha256'):
        raise ValueError('ITERATION_PRESENTATION_CORE_PROVENANCE_MISMATCH')
    trace = {(r['project_id'], r['column']): r for r in restored}
    filled = {(r['專案ID'], c): v for r in original for c, v in r.items() if v != ''}
    if len(trace) != len(restored) or set(trace) != set(filled) or any(trace[k]['value'] != v for k, v in filled.items()):
        raise ValueError('ITERATION_PRESENTATION_ARCHIVE_PROVENANCE_MISMATCH')
    gaps = {(r['project_id'], r['column']) for r in archive['missing']}
    if (len(gaps) != len(archive['missing']) or gaps != {(r['專案ID'], OLD) for r in original if not r[OLD]}):
        raise ValueError('ITERATION_PRESENTATION_ARCHIVE_DIAGNOSTIC_MISMATCH')
    serialization = archive['serialization']
    if set(map(tuple, serialization['provenance_order'])) != set(trace) or len(serialization['provenance_order']) != len(trace):
        raise ValueError('ITERATION_PRESENTATION_CORE_ORDER_MISMATCH')
    if _csv_hash(serialization['provenance_fields'], [trace[tuple(k)] for k in serialization['provenance_order']]) != mapping['core_output_hashes']['field_provenance.csv']:
        raise ValueError('ITERATION_PRESENTATION_CORE_TRACE_HASH_MISMATCH')
    _, current_missing = _read(Path(folder) / 'missing_fields.csv')
    restored_missing = [dict(r) for r in current_missing if r['column'] != NEW] + copy.deepcopy(archive['missing'])
    gap_trace = {(r['project_id'], r['column']): r for r in restored_missing}
    if len(gap_trace) != len(restored_missing) or set(map(tuple, serialization['missing_order'])) != set(gap_trace) or len(serialization['missing_order']) != len(gap_trace):
        raise ValueError('ITERATION_PRESENTATION_CORE_GAP_ORDER_MISMATCH')
    for pid, column, label, rule in serialization['blank_annotations']:
        for field, value in [('blank_class', label), ('blank_rule_id', rule)]:
            if field in serialization['missing_fields']:
                gap_trace[(pid, column)][field] = value
    if _csv_hash(serialization['missing_fields'], [gap_trace[tuple(k)] for k in serialization['missing_order']]) != mapping['core_output_hashes']['missing_fields.csv']:
        raise ValueError('ITERATION_PRESENTATION_CORE_GAP_HASH_MISMATCH')
    actual_notes = {r['project_id']: r for r in provenance if r['column'] == NEW}
    for row, output in zip(original, rows):
        value, record = build_note(row, trace)
        if output[NEW] != value or actual_notes.get(row['專案ID']) != record:
            raise ValueError('ITERATION_PRESENTATION_NOTE_MISMATCH')
    old_count = sum(bool(r[OLD]) for r in original)
    notes = len(actual_notes)
    metrics = dict(original_53_column_evidence=_coverage(len(filled), len(rows), 53),
        remaining_52_columns=_coverage(len(filled) - old_count, len(rows), 52),
        final_53_column_presentation=_coverage(len(filled) - old_count + notes, len(rows), 53),
        retired_consistency_cells=old_count, total_note_cells=notes, note_cells_are_scientific_evidence_gain=False)
    if summary.get('coverage_metrics') != metrics:
        raise ValueError('ITERATION_PRESENTATION_COVERAGE_MISMATCH')
    if archive['core_summary'].get('filled_counts') != {c: sum(r[c] != '' for r in original) for c in core_columns}:
        raise ValueError('ITERATION_PRESENTATION_CORE_COUNTS_MISMATCH')
    return metrics


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    print(_json(convert_summary(args.source, args.output)))


if __name__ == '__main__':
    main()
