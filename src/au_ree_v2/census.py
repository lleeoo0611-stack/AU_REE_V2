"""Read official project-list workbooks as source records, without fabricated Project IDs.

A row mentioning REE is a discoverable candidate, not proof that it is one
independent mining project, JORC resource, or an eligible MCDA alternative.
"""
import json
import re
from contextlib import closing, nullcontext
from functools import lru_cache
from io import BytesIO
from pathlib import Path
from openpyxl import load_workbook
from .store import canonical, entity, issue

REE = re.compile(r'rare[\s\-]*earth|\bTREO\b|\bREEs?\b',re.IGNORECASE)
STATES = {'WA','SA','NT','NSW','QLD','VIC','TAS','ACT'}

CANDIDATE_VERSION='ree-candidate-v3'
ELEMENTS='lanthanum cerium praseodymium neodymium promethium samarium europium gadolinium terbium dysprosium holmium erbium thulium ytterbium lutetium yttrium'.split()
SYMBOLS='La Ce Pr Nd Pm Sm Eu Gd Tb Dy Ho Er Tm Yb Lu Y'.split()
AGGREGATE=re.compile(r'(?<!\w)(?:REEs?|REOs?|TREO|HREEs?|LREEs?|NdPr|rare[\s-]*earths?(?:\s*elements?)?|lanthanides?)(?!\w)',re.I)


def classify_ree(fields, structured=(),version=None):
    """Candidate recall only; short element symbols require commodity context."""
    version=version or CANDIDATE_VERSION
    if version not in ('ree-candidate-v2','ree-candidate-v3'):raise ValueError('UNKNOWN_CANDIDATE_CLASSIFICATION_VERSION')
    matches=[];roles=set();structured=set(structured)
    for field,value in sorted(fields.items()):
        text=str(value or '')
        if field.casefold() in ('ticker','asx_code','company','company_name'):continue
        tests=[('REE_EXPLICIT',AGGREGATE),
               ('REE_ELEMENT',re.compile(r'(?<!\w)(?:'+'|'.join(ELEMENTS)+r')(?:\s+oxides?)?(?!\w)',re.I)),
               ('REE_MINERAL',re.compile(r'\b(?:monazite|xenotime)\b',re.I)),
               ('SCANDIUM_RELATED',re.compile(r'\bscandium(?:\s+oxide)?\b',re.I))]
        if field in structured:
            tests.append(('REE_ELEMENT',re.compile(r'(?<![A-Za-z0-9_])(?:'+'|'.join(SYMBOLS)+r'|La2O3|CeO2|Pr6O11|Nd2O3|Tb4O7|Dy2O3|Y2O3)(?![A-Za-z0-9_])')))
            if version=='ree-candidate-v3':tests.append(('SCANDIUM_RELATED',re.compile(r'(?<![A-Za-z0-9_])Sc(?:2O3)?(?![A-Za-z0-9_])')))
        elif version=='ree-candidate-v3' and re.search(r'\b(?:mineralisation|mineralization|assays?|ppm|significant)\b',text,re.I):
            # Narrative symbols require an explicit geological/assay context;
            # degree titles, company codes and normal prose remain excluded.
            tests.append(('REE_ELEMENT',re.compile(r'(?<![A-Za-z0-9_])(?:La|Ce|Pr|Nd|Tb|Dy|Y)(?![A-Za-z0-9_])')))
        for role,pattern in tests:
            for hit in pattern.finditer(text):
                if re.search(r'\b(?:ASX|LSE|TSX)\s*:\s*$',text[:hit.start()],re.I):continue
                roles.add(role);matches.append(dict(field=field,term=hit.group(),text=text,
                    field_role='STRUCTURED_COMMODITY' if field in structured else 'NARRATIVE_MENTION',role=role))
    role=('EXPLICIT_REE' if 'REE_EXPLICIT' in roles else 'REE_ELEMENT' if 'REE_ELEMENT' in roles else
          'MINERAL_ONLY' if 'REE_MINERAL' in roles else 'SC_ONLY' if roles else 'NO_REE_MATCH')
    if role in ('EXPLICIT_REE','REE_ELEMENT') and all(m['field_role']=='NARRATIVE_MENTION' for m in matches):role='MENTION_ONLY'
    return dict(version=version,include=bool(matches),role=role,matches=matches,
        reason='CANDIDATE_ONLY_NOT_PROJECT_OR_RESOURCE' if matches else 'NO_CONTEXTUAL_REE_TERM')

def ingest_workbook(db, root, source, candidate_version=None):
    path=Path(root)/source['path']
    try:
        workbook=path if path.suffix.lower() in ('.xlsx','.xlsm','.xltx','.xltm') else BytesIO(path.read_bytes())
        wb=load_workbook(workbook,read_only=True,data_only=True)
    except Exception as exc:
        issue(db,None,source['sha256'],'CENSUS_WORKBOOK_UNREADABLE',str(exc))
        return 0
    count=0
    try:
        for ws in wb.worksheets:
            headers=None
            for index, row in enumerate(ws.iter_rows(values_only=True),start=1):
                values=[str(v).strip() if v is not None else '' for v in row]
                if sum(bool(v) for v in values)<2:
                    continue
                if any(re.fullmatch(r'commodit(?:y|ies)|mineral(?:s)?',v,re.I) for v in values):
                    headers=values;continue
                fields={((headers[i] if headers and i<len(headers) and headers[i] else f'column_{i+1}')):v for i,v in enumerate(values)}
                structured=[k for k in fields if re.fullmatch(r'commodit(?:y|ies)|mineral(?:s)?',k,re.I)]
                decision=classify_ree(fields,structured,candidate_version) if candidate_version else None
                if not (decision['include'] if decision else any(REE.search(v) for v in values)):
                    continue
                native=f"{source['sha256']}:{ws.title}:{index}"
                eid=entity(db,'DISR_REMP_ROW',native,'SOURCE_RECORD')
                state=next((v.upper() for v in values if v.upper() in STATES),None)
                payload={'source_key':source['key'],'sheet':ws.title,'row_number':index,
                         'cells':values,'match_rule':candidate_version or 'REE_TERMS_V1',
                         **({'candidate_classification':decision,'original_fields':fields} if decision else {}),
                         'classification':'UNRESOLVED_PROJECT_CANDIDATE_SOURCE_RECORD'}
                db.execute('INSERT OR IGNORE INTO records VALUES(?,?,?,?,?,?,?,?,?)',
                           (eid,source['sha256'],f"{ws.title}!{index}",state,None,None,None,None,
                            canonical(payload)))
                count+=1
    finally:
        wb.close()
    if count==0:
        issue(db,None,source['sha256'],'NO_REE_WORKBOOK_ROWS',
              'No multi-cell rows match versioned REE terms; inspect workbook layout')
    return count


# Integrated summary rules: reviewed functions, canonical evidence only.
import csv
import math
import sqlite3
from collections import Counter, defaultdict
from datetime import date
from decimal import Decimal, InvalidOperation
from .store import digest, filehash
from .selection import choose, date_end
from .evidence_model import compatible_resource_context


def summary_resource_bundle(observations, partial_resource=None):
    """Require paired ore/TREO by default; partial projection needs explicit proof."""
    if partial_resource is not None:
        partial_resource_bundle=summary_partial_bundle
        return partial_resource_bundle(observations, partial_resource)
    for o in observations:
        try:raw=json.loads(o.get('raw','{}'))
        except (TypeError,ValueError):raw={}
        if isinstance(raw,dict) and raw.get('partial_resource_projection'):
            return None,'PARTIAL_RESOURCE_OPT_IN_REQUIRED'
    grouped=defaultdict(list)
    for o in observations:
        if o['status']=='AUTO_VALIDATED' and o['variable'] in ('ore_mt','grade','contained_treo_kt') and o['basis']=='TREO':
            grouped[(o['source_sha'],o['statement_id'],o['scope'],o['effective_date'])].append(o)
    options=[]
    for key,rows in grouped.items():
        if not compatible_resource_context(rows):
            continue
        values={};invalid=False
        for variable in ('ore_mt','grade','contained_treo_kt'):
            found=[r for r in rows if r['variable']==variable]
            distinct={(r['value'],r['unit'],r['basis']) for r in found}
            if len(distinct)>1:invalid=True
            if found:values[variable]=found[0]
        if invalid or not {'ore_mt','grade'}<=values.keys():continue
        ore,grade=values['ore_mt'],values['grade']
        if ore['unit']!='Mt' or grade['unit'] not in ('ppm','%'):continue
        if not all(isinstance(r['value'],(int,float)) and math.isfinite(r['value']) for r in values.values()):continue
        pct=grade['value']/10000 if grade['unit']=='ppm' else grade['value']
        if ore['value']<=0 or not 0<pct<=100:continue
        calculated=ore['value']*pct*10
        reported=values.get('contained_treo_kt');rounding={}
        if reported:
            if reported['unit'] not in ('kt','kt TREO') or reported['value']<0:continue
            half_ore=json.loads(ore['raw']).get('rounding_half_width') or 0
            half_grade=json.loads(grade['raw']).get('rounding_half_width') or 0
            factor=.001 if grade['unit']=='ppm' else 10
            lo=(ore['value']-half_ore)*(grade['value']-half_grade)*factor
            hi=(ore['value']+half_ore)*(grade['value']+half_grade)*factor
            rounding=dict(lower_kt=lo,upper_kt=hi)
            if not lo-1e-8<=reported['value']<=hi+1e-8:continue
        value=dict(ore_mt=ore['value'],grade_pct=pct,contained_treo_kt=reported['value'] if reported else calculated)
        options.append(dict(evidence_id=digest(key),source_sha256=key[0],statement_id=key[1],scope=key[2],effective_date=key[3],
            basis='TREO',value=value,observations=rows,contained_method='REPORTED' if reported else 'ORE_MT_X_GRADE_PERCENT_X_10',rounding=rounding))
    selected,reason=choose(options,('scope','basis'))
    return selected,reason

def summary_complete_sum(elements,required):
    return sum(elements[k] for k in required) if all(k in elements and elements[k] is not None for k in required) else None

def summary_reported_oxide_group(same,bundle,variable,basis,material_basis):
    """Project the explicitly reported group on its matched resource basis."""
    if bundle.get('partial_resource_projection'):return None
    groups=[o for o in same if o['variable']==variable and o['unit']=='ppm' and o['basis']==basis and
        json.loads(o['raw']).get('material_basis')==material_basis]
    grade=bundle['value']['grade_pct']*10000
    if not math.isfinite(grade) or grade<=0:return None
    if not groups or len({o['value'] for o in groups})!=1 or not 0<=groups[0]['value']<=grade:return None
    g=groups[0]
    return dict(observation=g,contained_kt=bundle['value']['ore_mt']*g['value']*.001,share_percent=g['value']/grade*100)


