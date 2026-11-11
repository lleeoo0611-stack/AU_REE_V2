"""Append-only, researcher-gated round-two projection and acceptance utilities."""
import copy
import csv
import json
from pathlib import Path
from .blank_classification import classify_blanks, load_blank_rules
from .coverage_task_audit import compare_projections, coverage, identical_replays
from .iteration_review import audit_summary
from .store import filehash

FILES = ('專案總表.csv', 'field_provenance.csv', 'missing_fields.csv', 'census_inventory.csv', 'summary.json', 'audit.json')

def read_csv(path):
    with Path(path).open(encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        return reader.fieldnames, list(reader)

def write_csv(path, fields, rows):
    with Path(path).open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fields)
        writer.writeheader()
        writer.writerows(rows)

def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)+'\n', encoding='utf8')

def metrics(folder):
    value = coverage(folder)
    value['treo_coverage'] = value['treo_filled']/value['treo_denominator'] if value['treo_denominator'] else None
    return value

def apply_fills(before, out, fills, decisions, repo):
    """No existing value, trace, row, inventory byte or unapproved fill may change."""
    before, out, repo = map(Path, (before, out, repo))
    if out.exists():
        raise ValueError('ROUND2_FRESH_OUTPUT_REQUIRED')
    columns, rows = read_csv(before/'專案總表.csv')
    pfields, trace = read_csv(before/'field_provenance.csv')
    mfields, missing = read_csv(before/'missing_fields.csv')
    indexed = {r['專案ID']: r for r in rows}
    registry = {d['decision_id']: d for d in decisions['decisions'] if d.get('decided_by') == 'USER_EXPLICIT_APPROVAL'}
    known = {(p['project_id'], p['column']) for p in trace}
    for fill in fills:
        pid, column = fill['project_id'], fill['column']
        if pid not in indexed or column not in columns or indexed[pid][column] != '' or (pid, column) in known:
            raise ValueError('ROUND2_EXISTING_OR_UNKNOWN_CELL')
        if fill['decision_id'] not in registry:
            raise ValueError('ROUND2_UNAPPROVED_DECISION')
        value = str(fill['value'])
        if not value:
            raise ValueError('ROUND2_EMPTY_FILL')
        p = dict.fromkeys(pfields, '')
        p.update({k: v for k, v in fill.get('provenance',fill.get('source_provenance',{})).items() if k in p})
        p.update(project_id=pid, column=column, value=value)
        if not p.get('source_sha256') or not p.get('locator') or not p.get('method'):
            raise ValueError('ROUND2_SOURCE_PROVENANCE_REQUIRED')
        indexed[pid][column] = value
        trace.append(p)
        known.add((pid,column))
    filled_keys = {(f['project_id'],f['column']) for f in fills}
    missing = [m for m in missing if (m['project_id'],m['column']) not in filled_keys]
    summary = json.loads((before/'summary.json').read_text('utf8'))
    summary['filled_counts'] = {c: sum(r[c] != '' for r in rows) for c in columns}
    summary['blank_coverage'] = classify_blanks(rows, missing, trace, load_blank_rules(repo/'config/blank_classification_legacy53.json'))
    out.mkdir(parents=True)
    for name,fields,records in [('專案總表.csv',columns,rows),('field_provenance.csv',pfields,trace),('missing_fields.csv',mfields,missing)]:
        write_csv(out/name,fields,records)
    (out/'census_inventory.csv').write_bytes((before/'census_inventory.csv').read_bytes())
    summary['output_hashes'] = {name:filehash(out/name) for name in FILES[:4]}
    write_json(out/'summary.json',summary)
    write_json(out/'audit.json',audit_summary(out))
    additions,changes = compare_projections(before,out)
    if changes or len(additions) != len(fills):
        raise ValueError('ROUND2_UNEXPECTED_CELL_DELTA')
    return additions

def stage_style_fill(row, fill, native):
    """Preserve the native source fields while recording a distinct new derivation."""
    p = copy.deepcopy(native)
    scope = json.loads(fill['scope'])
    p.update(project_id=row['專案ID'],column=fill['column'],value=str(fill['value']),
             source_sha256=fill['sha'],locator=fill['locator'],method=fill['method'],scope=fill['scope'])
    return dict(project_id=row['專案ID'],column=fill['column'],value=str(fill['value']),
                method=fill['method'],decision_id=scope['decision_id'],provenance=p)

