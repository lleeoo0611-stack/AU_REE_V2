import json
from pathlib import Path
import pytest
from au_ree_v2 import round4_stage as s

@pytest.fixture
def cfg():
    return json.loads((Path(__file__).parents[1]/'config/round4_stage_hit_rules.json').read_text(encoding='utf8'))

def row(name='Test Project',pid='p',stage=''):
    return {'專案ID':pid,'專案名稱':name,'開發階段':'','開發階段代碼':stage,'開發階段類別':''}

def assess(cfg,text,url='https://example.test/project',shared=()):
    return s.assess_hit({'keyword':'Scoping','sentence':text,'physical_page':1},row(),{'sha256':'abc','url':url},shared,cfg)

@pytest.mark.parametrize('text', ['Test Project: to underpin a Scoping Study.','Test Project production costs are uncertain.','Test Project plans to undertake a Scoping Study.','If Test Project enters production, returns may improve.'])
def test_future_and_nominal_fail(cfg,text):
    assert assess(cfg,text)['point3']=='FAIL'

def test_completed_current_project_pass(cfg):
    h=assess(cfg,'The Company completed the Scoping Study for Test Project in 2024.')
    assert h['outcome']=='PASS'
    assert (h['point1'],h['point2'],h['point3'])==('PASS','PASS','PASS')

def test_gis_excludes_hits_and_unclear(cfg):
    h=assess(cfg,'Under Construction','https://services.ga.gov.au/gis/rest/services/Electricity_Infrastructure/MapServer/2')
    assert h['point1']==h['point2']==h['point3']=='FAIL'

def test_other_project_is_not_this_project(cfg):
    assert assess(cfg,'Other Deposit completed its Scoping Study.')['point2']=='FAIL'

def test_ambiguous_and_mixed_block(cfg):
    assert assess(cfg,'Test Project Scoping Study.')['outcome']=='UNCLEAR'
    assert assess(cfg,'Test Project completed exploration and plans to commence production.')['outcome']=='UNCLEAR'

def test_shared_project_specific_not_blanket_excluded(cfg):
    assert s.source_assessment({'sha256':'technical','url':'https://example.test'}, {'p','q'},cfg)[0]=='PASS'
    sha=next(iter(cfg['source_classifications']))
    assert s.source_assessment({'sha256':sha}, {'p','q'},cfg)[0]=='FAIL'
    assert s.source_assessment({'sha256':sha}, {'p'},cfg)[0]=='UNCLEAR'

def test_approval_exact_and_narrow(cfg):
    with pytest.raises(ValueError):s.approve({'decisions':[]},cfg['decision_id'],s.RULE)
    s.approve({'decisions':[{'decision_id':cfg['decision_id'],'rule':s.RULE,'decided_by':'USER_EXPLICIT_APPROVAL','approval_evidence':s.EVIDENCE}]},cfg['decision_id'],s.RULE)

def test_complete_sentence_not_clipped(tmp_path):
    p=tmp_path/'original.txt'; sentence='Test Project '+('important context '*30)+'completed a Scoping Study in 2024.'
    p.write_text(sentence,encoding='utf8')
    e={'path':str(p),'sha256':s.legacy.sha256(p),'kind':'txt'}
    hits=s.complete_hits(e,['Scoping'])
    assert len(hits)==1 and hits[0]['sentence']==sentence
    p.write_text('modified')
    assert s.complete_hits(e,['Scoping'])==[]

def test_charley_exact_four_and_frozen_provenance():
    repo=Path(__file__).parents[1]
    decision={'decisions':[dict(decision_id='round4-charley-exit-20261113',rule=s.EXIT_RULE,decided_by='USER_EXPLICIT_APPROVAL',approval_evidence=s.EVIDENCE)]}
    rows=[row(pid=pid) for pid in s.EXIT_IDS]+[row(pid='unapproved')]
    before=json.dumps(rows)
    fills,reviews,extra=s.collect_charley_exit(rows,[],decision,repo)
    assert not reviews and len(fills)==8 and json.dumps(rows)==before
    assert {f['project_id'] for f in fills}==set(s.EXIT_IDS)
    assert {f['column'] for f in fills}=={'開發階段代碼','開發階段類別'}
    assert any(e['superseded_blockers'] for e in extra['charley_exit_evidence'])
    assert all(json.loads(f['provenance']['scope'])['qualifier']==s.EXIT_RULE for f in fills)
    rows[0]['開發階段代碼']='A1'
    assert len(s.collect_charley_exit(rows,[],decision,repo)[0])==6

