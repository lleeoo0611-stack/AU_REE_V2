import itertools
from au_ree_v2.round5_stage import priority,core_name,reassess_hit,build_aliases,collect_task1

def test_priority():
    for points in itertools.product(('PASS','UNCLEAR','FAIL'),repeat=3):
        assert priority(*points)==('FAIL' if 'FAIL' in points else 'UNCLEAR' if 'UNCLEAR' in points else 'PASS')

def test_core():
    assert core_name('Wudinna Rare Earths Project')=='Wudinna'
    assert core_name('Donald Rare Earth and Mineral Sands Project — MIN5532 resource scope')=='Donald'
    assert core_name('Diemals Li–REE Project')=='Diemals Li–REE'

def test_alias_ambiguity_and_ocr():
    rows=[dict(project_id=x,aliases=[dict(alias='Cascade',source='test')]) for x in ('a','b')]
    aliases=dict(projects=rows)
    row={'專案ID':'a','專案名稱':'Cascade Rare Earth Project'}
    settings={'source_classifications':{},'project_aliases':{},'future_patterns':[r'\bwill\b'],'completed_patterns':[r'\bcompleted\b']}
    entry=dict(sha256='abc',url='')
    h=dict(sentence='Cascade completed feasibility study.',physical_page=1,keyword='feasibility')
    r=reassess_hit(h,row,entry,set(),settings,aliases)
    assert r['point2']=='UNCLEAR' and r['reason2']=='AMBIGUOUS_ALIAS'
    r=reassess_hit(dict(h,ocr_confidence=79),row,entry,set(),settings,aliases)
    assert r['point3']=='UNCLEAR'

def test_frozen_812_review_is_deterministic_and_no_fill(monkeypatch):
    monkeypatch.setattr("au_ree_v2.round5_stage.verify_source_hits",lambda *a: {"status":"mocked unit test"})
    import csv,json
    from pathlib import Path
    from au_ree_v2.round5_stage import DECISION_ID,RULE,EVIDENCE
    repo=Path(__file__).resolve().parents[1]
    rows=list(csv.DictReader((repo/'results/asx-current/專案總表.csv').open(encoding='utf-8-sig')))
    decisions={'decisions':[dict(decision_id=DECISION_ID,rule=RULE,decided_by='USER_EXPLICIT_APPROVAL',approval_evidence=EVIDENCE)]}
    a=collect_task1(rows,[],decisions,repo,None)
    b=collect_task1(rows,[],decisions,repo,None)
    assert a==b and a[0]==[] and len(a[2]['hit_reviews'])==812
    old=json.loads((repo/'results/round4-3-2026-11-13/stage_search_manifests.json').read_text('utf8'))
    assert [m['blockers'] for m in old]==[m['blockers'] for m in a[2]['stage_search_manifests']]
    assert a[2]['network_requests']==0


def test_no_approval_no_replay():
    import pytest
    from pathlib import Path
    with pytest.raises(ValueError,match='EXPLICIT_APPROVAL'):
        collect_task1([],[],{},Path(__file__).resolve().parents[1],None)


def test_aliases_cover_all_92_rows_without_generic_names():
    from pathlib import Path
    from au_ree_v2.round5_stage import load_aliases,valid_alias
    aliases=load_aliases(Path(__file__).resolve().parents[1])
    assert len(aliases['projects'])==92
    assert all(valid_alias(a['alias']) for p in aliases['projects'] for a in p['aliases'])
    assert len({p['project_id'] for p in aliases['projects']})==92

def test_ambiguous_match_cannot_be_overridden_by_unique_match():
    aliases={'projects':[{'project_id':'a','aliases':[{'alias':'Cascade','source':'test'},{'alias':'Cascade Rare Earth Project','source':'test'}]},{'project_id':'b','aliases':[{'alias':'Cascade','source':'test'}]}]}
    row={'專案ID':'a','專案名稱':'Cascade Rare Earth Project'}
    settings={'source_classifications':{},'project_aliases':{},'future_patterns':[],'completed_patterns':[r'completed']}
    h={'sentence':'Cascade Rare Earth Project completed feasibility study.','physical_page':1,'keyword':'study'}
    result=reassess_hit(h,row,{'sha256':'x','url':''},set(),settings,aliases)
    assert result['point2']=='UNCLEAR' and result['reason2']=='AMBIGUOUS_ALIAS'


def test_source_verifier_rejects_changed_hit_identity(monkeypatch):
    import pytest
    from au_ree_v2.round5_stage import verify_source_hits
    monkeypatch.setattr('au_ree_v2.round4_stage.collect_stage_three_point',lambda *a:([],[],{'hit_reviews':[]}))
    h=dict(project_id='a',source_sha256='x',physical_page=1,keyword='study',sentence='Original sentence.')
    with pytest.raises(ValueError,match='IDENTITY_MISMATCH'):
        verify_source_hits([],[],{},'.','census',[h])
