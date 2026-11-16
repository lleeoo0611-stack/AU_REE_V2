"""Compare frozen scientific matrices/ranks, excluding run metadata and logs."""
import csv
import json
import math
import sys
from pathlib import Path


def rows(path):
    with path.open(encoding='utf-8-sig', newline='') as stream:
        data=list(csv.DictReader(stream))
    key=lambda r:tuple(r.get(k,'') for k in ('scenario','project_id','code','criterion'))
    if len({key(r) for r in data})!=len(data):
        raise ValueError('Duplicate scientific row identity: '+str(path))
    return sorted(data,key=key)


def equivalent(a,b):
    if a==b:return True
    try:
        x,y=float(a),float(b)
        return math.isfinite(x) and math.isfinite(y) and math.isclose(x,y,rel_tol=1e-12,abs_tol=1e-12)
    except (ValueError,TypeError):return False


def verify(baseline,latest):
    baseline=Path(baseline)
    run=Path(json.loads(Path(latest).read_text(encoding='utf-8'))['output_dir'])
    checked=[]
    for name in ('matrix.csv','ranking.csv','criteria.csv','weights.csv'):
        for original in sorted(baseline.glob('*/'+name)):
            relative=original.relative_to(baseline)
            a,b=rows(original),rows(run/relative)
            if len(a)!=len(b) or any(set(x)!=set(y) or any(not equivalent(x[k],y[k]) for k in x) for x,y in zip(a,b)):
                raise ValueError('Scientific replay differs: '+relative.as_posix())
            checked.append(relative.as_posix())
    if not checked:raise ValueError('No frozen scientific outputs found')
    return dict(status='MATCHED',files=len(checked),tolerance='numeric 1e-12; identities/text exact',baseline=str(baseline),run=str(run))


if __name__=='__main__':
    print(json.dumps(verify(sys.argv[1],sys.argv[2]),indent=2))
