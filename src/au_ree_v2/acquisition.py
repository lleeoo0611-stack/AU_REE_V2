"""Immutable content-addressed acquisition, complete ArcGIS ID retrieval."""
import hashlib
import json
import urllib.parse
import urllib.request
import urllib.error
import time
import socket
import re
import zipfile
from email.utils import parsedate_to_datetime
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlsplit
from .security import sensitive_reference
from .source_discovery import official_query, strict_search_plan
from .store import canonical, digest, filehash, append_snapshots
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
                **({'network_error':True} if getattr(exc,'strict_network_error',False) else {}),
                **({'validation_error':str(exc)} if isinstance(exc,ValueError) and __import__('re').fullmatch(r'[A-Z_]{3,100}',str(exc)) else {}),
                retry_after_seconds=getattr(exc,'retry_after_seconds',None),
                reason=type(exc).__name__+('_'+str(code) if code else ''),
                interpretation='URL_FAILURE_NOT_DOCUMENT_ABSENCE')


def request(url, params=None, headers=None, timeout=25, method='GET', max_bytes=None):
    data=None
    if params and method=='POST':data=urllib.parse.urlencode(params).encode()
    elif params:
        url += ('&' if '?' in url else '?') + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, data=data,method=method,headers={'User-Agent': 'AU_REE_V2/0.1 public research', **(headers or {})})
    for attempt in range(3):
        host=urllib.parse.urlsplit(url).netloc
        pause=.25-(time.monotonic()-_last_request.get(host,0))
        if pause>0:time.sleep(pause)
        _last_request[host]=time.monotonic()
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                raw=response.read(max_bytes+1) if max_bytes is not None else response.read()
                if max_bytes is not None and len(raw)>max_bytes:raise ValueError('DOCUMENT_BYTE_BUDGET_EXCEEDED')
                return raw, dict(response.headers)
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

def arcgis(url, where='1=1', windows=None, archive=None, fetch=None, max_records=None,start_after=None):
    """Inventory-complete retrieval, globally or within each registered project AOI."""
    def query(params):
        raw, _ = (fetch or request)(url.rstrip('/') + '/query', {'f': 'json', **params})
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
        total_count=len(expected)
        if start_after is not None:expected=[oid for oid in expected if oid>start_after]
        remaining_count=len(expected)
        if max_records is not None:expected=expected[:max(0,max_records-len(all_features))]
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
                         'count':len(all_features), 'complete':max_records is None or (remaining_count if start_after is not None else total_count)<=max_records,
                         **({'matched_count':total_count,'record_budget':max_records} if max_records is not None else {}),
                         **({'start_after':start_after,'remaining_count':remaining_count,
                             'next_cursor':max(all_features) if all_features and max_records is not None and remaining_count>len(all_features) else None} if start_after is not None else {}),
                         'scope':scope, 'queries':inventories}}


def ckan(url, query, rows=10, max_pages=2, fetch=None, archive=None,start_offset=0):
    """Bounded public package_search; count is not the number retrieved.

    API-level failures, duplicates, count drift and premature empty pages are
    failures, even with HTTP 200. Each original response is archived first.
    """
    if not 1<=rows<=1000 or not 1<=max_pages<=20:raise ValueError('INVALID_CKAN_BUDGET')
    items={};count=None;pages=0
    for page in range(max_pages):
        raw,_=(fetch or request)(url.rstrip('/')+'/package_search',dict(q=query,rows=rows,start=start_offset+page*rows,sort='id asc'))
        if archive:archive(raw)
        data=json.loads(raw)
        if data.get('success') is not True:raise ValueError('CKAN_API_UNSUCCESSFUL')
        result=data['result'];current=result['count']
        if not isinstance(current,int) or current<0:raise ValueError('CKAN_INVALID_COUNT')
        if count is not None and count!=current:raise ValueError('CKAN_COUNT_CHANGED_RETRY_LATER')
        count=current;batch=result['results'];pages+=1
        if not isinstance(batch,list) or len(batch)>rows:raise ValueError('CKAN_INVALID_PAGE')
        if not batch and start_offset+len(items)<count:raise ValueError('CKAN_PREMATURE_EMPTY_PAGE')
        for item in batch:
            if not item.get('id') or item['id'] in items:raise ValueError('CKAN_DUPLICATE_OR_MISSING_NATIVE_ID')
            items[item['id']]=item
        if start_offset+len(items)>count:raise ValueError('CKAN_COUNT_EXCEEDED')
        if start_offset+len(items)==count:break
        if len(batch)<rows:raise ValueError('CKAN_TRUNCATED_PAGE')
    return dict(results=list(items.values()),inventory=dict(query=query,matched_count=count,
        retrieved_count=len(items),pages=pages,rows=rows,max_pages=max_pages,complete=start_offset+len(items)==count,
        **(dict(start_offset=start_offset,next_start=start_offset+len(items) if start_offset+len(items)<count else None) if start_offset else {})))


def wfs(source, archive=None, fetch=None):
    """Count-bound, native-ID checked WFS paging; never accept a partial inventory."""
    import xml.etree.ElementTree as ET
    base={'service':'WFS','version':source.get('wfs_version','2.0.0'),
          'request':'GetFeature','typeName':source['type_name'],
          'typeNames':source['type_name'],'srsName':'EPSG:4326'}
    hit,_=(fetch or request)(source['url'],{**base,'resultType':'hits'})
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
        raw,_=(fetch or request)(source['url'],params)
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
    """Historical refresh preserved for older callers, outside the Census entry."""
    root = Path(root)
    manifest_path = root / 'data/manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    outcomes = []
    for source in registry['sources']:
        if source['kind'] in STATIC_ARCHIVE_KINDS:
            outcomes.append({'key': source['key'], 'status': 'MANAGED_BY_CENSUS_ACQUISITION'})
            continue
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
            if source['kind']=='minedex_resource_batch':
                raw,headers=minedex_resource_batch(source['url'],source['product_alias'],archive)
            elif source['kind']=='government_wfs':
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
            suffix = '.zip' if source['kind']=='minedex_resource_batch' else '.pdf' if source['kind'] == 'pdf' else '.xlsx' if source['kind'] == 'xlsx_census' else '.csv' if source['kind']=='government_csv' else '.html' if source['kind']=='html' else '.json'
            path = root / 'data/snapshots' / (sha + suffix)
            path.parent.mkdir(parents=True, exist_ok=True)
            if not path.exists():path.write_bytes(raw)
            if filehash(path)!=sha:raise ValueError('IMMUTABLE_SNAPSHOT_CONTENT_MISMATCH')
            now = datetime.now(timezone.utc).isoformat()
            entry = {**source, 'sha256': sha, 'path': path.relative_to(root).as_posix(),
                     'acquired_at': now, 'available_date': now[:10],
                     'etag':headers.get('ETag'),'last_modified':headers.get('Last-Modified')}
            entry.update(redaction)
            if source['kind']=='minedex_resource_batch':
                entry.update(source_update=headers.get('X-DASC-Updated'),resolved_download_url=headers.get('X-DASC-Download'))
                entry['publication_date']=datetime.strptime(headers['X-DASC-Updated'],'%d/%m/%Y').date().isoformat()
                entry['request_count']=int(headers['X-DASC-Requests']);entry['elapsed_seconds']=float(headers['X-DASC-Seconds'])
            if pages:entry['original_responses']=pages
            if changes:entry['native_changes']=changes
            manifest['snapshots'].append(entry)
            manifest=append_snapshots(manifest_path,manifest['snapshots'])
            outcomes.append({'key': source['key'], 'status': 'ADDED', 'sha256': sha})
        except Exception as exc:
            outcomes.append({'key': source['key'], 'status': 'UNAVAILABLE', 'reason': str(exc),
                             **failure_details(exc),
                             **({'original_responses':pages} if pages else {})})
    append_snapshots(manifest_path,manifest['snapshots'])
    return outcomes

def minedex_resource_batch(url, product_alias, archive=None, fetch=None):
    """Discover CSV ZIP through the official DASC hierarchy, not MapServer sites.

    The original directory responses precede the immutable ZIP. Native product
    alias and advertised format determine the download, never a guessed file ID.
    """
    import re,io,zipfile
    transport=fetch or request;request_count=0;started=time.monotonic()
    def fetch(*args,**kwargs):
        nonlocal request_count
        request_count+=1
        return transport(*args,**kwargs)
    raw,_=fetch(url)
    if archive:archive(raw)
    match=re.search(rb'var tabs\s*=\s*(\[.*?\]);',raw,re.S)
    if not match:raise ValueError('DASC_TAB_DIRECTORY_ABSENT')
    base=urllib.parse.urljoin(url,'/')
    products=[]
    def walk(nodes):
        for n in nodes:
            if n.get('NodeType')=='File' and n.get('FileFormat')=='CSV':products.append(n)
            walk(n.get('Children') or [])
    # Fixed budget for advertised directory roots, not open-ended crawling.
    for tab in json.loads(match[1])[:4]:
        body,_=fetch(urllib.parse.urljoin(base,'Home/GetHierarchy'),dict(mapsheetNumber='',productAlias=product_alias,parentFolderId=tab['Id']))
        if archive:archive(body)
        walk(json.loads(body))
    unique={p['Path']:p for p in products}
    if len(unique)!=1:raise ValueError('DASC_CSV_PRODUCT_AMBIGUOUS_OR_MISSING')
    product=next(iter(unique.values()));download=urllib.parse.urljoin(base,product['Path'])
    if urllib.parse.urlsplit(download).netloc!=urllib.parse.urlsplit(url).netloc:raise ValueError('DASC_EXTERNAL_DOWNLOAD_NOT_ALLOWED')
    body,headers=fetch(download)
    if archive:archive(body)
    with zipfile.ZipFile(io.BytesIO(body)) as z:
        names=[n for n in z.namelist() if n.lower().endswith('.csv')]
        if len(names)!=1 or z.getinfo(names[0]).file_size>30_000_000:raise ValueError('DASC_RESOURCE_CSV_MEMBER_INVALID')
        header=z.read(names[0]).decode('utf-8-sig').splitlines()[0]
        if not {'PROJ_CODE','EST_COM','RES_QTY','RES_CON','LOC_SITE'}.issubset(header.split(',')):raise ValueError('DASC_NOT_RESOURCE_ESTIMATE_PRODUCT')
    return body,dict(headers,**{'X-DASC-Updated':product['UpdatedDate'],'X-DASC-Download':download,'X-DASC-Requests':str(request_count),'X-DASC-Seconds':str(time.monotonic()-started)})


def evidenced_snapshot(root, source, cutoff):
    path = Path(root) / 'work/pre_cutoff_evidence_verified.json'
    if not path.is_file():
        return source
    try:
        proof = json.loads(path.read_text(encoding='utf8'))
        record = proof['sources'].get(source['key'], {})
        evidence = record.get('declaration', {})
        if (record.get('valid') is not True or
                proof['sources_sha256'] != filehash(Path(root) / 'config/sources.json') or
                evidence.get('recorded_sha256') != source['sha256'] or
                evidence.get('evidence_date', '9999') > cutoff):
            return source
        return dict(source, available_date=min(source['available_date'], evidence['evidence_date']),
                    pre_cutoff_evidence=evidence)
    except (OSError, ValueError, KeyError, TypeError):
        return source


