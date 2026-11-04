"""Fixed development regression and source-page evaluation, never production labels."""
import json
import sys
from pathlib import Path
from evaluate_technical import evaluate
from au_ree_v2.pdf_extract import recognize_document,project_registry
from au_ree_v2.technical import burden_states

def run(root):
    import pymupdf
    root=Path(root);version='document-recognition-v6-context-bound'
    regression=evaluate(root,version)
    for r in regression['results']:
        r['partition']='PHASE16_DEVELOPMENT_REGRESSION_NOT_HELD_OUT'
    policy=json.loads((root/'results/phase16-2026-11-04/configuration.json').read_text())['research']['evidence_resolution']['technical_profile']
    manifest=json.loads((root/'data/manifest.json').read_text())['snapshots']
    source=next(s for s in manifest if s['key']=='koppamurra_pfs2026' and s['kind']=='pdf')
    d=recognize_document(root,source,project_registry(root),parser_version=version,page_numbers={11})
    numbers=[n for c in d['candidates'] if c['domain']=='Technical' for n in c.get('numbers',[]) if n.get('quantity_role')]
    expected=[(68,'TREO','REPORTED_RECOVERY'),(68,'MREO','REPORTED_RECOVERY')]
    predicted=[(n['value'],n.get('basis'),n['quantity_role']) for n in numbers]
    extraction=dict(source_sha256=source['sha256'],pdf_page=11,partition='NOT_USED_FOR_PHASE16_RULE_ADJUSTMENT_KNOWN_ARCHIVE_NOT_BLIND',
        sampling='First existing PFS resource-to-final-MREO source case without Phase15 technical cells; fixed p11 and two explicit recovery clauses, not random national sampling',
        expected=expected,predicted=predicted,true_positive=sum(t in predicted for t in expected),false_negative=sum(t not in predicted for t in expected),false_positive=sum(t not in expected for t in predicted))
    interpretations=[]
    # Source-page labels read from originals after fixing the rule set. Misses
    # remain evaluation outcomes; these documents are not used to retune rules.
    for key,page,criterion,expected_state in [('koppamurra_pfs2026',11,'T-B','EXPLICIT_ADDITIONAL_REQUIREMENT'),('cowalinya_ar2024',9,'T-A','EXPLICIT_ADDITIONAL_REQUIREMENT'),('cowalinya_ar2024',9,'T-B','OBSERVED_MAJOR_OBSTACLE')]:
        s=next(s for s in manifest if s['key']==key and s['kind']=='pdf')
        with pymupdf.open(root/s['path']) as doc:text=doc[page-1].get_text(sort=True)
        states=sorted({r['state'] for r in burden_states(text,policy) if r['criterion']==criterion}) or ['UNKNOWN']
        interpretations.append(dict(source_sha256=s['sha256'],pdf_page=page,criterion=criterion,expected_source_scoped_state=expected_state,predicted_states=states,exact_match=states==[expected_state],partition='HELD_FROM_RULE_ADJUSTMENT_NOT_BLIND_NOT_EXPERT_VALIDATED'))
    return dict(version='phase16-evaluation-v1',regression=regression,held_document_extraction=extraction,burden_interpretation=interpretations,
        annotation='AI-assisted original-page reading plus rendered-page review, not independent experts; fixed purposive sample, no corpus accuracy claim',
        revisions='Browns Range moved to development/regression after repair. No holdout-driven changes to the burden rule set.')

if __name__=='__main__':
    root=Path(__file__).resolve().parents[1]
    Path(sys.argv[1]).write_text(json.dumps(run(root),indent=2)+'\n',encoding='utf8')
