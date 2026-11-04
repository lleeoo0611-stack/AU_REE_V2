"""Selective page extraction: native, positioned text, then explicit local OCR.

No glyph substitution or numerical correction is guessed. Evidence consumers
must still validate source scope, units, dates and rendered page values.
"""
import re
import json
from datetime import datetime,timezone
from pathlib import Path
from pypdf import PdfReader
from .store import filehash,canonical

DOCUMENT_VERSION = 'document-recognition-v6-context-bound'
RESOURCE_LAYOUT_VERSION = 'positioned-resource-columns-v2'
NUMBER = r'(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?'


def classify(text):
    """Multiple labels describe a document; a keyword never validates a value."""
    rules = {
        'JORC_RESOURCE': r'(?i)\b(?:mineral resource|MRE)\b',
        'ORE_RESERVE': r'(?i)\bore reserves?\b',
        'EXPLORATION_TARGET': r'(?i)\bexploration target\b',
        'SCOPING': r'(?i)\bscoping study\b',
        'PFS': r'(?i)\b(?:pre[- ]?feasibility|PFS)\b',
        'DFS': r'(?i)\b(?:definitive feasibility|DFS|BFS)\b',
        'METALLURGICAL': r'(?i)\b(?:metallurg\w*|leach\w*|beneficiation)\b',
        'QUARTERLY': r'(?i)\bquarter(?:ly| ended)\b',
        'ANNUAL_REPORT': r'(?i)\bannual report\b',
        'FINANCING': r'(?i)\b(?:financing|financial close|drawdown|credit approval)\b',
        'OFFTAKE': r'(?i)\b(?:offtake|off-take|supply agreement)\b',
    }
    return [label for label, pattern in rules.items() if re.search(pattern, text)]


def project_registry(root):
    """Reuse registered identities only; no observation values are read here."""
    from .store import digest
    data=json.loads((Path(root)/'data/claims.json').read_text(encoding='utf-8'))
    rows=[]
    for p in data['projects']:
        if p.get('entity_kind','PROJECT')!='PROJECT':continue
        # Registry labels supply search terms, never authority to merge entities.
        name=re.split(r'\s[—–]\s|\b(?:Rare Earths?|Heavy Rare Earths?|REE|Critical Minerals|Project|development study)\b',p['name'],flags=re.I)[0].strip()
        aliases=sorted({name,*p.get('aliases',[])})
        rows.append(dict(entity_id='AU-'+digest([p.get('entity_namespace','project_registry_v1'),str(p['id'])])[:20],
                         native_id=str(p['id']),name=p['name'],aliases=aliases,
                         identity_source=p['identity_source']))
    return rows


def _matches(text, registry):
    return [p for p in registry if any(re.search(r'(?<!\w)'+re.escape(a)+r'(?!\w)',text,re.I) for a in p['aliases'] if len(a)>3)]


def _number(token):
    return float(token.replace(',',''))


def _half(token):
    return .5*10**(-len(token.split('.')[1]) if '.' in token else 0)


def publication_date(text):
    """Only a dated release header/first nonempty line, never a cited study date."""
    from datetime import datetime
    month=r'(?:January|February|March|April|May|June|July|August|September|October|November|December)'
    lines=[line.strip() for line in text.splitlines() if line.strip()]
    found=[]
    for i,line in enumerate(lines[:25]):
        if i!=0 and not re.search(r'ASX\s+(?:Announcement|Release)\s*:|^(?:Release|Date)\s*:',line,re.I):continue
        for value in re.findall(r'\b\d{1,2}\s+'+month+r'\s+20\d{2}\b',line,re.I):
            try:found.append(datetime.strptime(value,'%d %B %Y').date().isoformat())
            except ValueError:pass
    return found[0] if len(set(found))==1 else None


def candidate_value_issues(candidate):
    """Validate structured values against row tokens, independent of stored SHA."""
    c=candidate
    try:
        if c['kind']=='TECHNICAL_TABLE_CELL':
            from .technical_tables import number_token
            parsed=number_token(c['original_token'])
            if not parsed or parsed['value']!=c['value'] or parsed['bounds']!=c.get('bounds'):return ['CELL_TOKEN_VALUE_MISMATCH']
            if c['value'] is not None and c.get('unit')=='%' and not 0<=c['value']<=100:return ['PERCENT_OUT_OF_RANGE']
        elif c['kind']=='LEACH_TABLE_ROW':
            labels=re.findall(r'TREO|MREO|Pr6O11|Nd2O3|Tb4O7|Dy2O3|Sc2O3',c['header'])
            tokens=re.findall('('+NUMBER+r')\s*%',c['raw_text'])
            if len(labels)!=len(tokens) or c['values']!={k:_number(v) for k,v in zip(labels,tokens)}:
                return ['ROW_TOKEN_VALUE_MISMATCH']
        elif c['kind']=='RESOURCE_TABLE_TOTAL':
            tokens=re.findall(NUMBER,re.sub(r'^\s*(?:Grand Total|Total)\s+','',c['raw_text'],flags=re.I))
            indices=c.get('row_token_indices',{'ore_mt':0,'grade':1})
            if any(c['values'][k]!=_number(tokens[indices[k]]) for k in ('ore_mt','grade')):
                return ['ROW_TOKEN_VALUE_MISMATCH']
            if c['values'].get('contained_treo_kt') is not None:
                factor=1 if re.search(r'000|\bkt\b',c['header'],re.I) else .001
                if c['values']['contained_treo_kt']!=_number(tokens[indices.get('contained_treo_kt',2)])*factor:return ['ROW_TOKEN_VALUE_MISMATCH']
        return []
    except (ValueError,KeyError,IndexError,TypeError):return ['ROW_TOKEN_CONTRACT_INCOMPLETE']


