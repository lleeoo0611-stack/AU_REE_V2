"""Explicit basis and scope checks, no inference of independent approval."""
import json
import math
from pathlib import Path
from .store import canonical, digest, entity, issue
from .census import ingest_workbook
from .official import ingest_official_table

def ingest_sources(db, root, snapshots):
    for s in snapshots:
        db.execute('INSERT OR IGNORE INTO sources VALUES(?,?,?,?,?,?,?,?)',
                   (s['sha256'], s['key'], s['url'], s.get('publication_date'),
                    s['acquired_at'], s['path'], s['kind'], canonical(s)))
        if s['kind'] == 'official_table_transcription':
            ingest_official_table(db,root,s)
            continue
        if s['kind'] == 'xlsx_census':
            ingest_workbook(db,root,s)
            continue
        if s['kind'] != 'arcgis_census':
            continue
        raw = json.loads((Path(root) / s['path']).read_text(encoding='utf-8'))
        for feature in raw['features']:
            a = feature['attributes']
            native = a.get(s['id_field'])
            if native is None:
                issue(db, None, s['sha256'], 'MISSING_NATIVE_ID', canonical(a))
                continue
            eid = entity(db, s['namespace'], native, s['entity_kind'])
            lon, lat = a.get('longitude'), a.get('latitude')
            if lon is None or lat is None:
                g = feature.get('geometry') or {}
                lon, lat = g.get('x'), g.get('y')
            if lon is not None and lat is not None and not (110 <= lon <= 155 and -45 <= lat <= -9):
                issue(db, eid, s['sha256'], 'COORDINATE_RANGE', canonical([lon, lat]))
                lon = lat = None
            db.execute('INSERT OR IGNORE INTO records VALUES(?,?,?,?,?,?,?,?,?)',
                       (eid, s['sha256'], a[s['name_field']], a.get('state'), lon, lat,
                        a.get('mineraldeposittype'), a.get('currentstatus'), canonical(a)))

def normalize(observation):
    """Mt × % -> kt = Mt × percent × 10; Mt × ppm -> kt = Mt × ppm / 1000."""
    o = observation
    reasons = []
    value = o.get('value')
    numeric = isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
    if not numeric:
        reasons.append('MISSING_OR_NONFINITE')
    elif value < 0:
        reasons.append('NEGATIVE_VALUE')
    if o.get('basis') != 'TREO' and o['variable'] in ('ore_mt', 'grade', 'contained_treo_kt'):
        reasons.append('NONCOMPARABLE_BASIS')
    if o['variable'] == 'grade':
        if o.get('unit') not in ('%', 'ppm'):
            reasons.append('UNSUPPORTED_GRADE_UNIT')
        elif numeric and value > (100 if o['unit'] == '%' else 1_000_000):
            reasons.append('GRADE_OUT_OF_RANGE')
    if not o.get('locator') or not o.get('scope') or not o.get('statement_id'):
        reasons.append('MISSING_SCOPE_OR_LOCATOR')
    if o.get('category') in ('EXPLORATION_TARGET', 'RESERVE') and o['variable'] in ('ore_mt', 'grade'):
        reasons.append('NOT_MINERAL_RESOURCE')
    if o['variable'] in ('ore_mt', 'grade','contained_treo_kt') and o.get('category') not in (
        'MEASURED','INDICATED','INFERRED','MEASURED_INDICATED_INFERRED_TOTAL','MEASURED_INDICATED_TOTAL'):
        reasons.append('UNSUPPORTED_RESOURCE_CATEGORY')
    if o.get('review_required'):
        reasons.append('SCIENTIFIC_REVIEW_REQUIRED')
    return sorted(set(reasons))

