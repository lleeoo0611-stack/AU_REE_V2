"""Conservative round-three official points and empirical NT datum controls."""
import csv,io,json,zipfile,hashlib,statistics,math
from pathlib import Path
from pyproj import Transformer,Geod,network
from . import round2_locations as prior
from . import official_location_adapters as base
network.set_network_enabled(False)
QUALIFIER='DATUM_GDA94_OR_GDA2020_INDISTINGUISHABLE'

def assess_controls(controls):
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
        if max(differences)<=2.0:return dict(accepted=True,datum='GDA94',qualifier=QUALIFIER,controls=len(controls),gda94_gda2020_max_difference_m=max(differences),errors=errors)
    return dict(accepted=False,reason='DATUM_CONTROL_THRESHOLDS_NOT_MET',controls=len(controls),errors=errors)

def nt_candidates(acquisitions,decisions):
    ga=next(r for r in acquisitions if r['dataset']=='GA_OZMIN');ga=base.verify_acquisition_snapshots(ga,decisions)
    nt=next(r for r in acquisitions if r['dataset']=='NT_STRIKE');receipt=nt['receipts'][0]
    raw=Path(receipt['path']).read_bytes()
    if hashlib.sha256(raw).hexdigest()!=receipt['sha256']:raise ValueError('NT_ARCHIVE_HASH')
    with zipfile.ZipFile(io.BytesIO(raw)) as z:data=z.read('MINERALOCCURRENCES.csv')
    if hashlib.sha256(data).hexdigest()!=prior.NT_MEMBER_SHA:raise ValueError('NT_MEMBER_HASH')
    native=list(csv.DictReader(io.StringIO(data.decode('utf-8-sig'))));controls=[];unmatched=[]
    for f in ga['features']:
        a=base._attributes(f['feature'])
        if base.native_state(a.get('STATE'))!='NT':continue
        name=prior.normalized_name(a['OCCURRENCE_NAME']);matches=[n for n in native if prior.normalized_name(n['NAME'])==name]
        if len(matches)!=1:unmatched.append(dict(name=a['OCCURRENCE_NAME'],matches=len(matches)));continue
        n=matches[0];controls.append(dict(name=a['OCCURRENCE_NAME'],easting=n['EASTING'],northing=n['NORTHING'],zone=n['ZONE_MGA'],longitude=a['LONG_GDA94'],latitude=a['LAT_GDA94'],nt_id=n['MODAT_ID'],ga_id=a['ENO'],ga_sha256=f['receipt']['sha256']))
    result=assess_controls(controls);result.update(unmatched_controls=unmatched,nt_sha256=receipt['sha256'],member_sha256=prior.NT_MEMBER_SHA,control_records=controls)
    candidates=[]
    if result['accepted']:
        for n in native:
            if not base.REE.search(n['COM_MAJOR']+' '+n['COM_MINOR']):continue
            x,y=prior.transform_nt(n['EASTING'],n['NORTHING'],n['ZONE_MGA'],result['datum']) if result['datum'] in ('GDA94','GDA2020') else Transformer.from_crs(20200+int(n['ZONE_MGA']),7844,always_xy=True,allow_ballpark=False).transform(float(n['EASTING']),float(n['NORTHING']),errcheck=True)
            candidates.append(dict(dataset='NT_STRIKE',layer='MINERALOCCURRENCES.csv',feature_id=n['MODAT_ID'],names=[n['NAME']],normalized_names=[prior.normalized_name(n['NAME'])],site_exact_names=[prior.normalized_name(n['NAME'])],state='NT',latitude=y,longitude=x,operator='',operator_field='',project_group=n['MODAT_ID'],project_title=n['NAME'],source_sha256=receipt['sha256'],source_url=receipt['url'],acquired_at=receipt['acquired_at'],qualifier=result['qualifier'],control_report='nt_datum_controls.json',input_datum=result['datum'],output_crs='EPSG:7844'))
    return candidates,result

