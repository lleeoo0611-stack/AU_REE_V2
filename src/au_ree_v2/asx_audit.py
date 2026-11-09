"""Freeze and retest historical ASX failures without changing the research store."""
import csv
import hashlib
import json
import shutil
import time
from collections import Counter
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import urlsplit
from .asx import fetch_pdf,is_asx_document
from .acquisition import failure_details
from .store import canonical,filehash


def historical_cases(root):
    root=Path(root);manifest=json.loads((root/'data/manifest.json').read_text(encoding='utf8'))
    cases={};receipts=[]
    for source in manifest['snapshots']:
        if source['kind']!='discovery_receipt':continue
        path=root/source['path']
        if filehash(path)!=source['sha256']:raise ValueError('HISTORICAL_RECEIPT_HASH_MISMATCH')
        receipts.append(dict(path=source['path'],sha256=source['sha256']))
        data=json.loads(path.read_text(encoding='utf8'))
        for section in ('sources','documents'):
            for row in data.get(section,[]):
                url=row.get('url','')
                if urlsplit(url).hostname not in ('www.asx.com.au','announcements.asx.com.au') or not row.get('failure_status'):continue
                case=cases.setdefault(url,dict(case_id=hashlib.sha256(url.encode()).hexdigest()[:16],url=url,history=[]))
                case['history'].append(dict(receipt_sha256=source['sha256'],receipt_path=source['path'],section=section,
                    failure_status=row['failure_status'],publication_date=row.get('publication_date'),
                    project_id=row.get('project_id'),seed_key=row.get('seed_key'),
                    title=' '.join(row.get('title','').split())))
    return dict(version='asx-historical-cohort-v1',manifest_sha256=filehash(root/'data/manifest.json'),
        receipts=receipts,cases=sorted(cases.values(),key=lambda c:c['url']),
        denominator='DISTINCT_FAILED_URLS_IN_IMMUTABLE_DISCOVERY_RECEIPTS; NOT_ALL_ASX_OR_PROJECTS')


