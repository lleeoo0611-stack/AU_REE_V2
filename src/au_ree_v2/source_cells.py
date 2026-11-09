"""Fail-closed source-cell checks for reviewed native tables and image transcripts.

A page hash authenticates bytes, not a transcription. Native cells are read from
an intersection of an explicitly selected row and semantic column. Raster cells
remain reviewed transcriptions, explicitly labelled as such in output provenance.
"""
import hashlib
import math
import re


def norm(text):
    return re.sub(r'\s+', ' ', text).strip().casefold()


def region_text(page, rect):
    """Select complete words by centre; textbox clipping can leak glyph fragments."""
    words = [w for w in page.get_text('words', sort=True)
             if rect.x0 <= (w[0]+w[2])/2 <= rect.x1 and rect.y0 <= (w[1]+w[3])/2 <= rect.y1]
    return ' '.join(w[4] for w in words)


def image_crop_hash(page, rect):
    """Hash fixed pixels from a full-page rendering, avoiding clip rounding drift."""
    import pymupdf
    pix = page.get_pixmap(matrix=pymupdf.Matrix(2, 2))
    left, top = math.floor(rect.x0*2), math.floor(rect.y0*2)
    right, bottom = math.ceil(rect.x1*2), math.ceil(rect.y1*2)
    pixels = pix.samples
    h = hashlib.sha256(f'{right-left},{bottom-top},{pix.n};'.encode())
    for y in range(top, bottom):
        h.update(pixels[y*pix.stride+left*pix.n:y*pix.stride+right*pix.n])
    return h.hexdigest()