def select_snapshots(root, cutoff, keys=None, acquired_through=None):
    manifest = json.loads((Path(root) / 'data/manifest.json').read_text(encoding='utf-8'))
    selected = {}
    def visible(s):
        s.update(evidenced_snapshot(root, s, cutoff))
        if (s.get('publication_date') or '')>cutoff:return False
        if s['available_date']<=cutoff:return True
        # Retrospective acquisition is explicit and limited to dated documents
        # and their extraction artifacts; never backdate live GIS/government rows,
        # except declared, verified pre_cutoff_evidence for the same source bytes.
        if not acquired_through or s['available_date']>acquired_through:return False
        if s['kind']=='discovery_receipt':return True  # Acquisition diagnostics, never observations.
        if s['kind']=='source_documentation':return True  # Access diagnostics, not dated scientific evidence.
        if s['kind']=='minedex_resource_batch':
            # An explicitly dated published ZIP is different from querying a
            # current live feature layer; acquisition time remains unchanged.
            try:
                catalog_date=datetime.strptime(s['source_update'],'%d/%m/%Y').date().isoformat()
                http_date=parsedate_to_datetime(s['last_modified']).date().isoformat()
            except (KeyError,TypeError,ValueError):return False
            return bool(s.get('publication_date')==catalog_date and catalog_date<=cutoff and http_date<=cutoff)
        if s['kind'] not in ('pdf','html','document_extraction','pdf_page_extraction'):return False
        if s['kind'] in ('pdf','html'):return bool(s.get('publication_date'))
        return any(o['sha256']==s.get('source_sha256') and o.get('publication_date') and o['publication_date']<=cutoff for o in manifest['snapshots'])
    for s in manifest['snapshots']:
        if keys and s['key'] not in keys:
            continue
        # Only declared, verified pre_cutoff_evidence may establish an earlier date.
        if not visible(s):
            continue
        if s['key'] not in selected or s['acquired_at'] > selected[s['key']]['acquired_at']:
            selected[s['key']] = s
    # A later safe capture must not erase an earlier declared redaction link.
    # All visible derivative bytes are still checksum-verified below.
    private={s['unpublished_original_sha256'] for s in manifest['snapshots']
             if (not keys or s['key'] in keys) and visible(s) and s.get('publication_derivative')}
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

gov={'services.ga.gov.au','public-services.slip.wa.gov.au','spatial-gis.information.qld.gov.au','data.stategrowth.tas.gov.au','public-gs.geoscience.nsw.gov.au','opendata.maps.vic.gov.au','geology.data.nt.gov.au','services.sarig.sa.gov.au','wamex.dmp.wa.gov.au','dasc.dmirs.wa.gov.au','geoscience.data.qld.gov.au','geoscience.nt.gov.au','strike.nt.gov.au','majorprojects.planningportal.nsw.gov.au'}
delivery={'warsydprdstagsdspub.blob.core.windows.net','gsq-prod-ckan-horizon-public.s3.ap-southeast-2.amazonaws.com'}
groups={
    'government-api':gov,
    'government-resource':delivery|{'data.gov.au','www.wa.gov.au','international.austrade.gov.au','www.industry.gov.au','dem-sdp.s3-ap-southeast-2.amazonaws.com'},
    'asx':{'announcements.asx.com.au','www.asx.com.au'},
    'issuer-ir':{'investorpa.com','orbitresources.au','www.itechminerals.com.au','asm-au.com','www.arultd.com','www.astronlimited.com.au','victorymetalsaustralia.com','www.devexresources.com.au','www.gippslandcriticalminerals.com','www.iluka.com','wcsecure.weblink.com.au','hermes-cdn.investorhub.com','staff-web.automicgroup.com.au','assets.birdsoftware.io','assets.ctfassets.net'},
    'aggregator':{'api.investi.com.au','company-announcements.afr.com','newswire.iguana2.com','www.marketindex.com.au','cdn-api.markitdigital.com','cdn.financialreports.eu','data-api.marketindex.com.au','investornews.com','www.annualreports.com','www.londonstockexchange.com'},
    'legacy-committed':{'raw.githubusercontent.com'}}
STRICT_HOSTS={host:group for group,items in groups.items() for host in items}


class InvalidNetworkRun(ValueError):
    """Acquisition diagnostics exist, but this run cannot supply research results."""


def strict_dns_preflight(registry, reports=()):
    """Resolve every configured source/report host before any HTTP request."""
    hosts={urllib.parse.urlsplit(s['url']).hostname for s in [*registry['sources'],*reports]
           if s.get('kind') != WA_TITLE_KIND}
    rows=[]
    for host in sorted(h for h in hosts if h):
        try:
            addresses=socket.getaddrinfo(host,443,type=socket.SOCK_STREAM)
            if not addresses:raise OSError('DNS_EMPTY_ADDRESS_LIST')
            rows.append(dict(host=host,status='DNS_OK',error=''))
        except OSError as exc:
            rows.append(dict(host=host,status='NETWORK_ERROR',error=str(exc)))
    return rows


def strict_failure_status(exc):
    """HTTP denial is source availability; transport failure invalidates a run."""
    if isinstance(exc,urllib.error.HTTPError):return 'UNAVAILABLE'
    if isinstance(exc,(urllib.error.URLError,ConnectionError,TimeoutError,socket.gaierror)):
        return 'NETWORK_ERROR'
    if str(exc).startswith('HOST_STOPPED:'):return 'HOST_STOPPED'
    if str(exc)=='CAPTCHA_OR_LOGIN':return 'HOST_STOPPED'
    return 'UNAVAILABLE'


def strict_network_report(work, outcomes, dns_rows):
    """Persist receipts even when no database or valid research run is created."""
    from .tabular import write_csv
    work=Path(work);work.mkdir(parents=True,exist_ok=True)
    failed={r['key'] for r in outcomes if r.get('network_error') or r['status']=='NETWORK_ERROR'}
    keys={r['key'] for r in outcomes if r['status'] != 'NEEDS_VERIFIED_STATIC_ARCHIVE'}
    dns_failed=any(r['status']!='DNS_OK' for r in dns_rows)
    invalid=dns_failed or bool(keys and len(failed)/len(keys)>.05)
    report=dict(status='RUN_INVALID_NETWORK' if invalid else 'NETWORK_VALID' if keys else 'DNS_PREFLIGHT_PASSED',
                dns_preflight=dns_rows,network_error_sources=len(failed),sources=len(keys),
                network_error_fraction=len(failed)/len(keys) if keys else None,
                maximum_network_error_fraction=.05,valid_for_delivery=bool(keys) and not invalid)
    (work/'network_status.json').write_text(canonical(report)+'\n',encoding='utf8')
    write_csv(work/'dns_preflight.csv',dns_rows,['host','status','error'])
    if outcomes:
        write_csv(work/'acquisition_report.csv',outcomes,sorted({k for r in outcomes for k in r}))
    return report


def strict_asx_probe(registry, transport):
    """Three registered documents per ASX host, sharing the build's stop state."""
    import hashlib
    rows=[]
    for host in ('www.asx.com.au','announcements.asx.com.au'):
        sources=[s for s in registry['sources'] if s['kind']=='pdf' and urllib.parse.urlsplit(s['url']).hostname==host][:3]
        if len(sources)!=3:raise ValueError('ASX_PROBE_REQUIRES_THREE_REGISTERED_DOCUMENTS:'+host)
        for source in sources:
            start=len(transport.attempts);transport.http.pop(host,None)
            row=dict(key=source['key'],url=source['url'],host=host,status='',http_status=None,reason='',sha256='')
            try:
                raw,headers=transport(source['url'],max_bytes=source.get('max_bytes',30_000_000))
                if not raw.startswith(b'%PDF'):raise ValueError('NOT_PDF')
                transport.probed[source['key']]=(raw,headers,transport.http.get(host),transport.attempts[start:])
                row.update(status='FETCHED',sha256=hashlib.sha256(raw).hexdigest())
            except Exception as exc:
                if host=='www.asx.com.au' and str(exc)=='NOT_PDF':transport.stopped[host]='NOT_PDF'
                row.update(status=strict_failure_status(exc),reason=str(exc))
                transport.probe_failures[source['key']]=(exc,transport.http.get(host),transport.attempts[start:])
            row.update(http_status=transport.http.get(host),http_attempts=canonical(transport.attempts[start:]))
            rows.append(row)
    return rows


