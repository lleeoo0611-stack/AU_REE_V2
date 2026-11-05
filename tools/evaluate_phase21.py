"""Seal existing pipeline outputs, compare cohorts and stress adopted item coding."""
import argparse,csv,json,math,shutil,statistics
from pathlib import Path
from au_ree_v2.analysis import write_csv,interval_mcda
from au_ree_v2.store import canonical,filehash
from au_ree_v2.cli import code_version

ROOT=Path(__file__).resolve().parents[1]
OLD=ROOT/'results/phase20-2026-11-05'
CODES=['R1','S1','T1','D1','I4','C1']


def rows(path):
    with Path(path).open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))


def compare_cohorts(out,config):
    before={r['project_id']:r for r in rows(OLD/'six_domain/matrix.csv')}
    after={r['project_id']:r for r in rows(out/'six_domain/matrix.csv')}
    common=sorted(before.keys()&after.keys());delta=[]
    for pid in common:
        for code in CODES:
            if not math.isclose(float(before[pid][code]),float(after[pid][code]),rel_tol=1e-12,abs_tol=1e-12):
                raise ValueError('Common-cohort point utility changed: '+pid+' '+code)
    old_ranks=rows(OLD/'six_domain/ranking.csv');new_ranks=rows(out/'six_domain/ranking.csv')
    for scenario in config['scenarios']:
        a={r['project_id']:r for r in old_ranks if r['scenario']==scenario};b={r['project_id']:r for r in new_ranks if r['scenario']==scenario}
        for method,prefix in [('SAW','saw'),('TOPSIS','topsis'),('PROMETHEE_II','promethee')]:
            reversals=sum((float(a[x][prefix])-float(a[y][prefix]))*(float(b[x][prefix])-float(b[y][prefix])) < -1e-12
                          for i,x in enumerate(common) for y in common[i+1:])
            for pid in common:
                score_changed=not math.isclose(float(a[pid][prefix]),float(b[pid][prefix]),rel_tol=1e-12,abs_tol=1e-12)
                if method in ('SAW','TOPSIS') and score_changed:raise ValueError('Fixed-anchor score changed on common cohort')
                delta.append(dict(scenario=scenario,method=method,project_id=pid,before_score=a[pid][prefix],after_score=b[pid][prefix],
                    before_rank=a[pid][prefix+'_rank'],after_rank=b[pid][prefix+'_rank'],common_pair_reversals=reversals,
                    score_changed=score_changed,interpretation='Insertion displacement separate from common-pair reversal; PROMETHEE flow depends on comparison cohort'))
    write_csv(out/'cohort_rank_changes.csv',delta,list(delta[0]))
    return dict(before_n=len(before),after_n=len(after),common_ids=common,new_ids=sorted(after.keys()-before.keys()),
        exited_ids=sorted(before.keys()-after.keys()),common_point_utilities_unchanged=True,
        SAW_TOPSIS_common_scores_unchanged=True,evidence_update_fixed_old_cohort='Point utilities identical; new evidence qualifies two previously incomplete groups')


def coding_stress(out,config):
    matrix=rows(out/'six_domain/matrix.csv');by_id={r['project_id']:i for i,r in enumerate(matrix)}
    original=[[float(r[c]) for c in CODES] for r in matrix];items=[r for r in rows(out/'disclosure_items.csv') if r['project_id'] in by_id]
    output=[]
    for scenario,dw in config['scenarios'].items():
        weights=[dw[next(c['domain'] for c in config['criteria'] if c['code']==code)] for code in CODES]
        baseline=interval_mcda([[(v,v) for v in rr] for rr in original],weights,config['promethee_threshold'])
        for item in items:
            actual=int(item['value']);alternative=1-actual;xx=[list(r) for r in original]
            xx[by_id[item['project_id']]][CODES.index('T1')]+=(alternative-actual)/7
            result=interval_mcda([[(v,v) for v in rr] for rr in xx],weights,config['promethee_threshold'])
            for method,rr in result.items():
                leaders={matrix[i]['project_id'] for i,r in enumerate(rr) if r['rank_best']==1}
                old={matrix[i]['project_id'] for i,r in enumerate(baseline[method]) if r['rank_best']==1}
                for project,r in zip(matrix,rr):
                    output.append(dict(scenario=scenario,method=method,changed_project_id=item['project_id'],item=item['item'],
                        assessment_id=item['assessment_id'],adopted_value=actual,counterfactual_value=alternative,
                        project_id=project['project_id'],**r,leader_set_changed=leaders!=old,
                        interpretation='One binary item stress, fixed denominator7; not recoding, measurement uncertainty, probability or confidence interval'))
    write_csv(out/'disclosure_coding_sensitivity.csv',output,list(output[0]))
    return dict(complete_groups=len(matrix),reviewed_positive_and_zero_items=len(items),
        leader_changing_variants=len({(r['scenario'],r['method'],r['changed_project_id'],r['item']) for r in output if r['leader_set_changed']}),
        rule='Each adopted 0/1 inverted individually; hypothetical stress only, original judgments retained')


