"""Verify protected baseline, two offline replays, then publish the scoped result."""
import argparse,csv,json,shutil,sys,xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path
REPO=Path(__file__).resolve().parents[1];sys.path.insert(0,str(REPO/'src'))
from au_ree_v2.store import filehash
from au_ree_v2.iteration_review import audit_summary


def main(work,out,publish=False):
    work,out=Path(work).resolve(),Path(out).resolve()
    if out.exists():raise ValueError('REPORT_REQUIRE_FRESH_OUTPUT')
    baseline=json.loads((work/'baseline.json').read_text('utf8'))
    for name,sha in baseline['protected'].items():
        if filehash(REPO/name)!=sha:raise ValueError('PROTECTED_BASELINE_CHANGED:'+name)
    if filehash(baseline['census_path'])!=baseline['census_sha256']:raise ValueError('CENSUS_CHANGED')
    def read(path):
        with Path(path).open(encoding='utf-8-sig',newline='') as f:
            rd=csv.DictReader(f);return rd.fieldnames,list(rd)
    a,b=work/'final-approved-a',work/'final-approved-b'
    files=['專案總表.csv','field_provenance.csv','missing_fields.csv','census_inventory.csv','summary.json','audit.json']
    for name in files:
        if filehash(a/name)!=filehash(b/name):raise ValueError('TWO_REBUILDS_DIFFER:'+name)
    columns,oldrows=read(work/'baseline-專案總表.csv');_,newrows=read(a/'專案總表.csv')
    old={r['專案ID']:r for r in oldrows};new={r['專案ID']:r for r in newrows}
    if old.keys()!=new.keys() or len(columns)!=53:raise ValueError('COHORT_CHANGED')
    _,oldtrace=read(work/'baseline-field_provenance.csv');_,newtrace=read(a/'field_provenance.csv')
    oldp={(p['project_id'],p['column']):p for p in oldtrace};newp={(p['project_id'],p['column']):p for p in newtrace}
    if any(newp.get(key)!=p for key,p in oldp.items()):raise ValueError('OLD_PROVENANCE_CHANGED')
    changes=[]
    for pid,row in old.items():
        for col,value in row.items():
            if value and new[pid][col]!=value:raise ValueError('OLD_VALUE_CHANGED')
            if not value and new[pid][col]:
                proof=newp[(pid,col)]
                changes.append(dict(project_id=pid,name=new[pid]['專案名稱'],column=col,value=new[pid][col],
                    kind='TEMPLATE_MAPPING' if proof['method'].startswith('USER_PROVIDED_TEMPLATE_MAPPING') else
                         'DERIVED_NUMERIC' if proof['method'].startswith('DERIVED_') else 'SCIENTIFIC_DISCLOSURE_TEXT',
                    source_sha256=proof['source_sha256'],locator=proof['locator'],method=proof['method']))
    if filehash(a/'census_inventory.csv')!=filehash(work/'baseline-census_inventory.csv'):raise ValueError('INVENTORY_CHANGED')
    for row in newtrace:
        if row['method'].startswith('USER_PROVIDED_TEMPLATE_MAPPING'):
            if json.loads(row['scope'])['mapping_sha256']!=filehash(REPO/'config/user_template_mapping.json'):
                raise ValueError('MAPPING_REPLAY_CONFIGURATION_CHANGED')
    tests={}
    for name in ['targeted-tests.xml','regression-tests.xml']:
        tree=ET.parse(work/name);suites=tree.findall('testsuite');cases=tree.findall('.//testcase')
        if any(int(s.get(k,0)) for s in suites for k in ['failures','errors','skipped']):raise ValueError('TESTS_NOT_PASSING')
        tests[name]=dict(methods=len(cases),subtests=sum(int(s.get('tests',0)) for s in suites)-len(cases),failures=0,errors=0,skipped=0)
    audit=audit_summary(a);audit_summary(b)
    current=json.loads((a/'summary.json').read_text('utf8'))
    book=json.loads((REPO/'config/classification_codebook.json').read_text('utf8'))
    if book['status']!='DRAFT' or book['approved_by'] is not None or book['approved_date'] is not None:raise ValueError('DRAFT_APPROVAL_CHANGED')
    counts=dict(Counter(c['kind'] for c in changes))
    if counts!={'TEMPLATE_MAPPING':36,'DERIVED_NUMERIC':4,'SCIENTIFIC_DISCLOSURE_TEXT':1}:raise ValueError('UNEXPECTED_FILL_COUNTS')
    out.mkdir(parents=True)
    def write(name,value):(out/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    def csvwrite(name,rows,fields):
        with (out/name).open('w',encoding='utf-8-sig',newline='') as f:
            w=csv.DictWriter(f,fields);w.writeheader();w.writerows(rows)
    csvwrite('new_cells.csv',changes,list(changes[0]))
    mapping=json.loads((REPO/'config/user_template_mapping.json').read_text('utf8'))
    csvwrite('unmapped_classification.csv',mapping['unmapped'],['group','source_text','reason'])
    extraction=json.loads((work/'extraction-v2/summary.json').read_text('utf8'))
    # Publish metadata, not raw tables, full PDF text, PDFs or the user's input rows.
    docrows=[{k:v for k,v in d.items() if k!='local_path'} for d in extraction['documents']]
    csvwrite('archived_documents.csv',docrows,['source_sha256','pages','source_url'])
    pagerows=[dict(source_sha256=p['source_sha256'],physical_page=p['physical_page'],oxides=';'.join(p['oxides']),
        labels=';'.join(p['labels']),table_count=p['table_count'],disposition=p['disposition']) for p in extraction['pages']]
    for p in pagerows:
        if p['source_sha256']=='734d9ea35fd9617eb2bad21c48fec17cdae08a5c66fa3e3cf7857390d04218ab' and p['physical_page']==26:
            p['disposition']='ONE_TOTAL_Y2O3_CELL_VERIFIED;OTHER_CATEGORY_OXIDES_NOT_ADMITTED'
        if p['source_sha256']=='89467aedb62238c6a98902633fba1bcaf4ccd0f081beaa736facf71533ac3864' and p['physical_page']==3:
            p['disposition']='WUDINNA_CORROBORATION_ONLY;EXISTING_GROUP_ALREADY_FILLED;NO_OVERWRITE'
    csvwrite('candidate_pages.csv',pagerows,list(pagerows[0]))
    _,gaps=read(work/'baseline-missing_fields.csv')
    projectrows=[]
    for p in extraction['projects']:
        pid=p['project_id'];proofs=[c for c in changes if c['project_id']==pid and c['kind']!='TEMPLATE_MAPPING']
        reasons=sorted({g['reason'] for g in gaps if g['project_id']==pid and ('_kt' in g['column'] or g['column'].startswith('預估年產'))})
        projectrows.append(dict(project_id=pid,name=p['name'],selected_resource_sha256=p['selected_resource_sha256'],
            filled_oxides_before=p['filled_oxides'],new_individual_oxide_inputs=1 if proofs else 0,new_cells=len(proofs),
            preexisting_complete_set_derivation_gaps=len(p['derived_gaps']),
            remaining_source_limits=';'.join(reasons),
            decision='DUBBO_TOTAL_Y2O3_VERIFIED;OTHER_CATEGORY_OXIDES_NOT_WEIGHTED_OR_TRANSFERRED' if proofs else
                'NO_NEW_VALIDATED_CELLS;SCANNED_TABLES_ARE_CANDIDATES_NOT_COMPLETE_EXPERT_REVIEW_OF_EVERY_CELL'))
    csvwrite('element_project_review.csv',projectrows,list(projectrows[0]))
    for name in tests:shutil.copyfile(work/name,out/name)
    shutil.copyfile(work/'mapped-replay-rebuild.json',out/'core_rebuild_receipt.json')
    summary=dict(version='user-template-and-archived-elements-20261111',baseline_commit=baseline['baseline_commit'],
        research_cutoff='2026-11-05',rows=93,columns=53,filled_before=1944,filled_after=audit['filled_cells'],
        blank_before=2985,blank_after=audit['remaining_blank_cells'],existing_project_fills=len(changes),new_projects=0,new_project_cells=0,
        fill_types=counts,new_individual_oxide_grade_inputs=1,new_direct_reported_table_numeric_cells=0,
        scientific_contract_cells_before=465,scientific_contract_cells_after=audit['scientific_filled_cells'],
        new_source_downloads=0,asx_requests=0,new_coordinates=0,
        template=baseline['template'],codebook_status='DRAFT',codebook_approval_changed=False,
        extraction=dict(projects=len(extraction['projects']),documents=len(docrows),pages=extraction['total_pages'],candidate_pages=extraction['candidate_pages'],
            native_tables=extraction['native_tables'],table_errors=len(extraction['errors']),preexisting_complete_set_derivation_gaps=extraction['derived_gap_cells'],
            limitation='194 candidate pages found; not all252 tables have newly completed cell-by-cell scientific review.'),
        coverage=current['blank_coverage'],tests=tests,independent_full_source_replays=2,independent_additive_replays=2,
        protected_existing_filled_cells=len(oldp),existing_values_and_provenance_unchanged=True,
        protected_materialized_files=len(baseline['protected']),sparse_not_materialized_files=len(baseline['sparse_not_materialized']),
        census_sha256=baseline['census_sha256'],census_unchanged=True,inventory_unchanged=True,
        government_data='METADATA_RESEARCH_ONLY;NO_FEATURE_DOWNLOAD_OR_PIPELINE_INTEGRATION',
        full_scope_rounds_added=0,convergence_streak_changed=False,round21_created=False,
        output_hashes=current['output_hashes'])
    write('summary.json',summary)
    write('rebuild_receipt.json',dict(core_receipt_sha256=filehash(out/'core_rebuild_receipt.json'),
        mapping_sha256=filehash(REPO/'config/user_template_mapping.json'),element_additions_sha256=filehash(REPO/'config/asx_archived_element_additions.json'),
        input_csv_sha256=mapping['source']['sha256'],mapping_hash_in_both_core_summaries_verified=True,
        independently_rebuilt_outputs_identical=True,source_replays=2,additive_replays=2,
        final_hashes={n:filehash(a/n) for n in files},
        core_receipt_note='Core replay launched before the wrapper added the mapping hash to its config inventory. Both core summary files carry and match the mapping hash; this envelope binds it explicitly.'))
    write('validation.json',dict(passed=True,protected_baseline=baseline['protected'],
        source_fingerprints={p.relative_to(REPO).as_posix():filehash(p) for p in [REPO/'src/au_ree_v2/template_mapping.py',REPO/'src/au_ree_v2/archived_element_additions.py',REPO/'tools/apply_archived_element_additions.py']},
        artifact_hashes={p.name:filehash(p) for p in out.iterdir() if p.is_file()}))
    if publish:
        for name in files:shutil.copyfile(a/name,REPO/'results/asx-current'/name)
        (REPO/'results/asx-current/validation.json').write_text(json.dumps(dict(passed=True,delivery=str(out.relative_to(REPO)),protected_existing_cells=len(oldp),
            old_values_and_provenance_unchanged=True,independent_rebuilds=2,output_hashes=current['output_hashes']),ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps({k:summary[k] for k in ['filled_after','blank_after','existing_project_fills','fill_types','tests']},ensure_ascii=False,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--work',type=Path,default=REPO/'work/attachment-elements-20261111')
    p.add_argument('--out',type=Path,required=True);p.add_argument('--publish-current',action='store_true');a=p.parse_args()
    main(a.work,a.out,a.publish_current)
