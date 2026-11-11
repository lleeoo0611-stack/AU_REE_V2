"""Fail-closed, offline candidate-table matching against selected resource cells.

Numeric agreement is necessary, never sufficient. A promotion also needs the
already validated resource row/section in the same source, and is submitted to
asx_validation.validate_reviews before it can reach project_summary.
"""
from decimal import Decimal, InvalidOperation
import copy
import re

SUBS = str.maketrans('₀₁₂₃₄₅₆₇₈₉', '0123456789')
OXIDES = ('La2O3','CeO2','Pr6O11','Nd2O3','Sm2O3','Eu2O3','Gd2O3','Tb4O7','Dy2O3','Ho2O3','Er2O3','Tm2O3','Yb2O3','Lu2O3','Y2O3')
FACTORS = {'ppm':Decimal(1), '%':Decimal(10000), 'kg/t':Decimal(1000)}


def compact(value):
    return re.sub(r'\s+', '', str(value or '').translate(SUBS)).casefold()


def numeric(token):
    text = str('' if token is None else token).strip().replace(',', '')
    if not re.fullmatch(r'[+]?(?:\d+(?:\.\d*)?|\.\d+)', text):
        raise ValueError('NON_NUMERIC_OR_CENSORED_TOKEN')
    value = Decimal(text)
    if not value.is_finite():
        raise ValueError('NON_FINITE_TOKEN')
    return value


def rounding_half_width(token):
    """Half the last printed decimal unit, not a fixed relative tolerance."""
    value = numeric(token)
    return Decimal(5).scaleb(value.as_tuple().exponent-1)


def matches_rounded(token, expected):
    value = numeric(token)
    delta = abs(value-Decimal(str(expected)))
    tolerance = rounding_half_width(token)
    return delta <= tolerance, dict(token=str(token), expected=str(expected),
        half_width=str(tolerance), absolute_difference=str(delta),
        calculation='0.5 * 10**printed_decimal_exponent')


def oxide_name(header):
    """Recognize spaced/subscript formulae, including PDF baseline/subscript order."""
    value = compact(header)
    found=[]
    for oxide in OXIDES:
        canonical=oxide.casefold()
        # PDF table extraction may return Nd O / 2 3 rather than Nd2 O3.
        element, a, b = re.fullmatch(r'([A-Z][a-z]?)(\d*)O(\d+)',oxide).groups()
        forms={canonical,(element+'O'+a+b).casefold()}
        if any(re.search(r'(?<![a-z0-9])'+re.escape(f)+r'(?![a-z0-9])',value) for f in forms):
            found.append(oxide)
    return found[0] if len(found)==1 else None


def header_unit(header):
    value=compact(header)
    units=[]
    for unit,pattern in [('kg/t',r'kg/t'),('ppm',r'ppm'),('%',r'%'),('kt',r'(?<![a-z])kt(?![a-z])'),('t',r'(?<![a-z/])t(?![a-z])')]:
        if re.search(pattern,value):units.append(unit)
    # Never interpret percentages of TREO/HM as bulk-ore grade.
    if '%treo' in value or '%hm' in value or 'oftreo' in value or 'ofhm' in value:
        raise ValueError('NON_BULK_ORE_UNIT')
    if len(units)!=1:raise ValueError('UNIT_UNKNOWN_OR_CONFLICT')
    return units[0]


def ppm_value(token, unit, ore_mt=None):
    value=numeric(token)
    if unit in FACTORS:return value*FACTORS[unit]
    if unit in ('t','kt') and ore_mt is not None and Decimal(str(ore_mt))>0:
        return value*(Decimal(1) if unit=='t' else Decimal(1000))/Decimal(str(ore_mt))
    raise ValueError('UNIT_UNKNOWN_OR_CONFLICT')


def infer_columns(cells):
    """Use header rows preceding the first fully numeric ore/grade data row."""
    first=next((i for i,row in enumerate(cells) if any(re.fullmatch(r'(?i)(total|global|measured|indicated|inferred)',str(v or '').strip()) for v in row)),None)
    if first is None:return {},None
    width=max(map(len,cells),default=0)
    headers=[' '.join(str(row[c] or '') for row in cells[:first] if c<len(row)) for c in range(width)]
    out={}
    for c,h in enumerate(headers):
        key=oxide_name(h)
        text=compact(h)
        if key is None and any(word in text for word in ('tonnes','tonnage','resource(m','ore(mt')):key='ore'
        if key is None and re.search(r'treo(?:\d+)?(?:\(|ppm|%)',text) and not any(x in text for x in ('treo-ce','treo–ce','treo+','%treo')):key='grade'
        if key:
            if key in out:raise ValueError('DUPLICATE_SEMANTIC_COLUMN')
            out[key]=dict(column=c,header=h)
    return out,first