def resource_rows(text, page, registry):
    """Recognize aligned total rows; retain every cutoff/table independently.

    No cross-table addition and no silent conversion of reserve/target to MRE.
    Header and nearby definition text travel with every candidate.
    """
    lines=text.splitlines(); result=[]
    for index,line in enumerate(lines):
        match=re.match(r'^\s*(Total|TOTAL|Grand Total)\s+('+NUMBER+r')(?:\s+('+NUMBER+r')){1,}',line)
        if not match:continue
        tokens=re.findall(NUMBER,line[match.end(1):])
        if len(tokens)<2:continue
        before='\n'.join(lines[max(0,index-22):index]);after='\n'.join(lines[index+1:index+12])
        context=before+'\n'+line+'\n'+after
        if not re.search(r'\bTREO\b',before,re.I):continue
        headings=[x.strip() for x in lines[max(0,index-28):index] if re.search(r'(?:Table\s*\d.*(?:Resource|Reserve)|(?:Mineral Resource|Ore Reserve).*(?:Estimate|summary)|JORC.*Resource)',x,re.I)]
        heading=headings[-1] if headings else ''
        hits=_matches(heading+'\n'+before,registry)
        if len(hits)!=1:hits=_matches(text[:250],registry)
        pid=hits[0]['entity_id'] if len(hits)==1 else None
        reserve=bool(re.search(r'\b(?:Proved|Probable)\b',before,re.I))
        cats=[c for c in ('Measured','Indicated','Inferred') if re.search(r'\b'+c+r'\b',before,re.I)]
        category='_'.join(c.upper() for c in cats)+'_TOTAL' if len(cats)>1 else (cats[0].upper() if cats else None)
        header=' '.join(x for x in lines[max(0,index-12):index] if re.search(r'JORC|Classification|Tonnes|TREO|ppm|\(Mt\)',x,re.I))
        unit='Mt' if re.search(r'Million\s+Tonnes|\bMt\b',header,re.I) else None
        grade_unit='%' if re.search(r'TREO\S*\s*\(?%\)?',header,re.I) else ('ppm' if re.search(r'\bppm\b',header,re.I) else None)
        # The first two numerical columns must explicitly be tonnage and TREO.
        columns_ok=bool(re.search(r'(?:Tonnes|\bMt\b).*?TREO',header,re.I))
        if re.search(r'\bBD\b|g/cm|bulk density',header,re.I):columns_ok=False
        reasons=[]
        if not pid:reasons.append('PROJECT_ATTRIBUTION_AMBIGUOUS')
        if not heading:reasons.append('TABLE_SCOPE_HEADING_NOT_RESOLVED')
        if reserve:reasons.append('RESERVE_SUBSET_NOT_RESOURCE')
        if not category:reasons.append('JORC_CATEGORY_NOT_RESOLVED')
        if not columns_ok or not unit or not grade_unit:reasons.append('TABLE_COLUMN_OR_UNIT_UNRESOLVED')
        if re.search(r'THM|heavy mineral|monazite',header,re.I):reasons.append('BULK_VERSUS_MINERAL_FRACTION_UNRESOLVED')
        basis_definition=' '.join(x.strip() for x in lines[max(0,index-8):index+16] if re.search(r'TREO.*(?:defined|=|include)|Total Rare Earth Oxides.*defined',x,re.I))
        cutoff=' '.join(x.strip() for x in lines[max(0,index-28):index+16] if re.search(r'cut[- ]?off',x,re.I))
        if not basis_definition:reasons.append('REO_DEFINITION_NOT_LOCATED')
        values={'ore_mt':_number(tokens[0]),'grade':_number(tokens[1])}
        units={'ore_mt':unit,'grade':grade_unit}
        column_labels=[];extra_values=[]
        for prior in lines[max(0,index-12):index]:
            labels=re.findall(r'Tonnes|TREO|MREO|LREO|HREO|Pr6O11|Nd2O3|Dy2O3|Tb4O7|Sc2O3|\bU\b|\bTh\b',prior)
            if len(labels)==len(tokens) and labels[:2]==['Tonnes','TREO']:
                column_labels=labels
                for label,token in zip(labels[2:],tokens[2:]):
                    extra_values.append(dict(label=label,value=_number(token),unit='ppm' if grade_unit=='ppm' else None,original_token=token))
        # Only an explicit contained-TREO header grants a contained value.
        if len(tokens)==3 and re.search(r'TREO.*(?:000|kt|tonnes)',header,re.I):
            factor=1 if re.search(r'000|\bkt\b',header,re.I) else .001
            values['contained_treo_kt']=_number(tokens[2])*factor;units['contained_treo_kt']='kt TREO'
        bounds=None
        if unit and grade_unit:
            factor=10 if grade_unit=='%' else .001
            bounds=[(values['ore_mt']-_half(tokens[0]))*(values['grade']-_half(tokens[1]))*factor,
                    (values['ore_mt']+_half(tokens[0]))*(values['grade']+_half(tokens[1]))*factor]
            if values.get('contained_treo_kt') is not None and not bounds[0]<=values['contained_treo_kt']<=bounds[1]:reasons.append('REPORTED_CONTAINED_CONFLICT')
        result.append(dict(domain='Resource',kind='RESOURCE_TABLE_TOTAL',project_id=pid,physical_page=page,
                           scope=heading or 'Unresolved table scope',resource_type='ORE_RESERVE' if reserve else 'MINERAL_RESOURCE',
                           category=category,values=values,units=units,original_tokens=tokens,header=header,
                           raw_text=line.strip(),context=context,basis='TREO',basis_definition=basis_definition,
                           cutoff=cutoff or None,rounding_bounds_kt=bounds,issues=sorted(set(reasons)),
                           column_labels=column_labels,extra_values=extra_values,row_index=index))
    return result


