"""Triage an external name list; never admit projects, companies or numbers."""
import argparse,csv,json,re
from collections import Counter,defaultdict
from pathlib import Path
from au_ree_v2.pdf_extract import project_registry
from au_ree_v2.reviewed_discovery import project_id
from au_ree_v2.store import filehash

def screen(input_file,root,summary,discovery,out):
    with Path(input_file).open(encoding='utf-8-sig',newline='') as f:
        reader=csv.DictReader(f);headers=reader.fieldnames;rows=list(reader)
    if not headers or len(headers)!=3:raise ValueError('EXTERNAL_NAME_LIST_THREE_COLUMNS_REQUIRED')
    with Path(summary).open(encoding='utf-8-sig',newline='') as f:master=list(csv.DictReader(f))
    ids={r['專案ID'] for r in master};names=defaultdict(set)
    def norm(s):return re.sub(r'\W+','',s.casefold())
    for r in master:names[norm(r['專案名稱'])].add(r['專案ID'])
    for p in project_registry(root):
        if p['entity_id'] in ids:
            for name in [p['name'],*p['aliases']]:names[norm(name)].add(p['entity_id'])
    cfg=json.loads(Path(discovery).read_text('utf8'));decisions={}
    for r in cfg['candidates']:
        for name in [r['name'],*r['aliases']]:
            decisions[norm(name)]=r['decision']
            if r['decision']=='ADMIT_PROJECT':names[norm(name)].add(project_id(r['candidate_key']))
    results=[]
    for i,r in enumerate(rows,2):
        name=r[headers[0]];match=sorted(names.get(norm(name),set()));disposition=decisions.get(norm(name),'')
        status='EXACT_REGISTERED_NAME_MATCH;DEVELOPER_TICKER_STILL_UNVERIFIED' if len(match)==1 else 'AMBIGUOUS_NAME_MATCH' if match else 'REVIEWED_'+disposition if disposition else 'UNVERIFIED_EXTERNAL_LEAD;NOT_AUTOMATIC_PROJECT_ADMISSION'
        # Preserve disagreements as a review queue; no typo or company overwrite.
        if norm(name)=='narraburri':status='POSSIBLE_NARRABURRA_TYPO;NO_AUTOMATIC_IDENTITY_MERGE'
        if norm(name)=='caldeiraprojecthq':status='OVERSEAS_PROJECT_LEAD;AUSTRALIAN_COMPANY_ADDRESS_NOT_PROJECT_COUNTRY'
        results.append(dict(input_row=i,input_name=name,input_developer=r[headers[1]],input_ticker=r[headers[2]],status=status,matched_project_ids=json.dumps(match)))
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    with (out/'Gemini_名稱核對.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,list(results[0]));w.writeheader();w.writerows(results)
    report=dict(input_sha256=filehash(input_file),input_rows=len(rows),status_counts=dict(Counter(r['status'] for r in results)),
        numeric_values_imported=0,projects_admitted_from_external_list_alone=0,companies_or_tickers_overwritten=0,
        raw_input_rows_published=False,interpretation='NAME_TRIAGE_ONLY;MATCH_IS_NOT_CURRENT_DEVELOPER_LEGAL_OR_TECHNICAL_VALIDATION;UNMATCHED_IS_NOT_ABSENCE',
        followup_notes=[dict(topic='Caldeira',reason='PRIMARY_ISSUER_IDENTIFIES_BRAZIL;HQ_IS_NOT_MINE_LOCATION',source_url='https://meteoric.com.au/'),
            dict(topic='WIM100',reason='ILUKA_DATED_ORIGINAL_CONFIRMS_OWN_WIM100;DO_NOT_MERGE_WITH_WIM_RESOURCE_NAME_OR_AVONBANK',source_url='https://www.asx.com.au/asx/v2/statistics/displayAnnouncement.do?display=pdf&idsId=03053666'),
            dict(topic='Cowalinya',reason='REVIEWED_HRE_RESOURCE_ORIGINAL;GEMINI_HVY_COMPANY_TICKER_PAIR_NOT_IMPORTED',source_url='https://wcsecure.weblink.com.au/pdf/HRE/02860130.pdf')])
    (out/'gemini_screening.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    return report

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for key in ['input','root','summary','discovery-ledger','out']:p.add_argument('--'+key,required=True)
    a=p.parse_args();print(json.dumps(screen(a.input,a.root,a.summary,a.discovery_ledger,a.out),ensure_ascii=False,indent=2))