class StrictTransport:
    """One build-scoped transport; no legacy request semantics are changed."""
    def __init__(self, hosts):
        self.hosts=hosts;self.last={};self.stopped={};self.http={};self.attempts=[]
        self.probed={};self.probe_failures={}
        owner=self
        class Redirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, newurl):
                old=urllib.parse.urlsplit(req.full_url).hostname;new=urllib.parse.urlsplit(newurl).hostname
                owner.http[old]=code;owner.attempts.append(dict(host=old,http_status=code))
                if hasattr(owner,'before_request') and (old=='www.asx.com.au' or owner.hosts.get(old)=='alternate'):owner.attempts[-1]['url']=req.full_url
                if urllib.parse.urlsplit(newurl).scheme!='https' or new not in owner.hosts or (old!=new and owner.hosts.get(old)!=owner.hosts.get(new)):
                    raise ValueError('REDIRECT_DESTINATION_NOT_APPROVED')
                if hasattr(owner,'before_request'):owner.before_request(newurl)
                owner.guard(new)
                return super().redirect_request(req,fp,code,msg,headers,newurl)
        self.opener=urllib.request.build_opener(Redirect())

    def guard(self,host):
        if host in self.stopped:raise ValueError('HOST_STOPPED:'+self.stopped[host])
        delay=3-(time.monotonic()-self.last.get(host,-1e10))
        if delay>0:time.sleep(delay)
        self.last[host]=time.monotonic()

    def __call__(self,url,params=None,headers=None,timeout=25,method='GET',max_bytes=None):
        host=urllib.parse.urlsplit(url).hostname
        if urllib.parse.urlsplit(url).scheme!='https' or host not in self.hosts:raise ValueError('UNAPPROVED_HOST')
        data=None
        if params and method=='POST':data=urllib.parse.urlencode(params).encode()
        elif params:url+=('&' if '?' in url else '?')+urllib.parse.urlencode(params)
        req=urllib.request.Request(url,data=data,method=method,headers={'User-Agent':'AU_REE_V2/0.1 public research'})
        for attempt in range(2):
            self.http.pop(host,None)
            if hasattr(self,'before_request'):self.before_request(url)
            self.guard(host)
            try:
                with self.opener.open(req,timeout=timeout) as response:
                    final=urllib.parse.urlsplit(response.geturl()).hostname
                    self.resolved_url=response.geturl()
                    self.http[host]=response.status;self.attempts.append(dict(host=host,http_status=response.status))
                    # Scope URL audit to www/alternates; bulk government pages retain their bounded receipt format.
                    if hasattr(self,'before_request') and (host=='www.asx.com.au' or self.hosts.get(host)=='alternate'):self.attempts[-1]['url']=req.full_url
                    raw=response.read(max_bytes+1) if max_bytes is not None else response.read()
                    if max_bytes is not None and len(raw)>max_bytes:raise ValueError('DOCUMENT_BYTE_BUDGET_EXCEEDED')
                    sample=raw[:200000].lower()
                    if not raw.startswith((b'%PDF',b'PK')) and (any(token in sample for token in (b'captcha',b'type="password"',b"type='password'",b'please log in',b'please sign in')) or re.search(br'<form[^>]*(?:log.?in|sign.?in)|<(?:title|h1)[^>]*>[^<]*(?:log.?in|sign.?in)',sample)):
                        self.stopped[host]=self.stopped[final]='CAPTCHA_OR_LOGIN'
                        raise ValueError('CAPTCHA_OR_LOGIN')
                    return raw,dict(response.headers)
            except urllib.error.HTTPError as exc:
                self.http[host]=exc.code;self.attempts.append(dict(host=host,http_status=exc.code));exc.request_attempts=attempt+1
                if hasattr(self,'before_request') and (host=='www.asx.com.au' or self.hosts.get(host)=='alternate'):self.attempts[-1]['url']=req.full_url
                if exc.code in (403,404,410) and urllib.parse.urlsplit(req.full_url).path=='/robots.txt':
                    return b'',{}
                if 400<=exc.code<500 and exc.code!=404:
                    self.stopped[host]=str(exc.code)
                    self.stopped[urllib.parse.urlsplit(exc.url).hostname]=str(exc.code)
                    raise
                if not 500<=exc.code<600 or attempt:raise
            except (urllib.error.URLError,ConnectionError,TimeoutError,socket.gaierror) as exc:
                self.attempts.append(dict(host=host,http_status=None,error='TIMEOUT' if isinstance(getattr(exc,'reason',exc),(TimeoutError,socket.timeout)) else 'NETWORK_ERROR'))
                exc.strict_network_error=True
                if not isinstance(getattr(exc,'reason',exc),(TimeoutError,socket.timeout)) or attempt:raise


class SameSHAAlternates:
    """Bounded discovery of immutable copies; no change to declared evidence."""
    def __init__(self, root, primary):
        path = Path(root) / 'config/evidence_policy.json'
        self.policy = json.loads(path.read_text(encoding='utf8')).get('same_sha_fallback', {}) if path.exists() else {}
        self.primary = primary
        self.reports, self.patch, self.robots, self.indexes = [], [], {}, {}
        self.used = 0
        self.transport = StrictTransport({})
        for name in ('last', 'stopped', 'http', 'attempts'):
            setattr(self.transport, name, getattr(primary, name))
        self.transport.before_request = lambda url: self.check(url, self.transport, True)
        if self.policy.get('enabled'):
            if self.policy.get('search_api',{}).get('enabled'):
                raise ValueError('SEARCH_API_PROVIDER_NOT_IMPLEMENTED')
            for key, limit in [('max_candidates_per_source', 8), ('max_fallback_requests_per_build', 400)]:
                if not 0 < self.policy[key] <= limit:
                    raise ValueError('INVALID_FALLBACK_BUDGET')
            primary.before_request = lambda url: self.check(url, primary, False)
        primary.same_sha = self

    def check(self, url, transport, counted):
        from urllib.robotparser import RobotFileParser
        from .security import sensitive_reference
        if sensitive_reference(url):raise ValueError('SENSITIVE_ALTERNATE_URL')
        parsed = urllib.parse.urlsplit(url)
        if parsed.hostname in transport.stopped:
            raise ValueError('HOST_STOPPED:' + transport.stopped[parsed.hostname])
        if counted:
            if self.used >= self.policy['max_fallback_requests_per_build']:
                raise ValueError('FALLBACK_REQUEST_BUDGET_EXHAUSTED')
            self.used += 1
        if parsed.path == '/robots.txt':
            return
        origin = urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, '', '', ''))
        if origin not in self.robots:
            self.robots[origin] = None
            try:
                raw, _ = transport(origin + '/robots.txt', max_bytes=100000)
            finally:
                transport.http.pop(parsed.hostname,None)
            if raw.lstrip().startswith(b'<') or (raw.strip() and b'user-agent:' not in raw.lower()):
                raise ValueError('ROBOTS_NOT_TEXT')
            parser = RobotFileParser()
            parser.parse(raw.decode('utf-8-sig').splitlines())
            self.robots[origin] = parser
        if not self.robots[origin] or not self.robots[origin].can_fetch('AU_REE_V2/0.1 public research', url):
            raise ValueError('ROBOTS_DISALLOWED')

    def find(self, source, receipt, expected, cache):
        import hashlib, re
        from .source_discovery import candidates
        trigger = receipt['stop_reason'].split(':')[0]
        if receipt['http_status'] == 404:
            trigger = 'HTTP_404'
        elif trigger == 'CAPTCHA_OR_LOGIN':
            trigger = 'LOGIN_OR_CAPTCHA'
        elif receipt['status'] == 'HOST_STOPPED':
            trigger = 'HOST_STOPPED'
        elif urllib.parse.urlsplit(source['url']).hostname in self.primary.stopped:
            trigger = 'HOST_STOPPED'
        if not self.policy.get('enabled') or source['kind'] != 'pdf' or len(expected) != 1 or trigger not in self.policy['trigger_statuses']:
            return None
        if source.get('alternate_policy', 'SAME_SHA_ONLY') != 'SAME_SHA_ONLY':
            return None
        report = dict(key=source['key'],primary_status=receipt['status'],primary_reason=receipt['stop_reason'],candidate_count=0,
                      found_url='',host_type='',sha_match=False,stop_reason='',attempts=[])
        self.reports.append(report)
        index = self.policy['issuer_ir_indexes'].get(source.get('issuer', {}).get('asx_code'))
        issuer = urllib.parse.urlsplit(index).hostname if index else None
        issuer_hosts = set(self.policy.get('issuer_ir_hosts',{}).get(source.get('issuer',{}).get('asx_code'),[])) | ({issuer} if issuer else set())
        hosts = set(self.policy['approved_hosts']) | issuer_hosts
        self.transport.hosts = {h: 'alternate' for h in hosts if h != 'www.asx.com.au'}
        urls = list(dict.fromkeys(source.get('alternate_urls', [])))
        found = None
        for phase in ('declared', 'index'):
            if report['candidate_count'] >= self.policy['max_candidates_per_source']:
                report['stop_reason'] = 'CANDIDATE_BUDGET_EXHAUSTED'
                break
            if phase == 'index' and index:
                try:
                    if index not in self.indexes:
                        self.indexes[index] = None
                        raw, _ = self.transport(index, max_bytes=2000000)
                        if re.search(br'<form[^>]*(?:login|consent|terms)|terms\s+(?:and\s+conditions|of\s+use)|<(?:title|h1)[^>]*>[^<]*(?:consent|log.?in|sign.?in)', raw, re.I):
                            self.transport.stopped[issuer] = 'PROTECTED_INDEX_NOT_PARSED'
                            raise ValueError('PROTECTED_INDEX_NOT_PARSED')
                        seed = dict(url=index,key=source['key'],allowed_hosts=hosts,pattern=r'\.pdf(?:\b|\?)|/pdf/|/file/')
                        self.indexes[index] = candidates(raw, seed)
                    if self.indexes[index] is None:
                        raise ValueError('INDEX_PREVIOUSLY_UNAVAILABLE')
                    for candidate in self.indexes[index]:
                        date = candidate['publication_date']
                        dates = re.findall(r'\b\d{2}/\d{2}/20\d{2}\b',candidate['title'])
                        if not date and len(dates)==1:
                            date = datetime.strptime(dates[0],'%d/%m/%Y').date().isoformat()
                        tokens = source.get('title_tokens', [])
                        dated = bool(date and source.get('publication_date') and abs((datetime.fromisoformat(date)-datetime.fromisoformat(source['publication_date'])).days) <= 7)
                        if dated or any(t.casefold() in (candidate['title']+' '+candidate['url']).casefold() for t in tokens):
                            urls.append(candidate['url'])
                except Exception as exc:
                    report['attempts'].append(dict(url=index,stage='INDEX',reason=str(exc)))
                    receipt['network_error'] = receipt.get('network_error',False) or strict_failure_status(exc) == 'NETWORK_ERROR'
            for url in dict.fromkeys(urls):
                if report['candidate_count'] >= self.policy['max_candidates_per_source']:
                    report['stop_reason'] = 'CANDIDATE_BUDGET_EXHAUSTED'
                    break
                if any(a.get('url') == url and a.get('stage') == 'PDF' for a in report['attempts']):
                    continue
                report['candidate_count'] += 1
                attempt = dict(url=url,stage='PDF',actual_sha256='',reason='')
                report['attempts'].append(attempt)
                try:
                    raw, _ = self.transport(url, max_bytes=30000000)
                    actual = hashlib.sha256(raw).hexdigest()
                    attempt['actual_sha256'] = actual
                    if actual not in expected:
                        attempt['reason'] = 'ALTERNATE_SHA_MISMATCH'
                    elif not raw.startswith(b'%PDF'):
                        attempt['reason'] = 'NOT_PDF'
                    else:
                        found = raw
                        report.update(found_url=self.transport.resolved_url,sha_match=True,stop_reason='')
                        break
                except Exception as exc:
                    attempt['reason'] = str(exc)
                    receipt['network_error'] = receipt.get('network_error',False) or strict_failure_status(exc) == 'NETWORK_ERROR'
            urls = []
            if found is not None:
                break
        if found is None and not report['stop_reason']:
            reason = report['attempts'][-1]['reason'] if report['attempts'] else ''
            report['stop_reason'] = reason or ('NO_ELIGIBLE_INDEX_PDF_LINK' if index else 'NO_REGISTERED_IR_INDEX_OR_CANDIDATE')
        receipt['alternate_mismatches'] = canonical([dict(a,key=source['key']) for a in report['attempts'] if a['reason']=='ALTERNATE_SHA_MISMATCH'])
        if found is None:
            return None
        host = urllib.parse.urlsplit(report['found_url']).hostname
        report['host_type'] = 'ASX_DIRECT_PDF' if host == 'announcements.asx.com.au' else 'ISSUER_IR' if host in issuer_hosts else 'APPROVED_THIRD_PARTY'
        sha = next(iter(expected))
        path = cache / (sha + '.pdf')
        path.write_bytes(found)
        receipt.update(status='ALTERNATE_SAME_SHA',sha_match=True,actual_sha256=sha,alternate_url=report['found_url'],alternate_host_type=report['host_type'])
        self.patch.append(dict(key=source['key'],source_sha256=sha,alternate_urls=list(dict.fromkeys([*source.get('alternate_urls',[]),report['found_url']]))))
        now = datetime.now(timezone.utc).isoformat()
        return dict(source,url=report['found_url'],primary_url=source['url'],sha256=sha,path=str(path),available_date=now[:10],acquired_at=now)

    def save(self, work):
        from .tabular import write_csv
        rows = [dict(r,attempts=canonical(r['attempts'])) for r in self.reports]
        columns = ['key','primary_status','primary_reason','candidate_count','found_url','host_type','sha_match','stop_reason','attempts']
        write_csv(Path(work)/'fallback_report.csv', rows, columns)
        proposed = dict(requires_researcher_approval=True,request_slots_used=self.used,changes=self.patch)
        (Path(work)/'proposed_sources_patch.json').write_text(canonical(proposed)+'\n',encoding='utf8')


