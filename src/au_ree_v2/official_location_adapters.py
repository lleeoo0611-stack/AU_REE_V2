"""Approval-gated official occurrence locations; never resource geometry or identity merges.

All transports are bounded, official-endpoint-only and stop on first refusal.
The default decision configuration performs zero network requests.
"""
import csv
import hashlib
import io
import json
import math
import re
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode, urlsplit, parse_qs

from pyproj import Geod, Transformer

RULE = 'SELECT_OFFICIAL_LOCATION_DATASET'
ROLE = 'OFFICIAL_OCCURRENCE_REPRESENTATIVE_POINT'
STATES = {'Western Australia':'WA','Northern Territory':'NT','Queensland':'QLD',
          'South Australia':'SA','Victoria':'VIC','Tasmania':'TAS','New South Wales':'NSW',
          '西澳':'WA','北領地':'NT','昆士蘭':'QLD','南澳':'SA','維多利亞':'VIC','塔斯馬尼亞':'TAS','新南威爾斯':'NSW'}
REE = re.compile(r'\bREE\b|rare\s*earth|monazite|xenotime', re.I)
DATASETS = {
 'WA_MINEDEX': dict(kind='arcgis',url='https://public-services.slip.wa.gov.au/public/rest/services/SLIP_Public_Services/Industry_and_Mining_WFS/MapServer/0',layer='0',state='WA',id='site_code',names=['site_title','short_name','proj_title'],commodity=['site_commo','commodity'],lon='longitude',lat='latitude',crs=7844,accuracy='point_conf',accuracy_unit='SOURCE_TEXT_NOT_METRES',method=None,date='extract_da',license='https://catalogue.data.wa.gov.au/dataset/minedex-dmirs-001'),
 'GA_OZMIN': dict(kind='wfs',url='https://services.ga.gov.au/gis/earthresource/ows',layer='ama:MineralOccurrences',state=None,state_field='STATE',id='ENO',names=['OCCURRENCE_NAME','PROJECT'],commodity=['COMMODITY_CODES','COMMODITY_NAMES'],lon='LONG_GDA94',lat='LAT_GDA94',crs=4283,accuracy='ACCURACY_M',accuracy_unit='m',method=None,date=None,license='https://dev.ecat.ga.gov.au/geonetwork/srv/api/records/7fb71158-fc8b-4de6-af81-ae8afcaea1da'),
 'SA_SARIG': dict(kind='wfs',url='https://services.sarig.sa.gov.au/vector/mines_and_mineral_deposits/wfs',layer='mines_and_mineral_deposits:all_mines_and_mineral_deposits',state='SA',id='MINERAL_DEPOSIT_NO',names=['DEPOSIT_NAME','DEPOSIT_SYNONYMS'],commodity=['DEPOSIT_COMMODITIES'],lon='LONGITUDE',lat='LATITUDE',crs=7844,accuracy='HORIZ_ACCURACY',accuracy_unit='UNVERIFIED_NATIVE_UNIT',method='SVY_METHOD_HORIZ',date=None,license='https://www.energymining.sa.gov.au/industry/geological-survey/products-and-services/map-viewers-databases-and-services/data-services'),
 'QLD_MINOCC': dict(kind='arcgis',url='https://spatial-gis.information.qld.gov.au/arcgis/rest/services/GeoscientificInformation/MiningResources/MapServer/12',layer='12',state='QLD',id='site_no',names=['occur_name','site_locality'],commodity=['main_commodity','all_commodities'],lon='longitude',lat='latitude',crs=4283,geometry_crs=3857,accuracy='loc_accuracy',accuracy_unit='m',method='loc_method',date='date_current',license='https://www.data.qld.gov.au/dataset/queensland-resource-web-map-service-json'),
 'NSW_MINVIEW': dict(kind='wfs',url='https://public-gs.geoscience.nsw.gov.au/geoserver/ows',layer='mineral-occurrence:mineral_occurrence',state='NSW',id='occurrence_id',names=['deposit_name','all_names'],commodity=['major_comm','minor_comm'],lon='longda94',lat='latgda94',crs=4283,accuracy='accuracy',accuracy_unit='UNVERIFIED_NATIVE_UNIT',method='loc_method',date=None,license='https://www.resources.nsw.gov.au/geological-survey/minview'),
 'NT_STRIKE': dict(kind='zip_report_only',url='https://strike.nt.gov.au/link/https://geoscience.nt.gov.au/contents/prod/Downloads/Mineral_Deposits/MINERALOCCURRENCES_csv.zip',layer='CSV_SCHEMA_UNVERIFIED',state='NT',license='https://www.ntlis.nt.gov.au/metadata/export_data?metadata_id=FA9776DB9DFB9746E040CD9B2144298B&type=html'),
}
for key, layer in [('SA_PROJECTS_MAJOR','major_mines___minerals'),('SA_PROJECTS_DEVELOPING','developing_projects___minerals')]:
    DATASETS[key] = dict(kind='wfs_linked',url='https://services.sarig.sa.gov.au/vector/south_australia_mining_projects/wfs',layer='south_australia_mining_projects:'+layer,state='SA',id='MINERAL_DEPOSIT_NUMBER',names=['PROJECT_NAME'],commodity=[],lon='LONGITUDE',lat='LATITUDE',crs=None,accuracy=None,accuracy_unit='UNVERIFIED_NATIVE_UNIT',method=None,date=None,license=DATASETS['SA_SARIG']['license'])


