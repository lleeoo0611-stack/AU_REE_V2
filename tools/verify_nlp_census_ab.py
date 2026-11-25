"""Verify the frozen targets, blind candidate reviews and the real Phase 22 A/B releases."""
import argparse
import csv
import hashlib
import json
import sqlite3
from collections import Counter
from pathlib import Path


def read(path):
    return json.loads(path.read_bytes())


def sha(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f,'sha256').hexdigest()


def rows(path):
    with path.open(encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


def cells(release):
    data=rows(release/'REE project census.csv')
    result={(row['專案ID'],column):value for row in data for column,value in row.items()}
    if len(data)!=93 or len(result)!=4743:
        raise ValueError('Unexpected Census dimensions')
    return result


def verify(args):
    experiment=args.experiment
    predictions=read(experiment/'predictions.json')['cases']
    cases={c['case_id']:c for c in predictions}
    review=[r for file in args.adjudications for r in read(file)['cases']]
    if len(cases)!=len(review) or {r['case_id'] for r in review}!=set(cases):
        raise ValueError('Adjudication does not exactly cover every query')
    pool=set()
    for r in review:
        c=cases[r['case_id']]
        inspected={(p['sha256'],p['page']) for p in r['inspected_pages']}
        expected=set(map(tuple,c['rules']+c['rules_nlp']))
        if (c['project_id']!=r['project_id'] or set(c['columns'])!=set(r['columns']) or inspected!=expected
                or not r['reason'].strip() or r['disposition'] not in ('HELD','SUPPORTED')):
            raise ValueError('Incomplete union review: '+c['case_id'])
        pool.update(expected)
    original=cells(args.baseline)
    base=read(args.baseline/'census_release.json')
    target={(c['project_id'],col) for c in predictions for col in c['columns']}
    if len(target)!=90 or any(original[k] for k in target):
        raise ValueError('Target set is not the 90 empty baseline cells')
    output={'baseline_run':base['run_id'],'cutoff':base['cutoff'],'target_cells':len(target),
            'original_applicable':3034,'unique_reviewed_pdf_pages':len(pool),
            'review_outcomes':dict(Counter(r['disposition'] for r in review)),'arms':{}}
    for arm,release,work in [('rules',args.rules_release,args.rules_work),('rules_nlp',args.nlp_release,args.nlp_work)]:
        m=read(release/'census_release.json')
        coverage=read(release/'coverage.json')['gap_review']
        current=cells(release)
        if (original.keys()!=current.keys() or coverage['baseline_applicable']!=3034
                or m['cutoff']!=base['cutoff'] or m['phase22_lock_sha256']!=base['phase22_lock_sha256']
                or m['mode']!='offline' or sha(release/'REE project census.csv')!=m['census_csv_sha256']):
            raise ValueError('Population, source lock, cutoff or output checksum changed')
        controls = {('AU-0832169526bb5ec07626','緯度'):'-33.2772965',
                    ('AU-0832169526bb5ec07626','經度'):'139.4657582',
                    ('AU-68da41afe874c3bd66d4','礦床型態代碼'):'iac'}
        if any(current[k]!=v or k in target for k,v in controls.items()):
            raise ValueError('Existing positive admissions were lost or leaked into the target count')
        difference=[{'project_id':p,'column':col,'before':v,'after':current[p,col]}
                    for (p,col),v in original.items() if v!=current[p,col]]
        new={(p,col):current[p,col] for p,col in target if current[p,col]}
        expected_values={}
        for r in review:
            if r['disposition']=='SUPPORTED':
                c=cases[r['case_id']]
                for v in r['supported_cells']:
                    if set(map(tuple,v['required_candidate_pages'])).issubset(set(map(tuple,c[arm]))):
                        expected_values[(r['project_id'],v['column'])]=str(v['value'])
        errors=[k for k,v in new.items() if expected_values.get(k)!=v]
        omitted=[k for k in expected_values if k not in new]
        unexpected_fills=[v for v in difference if not v['before'] and (v['project_id'],v['column']) not in target]
        if errors or omitted or unexpected_fills:
            raise ValueError(f'Admission discrepancy in {arm}: {errors}, {omitted}, {unexpected_fills}')
        if sha(release/'source_selection.csv')!=sha(args.baseline/'source_selection.csv'):
            raise ValueError('Source-selection decisions differ from the frozen common pool')
        if m['code']['content_sha256']!=base['code']['content_sha256']:
            raise ValueError('Production Python/R content drifted between the paired runs')
        actual_run=work/'runs'/m['run_id']
        if read(actual_run/'census_release.json')!=m:
            raise ValueError('Release and runtime manifest disagree')
        changes=[]
        artifacts=0
        if set(m['ranking_panels'])!=set(base['ranking_panels']):
            raise ValueError('Ranking panel set changed')
        for panel,meta in m['ranking_panels'].items():
            digests=meta['digests']
            if meta['status']!='COMPLETED' or set(digests)!=set(base['ranking_panels'][panel]['digests']):
                raise ValueError(panel)
            for name,h in digests.items():
                if sha(actual_run/panel/name)!=h: raise ValueError(f'Incorrect R artifact: {panel}/{name}')
                if base['ranking_panels'][panel]['digests'][name]!=h: changes.append([panel,name])
                artifacts+=1
        db=work/'databases'/m['run_id']/'canonical.sqlite'
        with sqlite3.connect(db.resolve().as_uri()+'?mode=ro',uri=True) as con:
            if (con.execute('PRAGMA integrity_check').fetchone()!=('ok',) or con.execute('PRAGMA foreign_key_check').fetchone()
                    or con.execute('SELECT status FROM runs WHERE run_id=?',(m['run_id'],)).fetchone()!=('COMPLETED',)):
                raise ValueError('SQLite integrity or completion failed')
        output['arms'][arm]={'run_id':m['run_id'],'code':m['code'],'filled':coverage['filled_within_baseline'],
                  'fixed_coverage':coverage['filled_within_baseline']/3034,'actual_target_fills':len(new),
                  'wrong_new_admissions':len(errors),'admission_precision':(len(new)-len(errors))/len(new) if new else None,
                  'existing_positive_control_cells':len(controls),'all_value_changes':difference,'census_sha256':m['census_csv_sha256'],'panels':len(m['ranking_panels']),
                  'verified_r_artifacts':artifacts,'changed_r_artifacts':changes,'sqlite_integrity':'ok','source_selection_matches_baseline':True,
                  'cell_status_matches_baseline':sha(release/'field_status.csv')==sha(args.baseline/'field_status.csv'),
                  'field_provenance_matches_baseline':sha(release/'field_provenance.csv')==sha(args.baseline/'field_provenance.csv')}
    (experiment/'census_verification.json').write_bytes((json.dumps(output,ensure_ascii=False,indent=2)+'\n').encode())
    return output


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for arg in ('baseline','rules-release','rules-work','nlp-release','nlp-work','experiment'):
        parser.add_argument('--'+arg,type=Path,required=True)
    parser.add_argument('--adjudications',nargs=2,type=Path,required=True)
    verify(parser.parse_args())
