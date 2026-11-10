import copy
import pymupdf
import pytest
from au_ree_v2.source_cells import validate_cell


def table():
    doc=pymupdf.open();p=doc.new_page()
    for xy,text in [((30,30),'Resource'),((30,50),'Dated global resource'),
                    ((200,75),'Tonnes'),((200,90),'(000)'),((30,115),'Total'),((200,115),'379,421')]:
        p.insert_text(xy,text,fontsize=8)
    def box(text):
        r=p.search_for(text)[0]
        return [r.x0-.1,r.y0-.1,r.x1+.1,r.y1+.1]
    b=dict(mode='native_cell',field='ore_mt',basis='TREO',scope='global',page=1,original_unit='kt',
        table_bbox=[20,15,300,130],row_bbox=[20,103,300,120],column_bbox=[195,15,250,130],
        row_label='Total',row_label_bbox=box('Total'),column_label='Tonnes',column_label_bbox=box('Tonnes'),
        unit_label='(000)',unit_bbox=box('(000)'),table_label='Resource',table_label_bbox=box('Resource'),
        scope_anchor='Dated global resource',scope_anchor_bbox=box('Dated global resource'),section_id='global')
    s={'global':dict(page=1,bbox=b['table_bbox'],anchor=b['scope_anchor'],anchor_bbox=b['scope_anchor_bbox'])}
    return doc,b,s


def test_thousand_tonnes_header_is_kt_mass():
    d,b,s=table()
    with d:
        assert validate_cell(d,b,'ore_mt','379,421','kt','global',selected_sections=s)=='NATIVE_TABLE_ROW_COLUMN_CELL_BINDING'


@pytest.mark.parametrize('field,unit',[('grade','ppm'),('ore_mt','Mt'),('contained_treo_kt','kt')])
def test_thousand_header_cannot_supply_grade_million_tonnes_or_contained_reo(field,unit):
    d,b,s=table();b=copy.deepcopy(b);b.update(field=field,original_unit=unit)
    with d,pytest.raises(ValueError,match='SOURCE_UNIT_SEMANTICS'):
        validate_cell(d,b,field,'379,421',unit,'global',selected_sections=s)
