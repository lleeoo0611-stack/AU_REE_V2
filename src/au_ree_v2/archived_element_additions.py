"""Add reviewed resource-oxide cells after native same-version verification."""
import hashlib
import json
import math
import re
from pathlib import Path
from .store import canonical,filehash


def matching_resource(row,trace,db,entry):
    """An exact existing observation contract, never matching on numbers alone."""
    pid=entry['project_id']
    native=[p for p in trace if p['project_id']==pid and p['column']=='礦石蘊藏量_Mt']
    if len(native)!=1 or native[0]['source_sha256']!=entry['selected_source_sha256']:
        raise ValueError('ADDITION_SELECTED_RESOURCE_SOURCE')
    ids=json.loads(native[0]['observation_ids'])
    observations=[dict(o) for o in db.execute('SELECT * FROM observations WHERE entity_id=?',(pid,)) if o['obs_id'] in ids]
    required=set(entry.get('required_variables',['ore_mt','grade','contained_treo_kt']))
    selected={o['variable']:o for o in observations if o['variable'] in required}
    if len(observations)!=len(ids) or set(selected)!=required:
        raise ValueError('ADDITION_RESOURCE_OBSERVATIONS')
    for o in selected.values():
        raw=json.loads(o['raw'])
        if o['status']!='AUTO_VALIDATED' or o['source_sha']!=entry['selected_source_sha256'] or any(
            o[k]!=entry[k] for k in ('scope','statement_id','effective_date','category')):
            raise ValueError('ADDITION_SCOPE_VERSION_CATEGORY_DATE')
        if any(raw.get(k)!=v for k,v in entry['raw_contract'].items()):
            raise ValueError('ADDITION_CUTOFF_REO_BASIS')
    if selected['ore_mt']['unit']!='Mt' or selected['grade']['unit']!='ppm' or any(o['basis']!='TREO' for o in selected.values()):
        raise ValueError('ADDITION_RESOURCE_UNITS')
    ore,grade=selected['ore_mt']['value'],selected['grade']['value']
    contained=selected['contained_treo_kt']['value'] if 'contained_treo_kt' in selected else ore*grade*.001
    if float(row['礦石蘊藏量_Mt'])!=ore or float(row['TREO品位_pct'])*10000!=grade or not math.isclose(float(row['總TREO蘊藏量_kt']),contained,rel_tol=0,abs_tol=1e-9):
        raise ValueError('ADDITION_CURRENT_VALUE_CONFLICT')
    return ore,grade,ids,native[0]


def verify_single_oxide(row,trace,db,entry,roots):
    """Exact already-selected PDF total, with rendered row/column intersection."""
    import pymupdf
    from .project_summary import ELEMENTS
    ore,grade,ids,native=matching_resource(row,trace,db,entry)
    pdf=entry['pdf'];root=Path(roots[pdf['asset_set']]).resolve();path=(root/pdf['path']).resolve()
    if not path.is_relative_to(root) or filehash(path)!=entry['selected_source_sha256'] or pdf['sha256']!=entry['selected_source_sha256']:
        raise ValueError('ADDITION_SAME_SELECTED_PDF_REQUIRED')
    compact=lambda t:re.sub(r'\s+','',t).casefold()
    with pymupdf.open(path) as doc:
        page=doc[pdf['page']-1];text=page.get_text(sort=True)
        if hashlib.sha256(page.get_pixmap(matrix=pymupdf.Matrix(1.5,1.5)).samples).hexdigest()!=pdf['render_sha256']:
            raise ValueError('ADDITION_RENDER_CHANGED')
        if any(compact(m) not in compact(text) for m in entry['same_version_markers']):
            raise ValueError('ADDITION_NATIVE_SCOPE_VERSION_PROOF')
        cell=entry['cell_binding'];rect=pymupdf.Rect(cell['bbox'])
        if not page.rect.contains(rect) or page.get_text(clip=rect).strip()!=cell['original_token']:
            raise ValueError('ADDITION_OXIDE_NATIVE_CELL')
        header=pymupdf.Rect(cell['header_bbox']);label=pymupdf.Rect(cell['row_label_bbox'])
        if not all(page.rect.contains(b) for b in (header,label)) or rect.x0<header.x0 or rect.x1>header.x1 or abs(rect.y0-label.y0)>2:
            raise ValueError('ADDITION_OXIDE_COLUMN_ROW_INTERSECTION')
        if compact(cell['header_marker']) not in compact(page.get_text(clip=header)) or page.get_text(clip=label).strip()!='Total':
            raise ValueError('ADDITION_OXIDE_HEADER_OR_TOTAL_LABEL')
    if cell['oxide']!='Y2O3' or cell['unit']!='ppm bulk ore' or cell['original_token']!='1,400':
        raise ValueError('ADDITION_OXIDE_REVIEWED_CONTRACT')
    if any(next(v for k,v in row.items() if k.startswith(o+'_'))!='' for o in ELEMENTS if o!='Y2O3'):
        raise ValueError('ADDITION_PARTIAL_SUM_OTHER_ELEMENTS_REQUIRE_REVIEW')
    ppm=float(cell['original_token'].replace(',',''));value=ore*ppm*.001
    if row['Y2O3_氧化釔_kt']!='' and not math.isclose(float(row['Y2O3_氧化釔_kt']),value,rel_tol=0,abs_tol=1e-9):
        raise ValueError('ADDITION_EXISTING_OXIDE_CONFLICT')
    scope=canonical(dict(resource_scope=entry['scope'],statement_id=entry['statement_id'],category=entry['category'],
        effective_date_inherited_from_canonical=entry['effective_date'],native_date_precision='YEAR',native_year='2017',
        source_sha256=entry['selected_source_sha256'],pdf=pdf,cell_binding=cell,
        original_values={'ore_mt':ore,'y2o3_ppm':ppm},formula='Mt * bulk-ore oxide ppm * 0.001 = kt',
        treo_basis='Native TREO7400ppm excludes Y2O3; existing canonical8800ppm includes1400ppmY2O3. No changes to original grade or provenance.',
        cutoff='Same selected source/table/resource total; no cross-document cutoff transfer',
        rounding='Ore rounded to0.01Mt; oxide rounded to100ppm; not full15-oxide closure',
        underlying_resource_provenance=native))
    values=[('Y2O3_氧化釔_kt',value,'DERIVED_SAME_SOURCE_TOTAL_ORE_MT_X_Y2O3_PPM_X_0_001'),
        ('已公布元素數_共15項',1,'DERIVED_COUNT_VERIFIED_MATCHED_INDIVIDUAL_OXIDES'),
        ('已公布元素總和_kt',value,'DERIVED_SUM_AVAILABLE_MATCHED_OXIDES_NOT_TOTAL_RESOURCE'),
        ('元素總和/TREO',value/float(row['總TREO蘊藏量_kt']),'DERIVED_AVAILABLE_OXIDE_SUM_DIVIDED_BY_MATCHED_TREO'),
        ('元素數據一致性檢查','已核實同範圍Y2O3；部分元素，未進行完整15項閉合檢查','SOURCE_REVIEWED_PARTIAL_OXIDE_DISCLOSURE')]
    return [dict(column=c,value=v,method=m,scope=scope,source_sha256=entry['selected_source_sha256'],source_url=native['source_url'],
        locator='physical PDF p26 Table2 Total row / Y2O3(ppm) column',observation_ids=canonical(ids),review_id=entry['review_id'])
        for c,v,m in values if row[c]=='']
