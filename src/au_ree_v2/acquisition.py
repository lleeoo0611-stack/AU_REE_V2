"""Immutable content-addressed acquisition, complete ArcGIS ID retrieval."""
import json
import urllib.parse
import urllib.request
import urllib.error
import time
import socket
from email.utils import parsedate_to_datetime
from datetime import datetime, timezone
from pathlib import Path
from .store import canonical, digest, filehash
from .spatial import project_windows

_last_request = {}


def failure_details(exc):
    """One public failure vocabulary for refresh and discovery; absence is unknown."""
    code=getattr(exc,'code',None)
    cause=getattr(exc,'reason',exc)
    state=({429:'HTTP_429_RATE_LIMITED',403:'HTTP_403_RESTRICTED',404:'HTTP_404_NOT_FOUND_AT_URL'}
           .get(code,'HTTP_'+str(code) if code else
                'TIMEOUT' if isinstance(cause,(TimeoutError,socket.timeout)) else
                'NON_PDF_RESPONSE' if str(exc) in ('NOT_PDF','Not a PDF response') else
                'TERMS_INTERSTITIAL_NOT_ACCEPTED' if str(exc)=='TERMS_INTERSTITIAL_NOT_ACCEPTED' else type(exc).__name__))
    return dict(failure_status=state,http_status=code,attempts=getattr(exc,'request_attempts',1),
                retry_after_seconds=getattr(exc,'retry_after_seconds',None),
                reason=type(exc).__name__+('_'+str(code) if code else ''),
                interpretation='URL_FAILURE_NOT_DOCUMENT_ABSENCE')


def request(url, params=None, headers=None, timeout=25):
    if params:
        url += ('&' if '?' in url else '?') + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={'User-Agent': 'AU_REE_V2/0.1 public research', **(headers or {})})
    for attempt in range(3):
        host=urllib.parse.urlsplit(url).netloc
        pause=.25-(time.monotonic()-_last_request.get(host,0))
        if pause>0:time.sleep(pause)
        _last_request[host]=time.monotonic()
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                return response.read(), dict(response.headers)
        except urllib.error.HTTPError as exc:
            exc.request_attempts=attempt+1
            delay=exc.headers.get('Retry-After') if exc.headers else None
            try:
                delay=max(0,float(delay))
            except (TypeError,ValueError):
                try:delay=max(0,(parsedate_to_datetime(delay)-datetime.now(timezone.utc)).total_seconds())
                except (TypeError,ValueError,OverflowError):delay=None
            exc.retry_after_seconds=delay
            # A long Retry-After is deferred, never capped then retried early.
            if exc.code not in (408,429,500,502,503,504) or attempt==2 or (delay is not None and delay>30):raise
            time.sleep(max(.5*(2**attempt),delay or 0))
        except (urllib.error.URLError,TimeoutError) as exc:
            exc.request_attempts=attempt+1
            if attempt==2:raise
            time.sleep(.5*(2**attempt))

