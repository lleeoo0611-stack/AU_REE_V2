"""Compare frozen scientific matrices/ranks, excluding run metadata and logs."""
from hashlib import file_digest
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


def verify_hash_seed_replay(baseline_latest, updated_latest, baseline_seed, updated_seed):
    """Verify exact sealed scientific outputs from two independent rebuilds."""
    if baseline_seed == updated_seed:
        raise ValueError('Hash-seed replay requires two distinct process seeds')
    paths = [Path(json.loads(Path(latest).read_text())['output_dir'])
             for latest in (baseline_latest, updated_latest)]
    summaries = [json.loads((path / 'summary.json').read_text()) for path in paths]
    before, after = summaries
    if paths[0] == paths[1] or any(run['status'] != 'COMPLETED' for run in summaries):
        raise ValueError('Hash-seed replay requires independent completed runs')
    for key in ('cutoff', 'configuration_sha256', 'snapshot_sha256', 'logical_database_sha256'):
        if before[key] != after[key]:
            raise ValueError('Hash-seed run differs: ' + key)
    panels_before, panels_after = ({name: (item['n'], item['status']) for name, item in run['r_results'].items()}
                                   for run in summaries)
    if panels_before != panels_after or not panels_before:
        raise ValueError('Hash-seed replay changed panel membership or execution status')
    scientific_files = {'configuration.json', 'canonical_membership.csv', 'resources.csv', 'value_trace.csv',
                        'formal_gate_compatibility.csv', 'eligibility_cohorts.csv'}
    required_panel_files = {'criteria.csv', 'matrix.csv', 'weights.csv'}
    r_files = {'ranking.csv', 'weight_uncertainty.csv', 'rounding_uncertainty.csv', 'uncertainty_by_method.csv',
               'shared_draw_contract.csv', 'shared_draw_ranks.csv'}
    for name, (_, status) in panels_before.items():
        scientific_files.update(f'{name}/{file}' for file in required_panel_files)
        if status == 'COMPLETED':
            scientific_files.add(f'{name}/ranking.csv')
        scientific_files.update(f'{name}/{file}' for file in r_files
                                if any(f'{name}/{file}' in run['output_hashes'] for run in summaries))
    verified = {}
    for item in sorted(scientific_files):
        for path, run in zip(paths, summaries, strict=True):
            with (path / item).open('rb') as stream:
                actual = file_digest(stream, 'sha256').hexdigest()
            if actual != run['output_hashes'].get(item) or actual != verified.setdefault(item, actual):
                raise ValueError('Hash-seed scientific output differs or seal does not match: ' + item)
    return {'status': 'EXACT_SCIENTIFIC_REPLAY', 'python_hash_seeds': [baseline_seed, updated_seed],
            'run_ids': [run['run_id'] for run in summaries], 'panels': sorted(panels_before),
            'inputs': {name: before[name] for name in ('cutoff', 'configuration_sha256', 'snapshot_sha256',
                                                       'logical_database_sha256')},
            'scientific_artifact_sha256': verified}


if __name__=='__main__':
    if sys.argv[1] == '--hash-seed-replay':
        _, _, before, after, baseline_seed, updated_seed, output = sys.argv
        Path(output).write_text(json.dumps(verify_hash_seed_replay(before, after, baseline_seed, updated_seed),
                                           indent=2) + '\n', encoding='utf-8')
    else:
        print(json.dumps(verify(sys.argv[1], sys.argv[2]), indent=2))
