"""Evaluate fixed original-page gold through the existing recognizer, never ingest labels."""
import json
import sys
from pathlib import Path
from collections import Counter
from au_ree_v2.pdf_extract import recognize_document,project_registry
from au_ree_v2.store import filehash


def evaluate(root,parser_version):
 root=Path(root);gold=json.loads((root/'data/technical_benchmark.json').read_text());registry=project_registry(root)
 manifest=json.loads((root/'data/manifest.json').read_text())['snapshots'];cache={};results=[]
 for case in gold['documents']:
  sha=case['source_sha256'];source=next(s for s in manifest if s['sha256']==sha and s['kind']=='pdf')
  if filehash(root/source['path'])!=sha:raise ValueError('BENCHMARK_ORIGINAL_SHA_MISMATCH')
  if sha not in cache:cache[sha]=recognize_document(root,source,registry,parser_version=parser_version,page_numbers={c['physical_page'] for c in gold['documents'] if c['source_sha256']==sha})
  allowed={'ELEMENT_EXTRACTION':{'extraction_pct'},'DRY_FEED_REAGENTS':{'dry_feed_mtpa','reagent_tpa'},'FLOTATION':{'grade_pct','recovery_pct'},'MODEL_RECOVERY_GRADE':{'grade_pct','recovery_pct','stage_recovery_pct'},'BRANCH_RECOVERY':{'stage_recovery_pct'},'MODEL_COEFFICIENTS':{'downstream_recovery_factor'}}[case['family']]
  predicted=[c for c in cache[sha]['candidates'] if c['kind']=='TECHNICAL_TABLE_CELL' and c['physical_page']==case['physical_page'] and c['quantity'] in allowed and (case['family']!='BRANCH_RECOVERY' or c.get('basis') in {'CeO2','Y2O3'})]
  expected=case['expected'];used=set();tp=semantic=located=0;failures=[]
  for e in expected:
   identity={k:v for k,v in e.items() if k!='value'}
   matches=[(i,c) for i,c in enumerate(predicted) if i not in used and all(c.get(k)==v for k,v in identity.items())]
   if len(matches)==1 and matches[0][1]['value']==e['value']:
    i,c=matches[0];used.add(i);tp+=1;semantic+=1;located+=bool(c.get('bbox') and c.get('header_path'))
   else:failures.append(e)
  fp=len(predicted)-len(used);fn=len(expected)-tp
  results.append(dict(source_key=case['source_key'],source_sha256=sha,physical_page=case['physical_page'],partition=case['partition'],family=case['family'],
    expected_cells=len(expected),predicted_cells=len(predicted),true_positive=tp,false_positive=fp,false_negative=fn,
    precision=tp/(tp+fp) if tp+fp else None,recall=tp/(tp+fn) if tp+fn else None,strict_quantity_unit_scope_correct=semantic,
    located_matches=located,unmatched_expected=failures,quantity_counts=dict(Counter(e['quantity'] for e in expected))))
 return dict(version='technical-benchmark-v1',parser_version=parser_version,annotation=gold['annotation'],documents=len(cache),results=results,
   scope='FIXED_PAGES_AND_QUANTITIES_ONLY; disclosed documents development/regression; no national accuracy claim; negative source value counts as correct transcription, not valid performance')

if __name__=='__main__':
 root=Path(__file__).resolve().parents[1]
 data=evaluate(root,sys.argv[2] if len(sys.argv)>2 else 'document-recognition-v5-technical-cells')
 Path(sys.argv[1]).write_text(json.dumps(data,indent=2)+'\n',encoding='utf-8')
