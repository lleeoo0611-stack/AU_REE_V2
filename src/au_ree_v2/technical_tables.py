"""Native technical cell recognition, using geometry rather than project rules.

This replaces the JR/Avg-only path for opted-in documents. Recognition preserves
source anomalies; scientific use is decided downstream, never by repairing cells.
"""
import re
from .store import digest

VERSION='document-recognition-v5-technical-cells'
NUM=r'[+\-−–]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?'
ELEMENTS=r'La|Ce|Pr|Nd|Sm|Eu|Gd|Tb|Dy|Ho|Er|Tm|Yb|Lu|Y|Sc'


def number_token(token):
    """Keep ranges and missing tokens; never turn a range into a midpoint."""
    s=str(token or '').strip(); normalized=s.replace('−','-')
    m=re.fullmatch('('+NUM+r')\s*%?',normalized)
    if m:return dict(original_token=s,value=float(m[1].replace(',','').replace('–','-')),bounds=None,token_state='NUMBER')
    m=re.fullmatch('('+NUM+r')\s*(?:–|—|to|-)\s*('+NUM+r')\s*%?',normalized)
    if m:return dict(original_token=s,value=None,bounds=[float(m[1].replace(',','').replace('–','-')),float(m[2].replace(',','').replace('–','-'))],token_state='RANGE')
    if s in ('-','—','–','','N/A','n/a','NA','NR'):return dict(original_token=s,value=None,bounds=None,token_state='NOT_APPLICABLE' if s.upper() in ('N/A','NA') else 'NOT_REPORTED')
    return None


def cells(table):
    """Nonempty native cells with original row/column and exact rectangle."""
    result=[]
    for ri,row in enumerate(table['cells']):
        for ci,value in enumerate(row):
            boxes=table.get('rows',[])
            box=boxes[ri][ci] if ri<len(boxes) and ci<len(boxes[ri]) else None
            if value is not None and str(value).strip() and box:
                result.append(dict(row=ri,column=ci,text=str(value).strip(),bbox=list(box)))
    return result


def path_above(cell, allcells, first_data):
    x=(cell['bbox'][0]+cell['bbox'][2])/2
    return [c['text'] for c in allcells if c['row']<first_data and c['text'] and c['bbox'][0]-.1<=x<=c['bbox'][2]+.1]


def _base(table,cell,header,caption,quantity,basis,unit,scope,**extra):
    n=number_token(cell['text'])
    if n is None:return None
    return dict(domain='Technical',kind='TECHNICAL_TABLE_CELL',physical_page=table['physical_page'],
                table_index=table['table_index'],row_index=cell['row'],column_index=cell['column'],
                bbox=cell['bbox'],bboxes=[cell['bbox']],header_path=header,header=' | '.join(header),
                scope=scope,table_caption=caption,raw_text=cell['text'],context=caption+' | '+' | '.join(header),
                quantity=quantity,basis=basis,unit=unit,issues=[],limitations=[],
                **n,**{'statistic':'SOURCE_TABLE_VALUE','evidence_mode':'TESTWORK',**extra})


def technical_cells(table,text):
    """Three physical table families; no filenames, source SHA or answer values."""
    cc=cells(table);out=[]
    captions=[x.strip() for x in text.splitlines() if re.search(r'^\s*Table\s+\d+(?:[-.]\d+)?\s*[:–-]',x,re.I)]
    caption=table.get('caption') or (captions[0] if len(captions)==1 else None)
    if not caption:return []
    for recognize in (_element_cells,_product_cells,_design_cells):
        result=recognize(table,cc,caption,text)
        if result:return result
    return []


