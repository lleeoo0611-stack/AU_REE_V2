"""One explicit oxide subtraction from the same selected native resource row."""
import math
import pymupdf
from .source_cells import norm, region_text
from .technical_tables import number_token

METHOD='DERIVED_SAME_ROW_TREO_MINUS_TREO_EX_CEO2_FROM_ROUNDED_REPORTED_INPUTS'


def validate_oxide_difference(doc,binding,field,token,unit,scope,selected_sections):
    from .source_cells import validate_cell
    def fail(code):raise ValueError('REVIEW_OXIDE_DIFFERENCE_'+code)
    if field!='reported_resource_ce_ppm' or binding.get('basis')!='CeO2' or unit!='ppm':fail('FIELD_BASIS_UNIT')
    if binding.get('derivation_method')!='TREO_PPM_MINUS_TREO_EX_CEO2_PPM':fail('METHOD')
    page=doc[binding['page']-1]
    bounds=page.rect*page.derotation_matrix
    def rect(values):
        if (not isinstance(values,list) or len(values)!=4 or any(isinstance(x,bool) or not isinstance(x,(int,float)) or not math.isfinite(x) for x in values)):fail('RECT')
        r=pymupdf.Rect(values)
        if r.is_empty or r.is_infinite or not bounds.contains(r):fail('RECT')
        return r
    table=rect(binding['table_bbox']);row=rect(binding['row_bbox']);label=rect(binding['row_label_bbox'])
    section=(selected_sections or {}).get(binding['section_id'],{})
    if (binding.get('row_label')!='Total' or norm(section.get('row_label',''))!='total'
            or list(section.get('bbox',[]))!=list(binding['table_bbox']) or not table.contains(row)
            or not row.contains(label) or norm(region_text(page,label))!='total'):fail('SELECTED_TOTAL_ROW')
    source=binding['input_treo'];other=binding['input_treo_ex_ceo2']
    if (source.get('mode')!='native_cell' or source.get('page')!=binding['page'] or source.get('section_id')!=binding['section_id']
            or source.get('row_bbox')!=binding['row_bbox'] or source.get('table_bbox')!=binding['table_bbox']
            or source.get('row_label')!='Total' or source.get('column_label')!='TREO'
            or source.get('original_unit')!='ppm'):fail('SAME_SOURCE_ROW')
    a=number_token(binding['treo_token']);b=number_token(other['token']);result=number_token(token)
    if not a or not b or not result or any(x.get('value') is None for x in [a,b,result]):fail('NUMBER')
    validate_cell(doc,source,'grade',binding['treo_token'],'ppm',scope,selected_sections=selected_sections)
    column=rect(other['column_bbox']);header=rect(other['column_label_bbox']);units=rect(other['unit_bbox'])
    if (not table.contains(column) or not column.contains(header) or not column.contains(units)
            or header.y1>row.y0 or units.y1>row.y0
            or norm(region_text(page,header))!='treo-ceo2'
            or norm(region_text(page,units))!='(ppm)'):fail('EXCLUSION_COLUMN')
    if not (column & rect(source['column_bbox'])).is_empty:fail('OVERLAPPING_COLUMNS')
    parsed=number_token(norm(region_text(page,column & row)))
    if not parsed or parsed['value']!=b['value']:fail('EXCLUSION_NATIVE_TOKEN')
    definition=norm(region_text(page,rect(binding['definition_bbox'])))
    if definition!='treo-ceo2 = treo grade minus ceo2':fail('EXPLICIT_DEFINITION')
    difference=a['value']-b['value']
    if not 0<=b['value']<=a['value']<=1000000 or not math.isclose(difference,result['value'],rel_tol=1e-12,abs_tol=1e-10):fail('RESULT')
    return METHOD