def summary_matching_resource_pdf(observation, raw, bundle):
    """Allow page-verified composition from an explicitly matched PDF edition."""
    reference = raw.get('census_equivalent_resource_pdf')
    if not reference or bundle.get('partial_resource_projection'):
        return False
    ore = next(o for o in bundle['observations'] if o['variable']=='ore_mt')
    return (
        observation['source_sha'] != bundle['source_sha256']
        and bool(raw.get('page_extraction_sha256'))
        and reference == dict(source_sha256=bundle['source_sha256'], **bundle['value'])
        and all(observation[k] == bundle[k] for k in ('statement_id','scope','effective_date'))
        and observation['category'] == ore['category']
    )

def summary_decimal_token(value):
    if not isinstance(value,str) or not re.fullmatch(r'(?:0|[1-9][0-9]*)(?:\.[0-9]+)?',value):
        raise ValueError('NUMERIC_PRESENTATION_SOURCE_TOKEN')
    return Decimal(value)

def summary_decimal_text(value):
    return format(value,'f').rstrip('0').rstrip('.') if '.' in format(value,'f') else format(value,'f')

def summary_classify_stage(text, has_mre, rules):
    """Return a proposal, never approval. Ambiguous completion stays in review."""
    text = (text or '').strip()
    result = {'source_text': text, 'code': None, 'category': None, 'rule': None, 'reason': ''}
    def finish(reason, code=None, ongoing=False):
        result.update(reason=reason, code=code, category=rules['stage_categories'].get(code), rule=rules['stage_rules'].get(code), ongoing_study=ongoing)
        return result
    if not text:
        return finish('NO_NATIVE_STAGE_TEXT')
    t = text.lower()
    if re.search(rules['stage_pattern_96'], t):
        return finish('WITHDRAWAL_REQUIRES_RESEARCHER_REVIEW')
    if re.search(rules['stage_pattern_98'], t):
        return finish('OPERATING_NOT_EVIDENCE_OF_DESIGN_CAPACITY')
    if re.search(rules['stage_pattern_100'], t):
        return finish('NEGATED_OR_CONTRADICTORY_STAGE_REQUIRES_REVIEW')
    future = rules['stage_future']
    if re.search(rules['stage_pattern_103'], t) and re.search(future, t):
        return finish('PLANNED_OR_CONDITIONAL_DEVELOPMENT_REQUIRES_REVIEW')
    if re.search(rules['stage_pattern_105'], t):
        return finish('EXPLICIT_CONSTRUCTION', 'C2')
    if re.search(rules['stage_pattern_107'], t):
        return finish('EXPLICIT_FINAL_INVESTMENT_DECISION', 'C1')
    study = re.compile(rules['stage_pattern_109'])
    completed, unknown, ongoing = [], False, False
    completed_levels, ongoing_levels = [], []
    def level(label):
        return 1 if 'scoping' in label else 2 if re.search(rules['stage_pattern_113'], label) else 3
    # Each status binds to one adjacent study mention, never to a whole clause.
    clauses = re.split(rules['stage_pattern_115'], t)
    for clause in clauses:
        matches = list(study.finditer(clause))
        if not matches:
            continue
        for index, m in enumerate(matches):
            # A directly parenthesized acronym is the same mention, not a second study.
            if index and level(matches[index-1].group()) == level(m.group()) and re.fullmatch(rules['stage_pattern_122'], clause[matches[index-1].end():m.start()]) and clause[m.end():].lstrip().startswith(')'):
                continue
            previous_end = matches[index-1].end() if index else 0
            next_start = matches[index+1].start() if index+1 < len(matches) else len(clause)
            prefix, suffix = clause[previous_end:m.start()], clause[m.end():next_start]
            done = bool(
                re.search(rules['stage_pattern_128'], prefix)
                or re.match(rules['stage_pattern_129'], suffix))
            progress = bool(
                re.search(rules['stage_pattern_131'], prefix)
                or re.match(rules['stage_pattern_132'], suffix))
            conditional = bool(re.search(future, prefix)) or bool(re.match(rules['stage_pattern_133'], suffix))
            if conditional:
                progress = True
                done = False
            if progress:
                ongoing = True
                ongoing_levels.append(level(m.group()))
                if done:
                    return finish('CONFLICTING_STUDY_COMPLETION_FOR_SAME_STUDY')
                continue
            if not done:
                unknown = True
                continue
            label = m.group()
            completed.append('B1' if re.search(rules['stage_pattern_147'], label) else 'B2')
            completed_levels.append(level(label))
    if completed_levels and ongoing_levels and max(completed_levels) >= min(ongoing_levels):
        return finish('CONTRADICTORY_COMPLETED_AND_IN_PROGRESS_STUDIES')
    if unknown:
        return finish('STUDY_COMPLETION_NOT_EXPLICIT')
    if completed:
        return finish('HIGHEST_EXPLICIT_COMPLETED_STUDY', max(completed), ongoing)
    if ongoing:
        return finish('IN_PROGRESS_WITHOUT_COMPLETED_PREVIOUS_STUDY')
    if re.search(rules['stage_pattern_157'], t):
        if has_mre is None:
            return finish('SELECTED_MRE_STATUS_UNVERIFIED')
        return finish('EXPLORATION_SELECTED_MRE_SPLIT', 'A2' if has_mre else 'A1')
    return finish('UNMAPPED_STAGE_REQUIRES_REVIEW')

def summary_stage_case(row, proposal, native, rules):
    """Explicitly scoped proposal; approval is still checked by the caller."""
    case = rules['stage_cases'].get(row['專案ID'])
    if case is None or proposal['code'] is not None:
        return proposal
    code, rule = case
    if proposal['reason'] != rules['stage_case_reasons'][rule]:
        return proposal
    if rule == 'NAMED_STUDY_TREATED_AS_COMPLETED':
        # Reject a changed study name that no longer supports the reviewed level.
        text = str(row.get('開發階段', '')).lower()
        lower = bool(re.search(r'scoping|pre[ -]?feasibility|preliminary feasibility|\bpfs\b', text))
        higher = bool(re.search(r'bankable|definitive|\bbfs\b|\bdfs\b|(?<!pre-)feasibility study', text))
        if (code == 'B1' and not lower) or (code == 'B2' and (lower or not higher)):
            return proposal
    result = dict(proposal, code=code, category=rules['stage_categories'][code], rule=rule,
                  ongoing_study=False)
    qualifiers = []
    if rule == 'IN_PROGRESS_STUDY_IMPLIES_B1':
        qualifiers.append('IN_PROGRESS_STUDY')
    dates = [str(native.get(k) or '') for k in ('publication_date', 'document_issue_date', 'effective_date')]
    if any(re.fullmatch(r'\d{4}-\d{2}(?:-\d{2})?', d) and d < '2021-01-01' for d in dates):
        qualifiers.append('STAGE_SOURCE_DATED')
    result['qualifier'] = '|'.join(qualifiers)
    if code == 'D':
        result['production_scope'] = 'PRODUCTION_COMMENCED_AT_SOURCE_DATE_NOT_DESIGN_CAPACITY'
    if code == 'X':
        result['withdrawal_scope'] = 'RESEARCH_ROW_RETAINED_DENOMINATOR_UNCHANGED'
    return result

def summary_template_fills(row, provenance, book, fields):
    cfg = book['config']; result = []; FIELDS=fields
    for group, (source, targets) in FIELDS.items():
        entry = cfg['mappings'][group].get(row.get(source, ''))
        if entry is None:
            continue
        native = next((p for p in provenance if p['project_id'] == row['專案ID'] and p['column'] == source), None)
        if native is None:
            raise ValueError('TEMPLATE_MAPPING_NATIVE_PROVENANCE_REQUIRED')
        for key, column in targets.items():
            if row[column] != '':
                continue
            result.append(dict(column=column, value=entry[key], sha=native['source_sha256'],
                locator='user CSV vocabulary; exact dated native description from '+source,
                method='USER_PROVIDED_TEMPLATE_MAPPING_FROM_'+source,
                scope=canonical(dict(mapping_version=cfg['version'], mapping_sha256=book['sha256'],
                    vocabulary_source_sha256=cfg['source']['sha256'], source_column=source,
                    source_value=row[source], source_provenance=native, template_label=entry['template_label'],
                    rationale=entry['rationale'], temporal_scope='AT_NATIVE_SOURCE_DATE_NOT_CURRENT_STATUS',
                    codebook_approval='UNCHANGED_DRAFT;ONLY_THESE_EXPLICIT_MAPPINGS'))))
    return result

def summary_native_column(doc, binding, label, header_y, unit_y):
    """Bind one native header, ppm unit and one token to the selected exact row."""
    import pymupdf
    region_text=summary_region_text; norm=summary_norm
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

def summary_settings(root):
    book=json.loads((Path(root)/'config/summary_rules.json').read_text(encoding='utf8'))
    if any(not p.get('source_file') or not p.get('source_key') for p in book['parameters'].values()):
        raise ValueError('SUMMARY_RULE_ORIGIN_REQUIRED')
    rules={k:v['value'] for k,v in book['parameters'].items()}
    decisions=json.loads((Path(root)/'config/researcher_rule_decisions.json').read_text(encoding='utf8'))['decisions']
    return rules,[d for d in decisions if isinstance(d.get('decided_by'),str) and d['decided_by'].strip()]


def summary_decision(decisions, rule, project_id=None, bundle=None):
    matches=[d for d in decisions if d.get('rule')==rule and (project_id is None or d.get('project_id')==project_id)]
    if bundle is not None:
        matches=[d for d in matches if isinstance(d.get('scope'),dict) and
            d['scope'].get('statement_id')==bundle['statement_id'] and d['scope'].get('source_sha256')==bundle['source_sha256']]
    if len(matches)>1:raise ValueError('SUMMARY_AMBIGUOUS_RULE_DECISION:'+rule)
    return matches[0] if matches else None


def summary_norm(text):
    return re.sub(r'\s+',' ',str(text)).strip().casefold()


def summary_region_text(page, rect):
    words=[w for w in page.get_text('words',sort=True)
           if rect.x0<=(w[0]+w[2])/2<=rect.x1 and rect.y0<=(w[1]+w[3])/2<=rect.y1]
    return ' '.join(w[4] for w in words)


