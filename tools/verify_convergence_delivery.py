"""Verify the engineering delivery using local receipts and immutable baselines."""
import argparse
import json
import xml.etree.ElementTree as ET
from pathlib import Path
from au_ree_v2.iteration_review import audit_summary
from au_ree_v2.review_storage import restore_review,sha
from au_ree_v2.store import filehash
from verify_engineering_baseline import verify

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'results/convergence-codebook'


def tests(path):
    root=ET.parse(path).getroot()
    suites=list(root.iter('testsuite'))
    assert suites and all(not int(s.get(k,'0')) for s in suites for k in ('failures','errors','skipped')), 'TESTS_NOT_ALL_PASSED'
    cases=list(root.iter('testcase'))
    unique={(t.get('classname'),t.get('name')) for t in cases}
    # pytest counts successful subtests in testsuite.tests without emitting
    # separate testcase nodes. Counting only XML elements would underreport them.
    total=sum(int(s.get('tests','0')) for s in suites)
    return dict(test_methods=len(unique),subtests=total-len(unique),cases=total,failures=0,errors=0,skipped=0,
                report_sha256=filehash(path)),unique


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rebuild-prefix',required=True)
    args=parser.parse_args();prefix=Path(args.rebuild_prefix)
    value=verify();csvs=('專案總表.csv','field_provenance.csv','missing_fields.csv','census_inventory.csv')
    rebuilt={}
    for kind in ('base52','53'):
        a=prefix.with_name(prefix.name+'-a-'+kind);b=prefix.with_name(prefix.name+'-b-'+kind)
        hashes={n:filehash(a/n) for n in csvs}
        assert hashes=={n:filehash(b/n) for n in csvs},'INDEPENDENT_EXPORT_MISMATCH'
        audit_summary(a);audit_summary(b)
        if kind=='53':
            assert hashes=={n:filehash(ROOT/'results/asx-current'/n) for n in csvs},'CURRENT_EXPORT_MISMATCH'
            verify(a);verify(b)
        rebuilt[kind]=hashes
    book=json.loads((ROOT/'config/classification_codebook.json').read_text('utf8'))
    assert book['status']=='DRAFT' and book['approved_by'] is None and book['approved_date'] is None,'UNAUTHORIZED_CODEBOOK_APPROVAL'
    reports={};all_names={}
    for name in ('task1-tests.xml','task2-tests.xml','task3-tests.xml','task4-tests.xml','affected-tests.xml','all-tests.xml'):
        reports[name],all_names[name]=tests(OUT/name)
    _,old_names=tests(ROOT/'results/asx-full-scope-2026-11-10/round-20-report/tests.xml')
    assert len(old_names)==405 and old_names<=all_names['affected-tests.xml'],'ORIGINAL_405_NOT_ALL_REPLAYED'
    # The full suite uses byte-identical test copies; module paths gain an overlay prefix.
    normalized=lambda items:{('.'.join(c.split('.')[-2:]),n) for c,n in items}
    assert normalized(all_names['affected-tests.xml'])<=normalized(all_names['all-tests.xml']),'FULL_SUITE_MISSING_AFFECTED_TESTS'
    final_methods=normalized(all_names['all-tests.xml'])|normalized(all_names['task4-tests.xml'])
    rejudgment=json.loads((OUT/'historical_rejudgment.json').read_text('utf8'))
    assert [r['rejudged_stopping_rule']['newly_filled_cells'] for r in rejudgment['rounds']]==[4,0]
    assert [r['rejudged_stopping_rule']['consecutive_zero_rounds'] for r in rejudgment['rounds']]==[0,1]
    assert all(r['rejudged_stopping_rule']['decision']=='CONTINUE' for r in rejudgment['rounds'])
    storage=json.loads((OUT/'review_storage_validation.json').read_text('utf8'))
    for example in storage['examples']:
        path=ROOT/example['path'];raw=restore_review(path)
        assert sha(raw)==example['full_sha256']
        assert restore_review(path,verify_snapshot=False)==raw,'DELTA_CHAIN_REQUIRES_NONANCHOR_SNAPSHOT'
        if example['kind']=='historical':
            original=ROOT/f"results/asx-full-scope-2026-11-10/round-{example['round']}-report/audit/cycle_review.json"
            assert raw==original.read_bytes(),'HISTORICAL_RESTORATION_NOT_BYTE_IDENTICAL'
    value.update(version='convergence-codebook-engineering-delivery-v1',new_sources_or_data_rounds=0,
        codebook_status='DRAFT',original_405_test_methods_passed=True,tests=reports,
        final_test_method_union=len(final_methods),
        supplementary_final_packaging_methods=len(final_methods-normalized(all_names['all-tests.xml'])),
        independent_rebuilds=2,four_csv_hashes_identical=True,base52_and_53_hashes=rebuilt,
        current_projection_matches_rebuild=True,all_delta_chains_restore_original_bytes=True,
        coverage=json.loads((ROOT/'results/asx-current/summary.json').read_text('utf8'))['blank_coverage'],
        projection_config_hashes={n:filehash(ROOT/'config'/n) for n in ('classification_codebook.json','blank_classification.json')},
        implementation_hashes={p.relative_to(ROOT).as_posix():filehash(p) for base in ('src','tools','config','tests')
            for p in sorted((ROOT/base).rglob('*')) if p.is_file() and p.suffix in ('.py','.json')},
        limitations='Local tests and approved-evidence replay, not remote CI or new data collection. Research rows are not independent mines; Yttria/Mt Stirling resources must not be summed. STOP is not source exhaustion.')
    (OUT/'verification.json').write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps({k:v for k,v in value.items() if k not in ('implementation_hashes','base52_and_53_hashes')},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
