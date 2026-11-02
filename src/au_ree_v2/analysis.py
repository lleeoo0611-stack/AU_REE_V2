"""Frozen panels, anchored scoring, coverage and traceable R interchange."""
import csv
import json
import math
import shutil
import subprocess
from pathlib import Path
from .store import canonical

def write_csv(path, rows, columns):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(rows)

def score(value, criterion, alternative=False):
    low, high = criterion['low'], criterion['high']
    if not math.isfinite(value) or high <= low:
        raise ValueError('Invalid score value or anchors')
    if criterion['function']=='log1p' and not alternative:
        val = (math.log1p(max(low, min(value,high)))-math.log1p(low))/(math.log1p(high)-math.log1p(low))
    else:
        val = (value-low)/(high-low)
    val = max(0., min(1., val))
    return 1-val if criterion['direction']=='MIN' else val

def prepare(db, cutoff, snapshots, resources, gis_values, config, out, project=None):
    out = Path(out)
    criteria = {c['code']:c for c in config['criteria']}
    selected_shas = {s['sha256'] for s in snapshots}
    coverage, traces, matrices = [], [], {}
    project_ids = list(resources)
    if project:
        project_ids = [eid for eid in project_ids if db.execute('SELECT native_id FROM entities WHERE entity_id=?',(eid,)).fetchone()[0]==project]
    for eid in project_ids:
        resource = resources[eid]
        name = db.execute('SELECT name FROM records WHERE entity_id=? ORDER BY source_sha LIMIT 1',(eid,)).fetchone()[0]
        values = {'contained_treo_kt':resource['contained_treo_kt']}
        provenance = {'contained_treo_kt':resource}
        for r in db.execute("SELECT * FROM observations WHERE entity_id=? AND status='AUTO_VALIDATED' AND effective_date<=? ORDER BY effective_date",(eid,cutoff)):
            if r['source_sha'] in selected_shas and r['variable'] not in ('contained_treo_kt','ore_mt','grade'):
                values[r['variable']] = r['value']
                provenance[r['variable']] = {'obs_ids':[r['obs_id']], 'source_sha':r['source_sha']}
        for key, v in gis_values.get(eid,{}).items():
            values[key]=v['value'];provenance[key]=v
        scored={code:score(values[c['variable']],c) for code,c in criteria.items() if c['variable'] in values}
        is_dev = all(v in values for v in ('study_maturity_ord','recovery_pct'))
        is_full = is_dev and all(code in scored for code in config['panels']['six_domain'])
        coverage.append({'entity_id':eid,'project_name':name,'scope':resource['scope'],
                         'resource_defined':1,'development':int(is_dev),'full_evidence':int(is_full),
                         **{code:int(code in scored) for code in criteria}})
        for code, val in scored.items():
            c=criteria[code]
            traces.append({'entity_id':eid,'criterion':code,'raw_value':values[c['variable']],
                           'score':val,'config_version':config['version'],
                           'source':canonical(provenance[c['variable']]),'scoring':canonical(c)})
        for panel, codes in config['panels'].items():
            if not all(c in scored for c in codes) or (panel=='six_domain' and not is_full):
                continue
            row={'project_id':eid,'project_name':name,'scope':resource['scope']}
            for code in codes:
                c=criteria[code]; raw=values[c['variable']]
                row[code]=scored[code]
                row[code+'_alt']=score(raw,c,alternative=True)
                # These are source rounding intervals, not geological uncertainty.
                bounds=resource['rounding_bounds_kt'] if code=='R1' else [raw,raw]
                row[code+'_lower']=min(score(v,c) for v in bounds)
                row[code+'_upper']=max(score(v,c) for v in bounds)
            matrices.setdefault(panel,[]).append(row)
    write_csv(out/'cohort_coverage.csv',coverage,['entity_id','project_name','scope','resource_defined','development','full_evidence',*criteria])
    write_csv(out/'value_trace.csv',traces,['entity_id','criterion','raw_value','score','config_version','source','scoring'])
    write_csv(out/'resources.csv',list(resources.values()),['entity_id','scope','date','ore_mt','grade_pct','contained_treo_kt','calculated_from_rounded_inputs_kt','rounding_bounds_kt','source_sha','obs_ids','interpretation'])
    for panel, rows in matrices.items():
        codes=config['panels'][panel]
        folder=out/panel
        write_csv(folder/'matrix.csv',rows,['project_id','project_name','scope',*[key for code in codes for key in (code,code+'_alt',code+'_lower',code+'_upper')]])
        write_csv(folder/'criteria.csv',[criteria[c] for c in codes],['code','domain','direction','low','high','function'])
        weights=[]
        for scenario, domain_weights in config['scenarios'].items():
            domains={criteria[c]['domain'] for c in codes}
            total=sum(domain_weights[d] for d in domains)
            for code in codes:
                domain=criteria[code]['domain']
                count=sum(criteria[c]['domain']==domain for c in codes)
                weights.append({'scenario':scenario,'criterion':code,'weight':domain_weights[domain]/total/count})
        write_csv(folder/'weights.csv',weights,['scenario','criterion','weight'])
    return {'coverage':coverage,'panels':{p:len(v) for p,v in matrices.items()},'trace_values':len(traces)}

def run_r(root, out, prepared, config, rscript=None):
    executable = rscript or shutil.which('Rscript')
    if not executable:
        raise RuntimeError('Rscript is required. Supply --rscript or explicitly use --skip-r for coverage only.')
    results={}
    for panel,n in prepared['panels'].items():
        if n<2:
            results[panel]={'status':'INSUFFICIENT_SAMPLE','n':n};continue
        folder=Path(out)/panel
        command=[str(executable),str(Path(root)/'R/run_mcda.R'),str(folder),
                 str(config['monte_carlo']['seed']),str(config['monte_carlo']['reps']),str(config['promethee_threshold']),
                 str(config['monte_carlo']['dirichlet_concentration'])]
        result=subprocess.run(command,capture_output=True,text=True,timeout=300)
        (folder/'R.log').write_text(result.stdout+'\n'+result.stderr,encoding='utf-8')
        if result.returncode:
            raise RuntimeError('R MCDA failed: '+result.stderr[-2000:])
        expected=('ranking.csv','weight_uncertainty.csv','rounding_uncertainty.csv','leave_out.csv',
                  'method_comparison.csv','function_sensitivity.csv','cohort_sensitivity.csv','ahp_audit.csv')
        if not all((folder/p).is_file() for p in expected):
            raise RuntimeError('R output contract incomplete')
        results[panel]={'status':'COMPLETED','n':n,'weight_status':config['weight_status']}
    return results