def match_rows(cells, columns, ore, grade, ore_unit='Mt', grade_unit='ppm', row_label='Total'):
    if 'ore' not in columns or 'grade' not in columns:raise ValueError('ORE_AND_TREO_COLUMNS_REQUIRED')
    matches=[]
    for i,row in enumerate(cells):
        try:
            ot=row[columns['ore']['column']];gt=row[columns['grade']['column']]
            ok1,r1=matches_rounded(ot,ore);ok2,r2=matches_rounded(gt,grade)
        except (ValueError,IndexError,InvalidOperation):continue
        if ok1 and ok2:
            labels=[str(x).strip() for x in row if x and re.fullmatch(r'(?i)(total|global|measured|indicated|inferred)',str(x).strip())]
            matches.append(dict(row=i,label=labels[0] if len(labels)==1 else '',ore_tolerance=r1,grade_tolerance=r2))
    if len(matches)>1:raise ValueError('MULTIPLE_MATCHING_ROWS')
    if not matches:raise ValueError('ORE_GRADE_NO_MATCH')
    match=matches[0]
    if compact(match['label'])!=compact(row_label):raise ValueError('RESOURCE_CATEGORY_OR_SUBSET_MISMATCH')
    return match


def verify_scope(selected, candidate, bridge_verifier=None):
    """A cross-document bridge is a separately reviewed contract, never inferred."""
    for key in ('statement_id','scope','category','cutoff','effective_date','reo_basis'):
        if selected.get(key) is None or candidate.get(key) is None:raise ValueError('SCOPE_EVIDENCE_MISSING:'+key)
        if selected[key]!=candidate[key]:raise ValueError('SCOPE_MISMATCH:'+key)
    if candidate.get('source_sha256')!=selected.get('source_sha256'):
        bridge=candidate.get('same_mre_bridge')
        if not bridge or bridge_verifier is None or bridge_verifier(bridge) is not True or bridge.get('selected_sha256')!=selected.get('source_sha256') or bridge.get('candidate_sha256')!=candidate.get('source_sha256'):
            raise ValueError('CROSS_DOCUMENT_MRE_PROOF_REQUIRED')
        if any(bridge.get(k)!=selected.get(k) for k in ('statement_id','effective_date','ore_mt','grade_ppm')):
            raise ValueError('CROSS_DOCUMENT_MRE_PROOF_MISMATCH')
    return True


def closure_check(grades, half_widths, treo_ppm, treo_half_width):
    if set(grades)!=set(OXIDES):return None
    if set(half_widths)!=set(OXIDES):raise ValueError('CLOSURE_PRECISION_MISSING')
    delta=abs(sum(Decimal(str(grades[o])) for o in OXIDES)-Decimal(str(treo_ppm)))
    tolerance=sum(Decimal(str(half_widths[o])) for o in OXIDES)+Decimal(str(treo_half_width))
    if delta>tolerance:raise ValueError('CLOSURE_FAIL')
    return dict(delta_ppm=str(delta),tolerance_ppm=str(tolerance),method='SUM_PRINTED_HALF_WIDTHS')


def same_row_band(a,b):
    if not a or not b:return False
    # Horizontal extents can differ because each original binding is column-specific.
    return max(a[1],b[1])<=min((a[1]+a[3])/2,(b[1]+b[3])/2) and min(a[3],b[3])>=max((a[1]+a[3])/2,(b[1]+b[3])/2)