@pytest.mark.parametrize('excluded,unknown_date,has_mre,expect_fills',[(False,False,False,2),(False,True,False,0),(False,False,None,0),(True,False,False,0)])
def test_collector_blockers_and_no_existing_edits(tmp_path,monkeypatch,cfg,excluded,unknown_date,has_mre,expect_fills):
    import au_ree_v2.stage_rules
    original=tmp_path/'original.txt';original.write_text('Early exploration only.',encoding='utf8')
    e=dict(path=str(original),sha256=s.legacy.sha256(original),kind='txt',url='https://example.test',dates=[] if unknown_date else ['2024-01-01'],associations=['test'])
    baseline=[dict(project_id='p',original_sha256s=[e['sha256']])]
    (tmp_path/'baseline.json').write_text(json.dumps(baseline))
    (tmp_path/'old.json').write_text(json.dumps(dict(keywords=['Scoping'],keyword_version='old')))
    cfg=dict(cfg,baseline_manifests='baseline.json',legacy_settings='old.json')
    monkeypatch.setattr(s.legacy,'original_inventory',lambda *a:({'p':[e],'filled':[]},{}))
    monkeypatch.setattr(au_ree_v2.stage_rules,'selected_mre',lambda *a:(has_mre,{}))
    if excluded:
        monkeypatch.setattr(s,'source_assessment',lambda *a:('FAIL','excluded generic'))
        monkeypatch.setattr(s.legacy,'scan_original',lambda *a:([],[dict(reason='IMAGE_DOMINATED_PAGE_REQUIRES_OCR_REVIEW')],1))
    d={'decisions':[dict(decision_id=cfg['decision_id'],rule=s.RULE,decided_by='USER_EXPLICIT_APPROVAL',approval_evidence=s.EVIDENCE)]}
    rows=[row(),row(pid='filled',stage='B1')]
    fills,reviews,extra=s.collect_stage_three_point(rows,[],d,tmp_path,tmp_path,cfg)
    assert len(fills)==expect_fills
    assert all(f['project_id']=='p' for f in fills)
    assert rows[1]['開發階段代碼']=='B1'
    assert extra['network_requests']==0
    if excluded:
        assert any(b['reason']=='NO_DATED_PROJECT_SPECIFIC_ORIGINAL_FOR_INFERENCE' for b in reviews[0]['blockers'])
        assert extra['stage_search_manifests'][0]['latest_original_date'] is None
        assert not any(b['reason']=='IMAGE_DOMINATED_PAGE_REQUIRES_OCR_REVIEW' for b in reviews[0]['blockers'])

@pytest.mark.parametrize('text,expected',[
 ('Test Project completed a Scoping Study in 2024.',0),
 ('Test Project plans to complete a Scoping Study.',2),
 ('Test Project Scoping Study.',0),
 ('Other Deposit completed a Scoping Study.',2),
])
def test_collector_hit_outcomes(tmp_path,monkeypatch,cfg,text,expected):
    import au_ree_v2.stage_rules
    p=tmp_path/'source.txt';p.write_text(text,encoding='utf8')
    e=dict(path=str(p),sha256=s.legacy.sha256(p),kind='txt',url='https://example.test',dates=['2024-01-01'],associations=['test'])
    (tmp_path/'baseline.json').write_text(json.dumps([dict(project_id='p',original_sha256s=[e['sha256']])]))
    (tmp_path/'old.json').write_text(json.dumps(dict(keywords=['Scoping'],keyword_version='old')))
    cfg=dict(cfg,baseline_manifests='baseline.json',legacy_settings='old.json')
    monkeypatch.setattr(s.legacy,'original_inventory',lambda *a:({'p':[e]},{}))
    monkeypatch.setattr(au_ree_v2.stage_rules,'selected_mre',lambda *a:(False,{}))
    d={'decisions':[dict(decision_id=cfg['decision_id'],rule=s.RULE,decided_by='USER_EXPLICIT_APPROVAL',approval_evidence=s.EVIDENCE)]}
    fills,reviews,extra=s.collect_stage_three_point([row()],[],d,tmp_path,tmp_path,cfg)
    assert len(fills)==expected
    assert extra['hit_reviews'][0]['row_number']==2
    if fills:
        assert json.loads(fills[0]['provenance']['scope'])['hit_review_rows']==[2]
    else:
        assert reviews and all(f['value']!='B1' for f in fills)