def proposed_decisions():
    return [dict(decision_id='official-location-'+key.lower()+'-20261111',rule=RULE,
                 scope={'dataset':key,'layer':cfg['layer']},decided_by=None,decided_date='2026-11-11',
                 notes='政府位置資料集選擇；NT 僅欄位報告；SA projects 僅關聯輔助，CRS 未核實不得填值。')
            for key,cfg in DATASETS.items()]


def decision_for(dataset, decisions):
    entries=decisions.get('decisions',[]) if isinstance(decisions,dict) else decisions
    if not isinstance(entries,list):raise ValueError('LOCATION_DECISION_REGISTRY_INVALID')
    for d in entries:
        if isinstance(d,dict) and d.get('rule')==RULE and not isinstance(d.get('scope'),dict):
            raise ValueError('LOCATION_DECISION_SCOPE_INVALID')
    hits=[d for d in entries if isinstance(d,dict) and d.get('rule')==RULE and d.get('scope',{}).get('dataset')==dataset
          and d.get('scope',{}).get('layer')==DATASETS[dataset]['layer']]
    if len(hits)>1:raise ValueError('LOCATION_DUPLICATE_DECISION')
    if not hits or not isinstance(hits[0].get('decided_by'),str) or not hits[0]['decided_by'].strip():return None
    d=hits[0]
    if not d.get('decision_id') or not d.get('decided_date'):raise ValueError('LOCATION_DECISION_INCOMPLETE')
    datetime.fromisoformat(d['decided_date'])
    return d


def normalized_name(value):
    value=re.sub(r'[‐‑‒–—−-]',' ',str(value).casefold())
    value=' '.join(value.split())
    return re.sub(r'\s+(?:project|deposit)$','',value).strip()


def native_state(value):
    value=str(value or '').strip()
    return STATES.get(value, value.upper())


def commodity_filter(fields,dialect="sql"):
    if dialect=="cql":
        return "("+" OR ".join(field+" ILIKE '%"+term+"%'" for field in fields for term in ("REE","RARE EARTH","MONAZITE","XENOTIME"))+")"
    # Only documented text fields; unknown commodity codes never inferred.
    return '('+' OR '.join("UPPER("+field+") LIKE '%"+term+"%'" for field in fields
        for term in ('REE','RARE EARTH','MONAZITE','XENOTIME'))+')'


def _attributes(feature):
    return feature.get('attributes',feature.get('properties',{}))


