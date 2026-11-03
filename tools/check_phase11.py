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


def verify(before,after):
    a,b=folder(before),folder(after);checked=[]
    for f in sorted(a.glob('*/*.csv')):
        relative=f.relative_to(a)
        if f.name=='runtime.csv':
            x=next(csv.DictReader(f.open()));y=next(csv.DictReader((b/relative).open()))
            # R platform/version string is descriptive; the RNG algorithm and
            # every numerical scientific output must still match exactly.
            if {k:v for k,v in x.items() if k!='R_version'}!={k:v for k,v in y.items() if k!='R_version'}:
                raise ValueError('Runtime method contract differs: '+str(relative))
        elif csv_bytes(f)!=csv_bytes(b/relative):
            raise ValueError('Exact scientific replay differs: '+str(relative))
        checked.append(str(relative))
    if not checked:raise ValueError('No panel outputs')
    for name in ('technical_comparability.csv','commercial_project_coverage.csv','aim_c_technical_features.csv','formal_gate_compatibility.csv'):
        if csv_bytes(a/name)!=csv_bytes(b/name):raise ValueError('Evidence export differs: '+name)
    return dict(status='EXACT',panel_csv_files=len(checked),evidence_exports=4,numeric_tolerance=0,
                runtime_exception='R_version platform string and CSV CRLF/LF only; all values/RNG settings exact',before=str(a),after=str(b))


if __name__=='__main__':print(json.dumps(verify(sys.argv[1],sys.argv[2]),indent=2))
