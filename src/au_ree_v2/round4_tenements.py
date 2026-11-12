"""Offline, source-bound round-four tenement centroid projection.

No network calls are made here. Every applied geometry and source quotation must
be reproducible from the committed acquisition archive and own project original.
"""
import hashlib
import json
import math
import re
from pathlib import Path
from pyproj import CRS, Transformer, Geod, network
from shapely.geometry import shape
from shapely.ops import transform, unary_union
network.set_network_enabled(False)


def centroid(features, source_crs, limit_m=25000, id_field=None):
    """Union ALL exact-matched tenements; measure ALL vertices after fallback."""
    crs=CRS.from_user_input(source_crs)
    to_ll=Transformer.from_crs(crs,7844,always_xy=True,allow_ballpark=False)
    geometries=[transform(to_ll.transform,shape(f['geometry'])) for f in features]
    if not geometries or any(g.is_empty or not g.is_valid or g.geom_type not in ('Polygon','MultiPolygon') for g in geometries):
        return dict(accepted=False,reason='INVALID_OR_MISSING_POLYGON')
    union=unary_union(geometries)
    minx,miny,maxx,maxy=union.bounds
    if not (110<=minx<=maxx<=155 and -45<=miny<=maxy<=-9):
        return dict(accepted=False,reason='OUTSIDE_AUSTRALIA_OR_CRS_ERROR')
    # Local equal-area projection avoids measuring longitude/latitude degrees.
    metric=CRS.from_proj4(f'+proj=laea +lat_0={(miny+maxy)/2} +lon_0={(minx+maxx)/2} +ellps=GRS80 +units=m +no_defs')
    forward=Transformer.from_crs(7844,metric,always_xy=True)
    backward=Transformer.from_crs(metric,7844,always_xy=True)
    native=[transform(forward.transform,g) for g in geometries]
    titles={}
    for index,(feature,geometry) in enumerate(zip(features,native)):
        key=identifier_key(feature['properties'][id_field]) if id_field else index
        titles.setdefault(key,[]).append(geometry)
    title_geometries=[unary_union(parts) for parts in titles.values()]
    combined=unary_union(title_geometries);point=combined.centroid;method='TENEMENT_CENTROID'
    if not combined.covers(point):
        point=max(title_geometries,key=lambda g:g.area).centroid;method='LARGEST_TENEMENT_CENTROID'
        if not combined.covers(point):return dict(accepted=False,reason='LARGEST_TENEMENT_CENTROID_OUTSIDE_UNION')
    lon,lat=backward.transform(point.x,point.y)
    geod=Geod(ellps='GRS80')
    polygons=list(union.geoms) if union.geom_type=='MultiPolygon' else [union]
    vertices=[xy for p in polygons for ring in [p.exterior,*p.interiors] for xy in ring.coords]
    precision=max(geod.inv(lon,lat,x,y)[2] for x,y in vertices)
    if not math.isfinite(precision):raise ValueError('NONFINITE_PRECISION')
    return dict(accepted=precision<=limit_m,reason='ACCEPTED' if precision<=limit_m else 'TENEMENT_UNION_EXCEEDS_25KM',longitude=lon,latitude=lat,precision_m=precision,location_method=method,input_crs=crs.to_string(),input_datum=crs.datum.name,output_crs='EPSG:7844',metric_crs=metric.to_string())


def identifier_key(value):
    """Type and numeric identifier only, preserving WA district; no name match."""
    value=re.sub(r'\s+','',str(value)).upper()
    match=re.fullmatch(r'([A-Z]+)(\d+)(?:/(\d+))?',value)
    if not match:return value
    return (match[1],int(match[2]),int(match[3]) if match[3] else None)