def normalize_feature(dataset, feature, receipt):
    cfg=DATASETS[dataset]
    if cfg['kind'] in ('zip_report_only','wfs_linked'):raise ValueError('LOCATION_SCHEMA_OR_DATUM_NOT_VERIFIED')
    a=_attributes(feature);fid=a.get(cfg['id'])
    if fid in (None,''):raise ValueError('LOCATION_NATIVE_ID_MISSING')
    commodity='; '.join(str(a.get(f) or '') for f in cfg['commodity'])
    if not REE.search(commodity):raise ValueError('LOCATION_REE_COMMODITY_NOT_CONFIRMED')
    # Never use geometry as a fallback. QLD geometry is Web Mercator while
    # its attribute pair is GDA94; NSW geometry is likewise a separate CRS.
    raw=[a.get(cfg['lon']),a.get(cfg['lat'])]
    if any(isinstance(v,bool) or v in (None,'') for v in raw):raise ValueError('LOCATION_PAIR_REQUIRED')
    lon,lat=map(float,raw)
    if not all(math.isfinite(v) for v in (lon,lat)) or not (110<=lon<=155 and -45<=lat<=-9):raise ValueError('LOCATION_COORDINATE_RANGE')
    if dataset=='NSW_MINVIEW' and a.get('ll_coordsys') and not re.search('GDA.?94|4283',str(a['ll_coordsys']),re.I):raise ValueError('LOCATION_ATTRIBUTE_DATUM_CONFLICT')
    transformer=Transformer.from_crs(cfg['crs'],7844,always_xy=True,allow_ballpark=False)
    x,y=transformer.transform(lon,lat,errcheck=True)
    if not all(math.isfinite(v) for v in (x,y)):raise ValueError('LOCATION_TRANSFORMATION_FAILED')
    names=[]
    for field in cfg['names']:
        for name in re.split(r'[;|]',str(a.get(field) or '')):
            if name.strip():names.append(name.strip())
    if not names:raise ValueError('LOCATION_NAMES_MISSING')
    for required in ('sha256','acquired_at','url'):
        if not receipt.get(required):raise ValueError('LOCATION_RECEIPT_INCOMPLETE')
    return dict(dataset=dataset,layer=cfg['layer'],feature_id=str(fid),names=names,
        state=native_state(a.get(cfg.get('state_field')) if cfg.get('state_field') else cfg['state']),
        commodity=commodity,longitude=x,latitude=y,source_sha256=receipt['sha256'],
        source_url=receipt['url'],acquired_at=receipt['acquired_at'],
        source_version=receipt.get('source_version'),source_update=a.get(cfg['date']) if cfg.get('date') else None,
        original_longitude=raw[0],original_latitude=raw[1],original_crs='EPSG:'+str(cfg['crs']),
        output_crs='EPSG:7844',coordinate_source='ATTRIBUTES_ONLY',
        transformation=transformer.description,position_role=ROLE,
        measurement_method=a.get(cfg['method']) if cfg.get('method') else None,
        accuracy=a.get(cfg['accuracy']) if cfg.get('accuracy') else None,accuracy_unit=cfg['accuracy_unit'],
        license='CC BY 4.0',license_url=cfg['license'],
        temporal_role='DATASET_LOCATION_NOT_MRE_EFFECTIVE_DATE')


def match_project(row,candidates,aliases=(),reference=None,max_distance_m=None):
    if row.get('緯度') or row.get('經度'):return dict(status='EXISTING_PAIR_UNCHANGED',candidates=[])
    names={normalized_name(n) for n in [row['專案名稱'],*aliases]}
    # Resource-subscope labels may use an explicitly provided project alias,
    # but are never stripped to manufacture a matching identity.
    state=native_state(row.get('州省地區'))
    named=[c for c in candidates if names.intersection(normalized_name(n) for n in c['names'])]
    matches=[c.copy() for c in named if c['state']==state]
    if not matches:return dict(status='STATE_MISMATCH' if named else 'NO_EXACT_NAME_MATCH',candidates=named)
    if len(matches)!=1:return dict(status='MULTIPLE_CANDIDATES',candidates=matches)
    c=matches[0]
    if reference is not None:
        if max_distance_m is None or max_distance_m<=0:return dict(status='DISTANCE_THRESHOLD_REQUIRES_REVIEW',candidates=matches)
        _,_,distance=Geod(ellps='GRS80').inv(reference[0],reference[1],c['longitude'],c['latitude'])
        c['distance_m']=distance
        if distance>max_distance_m:return dict(status='DISTANT_FROM_VERIFIED_REFERENCE',candidates=matches)
    return dict(status='AUTO_MATCHED_OFFICIAL_POINT',candidates=matches)


