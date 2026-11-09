"""Opt-in ore/oxide projection when source cerium is not canonical CeO2.

This is not a complete TREO resource bundle. The reviewed contract is deliberately
narrow: native evidence of Ce2O3 and its 1.171 elemental conversion, one selected
resource-table section, direct bulk-ore oxide ppm, and no total normalization.
"""
import json
import math
import re
from .store import digest

MODE = 'ORE_AND_COMPATIBLE_OXIDES_ONLY'
REASON = 'SOURCE_CE2O3_INCOMPATIBLE_WITH_CANONICAL_CEO2'
CONTRACT_FIELDS = ('source_sha256', 'statement_id', 'scope', 'effective_date')
OBSERVATION_FIELDS = ('source_sha', 'statement_id', 'scope', 'effective_date')
WITHHELD_COLUMNS = frozenset((
    'TREO品位_pct', '總TREO蘊藏量_kt', '磁鐵稀土氧化物蘊藏量_kt',
    '磁鐵稀土佔TREO_pct', '元素總和/TREO', '有TREO資源估計', 'CeO2_氧化鈰_kt',
))


def _fail(code):
    raise ValueError('REVIEW_PARTIAL_RESOURCE_' + code)


def _number(value):
    return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value)


def validate_partial_resource(review, doc, evidence):
    """Return a proof-bound contract, or None when the opt-in key is absent.

    The parent validator owns source hash/receipt, date, scope and every numeric
    cell check. Neither a reason string nor a page-wide species mention suffices.
    """
    if 'partial_resource_projection' not in review:
        return None
    spec = review['partial_resource_projection']
    if isinstance(spec, dict) and spec.get('mode') == HM_MODE:
        return validate_hm_projection(review, doc, evidence)
    if not isinstance(spec, dict) or spec.get('mode') != MODE or spec.get('withholding_reason') != REASON:
        _fail('EXPLICIT_MODE_AND_REASON_REQUIRED')
    if spec.get('source_species') != 'Ce2O3' or spec.get('canonical_species') != 'CeO2':
        _fail('CERIUM_SPECIES_CONTRACT')
    if review.get('bulk_treo_grade_pct') is not None or review.get('bulk_hm_percent') is not None:
        _fail('NORMALIZATION_FORBIDDEN')
    rows = review.get('observations', [])
    if not rows:
        _fail('OBSERVATIONS_REQUIRED')
    for value in rows:
        if value.get('variable')=='reported_resource_magnet_ppm':
            _fail('GROUPED_OXIDES_FORBIDDEN')
        if value.get('variable') in ('grade', 'contained_treo_kt', 'magnet_reo_share_pct') or value.get('basis') in ('CeO2', 'Ce2O3'):
            _fail('TOTAL_GRADE_RATIO_OR_CERIUM_FORBIDDEN')
        if value.get('variable') != 'ore_mt' and (
            not value.get('variable', '').startswith('reported_resource_') or
            value.get('original_unit', value.get('unit')) != 'ppm' or value.get('unit') != 'ppm'
        ):
            _fail('DIRECT_BULK_OXIDE_PPM_REQUIRED')
        for key in CONTRACT_FIELDS:
            if key in value and value[key] != review[key]:
                _fail('OBSERVATION_CONTRACT_MISMATCH')
        if 'source_sha' in value and value['source_sha'] != review['source_sha256']:
            _fail('OBSERVATION_CONTRACT_MISMATCH')

    import pymupdf
    from .source_cells import norm, region_text

    def region(page_no, bbox):
        if isinstance(page_no, bool) or not isinstance(page_no, int) or not 1 <= page_no <= len(doc):
            _fail('BASIS_PAGE_INVALID')
        if not isinstance(bbox, list) or len(bbox) != 4 or not all(_number(v) for v in bbox):
            _fail('BASIS_RECT_INVALID')
        page = doc[page_no - 1]
        rect = pymupdf.Rect(bbox)
        if rect.is_empty or rect.is_infinite or not (page.rect * page.derotation_matrix).contains(rect):
            _fail('BASIS_RECT_OUTSIDE_PAGE')
        return page, rect

    proof = spec.get('basis_proof')
    if not isinstance(proof, dict) or proof.get('kind') != 'NATIVE_ELEMENT_TO_OXIDE_ROW':
        _fail('BASIS_PROOF_REQUIRED')
    proof_evidence = proof.get('evidence')
    if not isinstance(proof_evidence, dict) or proof_evidence.get('page') != proof.get('page'):
        _fail('BASIS_EVIDENCE_PAGE_MISMATCH')
    content = evidence(proof_evidence)
    if not re.search(r'resource\s+reporting', content):
        _fail('RESOURCE_REPORTING_BASIS_REQUIRED')
    page, table = region(proof.get('page'), proof.get('table_bbox'))
    _, label = region(proof['page'], proof.get('table_label_bbox'))
    _, row = region(proof['page'], proof.get('row_bbox'))
    if not table.contains(label) or not table.contains(row) or label.y1 > row.y0 or row.height >= table.height:
        _fail('BASIS_ROW_OUTSIDE_TABLE')
    actual_label = norm(region_text(page, label))
    if actual_label != norm(proof.get('table_label', '')) or not re.search(r'factors\s+used\s+to\s+convert\s+elements\s+to\s+oxides', actual_label):
        _fail('BASIS_TABLE_SEMANTICS')
    # 1.171 corroborates Ce2O3 as intentional source chemistry, rather than a
    # lone typo in the resource header. It is NEVER used to normalize CeO2.
    if norm(region_text(page, row)) != 'cerium ce2o3 1.171':
        _fail('BASIS_CONVERSION_ROW_MISMATCH')
    if proof.get('conversion_factor') != 1.171:
        _fail('BASIS_CONVERSION_FACTOR_MISMATCH')

    header = spec.get('resource_header')
    if not isinstance(header, dict):
        _fail('SELECTED_RESOURCE_HEADER_REQUIRED')
    page, header_rect = region(header.get('page'), header.get('bbox'))
    if norm(region_text(page, header_rect)) != 'ce2o3':
        _fail('SELECTED_RESOURCE_CERIUM_HEADER_MISMATCH')
    section = (review.get('selected_resource_sections') or {}).get(header.get('section_id'))
    if not section or section.get('page') != header['page']:
        _fail('SELECTED_RESOURCE_SECTION_REQUIRED')
    if not section.get('cutoff_group'):
        _fail('SELECTED_RESOURCE_CUTOFF_GROUP_REQUIRED')
    # All direct inputs must be in this same resource table and section. This
    # deliberately rejects other cutoffs, other prospects and share tables.
    tables = set()
    for value in rows:
        binding = value.get('cell_binding') or {}
        if (binding.get('section_id') != header['section_id'] or binding.get('page') != header['page'] or
            binding.get('scope') != review['scope'] or value.get('evidence', {}).get('page') != header['page']):
            _fail('SELECTED_RESOURCE_SECTION_MISMATCH')
        _, table = region(header['page'], binding.get('table_bbox'))
        if not table.contains(header_rect):
            _fail('CERIUM_HEADER_OUTSIDE_SELECTED_TABLE')
        tables.add(tuple(binding['table_bbox']))
    if len(tables) != 1:
        _fail('SELECTED_RESOURCE_TABLE_MISMATCH')
    return dict(mode=MODE, withholding_reason=REASON, source_species='Ce2O3', canonical_species='CeO2',
                basis_proof_verified=True, basis_proof=proof, resource_header=header,
                review_id=review['review_id'], **{key: review[key] for key in CONTRACT_FIELDS})


