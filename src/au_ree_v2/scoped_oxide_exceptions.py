"""Source-bound, researcher-gated exceptions for two exact resource statements.

The existing partial-resource mode remains unchanged. This module reads additional
native cells only after the ordinary review validator and selected bundle agree.
No source review is mutated and no derived value is inserted as a native assay.
"""
import copy
import json
from decimal import Decimal
from pathlib import Path

CE = Decimal('140.116')
O = Decimal('15.999')
CONVERSION_MODE = 'CERIUM_STOICHIOMETRIC_CONVERSION'
SPLINTER = ('AU-574465211976ec57b1ef', 'splinter-inferred500-r254-20151109', '428c8f759ec2f4dc393177f0fccce12cc96c9b1359638d003f7ea30b6d388df7')
CIRCLE = ('AU-785536db5ff12c25350d', 'circle_valley_global_202306', '259ebe012c6b6e2048ca2f50f5b47e4c91d9a56e520c97f6deee554d069a54ad')
RULES = {SPLINTER[0]: 'CE2O3_TO_CEO2_STOICHIOMETRIC', CIRCLE[0]: 'ACCEPT_SOURCE_COMBINED_NDPR_OXIDE'}
DERIVED_CHANGE_COLUMNS = frozenset(('已公布元素數_共15項','已公布元素總和_kt','元素總和/TREO','元素數據一致性檢查'))


def decision_rows(value):
    if value is None: return []
    if isinstance(value, (str, Path)):
        value = json.loads(Path(value).read_text(encoding='utf-8'))
    rows = value.get('decisions', []) if isinstance(value, dict) else value
    if not isinstance(rows, list): raise ValueError('RESEARCHER_DECISIONS_LIST_REQUIRED')
    return rows


def approved_decision(decisions, identity):
    rows = [d for d in decision_rows(decisions) if isinstance(d, dict) and d.get('rule') == RULES[identity[0]] and d.get('project_id') == identity[0]]
    active = [d for d in rows if isinstance(d.get('decided_by'), str) and d['decided_by'].strip()]
    if not active: return None
    if len(active) != 1: raise ValueError('SCOPED_EXCEPTION_AMBIGUOUS_DECISION')
    d = active[0]
    scope = d.get('scope')
    sid = scope.get('statement_id') if isinstance(scope, dict) else scope
    if sid != identity[1] or not d.get('decision_id') or not d.get('decided_date'):
        raise ValueError('SCOPED_EXCEPTION_EXACT_DECISION_SCOPE_REQUIRED')
    if isinstance(scope, dict) and scope.get('source_sha256', identity[2]) != identity[2]:
        raise ValueError('SCOPED_EXCEPTION_DECISION_SHA_MISMATCH')
    return d


def cerium_factors():
    return {'Ce': float(CE), 'O': float(O),
            'ce2o3_element_ratio': float((2*CE+3*O)/(2*CE)),
            'ce2o3_to_ceo2': float(2*(CE+2*O)/(2*CE+3*O))}


def _column(doc, binding, label, header_y, unit_y):
    """Bind one native header, ppm unit and one token to the selected exact row."""
    import pymupdf
    from .source_cells import region_text, norm
    from .technical_tables import number_token
    page = doc[binding['page']-1]
    row = pymupdf.Rect(binding['row_bbox'])
    table = pymupdf.Rect(binding['table_bbox'])
    words = page.get_text('words')
    headers = sorted([w for w in words if header_y[0] <= (w[1]+w[3])/2 <= header_y[1] and table.x0 <= (w[0]+w[2])/2 <= table.x1], key=lambda w:w[0])
    matches = [i for i,w in enumerate(headers) if w[4] == label]
    if len(matches)!=1: raise ValueError('SCOPED_EXCEPTION_UNIQUE_HEADER_REQUIRED:'+label)
    i=matches[0]; h=headers[i]
    x0=(headers[i-1][2]+h[0])/2 if i else table.x0
    x1=(h[2]+headers[i+1][0])/2 if i+1<len(headers) else table.x1
    cell=pymupdf.Rect(x0,row.y0,x1,row.y1)
    token=region_text(page,cell)
    parsed=number_token(token)
    unit=region_text(page,pymupdf.Rect(x0,unit_y[0],x1,unit_y[1]))
    if norm(unit).strip('()')!='ppm' or parsed is None or not 0<=parsed['value']<=1000000:
        raise ValueError('SCOPED_EXCEPTION_NATIVE_PPM_CELL_REQUIRED:'+label)
    return {'value':parsed['value'],'original_token':token,'unit':'ppm','page':binding['page'],
            'bbox':list(cell),'header_bbox':list(h[:4]),'header':label,'row_bbox':list(row),
            'section_id':binding['section_id'],'rounding_half_width':float(Decimal(5)*Decimal(10)**(Decimal(token.replace(',','')).as_tuple().exponent-1))}