def acquire_dataset(dataset,decisions,snapshot_dir,fetch=None,page_size=500,max_records=100000,linked_deposit_ids=()):
    """Acquisition stops on any denial/invalid page; no partial inventory admission."""
    cfg=DATASETS[dataset];decision=decision_for(dataset,decisions)
    if decision is None:return dict(dataset=dataset,status='DISABLED_UNAPPROVED',network_requests=0,features=[],receipts=[])
    if not 1<=page_size<=1000 or not 1<=max_records<=200000:raise ValueError('LOCATION_INVALID_BUDGET')
    from .acquisition import request
    transport=fetch or request
    directory=Path(snapshot_dir);directory.mkdir(parents=True,exist_ok=True)
    receipts=[];calls=0
    def get(url,params):
        nonlocal calls
        # URL is constructed only from the static document-verified registry.
        hosts={urlsplit(cfg['url']).hostname}
        if cfg['kind']=='zip_report_only':hosts.add('geoscience.nt.gov.au')
        calls+=1
        raw,headers=transport(url,params=params,allowed_hosts=hosts,max_attempts=1,
            min_interval=.25,max_bytes=32*1024*1024,max_redirects=0 if cfg['kind']!='zip_report_only' else 2)
        sha=hashlib.sha256(raw).hexdigest();dest=directory/(sha+'.bin')
        if dest.exists() and dest.read_bytes()!=raw:raise ValueError('LOCATION_SNAPSHOT_COLLISION')
        if not dest.exists():dest.write_bytes(raw)
        receipt=dict(sha256=sha,acquired_at=datetime.now(timezone.utc).isoformat(),
            url=url+('?' + urlencode(params) if params else ''),dataset=dataset,layer=cfg['layer'],
            source_version=headers.get('Last-Modified') or headers.get('ETag'),path=str(dest),
            decision_id=decision['decision_id'])
        receipts.append(receipt)
        (directory/(sha+'.receipt.json')).write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
        return raw
    if cfg['kind']=='zip_report_only':
        raw=get(cfg['url'],{});report=[]
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            for info in z.infolist():
                if not info.filename.lower().endswith('.csv'):continue
                if info.file_size>32*1024*1024:raise ValueError('LOCATION_ZIP_MEMBER_BUDGET')
                data=z.read(info);reader=csv.reader(io.StringIO(data.decode('utf-8-sig')))
                report.append(dict(member=info.filename,columns=next(reader,[]),sha256=hashlib.sha256(data).hexdigest()))
        return dict(dataset=dataset,status='SCHEMA_REPORT_ONLY',network_requests=calls,features=[],receipts=receipts,field_report=report)
    if cfg['kind']=='wfs_linked':
        ids=sorted(set(str(x) for x in linked_deposit_ids))
        if not ids or any(not re.fullmatch(r'[0-9]+',x) for x in ids):raise ValueError('LOCATION_SA_LINKED_REE_IDS_REQUIRED')
        where=cfg['id']+' IN ('+','.join(ids)+')'
    else:where=commodity_filter(cfg['commodity'],dialect='sql' if cfg['kind']=='arcgis' else 'cql')
    features=[];seen=set();total=None
    while total is None or len(features)<total:
        if cfg['kind']=='arcgis':
            params=dict(f='json',where=where,outFields='*',returnGeometry='true',
                resultOffset=len(features),resultRecordCount=page_size,orderByFields=cfg['id'])
            url=cfg['url']+'/query'
        else:
            params=dict(service='WFS',version='2.0.0',request='GetFeature',typeNames=cfg['layer'],
                outputFormat='application/json',count=page_size,startIndex=len(features),sortBy=cfg['id'],CQL_FILTER=where)
            url=cfg['url']
        data=json.loads(get(url,params))
        if data.get('error') or not isinstance(data.get('features'),list):raise ValueError('LOCATION_SERVICE_ERROR_OR_SCHEMA')
        page=data['features']
        announced=data.get('numberMatched',data.get('totalFeatures'))
        if announced is not None and str(announced).isdigit():
            if total is not None and total!=int(announced):raise ValueError('LOCATION_INVENTORY_CHANGED')
            total=int(announced)
            if total>max_records:raise ValueError('LOCATION_RECORD_BUDGET')
        for feature in page:
            fid=_attributes(feature).get(cfg['id'])
            if fid is None or str(fid) in seen:raise ValueError('LOCATION_DUPLICATE_OR_MISSING_ID')
            seen.add(str(fid));features.append(dict(feature=feature,receipt=receipts[-1]))
        if len(features)>max_records:raise ValueError('LOCATION_RECORD_BUDGET')
        if cfg['kind']=='arcgis' and data.get('exceededTransferLimit') is False:total=len(features)
        elif cfg['kind']=='arcgis' and not page and data.get('exceededTransferLimit') is not True:total=len(features)
        elif total is None and cfg['kind']!='arcgis':raise ValueError('LOCATION_COMPLETE_COUNT_REQUIRED')
        if not page and len(features)!=total:raise ValueError('LOCATION_INCOMPLETE_PAGE')
    if len(features)!=total:raise ValueError('LOCATION_COUNT_MISMATCH')
    return dict(dataset=dataset,status='COMPLETE',network_requests=calls,features=features,receipts=receipts,
                inventory={'complete':True,'count':total,'filter':where},decision_id=decision['decision_id'])