def summary_hm_percent(raw, target):
    value = summary_decimal_token(raw['original_token'])
    conversion = raw.get('species_conversion')
    if not conversion:
        return value
    Pr, Tb, O = map(Decimal, ('140.908', '158.925', '15.999'))
    factors = {
        ('Pr2O3', 'Pr6O11'): (6*Pr + 11*O) / (3*(2*Pr + 3*O)),
        ('Tb2O3', 'Tb4O7'): (4*Tb + 7*O) / (2*(2*Tb + 3*O))
    }
    pair = (conversion.get('source_species'), conversion.get('target_species', target))
    if (conversion.get('method') != 'STOICHIOMETRIC_STANDARD_ATOMIC_WEIGHTS' or
            pair not in factors or pair[1] != target):
        raise ValueError('HM_SPECIES_CONVERSION_UNSUPPORTED')
    factor = factors[pair]
    if abs(Decimal(str(conversion.get('factor', factor))) - factor) > factor * Decimal('1e-12'):
        raise ValueError('HM_SPECIES_FACTOR_MISMATCH')
    return value * factor


def summary_partial_contract(observations, source):
    """Recheck native denominator/species proofs, never trust a migrated success flag."""
    import pymupdf
    contracts=[json.loads(o['raw']).get('review_contract',{}) for o in observations]
    reviews=[r for r in contracts if r.get('partial_resource_projection')]
    if not reviews:return None
    if len({canonical(r) for r in reviews})!=1:raise ValueError('PARTIAL_RESOURCE_CONTRACT_CONFLICT')
    review=reviews[0];spec=review['partial_resource_projection'];contract=dict(spec)
    def proof(doc,e):
        text=summary_norm(doc[e['page']-1].get_text())
        if not e.get('markers') or any(summary_norm(m) not in text for m in e['markers']):
            raise ValueError('PARTIAL_RESOURCE_PROOF_MISSING')
    def derived_mass(mass):
        if (mass is not spec['mass_inputs']['hm_mass_mt'] or
                mass['derivation'] != 'ORE_MT_X_HM_GRADE_PERCENT' or mass['unit'] != 'Mt'):
            raise ValueError('HM_MASS_DERIVATION_UNSUPPORTED')
        inputs = mass['inputs']
        for name, unit in (('ore_mt', 'Mt'), ('hm_grade_percent', '%')):
            item = inputs[name]
            proof(doc, item['evidence'])
            binding = item['cell_binding']
            page = doc[binding['page']-1]
            rect = pymupdf.Rect(binding['row_bbox']) & pymupdf.Rect(binding['column_bbox'])
            token = summary_region_text(page, rect).replace(',', '')
            native_unit = summary_region_text(page, pymupdf.Rect(binding['unit_bbox'])).strip('() ')
            if (item['evidence']['page'] != binding['page'] or len(item['evidence']['markers']) < 2 or
                    item['unit'] != unit or native_unit != unit):
                raise ValueError('HM_DERIVED_INPUT_UNIT_OR_MARKERS')
            if token != str(item['original_token']) or Decimal(str(item['value'])) != Decimal(token):
                raise ValueError('HM_DERIVED_INPUT_CELL_MISMATCH')
        ore_value = Decimal(str(inputs['ore_mt']['value']))
        value = ore_value * Decimal(str(inputs['hm_grade_percent']['value'])) / 100
        if ore_value != Decimal(str(spec['mass_inputs']['ore_mt']['value'])) or value != Decimal(str(mass['value'])):
            raise ValueError('HM_DERIVED_MASS_MISMATCH')
    with pymupdf.open(source['resolved_path']) as doc:
        if spec['mode']=='BULK_ORE_AND_HM_HOSTED_OXIDES_ONLY':
            for mass in spec['mass_inputs'].values():
                if mass.get('derivation'):
                    derived_mass(mass)
                    continue
                proof(doc,mass['evidence']);binding=mass['cell_binding'];page=doc[binding['page']-1]
                rect=pymupdf.Rect(binding['row_bbox']) & pymupdf.Rect(binding['column_bbox'])
                token=summary_region_text(page,rect).replace(',','')
                if Decimal(token)!=Decimal(str(mass['original_token']).replace(',','')) or mass['unit']!='Mt':
                    raise ValueError('HM_MASS_NATIVE_CELL_MISMATCH')
            for key in ('denominator_proof','mass_cutoff_proof','oxide_cutoff_proof'):proof(doc,spec[key]['evidence'])
            ore=spec['mass_inputs']['ore_mt']['value'];hm=spec['mass_inputs']['hm_mass_mt']['value'];oxides=[]
            for o in observations:
                raw=json.loads(o['raw'])
                if o['variable']=='ore_mt':
                    if o['value']!=ore or o['unit']!='Mt':raise ValueError('HM_ORE_MASS_MISMATCH')
                elif o['basis'] in ('La2O3','CeO2','Pr6O11','Nd2O3','Sm2O3','Eu2O3','Gd2O3','Tb4O7','Dy2O3','Ho2O3','Er2O3','Tm2O3','Yb2O3','Lu2O3','Y2O3'):
                    pct = summary_hm_percent(raw, o['basis'])
                    oxides.append(o['basis'])
                    left = Decimal(str(ore)) * Decimal(str(o['value'])) * Decimal('.001')
                    right = Decimal(str(hm)) * pct * 10
                    valid = (raw.get('original_unit') == '%HM' and raw.get('normalization') ==
                             'REPORTED_HM_MASS_X_OXIDE_PERCENT_DIVIDED_BY_BULK_ORE')
                    if not valid or abs(left-right) > max(abs(left), abs(right)) * Decimal('1e-12'):
                        raise ValueError('HM_SOURCE_MASS_TRANSFORM_MISMATCH')
            if len(oxides)!=15 or len(set(oxides))!=15:raise ValueError('HM_FIFTEEN_MATCHED_OXIDES_REQUIRED')
        else:
            basis=spec['basis_proof'];proof(doc,basis['evidence'])
            actual=summary_norm(summary_region_text(doc[basis['page']-1],pymupdf.Rect(basis['row_bbox'])))
            if actual!='cerium ce2o3 1.171' or spec.get('source_species')!='Ce2O3':
                raise ValueError('CERIUM_NATIVE_SPECIES_NOT_VERIFIED')
            header=spec['resource_header']
            if summary_norm(summary_region_text(doc[header['page']-1],pymupdf.Rect(header['bbox'])))!='ce2o3':
                raise ValueError('CERIUM_SELECTED_HEADER_MISMATCH')
        if confirmation := spec.get('in_situ_treo_confirmation'):
            try:
                proof(doc,confirmation)
                selected=[o for o in observations if o['variable']=='grade' and o['basis']=='TREO'
                          and o['unit']=='%' and o['source_sha']==review['source_sha256']
                          and all(o[k]==review[k] for k in ('statement_id','scope','effective_date'))]
                if len(selected)!=1:raise ValueError('IN_SITU_TREO_GRADE_BINDING_NOT_UNIQUE')
                grade=selected[0];native=json.loads(grade['raw']);binding=native['cell_binding']
                page=doc[binding['page']-1]
                rect=pymupdf.Rect(binding['row_bbox']) & pymupdf.Rect(binding['column_bbox'])
                ppm=Decimal(summary_region_text(page,rect).replace(',',''))
                unit=summary_region_text(page,pymupdf.Rect(binding['unit_bbox'])).strip()
                if (binding['page']!=confirmation['page'] or unit!='ppm'
                        or ppm/10000!=Decimal(str(grade['value'])) or ppm<=0):
                    raise ValueError('IN_SITU_TREO_NATIVE_PPM_MISMATCH')
                contained_kt=Decimal(str(spec['mass_inputs']['ore_mt']['value']))*ppm/1000
                if contained_kt*1000<=Decimal(str(confirmation['reported_lower_bound_tonnes'])):
                    raise ValueError('IN_SITU_TREO_REPORTED_LOWER_BOUND_FAILED')
                contract['verified_in_situ_treo']=dict(grade_pct=ppm/10000,contained_treo_kt=contained_kt)
            except (IndexError,KeyError,ValueError,InvalidOperation) as exc:
                contract['in_situ_treo_review_status']=str(exc)
    contract.update({k:review[k] for k in ('source_sha256','statement_id','scope','effective_date')})
    contract['basis_proof_verified']=True
    return contract


def summary_partial_bundle(observations, contract):
    """Paired mass/oxide scope only; partial resources never invent total TREO."""
    if not contract.get('basis_proof_verified'):return None,'PARTIAL_PROOFS_REQUIRED'
    key=tuple(contract[k] for k in ('source_sha256','statement_id','scope','effective_date'))
    rows=[o for o in observations if (o['source_sha'],o['statement_id'],o['scope'],o['effective_date'])==key]
    if not compatible_resource_context(rows):
        return None,'PARTIAL_RESOURCE_STATEMENT_CONTEXT_CONFLICT'
    ores=[o for o in rows if o['variable']=='ore_mt' and o['unit']=='Mt' and o['value']>0]
    if not ores or len({o['value'] for o in ores})!=1:return None,'PARTIAL_ORE_REQUIRED'
    treo=contract.get('verified_in_situ_treo',{})
    return dict(source_sha256=key[0],statement_id=key[1],scope=key[2],effective_date=key[3],
        basis='SOURCE_SCOPED_PARTIAL_OXIDES',value=dict(ore_mt=ores[0]['value'],**treo),observations=rows,
        partial_resource_projection=contract,contained_method='ORE_MT_X_VERIFIED_IN_SITU_TREO_PPM_X_0_001' if treo else None),''


