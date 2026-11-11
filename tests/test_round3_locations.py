import copy,math
import pytest
from pyproj import Transformer
from au_ree_v2 import round3_locations as m

def controls(datum='GDA94'):
    records=[];code={'GDA94':28353,'GDA2020':7853,'AGD66':20253}[datum]
    for i,(lon,lat) in enumerate([(133,-20),(133.1,-20.1),(133.2,-20.2)]):
        e,n=Transformer.from_crs(4283,code,always_xy=True,allow_ballpark=False).transform(lon,lat)
        records.append(dict(name=str(i),ga_id=str(i),nt_id=str(i),longitude=lon,latitude=lat,easting=e,northing=n,zone=53))
    return records

@pytest.mark.parametrize('datum',['GDA94','GDA2020'])
def test_gda_frames_indistinguishable_at_prescribed_threshold(datum):
    result=m.assess_controls(controls(datum));assert result['accepted'] and result['datum']=='GDA94'
    assert result['qualifier']==m.QUALIFIER
    assert result['errors'][datum]['median_m']<.01
    assert result['errors']['AGD66']['median_m']>150

def test_agd66_fixture_can_be_unambiguously_selected():
    r=m.assess_controls(controls('AGD66'));assert r['accepted'] and r['datum']=='AGD66'
    assert r['errors']['AGD66']['maximum_m']<.01

@pytest.mark.parametrize('n',[0,1,2])
def test_insufficient_controls_fail_closed(n):assert not m.assess_controls(controls()[:n])['accepted']

def test_duplicate_and_nonfinite_controls_rejected():
    assert not m.assess_controls([controls()[0]]*3)['accepted']
    c=controls();c[0]['easting']=float('nan');assert not m.assess_controls(c)['accepted']

def test_no_datum_within_threshold_is_rejected():
    c=controls()
    for r in c:r['longitude']+=.1
    assert not m.assess_controls(c)['accepted']

def row(name='Alpha',pid='p',operator='One Ltd',state='WA'):
    return {'專案ID':pid,'專案名稱':name,'開發商':operator,'州省地區':state,'緯度':'','經度':''}

def point(**kwargs):
    c=dict(dataset='WA_MINEDEX',state='WA',normalized_names=['alpha'],site_exact_names=['alpha'],project_group='g',operator='',operator_field='proj_title')
    c.update(kwargs);return c

def test_empty_operator_exact_single_site_is_accepted():assert m.match(row(),[point()],[row()])[0]=='MATCHED'

def test_blank_operator_short_name_only_is_not_enough():assert m.match(row(),[point(site_exact_names=['other'])],[row()])[0]=='BLANK_OPERATOR_REQUIRES_EXACT_SITE_OR_PROJECT_TITLE'

def test_filled_operator_mismatch_is_rejected():assert m.match(row(),[point(operator='Different Ltd')],[row()])[0]=='OPERATOR_MISMATCH'

def test_project_group_multiple_sites_is_rejected():
    c=[point(),point(normalized_names=['other'])]
    assert m.match(row(),c,[row()])[0]=='MULTIPLE_CANDIDATES_OR_PROJECT_SITES'

def test_same_point_multiple_research_rows_is_rejected():assert m.match(row(),[point()],[row(),row(pid='q')])[0]=='POINT_MATCHES_MULTIPLE_RESEARCH_ROWS'

def test_partial_existing_pair_never_filled():
    r=row();r['緯度']='-20';assert m.match(r,[point()],[r])[0]=='EXISTING_PAIR_UNCHANGED'

def test_uro_siblings_do_not_share_charley_main_point():
    c=point(dataset='NT_STRIKE',state='NT',normalized_names=['charley creek'],site_exact_names=['charley creek'],names=['Charley Creek'],operator_field='')
    main=row('Charley Creek REE Project — TOTAL INDICATED RESOURCES resource scope',operator='Enova',state='NT')
    sibling=row('Charley Creek North Project — URO',pid='s',operator='URO Corporation Pty Ltd',state='NT')
    assert m.match(main,[c],[main,sibling])[0]=='MATCHED'
    assert m.match(sibling,[c],[main,sibling])[0]=='URO_TENEMENT_SCOPE_NOT_SHARED'