def build_location_candidates(acquisitions,decisions):
    candidates=[];queue=[]
    for result in acquisitions:
        dataset=result['dataset'];decision=decision_for(dataset,decisions)
        if not decision or result.get('status')!='COMPLETE' or not result.get('inventory',{}).get('complete'):continue
        result=verify_acquisition_snapshots(result,decisions)
        for item in result['features']:
            try:
                c=normalize_feature(dataset,item['feature'],item['receipt']);c['decision_id']=decision['decision_id'];candidates.append(c)
            except (ValueError,TypeError,KeyError) as exc:
                queue.append(dict(dataset=dataset,reason=str(exc),feature=_attributes(item['feature'])))
    return candidates,queue

STATES.update({'西澳大利亞州':'WA','南澳大利亞州':'SA','昆士蘭州':'QLD','新南威爾斯州':'NSW','維多利亞州':'VIC','塔斯馬尼亞州':'TAS','北領地':'NT'})


def validate_candidate_pair(row,candidate,decisions,all_candidates,aliases=(),verified_reference=None):
    """Independent paired-datum/scope validator; does not weaken legacy GA guards."""
    decision=decision_for(candidate['dataset'],decisions)
    if not decision or candidate.get('decision_id')!=decision['decision_id']:raise ValueError('LOCATION_APPROVAL_REQUIRED')
    if candidate.get('position_role')!=ROLE or candidate.get('output_crs')!='EPSG:7844':raise ValueError('LOCATION_DATUM_OR_ROLE')
    ref=validate_reference(verified_reference) if verified_reference is not None else None
    result=match_project(row,all_candidates,aliases,reference=(ref['longitude'],ref['latitude']) if ref else None,max_distance_m=ref['max_distance_m'] if ref else None)
    if result['status']!='AUTO_MATCHED_OFFICIAL_POINT':raise ValueError('LOCATION_PAIR_'+result['status'])
    checked=result['candidates'][0]
    if {k:v for k,v in checked.items() if k!='distance_m'}!={k:v for k,v in candidate.items() if k!='distance_m'}:raise ValueError('LOCATION_PAIR_MATCH_NOT_UNIQUE')
    candidate=dict(checked,distance_check='WITHIN_EXPLICIT_VERIFIED_THRESHOLD' if ref else 'NO_VERIFIED_DISTANCE_COMPARATOR')
    if ref:candidate['distance_reference']={k:v for k,v in ref.items() if k!='source_path'}
    return [dict(column=column,value=candidate[field],method='AUTO_MATCHED_OFFICIAL_POINT',
        source_sha=candidate['source_sha256'],source_url=candidate['source_url'],
        scope=json.dumps(candidate,ensure_ascii=False,sort_keys=True),
        locator=candidate['layer']+'; feature '+candidate['feature_id']+'; '+ROLE,
        decision_id=decision['decision_id']) for column,field in [('緯度','latitude'),('經度','longitude')]]


