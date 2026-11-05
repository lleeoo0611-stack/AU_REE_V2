"""Existing point/rank invariants plus exact unified Technical and batch exports."""
import json
import sys
from check_phase15 import check as previous
from check_phase11 import folder,csv_bytes

EXPORTS=['technical_observations.csv','technical_project_profiles.csv','technical_burden_evidence.csv','technical_comparison_groups.csv','technical_model_decision.json','minedex_resource_batch.csv','minedex_resource_batch.json']

def check(a,b,reference=False):
    result=previous(a,b,reference=reference);left,right=folder(a),folder(b)
    for name in EXPORTS:
        if csv_bytes(left/name)!=csv_bytes(right/name):raise ValueError('Unified Technical replay differs: '+name)
    if not reference:
        a_sha=json.loads((left/'summary.json').read_text())['logical_database_sha256']
        b_sha=json.loads((right/'summary.json').read_text())['logical_database_sha256']
        if a_sha!=b_sha:raise ValueError('Independent clean logical databases differ')
    return dict(result,phase16_exports=len(EXPORTS),phase16_exact=True,clean_logical_database_exact=True if not reference else None)

if __name__=='__main__':print(json.dumps(check(sys.argv[1],sys.argv[2],reference='--reference' in sys.argv),indent=2))