def read_shapefile_zip(raw,member):
    """Read every native DBF/SHP/SHX record, preserving polygon rings and IDs."""
    import io,struct,zipfile
    from shapely.geometry import Polygon,MultiPolygon,mapping
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        dbf=z.read(member+'.dbf');shp=z.read(member+'.shp');shx=z.read(member+'.shx')
        crs=CRS.from_wkt(z.read(member+'.prj').decode('ascii'))
        encoding=z.read(member+'.cpg').decode('ascii').strip() if member+'.cpg' in z.namelist() else 'ascii'
        n,header,width=struct.unpack_from('<IHH',dbf,4)
        fields=[(dbf[i:i+11].split(b'\x00')[0].decode('ascii'),dbf[i+16]) for i in range(32,header-1,32)]
        if sum(w for _,w in fields)+1!=width or len(dbf)<header+n*width:raise ValueError('NT_DBF_LENGTH')
        if struct.unpack_from('>i',shp,24)[0]*2!=len(shp) or struct.unpack_from('>i',shx,24)[0]*2!=len(shx) or (len(shx)-100)//8!=n:raise ValueError('NT_SHP_SHX_COMPLETENESS')
        features=[]
        for i in range(n):
            row=dbf[header+i*width:header+(i+1)*width]
            if row[0]!=32:raise ValueError('NT_DELETED_DBF_RECORD')
            props={};pos=1
            for name,size in fields:props[name]=row[pos:pos+size].decode(encoding).strip();pos+=size
            offset,length=struct.unpack_from('>ii',shx,100+i*8);offset*=2;length*=2
            recno,reclen=struct.unpack_from('>ii',shp,offset)
            if recno!=i+1 or reclen*2!=length:raise ValueError('NT_SHP_RECORD_ALIGNMENT')
            b=shp[offset+8:offset+8+length]
            if struct.unpack_from('<i',b)[0] not in (5,15,25):raise ValueError('NT_POLYGON_SHAPE_REQUIRED')
            parts,count=struct.unpack_from('<ii',b,36)
            starts=list(struct.unpack_from('<'+'i'*parts,b,44))+[count]
            if starts[0]!=0 or starts!=sorted(starts):raise ValueError('NT_POLYGON_PARTS')
            points=[struct.unpack_from('<dd',b,44+parts*4+j*16) for j in range(count)]
            rings=[points[a:c] for a,c in zip(starts,starts[1:])]
            polys=[Polygon(r) for r in rings]
            if any(not p.is_valid or p.is_empty for p in polys):raise ValueError('NT_INVALID_RING')
            parents=[]
            for j,poly in enumerate(polys):
                containers=[k for k,other in enumerate(polys) if k!=j and other.area>poly.area and other.covers(poly)]
                parents.append(min(containers,key=lambda k:polys[k].area) if containers else None)
            def depth(index):
                d=0
                while parents[index] is not None:d+=1;index=parents[index]
                return d
            polygons=[Polygon(rings[j],[rings[k] for k in range(len(rings)) if parents[k]==j]) for j in range(len(rings)) if depth(j)%2==0]
            geom=MultiPolygon(polygons)
            if not geom.is_valid:raise ValueError('NT_INVALID_MULTIPOLYGON')
            features.append(dict(type='Feature',id=member+'.'+str(i+1),properties=props,geometry=mapping(geom)))
        return features,crs


def verify_feature_pages(repo,dataset,log):
    features=[];sha=[];offset=0;expected=None
    if dataset.get('format')=='NT_SHAPEFILE_ZIP':
        page=dataset['pages'][0]
        if len(dataset['pages'])!=1 or not any(r['source_sha256']==page['source_sha256'] and r.get('http_status')==200 for r in log):raise ValueError('GEOMETRY_REQUEST_RECEIPT_REQUIRED')
        features,crs=read_shapefile_zip(verified_bytes(repo,page),dataset['zip_member'])
        if crs!=CRS.from_user_input(dataset['source_crs']):raise ValueError('TENEMENT_SOURCE_CRS_MISMATCH')
        if len(features)!=dataset['native_record_count']:raise ValueError('NT_NATIVE_RECORD_COUNT')
        return features,[page['source_sha256']]
    for page in dataset['pages']:
        matches=[r for r in log if r['source_sha256']==page['source_sha256'] and r.get('http_status')==200]
        if len(matches)!=1:raise ValueError('GEOMETRY_REQUEST_RECEIPT_REQUIRED')
        raw=json.loads(verified_bytes(repo,page))
        total=raw.get('numberMatched');returned=raw.get('numberReturned')
        if not isinstance(total,int) or returned!=len(raw.get('features',[])):raise ValueError('TENEMENT_PAGINATION_INCOMPLETE')
        if expected is None:expected=total
        if total!=expected or page.get('start_index')!=offset:raise ValueError('TENEMENT_PAGINATION_INCOMPLETE')
        if raw.get('crs',{}).get('properties',{}).get('name')!=dataset['native_crs_uri']:raise ValueError('TENEMENT_SOURCE_CRS_MISMATCH')
        features.extend(raw['features']);sha.append(page['source_sha256']);offset+=returned
    if offset!=expected:raise ValueError('TENEMENT_PAGINATION_INCOMPLETE')
    ids=[f['id'] for f in features]
    if len(ids)!=len(set(ids)):raise ValueError('TENEMENT_DUPLICATE_FEATURE_ID')
    return features,sha


