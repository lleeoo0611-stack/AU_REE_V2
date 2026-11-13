import hashlib
import json
from pathlib import Path
from urllib.parse import parse_qsl,urlsplit
import pytest
from au_ree_v2.round5_wa import retry_url, response_error, matched_count, validate_pages, acquire, load_features, collect

REPO=Path(__file__).resolve().parents[1]

def setup_cfg(tmp_path):
    cfg=json.loads((REPO/'config/round5_wa.json').read_text('utf8'))
    (tmp_path/'config').mkdir()
    (tmp_path/'config/round5_wa.json').write_text(json.dumps(cfg),encoding='utf8')
    receipt=cfg['original_failed_receipt'];target=tmp_path/receipt['path'];target.parent.mkdir(parents=True)
    target.write_bytes((REPO/receipt['path']).read_bytes())
    return cfg

def test_only_sortby_removed():
    cfg=json.loads((REPO/'config/round5_wa.json').read_text('utf8'))
    u=cfg['original_url'];v=retry_url(u)
    assert 'sortby' not in v.lower()
    assert urlsplit(u)._replace(query='')==urlsplit(v)._replace(query='')
    assert parse_qsl(urlsplit(v).query)==[(k,v) for k,v in parse_qsl(urlsplit(u).query) if k!='sortBy']
    assert len(cfg['project_ids'])==12

def test_mismatch_no_features():
    with pytest.raises(ValueError,match='COUNT_MISMATCH'):
        validate_pages(2,[(0,{'features':[{'id':'one'}]})])

def test_duplicate_and_unstable_total_stop():
    with pytest.raises(ValueError,match='UNSTABLE'):
        validate_pages(2,[(0,{'features':[{'id':'one'},{'id':'one'}]})])
    with pytest.raises(ValueError,match='MATCHED_CHANGED'):
        validate_pages(2,[(0,{'numberMatched':3,'features':[{'id':'one'}]})])

def test_second_400_stops_no_parameter_change(tmp_path):
    cfg=setup_cfg(tmp_path);calls=[]
    def fetch(url):
        calls.append(url)
        return 400,b'<ExceptionReport>other parameter unsupported</ExceptionReport>'
    result=acquire(tmp_path,fetch)
    assert result['status']=='STOPPED' and result['request_count']==1 and len(calls)==1
    assert result['pages']==[]
    assert calls==[retry_url(cfg['original_url'],hits=True)]
    with pytest.raises(ValueError,match='ALREADY_RECORDED'):acquire(tmp_path,fetch)
    assert len(calls)==1

@pytest.mark.parametrize('status',[401,403,429,500,502,503,302])
def test_access_errors_stop(status):
    assert response_error(status,b'blocked').startswith('STOPPED_HTTP_')

def test_html_login_and_captcha_stop():
    assert response_error(200,b'<html>login</html>')
    assert response_error(200,b'captcha challenge')

def test_hits_xml_and_json():
    assert matched_count(b'<FeatureCollection numberMatched="4"/>')==4
    assert matched_count(b'{"numberMatched": 4}')==4
    with pytest.raises(ValueError):matched_count(b'{"numberMatched":"unknown"}')

def test_count_mismatch_acquisition_and_collector_stop(tmp_path,monkeypatch):
    cfg=setup_cfg(tmp_path);responses=[(200,b'{"numberMatched":2}'),(200,b'{"type":"FeatureCollection","features":[{"id":"one"}]}'),(200,b'{"type":"FeatureCollection","features":[]}')]
    m=acquire(tmp_path,lambda url:responses.pop(0))
    assert m['status']=='STOPPED' and m['request_count']==3
    with pytest.raises(ValueError,match='EMPTY_PAGE'):load_features(tmp_path,cfg)
    # Actual collector refuses all twelve rows when acquisition is incomplete.
    license_receipt=cfg['license_evidence']; target=tmp_path/license_receipt['path']; target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes((REPO/license_receipt['path']).read_bytes())
    monkeypatch.setattr('au_ree_v2.round5_wa.validate_original',lambda *args:None)
    old=json.loads((REPO/'config/round4_tenements.json').read_text('utf8'))
    (tmp_path/'config/round4_tenements.json').write_text(json.dumps(old))
    rows=[{'專案ID':pid,'專案名稱':pid,'緯度':'','經度':''} for pid in cfg['project_ids']]
    decisions={'decisions':[{'decision_id':cfg['decision_id'],'rule':'WA_REMOVE_SORTBY_ONLY','decided_by':'USER_EXPLICIT_APPROVAL'}]}
    fills,reviews,extra=collect(rows,[],decisions,tmp_path)
    assert fills==[] and len(reviews)==12
    assert all(r['reason']=='WA_EMPTY_PAGE_BEFORE_COMPLETION' for r in reviews)

def test_successful_manifest_replay_and_hash(tmp_path):
    cfg=setup_cfg(tmp_path)
    page={'type':'FeatureCollection','numberMatched':1,'numberReturned':1,'crs':{'properties':{'name':'urn:ogc:def:crs:EPSG::7844'}},'features':[{'id':'one'}]}
    responses=[(200,b'{"numberMatched":1}'),(200,json.dumps(page).encode())]
    m=acquire(tmp_path,lambda url:responses.pop(0))
    features,replay=load_features(tmp_path,cfg)
    assert m['status']=='COMPLETE' and features==[{'id':'one'}] and replay==m
    (tmp_path/m['pages'][0]['path']).write_bytes(b'changed')
    with pytest.raises(ValueError,match='HASH_MISMATCH'):load_features(tmp_path,cfg)

def test_no_silent_datum_assumption(tmp_path):
    cfg=setup_cfg(tmp_path)
    responses=[(200,b'{"numberMatched":1}'),(200,b'{"type":"FeatureCollection","features":[{"id":"one"}]}')]
    acquire(tmp_path,lambda url:responses.pop(0))
    with pytest.raises(ValueError,match='DATUM_NOT_VERIFIED'):load_features(tmp_path,cfg)
