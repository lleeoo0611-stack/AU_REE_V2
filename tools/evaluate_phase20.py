"""Seal the current evidence expansion against a same-store locked replay."""
import csv
import json
import shutil
import sqlite3
from pathlib import Path
from au_ree_v2.store import filehash,canonical
from au_ree_v2.cli import code_version
from au_ree_v2.analysis import write_csv

ROOT=Path(__file__).resolve().parents[1]
FIRST=ROOT/'work/phase5/runs/20261105T094121-dea124d7'
REPLAY=ROOT/'work/phase5/runs/20261105T094506-12df6e65'
OUT=ROOT/'results/phase20-2026-11-05'

def main():
    OUT.mkdir(exist_ok=True)
    for run in (FIRST,REPLAY):
        assert json.loads((run/'summary.json').read_text())['status']=='COMPLETED'
    names=['disclosure_items.csv','disclosure_scores.csv','disclosure_composite_matrix.csv',
           'disclosure_composite_ranking.csv','disclosure_weights.csv','disclosure_interval_sensitivity.csv',
           'cohort_coverage.csv','value_trace.csv','six_domain/matrix.csv','six_domain_disclosure/matrix.csv']
    replay={n:filehash(FIRST/n)==filehash(REPLAY/n) for n in names}
    assert all(replay.values()),replay
    for name in names+['disclosure_analysis.json','disclosure_baseline.json','snapshot_lock.json','configuration.json']:
        target=OUT/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(REPLAY/name,target)
    for panel in ('six_domain','six_domain_disclosure'):
        for p in (FIRST/panel).iterdir():
            if p.is_file():shutil.copy2(p,OUT/panel/p.name)
    matrix=list(csv.DictReader((REPLAY/'disclosure_composite_matrix.csv').open(encoding='utf8')))
    codes=['R1','S1','T1','D1','I4','C1'];gaps=[]
    for row in matrix:
        missing=[c for c in codes if row[c]=='']
        gaps.append(dict(project_id=row['project_id'],project_name=row['project_name'],scope=row['scope'],
            missing_domain_count=len(missing),missing_criteria=';'.join(missing),
            full_six_point=not missing,
            interpretation='Evidence recovery priority by missing domains; not MCDA rank or independent Project approval'))
    gaps.sort(key=lambda r:(r['missing_domain_count'],r['project_name']))
    write_csv(OUT/'six_domain_gap_priority.csv',gaps,list(gaps[0]))
    full=[r['project_name'] for r in gaps if r['full_six_point']]
    log=(ROOT/'work/phase20/full_tests.log').read_text(encoding='utf8')
    assert 'Ran 292 tests' in log and '\nOK\n' in log
    shutil.copy2(ROOT/'work/phase20/full_tests.log',OUT/'tests.log')
    with sqlite3.connect('file:'+str(ROOT/'work/phase5/canonical.sqlite').replace('\\','/')+'?mode=ro',uri=True) as db:
        counts={t:db.execute('SELECT count(*) FROM '+t).fetchone()[0] for t in ('sources','entities','observations')}
    result=dict(status='PASS',version='research-v6-current-disclosure-evidence',code=code_version(ROOT),
        cutoff='2026-11-05',complete_six_before=1,complete_six_after=len(full),complete_groups=full,
        total_groups=31,independent_project_census=False,new_original_documents=0,
        evidence_additions=dict(area1_oxide_rows=7,koppamurra_project_funding_plan=1),
        source_counts=counts,python_tests=dict(n=292,status='PASS'),locked_same_database_replay=replay,
        extraction_experiment=dict(original_seconds=16.535744300010265,selective_seconds=3.6249148000060814,
            speedup=4.561691849966383,identical_assessments=217,cited_pdf_pages=91,
            scope='One in-memory before/after experiment on the same frozen corpus; not overall pipeline speedup'),
        R=dict(panels=['six_domain','six_domain_disclosure'],methods=['SAW','TOPSIS','PROMETHEE_II'],
            preference_simulations_per_scenario=1000,status='COMPLETED'),
        executions=dict(first=FIRST.name,locked_replay=REPLAY.name),
        limitations=['Only three complete groups; no national or Aim C inferential conclusion',
            'Technical is disclosure transparency, not technical feasibility',
            'Commercial is a dated disclosed financing milestone, not secured funding or full commercial/ESG coverage',
            'Unknown domains remain sets; original non-Technical rounding propagation in disclosure-only interchange remains incomplete',
            'Weights are researcher assumptions; strategic rankings differ across methods',
            'Formal C1/C2 approval unchanged; uncommitted changes; no GitHub CI run'])
    (OUT/'evaluation.json').write_text(canonical(result)+'\n',encoding='utf8')
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
