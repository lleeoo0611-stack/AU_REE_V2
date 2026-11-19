"""Read only this clean CI's verified PDFs; never fetch or repair a locator."""
import hashlib
import json
import os
import subprocess
from collections import Counter, defaultdict
from pathlib import Path
from au_ree_v2.evidence import validate_pages
from au_ree_v2.pdf_extract import extract_page
from au_ree_v2.store import canonical, digest, filehash
from company_marker_approvals import (ROOT,load_ledger,project_map,binding_for,
                                     expected_claims,read_rows,write_rows)

FIELDS=['proposal_id','project_id','column','source_key','source_sha256','pdf_page',
        'declaration_pointer','status','reason','page_text_first_300','extraction_method',
        'current_binding_status','selected_source_sha256']
ADOPTED={'FETCHED_SHA_VERIFIED','ALTERNATE_SAME_SHA','COMMITTED_SNAPSHOT_SAME_SHA',
         'COMMITTED_MANAGED_SAME_SHA','SNAPSHOT_FALLBACK_SAME_SHA','STATIC_PDF_SHA_VERIFIED',
         'ARCHIVED_PRE_CUTOFF_SHA_VERIFIED'}
V10='6eeaeae118bf404eef3fe458b9cdcf42252ce6a5'
INTEGRATION_BASE='a03cfb194a0e8ab2d9a441e4a1b6ea14e86ead61'
COMPANY={'ASX代碼','未上市公司'}


def revision_claims(root, revision):
    return json.loads(subprocess.check_output(['git','show',revision+':data/claims.json'],cwd=root))


def approved_contract(project, row):
    binding=binding_for(project,row)
    pointer=row['declaration_pointer'].split('/')
    if pointer[1]=='identity_declaration':
        return project['identity_source'],binding
    # Other page contexts in this attribute have their own approval history.
    parent=project['attributes'][int(pointer[2])]
    return {k:v for k,v in parent.items() if k!='context_evidence'},binding


def proposal_markers(projects, rows):
    """Index exact proposal words at their project, field, source, page and pointer."""
    words=defaultdict(set)
    pairs=defaultdict(set)
    pointers=defaultdict(set)
    for row in rows:
        words[row['source_sha256']].update((row['marker_1'],row['marker_2']))
        pairs[row['source_sha256']].add((row['marker_1'],row['marker_2']))
        pointers[row['project_id']].add(row['declaration_pointer'])
    found=set()
    for pid,project in projects.items():
        def visit(pointer, column, key, sha, declaration):
            page=declaration.get('pdf_page',declaration.get('page'))
            markers=declaration.get('page_markers',declaration.get('markers',[]))
            # A new declaration may independently cite a shared issuer or project name.
            # At an unsigned location, only the complete proposed pair signals reuse.
            if pointer in pointers[pid]:
                guarded=words.get(sha,set()).intersection(markers)
            else:
                guarded={pair for pair in pairs.get(sha,()) if all(word in markers for word in pair)}
            for marker in guarded:
                found.add((pid,pointer,column,key,sha,page,marker))
        identity=project.get('identity_declaration',{})
        visit('/identity_declaration','ASX代碼',project.get('identity_source'),
              identity.get('source_sha256'),identity)
        for group in ('attributes','observations'):
            for i,claim in enumerate(project.get(group,[])):
                pointer=f'/{group}/{i}'
                column=claim.get('column',claim.get('variable'))
                key,sha=claim.get('source_key'),claim.get('source_sha256')
                visit(pointer,column,key,sha,claim)
                for j,context in enumerate(claim.get('context_evidence',[])):
                    visit(f'{pointer}/context_evidence/{j}',column,key,sha,context)
    return found


def check_contract(claims, published, rows, integrated_base=None):
    if integrated_base is None:
        if claims!=published:
            raise ValueError('V10_CLAIMS_CONTAIN_UNAPPROVED_CHANGES')
        return
    old,current=project_map(published),project_map(claims)
    if len(current)!=len(claims['projects']):
        raise ValueError('DUPLICATE_PROJECT_ID')
    for row in rows:
        if row['approved']!='Y':
            continue
        pid=row['project_id']
        try:
            same=approved_contract(current[pid],row)==approved_contract(old[pid],row)
        except (KeyError,ValueError,IndexError,TypeError):
            same=False
        if not same:
            raise ValueError('APPROVED_COMPANY_BINDING_CHANGED: '+row['proposal_id'])
    # Historical text already present in a separately published integrated claim
    # gives no v10 approval to that claim. Guard against new out-of-scope reuse.
    prior=proposal_markers(old,rows) | proposal_markers(project_map(integrated_base),rows)
    extra=proposal_markers(current,rows)-prior
    if extra:
        raise ValueError('UNAPPROVED_PROPOSAL_MARKER_SCOPE: '+repr(sorted(extra,key=str)[0]))


def census_selections(root, run, config):
    """Only the current sealed build can establish which company source won."""
    summary=json.loads((run/'summary.json').read_bytes())
    relative='project-summary/field_provenance.csv'
    path=run/relative
    hashes=summary.get('output_hashes',{})
    if (summary.get('status')!='COMPLETED' or config['claims_sha256']!=filehash(root/'data/claims.json')
        or summary.get('configuration_sha256')!=digest(config)
        or any(hashes.get(name)!=filehash(run/name) for name in
               ('configuration.json','snapshot_lock.json','acquisition_report.csv',relative))):
        raise ValueError('COMPANY_MARKER_RUN_OR_TRACE_DIGEST_MISMATCH')
    selected={}
    for row in read_rows(path):
        if row['column'] not in COMPANY:
            continue
        position=row['project_id'],row['column']
        if position in selected:
            raise ValueError('DUPLICATE_CENSUS_COMPANY_FIELD')
        selected[position]=row
    return selected


