"""Source-held error accounting; no retuning or production labels."""
import ast,json,hashlib,sys
from pathlib import Path
from au_ree_v2.technical import burden_states,claim_purpose,target_applicability,technical_compare
from au_ree_v2.store import filehash

def run(root):
    import pymupdf
    root=Path(root);reg=json.loads((root/'data/phase16_remediation_preregistration.json').read_text())
    code=(root/'src/au_ree_v2/technical.py').read_text();mod=ast.parse(code)
    actual={f.name:hashlib.sha256(ast.get_source_segment(code,f).encode()).hexdigest() for f in mod.body if isinstance(f,ast.FunctionDef) and f.name in reg['held_rule_freeze']}
    if actual!=reg['held_rule_freeze']:raise ValueError('HELD_RULE_FREEZE_CHANGED_REQUIRES_PARTITION_DISCLOSURE')
    labels=json.loads((root/'data/phase16_remediation_held_labels.json').read_text());manifest=json.loads((root/'data/manifest.json').read_text())['snapshots']
    profile=json.loads((root/'config/evidence_policy.json').read_text())['technical_profile'];documents={};sources={}
    for item in reg['holdout']:
        source=next(s for s in manifest if s['key']==item['key'] and s['kind']=='pdf')
        assert filehash(root/source['path'])==source['sha256']
        artifact=next(s for s in reversed(manifest) if s['kind']=='document_extraction' and s['source_sha256']==source['sha256'])
        assert filehash(root/artifact['path'])==artifact['sha256']
        documents[item['key']]=json.loads((root/artifact['path']).read_text());sources[item['key']]=source
    numeric=[]
    for target in labels['numeric_targets']:
        data=documents[target['key']];candidates=[c for c in data['candidates'] if c.get('pdf_page',c.get('physical_page'))==target['page']]
        hits=[dict(n,candidate_id=c.get('candidate_id'),raw_text=c.get('raw_text')) for c in candidates for n in c.get('numbers',[]) if n.get('value')==target['value'] and n.get('unit')==target['unit']]
        bound=any(n.get('basis')==target['basis'] and n.get('endpoint')==target['endpoint'] for n in hits)
        numeric.append(dict(target,source_sha256=sources[target['key']]['sha256'],token_found=bool(hits),quantity_scope_bound=bound,predicted=hits,disposition='RAW_TOKEN_ONLY_NOT_ADMITTED' if hits and not bound else 'MISSED_TARGET' if not hits else 'SOURCE_SCOPED_ONLY'))
    claims=[]
    for target in labels['claim_targets']:
        source=sources[target['key']]
        with pymupdf.open(root/source['path']) as doc:text=' '.join(doc[target['page']-1].get_text(sort=True).split())
        start=text.index(target['start']);end=text.find(target['end'],start+len(target['start']))
        if end<0:end=len(text)
        quote=text[start:end].strip();pred=[r for r in burden_states(quote,profile) if r['criterion']==target['criterion']]
        actual=bool(pred);purpose=claim_purpose(quote)
        scope=target_applicability({'scope':'reported sample','source_sha256':source['sha256']},{})
        claims.append(dict(target,source_sha256=source['sha256'],quote=quote,predicted_claim=actual,predicted=pred,predicted_nature=purpose,nature_match=purpose==target['expected_nature'],project_extrapolation=scope['project_extrapolation'],result='TP' if actual and target['expected_claim'] else 'FP' if actual else 'FN' if target['expected_claim'] else 'TN',disposition='MISSED_POSITIVE_RETAIN_FOR_FUTURE_DEVELOPMENT' if target['expected_claim'] and not actual else 'SOURCE_SCOPE_ONLY_NOT_COMMON_SCORE'))
    acceptance=[]
    contract=profile['numeric_model']['contract']
    for target in labels['acceptance_targets']:
        data=documents[target['key']];attempts=[]
        for candidate in data['candidates']:
            for number in candidate.get('numbers',[]):
                # Unknown quantity/case/endpoint stays unknown, never filled from
                # the gold label or from a matching percentage in another source.
                record=dict(variable=number.get('variable'),value=number.get('value'),unit=number.get('unit'),basis=number.get('basis'),feed=number.get('feed',candidate.get('feed')),endpoint=number.get('endpoint',candidate.get('endpoint')),scale=number.get('scale',candidate.get('scale')),scope=candidate.get('scope'),case_id=candidate.get('case_id'),study_date=candidate.get('study_date'),evidence_mode=candidate.get('evidence_mode'),evidence_reason=None)
                reasons=technical_compare(record,contract,contract['model_assumptions'])
                if not candidate.get('project_id'):reasons.append('PROJECT_IDENTITY_NOT_ESTABLISHED')
                attempts.append(dict(candidate_id=candidate.get('candidate_id'),page=candidate.get('physical_page'),value=number.get('value'),reasons=sorted(set(reasons))))
        admitted=any(not r['reasons'] for r in attempts)
        acceptance.append(dict(target,source_sha256=sources[target['key']]['sha256'],actual_common_whole_ore_design_panel=admitted,result='FP' if admitted else 'TN',attempts=attempts))
    metrics={k:sum(r['result']==k for r in claims) for k in ('TP','FP','FN','TN')};metrics['precision']=metrics['TP']/(metrics['TP']+metrics['FP']) if metrics['TP']+metrics['FP'] else None;metrics['recall']=metrics['TP']/(metrics['TP']+metrics['FN']) if metrics['TP']+metrics['FN'] else None
    return dict(version='phase16-remediation-held-evaluation-v1',documents=len(documents),partition='THREE_FIXED_DOCUMENTS_NOT_USED_FOR_REMEDIATION_RULE_ADJUSTMENT_NOT_BLIND',rule_freeze_verified=True,numeric_targets=numeric,token_metrics={'TP':sum(r['token_found'] for r in numeric),'FN':sum(not r['token_found'] for r in numeric),'FP':None,'precision':None,'reason':'Targeted statement retrieval, not exhaustive page annotation; no invented precision'},quantity_binding_metrics={'TP':sum(r['quantity_scope_bound'] for r in numeric),'FN':sum(not r['quantity_scope_bound'] for r in numeric)},claim_results=claims,claim_metrics=metrics,nature_matches=sum(r['nature_match'] for r in claims),acceptance_results=acceptance,acceptance_metrics={k:sum(r['result']==k for r in acceptance) for k in ('TP','FP','FN','TN')},project_extrapolation_false=sum(not r['project_extrapolation'] for r in claims),disposition='All new held candidates remain raw or review without complete basis/feed/endpoint/identity; none can affect adopted design panel',limitations=labels['annotation'],no_retuning=True)

if __name__=='__main__':
    root=Path(__file__).resolve().parents[1];result=run(root);Path(sys.argv[1]).write_text(json.dumps(result,indent=2)+'\n',encoding='utf8');print(json.dumps({k:v for k,v in result.items() if k not in ('numeric_targets','claim_results','acceptance_results')},indent=2))
