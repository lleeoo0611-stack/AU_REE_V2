"""Immutable content-addressed acquisition, complete ArcGIS ID retrieval."""
import json
import urllib.parse
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path
from .store import canonical, digest, filehash
from .spatial import project_windows

def request(url, params=None, headers=None, timeout=25):
    if params:
        url += '?' + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={'User-Agent': 'AU_REE_V2/0.1 public research', **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.read(), dict(response.headers)

def arcgis(url, where='1=1', windows=None):
    """Inventory-complete retrieval, globally or within each registered project AOI."""
    def query(params):
        raw, _ = request(url.rstrip('/') + '/query', {'f': 'json', **params})
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
        for start in range(0,len(expected),150):
            page = query({'objectIds': ','.join(map(str,expected[start:start+150])),
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

def refresh(root, registry):
    """A failed source is recorded and does not discard any existing snapshot."""
    root = Path(root)
    manifest_path = root / 'data/manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    outcomes = []
    for source in registry['sources']:
        try:
            previous = [s for s in manifest['snapshots'] if s['key']==source['key']]
            latest = max(previous,key=lambda s:s['acquired_at']) if previous else {}
            if source['kind'] in ('official_table_transcription','official_project_catalogue_transcription','historical_e1_candidates','legacy_screen_index'):
                if not latest:
                    raise ValueError('Managed table snapshot absent')
                if filehash(root/latest['path']) != latest['sha256']:
                    raise ValueError('Managed table snapshot checksum mismatch')
                outcomes.append({'key':source['key'],'status':'MANAGED_TRANSCRIPTION_VERIFIED',
                                 'sha256':latest['sha256']})
                continue
            if source['kind'] in ('arcgis_census', 'arcgis_gis'):
                windows = project_windows(root, manifest, source['aoi_radius_km']) if source.get('aoi_radius_km') else None
                raw = (canonical(arcgis(source['url'], source.get('where', '1=1'), windows=windows)) + '\n').encode()
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
            sha = hashlib.sha256(raw).hexdigest()
            if any(s['sha256'] == sha and s['key'] == source['key'] for s in manifest['snapshots']):
                outcomes.append({'key': source['key'], 'status': 'UNCHANGED', 'sha256': sha})
                continue
            suffix = '.pdf' if source['kind'] == 'pdf' else '.xlsx' if source['kind'] == 'xlsx_census' else '.json'
            path = root / 'data/snapshots' / (sha + suffix)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
            now = datetime.now(timezone.utc).isoformat()
            entry = {**source, 'sha256': sha, 'path': path.relative_to(root).as_posix(),
                     'acquired_at': now, 'available_date': now[:10],
                     'etag':headers.get('ETag'),'last_modified':headers.get('Last-Modified')}
            manifest['snapshots'].append(entry)
            outcomes.append({'key': source['key'], 'status': 'ADDED', 'sha256': sha})
        except Exception as exc:
            outcomes.append({'key': source['key'], 'status': 'UNAVAILABLE', 'reason': str(exc)})
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    return outcomes

def select_snapshots(root, cutoff, keys=None):
    manifest = json.loads((Path(root) / 'data/manifest.json').read_text(encoding='utf-8'))
    selected = {}
    for s in manifest['snapshots']:
        if keys and s['key'] not in keys:
            continue
        # Never backdate a current live response to an earlier analysis cutoff.
        if s['available_date'] > cutoff or s.get('publication_date', '') > cutoff:
            continue
        if filehash(Path(root) / s['path']) != s['sha256']:
            raise ValueError('Snapshot checksum mismatch: ' + s['path'])
        if s['key'] not in selected or s['acquired_at'] > selected[s['key']]['acquired_at']:
            selected[s['key']] = s
    return [selected[k] for k in sorted(selected)]
