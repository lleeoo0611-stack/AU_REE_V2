"""Package existing rounds 19/20 as new difference-chain examples; history stays read-only."""
import json
from pathlib import Path
from au_ree_v2.review_storage import encoded,restore_review,sha,write_review

ROOT=Path(__file__).resolve().parents[1]


if __name__=='__main__':
    results=[]
    for kind in ('historical','rejudged'):
        previous=None
        for number in (19,20):
            source=(ROOT/f'results/asx-full-scope-2026-11-10/round-{number}-report/audit/cycle_review.json'
                    if kind=='historical' else ROOT/f'work/convergence-engineering/round-{number}-rejudged-full.json')
            raw=source.read_bytes();report=json.loads(raw)
            path=ROOT/f'results/convergence-codebook/{kind}-{number}/cycle_review.json'
            receipt=write_review(report,path,previous,original_bytes=raw)
            assert sha(restore_review(path))==sha(raw)
            # Prove delta-only restoration using just the initial anchor snapshot.
            assert restore_review(path,verify_snapshot=False)==raw
            results.append(dict(kind=kind,round=number,path=str(path.relative_to(ROOT)),**receipt))
            previous=path
    out=ROOT/'results/convergence-codebook/review_storage_validation.json'
    out.write_text(json.dumps(dict(version='review-storage-examples-v1',historical_reports_modified=False,
                                 all_restored_original_sha256=True,examples=results),ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(out.read_text('utf8'))