def selected_review(row, trace, reviews):
    matches=[t for t in trace if t['project_id']==row['專案ID'] and t['column']=='礦石蘊藏量_Mt']
    if len(matches)!=1:raise ValueError('SELECTED_RESOURCE_PROVENANCE_REQUIRED')
    provenance=matches[0]
    candidates=[r for r in reviews if r['project_id']==row['專案ID'] and r['source_sha256']==provenance['source_sha256'] and r.get('scope')==provenance['scope'] and any(o['variable']=='ore_mt' for o in r.get('observations',[]))]
    if len(candidates)!=1:raise ValueError('SELECTED_REVIEW_ROW_BINDING_UNAVAILABLE')
    review=candidates[0]
    obs={o['variable']:o for o in review['observations']}
    if not all(k in obs for k in ('ore_mt','grade')):raise ValueError('SELECTED_ORE_GRADE_PAIR_REQUIRED')
    ob,gb=(obs[k].get('cell_binding',{}) for k in ('ore_mt','grade'))
    if ob.get('mode')!='native_cell' or gb.get('mode')!='native_cell':raise ValueError('SELECTED_NATIVE_ROW_BINDING_REQUIRED')
    if ob.get('page')!=gb.get('page') or not same_row_band(ob.get('row_bbox'),gb.get('row_bbox')):raise ValueError('SELECTED_ORE_GRADE_DIFFERENT_ROWS')
    return review,provenance,obs


def make_native_observation(page, native_table, row_index, column_index, oxide, token, unit, review, ore_observation):
    """Reuse verified row/scope anchors; derive only the new semantic column."""
    import pymupdf
    from .source_cells import region_text,validate_cell
    original=ore_observation['cell_binding']
    rect=pymupdf.Rect(native_table.rows[row_index].cells[column_index])
    row=pymupdf.Rect(original['row_bbox'])
    if not row.y0<=rect.y0+rect.height/2<=row.y1:raise ValueError('SELECTED_ROW_GEOMETRY_MISMATCH')
    table=pymupdf.Rect(original['table_bbox'])
    if rect.x0<table.x0 or rect.x1>table.x1:raise ValueError('OXIDE_OUTSIDE_SELECTED_TABLE')
    words=page.get_text('words',sort=True)
    # A semantic label must be independently native text, not invented from the
    # candidate JSON. Split/reordered glyphs remain in the manual review queue.
    header_words=[w for w in words if rect.x0<=(w[0]+w[2])/2<=rect.x1 and table.y0<=(w[1]+w[3])/2<row.y0]
    labels=[w for w in header_words if compact(w[4])==compact(oxide)]
    units=[w for w in header_words if compact(w[4]).strip('()')==unit.casefold()]
    if len(labels)!=1 or len(units)!=1:raise ValueError('NATIVE_HEADER_OR_UNIT_ANCHOR_AMBIGUOUS')
    def box(w):return [w[0]-.01,w[1]-.01,w[2]+.01,w[3]+.01]
    field='reported_resource_'+re.match(r'[A-Z][a-z]?',oxide)[0].lower()+'_ppm'
    binding=copy.deepcopy(original)
    binding.update(field=field,basis=oxide,original_unit=unit,column_bbox=[rect.x0,table.y0,rect.x1,table.y1],
        column_label=oxide,column_label_bbox=box(labels[0]),unit_bbox=box(units[0]),unit_label=units[0][4])
    validate_cell([page] if original['page']==1 else _PageIndex(page,original['page']),binding,field,str(token),unit,review['scope'],selected_sections=review['selected_resource_sections'])
    value=ppm_value(token,unit,ore_observation['value'])
    half=rounding_half_width(token)*FACTORS[unit] if unit in FACTORS else mass_grade_half_width(token,unit,ore_observation)
    return dict(variable=field,value=float(value),unit='ppm',basis=oxide,original_unit=unit,original_token=str(token),
        rounding_half_width=float(half),
        evidence=dict(page=original['page'],markers=[oxide,str(token)]),cell_binding=binding,
        candidate_match=dict(review_method='AUTO_MATCHED_SAME_SCOPE_TABLE',physical_page=original['page'],table_bbox=list(native_table.bbox),row=row_index,column=column_index,original_token=str(token),unit=unit,ore_mt=ore_observation['value'],ore_original_token=ore_observation.get('original_token'),ore_original_unit=ore_observation.get('original_unit',ore_observation['unit']),normalization='SOURCE_MASS_DIVIDED_BY_SAME_ROW_ORE' if unit in ('t','kt') else 'SOURCE_GRADE_TO_PPM'))