def declared_json_hash(raw, source):
    """Explicit JSON policy; raw snapshot identity remains the byte SHA256."""
    import hashlib
    policy = source['hash_policy']
    if policy != 'JSON_DROP_TOP_LEVEL_KEYS_V1':
        raise ValueError('UNKNOWN_SOURCE_HASH_POLICY')
    keys = source.get('hash_drop_keys')
    if not isinstance(keys, list) or not keys:
        raise ValueError('INVALID_HASH_DROP_KEYS')
    if any(not isinstance(key, str) or not key for key in keys):
        raise ValueError('INVALID_HASH_DROP_KEYS')
    if len(set(keys)) != len(keys):
        raise ValueError('DUPLICATE_HASH_DROP_KEYS')
    try:
        document = json.loads(raw.decode('utf-8'))
    except (UnicodeDecodeError, ValueError) as exc:
        raise ValueError('HASH_POLICY_INVALID_JSON') from exc
    if not isinstance(document, dict):
        raise ValueError('HASH_POLICY_TOP_LEVEL_OBJECT_REQUIRED')
    if any(key not in document for key in keys):
        raise ValueError('HASH_POLICY_TOP_LEVEL_KEY_MISSING')
    for key in keys:
        del document[key]
    encoded = json.dumps(
        document, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False
    ).encode('utf-8')
    content_sha = hashlib.sha256(encoded).hexdigest()
    metadata = {
        'hash_policy': policy,
        'hash_drop_keys': keys,
        'content_sha256': content_sha,
        'raw_sha256': hashlib.sha256(raw).hexdigest(),
    }
    return content_sha, metadata


def declared_source_hashes(registry, claims):
    declared={}
    def visit(value):
        if isinstance(value,dict):
            if value.get('source_key') and value.get('source_sha256'):declared.setdefault(value['source_key'],set()).add(value['source_sha256'])
            for v in value.values():visit(v)
        elif isinstance(value,list):
            for v in value:visit(v)
    visit(claims)
    # Exact URL aliases share reviewed bindings; never infer a derivative parent.
    by_url={}
    for source in registry['sources']:
        if source['kind'] in ('pdf','html'):
            bindings=set(declared.get(source['key'],set()))
            if source.get('source_sha256'):bindings.add(source['source_sha256'])
            by_url.setdefault(source['url'],set()).update(bindings)
    return declared,by_url


def official_reports(registry, tasks, fetch, save, originals=()):
    """Official metadata -> candidate documents, within the existing manifest.

    Report IDs are source identities, never Project IDs. Name/company matches
    remain candidate relations; no entity mutation or resource admission here.
    """
    from .security import public_export
    reports=[];outcomes=[];seeds=[];documents=[]
    for source in registry.get('official_reports',[]):
        key=source['key'];url=source['url'];page_shas=[]
        def archive(raw):
            sha=save(raw,dict(key=key+'_response_'+hashlib.sha256(raw).hexdigest()[:16],
                kind='discovery_receipt',url=url,metadata_only=True),'.json')
            page_shas.append(sha)
        try:
            if source['protocol']=='arcgis':
                where=official_query(source,tasks)
                if where is None:
                    outcomes.append(dict(seed_key=key,url=url,status='NO_APPLICABLE_CANDIDATE_TASK',query_complete=False));continue
                contract=hashlib.sha256((url+'|'+where).encode()).hexdigest()
                cursor=registry.get('official_cursors',{}).get(contract,0) if source.get('dynamic_candidates') else None
                data=arcgis(url,where,archive=archive,fetch=fetch,max_records=source.get('max_records',30),start_after=cursor)
                if source.get('dynamic_candidates'):data['inventory'].update(query_contract=contract,
                    termination='SOURCE_EXHAUSTED' if data['inventory']['complete'] else 'RECORD_BUDGET_EXHAUSTED_RESUMABLE')
                records=[dict(native_id='WAMEX:A'+str(f['attributes']['anumber']),
                    title=f['attributes'].get('title'),attributes=f['attributes'],geometry=f.get('geometry'),
                    spatial_reference=data['spatialReference'],
                    detail_url=f['attributes'].get('dpxe_rep'),report_year=f['attributes'].get('report_year'),
                    released_date=(datetime.fromtimestamp(f['attributes']['date_released']/1000,timezone.utc).date().isoformat()
                                   if f['attributes'].get('date_released') else None),
                    resources=[]) for f in data['features']]
            elif source['protocol']=='ckan':
                query=source['query']
                if source.get('dynamic_candidates'):
                    aliases=sorted({a for task in tasks if task.get('state')=='QLD' for a in task['aliases'] if len(a)>=4})
                    if not aliases:
                        outcomes.append(dict(seed_key=key,url=url,status='NO_APPLICABLE_CANDIDATE_TASK',query_complete=False));continue
                    query='('+' OR '.join('"'+a.replace('"','').replace('\\','')+'"' for a in aliases)+') AND ('+query+')'
                contract=hashlib.sha256((url+'|'+query).encode()).hexdigest()
                start=registry.get('official_cursors',{}).get(contract,0) if source.get('resume') else 0
                data=ckan(url,query,source.get('rows',10),source.get('max_pages',2),fetch,archive,start_offset=start)
                if source.get('resume'):data['inventory'].update(query_contract=contract,start_offset=start,
                    next_start=start+len(data['results']) if not data['inventory']['complete'] else None,
                    termination='SOURCE_EXHAUSTED' if data['inventory']['complete'] else 'PAGE_BUDGET_EXHAUSTED_RESUMABLE')
                for item in data['results'][:source.get('max_package_show',2)]:
                    try:
                        raw,_=fetch(url.rstrip('/')+'/package_show',{'id':item['id']});archive(raw)
                        shown=json.loads(raw)
                        if shown.get('success') is not True or shown['result'].get('id')!=item['id']:
                            raise ValueError('CKAN_PACKAGE_IDENTITY_MISMATCH')
                        item.update(shown['result'])
                    except Exception as exc:
                        outcomes.append(dict(seed_key=key+'_package_'+item['id'],url=url,status='UNAVAILABLE',metadata_only=True,**failure_details(exc)))
                records=[dict(native_id='GSQ:'+r['name'],package_id=r['id'],title=r.get('title'),
                    attributes=r,detail_url=urljoin(url,'/dataset/'+r['name']),
                    released_date=r.get('open_file_date'),resources=r.get('resources',[])) for r in data['results']]
            else:raise ValueError('UNSUPPORTED_OFFICIAL_REPORT_PROTOCOL')
            for record in records:
                record.update(source_key=key,metadata_sha256=page_shas,identity_status='OFFICIAL_REPORT_NOT_PROJECT',
                    relation_status='CANDIDATE_ONLY_NO_ENTITY_EQUIVALENCE')
                text=json.dumps(record.get('attributes',{}),ensure_ascii=False).casefold()
                record['project_candidates']=[]
                for task in tasks:
                    aliases=[a for a in task['aliases'] if len(a)>=5 and a.casefold() in text]
                    company=task.get('company');company_match=bool(company and company.casefold() in text)
                    if aliases:record['project_candidates'].append(dict(project_id=task['project_id'],
                        alias_matches=aliases,company_match=company_match,
                        decision='CANDIDATE_REQUIRES_INDEPENDENT_SCOPE_AND_IDENTITY_EVIDENCE'))
                record['document_candidates']=[]
                for resource in record['resources']:
                    if str(resource.get('format','')).upper()!='PDF':continue
                    docurl=(resource.get('url') or resource.get('download_url','')) if source.get('prefer_original_resource_url') else (resource.get('download_url') or resource.get('url',''))
                    rid=resource.get('id')
                    status='DISCOVERED_BUDGET_DEFERRED'
                    # Signed credentials stay out of receipts/manifest/logs.
                    if sensitive_reference(docurl):status='SIGNED_LINK_NOT_PUBLISHED_OR_FETCHED'
                    elif urlsplit(docurl).scheme!='https' or urlsplit(docurl).hostname not in source.get('document_hosts',[]):status='UNCONFIGURED_DOCUMENT_HOST'
                    size=resource.get('resource:size','')
                    match=re.fullmatch(r'([\d.]+)\s*(KB|MB|GB)',size,re.I)
                    estimated=float(match[1])*{'KB':1024,'MB':1024**2,'GB':1024**3}[match[2].upper()] if match else None
                    if estimated is not None and estimated>source.get('max_document_bytes',20000000):status='DOCUMENT_SIZE_BUDGET_DEFERRED'
                    item=dict(resource_id=rid,title=resource.get('name'),status=status,estimated_bytes=estimated)
                    if not sensitive_reference(docurl):item['url']=docurl
                    record['document_candidates'].append(item)
                    if status!='DISCOVERED_BUDGET_DEFERRED' or len(seeds)>=registry.get('max_official_documents',4):continue
                    seeds.append(dict(key=key+'_'+hashlib.sha256((record['native_id']+'|'+str(rid)).encode()).hexdigest()[:16],
                        url=docurl,allowed_hosts=source['document_hosts'],authority='OFFICIAL_PUBLIC_REPORT_DELIVERY',
                        report_native_id=record['native_id'],resource_native_id=rid,project_id=None,
                        max_document_bytes=source.get('max_document_bytes',20000000),
                        source_document_version=hashlib.sha256(json.dumps([resource.get(k) for k in ('id','metadata_modified','last_modified','hash','resource:size')]).encode()).hexdigest(),
                        publication_date=record.get('released_date'),metadata_sha256=page_shas))
                    item['status']='QUEUED_DOCUMENT_ACQUISITION'
                if not record['resources'] and record.get('detail_url'):
                    # WAMEX permanent details are public HTML. No assumed private
                    # download API, terms submission or signed-token persistence.
                    record['document_access']='DETAIL_PAGE_REQUIRES_PUBLIC_LINK_DISCOVERY'
                reports.append(public_export(record))
            outcomes.append(dict(seed_key=key,url=url,status='PARSED',sha256=page_shas[-1],
                metadata_only=True,inventory=data['inventory'],reports=len(records)))
        except Exception as exc:outcomes.append(dict(seed_key=key,url=url,status='UNAVAILABLE',**failure_details(exc)))
    # The public WAMEX UI's ReportDocuments_Read transport is a read-only POST.
    # Signed links are transient: public snapshots retain a declared sanitized
    # derivative and SHA of the ignored original, never the bearer URL.
    for report in sorted(reports,key=lambda r:(-int(bool(re.search(r'metallurg|mineralo|mineral process|recover',str(r.get('attributes',{})),re.I))),
                                              -(r.get('report_year') or 0),r['native_id'])):
        if report.get('resources') or not report.get('detail_url') or not report.get('project_candidates'):continue
        if sum(s.get('report_detail') is True for s in outcomes)>=registry.get('max_official_details',2):break
        key='wamex_'+report['native_id'].split(':')[-1];native=report['attributes']['anumber']
        endpoint='https://wamex.dmp.wa.gov.au/Wamex/Search/ReportDetails/ReportDocuments_Read'
        try:
            raw,_=fetch(endpoint,{'aNumber[0]':native,'page':1,'pageSize':20},method='POST')
            data=json.loads(raw)
            if data.get('Errors') or not isinstance(data.get('Total'),int) or not isinstance(data.get('Data'),list):raise ValueError('WAMEX_DOCUMENT_LIST_INVALID')
            if any(r.get('ANumber')!=native for r in data['Data']):raise ValueError('WAMEX_REPORT_IDENTITY_MISMATCH')
            sha=save(raw,dict(key=key+'_document_list',url=report['detail_url'],kind='discovery_receipt',metadata_only=True,omit_signed_urls=True),'.json')
            report['document_list_sha256']=sha;report['document_list_total']=data['Total']
            report['document_list_complete']=len(data['Data'])==data['Total']
            for resource in data['Data']:
                if str(resource.get('FileType','')).lower()!='.pdf':continue
                rid=str(resource['BLTId']);link=resource.get('Link','');size=resource.get('FileSize','')
                match=re.fullmatch(r'([\d.]+)\s*(KB|MB|GB)',size,re.I)
                estimated=float(match[1])*{'KB':1024,'MB':1024**2,'GB':1024**3}[match[2].upper()] if match else None
                item=dict(resource_id=rid,title=resource.get('FileName'),estimated_bytes=estimated,status='DISCOVERED_BUDGET_DEFERRED')
                report['document_candidates'].append(item)
                if re.search(r'logging.?codes|litholog.?codes',item['title'] or '',re.I):
                    item['status']='METHODOLOGY_APPENDIX_RETAINED_NOT_PRIORITY_TECHNICAL_REPORT';continue
                if estimated is None or estimated>registry.get('max_wamex_document_bytes',20000000):
                    item['status']='DOCUMENT_SIZE_UNKNOWN_OR_BUDGET_DEFERRED';continue
                if len(documents)>=registry.get('max_wamex_documents',2):continue
                if urlsplit(link).scheme!='https' or urlsplit(link).hostname!='warsydprdstagsdspub.blob.core.windows.net':
                    item['status']='UNCONFIGURED_DOCUMENT_HOST';continue
                identity=key+'_'+rid
                resource_version=hashlib.sha256(json.dumps([resource.get(k) for k in ('BLTId','FileName','FileSize','EditDate')]).encode()).hexdigest()
                cached=next((s for s in reversed(originals) if s.get('report_native_id')==report['native_id'] and s.get('resource_native_id')==rid and s.get('source_document_version')==resource_version),None)
                if cached:
                    item.update(status='REUSED_VERIFIED_ORIGINAL',document_sha256=cached['sha256'])
                    documents.append(dict(candidate_id=hashlib.sha256(identity.encode()).hexdigest(),source_key=cached['key'],seed_key=key,
                        url=report['detail_url'],document_sha256=cached['sha256'],status='REUSED_VERIFIED_ORIGINAL'))
                    continue
                try:
                    # A signed link is acquired only from the current public
                    # response; it is not copied into the manifest or receipt.
                    body,_=fetch(link,max_bytes=registry.get('max_wamex_document_bytes',20000000))
                    if not body.startswith(b'%PDF'):raise ValueError('NOT_PDF')
                    pdfsha=save(body,dict(key=identity,url=report['detail_url'],kind='pdf',
                        report_native_id=report['native_id'],resource_native_id=rid,original_filename=item['title'],
                        source_document_version=resource_version,
                        metadata_sha256=[sha],**({'publication_date':report['released_date']} if report.get('released_date') else {}),
                        date_role='OPEN_FILE_RELEASE_NOT_RESOURCE_EFFECTIVE_DATE',authority='OFFICIAL_WAMEX_REPORT'),'.pdf')
                    item.update(status='ORIGINAL_ACQUIRED',document_sha256=pdfsha)
                    documents.append(dict(candidate_id=hashlib.sha256(identity.encode()).hexdigest(),source_key=identity,seed_key=key,
                        url=report['detail_url'],title=item['title'],document_sha256=pdfsha,
                        report_native_id=report['native_id'],resource_native_id=rid,status='SNAPSHOT_REQUIRES_DATED_SCOPE_EXTRACTION'))
                except Exception as exc:
                    item.update(status='DOWNLOAD_UNAVAILABLE',**failure_details(exc))
                    documents.append(dict(candidate_id=hashlib.sha256(identity.encode()).hexdigest(),seed_key=key,
                        url=report['detail_url'],title=item['title'],status='DOWNLOAD_UNAVAILABLE',**failure_details(exc)))
            outcomes.append(dict(seed_key=key,url=report['detail_url'],status='PARSED',sha256=sha,report_detail=True))
        except Exception as exc:outcomes.append(dict(seed_key=key,url=report['detail_url'],status='UNAVAILABLE',report_detail=True,**failure_details(exc)))
    return reports,outcomes,seeds,documents


