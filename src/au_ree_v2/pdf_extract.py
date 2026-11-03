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

DOCUMENT_VERSION = 'document-recognition-v1'
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
        if c['kind']=='LEACH_TABLE_ROW':
            labels=re.findall(r'TREO|MREO|Pr6O11|Nd2O3|Tb4O7|Dy2O3|Sc2O3',c['header'])
            tokens=re.findall('('+NUMBER+r')\s*%',c['raw_text'])
            if len(labels)!=len(tokens) or c['values']!={k:_number(v) for k,v in zip(labels,tokens)}:
                return ['ROW_TOKEN_VALUE_MISMATCH']
        elif c['kind']=='RESOURCE_TABLE_TOTAL':
            tokens=re.findall(NUMBER,re.sub(r'^\s*(?:Grand Total|Total)\s+','',c['raw_text'],flags=re.I))
            if c['values']['ore_mt']!=_number(tokens[0]) or c['values']['grade']!=_number(tokens[1]):
                return ['ROW_TOKEN_VALUE_MISMATCH']
            if c['values'].get('contained_treo_kt') is not None:
                factor=1 if re.search(r'000|\bkt\b',c['header'],re.I) else .001
                if c['values']['contained_treo_kt']!=_number(tokens[2])*factor:return ['ROW_TOKEN_VALUE_MISMATCH']
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


def narrative_candidates(text, page, registry):
    """Keep scoped technical and commercial facts, without guessing endpoints.

    Clauses are candidates until attribution, numeric token and semantic context
    are sufficient. Unstated feed/scale/date/conditions remain NULL.
    """
    flat=re.sub(r'\s+',' ',text);result=[]
    sentences=re.split(r'(?<=[.;])\s+(?=[A-Z])',flat)
    for i,sentence in enumerate(sentences):
        if len(sentence)<25:continue
        domain='Technical' if re.search(r'(?i)\b(?:recover\w*|extract\w*|leach\w*|reagent|thorium|uranium|NORM)\b',sentence) else ('Commercial' if re.search(r'(?i)\b(?:financing|offtake|off-take|financial close|drawdown|credit approval|grant|funding|cash position)\b',sentence) else ('Development' if re.search(r'(?i)\b(?:scoping study|PFS|DFS|care and maintenance|construction commenced)\b',sentence) else None))
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
        for number in numbers:
            prefix=sentence[max(0,number['start']-45):number['start']]
            number['quantity_role']=('MAXIMUM_EXTRACTION' if re.search(r'up to\s*$',prefix,re.I) else
                                     'AVERAGE_EXTRACTION' if re.search(r'averag(?:e|ing)\s*(?:of\s*)?$',prefix,re.I) else None)
            if not re.search(r'extract|recover|leach',sentence,re.I):number['quantity_role']=None
        # Text observations are valid disclosures, not numerical project scores.
        reasons=[]
        if not pid:reasons.append('PROJECT_ATTRIBUTION_AMBIGUOUS')
        if re.search(r'(?i)\b(?:will|planned|targeting|expected|aims|potential)\b',sentence):reasons.append('FORWARD_LOOKING_NOT_COMPLETED_EVENT')
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


