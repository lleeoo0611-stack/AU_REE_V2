"""Append-only acceptance independent of current production counts."""
import copy
import json
from pathlib import Path
import pytest
from au_ree_v2.round2_pipeline import apply_fills,write_csv,write_json,read_csv,metrics
from au_ree_v2.iteration_review import audit_summary
from au_ree_v2.store import filehash

ROOT=Path(__file__).resolve().parents[1]

@pytest.fixture
def sample(tmp_path):
    before=tmp_path/'before';before.mkdir()
    columns=json.loads((ROOT/'config/project_summary_columns.json').read_text('utf8'))+['ASX代碼']
    row=dict.fromkeys(columns,'');row.update({'專案ID':'test','專案名稱':'Test','礦床型態':'Clay hosted'})
    pfields=['project_id','column','value','source_sha256','source_url','locator','method','scope']
    trace=[dict(project_id='test',column=k,value=v,source_sha256='a'*64,source_url='https://example.org/source',locator='p.1',method='SOURCE',scope='') for k,v in row.items() if v]
    missing=[dict(project_id='test',column=k,reason='NO_SOURCE_VALUE',blank_class='',blank_rule_id='') for k,v in row.items() if not v]
    write_csv(before/'專案總表.csv',columns,[row]);write_csv(before/'field_provenance.csv',pfields,trace)
    write_csv(before/'missing_fields.csv',list(missing[0]),missing)
    write_csv(before/'census_inventory.csv',['entity_id'],[dict(entity_id='test')])
    write_json(before/'summary.json',dict(version='census-project-summary-v3-asx-identity',base_contract_columns=52,identity_ledger_sha256='a'*64,output_hashes={n:filehash(before/n) for n in ('專案總表.csv','field_provenance.csv','missing_fields.csv','census_inventory.csv')}))
    write_json(before/'audit.json',audit_summary(before))
    decision=dict(decision_id='test-decision',decided_by='USER_EXPLICIT_APPROVAL')
    fill=dict(project_id='test',column='礦床型態代碼',value='iac',method='RULE',decision_id='test-decision',provenance=dict(trace[0],column='礦床型態代碼',value='iac',method='RULE'))
    return before,dict(decisions=[decision]),fill

def test_append_preserves_every_old_trace_and_inventory(sample,tmp_path):
    before,decisions,fill=sample;after=tmp_path/'after'
    oldtrace=read_csv(before/'field_provenance.csv')[1]
    assert len(apply_fills(before,after,[fill],decisions,ROOT))==1
    assert read_csv(after/'field_provenance.csv')[1][:-1]==oldtrace
    assert (before/'census_inventory.csv').read_bytes()==(after/'census_inventory.csv').read_bytes()
    assert metrics(after)['filled']==metrics(before)['filled']+1
    assert audit_summary(after)['provenance_complete']

@pytest.mark.parametrize('mutation',['existing','duplicate','unapproved','empty','no_source'])
def test_fail_closed(sample,tmp_path,mutation):
    before,decisions,fill=sample
    fills=[copy.deepcopy(fill)]
    if mutation=='existing':fills[0]['column']='專案名稱'
    if mutation=='duplicate':fills.append(copy.deepcopy(fill))
    if mutation=='unapproved':decisions['decisions']=[]
    if mutation=='empty':fills[0]['value']=''
    if mutation=='no_source':fills[0]['provenance']['source_sha256']=''
    with pytest.raises(ValueError):apply_fills(before,tmp_path/'after',fills,decisions,ROOT)
    assert not (tmp_path/'after').exists()

def test_identical_inputs_produce_bitwise_identical_outputs(sample,tmp_path):
    from au_ree_v2.coverage_task_audit import identical_replays
    before,decisions,fill=sample
    for name in ('a','b'):apply_fills(before,tmp_path/name,[fill],decisions,ROOT)
    assert len(identical_replays(tmp_path/'a',tmp_path/'b'))==6

def test_nt_acceptance_blocks_publication_before_current_write(monkeypatch,tmp_path):
    import importlib.util
    spec=importlib.util.spec_from_file_location('round2_runner_test',ROOT/'tools/run_round2.py')
    runner=importlib.util.module_from_spec(spec);spec.loader.exec_module(runner)
    records={'C':{'nt_real_control_point_validated':False}}
    monkeypatch.setattr(runner,'write_summary',lambda: ({},records,tmp_path))
    with pytest.raises(ValueError,match='PUBLICATION_BLOCKED_NT'):
        runner.publish()
    assert not list(tmp_path.iterdir())
    assert runner.publication_status(records)['task_c_acceptance']=='PARTIAL_NT_ACCEPTANCE_NOT_MET'
    assert not runner.publication_status({'C':{}})['ready_to_publish']

def test_summary_reuse_requires_identical_content(tmp_path):
    import importlib.util
    spec=importlib.util.spec_from_file_location('round2_runner_test2',ROOT/'tools/run_round2.py')
    runner=importlib.util.module_from_spec(spec);spec.loader.exec_module(runner)
    target=tmp_path/'comparison.json'
    runner.write_unchanged_or_new(target,{'new_cells':38})
    original=target.read_bytes()
    runner.write_unchanged_or_new(target,{'new_cells':38})
    assert target.read_bytes()==original
    with pytest.raises(ValueError,match='EXISTING_SUMMARY_DIFFERS'):
        runner.write_unchanged_or_new(target,{'new_cells':39})
    assert target.read_bytes()==original