def positioned_resource_columns(candidates, tables, text, registry, version='positioned-resource-columns-v2'):
    """Repair columns only when native cell values and exact headers align.

    No document-specific values, density skipping by position, or cross-table
    addition. A continuation without tonnage/TREO headers remains unresolved.
    Missing REO definitions and other scientific validation issues remain held.
    """
    modern=version in ('positioned-resource-columns-v3','positioned-resource-columns-v4')
    import unicodedata
    def header_text(value):
        return re.sub(r'\s+',' ',unicodedata.normalize('NFKC',str(value or ''))).strip()
    def grade_header(value):
        return bool(re.fullmatch(r'TREO\*?\s*(?:\+\s*Y2O3\s*)?\(?(?:%|ppm)\)?',value,re.I))
    if version=='positioned-resource-columns-v4':
        # Native table totals recover vertically split JORC rows. Only a single
        # explicit on-page caption and exact native values grant a candidate.
        # Captions may be below a table; arbitrary nearby project mentions do not.
        captions=[line.strip() for line in text.splitlines() if re.search(r'Table\s+\d+.*(?:Mineral Resource|Ore Reserve)',line,re.I)]
        for table in tables:
            for row in table['cells']:
                if not any(re.fullmatch(r'Total|Grand Total',str(v or '').strip(),re.I) for v in row):continue
                tokens=[str(v).strip() for v in row if v and re.fullmatch(NUMBER,str(v).strip())]
                if len(tokens)<2 or any(c.get('original_tokens')==tokens for c in candidates):continue
                raw=next((line.strip() for line in text.splitlines() if re.match(r'^\s*(?:TOTAL|Grand Total)\s+',line,re.I)
                          and re.findall(NUMBER,re.sub(r'^\s*(?:TOTAL|Grand Total)\s+','',line,flags=re.I))==tokens),None)
                if not raw or len(captions)!=1:continue
                caption=captions[0];hits=_matches(caption,registry)
                category=[c for c in ('Measured','Indicated','Inferred') if re.search(r'\b'+c+r'\b',caption,re.I)]
                reserve=bool(re.search(r'Ore Reserve',caption,re.I))
                issues=['TABLE_COLUMN_OR_UNIT_UNRESOLVED','REO_DEFINITION_NOT_LOCATED']
                if len(hits)!=1:issues.append('PROJECT_ATTRIBUTION_AMBIGUOUS')
                if not category:issues.append('JORC_CATEGORY_NOT_RESOLVED')
                if reserve:issues.append('RESERVE_SUBSET_NOT_RESOURCE')
                candidates.append(dict(domain='Resource',kind='RESOURCE_TABLE_TOTAL',project_id=hits[0]['entity_id'] if len(hits)==1 else None,
                    physical_page=table['physical_page'],scope=caption,resource_type='ORE_RESERVE' if reserve else 'MINERAL_RESOURCE',
                    category='_'.join(c.upper() for c in category)+'_TOTAL' if len(category)>1 else category[0].upper() if category else None,
                    values={},units={},original_tokens=tokens,header='',raw_text=raw,context=text,basis='TREO',basis_definition='',
                    cutoff=None,rounding_bounds_kt=None,issues=issues,column_labels=[],extra_values=[],row_index=None))
    for c in candidates:
        if c['kind']!='RESOURCE_TABLE_TOTAL':continue
        if not modern and not any(x in c['issues'] for x in ('TABLE_COLUMN_OR_UNIT_UNRESOLVED','PROJECT_ATTRIBUTION_AMBIGUOUS')):continue
        tokens=c['original_tokens'];matches=[]
        for table in tables:
            for ri,row in enumerate(table['cells']):
                if not row:continue
                label=next((v for v in row if v and str(v).strip()),'') if modern else (row[0] or '') if row else ''
                if version=='positioned-resource-columns-v4':label=next((v for v in row if re.fullmatch(r'\s*(?:Grand Total|Total)\s*',str(v or ''),re.I)),label)
                if not row or not re.fullmatch(r'\s*(?:Grand Total|Total)\s*',label,re.I):continue
                numeric=[(j,v.strip()) for j,v in enumerate(row) if v and re.fullmatch(NUMBER,v.strip())]
                if [v for j,v in numeric]!=tokens:continue
                first_data=next((i for i,r in enumerate(table['cells']) if re.match(r'^(?:Measured|Indicated|Inferred|Subtotal|Total)\b',next((v for v in r if v and str(v).strip()),'') if modern else r[0] or '',re.I)),ri)
                if version=='positioned-resource-columns-v4':
                    first_data=next((i for i,r in enumerate(table['cells']) if any(re.match(r'^(?:Measured|Indicated|Inferred|Subtotal|Total)\b',str(v or '').strip(),re.I) for v in r)),first_data)
                headers=[' '.join(str(r[j] or '') for r in table['cells'][:first_data]) for j in range(len(row))]
                if modern:headers=[header_text(h) for h in headers]
                # A visually separate header table is usable only with the same
                # columns and horizontal bounds, immediately above this table.
                if not any(re.search(r'Tonnage|Tonnes|Material',h,re.I) for h in headers):
                    prior=[t for t in tables if t['bbox'][3]<=table['bbox'][1] and len(t['cells'][0])==len(row)
                           and abs(t['bbox'][0]-table['bbox'][0])<2 and abs(t['bbox'][2]-table['bbox'][2])<2]
                    if prior:
                        previous=max(prior,key=lambda t:t['bbox'][3])
                        headers=[' '.join(str(r[j] or '') for r in previous['cells']) for j in range(len(row))]
                ton=[j for j,h in enumerate(headers) if re.search(r'Tonnage|Tonnes|Material',h,re.I) and re.search(r'\bMt\b',h)]
                grade=[j for j,h in enumerate(headers) if grade_header(h)] if modern else [j for j,h in enumerate(headers) if re.fullmatch(r'\s*TREO\s*(?:%|ppm)\s*',h,re.I)]
                if len(ton)!=1 or len(grade)!=1:continue
                positions={j:i for i,(j,v) in enumerate(numeric)}
                if ton[0] not in positions or grade[0] not in positions:continue
                section=' '.join(headers[:ton[0]]) if modern else None
                matches.append((headers,positions[ton[0]],positions[grade[0]],table['bbox'],section))
        if len(matches)!=1:continue
        headers,ti,gi,bbox,section=matches[0]
        c['values']={'ore_mt':_number(tokens[ti]),'grade':_number(tokens[gi])}
        c['units']={'ore_mt':'Mt','grade':'%' if '%' in headers[next(j for j,h in enumerate(headers) if grade_header(h))] else 'ppm'}
        c['row_token_indices']={'ore_mt':ti,'grade':gi}
        c['positioned_column_evidence']=dict(headers=headers,bbox=bbox,method=version)
        c['header']=' | '.join(headers)
        c['extra_values']=[];c['column_labels']=[]
        c['issues']=[x for x in c['issues'] if x not in ('TABLE_COLUMN_OR_UNIT_UNRESOLVED','REPORTED_CONTAINED_CONFLICT')]
        if modern:
            # Require an explicit on-page oxide definition; location is retained.
            definition=[line.strip() for line in text.splitlines() if re.search(r'TREO.*(?:includes?:|defined|=)',line,re.I)]
            if definition:
                c['basis_definition']=' '.join(definition)
                c['issues']=[x for x in c['issues'] if x!='REO_DEFINITION_NOT_LOCATED']
            # Named sections in separate native tables remain separate scopes.
            section=re.sub(r'Classification|Category|Deposit','',section or '',flags=re.I).strip()
            if re.fullmatch(r'Mineral\s+Resource',section,re.I):section=None
            if section and section not in c['scope']:c['scope']+=' | '+section
        if version=='positioned-resource-columns-v4':
            captions=[line.strip() for line in text.splitlines() if re.search(r'Table\s+\d+.*(?:Mineral Resource|Ore Reserve)',line,re.I)]
            if len(captions)==1:
                c['scope']=captions[0]
                c['issues']=[x for x in c['issues'] if x!='TABLE_SCOPE_HEADING_NOT_RESOLVED']
            # Subscript digits split by the PDF font are normalized only in an
            # explicit chemical column header, never in numerical cell values.
            normalized=[re.sub(r'\s+','',h).replace('*','') for h in headers]
            font_order={'PrO611ppm':'Pr6O11ppm','NdO23ppm':'Nd2O3ppm','DyO23ppm':'Dy2O3ppm','TbO47ppm':'Tb4O7ppm'}
            normalized=[font_order.get(h,h) for h in normalized]
            oxide_labels=('Pr6O11','Nd2O3','Dy2O3','Tb4O7','Y2O3','Sc2O3')
            # The matched row must be reselected by its exact token sequence.
            native_rows=[r for t in tables for r in t['cells'] if [v.strip() for v in r if v and re.fullmatch(NUMBER,v.strip())]==tokens]
            if len(native_rows)==1:
                native=native_rows[0];positions={j:i for i,(j,v) in enumerate([(j,v) for j,v in enumerate(native) if v and re.fullmatch(NUMBER,v.strip())])}
                for label in oxide_labels:
                    columns=[j for j,h in enumerate(normalized) if h==label+'ppm']
                    if len(columns)==1 and columns[0] in positions:
                        token=tokens[positions[columns[0]]]
                        c['extra_values'].append(dict(label=label,value=_number(token),unit='ppm',original_token=token))
            # Formula continuation is copied verbatim, without inventing REO basis.
            lines=text.splitlines()
            definitions=[i for i,line in enumerate(lines) if re.search(r'TREO\s*=\s*La2O3',line)]
            if len(definitions)==1:
                i=definitions[0];c['basis_definition']=' '.join(lines[i:i+3]).strip()
                c['issues']=[x for x in c['issues'] if x!='REO_DEFINITION_NOT_LOCATED']
        if not c['project_id']:
            hits=_matches(text,registry)
            if len(hits)==1:
                c['project_id']=hits[0]['entity_id'];c['issues']=[x for x in c['issues'] if x!='PROJECT_ATTRIBUTION_AMBIGUOUS']
        factor=10 if c['units']['grade']=='%' else .001
        c['rounding_bounds_kt']=[(_number(tokens[ti])-_half(tokens[ti]))*(_number(tokens[gi])-_half(tokens[gi]))*factor,
                                 (_number(tokens[ti])+_half(tokens[ti]))*(_number(tokens[gi])+_half(tokens[gi]))*factor]
    return candidates