def recognize_document(root, source, registry, tessdata=None):
    """Scan every page once, then extract tables/OCR only relevant pages."""
    import pymupdf
    root=Path(root);path=root/source['path']
    if filehash(path)!=source['sha256']:raise ValueError('SOURCE_HASH_MISMATCH')
    pages=[];candidates=[];tables=[]
    if source['kind']=='html':
        from .evidence import html_text
        texts=[html_text(root,source)];doc=None
    else:
        doc=pymupdf.open(path);texts=[p.get_text(sort=True) for p in doc]
    try:
        for n,text in enumerate(texts,1):
            labels=classify(text);method='MUPDF_POSITIONED' if doc else 'STATIC_HTML'
            if doc and not readable(text) and tessdata:
                extracted=extract_page(path,n,tessdata);text=extracted['text'];method=extracted['method'];labels=classify(text)
            relevant=bool(labels) and bool(re.search(r'TREO|rare earth|\bREE\b',text,re.I))
            page=dict(physical_page=n,method=method,labels=labels,relevant=relevant,text=text,
                      status='EXTRACTED' if readable(text) else 'UNREADABLE',tables=[])
            if relevant:
                recognized=resource_rows(text,n,registry)+leach_tables(text,n,registry)+narrative_candidates(text,n,registry)
                if doc and any(c['kind'] in ('RESOURCE_TABLE_TOTAL','LEACH_TABLE_ROW') for c in recognized):
                    try:
                        for i,t in enumerate(doc[n-1].find_tables().tables):
                            table=dict(physical_page=n,table_index=i,bbox=list(t.bbox),cells=t.extract(),
                                       header=t.header.names,external_header=t.header.external)
                            tables.append(table);page['tables'].append(i)
                    except Exception as exc:page['table_error']=type(exc).__name__
                for c in recognized:
                    c.update(source_sha256=source['sha256'],source_key=source['key'],
                             publication_date=source.get('publication_date'),effective_date=None,
                             date_role='PUBLICATION_DATE_ONLY_EFFECTIVE_DATE_NOT_INFERRED',
                             extraction_method=method,parser_version=DOCUMENT_VERSION)
                    # Word coordinates bind the row/paragraph to the physical page.
                    if doc:
                        needles=c['raw_text'].split()
                        boxes=doc[n-1].search_for(c['raw_text'][:150])
                        c['bboxes']=[list(b) for b in boxes]
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
        return dict(version=DOCUMENT_VERSION,observation_contract='automatic-observation-v1-element-basis',source_sha256=source['sha256'],source_key=source['key'],
                    source_url=source['url'],publication_date=source.get('publication_date') or publication_date(texts[0]),
                    labels=classify(texts[0]),mentioned_labels=sorted({v for p in pages for v in p['labels']}),pages=pages,tables=tables,candidates=candidates,
                    backend_version=pymupdf.VersionBind,registry_identity_sha256=__import__('hashlib').sha256(canonical(registry).encode()).hexdigest(),
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
                    if (cached['version']==DOCUMENT_VERSION and cached.get('observation_contract')=='automatic-observation-v1-element-basis'
                            and cached['registry_identity_sha256']==hashlib.sha256(canonical(registry).encode()).hexdigest()):
                        outcomes.append(dict(source_key=source['key'],source_sha256=source['sha256'],status='REUSED_VERIFIED_EXTRACTION',sha256=latest['sha256']))
                        continue
            data=recognize_document(root,source,registry,tessdata)
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


def extract_page(path, number, tessdata=None, markers=()):
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
            model=Path(tessdata)/'eng.traineddata'
            model_sha=filehash(model)
            tp=page.get_textpage_ocr(language='eng',dpi=200,full=True,tessdata=str(Path(tessdata).resolve()))
            text=page.get_text(textpage=tp);method='MUPDF_TESSERACT_200DPI_SELECTED_PAGE'
        return {'source_sha256':filehash(path),'physical_page':number,'version':'pdf-page-v1',
                'method':method,'backend_version':pymupdf.VersionBind,'model_sha256':model_sha,
                'native_error':native_error,'native_text':native,'positioned_text':alternate,'text':text,
                'status':'EXTRACTED_REQUIRES_SCOPE_VALIDATION' if good(text) else 'UNREADABLE',
                'transformations':['NATIVE_AND_POSITIONED_TEXT_ATTEMPTED','NO_GUESSED_CHARACTER_OR_NUMERIC_SUBSTITUTION']}


def capture_pages(root, source, pages, tessdata=None):
    """One source manifest, content-addressed derivatives, per-page isolation."""
    import hashlib
    root=Path(root);path=root/'data/manifest.json'
    manifest=json.loads(path.read_text(encoding='utf-8'));outcomes=[]
    if filehash(root/source['path'])!=source['sha256']:raise ValueError('PDF source checksum mismatch')
    for page in sorted(set(pages)):
        try:
            result=extract_page(root/source['path'],page,tessdata)
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