def summary_resource_fields(row, observations, sources, rules, decisions, put, project=None):
    decoded=[dict(o,raw=canonical(summary_observation(o))) for o in observations]
    contracts={canonical({k:r[k] for k in ('source_sha256','statement_id','scope','effective_date')})
        for o in decoded if (r:=json.loads(o['raw']).get('review_contract',{})) and
        r.get('selection_role',r.get('resource_selection_role','PREFERRED'))=='PREFERRED' and o['variable']=='ore_mt'}
    declared={canonical({k:r[k] for k in ('source_sha256','statement_id','scope','effective_date')})
        for o in (project or {}).get('observations',[]) if o['variable']=='ore_mt' and
        (r:=o.get('raw',{}).get('review_contract',{})) and
        r.get('selection_role',r.get('resource_selection_role','PREFERRED'))=='PREFERRED'}
    if declared:contracts=declared
    if len(contracts)>1:return None,{},'MULTIPLE_PREFERRED_RESOURCE_STATEMENTS'
    primary=decoded
    if contracts:
        contract=json.loads(next(iter(contracts)))
        primary=[o for o in decoded if all(o[k]==contract[v] for k,v in [('source_sha','source_sha256'),('statement_id','statement_id'),('scope','scope'),('effective_date','effective_date')])]
    partial=None
    try:
        first=next((o for o in primary if json.loads(o['raw']).get('review_contract',{}).get('partial_resource_projection')),None)
        if first:partial=summary_partial_contract(primary,sources[first['source_sha']])
    except (KeyError,ValueError,IndexError,InvalidOperation):return None,{},'PARTIAL_RESOURCE_PROOF_INVALID'
    bundle,reason=summary_resource_bundle(primary,partial)
    if not bundle:return None,{},reason if primary else 'NO_VALIDATED_RESOURCE_OBSERVATIONS'
    sha=bundle['source_sha256'];scope=bundle['scope'];ids=[o['obs_id'] for o in bundle['observations']]
    locator='; '.join(sorted({o['locator'] for o in bundle['observations']}))
    for variable,column in [('ore_mt','礦石蘊藏量_Mt'),('grade_pct','TREO品位_pct'),('contained_treo_kt','總TREO蘊藏量_kt')]:
        if variable in bundle['value']:put(column,bundle['value'][variable],sha,locator,
            bundle['contained_method'] if variable=='contained_treo_kt' else 'SAME_SOURCE_STATEMENT_SCOPE_DATE',scope,ids)
    if 'grade_pct' in bundle['value']:put('有TREO資源估計','是',sha,locator,'COMPLETE_SOURCE_BOUND_RESOURCE_PAIR',scope,ids)
    put('資料來源名稱',sources[sha]['key'],sha,locator);put('資料來源URL',sources[sha]['url'],sha,locator)
    same=[o for o in primary if (o['source_sha'],o['statement_id'],o['scope'],o['effective_date'])==
          (sha,bundle['statement_id'],scope,bundle['effective_date'])
          and compatible_resource_context([*bundle['observations'],o])]
    supplemental=[o for o in decoded if summary_matching_resource_pdf(o,json.loads(o['raw']),bundle)
                  and compatible_resource_context([*bundle['observations'],o])]
    # A bulk pair with an unspecified cutoff can be individually compatible with
    # two mutually incompatible element rows. Test the proposed composition as a set.
    if not compatible_resource_context([*same,*supplemental]):
        core_ids = {o['obs_id'] for o in bundle['observations']}
        bundle['incompatible_component_ids'] = {o['obs_id'] for o in [*same,*supplemental]} - core_ids
        same = [o for o in same if o['obs_id'] in core_ids]
        supplemental = []
    ids=sorted({o['obs_id'] for o in same})
    shares=[o for o in same if o['variable']=='magnet_reo_share_pct' and o['unit']=='%' and
        o['basis'] in ('PrNdDyTb_OXIDES_OVER_TREO','PrNdDyTb_REO_DIV_TREO') and 0<=o['value']<=100]
    group=summary_reported_oxide_group(same,bundle,'reported_resource_magnet_ppm','PrNdDyTb_OXIDES',
        'RESOURCE_ORE_GRADE_MAGNET_OXIDE_GROUP_PPM')
    if not shares and group:
        group_locator='; '.join(sorted({locator,group['observation']['locator']}))
        put('磁鐵稀土氧化物蘊藏量_kt',group['contained_kt'],sha,group_locator,'ORE_MT_X_REPORTED_MAGNET_OXIDE_GROUP_PPM_X_0_001',scope,ids)
        put('磁鐵稀土佔TREO_pct',group['share_percent'],sha,group_locator,'REPORTED_MAGNET_GROUP_PPM_DIV_MATCHED_TREO_PPM_X_100',scope,ids)
    if not partial and shares and len({o['value'] for o in shares})==1:
        put('磁鐵稀土佔TREO_pct',shares[0]['value'],sha,shares[0]['locator'],'SOURCE_REPORTED',scope,[shares[0]['obs_id']])
        put('磁鐵稀土氧化物蘊藏量_kt',bundle['value']['contained_treo_kt']*shares[0]['value']/100,sha,locator,'TREO_KT_X_MAGNET_SHARE_PERCENT',scope,ids)
    composition=[*same,*supplemental]
    composition_ids=sorted({o['obs_id'] for o in composition})
    composition_sha=';'.join(sorted({o['source_sha'] for o in composition}))
    composition_locator='; '.join(sorted({locator,*(o['locator'] for o in supplemental)}))
    elements={};review=next((json.loads(o['raw']).get('review_contract') for o in same if json.loads(o['raw']).get('review_contract')),None)
    matched_composition_denominator=not any(json.loads(o['raw']).get('composition_denominator_basis')=='TREO_EXCLUDES_Y2O3' for o in supplemental)
    for oxide in rules['oxides']:
        found=[o for o in composition if o['basis']==oxide and o['unit']=='ppm' and
            json.loads(o['raw']).get('material_basis')=='RESOURCE_ORE_GRADE_OXIDE_PPM']
        if not found and not partial:
            contained=[o for o in composition if o['basis']==oxide and o['unit']=='kt' and
                (raw:=json.loads(o['raw'])).get('material_basis')=='RESOURCE_CONTAINED_OXIDE_MASS_KT' and
                raw.get('transform',{}).get('rule') in ('SUM_RECONCILED_RESOURCE_BLOCK_MASSES',
                                                       'SUM_SAME_CUTOFF_CATEGORY_OXIDE_MASSES',
                                                       'RECONCILED_AGGREGATE_OXIDE_RESIDUAL_KT',
                                                       'REVIEWED_IMAGE_ROW_CEO2_DIFFERENCE_KT')]
            if contained and len({o['value'] for o in contained})==1:
                o=contained[0]
                elements[oxide]=o['value']
                rule=json.loads(o['raw'])['transform']['rule']
                put(next(c for c in row if c.startswith(oxide+'_')),o['value'],o['source_sha'],o['locator'],
                    rule,scope,ids+[o['obs_id']])
            continue
        if not found or len({o['value'] for o in found})!=1:continue
        o=found[0];raw=json.loads(o['raw']);value=bundle['value']['ore_mt']*o['value']*.001
        if partial and partial['mode']=='BULK_ORE_AND_HM_HOSTED_OXIDES_ONLY':
            mass = partial['mass_inputs']['hm_mass_mt']
            hm = (Decimal(str(mass['value'])) if mass.get('derivation')
                  else summary_decimal_token(mass['original_token']))
            value = hm * summary_hm_percent(raw, oxide) * 10
        elements[oxide]=value
        method='DERIVED_SAME_ROW_TREO_MINUS_TREO_EX_CEO2_X_MATCHED_ORE_MT_X_0_001' if raw.get('review_method','').startswith('DERIVED_SAME_ROW_TREO_MINUS_TREO_EX_CEO2') else 'ORE_MT_X_OXIDE_PPM_X_0_001'
        if raw.get('transform',{}).get('rule')=='REVIEWED_ELEMENTAL_PPM_TO_OXIDE_PPM':
            method='ORE_MT_X_STOICHIOMETRIC_OXIDE_FROM_REVIEWED_ELEMENTAL_PPM'
        put(next(c for c in row if c.startswith(oxide+'_')),value,o['source_sha'],o['locator'],method,scope,ids+[o['obs_id']])
    if review:
        summary_scoped_oxide_fields(row,bundle,review,elements,sources[sha],rules,decisions,put)
    total=bundle['value'].get('contained_treo_kt')
    if elements:
        put('已公布元素數_共15項',len(elements),composition_sha,composition_locator,'COUNT_CANONICAL_INDIVIDUAL_OXIDES',scope,composition_ids)
        put('已公布元素總和_kt',sum(elements.values()),composition_sha,composition_locator,'SUM_AVAILABLE_MATCHED_OXIDES_NOT_TOTAL_RESOURCE',scope,composition_ids)
        if total and matched_composition_denominator:
            put('元素總和/TREO',float(sum(elements.values()))/float(total),composition_sha,composition_locator,'AVAILABLE_OXIDE_SUM_DIVIDED_BY_MATCHED_TREO',scope,composition_ids)
    for needed,column in [(('Nd2O3','Pr6O11'),'NdPr蘊藏量_kt_需兩者皆公布'),(rules['heavy'],'完整重稀土組合蘊藏量_kt_需8元素皆公布'),(rules['magnet'],'磁性元素重算值_NdPrTbDy_kt')]:
        value=summary_complete_sum(elements,needed)
        if value is not None:put(column,value,composition_sha,composition_locator,'SUM_COMPLETE_MATCHED_OXIDE_SET',scope,composition_ids)
    if row['NdPr蘊藏量_kt_需兩者皆公布'] in (None,''):
        ndpr=summary_reported_oxide_group(composition,bundle,'reported_resource_ndpr_ppm','NdPr_OXIDES',
            'RESOURCE_ORE_GRADE_NDPR_OXIDE_GROUP_PPM')
        if ndpr:
            group_locator='; '.join(sorted({locator,ndpr['observation']['locator']}))
            put('NdPr蘊藏量_kt_需兩者皆公布',ndpr['contained_kt'],ndpr['observation']['source_sha'],group_locator,
                'ORE_MT_X_REPORTED_NDPR_OXIDE_GROUP_PPM_X_0_001',scope,ids+[ndpr['observation']['obs_id']])
        elif not partial:
            reported=[o for o in composition if o['variable']=='reported_resource_ndpr_kt' and o['unit']=='kt'
                and o['basis']=='NdPr_OXIDES' and
                json.loads(o['raw']).get('material_basis')=='RESOURCE_CONTAINED_NDPR_OXIDE_GROUP_KT']
            if reported and len({o['value'] for o in reported})==1:
                o=reported[0]
                put('NdPr蘊藏量_kt_需兩者皆公布',o['value'],o['source_sha'],o['locator'],
                    'SOURCE_REPORTED_MATCHED_NDPR_OXIDE_GROUP_KT',scope,ids+[o['obs_id']])
    magnet=summary_complete_sum(elements,rules['magnet'])
    if magnet is not None:
        put('四項磁性元素皆公布','是',composition_sha,composition_locator,'SUM_COMPLETE_MATCHED_OXIDE_SET',scope,composition_ids)
        if row['磁鐵稀土氧化物蘊藏量_kt'] in (None,''):
            method='SUM_MATCHED_HM_HOSTED_MAGNET_OXIDES' if partial and partial['mode']=='BULK_ORE_AND_HM_HOSTED_OXIDES_ONLY' else 'SUM_COMPLETE_MATCHED_MAGNET_OXIDES_AFTER_CE_CANONICALIZATION'
            put('磁鐵稀土氧化物蘊藏量_kt',magnet,sha,locator,method,scope,ids)
            if total:
                method='MATCHED_HM_HOSTED_OXIDES_DIVIDED_BY_VERIFIED_IN_SITU_TREO' if partial else 'SOURCE_TREO_PLUS_Y_MINUS_CE2O3_PLUS_CEO2'
                put('磁鐵稀土佔TREO_pct',float(magnet)/float(total)*100,sha,locator,method,scope,ids)
    note=rules['notes']['hm' if partial and partial['mode']=='BULK_ORE_AND_HM_HOSTED_OXIDES_ONLY' else 'cerium_partial' if partial else 'closure_pending' if len(elements)==15 else 'partial'] if elements else ''
    if len(elements)==15 and not partial:
        components=[o for o in same if o['basis'] in elements and json.loads(o['raw']).get('material_basis')=='RESOURCE_ORE_GRADE_OXIDE_PPM']
        grade=next((o for o in same if o['variable']=='grade'),None)
        if grade and len({o['basis'] for o in components})==15 and all(json.loads(o['raw']).get('rounding_half_width') is not None for o in [grade,*components]):
            total_ppm=grade['value']*(10000 if grade['unit']=='%' else 1)
            half=sum(json.loads(o['raw'])['rounding_half_width'] for o in components)+json.loads(grade['raw'])['rounding_half_width']*(10000 if grade['unit']=='%' else 1)
            if abs(sum(o['value'] for o in components)-total_ppm)<=half+1e-9:note=rules['notes']['closure']
    if bundle.get('cerium_conversion'):note=rules['notes']['cerium_canonical'].format(factor=bundle['cerium_conversion']['factor'])
    return bundle,dict(sha=sha,scope=scope,ids=ids,locator=locator,note=note,scope_label=(review or {}).get('summary_resource_scope_label')),reason


