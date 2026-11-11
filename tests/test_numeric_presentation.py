import copy,json
from pathlib import Path
from decimal import Decimal
import pytest
from au_ree_v2 import numeric_presentation as n,round3_schema as s
from au_ree_v2.round2_pipeline import read_csv
ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'results/asx-current'

@pytest.fixture(autouse=True)
def historical_source(tmp_path,monkeypatch):
    global SOURCE
    if (SOURCE/n.ARCHIVE).exists():
        original=tmp_path/'original';original.mkdir()
        archive=json.loads((SOURCE/n.ARCHIVE).read_text('utf8'))
        for name,rec in archive['files'].items():(original/name).write_bytes(s.unpack(rec))
        monkeypatch.setattr(__import__(__name__,fromlist=['SOURCE']),'SOURCE',original)

def review():
    return next(r for r in json.loads((ROOT/'config/asx_source_reviews.json').read_text('utf8'))['reviews'] if r.get('review_id')=='cycle1_wim100_hm_oxides2026')

def test_exact_original_tokens_not_invented_significant_figures():
    r=review();cols,_=read_csv(SOURCE/'專案總表.csv')
    values=n.exact_hm_values(r,cols)
    assert values['NdPr蘊藏量_kt_需兩者皆公布']==Decimal('89.75')
    assert next(o['original_token'] for o in r['observations'] if o.get('basis')=='Nd2O3')=='0.28'

@pytest.mark.parametrize('bad',['nan','Infinity','1e2','-1','1,000',''])
def test_invalid_source_decimal_rejected(bad):
    with pytest.raises(ValueError):n.token(bad)

def test_source_scope_mismatch_never_changes_value():
    _,rows=read_csv(SOURCE/'專案總表.csv');_,trace=read_csv(SOURCE/'field_provenance.csv')
    r=review();r['scope']='other resource'
    newrows,newtrace,changes=n.derive(rows,trace,[r])
    assert (newrows,newtrace,changes)==(rows,trace,[])

def test_real_value_difference_is_not_rounded_away():
    _,rows=read_csv(SOURCE/'專案總表.csv');_,trace=read_csv(SOURCE/'field_provenance.csv');r=review()
    next(row for row in rows if row['專案ID']==r['project_id'])['NdPr蘊藏量_kt_需兩者皆公布']='89.76'
    with pytest.raises(ValueError,match='NOT_BINARY_TAIL'):n.derive(rows,trace,[r])

def test_two_presentations_identical_and_old_bytes_recoverable(tmp_path):
    a=tmp_path/'a';b=tmp_path/'b';n.present(SOURCE,a,ROOT);n.present(SOURCE,b,ROOT)
    assert {p.name:p.read_bytes() for p in a.iterdir()}=={p.name:p.read_bytes() for p in b.iterdir()}
    archive=json.loads((a/n.ARCHIVE).read_text('utf8'))
    for name,record in archive['files'].items():assert s.unpack(record)==(SOURCE/name).read_bytes()
    assert s.audit(a)['new_cells']==0
    changes=json.loads((a/n.TRACE).read_text('utf8'))['changes']
    assert any(c['old_value']=='89.75000000000001' and c['new_value']=='89.75' for c in changes)
    _,before=read_csv(SOURCE/'專案總表.csv');_,after=read_csv(a/'專案總表.csv')
    for old,new in zip(before,after):
        for col in old:
            if old[col]!=new[col]:assert abs(Decimal(old[col])-Decimal(new[col]))<Decimal('1e-10')
        assert old['有TREO資源估計']==new['有TREO資源估計']

@pytest.mark.parametrize('name',['專案總表.csv','field_provenance.csv','numeric_presentation_changes.json','numeric_presentation_original.json','validation.json'])
def test_tampering_fails_audit(tmp_path,name):
    out=tmp_path/'out';n.present(SOURCE,out,ROOT)
    text=(out/name).read_text('utf-8-sig');(out/name).write_text(text.replace('89.75','89.76'),encoding='utf8')
    if name==n.ARCHIVE:
        value=json.loads((out/name).read_text('utf8'));value['files']['專案總表.csv']['sha256']='0'*64
        (out/name).write_text(json.dumps(value),encoding='utf8')
    if name=='validation.json':(out/name).write_text('{}',encoding='utf8')
    with pytest.raises((ValueError,KeyError)):s.audit(out)


def test_non_hm_review_not_used():
    r=review();r['partial_resource_projection']['mode']='OTHER'
    _,rows=read_csv(SOURCE/'專案總表.csv');_,trace=read_csv(SOURCE/'field_provenance.csv')
    assert n.derive(rows,trace,[r])==(rows,trace,[])

@pytest.mark.parametrize('kind',['missing_token','duplicate_review'])
def test_missing_token_or_ambiguous_review_fails(kind):
    r=review();_,rows=read_csv(SOURCE/'專案總表.csv');_,trace=read_csv(SOURCE/'field_provenance.csv')
    if kind=='missing_token':
        next(o for o in r['observations'] if o.get('original_unit')=='%HM').pop('original_token')
        with pytest.raises((KeyError,ValueError)):n.derive(rows,trace,[r])
    else:
        with pytest.raises(ValueError,match='AMBIGUOUS'):n.derive(rows,trace,[r,r])