def narrative_candidates(text, page, registry, parser_version='document-recognition-v1'):
    """Keep scoped technical and commercial facts, without guessing endpoints.

    Clauses are candidates until attribution, numeric token and semantic context
    are sufficient. Unstated feed/scale/date/conditions remain NULL.
    """
    flat=re.sub(r'\s+',' ',text);result=[]
    sentences=re.split(r'(?<=[.;])\s+(?=[A-Z])',flat)
    for i,sentence in enumerate(sentences):
        if len(sentence)<25:continue
        technical=r'(?i)\b(?:recover\w*|extract\w*|leach\w*|reagent|thorium|uranium|NORM)\b'
        if parser_version in ('document-recognition-v2-mineralogy','document-recognition-v3-bound-quantities','document-recognition-v4-native-resource-totals','document-recognition-v5-technical-cells','document-recognition-v6-context-bound'):technical=r'(?i)\b(?:recover\w*|extract\w*|leach\w*|reagent|thorium|uranium|NORM|mineralog\w*|monazite|xenotime|rhabdophane|churchite|gangue)\b'
        domain='Technical' if re.search(technical,sentence) else ('Commercial' if re.search(r'(?i)\b(?:financing|offtake|off-take|financial close|drawdown|credit approval|grant|funding|cash position)\b',sentence) else ('Development' if re.search(r'(?i)\b(?:scoping study|PFS|DFS|care and maintenance|construction commenced)\b',sentence) else None))
        if not domain:continue
        context=' '.join(sentences[max(0,i-1):i+2])
        hits=_matches(sentence if domain=='Commercial' else context,registry)
        pid=hits[0]['entity_id'] if len(hits)==1 else None
        endpoint=('LEACH_SOLUTION' if re.search(r'(?i)leach|extraction.*(?:acid|hydrochloric)',context) else
                  'MINERAL_CONCENTRATE' if re.search(r'(?i)(?:flotation|mineral|xenotime) concentrate',context) else
                  'MREC' if re.search(r'(?i)\bMREC\b|mixed rare earth carbonate',context) else
                  'FINAL_SEPARATED_REO' if re.search(r'(?i)separated (?:rare earth )?oxides',context) else None)
        scale='BENCH' if re.search(r'(?i)bench|composite samples|laboratory',context) else ('PILOT' if re.search(r'(?i)\bpilot\b',context) else None)
        numbers=[dict(value=_number(m.group(1)),unit='%',token=m.group(0),start=m.start()) for m in re.finditer('('+NUMBER+r')\s*%',sentence)]
        if parser_version in ('document-recognition-v5-technical-cells','document-recognition-v6-context-bound'):
            from .technical_tables import technical_numbers
            numbers=technical_numbers(sentence)
        for number in numbers:
            prefix=sentence[max(0,number['start']-45):number['start']]
            number['quantity_role']=('MAXIMUM_EXTRACTION' if re.search(r'up to\s*$',prefix,re.I) else
                                     'AVERAGE_EXTRACTION' if re.search(r'averag(?:e|ing)\s*(?:of\s*)?$',prefix,re.I) else None)
            if not re.search(r'extract|recover|leach',sentence,re.I):number['quantity_role']=None
            if parser_version in ('document-recognition-v3-bound-quantities','document-recognition-v4-native-resource-totals','document-recognition-v5-technical-cells','document-recognition-v6-context-bound'):
                suffix=sentence[number['start']+len(number['token']):number['start']+len(number['token'])+65]
                local=prefix[-35:]+' '+number['token']+' '+suffix[:35]
                coordinated_mean=bool(re.search(r'(?:extraction|recovery|recoveries)\s+(?:achieved\s+)?up to\s+'+NUMBER+r'\s*%\s*,\s*averaging\s*$',sentence[:number['start']],re.I))
                bound=bool(coordinated_mean or re.search(r'(?:extraction|recovery|recoveries)\s*(?:achieved\s*|of\s*|averag(?:e|ing)\s*|up to\s*)*$',prefix,re.I) or
                           re.match(r'\s*(?:TREO\s+|rare earth\s+)?(?:extraction|recovery|recoveries)\b',suffix,re.I))
                # Numeric narrative promotion stays restricted to the existing
                # explicit maximum/mean forms. Nearby graphic axis labels are
                # not sufficient to introduce a new generic percentage parser.
                if not number['quantity_role'] or not bound or re.search(r'moisture|deportment|\bgrade\b|\bTREO\s*[.,;]',local,re.I):number['quantity_role']=None
                else:
                    quantity='RECOVERY' if re.search(r'recover',prefix[-45:]+suffix[:25],re.I) else 'EXTRACTION'
                    if quantity=='RECOVERY' and re.search(r'mining\s+recovery',local,re.I):quantity='MINING_RECOVERY'
                    qualifier='MAXIMUM' if re.search(r'up to\s*$',prefix,re.I) else 'AVERAGE' if re.search(r'averag(?:e|ing)',prefix[-40:],re.I) else 'REPORTED'
                    number['quantity_role']=qualifier+'_'+quantity
        if parser_version in ('document-recognition-v5-technical-cells','document-recognition-v6-context-bound') and domain=='Technical':
            from .technical_tables import quantity_binding
            for number in numbers:number.update(quantity_binding(sentence,number))
        # Text observations are valid disclosures, not numerical project scores.
        reasons=[]
        if not pid:reasons.append('PROJECT_ATTRIBUTION_AMBIGUOUS')
        if re.search(r'(?i)\b(?:will|planned|targeting|expected|aims|potential)\b',sentence) and not (parser_version in ('document-recognition-v5-technical-cells','document-recognition-v6-context-bound') and domain=='Technical' and re.search(r'design|model|DFS|scoping|PFS',context,re.I)):reasons.append('FORWARD_LOOKING_NOT_COMPLETED_EVENT')
        result.append(dict(domain=domain,kind='SCOPED_TEXT_DISCLOSURE',project_id=pid,physical_page=page,
                           scope=context,raw_text=sentence,context=context,endpoint=endpoint,scale=scale,
                           feed='SELECTED_COMPOSITES' if re.search(r'(?i)composite samples|selected composite',context) else None,
                           numbers=numbers,issues=reasons,attribution='PROJECT' if pid else None,
                           finance_state=None,conditions=None,row_index=i))
    return result