def summary_scoped_oxide_fields(row,bundle,review,elements,source,rules,decisions,put):
    import pymupdf
    pid=row['專案ID'];sha=bundle['source_sha256'];ore=bundle['value']['ore_mt']
    identity=rules['oxide_exception_identities'].get(pid)
    if not identity or identity[1:]!=[bundle['statement_id'],sha]:return
    rule=rules['oxide_exception_rules'][pid]
    decision=summary_decision(decisions,rule,pid,bundle)
    if not decision:return
    binding=next((o.get('cell_binding') for o in review.get('observations',[]) if o['variable']=='ore_mt'),None)
    # The migrated review contract preserves bindings separately from observations.
    binding=binding or review.get('ore_binding')
    if not binding:return
    ids=[o['obs_id'] for o in bundle['observations']];scope=bundle['scope']
    with pymupdf.open(source['resolved_path']) as doc:
        if rule=='ACCEPT_SOURCE_COMBINED_NDPR_OXIDE':
            native=summary_native_column(doc,binding,'NdPr',rules['circle_header_y'],rules['circle_unit_y'])
            text=summary_norm(doc[1].get_text()).replace('₂','2').replace('₃','3')
            if 'ndpr = nd2o3 + pr6o11' not in text:raise ValueError('NDPR_OXIDE_DEFINITION_REQUIRED')
            put('NdPr蘊藏量_kt_需兩者皆公布',ore*native['value']*.001,sha,canonical(native),'SOURCE_COMBINED_NDPR_OXIDE_PPM_X_ORE_MT',scope,ids)
        else:
            ce=summary_native_column(doc,binding,'Ce2O3',rules['splinter_header_y'],rules['splinter_unit_y'])
            weights=rules['atomic_weights'];Ce=weights['Ce'];O=weights['O'];factor=2*(Ce+2*O)/(2*Ce+3*O)
            elements['CeO2']=ore*ce['value']*factor*.001
            bundle['cerium_conversion']=dict(factor=factor,native=ce,decision_id=decision['decision_id'])
            put('CeO2_氧化鈰_kt',elements['CeO2'],sha,canonical(ce),'DERIVED_STOICHIOMETRIC_CE2O3_TO_CEO2',scope,ids)
            definition=summary_norm(doc[68].get_text())
            if 'in order to calculate the treo+y2o3' in definition and 'resource reporting' in definition:
                native=summary_native_column(doc,binding,'TREO+Y2O3',rules['splinter_header_y'],rules['splinter_unit_y'])
                ppm=native['value']-ce['value']+ce['value']*factor
                bundle['value'].update(grade_pct=ppm/10000,contained_treo_kt=ore*ppm*.001)
                for column,value in [('TREO品位_pct',ppm/10000),('總TREO蘊藏量_kt',ore*ppm*.001),('有TREO資源估計','是')]:
                    put(column,value,sha,canonical(dict(native=native,cerium=ce,factor=factor,decision=decision['decision_id'])),'SOURCE_TREO_PLUS_Y_MINUS_CE2O3_PLUS_CEO2',scope,ids)


def summary_observation(observation):
    raw=json.loads(observation['raw']);reviewed=raw.get('raw',{}).get('reviewed_observation',{})
    result=dict(reviewed,**raw);result['review_contract']=raw.get('raw',{}).get('review_contract',{})
    return result


def _completed_drilling_stage(proposal, row, trace, sources, rules):
    """Bind completed drilling and a selected MRE to the same dated disclosure."""
    pid = row['專案ID']
    review = rules.get('completed_drilling_stage_reviews', {}).get(pid)
    if not review or proposal['code'] or proposal['reason'] != 'STUDY_COMPLETION_NOT_EXPLICIT':
        return proposal
    stage = trace[pid, '開發階段']
    ore = trace.get((pid, '礦石蘊藏量_Mt'), {})
    report = sources.get(review['stage_sha256'])
    if (not report or report.get('kind') != 'pdf' or stage['source_sha256'] != review['stage_sha256']
            or stage.get('value') != review['stage_text'] or stage.get('pdf_page') != str(review['stage_page'])
            or stage.get('effective_date') != review['stage_date']
            or ore.get('source_sha256') != review['resource_sha256']
            or ore.get('effective_date') != review['resource_date']):
        return proposal
    import pymupdf
    with pymupdf.open(report['resolved_path']) as document:
        for evidence in review['original_pages']:
            page = evidence['page']
            if not 1 <= page <= len(document):
                return proposal
            text = summary_norm(document[page - 1].get_text())
            if not all(summary_norm(marker) in text for marker in evidence['markers']):
                return proposal
    return dict(proposal, code='A2', category=rules['stage_categories']['A2'], rule=rules['stage_rules']['A2'],
                reason='COMPLETED_EXPLORATION_DRILLING_WITH_SELECTED_MRE', evidence=review)


def summary_stage_fields(row, trace, sources, associations, rules, decisions, put, audit, cache, resource_expected=False, inventory=None):
    pid=row['專案ID'];native=trace.get((pid,'開發階段'))
    has_mre=True if row['礦石蘊藏量_Mt'] else None if resource_expected else False
    if native:
        proposal=summary_stage_case(row,summary_classify_stage(row['開發階段'],has_mre,rules),native,rules)
        if has_mre:
            proposal = _completed_drilling_stage(proposal, row, trace, sources, rules)
        decision=summary_decision(decisions,proposal.get('rule'))
        if decision and proposal.get('code') and (not proposal.get('ongoing_study') or summary_decision(decisions,'IN_PROGRESS_STUDY_USE_HIGHEST_EXPLICIT_COMPLETED')):
            for column,key in [('開發階段代碼','code'),('開發階段類別','category')]:
                if not row[column]:put(column,proposal[key],native['source_sha256'],native['locator'],'APPROVED_RESEARCHER_STAGE_RULE',canonical(dict(proposal=proposal,decision=decision['decision_id'])),native['observation_ids'])
    exit_case=rules['stage_exit'].get(pid)
    if exit_case and summary_decision(decisions,'STAGE_EXIT_RESEARCHER_DECISION_RELINQUISHMENT'):
        sha,page,keyword=exit_case
        if sha in sources:
            import pymupdf
            with pymupdf.open(sources[sha]['resolved_path']) as doc:text=doc[page-1].get_text()
            if keyword in text.casefold():
                for column,value in [('開發階段代碼','X'),('開發階段類別',rules['stage_categories']['X'])]:
                    if not row[column]:put(column,value,sha,'physical PDF p'+str(page),'STAGE_EXIT_RESEARCHER_DECISION_RELINQUISHMENT','FOUR_SOURCE_BOUND_HISTORICAL_CHARLEY_PROJECTS')
    if row['開發階段'] or row['開發階段代碼'] or has_mre is None or not summary_decision(decisions,'STAGE_INFERRED_FROM_EVIDENCE_ABSENCE'):return
    from .pdf_extract import summary_scan_stage, summary_hit_priority, summary_source_assessment
    from .pdf_extract import summary_review_hit
    hits=[];blockers=[];eligible=[]
    if not inventory:
        audit.append(dict(project_id=pid,reason='STAGE_SOURCE_INVENTORY_UNVERIFIED'))
        return
    metadata={m['source_sha256']:m for m in (inventory or [])}
    expected=associations.get(pid,set())|set(metadata)
    for sha in sorted(expected):
        meta=metadata.get(sha,{})
        entry=dict(sha256=sha,url=meta.get('url',''))
        if summary_source_assessment(entry,meta.get('shared_projects',[]),rules['stage_hit_settings'])[0]=='FAIL':continue
        if sha not in sources:blockers.append(dict(reason='SOURCE_NOT_ACQUIRED',source_sha256=sha));continue
        s=sources[sha];point1,_=summary_source_assessment(dict(s,sha256=sha),s.get('summary_project_ids',[]),rules['stage_hit_settings'])
        if point1=='FAIL':continue
        if not s.get('publication_date') and not meta.get('dates'):blockers.append(dict(reason='ARCHIVED_ORIGINAL_DATE_UNKNOWN',source_sha256=sha))
        if s['kind'] not in ('pdf','html'):blockers.append(dict(reason='SOURCE_FORMAT_UNVERIFIED',source_sha256=sha));continue
        if sha not in cache:cache[sha]=summary_scan_stage(dict(s,stage_visual_reviews=meta.get('visual_reviews',[])),rules)
        found,problems=cache[sha];blockers.extend(problems)
        eligible.append(s)
        for h in found:hits.append(summary_review_hit(h,row,s,rules))
    audit.extend(dict(project_id=pid,**h) for h in blockers)
    for hit in hits:
        if hit['outcome']=='UNCLEAR':
            hit['reason']=hit['reason2'] if hit['point2']=='UNCLEAR' else 'STAGE_HIT_REQUIRES_REVIEW'
    audit.extend(hits)
    if not expected or blockers or not eligible or any(h['outcome']!='FAIL' for h in hits):return
    dated=[s for s in eligible if s.get('publication_date')]
    if not dated:return
    s=max(dated,key=lambda s:(s['publication_date'],s['sha256']));code='A2' if has_mre else 'A1'
    for column,value in [('開發階段代碼',code),('開發階段類別',rules['stage_categories'][code])]:
        put(column,value,s['sha256'],'all associated registered originals; all physical pages','STAGE_INFERRED_FROM_EVIDENCE_ABSENCE',canonical(dict(sources=sorted(expected),hits=hits,selected_mre=has_mre)))