def partial_resource_bundle(observations, contract):
    """No default, no alternate-source fallback, no fabricated total or zero."""
    from .project_summary import ELEMENTS
    if isinstance(contract, dict) and contract.get('mode') == HM_MODE:
        return hm_resource_bundle(observations, contract)
    if (not isinstance(contract, dict) or contract.get('mode') != MODE or
        contract.get('withholding_reason') != REASON or contract.get('basis_proof_verified') is not True or
        contract.get('source_species') != 'Ce2O3' or contract.get('canonical_species') != 'CeO2' or
        not contract.get('basis_proof') or not contract.get('resource_header') or
        any(not contract.get(k) for k in CONTRACT_FIELDS)):
        return None, 'PARTIAL_RESOURCE_VERIFIED_CONTRACT_REQUIRED'
    expected = tuple(contract[k] for k in CONTRACT_FIELDS)
    relevant = [o for o in observations if o.get('variable') in ('ore_mt', 'grade', 'contained_treo_kt', 'magnet_reo_share_pct') or
                o.get('variable', '').startswith('reported_resource_')]
    if not relevant or any(tuple(o.get(k) for k in OBSERVATION_FIELDS) != expected for o in relevant):
        return None, 'PARTIAL_RESOURCE_EXACT_CONTRACT_REQUIRED'
    if any(o.get('status') != 'AUTO_VALIDATED' for o in relevant):
        return None, 'PARTIAL_RESOURCE_VALIDATED_INPUTS_REQUIRED'
    ore = []; oxides = {}; raw_contract = {k: contract[k] for k in CONTRACT_FIELDS}
    for o in relevant:
        try:
            raw = json.loads(o['raw'])
        except (KeyError, TypeError, ValueError):
            return None, 'PARTIAL_RESOURCE_INPUT_PROVENANCE_REQUIRED'
        if (not isinstance(raw, dict) or raw.get('partial_resource_projection') != contract or
            any(raw.get(k) != v for k, v in raw_contract.items())):
            return None, 'PARTIAL_RESOURCE_INPUT_PROVENANCE_REQUIRED'
        if not _number(o.get('value')):
            return None, 'PARTIAL_RESOURCE_FINITE_NUMBERS_REQUIRED'
        if o['variable'] == 'ore_mt':
            if o['basis'] != 'TREO' or o['unit'] != 'Mt' or o['value'] <= 0:
                return None, 'PARTIAL_RESOURCE_ORE_UNIT_OR_BASIS'
            ore.append(o)
        elif (o['variable'].startswith('reported_resource_') and o.get('basis') in ELEMENTS and o['basis'] != 'CeO2' and
              o.get('unit') == 'ppm' and 0 <= o['value'] <= 1000000 and raw.get('original_unit') == 'ppm' and
              raw.get('material_basis') == 'RESOURCE_ORE_GRADE_OXIDE_PPM' and not raw.get('normalization')):
            values = oxides.setdefault(o['basis'], [])
            values.append(o)
        else:
            return None, 'PARTIAL_RESOURCE_TOTAL_GRADE_RATIO_CERIUM_OR_TRANSFORM_FORBIDDEN'
    if not ore or not oxides:
        return None, 'PARTIAL_RESOURCE_ORE_AND_OXIDES_REQUIRED'
    if len({o['value'] for o in ore}) != 1 or any(len({o['value'] for o in rows}) != 1 for rows in oxides.values()):
        return None, 'PARTIAL_RESOURCE_CONFLICTING_INPUTS'
    return dict(evidence_id=digest(expected), source_sha256=expected[0], statement_id=expected[1], scope=expected[2],
                effective_date=expected[3], basis='COMPATIBLE_INDIVIDUAL_OXIDES_WITHOUT_TREO',
                value=dict(ore_mt=ore[0]['value']), observations=relevant,
                partial_resource_projection=contract, contained_method=None, rounding={}), 'PARTIAL_RESOURCE_' + REASON


