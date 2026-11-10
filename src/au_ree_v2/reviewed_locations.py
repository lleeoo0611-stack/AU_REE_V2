"""Reviewed GA catalogue points; never resource boundaries, status or identity merges."""
import json
import math
import re
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit, parse_qs
from .store import filehash, canonical
from .project_identity import normalized_name

BASE = 'https://services.ga.gov.au/gis/rest/services/AustralianCriticalMineralsOperatingMinesAndDeposits/MapServer'


def validate_location_target(row, attributes, states, resource_subscope=False):
    if resource_subscope or 'resource scope' in row['專案名稱'].lower():
        raise ValueError('LOCATION_PROJECT_POINT_NOT_SELECTED_RESOURCE_SUBSCOPE')
    if any(row[c] for c in ('緯度','經度')):
        raise ValueError('LOCATION_CANNOT_OVERWRITE_EXISTING_PAIR')
    if len(attributes)!=2 or {a['column'] for a in attributes}!={'緯度','經度'}:
        raise ValueError('LOCATION_PAIR_REQUIRED')
    if len({a['state'] for a in attributes})!=1 or row['州省地區']!=states[attributes[0]['state']]:
        raise ValueError('LOCATION_PROJECT_STATE_MISMATCH')


def validate_locations(ledger_path, asset_roots, projects, cutoff, verified_pdf_reviews=()):
    cfg = json.loads(Path(ledger_path).read_text('utf8'))
    def fail(code):
        raise ValueError('LOCATION_' + code)
    if (cfg.get('version') != 'ga-native-project-location-v1' or cfg.get('cutoff') != cutoff
            or cfg.get('effective_date') != '2025-12-31'
            or cfg.get('date_precision') != 'MONTH'
            or cfg.get('effective_date_interval') != ['2025-12-01', '2025-12-31']
            or date.fromisoformat(cfg['effective_date']) > date.fromisoformat(cutoff)):
        fail('CURRENCY_CONTRACT')
    def load(proof):
        root = Path(asset_roots[proof['asset_set']]).resolve()
        path = (root/proof['path']).resolve()
        if root not in path.parents or filehash(path) != proof['sha256']:
            fail('ASSET_HASH_OR_PATH')
        rows = json.loads((root/'downloads.json').read_text('utf8'))
        if not any(r.get('url') == proof['url'] and r.get('document_sha256') == proof['sha256']
                   and r.get('status') == 'HTML_CAPTURED' for r in rows):
            fail('TEXT_CAPTURE_RECEIPT')
        return json.loads(path.read_text('utf8'))
    meta_proof = cfg['service_metadata']
    if meta_proof['url'] != BASE+'?f=pjson':
        fail('OFFICIAL_METADATA_URL')
    meta = load(meta_proof)
    if (meta.get('spatialReference', {}).get('wkid') != 4283
            or 'as at December 2025' not in meta.get('description', '')
            or '150802' not in meta.get('description', '')):
        fail('DATUM_OR_CURRENCY')
    datasets = {}; sources = {}
    for key, proof in cfg['sources'].items():
        u = urlsplit(proof['url']); layer = re.fullmatch(re.escape(urlsplit(BASE).path)+r'/([4-7])/query', u.path)
        if (u.scheme != 'https' or u.netloc != 'services.ga.gov.au' or not layer or u.fragment
                or parse_qs(u.query) != {'where':['1=1'], 'outFields':['*'], 'outSR':['4283'],
                                       'returnGeometry':['true'], 'f':['pjson']}):
            fail('OFFICIAL_FEATURE_URL')
        data = load(proof)
        if (data.get('spatialReference', {}).get('wkid') != 4283
                or data.get('exceededTransferLimit') not in (None, False)
                or not isinstance(data.get('features'), list) or data.get('error')):
            fail('INCOMPLETE_OR_WRONG_CRS_RESPONSE')
        datasets[key] = data
        sources[proof['sha256']] = dict(key=key, kind='json', sha256=proof['sha256'],
            path=proof['path'], asset_root=str(Path(asset_roots[proof['asset_set']]).resolve()),
            url=proof['url'], publication_date=None, available_date=cfg['acquired_through'],
            publication_date_role='DATASET_RELEASE_DAY_UNKNOWN;CURRENCY_MONTH_ONLY',
            source_kind='GOVERNMENT_SPATIAL_CATALOGUE')
    date.fromisoformat(cfg['acquired_through'])
    registry = {p['entity_id']:p for p in projects}; attributes = {}; receipts = []; seen = set(); review_ids=set()
    for case in cfg['reviews']:
        pid = case['project_id']; rid = case['review_id']; oid = case['objectid']
        if pid in seen or rid in review_ids or pid not in registry or isinstance(oid, bool) or not isinstance(oid, int):
            fail('PROJECT_OR_DUPLICATE')
        seen.add(pid); review_ids.add(rid); p = registry[pid]
        if p['name'] != case['reviewed_project_name'] or case['scope_match'] != 'NAMED_SINGLE_PROJECT_OR_DEPOSIT':
            fail('REVIEWED_PROJECT_SCOPE')
        name = p['name'].split(' — ')[0]
        if 'resource scope' in p['name'].lower() or ' – ' in name:
            fail('COMPONENT_OR_RESOURCE_SCOPE_REQUIRES_SEPARATE_PROOF')
        key = case['source_key']; proof = cfg['sources'][key]
        hits = [f for f in datasets[key]['features'] if f.get('attributes', {}).get('objectid') == oid]
        if len(hits) != 1:
            fail('UNIQUE_NATIVE_RECORD')
        f = hits[0]; a = f['attributes']; g = f.get('geometry', {})
        if (a.get('projectname') != case['source_project_name'] or a.get('state') != case['state']
                or normalized_name(a['projectname']) not in {normalized_name(x) for x in p['aliases']+[p['name']]}
                or '150802' not in (a.get('source') or '')):
            fail('NAME_STATE_COMMODITY_OR_SOURCE')
        material_proof = None
        if not re.search(r'\bREE\b|rare earth|monazite|xenotime', a.get('commodities') or '', re.I):
            # A location catalogue need not list every by-product. A second,
            # independently validated PDF must establish this same HMS project's
            # REE role; neither commodity quantities nor a neighbouring mine pass.
            proof=case.get('ree_hms_material_proof')
            if (not isinstance(proof,dict) or 'mineral sands' not in p['name'].lower()
                    or not (a.get('commodities') or '').lower().startswith('heavy mineral sands')
                    or not any(r.get('status')=='VALIDATED' and r['project_id']==pid
                        and r['review_id']==proof.get('review_id') and r['source_sha256']==proof.get('sha256')
                        for r in verified_pdf_reviews)):
                fail('NAME_STATE_COMMODITY_OR_SOURCE')
            material_review=next(r for r in verified_pdf_reviews if r.get('status')=='VALIDATED'
                and r['project_id']==pid and r['review_id']==proof['review_id'] and r['source_sha256']==proof['sha256'])
            if date.fromisoformat(material_review['effective_date'])>date.fromisoformat(cutoff):
                fail('MATERIAL_DATE_OUTSIDE_CUTOFF')
            import pymupdf,hashlib
            from .source_cells import norm,region_text
            root=Path(asset_roots[proof['asset_set']]).resolve();path=(root/proof['path']).resolve()
            if root not in path.parents or filehash(path)!=proof['sha256']:
                fail('MATERIAL_PDF_HASH_OR_PATH')
            with pymupdf.open(path) as doc:
                pn=proof.get('page');raw=proof.get('bbox')
                if (isinstance(pn,bool) or not isinstance(pn,int) or not 1<=pn<=len(doc)
                        or not isinstance(raw,list) or len(raw)!=4
                        or any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) for v in raw)):
                    fail('MATERIAL_PDF_REGION')
                pg=doc[pn-1];box=pymupdf.Rect(raw)
                if box.is_empty or box.is_infinite or not pg.rect.contains(box):fail('MATERIAL_PDF_REGION')
                text=norm(region_text(pg,box));marker=norm(proof.get('project_marker',''))
                if (normalized_name(marker)!=normalized_name(a['projectname']) or marker not in text
                        or hashlib.sha256(text.encode()).hexdigest()!=proof.get('statement_sha256')
                        or not re.search(r'\bree\b|rare earth|monazite|xenotime',text)
                        or not re.search(r'heavy mineral|mineral sands|rutile|zircon',text)):
                    fail('MATERIAL_PDF_PROJECT_OR_REE_ROLE')
            material_proof=dict(review_id=proof['review_id'],sha256=proof['sha256'],page=pn,
                statement_sha256=proof['statement_sha256'],pdf_evidence_effective_date=material_review['effective_date'],
                pdf_evidence_date_precision=material_review['date_precision'],
                date_relationship='LATER_CORROBORATION_NOT_BACKDATED_AS_DATASET_KNOWLEDGE')
        values = [a.get('latitude'), a.get('longitude'), g.get('y'), g.get('x')]
        if any(isinstance(v, bool) or not isinstance(v, (int,float)) or not math.isfinite(v) for v in values):
            fail('FINITE_PAIRED_COORDINATES')
        lat, lon, y, x = values
        if (not -44 < lat < -10 or not 110 < lon < 155
                or abs(lat-y) > 1e-6 or abs(lon-x) > 1e-6):
            fail('AU_RANGE_OR_GEOMETRY_ATTRIBUTE_DISAGREEMENT')
        scope_data = dict(meaning='OFFICIAL_NAMED_PROJECT_REPRESENTATIVE_POINT_NOT_RESOURCE_EXTENT_OR_BOUNDARY',
            source_project=a['projectname'], state=a['state'], objectid=oid, crs='GDA94 / EPSG:4283',
            unit='decimal degrees', source_latitude=lat, source_longitude=lon,
            display_rounding='at most 4 decimal places; does not improve coarse native precision',
            positional_accuracy='NOT_STATED;DISPLAY_ROUNDING_AND_SERVICE_TOLERANCE_ARE_NOT_GROUND_ACCURACY',
            service_metadata_sha256=meta_proof['sha256'],dataset_currency='December 2025; day unknown')
        if material_proof:scope_data['ree_hms_material_proof']=material_proof
        scope=canonical(scope_data)
        attributes[pid] = [dict(column=col, value=round(value,4), source_sha=proof['sha256'],
            locator='GA native feature objectid='+str(oid)+'; attributes.'+field+' checked against geometry; '+scope,
            method='REVIEWED_GA_GDA94_NAMED_REPRESENTATIVE_POINT_NOT_BOUNDARY',scope=scope,
            state=case['state'],review_id=rid) for col,field,value in [('緯度','latitude',lat),('經度','longitude',lon)]]
        receipts.append(dict(project_id=pid,review_id=rid,source_sha256=proof['sha256'],scope=scope,
            effective_date=cfg['effective_date'],effective_date_interval=cfg['effective_date_interval'],
            effective_date_role='DATASET_CURRENCY_MONTH_UPPER_BOUND_NOT_RELEASE_OR_PROJECT_STATUS_DATE',
            date_precision='MONTH',review_methods=['OFFICIAL_NATIVE_PAIRED_POINT_RECORD;DATUM_AND_CURRENCY_VERIFIED']))
    return dict(attributes=attributes,sources=sources,receipts=receipts,ledger_sha256=filehash(ledger_path))