def summary_deposit_fields(row,trace,attributes,rules,decisions,put):
    if row['礦床型態代碼']:return
    native=trace.get((row['專案ID'],'礦床型態'));text=row['礦床型態'];case=None
    if text.casefold() in rules['deposit_clays']:case=('iac','clay')
    elif text in rules['deposit_exact']:case=rules['deposit_exact'][text]
    else:
        support=next((a for a in attributes if a.get('deposit_host_review')),None)
        if support:
            review=support['deposit_host_review'];ore=trace.get((row['專案ID'],'礦石蘊藏量_Mt'))
            if not review['selected_mre_required'] or ore and ore['source_sha256']==support['source_sha256']:
                case=(review['code'],'g4');native=support
    if not native or not case:return
    rule=rules['deposit_rules'][case[1]];decision=summary_decision(decisions,rule)
    if row['專案ID'] in rules['deposit_speculative'] and not summary_decision(decisions,rules['deposit_rules']['potential']):return
    if decision:put('礦床型態代碼',case[0],native['source_sha256'],native.get('locator',''),rule,canonical(dict(decision=decision['decision_id'],source_value=text,qualifier='IONIC_NOT_CONFIRMED' if case[0]=='iac' else '')),native.get('observation_ids') or [native['obs_id']])


def export_summary(root, database, out, cutoff=None, *, connection=None, run_id=None,
                   configuration=None, snapshots=None, membership=None, acquisition_rows=None, audit=None,
                   claim_declarations=None, replay_assets=None):
    """Project-scoped, read-only export from one canonical run, with every cell accounted for."""
    root=Path(root).resolve();database=Path(database).resolve();out=Path(out).resolve()
    if out==database.parent or any(out==root/p or (root/p) in out.parents for p in ('src','config','data')):
        raise ValueError('SUMMARY_OUTPUT_MUST_BE_ISOLATED')
    if not database.is_file():raise ValueError('SUMMARY_DATABASE_REQUIRED')
    standalone=connection is None
    session=closing(sqlite3.connect(database.as_uri()+'?mode=ro',uri=True)) if standalone else nullcontext(connection)
    with session as db:
        return _export_summary(root,database,out,db,cutoff,run_id,standalone,configuration,
                               snapshots,membership,acquisition_rows,audit,claim_declarations,replay_assets)


