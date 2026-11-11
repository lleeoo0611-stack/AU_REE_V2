"""Offline, source-stated oxide annual output. No throughput/grade derivations."""
from copy import deepcopy
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import re

RULE = 'SOURCE_STATED_ANNUAL_PRODUCTION'
SCOPE = 'CENSUS_ARCHIVED_SOURCE_STATED_OXIDE_ANNUAL_PRODUCTION'
DECISION_ID = 'round2-annual-source-stated-20261111'
COLUMNS = ('預估年產TREO_t_per_year', '預估年產NdPr_t_per_year', '預估年產重稀土_t_per_year')
HREO = frozenset(('Tb', 'Dy', 'Ho', 'Er', 'Tm', 'Yb', 'Lu', 'Y'))


def proposed_decision():
    return dict(decision_id=DECISION_ID, rule=RULE, scope=SCOPE,
                decided_by='USER_EXPLICIT_APPROVAL', decided_date='2026-11-11',
                notes='僅用 census 已封存原件明寫的氧化物年產；禁止進料×品位×回收率推算，混合產品須有來源明寫 REO 當量。',
                approval_evidence='1：G1 選 B、潛力案給、G4 照建議；2：(a) 算完成、(b) 給 B1、(c) 新增 D、(d) 標成X')


def _norm(text):
    return ' '.join(str(text).replace('\xa0', ' ').split()).casefold()


def validate_candidate(item):
    """Validate an explicitly transcribed annual oxide value, never calculate one."""
    if item.get('source_stated') is not True or item.get('derivation'):
        raise ValueError('ANNUAL_SOURCE_STATED_REQUIRED')
    if item.get('column') not in COLUMNS:
        raise ValueError('ANNUAL_COLUMN_REQUIRED')
    if item.get('product_basis') not in {'TOTAL_RARE_EARTH_OXIDE', 'MIXED_RARE_EARTH_OXIDE',
            'NDPR_OXIDE', 'HREO_8_ELEMENT', 'REO_EQUIVALENT_IN_MIXED_CARBONATE', 'REO_EQUIVALENT_IN_CONCENTRATE'}:
        raise ValueError('ANNUAL_OXIDE_EQUIVALENT_REQUIRED')
    if item['column'] == COLUMNS[2] and (item.get('product_basis') != 'HREO_8_ELEMENT'
            or set(item.get('hre_elements', [])) != HREO):
        raise ValueError('ANNUAL_HREO_8_ELEMENT_DEFINITION_REQUIRED')
    if item['column'] == COLUMNS[1] and item.get('product_basis') != 'NDPR_OXIDE':
        raise ValueError('ANNUAL_NDPR_OXIDE_REQUIRED')
    if not item.get('annual_basis') or not item.get('scope_relation'):
        raise ValueError('ANNUAL_BASIS_AND_SCOPE_REQUIRED')
    units = {'tpa': Decimal(1), 't/a': Decimal(1), 't per annum': Decimal(1), 'ktpa': Decimal(1000)}
    if item.get('original_unit') not in units:
        raise ValueError('ANNUAL_EXPLICIT_UNIT_REQUIRED')
    token = str(item.get('original_token', '')).replace(',', '')
    if not re.fullmatch(r'\d+(?:\.\d+)?', token):
        raise ValueError('ANNUAL_NUMERIC_TOKEN_REQUIRED')
    try:
        value = Decimal(token) * units[item['original_unit']]
        expected = Decimal(str(item.get('value')))
    except InvalidOperation:
        raise ValueError('ANNUAL_NUMERIC_VALUE_REQUIRED') from None
    if not expected.is_finite() or expected <= 0 or expected != value:
        raise ValueError('ANNUAL_TOKEN_VALUE_MISMATCH')
    return format(value, 'f').rstrip('0').rstrip('.') if '.' in format(value, 'f') else format(value, 'f')


def _approved(decisions):
    if isinstance(decisions, (str, Path)):
        decisions = json.loads(Path(decisions).read_text(encoding='utf-8-sig'))
    records = decisions.get('decisions', []) if isinstance(decisions, dict) else decisions
    found = [d for d in records if d.get('rule') == RULE and d.get('scope') == SCOPE]
    if len(found) > 1:
        raise ValueError('ANNUAL_DUPLICATE_DECISION')
    if not found or found[0].get('decided_by') != 'USER_EXPLICIT_APPROVAL' or not found[0].get('approval_evidence'):
        return None
    if not found[0].get('decision_id') or not found[0].get('decided_date'):
        return None
    return found[0]


