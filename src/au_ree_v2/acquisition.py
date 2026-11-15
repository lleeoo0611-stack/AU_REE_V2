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


def select_snapshots(root, cutoff, keys=None, acquired_through=None):
    manifest = json.loads((Path(root) / 'data/manifest.json').read_text(encoding='utf-8'))
    selected = {}
    def visible(s):
        if (s.get('publication_date') or '')>cutoff:return False
        if s['available_date']<=cutoff:return True
        # Retrospective acquisition is explicit and limited to dated documents
        # and their extraction artifacts; never backdate live GIS/government rows.
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
        # Never backdate a current live response to an earlier analysis cutoff.
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

gov={'services.ga.gov.au','public-services.slip.wa.gov.au','spatial-gis.information.qld.gov.au','data.stategrowth.tas.gov.au','public-gs.geoscience.nsw.gov.au','opendata.maps.vic.gov.au','geology.data.nt.gov.au','services.sarig.sa.gov.au','wamex.dmp.wa.gov.au','dasc.dmirs.wa.gov.au','geoscience.data.qld.gov.au'}
delivery={'warsydprdstagsdspub.blob.core.windows.net','gsq-prod-ckan-horizon-public.s3.ap-southeast-2.amazonaws.com'}
groups={
    'government-api':gov,
    'government-resource':delivery|{'www.wa.gov.au','international.austrade.gov.au','www.industry.gov.au','dem-sdp.s3-ap-southeast-2.amazonaws.com'},
    'asx':{'announcements.asx.com.au','www.asx.com.au'},
    'issuer-ir':{'investorpa.com','orbitresources.au','www.itechminerals.com.au','asm-au.com','www.arultd.com','www.astronlimited.com.au','victorymetalsaustralia.com','www.devexresources.com.au','www.gippslandcriticalminerals.com','www.iluka.com','wcsecure.weblink.com.au','hermes-cdn.investorhub.com','staff-web.automicgroup.com.au','assets.birdsoftware.io','assets.ctfassets.net'},
    'aggregator':{'api.investi.com.au','company-announcements.afr.com','newswire.iguana2.com','www.marketindex.com.au','cdn-api.markitdigital.com','cdn.financialreports.eu','data-api.marketindex.com.au','investornews.com','www.annualreports.com','www.londonstockexchange.com'},
    'legacy-committed':{'raw.githubusercontent.com'}}
STRICT_HOSTS={host:group for group,items in groups.items() for host in items}

class StrictTransport:
    """One build-scoped transport; no legacy request semantics are changed."""
    def __init__(self, hosts):
        self.hosts=hosts;self.last={};self.stopped={};self.http={};self.attempts=[]
        owner=self
        class Redirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, newurl):
                old=urllib.parse.urlsplit(req.full_url).hostname;new=urllib.parse.urlsplit(newurl).hostname
                owner.http[old]=code;owner.attempts.append(dict(host=old,http_status=code))
                if urllib.parse.urlsplit(newurl).scheme!='https' or new not in owner.hosts or (old!=new and owner.hosts.get(old)!=owner.hosts.get(new)):
                    raise ValueError('REDIRECT_DESTINATION_NOT_APPROVED')
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
            self.guard(host)
            try:
                with self.opener.open(req,timeout=timeout) as response:
                    final=urllib.parse.urlsplit(response.geturl()).hostname
                    self.http[host]=response.status;self.attempts.append(dict(host=host,http_status=response.status))
                    raw=response.read(max_bytes+1) if max_bytes is not None else response.read()
                    if max_bytes is not None and len(raw)>max_bytes:raise ValueError('DOCUMENT_BYTE_BUDGET_EXCEEDED')
                    sample=raw[:200000].lower()
                    if not raw.startswith((b'%PDF',b'PK')) and any(token in sample for token in (b'captcha',b'type="password"',b"type='password'",b'please log in',b'please sign in')):
                        self.stopped[host]=self.stopped[final]='CAPTCHA_OR_LOGIN'
                        raise ValueError('CAPTCHA_OR_LOGIN')
                    return raw,dict(response.headers)
            except urllib.error.HTTPError as exc:
                self.http[host]=exc.code;self.attempts.append(dict(host=host,http_status=exc.code));exc.request_attempts=attempt+1
                if 400<=exc.code<500:
                    self.stopped[host]=str(exc.code)
                    self.stopped[urllib.parse.urlsplit(exc.url).hostname]=str(exc.code)
                    raise
                if not 500<=exc.code<600 or attempt:raise
            except (urllib.error.URLError,TimeoutError) as exc:
                self.attempts.append(dict(host=host,http_status=None,error='TIMEOUT' if isinstance(getattr(exc,'reason',exc),(TimeoutError,socket.timeout)) else 'NETWORK_ERROR'))
                if not isinstance(getattr(exc,'reason',exc),(TimeoutError,socket.timeout)) or attempt:raise


