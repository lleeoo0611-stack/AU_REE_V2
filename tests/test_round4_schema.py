from pathlib import Path
import copy,json
import pytest
from au_ree_v2 import round4_schema as s
from au_ree_v2.round2_pipeline import read_csv
ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'results/round3-4-2026-11-11/projection'

@pytest.fixture
def merged(tmp_path):
    out=tmp_path/'merge';s.merge(BASE,out,ROOT);return out

def test_round4_merge_scoped_and_reconstructable(merged):
    _,rows=read_csv(merged/'專案總表.csv');assert len(rows)==92
    assert s.DROP not in {r['專案ID'] for r in rows}
    ar=json.loads((merged/s.ARCHIVE).read_text('utf8'))
    original=next(r for r in read_csv(BASE/'專案總表.csv')[1] if r['專案ID']==s.DROP)
    assert ar['merge']['merged_rows'][0]['row']==original
    assert next(r for r in rows if r['專案ID']==s.KEEP)['開發商']=='GoldArc Resources Limited'
    assert s.audit(merged,ROOT)['provenance_complete']

def test_round4_classification_only_and_denominators(merged,tmp_path):
    out=tmp_path/'classify';new,changes,_,_=s.classify(merged,out,ROOT)
    assert not new and changes
    assert (out/'專案總表.csv').read_bytes()==(merged/'專案總表.csv').read_bytes()
    assert (out/'field_provenance.csv').read_bytes()==(merged/'field_provenance.csv').read_bytes()
    a=json.loads((merged/'summary.json').read_text());b=json.loads((out/'summary.json').read_text())
    assert a['original_53_columns']==b['original_53_columns']
    assert a['all_retained_columns']['denominator']-b['all_retained_columns']['denominator']==b['not_applicable_stage_excluded']
    assert all(g['blank_class']!='PENDING_CODEBOOK' for g in read_csv(out/'missing_fields.csv')[1])

def test_round4_product_reactivates_without_filling():
    rows=[{'專案ID':'test','開發階段代碼':'A1',s.PRODUCT:''}];g=[{'project_id':'test','column':s.PRODUCT,'reason':'NO_PRODUCT'}]
    s.classify_gaps(rows,g,ROOT);assert g[0]['blank_class']=='NOT_APPLICABLE_STAGE'
    for stage in ('B1','D',''):
        rows[0]['開發階段代碼']=stage;s.classify_gaps(rows,g,ROOT)
        assert g[0]['blank_class']=='UNKNOWN' and rows[0][s.PRODUCT]==''

def test_round4_presentation_preserves_notes(merged,tmp_path):
    out=tmp_path/'presentation';s.present(merged,out,ROOT);assert s.audit(out,ROOT)['preexisting_notes_preserved']
    rows={r['專案ID']:r for r in read_csv(out/'專案總表.csv')[1]}
    ar=json.loads((merged/s.ARCHIVE).read_text());old={r['專案ID']:r for r in s.old.archive_csv(ar['presentation_files'],'專案總表.csv')}
    assert all(r['總說明']==old[pid]['總說明'] for pid,r in rows.items())

def test_round4_duplicate_or_overwrite_rejected(merged,tmp_path):
    with pytest.raises(ValueError,match='NOT_APPROVED_BLANK'):
        s.fill(merged,tmp_path/'bad',[dict(project_id=s.KEEP,column='開發商',value='Wrong',decision_id='d')],{'decisions':[dict(decision_id='d',decided_by='USER_EXPLICIT_APPROVAL')]},ROOT)

def test_round4_merge_requires_explicit_approval(tmp_path,monkeypatch):
    original=s._load
    def load(path):
        if Path(path).name=='researcher_rule_decisions.json':return {'decisions':[]}
        return original(path)
    monkeypatch.setattr(s,'_load',load)
    with pytest.raises(ValueError,match='MERGE_NOT_APPROVED'):s.merge(BASE,tmp_path/'blocked',ROOT)

def test_round4_issuer_metadata_is_not_stale(merged):
    p=next(r for r in read_csv(merged/'field_provenance.csv')[1] if r['project_id']==s.KEEP and r['column']=='開發商')
    assert p['source_url']=='https://investorpa.com/announcement-pdf/20260330/275183.pdf'
    assert p['publication_date']==p['document_issue_date']=='2026-03-30'
    assert p['publication_date_precision']=='day'
    assert p['effective_date']==p['effective_date_role']==''
    original=next(r for r in read_csv(BASE/'field_provenance.csv')[1] if r['project_id']==s.KEEP and r['column']=='開發商')
    assert json.loads(p['supporting_provenance'])==[original]

def test_round4_arbitrary_presentation_change_rejected(merged,monkeypatch):
    ar=json.loads((merged/s.ARCHIVE).read_text())
    original=s.old.archive_csv
    def tampered(records,name):
        rows=original(records,name)
        if records is ar['presentation_files'] and name=='專案總表.csv':rows[0]['開發商']='Unauthorized replacement'
        return rows
    monkeypatch.setattr(s.old,'archive_csv',tampered)
    with pytest.raises(ValueError,match='UNAPPROVED_PRESENTATION_BASELINE_DIFFERENCE'):
        s.presentation_records(read_csv(merged/'專案總表.csv')[1],read_csv(merged/'field_provenance.csv')[1],read_csv(merged/'missing_fields.csv')[1],ar)