def _export_summary(root, database, out, db, cutoff, run_id, standalone,
                    configuration, snapshots, membership, acquisition_rows, audit, claim_declarations, replay_assets):
    from .tabular import write_csv
    from .evidence import load_claims,claim_evidence_ids
    rules,decisions=summary_settings(root)
    hashes={name:filehash(root/'config'/name) for name in
            ('summary_rules.json','researcher_rule_decisions.json','project_summary_columns.json')}
    evidence_files = ('config/assay_evidence.json','config/candidate_milestones.json',
                      'data/candidate_milestone_evidence.json','config/formal_c1_review.json',
                      'config/eligibility_compatibility.json')
    hashes.update({file:filehash(root/file) for file in evidence_files if (root/file).is_file()})
    columns=json.loads((root/'config/project_summary_columns.json').read_text(encoding='utf8'))
    if len(columns)!=51 or len(set(columns))!=51:raise ValueError('SUMMARY_51_COLUMN_CONTRACT_REQUIRED')
    db.row_factory=sqlite3.Row
    run=(db.execute('SELECT * FROM runs WHERE run_id=?',(run_id,)).fetchone() if run_id is not None
         else db.execute('SELECT * FROM runs ORDER BY started_at DESC,run_id DESC LIMIT 1').fetchone())
    if not run or (standalone and run['status']!='COMPLETED'):
        raise ValueError('SUMMARY_REQUIRES_COMPLETED_RUN')
    cutoff=cutoff or run['cutoff']
    if standalone:
        from .census_replay import read_run_inputs
        saved = read_run_inputs(db,database,root,run,hashes,cutoff,replay_assets)
        if saved is not None:
            configuration,snapshots,membership,acquisition_rows = saved
        elif configuration and configuration.get('source_mode'):
            raise ValueError('SUMMARY_RUN_METADATA_REQUIRED')
    configuration = configuration or {}
    if audit is None:audit=standalone and bool(configuration.get('source_mode'))
    frozen=claim_declarations
    if frozen is None:frozen,_=load_claims(root,configuration.get('claims_sha256'))
    active=set(configuration.get('verified_claim_ids',claim_evidence_ids(frozen)))
    live=frozen
    declarations={'AU-'+digest([p.get('entity_namespace','project_registry_v1'),str(p['id'])])[:20]:p for p in live['projects']}
    registry=configuration.get('sources') or json.loads((root/'config/sources.json').read_text(encoding='utf8'))
    registry=registry['sources']
    by_key={s['key']:s for s in registry};sources={};source_errors={};acquisition={}
    if acquisition_rows is not None:
        acquisition={r['key']:r for r in acquisition_rows}
    selected=None if snapshots is None else {s['sha256']: (root/s['path']).resolve() for s in snapshots}
    for source in db.execute('SELECT * FROM sources'):
        if selected is not None and source['sha'] not in selected:continue
        s=dict(json.loads(source['metadata']),**dict(source));s['sha256']=source['sha'];s['key']=source['source_key']
        path=(selected[s['sha256']] if selected is not None else (root/s['path']).resolve());reason=''
        if not (path.is_relative_to(root) or (selected is not None and selected.get(s['sha256'])==path)) or not path.is_file():reason='SOURCE_NOT_ACQUIRED'
        elif filehash(path)!=s['sha256']:reason='SOURCE_SHA_CHANGED'
        elif s.get('publication_date') and date_end(s['publication_date'])>cutoff:reason='SOURCE_AFTER_CUTOFF'
        elif s['kind'] not in ('pdf','html','pdf_page_extraction','document_extraction') and s.get('available_date',s['acquired_at'][:10])>cutoff:reason='SOURCE_AFTER_CUTOFF'
        if reason:source_errors[s['key']]=reason
        else:s['resolved_path']=str(path);s['path']=str(path);sources[s['sha256']]=s
    records=defaultdict(list);observations=defaultdict(list);attributes=defaultdict(list);studies=defaultdict(list)
    for r in db.execute('SELECT * FROM records'):
        if r['source_sha'] in sources:records[r['entity_id']].append(dict(r))
    for o in db.execute("SELECT * FROM observations WHERE status='AUTO_VALIDATED' AND effective_date<=?",(cutoff,)):
        if o['source_sha'] not in sources or o['transform_version']=='normalization-v1' and o['obs_id'] not in active:continue
        if o['variable']=='project_attribute':attributes[o['entity_id']].append(dict(json.loads(o['raw']),obs_id=o['obs_id']))
        else:observations[o['entity_id']].append(dict(o))
    for s in db.execute('SELECT * FROM study_cases WHERE effective_date<=?',(cutoff,)):
        if s['source_sha'] in sources:studies[s['project_id']].append(dict(s))
    field_issues=defaultdict(list);identity_issues=defaultdict(list)
    for q in db.execute('SELECT issue_id,entity_id,source_sha,reason,details FROM review_queue ORDER BY issue_id'):
        issue=dict(q)
        try:detail=json.loads(issue.pop('details'))
        except (TypeError,ValueError):continue
        if not isinstance(detail,dict):continue
        if isinstance(detail.get('column'),str) and detail['column']:
            field_issues[issue['entity_id'],detail['column']].append(issue)
        elif detail.get('project') and detail.get('identity_source'):
            identity_issues[issue['entity_id']].append(issue)
    cohort={p['project_id']:p for p in rules['cohort']}
    for member in membership or ():
        pid=member['canonical_id']
        if member['kind']!='PROJECT' or pid in cohort or not records[pid]:continue
        entity=db.execute('SELECT native_id FROM entities WHERE entity_id=? AND kind=?',(pid,'PROJECT')).fetchone()
        if entity:cohort[pid]=dict(project_id=pid,native_id=entity['native_id'])
    rows=[];trace={};missing=[];stage_audit=[];cache={};associations=defaultdict(set)
    diagnoses={};bundles={}
    if audit:
        from .census_audit import field_diagnosis, write_census_audit
    for p in live['projects']:
        pid='AU-'+digest([p.get('entity_namespace','project_registry_v1'),str(p['id'])])[:20]
        associations[pid].update(o['source_sha256'] for o in [*p['observations'],*p.get('attributes',[])])
        identity=by_key.get(p['identity_source'],{}).get('source_sha256')
        if identity:associations[pid].add(identity)
    for s in registry:
        for pid in s.get('summary_project_ids',[]):
            if s.get('source_sha256'):associations[pid].add(s['source_sha256'])
    mapping=dict(version=rules['template.version'],mappings=rules['template.mappings'],source=dict(sha256=rules['template_source_sha256']))
    template=dict(config=mapping,sha256=hashes['summary_rules.json'])
    from .spatial import summary_locations
    from .technical import summary_forecasts

    @lru_cache(maxsize=16)
    def read_spatial_json(path):
        return json.loads(Path(path).read_text(encoding='utf8'))

    for project in sorted(cohort.values(),key=lambda p:p['project_id']):
        pid=project['project_id'];row=dict.fromkeys(columns,'');p=declarations.get(pid,{})
        def put(column,value,sha='',locator='',method='SOURCE_REPORTED',scope='',obs_ids=(),**extra):
            if column not in row or value is None or value=='':return
            row[column]=summary_decimal_text(value) if isinstance(value,Decimal) else str(value)
            shas=sha.split(';') if sha else []
            ids=json.loads(obs_ids) if isinstance(obs_ids,str) else list(obs_ids)
            if not ids and method.startswith('USER_PROVIDED_TEMPLATE_MAPPING_FROM_'):
                ids=json.loads(json.loads(scope)['source_provenance']['observation_ids'])
            dates=[o['effective_date'] for o in observations[pid] if o['obs_id'] in ids]+[a['effective_date'] for a in attributes[pid] if a['obs_id'] in ids]
            trace[pid,column]=dict(project_id=pid,column=column,value=row[column],source_sha256=sha,
                source_url=';'.join(sources[s]['url'] for s in shas if s in sources),locator=locator,method=method,scope=scope,
                observation_ids=canonical(ids),attribute_ids=canonical([a.get('attribute_id',a['obs_id']) for a in attributes[pid] if a['obs_id'] in ids]),
                pdf_page=';'.join(sorted({str(json.loads(o['raw']).get('pdf_page')) for o in observations[pid] if o['obs_id'] in ids and json.loads(o['raw']).get('pdf_page')}|
                    {str(a['pdf_page']) for a in attributes[pid] if a['obs_id'] in ids and a.get('pdf_page')})),
                effective_date=max(dates or [sources[s].get('publication_date') or '' for s in shas if s in sources],default=''))
            trace[pid,column].update(extra)
        put('專案ID',pid,method='EXISTING_CANONICAL_PROJECT_RELATION')
        put('國家','澳洲',method='AUSTRALIAN_CENSUS_SCOPE',scope='REGISTERED_AUSTRALIAN_CENSUS_COHORT')
        rs=sorted(records[pid],key=lambda r:(sources[r['source_sha']].get('publication_date') or '',r['source_sha']),reverse=True)
        identity=next((r for r in rs if sources[r['source_sha']]['key']==p.get('identity_source')),rs[0] if rs else None)
        if identity:put('專案名稱',identity['name'],identity['source_sha'],'canonical source-bound project record','EXISTING_PROJECT_REGISTRY')
        state=next((r for r in rs if r.get('state')),None)
        if state:
            code=state['state'];name=rules['states'].get(code,code);sha=state['source_sha']
            for column,value in [('州省地區',name),('所在地_中文','澳洲（'+name+'）'),('所在地_英文','Australia ('+code+')')]:put(column,value,sha,'source state code','SOURCE_STATE_CODE_LABEL')
        coordinate=next((r for r in rs if r.get('longitude') is not None and r.get('latitude') is not None),None)
        if coordinate:
            for column,key in [('緯度','latitude'),('經度','longitude')]:put(column,coordinate[key],coordinate['source_sha'],'same representative-point record','REPRESENTATIVE_POINT_NOT_BOUNDARY')
        deposit=next((r for r in rs if r.get('deposit_type')),None)
        if deposit:put('礦床型態',deposit['deposit_type'],deposit['source_sha'],'source deposit description')
        for r in rs:
            raw=json.loads(r['raw']);owner=raw.get('owner') or raw.get('developer') or raw.get('company')
            if owner:put('開發商',str(owner),r['source_sha'],'source owner/developer label');break
        for a in sorted(attributes[pid],key=lambda a:(a['effective_date'],a.get('review_id',''))):
            if a.get('support_only'):continue
            put(a['column'],a['value'],a['source_sha256'],a['locator'],a.get('method','SOURCE_REVIEWED_ATTRIBUTE_NOT_CURRENT_LEGAL_CERTIFICATION'),a.get('scope',''),[a['obs_id']],effective_date=a['effective_date'])
        maturity=[o for o in observations[pid] if o['variable']=='study_maturity_ord']
        if maturity and not row['開發階段']:
            latest=max(o['effective_date'] for o in maturity);same=[o for o in maturity if o['effective_date']==latest]
            if len({o['value'] for o in same})==1 and str(int(same[0]['value'])) in rules['source_stage_labels']:
                o=same[0];put('開發階段',rules['source_stage_labels'][str(int(o['value']))]+'（'+latest+'）',o['source_sha'],o['locator'],'DATED_STUDY_DISCLOSURE_NOT_CURRENT_OPERATING_STATUS',o['scope'],[o['obs_id']])
        bundle,resource_note,resource_reason=summary_resource_fields(row,observations[pid],sources,rules,decisions,put,p)
        if audit and bundle:bundles[pid]=bundle
        label=resource_note.get('scope_label')
        if bundle and label and row['專案名稱']:
            import pymupdf
            with pymupdf.open(sources[bundle['source_sha256']]['resolved_path']) as doc:
                if any(summary_norm(label) in summary_norm(page.get_text()) for page in doc):
                    put('專案名稱',row['專案名稱']+' — '+label+' resource scope',bundle['source_sha256'],resource_note['locator'],'EXISTING_PROJECT_WITH_EXPLICIT_RESOURCE_SUBSCOPE_LABEL',bundle['scope'],resource_note['ids'])
        project_trace=[trace[pid,c] for c in columns if (pid,c) in trace]
        for fill in summary_template_fills(row,project_trace,template,rules['template_fields']):put(**fill)
        summary_deposit_fields(row,trace,attributes[pid],rules,decisions,put)
        stage_start=len(stage_audit)
        summary_stage_fields(row,trace,sources,associations,rules,decisions,put,stage_audit,cache,
            any(o['variable']=='ore_mt' for o in p.get('observations',[])),p.get('identity_declaration',{}).get('stage_inventory'))
        stage_blockers=[{k:a[k] for k in ('reason','source_sha256','physical_page') if k in a}
            for a in stage_audit[stage_start:] if a.get('reason')]
        extent_rejections=[]
        for fill in summary_locations(row,rows,registry,sources,rules,decisions,read_json=read_spatial_json,
                                      cutoff=cutoff,extent_rejections=extent_rejections):put(**fill)
        for fill in summary_forecasts(pid,studies[pid],attributes[pid],sources,rules,decisions,cutoff,row,stage_audit):put(**fill)
        docs={r['source_sha'] for r in rs if sources[r['source_sha']]['kind']=='pdf'}|{o['source_sha'] for o in observations[pid] if sources[o['source_sha']]['kind']=='pdf'}
        docs.update(a['source_sha256'] for a in attributes[pid] if sources[a['source_sha256']]['kind']=='pdf')
        if docs:put('有來源文件','是',sorted(docs)[0],'verified original PDF','VERIFIED_PDF_SOURCE_PRESENT_NOT_COMPLETENESS')
        if not row['資料來源URL'] and identity:
            sha=identity['source_sha'];put('資料來源名稱',sources[sha]['key'],sha,'identity source');put('資料來源URL',sources[sha]['url'],sha,'identity source')
        parts=[];support=[]
        if resource_note.get('note'):parts.append(resource_note['note']);support.append(trace[pid,'礦石蘊藏量_Mt'])
        if (pid,'開發階段') in trace:
            parts.append(rules['notes']['stage'].format(stage=row['開發階段']));support.append(trace[pid,'開發階段'])
        if (location:=trace.get((pid,'緯度'))) and location['method']!='REPRESENTATIVE_POINT_NOT_BOUNDARY':
            parts.append(rules['notes']['point'].format(dataset=location.get('scope','')));support.append(location)
        if project['native_id']=='yttria':parts.append(rules['notes']['duplicate'])
        if parts:
            put('總說明','；'.join(parts),';'.join(sorted({s for r in support for s in r['source_sha256'].split(';') if s})),
                'source records retained in scope','DETERMINISTIC_SOURCE_GROUNDED_PRESENTATION_NOTES_V1',canonical(dict(source_records=support,structural_difference=project['native_id']=='yttria')),
                sorted({i for r in support for i in json.loads(r['observation_ids'])}))
        for column in columns:
            if row[column]=='':
                source_findings=[] if audit else None
                reason,detail=summary_missing(column,p,row,bundle,by_key,sources,source_errors,acquisition,cutoff,rules,decisions,
                    findings=source_findings, verified_attributes=attributes[pid], extent_rejections=extent_rejections)
                if reason=='RULE_INPUT_MISSING':
                    blockers=field_issues[pid,column]
                    if not row['專案名稱'] and identity_issues[pid]:
                        detail+='; project_identity='+canonical(identity_issues[pid])
                    if blockers:
                        detail+='; field_review='+canonical(blockers)
                    if column in rules['resource_columns']:
                        if bundle:
                            detail+='; resource='+canonical(dict(reason='NO_COMPATIBLE_FIELD_INPUT_IN_SELECTED_RESOURCE',
                                source_sha256=bundle['source_sha256'],statement_id=bundle['statement_id'],
                                scope=bundle['scope'],effective_date=bundle['effective_date']))
                        else:
                            detail+='; resource='+canonical(dict(reason=resource_reason))
                    if stage_blockers and column in ('開發階段代碼','開發階段類別'):
                        detail+='; stage_scan='+canonical(stage_blockers)
                if audit:
                    review=field_issues[pid,column] + (identity_issues[pid] if not row['專案名稱'] else [])
                    scans=stage_blockers if column in ('開發階段代碼','開發階段類別') else []
                    status,findings=field_diagnosis(column,reason,review,scans,bundle,resource_reason,rules)
                    diagnoses[pid,column]=(status,reason,[*source_findings,*findings])
                missing.append(dict(project_id=pid,column=column,reason=reason,details=detail))
                trace[pid,column]=dict(project_id=pid,column=column,value='',source_sha256='',source_url='',pdf_page='',locator=detail,
                    method=reason,scope='',observation_ids='[]',attribute_ids='[]',effective_date='')
        rows.append(row)
    out.mkdir(parents=True,exist_ok=True);names=rules['output_files']
    write_csv(out/names['summary'],rows,columns)
    all_trace=[trace[r['專案ID'],c] for r in rows for c in columns]
    write_csv(out/names['provenance'],all_trace,list(all_trace[0]) if all_trace else [])
    write_csv(out/names['missing'],missing,['project_id','column','reason','details'])
    write_csv(out/'stage_rule_audit.csv',stage_audit,sorted({k for r in stage_audit for k in r}))
    coverage=summary_coverage(rows,columns,missing,rules)
    if audit:
        from .milestones import write_milestones
        from .formal_cohort import write_formal_cohort
        from .assays import write_assay_evidence
        coverage.update(write_census_audit(db,out,rows,trace,diagnoses,observations,bundles,
                                           resource_columns=rules['resource_columns']))
        if configuration.get('census_gap_review_sha256'):
            from .census_gap_review import write_gap_review
            coverage.update(write_gap_review(root,out,rows,trace,diagnoses,sources,associations,cutoff,
                                             configuration['census_gap_review_sha256']))
        coverage.update(write_milestones(root,out,rows,sources,observations,bundles,stage_audit,cutoff))
        if (root/'config/formal_c1_review.json').is_file():
            coverage.update(write_formal_cohort(root,out,rows,trace,sources,observations,cutoff))
        if (root/'config/assay_evidence.json').is_file():
            coverage.update(write_assay_evidence(root,out,rows,sources,db,cutoff,active))
    coverage.setdefault('formal_C1', False)
    coverage['export_contract_sha256']=hashes
    coverage.update(database_sha256=filehash(database) if standalone else None,cutoff=cutoff,source_scope='LATEST_CANONICAL_RUN_ONLY',
        rows=len(rows),column_count=len(columns),same_mre_aggregation='NO_RESOURCE_SUMS_EXPORTED;Yttria/Mt_Stirling_NON_ADDITIVE')
    (out/names['coverage']).write_text(canonical(coverage)+'\n',encoding='utf8')
    return coverage


