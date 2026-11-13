"""Narrow WA retry and offline projection; no networking in collect()."""
import hashlib
import json
import urllib.parse
import xml.etree.ElementTree as ET
from pathlib import Path
from .round4_tenements import verified_bytes, validate_original, identifier_key, centroid

DECISION = 'round5-wa-sortby-20261113'
RULE = 'WA_REMOVE_SORTBY_ONLY'


def retry_url(original, *, hits=False, start_index=None):
    """Only remove sortBy; permitted hits/paging controls are explicit."""
    u = urllib.parse.urlsplit(original)
    pairs = [(k,v) for k,v in urllib.parse.parse_qsl(u.query, keep_blank_values=True) if k.lower() != 'sortby']
    if start_index is not None:
        pairs = [(k, str(start_index) if k == 'startIndex' else v) for k,v in pairs]
    if hits:
        pairs.append(('resultType', 'hits'))
    return urllib.parse.urlunsplit((u.scheme,u.netloc,u.path,urllib.parse.urlencode(pairs),u.fragment))


def response_error(status, raw):
    if status != 200:
        return f'STOPPED_HTTP_{status}_NO_RETRY'
    text = raw.decode('utf8', errors='replace').lower()
    if '<html' in text or '<!doctype html' in text or any(x in text for x in ('captcha','sign in','log in','login')):
        return 'STOPPED_LOGIN_CAPTCHA_OR_HTML_NO_RETRY'
    if 'exceptionreport' in text or 'serviceexception' in text:
        return 'STOPPED_SERVICE_EXCEPTION_NO_PARAMETER_CHANGE'
    return None


def matched_count(raw):
    try:
        value = json.loads(raw)['numberMatched']
    except (ValueError, KeyError):
        value = ET.fromstring(raw).attrib.get('numberMatched')
    if isinstance(value, bool) or not str(value).isdigit():
        raise ValueError('WA_NUMBER_MATCHED_REQUIRED')
    return int(value)


def validate_pages(expected, pages):
    """Reject overlaps/unstable counts instead of filling from partial pages."""
    features=[]; ids=set(); offset=0
    for start, page in pages:
        found=page.get('features')
        if start != offset or not isinstance(found,list) or not found:
            raise ValueError('WA_PAGINATION_INCOMPLETE')
        if 'numberMatched' in page and str(page['numberMatched']) != str(expected):
            raise ValueError('WA_PAGINATION_MATCHED_CHANGED')
        if 'numberReturned' in page and page['numberReturned'] != len(found):
            raise ValueError('WA_PAGINATION_RETURNED_MISMATCH')
        for feature in found:
            fid=feature.get('id')
            if fid is None or str(fid) in ids:
                raise ValueError('WA_UNSTABLE_OR_MISSING_FEATURE_ID')
            ids.add(str(fid));features.append(feature)
        offset+=len(found)
    if len(ids)!=expected:
        raise ValueError('WA_PAGINATION_COUNT_MISMATCH')
    return features