def strict_refresh(root, registry, work, claims, cutoff, transport=None, dns_rows=None):
    """Fresh work-only originals and bounded, policy-approved same-SHA copies."""
    import hashlib,subprocess,uuid
    root=Path(root).resolve();work=Path(work).resolve()
    policy,deferred=strict_search_plan(root)
    reports=policy.get('official_reports',[])
    dns_rows=strict_dns_preflight(registry,reports) if dns_rows is None else dns_rows
    if any(r['status']!='DNS_OK' for r in dns_rows):
        strict_network_report(work,[],dns_rows)
        raise InvalidNetworkRun('RUN_INVALID_NETWORK: DNS preflight failed; no HTTP requests or build started')
    work.mkdir(parents=True,exist_ok=True)
    cache=work/('strict-'+uuid.uuid4().hex[:16]);cache.mkdir()
    manifest=json.loads((root/'data/manifest.json').read_text(encoding='utf8'))['snapshots']
    declared,by_url=declared_source_hashes(registry,claims)
    transport=transport or StrictTransport(STRICT_HOSTS);outcomes=[];selected=[]
    alternate=getattr(transport,'same_sha',None) or SameSHAAlternates(root,transport)
    managed={'official_table_transcription','official_project_catalogue_transcription','historical_e1_candidates','legacy_screen_index','pdf_page_extraction'}
    def committed(s,expected):
        p=Path(s['path']);target=(root/p).resolve()
        if p.is_absolute() or not target.is_relative_to(root/'data/snapshots') or s['sha256'] not in expected:return False
        check=subprocess.run(['git','cat-file','blob','HEAD:'+p.as_posix()],cwd=root,capture_output=True)
        return check.returncode==0 and hashlib.sha256(check.stdout).hexdigest()==s['sha256'] and target.is_file() and filehash(target)==s['sha256']
    if (root/'config/discovery.json').exists():
        for report in deferred:
            outcomes.append(dict(key=report['key'],host=urllib.parse.urlsplit(report['url']).hostname,http_status=None,sha_match=None,status='NO_FIXED_QUERY_NOT_EXPANDED',stop_reason='No configured fixed WAMEX query'))
        def save_receipt(raw,meta,suffix):
            from .security import sensitive_reference
            if sensitive_reference(raw.decode('utf8',errors='ignore')):raw=b'REDACTED_SENSITIVE_RECEIPT'
            sha=hashlib.sha256(raw).hexdigest();(cache/(sha+suffix)).write_bytes(raw);return sha
        _,reports,seeds,_=official_reports(policy,[],transport,save_receipt)
        for report in reports:
            host=urllib.parse.urlsplit(report['url']).hostname
            attempts=[a for a in transport.attempts if a['host']==host]
            network=bool(report.get('network_error'))
            outcomes.append(dict(key=report['seed_key'],host=host,http_status=report.get('http_status',transport.http.get(host)),sha_match=None,status='NETWORK_ERROR' if network else report['status'],stop_reason=report.get('reason',''),network_error=network,http_attempts=canonical(attempts)))
        # Returned exact delivery URLs are receipts only, never unreviewed claims.
        for seed in seeds:
            host=urllib.parse.urlsplit(seed['url']).hostname
            try:
                raw,_=transport(seed['url'],max_bytes=seed.get('max_document_bytes'))
                if not raw.startswith(b'%PDF'):raise ValueError('NOT_PDF')
                save_receipt(raw,{},'.pdf');status='API_DOCUMENT_CACHED_NOT_ADOPTED';reason=''
            except Exception as exc:status=strict_failure_status(exc);reason=str(exc)
            outcomes.append(dict(key=seed['key'],host=host,http_status=transport.http.get(host),sha_match=None,status=status,stop_reason=reason))
    for source in registry['sources']:
        key=source['key'];host=urllib.parse.urlsplit(source['url']).hostname
        transport.http.pop(host,None);request_start=len(transport.attempts)
        old=[s for s in manifest if s['key']==key and (s.get('publication_date') or '')<=cutoff]
        expected=set(declared.get(key,set()))
        if source.get('source_sha256') and source['kind'] not in managed:expected.add(source['source_sha256'])
        if source['kind'] in ('pdf','html'):expected.update(by_url.get(source['url'],set()))
        if source['kind'] in managed and not expected and old:expected={max(old,key=lambda x:x['acquired_at'])['sha256']}
        row=dict(key=key,host=host,http_status=None,sha_match=None,status='UNAVAILABLE',stop_reason='',expected_sha256=';'.join(sorted(expected)))
        if source['kind'] == WA_TITLE_KIND:
            row.update(status='NEEDS_VERIFIED_STATIC_ARCHIVE',
                       stop_reason='Select the registered government ZIP through the static library or exact receipt replay')
            outcomes.append(row)
            continue
        if source.get('enabled') is False:
            row.update(status='SOURCE_NOT_ACQUIRED',stop_reason=source.get('disabled_reason','SOURCE_DISABLED'));outcomes.append(row);continue
        if source['url']=='https://www.gippslandcriticalminerals.com/project-overview/':
            row.update(status='SOURCE_NOT_ACQUIRED',stop_reason='INDEX_LANDING_DISABLED');outcomes.append(row);continue
        candidate_mismatch=False
        try:
            if len(expected)>1:raise ValueError('CONFLICTING_DECLARED_SOURCE_SHA')
            if host in transport.stopped:raise ValueError('HOST_STOPPED:'+transport.stopped[host])
            if source.get('committed_snapshot_sha256') and 'hash_policy' not in source:
                candidates=[s for s in old if committed(s,{source['committed_snapshot_sha256']})]
                if not candidates:raise ValueError('DECLARED_COMMITTED_SNAPSHOT_UNAVAILABLE')
                selected.append(evidenced_snapshot(
                    root, dict(max(candidates,key=lambda s:s['acquired_at']),**source), cutoff))
                row.update(status='COMMITTED_SNAPSHOT_SAME_SHA',sha_match=True);outcomes.append(row);continue
            if source['kind'] in managed:
                candidates=[s for s in old if committed(s,expected)]
                if not candidates:raise ValueError('DECLARED_COMMITTED_DERIVATIVE_UNAVAILABLE')
                selected.append(max(candidates,key=lambda s:s['acquired_at']));row.update(status='COMMITTED_MANAGED_SAME_SHA',sha_match=True)
                outcomes.append(row);continue
            if key in transport.probe_failures:
                exc,http,attempts=transport.probe_failures.pop(key)
                transport.http[host]=http;row['probe_http_attempts']=canonical(attempts)
                raise exc
            # Only registry entries are requested. There is no discovery/index path.
            if key in transport.probed:
                raw,headers,http,attempts=transport.probed.pop(key);transport.http[host]=http
                row.update(reused_successful_probe=True,probe_http_attempts=canonical(attempts))
            elif host=='wamex.dmp.wa.gov.au' and 'ReportDetails' in source['url']:
                import re
                query=urllib.parse.parse_qs(urllib.parse.urlsplit(source['url']).query)
                native=int(next(v[0] for k,v in query.items() if k.lower()=='anumber'))
                body,headers=transport('https://wamex.dmp.wa.gov.au/Wamex/Search/ReportDetails/ReportDocuments_Read',{'aNumber[0]':native,'page':1,'pageSize':20},method='POST')
                listing=json.loads(body)
                if listing.get('Errors') or not isinstance(listing.get('Total'),int) or not isinstance(listing.get('Data'),list) or any(r.get('ANumber')!=native for r in listing['Data']):raise ValueError('WAMEX_REPORT_IDENTITY_MISMATCH')
                raw=None;attempted=0
                for item in listing['Data']:
                    if attempted>=2:break
                    link=item.get('Link','');size=re.fullmatch(r'([\d.]+)\s*(KB|MB|GB)',item.get('FileSize',''),re.I)
                    if str(item.get('FileType','')).lower()!='.pdf' or not size:continue
                    if float(size[1])*{'KB':1024,'MB':1024**2,'GB':1024**3}[size[2].upper()]>30000000:continue
                    if urllib.parse.urlsplit(link).scheme!='https' or urllib.parse.urlsplit(link).hostname!='warsydprdstagsdspub.blob.core.windows.net':continue
                    attempted+=1;candidate,headers=transport(link,max_bytes=30000000)
                    if not candidate.startswith(b'%PDF'):continue
                    sha=hashlib.sha256(candidate).hexdigest();(cache/(sha+'.pdf')).write_bytes(candidate)
                    if sha in expected:raw=candidate;break
                    candidate_mismatch=True
                if raw is None:raise ValueError('SOURCE_SHA_CHANGED' if attempted else 'WAMEX_NO_ELIGIBLE_DOCUMENT')
            elif source['kind']=='minedex_resource_batch':raw,headers=minedex_resource_batch(source['url'],source['product_alias'],fetch=transport)
            elif source['kind']==ASIC_REGISTER_KIND:
                raw,headers=transport(source['url'],timeout=source.get('timeout_seconds',60),
                                      max_bytes=min(source.get('max_bytes',100_000_000),100_000_000))
            elif source.get('fixed_query'):raw,headers=transport(source['url'],max_bytes=source.get('max_bytes',50_000_000))
            elif source['kind'] in ('arcgis_census','arcgis_gis','government_arcgis'):
                raw=(canonical(arcgis(source['url'],source.get('where','1=1'),windows=project_windows(root,{'snapshots':manifest},source['aoi_radius_km']) if source.get('aoi_radius_km') else None,fetch=transport))+'\n').encode();headers={}
            elif source['kind']=='government_wfs':raw=(canonical(wfs(source,fetch=transport))+'\n').encode();headers={}
            else:raw,headers=transport(source['url'],timeout=source.get('timeout_seconds',25))
            row['http_status']=transport.http.get(host)
            if source['kind']=='pdf' and not raw.startswith(b'%PDF'):raise ValueError('NOT_PDF')
            if source['kind']=='xlsx_census' and not raw.startswith(b'PK'):raise ValueError('NOT_XLSX')
            sha = hashlib.sha256(raw).hexdigest()
            row['actual_sha256'] = sha
            compared_sha = sha
            hash_metadata = {}
            if 'hash_policy' in source:
                (cache / (sha + '.json')).write_bytes(raw)
                row.update(
                    raw_sha256=sha,
                    hash_policy=source['hash_policy'],
                    hash_drop_keys=canonical(source.get('hash_drop_keys')),
                    sha_match=False,
                )
                compared_sha, hash_metadata = declared_json_hash(raw, source)
                row.update(hash_metadata)
                row['hash_drop_keys'] = canonical(hash_metadata['hash_drop_keys'])
            row['sha_match'] = compared_sha in expected if expected else None
            if expected and compared_sha not in expected:
                raise ValueError('SOURCE_SHA_CHANGED')
            suffix='.pdf' if source['kind']=='pdf' else '.xlsx' if source['kind']=='xlsx_census' else '.zip' if source['kind'] in ('minedex_resource_batch',ASIC_REGISTER_KIND) else '.csv' if source['kind']=='government_csv' else '.html' if source['kind']=='html' else '.json'
            path=cache/(sha+suffix);path.write_bytes(raw)
            now=datetime.now(timezone.utc).isoformat()
            entry=dict(source,sha256=sha,path=str(path),acquired_at=now,available_date=now[:10])
            entry.update(hash_metadata)
            entry = evidenced_snapshot(root, entry, cutoff)
            if source['kind']==ASIC_REGISTER_KIND:
                entry['available_date']=asic_capture_date(root,source,path,sha)
            if source['kind']=='minedex_resource_batch':
                entry.update(source_update=headers['X-DASC-Updated'],resolved_download_url=headers['X-DASC-Download'],last_modified=headers.get('Last-Modified'))
                entry['publication_date']=datetime.strptime(headers['X-DASC-Updated'],'%d/%m/%Y').date().isoformat()
            if source['kind'] in ('pdf','html') and not expected:
                row['status']='CACHED_UNBOUND_SOURCE_NOT_ADOPTED'
            else:
                selected.append(entry);row['status']='FETCHED_SHA_VERIFIED' if expected else 'FETCHED_UNBOUND_GOVERNMENT_OR_SOURCE'
        except Exception as exc:
            if host=='www.asx.com.au' and str(exc)=='NOT_PDF':transport.stopped[host]='NOT_PDF'
            failure='SOURCE_SHA_CHANGED' if candidate_mismatch or str(exc)=='SOURCE_SHA_CHANGED' else str(exc)
            status=failure if failure in ('SOURCE_SHA_CHANGED','CONFLICTING_DECLARED_SOURCE_SHA') else strict_failure_status(exc)
            row.update(http_status=transport.http.get(host),stop_reason=failure,status=status,network_error=status=='NETWORK_ERROR')
            replacement=None if 'hash_policy' in source else alternate.find(source,row,expected,cache)
            if replacement:selected.append(replacement)
            elif (
                'hash_policy' not in source
                and failure not in ('SOURCE_SHA_CHANGED', 'CONFLICTING_DECLARED_SOURCE_SHA')
                and status not in ('NETWORK_ERROR', 'HOST_STOPPED')
                and host != 'www.asx.com.au'
            ):
                candidates=[s for s in old if committed(s,expected)]
                if candidates:selected.append(max(candidates,key=lambda s:s['acquired_at']));row.update(status='SNAPSHOT_FALLBACK_SAME_SHA',sha_match=True)
        row['http_attempts']=canonical(transport.attempts[request_start:])
        outcomes.append(row)
    changed_keys={r['key'] for r in outcomes if r['status']=='SOURCE_SHA_CHANGED'}
    changed_urls={s['url'] for s in registry['sources'] if s['key'] in changed_keys}
    invalid={s['key']:'SOURCE_SHA_CHANGED' for s in registry['sources'] if s['url'] in changed_urls}
    original_shas={s['sha256'] for s in selected if s['kind']=='pdf' and s['key'] not in invalid}
    for source in selected:
        if source['kind'] in ('pdf_page_extraction','official_table_transcription','official_project_catalogue_transcription'):
            parent=source.get('parent_source_sha256',source.get('source_sha256'))
            if not parent or parent not in original_shas:
                invalid.setdefault(source['key'],'SOURCE_NOT_ACQUIRED')
    selected=[s for s in selected if s['key'] not in invalid]
    for row in outcomes:
        if row['key'] in invalid:
            row.update(status=invalid[row['key']],stop_reason='PARENT_OR_ALIAS_SOURCE_NOT_VALIDATED',sha_match=False if invalid[row['key']]=='SOURCE_SHA_CHANGED' else row.get('sha_match'))
    alternate.save(work)
    report=strict_network_report(work,outcomes,dns_rows)
    if report['status']=='RUN_INVALID_NETWORK':
        raise InvalidNetworkRun('RUN_INVALID_NETWORK: network errors exceed 5%; see '+str(work/'network_status.json'))
    return selected,outcomes