def _verify_cell(item, source):
    import pymupdf
    value = validate_candidate(item)
    with pymupdf.open(source) as doc:
        page = doc[item['page'] - 1]
        box = pymupdf.Rect(item['bbox'])
        row = pymupdf.Rect(item['row_bbox'])
        if box.is_empty or not row.contains(box) or not page.rect.contains(row):
            raise ValueError('ANNUAL_BBOX_OUTSIDE_ROW')
        if _norm(page.get_textbox(box)) != _norm(item['original_token']):
            raise ValueError('ANNUAL_SOURCE_TOKEN_MISMATCH')
        actual = _norm(page.get_textbox(row))
        if actual != _norm(item['row_text']):
            raise ValueError('ANNUAL_SOURCE_ROW_MISMATCH')
        if not re.search(r'\btpa\b|per annum', actual):
            raise ValueError('ANNUAL_SOURCE_UNIT_MISSING')
        if not any(s in actual for s in ('mixed rare earth oxide', 'reo contained in mixed carbonate')):
            raise ValueError('ANNUAL_SOURCE_OXIDE_LABEL_MISSING')
        for proof in item.get('context_proofs', []):
            pg = doc[proof['page']-1]
            if _norm(pg.get_textbox(pymupdf.Rect(proof['bbox']))) != _norm(proof['text']):
                raise ValueError('ANNUAL_CONTEXT_PROOF_MISMATCH')
    return value


REASONS = {
    'North Stanmore': ('NON_OXIDE_PRODUCT_WITHOUT_STATED_REO_EQUIVALENT', 'PFS 2026-08-18 pp4,62,66: ~29,000 wet tpa HREO-enriched flotation concentrate, not oxide tonnes; no throughput×grade conversion.'),
    'Dubbo': ('HREO_DEFINITION_MISMATCH_AND_NO_TOTAL_OUTPUT', 'Scoping 2025-07-11 pp5,17,45: LOM NdPr 1,037 tpa already filled; Dy 49 and Tb 11 tpa are not the eight-element HREO sum; do not sum products into unstated TREO.'),
    'Goschen —': ('HREO_DEFINITION_MISMATCH_AND_NON_OXIDE_CONCENTRATE', 'Updated economics 2026-09-21 pp1,2,6: 8,300 tpa REC is concentrate; 115 tpa Dy+Tb is not eight-element HREO; 990 tpa NdPr already filled.'),
    'Cummins Range': ('MULTIPLE_STAGE_ANNUAL_OUTPUTS_REQUIRE_RESEARCHER_SELECTION', 'Scoping 2023-08-22 p77: explicitly stated TREO 17,11,7 ktpa for Stages 2a,2b,3. No single project annual average and no approved stage selection; retain all candidates, do not average or sum.'),
    'Sandy Mitchell': ('NON_OXIDE_PRODUCT_WITHOUT_STATED_REO_EQUIVALENT', 'Scoping Update 2026-10-29 pp7-8: monazite 7.0 ktpa and xenotime 0.2 ktpa in REMC; no explicitly stated annual oxide equivalent.'),
    'Charley Creek REE': ('NO_SOURCE_STATED_COMPONENT_ANNUAL_OXIDE', 'Scoping 2013-04-15 p5 states REO equivalent only; no accepted annual NdPr or matching eight-element HREO. STAGE_SOURCE_DATED.'),
    'Goschen Central': ('NO_SOURCE_STATED_COMPONENT_ANNUAL_OXIDE', 'Scoping 2025-06-12 Table10 p21 states 3,041 tpa mixed REO in Phase1+2; xenotime concentrate 480 tpa is not HREO and no NdPr output is stated.'),
    'Donald': ('HREO_DEFINITION_MISMATCH', '2026-02-27 disclosure pp1,3,15 reports Dy and Tb only; no matching eight-element HREO annual value. Existing TREO and NdPr retained.'),
    'Brockman': ('PRIMARY_STUDY_NOT_IN_CENSUS', 'Archived WA fact sheet and company reports disclose Scoping status/resources; need the primary Brockman Scoping Study annual oxide product schedule.'),
    'Fingerboards': ('PRIMARY_STUDY_NOT_IN_CENSUS', 'Archived Austrade prospectus p36 is a project/status summary; need primary Fingerboards Feasibility Study oxide annual product schedule.'),
    'Avonbank': ('PRIMARY_STUDY_NOT_IN_CENSUS', 'Archived Austrade prospectus p46 is a project/status summary; need primary Avonbank Feasibility Study oxide annual product schedule.'),
    'Copi': ('PRIMARY_STUDY_NOT_IN_CENSUS', 'Archived Austrade prospectus p47 is a project/status summary; need primary Copi BFS oxide annual product schedule.'),
    'WIM150': ('PRIMARY_STUDY_NOT_IN_CENSUS', 'Archived 2015-10-30 quarterly report discloses BFS/optimisation status; need primary WIM150 BFS annual oxide schedule. STAGE_SOURCE_DATED.'),
    'Wimmera': ('PRIMARY_STUDY_NOT_IN_CENSUS', 'Archived 2026-01-29 MRE/quarterly disclosure: DFS in progress; need a completed source-stated WIM100 annual oxide schedule.'),
    'Euston': ('PRIMARY_STUDY_NOT_IN_CENSUS', 'Archived Iluka 2022 annual report p41: PFS work progressed; need Euston PFS annual oxide product schedule, not Iluka refinery production.'),
}