def main():
    p=argparse.ArgumentParser();p.add_argument('--run',default='work/phase5/latest.json');p.add_argument('--out',default='results/phase21-2026-11-05');a=p.parse_args()
    receipt=json.loads(Path(a.run).read_text(encoding='utf8'));source=Path(receipt['output_dir']);out=ROOT/a.out;out.mkdir(parents=True,exist_ok=True)
    if receipt['status']!='COMPLETED' or receipt['r_skipped']:raise ValueError('Require completed main CLI with R')
    if receipt['code']['content_sha256']!=code_version(ROOT)['content_sha256']:raise ValueError('Run source code differs from current code')
    for pattern in ('*.csv','disclosure_analysis.json','disclosure_baseline.json','configuration.json','snapshot_lock.json','eligibility_audit.json','summary.json'):
        for file in source.glob(pattern):shutil.copy2(file,out/file.name)
    for panel,result in receipt['r_results'].items():
        if result['status']!='COMPLETED':continue
        for file in (source/panel).glob('*'):
            if file.suffix not in ('.csv','.json','.svg'):continue
            target=out/panel/file.name;target.parent.mkdir(exist_ok=True);shutil.copy2(file,target)
    for file in (ROOT/'work/phase21/census').glob('*'):shutil.copy2(file,out/file.name)
    config=json.loads((out/'configuration.json').read_text(encoding='utf8'))['research']
    change=compare_cohorts(out,config);stress=coding_stress(out,config)
    matrix=rows(out/'disclosure_composite_matrix.csv');gaps=[]
    for r in matrix:
        missing=[c for c in CODES if r[c]=='']
        gaps.append(dict(project_id=r['project_id'],project_name=r['project_name'],scope=r['scope'],missing_domain_count=len(missing),
            missing_criteria=';'.join(missing),full_six_point=not missing,interpretation='Evidence recovery priority, not independent Project approval or potential rank'))
    gaps.sort(key=lambda r:(r['missing_domain_count'],r['project_name']))
    write_csv(out/'six_domain_gap_priority.csv',gaps,list(gaps[0]))
    old_groups={r['project_id'] for r in rows(OLD/'disclosure_composite_matrix.csv')}
    if not old_groups<={r['project_id'] for r in matrix}:raise ValueError('Established group identity disappeared')
    before={r['source_key']:r for r in rows(ROOT/'work/phase21/census_phase20/national_source_coverage.csv')}
    after=rows(out/'national_source_coverage.csv');comparisons=[]
    for r in after:
        if r['source_key'] not in before or not r['raw_records']:continue
        b=before[r['source_key']]
        comparisons.append(dict(source_key=r['source_key'],state=r['state'],before_sha256=b['source_sha256'],after_sha256=r['source_sha256'],
            previous_source_previous_rule=b['previous_rule_candidates'],previous_source_current_rule=b['candidate_records'],
            current_source_previous_rule=r['previous_rule_candidates'],current_source_current_rule=r['candidate_records'],
            before_raw_records=b['raw_records'],after_raw_records=r['raw_records'],unit='SOURCE_RECORDS_INCLUDING_RELATED_ROLES_NOT_PROJECTS'))
    write_csv(out/'source_version_rule_comparison.csv',comparisons,list(comparisons[0]))
    result=dict(status='VERIFIED_WITH_DECLARED_LIMITS',code=receipt['code'],run_id=receipt['run_id'],cutoff=receipt['cutoff'],
        counts=dict(canonical_groups=receipt['canonical_projects_n'],resource_cases=receipt['resource_defined_n'],full_six=receipt['full_evidence_n'],
            point_disclosure=sum(r['T1']!='' for r in matrix),government_native_candidates=receipt['live_government_native_entities_n'],
            government_raw_source_records=receipt['live_government_raw_records_n'],source_snapshots=receipt['source_count'],entity_kinds=receipt['census_by_kind']),
        point_domain_coverage={c:sum(r[c]!='' for r in matrix) for c in CODES},cohort_change=change,coding_sensitivity=stress,
        formal_C1=receipt['eligibility_audit'],known_group_ids_preserved=True,scientific_definition_unchanged=True,
        new_complete_case_origin='Existing-group evidence recovery: Cummins Range and Nolans; no new national-discovery complete MCDA case',
        barkly='Registered Project plus2source-bound prospects; source40Mt*2100ppm vsreported82kt conflict prevents R1; detailed prospectus403, unknown transparency retained',
        limits=['Single-agent source-field validation is not independent gold or national recall','ACT dedicated adapter and external territories incomplete',
            'End-to-end development benchmarks overlapped other local work; no controlled whole-system speedup claim','No error-induced or missing-value zero imputation'])
    (out/'evaluation.json').write_text(canonical(result)+'\n',encoding='utf8')
    print(canonical(result))


if __name__=='__main__':main()