def arcgis(url, where='1=1', windows=None, archive=None):
    """Inventory-complete retrieval, globally or within each registered project AOI."""
    def query(params):
        raw, _ = request(url.rstrip('/') + '/query', {'f': 'json', **params})
        if archive is not None:archive(raw)
        data = json.loads(raw)
        if 'error' in data:
            raise ValueError(canonical(data['error']))
        return data
    all_features = {}
    inventories = []
    oid_field = None
    for window in (windows if windows is not None else [None]):
        spatial = {}
        if window is not None:
            spatial = {'geometry': ','.join(map(str, window['bbox'])),
                       'geometryType':'esriGeometryEnvelope',
                       'inSR':4326, 'spatialRel':'esriSpatialRelIntersects'}
        ids = query({'where':where, 'returnIdsOnly':'true', **spatial})
        if 'objectIds' not in ids or not ids.get('objectIdFieldName'):
            raise ValueError('Missing ArcGIS ID inventory')
        field = ids['objectIdFieldName']
        if oid_field is not None and field != oid_field:
            raise ValueError('ArcGIS object ID field changed between windows')
        oid_field = field
        expected = sorted(set(ids['objectIds'] or []))
        seen = []
        for start in range(0,len(expected),500):
            page = query({'objectIds': ','.join(map(str,expected[start:start+500])),
                          'outFields':'*', 'outSR':4326, 'returnGeometry':'true'})
            if page.get('exceededTransferLimit'):
                raise ValueError('ArcGIS truncated response')
            for feature in page.get('features',[]):
                key = feature['attributes'][field]
                seen.append(key)
                all_features[key] = feature
        if len(seen) != len(expected) or sorted(seen) != expected:
            raise ValueError('Incomplete or duplicate ArcGIS IDs')
        if window is not None:
            inventories.append({**window,'id_count':len(expected),'complete':True})
    if oid_field is None:
        raise ValueError('Missing ArcGIS inventory scope')
    scope = 'registered_project_aoi' if windows is not None else 'global'
    return {'features':[all_features[k] for k in sorted(all_features)],
            'spatialReference':{'wkid':4326},
            'inventory':{'where':where, 'objectIdFieldName':oid_field,
                         'count':len(all_features), 'complete':True,
                         'scope':scope, 'queries':inventories}}


def wfs(source, archive=None):
    """Count-bound, native-ID checked WFS paging; never accept a partial inventory."""
    import xml.etree.ElementTree as ET
    base={'service':'WFS','version':source.get('wfs_version','2.0.0'),
          'request':'GetFeature','typeName':source['type_name'],
          'typeNames':source['type_name'],'srsName':'EPSG:4326'}
    hit,_=request(source['url'],{**base,'resultType':'hits'})
    if archive is not None:archive(hit)
    node=ET.fromstring(hit)
    total=node.get('numberMatched',node.get('numberOfFeatures'))
    if total is None or not str(total).isdigit():raise ValueError('WFS count not disclosed')
    total=int(total);features=[];seen=set();size=source.get('page_size',1000)
    if total>source.get('max_records',200000):raise ValueError('WFS inventory exceeds configured bound')
    while len(features)<total:
        params={**base,'outputFormat':'application/json','count':size,'maxFeatures':size}
        # SARIG WFS1.1 rejects even startIndex=0 on views without a declared PK.
        if len(features) or total>size:params['startIndex']=len(features)
        if source.get('sort_by'):params['sortBy']=source['sort_by']
        raw,_=request(source['url'],params)
        if archive is not None:archive(raw)
        if raw.lstrip().startswith(b'<'):
            raise ValueError('WFS service exception: '+' '.join(ET.fromstring(raw).itertext())[:800])
        data=json.loads(raw)
        page=data.get('features')
        if data.get('type')!='FeatureCollection' or not isinstance(page,list) or not page:
            raise ValueError('WFS missing page/FeatureCollection')
        for f in page:
            key=f.get('properties',{}).get(source['id_field'])
            if key is None or str(key) in seen:raise ValueError('WFS missing/duplicate native ID; unstable paging')
            seen.add(str(key));features.append(f)
        matched=data.get('numberMatched',data.get('totalFeatures'))
        if matched is not None and str(matched).isdigit() and int(matched)!=total:
            raise ValueError('WFS inventory changed during paging')
    if len(features)!=total:raise ValueError('WFS count mismatch')
    return {'type':'FeatureCollection','features':features,
            'inventory':{'complete':True,'count':total,'scope':'global','type_name':source['type_name'],
                         'id_field':source['id_field'],'srsName':'EPSG:4326','page_size':size}}


