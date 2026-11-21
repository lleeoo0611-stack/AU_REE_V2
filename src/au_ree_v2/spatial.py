"""Project-scoped, projected ArcGIS query windows with explicit coverage limits.

A window encloses the EPSG:3577 radius, and an inventory-complete ArcGIS
spatial query proves nearest proximity only when the returned distance is
strictly inside that radius. No legal road, rail or power access is inferred.
"""
import json
import statistics
from pathlib import Path
from pyproj import Transformer
from .store import filehash

_TO = Transformer.from_crs(4326, 3577, always_xy=True)
_FROM = Transformer.from_crs(3577, 4326, always_xy=True)

def bounding_window(lon, lat, radius_km):
    if not (110 <= lon <= 155 and -45 <= lat <= -9 and 0 < radius_km <= 1000):
        raise ValueError('Invalid project point or AOI radius')
    x, y = _TO.transform(lon, lat)
    r = radius_km * 1000.0
    samples = []
    # Sampling the boundary of a bounding square is deliberately conservative.
    for k in range(17):
        t = -r + 2 * r * k / 16
        samples.extend(((x-r, y+t), (x+r, y+t), (x+t, y-r), (x+t, y+r)))
    coords = [_FROM.transform(a, b) for a, b in samples]
    return [min(p[0] for p in coords), min(p[1] for p in coords),
            max(p[0] for p in coords), max(p[1] for p in coords)]

def project_windows(root, manifest, radius_km):
    """Only evidenced project-to-deposit anchors; do not equate deposits with projects."""
    root = Path(root)
    claims = json.loads((root/'data/claims.json').read_text(encoding='utf-8'))
    available = {}
    for s in manifest['snapshots']:
        if s['kind'] != 'arcgis_census':
            continue
        if s['key'] not in available or s['acquired_at'] > available[s['key']]['acquired_at']:
            available[s['key']] = s
    positions = {}
    for key, s in available.items():
        path = root/s['path']
        if filehash(path) != s['sha256']:
            raise ValueError('AOI anchor source checksum mismatch')
        data = json.loads(path.read_text(encoding='utf-8'))
        for f in data['features']:
            attrs = f['attributes']
            native = attrs.get(s['id_field'])
            if native is None:
                continue
            if isinstance(native, float) and native.is_integer():
                native=int(native)
            g = f.get('geometry') or {}
            lon = attrs.get('longitude', g.get('x'))
            lat = attrs.get('latitude', g.get('y'))
            if lon is not None and lat is not None:
                positions[(key, str(native))] = (float(lon), float(lat), s['sha256'])
    out = []
    for p in sorted(claims['projects'], key=lambda v: v['id']):
        anchor = positions.get((p.get('coordinate_source'), str(p.get('coordinate_native_id'))))
        if anchor is None:
            continue
        lon, lat, sha = anchor
        out.append({'project_id':p['id'], 'longitude':lon, 'latitude':lat,
                    'radius_km':radius_km, 'bbox':bounding_window(lon, lat, radius_km),
                    'coordinate_source_sha256':sha})
    if not out:
        raise ValueError('No source-anchored registered project coordinates; AOI acquisition refused: ' +
                         repr({'available':list(available),'position_count':len(positions),
                               'position_sample':list(positions)[:3],
                               'requested':[(p.get('coordinate_source'), str(p.get('coordinate_native_id')))
                                            for p in claims['projects']]}))
    return out

def covered_project(inventory, project_id, lon, lat):
    for q in inventory.get('queries', []):
        if (q.get('project_id') == project_id and
            abs(q['longitude'] - lon) < 1e-5 and abs(q['latitude'] - lat) < 1e-5):
            return q
    return None


# Integrated summary rules: reviewed functions, canonical evidence only.
import math
import re
from pyproj import CRS, Geod
from shapely.geometry import shape
from shapely.ops import transform, unary_union


def summary_identifier_key(value):
    """Type and numeric identifier only, preserving WA district; no name match."""
    value=re.sub(r'\s+','',str(value)).upper()
    match=re.fullmatch(r'([A-Z]+)(\d+)(?:/(\d+))?',value)
    if not match:return value
    return (match[1],int(match[2]),int(match[3]) if match[3] else None)