def verify_acquisition_snapshots(result,decisions=None):
    """Rebuild the entire inventory from every raw page, never from selected rows.

    Pagination, query/filter and terminal evidence are checked against raw bytes.
    Removing a competing feature or a page cannot manufacture unique matches.
    """
    if result.get('status')!='COMPLETE':return result
    dataset=result['dataset'];cfg=DATASETS[dataset]
    if cfg['kind']=='zip_report_only':raise ValueError('LOCATION_NT_CANNOT_BE_COMPLETE_POINTS')
    inventory=result.get('inventory',{});receipts=result.get('receipts')
    if not inventory.get('complete') or not isinstance(receipts,list) or not receipts:raise ValueError('LOCATION_INCOMPLETE_ACQUISITION')
    decision=decision_for(dataset,decisions) if decisions is not None else None
    expected_decision=decision['decision_id'] if decision else result.get('decision_id')
    if not expected_decision or (decisions is not None and not decision):raise ValueError('LOCATION_APPROVAL_REQUIRED')
    if result.get('decision_id')!=expected_decision:raise ValueError('LOCATION_RECEIPT_DECISION')
    if result.get('network_requests')!=len(receipts):raise ValueError('LOCATION_RECEIPT_PAGE_COUNT')
    expected_where=commodity_filter(cfg['commodity'],dialect='sql' if cfg['kind']=='arcgis' else 'cql') if cfg['kind']!='wfs_linked' else inventory.get('filter')
    if cfg['kind']=='wfs_linked' and not re.fullmatch(re.escape(cfg['id'])+r' IN \([0-9]+(?:,[0-9]+)*\)',str(expected_where)):
        raise ValueError('LOCATION_LINKED_FILTER_INVALID')
    if inventory.get('filter')!=expected_where:raise ValueError('LOCATION_FILTER_CHANGED')
    rebuilt=[];seen=set();total=None;size=None;terminal=False
    for index,receipt in enumerate(receipts):
        if terminal:raise ValueError('LOCATION_PAGE_AFTER_TERMINAL')
        if (receipt.get('dataset')!=dataset or receipt.get('layer')!=cfg['layer']
            or receipt.get('decision_id')!=expected_decision):raise ValueError('LOCATION_RECEIPT_SCOPE')
        snapshot=Path(receipt['path'])
        if not snapshot.is_absolute():
            repo=Path(__file__).resolve().parents[2];snapshot=(repo/snapshot).resolve()
            if not snapshot.is_relative_to(repo):raise ValueError('LOCATION_SNAPSHOT_PATH_ESCAPE')
        archived_receipt=json.loads(snapshot.with_suffix('.receipt.json').read_text('utf8'))
        if archived_receipt!=receipt:raise ValueError('LOCATION_ARCHIVED_RECEIPT_MISMATCH')
        raw=snapshot.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=receipt['sha256']:raise ValueError('LOCATION_SNAPSHOT_HASH')
        url=urlsplit(receipt['url']);base=urlsplit(cfg['url']+('/query' if cfg['kind']=='arcgis' else ''))
        if (url.scheme,url.netloc,url.path,url.fragment)!=(base.scheme,base.netloc,base.path,''):raise ValueError('LOCATION_SNAPSHOT_ENDPOINT')
        query=parse_qs(url.query,keep_blank_values=True)
        size_key='resultRecordCount' if cfg['kind']=='arcgis' else 'count'
        try:page_size=int(query[size_key][0])
        except (KeyError,ValueError,IndexError):raise ValueError('LOCATION_PAGE_SIZE_INVALID')
        if not 1<=page_size<=1000 or (size is not None and size!=page_size):raise ValueError('LOCATION_PAGE_SIZE_INVALID')
        size=page_size
        if cfg['kind']=='arcgis':
            expected=dict(f='json',where=expected_where,outFields='*',returnGeometry='true',resultOffset=str(len(rebuilt)),resultRecordCount=str(size),orderByFields=cfg['id'])
        else:
            expected=dict(service='WFS',version='2.0.0',request='GetFeature',typeNames=cfg['layer'],outputFormat='application/json',count=str(size),startIndex=str(len(rebuilt)),sortBy=cfg['id'],CQL_FILTER=expected_where)
        if query!={k:[v] for k,v in expected.items()}:raise ValueError('LOCATION_QUERY_PAGINATION_OR_FILTER_CHANGED')
        page=json.loads(raw)
        if page.get('error') or not isinstance(page.get('features'),list):raise ValueError('LOCATION_SERVICE_ERROR_OR_SCHEMA')
        items=page['features']
        if len(items)>size:raise ValueError('LOCATION_PAGE_EXCEEDS_REQUEST')
        if cfg['kind']!='arcgis':
            announced=page.get('numberMatched',page.get('totalFeatures'))
            if announced is None or not str(announced).isdigit():raise ValueError('LOCATION_COMPLETE_COUNT_REQUIRED')
            if total is not None and total!=int(announced):raise ValueError('LOCATION_INVENTORY_CHANGED')
            total=int(announced)
        for feature in items:
            fid=_attributes(feature).get(cfg['id'])
            if fid in (None,'') or str(fid) in seen:raise ValueError('LOCATION_DUPLICATE_OR_MISSING_ID')
            seen.add(str(fid));rebuilt.append(dict(feature=feature,receipt=receipt))
        if len(rebuilt)>200000:raise ValueError('LOCATION_RECORD_BUDGET')
        if cfg['kind']=='arcgis':
            terminal=page.get('exceededTransferLimit') is False or (not items and page.get('exceededTransferLimit') is not True)
        else:
            if len(rebuilt)>total:raise ValueError('LOCATION_COUNT_MISMATCH')
            terminal=len(rebuilt)==total
        if not items and not terminal:raise ValueError('LOCATION_INCOMPLETE_PAGE')
    if not terminal:raise ValueError('LOCATION_TERMINAL_PAGE_MISSING')
    if len(rebuilt)!=inventory.get('count'):raise ValueError('LOCATION_SNAPSHOT_COUNT')
    if result.get('features')!=rebuilt:raise ValueError('LOCATION_FEATURE_CACHE_NOT_COMPLETE_RAW_INVENTORY')
    return {**result,'features':rebuilt}