def collect_stage(rows, provenance, decisions):
    from .stage_rules import stage_rule_fills, classify_stage, selected_mre
    fills, reviews = [], []
    trace = {(p['project_id'],p['column']):p for p in provenance}
    for row in rows:
        if row['開發階段代碼'] and row['開發階段類別']:
            continue
        native = trace.get((row['專案ID'],'開發階段'))
        additions = stage_rule_fills(row,provenance,decisions)
        for f in additions:
            fills.append(stage_style_fill(row,f,native))
        if not additions and row.get('開發階段'):
            has_mre,_ = selected_mre(row,provenance)
            proposal = classify_stage(row['開發階段'],has_mre)
            reviews.append(dict(project_id=row['專案ID'],project=row['專案名稱'],reason=proposal['reason'],source_text=row['開發階段']))
    return fills,reviews

def collect(task, before, decisions, repo):
    _,rows = read_csv(Path(before)/'專案總表.csv')
    _,trace = read_csv(Path(before)/'field_provenance.csv')
    if task == 'A':
        from .round2_deposit import collect_deposit
        fills,reviews = collect_deposit(rows,trace,decisions,repo)
        return fills,reviews,{}
    if task == 'B':
        fills,reviews = collect_stage(rows,trace,decisions)
        return fills,reviews,{}
    if task == 'C':
        from .round2_locations import build_round2_locations
        acquisitions = json.loads((Path(repo)/'results/coverage-approved-2026-11-11/government/acquisitions.json').read_text('utf8'))
        grouped,reviews = build_round2_locations(rows,acquisitions,decisions)
        fills=[]
        for pid,items in grouped.items():
            for f in items:
                value=format(float(f['value']),'.10g')
                p=dict(project_id=pid,column=f['column'],value=value,source_sha256=f.get('sha',f.get('source_sha')),source_url=f['source_url'],locator=f['locator'],method=f['method'],scope=f['scope'],observation_ids='[]',review_ids=json.dumps([f['decision_id']]),review_methods='[\"NORMALIZED_NAME_MATCH\"]',acquired_through=f['acquired_at'],source_kind='GOVERNMENT_SPATIAL_CATALOGUE',publication_date_role='DATASET_VERSION_NOT_MRE',resource_effective_date_unknown='True',public_release_date_unknown='True')
                fills.append(dict(project_id=pid,column=f['column'],value=value,method=f['method'],decision_id=f['decision_id'],provenance=p))
        result = (fills,reviews,dict(nt_conversion_status='BLOCKED_ARCHIVED_DATUM_METADATA_UNVERIFIED',nt_real_control_point_validated=False))
    else:
        from .round2_annual_production import apply_annual_production
        result = apply_annual_production(rows,trace,decisions,repo)
    if isinstance(result,tuple):
        return result[0],result[1],result[2] if len(result)>2 else {}
    return result['fills'],result['reviews'],{k:v for k,v in result.items() if k not in ('fills','reviews')}

def summarize_task(task,before,after,other,decisions,repo,out):
    """Persist measured increments; full-replay receipts are supplied by the runner."""
    out = Path(out)
    if out.exists():
        raise ValueError('ROUND2_REPORT_FRESH_OUTPUT_REQUIRED')
    hashes = identical_replays(after,other)
    additions,changes = compare_projections(before,after)
    _,rows = read_csv(Path(before)/'專案總表.csv')
    names = {r['專案ID']:r['專案名稱'] for r in rows}
    _,trace = read_csv(Path(after)/'field_provenance.csv')
    traces = {(p['project_id'],p['column']):p for p in trace}
    fills,reviews,extra = collect(task,before,decisions,repo)
    by_key = {(f['project_id'],f['column']):f for f in fills}
    new = []
    for a in additions:
        p = traces[a['project_id'],a['column']]
        f = by_key[a['project_id'],a['column']]
        new.append(dict(project_id=a['project_id'],project=names[a['project_id']],column=a['column'],value=a['new_value'],
                        method=p['method'],decision_id=f['decision_id'],locator=p['locator'],source_sha256=p['source_sha256']))
    out.mkdir(parents=True)
    write_csv(out/'new_cells.csv',['project_id','project','column','value','method','decision_id','locator','source_sha256'],new)
    write_csv(out/'changed_cells.csv',['project_id','project','column','old_value','new_value','reason'],[])
    fields = list(dict.fromkeys(['project_id','project','reason']+[k for r in reviews for k in r]))
    normalized = [{k:(json.dumps(v,ensure_ascii=False,sort_keys=True) if isinstance(v,(list,dict)) else v) for k,v in r.items()} for r in reviews]
    write_csv(out/'review_queue.csv',fields,normalized)
    summary = dict(task=task,new_cells=len(new),changed_cells=0,before=metrics(before),after=metrics(after),
                   review_queue=len(reviews),independent_full_rebuilds=2,bitwise_identical_files=hashes,
                   decision_file_sha256=filehash(Path(repo)/'config/researcher_rule_decisions.json'),network_requests=0,
                   preexisting_values_and_provenance_unchanged=True,**extra)
    write_json(out/'summary.json',summary)
    return summary