def summary_tenement_centroid(features, source_crs, limit_m=25000, id_field=None):
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
        key=summary_identifier_key(feature['properties'][id_field]) if id_field else index
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

def _arcgis_tenement_features(data, binding):
    """Read the selected polygons from a complete, dated native ArcGIS inventory."""
    from shapely import build_area
    from shapely.geometry import LinearRing, MultiLineString, mapping

    inventory = data.get('inventory', {})
    features = data.get('features', [])
    crs = data.get('spatialReference', {}).get('wkid')
    if (inventory.get('complete') is not True or inventory.get('count') != len(features)
            or inventory.get('scope') != 'global' or data.get('exceededTransferLimit')
            or CRS.from_user_input(binding['source_crs']).to_epsg() != crs):
        return []
    wanted = {summary_identifier_key(identifier) for identifier in binding['tenement_ids']}
    selected = []
    for feature in features:
        attributes = feature.get('attributes', {})
        if summary_identifier_key(attributes.get(binding['id_field'], '')) not in wanted:
            continue
        if any(attributes.get(key) != value for key, value in binding['required_attributes'].items()):
            return []
        rings = (feature.get('geometry') or {}).get('rings', [])
        if not rings or any(len(r) < 4 or r[0] != r[-1] or not LinearRing(r).is_valid for r in rings):
            return []
        lines = MultiLineString(rings)
        polygon = build_area(lines)
        if (polygon.geom_type not in ('Polygon', 'MultiPolygon') or not polygon.is_valid
                or not polygon.boundary.equals(lines)):
            return []
        selected.append(dict(properties=attributes, geometry=mapping(polygon)))
    return selected


def summary_read_shapefile_zip(raw,member):
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

def summary_assess_controls(controls):
    keys=[(c.get('nt_id',c.get('name')),c.get('ga_id',c.get('name'))) for c in controls]
    if len(set(keys))!=len(keys) or len({k[0] for k in keys})!=len(keys) or len({k[1] for k in keys})!=len(keys):return dict(accepted=False,reason='DUPLICATE_CONTROL_PAIR',controls=len(controls),errors={})
    if any(not all(math.isfinite(float(c[k])) for k in ('easting','northing','longitude','latitude')) for c in controls):return dict(accepted=False,reason='NONFINITE_CONTROL',controls=len(controls),errors={})
    if len(controls)<3:return dict(accepted=False,reason='FEWER_THAN_THREE_CONTROLS',controls=len(controls),errors={})
    errors={}
    for datum,code in [('GDA94',28300),('GDA2020',7800),('AGD66',20200)]:
        measured=[]
        for c in controls:
            zone=int(c['zone'])
            if zone not in (52,53,54):raise ValueError('NT_CONTROL_ZONE')
            x,y=Transformer.from_crs(code+zone,4283,always_xy=True,allow_ballpark=False).transform(float(c['easting']),float(c['northing']),errcheck=True)
            distance=Geod(ellps='GRS80').inv(x,y,float(c['longitude']),float(c['latitude']))[2]
            measured.append(dict(name=c['name'],distance_m=distance,longitude=x,latitude=y))
        errors[datum]=dict(median_m=statistics.median(v['distance_m'] for v in measured),maximum_m=max(v['distance_m'] for v in measured),points=measured)
    winners=[d for d,e in errors.items() if e['median_m']<50 and all(v['median_m']>150 for other,v in errors.items() if other!=d)]
    if len(winners)==1:return dict(accepted=True,datum=winners[0],qualifier='DATUM_EMPIRICALLY_SELECTED',controls=len(controls),errors=errors)
    if errors['GDA94']['median_m']<50 and errors['GDA2020']['median_m']<50 and errors['AGD66']['median_m']>150:
        differences=[Geod(ellps='GRS80').inv(a['longitude'],a['latitude'],b['longitude'],b['latitude'])[2] for a,b in zip(errors['GDA94']['points'],errors['GDA2020']['points'])]
        if max(differences)<=2.0:return dict(accepted=True,datum='GDA94',qualifier='DATUM_GDA94_OR_GDA2020_INDISTINGUISHABLE',controls=len(controls),gda94_gda2020_max_difference_m=max(differences),errors=errors)
    return dict(accepted=False,reason='DATUM_CONTROL_THRESHOLDS_NOT_MET',controls=len(controls),errors=errors)

