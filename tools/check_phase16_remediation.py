"""Unchanged historical rank/RNG checks plus remediated source/semantic exports."""
import csv,json,sys
from pathlib import Path
from check_phase16 import check as previous
from check_phase11 import folder,csv_bytes
from check_replay import equivalent
EXTRA=['minedex_commodity_decisions.csv','technical_coverage_gaps.csv','technical_identity_bridge.csv','technical_burden_remediation.csv','technical_input_intensities.csv','technical_product_constraints.csv','technical_functional_unit_check.csv','technical_analysis_decisions.json','technical_panel_eligibility.csv','technical_panel_cases.csv','technical_panel_inputs.csv','technical_scope_sensitivity.csv','technical_membership_sensitivity.csv']
def check(a,b,reference=False):
    result=previous(a,b,reference=reference);left,right=folder(a),folder(b)
    for name in EXTRA:
        if csv_bytes(left/name)!=csv_bytes(right/name):raise ValueError('Remediation evidence differs: '+name)
    name='technical_definition_sensitivity.csv';differences=[]
    if not reference:
        if csv_bytes(left/name)!=csv_bytes(right/name):raise ValueError('Same-environment Technical sensitivity differs')
    else:
        with (left/name).open(encoding='utf8',newline='') as f:x=list(csv.DictReader(f))
        with (right/name).open(encoding='utf8',newline='') as f:y=list(csv.DictReader(f))
        if len(x)!=len(y):raise ValueError('Technical sensitivity row count differs')
        for i,(r,s) in enumerate(zip(x,y)):
            if set(r)!=set(s):raise ValueError('Technical sensitivity columns differ')
            for k in r:
                if r[k]==s[k]:continue
                if k not in ('score','baseline_score','score_change') or not equivalent(r[k],s[k]):raise ValueError('Technical sensitivity field differs: '+k)
                differences.append(dict(row=i,column=k,absolute_difference=abs(float(r[k])-float(s[k]))))
    return dict(result,remediation_exact_exports=len(EXTRA),technical_sensitivity_static_point_differences=differences)
if __name__=='__main__':print(json.dumps(check(sys.argv[1],sys.argv[2],reference='--reference' in sys.argv),indent=2))
