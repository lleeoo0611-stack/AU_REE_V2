"""Supplement unapproved locator proposals using this CI's verified bytes only."""
import csv
import hashlib
import json
import os
import re
from collections import Counter
from pathlib import Path
from au_ree_v2.pdf_extract import extract_page
from au_ree_v2.store import digest

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'results/claims-locators-2026-11-16/v9'
def norm(value):return re.sub(r'\s+',' ',str(value)).strip()

def choose_markers(text,old,preferred):
    normalized=norm(text)
    candidates=[]
    for value in preferred:
        if not isinstance(value,str) or len(norm(value))<4:continue
        match=re.search(re.escape(norm(value)),normalized,re.I)
        if match:candidates.append(normalized[match.start():match.end()])
    candidates.extend(m.group() for m in re.finditer(r'\bASX\s*(?::|Code\s*:|\|)\s*[A-Z0-9]{2,5}\b',normalized))
    lines=[norm(line) for line in text.splitlines()]
    lines.sort(key=lambda line:(not bool(re.search(r'Annual Report|Mineral Resource|Project|Limited|Quarter|Scoping|Exploration',line,re.I)),len(line)))
    candidates.extend(lines)
    result=[]
    for marker in candidates:
        if not 8<=len(marker)<=180 or not re.search('[A-Za-z]{3}',marker):continue
        if re.search(r'personal use only|^page\s*\d|^www\.|^https?://|copyright|all rights reserved',marker,re.I):continue
        if marker not in normalized or any(marker in norm(existing) for existing in old):continue
        if any(marker in existing or existing in marker for existing in result):continue
        result.append(marker)
        if len(result)==2:break
    return result

def verified_path(source,receipt,sha):
    if source.get('sha256')!=sha or receipt.get('sha_match')!='True':return None
    if receipt.get('status') not in ('FETCHED_SHA_VERIFIED','ALTERNATE_SAME_SHA','COMMITTED_SNAPSHOT_SAME_SHA','SNAPSHOT_FALLBACK_SAME_SHA'):
        return None
    path=(ROOT/source['path']).resolve()
    if not path.is_relative_to(ROOT.resolve()) or not path.is_file():return None
    return path if hashlib.sha256(path.read_bytes()).hexdigest()==sha else None

def main():
    csv.field_size_limit(16*1024*1024)
    clean=ROOT/'work/clean'
    latest=json.loads((clean/'latest.json').read_text())
    run=Path(latest['output_dir'])
    lock=json.loads((run/'snapshot_lock.json').read_text())
    with (run/'acquisition_report.csv').open(encoding='utf-8-sig',newline='') as f:receipts={r['key']:r for r in csv.DictReader(f)}
    adopted={}
    for source in lock:
        if source.get('kind')=='pdf':
            path=verified_path(source,receipts.get(source['key'],{}),source['sha256'])
            if path:adopted[source['sha256']]=path
    claims=json.loads((ROOT/'data/claims.json').read_text())['projects']
    projects={'AU-'+digest([p.get('entity_namespace','project_registry_v1'),str(p['id'])])[:20]:p for p in claims}
    registry={s['key']:s for s in json.loads((ROOT/'config/sources.json').read_text())['sources']}
    with (BASE/'p2_marker_proposals.csv').open(encoding='utf-8-sig',newline='') as f:rows=list(csv.DictReader(f))
    changed=[]
    for row in rows:
        if row['approved'] or row['status']=='PROPOSED':continue
        path=adopted.get(row['source_sha256'])
        if not path:continue
        markers=json.loads(row['existing_markers'])
        data=extract_page(path,int(row['pdf_page']),os.environ.get('TESSDATA_PREFIX'),markers=markers)
        text=norm(data['text'])
        if any(norm(m) not in text for m in markers):
            row['status']='EXISTING_MARKER_NOT_ON_PAGE';continue
        p=projects[row['project_id']]
        preferred=[registry.get(row['source_key'],{}).get('issuer',{}).get('name',''),p['name'],*p.get('aliases',[])]
        preferred.extend(a['value'] for a in p.get('attributes',[]) if a.get('column') in ('開發商','ASX代碼'))
        pair=choose_markers(data['text'],markers,preferred)
        if len(pair)!=2:
            row['status']='NO_TWO_INDEPENDENT_CANDIDATES';continue
        snippets=[]
        for marker in pair:
            at=text.index(marker);snippets.append(text[max(0,at-80):at+len(marker)+80])
        row.update(marker_1=pair[0],marker_2=pair[1],snippet=json.dumps(snippets,ensure_ascii=False),
                   status='PROPOSED',extraction_method=data['method'],model_sha256=data.get('model_sha256') or '')
        row['proposal_id']=digest([row['project_id'],row['declaration_pointer'],row['source_sha256'],
                                   int(row['pdf_page']),*pair])[:20]
        changed.append(dict(proposal_id=row['proposal_id'],source_sha256=row['source_sha256'],
                            project_id=row['project_id'],column=row['column'],pdf_page=row['pdf_page']))
    with (clean/'p2_marker_proposals.csv').open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,list(rows[0]));writer.writeheader();writer.writerows(rows)
    summary=dict(rows=len(rows),supplemented_rows=len(changed),statuses=dict(Counter(r['status'] for r in rows)),
                 approved_values_written=0,claims_modified=False,source='Same CI snapshot_lock plus SHA-verifying acquisition receipts',
                 supplemental_proposals=changed)
    (clean/'p2_cache_completion.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps(dict(supplemented_rows=len(changed),statuses=summary['statuses'])))

if __name__=='__main__':main()