def leach_tables(text, page, registry):
    """Aligned laboratory extraction rows, with element and reagent boundaries.

    A test mean is not resource-to-product recovery. No mean is recalculated,
    and Sc is kept outside the source's TREO definition.
    """
    lines=text.splitlines();rows=[]
    for index,line in enumerate(lines):
        match=re.match(r'^\s*(JR\d+|Avg|Average|Mean)\s+((?:'+NUMBER+r'\s*%\s*){2,})',line,re.I)
        if not match:continue
        start=next((i for i in range(index-1,max(-1,index-25),-1) if re.search(r'Test\s+ID.*TREO',lines[i],re.I)),None)
        if start is None:continue
        header=lines[start];labels=re.findall(r'TREO|MREO|Pr6O11|Nd2O3|Tb4O7|Dy2O3|Sc2O3',header)
        tokens=re.findall('('+NUMBER+r')\s*%',match.group(2))
        if len(labels)!=len(tokens) or not labels:continue
        end=next((i for i in range(index+1,min(len(lines),index+18)) if re.search(r'Table\s+\d.*(?:Leach|Testwork)',lines[i],re.I)),index+1)
        caption=lines[end].strip() if end<len(lines) else ''
        context='\n'.join(lines[max(0,start-6):min(len(lines),end+1)])
        hits=_matches(caption+'\n'+context,registry);pid=hits[0]['entity_id'] if len(hits)==1 else None
        reagent=re.search(r'using\s+(.+?)\s+at\s+\d',caption,re.I)
        reagent=reagent.group(1).strip() if reagent else None
        temp=re.search(r'(\d+(?:\.\d+)?)\s*°?C\b',context)
        time=re.search(r'(\d+(?:\.\d+)?)\s*[- ]hour\s+(?:residence|leach)',context,re.I)
        issues=[]
        if not pid:issues.append('PROJECT_ATTRIBUTION_AMBIGUOUS')
        if not reagent:issues.append('REAGENT_NOT_ESTABLISHED')
        if not all(0<=_number(t)<=100 for t in tokens):issues.append('PERCENT_OUT_OF_RANGE')
        if not re.search(r'TREO.*defined.*plus Y',text,re.I):issues.append('REO_DEFINITION_NOT_LOCATED')
        rows.append(dict(domain='Technical',kind='LEACH_TABLE_ROW',project_id=pid,physical_page=page,
                         scope=caption,raw_text=line.strip(),context=context,header=header,row_index=index,
                         sample_id=match.group(1),sample_interval=line[match.end():].strip() or None,
                         statistic='SOURCE_REPORTED_MEAN' if match.group(1).casefold() in ('avg','average','mean') else 'INDIVIDUAL_SELECTED_TEST',
                         values={label:_number(token) for label,token in zip(labels,tokens)},
                         original_tokens=tokens,unit='%',basis='SOURCE_DEFINED_TREO_INCLUDING_Y_EXCLUDING_SC',
                         endpoint='LEACH_SOLUTION',feed='SELECTED_DRILL_INTERVALS',
                         scale='LABORATORY_TESTWORK_SCALE_UNSPECIFIED',reagent=reagent,
                         temperature_c=float(temp.group(1)) if temp else None,
                         residence_hours=float(time.group(1)) if time else None,
                         acid_concentration=None,pressure=None,issues=issues))
    return rows


def source_binding_signature(root,source):
    """Identity-only cache dependencies; scientific observation values are excluded."""
    from .store import digest
    claims=json.loads((Path(root)/'data/claims.json').read_text(encoding='utf-8'))
    owners=sorted(str(p['id']) for p in claims['projects'] if any(o.get('source_sha256')==source['sha256'] for o in p.get('observations',[])))
    return digest([owners,source.get('recognition_project_native_id'),source.get('project_binding_status')])


def extraction_dependencies():
    """V6 cache binds parser/semantic implementation and native backend version."""
    import pymupdf
    from .store import digest
    return digest(dict(backend=pymupdf.VersionBind,files={name:filehash(Path(__file__).parent/name) for name in ('pdf_extract.py','technical_tables.py')}))


def _native_tables(doc,n,table_cache,modern,parser_version):
    """Geometry cache depends on native cell rectangles, not scientific defaults."""
    return (table_cache[n] if table_cache is not None and n in table_cache and (not modern or all('rows' in t for t in table_cache[n])) and (table_cache[n] or parser_version not in ('document-recognition-v4-native-resource-totals','document-recognition-v5-technical-cells','document-recognition-v6-context-bound')) else
        [dict(physical_page=n,table_index=i,bbox=list(t.bbox),cells=t.extract(),header=t.header.names,external_header=t.header.external,**({'rows':[list(r.cells) for r in t.rows]} if modern else {}))
         for i,t in enumerate(doc[n-1].find_tables().tables)])


