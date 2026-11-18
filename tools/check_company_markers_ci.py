"""Read only this clean CI's verified PDFs; never fetch or repair a locator."""
import hashlib
import json
import os
from collections import Counter
from pathlib import Path
from au_ree_v2.evidence import validate_pages
from au_ree_v2.pdf_extract import extract_page
from au_ree_v2.store import canonical
from company_marker_approvals import (ROOT,BASE,load_ledger,project_map,binding_for,
                                     expected_claims,write_rows)

FIELDS=['proposal_id','project_id','column','source_key','source_sha256','pdf_page',
        'declaration_pointer','status','reason','page_text_first_300','extraction_method']
ADOPTED={'FETCHED_SHA_VERIFIED','ALTERNATE_SAME_SHA','COMMITTED_SNAPSHOT_SAME_SHA',
         'COMMITTED_MANAGED_SAME_SHA','SNAPSHOT_FALLBACK_SAME_SHA'}


def check_row(root,row,project,source,snapshots,cache,output):
    record={k:row[k] for k in FIELDS[:7]}
    record.update(status='NOT_CHECKED_SOURCE_UNAVAILABLE',reason='SOURCE_NOT_ACQUIRED',
                  page_text_first_300='',extraction_method='')
    if not source:return record
    original=(root/source['path']).resolve()
    try:
        if not original.is_relative_to(root.resolve()) or hashlib.sha256(original.read_bytes()).hexdigest()!=row['source_sha256']:
            record['reason']='SOURCE_SHA_CHANGED';return record
    except OSError:
        record['reason']='SOURCE_FILE_UNAVAILABLE';return record
    binding=binding_for(project,row)
    markers=binding.get('page_markers',binding.get('markers',[]))
    page=int(row['pdf_page'])
    try:
        data=extract_page(original,page,os.environ.get('TESSDATA_PREFIX'),markers=markers)
        record.update(page_text_first_300=data['text'][:300],extraction_method=data['method'])
        if data['status']!='EXTRACTED_REQUIRES_SCOPE_VALIDATION':
            raise ValueError('EXTRACTION_PAGE_CHECK_FAILED')
        # Use the same SHA-bound extraction-artifact path as strict_claims.
        payload=(canonical(data)+'\n').encode('utf8')
        sha=hashlib.sha256(payload).hexdigest()
        path=output/'page-proofs'/(sha+'.json');path.parent.mkdir(parents=True,exist_ok=True)
        path.write_bytes(payload)
        artifact=dict(key='v10_audit_'+sha,sha256=sha,path=str(path),kind='pdf_page_extraction')
        evidence=dict(source_sha256=row['source_sha256'],pdf_page=page,page_markers=markers,
            page_extraction_key=artifact['key'],page_extraction_sha256=sha,
            marker_normalization='WHITESPACE_ONLY_V1')
        validate_pages(root,source,evidence,[*snapshots,artifact],cache)
        record.update(status='PASS',reason='EVIDENCE_PY_PAGE_AND_MARKERS_VERIFIED')
    except Exception as exc:
        record.update(status='FAILED_IN_CI',reason=str(exc) or type(exc).__name__)
    return record


def main():
    root=ROOT.resolve();clean=root/'work/clean';output=clean/'v10'
    output.mkdir(parents=True,exist_ok=True)
    rows,approved=load_ledger(root)
    claims=json.loads((root/'data/claims.json').read_bytes())
    expected,_=expected_claims(root)
    if claims!=expected:raise ValueError('CLAIMS_CONTAIN_UNAPPROVED_CHANGES')
    projects=project_map(claims)
    latest=json.loads((clean/'latest.json').read_bytes())
    run=Path(latest['output_dir'])
    snapshots=json.loads((run/'snapshot_lock.json').read_bytes())
    from company_marker_approvals import read_rows
    receipts={r['key']:r for r in read_rows(run/'acquisition_report.csv')}
    sources={s['sha256']:s for s in snapshots if s.get('kind')=='pdf' and
        receipts.get(s['key'],{}).get('sha_match')=='True' and
        receipts[s['key']]['status'] in ADOPTED}
    cache={};results=[]
    for row in approved:
        results.append(check_row(root,row,projects[row['project_id']],sources.get(row['source_sha256']),
                                 snapshots,cache,output))
    failed={r['proposal_id'] for r in results if r['status']=='FAILED_IN_CI'}
    for row in rows:
        if row['approved']=='Y' and row['proposal_id'] in failed:row['approved']='FAILED_IN_CI'
    write_rows(output/'p2_marker_proposals_approved.csv',rows,list(rows[0]))
    write_rows(output/'p2_ci_marker_results.csv',results,FIELDS)
    write_rows(output/'p2_ci_marker_failures.csv',[r for r in results if r['status']=='FAILED_IN_CI'],FIELDS)
    summary=dict(approved_rows=70,statuses=dict(Counter(r['status'] for r in results)),
                 claims_modified=False,markers_or_pages_repaired=False,http_requests=0)
    (output/'p2_ci_marker_summary.json').write_text(json.dumps(summary,indent=2)+'\n',encoding='utf8')
    print(json.dumps(summary))


if __name__=='__main__':main()
