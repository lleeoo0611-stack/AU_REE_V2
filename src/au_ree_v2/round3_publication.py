"""Fail-closed release receipts and rollback-capable same-filesystem publication."""
import hashlib
import json
from pathlib import Path

FILES = ('專案總表.csv', 'field_provenance.csv', 'missing_fields.csv', 'census_inventory.csv', 'summary.json', 'audit.json')


def file_sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def tree_hashes(folder):
    folder=Path(folder)
    return {p.relative_to(folder).as_posix():file_sha(p) for p in sorted(folder.rglob('*')) if p.is_file()}


def json_read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def check_task_receipts(repo, date, tests_pass, verify_nt):
    """Recheck all accepted task receipts, exact tests, outputs and fresh NT controls.

    tests_pass must parse JUnit and reject any skip/failure/error, as the runner's
    existing gate does. verify_nt recomputes controls from hash-verified archives,
    never merely reads the previously accepted report.
    """
    repo=Path(repo); records=[]; census=set()
    for number in range(6):
        folder=repo/f'results/round3-{number}-{date}'
        receipt=json_read(folder/'rebuild_receipt.json'); summary=json_read(folder/'summary.json')
        if receipt.get('independent_full_rebuilds')!=2 or summary.get('independent_full_rebuilds')!=2:
            raise ValueError('ROUND3_PUBLICATION_DOUBLE_REBUILD_REQUIRED')
        expected=receipt.get('output_hashes',{})
        if set(expected)!=set(FILES) or any(file_sha(folder/'projection'/name)!=expected[name] for name in FILES):
            raise ValueError('ROUND3_PUBLICATION_ACCEPTED_OUTPUT_CHANGED')
        if summary.get('bitwise_identical_files')!=expected:
            raise ValueError('ROUND3_PUBLICATION_SUMMARY_RECEIPT_MISMATCH')
        tests=tests_pass(folder/'offline-tests.xml')
        if tests!=receipt.get('tests') or tests!=summary.get('tests'):
            raise ValueError('ROUND3_PUBLICATION_TEST_RECEIPT_CHANGED')
        if summary.get('task')!=number or summary.get('preexisting_values_and_provenance_unchanged') is not True:
            raise ValueError('ROUND3_PUBLICATION_TASK_ACCEPTANCE_REQUIRED')
        sha=receipt.get('census_sha256')
        if not isinstance(sha,str) or len(sha)!=64:
            raise ValueError('ROUND3_PUBLICATION_CENSUS_SHA_REQUIRED')
        census.add(sha);records.append(summary)
    if len(census)!=1:
        raise ValueError('ROUND3_PUBLICATION_CENSUS_CHANGED')
    control=json_read(repo/f'results/round3-3-{date}/nt_datum_controls.json')
    fresh=verify_nt()
    if control!=fresh:
        raise ValueError('ROUND3_PUBLICATION_CONTROL_REPORT_CHANGED')
    if control.get('accepted') is not True or control.get('controls',0)<3:
        raise ValueError('ROUND3_PUBLICATION_NT_ACCEPTANCE_REQUIRED')
    return dict(tasks=records,census_sha256=next(iter(census)),nt_datum_controls=control)


def _plain_directory(path):
    return path.is_dir() and not path.is_symlink() and not (hasattr(path,'is_junction') and path.is_junction())


def publish_transaction(current, staged, backup, expected_current_hashes, validate, rename=None):
    """Validate before rename; retain old tree and recover on installation failure.

    This is NOT a single atomic exchange on Windows. Two same-filesystem renames
    have a brief absent-current interval. No tree is deleted. On rollback a
    failed newly-installed tree is retained at '<staged>.failed'.
    """
    current,staged,backup=map(lambda p:Path(p).absolute(),(current,staged,backup))
    failed=staged.with_name(staged.name+'.failed')
    if len({current,staged,backup,failed})!=4 or len({p.parent.resolve() for p in (current,staged,backup)})!=1:
        raise ValueError('ROUND3_PUBLICATION_SIBLING_DIRECTORIES_REQUIRED')
    if not _plain_directory(current) or not _plain_directory(staged):
        raise ValueError('ROUND3_PUBLICATION_PLAIN_DIRECTORIES_REQUIRED')
    if backup.exists() or failed.exists():
        raise ValueError('ROUND3_PUBLICATION_FRESH_BACKUP_REQUIRED')
    rename=rename or (lambda a,b:a.rename(b))
    if tree_hashes(current)!=expected_current_hashes:
        raise ValueError('ROUND3_PUBLICATION_CURRENT_CHANGED')
    staged_validation=validate(staged)
    expected_new=tree_hashes(staged)
    if tree_hashes(current)!=expected_current_hashes:
        raise ValueError('ROUND3_PUBLICATION_CURRENT_CHANGED_DURING_VALIDATION')
    # Rename must never replace an existing destination.
    rename(current,backup)
    try:
        rename(staged,current)
        if tree_hashes(current)!=expected_new:
            raise ValueError('ROUND3_PUBLICATION_INSTALLED_HASH_MISMATCH')
        installed_validation=validate(current)
        if installed_validation!=staged_validation:
            raise ValueError('ROUND3_PUBLICATION_AUDIT_CHANGED')
        if tree_hashes(backup)!=expected_current_hashes:
            raise ValueError('ROUND3_PUBLICATION_BACKUP_CHANGED')
    except Exception as cause:
        try:
            if current.exists():
                rename(current,failed)
            rename(backup,current)
            if tree_hashes(current)!=expected_current_hashes:
                raise ValueError('RESTORED_CURRENT_HASH_MISMATCH')
        except Exception as recovery:
            raise RuntimeError('ROUND3_PUBLICATION_ROLLBACK_INCOMPLETE: inspect current, backup and staging before retry') from recovery
        raise RuntimeError('ROUND3_PUBLICATION_FAILED_ROLLED_BACK: old current restored; failed artifacts retained') from cause
    return dict(status='PUBLISHED_VALIDATED_ROLLBACK_CAPABLE_SWAP',backup_path=str(backup),
                current_output_hashes=expected_new,previous_current_hashes=expected_current_hashes,
                publication_audit=installed_validation)
