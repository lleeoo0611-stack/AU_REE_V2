"""Researcher-approved additive deposit classification, exclusively offline."""
import json
import re
from pathlib import Path
from .stage_rules import decision_records, _native
from .store import canonical, filehash

SCOPE='ROUND2_NATIVE_DEPOSIT_DESCRIPTION_AND_ARCHIVED_HOST'
APPROVAL='1：G1 選 B、潛力案給、G4 照建議；2：(a) 算完成、(b) 給 B1、(c) 新增 D、(d) 標成X'
RULE_NAMES={
 'clay':'RESEARCHER_RULE_CLAY_REGOLITH_TO_IAC',
 'potential':'SPECULATIVE_DEPOSIT_STYLE_ALLOWED',
 'hard':'RESEARCHER_RULE_PEGMATITE_TO_HARD',
 'placer':'RESEARCHER_RULE_SANDS_TO_PLACER',
 'g4':'RESEARCHER_RULE_CASE_SPECIFIC_ARCHIVED_HOST',
}
CLAYS=frozenset(s.casefold() for s in [
 'Clay hosted','Clay Saprolite/Granitoid','Clay/regolith','Regolith/clay','Regolith / granite','Regolith/granite','Regolith/oxide-transition','TREO enrichment in regolith','Rare Earth Elements (REE) hosted in clays','clay horizon','clay-hosted','weathered clay horizon','saprolitic clays','deeply weathered granites','halloysite-kaolinite','kaolinitic fine-grained sediments','potential for large scale, clay-hosted REE mineralisation','prospective for halloysite-kaolinite and rare earth elements (REE)',
 'The data suggests a clay hosted ionic REE type mineralisation style on the project. This interpretation is subject to amendment with additional data from follow up drilling and metallurgical test work.'
])
SPECULATIVE={'AU-b31d00e2272ffa6ccbd3','AU-6a5615e0ed95d955c2dd','AU-81b21bdd06796fa2217d'}
EXACT={
 'consistent with a highly evolved pegmatite system':('hard','hard'),
 'potential for REE, Niobium–yttrium–fluorine Pegmatites to exist':('hard','hard'),
 'alluvial sand':('placer','placer'),
 'assemblage rich in natural rutile and premium zircon':('placer','placer'),
 'heavily weathered pegmatites and saprolitic outcrops':('hard','g4'),
 'heavy mineral bearing sandstone unit':('hard','g4'),
}

def proposed_decisions():
 return [dict(decision_id='round2-deposit-'+key+'-20261111',rule=rule,scope=SCOPE,decided_by='USER_EXPLICIT_APPROVAL',decided_date='2026-11-11',notes='僅新增空白礦床型態代碼；既有原文與代碼不變；歧義留待審查。',approval_evidence=APPROVAL) for key,rule in RULE_NAMES.items()]

def approved(decisions,key):
 matches=[d for d in decision_records(decisions) if d.get('rule')==RULE_NAMES[key] and d.get('scope')==SCOPE and d.get('decided_by')=='USER_EXPLICIT_APPROVAL' and d.get('approval_evidence') and d.get('decision_id') and d.get('decided_date')=='2026-11-11']
 if len(matches)>1:raise ValueError('DEPOSIT_DUPLICATE_DECISION')
 return matches[0] if matches else None

def _verified_reviews(repo):
 payload=json.loads((repo/'config/round2_deposit_reviews.json').read_text('utf8'))
 roots=json.loads((repo/'config/asx_local_asset_roots.json').read_text('utf8'))['roots']
 for entry in payload['accepted']:
  p=(repo/roots[entry['asset_set']]/entry['path']).resolve()
  if filehash(p)!=entry['source_sha256']:raise ValueError('DEPOSIT_SOURCE_SHA_MISMATCH')
  if p.suffix=='.pdf':
   import fitz
   with fitz.open(p) as doc:text=' '.join(doc[entry['page']-1].get_text().split())
  else:text=p.read_text('utf8')
  if entry['quote'] not in text:raise ValueError('DEPOSIT_SOURCE_QUOTE_MISSING')
 return payload

def collect_deposit(rows,provenance,decisions,repo_root):
 payload=_verified_reviews(Path(repo_root));reviews={r['project_id']:r for r in payload['accepted']};pending={r['project_id']:r for r in payload['review_queue']}
 fills=[];queue=[]
 for row in rows:
  pid=row['專案ID'];text=row.get('礦床型態','')
  if row.get('礦床型態代碼') or not text:continue
  native=_native(row,provenance,'礦床型態');qualifiers=[];extra=None;review=reviews.get(pid);note=''
  if text.casefold() in CLAYS:
   code,key='iac','clay';qualifiers=['IONIC_NOT_CONFIRMED']
  elif text in EXACT:code,key=EXACT[text]
  elif review:
   code,key=review['code'],'g4';qualifiers=review['qualifiers'];note=review['note']
   if review['selected_mre_required']:
    ore=_native(row,provenance,'礦石蘊藏量_Mt')
    if not ore or ore['source_sha256']!=review['source_sha256']:raise ValueError('DEPOSIT_SELECTED_MRE_SOURCE_MISMATCH')
  else:
   queue.append(dict(project_id=pid,project=row['專案名稱'],column='礦床型態代碼',source_text=text,**{k:v for k,v in pending.get(pid,dict(reason='UNMAPPED_DEPOSIT_DESCRIPTION')).items() if k!='project_id'}));continue
  decision=approved(decisions,key)
  if pid in SPECULATIVE:
   extra=approved(decisions,'potential');qualifiers.append('SPECULATIVE_DEPOSIT_STYLE')
  if not native or not decision or (pid in SPECULATIVE and not extra):
   queue.append(dict(project_id=pid,project=row['專案名稱'],column='礦床型態代碼',source_text=text,reason='NATIVE_PROVENANCE_OR_RESEARCHER_DECISION_REQUIRED'));continue
  if 'saprolitic outcrops' in text:note='原生礦化為偉晶岩；來源取樣位置在腐岩／風化露頭，不以取樣層改判離子型。'
  if 'heavy mineral bearing sandstone' in text:
   precedent=next((r for r in rows if r.get('礦床型態')=='REE-bearing quartz sandstone' and r.get('礦床型態代碼')=='hard'),None)
   if not precedent:raise ValueError('DEPOSIT_SANDSTONE_PRECEDENT_MISSING')
   note='沿用既有 REE-bearing quartz sandstone → hard 口徑；先例專案 '+precedent['專案ID']
  method=RULE_NAMES[key];meta=dict(decision_id=decision['decision_id'],decision=decision,additional_decision=extra,qualifier=qualifiers,source_value=text,source_provenance=native,archived_host_review=review,note=note)
  trace=dict(native);trace['locator']=native.get('locator') or 'frozen source-bound native field 礦床型態; project '+pid+'; source SHA '+native['source_sha256'];trace.update(column='礦床型態代碼',value=code,method=method,scope=canonical(meta),review_ids=canonical([decision['decision_id']]+([extra['decision_id']] if extra else [])))
  if review:
   trace.update(source_sha256=review['source_sha256'],source_url=review['source_url'],locator=review['locator'],publication_date=review['publication_date'],effective_date=review['publication_date'],effective_date_role='DEPOSIT_HOST_AT_SOURCE_PUBLICATION',source_kind='ISSUER_TECHNICAL_DISCLOSURE',date_precision='DAY',publication_date_precision='DAY',publication_date_interval='null',effective_date_interval='null')
  fills.append(dict(project_id=pid,column='礦床型態代碼',value=code,method=method,decision_id=decision['decision_id'],provenance=trace))
 return fills,queue