def government_changes(root,source,previous,raw):
    """Compare complete inventories by native ID; changes never mutate older bytes."""
    import csv,io
    def index(data):
        if source['kind']=='government_csv':
            rows=[{'attributes':r} for r in csv.DictReader(io.StringIO(data.decode(source.get('encoding','utf-8-sig'),errors=source.get('encoding_errors','strict'))))]
        else:rows=json.loads(data)['features']
        result={}
        for row in rows:
            attrs=row.get('attributes',row.get('properties',{}));key=attrs.get(source['id_field'])
            if key is None:raise ValueError('Version comparison missing native ID')
            # Some WFS views generate a new response FID on every request.
            # Native attributes and geometry define the data change, not that envelope FID.
            result.setdefault(str(key),set()).add(digest({'attributes':attrs,'geometry':row.get('geometry')}))
        return result
    current=index(raw)
    if not previous:return {'baseline':'FIRST_CAPTURE','current_native_id_groups':len(current)}
    old=index((Path(root)/previous['path']).read_bytes())
    shared=old.keys()&current.keys()
    return {'previous_sha256':previous['sha256'],'current_native_id_groups':len(current),
            'added_native_id_groups':len(current.keys()-old.keys()),'removed_native_id_groups':len(old.keys()-current.keys()),
            'changed_native_id_groups':sum(old[k]!=current[k] for k in shared),
            'unchanged_native_id_groups':sum(old[k]==current[k] for k in shared),
            'unit':'SOURCE_NATIVE_ID_GROUPS_NOT_PROJECTS'}

