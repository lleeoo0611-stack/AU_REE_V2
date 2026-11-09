"""Source-bound ASX metadata and explicit, reversible summary identity merges.

The frozen 52-column research projection remains reproducible. This projection
appends one ASX column; code evidence never creates resource observations.
"""
import csv
import json
import re
from datetime import date, datetime
from pathlib import Path
from .store import filehash, digest

ASX_COLUMN = 'ASX代碼'


def normalized_name(value):
    value = re.sub(r'\bmt\.?\b', 'mount', value.casefold())
    value = re.sub(r'\b(rare\s+earths?|ree|project)\b', ' ', value.casefold())
    return re.sub(r'\W+', '', value)


def merge_eligible(left, right, aliases=()):
    """Same verified, nonempty ASX code AND same name/explicit alias pair."""
    code = left.get(ASX_COLUMN, '')
    if not re.fullmatch(r'[A-Z][A-Z0-9]{1,4}', code) or code != right.get(ASX_COLUMN):
        return False
    a, b = normalized_name(left['專案名稱']), normalized_name(right['專案名稱'])
    if not a or not b:
        return False
    return a == b or any({a, b} <= {normalized_name(n) for n in pair} for pair in aliases)


def validate_identity(ledger, assets, rows, cutoff):
    import pymupdf
    cfg = json.loads(Path(ledger).read_text('utf8'))
    if cfg.get('version') != 'reviewed-project-identity-v1' or cfg.get('cutoff') != cutoff:
        raise ValueError('IDENTITY_VERSION_OR_CUTOFF')
    date.fromisoformat(cfg['acquired_through'])
    ids = {r['專案ID'] for r in rows}
    project_rows = {r['專案ID']:r for r in rows}
    sources = {}
    for key, source in cfg['sources'].items():
        root = Path(assets[source['asset_set']]).resolve()
        path = (root / source['path']).resolve()
        if root not in path.parents or filehash(path) != source['sha256']:
            raise ValueError('IDENTITY_SOURCE_HASH_OR_PATH')
        if (root / 'downloads.json').exists():
            receipts = json.loads((root / 'downloads.json').read_text('utf8'))
            matches = [r for r in receipts if r['url'] == source['url'] and r.get('document_sha256') == source['sha256'] and r['status'] == 'PDF_ACQUIRED']
        else:
            receipts = json.loads((root / 'data/manifest.json').read_text('utf8'))['snapshots']
            matches = [r for r in receipts if r['url'] == source['url'] and r['sha256'] == source['sha256'] and r['kind'] == 'pdf']
        if not matches:
            raise ValueError('IDENTITY_URL_HASH_RECEIPT')
        sources[key] = (source, path)

    def proof(doc, evidence):
        pn = evidence['page']
        if not isinstance(pn, int) or not 1 <= pn <= len(doc):
            raise ValueError('IDENTITY_PAGE')
        text = ' '.join(doc[pn-1].get_text(sort=True).split()).casefold()
        if not evidence.get('markers') or any(' '.join(m.split()).casefold() not in text for m in evidence['markers']):
            raise ValueError('IDENTITY_MARKER')
        return text

    entries = {}
    for entry in cfg['codes']:
        pid = entry['project_id']
        if pid not in ids or pid in entries:
            raise ValueError('IDENTITY_PROJECT_UNKNOWN_OR_DUPLICATE')
        code = entry['code']
        if not re.fullmatch(r'[A-Z][A-Z0-9]{1,4}', code) or not entry.get('issuer_name'):
            raise ValueError('IDENTITY_CODE_OR_ISSUER')
        day = entry['evidence_date']; date.fromisoformat(day)
        if day > cutoff:
            raise ValueError('IDENTITY_AFTER_CUTOFF')
        source, path = sources[entry['source_key']]
        with pymupdf.open(path) as doc:
            content = proof(doc, entry['date_evidence'])
            labels = [datetime.strptime(day, '%Y-%m-%d').strftime(fmt).lstrip('0').casefold() for fmt in ('%d %B %Y','%d %b %Y')]
            content = re.sub(r'\b(\d{1,2})(?:st|nd|rd|th)\b', r'\1', content)
            if not any(label in content for label in labels):
                raise ValueError('IDENTITY_DATE_PROOF')
            content = proof(doc, entry['project_evidence'])
            if not entry['project_marker'] or entry['project_marker'].casefold() not in content:
                raise ValueError('IDENTITY_PROJECT_PROOF')
            marker = normalized_name(entry['project_marker'])
            if len(marker)<4 or marker not in normalized_name(project_rows[pid]['專案名稱']):
                raise ValueError('IDENTITY_PROJECT_NAME_BINDING')
            content = proof(doc, entry['issuer_evidence'])
            if entry['issuer_name'].casefold() not in content:
                raise ValueError('IDENTITY_ISSUER_PROOF')
            content = proof(doc, entry['code_evidence'])
            label = entry['code_label']
            if (not re.search(r'ASX|\bcode\b',label,re.I) or
                not re.search(r'(?<![A-Z0-9])'+re.escape(code)+r'(?![A-Z0-9])', label) or ' '.join(label.split()).casefold() not in content):
                raise ValueError('IDENTITY_CODE_PROOF')
        entries[pid] = dict(entry, source=source)
    merges = []
    row_map = {r['專案ID']:dict(r, **{ASX_COLUMN:entries.get(r['專案ID'],{}).get('code','')}) for r in rows}
    used = set()
    for merge in cfg.get('merges', []):
        target, other = merge['target_id'], merge['absorbed_id']
        if target == other or target not in row_map or other not in row_map or {target, other} & used:
            raise ValueError('IDENTITY_MERGE_DUPLICATE_OR_UNKNOWN')
        if not merge_eligible(row_map[target], row_map[other], merge.get('alias_pairs', [])):
            raise ValueError('IDENTITY_MERGE_REQUIRES_SAME_CODE_AND_NAME')
        if merge['source_key'] not in sources:
            raise ValueError('IDENTITY_MERGE_SOURCE')
        source, path = sources[merge['source_key']]
        with pymupdf.open(path) as doc:
            content = proof(doc, merge['same_project_evidence'])
            # Short and long aliases must both occur in the same source proof.
            names = merge.get('alias_pairs', [])
            if names and any(any(n.casefold() not in content for n in pair) for pair in names):
                raise ValueError('IDENTITY_MERGE_ALIAS_PROOF')
        used.update((target, other)); merges.append(dict(merge, source=source))
    return dict(entries=entries, merges=merges, ledger=cfg, ledger_sha256=filehash(ledger))


