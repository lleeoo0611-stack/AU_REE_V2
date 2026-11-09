"""Source-bound modeled annual TREO x Base Case Nd/Pr composition.

A narrowly opt-in cross-table model calculation, not a reported component
forecast and not actual production. Resource assays cannot serve as shares.
"""
import math,re
from .source_cells import norm,region_text,validate_cell
from .technical_tables import number_token

METHOD='MODEL_ANNUAL_TREO_X_BASE_CASE_NDPR_SHARE'
PROFILE='JUPITER_SCOPING_BASE_CASE_MREC_TABLES_4_2_5_3'

def validate_model_annual_derivation(doc,review,study,spec,result,evidence):
    import pymupdf
    def fail(code):raise ValueError('REVIEW_MODEL_ANNUAL_'+code)
    def number(v):return not isinstance(v,bool) and isinstance(v,(int,float)) and math.isfinite(v)
    if (spec.get('method')!=METHOD or spec.get('profile')!=PROFILE or study.get('selected_scenario')!='Base Case'
        or study.get('endpoint')!='MREC' or study.get('scale')!='SCOPING_MODEL' or
        spec.get('assurance')!='MODEL_ASSUMPTION_DERIVED_NOT_DIRECT_REPORTED_OUTPUT'):
        fail('PROFILE_PRODUCT_SCENARIO_REQUIRED')
    contract={k:review[k] for k in ('source_sha256','statement_id','scope','effective_date')}
    if any(spec.get(k)!=v for k,v in contract.items()):fail('SOURCE_SCOPE_DATE_MISMATCH')
    inputs=spec.get('inputs',[])
    if len(inputs)!=3 or {i.get('name') for i in inputs}!={'annual_treo_t','nd_percent_of_treo','pr_percent_of_treo'}:fail('THREE_INPUTS_REQUIRED')
    items={i['name']:i for i in inputs}
    def rect(page,raw):
        if not isinstance(raw,list) or len(raw)!=4 or not all(number(v) for v in raw):fail('RECT_REQUIRED')
        box=pymupdf.Rect(raw)
        if box.is_empty or not page.rect.contains(box):fail('RECT_OUTSIDE_PAGE')
        return box
    def proof(name):
        p=spec.get(name,{})
        pn=p.get('page')
        if isinstance(pn,bool) or not isinstance(pn,int) or not 1<=pn<=len(doc):fail('PROOF_PAGE_REQUIRED')
        if p.get('evidence',{}).get('page')!=pn:fail('EVIDENCE_PAGE_MISMATCH')
        evidence(p['evidence']);actual=norm(region_text(doc[pn-1],rect(doc[pn-1],p.get('bbox'))))
        if actual!=norm(p.get('text','')):fail('PROOF_TEXT_MISMATCH')
        return pn,actual
    annual_page,annual_text=proof('annual_model_proof')
    if not all(t in annual_text for t in ('the base case reflects the metallurgical recovery and production assumptions adopted in the scoping study financial model','base case annual production represents the life-of-mine annual average and includes ramp-up and scheduling effects')):fail('LOM_MODEL_PROOF_REQUIRED')
    comp_page,comp_text=proof('composition_model_proof')
    if not all(t in comp_text for t in ('the distribution of the four principal magnet rare earth oxides and yttrium in the base case mrec is','presented in table 5.3.')):fail('COMPOSITION_MODEL_PROOF_REQUIRED')
    origin_page,origin_text=proof('composition_origin_proof')
    if origin_page!=comp_page or not origin_text.startswith('the base case mrec composition is based on the high-grade mrec produced by'):fail('COMPOSITION_ORIGIN_REQUIRED')
    if annual_page!=study.get('annual_basis_evidence',{}).get('page') or comp_page!=annual_page+1:fail('MODEL_TABLE_SEQUENCE_MISMATCH')
    tables=[];values={};widths={}
    for name,item in items.items():
        if any(item.get(k)!=v for k,v in contract.items()):fail('INPUT_SOURCE_SCOPE_DATE_MISMATCH')
        v=item.get('value');token=item.get('original_token');parsed=number_token(token)
        if not number(v) or v<=0 or not parsed or parsed.get('value')!=v:fail('TOKEN_VALUE_MISMATCH')
        e=item.get('evidence',{});evidence(e)
        b=item.get('cell_binding',{})
        if b.get('mode')!='native_cell' or b.get('scope')!=review['scope'] or b.get('page')!=e.get('page'):fail('INPUT_NATIVE_BINDING_REQUIRED')
        width=item.get('rounding_half_width');t=str(token).replace(',','');minwidth=.5*10**(-len(t.split('.')[1]) if '.' in t else 0)
        if not number(width) or width<minwidth or width>=v:fail('ROUNDING_INTERVAL_REQUIRED')
        if name=='annual_treo_t':
            if item.get('unit')!='tpa' or b.get('page')!=annual_page or b.get('column_label')!='Base Case' or b.get('row_label')!='Average annual contained TREO in MREC':fail('ANNUAL_PRODUCT_SCENARIO_MISMATCH')
            if study.get('parameters',{}).get('average_annual_treo_product_t')!=v or study.get('parameter_bindings',{}).get('average_annual_treo_product_t')!=b:fail('SELECTED_ANNUAL_TREO_MISMATCH')
            validate_cell(doc,b,'average_annual_treo_product_t',token,'tpa',review['scope'],'Base Case')
        else:
            oxide='Nd2O3' if name=='nd_percent_of_treo' else 'Pr6O11'
            if item.get('basis')!=oxide or item.get('unit')!='%TREO' or v>100 or b.get('page')!=comp_page:fail('OXIDE_SHARE_BASIS_MISMATCH')
            page=doc[comp_page-1];table=rect(page,b.get('table_bbox'));row=rect(page,b.get('row_bbox'));column=rect(page,b.get('column_bbox'))
            cell=row&column
            if not table.contains(row) or not table.contains(column) or cell.is_empty or row.height>=table.height or column.width>=table.width:fail('SHARE_REGION_MISMATCH')
            def anchor(key,label,container):
                box=rect(page,b.get(key));actual=norm(region_text(page,box))
                if not container.contains(box) or actual.translate(str.maketrans('₀₁₂₃₄₅₆₇₈₉','0123456789'))!=norm(label).translate(str.maketrans('₀₁₂₃₄₅₆₇₈₉','0123456789')):fail('SHARE_ANCHOR_MISMATCH')
                return box
            anchor('table_label_bbox','Table 5.3 | Key Rare Earth Distribution in MREC',table)
            head=anchor('column_label_bbox','% of contained TREO',column)
            label='Neodymium (Nd₂O₃)' if oxide=='Nd2O3' else 'Praseodymium (Pr₆O₁₁)'
            anchor('row_label_bbox',label,row)
            if head.y1>row.y0:fail('SHARE_ROW_OUTSIDE_HEADER')
            actual=norm(region_text(page,cell));p=number_token(actual)
            if not re.fullmatch(r'\d+(?:\.\d+)?',actual) or not p or p['value']!=v:fail('SHARE_CELL_TOKEN_MISMATCH')
            tables.append((tuple(b['table_bbox']),tuple(b['column_bbox'])))
        values[name]=v;widths[name]=width
    if len(set(tables))!=1:fail('SHARE_TABLE_MISMATCH')
    share=values['nd_percent_of_treo']+values['pr_percent_of_treo']
    if share>100:fail('SHARE_SUM_EXCEEDS_100')
    expected=values['annual_treo_t']*share/100
    if not number(result) or not math.isclose(expected,result,rel_tol=1e-12,abs_tol=1e-9):fail('RESULT_MISMATCH')
    half=widths['nd_percent_of_treo']+widths['pr_percent_of_treo']
    interval=[(values['annual_treo_t']-widths['annual_treo_t'])*(share-half)/100,(values['annual_treo_t']+widths['annual_treo_t'])*(share+half)/100]
    if len(spec.get('rounding_interval_tpa',[]))!=2 or any(not number(a) or not math.isclose(a,b,rel_tol=1e-12) for a,b in zip(spec['rounding_interval_tpa'],interval)):fail('RESULT_ROUNDING_INTERVAL_MISMATCH')
    return expected
