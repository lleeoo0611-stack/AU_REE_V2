import copy
import importlib.util
from pathlib import Path
import pytest
from au_ree_v2.round2_pipeline import write_csv

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('partial_publication_test',ROOT/'tools/publish_round2_partial.py')
partial=importlib.util.module_from_spec(spec);spec.loader.exec_module(partial)

def decision():
    return dict(decision_id=partial.DECISION_ID,rule=partial.RULE,scope=partial.SCOPE,decided_by='USER_EXPLICIT_APPROVAL',decided_date='2026-11-11',approval_evidence=partial.EVIDENCE)

def test_exact_partial_publication_approval():
    d=decision();assert partial.approval({'decisions':[d]})==d

@pytest.mark.parametrize('field',['decision_id','rule','scope','decided_by','decided_date','approval_evidence'])
def test_inexact_partial_approval_rejected(field):
    d=decision();d[field]='wrong'
    with pytest.raises(ValueError,match='EXPLICIT_APPROVAL_REQUIRED'):partial.approval({'decisions':[d]})

def test_missing_and_duplicate_approval_rejected():
    for records in ([],[decision(),decision()]):
        with pytest.raises(ValueError,match='EXPLICIT_APPROVAL_REQUIRED'):partial.approval({'decisions':records})

def test_nt_values_cannot_change(tmp_path):
    old=tmp_path/'old';new=tmp_path/'new';old.mkdir();new.mkdir()
    fields=['專案ID','州省地區','緯度','經度']
    row=dict(zip(fields,['nt','NT','','']))
    for path in (old,new):write_csv(path/'專案總表.csv',fields,[row])
    partial.nt_unchanged(old,new)
    write_csv(new/'專案總表.csv',fields,[dict(row,緯度='-20')])
    with pytest.raises(ValueError,match='NT_COORDINATES_CHANGED'):partial.nt_unchanged(old,new)

def test_publish_refuses_before_writing_when_acceptance_missing(monkeypatch,tmp_path):
    monkeypatch.setattr(partial,'validate_publication_inputs',lambda out: (_ for _ in ()).throw(ValueError('missing acceptance')))
    monkeypatch.setattr(partial.sys,'addaudithook',lambda hook:None)
    monkeypatch.setattr(partial.os,'chdir',lambda path:None)
    with pytest.raises(ValueError,match='missing acceptance'):partial.publish(tmp_path)
    assert not list(tmp_path.iterdir())

def test_current_note_provenance_change_is_separate(tmp_path):
    before=tmp_path/'before';after=tmp_path/'after';out=tmp_path/'out'
    for path in (before,after,out):path.mkdir()
    fields=['專案ID','總說明','原有欄位'];row=dict(zip(fields,['p','note','existing']))
    pf=['project_id','column','value','scope']
    p=[dict(zip(pf,['p',c,row[c],'original'])) for c in fields]
    for path in (before,after):write_csv(path/'專案總表.csv',fields,[row]);write_csv(path/'field_provenance.csv',pf,p)
    changed=copy.deepcopy(p);changed[1]['scope']='new stage provenance'
    write_csv(after/'field_provenance.csv',pf,changed)
    result=partial.presentation_changes(before,after,out)
    assert result['existing_note_value_changes']==0 and result['existing_note_provenance_changes']==1
    changed[2]['scope']='forbidden';write_csv(after/'field_provenance.csv',pf,changed)
    with pytest.raises(ValueError,match='PRESENTATION_CORE_CHANGED'):partial.presentation_changes(before,after,out)
