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

def test_round4_publication_metadata_preserves_history_and_updates_count(tmp_path,monkeypatch):
    import json,shutil
    import au_ree_v2.round4_release as release
    import au_ree_v2.round4_schema as schema
    from au_ree_v2.round2_pipeline import FILES,write_json,write_csv
    from au_ree_v2.store import filehash
    date='2026-11-13';current=tmp_path/'results/asx-current';current.mkdir(parents=True)
    old={'status':'ROUND3_PUBLISHED','published':True,'new_cells':29,'backup':'old-backup','history':[{'status':'older'}]}
    write_json(current/'publication_status.json',old)
    tests={'tests':1000,'failures':0,'errors':0,'skipped':0}
    metric={'filled':1,'denominator':2,'coverage':.5}
    for n,new in enumerate([0,0,8,0,4,0]):
        folder=tmp_path/f'results/round4-{n}-{date}';projection=folder/'projection';projection.mkdir(parents=True)
        write_csv(projection/'專案總表.csv',['專案ID'],[{'專案ID':'p'}]);write_csv(projection/'field_provenance.csv',['project_id','column'],[])
        for name in ['missing_fields.csv','census_inventory.csv']:(projection/name).write_text('header\n')
        write_json(projection/'summary.json',{'original_53_columns':metric,'all_retained_columns':metric,'tiered_coverage':{'combined':metric}});write_json(projection/'audit.json',{})
        hashes={f:filehash(projection/f) for f in FILES}
        write_json(folder/'summary.json',{'task':n,'new_cells':new,'tests':tests,'independent_full_rebuilds':2,'bitwise_identical_files':hashes})
        write_json(folder/'rebuild_receipt.json',{'independent_full_rebuilds':2,'output_hashes':hashes,'tests':tests,'census_sha256':'a'*64})
    monkeypatch.setattr(schema,'audit',lambda *args: {'validated':True})
    monkeypatch.setattr(schema,'present',lambda source,out,repo: shutil.copytree(source,out))
    monkeypatch.setattr(release,'verify_public_tree',lambda folder: {'safe':True})
    work=tmp_path/'work';work.mkdir()
    release.publish(tmp_path,date,work,folder,tree_hashes(current),lambda path:tests)
    actual=json.loads((current/'publication_status.json').read_text('utf8'))
    assert actual['new_cells']==12 and actual['history'][0]==old['history'][0]
    assert actual['history'][-1]['previous_publication_status']==old
    assert actual['backup']==f'results/asx-current.pre-round4-{date}'
    assert (tmp_path/actual['backup']/'publication_status.json').exists()
