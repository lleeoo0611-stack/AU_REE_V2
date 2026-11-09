"""Audit the fixed37 cohort separately from round5 project admissions."""
import argparse,csv,json,math,shutil,xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path
from au_ree_v2.asx_validation import compare_summaries
from au_ree_v2.iteration_review import audit_summary,SCIENCE_INDEXES
from au_ree_v2.store import filehash
from au_ree_v2.asx import is_asx_document

BASELINE='243381670e5e8a17bacb803c1dd5d3f91011913b'
BASELINE_CSV='e481ce42d7ff392b7b2d661a32cd0a4475898c3f384a1526cf5a5fdf830079a0'
SQLITE_SHA='99ed9c0fc004960f92680ee782ef8764c189a08d98bce4d14c2d0e5ad99091d0'

def read(folder,name):
    with (Path(folder)/name).open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))

def write(folder,name,rows):
    with (Path(folder)/name).open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,list(rows[0]));w.writeheader();w.writerows(rows)

def numeric(value):
    try:return math.isfinite(float(value))
    except ValueError:return False

def package(a):
    out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    summary=json.loads((Path(a.updated)/'summary.json').read_text('utf8'));integrity=audit_summary(a.updated)
    if filehash(Path(a.baseline)/'專案總表.csv')!=BASELINE_CSV:raise ValueError('ROUND5_BASELINE_MISMATCH')
    if filehash(a.database)!=SQLITE_SHA or summary['database_sha256']!=SQLITE_SHA or summary['database_modified']:raise ValueError('ROUND5_DATABASE_CHANGED')
    for key,path in [('review_ledger_sha256',a.ledger),('discovery_ledger_sha256',a.discovery_ledger)]:
        if summary[key]!=filehash(path):raise ValueError('ROUND5_LEDGER_MISMATCH')
    if any(filehash(Path(a.repeat)/n)!=sha for n,sha in summary['output_hashes'].items()):raise ValueError('ROUND5_REPLAY_CHANGED')
    old=read(a.baseline,'專案總表.csv');rows=read(a.updated,'專案總表.csv');ids={r['專案ID'] for r in old}
    if len(old)!=37 or len(rows)!=43 or sum(v=='' for r in old for v in r.values())!=1024:raise ValueError('ROUND5_COHORT_MISMATCH')
    increment=compare_summaries(a.baseline,a.updated,out,True);changes=read(out,'field_changes.csv')
    science=[list(rows[0])[i] for i in SCIENCE_INDEXES]
    increment['scientific_newly_filled_cells']=sum(r['status']=='NEWLY_FILLED' and r['column'] in science for r in changes)
    increment['numeric_newly_filled_cells']=sum(r['status']=='NEWLY_FILLED' and numeric(r['after']) for r in changes)
    (out/'field_increment.json').write_text(json.dumps(increment,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    for n in ['專案總表.csv','field_provenance.csv','missing_fields.csv','census_inventory.csv','summary.json']:shutil.copyfile(Path(a.updated)/n,out/n)
    shutil.copyfile(Path(a.baseline)/'專案總表.csv',out/'專案總表_補值前.csv')
    for n in ['discovery_reviews.csv','discovery_candidate_queue.csv','discovery_validation.json']:shutil.copyfile(Path(a.discovery_audit)/n,out/n)
    for src,n in [(a.ledger,'source_reviews.json'),(a.discovery_ledger,'project_discovery_reviews.json'),(Path(a.source_dir)/'downloads.json','research_downloads.json')]:shutil.copyfile(src,out/n)
    if a.candidate_audit:
        audit=json.loads((Path(a.candidate_audit)/'candidate_validation.json').read_text('utf8'))
        for n in ['candidate_validation.csv','candidate_validation.json']:shutil.copyfile(Path(a.candidate_audit)/n,out/n)
    if a.source_consistency:shutil.copyfile(a.source_consistency,out/'source_consistency.csv')
    if a.external_screen:
        external=json.loads(Path(a.external_screen).read_text('utf8'))
        if external['raw_input_rows_published'] or external['numeric_values_imported'] or external['projects_admitted_from_external_list_alone']:raise ValueError('ROUND5_EXTERNAL_LIST_NOT_EVIDENCE')
        shutil.copyfile(a.external_screen,out/'gemini_screening.json')
    cfg=json.loads(Path(a.discovery_ledger).read_text('utf8'));follow=[r for r in cfg['candidates'] if r.get('round5_review')]
    if len(follow)!=16:raise ValueError('ROUND5_FOLLOWUP_COHORT_MISMATCH')
    write(out,'candidate_followup.csv',[dict(candidate_key=r['candidate_key'],project_name=r['name'],decision=r['decision'],
        admitted_project_id=next((p['project_id'] for p in summary['discovery_reviews'] if p['candidate_key']==r['candidate_key']),'') if r['decision']=='ADMIT_PROJECT' else '',
        reason=r['reason'],scope_assessment=json.dumps(r['round5_review'],ensure_ascii=False),
        source_urls=json.dumps([s['url'] for s in r['sources']]),source_hashes=json.dumps([s['sha256'] for s in r['sources']]),
        source_evidence=json.dumps([s['evidence'] for s in r['sources']],ensure_ascii=False)) for r in follow])
    coverage=[]
    for label,cohort in [('BASELINE37',old),('UPDATED_SAME37',[r for r in rows if r['專案ID'] in ids]),('NEW6',[r for r in rows if r['專案ID'] not in ids]),('EXPANDED43',rows)]:
        coverage.append(dict(cohort=label,projects=len(cohort),filled_cells=sum(v!='' for r in cohort for v in r.values()),blank_cells=sum(v=='' for r in cohort for v in r.values()),
            science_filled=sum(bool(r[c]) for r in cohort for c in science),science_total=len(cohort)*25,
            paired_resources=sum(bool(r['礦石蘊藏量_Mt'] and r['TREO品位_pct']) for r in cohort),full15=sum(r['已公布元素數_共15項']=='15' for r in cohort),
            annual_treo=sum(bool(r['預估年產TREO_t_per_year']) for r in cohort),annual_ndpr=sum(bool(r['預估年產NdPr_t_per_year']) for r in cohort),annual_hree8=sum(bool(r['預估年產重稀土_t_per_year']) for r in cohort)))
    write(out,'cohort_coverage.csv',coverage)
    gaps=read(a.updated,'missing_fields.csv');write(out,'priority_missing_fields.csv',[r for r in gaps if r['column'] in science])
    write(out,'remaining_gap_reasons.csv',[dict(reason=k,blank_cells=v) for k,v in Counter(r['reason'] for r in gaps).most_common()])
    write(out,'project_gap_assessment.csv',[dict(project_id=r['專案ID'],project_name=r['專案名稱'],cohort='BASELINE37' if r['專案ID'] in ids else 'NEW6',
        filled_cells=sum(bool(v) for v in r.values()),blank_cells=sum(v=='' for v in r.values()),scientific_blanks=sum(r[c]=='' for c in science),
        newly_filled_original_cells=sum(c['project_id']==r['專案ID'] and c['status']=='NEWLY_FILLED' for c in changes),
        resource_pair=bool(r['礦石蘊藏量_Mt'] and r['TREO品位_pct']),remaining_reasons=json.dumps(sorted({g['reason'] for g in gaps if g['project_id']==r['專案ID']}),ensure_ascii=False)) for r in rows])
    downloads=json.loads((Path(a.source_dir)/'downloads.json').read_text('utf8'));archives=[json.loads(Path(p).read_text('utf8')) for p in a.archive]
    write(out,'document_dispositions.csv',[dict(key=r['key'],status=r['status'],url=r['url'],source_sha256=r.get('document_sha256',''),pages=r.get('physical_pages',''),
        numeric_reviews=json.dumps([v['review_id'] for v in json.loads(Path(a.ledger).read_text('utf8'))['reviews'] if v['source_sha256']==r.get('document_sha256')]),
        failure_reason=r.get('failure_status',''),interpretation='CAPTURE_IS_NOT_NUMERIC_ADMISSION;SEE_SOURCE_REVIEW_AND_REPORT') for r in downloads])
    (out/'supplemental_archive_discovery.json').write_text(json.dumps(dict(searches=archives),ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    tests=[]
    for path in a.test_report:
        p=Path(path);s=ET.parse(p).getroot().find('testsuite')
        if s is None or any(int(s.get(k,'0')) for k in ['failures','errors']):raise ValueError('ROUND5_TEST_FAILURE')
        tests.append(dict(report=p.name,sha256=filehash(p),tests_including_subtests=int(s.get('tests','0')),failures=0,errors=0,seconds=float(s.get('time','0'))))
    validation=dict(baseline_commit=BASELINE,iteration=7,research_round=5,cutoff=summary['cutoff'],database_sha256=SQLITE_SHA,database_modified=False,
        current_integrity=integrity,increment=increment,coverage=coverage,followup16=dict(Counter(r['decision'] for r in follow)),
        review_ledger_sha256=filehash(a.ledger),discovery_ledger_sha256=filehash(a.discovery_ledger),tests=tests,repeated_csv_exports_identical=True,
        acquisition=dict(urls=len(downloads),status_counts=dict(Counter(r['status'] for r in downloads)),pdf_attempts=sum(r['kind']=='pdf' for r in downloads),
            pdf_acquired=sum(r['status']=='PDF_ACQUIRED' for r in downloads),pdf_physical_pages=sum(r.get('physical_pages',0) for r in downloads if r['status']=='PDF_ACQUIRED'),
            asx_pdf_attempts=sum(is_asx_document(r['url']) for r in downloads),asx_pdf_acquired=sum(is_asx_document(r['url']) and r['status']=='PDF_ACQUIRED' for r in downloads),
            archive_pages=sum(len(x['receipts']) for x in archives),parsed_archives=sum(r['status']=='PARSED' for x in archives for r in x['receipts']),
            distinct_announcement_links=len({r['url'] for x in archives for r in x['documents']})),
        test_interpretation='RELATED_REGRESSIONS_AND_FOCUSED_TESTS_OVERLAP;NO_FULL_HISTORICAL_REBUILD_OR_REMOTE_CI',
        code_fingerprint={str(p).replace('\\','/'):filehash(p) for base in ['src','tools','config'] for p in sorted(Path(base).rglob('*')) if p.is_file() and p.suffix in ('.py','.json')},
        artifact_hashes={p.name:filehash(p) for p in out.iterdir() if p.is_file() and p.name!='validation.json'})
    (out/'validation.json').write_text(json.dumps(validation,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    return dict(increment=increment,coverage=coverage,acquisition=validation['acquisition'],followup16=validation['followup16'])

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for key in ['baseline','updated','repeat','ledger','discovery-ledger','discovery-audit','database','source-dir','out']:p.add_argument('--'+key,required=True)
    p.add_argument('--archive',action='append',required=True);p.add_argument('--test-report',action='append',required=True)
    p.add_argument('--candidate-audit');p.add_argument('--source-consistency');p.add_argument('--external-screen')
    print(json.dumps(package(p.parse_args()),ensure_ascii=False,indent=2))