def extend_summary(baseline, out, ledger, assets):
    from .iteration_review import audit_summary
    audit_summary(baseline)
    baseline, out = Path(baseline), Path(out)
    if baseline.resolve() == out.resolve():
        raise ValueError('IDENTITY_OUTPUT_MUST_BE_SEPARATE')
    def read(name):
        with (baseline/name).open(encoding='utf-8-sig', newline='') as f:
            reader = csv.DictReader(f); return list(reader), reader.fieldnames
    rows, columns = read('專案總表.csv')
    if ASX_COLUMN in columns:
        raise ValueError('IDENTITY_INPUT_ALREADY_EXTENDED')
    trace, trace_fields = read('field_provenance.csv')
    missing, missing_fields = read('missing_fields.csv')
    inventory, inventory_fields = read('census_inventory.csv')
    summary = json.loads((baseline/'summary.json').read_text('utf8'))
    reviewed = validate_identity(ledger, assets, rows, summary['cutoff'])
    for row in rows:
        pid = row['專案ID']; entry = reviewed['entries'].get(pid)
        row[ASX_COLUMN] = entry['code'] if entry else ''
        if not entry:
            missing.append(dict(project_id=pid, column=ASX_COLUMN, reason='NO_SOURCE_BOUND_PROJECT_ISSUER_ASX_CODE;PRIVATE_OR_HISTORICAL_OWNER_NOT_ASSUMED'))
            continue
        source = entry['source']
        p = dict.fromkeys(trace_fields, '')
        p.update(project_id=pid, column=ASX_COLUMN, value=entry['code'], source_sha256=source['sha256'], source_url=source['url'],
            locator='physical PDF p'+str(entry['code_evidence']['page']), method='SOURCE_BOUND_PROJECT_REPORTING_ISSUER_ASX_CODE',
            scope=entry['scope'], observation_ids='[]')
        for k,v in dict(effective_date=entry['evidence_date'], effective_date_role='ISSUER_CODE_AT_DOCUMENT_DATE_NOT_CURRENT_LEGAL_TITLE',
            date_precision='DAY', review_ids=json.dumps([entry['review_id']]), acquired_through=reviewed['ledger']['acquired_through']).items():
            if k in p:p[k]=v
        trace.append(p)
    merge_receipts = []
    # Identity consolidation is separate from scientific data selection. Preserve
    # the selected target row as-is; no cross-scope numerical borrowing or sum.
    for merge in reviewed['merges']:
        target, other = merge['target_id'], merge['absorbed_id']
        a = next(r for r in rows if r['專案ID']==target); b = next(r for r in rows if r['專案ID']==other)
        conflicts = [c for c in columns if a[c] and b[c] and a[c] != b[c]]
        merge_receipts.append(dict(target_id=target, absorbed_id=other, code=a[ASX_COLUMN], conflicts=conflicts,
            numerical_fields_copied=0, removed_filled_cells=sum(v!='' for v in b.values()),removed_blank_cells=sum(v=='' for v in b.values()),
            source_sha256=merge['source']['sha256'], source_url=merge['source']['url'], decision='EXPLICIT_SUMMARY_IDENTITY_MERGE;TARGET_RESOURCE_SCOPE_PRESERVED'))
        rows = [r for r in rows if r['專案ID'] != other]
        trace = [r for r in trace if r['project_id'] != other]
        missing = [r for r in missing if r['project_id'] != other]
        for r in inventory:
            if r['entity_id'] == other:r.update(included_in_project_summary=False,unit_of_analysis='SUMMARY_ALIAS_OF:'+target+';CANONICAL_DATABASE_UNCHANGED')
    out.mkdir(parents=True, exist_ok=True)
    def write(name, values, fields):
        with (out/name).open('w',encoding='utf-8-sig',newline='') as f:
            w=csv.DictWriter(f,fields);w.writeheader();w.writerows(values)
    columns = columns+[ASX_COLUMN]
    write('專案總表.csv', rows, columns);write('field_provenance.csv',trace,trace_fields)
    write('missing_fields.csv',missing,missing_fields);write('census_inventory.csv',inventory,inventory_fields)
    summary.update(version='census-project-summary-v3-asx-identity', columns=len(columns), rows=len(rows), unique_project_ids=len(rows),
        base_contract_columns=52, base_projection_hashes=summary['output_hashes'], identity_ledger_sha256=reviewed['ledger_sha256'],
        columns_sha256=digest(columns), filled_counts={c:sum(r[c]!='' for r in rows) for c in columns},
        identity_merges=merge_receipts, validated_asx_codes=len(reviewed['entries']),
        identity_sources={key:entry['source'] for key,entry in reviewed['entries'].items()},
        verified_source_hashes=len({p['source_sha256'] for p in trace if p['source_sha256']}),
        asx_code_definition='SOURCE_VERIFIED_PROJECT_REPORTING_ISSUER_AT_EVIDENCE_DATE;NOT_REAL_TIME_OWNERSHIP_OR_LISTING_STATUS',
        output_hashes={name:filehash(out/name) for name in ['專案總表.csv','field_provenance.csv','missing_fields.csv','census_inventory.csv']})
    (out/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    audit_summary(out)
    return summary