def checked_replay_path(root, entry, source_key, *, replay_assets=None, receipt_paths=False):
    """Verify one immutable original or attachment within its declared library."""
    path = root / entry['path']
    external = not path.resolve().is_relative_to(root.resolve())
    if receipt_paths and external and replay_assets is None:
        raise ValueError(f"External receipt path requires --replay-assets: {source_key}")
    if replay_assets is not None and (external or not path.is_file()):
        sha = entry['sha256']
        if not re.fullmatch('[0-9a-f]{64}', sha):
            raise ValueError('Invalid asset SHA-256 in snapshot lock')
        folder = Path(replay_assets).resolve(strict=True)
        path = (folder / sha).resolve()
        if not path.is_relative_to(folder):
            raise ValueError('Replay asset escapes its library')
    if not path.is_file() or filehash(path) != entry['sha256']:
        raise ValueError(f"Locked snapshot checksum mismatch: {source_key} ({path.name})")
    return path


def checked_snapshots(root, snapshots, cutoff, acquired_through=None, *, replay_assets=None, receipt_paths=False):
    """Resolve immutable originals and their raw response attachments."""
    from .selection_rules import date_end

    for source in snapshots:
        if source.get('publication_date') and date_end(source['publication_date']) > cutoff:
            raise ValueError(f"Snapshot after publication cutoff: {source['key']}")
        if acquired_through and source['available_date'] > acquired_through:
            raise ValueError(f"Snapshot after acquisition cutoff: {source['key']}")
        for entry in [source, *source.get('original_responses', [])]:
            path = checked_replay_path(root, entry, source['key'], replay_assets=replay_assets, receipt_paths=receipt_paths)
            if path != root / entry['path']:
                entry['path'] = str(path)
    return snapshots


