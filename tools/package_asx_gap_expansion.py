"""Publish derived gap-expansion results; original PDFs/text/database stay local."""
import argparse,csv,json,re,shutil,xml.etree.ElementTree as ET
from collections import Counter,defaultdict
from pathlib import Path
from au_ree_v2.store import filehash,digest

PRIORITY=['礦石蘊藏量_Mt','TREO品位_pct','總TREO蘊藏量_kt','NdPr蘊藏量_kt_需兩者皆公布',
    '完整重稀土組合蘊藏量_kt_需8元素皆公布','預估年產TREO_t_per_year','預估年產NdPr_t_per_year','預估年產重稀土_t_per_year']

def read_csv(path):
    with Path(path).open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for key in ['baseline','updated','repeat','comparison','technical-dir','selected-dir','audit-dir','ledger','database','out']:
        p.add_argument('--'+key,required=True)
    p.add_argument('--test-report',action='append',required=True)
    p.add_argument('--extra-selected-dir',action='append',default=[])
    p.add_argument('--extra-archive-dir',action='append',default=[])
    p.add_argument('--research-dir')
    a=p.parse_args()
    before=Path(a.baseline);updated=Path(a.updated);out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    summary=json.loads((updated/'summary.json').read_text('utf8'));increment=json.loads((Path(a.comparison)/'field_increment.json').read_text('utf8'))
    if summary['review_ledger_sha256']!=filehash(a.ledger):raise ValueError('REVIEW_LEDGER_CHANGED_AFTER_EXPORT')
    if summary['database_sha256']!=filehash(a.database):raise ValueError('READ_ONLY_DATABASE_CHANGED')
    if increment['baseline_csv_sha256']!=filehash(before/'專案總表.csv') or increment['updated_csv_sha256']!=filehash(updated/'專案總表.csv'):
        raise ValueError('SUMMARY_CHANGED_AFTER_COMPARISON')
    for name,sha in summary['output_hashes'].items():
        if filehash(updated/name)!=sha or filehash(Path(a.repeat)/name)!=sha:raise ValueError('EXPORT_REPLAY_MISMATCH')
    tests=[]
    for path in a.test_report:
        root=ET.parse(path).getroot();suites=[root] if root.tag=='testsuite' else root.findall('testsuite')
        counts={k:sum(int(s.get(k,0)) for s in suites) for k in ['tests','failures','errors','skipped']}
        if counts['failures'] or counts['errors'] or counts['skipped']:raise ValueError('REQUIRED_TESTS_NOT_ALL_PASSED')
        tests.append(dict(report=Path(path).name,sha256=filehash(path),**counts))
    ledger=json.loads(Path(a.ledger).read_text('utf8'));reviewed={r['source_sha256'] for r in ledger['reviews']}
    technical=Path(a.technical_dir);selected=Path(a.selected_dir)
    previous=json.loads((before/'technical_downloads.json').read_text('utf8'))
    old=json.loads((Path(a.audit_dir)/'retest.json').read_text('utf8'))['outcomes']
    fetched=json.loads((technical/'downloads.json').read_text('utf8'));extra=json.loads((selected/'downloads.json').read_text('utf8'))
    selected_sets=[(selected,extra)]
    for directory in a.extra_selected_dir:
        directory=Path(directory);selected_sets.append((directory,json.loads((directory/'downloads.json').read_text('utf8'))))
    extra=[r for _,records in selected_sets for r in records]
    index=json.loads((technical/'archive_discovery.json').read_text('utf8'));native=json.loads((technical/'native_inventory.json').read_text('utf8'))
    for row in index['receipts']:
        if row.get('sha256') and filehash(technical/'data/snapshots'/(row['sha256']+'.html'))!=row['sha256']:raise ValueError('ARCHIVE_HASH_MISMATCH')
    native_by_sha={r['source_sha256']:r for r in native};document_audit=[]
    for directory,rows in [(technical,fetched)]+selected_sets:
        for r in rows:
            sha=r.get('document_sha256');status=r['status']
            if status=='PDF_ACQUIRED' and filehash(directory/r['path'])!=sha:raise ValueError('PDF_HASH_MISMATCH')
            inv=native_by_sha.get(sha,{})
            if inv and filehash(technical/inv['native_text_path'])!=inv['native_text_sha256']:raise ValueError('NATIVE_TEXT_HASH_MISMATCH')
            unrelated=bool(re.search(r'Murchison|Turnberry|St Anne|Mt Holland|King Tamba|Mt Lindsay|Star of Mangaroon|Mt Clement',r['title'],re.I))
            disposition=('SOURCE_REVIEW_LEDGER;VALUES_ONLY_IF_EXPLICITLY_ADMITTED' if sha in reviewed else
                'OTHER_ASSET_OR_COMMODITY_TITLE;NO_SUMMARY_ADMISSION' if unrelated else 'UNREVIEWED_OR_CORROBORATING_CONTEXT;NO_AUTOMATIC_ADMISSION')
            document_audit.append(dict(url=r['url'],title=r['title'],source_sha256=sha,status=status,
                first_page_name_matches=json.dumps(inv.get('first_page_project_name_matches',[])),disposition=disposition))
    rows=read_csv(updated/'專案總表.csv');baseline=read_csv(before/'專案總表.csv');changes=read_csv(Path(a.comparison)/'field_changes.csv');gaps=read_csv(updated/'missing_fields.csv')
    if len(rows)!=33 or len(rows[0])!=52 or len({r['專案ID'] for r in rows})!=33:raise ValueError('SUMMARY_COHORT_CONTRACT_CHANGED')
    numeric_new=0
    for c in changes:
        if c['status']=='NEWLY_FILLED':
            try:float(c['after']);numeric_new+=1
            except ValueError:pass
    gaps_by_project=defaultdict(list)
    for g in gaps:gaps_by_project[g['project_id']].append(g)
    project_audit=[]
    for row in rows:
        pid=row['專案ID'];reviews=[r for r in ledger['reviews'] if r['project_id']==pid]
        pending=gaps_by_project[pid];priority=[g for g in pending if g['column'] in PRIORITY or '_氧化' in g['column']]
        specific=[g for g in priority if g.get('review_id')]
        project_audit.append(dict(project_id=pid,project_name=row['專案名稱'],remaining_blank_cells=len(pending),
            remaining_priority_cells=len(priority),newly_filled_cells=sum(c['project_id']==pid and c['status']=='NEWLY_FILLED' for c in changes),
            review_ids=json.dumps([r['review_id'] for r in reviews]),source_specific_gap_reasons=json.dumps(sorted({g['reason'] for g in specific})),
            review_state='SOURCE_SCOPES_REVIEWED;REMAINING_CELLS_NOT_PROVEN_ABSENT' if reviews else 'NO_NEW_COMPLETE_SOURCE_REVIEW;GAPS_REMAIN_UNRESOLVED'))
    def write(name,data):
        with (out/name).open('w',encoding='utf-8-sig',newline='') as f:
            w=csv.DictWriter(f,list(data[0]));w.writeheader();w.writerows(data)
    write('document_dispositions.csv',document_audit);write('project_gap_assessment.csv',project_audit)
    write('priority_missing_fields.csv',[g for g in gaps if g['column'] in PRIORITY or '_氧化' in g['column']])
    for name in ['專案總表.csv','field_provenance.csv','missing_fields.csv','summary.json']:shutil.copyfile(updated/name,out/name)
    shutil.copyfile(before/'專案總表.csv',out/'專案總表_補值前.csv');shutil.copyfile(a.ledger,out/'source_reviews.json')
    for name in ['field_changes.csv','field_increment.json','candidate_validation.csv','candidate_validation.json']:shutil.copyfile(Path(a.comparison)/name,out/name)
    for source,name in [(technical/'downloads.json','technical_downloads.json'),(technical/'archive_discovery.json','technical_discovery.json'),(technical/'native_inventory.json','technical_native_inventory.json'),(selected/'downloads.json','selected_downloads.json')]:shutil.copyfile(source,out/name)
    (out/'selected_downloads.json').write_text(json.dumps(extra,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    previous_selected=json.loads((before/'selected_downloads.json').read_text('utf8')) if (before/'selected_downloads.json').exists() else []
    all_docs=old+fetched+extra;success=[r for r in all_docs if r['status']=='PDF_ACQUIRED'];prior_urls={r['url'] for r in old+previous+previous_selected}
    round_rows=[r for r in fetched+extra if r['url'] not in prior_urls]
    evaluation=dict(version='asx-gap-expansion-v1',cutoff=summary['cutoff'],acquired_through=summary['acquired_through'],
        increment=increment,newly_filled_numeric_cells=numeric_new,filled_cells_before=sum(bool(v) for r in baseline for v in r.values()),
        filled_cells_after=sum(bool(v) for r in rows for v in r.values()),
        archive_codes=len(index['codes']),archive_pages_attempted=len(index['receipts']),archive_statuses=dict(Counter(r['status'] for r in index['receipts'])),
        archive_failures=dict(Counter(r.get('failure_status','UNKNOWN') for r in index['receipts'] if r['status']!='PARSED')),
        discovered_technical_keyword_urls=len(index['documents']),round_new_url_attempts=len(round_rows),round_pdf_successes=sum(r['status']=='PDF_ACQUIRED' for r in round_rows),
        round_pdf_failures=dict(Counter(r.get('failure_status','UNKNOWN') for r in round_rows if r['status']!='PDF_ACQUIRED')),
        combined_distinct_urls=len({r['url'] for r in all_docs}),combined_distinct_pdf_hashes=len({r['document_sha256'] for r in success}),
        technical_native_pages=sum(r['physical_pages'] for r in native),
        review_groups=len(ledger['reviews']),source_specific_gap_cells=sum(bool(g.get('review_id')) for g in gaps),gap_reasons=dict(Counter(g['reason'] for g in gaps)),
        limitations=['BOUNDED_ISSUER_YEARS_AND_TITLE_SEARCH;NOT_ALL_ASX_HISTORY','HTTP200_DENIALS_ARE_FAILURES_NOT_NO_ANNOUNCEMENTS',
        'UNREVIEWED_DOCUMENTS_AND_BLANKS_ARE_UNKNOWN_NOT_PROVEN_ABSENT','BARKLY_ASX_PUBLICATION_DATE_IS_DISTINCT_FROM_PROSPECTUS_ISSUE_AND_RESOURCE_EFFECTIVE_DATE',
        'DONALD_MIN5532_RESOURCE_SUBSCOPE_AND_HM_TO_BULK_NORMALIZATION_ARE_EXPLICIT','OLD_CUMMINS_MAGNET_SHARE_NOT_CARRIED_TO_UPDATED_RESOURCE',
        'NO_FORMAL_C1_OR_MCDA_RECALCULATION;ORIGINAL_SQLITE_UNCHANGED'])
    additional=[]
    for number,directory in enumerate(a.extra_archive_dir,1):
        directory=Path(directory);extra_index=json.loads((directory/'archive_discovery.json').read_text('utf8'))
        for r in extra_index['receipts']:
            if r.get('sha256') and filehash(directory/'data/snapshots'/(r['sha256']+'.html'))!=r['sha256']:raise ValueError('SUPPLEMENTAL_ARCHIVE_HASH_MISMATCH')
        shutil.copyfile(directory/'archive_discovery.json',out/f'supplemental_archive_discovery_{number}.json')
        additional.extend(extra_index['receipts'])
    evaluation.update(additional_archive_pages_attempted=len(additional),additional_archive_statuses=dict(Counter(r['status'] for r in additional)),
        additional_parsed_pages_with_zero_links=sum(r['status']=='PARSED' and r.get('document_links')==0 for r in additional),
        additional_archive_failures=dict(Counter(r.get('failure_status','UNKNOWN') for r in additional if r['status']!='PARSED')))
    if a.research_dir:
        research=Path(a.research_dir);checked=json.loads((research/'research_gap_validation.json').read_text('utf8'))
        if not checked['all_bindings_verified']:raise ValueError('RESEARCH_SOURCE_BINDINGS_NOT_VERIFIED')
        for name,sha in checked['output_hashes'].items():
            if filehash(research/name)!=sha:raise ValueError('RESEARCH_AUDIT_CHANGED')
            shutil.copyfile(research/name,out/name)
        if checked['config_sha256']!=filehash(research/'research_gap_reviews.json'):raise ValueError('RESEARCH_CONFIG_CHANGED')
        shutil.copyfile(research/'research_gap_validation.json',out/'research_gap_validation.json')
        evaluation['source_bound_search_review_groups']=checked['review_groups']
    (out/'evaluation.json').write_text(json.dumps(evaluation,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    repo=Path(__file__).resolve().parents[1]
    fingerprint=digest([(p.relative_to(repo).as_posix(),filehash(p)) for folder in ['src','tools'] for p in sorted((repo/folder).rglob('*.py'))])
    validation=dict(version='asx-gap-expansion-validation-v1',tests=tests,database_sha256=filehash(a.database),database_modified=False,
        review_ledger_sha256=filehash(a.ledger),replay_csv_hashes_identical=True,template_columns=52,unique_project_ids=33,
        code_fingerprint_src_tools=fingerprint,output_hashes={p.name:filehash(p) for p in sorted(out.iterdir()) if p.is_file() and p.name!='validation.json'})
    (out/'validation.json').write_text(json.dumps(validation,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps(evaluation,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