def test_digit_suffix_is_not_removed_to_manufacture_control():
    assert m.prior.normalized_name('Charley Creek1')!=m.prior.normalized_name('Charley Creek')


def test_control_native_ids_must_each_be_distinct():
    c=controls();c[1]["nt_id"]=c[0]["nt_id"]
    assert not m.assess_controls(c)["accepted"]


@pytest.mark.parametrize('change',['hash','count','retry','missingstate'])
def test_official_receipt_integrity(tmp_path,change):
    import json,hashlib
    folder=tmp_path/'results/round3-government-2026-11-11';folder.mkdir(parents=True)
    raw=b'blocked response';(folder/'raw.bin').write_bytes(raw)
    requests=[dict(decision_id='round3-vic-tas-official-20261111',version='unversioned HTTP response',state='TAS',path='results/round3-government-2026-11-11/raw.bin',source_sha256=hashlib.sha256(raw).hexdigest(),requested_at='2026-11-11',url='https://www.mrt.tas.gov.au/',http_status=403,status='STOPPED')]
    acquisition=dict(request_count=1,datasets=[dict(state='VIC',status='NO_DATA'),dict(state='TAS',status='STOPPED')])
    if change=='hash':requests[0]['source_sha256']='0'*64
    elif change=='count':acquisition['request_count']=0
    elif change=='retry':requests*=2;acquisition['request_count']=2
    else:acquisition['datasets']=[]
    (folder/'request_log.json').write_text(json.dumps(requests));(folder/'acquisition.json').write_text(json.dumps(acquisition))
    with pytest.raises(ValueError):m.verify_official_acquisition(tmp_path)


def vic_fixture(tmp_path, duplicate=False, missing=False, multiple=False):
    import json
    root=tmp_path/'results/round3-government-2026-11-11';root.mkdir(parents=True)
    features=[dict(type='Feature',geometry=dict(type='Point',coordinates=[145,-37]),properties=dict(siteid=1,mine_name='Alpha',project='Group',pri_comm='Rare Earth',sec_comm='',min_ass=''))]
    if multiple:features.append(dict(type='Feature',geometry=dict(type='Point',coordinates=[145.1,-37]),properties=dict(siteid=2,mine_name='Alpha',project='Group',pri_comm='Gold',sec_comm='',min_ass='')))
    if duplicate:features*=2
    data=dict(type='FeatureCollection',crs=dict(properties=dict(name='urn:ogc:def:crs:EPSG::4283')),numberMatched=len(features)+(1 if missing else 0),numberReturned=len(features),features=features)
    (root/'page.json').write_text(json.dumps(data))
    request=dict(state='VIC',url='https://opendata.maps.vic.gov.au/geoserver/wfs?request=GetFeature&startIndex=0',http_status=200,path='results/round3-government-2026-11-11/page.json',source_sha256='a'*64,requested_at='2026-11-11')
    (root/'request_log.json').write_text(json.dumps([request]))
    return tmp_path

def test_vic_exact_native_point(tmp_path):
    c,r=m.vic_candidates(vic_fixture(tmp_path),{})
    assert len(c)==1 and c[0]['site_exact_names']==['alpha'] and r['total_native_sites']==1
    assert c[0]['qualifier']=='NO_OPERATOR_FIELD'

@pytest.mark.parametrize('kwargs',[dict(duplicate=True),dict(missing=True)])
def test_vic_incomplete_or_duplicate_rejected(tmp_path,kwargs):
    with pytest.raises(ValueError):m.vic_candidates(vic_fixture(tmp_path,**kwargs),{})

def test_vic_group_counts_non_ree_sites(tmp_path):
    c,_=m.vic_candidates(vic_fixture(tmp_path,multiple=True),{})
    assert len(c)==1 and c[0]['project_site_count']==2
    r=row('Alpha',state='VIC')
    assert m.match(r,c,[r])[0]=='MULTIPLE_CANDIDATES_OR_PROJECT_SITES'


def test_vic_missing_operator_field_requires_review():
    r=row("Alpha",state="VIC");c=point(dataset="VIC_MINSITE",state="VIC",operator_field="")
    assert m.match(r,[c],[r])[0]=="NO_OPERATOR_FIELD_REQUIRES_REVIEW"