def _element_cells(table,cc,caption,text):
    out=[]
    # Element rows beneath hierarchical crush/acid headers.
    elements=[c for c in cc if re.fullmatch(ELEMENTS,c['text'])]
    if elements and any('Extraction' in c['text'] and '%' in c['text'] for c in cc):
        first=min(c['row'] for c in elements)
        for label in elements:
            row=[c for c in cc if c['row']==label['row'] and c['bbox'][0]>=label['bbox'][2]-.1 and number_token(c['text'])]
            for position,cell in enumerate(row,1):
                header=path_above(cell,cc,first);h=' | '.join(header)
                if not re.search(r'Extraction.*%',h,re.I):continue
                sample=next((re.search(r'\b([\w-]+)\s+Final Extraction',s,re.I)[1] for s in header if re.search(r'\b([\w-]+)\s+Final Extraction',s,re.I)),None)
                grain=re.search(r'(\d+(?:\.\d+)?)\s*mm\s+crush',h,re.I)
                acid=re.search(r'(\d+(?:\.\d+)?)\s*g\s*/\s*L\s+(\w+)',h,re.I)
                c=_base(table,cell,header,caption,'extraction_pct',label['text'],'%',caption+' | '+str(sample),
                        sample_id=sample,sample_population=sample,source_column=position,endpoint='LEACH_SOLUTION',feed='ZONE_COMPOSITE',
                        scale='BOTTLE_ROLL' if re.search(r'bottle.?roll',caption,re.I) else 'LAB_SCALE_UNSPECIFIED',
                        grain_mm=float(grain[1]) if grain else None,acid_concentration=float(acid[1]) if acid else None,
                        acid_unit='g/L' if acid else None,reagent=acid[2] if acid else None)
                if c:out.append(c)
        grain_headers=[c for c in cc if c['row']<first and re.fullmatch(r'\d+(?:\.\d+)? mm crush',c['text'])]
        duplicate_grain=len({c['text'] for c in grain_headers})<len(grain_headers)
        acid_values={c.get('acid_concentration') for c in out}
        for c in out:
            if duplicate_grain:c['limitations'].append('DUPLICATE_GRAIN_LABEL_DIFFERENT_SOURCE_COLUMNS')
            if len(acid_values)==1:c['limitations'].append('NO_ACID_CONTRAST_IN_PRINTED_HEADERS')
            if re.search(r'kg/t',text,re.I):c['limitations'].append('TABLE_G_L_AND_NARRATIVE_KG_T_NOT_RECONCILED')
        return out


def _product_cells(table,cc,caption,text):
    out=[]
    # Test/product rows with quantity and element carried in column headers.
    products=[c for c in cc if re.match(r'^(?:F\d+\s+|Feed$)',c['text'])]
    if products and any(re.search(r'Test\s*/\s*Product',c['text'],re.I) for c in cc):
        first=min(c['row'] for c in products)
        for label in products:
            for cell in cc:
                if cell['row']!=label['row'] or cell['bbox'][0]<label['bbox'][2]-.1:continue
                header=path_above(cell,cc,first);h=' '.join(header)
                m=re.search(r'\b(TREO|MREO|Ce|Nd|Pr|Dy|Tb)\s+(Grade|Recovery)\b',h,re.I)
                if not m or '%' not in h:continue
                product=re.sub(r'^F\d+\s*','',label['text'])
                c=_base(table,cell,header,caption,m[2].lower()+'_pct',m[1],'%',caption,
                        test_id=re.match(r'F\d+',label['text'])[0] if re.match(r'F\d+',label['text']) else None,
                        product=product,endpoint=product,feed='SOURCE_TABLE_FEED',scale='LAB_FLOTATION',
                        sample_id=None,sample_population=None,source_column=None)
                if c:
                    c['statistic']='FEED_REFERENCE' if label['text']=='Feed' else 'SELECTED_INDIVIDUAL_TEST'
                    out.append(c)
        return out


def _design_cells(table,cc,caption,text):
    out=[]
    # Annual reagent mass and same-stage dry plant feed design parameters.
    headers=[c for c in cc if re.fullmatch(r'Stage\s+\w+',c['text'],re.I)]
    if headers and any(c['text']=='Units' for c in cc):
        unithead=next(c for c in cc if c['text']=='Units');deschead=next((c for c in cc if c['text']=='Description'),None)
        if not deschead:return []
        for ri in sorted({c['row'] for c in cc if c['row']>unithead['row']}):
            row=[c for c in cc if c['row']==ri]
            def aligned(head):
                x=(head['bbox'][0]+head['bbox'][2])/2
                return next((c for c in row if c['bbox'][0]<=x<=c['bbox'][2]),None)
            desc=aligned(deschead);unit=aligned(unithead)
            if not desc or not unit:continue
            y=(desc['bbox'][1]+desc['bbox'][3])/2
            group=[c['text'] for c in cc if c['bbox'][2]<deschead['bbox'][0] and c['bbox'][1]<=y<=c['bbox'][3] and c['text']]
            dry=bool(re.search(r'annual tonnage\s*\(dry\)',desc['text'],re.I) and unit['text']=='Mtpa')
            reagent='Reagents' in group and unit['text']=='tpa'
            if not dry and not reagent:continue
            for head in headers:
                cell=aligned(head)
                if not cell:continue
                c=_base(table,cell,[head['text'],desc['text'],unit['text']],caption,
                        'dry_feed_mtpa' if dry else 'reagent_tpa',None,unit['text'],caption+' | '+head['text'],
                        stage=head['text'],reagent=None if dry else desc['text'],feed='DRY_PLANT_FEED',endpoint='BENEFICIATION_PLANT',
                        scale='SCOPING_MODEL',sample_population=None)
                if c:c.update(evidence_mode='ENGINEERING_MODEL',statistic='ENGINEERING_DESIGN');out.append(c)
    return out