def ingest_claims(db, root, snapshots, cutoff, project=None):
    by_key = {s['key']: s for s in snapshots}
    claims = json.loads((Path(root) / 'data/claims.json').read_text(encoding='utf-8'))
    for p in claims['projects']:
        if project and p['id'] != project:
            continue
        source = by_key.get(p['identity_source'])
        if not source:
            continue
        eid = entity(db, 'project_registry_v1', p['id'], 'PROJECT')
        db.execute('INSERT OR IGNORE INTO records VALUES(?,?,?,?,?,?,?,?,?)',
                   (eid, source['sha256'], p['name'], p['state'], p.get('longitude'), p.get('latitude'),
                    p.get('deposit_type'), None, canonical(p)))
        coordinate_source = by_key.get(p.get('coordinate_source'))
        if coordinate_source:
            dep = db.execute('''SELECT r.* FROM records r JOIN entities e USING(entity_id)
                WHERE e.native_namespace=? AND e.native_id=? AND r.source_sha=?''',
                (coordinate_source['namespace'], str(p['coordinate_native_id']), coordinate_source['sha256'])).fetchone()
            if dep:
                db.execute('INSERT OR IGNORE INTO records VALUES(?,?,?,?,?,?,?,?,?)',
                    (eid, coordinate_source['sha256'], p['name'], p['state'],dep['longitude'],dep['latitude'],
                     p.get('deposit_type'), None, canonical(p)))
                db.execute('INSERT OR IGNORE INTO relations VALUES(?,?,?,?,?,?,?)',
                    (digest([eid,dep['entity_id'],'REPRESENTATIVE_POINT']),eid,dep['entity_id'],
                     'REPRESENTATIVE_POINT_NOT_ENTITY_EQUIVALENCE',coordinate_source['available_date'],
                     coordinate_source['sha256'],p['coordinate_role']))
        for o in p['observations']:
            s = by_key.get(o['source_key'])
            if not s or o['effective_date'] > cutoff:
                continue
            reasons = normalize(o)
            # Claim binding prevents silently applying old extraction to a changed PDF.
            if o['source_sha256'] != s['sha256']:
                reasons.append('EXTRACTION_VERSION_MISMATCH')
            if s['kind']=='pdf' and o.get('pdf_page'):
                from pypdf import PdfReader
                try:
                    text = PdfReader(Path(root)/s['path']).pages[o['pdf_page']-1].extract_text()
                    if not all(marker in text for marker in o.get('page_markers', [])):
                        reasons.append('EXTRACTION_PAGE_CHECK_FAILED')
                except Exception:
                    reasons.append('EXTRACTION_READ_FAILED')
            obsid = digest([eid, s['sha256'], o])
            db.execute('INSERT OR IGNORE INTO observations VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                       (obsid, eid, o['variable'], o.get('value'), o.get('unit'), o.get('basis'),
                        o['scope'], o['statement_id'], o.get('category'), o['effective_date'],
                        s['sha256'], o['locator'], 'AUTO_VALIDATED' if not reasons else 'REVIEW',
                        canonical(reasons), canonical(o), 'normalization-v1'))
            for reason in reasons:
                issue(db, eid, s['sha256'], reason, obsid)
    # Conflicting same-date, same-scope values are never resolved by insertion order.
    groups = db.execute('''SELECT entity_id,variable,scope,effective_date,COUNT(DISTINCT value) n
        FROM observations WHERE status='AUTO_VALIDATED' GROUP BY entity_id,variable,scope,effective_date HAVING n>1''').fetchall()
    for g in groups:
        params = tuple(g[k] for k in ('entity_id', 'variable', 'scope', 'effective_date'))
        db.execute('''UPDATE observations SET status='REVIEW' WHERE entity_id=? AND variable=?
                      AND scope=? AND effective_date=? AND status='AUTO_VALIDATED' ''', params)
        issue(db, g['entity_id'], None, 'SOURCE_CONFLICT', canonical(dict(g)))

def resource_values(db, cutoff, snapshot_shas):
    """Pick latest complete statement per scope; competing scopes require review."""
    result = {}
    projects = [r[0] for r in db.execute("SELECT entity_id FROM entities WHERE kind='PROJECT'")]
    for eid in projects:
        rows = [dict(r) for r in db.execute('''SELECT * FROM observations
            WHERE entity_id=? AND effective_date<=? AND status='AUTO_VALIDATED'
            ORDER BY effective_date,obs_id''', (eid, cutoff)) if r['source_sha'] in snapshot_shas]
        statements = {}
        for r in rows:
            statements.setdefault((r['statement_id'], r['scope'], r['effective_date']), {})[r['variable']] = r
        valid = []
        for (sid, scope, date), values in statements.items():
            if not {'ore_mt', 'grade'} <= values.keys():
                continue
            ore, grade = values['ore_mt'], values['grade']
            if ore['unit'] != 'Mt' or ore['basis'] != grade['basis'] or ore['source_sha'] != grade['source_sha']:
                continue
            contained = ore['value'] * grade['value'] * (10 if grade['unit'] == '%' else .001)
            ore_raw, grade_raw = json.loads(ore['raw']), json.loads(grade['raw'])
            ore_half = ore_raw.get('rounding_half_width') or 0
            grade_half = grade_raw.get('rounding_half_width') or 0
            factor = 10 if grade['unit']=='%' else .001
            bounds = [(ore['value']-ore_half)*(grade['value']-grade_half)*factor,
                      (ore['value']+ore_half)*(grade['value']+grade_half)*factor]
            reported = values.get('contained_treo_kt')
            if reported and not bounds[0] <= reported['value'] <= bounds[1]:
                issue(db,eid,reported['source_sha'],'REPORTED_CONTAINED_CONFLICT',canonical([reported['value'],bounds]))
                continue
            valid.append({'entity_id': eid, 'statement_id': sid, 'scope': scope, 'date': date,
                          'ore_mt': ore['value'], 'grade_pct': grade['value'] if grade['unit']=='%' else grade['value']/10000,
                          'contained_treo_kt': reported['value'] if reported else contained,
                          'calculated_from_rounded_inputs_kt':contained,'rounding_bounds_kt':bounds,
                          'obs_ids': [ore['obs_id'], grade['obs_id']] + ([reported['obs_id']] if reported else []),
                          'source_sha': ore['source_sha'], 'basis': 'TREO',
                          'interpretation': 'IN_SITU_RESOURCE_NOT_RECOVERABLE_PRODUCT'})
        if not valid:
            continue
        latest = max(v['date'] for v in valid)
        active = [v for v in valid if v['date'] == latest]
        if len(active) != 1:
            issue(db, eid, None, 'RESOURCE_SCOPE_AMBIGUITY', canonical(active))
            continue
        result[eid] = active[0]
    return result
