import copy
import sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from run_round4 import comparison_report

def record(n,original,all_columns,tiered,excluded=0):
    def metric(d):return {'filled':n,'denominator':d,'coverage':n/d}
    return {'original_53_columns':metric(original),'all_retained_columns':metric(all_columns),'tiered_coverage':{'combined':metric(tiered),'tier1':{'not_applicable_stage_excluded':16 if excluded else 0},'tier2':{'not_applicable_stage_excluded':excluded-16 if excluded else 0}},'not_applicable_stage_excluded':excluded}

def scenario():
    base=record(2170,4929,4743,3038);merged=record(2137,4876,4692,2987);classified=record(2137,4876,4656,2951,36)
    tasks=[dict(merged,new_cells=0),dict(classified,new_cells=0),{'new_cells':8},{'new_cells':0},{'new_cells':4},{'new_cells':0}]
    final=record(2149,4876,4656,2951,36)
    return tasks,base,final

def test_report_separates_merge_applicability_and_research():
    tasks,base,final=scenario();r=comparison_report(tasks,base,final,{'tenement_centroid_rows':2})
    assert r['evidence_changes']=={'baseline':2170,'merge_delta':-33,'new_research':12,'final':2149}
    assert r['denominator_changes']['merge']=={'original_53_columns':-53,'all_retained_columns':-51,'tiered_combined':-51}
    assert r['denominator_changes']['not_applicable_stage']=={'original_53_columns':0,'all_retained_columns':-36,'tiered_combined':-36}
    assert r['applicability']['additional_after_task1']==0

def test_later_stage_new_classification_separately_counted():
    tasks,base,final=scenario();tasks[3]['new_cells']=2;final=record(2151,4876,4655,2950,37)
    r=comparison_report(tasks,base,final,{})
    assert r['new_research_cells']==14 and r['applicability']['additional_after_task1']==1

@pytest.mark.parametrize('field',['denominator','filled'])
def test_unreconciled_counts_block_report(field):
    tasks,base,final=scenario();final['original_53_columns'][field]+=1
    with pytest.raises(ValueError,match='RECONCILIATION'):comparison_report(tasks,base,final,{})
