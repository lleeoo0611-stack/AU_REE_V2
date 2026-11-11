import importlib.util,json
from pathlib import Path
import pytest
from au_ree_v2 import round3_publication as pub


def trees(tmp_path):
    old=tmp_path/'current';new=tmp_path/'stage';backup=tmp_path/'backup'
    old.mkdir();new.mkdir();(old/'value').write_text('old');(new/'value').write_text('new')
    return old,new,backup


def validate(path):
    if (path/'value').read_text()!='new':raise ValueError('INVALID_NEW_CONTENT')
    return {'valid':True}


def test_success_retains_previous_tree(tmp_path):
    old,new,backup=trees(tmp_path);before=pub.tree_hashes(old)
    result=pub.publish_transaction(old,new,backup,before,validate)
    assert (old/'value').read_text()=='new' and (backup/'value').read_text()=='old'
    assert pub.tree_hashes(backup)==before and not new.exists()
    assert result['current_output_hashes']==pub.tree_hashes(old)


def test_invalid_staged_never_changes_current(tmp_path):
    old,new,backup=trees(tmp_path);before=pub.tree_hashes(old);(new/'value').write_text('invalid')
    with pytest.raises(ValueError,match='INVALID_NEW_CONTENT'):pub.publish_transaction(old,new,backup,before,validate)
    assert pub.tree_hashes(old)==before and new.exists() and not backup.exists()


def test_current_change_blocks_before_rename(tmp_path):
    old,new,backup=trees(tmp_path);before=pub.tree_hashes(old);(old/'value').write_text('external edit')
    with pytest.raises(ValueError,match='CURRENT_CHANGED'):pub.publish_transaction(old,new,backup,before,validate)
    assert (old/'value').read_text()=='external edit' and not backup.exists()


def test_install_rename_failure_restores_old(tmp_path):
    old,new,backup=trees(tmp_path);before=pub.tree_hashes(old)
    def rename(a,b):
        if a==new:raise OSError('locked destination')
        return a.rename(b)
    with pytest.raises(RuntimeError,match='ROLLED_BACK'):pub.publish_transaction(old,new,backup,before,validate,rename)
    assert pub.tree_hashes(old)==before and new.exists() and not backup.exists()


def test_post_install_audit_failure_restores_old_and_retains_failed(tmp_path):
    old,new,backup=trees(tmp_path);before=pub.tree_hashes(old)
    def check(path):
        if path==old:raise ValueError('post-install failed')
        return validate(path)
    with pytest.raises(RuntimeError,match='ROLLED_BACK'):pub.publish_transaction(old,new,backup,before,check)
    assert pub.tree_hashes(old)==before and (new.with_name(new.name+'.failed')/'value').read_text()=='new'


def test_existing_backup_is_never_overwritten(tmp_path):
    old,new,backup=trees(tmp_path);backup.mkdir()
    with pytest.raises(ValueError,match='FRESH_BACKUP'):pub.publish_transaction(old,new,backup,pub.tree_hashes(old),validate)
    assert (old/'value').read_text()=='old'


def accepted_repo(tmp_path):
    date='2026-11-11';tests={'tests':999,'failures':0,'errors':0,'skipped':0,'junit_sha256':'b'*64}
    for n in range(6):
        out=tmp_path/f'results/round3-{n}-{date}';proj=out/'projection';proj.mkdir(parents=True)
        for name in pub.FILES:(proj/name).write_text('test data')
        hashes={name:pub.file_sha(proj/name) for name in pub.FILES}
        receipt={'independent_full_rebuilds':2,'output_hashes':hashes,'tests':tests,'census_sha256':'a'*64}
        summary={'task':n,'independent_full_rebuilds':2,'bitwise_identical_files':hashes,'tests':tests,'preexisting_values_and_provenance_unchanged':True}
        (out/'rebuild_receipt.json').write_text(json.dumps(receipt));(out/'summary.json').write_text(json.dumps(summary));(out/'offline-tests.xml').write_text('test fixture')
    control={'accepted':True,'controls':20};(tmp_path/f'results/round3-3-{date}/nt_datum_controls.json').write_text(json.dumps(control))
    return date,tests,control


def test_all_six_receipts_required(tmp_path):
    date,tests,control=accepted_repo(tmp_path)
    result=pub.check_task_receipts(tmp_path,date,lambda p:tests,lambda:control)
    assert len(result['tasks'])==6
    (tmp_path/f'results/round3-2-{date}/rebuild_receipt.json').unlink()
    with pytest.raises(FileNotFoundError):pub.check_task_receipts(tmp_path,date,lambda p:tests,lambda:control)


@pytest.mark.parametrize('case',['output','tests','control','nt-fail','single-rebuild'])
def test_acceptance_tampering_rejected(tmp_path,case):
    date,tests,control=accepted_repo(tmp_path)
    if case=='output':(tmp_path/f'results/round3-1-{date}/projection/summary.json').write_text('tampered')
    if case=='tests':tests=dict(tests,tests=1000)
    if case=='control':control=dict(control,controls=19)
    if case=='nt-fail':
        control={'accepted':False,'controls':20};(tmp_path/f'results/round3-3-{date}/nt_datum_controls.json').write_text(json.dumps(control))
    if case=='single-rebuild':
        p=tmp_path/f'results/round3-4-{date}/rebuild_receipt.json';v=json.loads(p.read_text());v['independent_full_rebuilds']=1;p.write_text(json.dumps(v))
    with pytest.raises(ValueError):pub.check_task_receipts(tmp_path,date,lambda p:tests,lambda:control)
