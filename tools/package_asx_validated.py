"""Package reviewed values, candidate dispositions and gaps; no raw PDFs or SQLite."""
import argparse,csv,json,shutil
from pathlib import Path
from collections import Counter
from au_ree_v2.store import filehash,digest

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('audit-dir','technical-dir','baseline','updated','analysis','review-ledger','out'):p.add_argument('--'+key,required=True)
    a=p.parse_args();audit=Path(a.audit_dir);tech=Path(a.technical_dir);baseline=Path(a.baseline);updated=Path(a.updated);analysis=Path(a.analysis);out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    summary=json.loads((updated/'summary.json').read_text('utf8'));increment=json.loads((analysis/'field_increment.json').read_text('utf8'));candidates=json.loads((analysis/'candidate_validation.json').read_text('utf8'))
    if summary['review_ledger_sha256']!=filehash(a.review_ledger):raise ValueError('REVIEW_LEDGER_CHANGED')
    if increment['updated_csv_sha256']!=filehash(updated/'專案總表.csv'):raise ValueError('SUMMARY_CHANGED_AFTER_COMPARISON')
    old=json.loads((audit/'retest.json').read_text('utf8'))['outcomes'];new=json.loads((tech/'downloads.json').read_text('utf8'))
    discovery=json.loads((tech/'archive_discovery.json').read_text('utf8'));native=json.loads((tech/'native_inventory.json').read_text('utf8'))
    for directory,rows in [(audit,old),(tech,new)]:
        for row in rows:
            if row['status']=='PDF_ACQUIRED' and filehash(directory/row['path'])!=row['document_sha256']:raise ValueError('RAW_DOCUMENT_HASH_MISMATCH')
    for row in native:
        if filehash(tech/row['native_text_path'])!=row['native_text_sha256']:raise ValueError('NATIVE_TEXT_HASH_MISMATCH')
    with (analysis/'field_changes.csv').open(encoding='utf-8-sig') as f:changes=list(csv.DictReader(f))
    numeric_new=0
    for row in changes:
        if row['status']=='NEWLY_FILLED':
            try:float(row['after']);numeric_new+=1
            except ValueError:pass
    with (updated/'missing_fields.csv').open(encoding='utf-8-sig') as f:gaps=list(csv.DictReader(f))
    with (updated/'專案總表.csv').open(encoding='utf-8-sig') as f:rows=list(csv.DictReader(f))
    evaluation=dict(version='asx-reviewed-summary-evaluation-v1',source_cutoff=summary['cutoff'],acquired_through=summary['acquired_through'],
        archive_issuer_codes=len(discovery['codes']),archive_pages_attempted=len(discovery['receipts']),discovered_technical_keyword_urls=len(discovery['documents']),
        technical_download_attempts=len(new),technical_download_successes=sum(r['status']=='PDF_ACQUIRED' for r in new),
        technical_download_failures=dict(Counter(r.get('failure_status','DEFERRED') for r in new if r['status']!='PDF_ACQUIRED')),
        newly_attempted_urls_vs_initial24=sum(r['url'] not in {d['url'] for d in old} for r in new),
        combined_distinct_urls=len({r['url'] for r in old+new}),combined_distinct_pdf_hashes=len({r['document_sha256'] for r in old+new if r['status']=='PDF_ACQUIRED'}),
        technical_native_pages=sum(r['physical_pages'] for r in native),
        original_candidates=candidates,review_groups=len(summary['validated_reviews']),
        reviewed_pdf_hashes=len({r['source_sha256'] for r in summary['validated_reviews']}),
        validated_resource_observations=sum(r['new_observations'] for r in summary['validated_reviews']),
        validated_forecast_parameters=sum(r['forecast_parameters'] for r in summary['validated_reviews']),
        increment=increment,newly_filled_numeric_cells=numeric_new,
        filled_cells=sum(v!='' for row in rows for v in row.values()),total_cells=len(rows)*len(rows[0]),
        gap_reasons=dict(Counter(r['reason'] for r in gaps)),project_summary=summary,
        interpretation=['TITLE_KEYWORD_DOWNLOADS_INCLUDE_UNRELATED_ASSETS;ONLY_EXPLICIT_SOURCE_REVIEWS_PROMOTED',
        'SOURCE_REVIEW_INCLUDES_RENDERED_TRANSCRIPTION_AND_ARITHMETIC_CHECKS;NOT_INDEPENDENT_APPROVAL',
        '691_CANDIDATES_CLASSIFIED;NOT_ALL_APPROVED_OR_PROMOTED',
        'NATIVE_OR_RENDERED_TABLES_REEXTRACTED_WHERE_ORIGINAL_CANDIDATES_WERE_INCOMPLETE',
        'RESOURCE_REAFFIRMATION_DATES_AND_INTERVALS_ARE_NOT_IMPUTED_POINT_ESTIMATE_DATES',
        'FORMAL_C1_AND_MCDA_NOT_RECOMPUTED;ORIGINAL_DATABASE_AND_RESULTS_UNCHANGED'])
    (out/'evaluation.json').write_text(json.dumps(evaluation,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    for name in ('專案總表.csv','field_provenance.csv','missing_fields.csv','census_inventory.csv','summary.json'):shutil.copyfile(updated/name,out/name)
    for name in ('candidate_validation.csv','candidate_validation.json','field_changes.csv','field_increment.json'):shutil.copyfile(analysis/name,out/name)
    shutil.copyfile(baseline/'專案總表.csv',out/'專案總表_補值前.csv');shutil.copyfile(a.review_ledger,out/'source_reviews.json')
    for src,dst in [('downloads.json','technical_downloads.json'),('archive_discovery.json','technical_discovery.json'),('native_inventory.json','technical_native_inventory.json')]:shutil.copyfile(tech/src,out/dst)
    print(json.dumps(dict(newly_filled_cells=increment['newly_filled_cells'],newly_filled_numeric_cells=numeric_new,remaining_blank_cells=increment['remaining_blank_cells'],reviewed_pdf_hashes=evaluation['reviewed_pdf_hashes']),ensure_ascii=False))

if __name__=='__main__':main()
