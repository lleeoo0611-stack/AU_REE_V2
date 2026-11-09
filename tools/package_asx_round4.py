"""Package separately audited fixed-cohort gap fills and reviewed project expansion."""
import argparse,csv,json,shutil,xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path
from au_ree_v2.asx_validation import compare_summaries
from au_ree_v2.iteration_review import audit_summary,SCIENCE_INDEXES
from au_ree_v2.store import filehash


def package(a):
    baseline=Path(a.baseline);updated=Path(a.updated);repeat=Path(a.repeat);out=Path(a.out)
    ledger=Path(a.ledger);discovery=Path(a.discovery_ledger);database=Path(a.database)
    report=audit_summary(updated);summary=json.loads((updated/'summary.json').read_text('utf8'))
    if summary['review_ledger_sha256']!=filehash(ledger) or summary['discovery_ledger_sha256']!=filehash(discovery):raise ValueError('ROUND4_LEDGER_MISMATCH')
    if summary['database_modified'] or summary['database_sha256']!=filehash(database):raise ValueError('ROUND4_DATABASE_CHANGED')
    if any(filehash(repeat/name)!=sha for name,sha in summary['output_hashes'].items()):raise ValueError('ROUND4_REPLAY_MISMATCH')
    def read(folder,name):
        with (folder/name).open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
    old=read(baseline,'專案總表.csv');rows=read(updated,'專案總表.csv')
    if len(old)!=33 or len(rows)!=37 or len(rows[0])!=52:raise ValueError('ROUND4_COHORT_COUNT')
    out.mkdir(parents=True,exist_ok=True)
    increment=compare_summaries(baseline,updated,out,allow_expansion=True)
    changes=read(out,'field_changes.csv')
    increment['numeric_newly_filled_cells']=sum(r['status']=='NEWLY_FILLED' and _numeric(r['after']) for r in changes)
    increment['scientific_newly_filled_cells']=sum(r['status']=='NEWLY_FILLED' and r['column'] in report['scientific_columns'] for r in changes)
    (out/'field_increment.json').write_text(json.dumps(increment,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    for name in ['專案總表.csv','field_provenance.csv','missing_fields.csv','census_inventory.csv','summary.json']:shutil.copyfile(updated/name,out/name)
    shutil.copyfile(baseline/'專案總表.csv',out/'專案總表_補值前.csv')
    for f in Path(a.discovery_audit).glob('*'):
        if f.suffix in ('.csv','.json'):shutil.copyfile(f,out/f.name)
    if a.parallel_comparison:
        for name in ['field_changes.csv','field_increment.json']:
            shutil.copyfile(Path(a.parallel_comparison)/name,out/('parallel_'+name))
    if a.source_consistency:shutil.copyfile(a.source_consistency,out/'source_consistency.csv')
    if a.candidate_audit:
        for name in ['candidate_validation.csv','candidate_validation.json']:
            shutil.copyfile(Path(a.candidate_audit)/name,out/name)
    # Receipts contain metadata and hashes only; raw sources stay local.
    shutil.copyfile(Path(a.source_dir)/'downloads.json',out/'research_downloads.json')
    shutil.copyfile(Path(a.archive_dir)/'archive_discovery.json',out/'supplemental_archive_discovery.json')
    shutil.copyfile(ledger,out/'source_reviews.json');shutil.copyfile(discovery,out/'project_discovery_reviews.json')
    downloads=json.loads((Path(a.source_dir)/'downloads.json').read_text('utf8'))
    archives=json.loads((Path(a.archive_dir)/'archive_discovery.json').read_text('utf8'))
    reviews=json.loads(ledger.read_text('utf8'))['reviews']
    docs=[]
    for r in downloads:
        sha=r.get('document_sha256','');matched=[v['review_id'] for v in reviews if v['source_sha256']==sha]
        docs.append(dict(key=r['key'],url=r['url'],status=r['status'],source_sha256=sha,physical_pages=r.get('physical_pages',''),
            failure_reason=r.get('failure_status',''),review_ids=json.dumps(matched),
            disposition='ENCODED_TEXT_UNUSABLE;NO_NUMERIC_ADMISSION;REPLACEMENT_STUDY_REVIEWED' if r['key']=='sandy_mre2026' else
                'EXPLICIT_LEDGER_VALUES_ONLY' if matched else 'DISCOVERY_OR_CORROBORATION_ONLY;NOT_AUTOMATIC_NUMERIC_ADMISSION'))
    def write(name,data,fields=None):
        with (out/name).open('w',encoding='utf-8-sig',newline='') as f:
            w=csv.DictWriter(f,fields or list(data[0]));w.writeheader();w.writerows(data)
    write('document_dispositions.csv',docs)
    ids={r['專案ID'] for r in old};columns=list(rows[0]);science=[columns[i] for i in SCIENCE_INDEXES]
    fixed=[r for r in rows if r['專案ID'] in ids];added=[r for r in rows if r['專案ID'] not in ids]
    metrics=[]
    for label,cohort in [('BASELINE_33',old),('UPDATED_SAME_33',fixed),('NEW_4',added),('EXPANDED_37',rows)]:
        metrics.append(dict(cohort=label,projects=len(cohort),total_cells=len(cohort)*52,filled_cells=sum(v!='' for r in cohort for v in r.values()),
            blank_cells=sum(v=='' for r in cohort for v in r.values()),scientific_filled_cells=sum(r[c]!='' for r in cohort for c in science),scientific_total_cells=len(cohort)*25,
            paired_resource_projects=sum(bool(r['礦石蘊藏量_Mt'] and r['TREO品位_pct']) for r in cohort),full_15_oxide_projects=sum(r['已公布元素數_共15項']=='15' for r in cohort),
            annual_treo_projects=sum(bool(r['預估年產TREO_t_per_year']) for r in cohort),annual_ndpr_projects=sum(bool(r['預估年產NdPr_t_per_year']) for r in cohort),
            annual_hree8_projects=sum(bool(r['預估年產重稀土_t_per_year']) for r in cohort)))
    write('cohort_coverage.csv',metrics)
    gaps=read(updated,'missing_fields.csv');write('priority_missing_fields.csv',[r for r in gaps if r['column'] in science])
    assessments=[]
    cfg=json.loads(discovery.read_text('utf8'))
    for row in rows:
        pid=row['專案ID'];pending=[r for r in gaps if r['project_id']==pid]
        named=[r for r in cfg['candidates'] if r['name']==row['專案名稱'] or row['專案名稱'] in r.get('aliases',[])]
        assessments.append(dict(project_id=pid,project_name=row['專案名稱'],cohort='ORIGINAL33' if pid in ids else 'REVIEWED_EXTENSION',
            remaining_blank_cells=len(pending),newly_filled_existing_cells=sum(c['project_id']==pid and c['status']=='NEWLY_FILLED' for c in changes),
            source_specific_reasons=json.dumps(sorted({g['reason'] for g in pending if g.get('review_id')}|{r['reason'] for r in named}),ensure_ascii=False),
            resource_pair_available=bool(row['礦石蘊藏量_Mt'] and row['TREO品位_pct'])))
    write('project_gap_assessment.csv',assessments)
    tests=[]
    for name in a.test_report:
        p=Path(name);s=ET.parse(p).getroot().find('testsuite')
        if s is None or any(int(s.get(k,'0')) for k in ['failures','errors']):raise ValueError('ROUND4_TEST_FAILURE')
        tests.append(dict(report=p.name,sha256=filehash(p),tests_including_subtests=int(s.get('tests','0')),failures=int(s.get('failures','0')),errors=int(s.get('errors','0')),skipped=int(s.get('skipped','0')),seconds=float(s.get('time','0'))))
    validation=dict(baseline_commit='b1625cf3f8f10155eec76f6f0ca5905251a7362b',parallel_baseline_commit='bf581820d176f732071a1463a0797a2d6301e93b',iteration=6,research_round=4,cutoff=summary['cutoff'],
        database_sha256=filehash(database),database_modified=False,review_ledger_sha256=filehash(ledger),discovery_ledger_sha256=filehash(discovery),
        current_integrity=report,increment=increment,coverage=metrics,
        acquisition=dict(urls=len(downloads),status_counts=dict(Counter(r['status'] for r in downloads)),
            pdf_urls_attempted=sum(r['kind']=='pdf' for r in downloads),pdf_urls_acquired=sum(r['status']=='PDF_ACQUIRED' for r in downloads),
            distinct_pdf_hashes=len({r['document_sha256'] for r in downloads if r['status']=='PDF_ACQUIRED'}),physical_pages=sum(r.get('physical_pages',0) for r in downloads if r['status']=='PDF_ACQUIRED'),
            archive_pages=len(archives['receipts']),parsed_archive_pages=sum(r['status']=='PARSED' for r in archives['receipts']),distinct_dated_archive_links=len(archives['documents'])),
        tests=tests,test_interpretation='RELATED_REGRESSIONS_AND_FOCUSED_TESTS_OVERLAP;NOT_FULL_HISTORICAL_REBUILD_OR_REMOTE_CI',
        repeated_csv_exports_identical=True,source_validation='STRICT_V2_SOURCE_CELLS_PLUS_SEPARATE_PROJECT_IDENTITY_REVIEW',
        code_fingerprint={str(p).replace('\\','/'):filehash(p) for base in ['src','tools','config'] for p in sorted(Path(base).rglob('*')) if p.is_file() and p.suffix in ('.py','.json')},
        artifact_hashes={p.name:filehash(p) for p in out.iterdir() if p.is_file() and p.name!='validation.json'})
    (out/'validation.json').write_text(json.dumps(validation,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    return dict(increment=increment,coverage=metrics,acquisition=validation['acquisition'])


def _numeric(value):
    try:float(value);return True
    except ValueError:return False


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for key in ['baseline','updated','repeat','ledger','discovery-ledger','discovery-audit','database','source-dir','archive-dir','out']:p.add_argument('--'+key,required=True)
    p.add_argument('--parallel-comparison');p.add_argument('--source-consistency');p.add_argument('--candidate-audit')
    p.add_argument('--test-report',action='append',required=True)
    print(json.dumps(package(p.parse_args()),ensure_ascii=False,indent=2))