class _PageIndex:
    def __init__(self,page,index):self.page,self.index=page,index
    def __len__(self):return self.index
    def __getitem__(self,index):
        if index!=self.index-1:raise IndexError(index)
        return self.page


def validate_candidate_metadata(doc,review,value):
    """Verify optional AUTO_MATCH metadata only after ordinary cell validation.

    The row/column indices and tolerance receipt are checked against the original
    native table. A caller-provided method label alone grants no authority.
    """
    metadata=value.get('candidate_match')
    if metadata is None:return None
    if not isinstance(metadata,dict) or metadata.get('review_method')!='AUTO_MATCHED_SAME_SCOPE_TABLE':
        raise ValueError('REVIEW_CANDIDATE_METHOD_SCHEMA')
    binding=value['cell_binding'];page_no=metadata.get('physical_page')
    if page_no!=binding['page'] or metadata.get('original_token')!=str(value['original_token']) or metadata.get('unit')!=value.get('original_unit',value['unit']):
        raise ValueError('REVIEW_CANDIDATE_METADATA_MISMATCH')
    for field in ('row','column'):
        if type(metadata.get(field)) is not int or metadata[field]<0:raise ValueError('REVIEW_CANDIDATE_INDEX_SCHEMA')
    tables=[t for t in doc[page_no-1].find_tables().tables if list(t.bbox)==metadata.get('table_bbox')]
    if len(tables)!=1:raise ValueError('REVIEW_CANDIDATE_TABLE_MISMATCH')
    table=tables[0];cells=table.extract();columns,_=infer_columns(cells)
    oxide=value['basis'];column=columns.get(oxide)
    if not column or column['column']!=metadata['column']:raise ValueError('REVIEW_CANDIDATE_COLUMN_MISMATCH')
    if header_unit(column['header'])!=metadata['unit']:raise ValueError('REVIEW_CANDIDATE_UNIT_MISMATCH')
    try:token=cells[metadata['row']][metadata['column']]
    except IndexError:raise ValueError('REVIEW_CANDIDATE_CELL_MISMATCH')
    if str(token)!=metadata['original_token']:raise ValueError('REVIEW_CANDIDATE_CELL_MISMATCH')
    obs={o['variable']:o for o in review['observations'] if o['variable'] in ('ore_mt','grade')}
    if set(obs)!=set(('ore_mt','grade')):raise ValueError('REVIEW_CANDIDATE_RESOURCE_PAIR_REQUIRED')
    for o in obs.values():
        b=o.get('cell_binding',{})
        if b.get('page')!=page_no or not same_row_band(b.get('row_bbox'),binding.get('row_bbox')):
            raise ValueError('REVIEW_CANDIDATE_SELECTED_ROW_MISMATCH')
    if metadata.get('ore_mt')!=obs['ore_mt']['value'] or metadata.get('ore_original_token')!=obs['ore_mt'].get('original_token') or metadata.get('ore_original_unit')!=obs['ore_mt'].get('original_unit',obs['ore_mt']['unit']):
        raise ValueError('REVIEW_CANDIDATE_ORE_INPUT_MISMATCH')
    expected=match_rows(cells,columns,numeric(obs['ore_mt'].get('original_token',obs['ore_mt']['value'])),numeric(obs['grade'].get('original_token',obs['grade']['value'])),row_label=binding['row_label'])
    if expected!=metadata.get('tolerances') or expected['row']!=metadata['row']:
        raise ValueError('REVIEW_CANDIDATE_TOLERANCE_RECEIPT_MISMATCH')
    return copy.deepcopy(metadata)


def mass_grade_half_width(token,unit,ore_observation):
    mass=numeric(token);mass_half=rounding_half_width(token)
    ore=Decimal(str(ore_observation['value']))
    ore_factor={'Mt':Decimal(1),'kt':Decimal('.001'),'t':Decimal('.000001')}[ore_observation.get('original_unit',ore_observation['unit'])]
    ore_half=rounding_half_width(ore_observation.get('original_token',ore_observation['value']))*ore_factor
    if ore<=ore_half:raise ValueError('MASS_GRADE_ORE_PRECISION_INVALID')
    factor=Decimal(1000) if unit=='kt' else Decimal(1)
    point=mass*factor/ore
    return max(abs((mass-mass_half)*factor/(ore+ore_half)-point),abs((mass+mass_half)*factor/(ore-ore_half)-point))