def census_selection(summary_csv, membership, filters, out):
    """Match display fields first, then require a canonical Project in SQLite."""
    from .tabular import write_csv
    with Path(summary_csv).open(encoding='utf-8-sig',newline='') as stream:
        reader=csv.DictReader(stream)
        columns=reader.fieldnames
        rows=list(reader)
    values=defaultdict(set)
    for expression in filters:
        field,separator,value=expression.partition('=')
        if not separator or field not in columns:
            raise ValueError(f'Invalid census filter {expression!r}. Use a CSV column followed by = and its value.')
        values[field].add(value)
    canonical={r['entity_id']:r['canonical_id'] for r in membership if r['kind']=='PROJECT'}
    audit=[]
    for row in rows:
        pid=row['專案ID']
        matched=all(row[field] in allowed for field,allowed in values.items())
        resolved=canonical.get(pid)
        status=('FILTER_EXCLUDED' if not matched else 'UNRESOLVED_PROJECT'
                if not resolved or not row['專案名稱'] else 'SELECTED')
        audit.append(dict(project_id=pid,canonical_project_id=resolved,filter_match=int(matched),status=status))
    write_csv(out/'census_selection.csv',audit,['project_id','canonical_project_id','filter_match','status'])
    return {r['canonical_project_id'] for r in audit if r['status']=='SELECTED'}


def publish_census(root, run_dir, run_id, destination=None):
    """Publish a single completed run as a directory."""
    from shutil import copyfile, rmtree
    from uuid import uuid4

    target=(Path(destination).resolve() if destination else
            root/'results'/'ree-project-census'/run_id)
    if not target.is_relative_to(root/'results'):
        raise ValueError('Census publication must be inside this checkout’s results directory')
    target.parent.mkdir(parents=True,exist_ok=True)
    if target.exists():
        raise FileExistsError(f'Census publication already exists: {target}')
    staging=target.with_name('.census-'+uuid4().hex)
    staging.mkdir()
    try:
        summary=run_dir/'project-summary'
        names=summary_settings(root)[0]['output_files']
        copyfile(summary/names['summary'],staging/'REE project census.csv')
        for name in (names['provenance'],names['missing'],names['coverage']):
            copyfile(summary/name,staging/name)
        for name in ('field_status.csv','gap_review.csv','resource_statement_observations.csv','spatial_point_quality.csv',
                     'resource_statement_lineage.csv','milestone_comparison.csv','milestone_events.csv',
                     'formal_c1_gates.csv','formal_c1_panel_comparison.csv','formal_c1_release.json',
                     'assay_method_evidence.csv'):
            if (summary/name).is_file():copyfile(summary/name,staging/name)
        for name in ('census_selection.csv','mcda_census_gate.csv','source_selection.csv',
                     'acquisition_report.csv','resource_scope_selection.csv','census_release.json',
                     'census_identity_roles.csv','mcda_criterion_lineage.csv','mcda_panel_decisions.csv',
                     'aim_c_availability.csv','census_evidence_requests.csv','census_gis_sensitivity.csv','census_gis_rank_sensitivity.csv'):
            if (run_dir/name).is_file():copyfile(run_dir/name,staging/name)
        for ranking in sorted(run_dir.glob('*/ranking.csv')):
            panel=staging/'MCDA'/ranking.parent.name
            panel.mkdir(parents=True)
            copyfile(ranking,panel/'ranking.csv')
        staging.rename(target)
    finally:
        if staging.exists() and staging.resolve().parent==target.parent:
            rmtree(staging)
    return target/'REE project census.csv'


def summary_missing(column, project, row, bundle, registry, sources, source_errors, acquisition, cutoff, rules, decisions, *, findings=None, verified_attributes=(), extent_rejections=()):
    if column in ('經度', '緯度') and extent_rejections:
        # A measured, admitted tenure union explains the gap even if another capture was late.
        if findings is not None:
            findings.extend(extent_rejections)
        return 'RULE_INPUT_MISSING', canonical(extent_rejections)
    attributes=[a for a in project.get('attributes',[]) if a['column']==column]
    if column == 'ASX代碼' and not attributes and row.get('未上市公司') == '是':
        # A developer may be a public company without being stock-exchange listed.
        # Bind this exclusion to the reviewed developer and explicit listing on its page.
        developer = row.get('開發商', '')
        for evidence in verified_attributes:
            markers = evidence.get('page_markers', [])
            if (evidence['column'] == '未上市公司' and evidence['value'] == '是'
                    and developer and developer in markers
                    and {'Unlisted Private Company', 'Unlisted Public Company'}.intersection(markers)):
                proof = dict(source_sha256=evidence['source_sha256'], pdf_page=evidence['pdf_page'],
                             effective_date=evidence['effective_date'], developer=developer)
                if findings is not None:
                    findings.append(dict(kind='DATED_OPERATOR_LISTING', **proof))
                return 'NOT_APPLICABLE_UNLISTED_DEVELOPER', canonical(proof)
    resource=column in rules['resource_columns']
    resource_inputs=[o for o in project.get('observations',[]) if o['variable'] in rules['missing_resource_variables']
        or o.get('material_basis')=='RESOURCE_ORE_GRADE_OXIDE_PPM']
    preferred=[o['raw']['review_contract'] for o in resource_inputs if o['variable']=='ore_mt' and
        (r:=o.get('raw',{}).get('review_contract',{})) and
        r.get('selection_role',r.get('resource_selection_role','PREFERRED'))=='PREFERRED']
    if len(preferred)==1:
        r=preferred[0]
        resource_inputs=[o for o in resource_inputs if all(o.get(k)==r.get(k) for k in ('source_sha256','statement_id','scope','effective_date'))]
    candidates=attributes or (resource_inputs if resource else [])
    if column in rules['annual_columns']:
        candidates=[a for a in project.get('attributes',[]) if rules['annual_parameters'].get(column) in (a.get('engineering_forecast') or {}).get('parameters',{})
            or a.get('source_stated_annual',{}).get('column')==column]
    if column in ('經度','緯度'):
        if project.get('coordinate_source'):candidates=[dict(source_key=project['coordinate_source'])]
        pid='AU-'+digest([project.get('entity_namespace','project_registry_v1'),str(project.get('id',''))])[:20]
        candidates.extend(dict(source_key=s['key'],source_sha256=s.get('source_sha256')) for s in registry.values()
            if any(b['project_id']==pid for b in [*s.get('summary_bindings',[]),*s.get('summary_tenements',[]),
                                                *s.get('summary_official_point_bindings',[])]))
    if not candidates and project.get('identity_source'):candidates=[dict(source_key=project['identity_source'])]
    reasons=[];details=[]
    for c in candidates:
        key=c['source_key'];source=registry.get(key);receipt=acquisition.get(key,{})
        reason=source_errors.get(key)
        if not source:reason='SOURCE_NOT_REGISTERED'
        elif receipt.get('status')=='SOURCE_SHA_CHANGED':reason='SOURCE_SHA_CHANGED'
        elif receipt.get('admission_status')=='SOURCE_VERSION_NOT_DECLARED':reason='SOURCE_SHA_CHANGED'
        elif receipt.get('admission_status')=='SOURCE_AFTER_CUTOFF':reason='SOURCE_AFTER_CUTOFF'
        elif receipt.get('admission_status') in ('SOURCE_DATE_UNVERIFIED','SOURCE_PUBLICATION_DATE_MISMATCH'):
            reason=receipt['admission_status']
        elif receipt.get('status')=='HOST_STOPPED' and re.search(r'\b4\d\d\b',receipt.get('stop_reason','')):reason='HOST_STOPPED_4XX'
        elif any(date_end(d)>cutoff for d in (c.get('effective_date'),source.get('publication_date')) if d):reason='SOURCE_AFTER_CUTOFF'
        elif not any(s['key']==key or s['sha256']==(c.get('source_sha256') or source.get('committed_snapshot_sha256')) for s in sources.values()):reason=reason or 'SOURCE_NOT_ACQUIRED'
        if reason:
            reasons.append(reason)
            evidence=dict(source_key=key,status=receipt.get('status'),reason=reason,source_sha256=c.get('source_sha256'))
            details.append(canonical(evidence))
            if findings is not None:findings.append(dict(kind='SOURCE_REVIEW',**evidence))
    priority=['SOURCE_SHA_CHANGED','HOST_STOPPED_4XX','SOURCE_AFTER_CUTOFF','SOURCE_PUBLICATION_DATE_MISMATCH','SOURCE_DATE_UNVERIFIED','SOURCE_NOT_REGISTERED','SOURCE_NOT_ACQUIRED']
    if reasons:return next(r for r in priority if r in reasons),'; '.join(details)
    if resource and not bundle and not any(o['variable']=='ore_mt' for o in project.get('observations',[])):
        return 'NOT_APPLICABLE_NO_MRE','NO_SELECTED_MRE_IN_VERIFIED_PROJECT_DECLARATIONS;NOT_A_NATIONAL_ABSENCE_CLAIM'
    if column=='產品/產出' and row['開發階段代碼'] in ('A1','A2') and summary_decision(decisions,'NO_PRODUCT_BEFORE_STUDY_STAGE'):
        return 'NOT_APPLICABLE_STAGE','APPROVED_PRE_STUDY_PRODUCT_RULE'
    if resource or attributes or column in ('開發階段代碼','開發階段類別','礦床型態代碼','經度','緯度') or (
        column in rules['identity_columns'] and project.get('identity_declaration') and not row['專案名稱']):
        return 'RULE_INPUT_MISSING','SOURCE_ACQUIRED_BUT_VALIDATED_COMPATIBLE_RULE_INPUTS_OR_DECISION_MISSING'
    return 'NO_SOURCE_VALUE','NO_REVIEWED_SOURCE_VALUE_FOR_THIS_FIELD'


def summary_coverage(rows,columns,missing,rules):
    reasons=Counter(r['reason'] for r in missing);filled=sum(v!='' for r in rows for v in r.values())
    metrics=dict(filled_cells=filled,total_cells=len(rows)*len(columns),raw_coverage=filled/(len(rows)*len(columns)) if rows else None,
        missing_reasons=dict(reasons),columns={c:dict(filled=sum(r[c]!='' for r in rows),rows=len(rows),coverage=sum(r[c]!='' for r in rows)/len(rows) if rows else None) for c in columns},tiers={})
    for tier,predicate in [('T1',lambda r:bool(r['礦石蘊藏量_Mt'])),('T2',lambda r:not r['礦石蘊藏量_Mt'])]:
        selected=[r for r in rows if predicate(r)];ids={r['專案ID'] for r in selected}
        excluded=sum(r['reason']=='NOT_APPLICABLE_NO_MRE' and r['project_id'] in ids for r in missing)
        numerator=sum(v!='' for r in selected for v in r.values());total=len(selected)*len(columns);denominator=total-excluded
        metrics['tiers'][tier]=dict(rows=len(selected),filled_cells=numerator,total_cells=total,excluded_not_applicable_no_mre=excluded,
            denominator=denominator,coverage=numerator/denominator if denominator else None)
    return metrics