def match(row,candidates,rows):
    if row.get('緯度') or row.get('經度'):return 'EXISTING_PAIR_UNCHANGED',[]
    name=prior.normalized_name(row['專案名稱']);state=base.native_state(row.get('州省地區'))
    matches=[c for c in candidates if c['state']==state and name in c['normalized_names']]
    if 'uro' in prior.operator_name(row.get('開發商')) and 'charley creek' in name:return 'URO_TENEMENT_SCOPE_NOT_SHARED',matches
    if not matches:return 'NO_NORMALIZED_NAME_MATCH',[]
    groups={(c['dataset'],c.get('project_group')) for c in matches if c.get('project_group')}
    expanded=[c for c in candidates if c in matches or (c['dataset'],c.get('project_group')) in groups]
    if len(expanded)!=1 or any(c.get('project_site_count',1)!=1 for c in matches):return 'MULTIPLE_CANDIDATES_OR_PROJECT_SITES',expanded
    c=matches[0]
    if c['dataset']=='VIC_MINSITE' and not c.get('operator_field'):return 'NO_OPERATOR_FIELD_REQUIRES_REVIEW',matches
    if c.get('operator') and prior.operator_name(c['operator'])!=prior.operator_name(row.get('開發商')):return 'OPERATOR_MISMATCH',matches
    if c.get('operator_field') and not c.get('operator') and name not in c.get('site_exact_names',[]):return 'BLANK_OPERATOR_REQUIRES_EXACT_SITE_OR_PROJECT_TITLE',matches
    competing=[r for r in rows if r['專案ID']!=row['專案ID'] and base.native_state(r.get('州省地區'))==state and prior.normalized_name(r['專案名稱']) in c['normalized_names'] and (not c.get('operator') or prior.operator_name(c['operator'])==prior.operator_name(r.get('開發商')))]
    if c['dataset']=='NT_STRIKE' and name=='charley creek' and prior.normalized_name(c['names'][0])=='charley creek':
        competing=[r for r in competing if not ('uro' in prior.operator_name(r.get('開發商')))]
    if competing:return 'POINT_MATCHES_MULTIPLE_RESEARCH_ROWS',matches
    return 'MATCHED',matches

