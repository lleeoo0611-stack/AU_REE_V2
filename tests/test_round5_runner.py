import importlib.util
from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('fifth',ROOT/'tools/run_round5.py');r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)
def test_round5_baseline_provenance_unchanged():
 r.verify_existing(ROOT/'results/round4-5-2026-11-13/projection')
def test_round5_baseline_and_full_replay_contract():
 assert r.BASELINE=='a35b151c92cc982dc0758cb4966c1655cf9fe9bb'
 assert len(r.FILES)==6
 s=(ROOT/'tools/run_round5.py').read_text('utf8')
 assert 'fourth.full_baseline(work,census)' in s
 assert 'fourth.apply(stage,before,after,decisions,census)' in s
 assert 'OFFLINE_OCR_ENGINE_OR_EXECUTION_REQUIRED' in s
 assert 'round5_wa import collect as collect_task3' in s

def test_round5_full_audit_receipt_required():
 s=(ROOT/'tools/run_round5.py').read_text('utf8')
 assert "audit_passes['a']!=audit_passes['b']" in s
 assert "audit_payload.json" in s
 release=(ROOT/'src/au_ree_v2/round5_release.py').read_text('utf8')
 assert 'ROUND5_AUDIT_CHANGED' in release
 assert 'ROUND5_AUDIT_RECEIPT_REQUIRED' in release

@pytest.mark.parametrize('decision_id',['round5-stage-priority-aliases-20261113','round5-offline-ocr-20261113','round5-wa-sortby-20261113'])
@pytest.mark.parametrize('field',['rule','scope','approval_evidence','decided_by','decided_date','project_id'])
def test_round5_extensions_cannot_weaken_historical_gate(decision_id,field):
 import json
 from au_ree_v2.approved_coverage_audit import validate_decisions
 registry=json.loads((ROOT/'config/researcher_rule_decisions.json').read_text('utf8'))
 assert len(validate_decisions(registry))==19
 next(d for d in registry['decisions'] if d['decision_id']==decision_id)[field]='TAMPERED'
 with pytest.raises(ValueError,match='EXTENSION'):validate_decisions(registry)

def test_required_outcome_diff_export_contract():
 source=(ROOT/'tools/run_round5.py').read_text('utf8')
 assert "extra['outcome_diff']=extra.pop('hit_review_diff')" in source
 assert "key in ('hit_reviews','outcome_diff')" in source
