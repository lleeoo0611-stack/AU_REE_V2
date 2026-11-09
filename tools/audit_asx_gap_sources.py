"""Verify search-review source bindings without promoting additional numbers."""
import argparse,csv,json,re
from pathlib import Path
from au_ree_v2.store import filehash

def audit(config,assets,out):
    import pymupdf
    cfg=json.loads(Path(config).read_text('utf8'));rows=[];native=[]
    captured={}
    for name,root in assets.items():
        root=Path(root).resolve();m=root/'data/manifest.json';d=root/'downloads.json';r=root/'retest.json'
        if m.exists():records=json.loads(m.read_text('utf8'))['snapshots']
        elif d.exists():records=json.loads(d.read_text('utf8'))
        elif r.exists():records=json.loads(r.read_text('utf8'))['outcomes']
        else:raise ValueError('AUDIT_CAPTURE_RECEIPT_MISSING')
        captured[name]={(x['url'],x.get('sha256') or x.get('document_sha256')) for x in records if x.get('kind')=='pdf' or x.get('status')=='PDF_ACQUIRED'}
    for review in cfg['reviews']:
        for s in review['sources']:
            root=Path(assets[s['asset_set']]).resolve();path=(root/s['path']).resolve()
            if root not in path.parents or filehash(path)!=s['sha256']:raise ValueError('AUDIT_SOURCE_HASH_OR_PATH_MISMATCH')
            if (s['url'],s['sha256']) not in captured[s['asset_set']]:raise ValueError('AUDIT_RECEIPT_BINDING_MISMATCH')
            with pymupdf.open(path) as d:
                for e in s['evidence']:
                    text=re.sub(r'\s+',' ',d[e['page']-1].get_text(sort=True)).casefold()
                    if not e['markers'] or any(re.sub(r'\s+',' ',m).casefold() not in text for m in e['markers']):raise ValueError('AUDIT_MARKER_MISMATCH:'+review['review_id'])
                native.append(dict(source_sha256=s['sha256'],physical_pages=len(d),source_url=s['url']))
            rows.append(dict(review_id=review['review_id'],project_id=review['project_id'],priority=review['priority'],
                decision=review['decision'],reason=review['reason'],source_sha256=s['sha256'],source_url=s['url'],
                pages=json.dumps([e['page'] for e in s['evidence']]),binding_status='SOURCE_HASH_RECEIPT_AND_PAGE_MARKERS_VERIFIED;INTERPRETATION_IS_SOURCE_REVIEW_NOT_INDEPENDENT_APPROVAL'))
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    with (out/'research_gap_reviews.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,list(rows[0]));w.writeheader();w.writerows(rows)
    (out/'research_gap_reviews.json').write_text(json.dumps(cfg,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    native=list({r['source_sha256']:r for r in native}.values())
    result=dict(config_sha256=filehash(config),review_groups=len(cfg['reviews']),source_references=len(rows),distinct_reviewed_pdf_hashes=len(native),
        physical_pages_in_distinct_reviewed_documents=sum(r['physical_pages'] for r in native),all_bindings_verified=True,
        output_hashes={n:filehash(out/n) for n in ['research_gap_reviews.csv','research_gap_reviews.json']})
    (out/'research_gap_validation.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf8')
    return result

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--config',required=True);p.add_argument('--asset-root',action='append',required=True);p.add_argument('--out',required=True);a=p.parse_args()
    print(json.dumps(audit(a.config,dict(x.split('=',1) for x in a.asset_root),a.out),indent=2))

if __name__=='__main__':main()
