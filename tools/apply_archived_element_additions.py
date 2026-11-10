"""Verified additive projection over a separately rebuilt 53-column summary."""
import argparse,csv,json,shutil,sqlite3,sys
from pathlib import Path
REPO=Path(__file__).resolve().parents[1];sys.path.insert(0,str(REPO/'src'))
from au_ree_v2.archived_element_additions import verify_single_oxide
from au_ree_v2.blank_classification import load_blank_rules,classify_blanks
from au_ree_v2.iteration_review import audit_summary
from au_ree_v2.store import canonical,filehash


def apply(before,out,ledger,database):
    before,out,ledger,database=map(Path,(before,out,ledger,database))
    if out.exists():raise ValueError('ADDITIONS_REQUIRE_FRESH_OUTPUT')
    def read(name):
        with (before/name).open(encoding='utf-8-sig',newline='') as f:
            reader=csv.DictReader(f);rows=list(reader);return reader.fieldnames,rows
    columns,rows=read('專案總表.csv');tracefields,trace=read('field_provenance.csv');missingfields,missing=read('missing_fields.csv')
    if len(columns)!=53:raise ValueError('ADDITIONS_REQUIRE_53_COLUMNS')
    cfg=json.loads(ledger.read_text('utf8'))
    if cfg['version']!='archived-element-additions-v1':raise ValueError('ADDITIONS_LEDGER_VERSION')
    roots=json.loads((REPO/'config/asx_local_asset_roots.json').read_text('utf8'))['roots'];roots={k:(REPO/v).resolve() for k,v in roots.items()}
    olddb=filehash(database);receipts=[]
    with sqlite3.connect(database.resolve().as_uri()+'?mode=ro',uri=True) as db:
        db.row_factory=sqlite3.Row
        for entry in cfg['reviews']:
            row=next(r for r in rows if r['專案ID']==entry['project_id'])
            if entry.get('mode')!='SAME_SELECTED_PDF_SINGLE_OXIDE':raise ValueError('ADDITIONS_UNSUPPORTED_MODE')
            for fill in verify_single_oxide(row,trace,db,entry,roots):
                row[fill['column']]=str(fill['value']);p=dict.fromkeys(tracefields,'')
                p.update({k:fill[k] for k in fill if k in p});p.update(project_id=entry['project_id'],value=str(fill['value']),
                    effective_date=entry['effective_date'],effective_date_role='INHERITED_CANONICAL_RESOURCE_DATE;NATIVE_PDF_YEAR_ONLY' if entry.get('mode') else 'RESOURCE_EFFECTIVE_DATE',date_precision='YEAR' if entry.get('mode') else 'DAY',
                    review_ids=canonical([entry['review_id']]),acquired_through=cfg['acquired_through'],publication_date=entry['publication_date'],
                    source_kind='pdf' if entry.get('mode') else 'html',review_methods=canonical(['ARCHIVED_NATIVE_SAME_SELECTED_RESOURCE_TOTAL_ROW']))
                trace.append(p);receipts.append(dict(project_id=entry['project_id'],**fill))
    if filehash(database)!=olddb:raise ValueError('ADDITIONS_DATABASE_CHANGED')
    keys={(f['project_id'],f['column']) for f in receipts};missing=[m for m in missing if (m['project_id'],m['column']) not in keys]
    summary=json.loads((before/'summary.json').read_text('utf8'))
    summary['blank_coverage']=classify_blanks(rows,missing,trace,load_blank_rules(REPO/'config/blank_classification.json'))
    out.mkdir(parents=True)
    for name,values,fields in [('專案總表.csv',rows,columns),('field_provenance.csv',trace,tracefields),('missing_fields.csv',missing,missingfields)]:
        with (out/name).open('w',encoding='utf-8-sig',newline='') as f:
            w=csv.DictWriter(f,fields);w.writeheader();w.writerows(values)
    shutil.copyfile(before/'census_inventory.csv',out/'census_inventory.csv')
    summary.update(filled_counts={c:sum(r[c]!='' for r in rows) for c in columns},
        archived_element_additions=dict(ledger_sha256=filehash(ledger),new_raw_individual_oxide_cells=0,derived_numeric_cells=sum(f['method'].startswith('DERIVED_') for f in receipts),new_text_cells=sum(not f['method'].startswith('DERIVED_') for f in receipts),reviews=receipts),
        output_hashes={name:filehash(out/name) for name in ['專案總表.csv','field_provenance.csv','missing_fields.csv','census_inventory.csv']})
    (out/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    (out/'audit.json').write_text(json.dumps(audit_summary(out),ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    return summary


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--before',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--ledger',type=Path,default=REPO/'config/asx_archived_element_additions.json')
    p.add_argument('--database',type=Path,default=REPO.parent/'AU_REE_V2/work/phase22/verified-performance-v3/isolated-round-0/after/canonical.sqlite')
    a=p.parse_args();apply(a.before,a.out,a.ledger,a.database)