def refresh(root, registry):
    """A failed source is recorded and does not discard any existing snapshot."""
    root = Path(root)
    manifest_path = root / 'data/manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    outcomes = []
    for source in registry['sources']:
        try:
            pages=[]
            def archive(raw):
                import hashlib
                sha=hashlib.sha256(raw).hexdigest()
                path=root/'data/snapshots'/(sha+'.response')
                if not path.exists():path.write_bytes(raw)
                if filehash(path)!=sha:raise ValueError('ORIGINAL_RESPONSE_CONTENT_MISMATCH')
                pages.append({'sha256':sha,'path':path.relative_to(root).as_posix()})
            previous = [s for s in manifest['snapshots'] if s['key']==source['key']]
            latest = max(previous,key=lambda s:s['acquired_at']) if previous else {}
            if source['kind'] in ('official_table_transcription','official_project_catalogue_transcription','historical_e1_candidates','legacy_screen_index','pdf_page_extraction'):
                if not latest:
                    raise ValueError('Managed table snapshot absent')
                if filehash(root/latest['path']) != latest['sha256']:
                    raise ValueError('Managed table snapshot checksum mismatch')
                outcomes.append({'key':source['key'],'status':'MANAGED_TRANSCRIPTION_VERIFIED',
                                 'sha256':latest['sha256']})
                continue
            if source['kind']=='government_wfs':
                raw=(canonical(wfs(source,archive))+'\n').encode();headers={}
            elif source['kind'] in ('arcgis_census', 'arcgis_gis','government_arcgis'):
                windows = project_windows(root, manifest, source['aoi_radius_km']) if source.get('aoi_radius_km') else None
                raw = (canonical(arcgis(source['url'], source.get('where', '1=1'), windows=windows,
                                       archive=archive if source['kind']=='government_arcgis' else None)) + '\n').encode()
                headers={}
            else:
                conditional={}
                if latest.get('etag'):conditional['If-None-Match']=latest['etag']
                if latest.get('last_modified'):conditional['If-Modified-Since']=latest['last_modified']
                try:
                    raw, headers = request(source['url'],headers=conditional,timeout=source.get('timeout_seconds',25))
                except urllib.error.HTTPError as exc:
                    if exc.code==304 and latest:
                        outcomes.append({'key':source['key'],'status':'UNCHANGED_HTTP_304','sha256':latest['sha256']})
                        continue
                    raise
                if source['kind'] == 'pdf' and not raw.startswith(b'%PDF'):
                    raise ValueError('Not a PDF response')
                if source['kind'] == 'xlsx_census' and not raw.startswith(b'PK\x03\x04'):
                    raise ValueError('Not an OOXML workbook response')
            import hashlib
            from .security import public_snapshot
            raw,redaction=public_snapshot(root,raw,'.csv' if source['kind']=='government_csv' else '.json')
            sha = hashlib.sha256(raw).hexdigest()
            changes=government_changes(root,source,latest,raw) if source.get('national_government') else None
            if any(s['sha256'] == sha and s['key'] == source['key'] for s in manifest['snapshots']):
                existing=next(s for s in manifest['snapshots'] if s['sha256']==sha and s['key']==source['key'])
                if filehash(root/existing['path'])!=sha:raise ValueError('IMMUTABLE_SNAPSHOT_CONTENT_MISMATCH')
                outcomes.append({'key': source['key'], 'status': 'UNCHANGED', 'sha256': sha,
                                 **({'native_changes':changes} if changes else {}),
                                 **({'original_responses':pages} if pages else {})})
                continue
            suffix = '.pdf' if source['kind'] == 'pdf' else '.xlsx' if source['kind'] == 'xlsx_census' else '.csv' if source['kind']=='government_csv' else '.html' if source['kind']=='html' else '.json'
            path = root / 'data/snapshots' / (sha + suffix)
            path.parent.mkdir(parents=True, exist_ok=True)
            if not path.exists():path.write_bytes(raw)
            if filehash(path)!=sha:raise ValueError('IMMUTABLE_SNAPSHOT_CONTENT_MISMATCH')
            now = datetime.now(timezone.utc).isoformat()
            entry = {**source, 'sha256': sha, 'path': path.relative_to(root).as_posix(),
                     'acquired_at': now, 'available_date': now[:10],
                     'etag':headers.get('ETag'),'last_modified':headers.get('Last-Modified')}
            entry.update(redaction)
            if pages:entry['original_responses']=pages
            if changes:entry['native_changes']=changes
            manifest['snapshots'].append(entry)
            manifest_path.write_text(json.dumps(manifest,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
            outcomes.append({'key': source['key'], 'status': 'ADDED', 'sha256': sha})
        except Exception as exc:
            outcomes.append({'key': source['key'], 'status': 'UNAVAILABLE', 'reason': str(exc),
                             **failure_details(exc),
                             **({'original_responses':pages} if pages else {})})
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    return outcomes

def select_snapshots(root, cutoff, keys=None, acquired_through=None):
    manifest = json.loads((Path(root) / 'data/manifest.json').read_text(encoding='utf-8'))
    selected = {}
    def visible(s):
        if s.get('publication_date', '')>cutoff:return False
        if s['available_date']<=cutoff:return True
        # Retrospective acquisition is explicit and limited to dated documents
        # and their extraction artifacts; never backdate live GIS/government rows.
        if not acquired_through or s['available_date']>acquired_through:return False
        if s['kind']=='discovery_receipt':return True  # Acquisition diagnostics, never observations.
        if s['kind'] not in ('pdf','html','document_extraction','pdf_page_extraction'):return False
        if s['kind'] in ('pdf','html'):return bool(s.get('publication_date'))
        return any(o['sha256']==s.get('source_sha256') and o.get('publication_date') and o['publication_date']<=cutoff for o in manifest['snapshots'])
    for s in manifest['snapshots']:
        if keys and s['key'] not in keys:
            continue
        # Never backdate a current live response to an earlier analysis cutoff.
        if not visible(s):
            continue
        if s['key'] not in selected or s['acquired_at'] > selected[s['key']]['acquired_at']:
            selected[s['key']] = s
    private={s['unpublished_original_sha256'] for s in selected.values() if s.get('publication_derivative')}
    # Every available historical file remains checksum-checked. Only an explicitly
    # declared unpublished original can be absent from a public derivative replay.
    for s in manifest['snapshots']:
        if keys and s['key'] not in keys:continue
        if not visible(s):continue
        path=Path(root)/s['path']
        if not path.exists() and s['sha256'] in private:continue
        if not path.exists() or filehash(path)!=s['sha256']:raise ValueError('Snapshot checksum mismatch: '+s['path'])
        for page in s.get('original_responses',[]):
            if filehash(Path(root)/page['path'])!=page['sha256']:raise ValueError('Original service response checksum mismatch: '+page['path'])
    return [selected[k] for k in sorted(selected)]