def _write(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf8')


def summary(cohort,outcomes):
    passed=[r for r in outcomes if r['status']=='PDF_ACQUIRED']
    attempted=[r for r in outcomes if r['status']!='DEFERRED']
    return dict(cohort_urls=len(cohort['cases']),completed_urls=len(outcomes),attempted_urls=len(attempted),
        successful_urls=len(passed),success_rate_all_urls=len(passed)/len(cohort['cases']) if cohort['cases'] else None,
        success_rate_attempted=len(passed)/len(attempted) if attempted else None,
        unique_pdf_hashes=len({r['document_sha256'] for r in passed}),
        new_pdf_hashes=len({r['document_sha256'] for r in passed if not r['already_in_manifest']}),
        failure_reasons=dict(Counter(r.get('failure_reason') for r in outcomes if r['status']!='PDF_ACQUIRED')),
        historical_failure_records=sum(len(c['history']) for c in cohort['cases']),
        historical_reasons=dict(Counter(h['failure_status'] for c in cohort['cases'] for h in c['history'])))


def retest(root,out,fetch=None,min_free_bytes=128*1024*1024):
    root=Path(root).resolve();out=Path(out).resolve();out.mkdir(parents=True,exist_ok=True)
    if out==root or root in out.parents and out.relative_to(root).parts[0] in ('data','results','config','src'):
        raise ValueError('AUDIT_OUTPUT_MUST_BE_ISOLATED')
    cohort=historical_cases(root);frozen=out/'cohort.json'
    if frozen.exists() and json.loads(frozen.read_text('utf8'))!=cohort:raise ValueError('FROZEN_COHORT_CHANGED')
    _write(frozen,cohort)
    (out/'data/snapshots').mkdir(parents=True,exist_ok=True)
    manifest=json.loads((root/'data/manifest.json').read_text('utf8'))['snapshots']
    known={s['sha256'] for s in manifest if s['kind']=='pdf'}
    checkpoint=out/'retest.json'
    report=json.loads(checkpoint.read_text('utf8')) if checkpoint.exists() else dict(
        version='asx-historical-retest-v1',started_at=datetime.now(timezone.utc).isoformat(),outcomes=[])
    done={r['case_id'] for r in report['outcomes']}
    def archive(raw,url,suffix):
        sha=hashlib.sha256(raw).hexdigest();path=out/'data/snapshots'/(sha+suffix)
        if not path.exists():path.write_bytes(raw)
        if filehash(path)!=sha:raise ValueError('AUDIT_SNAPSHOT_HASH_MISMATCH')
        return sha
    for index,case in enumerate(cohort['cases'],1):
        if case['case_id'] in done:continue
        start=time.monotonic();row=dict(case_id=case['case_id'],url=case['url'],tested_at=datetime.now(timezone.utc).isoformat())
        if not is_asx_document(case['url']):row.update(status='DEFERRED',failure_reason='ARCHIVE_INDEX_NOT_DOCUMENT_URL')
        elif shutil.disk_usage(out).free<min_free_bytes+40*1024*1024:row.update(status='DEFERRED',failure_reason='LOCAL_DISK_RESERVE')
        else:
            try:
                raw,_,receipt=fetch_pdf(case['url'],fetch=fetch,archive=archive)
                sha=archive(raw,receipt['resolved_url'],'.pdf')
                row.update(status='PDF_ACQUIRED',document_sha256=sha,path='data/snapshots/'+sha+'.pdf',
                    already_in_manifest=sha in known,asx_acquisition=receipt,bytes=len(raw))
            except Exception as exc:
                details=failure_details(exc)
                row.update(status='UNAVAILABLE',failure_reason=details.get('validation_error') or details['failure_status'],**details)
        row['elapsed_seconds']=round(time.monotonic()-start,3);report['outcomes'].append(row)
        report['summary']=summary(cohort,report['outcomes']);_write(checkpoint,report)
        print(f"{index}/{len(cohort['cases'])} {row['status']} {case['url'].split('idsId=')[-1]}",flush=True)
    report['completed_at']=datetime.now(timezone.utc).isoformat();report['summary']=summary(cohort,report['outcomes'])
    _write(checkpoint,report)
    return report


def assess(root,out):
    """Reuse the existing recognizer; candidate availability is not resource admission."""
    from .pdf_extract import project_registry,recognize_document,candidate_value_issues,narrative_context_issues,extraction_dependencies
    root=Path(root);out=Path(out);cohort=json.loads((out/'cohort.json').read_text('utf8'))
    result=json.loads((out/'retest.json').read_text('utf8'));by_id={c['case_id']:c for c in cohort['cases']}
    manifest=json.loads((root/'data/manifest.json').read_text('utf8'))['snapshots']
    # A local copy of identity claims is an extraction input, never edited or promoted.
    claims=out/'data/claims.json';original=root/'data/claims.json'
    if claims.exists() and filehash(claims)!=filehash(original):raise ValueError('AUDIT_CLAIMS_CHANGED')
    if not claims.exists():shutil.copyfile(original,claims)
    registry=project_registry(root);aliases={p['entity_id']:p['aliases'] for p in registry}
    cached={s.get('source_sha256'):s for s in manifest if s['kind']=='document_extraction' and s.get('parser_version')=='document-recognition-v6-context-bound'}
    prior_path=out/'assessment.json'
    prior={d['source_sha256']:d for d in json.loads(prior_path.read_text('utf8'))['documents'] if d.get('extraction_path')} if prior_path.exists() else {}
    dependencies=extraction_dependencies();documents=[];candidates=[];opportunities=[]
    import re
    field_rules={
        '礦石蘊藏量_Mt/TREO品位_pct/總TREO蘊藏量_kt':r'mineral resources?|\bMRE\b',
        '磁鐵稀土/元素組成':r'Nd2O3|Pr6O11|Dy2O3|Tb4O7|NdPr|magnet rare earth',
        '預估年產/產品':r'(?i)(?:annual|per annum|\btpa\b|t/y).{0,100}(?:TREO|NdPr|oxide)|(?:TREO|NdPr|oxide).{0,100}(?:per annum|\btpa\b|t/y)',
        '開發階段':r'definitive feasibility|pre.feasibility|scoping study|construction|commissioning',
        'Technical揭露':r'metallurg|beneficiation|leach|recovery|pilot plant'}
    for row in result['outcomes']:
        if row['status']!='PDF_ACQUIRED':continue
        case=by_id[row['case_id']];sha=row['document_sha256']
        dates={h['publication_date'] for h in case['history'] if h.get('publication_date')}
        date=next(iter(dates)) if len(dates)==1 else None
        try:
            data=None
            if sha in prior:
                old=prior[sha];path=out/old['extraction_path']
                if filehash(path)!=old['extraction_sha256']:raise ValueError('EXTRACTION_HASH_MISMATCH')
                data=json.loads(path.read_text('utf8'));mode='AUDIT_EXTRACTION_CACHE'
            elif sha in cached:
                old=cached[sha];path=root/old['path']
                if filehash(path)!=old['sha256']:raise ValueError('EXTRACTION_HASH_MISMATCH')
                data=json.loads(path.read_text('utf8'));mode='EXISTING_VERIFIED_EXTRACTION'
            if data and data.get('extraction_dependency_sha256')!=dependencies:data=None
            if data is None:
                source=dict(key='asx_audit_'+row['case_id'],kind='pdf',path=row['path'],sha256=sha,url=row['url'],publication_date=date)
                data=recognize_document(out,source,registry);mode='EXISTING_V6_RECOGNIZER'
            raw=(canonical(data)+'\n').encode('utf8');artifact=out/'data/snapshots'/(hashlib.sha256(raw).hexdigest()+'.extraction.json')
            if not artifact.exists():artifact.write_bytes(raw)
            if filehash(artifact)!=hashlib.sha256(raw).hexdigest():raise ValueError('EXTRACTION_HASH_MISMATCH')
            pages={p['physical_page']:p for p in data['pages']};counts=Counter();clean=0
            for c in data['candidates']:
                issues=sorted(set(c.get('issues',[])+candidate_value_issues(c)+narrative_context_issues(
                    c,pages[c['physical_page']],version='scientific-context-v5-peer-boundary',project_aliases=aliases.get(c.get('project_id'),()))))
                counts[c['kind']]+=1;clean+=not issues
                candidates.append(dict(case_id=row['case_id'],source_sha256=sha,candidate_id=c['candidate_id'],
                    project_id=c.get('project_id'),kind=c['kind'],physical_page=c['physical_page'],issues=canonical(issues),
                    scope=c.get('scope'),values=canonical(c.get('values',c.get('value'))),raw_text=c['raw_text'],
                    admission='CANDIDATE_ONLY_EFFECTIVE_DATE_SCOPE_AND_ENTITY_CHECKS_REQUIRED'))
            for field,pattern in field_rules.items():
                for p in data['pages']:
                    text=' '.join(p['text'].split());match=re.search(pattern,text,re.I)
                    if match:opportunities.append(dict(case_id=row['case_id'],source_sha256=sha,field_group=field,
                        physical_page=p['physical_page'],excerpt=text[max(0,match.start()-100):match.end()+250],
                        status='PAGE_REVIEW_OPPORTUNITY_NOT_A_VALIDATED_VALUE'))
            historical_projects=sorted({h['project_id'] for h in case['history'] if h.get('project_id')})
            actual_projects=sorted({c.get('project_id') for c in data['candidates'] if c.get('project_id')})
            documents.append(dict(case_id=row['case_id'],source_sha256=sha,already_in_manifest=row['already_in_manifest'],
                publication_date=date,recognized_publication_date=data.get('publication_date'),
                date_conflict=bool(date and data.get('publication_date') and date!=data['publication_date']),
                historical_project_context=historical_projects,recognized_project_ids=actual_projects,
                project_context_is_not_verified_attribution=True,mode=mode,physical_pages=len(pages),
                candidate_count=len(data['candidates']),candidate_kinds=dict(counts),candidates_without_local_issues=clean,
                validated_new_summary_values=0,extraction_path=artifact.relative_to(out).as_posix(),extraction_sha256=filehash(artifact)))
            print('assessed',row['case_id'],len(pages),'pages',len(data['candidates']),'candidates',flush=True)
        except Exception as exc:documents.append(dict(case_id=row['case_id'],source_sha256=sha,status='EXTRACTION_FAILED',**failure_details(exc)))
        _write(out/'assessment.json',dict(documents=documents,scope='CANDIDATE_YIELD_NOT_FORMAL_ADMISSION'))
    for filename,rows,fields in [
        ('candidate_evidence.csv',candidates,['case_id','source_sha256','candidate_id','project_id','kind','physical_page','issues','scope','values','raw_text','admission']),
        ('field_opportunities.csv',opportunities,['case_id','source_sha256','field_group','physical_page','excerpt','status'])]:
        with (out/filename).open('w',encoding='utf-8-sig',newline='') as stream:
            writer=csv.DictWriter(stream,fields);writer.writeheader();writer.writerows(rows)
    return documents


def package_evaluation(root,audit_dir,summary_dir,out):
    """Publish statistical results and provenance; keep raw originals in the audit store."""
    from .pdf_extract import project_registry
    root=Path(root);audit_dir=Path(audit_dir);summary_dir=Path(summary_dir);out=Path(out)
    out.mkdir(parents=True,exist_ok=True)
    cohort=json.loads((audit_dir/'cohort.json').read_text('utf8'))
    retested=json.loads((audit_dir/'retest.json').read_text('utf8'))
    assessed=json.loads((audit_dir/'assessment.json').read_text('utf8'))['documents']
    exported=json.loads((summary_dir/'summary.json').read_text('utf8'))
    for name,sha in exported['output_hashes'].items():
        if filehash(summary_dir/name)!=sha:raise ValueError('SUMMARY_OUTPUT_HASH_MISMATCH')
    names={p['entity_id']:p['name'] for p in project_registry(root)}
    cases={c['case_id']:c for c in cohort['cases']};docs={d['case_id']:d for d in assessed}
    with (audit_dir/'candidate_evidence.csv').open(encoding='utf-8-sig') as f:candidates=list(csv.DictReader(f))
    with (audit_dir/'field_opportunities.csv').open(encoding='utf-8-sig') as f:opportunities=list(csv.DictReader(f))
    case_rows=[];by_project={}
    for r in retested['outcomes']:
        c=cases[r['case_id']];d=docs.get(r['case_id'],{})
        projects=sorted({h['project_id'] for h in c['history'] if h.get('project_id')})
        case_rows.append(dict(case_id=r['case_id'],url=r['url'],status=r['status'],failure_reason=r.get('failure_reason',''),
            historical_project_context=canonical(projects),document_sha256=r.get('document_sha256',''),
            physical_pages=d.get('physical_pages',''),candidate_count=d.get('candidate_count',''),
            title=c['history'][0]['title'],publication_date=c['history'][0].get('publication_date'),
            extraction_status=d.get('status','PARSED') if d else 'NOT_ASSESSED'))
        for pid in projects:
            p=by_project.setdefault(pid,dict(project_id=pid,project_name=names.get(pid,pid),urls=[],field_groups=set(),pages=0,candidates=0))
            p['urls'].append(r['case_id']);p['pages']+=d.get('physical_pages',0);p['candidates']+=d.get('candidate_count',0)
            p['field_groups'].update(o['field_group'] for o in opportunities if o['case_id']==r['case_id'])
    project_rows=[dict(project_id=p['project_id'],project_name=p['project_name'],historical_urls=len(p['urls']),
        pages=p['pages'],candidates=p['candidates'],field_groups=canonical(sorted(p['field_groups'])),
        status='HISTORICAL_ISSUER_SEARCH_CONTEXT_NOT_VERIFIED_PROJECT_ATTRIBUTION') for p in by_project.values()]
    failure_issues=Counter(i for c in candidates for i in json.loads(c['issues']))
    evaluation=dict(version='asx-expanded-evaluation-v1',retrieval=retested['summary'],issuer_search_contexts=len(by_project),
        physical_pages=sum(d.get('physical_pages',0) for d in assessed),parsed_documents=sum('candidate_count' in d for d in assessed),
        candidate_count=len(candidates),candidate_kinds=dict(Counter(c['kind'] for c in candidates)),
        candidates_without_local_issues=sum(not json.loads(c['issues']) for c in candidates),
        candidate_kinds_without_local_issues=dict(Counter(c['kind'] for c in candidates if not json.loads(c['issues']))),
        candidate_issue_counts=dict(failure_issues),
        field_opportunity_document_counts={g:len({o['case_id'] for o in opportunities if o['field_group']==g}) for g in sorted({o['field_group'] for o in opportunities})},
        validated_new_numeric_summary_values=0,project_summary=exported,
        limitations=['ALL_HISTORICAL_FAILURES_WERE_TERMS_INTERSTITIALS_NOT_A_GENERAL_WAF_BENCHMARK',
        'FIELD_OPPORTUNITIES_ARE_PAGE_KEYWORD_HITS_NOT_VERIFIED_VALUES',
        'HISTORICAL_ISSUER_CONTEXT_IS_NOT_PROJECT_OR_RESOURCE_SCOPE_EQUIVALENCE',
        'NOVEMBER9_ACQUISITION_DOES_NOT_CHANGE_NOVEMBER5_FROZEN_RESULTS',
        'NO_NEW_MCDA_OR_FORMAL_C1_ADMISSION_CLAIM',
        'RAW_PDFS_AND_FULL_EXTRACTION_ARTIFACTS_RETAINED_LOCALLY_NOT_PACKAGED'])
    _write(out/'evaluation.json',evaluation)
    for filename,data,fields in [
        ('case_results.csv',case_rows,['case_id','url','status','failure_reason','historical_project_context','document_sha256','physical_pages','candidate_count','title','publication_date','extraction_status']),
        ('research_recovery_by_project.csv',project_rows,['project_id','project_name','historical_urls','pages','candidates','field_groups','status']),
        ('candidate_review.csv',candidates,['case_id','source_sha256','candidate_id','project_id','kind','physical_page','issues','scope','values','admission']),
        ('field_opportunities.csv',opportunities,['case_id','source_sha256','field_group','physical_page','status'])]:
        with (out/filename).open('w',encoding='utf-8-sig',newline='') as f:
            w=csv.DictWriter(f,fields,extrasaction='ignore');w.writeheader();w.writerows(data)
    for name in ('cohort.json','retest.json','assessment.json'):shutil.copyfile(audit_dir/name,out/name)
    for name in ('專案總表.csv','field_provenance.csv','missing_fields.csv','census_inventory.csv','summary.json'):shutil.copyfile(summary_dir/name,out/name)
    return evaluation
