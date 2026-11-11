import copy,json
from pathlib import Path
from au_ree_v2 import round2_deposit
from au_ree_v2.round2_deposit import collect_deposit,proposed_decisions,CLAYS,SPECULATIVE
ROOT=Path(__file__).resolve().parents[1]
ARCHIVE_ROOT=Path(round2_deposit.__file__).resolve().parents[2]

def baseline():
 return json.loads((ROOT/'tests/fixtures/round2_deposit_baseline.json').read_text('utf8'))

def test_actual_additive_deposit_rules_and_qualifiers():
 b=baseline();original=copy.deepcopy(b);f,q=collect_deposit(b['rows'],b['provenance'],proposed_decisions(),ARCHIVE_ROOT)
 assert b==original
 assert len(f)==38
 assert {x['project_id'] for x in q}=={'AU-47d12ebe6b66df8e5936','AU-794821a2df9b7a244f96'}
 old={r['專案ID']:r for r in b['rows']}
 assert sum(bool(r['礦床型態代碼']) for r in b['rows'])==29
 for x in f:
  assert not old[x['project_id']]['礦床型態代碼']
  scope=json.loads(x['provenance']['scope'])
  if old[x['project_id']]['礦床型態'].casefold() in CLAYS:
   assert x['value']=='iac' and 'IONIC_NOT_CONFIRMED' in scope['qualifier']
  assert ('SPECULATIVE_DEPOSIT_STYLE' in scope['qualifier'])==(x['project_id'] in SPECULATIVE)
  assert x['provenance']['locator']
 assert len([x for x in f if x['project_id'] in SPECULATIVE])==3

def test_decisions_removed_fail_closed():
 b=baseline();full=proposed_decisions()
 assert collect_deposit(b['rows'],b['provenance'],[],ARCHIVE_ROOT)[0]==[]
 for d in full:
  f,_=collect_deposit(b['rows'],b['provenance'],[x for x in full if x!=d],ARCHIVE_ROOT)
  assert all(x['decision_id']!=d['decision_id'] for x in f)
  if 'SPECULATIVE' in d['rule']:assert not any(x['project_id'] in SPECULATIVE for x in f)

def test_unknown_host_stays_blank():
 b=baseline();r=next(r for r in b['rows'] if r['專案ID']=='AU-47d12ebe6b66df8e5936')
 f,q=collect_deposit([r],b['provenance'],proposed_decisions(),ARCHIVE_ROOT)
 assert not f and q[0]['reason']=='PROJECT_WIDE_DOMINANT_HOST_NOT_ESTABLISHED'
