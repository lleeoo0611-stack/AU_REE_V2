"""Read official project-list workbooks as source records, without fabricated Project IDs.

A row mentioning REE is a discoverable candidate, not proof that it is one
independent mining project, JORC resource, or an eligible MCDA alternative.
"""
import json
import re
from pathlib import Path
from openpyxl import load_workbook
from .store import canonical, entity, issue

REE = re.compile(r'rare[\\s\\-]*earth|\\bTREO\\b|\\bREEs?\\b',re.IGNORECASE)
STATES = {'WA','SA','NT','NSW','QLD','VIC','TAS','ACT'}

def ingest_workbook(db, root, source):
    path=Path(root)/source['path']
    try:
        wb=load_workbook(path,read_only=True,data_only=True)
    except Exception as exc:
        issue(db,None,source['sha256'],'CENSUS_WORKBOOK_UNREADABLE',str(exc))
        return 0
    count=0
    try:
        for ws in wb.worksheets:
            for index, row in enumerate(ws.iter_rows(values_only=True),start=1):
                values=[str(v).strip() if v is not None else '' for v in row]
                if sum(bool(v) for v in values)<2:
                    continue
                if not any(REE.search(v) for v in values):
                    continue
                native=f"{source['sha256']}:{ws.title}:{index}"
                eid=entity(db,'DISR_REMP_ROW',native,'SOURCE_RECORD')
                state=next((v.upper() for v in values if v.upper() in STATES),None)
                payload={'source_key':source['key'],'sheet':ws.title,'row_number':index,
                         'cells':values,'match_rule':'REE_TERMS_V1',
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
