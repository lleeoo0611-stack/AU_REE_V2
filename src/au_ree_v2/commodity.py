"""Versioned REE candidate rules and element vocabulary."""

import re


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