def collect(rows,trace,decisions,repo):
    repo=Path(repo);settings=json.loads((repo/'config/round3_locations.json').read_text('utf8'))
    approved={d['decision_id']:d for d in decisions['decisions'] if d.get('decided_by')=='USER_EXPLICIT_APPROVAL'}
    for key in ('wa_decision_id','nt_decision_id','shared_decision_id'):
        if settings[key] not in approved or approved[settings[key]].get('approval_evidence')!=settings['approval_evidence'] or approved[settings[key]].get('rule')!=settings['rules'][key]:raise ValueError('ROUND3_LOCATION_APPROVAL_REQUIRED')
    expected_scopes={
        'wa_decision_id':'SAME_STATE_UNIQUE_EXACT_SITE_OR_PROJECT_TITLE_EMPTY_OPERATOR_VALUE',
        'nt_decision_id':'NT_ARCHIVED_GA_CONTROL_DATUM_MIN3',
        'shared_decision_id':['Mt Stirling — Yttria resource scope','Yttria REE Project'],
    }
    if any(approved[settings[k]].get('scope')!=scope for k,scope in expected_scopes.items()):raise ValueError('ROUND3_LOCATION_SCOPE_MISMATCH')
    if settings['shared_row_names']!=expected_scopes['shared_decision_id']:raise ValueError('ROUND3_SHARED_ROW_SCOPE_MISMATCH')
    acquisitions=json.loads((repo/'results/coverage-approved-2026-11-11/government/acquisitions.json').read_text('utf8'))
    candidates,discarded=prior.load_candidates(acquisitions,decisions)
    wa=next(a for a in acquisitions if a['dataset']=='WA_MINEDEX')
    native={str(base._attributes(i['feature'])['site_code']):base._attributes(i['feature']) for i in wa['features']}
    for c in candidates:
        if c['dataset']=='WA_MINEDEX':
            a=native[c['feature_id']];c['site_exact_names']=[prior.normalized_name(a.get('site_title')),prior.normalized_name(str(a.get('proj_title') or '').partition(' / ')[0])]
    nts,control=nt_candidates(acquisitions,decisions);candidates+=nts
    official=verify_official_acquisition(repo)
    vic=next(d for d in official['datasets'] if d['state']=='VIC')
    vic_report=dict(status=vic['status'])
    if vic['status']=='COMPLETE':
        if vic.get('license',vic.get('licence',{})).get('id')!='CC-BY-4.0':raise ValueError('VIC_OPEN_LICENSE_REQUIRED')
        if 'round3-vic-tas-official-20261111' not in approved or approved['round3-vic-tas-official-20261111'].get('rule')!='ACQUIRE_OFFICIAL_VIC_TAS_OPEN_DATA' or approved['round3-vic-tas-official-20261111'].get('approval_evidence')!=settings['approval_evidence']:raise ValueError('VIC_ACQUISITION_APPROVAL_REQUIRED')
        vc,vic_report=vic_candidates(repo,official);candidates+=vc

    fills=[];reviews=[];shared_report=[]
    def add(row,c,decision,qualifier):
        scope=dict(c,qualifier=qualifier,decision_id=decision,scope_note='官方礦點代表位置，不是礦權／資源邊界。')
        for column,key in [('緯度','latitude'),('經度','longitude')]:
            if row[column]:continue
            value=format(float(c[key]),'.10g')
            p=dict(project_id=row['專案ID'],column=column,value=value,source_sha256=c['source_sha256'],source_url=c['source_url'],locator=c['layer']+'; feature '+c['feature_id'],method='ROUND3_OFFICIAL_POINT_RESEARCHER_APPROVED',scope=json.dumps(scope,ensure_ascii=False,sort_keys=True),observation_ids='[]',review_ids=json.dumps([decision]),review_methods='["NORMALIZED_NAME_MATCH"]',acquired_through=c['acquired_at'],source_kind='GOVERNMENT_SPATIAL_CATALOGUE',publication_date_role='DATASET_VERSION_NOT_MRE',resource_effective_date_unknown='True',public_release_date_unknown='True')
            fills.append(dict(project_id=row['專案ID'],column=column,value=value,decision_id=decision,provenance=p))
    shared_names=set(settings['shared_row_names'])
    shared_candidates=[c for c in candidates if c['dataset']=='WA_MINEDEX' and 'yttria' in c['normalized_names'] and prior.normalized_name(c['project_title'])=='mt stirling']
    for row in rows:
        if row['專案名稱'] in shared_names:
            if len(shared_candidates)!=1:reviews.append(dict(project_id=row['專案ID'],reason='APPROVED_SHARED_POINT_NOT_UNIQUE'));continue
            shared_ids={r['專案ID'] for r in rows if r['專案名稱'] in shared_names}
            evidence=[{k:p.get(k,'') for k in ('project_id','source_sha256','locator','publication_date','effective_date')} for p in trace if p['project_id'] in shared_ids and p['column']=='礦石蘊藏量_Mt']
            c=dict(shared_candidates[0],shared_research_rows=sorted(shared_names),resource_estimate_date='2024-04-16',shared_resource_evidence=evidence,existing_coordinate_policy='KEEP_PREEXISTING_YTTRIA_COORDINATES; distance in shared_deposit_points.json',not_additive='同一估計／礦床，不可直接加總')
            if row.get('緯度') and row.get('經度'):
                distance=Geod(ellps='GRS80').inv(float(row['經度']),float(row['緯度']),c['longitude'],c['latitude'])[2]
                shared_report.append(dict(project_id=row['專案ID'],existing_point_preserved=True,distance_to_minedex_m=distance))
            elif not row.get('緯度') and not row.get('經度'):add(row,c,settings['shared_decision_id'],'SHARED_DEPOSIT_POINT_RESEARCHER_APPROVED')
            else:reviews.append(dict(project_id=row['專案ID'],reason='PARTIAL_EXISTING_PAIR_UNCHANGED'))
            continue
        status,options=match(row,candidates,rows)
        if status=='EXISTING_PAIR_UNCHANGED':continue
        if status!='MATCHED':reviews.append(dict(project_id=row['專案ID'],project=row['專案名稱'],reason=status,candidates=options));continue
        c=options[0]
        if c['dataset']=='NT_STRIKE':add(row,c,settings['nt_decision_id'],control['qualifier'])
        elif c['dataset']=='VIC_MINSITE':reviews.append(dict(project_id=row['專案ID'],reason='NO_OPERATOR_FIELD_REQUIRES_REVIEW',candidates=options))
        elif c['dataset']=='WA_MINEDEX' and not c.get('operator'):add(row,c,settings['wa_decision_id'],'NO_OPERATOR_VALUE')
        else:reviews.append(dict(project_id=row['專案ID'],project=row['專案名稱'],reason='NO_NEW_ROUND3_RULE_FOR_CANDIDATE',candidates=options))
    return fills,reviews,dict(nt_datum_controls=control,shared_deposit_points=shared_report,vic_native_point_validation=vic_report)