def acquire(repo, fetch):
    """One durable attempt; injected fetch must not retry or follow redirects."""
    repo=Path(repo); cfg=json.loads((repo/'config/round5_wa.json').read_text('utf8'))
    original=cfg['original_failed_receipt']
    verified_bytes(repo,original)
    if original['url']!=cfg['original_url'] or original.get('state')!='WA' or original.get('http_status')!=400:
        raise ValueError('WA_ORIGINAL_FAILED_REQUEST_REQUIRED')
    endpoint='https://public-services.slip.wa.gov.au/public/services/SLIP_Public_Services/Industry_and_Mining_WFS/MapServer/WFSServer'
    if cfg['original_url'].split('?',1)[0]!=endpoint:
        raise ValueError('WA_ENDPOINT_CHANGE_FORBIDDEN')
    out=repo/cfg['acquisition_dir'];out.mkdir(parents=True,exist_ok=True)
    manifest_path=out/'manifest.json'
    if manifest_path.exists():
        raise ValueError('WA_ATTEMPT_ALREADY_RECORDED_NO_RETRY')
    manifest=dict(decision_id=cfg['decision_id'],state='WA',status='STARTED',request_count=0,requests=[],pages=[],numberMatched=None)
    def save():manifest_path.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    save()
    def get(url, kind, start=None):
        from datetime import datetime, timezone
        receipt=dict(state='WA',url=url,requested_at=datetime.now(timezone.utc).isoformat(),version='retrieval snapshot',decision_id=cfg['decision_id'],kind=kind)
        manifest['requests'].append(receipt);manifest['request_count']+=1;save()
        status, raw=fetch(url)
        sha=hashlib.sha256(raw).hexdigest();path=out/(sha+'.raw');path.write_bytes(raw)
        receipt.update(http_status=status,source_sha256=sha,path=path.relative_to(repo).as_posix())
        if start is not None:receipt['start_index']=start
        error=response_error(status,raw)
        receipt['status']='STOPPED' if error else 'COMPLETE';save()
        if error:raise ValueError(error)
        return raw,dict(receipt)
    try:
        raw,hits=get(retry_url(cfg['original_url'],hits=True),'HITS')
        expected=matched_count(raw);manifest['numberMatched']=expected;manifest['hits']=hits;save()
        start=0;decoded=[]
        while start<expected:
            raw,page=get(retry_url(cfg['original_url'],start_index=start),'FEATURES',start)
            data=json.loads(raw)
            if data.get('type')!='FeatureCollection':raise ValueError('WA_FEATURE_COLLECTION_REQUIRED')
            decoded.append((start,data));manifest['pages'].append(page);save()
            found=data.get('features',[])
            if not found:raise ValueError('WA_EMPTY_PAGE_BEFORE_COMPLETION')
            # Detect overlap immediately, even before final completeness check.
            ids=[str(f.get('id')) for _,p in decoded for f in p['features']]
            if len(ids)!=len(set(ids)) or any(f.get('id') is None for _,p in decoded for f in p['features']):
                raise ValueError('WA_UNSTABLE_OR_MISSING_FEATURE_ID')
            if 'numberMatched' in data and str(data['numberMatched'])!=str(expected):raise ValueError('WA_PAGINATION_MATCHED_CHANGED')
            start+=len(found)
        validate_pages(expected,decoded)
        manifest['status']='COMPLETE'
    except Exception as exc:
        manifest['status']='STOPPED';manifest['reason']=str(exc)
    save()
    return manifest


def load_features(repo,cfg):
    manifest=json.loads((repo/cfg['acquisition_dir']/'manifest.json').read_text('utf8'))
    requests=manifest['requests']; stopped=False
    for receipt in requests:
        if stopped:raise ValueError('WA_REQUEST_AFTER_STOP')
        if receipt.get('state')!='WA' or receipt.get('decision_id')!=cfg['decision_id']:raise ValueError('WA_RECEIPT_SCOPE')
        kind=receipt.get('kind');expected=retry_url(cfg['original_url'],hits=kind=='HITS',start_index=receipt.get('start_index') if kind=='FEATURES' else None)
        if receipt['url']!=expected:raise ValueError('WA_UNAUTHORIZED_PARAMETER_CHANGE')
        if 'source_sha256' not in receipt:raise ValueError(manifest.get('reason','WA_REQUEST_INTERRUPTED'))
        raw=verified_bytes(repo,receipt)
        stopped=bool(response_error(receipt['http_status'],raw))
    if manifest['request_count']!=len(requests):raise ValueError('WA_REQUEST_COUNT_MISMATCH')
    if manifest['status']!='COMPLETE' or stopped:raise ValueError(manifest.get('reason','WA_ACQUISITION_INCOMPLETE'))
    if not requests or requests[0]['kind']!='HITS':raise ValueError('WA_HITS_FIRST_REQUIRED')
    if manifest['hits']!=requests[0] or sum(r['kind']=='HITS' for r in requests)!=1:raise ValueError('WA_HITS_RECEIPT_MISMATCH')
    expected=matched_count(verified_bytes(repo,manifest['hits']))
    if expected!=manifest['numberMatched']:raise ValueError('WA_MATCHED_COUNT_CHANGED')
    if manifest['pages']!=[r for r in requests if r['kind']=='FEATURES']:raise ValueError('WA_PAGE_RECEIPT_MISMATCH')
    pages=[]
    for receipt in manifest['pages']:
        data=json.loads(verified_bytes(repo,receipt))
        # Require explicit datum instead of treating requested datum as observed.
        crs=data.get('crs',{}).get('properties',{}).get('name')
        if crs not in ('urn:ogc:def:crs:EPSG::7844','EPSG:7844','urn:ogc:def:crs:EPSG:0:7844'):
            raise ValueError('WA_SOURCE_DATUM_NOT_VERIFIED')
        pages.append((receipt['start_index'],data))
    return validate_pages(expected,pages),manifest