def direct_role(sentence,number):
    """Bind a percent to its own noun phrase, not every percent in a sentence."""
    before=sentence[:number['start']];after=sentence[number['start']+len(number['token']):]
    noun=r'(?:TREO|MREO|Nd|Pr|Dy|Tb|rare earth)?\s*(recovery|extraction)'
    prefix=re.search(noun+r'\s*(?:of\s+(?:Nd|Pr|Dy|Tb|TREO)\s+)?(?:of|is|was|reached|achieved|averaging|averaged|up to)?\s*$',before,re.I)
    suffix=re.match(r'\s*(?:TREO\s+|MREO\s+|rare earth\s+)?(recovery|extraction)\b',after,re.I)
    if not prefix and not suffix:return None
    local=before[-60:]+' '+after[:35]
    if re.search(r'(?:mining|core|water|moisture)\s+recovery|IRR|internal rate|deportment',local,re.I):return None
    quantity=(prefix or suffix)[1].upper()
    qualifier='MAXIMUM' if re.search(r'up to\s*$',before,re.I) else 'AVERAGE' if re.search(r'averag(?:e|ing|ed)(?:\s+of)?\s*$',before,re.I) else 'REPORTED'
    return qualifier+'_'+quantity



def flow_cells(tables,words,text,page):
    """Positioned From/To table body below a native merged header.

    Header rectangles, printed destination labels and word geometry define
    branches. A shared CUP header is never interpreted as a serial flow.
    """
    captions=[s.strip() for s in text.splitlines() if re.match(r'\s*Table\s+[\d-]+:.*recovery performance',s,re.I)]
    if len(captions)!=1:return []
    froms=[w for w in words if w[4]=='From'];tos=[w for w in words if w[4]=='To']
    if len(froms)!=1 or len(tos)!=1:return []
    fr,to=froms[0],tos[0]
    headers=[c for t in tables for c in cells(t) if c['row']==0 and re.search('Recovery|Overall',c['text'],re.I) and 'Parameters' not in c['text'] and c['bbox'][3]<=fr[1]+1]
    if len(headers)<3:return []
    def line_at(y):return sorted([w for w in words if abs(w[1]-y)<2],key=lambda w:w[0])
    fw,tw=line_at(fr[1]),line_at(to[1]);lines={}
    for w in words:
        if w[1]>to[3]+2:lines.setdefault(round(w[1]),[]).append(w)
    out=[]
    for ri,(_,ww) in enumerate(sorted(lines.items())):
        ww.sort(key=lambda w:w[0]);numeric=[w for w in ww if number_token(w[4]) and any(h['bbox'][0]<=sum(w[0:3:2])/2<=h['bbox'][2] for h in headers)]
        if len(numeric)<3:continue
        label=' '.join(w[4] for w in ww if w[2]<headers[0]['bbox'][0])
        if not label:continue
        element=re.match(r'(CeO2|Y2O3|TiO2|ZrO2|THM)\b',label)
        for ci,w in enumerate(numeric):
            x=(w[0]+w[2])/2;h=next((h for h in headers if h['bbox'][0]<=x<=h['bbox'][2]),None)
            if not h:continue
            f=' '.join(q[4] for q in fw if h['bbox'][0]<=(q[0]+q[2])/2<=h['bbox'][2])
            target=[q for q in tw if h['bbox'][0]<=(q[0]+q[2])/2<=h['bbox'][2]]
            if 'CUP' in h['text'] and len(target)>1:
                destination=min(target,key=lambda q:abs((q[0]+q[2])/2-x))[4]
            else:destination=' '.join(q[4] for q in target)
            cell=dict(text=w[4],row=ri,column=ci,bbox=list(w[:4]))
            quantity='grade_pct' if 'Grade' in label else 'stage_recovery_pct' if element else 'mass_fraction_pct'
            c=_base(dict(physical_page=page,table_index=headers[0].get('table_index',0)),cell,[h['text'],label,'From: '+f,'To: '+destination],captions[0],quantity,element[1] if element else None,'%',captions[0]+' | '+label,
                    source_column=ci+1,feed=f,endpoint=destination,from_material=f,to_material=destination,
                    sample_population=captions[0],sample_id=captions[0],scale='REPORTED_STAGE_PERFORMANCE',process_stage=h['text'],
                    fraction_scope=label,evidence_mode='REPORTED_PARAMETERS')
            if c:out.append(c)
    return out

