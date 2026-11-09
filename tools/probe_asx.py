"""Bounded live A/B check in a separate artifact store, without canonical ingestion."""
import argparse
import hashlib
import json
import subprocess
import time
from datetime import datetime,timezone
from pathlib import Path
from au_ree_v2.acquisition import request,failure_details
from au_ree_v2.asx import is_asx_document,HOSTS,VERSION
from au_ree_v2.discovery import discover
from au_ree_v2.store import filehash


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cases',default='config/asx_probe_cases.json')
    parser.add_argument('--out',default='work/asx-probe')
    args=parser.parse_args()
    cases=json.loads(Path(args.cases).read_text(encoding='utf8'))['cases']
    if not 1<=len(cases)<=4 or any(not is_asx_document(c['url']) for c in cases):
        raise ValueError('Require 1 to 4 public ASX document URLs')
    root=Path(args.out).resolve();root.mkdir(parents=True,exist_ok=True)
    # An existing research store is never accepted as a probe output.
    marker=root/'ASX_PROBE_ONLY'
    if not marker.exists() and any(root.iterdir()):raise ValueError('Require an empty or existing ASX probe directory')
    marker.write_text(VERSION,encoding='utf8')
    (root/'data/snapshots').mkdir(parents=True,exist_ok=True)
    manifest=root/'data/manifest.json'
    if not manifest.exists():manifest.write_text('{"snapshots":[]}',encoding='utf8')
    baseline=[]
    for case in cases:
        start=time.monotonic()
        try:
            raw,headers=request(case['url'],max_bytes=40*1024*1024,allowed_hosts=HOSTS,max_attempts=1,min_interval=1.)
            suffix='.pdf' if raw.startswith(b'%PDF-') else '.html'
            sha=hashlib.sha256(raw).hexdigest()
            path=root/'data/snapshots'/(sha+suffix)
            if not path.exists():path.write_bytes(raw)
            if filehash(path)!=sha:raise ValueError('BASELINE_SNAPSHOT_HASH_MISMATCH')
            baseline.append(dict(key=case['key'],url=case['url'],
                status='PDF_MAGIC_ONLY' if suffix=='.pdf' else 'TERMS_INTERSTITIAL' if b'announcementTerms.do' in raw else 'NON_PDF',
                sha256=sha,bytes=len(raw),path=path.relative_to(root).as_posix(),
                elapsed_seconds=round(time.monotonic()-start,3)))
        except Exception as exc:baseline.append(dict(key=case['key'],url=case['url'],status='UNAVAILABLE',**failure_details(exc)))
    config=dict(asx_public_acquisition=True,max_documents_per_seed=1,
        seeds=[dict(key=c['key'],url=c['url'],allowed_hosts=list(HOSTS),authority='EXCHANGE') for c in cases])
    start=time.monotonic();result=discover(root,config)
    elapsed=round(time.monotonic()-start,3)
    repeat=discover(root,config)
    snapshots=json.loads(manifest.read_text(encoding='utf8'))['snapshots']
    verified=all(filehash(root/s['path'])==s['sha256'] for s in snapshots)
    repo=Path(__file__).resolve().parents[1]
    commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=repo,text=True).strip()
    code_sha=hashlib.sha256(json.dumps({p.relative_to(repo).as_posix():filehash(p) for p in sorted((repo/'src').rglob('*.py'))},sort_keys=True).encode()).hexdigest()
    report=dict(version=VERSION,acquired_at=datetime.now(timezone.utc).isoformat(),base_commit=commit,
        source_content_sha256=code_sha,baseline=baseline,experimental=result,experimental_elapsed_seconds=elapsed,
        repeat_sources=repeat['sources'],all_snapshot_hashes_verified=verified,
        limitation='BOUNDED_SELECTED_URLS; NO_GENERAL_CAPTCHA_BYPASS_OR_EXHAUSTIVE_ARCHIVE_COVERAGE; NO_SCIENTIFIC_ADMISSION',
        raw_store=str(root),canonical_store_modified=False)
    (root/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps(dict(report=str(root/'report.json'),baseline=[b['status'] for b in baseline],
        experimental=[s['status'] for s in result['sources']],repeat=[s['status'] for s in repeat['sources']],
        all_snapshot_hashes_verified=verified),ensure_ascii=False))


if __name__=='__main__':main()