def summary_location_name(value):
    value=re.sub(r'[‐‑‒–—−-]',' ',str(value).casefold())
    return re.sub(r'\s+(?:project|deposit)$','',' '.join(value.split())).strip()


def _resource_point_scope(case, row, government, sources, cutoff, lon, lat):
    """Replay the issuer figure used to review a native representative point."""
    import pymupdf
    from .census import summary_norm
    from .selection import date_end

    proof = case.get('issuer_scope_reference') or {}
    original = sources.get(proof.get('source_sha256'))
    if (not original or original['kind'] != 'pdf' or original['key'] != proof.get('source_key')
            or case.get('census_project_name') != row['專案名稱'] or not cutoff):
        return None
    available = government.get('available_date')
    published = original.get('publication_date')
    if not available or not published or max(date_end(available), date_end(published)) > cutoff:
        return None
    page = proof.get('physical_page')
    figure, caption, grid = proof.get('figure'), proof.get('caption'), proof.get('grid_epsg')
    if (type(page) is not int or page < 1 or not figure or not caption or not proof.get('review')
            or type(grid) is not int
            or (grid not in range(28349, 28357) and grid not in range(32749, 32757))):
        return None
    with pymupdf.open(original['resolved_path']) as document:
        if page > len(document):
            return None
        text = summary_norm(document[page - 1].get_text())
    if summary_norm(figure) not in text or summary_norm(caption) not in text:
        return None
    x, y = Transformer.from_crs(4283, grid, always_xy=True, allow_ballpark=False).transform(
        lon, lat, errcheck=True)
    return dict(proof, review_method='MANUAL_FIGURE_SCOPE_REVIEW',
                publication_date=published, government_available_date=available,
                easting_m=round(x), northing_m=round(y))