def model_parameters(words,text,page):
    """Explicit dimensional consumption and oxide coefficients, not equation evaluation."""
    out=[];lines={}
    for w in words:lines.setdefault(round(w[1]),[]).append(w)
    for ri,(_,ww) in enumerate(sorted(lines.items())):
        ww.sort(key=lambda w:w[0]);line=' '.join(w[4] for w in ww)
        m=re.search(r'\b([A-Z][A-Za-z0-9]+)\s+Consumption\s+('+NUM+r')\s+kg/t\s+concentrate\b',line)
        coefficient=re.search(r'\b([A-Z][A-Za-z0-9]+)\s+Recovery\s+t\s+('+NUM+r')\s+x\s+([A-Z][A-Za-z0-9]+)\b',line)
        if not m and not coefficient:continue
        if m:
            label,token=m[1],m[2];quantity='reagent_intensity';unit='kg/t concentrate';basis=None;target='CONCENTRATE_TREATMENT';issues=[]
        else:
            label,token=coefficient[1],coefficient[2];quantity='downstream_recovery_factor';unit='fraction';basis=label;target='SOURCE_DEFINED_DOWNSTREAM_PRODUCTS';issues=[] if coefficient[1]==coefficient[3] else ['OXIDE_EQUATION_LABEL_CONFLICT']
        tokenword=[w for w in ww if w[4]==token]
        if len(tokenword)!=1:continue
        w=tokenword[0];caption=next((s.strip() for s in text.splitlines() if re.search(r'TREO Recovery Parameters|Key Concentrate Composition Equations',s,re.I)),None)
        if not caption:continue
        c=_base(dict(physical_page=page,table_index=-1),dict(text=token,row=ri,column=0,bbox=list(w[:4])),[line],caption,quantity,basis,unit,caption+' | '+label,
                reagent=label if m else None,feed='CONCENTRATE',endpoint=target,scale='DFS_MODEL',sample_population='SOURCE_DESIGN_PARAMETERS',evidence_mode='ENGINEERING_MODEL')
        c.update(issues=issues,statistic='ENGINEERING_DESIGN',raw_equation=line);out.append(c)
    return out

def technical_numbers(sentence):
    pattern=r'(?<![\w.])((?:'+NUM+r'\s*(?:–|—|to|-)\s*'+NUM+r'|'+NUM+r'))\s*%'
    return [dict(number_token(m[1]),unit='%',token=m[0],start=m.start(),quantity_role=None) for m in re.finditer(pattern,sentence)]

def sample_context(texts,sample,source_sha):
    """Only a paragraph naming the exact sample can carry its population claim."""
    if not sample:return None
    matches=[]
    for page,text in enumerate(texts,1):
        for paragraph in re.split(r'\n\s*\n',text):
            flat=' '.join(paragraph.split())
            if not re.search(r'(?<![\w-])'+re.escape(sample)+r'(?![\w-])',flat):continue
            representative=re.search(r'representative of ([^.]+)',flat,re.I)
            restricted=re.search(r'not\s+necessarily\s+reflective of ([^.]+)',flat,re.I)
            if representative or restricted:
                m=restricted or representative
                matches.append(dict(source_sha256=source_sha,pdf_page=page,quote=flat,sample_id=sample,
                                    target_population=m[1],qualification='SOURCE_LIMITATION_ONLY' if restricted else 'SOURCE_ASSERTION_ONLY',
                                    validation='EXACT_NAMED_SAMPLE_PARAGRAPH_IN_ORIGINAL',state='SELECTED_SAMPLE_LIMITATION' if restricted else 'SOURCE_ASSERTED'))
    return matches[0] if len(matches)==1 else None