def validate_technical_report_dates(review, doc, evidence):
    """Use an issue date only as a disclosed ordering date, not geological age."""
    if review.get('effective_date_role') != 'TECHNICAL_REPORT_RESOURCE_AS_REPORTED':
        return False
    if (review.get('source_kind') != 'PUBLIC_ARCHIVED_TECHNICAL_REPORT' or
        review.get('publication_date_role') != 'TECHNICAL_REPORT_ISSUE_DATE_NOT_RELEASE' or
        review.get('resource_effective_date_unknown') is not True or
        review.get('public_release_date_unknown') is not True or
        review.get('date_precision') != 'DAY' or review.get('effective_date_interval') is not None or
        review.get('publication_date_precision', 'DAY') != 'DAY' or review.get('publication_date_interval') is not None or
        review.get('document_issue_date') != review.get('publication_date') or
        review.get('effective_date') != review.get('document_issue_date') or
        not isinstance(review.get('partial_resource_projection'), dict) or
        review['partial_resource_projection'].get('mode') != MODE or review.get('study')):
        _fail('TECHNICAL_REPORT_DATE_CONTRACT_REQUIRED')
    proof = review.get('document_issue_evidence')
    if not isinstance(proof, dict):
        _fail('DOCUMENT_ISSUE_PROOF_REQUIRED')
    evidence(proof)
    import pymupdf
    from datetime import datetime
    from .source_cells import norm, region_text
    page_no = proof.get('page'); bbox = proof.get('bbox')
    if (isinstance(page_no, bool) or not isinstance(page_no, int) or not 1 <= page_no <= min(3, len(doc)) or
        not isinstance(bbox, list) or len(bbox) != 4 or not all(_number(v) for v in bbox)):
        _fail('DOCUMENT_ISSUE_REGION_REQUIRED')
    page = doc[page_no - 1]; rect = pymupdf.Rect(bbox)
    if rect.is_empty or rect.is_infinite or not (page.rect * page.derotation_matrix).contains(rect):
        _fail('DOCUMENT_ISSUE_REGION_INVALID')
    actual = norm(region_text(page, rect))
    day = norm(datetime.strptime(review['document_issue_date'], '%Y-%m-%d').strftime('%d %B %Y').lstrip('0'))
    if actual != norm(proof.get('text', '')) or not re.search(r'(?<!\d)' + re.escape(day) + r'(?!\d)', re.sub(r'\b0(?=\d\b)', '', actual)):
        _fail('DOCUMENT_ISSUE_DATE_MISMATCH')
    return True

