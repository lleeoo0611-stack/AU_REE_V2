"""Re-extract selected, source-hashed resource PDFs without any network access."""
import argparse
import csv
import json
import sys
from pathlib import Path
REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO/'src'))
from au_ree_v2.element_reextraction import oxide_hints,derivation_gaps
from au_ree_v2.project_summary import ELEMENTS
from au_ree_v2.store import filehash


def run(out):
    import pymupdf
    out=Path(out)
    if out.exists():raise ValueError('REEXTRACTION_REQUIRES_FRESH_OUT')
    out.mkdir(parents=True)
    def read(name):return list(csv.DictReader((REPO/'results/asx-current'/name).open(encoding='utf-8-sig',newline='')))
    rows=read('專案總表.csv');trace=read('field_provenance.csv')
    targets=[r for r in rows if r['礦石蘊藏量_Mt'] and any(not next(v for k,v in r.items() if k.startswith(o+'_')) for o in ELEMENTS)]
    roots=json.loads((REPO/'config/asx_local_asset_roots.json').read_text('utf8'))['roots']
    roots={k:(REPO/v).resolve() for k,v in roots.items()}
    projects=[];documents={};pages=[];errors=[];planned={}
    ledger=json.loads((REPO/'config/asx_source_reviews.json').read_text('utf8'))['reviews']
    for row in targets:
        pid=row['專案ID']
        source=next(p for p in trace if p['project_id']==pid and p['column']=='礦石蘊藏量_Mt')
        sha=source['source_sha256']
        projects.append(dict(project_id=pid,name=row['專案名稱'],selected_resource_sha256=sha,
            filled_oxides=sum(bool(next(v for k,v in row.items() if k.startswith(o+'_'))) for o in ELEMENTS),
            derived_gaps=derivation_gaps(row)))
        matches=[root/'data/snapshots'/f'{sha}.pdf' for root in roots.values() if (root/'data/snapshots'/f'{sha}.pdf').is_file()]
        if matches:planned[sha]=(matches[0],source['source_url'])
        else:projects[-1]['selected_source_note']='SELECTED_RESOURCE_IS_NOT_LOCAL_PDF;RELATED_ARCHIVED_REPORTS_SCANNED_WITHOUT_SCOPE_TRANSFER'
        for review in ledger:
            if review['project_id']==pid and review['path'].lower().endswith('.pdf'):
                planned[review['source_sha256']]=(roots[review['asset_set']]/review['path'],review['url'])
    for sha,(path,url) in sorted(planned.items()):
        if filehash(path)!=sha:raise ValueError('SELECTED_PDF_HASH:'+sha)
        textpages=[];docout=out/sha;docout.mkdir()
        with pymupdf.open(path) as doc:
            documents[sha]=dict(source_sha256=sha,local_path=str(path),pages=len(doc),source_url=url)
            for index,page in enumerate(doc):
                text=page.get_text(sort=True);hints=oxide_hints(text)
                textpages.append(text)
                if not hints['extract_tables']:continue
                item=dict(source_sha256=sha,physical_page=index+1,**hints,
                    disposition='CANDIDATE_ONLY;RESOURCE_SCOPE_UNITS_VERSION_CUTOFF_CATEGORY_REO_BASIS_NOT_AUTO_VALIDATED')
                try:
                    finder=page.find_tables()
                    tables=[dict(index=i,bbox=list(t.bbox),cells=t.extract(),header=t.header.names) for i,t in enumerate(finder.tables)]
                    item['table_count']=len(tables)
                    if not tables:
                        # A text-position fallback retains exact words and bounds; it never repairs guessed columns.
                        item['fallback']='POSITIONED_WORDS_REQUIRES_REVIEW'
                    payload=dict(**item,text=text,tables=tables,words=page.get_text('words'))
                    (docout/f'page-{index+1}.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
                except Exception as exc:
                    item['table_count']=0;item['error']=type(exc).__name__;errors.append(item.copy())
                pages.append(item)
        (docout/'native-text.txt').write_text('\n\f\n'.join(textpages),encoding='utf8')
        print(sha,documents[sha]['pages'],'pages; candidate pages',sum(p['source_sha256']==sha for p in pages),flush=True)
    summary=dict(version='offline-archived-elements-v1',network_requests=0,projects=projects,
        documents=list(documents.values()),pages=pages,errors=errors,
        total_pages=sum(d['pages'] for d in documents.values()),candidate_pages=len(pages),
        native_tables=sum(p['table_count'] for p in pages),derived_gap_cells=sum(len(p['derived_gaps']) for p in projects),
        new_observations=0,limitation='Discovery only; no automatic promotion, cross-document match, missing-zero, sample-to-resource or current-status inference.')
    (out/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    return summary

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True)
    run(p.parse_args().out)