def quantity_binding(sentence,number):
    role=direct_role(sentence,number)
    if not role:return dict(quantity_role=None,basis=None)
    before=sentence[:number['start']];after=sentence[number['start']+len(number['token']):]
    element=r'(TREO|MREO|CeO2|Nd2O3|Pr6O11|Dy2O3|Tb4O7|Nd|Pr|Dy|Tb)'
    suffix=re.match(r'\s*'+element+r'\s+(?:recovery|extraction)\b',after,re.I)
    prefix=re.search(element+r'\s+(?:recovery|extraction)\s*(?:of|is|was|reached|achieved)?\s*$',before,re.I)
    extraction=re.search(r'extraction of\s+'+element+r'\s+(?:reached|achieved|was)\s*$',before,re.I)
    basis=(suffix or prefix or extraction)[1] if suffix or prefix or extraction else None
    nature='SOURCE_REPORTED_QUANTITY_SCALE_UNRESOLVED'
    if re.search(r'design|model(?:led)?',sentence,re.I):nature='ENGINEERING_DESIGN_DISCLOSURE'
    elif re.search(r'expected|target(?:ing)?|planned|will',sentence,re.I):nature='FORWARD_LOOKING_TARGET'
    elif re.search(r'testwork|test results|laboratory|bench|pilot',sentence,re.I):nature='TESTWORK_DISCLOSURE_SCALE_REQUIRES_CONTEXT'
    return dict(quantity_role=role,basis=basis,evidence_nature=nature,statistic='SOURCE_REPORTED_MAXIMUM' if role.startswith('MAXIMUM') else 'SOURCE_REPORTED_MEAN' if role.startswith('AVERAGE') else 'SOURCE_REPORTED_POINT')


def metric_cells(table, text, words=()):
    """Explicit quantity / units / value rows; table shape proves no test scale."""
    cc=cells(table);out=[]
    caption=next((s.strip() for s in text.splitlines() if re.match(r'\s*Table\s+\d+\s+Key\s+Project\s+metrics',s,re.I)),None)
    if not caption:return out
    for label in cc:
        merged=re.fullmatch(r'((?:Average\s+)?(?:TREO recovery to concentrate|Concentrate grade))\s+(%\s*(?:TREO)?)\s+('+NUM+r')',label['text'],re.I)
        if merged:
            hits=[w for w in words if w[4]==merged[3] and label['bbox'][0]<=w[0]<=label['bbox'][2] and label['bbox'][1]<=w[1]<=label['bbox'][3]]
            if len(hits)!=1:continue
            w=hits[0];cell=dict(text=merged[3],bbox=list(w[:4]),row=label['row'],column=2)
            c=_base(table,cell,[merged[1],merged[2]],caption,'recovery_pct' if 'recovery' in merged[1].lower() else 'grade_pct','TREO','%',caption,
                    product='Concentrate',feed=None,endpoint='MINERAL_CONCENTRATE',scale=None,sample_population=None,evidence_mode='SOURCE_DISCLOSURE',statistic='REPORTED_LOM_MODEL_PARAMETER')
            if c:out.append(c)
            continue
        if not re.fullmatch(r'(?:Average\s+)?(?:TREO recovery to concentrate|Concentrate grade)',label['text'],re.I):continue
        row=[c for c in cc if c['row']==label['row'] and c['column']>label['column']]
        unit=next((c for c in row if c['text'].startswith('%')),None)
        values=[c for c in row if number_token(c['text'])]
        if not unit or len(values)!=1:continue
        quantity='recovery_pct' if 'recovery' in label['text'].lower() else 'grade_pct'
        c=_base(table,values[0],[label['text'],unit['text']],caption,quantity,'TREO','%',caption,
                product='Concentrate',feed=None,endpoint='MINERAL_CONCENTRATE',scale=None,
                sample_population=None,evidence_mode='SOURCE_DISCLOSURE',statistic='REPORTED_LOM_MODEL_PARAMETER')
        if c:out.append(c)
    return out