def validate_cell(doc, binding, field, token, unit, scope, selected_scenario=None, selected_sections=None):
    import pymupdf
    from .technical_tables import number_token

    def fail(code):
        raise ValueError('REVIEW_CELL_' + code)

    if not binding:
        fail('BINDING_REQUIRED')
    if binding.get('field') != field or binding.get('scope') != scope:
        fail('FIELD_OR_SCOPE_MISMATCH')
    page_no = binding.get('page')
    if not isinstance(page_no, int) or not 1 <= page_no <= len(doc):
        fail('PAGE_INVALID')
    if field.startswith('reported_resource_'):
        from .project_summary import ELEMENTS
        expected = {'reported_resource_'+re.match(r'[A-Z][a-z]?',e)[0].lower()+'_ppm':e for e in ELEMENTS}.get(field)
        if field=='reported_resource_magnet_ppm':expected='PrNdDyTb_OXIDES'
        if not expected or binding.get('basis') != expected:
            fail('OXIDE_FIELD_BASIS_MISMATCH')
    page = doc[page_no - 1]
    # Native text coordinates are unrotated even for rotated PDF pages.
    page_bounds = page.rect * page.derotation_matrix if binding.get('mode') != 'reviewed_image_cell' else page.rect

    def rect(key):
        raw = binding.get(key)
        if not isinstance(raw, list) or len(raw) != 4 or any(
            not isinstance(v, (int, float)) or not math.isfinite(v) for v in raw
        ):
            fail('RECT_INVALID')
        r = pymupdf.Rect(raw)
        if r.is_empty or r.is_infinite or not page_bounds.contains(r):
            fail('RECT_OUTSIDE_PAGE')
        return r

    if field=='reported_resource_magnet_ppm':
        definition=norm(region_text(page,rect('group_definition_bbox')))
        exact='Total permanent magnet REO (MREO) = Total permanent magnet REOs (Pr6O11 + Nd2O3 + Tb4O7 + Dy2O3)'
        if unit!='ppm' or definition!=norm(exact):fail('MAGNET_GROUP_DEFINITION_REQUIRED')
    mode = binding.get('mode')
    if not field.startswith('average_annual_'):
        section = (selected_sections or {}).get(binding.get('section_id'))
        if not section or section.get('page') != page_no:
            fail('SELECTED_SECTION_REQUIRED')
        selected = pymupdf.Rect(section['bbox'])
        if not selected.contains(rect('row_bbox')):
            fail('ROW_OUTSIDE_SELECTED_SECTION')
        if mode == 'native_cell':
            anchor_rect = pymupdf.Rect(section['anchor_bbox'])
            if (not selected.contains(anchor_rect) or not page_bounds.contains(selected) or
                    norm(region_text(page,anchor_rect)) != norm(section['anchor']) or anchor_rect.y1 > rect('row_bbox').y0):
                fail('SELECTED_SECTION_ANCHOR_MISMATCH')
        elif mode == 'reviewed_image_cell' and section.get('mode') != 'reviewed_image_section':
            fail('IMAGE_SECTION_REVIEW_REQUIRED')
        cutoff_group = section.get('cutoff_group')
        if cutoff_group:
            # A vertically merged cutoff label can sit beside Unclassified,
            # below the selected Inferred row. Bind the whole three-row group
            # plus the exact class row, never borrow a nearby cutoff label.
            if mode != 'native_cell' or norm(section.get('row_label','')) != 'inferred':
                fail('CUTOFF_GROUP_NATIVE_INFERRED_REQUIRED')
            def group_rect(key):
                values = cutoff_group.get(key)
                if (not isinstance(values,list) or len(values)!=4 or
                    any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) for v in values)):
                    fail('CUTOFF_GROUP_RECT_INVALID')
                box=pymupdf.Rect(values)
                if box.is_empty or box.is_infinite or not page_bounds.contains(box):
                    fail('CUTOFF_GROUP_RECT_INVALID')
                return box
            group=group_rect('bbox');cutoff_label=group_rect('label_bbox')
            cutoff_column=group_rect('column_bbox');cutoff_header=group_rect('header_bbox')
            table=rect('table_bbox')
            if (not table.contains(group) or not group.contains(rect('row_bbox')) or not group.contains(cutoff_label) or
                not table.contains(cutoff_column) or not cutoff_column.contains(cutoff_label) or
                not cutoff_column.contains(cutoff_header) or cutoff_header.y1>group.y0):
                fail('CUTOFF_GROUP_BINDING_MISMATCH')
            label=norm(region_text(page,cutoff_label))
            if (label!=norm(cutoff_group.get('label','')) or not re.fullmatch(r'\d[\d,]*(?:\.\d+)?',label) or
                norm(region_text(page,cutoff_header))!=norm(cutoff_group.get('header_label','')) or
                norm(cutoff_group.get('header_label',''))!='cut off treo+y2o3'):
                fail('CUTOFF_GROUP_LABEL_OR_HEADER_MISMATCH')
            classes=[word.casefold() for word in region_text(page,group).split()
                     if word.casefold() in ('inferred','unclassified','total')]
            if classes!=['inferred','unclassified','total']:
                fail('CUTOFF_GROUP_CLASS_ROWS_MISMATCH')
    if mode == 'native_statement':
        statement = norm(page.get_textbox(rect('statement_bbox')))
        if statement != norm(binding.get('statement', '')):
            fail('STATEMENT_MISMATCH')
        prefix, suffix = norm(binding.get('before', '')), norm(binding.get('after', ''))
        match = re.fullmatch(re.escape(prefix) + r'\s*([\d,]+(?:\.\d+)?)\s*' + re.escape(suffix), statement)
        wanted = number_token(str(token))
        if not match or not wanted or number_token(match[1])['value'] != wanted['value']:
            fail('STATEMENT_TOKEN_MISMATCH')
        if field=='average_annual_ndpr_product_t':
            if prefix!='nd-pr contained in rec' or suffix!='tpa' or unit!='tpa':fail('STATEMENT_SEMANTICS_MISMATCH')
            time_basis=norm(region_text(page,rect('time_basis_bbox')))
            if time_basis!='operations metrics (life-of-mine annual average)':fail('STATEMENT_ANNUAL_BASIS_MISMATCH')
            proof=binding.get('oxide_basis_proof',{})
            pn=proof.get('page');box=proof.get('bbox')
            if not isinstance(pn,int) or not 1<=pn<=len(doc) or not isinstance(box,list) or len(box)!=4:
                fail('STATEMENT_OXIDE_BASIS_REQUIRED')
            region=pymupdf.Rect(box)
            if not doc[pn-1].rect.contains(region):fail('STATEMENT_OXIDE_BASIS_REQUIRED')
            exact='Nd-Pr, Dy and Tb production figures are life-of-mine annual average calculated by multiplying REC production by TREO grade and its respective rare earth oxide composition as a % of TREO'
            if norm(region_text(doc[pn-1],region))!=norm(exact):fail('STATEMENT_OXIDE_BASIS_REQUIRED')
        elif (field != 'average_annual_treo_product_t' or 'annual' not in prefix or
              not suffix.startswith('tpa of contained treo in concentrate') or unit != 'tpa'):
            fail('STATEMENT_SEMANTICS_MISMATCH')
        return 'NATIVE_SCOPED_STATEMENT_BINDING'
    table, row, column = rect('table_bbox'), rect('row_bbox'), rect('column_bbox')
    if not table.contains(row) or not table.contains(column):
        fail('OUTSIDE_TABLE')
    cell = row & column
    if cell.is_empty or row.height >= table.height or column.width >= table.width:
        fail('AMBIGUOUS_REGION')
    transposed = binding.get('resource_orientation') == 'oxide_rows'
    if transposed and (not field.startswith('reported_resource_') or mode != 'native_cell'):
        fail('RESOURCE_ORIENTATION_UNSUPPORTED')
    if not field.startswith('average_annual_'):
        if transposed:
            if norm(binding.get('column_label','')) != norm(section.get('category_label','total')):
                fail('RESOURCE_TOTAL_COLUMN_REQUIRED')
        elif norm(binding.get('row_label','')) != norm(section.get('row_label','total')):
            fail('RESOURCE_TOTAL_ROW_REQUIRED')
    if binding.get('original_unit') != unit:
        fail('UNIT_MISMATCH')

    # Never silently fall back to page-level matching for an image or a failed
    # native extraction. Reviewed image transcripts have a different assurance.
    if mode == 'reviewed_image_cell':
        if not binding.get('review_note'):
            fail('IMAGE_REVIEW_REQUIRED')
        expected = binding.get('reviewed_token')
        if expected != str(token):
            fail('IMAGE_TRANSCRIPTION_MISMATCH')
        if image_crop_hash(page, cell) != binding.get('cell_render_sha256'):
            fail('IMAGE_CROP_MISMATCH')
        if not binding.get('column_label') or not binding.get('row_label') or not binding.get('table_label'):
            fail('IMAGE_LABELS_REQUIRED')
        return 'REVIEWED_IMAGE_CELL_TRANSCRIPTION_NOT_INDEPENDENT_OCR'
    if mode != 'native_cell':
        fail('MODE_UNSUPPORTED')

    def anchor(box_key, text_key, container):
        box = rect(box_key)
        if not container.contains(box):
            fail('ANCHOR_OUTSIDE_REGION')
        expected = binding.get(text_key)
        actual = norm(region_text(page, box))
        if not expected or actual != norm(expected):
            fail('ANCHOR_MISMATCH')
        return actual

    anchor('table_label_bbox', 'table_label', table)
    if not field.startswith('average_annual_'):
        anchor('scope_anchor_bbox','scope_anchor',table)
        if rect('scope_anchor_bbox').y1 > row.y0:
            fail('ROW_OUTSIDE_SELECTED_SCOPE')
    label = anchor('column_label_bbox', 'column_label', column)
    anchor('row_label_bbox', 'row_label', row)
    forecast = field.startswith('average_annual_')
    unit_container = table if forecast else column
    if binding.get('unit_scope_bbox'):
        unit_container = rect('unit_scope_bbox')
        if not table.contains(unit_container) or not unit_container.contains(column):
            fail('SHARED_UNIT_SCOPE_MISMATCH')
    source_unit = anchor('unit_bbox', 'unit_label' if 'unit_label' in binding else 'original_unit', unit_container)
    source_unit = source_unit.strip('()')
    if source_unit == 'million' and unit == 'Mt': source_unit = 'mt'
    if source_unit == 'm tonnes' and unit == 'Mt': source_unit = 'mt'
    if source_unit == 'tonnes' and unit == 't': source_unit = 't'
    if source_unit == "'000 t" and unit == 'kt': source_unit = 'kt'
    if unit == '%HM' and source_unit == '% of total hm': source_unit = '%hm'
    if unit == '%TREO':
        if source_unit!='percentage proportion of treo in the mineral resources':
            context=anchor('metric_context_bbox','metric_context',table)
            if source_unit!='percentage' or context!='percentage proportion of treo in the mineral resources':
                fail('RESOURCE_SHARE_DENOMINATOR_REQUIRED')
        source_unit='%treo'
    if source_unit != norm(unit): fail('SOURCE_UNIT_SEMANTICS_MISMATCH')
    if forecast and (not selected_scenario or label != norm(selected_scenario)):
        fail('FORECAST_SCENARIO_MISMATCH')
    if forecast and binding.get('forecast_orientation') == 'product_rows':
        if not column.contains(rect('unit_bbox')): fail('UNIT_OUTSIDE_FORECAST_COLUMN')
    elif forecast and not row.contains(rect('unit_bbox')):
        fail('UNIT_OUTSIDE_FORECAST_ROW')
    # Field-to-header semantics, independent of the declared numeric token.
    if field == 'ore_mt':
        valid = label in ('material', 'tonnes', 'tonnage') and source_unit in ('mt', 'kt', 't')
    elif field == 'bulk_hm_percent':
        valid = label == 'hm' and source_unit == '%'
    elif field in ('grade', 'contained_treo_kt'):
        valid = label.strip('()') in ('treo','treo*','treo1','treo +','contained treo','total reo') and source_unit in (('ppm', '%', '%hm') if field == 'grade' else ('kg','t', 'kt','kt treo'))
    elif field.startswith('reported_resource_'):
        # The binding must identify the exact oxide, including stoichiometry.
        valid = label == norm(binding.get('basis', '')) and source_unit in ('ppm','%','%hm')
        if binding.get('resource_orientation')=='oxide_rows':
            valid=(source_unit=='%treo' and label=='total' and
                   norm(binding.get('row_label',''))==norm(binding.get('basis','')))
        if field=='reported_resource_magnet_ppm':valid=label=='mreo' and source_unit=='ppm'
    elif field.startswith('annual_input_'):
        # An annual product forecast may be converted to contained oxides only
        # from the selected product row, with independent mass/grade/%TREO cells.
        if field=='annual_input_annual_product_t':
            valid=label=='annual forecast reec production' and source_unit=='t'
        elif field=='annual_input_treo_percent':
            valid=label=='treo' and source_unit=='%'
        elif field in ('annual_input_nd_percent_of_treo','annual_input_pr_percent_of_treo'):
            context=anchor('metric_context_bbox','metric_context',table)
            expected='nd2o3' if field=='annual_input_nd_percent_of_treo' else 'pr6o11'
            valid=label==expected and source_unit=='%' and context=='as a % of treo'
        else:valid=False
        if not re.fullmatch(r'\d{4} reec product',norm(binding.get('row_label',''))):fail('ANNUAL_PRODUCT_ROW_MISMATCH')
    else:
        # Forecast tables orient metric labels on rows and scenarios on columns.
        metric = norm(binding.get('row_label', ''))
        context = ''
        if binding.get('metric_context_bbox'):
            context = anchor('metric_context_bbox','metric_context',table)
        if binding.get('forecast_orientation') == 'product_rows':
            target_row = 'total' if field == 'average_annual_treo_product_t' else 'ndpr oxide' if field == 'average_annual_ndpr_product_t' else None
            valid_product = (metric == target_row and label == 'average reo*' and source_unit == 't' and
                context.startswith('* average production is calculated as the arithmetic annual average') and
                'ramp up' in context and 'low grade stockpiles' in context)
            if not valid_product: fail('PRODUCT_FORECAST_SEMANTICS_MISMATCH')
            metric = ('average annual production treo' if field == 'average_annual_treo_product_t' else 'average annual production ndpr')
        elif context:
            if context != 'average annual production target': fail('FORECAST_METRIC_CONTEXT_MISMATCH')
            metric += ' '+context
        target = {'average_annual_treo_product_t': 'treo',
                  'average_annual_ndpr_product_t': 'ndpr',
                  'average_annual_hreo_product_t': 'hreo'}.get(field)
        valid = bool(target and re.search(r'\b'+target+r'\b',metric) and
                     ('annual' in metric or 'average' in metric) and
                     re.search(r'production|output|contained',metric) and
                     not re.search(r'grade|recovery|feed|price|cost',metric) and source_unit in ('t','tpa'))
    if not valid:
        fail('HEADER_SEMANTICS_MISMATCH')
    actual = norm(region_text(page, cell))
    if field.startswith('annual_input_') and unit=='%' and re.fullmatch(r'[+\-]?\d[\d,]*(?:\.\d+)?%',actual):
        actual=actual[:-1]
    # Whole-cell equality rejects borrowed numbers, substrings and extra values.
    parsed = number_token(actual)
    wanted = number_token(str(token))
    if (not parsed or not wanted or parsed.get('value') is None or
            not re.fullmatch(r'[+\-]?\d[\d,]*(?:\.\d+)?', actual) or
            parsed['value'] != wanted['value']):
        fail('TOKEN_MISMATCH')
    return 'NATIVE_TABLE_ROW_COLUMN_CELL_BINDING'