# HM assays are composition of an explicitly reported mineral mass, not ore
# grades and not a reported TREO total. Scandium is never admitted here.
HM_MODE = 'BULK_ORE_AND_HM_HOSTED_OXIDES_ONLY'
HM_REASON = 'HM_OXIDE_MASS_DERIVATION_WITHOUT_REPORTED_BULK_TREO'


def validate_hm_projection(review, doc, evidence):
    from .project_summary import ELEMENTS
    from .technical_tables import number_token
    from .source_cells import validate_cell, region_text, norm
    import pymupdf
    spec = review['partial_resource_projection']
    if spec.get('withholding_reason') != HM_REASON or review.get('bulk_hm_percent') is not None or review.get('bulk_treo_grade_pct') is not None:
        _fail('HM_EXPLICIT_CONTRACT_REQUIRED')
    for key in CONTRACT_FIELDS:
        if spec.get(key) != review[key]: _fail('HM_CONTRACT_MISMATCH')
    masses = spec.get('mass_inputs', {})
    if set(masses) != {'ore_mt', 'hm_mass_mt'}: _fail('HM_MASS_INPUTS_REQUIRED')
    def half_width(item):
        token = str(item['original_token']).replace(',', '')
        minimum = .5 * 10 ** (-len(token.split('.')[1]) if '.' in token else 0)
        half = item.get('rounding_half_width')
        if not _number(half) or half < minimum or half >= item['value']:
            _fail('HM_ROUNDING_REQUIRED')
        return half
    bindings = []
    for field, item in masses.items():
        token = number_token(item.get('original_token'))
        if not token or token['value'] != item.get('value') or not _number(item.get('value')) or item['value'] <= 0 or item.get('unit') != 'Mt':
            _fail('HM_MASS_TOKEN_OR_UNIT')
        e = item.get('evidence', {}); evidence(e)
        b = item.get('cell_binding', {})
        if b.get('page') != e.get('page') or b.get('mode') != 'native_cell': _fail('HM_NATIVE_MASS_BINDING_REQUIRED')
        validate_cell(doc, b, field, item['original_token'], 'Mt', review['scope'], selected_sections=review.get('selected_resource_sections'))
        half_width(item); bindings.append(b)
    ore, hm = masses['ore_mt'], masses['hm_mass_mt']
    if hm['value'] > ore['value']: _fail('HM_MASS_EXCEEDS_ORE')
    for key in ('page', 'section_id', 'row_bbox', 'table_bbox'):
        if bindings[0].get(key) != bindings[1].get(key): _fail('HM_MASS_SCOPE_MISMATCH')
    # Exact native note regions bind the denominator and cutoff between tables.
    def note(name, pattern):
        proof = spec.get(name, {}); e = proof.get('evidence', {})
        evidence(e)
        if proof.get('page') != e.get('page'): _fail('HM_NOTE_PAGE_MISMATCH')
        pn = proof.get('page'); raw = proof.get('bbox')
        if not isinstance(pn, int) or not 1 <= pn <= len(doc) or not isinstance(raw, list) or len(raw) != 4 or not all(_number(v) for v in raw): _fail('HM_NOTE_REGION_REQUIRED')
        box = pymupdf.Rect(raw)
        if box.is_empty or not doc[pn-1].rect.contains(box): _fail('HM_NOTE_REGION_REQUIRED')
        text = norm(region_text(doc[pn-1], box))
        if text != norm(proof.get('text', '')) or not re.fullmatch(pattern, text): _fail('HM_NOTE_SEMANTICS')
        return proof, text
    denom, _ = note('denominator_proof', r'the rare earth element oxide is reported as a percentage of the hm content from the reported mineral resource\.')
    c1, cutoff1 = note('mass_cutoff_proof', r'mineral resources are reported at a cut-off grade of [\d.]+% hm\.')
    c2, cutoff2 = note('oxide_cutoff_proof', r'mineral resources are reported at a cut-off grade of [\d.]+% hm\.')
    if cutoff1 != cutoff2 or c1['page'] != bindings[0]['page'] or c2['page'] != denom['page']: _fail('HM_CUTOFF_SCOPE_MISMATCH')
    rows = review.get('observations', []); ores = [o for o in rows if o.get('variable') == 'ore_mt']
    if len(ores) != 1 or any(ores[0].get(k) != ore.get(k) for k in ('value','original_token','cell_binding','unit','rounding_half_width')): _fail('HM_SELECTED_ORE_MISMATCH')
    oxide_rows = [o for o in rows if o.get('variable') != 'ore_mt']
    if not oxide_rows or len({o.get('basis') for o in oxide_rows}) != len(oxide_rows): _fail('HM_OXIDES_REQUIRED_OR_DUPLICATED')
    if {o.get('basis') for o in oxide_rows} != set(ELEMENTS): _fail('HM_COMPLETE_15_OXIDES_REQUIRED')
    table_keys = set()
    intervals = {}; percent_sum = 0
    resource_name = spec.get('resource_name')
    if not resource_name or resource_name.casefold() not in evidence(review['identity_evidence']): _fail('HM_RESOURCE_NAME_REQUIRED')
    mass_section = (review.get('selected_resource_sections') or {}).get(bindings[0].get('section_id'), {})
    if resource_name.casefold() not in norm(mass_section.get('anchor','')): _fail('HM_RESOURCE_NAME_REQUIRED')
    for o in oxide_rows:
        if o.get('basis') not in ELEMENTS or not o.get('variable','').startswith('reported_resource_') or o.get('original_unit') != '%HM' or o.get('unit') != 'ppm': _fail('HM_ONLY_CANONICAL_OXIDES')
        for key in CONTRACT_FIELDS:
            if key in o and o[key] != review[key]: _fail('HM_CONTRACT_MISMATCH')
        b = o.get('cell_binding', {}); e = o.get('evidence', {})
        if b.get('page') != denom['page'] or e.get('page') != denom['page'] or b.get('mode') != 'native_cell' or b.get('scope') != review['scope'] or norm(b.get('row_label','')) != norm(bindings[0].get('row_label','')): _fail('HM_OXIDE_SCOPE_MISMATCH')
        oxide_section = (review.get('selected_resource_sections') or {}).get(b.get('section_id'), {})
        if resource_name.casefold() not in norm(oxide_section.get('anchor','')): _fail('HM_RESOURCE_NAME_REQUIRED')
        table_keys.add((b.get('section_id'),tuple(b.get('table_bbox',[])),tuple(b.get('row_bbox',[]))))
        token = number_token(o.get('original_token')); pct = token['value'] if token else None
        if not _number(pct) or not 0 <= pct <= 100: _fail('HM_OXIDE_PERCENT_INVALID')
        percent_sum += pct
        pct_half = .5 * 10 ** (-len(str(o['original_token']).split('.')[1]) if '.' in str(o['original_token']) else 0)
        # Product intervals retain the uncertainty of both source tokens. They
        # are not confidence limits, and no precision is inferred from ratios.
        lo = (hm['value']-hm['rounding_half_width'])*max(0,pct-pct_half)*10
        hi = (hm['value']+hm['rounding_half_width'])*(pct+pct_half)*10
        intervals[o['basis']] = {'contained_kt':hm['value']*pct*10,'rounding_interval_kt':[lo,hi]}
    if len(table_keys) != 1: _fail('HM_OXIDE_TABLE_MISMATCH')
    if percent_sum > 100: _fail('HM_OXIDE_PERCENT_SUM_EXCEEDS_100')
    return dict(mode=HM_MODE,withholding_reason=HM_REASON,basis_proof_verified=True,
                review_id=review['review_id'], **{k:review[k] for k in CONTRACT_FIELDS},
                mass_inputs=masses,denominator_proof=denom,mass_cutoff_proof=c1,oxide_cutoff_proof=c2,
                bulk_hm_percent=hm['value']/ore['value']*100,oxide_rounding=intervals)


