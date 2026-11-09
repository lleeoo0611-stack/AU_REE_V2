"""Reconcile an external name queue against explicitly source-reviewed identities.

Input companies/tickers are retained only in the local crosswalk. They never
create a project, resource observation, code value or identity merge.
"""
import argparse,csv,hashlib,json
from collections import Counter
from pathlib import Path
from au_ree_v2.store import filehash


def review(input_file,review_ledger,summary,out):
    config=json.loads(Path(review_ledger).read_text('utf8'))
    if config.get('version')!='external-name-reviews-v1' or filehash(input_file)!=config['input_sha256']:
        raise ValueError('EXTERNAL_REVIEW_INPUT_CHANGED')
    with Path(input_file).open(encoding='utf-8-sig',newline='') as f:
        reader=csv.DictReader(f);headers=reader.fieldnames;inputs=list(reader)
    with (Path(summary)/'專案總表.csv').open(encoding='utf-8-sig',newline='') as f:master={r['專案ID']:r for r in csv.DictReader(f)}
    with (Path(summary)/'field_provenance.csv').open(encoding='utf-8-sig',newline='') as f:
        source_links={(r['project_id'],r['source_sha256'],r['source_url']) for r in csv.DictReader(f) if r['source_sha256']}
    if len(headers)!=3 or len(inputs)!=config['input_rows']:
        raise ValueError('EXTERNAL_REVIEW_INPUT_CONTRACT')
    reviews={r['input_row']:r for r in config['reviews']}
    if len(reviews)!=len(config['reviews']) or set(reviews)!=set(range(2,len(inputs)+2)):
        raise ValueError('EXTERNAL_REVIEW_INCOMPLETE_OR_DUPLICATE')
    public=[];local=[]
    for i,source in enumerate(inputs,2):
        r=reviews[i]
        if hashlib.sha256(source[headers[0]].encode('utf8')).hexdigest()!=r['input_name_sha256']:
            raise ValueError('EXTERNAL_REVIEW_NAME_HASH')
        pids=r.get('matched_project_ids',[])
        if any(p not in master for p in pids):raise ValueError('EXTERNAL_REVIEW_UNKNOWN_PROJECT')
        if r['status'] in ('SOURCE_REVIEWED_EXISTING_PROJECT','SOURCE_REVIEWED_NEW_PROJECT') and (len(pids)!=1 or not r.get('source_references')):
            raise ValueError('EXTERNAL_REVIEW_PRIMARY_PROJECT_PROOF_REQUIRED')
        if r['status'] in ('SOURCE_REVIEWED_EXISTING_PROJECT','SOURCE_REVIEWED_NEW_PROJECT') and any(
            (pids[0],s.get('source_sha256'),s.get('source_url')) not in source_links for s in r['source_references']):
            raise ValueError('EXTERNAL_REVIEW_PROJECT_SOURCE_BINDING')
        # The original company/ticker is deliberately not part of any join.
        row=dict(input_row=i,status=r['status'],matched_project_ids=json.dumps(pids),
            reviewed_project_names=json.dumps([master[p]['專案名稱'] for p in pids],ensure_ascii=False),
            source_verified_asx_codes=json.dumps([master[p].get('ASX代碼','') for p in pids]),
            reason=r['reason'],source_references=json.dumps(r.get('source_references',[]),ensure_ascii=False),
            search_query_count=len(r.get('search_ids',[])),input_name_sha256=r['input_name_sha256'])
        public.append(row);local.append(dict(input_row=i,input_name=source[headers[0]],input_developer=source[headers[1]],input_ticker=source[headers[2]],**{k:v for k,v in row.items() if k!='input_row'}))
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    def write(name,rows):
        with (out/name).open('w',encoding='utf-8-sig',newline='') as f:
            w=csv.DictWriter(f,list(rows[0]));w.writeheader();w.writerows(rows)
    write('external_name_reviews.csv',public);write('Gemini_逐項核對.csv',local)
    result=dict(input_sha256=config['input_sha256'],review_ledger_sha256=filehash(review_ledger),input_rows=len(inputs),status_counts=dict(Counter(r['status'] for r in public)),
        numeric_values_imported=0,projects_admitted_from_external_list_alone=0,companies_or_tickers_overwritten_from_input=0,raw_input_rows_published=False,
        queue_reviewed_rows=len(public),interpretation='SOURCE_SEARCH_AND_DISPOSITION_FOR_EVERY_ROW;UNVERIFIED_IS_NOT_ABSENCE;SOURCE_REVIEWED_IDENTITY_IS_NOT_CURRENT_TITLE_CERTIFICATION',
        public_review_sha256=filehash(out/'external_name_reviews.csv'),master_csv_sha256=filehash(Path(summary)/'專案總表.csv'))
    (out/'external_name_review.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for key in ['input','review-ledger','summary','out']:p.add_argument('--'+key,required=True)
    a=p.parse_args();print(json.dumps(review(a.input,a.review_ledger,a.summary,a.out),ensure_ascii=False,indent=2))