def strict_refresh(root, registry, work, claims, cutoff):
    """Fresh work-only originals, exact declared-SHA fallback, no index discovery."""
    import hashlib,subprocess,tempfile
    root=Path(root).resolve();work=Path(work).resolve();work.mkdir(parents=True,exist_ok=True)
    cache=Path(tempfile.mkdtemp(prefix='strict-',dir=work))
    manifest=json.loads((root/'data/manifest.json').read_text(encoding='utf8'))['snapshots']
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
    transport=StrictTransport(STRICT_HOSTS);outcomes=[];selected=[]
    managed={'official_table_transcription','official_project_catalogue_transcription','historical_e1_candidates','legacy_screen_index','pdf_page_extraction'}
    def committed(s,expected):
        p=Path(s['path']);target=(root/p).resolve()
        if p.is_absolute() or not target.is_relative_to(root/'data/snapshots') or s['sha256'] not in expected:return False
        check=subprocess.run(['git','cat-file','blob','HEAD:'+p.as_posix()],cwd=root,capture_output=True)
        return check.returncode==0 and hashlib.sha256(check.stdout).hexdigest()==s['sha256'] and target.is_file() and filehash(target)==s['sha256']
    discovery_path=root/'config/discovery.json'
    if discovery_path.exists():
        import copy
        from .discovery import official_reports
        policy=copy.deepcopy(json.loads(discovery_path.read_text(encoding='utf8')))
        fixed=[]
        for report in policy.get('official_reports',[]):
            if report['protocol']=='arcgis' and not report.get('where'):
                outcomes.append(dict(key=report['key'],host=urllib.parse.urlsplit(report['url']).hostname,http_status=None,sha_match=None,status='NO_FIXED_QUERY_NOT_EXPANDED',stop_reason='No configured fixed WAMEX query'))
                continue
            report.update(dynamic_candidates=False,resume=False);fixed.append(report)
        policy.update(official_reports=fixed,official_cursors={})
        def save_receipt(raw,meta,suffix):
            from .security import sensitive_reference
            if sensitive_reference(raw.decode('utf8',errors='ignore')):raw=b'REDACTED_SENSITIVE_RECEIPT'
            sha=hashlib.sha256(raw).hexdigest();(cache/(sha+suffix)).write_bytes(raw);return sha
        _,reports,seeds,_=official_reports(policy,[],transport,save_receipt)
        for report in reports:
            outcomes.append(dict(key=report['seed_key'],host=urllib.parse.urlsplit(report['url']).hostname,http_status=report.get('http_status',transport.http.get(urllib.parse.urlsplit(report['url']).hostname)),sha_match=None,status=report['status'],stop_reason=report.get('reason','')))
        # Returned exact delivery URLs are receipts only, never unreviewed claims.
        for seed in seeds:
            host=urllib.parse.urlsplit(seed['url']).hostname
            try:
                raw,_=transport(seed['url'],max_bytes=seed.get('max_document_bytes'))
                if not raw.startswith(b'%PDF'):raise ValueError('NOT_PDF')
                save_receipt(raw,{},'.pdf');status='API_DOCUMENT_CACHED_NOT_ADOPTED';reason=''
            except Exception as exc:status='UNAVAILABLE';reason=str(exc)
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
        if source['url']=='https://www.gippslandcriticalminerals.com/project-overview/':
            row.update(status='SOURCE_NOT_ACQUIRED',stop_reason='INDEX_LANDING_DISABLED');outcomes.append(row);continue
        candidate_mismatch=False
        try:
            if len(expected)>1:raise ValueError('CONFLICTING_DECLARED_SOURCE_SHA')
            if source['kind'] in managed:
                candidates=[s for s in old if committed(s,expected)]
                if not candidates:raise ValueError('DECLARED_COMMITTED_DERIVATIVE_UNAVAILABLE')
                selected.append(max(candidates,key=lambda s:s['acquired_at']));row.update(status='COMMITTED_MANAGED_SAME_SHA',sha_match=True)
                outcomes.append(row);continue
            # Only registry entries are requested. There is no discovery/index path.
            if host=='wamex.dmp.wa.gov.au' and 'ReportDetails' in source['url']:
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
            elif source['kind'] in ('arcgis_census','arcgis_gis','government_arcgis'):
                raw=(canonical(arcgis(source['url'],source.get('where','1=1'),windows=project_windows(root,{'snapshots':manifest},source['aoi_radius_km']) if source.get('aoi_radius_km') else None,fetch=transport))+'\n').encode();headers={}
            elif source['kind']=='government_wfs':raw=(canonical(wfs(source,fetch=transport))+'\n').encode();headers={}
            else:raw,headers=transport(source['url'],timeout=source.get('timeout_seconds',25))
            row['http_status']=transport.http.get(host)
            if source['kind']=='pdf' and not raw.startswith(b'%PDF'):raise ValueError('NOT_PDF')
            if source['kind']=='xlsx_census' and not raw.startswith(b'PK'):raise ValueError('NOT_XLSX')
            sha=hashlib.sha256(raw).hexdigest();row['actual_sha256']=sha
            row['sha_match']=sha in expected if expected else None
            if expected and sha not in expected:raise ValueError('SOURCE_SHA_CHANGED')
            suffix='.pdf' if source['kind']=='pdf' else '.xlsx' if source['kind']=='xlsx_census' else '.zip' if source['kind']=='minedex_resource_batch' else '.csv' if source['kind']=='government_csv' else '.html' if source['kind']=='html' else '.json'
            path=cache/(sha+suffix);path.write_bytes(raw)
            now=datetime.now(timezone.utc).isoformat()
            entry=dict(source,sha256=sha,path=str(path),acquired_at=now,available_date=now[:10])
            if source['kind']=='minedex_resource_batch':
                entry.update(source_update=headers['X-DASC-Updated'],resolved_download_url=headers['X-DASC-Download'],last_modified=headers.get('Last-Modified'))
                entry['publication_date']=datetime.strptime(headers['X-DASC-Updated'],'%d/%m/%Y').date().isoformat()
            if source['kind'] in ('pdf','html') and not expected:
                row['status']='CACHED_UNBOUND_SOURCE_NOT_ADOPTED'
            else:
                selected.append(entry);row['status']='FETCHED_SHA_VERIFIED' if expected else 'FETCHED_UNBOUND_GOVERNMENT_OR_SOURCE'
        except Exception as exc:
            failure='SOURCE_SHA_CHANGED' if candidate_mismatch or str(exc)=='SOURCE_SHA_CHANGED' else str(exc)
            row.update(http_status=transport.http.get(host),stop_reason=failure,status=failure if failure in ('SOURCE_SHA_CHANGED','CONFLICTING_DECLARED_SOURCE_SHA') else 'UNAVAILABLE')
            if failure not in ('SOURCE_SHA_CHANGED','CONFLICTING_DECLARED_SOURCE_SHA'):
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
            parent=source.get('source_sha256')
            if not parent or parent not in original_shas:
                invalid.setdefault(source['key'],'SOURCE_NOT_ACQUIRED')
    selected=[s for s in selected if s['key'] not in invalid]
    for row in outcomes:
        if row['key'] in invalid:
            row.update(status=invalid[row['key']],stop_reason='PARENT_OR_ALIAS_SOURCE_NOT_VALIDATED',sha_match=False if invalid[row['key']]=='SOURCE_SHA_CHANGED' else row.get('sha_match'))
    return selected,outcomes


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
