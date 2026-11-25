"""Read-only paired page retrieval on a frozen Phase 22 Census publication."""
import argparse
import csv
import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path

import pymupdf

from tools.nlp_page_retrieval import FAMILIES, PageIndex, rule_pages

CONTROL_PROJECTS = {
    'AU-efff91a06cf344122d88': ('Lynas / Mt Weld', ('mt_weld_2024', 'asx_mtweld_mre202408'), r'\b(?:lynas|m(?:oun)?t[.\s]+weld)\b'),
    'AU-9bd8e5ed8408cd84d876': ('Northern Minerals / Browns Range', ('browns_range_2025', 'browns_wolverine_mre20250116'), r'\b(?:northern\s+minerals|browns\s+range)\b'),
}
K = 5


def records(path):
    with path.open(encoding='utf-8-sig', newline='') as stream:
        return list(csv.DictReader(stream))


def dump(path, value):
    path.write_bytes((json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode())


def checksum(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def project_alias(name):
    # Remove the Census scope note and the standard activity suffix, retain the place.
    return re.split(r'\s+[—–]|\s+(?:Li[–-]REE|REE[–-]|REE\b|Rare Earth|Critical Mineral|Project\b|Mineral Sands)', name, maxsplit=1, flags=re.I)[0].strip()


def targets(release):
    groups = {}
    for row in records(release / 'gap_review.csv'):
        if row['class'] not in ('E2', 'E3', 'E4') or row['action'] != 'REVIEW_CASE':
            continue
        pid, col, name = row['project_id'], row['column'], row['project_name']
        family = FAMILIES[col]
        if pid in CONTROL_PROJECTS or row['current_value']:
            raise ValueError('Invalid held-out target or nonempty cell')
        g = groups.setdefault((pid, family), dict(case_id=pid+'_'+family, project_id=pid,
                              project_name=name, field=family, columns=[]))
        if col in g['columns']:
            raise ValueError('Duplicate target')
        g['columns'].append(col)
    rows = [groups[k] for k in sorted(groups)]
    counts = {kind:sum(len(r['columns']) for r in rows if r['field']==kind) for kind in ('coordinate','deposit','stage')}
    if counts != {'coordinate':58, 'deposit':20, 'stage':12} or len({r['project_id'] for r in rows})!=39:
        raise ValueError('Expected the frozen 90-cell cohort')
    return rows


def document_splits(release, assets, cases, cache):
    # Only editions with an explicit within-cutoff admission by the shared ingress.
    keys = defaultdict(list)
    for row in records(release/'source_selection.csv'):
        if (row['kind']=='pdf' and row['cutoff_status']=='WITHIN_CUTOFF'
                and row['action'] in ('ASX_SOURCE_ADDED','EXACT_PHASE22_SOURCE')
                and row['version_status'] in ('PINNED_SHA_VERIFIED','RECEIPT_SHA_VERIFIED')):
            keys[row['source_sha256']].append(row['key'])
    aliases = {project_alias(r['project_name']).lower() for r in cases}
    dev_keys = {k:pid for pid,(_,ks,_) in CONTROL_PROJECTS.items() for k in ks}
    documents, sets = [], {'development':[], 'holdout':[]}
    cache.mkdir(parents=True, exist_ok=True)
    for sha, names in sorted(keys.items()):
        original = assets/sha
        if not re.fullmatch('[a-f0-9]{64}',sha) or checksum(original)!=sha:
            raise ValueError(f'Invalid original {sha}')
        text_cache=cache/(sha+'.json')
        # Private text cache is regenerated from verified bytes on each run.
        with pymupdf.open(original) as pdf:
            pages=[page.get_text(sort=True) for page in pdf]
        joined=' '.join(' '.join(pages).lower().split())
        owners = {dev_keys[k] for k in names if k in dev_keys}
        terms = sorted(pid for pid,(_,_,regex) in CONTROL_PROJECTS.items() if re.search(regex,joined))
        mentions = sorted(a for a in aliases if a and re.search(r'(?<!\w)'+re.escape(a)+r'(?!\w)',joined))
        if owners:
            split='development' if len(owners)==1 and owners==set(terms) and not mentions else 'quarantine'
        else:
            split='quarantine' if terms else 'holdout'
        documents.append(dict(sha256=sha, keys=sorted(names), split=split, pages=len(pages),
                              searchable_pages=sum(bool(t.strip()) for t in pages),
                              control_project_mentions=terms))
        if split in sets:
            sets[split].extend((sha,i,t) for i,t in enumerate(pages,1))
        dump(text_cache,pages)
    if not sets['development'] or not sets['holdout']:
        raise ValueError('Empty development or holdout source set')
    return documents, sets


def run(release, assets, out, cache):
    out.mkdir(parents=True, exist_ok=True)
    cases=targets(release)
    documents,pools=document_splits(release,assets,cases,cache)
    baseline=rule_pages(release)
    index=PageIndex(pools['holdout'])
    controls=PageIndex(pools['development'])
    dev_results={}
    for pid,(family,_,_) in CONTROL_PROJECTS.items():
        dev_results[pid]=controls.rank_pair([family.split(' / ')[1]],'deposit',baseline.get((pid,'deposit'),()),k=K)
    dump(out/'split.json', dict(control_projects=sorted(CONTROL_PROJECTS), development_smoke=dev_results,
         heldout_projects=sorted({r['project_id'] for r in cases}), documents=documents,
         release_sha256=checksum(release/'census_release.json'), decisions_sha256=checksum(release/'source_selection.csv'),
         retrieval_source_sha256=checksum(Path(__file__).with_name('nlp_page_retrieval.py'))))
    for c in cases:
        result=index.rank_pair([project_alias(c['project_name'])],c['field'],baseline.get((c['project_id'],c['field']),()),k=K)
        c.update(result)
    dump(out/'predictions.json',dict(k=K,cases=cases))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for k in ('release','assets','out','cache'):
        parser.add_argument('--'+k,type=Path,required=True)
    args=parser.parse_args()
    if any(args.out.resolve()==p.resolve() or args.out.resolve().is_relative_to(p.resolve()) for p in (args.release,args.assets)):
        parser.error('Choose a separate experiment output directory')
    run(args.release,args.assets,args.out,args.cache)