def recognize_document(root, source, registry, tessdata=None, parser_version=None, table_cache=None, page_numbers=None):
    """Scan every page once, then extract tables/OCR only relevant pages."""
    import pymupdf
    parser_version=parser_version or DOCUMENT_VERSION
    if parser_version not in ('document-recognition-v1','document-recognition-v2-mineralogy','document-recognition-v3-bound-quantities','document-recognition-v4-native-resource-totals','document-recognition-v5-technical-cells','document-recognition-v6-context-bound'):
        raise ValueError('UNSUPPORTED_DOCUMENT_PARSER_VERSION')
    root=Path(root);path=root/source['path']
    if filehash(path)!=source['sha256']:raise ValueError('SOURCE_HASH_MISMATCH')
    pages=[];candidates=[];tables=[];sample_context_cache={}
    modern=parser_version in ('document-recognition-v5-technical-cells','document-recognition-v6-context-bound')
    bound=[]
    if modern:
        claims=json.loads((root/'data/claims.json').read_text(encoding='utf-8'))
        from .store import digest
        bound=[dict(project_id='AU-'+digest([p.get('entity_namespace','project_registry_v1'),str(p['id'])])[:20],method='REGISTERED_SOURCE_SHA_RELATION')
               for p in claims['projects'] if p.get('entity_kind','PROJECT')=='PROJECT' and any(o.get('source_sha256')==source['sha256'] for o in p.get('observations',[]))]
        bound=list({b['project_id']:b for b in bound}.values())
        native=source.get('recognition_project_native_id')
        if not bound and native:
            bound=[dict(project_id=p['entity_id'],method='SOURCE_REGISTRY_EXPLICIT_PROJECT_LINK') for p in registry if p['native_id']==native]
    if source['kind']=='html':
        from .evidence import html_text
        texts=[html_text(root,source)];doc=None
    else:
        doc=pymupdf.open(path);texts=[p.get_text(sort=True) for p in doc]
    try:
        if modern:
            title_hits=_matches(texts[0][:2500],registry)
            if len(title_hits)!=1 or not bound or title_hits[0]['entity_id'] not in {b['project_id'] for b in bound}:bound=[]
        for n,text in enumerate(texts,1):
            if page_numbers is not None and n not in page_numbers:continue
            labels=classify(text);method='MUPDF_POSITIONED' if doc else 'STATIC_HTML'
            if doc and not readable(text) and tessdata:
                extracted=extract_page(path,n,tessdata);text=extracted['text'];method=extracted['method'];labels=classify(text)
            technical_hint=modern and bool(re.search(r'Table\s+\d',text,re.I)) and bool(re.search(r'Extraction\s*\(%\)|Test\s*/\s*Product|process design basis|Stage Wise Recovery|Recovery Parameters|Concentrate Composition Equations'+('|Key Project metrics' if parser_version=='document-recognition-v6-context-bound' else ''),text,re.I|re.S))
            relevant=(bool(labels) and bool(re.search(r'TREO|rare earth|\bREE\b',text,re.I))) or technical_hint
            page=dict(physical_page=n,method=method,labels=labels,relevant=relevant,text=text,
                      status='EXTRACTED' if readable(text) else 'UNREADABLE',tables=[])
            if relevant:
                page_tables=[]
                recognized=resource_rows(text,n,registry)+leach_tables(text,n,registry)+narrative_candidates(text,n,registry,parser_version)
                if doc and (any(c['kind'] in ('RESOURCE_TABLE_TOTAL','LEACH_TABLE_ROW') for c in recognized) or (parser_version in ('document-recognition-v4-native-resource-totals','document-recognition-v5-technical-cells','document-recognition-v6-context-bound') and 'JORC_RESOURCE' in labels) or technical_hint):
                    page_tables=[]
                    try:
                        native=_native_tables(doc,n,table_cache,modern,parser_version)
                        for table in native:
                            i=table['table_index'];table=dict(table)
                            table.pop('continuation_candidate',None)
                            tables.append(table);page['tables'].append(i)
                            page_tables.append(table)
                    except Exception as exc:page['table_error']=type(exc).__name__
                    positioned_resource_columns(recognized,page_tables,text,registry,
                        version='positioned-resource-columns-v4' if parser_version in ('document-recognition-v4-native-resource-totals','document-recognition-v5-technical-cells','document-recognition-v6-context-bound') else 'positioned-resource-columns-v3' if parser_version=='document-recognition-v3-bound-quantities' else RESOURCE_LAYOUT_VERSION)
                if modern:
                    from .technical_tables import technical_cells,flow_cells,model_parameters,sample_context,metric_cells,bind_semantics
                    for table in page_tables if doc and 'page_tables' in locals() else []:
                        if table['physical_page']==n:
                            recognized.extend(technical_cells(table,text))
                            if parser_version=='document-recognition-v6-context-bound':recognized.extend(metric_cells(table,text,doc[n-1].get_text('words')))
                    if doc:
                        recognized.extend(flow_cells(page_tables,doc[n-1].get_text('words'),text,n))
                        recognized.extend(model_parameters(doc[n-1].get_text('words'),text,n))
                for c in recognized:
                    if modern and c['kind']=='SCOPED_TEXT_DISCLOSURE':
                        c['reported_ratios']=[dict(value=float(m[2]),unit='ratio',quantity='treo_upgrade_ratio',test_id=m[1],token=m[0]) for m in re.finditer(r'\b(F\d+)\s+achieved\s+(?:a\s+)?(\d+(?:\.\d+)?)x\s+TREO\s+upgrade',c['raw_text'],re.I)]
                    if modern and len(bound)==1 and not c.get('project_id'):
                        c['project_id']=bound[0]['project_id'];c['project_binding']=bound[0]
                        c['issues']=[x for x in c['issues'] if x!='PROJECT_ATTRIBUTION_AMBIGUOUS']
                    if modern and source.get('project_binding_status')=='UNRESOLVED_DISTINCT_PROJECT':
                        c['project_id']=None;c['issues'].append('DISTINCT_PROJECT_RELATION_NOT_ESTABLISHED')
                    if c['kind']=='TECHNICAL_TABLE_CELL':
                        if not c.get('project_id'):c['issues'].append('PROJECT_ATTRIBUTION_AMBIGUOUS')
                        c['table_scope_id']=digest([source['sha256'],n,c['table_index']])
                        c['case_id']=digest([c['table_scope_id'],c.get('sample_id'),c.get('stage')])
                        # Only explicit primary-composite statements bind a table to an earlier sample.
                        context_pages=[(j+1,t) for j,t in enumerate(texts[max(0,n-3):n],max(0,n-3)) if re.search(r'primary composite',t,re.I)]
                        samples=[(pn,m[1]) for pn,t in context_pages for m in re.finditer(r'Composite Sample\s*\(([A-Za-z0-9-]+)\)',t,re.I)]
                        if (c.get('scale')=='LAB_FLOTATION' or (parser_version=='document-recognition-v6-context-bound' and c.get('test_id'))) and len(set(x[1] for x in samples))==1:
                            c['sample_id']=c['sample_population']=samples[0][1];c['sample_binding']=dict(physical_page=samples[0][0],method='EXPLICIT_PRIMARY_COMPOSITE_STATEMENT')
                        sample=c.get('sample_id')
                        if sample not in sample_context_cache:sample_context_cache[sample]=sample_context(texts,sample,source['sha256'])
                        rep=sample_context_cache[sample]
                        if rep:
                            c['representativeness_evidence']=rep;c['representativeness']=rep['state']
                        if parser_version=='document-recognition-v6-context-bound':bind_semantics(c,texts,source['sha256'])
                        c['case_id']=digest([c['table_scope_id'],c.get('sample_id'),c.get('stage')])
                        c['scope']+=' | '+str(c.get('test_id') or '')+' | '+str(c.get('product') or c.get('source_column') or c.get('stage') or '')
                    c.update(source_sha256=source['sha256'],source_key=source['key'],
                             publication_date=source.get('publication_date'),effective_date=None,
                             date_role='PUBLICATION_DATE_ONLY_EFFECTIVE_DATE_NOT_INFERRED',
                             extraction_method=method,parser_version=parser_version)
                    # Word coordinates bind the row/paragraph to the physical page.
                    if doc:
                        needles=c['raw_text'].split()
                        boxes=doc[n-1].search_for(c['raw_text'][:150])
                        if c['kind']!='TECHNICAL_TABLE_CELL':c['bboxes']=[list(b) for b in boxes]
                        if not boxes and c['kind']=='RESOURCE_TABLE_TOTAL':
                            c['bboxes']=[list(w[:4]) for w in doc[n-1].get_text('words') if w[4] in needles]
                    else:c['bboxes']=[]
                    from .store import digest
                    c['candidate_id']=digest(c)
                candidates.extend(recognized)
            pages.append(page)
        # Cross-page tables are linked as candidates only; totals are never summed.
        for table in tables:
            previous=[t for t in tables if t['physical_page']==table['physical_page']-1 and t['header']==table['header'] and any(t['header'])]
            if len(previous)==1:
                table['continuation_candidate']=dict(physical_page=previous[0]['physical_page'],table_index=previous[0]['table_index'],status='HEADER_MATCH_ONLY_NOT_SCOPE_EQUIVALENCE')
        return dict(version=parser_version,resource_layout_version='positioned-resource-columns-v4' if parser_version in ('document-recognition-v4-native-resource-totals','document-recognition-v5-technical-cells','document-recognition-v6-context-bound') else 'positioned-resource-columns-v3' if parser_version=='document-recognition-v3-bound-quantities' else RESOURCE_LAYOUT_VERSION,observation_contract='automatic-observation-v1-element-basis',source_sha256=source['sha256'],source_key=source['key'],
                    source_url=source['url'],publication_date=source.get('publication_date') or publication_date(texts[0]),
                    labels=classify(texts[0]),mentioned_labels=sorted({v for p in pages for v in p['labels']}),pages=pages,tables=tables,candidates=candidates,
                    backend_version=pymupdf.VersionBind,registry_identity_sha256=__import__('hashlib').sha256(canonical(registry).encode()).hexdigest(),
                    **({'source_binding_sha256':source_binding_signature(root,source)} if modern else {}),
                    **({'extraction_dependency_sha256':extraction_dependencies()} if parser_version=='document-recognition-v6-context-bound' else {}),
                    **({'requested_physical_pages':sorted(page_numbers)} if page_numbers is not None else {}),
                    limitations=['NO_CROSS_TABLE_SUM','NO_DATE_OR_FEED_IMPUTATION','CANDIDATE_TEXT_IS_NOT_CRITERION_SCORE'])
    finally:
        if doc:doc.close()