def scoped_exception_fills(review, source_path, bundle, elements, row, decisions):
    """Return proposed fills; caller allows only blank fields or listed derivatives.

    Must be called after validate_reviews, with that review's selected resource
    bundle. No file is opened when its exact decision is not approved.
    """
    pid=review['project_id']
    if pid not in RULES: return []
    identity=SPLINTER if pid==SPLINTER[0] else CIRCLE
    decision=approved_decision(decisions, identity)
    if decision is None:return []
    if (pid,review['statement_id'],review['source_sha256'])!=identity:
        raise ValueError('SCOPED_EXCEPTION_IDENTITY_MISMATCH')
    if any(bundle.get(k)!=review.get(k) for k in ('source_sha256','statement_id','scope','effective_date')):
        raise ValueError('SCOPED_EXCEPTION_SELECTED_CONTRACT_MISMATCH')
    if not bundle.get('observations') or any(o.get('status')!='AUTO_VALIDATED' for o in bundle['observations']):
        raise ValueError('SCOPED_EXCEPTION_VALIDATED_BUNDLE_REQUIRED')
    from .store import filehash
    if filehash(source_path)!=identity[2]:raise ValueError('SCOPED_EXCEPTION_SOURCE_HASH_MISMATCH')
    import pymupdf
    from .source_cells import validate_cell, norm, region_text
    ore=next(o for o in review['observations'] if o['variable']=='ore_mt')
    if bundle['value']['ore_mt']!=ore['value']:raise ValueError('SCOPED_EXCEPTION_ORE_MISMATCH')
    proofs=[]; fills=[]
    with pymupdf.open(source_path) as doc:
        # Revalidate every selected native cell, retaining old validators' exact
        # class/cutoff/section constraints. Circle's derived Ce is already checked
        # by validate_reviews and is not an input to its grouped NdPr derivation.
        inputs=review['observations'] if pid==SPLINTER[0] else [ore]
        for o in inputs:
            validate_cell(doc,o['cell_binding'],o['variable'],o['original_token'],o.get('original_unit',o['unit']),review['scope'],selected_sections=review['selected_resource_sections'])
        provenance={'decision_id':decision['decision_id'],'source_sha256':identity[2],
                    'statement_id':identity[1],'scope':review['scope'],'effective_date':review['effective_date'],
                    'ore_mt':ore['value'],'ore_cell':ore['cell_binding']}
        def add(column,value,method):
            if row.get(column,'')!='' and column not in DERIVED_CHANGE_COLUMNS:
                raise ValueError('SCOPED_EXCEPTION_EXISTING_VALUE_PROTECTED:'+column)
            fills.append(dict(column=column,value=value,method=method,provenance=copy.deepcopy(provenance)))
        if pid==CIRCLE[0]:
            value=_column(doc,ore['cell_binding'],'NdPr',(298,312),(309.7,321.9))
            definition=norm(doc[1].get_text()).replace('₂','2').replace('₃','3')
            if 'ndpr = nd2o3 + pr6o11' not in definition or 'inferred' not in definition or '430ppm treo-ceo2' not in definition or 'us$145/kg' not in definition:
                raise ValueError('SCOPED_EXCEPTION_NDPR_SCOPE_OR_OXIDE_DEFINITION')
            provenance.update(native_ndpr=value,definition_page=2,definition='NdPr = Nd2O3 + Pr6O11')
            add('NdPr蘊藏量_kt_需兩者皆公布',ore['value']*value['value']*.001,'SOURCE_COMBINED_NDPR_OXIDE_PPM_X_ORE_MT')
            add('元素數據一致性檢查',row.get('元素數據一致性檢查','')+'；NdPr為來源公布之合計氧化物品位，依研究者決定填入；Nd、Pr個別值未公布','SOURCE_COMBINED_NDPR_OXIDE_PPM_X_ORE_MT')
            return fills
        from .partial_resource import validate_partial_resource
        def evidence(e):
            text=norm(doc[e['page']-1].get_text())
            if any(norm(m) not in text for m in e.get('markers',[])):raise ValueError('SCOPED_EXCEPTION_EVIDENCE_MARKER')
            return text
        validate_partial_resource(review,doc,evidence)
        ce=_column(doc,ore['cell_binding'],'Ce2O3',(135,149),(148.8,159.5))
        factor=cerium_factors()
        if abs(factor['ce2o3_element_ratio']-1.171)>.0005:
            raise ValueError('SCOPED_EXCEPTION_CE2O3_FACTOR_CONFLICT')
        ce_ppm=ce['value']*factor['ce2o3_to_ceo2']; ce_kt=ore['value']*ce_ppm*.001
        provenance.update(mode=CONVERSION_MODE,native_ce2o3=ce,atomic_weights={'Ce':factor['Ce'],'O':factor['O']},conversion_factor=factor['ce2o3_to_ceo2'],source_factor_crosscheck=factor['ce2o3_element_ratio'],basis_proof=review['partial_resource_projection']['basis_proof'])
        canonical=dict(elements);canonical['CeO2']=ce_kt
        add('CeO2_氧化鈰_kt',ce_kt,'DERIVED_STOICHIOMETRIC_CE2O3_TO_CEO2')
        from .project_summary import ELEMENTS,MAGNET,complete_sum
        definition=norm(doc[68].get_text())
        source_treo=None
        if 'in order to calculate the treo+y2o3' in definition and 'resource reporting' in definition:
            source_treo=_column(doc,ore['cell_binding'],'TREO+Y2O3',(135,149),(148.8,159.5))
            total_ppm=source_treo['value']-ce['value']+ce_ppm
            method='SOURCE_TREO_PLUS_Y_MINUS_CE2O3_PLUS_CEO2'
            provenance.update(source_treo=source_treo,treo_definition_page=69,treo_definition='TREO+Y2O3 (Total Rare Earth Oxides plus Yttrium Oxide); Table 33 Ce2O3 conversion used for resource reporting')
        elif set(canonical)==set(ELEMENTS):
            total_ppm=sum(canonical.values())/ore['value']/.001
            method='SUM_15_CANONICAL_OXIDES'
        else:
            total_ppm=None;method='CERIUM_ONLY_TREO_DEFINITION_UNRESOLVED'
        provenance['treo_method']=method
        add('已公布元素數_共15項',len(canonical),'COUNT_CANONICAL_INDIVIDUAL_OXIDES')
        add('已公布元素總和_kt',sum(canonical.values()),'SUM_AVAILABLE_MATCHED_CANONICAL_OXIDES')
        closure='未進行完整15項閉合檢查'
        if total_ppm is not None:
            total_kt=ore['value']*total_ppm*.001
            add('TREO品位_pct',total_ppm/10000,method)
            add('總TREO蘊藏量_kt',total_kt,method)
            add('有TREO資源估計','是',method)
            add('元素總和/TREO',sum(canonical.values())/total_kt,method)
            magnetic=complete_sum(canonical,MAGNET)
            if magnetic is not None:
                add('磁鐵稀土氧化物蘊藏量_kt',magnetic,'SUM_COMPLETE_MATCHED_MAGNET_OXIDES_AFTER_CE_CANONICALIZATION')
                add('磁鐵稀土佔TREO_pct',magnetic/total_kt*100,method)
            if set(canonical)==set(ELEMENTS):
                floating_delta=sum(canonical.values())-total_kt
                if source_treo:
                    # The same converted Ce input occurs on both sides, so it
                    # cancels. Do not count its uncertainty twice or use a %.
                    native_sum=sum(Decimal(str(o['original_token']).replace(',','')) for o in review['observations'] if o['variable']!='ore_mt')+Decimal(ce['original_token'].replace(',',''))
                    native_delta=native_sum-Decimal(source_treo['original_token'].replace(',',''))
                    half=sum(o.get('rounding_half_width',0) for o in review['observations'] if o['variable']!='ore_mt')+ce['rounding_half_width']+source_treo['rounding_half_width']
                    delta=float(native_delta*Decimal(str(ore['value']))*Decimal('.001'))
                    tolerance=ore['value']*half*.001
                    provenance.update(closure_difference_kt=delta,closure_rounding_tolerance_kt=tolerance,
                        source_15_oxide_sum_ppm=float(native_sum),source_sum_minus_treo_ppm=float(native_delta),
                        closure_rounding_half_width_ppm=half,closure_shared_ce_conversion_cancels=True,
                        floating_point_residual_kt=floating_delta)
                    closure='15項氧化物總和與TREO於來源有效位數範圍內一致' if abs(delta)<=tolerance else '15項閉合差值 '+str(delta)+' kt'
                else:
                    provenance.update(closure_difference_kt=0,closure_method='TOTAL_DEFINED_BY_SAME_15_OXIDES_NOT_INDEPENDENT_VALIDATION')
                    closure='TREO由相同15項氧化物加總定義；不是獨立來源總量閉合驗證'
        add('元素數據一致性檢查','來源以Ce2O3表示；依研究者決定以化學計量換算為CeO2（係數'+format(factor['ce2o3_to_ceo2'],'.10f')+'）；TREO依'+method+'重算；'+closure,'RESEARCHER_APPROVED_CANONICAL_OXIDE_CLOSURE')
    return fills
