"""Fetch explicitly located ASX originals with immutable URL/SHA receipts."""
import argparse,hashlib,json
from pathlib import Path
from au_ree_v2.asx import fetch_pdf
from au_ree_v2.acquisition import failure_details
from au_ree_v2.store import filehash

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--requests',required=True);p.add_argument('--out',required=True);a=p.parse_args()
    out=Path(a.out);(out/'data/snapshots').mkdir(parents=True,exist_ok=True)
    target=out/'downloads.json';rows=json.loads(target.read_text('utf8')) if target.exists() else []
    done={r['url'] for r in rows}
    def archive(raw,url,suffix):
        sha=hashlib.sha256(raw).hexdigest();path=out/'data/snapshots'/(sha+suffix)
        if not path.exists():path.write_bytes(raw)
        if filehash(path)!=sha:raise ValueError('SNAPSHOT_HASH_MISMATCH')
        return sha
    for request in json.loads(Path(a.requests).read_text('utf8'))['documents']:
        if request['url'] in done:continue
        row=dict(request)
        try:
            raw,_,receipt=fetch_pdf(row['url'],archive=archive);sha=archive(raw,receipt['resolved_url'],'.pdf')
            row.update(status='PDF_ACQUIRED',document_sha256=sha,path='data/snapshots/'+sha+'.pdf',asx_acquisition=receipt)
        except Exception as e:row.update(status='UNAVAILABLE',**failure_details(e))
        rows.append(row);target.write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
        print(row['status'],row['title'],flush=True)

if __name__=='__main__':main()