def apply_annual_production(rows, provenance, decisions, repo):
    """Return additive fills, field-level reviews and hash-verified document inventory."""
    repo = Path(repo)
    config = json.loads((repo/'config/round2_annual_evidence.json').read_text(encoding='utf-8-sig'))
    ledger = json.loads((repo/'config/asx_source_reviews.json').read_text(encoding='utf-8-sig'))['reviews']
    roots = json.loads((repo/'config/asx_local_asset_roots.json').read_text(encoding='utf-8-sig'))['roots']
    inventory = deepcopy(config['document_inventory'])
    paths = {}
    for doc in inventory:
        matches = [r for r in ledger if r.get('project_id') == doc['project_id'] and r.get('source_sha256') == doc['source_sha256']]
        if not matches:
            raise ValueError('ANNUAL_SOURCE_NOT_IN_CENSUS_LEDGER')
        r = matches[0]
        path = repo / roots[r['asset_set']] / r['path']
        if hashlib.sha256(path.read_bytes()).hexdigest() != doc['source_sha256']:
            raise ValueError('ANNUAL_SOURCE_SHA_MISMATCH')
        paths[(doc['project_id'], doc['source_sha256'])] = path
        doc['sha256_verified'] = True
    decision = _approved(decisions)
    by_id = {r['專案ID']: r for r in rows}
    fills = []
    for cell in config['cells']:
        row = by_id.get(cell['project_id'])
        if not row or row.get(cell['column'], '') != '' or row.get('開發階段代碼') not in ('B1', 'B2'):
            continue
        value = _verify_cell(cell, paths[(cell['project_id'], cell['source_sha256'])])
        if not decision:
            continue
        originals = [p for p in provenance if p.get('project_id') == cell['project_id'] and p.get('column') == '開發階段' and p.get('source_sha256') == cell['source_sha256']]
        if len(originals) != 1:
            raise ValueError('ANNUAL_NATIVE_STUDY_TRACE_REQUIRED')
        meta = deepcopy(cell)
        meta.update(method=RULE, decision_id=decision['decision_id'], meaning='SOURCE_FORECAST_NOT_ACTUAL_PRODUCTION')
        trace = deepcopy(originals[0])
        locator = json.dumps(meta, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
        trace.update(column=cell['column'], value=value, method=RULE, locator=locator,
                     scope=cell['scope_relation'], review_ids=json.dumps([decision['decision_id']]))
        fills.append(dict(project_id=cell['project_id'], project_name=row['專案名稱'], column=cell['column'], value=value,
                          sha=cell['source_sha256'], source_sha256=cell['source_sha256'], locator=locator, method=RULE,
                          scope=cell['scope_relation'], decision_id=decision['decision_id'], source_provenance=trace,
                          qualifier=cell['qualifier'], page=cell['page']))
    filled = {(f['project_id'], f['column']) for f in fills}
    target_ids = {d['project_id'] for d in inventory}
    reviews = []
    for pid in sorted(target_ids):
        row = by_id.get(pid)
        if not row:
            continue
        name = row['專案名稱']
        reason, detail = next((v for k,v in REASONS.items() if name.startswith(k)), ('NO_ACCEPTED_SOURCE_STATED_ANNUAL_OUTPUT', 'No source-stated annual oxide quantity accepted.'))
        for column in COLUMNS:
            if row.get(column, '') != '' or (pid, column) in filled:
                continue
            pending_cell = any(c['project_id']==pid and c['column']==column for c in config['cells'])
            reviews.append(dict(project_id=pid, project_name=name, column=column,
                reason='RESEARCHER_DECISION_REQUIRED' if pending_cell and not decision else reason,
                detail=detail, decision_id=decision['decision_id'] if decision else '',
                sources=[d for d in inventory if d['project_id']==pid]))
    return dict(fills=fills, reviews=reviews, document_inventory=inventory)