ASIC_REGISTER_KIND = 'asic_company_register_zip'
WA_TITLE_KIND = 'wa_dasc_tenements_zip'
STATIC_ARCHIVE_KINDS = {ASIC_REGISTER_KIND, WA_TITLE_KIND}
WA_TITLE_ORIGIN = (r'https://warsydprdstadasc\.blob\.core\.windows\.net/downloads/dasc/Dynamic/Tenements/'
                   r'(?:CurrentTenements(?:_GDA2020)?_shp|DeadTenements_shp)\.zip(?:\?ts=\d{14})?')
WA_TITLE_REPLAY_URL = re.compile(r'https://web\.archive\.org/web/(\d{14})id_/(' + WA_TITLE_ORIGIN + ')')


def wa_title_capture_date(root, source, archive, sha):
    """Resolve the availability of the exact WA government ZIP from its archived HTTP 200 inventory row."""
    import base64
    import hashlib

    replay = WA_TITLE_REPLAY_URL.fullmatch(source.get('url', ''))
    metadata = source.get('archive_index_sha256', '')
    if (not replay or not re.fullmatch('[0-9a-f]{64}', metadata) or
            (source.get('archive_capture_timestamp'), source.get('archive_origin_url')) != replay.groups() or
            sha != source.get('source_sha256') or sha != source.get('reviewed_static_archive_sha256')):
        raise ValueError('WA title archive capture or version mismatch')
    stamp, origin = replay.groups()
    capture = datetime.strptime(stamp, '%Y%m%d%H%M%S').date().isoformat()
    index = Path(root) / 'data' / 'snapshots' / (metadata + '.json')
    if not index.is_file() or filehash(index) != metadata:
        raise ValueError('WA title archive index checksum mismatch')
    index_url = urllib.parse.urlsplit(source.get('archive_index_url', ''))
    query = urllib.parse.parse_qs(index_url.query)
    targets = query.get('url', [])
    indexed_target = targets[0].removeprefix('https://').casefold() if len(targets) == 1 else ''
    origin_path = origin.removeprefix('https://').casefold()
    prefix_query = indexed_target.endswith('*') or query.get('matchType') == ['prefix']
    in_query = (origin_path.startswith(indexed_target.rstrip('*')) if prefix_query else origin_path == indexed_target)
    if ((index_url.scheme, index_url.netloc, index_url.path) != ('https', 'web.archive.org', '/cdx/search/cdx')
            or query.get('output') != ['json'] or not indexed_target.strip('*') or not in_query):
        raise ValueError('WA title archive index URL mismatch')
    header, *rows = json.loads(index.read_bytes())
    required = {'original', 'timestamp', 'digest', 'mimetype', 'statuscode'}
    if len(set(header)) != len(header) or not required.issubset(header):
        raise ValueError('WA title archive index schema mismatch')
    records = (dict(zip(header, record, strict=True)) for record in rows)
    matched = [r for r in records if r['original'] == origin and r['timestamp'] == stamp]
    if (len(matched) != 1 or matched[0]['statuscode'] != '200'
            or matched[0]['mimetype'] not in ('application/octet-stream', 'application/zip', 'application/x-zip-compressed')
            or matched[0]['digest'] != source.get('archive_sha1')
            or not zipfile.is_zipfile(archive)):
        raise ValueError('WA title archive index record mismatch')
    with Path(archive).open('rb') as stream:
        actual = base64.b32encode(hashlib.file_digest(stream, 'sha1').digest()).decode('ascii')
    if actual != matched[0]['digest'] or filehash(archive) != sha:
        raise ValueError('WA title archive payload checksum mismatch')
    return capture


def archive_capture_date(root, source, path, sha):
    if source['kind'] == WA_TITLE_KIND:
        return wa_title_capture_date(root, source, path, sha)
    return asic_capture_date(root, source, path, sha)


def asic_capture_date(root, source, archive, sha):
    """Verify the original monthly ASIC ZIP and the independently archived publisher metadata."""
    metadata_sha = source.get('archive_manifest_sha256', '')
    if (not re.fullmatch('[0-9a-f]{64}', metadata_sha)
            or sha != source.get('source_sha256') or sha != source.get('reviewed_static_archive_sha256')):
        raise ValueError('ASIC archive or manifest SHA is not pinned')
    metadata_path = Path(root) / 'data' / 'snapshots' / (metadata_sha + '.json')
    if not metadata_path.is_file() or filehash(metadata_path) != metadata_sha:
        raise ValueError('ASIC archive manifest checksum mismatch')
    data = json.loads(metadata_path.read_bytes())
    upstream = data['source']
    publication = source['publication_date']
    filename = 'company_' + publication[:7].replace('-', '') + '.zip'
    base = 'https://data.gov.au/data/dataset/7b8656f9-606d-4337-af29-66b89b2eeefb/resource/'
    official = base + 'd6d03876-71a4-4e82-8c77-2e4df5da4236/download/' + filename
    capture = datetime.fromisoformat(data['fetched_at'])
    modified = parsedate_to_datetime(upstream['http_last_modified'])
    catalogue_date = datetime.fromisoformat(upstream['resource_last_modified']).date().isoformat()
    if (data['dataset'] != 'asic-companies' or data.get('backfilled') is not False or data.get('tombstone')
            or data['version'] != publication or data['filename'] != filename or data['encoding'] != 'zip'
            or upstream['url'] != official or source['url'] != official
            or source['archive_manifest_url'] != f'https://publicdata.au/d/asic-companies/v/{publication}/manifest.json'
            or data['sha256'] != sha or data['bytes'] != Path(archive).stat().st_size
            or not capture.tzinfo or not modified.tzinfo or capture < modified
            or modified.date().isoformat() != publication or catalogue_date != publication):
        raise ValueError('ASIC register version or publisher date mismatch')
    with zipfile.ZipFile(archive) as dataset:
        members = [entry.filename for entry in dataset.infolist() if not entry.is_dir()]
        if members != [source['archive_member']]:
            raise ValueError('ASIC register ZIP member mismatch')
    return capture.astimezone(timezone.utc).date().isoformat()


def static_pdf_sources(registry, claims, directories, cutoff, already_selected, *, root=None):
    """Resolve registered PDF and archive originals in the same static library by their bytes."""
    from .selection_rules import date_end

    declared, bindings=declared_source_hashes(registry,claims)
    pending=[]
    for source in registry['sources']:
        key=source['key']
        if source['kind'] not in ('pdf', *STATIC_ARCHIVE_KINDS) or key in already_selected:
            continue
        pin=source.get('reviewed_static_archive_sha256' if source['kind'] in STATIC_ARCHIVE_KINDS else 'reviewed_static_pdf_sha256')
        if pin:
            # A reviewed local version can have the same landing URL as another
            # version. The pin does not grant access to that remote URL.
            expected=set(declared.get(key,set()))
            if pin!=source.get('source_sha256') or expected-{pin}:
                raise ValueError(f'Static PDF pin conflicts with declarations: {key}')
            expected={pin}
        else:
            if source.get('enabled') is False:
                continue
            expected=bindings.get(source['url'],set())
        if len(expected)!=1:
            continue
        publication=source.get('publication_date')
        if source['kind'] == WA_TITLE_KIND:
            stamp = source.get('archive_capture_timestamp', '')
            if not re.fullmatch(r'\d{14}', stamp):
                raise ValueError('WA title archive capture timestamp missing')
            if datetime.strptime(stamp, '%Y%m%d%H%M%S').date().isoformat() > cutoff:
                continue
        elif not publication or date_end(publication)>cutoff:
            continue
        pending.append((source,next(iter(expected))))
    wanted={(source['kind'],sha) for source,sha in pending}
    hashes={sha for _,sha in wanted}
    paths={}
    files=set()
    suffixes={'.pdf', '.zip'} if any(kind in STATIC_ARCHIVE_KINDS for kind,_ in wanted) else {'.pdf'}
    for directory in directories:
        folder=Path(directory).resolve(strict=True)
        if not folder.is_dir():
            raise ValueError(f'Static PDF library must be a directory: {folder}')
        files.update(p for p in folder.rglob('*') if p.suffix.lower() in suffixes and p.is_file())
    for path in sorted(files,key=lambda p:(p.stem not in hashes,str(p))):
        if wanted<=paths.keys():
            break
        with path.open('rb') as stream:
            signature=stream.read(5)
            if path.suffix.lower()=='.pdf' and signature==b'%PDF-':
                kinds=('pdf',)
            elif path.suffix.lower()=='.zip' and signature.startswith(b'PK\x03\x04'):
                kinds=STATIC_ARCHIVE_KINDS
            else:
                continue
        sha=filehash(path)
        for kind in kinds:
            if (kind,sha) in wanted:
                paths.setdefault((kind,sha),path.resolve())
    now=datetime.now(timezone.utc).isoformat()
    selected=[]
    for source,sha in pending:
        path=paths.get((source['kind'],sha))
        if path is not None:
            if source['kind'] in STATIC_ARCHIVE_KINDS:
                capture=archive_capture_date(root,source,path,sha)
                method=('STATIC_WA_DASC_ZIP_SHA_VERIFIED' if source['kind'] == WA_TITLE_KIND
                        else 'STATIC_ASIC_REGISTER_SHA_VERIFIED')
                if capture<=cutoff:
                    selected.append(dict(source,sha256=sha,path=str(path),acquired_at=now,
                        available_date=capture,acquisition_method=method))
                continue
            selected.append(dict(source,sha256=sha,path=str(path),
                acquired_at=now,available_date=now[:10],acquisition_method='STATIC_PDF_SHA_VERIFIED'))
    return selected


SOURCE_SELECTION_FIELDS = (
    'key', 'source_sha256', 'phase22_sha256', 'action', 'kind', 'cutoff',
    'publication_date', 'available_date', 'date_basis', 'date_used',
    'version_status', 'cutoff_status',
)


