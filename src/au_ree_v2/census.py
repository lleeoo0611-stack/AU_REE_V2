"""Read official project-list workbooks as source records, without fabricated Project IDs.

A row mentioning REE is a discoverable candidate, not proof that it is one
independent mining project, JORC resource, or an eligible MCDA alternative.
"""
import json
import re
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
        wb=load_workbook(path,read_only=True,data_only=True)
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