def verified_bytes(repo, record):
    path=(Path(repo)/record['path']).resolve()
    data=path.read_bytes()
    if hashlib.sha256(data).hexdigest()!=record['source_sha256']:raise ValueError('TENEMENT_ARCHIVE_HASH_MISMATCH')
    return data


def validate_original(record, project_id, repo, trace):
    if record.get('project_id')!=project_id or not record.get('tenement_ids') or not record.get('complete_project_scope'):
        raise ValueError('OWN_ORIGINAL_COMPLETE_TENEMENT_SCOPE_REQUIRED')
    references=record.get('original_references',[])
    if not references:raise ValueError('OWN_ORIGINAL_REFERENCE_REQUIRED')
    bound={p.get('source_sha256') for p in trace if p.get('project_id')==project_id}
    all_quotes=[]
    for ref in references:
        if ref.get('source_sha256') not in bound:raise ValueError('ORIGINAL_NOT_BOUND_TO_PROJECT')
        raw=verified_bytes(repo,ref)
        page=ref.get('page');quote=ref.get('quote','')
        if not isinstance(page,int) or page<1 or not quote:raise ValueError('ORIGINAL_PAGE_QUOTE_REQUIRED')
        if raw.startswith(b'%PDF'):
            import fitz
            with fitz.open(stream=raw,filetype='pdf') as doc:
                if page>len(doc):raise ValueError('ORIGINAL_PAGE_OUT_OF_RANGE')
                text=doc[page-1].get_text()
        else:
            if page!=1:raise ValueError('NONPDF_REFERENCE_PAGE')
            text=raw.decode('utf-8-sig')
        normalize=lambda s:re.sub(r'\s+',' ',s).strip()
        if normalize(quote) not in normalize(text):raise ValueError('ORIGINAL_QUOTE_MISMATCH')
        all_quotes.append(quote)
    for identifier in record['tenement_ids']:
        if not re.search(r'(?<![A-Za-z0-9])'+re.escape(identifier)+r'(?![A-Za-z0-9])','\n'.join(all_quotes)):raise ValueError('TENEMENT_ID_NOT_IN_ORIGINAL_QUOTE')


