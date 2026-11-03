"""Exact Phase11 MCDA replay, including Monte Carlo frequencies (no tolerance)."""
import csv
import json
import sys
from pathlib import Path


def folder(path):
    path=Path(path)
    return Path(json.loads(path.read_text())['output_dir']) if path.is_file() else path


def csv_bytes(path):
    # CSV transport newline only; every field/value remains byte-exact.
    return path.read_bytes().replace(b'\r\n',b'\n')


def verify(before,after,reference=False):
    a,b=folder(before),folder(after);checked=[];platform_differences=[]
    for f in sorted(a.glob('*/*.csv')):
        relative=f.relative_to(a)
        if f.name=='runtime.csv':
            x=next(csv.DictReader(f.open()));y=next(csv.DictReader((b/relative).open()))
            # R platform/version string is descriptive; the RNG algorithm and
            # every numerical scientific output must still match exactly.
            if {k:v for k,v in x.items() if k!='R_version'}!={k:v for k,v in y.items() if k!='R_version'}:
                raise ValueError('Runtime method contract differs: '+str(relative))
        elif reference and f.name in ('matrix.csv','ranking.csv','ahp_audit.csv'):
            # Reference portability uses the unchanged historical point-science
            # comparison. Same-environment replay above/below remains exact.
            # Rank and every stochastic statistic are always exact, in both modes.
            from check_replay import equivalent
            x=list(csv.DictReader(f.open(encoding='utf-8-sig')))
            y=list(csv.DictReader((b/relative).open(encoding='utf-8-sig')))
            if len(x)!=len(y):raise ValueError('Reference row count differs: '+str(relative))
            for index,(left,right) in enumerate(zip(x,y)):
                if set(left)!=set(right):raise ValueError('Reference columns differ: '+str(relative))
                for key in left:
                    if left[key]==right[key]:continue
                    # Only computed matrix scores, fixed-method scores and AHP
                    # diagnostics may use the pre-existing point comparison.
                    allowed=(f.name=='matrix.csv' and (key.endswith(('_alt','_lower','_upper')) or key in ('R1','R2','S1','T1','TC1','TC2','D1','C1','I1','I2','I3','I4'))) or (f.name=='ranking.csv' and key in ('saw','promethee','topsis')) or (f.name=='ahp_audit.csv' and key=='CR')
                    if not allowed or not equivalent(left[key],right[key]):raise ValueError('Reference scientific field differs: '+str(relative)+':'+key)
                    platform_differences.append(dict(file=relative.as_posix(),row=index,column=key,reference=left[key],rebuilt=right[key],absolute_difference=abs(float(left[key])-float(right[key]))))
        elif csv_bytes(f)!=csv_bytes(b/relative):
            raise ValueError('Exact scientific replay differs: '+str(relative))
        checked.append(str(relative))
    if not checked:raise ValueError('No panel outputs')
    for name in ('technical_comparability.csv','commercial_project_coverage.csv','aim_c_technical_features.csv','formal_gate_compatibility.csv'):
        if csv_bytes(a/name)!=csv_bytes(b/name):raise ValueError('Evidence export differs: '+name)
    return dict(status='REFERENCE_POINT_EQUIVALENT_RANKS_AND_MONTE_CARLO_EXACT' if reference else 'EXACT',panel_csv_files=len(checked),evidence_exports=4,numeric_tolerance='Unchanged check_replay point tolerance1e-12; ranks/stochastic0' if reference else 0,platform_differences=platform_differences,
                runtime_exception='R_version platform string and CSV CRLF/LF only; all values/RNG settings exact',before=str(a),after=str(b))


if __name__=='__main__':print(json.dumps(verify(sys.argv[1],sys.argv[2],reference='--reference' in sys.argv),indent=2))
