"""Round-four release must reject changed current before reading receipts."""
import pytest
from au_ree_v2.round4_release import publish
from au_ree_v2.round3_publication import tree_hashes
from au_ree_v2.iteration_review import audit_summary

def test_round4_release_requires_unchanged_current(tmp_path):
    current=tmp_path/'results/asx-current';current.mkdir(parents=True)
    (current/'a').write_text('old')
    expected=tree_hashes(current);(current/'a').write_text('changed')
    with pytest.raises(ValueError,match='ROUND4_CURRENT_CHANGED'):
        publish(tmp_path,'2026-11-13',tmp_path/'work',tmp_path/'out',expected,lambda _:None)

def test_round4_release_requires_all_six_receipts(tmp_path):
    current=tmp_path/'results/asx-current';current.mkdir(parents=True)
    with pytest.raises(FileNotFoundError):
        publish(tmp_path,'2026-11-13',tmp_path/'work',tmp_path/'out',tree_hashes(current),lambda _:None)

def test_round4_generic_audit_dispatch(tmp_path,monkeypatch):
    import au_ree_v2.round4_schema as schema
    (tmp_path/'summary.json').write_text('{"version":"round4-core-v1"}')
    monkeypatch.setattr(schema,'audit',lambda p: {'round4':True})
    assert audit_summary(tmp_path)=={'round4':True}