def collect(rows,trace,decisions,repo,census=None):
    repo=Path(repo);cfg=json.loads((repo/'config/round4_tenements.json').read_text('utf8'))
    approved={d['decision_id']:d for d in decisions['decisions'] if d.get('decided_by')=='USER_EXPLICIT_APPROVAL'}
    decision=cfg['decision_id']
    if decision not in approved or approved[decision].get('rule')!='TENEMENT_CENTROID_RESEARCHER_APPROVED':raise ValueError('ROUND4_TENEMENT_APPROVAL_REQUIRED')
    log=json.loads((repo/cfg['request_log']).read_text('utf8'));stopped=set()
    for r in log:
        if r['state']=='TAS':raise ValueError('TAS_REQUEST_FORBIDDEN')
        if r['state'] in stopped:raise ValueError('REQUEST_AFTER_TARGET_STOPPED')
        verified_bytes(repo,r)
        if r.get('http_status')!=200 or r.get('status')=='STOPPED':stopped.add(r['state'])
    records={r['project_id']:r for r in cfg['projects']};fills=[];reviews=[];accepted=[]
    for row in rows:
        if row.get('緯度') or row.get('經度'):continue
        pid=row['專案ID'];record=records.get(pid);reason='NO_VERIFIED_OWN_ORIGINAL_TENEMENT_IDS';result={}
        from .official_location_adapters import native_state
        state=native_state(row.get('州省地區'))
        result['state_status']=cfg.get('state_status',{}).get(state,'UNKNOWN_STATE')
        if state=='TAS':reason='TAS_PRIOR_403_NO_ATTEMPT'
        if record:
            try:
                validate_original(record,pid,repo,trace)
                if record.get('review_only_reason'):
                    result.update(record.get('historical_title_conflict',{}))
                    raise ValueError(record['review_only_reason'])
                state=record['state']
                if state=='TAS':raise ValueError('TAS_PRIOR_403_NO_ATTEMPT')
                if state in stopped:raise ValueError('OFFICIAL_TARGET_STOPPED')
                dataset=cfg['datasets'][record['dataset']]
                if record.get('historical') and not dataset.get('historical'):raise ValueError('HISTORICAL_TENEMENT_LAYER_UNAVAILABLE')
                license_raw=verified_bytes(repo,dataset['license_evidence']).decode('utf8')
                if dataset['license_url'] not in license_raw:raise ValueError('LICENSE_EVIDENCE_MISSING')
                if not dataset.get('pagination_complete'):raise ValueError('TENEMENT_PAGINATION_INCOMPLETE')
                features,sha=verify_feature_pages(repo,dataset,log)
                field=dataset['id_field'];wanted=record['tenement_ids']
                chosen=[f for f in features if identifier_key(f['properties'][field]) in {identifier_key(i) for i in wanted}]
                if {identifier_key(f['properties'][field]) for f in chosen}!={identifier_key(i) for i in wanted}:raise ValueError('EXACT_TENEMENT_IDS_NOT_ALL_FOUND')
                if dataset.get('active_field') and any(f['properties'][dataset['active_field']] not in dataset['accepted_active_values'] for f in chosen):raise ValueError('TENEMENT_NOT_CURRENT_REQUIRES_HISTORICAL_REVIEW')
                result=centroid(chosen,dataset['source_crs'],cfg['precision_limit_m'],id_field=field);reason=result['reason']
                if result['accepted']:
                    holders=sorted({str(f['properties'].get(dataset['holder_field'],'')).strip() for f in chosen})
                    scope=dict(result,decision_id=decision,tenement_ids=wanted,official_tenement_ids=[f['properties'][field] for f in chosen],identifier_rule='TYPE_AND_INTEGER_COMPONENTS_ONLY_NO_NAME_MATCH',layer_sha256=sha,holders=holders,holder_mismatch=any(h!=row.get('開發商','') for h in holders),original_references=record['original_references'],feature_properties=[f['properties'] for f in chosen],scope_note='Tenement centroid, NOT mineral occurrence point; existing notes preserved')
                    for column,key in [('緯度','latitude'),('經度','longitude')]:
                        value=f'{result[key]:.7f}'
                        provenance=dict(project_id=pid,column=column,value=value,source_sha256=sha[0],source_url=dataset['endpoint'],locator='; '.join(wanted),method='ROUND4_TENEMENT_CENTROID_RESEARCHER_APPROVED',scope=json.dumps(scope,ensure_ascii=False,sort_keys=True),observation_ids='[]',review_ids=json.dumps([decision]),review_methods='["EXACT_TENEMENT_ID_MATCH"]',acquired_through=dataset['acquired_at'],source_kind='GOVERNMENT_SPATIAL_CATALOGUE',publication_date_role='DATASET_VERSION_NOT_MRE',resource_effective_date_unknown='True',public_release_date_unknown='True')
                        provenance.update(location_method=result['location_method'],precision_m=str(result['precision_m']),datum=result['input_datum'],tenement_ids=json.dumps(wanted),layer_sha256=json.dumps(sha),holders=json.dumps(holders,ensure_ascii=False),holder_mismatch=str(scope['holder_mismatch']))
                        fills.append(dict(project_id=pid,column=column,value=value,decision_id=decision,provenance=provenance))
                    accepted.append(dict(project_id=pid,project=row['專案名稱'],**scope));continue
            except (ValueError,KeyError,FileNotFoundError) as error:reason=str(error)
        reviews.append(dict(project_id=pid,project=row['專案名稱'],reason=reason,candidates='[]',details=json.dumps(result,ensure_ascii=False,sort_keys=True)))
    return fills,reviews,dict(tenement_centroids=accepted,request_count=len(log),stopped_states=sorted(stopped),centroid_rows=len(accepted),point_rows=sum(bool(r.get('緯度') and r.get('經度')) for r in rows),review_rows=len(reviews),tas_attempts=0,state_status=cfg.get('state_status',{}),source_backed_projects=len(records))

