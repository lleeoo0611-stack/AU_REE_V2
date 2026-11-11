import copy,json
from pathlib import Path
import pytest
from au_ree_v2 import round3_schema as s
from au_ree_v2.blank_classification import load_blank_rules,classify_blanks
from au_ree_v2.round2_pipeline import read_csv,write_csv
from au_ree_v2.coverage_task_audit import identical_replays
ROOT=Path(__file__).resolve().parents[1]

def sample(ore='',trace_ore=True):
    columns=json.loads((ROOT/'config/project_summary_columns.json').read_text('utf8'))+['ASX代碼']
    row=dict.fromkeys(columns,'');row.update({'專案ID':'test','專案名稱':'Test','礦石蘊藏量_Mt':ore,'NdPr蘊藏量_kt_需兩者皆公布':'1'})
    trace=[dict(project_id='test',column=c,value=v,source_sha256='a'*64) for c,v in row.items() if v and (trace_ore or c!='礦石蘊藏量_Mt')]
    missing=[dict(project_id='test',column=c,reason='NO_SOURCE_VALUE',blank_class='',blank_rule_id='') for c,v in row.items() if not v]
    return row,trace,missing

def test_current_columns_and_rule_targets_retire_two_empty_columns():
    cfg=s.config(ROOT);row,_,_=sample();assert len(row)==51
    assert not set(s.RETIRED)&set(row)
    rules=load_blank_rules(ROOT/'config/blank_classification.json')['config']
    assert 'NOT_APPLICABLE_NO_MRE' in rules['excluded_from_adjusted_denominator']
    for rule in rules['rules']:
        assert not set(s.RETIRED)&set(rule['columns'])
        assert not set(s.RETIRED)&set(rule['when'].get('empty_fields',[]))
    assert set(cfg['resource_columns'])|set(cfg['nonresource_columns'])==set(row)

def test_no_mre_only_blank_resource_cells_are_reclassified():
    row,trace,missing=sample();before=copy.deepcopy(row);oldtrace=copy.deepcopy(trace)
    classify_blanks([row],missing,trace,load_blank_rules(ROOT/'config/blank_classification.json'))
    assert row==before and trace==oldtrace
    assert next(m for m in missing if m['column']=='TREO品位_pct')['blank_class']=='NOT_APPLICABLE_NO_MRE'
    assert next(m for m in missing if m['column']=='緯度')['blank_class']=='UNKNOWN'
    assert all(m['column']!='NdPr蘊藏量_kt_需兩者皆公布' for m in missing)

@pytest.mark.parametrize('trace_ore',[True,False])
def test_positive_or_unresolved_selected_mre_never_excluded(trace_ore):
    row,trace,missing=sample('2',trace_ore)
    classify_blanks([row],missing,trace,load_blank_rules(ROOT/'config/blank_classification.json'))
    assert next(m for m in missing if m['column']=='TREO品位_pct')['blank_class']=='UNKNOWN'
    assert all(m['blank_class']!='NOT_APPLICABLE_NO_MRE' for m in missing)

def test_filled_resource_exception_counts_in_both_numerator_denominator():
    row,trace,_=sample();cov=s.coverage([row],trace,s.config(ROOT))
    tier=cov['tiered_coverage']['tier2']
    assert tier['existing_filled_resource_cells']==1
    assert tier['filled']==3 and tier['denominator']==len(s.config(ROOT)['nonresource_columns'])+1
    assert cov['all_retained_columns']['denominator']==51

@pytest.mark.parametrize('mutation',['duplicate','overlap','missing','retired'])
def test_invalid_coverage_partition_fails(mutation):
    row,trace,_=sample();cfg=s.config(ROOT)
    if mutation=='duplicate':cfg['resource_columns'].append(cfg['resource_columns'][0])
    if mutation=='overlap':cfg['nonresource_columns'].append(cfg['resource_columns'][0])
    if mutation=='missing':cfg['nonresource_columns'].pop()
    if mutation=='retired':cfg['nonresource_columns'].append(s.RETIRED[0])
    with pytest.raises(ValueError,match='PARTITION'):s.coverage([row],trace,cfg)

def test_migration_rebuilds_archive_and_is_bitwise_deterministic(tmp_path):
    source=ROOT/'results/round2-D-2026-11-11/projection'
    for name in ('a','b'):s.migrate(source,tmp_path/name,ROOT)
    assert len(identical_replays(tmp_path/'a',tmp_path/'b'))==6
    archive=json.loads((tmp_path/'a'/s.ARCHIVE).read_text('utf8'))
    for name,record in archive['files'].items():assert s.unpack(record)==(source/name).read_bytes()
    summary=json.loads((tmp_path/'a/summary.json').read_text('utf8'))
    assert summary['columns']==51 and summary['tiered_coverage']['tier1']['rows']==38 and summary['tiered_coverage']['tier2']['rows']==55
    assert summary['all_retained_columns']['filled']==2141

def test_presentation_keeps_existing_notes_and_traces(tmp_path):
    source=ROOT/'results/round2-D-2026-11-11/projection';s.migrate(source,tmp_path/'core',ROOT)
    s.present(tmp_path/'core',tmp_path/'shown',ROOT)
    _,old=read_csv(ROOT/'results/asx-current/field_provenance.csv');_,new=read_csv(tmp_path/'shown/field_provenance.csv')
    assert [p for p in old if p['column']=='總說明']==[p for p in new if p['column']=='總說明']
    assert s.audit(tmp_path/'shown')['columns']==51

def test_archive_corruption_rejected():
    import base64,gzip
    with pytest.raises(ValueError,match='ARCHIVE_SHA'):s.unpack(dict(encoding='gzip-base64',sha256='0'*64,data=base64.b64encode(gzip.compress(b'x',mtime=0)).decode()))

@pytest.mark.parametrize('field',['rule','scope','approval_evidence','decided_by','decided_date'])
def test_round3_registry_extension_cannot_weaken_historical_gate(field):
    from au_ree_v2.approved_coverage_audit import validate_decisions
    registry=json.loads((ROOT/'config/researcher_rule_decisions.json').read_text('utf8'))
    assert len(validate_decisions(registry))==19
    next(d for d in registry['decisions'] if d['decision_id']=='round3-tiered-coverage-20261111')[field]='invalid'
    with pytest.raises(ValueError):validate_decisions(registry)