def verify_official_acquisition(repo):
    """Hash-verify even blocked acquisition receipts; missing evidence is not success."""
    repo=Path(repo).resolve();root=repo/'results/round3-government-2026-11-11'
    acquisition=json.loads((root/'acquisition.json').read_text('utf8'))
    requests=json.loads((root/'request_log.json').read_text('utf8'))
    if acquisition.get('request_count')!=len(requests):raise ValueError('OFFICIAL_ACQUISITION_REQUEST_COUNT')
    if {d.get('state') for d in acquisition.get('datasets',[])}!={'VIC','TAS'}:raise ValueError('OFFICIAL_ACQUISITION_STATES')
    from urllib.parse import urlsplit
    stopped=set()
    for record in requests:
        state=record.get('state')
        if record.get('decision_id')!='round3-vic-tas-official-20261111' or not record.get('version'):raise ValueError('OFFICIAL_RECEIPT_VERSION_DECISION_REQUIRED')
        if urlsplit(record.get('url','')).hostname not in {'discover.data.vic.gov.au','opendata.maps.vic.gov.au','www.mrt.tas.gov.au'}:raise ValueError('OFFICIAL_ACQUISITION_HOST_NOT_APPROVED')
        if state in stopped:raise ValueError('OFFICIAL_REQUEST_AFTER_SOURCE_STOP')
        path=(repo/record['path']).resolve()
        if not path.is_relative_to(root.resolve()) or hashlib.sha256(path.read_bytes()).hexdigest()!=record['source_sha256']:raise ValueError('OFFICIAL_ACQUISITION_RAW_HASH')
        if not record.get('requested_at') or not record.get('url','').startswith('https://'):raise ValueError('OFFICIAL_ACQUISITION_RECEIPT_INCOMPLETE')
        if record.get('publication_derivative'):
            original=(repo/record['original_private_path']).resolve()
            if record.get('http_status')!=403 or record.get('state')!='TAS' or not original.is_relative_to((repo/'work/retained_originals').resolve()):raise ValueError('OFFICIAL_ERROR_DERIVATIVE_SCOPE')
            raw=original.read_bytes()
            if hashlib.sha256(raw).hexdigest()!=record['original_response_sha256'] or len(raw)!=record['original_response_bytes']:raise ValueError('OFFICIAL_PRIVATE_ORIGINAL_HASH')
            if record.get('publication_transform')!='KEEP_HTTP_STATUS_AND_PAGE_TITLE_ONLY_REMOVE_CHALLENGE_SCRIPTS_AND_QUERY_TOKENS':raise ValueError('OFFICIAL_ERROR_DERIVATIVE_TRANSFORM')

        status=record.get('http_status')
        if status is None or status>=400 or record.get('status')=='STOPPED':stopped.add(state)
    vic=next(d for d in acquisition['datasets'] if d['state']=='VIC')
    if vic['status']=='COMPLETE':
        license=vic.get('license',{})
        matches=[r for r in requests if r['source_sha256']==license.get('evidence_sha256') and urlsplit(r['url']).hostname=='discover.data.vic.gov.au' and r['http_status']==200]
        if license.get('id')!='CC-BY-4.0' or len(matches)!=1:raise ValueError('VIC_LICENSE_EVIDENCE_REQUIRED')
        text=(repo/matches[0]['path']).read_text('utf8')
        if 'creativecommons.org/licenses/by/4.0' not in text:raise ValueError('VIC_LICENSE_ORIGINAL_MISMATCH')
    return acquisition