def collect(rows,trace,decisions,repo,census=None):
    repo=Path(repo);cfg=json.loads((repo/'config/round5_wa.json').read_text('utf8'))
    approved={d['decision_id']:d for d in decisions['decisions'] if d.get('decided_by')=='USER_EXPLICIT_APPROVAL'}
    if cfg['decision_id'] not in approved or approved[cfg['decision_id']].get('rule')!=RULE:
        raise ValueError('ROUND5_WA_APPROVAL_REQUIRED')
    old=json.loads((repo/'config/round4_tenements.json').read_text('utf8'))
    records={r['project_id']:r for r in old['projects'] if r['state']=='WA'}
    if sorted(records)!=sorted(cfg['project_ids']) or len(records)!=12:raise ValueError('WA_TWELVE_PROJECT_SCOPE_CHANGED')
    fills=[];reviews=[];accepted=[];error=None;manifest={}
    try:
        if cfg['license_url'] not in verified_bytes(repo,cfg['license_evidence']).decode('utf8'):raise ValueError('WA_LICENSE_EVIDENCE_MISSING')
        features,manifest=load_features(repo,cfg)
    except (ValueError,KeyError,FileNotFoundError) as exc:
        error=str(exc)
        path=repo/cfg['acquisition_dir']/'manifest.json'
        if path.exists():manifest=json.loads(path.read_text('utf8'))
    for row in rows:
        pid=row['專案ID']
        if pid not in records or row.get('緯度') or row.get('經度'):continue
        record=records[pid];result={}
        try:
            validate_original(record,pid,repo,trace)
            if error:raise ValueError(error)
            wanted={identifier_key(i) for i in record['tenement_ids']}
            chosen=[f for f in features if identifier_key(f['properties'].get('fmt_tenid','')) in wanted]
            if {identifier_key(f['properties']['fmt_tenid']) for f in chosen}!=wanted:raise ValueError('EXACT_TENEMENT_IDS_NOT_ALL_FOUND')
            result=centroid(chosen,'EPSG:7844',25000,id_field='fmt_tenid')
            if not result['accepted']:raise ValueError(result['reason'])
            holders=sorted({str(f['properties'].get('holder'+str(i),'')).strip() for f in chosen for i in range(1,10)}-{''})
            if not holders:raise ValueError('WA_HOLDER_METADATA_MISSING')
            sha=[p['source_sha256'] for p in manifest['pages']]
            scope=dict(result,decision_id=cfg['decision_id'],tenement_ids=record['tenement_ids'],official_tenement_ids=[f['properties']['fmt_tenid'] for f in chosen],identifier_rule='TYPE_AND_INTEGER_COMPONENTS_ONLY_NO_NAME_MATCH',layer_sha256=sha,holders=holders,holder_mismatch=any(h!=row.get('開發商','') for h in holders),original_references=record['original_references'],feature_properties=[f['properties'] for f in chosen],scope_note='TENEMENT_CENTROID, NOT mineral occurrence point; existing notes preserved',numberMatched=manifest['numberMatched'])
            for column,key in [('緯度','latitude'),('經度','longitude')]:
                value=f'{result[key]:.7f}'
                provenance=dict(project_id=pid,column=column,value=value,source_sha256=sha[0],source_url=cfg['endpoint'],locator='; '.join(record['tenement_ids']),method='ROUND5_WA_TENEMENT_CENTROID_RESEARCHER_APPROVED',scope=json.dumps(scope,ensure_ascii=False,sort_keys=True),observation_ids='[]',review_ids=json.dumps([cfg['decision_id']]),review_methods='["EXACT_TENEMENT_ID_MATCH"]',acquired_through=manifest['requests'][-1]['requested_at'],source_kind='GOVERNMENT_SPATIAL_CATALOGUE',publication_date_role='DATASET_VERSION_NOT_MRE',resource_effective_date_unknown='True',public_release_date_unknown='True',location_method=result['location_method'],precision_m=str(result['precision_m']),datum=result['input_datum'],tenement_ids=json.dumps(record['tenement_ids']),layer_sha256=json.dumps(sha),holders=json.dumps(holders),holder_mismatch=str(scope['holder_mismatch']))
                fills.append(dict(project_id=pid,column=column,value=value,decision_id=cfg['decision_id'],provenance=provenance))
            accepted.append(dict(project_id=pid,project=row['專案名稱'],**scope))
        except (ValueError,KeyError,FileNotFoundError) as exc:
            reviews.append(dict(project_id=pid,project=row['專案名稱'],reason=str(exc),candidates='[]',details=json.dumps(result,sort_keys=True)))
    return fills,reviews,dict(tenement_centroids=accepted,centroid_rows=len(accepted),request_count=manifest.get('request_count',0),state_status={'WA':manifest.get('status','NOT_ACQUIRED')},review_rows=len(reviews),source_backed_projects=12,other_state_requests=0,unchanged_filter=True)
