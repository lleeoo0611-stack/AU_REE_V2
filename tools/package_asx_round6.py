"""Audit fixed-cohort fills, new project cells and the ASX schema extension separately."""
import argparse,csv,json,math,shutil,xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path
from au_ree_v2.asx_validation import compare_summaries
from au_ree_v2.iteration_review import audit_summary,SCIENCE_INDEXES
from au_ree_v2.store import filehash
from au_ree_v2.asx import is_asx_document

BASELINE='b494607047c6d54111b7b6ad58e3335b3b93e889'
BASELINE_CSV='f1e96c107de86de73e7eb93d027290f809e834b84035d695bf9cf49e7bf60288'
SQLITE_SHA='99ed9c0fc004960f92680ee782ef8764c189a08d98bce4d14c2d0e5ad99091d0'

def read(folder,name):
    with (Path(folder)/name).open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))

def write(folder,name,rows,fields=None):
    with (Path(folder)/name).open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fields or list(rows[0]));w.writeheader();w.writerows(rows)

def package(a):
    out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    baseline=read(a.baseline,'專案總表.csv');base=read(a.base52,'專案總表.csv');rows=read(a.updated,'專案總表.csv')
    if filehash(Path(a.baseline)/'專案總表.csv')!=BASELINE_CSV or len(baseline)!=43 or len(baseline[0])!=52 or sum(v=='' for r in baseline for v in r.values())!=1268:
        raise ValueError('ROUND6_BASELINE_CHANGED')
    integrity=audit_summary(a.updated);base_integrity=audit_summary(a.base52)
    s=json.loads((Path(a.updated)/'summary.json').read_text('utf8'));bs=json.loads((Path(a.base52)/'summary.json').read_text('utf8'))
    if s['database_modified'] or filehash(a.database)!=SQLITE_SHA or s['database_sha256']!=SQLITE_SHA:
        raise ValueError('ROUND6_DATABASE_CHANGED')
    for key,path in [('review_ledger_sha256',a.ledger),('discovery_ledger_sha256',a.discovery_ledger),('identity_ledger_sha256',a.identity_ledger)]:
        if s[key]!=filehash(path):raise ValueError('ROUND6_LEDGER_CHANGED')
    for folder,repeat,summary in [(a.updated,a.repeat,s),(a.base52,a.repeat52,bs)]:
        if any(filehash(Path(repeat)/n)!=sha for n,sha in summary['output_hashes'].items()):raise ValueError('ROUND6_REPLAY_CHANGED')
    if len(rows[0])!=53 or list(rows[0])!=list(base[0])+['ASX代碼']:
        raise ValueError('ROUND6_ADDITIVE_SCHEMA_REQUIRED')
    # A consolidation is a distinct accounting event. Never call removed blank
    # cells recovered data; the current round has no eligible actual merge.
    if s['identity_merges'] or {r['專案ID'] for r in base}!={r['專案ID'] for r in rows}:
        raise ValueError('ROUND6_UNEXPECTED_MERGE_REQUIRES_SEPARATE_COHORT_ACCOUNTING')
    rowmap={r['專案ID']:r for r in rows}
    if any(any(r[c]!=rowmap[r['專案ID']][c] for c in r) for r in base):raise ValueError('ROUND6_IDENTITY_CHANGED_BASE_VALUES')
    increment=compare_summaries(a.baseline,a.base52,out,True);changes=read(out,'field_changes.csv')
    science=[list(base[0])[i] for i in SCIENCE_INDEXES];ids={r['專案ID'] for r in baseline}
    def numeric(value):
        try:return math.isfinite(float(value))
        except ValueError:return False
    increment.update(scientific_newly_filled_cells=sum(r['status']=='NEWLY_FILLED' and r['column'] in science for r in changes),
        numeric_newly_filled_cells=sum(r['status']=='NEWLY_FILLED' and numeric(r['after']) for r in changes),
        asx_new_column_filled=sum(bool(r['ASX代碼']) for r in rows),asx_new_column_blanks=sum(not r['ASX代碼'] for r in rows),
        asx_codes_original_cohort=sum(bool(r['ASX代碼']) for r in rows if r['專案ID'] in ids),
        asx_codes_new_cohort=sum(bool(r['ASX代碼']) for r in rows if r['專案ID'] not in ids),
        actual_identity_merges=0,base52_blanks_are_separate_from_new_asx_column=True)
    integration=None
    if a.remote_baseline:
        remote_compare=Path(a.remote_baseline)/'comparison_from_original';direct_compare=Path(a.remote_baseline)/'comparison_to_final'
        inherited=compare_summaries(a.baseline,a.remote_baseline,remote_compare)
        direct=compare_summaries(a.remote_baseline,a.base52,direct_compare,True)
        if increment['newly_filled_cells']!=inherited['newly_filled_cells']+direct['newly_filled_cells']:
            raise ValueError('ROUND6_REMOTE_INCREMENT_NOT_ADDITIVE')
        for folder,prefix in [(remote_compare,'inherited_remote_'),(direct_compare,'direct_round6_')]:
            for name in ['field_changes.csv','field_increment.json']:shutil.copyfile(folder/name,out/(prefix+name))
        integration=dict(integrated_commits=['b610eff5c1f0fce169dbb58e31bca4efe7a7f13b','ab098e267fdd70a85d39034c972548ce09a29bc7'],
            original_baseline=BASELINE,remote_parent='ab098e267fdd70a85d39034c972548ce09a29bc7',inherited_remote_newly_filled=inherited['newly_filled_cells'],
            direct_round6_newly_filled=direct['newly_filled_cells'],combined_since_original_baseline=increment['newly_filled_cells'],
            note='REMOTE_ADDITIONS_PRESERVED_AND_REPLAYED;NOT_CLAIMED_AS_NEW_SEARCH_RECOVERIES_OF_THIS_ROUND')
        (out/'remote_integration.json').write_text(json.dumps(integration,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    (out/'field_increment.json').write_text(json.dumps(increment,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    for n in ['專案總表.csv','field_provenance.csv','missing_fields.csv','census_inventory.csv','summary.json']:shutil.copyfile(Path(a.updated)/n,out/n)
    shutil.copyfile(Path(a.base52)/'專案總表.csv',out/'專案總表_原52欄.csv');shutil.copyfile(Path(a.baseline)/'專案總表.csv',out/'專案總表_補值前.csv')
    coverage=[]
    for label,cohort,columns in [('BASELINE43_ORIGINAL52',baseline,list(baseline[0])),('UPDATED43_ORIGINAL52',[r for r in base if r['專案ID'] in ids],list(base[0])),
        ('NEW_PROJECTS_ORIGINAL52',[r for r in base if r['專案ID'] not in ids],list(base[0])),('EXPANDED_ORIGINAL52',base,list(base[0])),
        ('UPDATED43_WITH_ASX',[r for r in rows if r['專案ID'] in ids],list(rows[0])),('NEW_PROJECTS_WITH_ASX',[r for r in rows if r['專案ID'] not in ids],list(rows[0])),('EXPANDED53',rows,list(rows[0]))]:
        coverage.append(dict(cohort=label,projects=len(cohort),columns=len(columns),filled_cells=sum(r[c]!='' for r in cohort for c in columns),blank_cells=sum(r[c]=='' for r in cohort for c in columns),
            science_filled=sum(r[c]!='' for r in cohort for c in science),science_total=len(cohort)*25,
            paired_resources=sum(bool(r['礦石蘊藏量_Mt'] and r['TREO品位_pct']) for r in cohort),full15=sum(r['已公布元素數_共15項']=='15' for r in cohort),
            annual_treo=sum(bool(r['預估年產TREO_t_per_year']) for r in cohort),annual_ndpr=sum(bool(r['預估年產NdPr_t_per_year']) for r in cohort),annual_hree8=sum(bool(r['預估年產重稀土_t_per_year']) for r in cohort)))
    write(out,'cohort_coverage.csv',coverage)
    disc=json.loads(Path(a.discovery_ledger).read_text('utf8'));identity=json.loads(Path(a.identity_ledger).read_text('utf8'))
    follow=[r for r in disc['candidates'] if r['candidate_key'] in ['caralue-bluff','franklyn','billeroo','olympic-dam','carrapateena']]
    if len(follow)!=5 or any(not r.get('round6_review') for r in follow):raise ValueError('ROUND6_FOLLOWUP5_INCOMPLETE')
    write(out,'candidate_followup5.csv',[dict(candidate_key=r['candidate_key'],name=r['name'],decision=r['decision'],reason=r['reason'],review=json.dumps(r['round6_review'],ensure_ascii=False),
        source_urls=json.dumps([s['url'] for s in r['sources']]),source_hashes=json.dumps([s['sha256'] for s in r['sources']]),source_evidence=json.dumps([s['evidence'] for s in r['sources']],ensure_ascii=False)) for r in follow])
    newids=set(rowmap)-ids
    admissions=[r for r in s['discovery_reviews'] if r.get('project_id') in newids]
    if {r['project_id'] for r in admissions}!=newids:raise ValueError('ROUND6_NEW_IDENTITY_RECEIPTS_MISSING')
    write(out,'new_project_admissions.csv',[dict(project_id=r['project_id'],name=r['name'],candidate_key=r['candidate_key'],source_date=r['identity']['publication_date'],
        scope=r['scope'],sources=json.dumps(r['sources'],ensure_ascii=False),note='DATED_RESEARCH_IDENTITY;CURRENT_TENURE_CONTINUITY_NOT_FORMALLY_CERTIFIED') for r in admissions])
    code_trace={r['project_id']:r for r in read(a.updated,'field_provenance.csv') if r['column']=='ASX代碼'}
    code_unknown={r['project_id']:r['reason'] for r in identity.get('unresolved_codes',[])}
    write(out,'asx_code_coverage.csv',[dict(project_id=r['專案ID'],project_name=r['專案名稱'],asx_code=r['ASX代碼'],cohort='ORIGINAL43' if r['專案ID'] in ids else 'NEW_PROJECT',
        evidence_date=code_trace.get(r['專案ID'],{}).get('effective_date',''),source_sha256=code_trace.get(r['專案ID'],{}).get('source_sha256',''),source_url=code_trace.get(r['專案ID'],{}).get('source_url',''),
        reason='' if r['ASX代碼'] else code_unknown.get(r['專案ID'],'NO_CAPTURED_ASX_ISSUER_PROOF;PRIVATE_LSE_OR_HISTORICAL_OWNER_NOT_ASSUMED')) for r in rows])
    write(out,'identity_merge_assessments.csv',[dict(project_ids=json.dumps(r['project_ids']),names=json.dumps(r['names']),decision=r['decision'],reason=r['reason'],source_url=r['source_url'],supplemental_url=r['supplemental_url']) for r in identity['merge_assessments']])
    gaps=read(a.updated,'missing_fields.csv');write(out,'priority_missing_fields.csv',[r for r in gaps if r['column'] in science])
    write(out,'remaining_gap_reasons.csv',[dict(reason=k,blank_cells=v) for k,v in Counter(r['reason'] for r in gaps).most_common()])
    write(out,'project_gap_assessment.csv',[dict(project_id=r['專案ID'],project_name=r['專案名稱'],cohort='ORIGINAL43' if r['專案ID'] in ids else 'NEW_PROJECT',
        original52_filled=sum(r[c]!='' for c in list(base[0])),original52_blanks=sum(r[c]=='' for c in list(base[0])),asx_code=r['ASX代碼'],
        scientific_blanks=sum(not r[c] for c in science),newly_filled_original_cells=sum(c['project_id']==r['專案ID'] and c['status']=='NEWLY_FILLED' for c in changes),
        remaining_reasons=json.dumps(sorted({g['reason'] for g in gaps if g['project_id']==r['專案ID']}),ensure_ascii=False)) for r in rows])
    for n in ['discovery_reviews.csv','discovery_candidate_queue.csv','discovery_validation.json']:shutil.copyfile(Path(a.discovery_audit)/n,out/n)
    for n in ['candidate_validation.csv','candidate_validation.json']:shutil.copyfile(Path(a.candidate_audit)/n,out/n)
    for n in ['external_name_reviews.csv','external_name_review.json']:shutil.copyfile(Path(a.external_audit)/n,out/n)
    for path,name in [(a.ledger,'source_reviews.json'),(a.discovery_ledger,'project_discovery_reviews.json'),(a.identity_ledger,'project_identity_reviews.json'),(a.external_ledger,'external_name_reviews.json'),(a.external_search,'external_search_receipts.json'),(Path(a.source_dir)/'downloads.json','research_downloads.json')]:shutil.copyfile(path,out/name)
    if a.source_consistency:shutil.copyfile(a.source_consistency,out/'source_consistency.csv')
    if a.replay_source_dir:
        replay=[json.loads((Path(path)/'downloads.json').read_text('utf8')) for path in a.replay_source_dir]
        (out/'integrated_source_replay.json').write_text(json.dumps(dict(source_sets=replay,ephemeral_links_published=False),ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    downloads=json.loads((Path(a.source_dir)/'downloads.json').read_text('utf8'));archives=[json.loads(Path(p).read_text('utf8')) for p in a.archive]
    write(out,'document_dispositions.csv',[dict(key=r['key'],url=r['url'],status=r['status'],source_sha256=r.get('document_sha256',''),pages=r.get('physical_pages',''),failure_reason=r.get('failure_status',''),
        numerical_reviews=json.dumps([x['review_id'] for x in json.loads(Path(a.ledger).read_text('utf8'))['reviews'] if x['source_sha256']==r.get('document_sha256')]),
        interpretation='DOCUMENT_CAPTURE_IS_NOT_NUMERIC_ADMISSION') for r in downloads])
    (out/'archive_discovery.json').write_text(json.dumps(dict(searches=archives),ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    tests=[]
    for path in a.test_report:
        p=Path(path);suite=ET.parse(p).getroot().find('testsuite')
        if suite is None or any(int(suite.get(k,'0')) for k in ['failures','errors']):raise ValueError('ROUND6_TEST_FAILED')
        tests.append(dict(report=p.name,sha256=filehash(p),tests_including_subtests=int(suite.get('tests','0')),failures=0,errors=0,seconds=float(suite.get('time','0'))))
    validation=dict(baseline_commit=BASELINE,iteration=10,research_round=6,cutoff=s['cutoff'],database_sha256=SQLITE_SHA,database_modified=False,
        integrity53=integrity,integrity52=base_integrity,increment=increment,coverage=coverage,followup5=dict(Counter(r['decision'] for r in follow)),
        original_canonical_projects=s['original_canonical_projects'],reviewed_project_extensions=s['reviewed_project_extensions'],
        tests=tests,test_interpretation='RELATED_REGRESSION_AND_FOCUSED_TESTS_OVERLAP;NO_FULL_HISTORICAL_REBUILD_OR_REMOTE_CI_CLAIM',repeated_csv_exports_identical=True,remote_integration=integration,
        acquisition=dict(urls=len(downloads),statuses=dict(Counter(r['status'] for r in downloads)),pdf_urls=sum(r['kind']=='pdf' for r in downloads),pdf_acquired=sum(r['status']=='PDF_ACQUIRED' for r in downloads),
            pdf_document_pages=sum(r.get('physical_pages',0) for r in downloads if r['status']=='PDF_ACQUIRED'),asx_pdf_urls=sum(is_asx_document(r['url']) for r in downloads),
            asx_pdf_acquired=sum(is_asx_document(r['url']) and r['status']=='PDF_ACQUIRED' for r in downloads),archive_pages=sum(len(x['receipts']) for x in archives),
            parsed_archives=sum(r['status']=='PARSED' for x in archives for r in x['receipts']),distinct_announcement_links=len({r['url'] for x in archives for r in x['documents']})),
        code_fingerprint={str(p).replace('\\','/'):filehash(p) for folder in ['src','tools','config'] for p in sorted(Path(folder).rglob('*')) if p.is_file() and p.suffix in ('.py','.json')},
        artifact_hashes={p.name:filehash(p) for p in out.iterdir() if p.is_file() and p.name!='validation.json'})
    (out/'validation.json').write_text(json.dumps(validation,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    return {k:validation[k] for k in ['increment','coverage','acquisition','followup5']}

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for key in ['baseline','base52','updated','repeat','repeat52','ledger','discovery-ledger','identity-ledger','external-ledger','discovery-audit','candidate-audit','external-audit','external-search','database','source-dir','out']:p.add_argument('--'+key,required=True)
    p.add_argument('--archive',action='append',required=True);p.add_argument('--test-report',action='append',required=True);p.add_argument('--source-consistency');p.add_argument('--remote-baseline');p.add_argument('--replay-source-dir',action='append')
    print(json.dumps(package(p.parse_args()),ensure_ascii=False,indent=2))
