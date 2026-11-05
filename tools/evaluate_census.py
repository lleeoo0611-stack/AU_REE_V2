"""Source-bound candidate decision audit and a bounded analyst-labelled reference."""
import argparse,json
from collections import Counter
from pathlib import Path
from au_ree_v2.census import classify_ree,CANDIDATE_VERSION
from au_ree_v2.national import government_features,REE_TERMS
from au_ree_v2.acquisition import select_snapshots
from au_ree_v2.analysis import write_csv
from au_ree_v2.store import canonical,digest


def main():
    p=argparse.ArgumentParser();p.add_argument('--out',required=True);p.add_argument('--reference');p.add_argument('--snapshot-lock');a=p.parse_args()
    root=Path(__file__).resolve().parents[1];out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    snapshots=json.loads(Path(a.snapshot_lock).read_text(encoding='utf8')) if a.snapshot_lock else select_snapshots(root,'2026-11-05')
    audit=[];coverage=[];features={}
    for s in snapshots:
        if not s.get('national_government') or s.get('record_filter'):continue
        raw=government_features(root,s);count=Counter();old_count=0;structured=[k for k in s['commodity_fields'] if not any(x in k.lower() for x in ('description','summary','ore_min','gangue','min_ass'))]
        for index,f in enumerate(raw):
            attrs=f.get('attributes',f.get('properties',{}));native=str(attrs.get(s['id_field']))
            fields={k:attrs.get(k) for k in s['commodity_fields']}
            result=classify_ree(fields,structured);old=bool(REE_TERMS.search('; '.join(str(v or '') for v in fields.values())))
            old_count+=old
            count[result['role']]+=1;features[s['key'],native]=(fields,structured,s['sha256'])
            # Keep every positive and deterministic excluded examples. No
            # sample is relabelled from a prediction to create a gold standard.
            if result['include'] or int(digest([s['key'],native])[:8],16)%100==0:
                audit.append(dict(source_key=s['key'],source_sha256=s['sha256'],state=s['state'],native_id=native,
                    name=attrs.get(s['name_field']),source_entity_kind=s.get('entity_kind','SITE'),
                    locator=f'original features[{index}] / '+s['id_field']+'='+native,
                    old_candidate=old,new_candidate=result['include'],role=result['role'],
                    matches=canonical(result['matches']),original_fields=canonical(fields),rule_version=CANDIDATE_VERSION))
        coverage.append(dict(state=s['state'],source_key=s['key'],source_sha256=s['sha256'],raw_records=len(raw),
            candidate_records=sum(v for k,v in count.items() if k!='NO_REE_MATCH'),previous_rule_candidates=old_count,role_counts=canonical(dict(count)),
            status='COMPLETE_SPECIFIED_SOURCE_NOT_COMPLETE_PROJECT_CENSUS'))
    for state in ('ACT',):coverage.append(dict(state=state,source_key='ga_aimr_and_portal_search',raw_records=None,candidate_records=None,
        status='NATIONAL_GA_AVAILABLE_NO_DEDICATED_ACT_MINERAL_ADAPTER_IDENTIFIED_NOT_ZERO_PROJECTS'))
    coverage.append(dict(state='OTHER_TERRITORIES',source_key=None,raw_records=None,candidate_records=None,
        status='NOT_EVALUATED_SEPARATELY: external territories and Australian Antarctic Territory outside current state adapters; no absence claim'))
    write_csv(out/'census_candidate_decisions.csv',audit,list(audit[0]))
    write_csv(out/'national_source_coverage.csv',coverage,['state','source_key','source_sha256','raw_records','candidate_records','previous_rule_candidates','role_counts','status'])
    if a.reference:
        ref=json.loads(Path(a.reference).read_text(encoding='utf8'));rows=[]
        for r in ref['records']:
            fields,structured,sha=features[r['source_key'],r['native_id']]
            if sha!=r['source_sha256'] or fields!=r['original_fields']:raise ValueError('REFERENCE_SOURCE_CHANGED')
            result=classify_ree(fields,structured)
            rows.append(dict(**r,old_candidate=bool(REE_TERMS.search('; '.join(str(v or '') for v in fields.values()))),
                predicted_candidate=result['include'],predicted_role=result['role']))
        metrics={}
        for split in ('development','held_out'):
            rr=[r for r in rows if r['split']==split];metrics[split]={}
            for version,field in [('previous','old_candidate'),('current','predicted_candidate')]:
                tp=sum(r['expected_candidate'] and r[field] for r in rr);fp=sum(not r['expected_candidate'] and r[field] for r in rr)
                fn=sum(r['expected_candidate'] and not r[field] for r in rr);tn=sum(not r['expected_candidate'] and not r[field] for r in rr)
                metrics[split][version]=dict(n=len(rr),TP=tp,FP=fp,FN=fn,TN=tn,
                    precision=tp/(tp+fp) if tp+fp else None,recall=tp/(tp+fn) if tp+fn else None,
                    F1=2*tp/(2*tp+fp+fn) if 2*tp+fp+fn else None)
            metrics[split]['role_correct']=sum(r['expected_role']==r['predicted_role'] for r in rr)
            metrics[split]['role_errors']=[dict(source_key=r['source_key'],native_id=r['native_id'],expected=r['expected_role'],actual=r['predicted_role']) for r in rr if r['expected_role']!=r['predicted_role']]
            metrics[split]['strict_REE_excluding_Sc_only']={}
            for version,field in [('previous','old_candidate'),('current','predicted_candidate')]:
                truth=[r['expected_candidate'] and r['expected_role']!='SC_ONLY' for r in rr]
                prediction=[r[field] and (version=='previous' or r['predicted_role']!='SC_ONLY') for r in rr]
                tp=sum(t and v for t,v in zip(truth,prediction));fp=sum(not t and v for t,v in zip(truth,prediction))
                fn=sum(t and not v for t,v in zip(truth,prediction));tn=sum(not t and not v for t,v in zip(truth,prediction))
                metrics[split]['strict_REE_excluding_Sc_only'][version]=dict(TP=tp,FP=fp,FN=fn,TN=tn,
                    precision=tp/(tp+fp) if tp+fp else None,recall=tp/(tp+fn) if tp+fn else None,
                    F1=2*tp/(2*tp+fp+fn) if 2*tp+fp+fn else None)
        (out/'census_validation.json').write_text(canonical(dict(reference=ref['annotation_status'],metrics=metrics,
            reference_scope='Purposeful stratified native records only; not national recall or independent gold',
            identity_precision_recall=None,identity_reason='No independent exhaustive Project crosswalk; new Barkly typed hierarchy source-checked separately',
            binding_scope='Cummins and Nolans source tables reviewed separately; no national binding accuracy claim'))+'\n',encoding='utf8')
    print(canonical(dict(sources=len(coverage)-2,decision_audit_rows=len(audit))))


if __name__=='__main__':main()