def hm_resource_bundle(observations, contract):
    from .project_summary import ELEMENTS
    if contract.get('withholding_reason') != HM_REASON or contract.get('basis_proof_verified') is not True or not contract.get('mass_inputs') or not contract.get('denominator_proof') or not contract.get('oxide_rounding') or any(not contract.get(k) for k in CONTRACT_FIELDS):
        return None, 'HM_PARTIAL_VERIFIED_CONTRACT_REQUIRED'
    expected = tuple(contract[k] for k in CONTRACT_FIELDS); ore = []; oxides = []
    for o in observations:
        if tuple(o.get(k) for k in OBSERVATION_FIELDS) != expected or o.get('status') != 'AUTO_VALIDATED': return None,'HM_PARTIAL_INPUT_CONTRACT'
        try: raw=json.loads(o['raw'])
        except (KeyError,ValueError,TypeError): return None,'HM_PARTIAL_RAW_REQUIRED'
        if raw.get('partial_resource_projection') != contract or not _number(o.get('value')): return None,'HM_PARTIAL_RAW_REQUIRED'
        if o.get('variable') == 'ore_mt' and o.get('unit') == 'Mt' and o.get('basis') == 'TREO' and o['value'] == contract['mass_inputs']['ore_mt']['value']:
            ore.append(o)
        elif o.get('basis') in ELEMENTS and o.get('variable','').startswith('reported_resource_') and o.get('unit') == 'ppm' and raw.get('original_unit') == '%HM' and raw.get('normalization') == 'REPORTED_HM_MASS_X_OXIDE_PERCENT_DIVIDED_BY_BULK_ORE' and raw.get('material_basis') == 'RESOURCE_ORE_GRADE_OXIDE_PPM':
            oxides.append(o)
        else:return None,'HM_PARTIAL_TOTAL_OR_UNSUPPORTED_VALUE'
    if len(ore)!=1 or len(oxides)!=len(ELEMENTS) or {o['basis'] for o in oxides}!=set(ELEMENTS):return None,'HM_PARTIAL_INPUTS_REQUIRED'
    for o in oxides:
        expected_kt=contract['oxide_rounding'].get(o['basis'],{}).get('contained_kt')
        if expected_kt is None or not math.isclose(ore[0]['value']*o['value']*.001,expected_kt,rel_tol=1e-12):return None,'HM_PARTIAL_MASS_TRANSFORM_MISMATCH'
    return dict(evidence_id=digest(expected),source_sha256=expected[0],statement_id=expected[1],scope=expected[2],effective_date=expected[3],basis='HM_HOSTED_OXIDES_WITHOUT_REPORTED_TREO',value=dict(ore_mt=ore[0]['value']),observations=observations,partial_resource_projection=contract,contained_method=None,rounding=contract['oxide_rounding']), 'PARTIAL_RESOURCE_'+HM_REASON