def selected_binding(row, selection, verified_ids, attribute_id=None):
    if not selection or not selection.get('source_sha256'):
        return 'NO_SELECTED_CENSUS_SOURCE',''
    sha=selection['source_sha256']
    if sha==row['source_sha256'] and (not attribute_id or attribute_id in json.loads(selection['attribute_ids'])):
        return 'SELECTED_SOURCE_MATCHES_APPROVAL',sha
    if not verified_ids.intersection(json.loads(selection['observation_ids'])):
        raise ValueError('UNVERIFIED_REPLACEMENT_COMPANY_SOURCE: '+row['proposal_id'])
    return 'SUPERSEDED_BY_VERIFIED_CENSUS_SOURCE',sha


def check_row(root,row,project,source,snapshots,cache,output):
    record={k:row[k] for k in FIELDS[:7]}
    record.update(status='NOT_CHECKED_SOURCE_UNAVAILABLE',reason='SOURCE_NOT_ACQUIRED',
                  page_text_first_300='',extraction_method='')
    if not source:return record
    original=(root/source['path']).resolve()
    try:
        if not original.is_relative_to(root.resolve()) or hashlib.sha256(original.read_bytes()).hexdigest()!=row['source_sha256']:
            record.update(status='FAILED_IN_CI',reason='SOURCE_SHA_OR_PATH_CHANGED');return record
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


def main(root=ROOT, clean=None, output=None):
    root=root.resolve();clean=clean or root/'work/clean';output=output or clean/'v10'
    output.mkdir(parents=True,exist_ok=True)
    rows,approved=load_ledger(root)
    claims=json.loads((root/'data/claims.json').read_bytes())
    expected,_=expected_claims(root)
    published=revision_claims(root,V10)
    if published!=expected:raise ValueError('FROZEN_V10_APPROVAL_CONTRACT_MISMATCH')
    latest=json.loads((clean/'latest.json').read_bytes())
    run=Path(latest['output_dir'])
    config=json.loads((run/'configuration.json').read_bytes())
    integrated='source_mode' in config
    check_contract(claims,published,rows,revision_claims(root,INTEGRATION_BASE) if integrated else None)
    selected=census_selections(root,run,config) if integrated else {}
    verified_ids=set(config.get('verified_claim_ids',[]))
    projects=project_map(published)
    snapshots=json.loads((run/'snapshot_lock.json').read_bytes())
    receipts={r['key']:r for r in read_rows(run/'acquisition_report.csv')}
    sources={(s['key'],s['sha256']):s for s in snapshots if s.get('kind')=='pdf' and
        receipts.get(s['key'],{}).get('sha_match')=='True' and
        receipts[s['key']].get('actual_sha256')==s['sha256'] and
        receipts[s['key']]['status'] in ADOPTED}
    cache={};results=[]
    for row in approved:
        record=check_row(root,row,projects[row['project_id']],sources.get((row['source_key'],row['source_sha256'])),
                         snapshots,cache,output)
        pointer=row['declaration_pointer'].strip('/').split('/')
        project=projects[row['project_id']]
        attribute_id=project['attributes'][int(pointer[1])]['attribute_id'] if pointer[0]=='attributes' else None
        state,sha=selected_binding(row,selected.get((row['project_id'],row['column'])),verified_ids,attribute_id) if integrated else ('FROZEN_V10','')
        record.update(current_binding_status=state,selected_source_sha256=sha)
        if state=='SUPERSEDED_BY_VERIFIED_CENSUS_SOURCE' and record['status']=='PASS':
            record.update(status='SUPERSEDED',reason='HISTORICAL_PAGE_VERIFIED_NEW_SOURCE_SELECTED')
        results.append(record)
    failed={r['proposal_id'] for r in results if r['status']=='FAILED_IN_CI'}
    for row in rows:
        if row['approved']=='Y' and row['proposal_id'] in failed:row['approved']='FAILED_IN_CI'
    write_rows(output/'p2_marker_proposals_approved.csv',rows,list(rows[0]))
    write_rows(output/'p2_ci_marker_results.csv',results,FIELDS)
    write_rows(output/'p2_ci_marker_failures.csv',[r for r in results if r['status']=='FAILED_IN_CI'],FIELDS)
    summary=dict(approved_rows=len(approved),frozen_v10_claims_verified=True,
                 current_binding_statuses=dict(Counter(r['current_binding_status'] for r in results)),
                 statuses=dict(Counter(r['status'] for r in results)),
                 claims_modified=False,markers_or_pages_repaired=False,http_requests=0)
    (output/'p2_ci_marker_summary.json').write_text(json.dumps(summary,indent=2)+'\n',encoding='utf8')
    print(json.dumps(summary))
    if failed:
        raise ValueError('COMPANY_MARKER_PDF_VALIDATION_FAILED: '+','.join(sorted(failed)))


if __name__=='__main__':main()