def summary_locations(row, all_rows, registry, sources, rules, decisions, *, read_json=None, cutoff=None,
                      extent_rejections=None):
    """Native pairs and exact tenement unions; no coordinate values in declarations."""
    from .census import summary_decision,summary_norm,summary_region_text
    from .selection import date_end
    from .store import canonical
    import io,csv,zipfile
    if read_json is None:
        def read_json(path):
            return json.loads(Path(path).read_text(encoding='utf8'))
    pid=row['專案ID'];fills=[]
    if row.get('緯度') or row.get('經度'):return fills
    approved={d.get('scope',{}).get('dataset'):d for d in decisions
        if d.get('rule')=='SELECT_OFFICIAL_LOCATION_DATASET' and isinstance(d.get('scope'),dict)}
    names={summary_location_name(row['專案名稱'])}
    alias_rows=rules['aliases.projects']
    names.update(summary_location_name(a['alias']) for p in alias_rows if p['project_id']==pid for a in p['aliases'])
    state=next((code for code,name in rules['states'].items() if name==row['州省地區']),None)
    options=[]
    def add(lon,lat,sha,method,locator,scope):
        if not all(math.isfinite(float(v)) for v in (lon,lat)) or not (110<=float(lon)<=155 and -45<=float(lat)<=-9):
            raise ValueError('SUMMARY_COORDINATE_RANGE')
        for column,value in [('緯度',lat),('經度',lon)]:
            fills.append(dict(column=column,value=value,sha=sha,locator=locator,method=method,scope=canonical(scope)))
    for registered in registry:
        frozen_tenure = rules.get('frozen_tenement_scopes', {}).get(registered.get('key'), {})
        sha=frozen_tenure.get('source_sha256') or registered.get('source_sha256');source=sources.get(sha)
        if frozen_tenure and source and source['key'] != registered['key']:
            continue
        if source is None and registered.get('hash_policy') == 'JSON_DROP_TOP_LEVEL_KEYS_V1':
            matches = [
                candidate for candidate in sources.values()
                if candidate['key'] == registered['key']
                and candidate.get('content_sha256') == sha
                and candidate.get('hash_policy') == registered['hash_policy']
                and candidate.get('hash_drop_keys') == registered.get('hash_drop_keys')
            ]
            if len(matches) == 1:
                source = matches[0]
                sha = source['sha256']
        if not source:continue
        bindings=[b for b in registered.get('summary_bindings',[]) if b['project_id']==pid]
        if bindings:
            data=read_json(source['resolved_path'])
            for b in bindings:
                case=b['binding'];hits=[f for f in data.get('features',[]) if (f.get('attributes') or {}).get('objectid')==b['feature_id']]
                if len(hits)!=1 or data.get('spatialReference',{}).get('wkid')!=4283 or data.get('exceededTransferLimit'):
                    continue
                a=hits[0]['attributes'];g=hits[0].get('geometry',{})
                if a.get('projectname')!=case['source_project_name'] or a.get('state')!=case['state'] or '150802' not in str(a.get('source','')):continue
                named_binding=case.get('census_project_name')
                if (summary_location_name(a['projectname']) not in names and
                        (not named_binding or summary_location_name(named_binding)!=
                         summary_location_name(row['專案名稱']))):
                    continue
                if not re.search(r'\bREE\b|rare earth|monazite|xenotime',str(a.get('commodities','')),re.I):
                    proof=case.get('ree_hms_material_proof');original=sources.get((proof or {}).get('sha256'))
                    if not proof or not original:continue
                    import pymupdf,hashlib
                    with pymupdf.open(original['resolved_path']) as doc:
                        text=summary_norm(summary_region_text(doc[proof['page']-1],pymupdf.Rect(proof['bbox'])))
                    if hashlib.sha256(text.encode()).hexdigest()!=proof['statement_sha256']:continue
                    if not re.search(r'\bree\b|rare earth|monazite|xenotime',text):continue
                lon,lat=a.get('longitude'),a.get('latitude')
                if not isinstance(lon,(int,float)) or not isinstance(lat,(int,float)) or abs(lon-g.get('x',float('inf')))>1e-6 or abs(lat-g.get('y',float('inf')))>1e-6:continue
                scope=dict(dataset='GA2025',datum='GDA94',feature_id=b['feature_id'],meaning='REPRESENTATIVE_POINT_NOT_BOUNDARY')
                if case.get('scope_match') == 'NAMED_DEPOSIT_WITHIN_SELECTED_RESOURCE':
                    reference = _resource_point_scope(case, row, source, sources, cutoff, lon, lat)
                    if not reference:
                        continue
                    scope['issuer_scope_reference'] = reference
                add(round(lon,rules['ga_display_digits']),round(lat,rules['ga_display_digits']),sha,b['rule'],
                    'native feature objectid='+str(b['feature_id']),scope)
            if fills:return fills
        tenements = [*registered.get('summary_tenements', []), *frozen_tenure.get('bindings', [])]
        if tenements:
            for b in tenements:
                if b['project_id']!=pid or not b['complete_project_scope'] or not summary_decision(decisions,'TENEMENT_CENTROID_RESEARCHER_APPROVED'):continue
                import pymupdf
                valid=True
                for proof in b['original_references']:
                    original=sources.get(proof['source_sha256'])
                    if not original:valid=False;break
                    if frozen_tenure and (not cutoff or original.get('kind') != 'pdf'
                            or not original.get('publication_date') or date_end(original['publication_date']) > cutoff):
                        valid=False;break
                    if original['kind']=='pdf':
                        with pymupdf.open(original['resolved_path']) as doc:
                            if not 1 <= proof['page'] <= len(doc):valid=False;break
                            text=doc[proof['page']-1].get_text()
                    else:text=Path(original['resolved_path']).read_text(encoding='utf8')
                    if summary_norm(proof['quote']) not in summary_norm(text):valid=False;break
                if not valid:continue
                raw=Path(source['resolved_path']).read_bytes()
                if frozen_tenure:
                    if not cutoff or not source.get('available_date') or source['available_date'] > cutoff:
                        continue
                    features = _arcgis_tenement_features(json.loads(raw), b)
                elif b.get('zip_member'):features,crs=summary_read_shapefile_zip(raw,b['zip_member'])
                else:
                    data=json.loads(raw);features=data.get('features',[])
                    if str(data.get('numberMatched'))!=str(len(features)):continue
                wanted={summary_identifier_key(i) for i in b['tenement_ids']};field=b.get('id_field') or 'tno'
                chosen=[f for f in features if summary_identifier_key(f['properties'].get(field,'')) in wanted]
                if {summary_identifier_key(f['properties'][field]) for f in chosen}!=wanted:continue
                result=summary_tenement_centroid(chosen,b['source_crs'],rules['tenement_precision_m'],field)
                if result['accepted']:
                    scope = dict(result, tenement_ids=b['tenement_ids'],
                                 holders=[f['properties'].get(b.get('holder_field','own_name')) for f in chosen],
                                 meaning='TENEMENT_REPRESENTATIVE_POINT_NOT_RESOURCE_BOUNDARY')
                    if frozen_tenure:
                        scope.update(dataset=registered['key'], feature_id=b['required_attributes']['permitid'],
                                     scope_references=b['original_references'], scope_review=b['scope_review'],
                                     government_available_date=source['available_date'])
                    add(result['longitude'],result['latitude'],sha,'ROUND4_TENEMENT_CENTROID_RESEARCHER_APPROVED',
                        '; '.join(b['tenement_ids']),scope)
                elif extent_rejections is not None and result['reason'] == 'TENEMENT_UNION_EXCEEDS_25KM':
                    extent_rejections.append(dict(kind='TENEMENT_CENTROID_REVIEW', reason=result['reason'],
                        source_key=registered['key'], source_sha256=sha, tenement_ids=b['tenement_ids'],
                        precision_m=result['precision_m'], limit_m=rules['tenement_precision_m']))
            if fills:return fills
        dataset=next((key for key,cfg in rules['government_datasets'].items() if source['url'].startswith(cfg['url'])),None)
        if not dataset or dataset not in approved:continue
        if dataset=='NT_STRIKE':
            if state!='NT' or 'uro' in summary_norm(row['開發商']) or not summary_decision(decisions,'NT_DATUM_FROM_ARCHIVED_CONTROL_POINTS'):continue
            with zipfile.ZipFile(source['resolved_path']) as z:
                native=list(csv.DictReader(io.StringIO(z.read('MINERALOCCURRENCES.csv').decode('utf-8-sig'))))
            matches=[n for n in native if summary_location_name(n['NAME']) in names and re.search(r'REE|rare earth|monazite|xenotime',n['COM_MAJOR']+' '+n['COM_MINOR'],re.I)]
            if len(matches)!=1:continue
            native_by_name={}
            for n in native:
                native_by_name.setdefault(summary_location_name(n['NAME']),[]).append(n)
            controls=[]
            for other in sources.values():
                if not other['url'].startswith(rules['government_datasets']['GA_OZMIN']['url']):continue
                data=read_json(other['resolved_path'])
                for f in data.get('features',[]):
                    a=f.get('properties') or f.get('attributes') or {}
                    paired=native_by_name.get(summary_location_name(a.get('OCCURRENCE_NAME','')),[])
                    if a.get('STATE')=='NT' and len(paired)==1:
                        n=paired[0];controls.append(dict(name=n['NAME'],nt_id=n['MODAT_ID'],ga_id=a['ENO'],easting=n['EASTING'],northing=n['NORTHING'],zone=n['ZONE_MGA'],longitude=a['LONG_GDA94'],latitude=a['LAT_GDA94']))
            result=summary_assess_controls(controls)
            if result['accepted']:
                n=matches[0];code=28300 if result['datum']=='GDA94' else 7800
                x,y=Transformer.from_crs(code+int(n['ZONE_MGA']),7844,always_xy=True,allow_ballpark=False).transform(float(n['EASTING']),float(n['NORTHING']),errcheck=True)
                add(x,y,sha,'ROUND3_OFFICIAL_POINT_RESEARCHER_APPROVED','MINERALOCCURRENCES.csv; feature '+n['MODAT_ID'],dict(dataset=dataset,datum_control=result,feature_id=n['MODAT_ID']))
            continue
        cfg=rules['government_datasets'][dataset]
        if cfg['kind'] not in ('arcgis','wfs'):continue
        data=read_json(source['resolved_path'])
        if data.get('exceededTransferLimit') or data.get('error'):continue
        points=[b for b in registered.get('summary_official_point_bindings',[])
                if b['project_id']==pid and b['census_project_name']==row['專案名稱']]
        if len(points)>1:continue
        point=points[0] if points else None
        features=data.get('features',[])
        if point:
            features=[f for f in features if str((f.get('attributes') or f.get('properties') or {}).get(cfg['id']))==point['feature_id']]
            if len(features)!=1:continue
        for f in features:
            a=f.get('attributes') or f.get('properties') or {}
            commodity='; '.join(str(a.get(k) or '') for k in cfg['commodity'])
            if not re.search(r'\bREE\b|rare\s*earth|monazite|xenotime',commodity,re.I):continue
            labels=[v.strip() for key in cfg['names'] for v in re.split('[;|]',str(a.get(key) or '')) if v.strip()]
            title=str(a.get('proj_title') or '');title_name,sep,operator=title.partition(' / ')
            if sep:labels=[title_name if v==title else v for v in labels]
            native_names={summary_location_name(v) for v in labels}
            if point and point['official_name'] not in labels:continue
            if not point and not names.intersection(native_names):continue
            native_state=a.get(cfg.get('state_field')) if cfg.get('state_field') else cfg.get('state')
            if native_state!=state:continue
            owner=lambda v:re.sub(r'\s+(?:limited|ltd\.?|nl)\s*$','',summary_norm(v))
            if operator and owner(operator)!=owner(row['開發商']):continue
            if dataset=='WA_MINEDEX' and not operator and not summary_decision(decisions,'NO_OPERATOR_VALUE'):continue
            if 'uro' in owner(row['開發商']) and 'charley creek' in summary_location_name(row['專案名稱']):continue
            competing={p['project_id'] for p in alias_rows if p['project_id']!=pid and any(summary_location_name(x['alias']) in native_names for x in p['aliases'])}
            if competing and not (point and operator) and not (summary_decision(decisions,'SHARED_DEPOSIT_POINT_RESEARCHER_APPROVED') and 'yttria' in native_names):continue
            lon,lat=a.get(cfg['lon']),a.get(cfg['lat'])
            if isinstance(lon,bool) or isinstance(lat,bool) or lon in (None,'') or lat in (None,''):continue
            x,y=Transformer.from_crs(cfg['crs'],7844,always_xy=True,allow_ballpark=False).transform(float(lon),float(lat),errcheck=True)
            if point:
                digits=rules['point_display_digits']
                add(format(x,'.'+str(digits)+'g'),format(y,'.'+str(digits)+'g'),sha,
                    'REVIEWED_OFFICIAL_PROJECT_FEATURE',dataset+'; feature '+point['feature_id'],
                    dict(dataset=dataset,feature_id=point['feature_id'],datum=cfg['crs'],
                         official_name=point['official_name'],meaning='REPRESENTATIVE_POINT_NOT_BOUNDARY'))
                return fills
            options.append(dict(longitude=x,latitude=y,sha=sha,dataset=dataset,feature_id=str(a.get(cfg['id'])),
                group=str(a.get('proj_code') or title or a.get(cfg['id'])),names=labels,datum=cfg['crs']))
    distinct={(o['dataset'],o['group'],o['feature_id']) for o in options}
    if len(distinct)==1 and summary_decision(decisions,'NORMALIZED_NAME_MATCH'):
        c=options[0];digits=rules['point_display_digits']
        add(format(c['longitude'],'.'+str(digits)+'g'),format(c['latitude'],'.'+str(digits)+'g'),c['sha'],
            'NORMALIZED_NAME_MATCH',c['dataset']+'; feature '+c['feature_id'],dict(c,distance_check='NO_VERIFIED_DISTANCE_COMPARATOR'))
    return fills