def vic_candidates(repo, acquisition):
    from urllib.parse import urlsplit,parse_qs
    repo=Path(repo);requests=json.loads((repo/'results/round3-government-2026-11-11/request_log.json').read_text('utf8'))
    pages=[]
    for receipt in requests:
        query={k.lower():v for k,v in parse_qs(urlsplit(receipt['url']).query).items()}
        if receipt['state']!='VIC' or query.get('request',[''])[0].lower()!='getfeature':continue
        if receipt['http_status']!=200:continue
        raw=json.loads((repo/receipt['path']).read_text('utf8'))
        if raw.get('type')!='FeatureCollection':raise ValueError('VIC_FEATURE_COLLECTION_REQUIRED')
        if raw.get('crs',{}).get('properties',{}).get('name')!='urn:ogc:def:crs:EPSG::4283':raise ValueError('VIC_SOURCE_CRS_REQUIRED')
        pages.append((int(query.get('startindex',['0'])[0]),raw,receipt))
    if not pages:return [],dict(status='NO_ACCEPTED_VIC_FEATURE_PAGES')
    pages.sort(key=lambda p:p[0]);total=pages[0][1]['numberMatched'];all_rows=[];offset=0
    for start,raw,receipt in pages:
        features=raw['features']
        if start!=offset or raw['numberMatched']!=total or raw['numberReturned']!=len(features):raise ValueError('VIC_PAGINATION_INCOMPLETE')
        all_rows.extend((feature,receipt) for feature in features);offset+=len(features)
    if offset!=total:raise ValueError('VIC_PAGINATION_INCOMPLETE')
    if any(link.get('rel')=='next' for link in pages[-1][1].get('links',[])):raise ValueError('VIC_FINAL_NEXT_PAGE_REMAINS')
    ids=[feature['properties']['siteid'] for feature,_ in all_rows]
    if any(type(i) is not int for i in ids):raise ValueError('VIC_NATIVE_SITE_ID_TYPE')
    if len(set(ids))!=total or ids!=sorted(ids):raise ValueError('VIC_SITE_IDS_DUPLICATE_OR_UNSORTED')
    groups={}
    for feature,_ in all_rows:
        prop=feature['properties'];group=prior.normalized_name(prop.get('mine_name') or '')
        if group:groups.setdefault(group,set()).add(prop['siteid'])
    candidates=[]
    for feature,receipt in all_rows:
        prop=feature['properties']
        if not base.REE.search(' '.join(str(prop.get(k) or '') for k in ('pri_comm','sec_comm','min_ass'))):continue
        geometry=feature.get('geometry') or {};coords=geometry.get('coordinates',[])
        if geometry.get('type')!='Point' or len(coords)!=2 or not all(math.isfinite(float(v)) for v in coords):raise ValueError('VIC_NATIVE_POINT_REQUIRED')
        if not (-40<float(coords[1])<-33 and 140<float(coords[0])<151):raise ValueError('VIC_POINT_OUTSIDE_STATE')
        names=[str(prop.get('mine_name') or '').strip()];names=[n for n in names if n]
        group=prior.normalized_name(prop.get('mine_name') or '')
        lon,lat=Transformer.from_crs(4283,7844,always_xy=True,allow_ballpark=False).transform(*coords,errcheck=True)
        candidates.append(dict(dataset='VIC_MINSITE',layer='open-data-platform:minsite',feature_id=str(prop['siteid']),names=names,normalized_names=[prior.normalized_name(n) for n in names],site_exact_names=[prior.normalized_name(n) for n in names],state='VIC',latitude=lat,longitude=lon,operator='',operator_field='',project_group=group or str(prop['siteid']),project_site_count=len(groups.get(group,{prop['siteid']})),project_title=prop.get('mine_name') or '',source_sha256=receipt['source_sha256'],source_url=receipt['url'],acquired_at=receipt['requested_at'],qualifier='NO_OPERATOR_FIELD',input_crs='EPSG:4283',output_crs='EPSG:7844',native_properties=prop,native_geometry=geometry))
    return candidates,dict(status='COMPLETE',total_native_sites=total,ree_native_sites=len(candidates),pages=len(pages),candidate_points=candidates,scope_note='Native project field is a catalogue source category, not a mining project identity; exact mine_name only. WIM 100 Global and East Core native areas are not automatically the whole Wimmera project. PagingIsTransactionSafe FALSE: completeness of archived pages, not an atomic service snapshot.')