def validate_reference(reference):
    """Explicit reviewed reference proof; never invent a distance threshold or CRS."""
    validate_mapping_proof(reference)
    if reference.get('crs')!='EPSG:7844':raise ValueError('LOCATION_REFERENCE_CRS_REQUIRED')
    values=[reference.get(k) for k in ('longitude','latitude','max_distance_m')]
    if any(isinstance(x,bool) or not isinstance(x,(int,float)) or not math.isfinite(x) for x in values):raise ValueError('LOCATION_REFERENCE_COORDINATE_OR_THRESHOLD')
    lon,lat,threshold=values
    if not (110<=lon<=155 and -45<=lat<=-9 and threshold>0):raise ValueError('LOCATION_REFERENCE_COORDINATE_OR_THRESHOLD')
    return reference


def validate_mapping_proof(proof):
    if (not isinstance(proof,dict) or not re.fullmatch(r'[0-9a-f]{64}',str(proof.get('source_sha256','')))
        or not str(proof.get('locator') or '').strip() or not str(proof.get('reviewed_by') or '').strip()
        or not proof.get('source_path')):raise ValueError('LOCATION_REFERENCE_VERIFIED_PROOF_REQUIRED')
    raw=Path(proof['source_path']).read_bytes()
    if hashlib.sha256(raw).hexdigest()!=proof['source_sha256']:raise ValueError('LOCATION_REFERENCE_SOURCE_HASH')
    return proof


def load_project_context(references_path=None,aliases_path=None):
    references=json.loads(Path(references_path).read_text('utf-8-sig')) if references_path else {}
    aliases=json.loads(Path(aliases_path).read_text('utf-8-sig')) if aliases_path else {}
    if not isinstance(references,dict) or not isinstance(aliases,dict):raise ValueError('LOCATION_CONTEXT_MAP_REQUIRED')
    for value in references.values():validate_reference(value)
    for value in aliases.values():
        validate_mapping_proof(value)
        names=value.get('aliases')
        if not isinstance(names,list) or not names or any(not isinstance(n,str) or not n.strip() for n in names):raise ValueError('LOCATION_EXACT_ALIASES_REQUIRED')
    return references,aliases