def census_admission(root, source, registered, claim_hashes, cutoff):
    """Verify the version and the time basis before a source reaches SQLite."""
    from .selection_rules import date_end

    key, sha, kind = source['key'], source['sha256'], source['kind']
    if registered.get('kind') == WA_TITLE_KIND:
        if kind != WA_TITLE_KIND:
            raise ValueError('WA title archive receipt kind mismatch')
        identity = ('url','archive_origin_url','archive_capture_timestamp','archive_sha1','archive_index_sha256','archive_index_url')
        if any(source.get(field) != registered.get(field) for field in identity):
            raise ValueError('WA title archive receipt identity mismatch')
    publication = source.get('publication_date')
    registered_publication = registered.get('publication_date')
    availability = source.get('available_date') or (source.get('acquired_at') or '')[:10]
    documentary = kind in ('pdf','html','pdf_page_extraction','document_extraction')
    date_basis = 'DOCUMENT_PUBLICATION' if documentary and publication else 'SOURCE_AVAILABILITY'
    date_value = publication if date_basis == 'DOCUMENT_PUBLICATION' else availability
    used = date_end(date_value) if date_value else ''
    month_interval = registered.get('publication_date_interval')
    month_precision = str(registered.get('publication_date_precision', '')).lower() == 'month'
    interval_mismatch = False
    if date_basis == 'DOCUMENT_PUBLICATION' and month_precision:
        month = publication[:7]
        used = date_end(month)
        if month_interval is not None:
            interval_mismatch = month_interval != [month + '-01', used]
    after_cutoff = used>cutoff or (publication and date_end(publication)>cutoff)
    cutoff_status = ('SOURCE_AFTER_CUTOFF' if after_cutoff else 'WITHIN_CUTOFF' if used else 'SOURCE_DATE_UNVERIFIED')
    if kind in STATIC_ARCHIVE_KINDS:
        capture=archive_capture_date(root, registered, Path(root)/source['path'], sha)
        date_basis='ARCHIVED_HTTP_CAPTURE' if kind == WA_TITLE_KIND else 'ARCHIVED_PUBLISHER_VERSION'
        used=capture
        if publication!=registered_publication or capture!=availability:
            cutoff_status='SOURCE_PUBLICATION_DATE_MISMATCH'
        elif capture>cutoff:
            cutoff_status='SOURCE_AFTER_CUTOFF'
    approved = {h for h in (registered.get('source_sha256'), registered.get('committed_snapshot_sha256'),
                             registered.get('reviewed_static_pdf_sha256')) if h} | claim_hashes.get(key,set())
    version_status = 'PINNED_SHA_VERIFIED' if sha in approved else 'RECEIPT_SHA_VERIFIED'
    if approved and sha not in approved:
        if registered.get('hash_policy') and declared_json_hash((root/source['path']).read_bytes(),registered)[0] in approved:
            version_status = 'DECLARED_CONTENT_AND_RECEIPT_SHA_VERIFIED'
        else:
            version_status = 'SOURCE_VERSION_NOT_DECLARED'
    if interval_mismatch or (documentary and publication and registered_publication and
            not (publication.startswith(registered_publication) or registered_publication.startswith(publication))):
        cutoff_status = 'SOURCE_PUBLICATION_DATE_MISMATCH'
    return dict(kind=kind,cutoff=cutoff,publication_date=publication,available_date=availability,
                date_basis=date_basis,date_used=used,version_status=version_status,cutoff_status=cutoff_status)


def replay_pdf_extensions(registry, receipt_sha, static_pdfs):
    """Accept an additive static PDF review only when the entire old registry still hashes identically."""
    if digest(registry) == receipt_sha:
        return []
    added = [s for s in registry['sources'] if s.get('replay_extension_of') == receipt_sha]
    retained = [s for s in registry['sources'] if s.get('replay_extension_of') != receipt_sha]
    keys = [s['key'] for s in registry['sources']]
    if (not static_pdfs or not added or len(keys) != len(set(keys))
            or digest(dict(registry, sources=retained)) != receipt_sha
            or any(not (s.get('archive_capture_timestamp') if s['kind'] == WA_TITLE_KIND else s.get('publication_date'))
                   or not s.get('source_sha256') or
                   (s['kind'], s['source_sha256']) not in (
                       ('pdf', s.get('reviewed_static_pdf_sha256')),
                       (ASIC_REGISTER_KIND, s.get('reviewed_static_archive_sha256')),
                       (WA_TITLE_KIND, s.get('reviewed_static_archive_sha256'))) for s in added)):
        raise ValueError('Acquisition replay source registry changed')
    return [s['key'] for s in added]


def census_acquisition(root, registry, work, claims, cutoff, replay=None, *, static_pdfs=(),
                       replay_assets=None, receipt_path=None):
    """One ASX source stage. Replays use the same selected inputs and receipts."""
    from .tabular import write_csv

    extensions = []
    if replay:
        receipt = json.loads(Path(replay).read_text(encoding='utf8'))
        if receipt['cutoff'] != cutoff:
            raise ValueError('Acquisition replay cutoff must match --as-of')
        extensions = replay_pdf_extensions(registry, receipt['registry_sha256'], static_pdfs)
        fresh = checked_snapshots(root, receipt['snapshots'], cutoff, replay_assets=replay_assets, receipt_paths=True)
        registered = {s['key']:s['kind'] for s in registry['sources']}
        if any(registered.get(s['key']) != s['kind'] for s in fresh):
            raise ValueError('Acquisition replay contains an unregistered source')
        outcomes = receipt['outcomes']
    elif static_pdfs:
        fresh,outcomes=[],[]
    else:
        policy, _ = strict_search_plan(root)
        dns_rows = strict_dns_preflight(registry, policy['official_reports'])
        network = strict_network_report(work, [], dns_rows)
        if network['status'] == 'RUN_INVALID_NETWORK':
            raise InvalidNetworkRun('RUN_INVALID_NETWORK: DNS preflight failed; no HTTP requests or build started')
        transport = StrictTransport(STRICT_HOSTS)
        SameSHAAlternates(root, transport)
        probe = strict_asx_probe(registry, transport)
        write_csv(work/'asx_probe.csv', probe, sorted({k for row in probe for k in row}))
        if probe and strict_network_report(work, probe, dns_rows)['status'] == 'RUN_INVALID_NETWORK':
            raise InvalidNetworkRun('RUN_INVALID_NETWORK: ASX probe network errors exceed 5%; build not started')
        fresh, outcomes = strict_refresh(root, registry, work, claims, cutoff, transport, dns_rows)
        # A downloaded future publication remains an acquisition receipt.
        fresh = [s for s in fresh if (s.get('publication_date') or '') <= cutoff]
    if static_pdfs:
        added=static_pdf_sources(registry,claims,static_pdfs,cutoff,{s['key'] for s in fresh},root=root)
        missing_extensions = set(extensions) - {s['key'] for s in added}
        if missing_extensions:
            raise ValueError('Missing verified static PDF extension: ' + ', '.join(sorted(missing_extensions)))
        checked_snapshots(root,added,cutoff)
        fresh=[*fresh,*added]
        updates={s['key']:dict(key=s['key'],host=urllib.parse.urlsplit(s['url']).hostname,
            status=s['acquisition_method'],actual_sha256=s['sha256'],expected_sha256=s['sha256'],
            sha_match=True,stop_reason='') for s in added}
        outcomes=[row for row in outcomes if row['key'] not in updates]+list(updates.values())
    if cutoff < '2026-11-05':
        raise ValueError('Integrated census requires a cutoff on or after the Phase 22 evidence cutoff')
    phase22 = root/'results/phase22-2026-11-06/snapshot_lock.json'
    release_summary = phase22.with_name('summary.json')
    if release_summary.is_file():
        hashes = json.loads(release_summary.read_text(encoding='utf8'))['output_hashes']
        if hashes.get('snapshot_lock.json') != filehash(phase22):
            raise ValueError('Phase 22 frozen source lock checksum mismatch')
    base = checked_snapshots(root, json.loads(phase22.read_text(encoding='utf8')), '2026-11-05', '2026-11-06',
                             replay_assets=replay_assets)
    # Keep reviewed Phase 22 originals at their frozen keys. ASX extends the
    # collection with additional keys and verified aliases, including page inputs.
    by_key = {s['key']: s for s in base}
    registered = {s['key']:s for s in registry['sources']}
    declared,_ = declared_source_hashes(registry,claims)
    decisions = []
    withheld = {}
    for source in fresh:
        key = source['key']
        prior = by_key.get(key)
        audit = census_admission(root,source,registered.get(key,{}),declared,cutoff)
        if prior:
            action = 'EXACT_PHASE22_SOURCE' if prior['sha256']==source['sha256'] else 'FROZEN_PHASE22_VERSION_RETAINED'
        else:
            action = next((status for status in (audit['version_status'],audit['cutoff_status']) if status in
                           ('SOURCE_VERSION_NOT_DECLARED','SOURCE_AFTER_CUTOFF','SOURCE_DATE_UNVERIFIED',
                            'SOURCE_PUBLICATION_DATE_MISMATCH')),
                          'ASX_SOURCE_ADDED')
            if action=='ASX_SOURCE_ADDED':by_key[key]=source
            else:withheld[key]=action
        decisions.append(dict(key=key, source_sha256=source['sha256'],
            phase22_sha256=prior['sha256'] if prior else '',action=action,**audit))
    outcomes=[dict(row,admission_status=withheld[row['key']]) if row['key'] in withheld
              else {k:v for k,v in row.items() if k!='admission_status'} for row in outcomes]
    work.mkdir(parents=True, exist_ok=True)
    def portable(entry):
        path=(root/entry['path']).resolve()
        return dict(entry,path=path.relative_to(root).as_posix()) if path.is_relative_to(root) else entry

    captured = dict(receipt if replay else {}, cutoff=cutoff, registry_sha256=digest(registry),
        snapshots=[dict(portable(s), original_responses=[portable(a) for a in s.get('original_responses', [])])
                   if 'original_responses' in s else portable(s) for s in fresh], outcomes=outcomes)
    if extensions:
        captured['static_pdf_extension'] = dict(parent_registry_sha256=receipt['registry_sha256'],
            parent_receipt_sha256=filehash(Path(replay)), added_keys=sorted(extensions))
    destination=Path(receipt_path) if receipt_path is not None else work/'source_acquisition.json'
    destination.parent.mkdir(parents=True,exist_ok=True)
    destination.write_text(canonical(captured)+'\n', encoding='utf8')
    return list(by_key.values()), outcomes, decisions


def record_source_not_acquired(root, key, source):
    """A discovery guard receipt, not a fetch or a fabricated source value."""
    import csv
    path=Path(root)/'work/discovery/acquisition_report.csv';path.parent.mkdir(parents=True,exist_ok=True)
    fields=['key','host','http_status','sha_match','status','stop_reason']
    row=dict(key=key,host=urllib.parse.urlsplit(source.get('url','')).hostname or '',http_status='',sha_match='',status='SOURCE_NOT_ACQUIRED',stop_reason='SOURCE_NOT_ACQUIRED')
    rows=[]
    if path.exists():
        with path.open(encoding='utf8',newline='') as stream:rows=list(csv.DictReader(stream))
    if row not in rows:
        with path.open('w',encoding='utf8',newline='') as stream:
            writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader();writer.writerows([*rows,row])
    return False
