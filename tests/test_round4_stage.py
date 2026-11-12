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

def alias_config(tmp_path):
    config=tmp_path/'config';config.mkdir()
    alias=dict(rule='SAME_ISSUER_RENAME_RESEARCHER_APPROVED',decision_id='round4-issuer-merge-20261113',current_name='GoldArc Resources Limited',current_asx='GA8',former_name='Asra Minerals Limited',former_asx='ASR',keep_project_id=s.MERGE_KEEP,drop_project_id=s.MERGE_DROP)
    (config/'issuer_aliases.json').write_text(json.dumps({'aliases':[alias]}),encoding='utf8')
    (config/'researcher_rule_decisions.json').write_text(json.dumps({'decisions':[dict(decision_id=alias['decision_id'],rule=alias['rule'],decided_by='USER_EXPLICIT_APPROVAL',approval_evidence=s.EVIDENCE)]}),encoding='utf8')
    return alias


def test_alias_inventory_unions_originals_dates_paths_issues_without_mutation(tmp_path,monkeypatch):
    import copy
    alias_config(tmp_path)
    def entry(sha,date,path,association):return dict(sha256=sha,path=path,paths=[path],dates=[date],associations=[association],url='https://example.test/'+sha,kind='pdf')
    raw={s.MERGE_KEEP:[entry('common','2024','keep.pdf','keep'),entry('keep-only','2026','k.pdf','keep')],s.MERGE_DROP:[entry('common','2025','drop.pdf','drop'),entry('drop-only','2025','d.pdf','drop')]}
    original=copy.deepcopy(raw)
    def inventory(repo,census,ids):
        assert ids=={s.MERGE_KEEP,s.MERGE_DROP}
        return raw,{s.MERGE_DROP:[dict(reason='DATE_UNKNOWN',sha256='drop-only')]}
    monkeypatch.setattr(s.legacy,'original_inventory',inventory)
    result,issues,aliases=s.round4_original_inventory(tmp_path,tmp_path,{s.MERGE_KEEP})
    assert raw==original and set(result)=={s.MERGE_KEEP}
    assert [e['sha256'] for e in result[s.MERGE_KEEP]]==['common','drop-only','keep-only']
    common=result[s.MERGE_KEEP][0]
    assert common['dates']==['2024','2025'] and common['paths']==['drop.pdf','keep.pdf']
    assert common['associations']==['drop','keep']
    assert common['original_project_ids']==sorted([s.MERGE_KEEP,s.MERGE_DROP])
    assert {r['project_id'] for r in common['original_association_records']}=={s.MERGE_KEEP,s.MERGE_DROP}
    assert issues[s.MERGE_KEEP][0]['original_project_id']==s.MERGE_DROP
    baseline=[dict(project_id=pid,original_sha256s=['common']) for pid in (s.MERGE_KEEP,s.MERGE_DROP)]
    shared=s.canonical_shared_projects(result,baseline,aliases)
    assert shared['common']=={s.MERGE_KEEP}
    baseline.append(dict(project_id='unrelated',original_sha256s=['common']))
    assert s.canonical_shared_projects(result,baseline,aliases)['common']=={s.MERGE_KEEP,'unrelated'}


def test_alias_scope_cannot_expand_to_other_issuer(tmp_path,monkeypatch):
    alias=alias_config(tmp_path);alias['drop_project_id']='unapproved-project'
    (tmp_path/'config/issuer_aliases.json').write_text(json.dumps({'aliases':[alias]}))
    with pytest.raises(ValueError,match='ALIAS_SCOPE_NOT_APPROVED'):
        s.round4_original_inventory(tmp_path,tmp_path,{s.MERGE_KEEP})

def test_excluded_gis_never_opened_scanned_or_rendered_but_manifest_retained(tmp_path,monkeypatch,cfg):
    import au_ree_v2.stage_rules
    missing=tmp_path/'must-not-open.json'
    sha='excluded-gis-sha'
    e=dict(path=str(missing),paths=[str(missing)],sha256=sha,kind='json',url='https://services.ga.gov.au/gis/rest/services/Electricity_Infrastructure/MapServer/2',dates=[],associations=['census:records'])
    old_hit=dict(source_sha256=sha,physical_page=None,keyword='construction',text='Under Construction')
    old_block=dict(reason='ARCHIVED_ORIGINAL_DATE_UNKNOWN',source_sha256=sha)
    (tmp_path/'baseline.json').write_text(json.dumps([dict(project_id='p',original_sha256s=[sha],hits=[old_hit],blockers=[old_block])]))
    (tmp_path/'old.json').write_text(json.dumps(dict(keywords=['construction'],keyword_version='old')))
    cfg=dict(cfg,baseline_manifests='baseline.json',legacy_settings='old.json')
    monkeypatch.setattr(s.legacy,'original_inventory',lambda *a:({'p':[e]},{'p':[dict(reason='ARCHIVED_ORIGINAL_MISSING',source_sha256=sha)]}))
    monkeypatch.setattr(au_ree_v2.stage_rules,'selected_mre',lambda *a:(False,{}))
    def forbidden(*a,**kw):raise AssertionError('Excluded source must not be parsed or rendered')
    monkeypatch.setattr(s.legacy,'scan_original',forbidden)
    monkeypatch.setattr(s.legacy,'verify_visual_reviews',forbidden)
    monkeypatch.setattr(s,'complete_hits',forbidden)
    d={'decisions':[dict(decision_id=cfg['decision_id'],rule=s.RULE,decided_by='USER_EXPLICIT_APPROVAL',approval_evidence=s.EVIDENCE)]}
    fills,reviews,extra=s.collect_stage_three_point([row()],[],d,tmp_path,tmp_path,cfg)
    assert not fills
    m=extra['stage_search_manifests'][0];original=m['originals'][0]
    assert m['original_sha256s']==[sha]
    assert original['source_sha256']==sha and original['source_url']==e['url']
    assert original['dates']==[] and original['associations']==e['associations']
    assert original['original_project_ids']==['p']
    assert original['point1']=='FAIL' and original['source_type_reason']
    assert original['scan_status']=='EXCLUDED_POINT1_FAIL_NOT_OPENED_OR_SCANNED'
    assert original['physical_pages_scanned']==0
    assert {b['reason'] for b in m['blockers']}=={'NO_DATED_PROJECT_SPECIFIC_ORIGINAL_FOR_INFERENCE'}
    assert {b['reason'] for b in original['ignored_blockers']}=={'ARCHIVED_ORIGINAL_DATE_UNKNOWN','ARCHIVED_ORIGINAL_MISSING'}
    assert extra['hit_reviews']==[]
    prior=original['excluded_prior_hit_contexts'][0]
    assert prior['point1']=='FAIL' and prior['text']=='Under Construction'
    assert prior['review_basis']=='FROZEN_ROUND3_CONTEXT_NOT_RESCANNED'
