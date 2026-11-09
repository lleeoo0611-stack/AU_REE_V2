"""Publish source-reviewed discoveries and the complete frozen candidate queue."""
import argparse,csv,json
from collections import Counter
from pathlib import Path
from au_ree_v2.reviewed_discovery import validate_discovery
from au_ree_v2.store import filehash


def audit(config,assets,baseline,out):
    baseline=Path(baseline);out=Path(out);out.mkdir(parents=True,exist_ok=True)
    def read(name):
        with (baseline/name).open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
    projects=[dict(entity_id=r['專案ID'],name=r['專案名稱'],aliases=[r['專案名稱']]) for r in read('專案總表.csv')]
    result=validate_discovery(config,assets,projects,'2026-11-05')
    reviews=[];links={}
    for r in result['receipts']:
        for eid in r['existing_candidate_ids']:links.setdefault(eid,[]).append(r['candidate_key'])
        reviews.append(dict(candidate_key=r['candidate_key'],name=r['name'],decision=r['decision'],reason=r['reason'],
            admitted_project_id=r.get('project_id',''),existing_candidate_ids=json.dumps(r['existing_candidate_ids']),
            source_sha256=json.dumps([s['sha256'] for s in r['sources']]),source_urls=json.dumps([s['url'] for s in r['sources']]),
            physical_pages=json.dumps([[e.get('page') for e in s['evidence']] for s in r['sources']]),
            interpretation='DOCUMENTARY_RESEARCH_REVIEW;NOT_FORMAL_C1_OR_TENURE_APPROVAL'))
    queue=[]
    for r in read('census_inventory.csv'):
        if r['kind']!='PROJECT_CANDIDATE':continue
        queue.append(dict(r,review_candidate_keys=json.dumps(links.get(r['entity_id'],[])),
            disposition='SOURCE_REVIEW_LINKED_CANDIDATE;NO_AUTOMATIC_IDENTITY_MERGE' if r['entity_id'] in links else 'FROZEN_OFFICIAL_CANDIDATE;PROJECT_IDENTITY_RESOURCE_AND_DATE_REVIEW_PENDING'))
    def write(name,data):
        with (out/name).open('w',encoding='utf-8-sig',newline='') as f:
            w=csv.DictWriter(f,list(data[0]));w.writeheader();w.writerows(data)
    write('discovery_reviews.csv',reviews);write('discovery_candidate_queue.csv',queue)
    report=dict(config_sha256=filehash(config),baseline_inventory_sha256=filehash(baseline/'census_inventory.csv'),
        source_reviewed_names=len(reviews),decisions=dict(Counter(r['decision'] for r in reviews)),
        original_project_candidate_records=len(queue),linked_project_candidate_records=sum(r['entity_id'] in links for r in queue),
        pending_project_candidate_records=sum(r['entity_id'] not in links for r in queue),
        admitted_project_ids=[p['entity_id'] for p in result['projects']],
        limitations=['CANDIDATE_RECORDS_ARE_NOT_COUNTS_OF_INDEPENDENT_PROJECTS','UNREVIEWED_IS_NOT_ABSENCE',
            'SEARCH_SOURCES_ARE_NON_EXHAUSTIVE;NO_NATIONAL_COMPLETENESS_CLAIM','CANONICAL_SQLITE_AND_IDENTITY_RELATIONS_NOT_MUTATED'],
        output_hashes={n:filehash(out/n) for n in ['discovery_reviews.csv','discovery_candidate_queue.csv']})
    (out/'discovery_validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for key in ['config','baseline','out']:p.add_argument('--'+key,required=True)
    p.add_argument('--asset-root',action='append',required=True);a=p.parse_args()
    print(json.dumps(audit(a.config,dict(x.split('=',1) for x in a.asset_root),a.baseline,a.out),ensure_ascii=False,indent=2))