def capture_documents(root, snapshots, keys=None, tessdata=None, only_missing=False):
    """Content-addressed extraction artifacts join the existing source manifest."""
    import hashlib
    root=Path(root);path=root/'data/manifest.json';manifest=json.loads(path.read_text(encoding='utf-8'))
    registry=project_registry(root);outcomes=[];seen=set()
    for source in snapshots:
        if source['kind'] not in ('pdf','html') or (keys and source['key'] not in keys) or source['sha256'] in seen:continue
        seen.add(source['sha256'])
        try:
            if filehash(root/source['path'])!=source['sha256']:raise ValueError('SOURCE_HASH_MISMATCH')
            if only_missing:
                prior=[s for s in manifest['snapshots'] if s['kind']=='document_extraction' and s.get('source_sha256')==source['sha256']]
                if prior:
                    latest=max(prior,key=lambda s:s['acquired_at'])
                    if filehash(root/latest['path'])!=latest['sha256']:raise ValueError('IMMUTABLE_EXTRACTION_MISMATCH')
                    cached=json.loads((root/latest['path']).read_text(encoding='utf-8'))
                    if (cached['version']==DOCUMENT_VERSION and (DOCUMENT_VERSION!='document-recognition-v6-context-bound' or cached.get('extraction_dependency_sha256')==extraction_dependencies()) and (DOCUMENT_VERSION not in ('document-recognition-v5-technical-cells','document-recognition-v6-context-bound') or cached.get('source_binding_sha256')==source_binding_signature(root,source)) and cached.get('observation_contract')=='automatic-observation-v1-element-basis'
                            and cached.get('resource_layout_version')==('positioned-resource-columns-v4' if DOCUMENT_VERSION in ('document-recognition-v4-native-resource-totals','document-recognition-v5-technical-cells','document-recognition-v6-context-bound') else 'positioned-resource-columns-v3' if DOCUMENT_VERSION=='document-recognition-v3-bound-quantities' else RESOURCE_LAYOUT_VERSION)
                            and cached['registry_identity_sha256']==hashlib.sha256(canonical(registry).encode()).hexdigest()):
                        outcomes.append(dict(source_key=source['key'],source_sha256=source['sha256'],status='REUSED_VERIFIED_EXTRACTION',sha256=latest['sha256']))
                        continue
            native_cache=None
            if DOCUMENT_VERSION in ('document-recognition-v3-bound-quantities','document-recognition-v4-native-resource-totals','document-recognition-v5-technical-cells','document-recognition-v6-context-bound'):
                import pymupdf
                prior=[s for s in manifest['snapshots'] if s['kind']=='document_extraction' and s.get('source_sha256')==source['sha256']]
                if prior:
                    latest=max(prior,key=lambda s:s['acquired_at'])
                    if filehash(root/latest['path'])!=latest['sha256']:raise ValueError('IMMUTABLE_EXTRACTION_MISMATCH')
                    previous=json.loads((root/latest['path']).read_text(encoding='utf-8'))
                    if previous.get('source_sha256')==source['sha256'] and previous.get('backend_version')==pymupdf.VersionBind:
                        native_cache={p['physical_page']:[t for t in previous['tables'] if t['physical_page']==p['physical_page']]
                                      for p in previous['pages'] if 'table_error' not in p and p['status']=='EXTRACTED'}
            data=recognize_document(root,source,registry,tessdata,table_cache=native_cache)
            raw=(canonical(data)+'\n').encode();sha=hashlib.sha256(raw).hexdigest()
            target=root/'data/snapshots'/(sha+'.json')
            if not target.exists():target.write_bytes(raw)
            if filehash(target)!=sha:raise ValueError('IMMUTABLE_EXTRACTION_MISMATCH')
            now=datetime.now(timezone.utc).isoformat()
            entry=dict(key='recognized_'+source['sha256'],kind='document_extraction',url=source['url'],
                       source_sha256=source['sha256'],sha256=sha,path=target.relative_to(root).as_posix(),
                       acquired_at=now,available_date=now[:10],parser_version=DOCUMENT_VERSION)
            if source.get('publication_date'):entry['publication_date']=source['publication_date']
            if not any(s['key']==entry['key'] and s['sha256']==sha for s in manifest['snapshots']):manifest['snapshots'].append(entry)
            outcomes.append(dict(source_key=source['key'],source_sha256=source['sha256'],status='CAPTURED',sha256=sha,
                                 pages=len(data['pages']),tables=len(data['tables']),candidates=len(data['candidates']),labels=data['labels']))
        except Exception as exc:outcomes.append(dict(source_key=source['key'],status='EXTRACTION_FAILED',reason=str(exc)))
    path.write_text(json.dumps(manifest,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    return outcomes


def readable(text):
    chars=[c for c in text if not c.isspace()]
    return bool(chars) and sum(32<=ord(c)<127 for c in chars)/len(chars)>.88


def extract_page(path, number, tessdata=None, markers=(), ocr_dpi=200, ocr_clip=None):
    import pymupdf
    path=Path(path)
    with pymupdf.open(path) as doc:
        if not 1<=number<=len(doc):raise ValueError('Physical page out of range')
        page=doc[number-1]
        native_error=None
        try:native=PdfReader(path).pages[number-1].extract_text() or ''
        except Exception as exc:native='';native_error=type(exc).__name__
        alternate=page.get_text(sort=True)
        good=lambda t:readable(t) and all(m in re.sub(r'\s+',' ',t) for m in markers)
        method='PYPDF_NATIVE';text=native
        if not good(text):method='MUPDF_POSITIONED';text=alternate
        model_sha=None
        if not good(text) and tessdata:
            if ocr_dpi not in (200,400,600):raise ValueError('UNSUPPORTED_SELECTIVE_OCR_DPI')
            model=Path(tessdata)/'eng.traineddata'
            model_sha=filehash(model)
            method='MUPDF_TESSERACT_'+str(ocr_dpi)+'DPI_SELECTED_PAGE'
            if ocr_clip:
                clip=pymupdf.Rect(ocr_clip)
                if clip.is_empty or not page.rect.contains(clip):raise ValueError('OCR_CLIP_OUTSIDE_SOURCE_PAGE')
                pix=page.get_pixmap(matrix=pymupdf.Matrix(ocr_dpi/72,ocr_dpi/72),clip=clip)
                with pymupdf.open(stream=pix.pdfocr_tobytes(language='eng',tessdata=str(Path(tessdata).resolve())),filetype='pdf') as region:
                    text=region[0].get_text()
                method=method.replace('SELECTED_PAGE','SELECTED_REGION')
            else:
                tp=page.get_textpage_ocr(language='eng',dpi=ocr_dpi,full=True,tessdata=str(Path(tessdata).resolve()))
                text=page.get_text(textpage=tp)
        result={'source_sha256':filehash(path),'physical_page':number,'version':'pdf-page-v1',
                'method':method,'backend_version':pymupdf.VersionBind,'model_sha256':model_sha,
                'native_error':native_error,'native_text':native,'positioned_text':alternate,'text':text,
                'status':'EXTRACTED_REQUIRES_SCOPE_VALIDATION' if good(text) else 'UNREADABLE',
                'transformations':['NATIVE_AND_POSITIONED_TEXT_ATTEMPTED','NO_GUESSED_CHARACTER_OR_NUMERIC_SUBSTITUTION']}
        if ocr_clip:result['ocr_clip']=list(ocr_clip)
        return result


def capture_pages(root, source, pages, tessdata=None, markers_by_page=None, ocr_dpi=200, ocr_clips_by_page=None):
    """One source manifest, content-addressed derivatives, per-page isolation."""
    import hashlib
    root=Path(root);path=root/'data/manifest.json'
    manifest=json.loads(path.read_text(encoding='utf-8'));outcomes=[]
    if filehash(root/source['path'])!=source['sha256']:raise ValueError('PDF source checksum mismatch')
    for page in sorted(set(pages)):
        try:
            markers=(markers_by_page or {}).get(page,())
            result=extract_page(root/source['path'],page,tessdata,markers=markers,ocr_dpi=ocr_dpi,ocr_clip=(ocr_clips_by_page or {}).get(page))
            if markers:result['requested_markers']=list(markers)
            raw=(canonical(result)+'\n').encode();sha=hashlib.sha256(raw).hexdigest()
            target=root/'data/snapshots'/(sha+'.json')
            if not target.exists():target.write_bytes(raw)
            now=datetime.now(timezone.utc).isoformat();key=source['key']+'_page_'+str(page)
            entry=dict(key=key,kind='pdf_page_extraction',url=source['url'],source_sha256=source['sha256'],physical_page=page,sha256=sha,path=target.relative_to(root).as_posix(),acquired_at=now,available_date=now[:10])
            if source.get('publication_date'):entry['publication_date']=source['publication_date']
            if not any(s['key']==key and s['sha256']==sha for s in manifest['snapshots']):manifest['snapshots'].append(entry)
            outcomes.append(dict(page=page,status=result['status'],method=result['method'],sha256=sha))
        except Exception as exc:outcomes.append(dict(page=page,status='UNAVAILABLE',reason=type(exc).__name__))
    path.write_text(json.dumps(manifest,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    return outcomes


def narrative_context_issues(candidate,page,version='page-context-v2'):
    """Definitions/abbreviations are reference text, never project events."""
    if version=='scientific-context-v4-column-binding' and candidate.get('kind')=='RESOURCE_TABLE_TOTAL':
        import unicodedata
        header=unicodedata.normalize('NFKC',candidate.get('header',''))
        # Matching row tokens proves transcription, not what their columns mean.
        # Extra quantities between tonnes and TREO require positioned binding.
        if not candidate.get('positioned_column_evidence'):
            for match in re.finditer(r'(?:Tonnes|Tonnage|Material)\b(.*?)\bTREO',header,re.I|re.S):
                if re.search(r'\b(?:P\s*2\s*O\s*5|Nb\s*2\s*O\s*5|THM|BD|density|Fe\s*2\s*O\s*3|Zr\s*O\s*2)\b',match.group(1),re.I):
                    return ['RESOURCE_NUMERIC_COLUMN_BINDING_NOT_ESTABLISHED']
    if candidate.get('kind')!='SCOPED_TEXT_DISCLOSURE':return []
    header=' '.join(page.get('text','').split())[:500]
    if re.search(r'(?i)glossary|abbreviations and defined terms|definition of terms',header):
        return ['SOURCE_GLOSSARY_NOT_PROJECT_DISCLOSURE']
    if version in ('scientific-context-v3','scientific-context-v4-column-binding'):
        text=candidate.get('raw_text','')
        reasons=[]
        if re.search(r'(?i)forward[- ]looking statements? (?:include|are|may)|terms of any future funding|no assurance (?:that|can)',text):
            reasons.append('CAUTION_OR_HYPOTHETICAL_TERMS_NOT_PROJECT_EVENT')
        if candidate.get('domain')=='Commercial' and re.search(r'(?i)\b(?:cash position|cash balance|cash at bank|cash equivalents)\b',text):
            if not re.search(r'(?i)(?:restricted|ring[- ]fenced|dedicated).*\bproject\b',text):
                reasons.append('COMPANY_CASH_NOT_PROJECT_ATTRIBUTED')
        return reasons
    return []
