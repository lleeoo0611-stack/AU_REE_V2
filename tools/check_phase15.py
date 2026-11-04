"""Exact new technical exports plus existing MCDA/evidence invariants."""
import json
import sys
from pathlib import Path
from check_phase11 import verify,folder,csv_bytes

TECHNICAL=['technical_cells.csv','technical_derived.csv','technical_grade_recovery.csv','technical_flow_consistency.csv','technical_conflicts.csv','technical_scope_profiles.csv','technical_analysis.json']

def check(a,b,reference=False):
 result=verify(a,b,reference=reference);left,right=folder(a),folder(b)
 for name in TECHNICAL:
  if csv_bytes(left/name)!=csv_bytes(right/name):raise ValueError('Technical reconstruction differs: '+name)
 return dict(result,technical_exports=len(TECHNICAL),technical_exact=True)

if __name__=='__main__':print(json.dumps(check(sys.argv[1],sys.argv[2],reference='--reference' in sys.argv),indent=2))