def bind_semantics(candidate, texts, source_sha):
    """V6 context binding. Native cell families cannot establish scientific metadata.

    Keep each supporting quote and page. Conflicting explicit local statements
    retain all candidates and leave the field unknown; never rank study stages.
    """
    c=candidate
    if c.get('kind')!='TECHNICAL_TABLE_CELL':return c
    n=c['physical_page'];local=[(i+1,texts[i]) for i in range(max(0,n-3),n)]
    evidence={};conflicts=[]
    # Title/header establishes document study type, not laboratory test scale.
    stage_patterns={'SCOPING_MODEL':r'\bscoping study\b','PFS_MODEL':r'\bpre[- ]feasibility study\b',
                    'DFS_MODEL':r'\b(?:definitive|bankable) feasibility study\b|\b(?:DFS|BFS)\b'}
    stage_hits=[]
    for value,pattern in stage_patterns.items():
        for page,t in [(1,texts[0][:3000]),(n,texts[n-1][-900:])]:
            for line in t.splitlines():
                if re.search(pattern,line,re.I):stage_hits.append(dict(value=value,pdf_page=page,quote=line.strip(),source_sha256=source_sha))
    stages={e['value'] for e in stage_hits}
    c['study_stage']=next(iter(stages)) if len(stages)==1 else None
    evidence['study_stage']=stage_hits
    if len(stages)>1:conflicts.append('STUDY_STAGE_CONTEXT_CONFLICT')
    # Remove family assumptions, retain explicit physical endpoints/units.
    if c['quantity'] in ('reagent_tpa','dry_feed_mtpa','downstream_recovery_factor','reagent_intensity'):
        c['scale']=c['study_stage']
        c['evidence_mode']='ENGINEERING_MODEL' if re.search(r'design|equation|parameter',c.get('table_caption',''),re.I) else 'SOURCE_DISCLOSURE'
        evidence['scale']=stage_hits
    elif c.get('scale')=='LAB_FLOTATION':c['scale']=None
    elif c.get('scale') in ('BOTTLE_ROLL','LAB_SCALE_UNSPECIFIED'):c['scale']=None
    elif c.get('scale')=='REPORTED_STAGE_PERFORMANCE':c['scale']=None
    if c.get('statistic')=='SELECTED_INDIVIDUAL_TEST':
        # A test identifier proves an individual row, not selection from a
        # larger experimental population. The source warning is kept separately.
        c['statistic']='SOURCE_REPORTED_TEST_ROW'
    if c.get('feed')=='ZONE_COMPOSITE':c['feed']=None
    scale_patterns={'BOTTLE_ROLL':r'bottle.?roll', 'LAB_FLOTATION':r'(?:laboratory|bench)[- ]?(?:scale)?.{0,40}flotation|flotation.{0,40}(?:laboratory|bench)',
                    'PILOT_FLOTATION':r'pilot[- ]?(?:scale)?.{0,40}flotation|flotation.{0,40}pilot'}
    scale_hits=[]
    for page,t in local:
        for line in t.splitlines():
            for value,pattern in scale_patterns.items():
                if re.search(pattern,line,re.I):scale_hits.append(dict(value=value,pdf_page=page,quote=line.strip(),source_sha256=source_sha))
    if c['quantity'] in ('extraction_pct','grade_pct','recovery_pct'):
        values={e['value'] for e in scale_hits};c['scale']=next(iter(values)) if len(values)==1 else None
        evidence['scale']=scale_hits
        if len(values)>1:conflicts.append('TEST_SCALE_CONTEXT_CONFLICT')
    if c.get('sample_id'):
        sample=c['sample_id']
        hits=[]
        for p,t in local:
            flat=' '.join(t.split());match=re.search(re.escape(sample)+r'.{0,40}composite|composite.{0,40}'+re.escape(sample),flat,re.I)
            if match:hits.append(dict(value='SOURCE_NAMED_COMPOSITE',pdf_page=p,quote=flat[max(0,match.start()-100):match.end()+200],source_sha256=source_sha))
        if hits:c['feed']='SOURCE_NAMED_COMPOSITE';evidence['feed']=hits
    # A printed footnote excludes La from base case; never replace it with zero.
    if c.get('quantity')=='downstream_recovery_factor':
        t=' '.join(texts[n-1].split())
        foot=re.search(r'\*\s*La2O3 recovery to final product.*?base case of the Project\)',t,re.I)
        if foot:
            c['scenario_evidence']=dict(source_sha256=source_sha,pdf_page=n,quote=foot[0])
            c['scenario']='LA_CIRCUIT_INCLUDED_ONLY' if c.get('basis')=='La2O3' else 'SOURCE_OTHER_OXIDE_COEFFICIENT'
            c['base_case_applicable']=False if c.get('basis')=='La2O3' else None
    c['semantic_evidence']=evidence;c['semantic_conflicts']=conflicts
    c['limitations'].extend(conflicts)
    c['semantics_version']='technical-context-v1'
    return c
