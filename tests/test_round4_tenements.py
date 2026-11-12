import hashlib,json
import pytest
from shapely.geometry import box,mapping
from au_ree_v2.round4_tenements import centroid,validate_original,collect

def feature(x,y,w=.01,h=.01):return {'geometry':mapping(box(x,y,x+w,y+h)),'properties':{}}

def test_small_polygon_centroid():
    result=centroid([feature(143,-36)],7844)
    assert result['accepted'] and result['location_method']=='TENEMENT_CENTROID'
    assert 500<result['precision_m']<1000

def test_union_over_25km_refused():
    result=centroid([feature(143,-36,1,1)],7844)
    assert not result['accepted'] and result['precision_m']>25000

def test_disjoint_largest_fallback_measures_entire_union():
    result=centroid([feature(143,-36,.02,.02),feature(143.1,-36)],7844)
    assert result['accepted'] and result['location_method']=='LARGEST_TENEMENT_CENTROID'
    assert result['longitude']<143.03 and result['precision_m']>8000

def test_disjoint_far_fallback_rejected():
    result=centroid([feature(143,-36,.02,.02),feature(144,-36)],7844)
    assert not result['accepted'] and result['precision_m']>80000

def test_missing_own_original_refused(tmp_path):
    with pytest.raises(ValueError,match='OWN_ORIGINAL_REFERENCE_REQUIRED'):
        validate_original({'project_id':'p','tenement_ids':['EL1'],'complete_project_scope':True},'p',tmp_path,[])

def test_other_project_original_refused(tmp_path):
    record={'project_id':'p','tenement_ids':['EL1'],'complete_project_scope':True,'original_references':[{'source_sha256':'abc','page':1,'quote':'EL1'}]}
    with pytest.raises(ValueError,match='ORIGINAL_NOT_BOUND_TO_PROJECT'):
        validate_original(record,'p',tmp_path,[{'project_id':'other','source_sha256':'abc'}])

def test_exact_original_quote_and_ids(tmp_path):
    raw=b'Project P has EL1 and EL2';(tmp_path/'original.txt').write_bytes(raw);sha=hashlib.sha256(raw).hexdigest()
    ref={'source_sha256':sha,'path':'original.txt','page':1,'quote':'Project P has EL1 and EL2'}
    record={'project_id':'p','tenement_ids':['EL1','EL2'],'complete_project_scope':True,'original_references':[ref]}
    validate_original(record,'p',tmp_path,[{'project_id':'p','source_sha256':sha}])
    record['tenement_ids']=['EL9']
    with pytest.raises(ValueError,match='TENEMENT_ID_NOT_IN_ORIGINAL_QUOTE'):validate_original(record,'p',tmp_path,[{'project_id':'p','source_sha256':sha}])

def test_existing_or_partial_pair_and_notes_never_overwritten(tmp_path):
    (tmp_path/'config').mkdir();(tmp_path/'log.json').write_text('[]')
    (tmp_path/'config/round4_tenements.json').write_text(json.dumps({'decision_id':'approved','request_log':'log.json','projects':[],'datasets':{},'precision_limit_m':25000}))
    rows=[{'專案ID':'p','專案名稱':'P','緯度':'-36','經度':'','總說明':'original note'}]
    before=json.dumps(rows)
    fills,reviews,extra=collect(rows,[],{'decisions':[{'decision_id':'approved','decided_by':'USER_EXPLICIT_APPROVAL','rule':'TENEMENT_CENTROID_RESEARCHER_APPROVED'}]},tmp_path)
    assert fills==[] and reviews==[] and json.dumps(rows)==before


def test_identifier_padding_not_fuzzy():
    from au_ree_v2.round4_tenements import identifier_key
    assert identifier_key('EL 6419')==identifier_key('EL006419')
    assert identifier_key('E70/5939')==identifier_key('E 70/05939')
    assert identifier_key('E70/5939')!=identifier_key('E71/5939')
    assert identifier_key('EL6419')!=identifier_key('MIN6419')

def test_incomplete_geometry_page_refused(tmp_path):
    from au_ree_v2.round4_tenements import verify_feature_pages
    raw=json.dumps({'features':[], 'numberMatched':1,'numberReturned':0,'crs':{'properties':{'name':'CRS'}}}).encode()
    (tmp_path/'page.json').write_bytes(raw);sha=hashlib.sha256(raw).hexdigest()
    page={'path':'page.json','source_sha256':sha,'start_index':0}
    dataset={'pages':[page],'native_crs_uri':'CRS'}
    with pytest.raises(ValueError,match='TENEMENT_PAGINATION_INCOMPLETE'):
        verify_feature_pages(tmp_path,dataset,[{'source_sha256':sha,'http_status':200}])


def test_largest_tenement_uses_sum_of_all_native_features():
    # A's two adjacent parts each smaller than B, but their union is larger.
    a1=feature(143,-36,.02,.02);a1['properties']['title']='EL1'
    a2=feature(143.02,-36,.02,.02);a2['properties']['title']='EL001'
    b=feature(143.12,-36,.03,.02);b['properties']['title']='EL2'
    result=centroid([a1,a2,b],7844,id_field='title')
    assert result['accepted'] and result['location_method']=='LARGEST_TENEMENT_CENTROID'
    assert 143.019<result['longitude']<143.021
    assert result['precision_m']>11000


def test_nt_official_archive_record_alignment_and_datum():
    from pathlib import Path
    from au_ree_v2.round4_tenements import read_shapefile_zip
    repo=Path(__file__).resolve().parents[1]
    archive=repo/'results/round4-4-2026-11-13/acquisition/cf91d27516b4212b7dd795877356827ad042cc90c8fc63d854a74983fed043f2.raw'
    features,crs=read_shapefile_zip(archive.read_bytes(),'MIN_TITLE_EXPL_GRNT')
    assert len(features)==2090 and crs.to_epsg()==4283
    assert len({f['id'] for f in features})==2090
    assert len([f for f in features if f['properties']['TITLEID']=='EL32455'])==2
    assert not any(f['properties']['TITLEID']=='EL32406' for f in features)
