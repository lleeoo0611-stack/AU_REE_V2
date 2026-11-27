"""Audit and recover the historical SHA-pinned Census inputs without changing the registry."""

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from urllib.parse import urlsplit

from .derived_cache import atomic_json
from .security import public_export
from .source_recovery import LOCK, _impact, _manifest, _NetworkRecovery, _store, recover_census_assets
from .store import canonical, digest, filehash
from .tabular import read_csv


SCHEMA = 'phase10-source-recovery-v1'
RELEASE = Path('results/ree-project-census/coverage-locked-20261125')
ASX_ARCHIVE = Path('results/claims-locators-2026-11-16')
ASX_AUDIT = 'asxpdf_receipt_audit.json'
ASX_REVOCATION = 'asxpdf_proposals_revoked.json'
_ASX_PDF = re.compile(r'/asxpdf/[0-9]{8}/pdf/[a-z0-9]+\.pdf', re.ASCII)


def _approved_asx_hint(url, policy):
    if not isinstance(url, str):
        return False
    try:
        parsed = urlsplit(url)
    except ValueError:
        return False
    return (parsed.scheme == 'https' and parsed.netloc == 'announcements.asx.com.au'
            and parsed.hostname in policy['same_sha_fallback']['approved_hosts']
            and not parsed.query and not parsed.fragment and _ASX_PDF.fullmatch(parsed.path) is not None)


def _archived_asx_hints(root, planned, needed):
    """An archived URL is a lead only; authorization and bytes are checked anew."""
    folder = root / ASX_ARCHIVE
    entries = {row['path']: row['sha256'] for row in read_csv(folder / 'SHA256SUMS.csv')}
    for name in (ASX_AUDIT, ASX_REVOCATION):
        if filehash(folder / name) != entries[name]:
            raise ValueError('HISTORICAL_ASX_LEAD_RECEIPT_SHA_MISMATCH')
    archive = json.loads((folder / ASX_AUDIT).read_bytes())
    revocation = json.loads((folder / ASX_REVOCATION).read_bytes())
    if revocation.get('status') != 'REVOKED' or revocation.get('applied') != 0:
        raise ValueError('HISTORICAL_ASX_REGISTRY_DISPOSITION_CHANGED')
    policy = json.loads((root / 'config/evidence_policy.json').read_bytes())
    candidates = {}
    for hint in archive['evidence']:
        sha, key, url = (hint.get(field) for field in ('receipt_sha256', 'source_key', 'asxpdf_url'))
        if sha not in needed or not _approved_asx_hint(url, policy):
            continue
        matches = [(source, item) for source, item, role in planned[sha]
                   if role == 'snapshot' and source['kind'] == 'pdf' and source['key'] == key]
        if not matches or any(source.get('enabled') is False for source, _ in matches):
            continue
        candidates[sha, url] = matches[0]
    return candidates, {str(ASX_ARCHIVE / name): entries[name] for name in (ASX_AUDIT, ASX_REVOCATION)}


def _fetch_archived_asx(root, planned, needed, directory, budget, timeout, *, exact_urls=None):
    candidates, provenance = _archived_asx_hints(root, planned, needed)
    if exact_urls is not None:
        requested = set(exact_urls.items())
        if not requested <= candidates.keys():
            raise ValueError('ARCHIVED_ASX_BATCH_URL_NOT_CURRENTLY_APPROVED')
        candidates = {key: candidates[key] for key in sorted(requested)}
    directory.mkdir(parents=True, exist_ok=True)
    assets = directory / 'assets'
    if assets.is_symlink():
        raise ValueError('RECOVERY_BATCH_ASSETS_MUST_BE_LOCAL_DIRECTORY')
    assets.mkdir(exist_ok=True)
    transport = _NetworkRecovery(root, directory, budget, timeout)
    attempts = {}
    for (sha, url), (source, item) in sorted(candidates.items()):
        path = assets / sha
        if path.is_symlink():
            raise ValueError('RECOVERY_BATCH_ASSET_MUST_NOT_BE_A_SYMBOLIC_LINK')
        if path.is_file():
            prior_sha = filehash(path)
            if prior_sha == sha:
                continue
            _store(directory / 'versions' / prior_sha, path)
            path.unlink()
            attempts[sha] = [{'status': 'CORRUPT_LOCAL_ASSET_QUARANTINED', 'actual_sha256': prior_sha}]
        if transport.used >= budget:
            break
        result = transport._primary(source, item, url, sha, planned[sha], attempts.setdefault(sha, []))
        if result['status'] == 'EXACT_LOCKED_BYTES' and filehash(path) != sha:
            raise ValueError('ASX_ARCHIVE_RECOVERED_SHA_MISMATCH')
        atomic_json(directory / 'archives_attempted.json', {'attempts': attempts, 'request_slots_used': transport.used})
    return {'archive_file_sha256': provenance, 'candidate_urls': len(candidates),
            'request_slots_used': transport.used, 'attempts': attempts,
            'registry_proposals_applied': 0, 'approval_basis': 'CURRENT_APPROVED_PUBLIC_ASX_HOST_FRESH_EXACT_SHA'}


def stage_recovered_batch(root, manifest, directory, *, request_budget=120, timeout=10):
    """Reacquire only the previously observed exact ASX batch for an artifact."""
    root, manifest, directory = map(lambda path: Path(path).resolve(), (root, manifest, directory))
    if not 1 <= request_budget <= 400 or not 1 <= timeout <= 60:
        raise ValueError('Phase 10 archive reacquisition requires bounded requests and timeout')
    if any(directory.is_relative_to(root / part) for part in ('config', 'data', 'results', 'src')):
        raise ValueError('Recovery batch output must be separate from research inputs and results')
    audit = json.loads(manifest.read_bytes())
    planned, contract = _manifest(root, root / RELEASE)
    batch = audit.get('fresh_asx_asset_sha256', [])
    if (audit.get('schema') != SCHEMA or audit.get('contract') != contract or not batch
            or len(set(batch)) != len(batch) or len(batch) != audit.get('fresh_asx_exact_assets')
            or any(sha not in planned for sha in batch)):
        raise ValueError('ARCHIVED_ASX_BATCH_CONTRACT_MISMATCH')
    eligible = {}
    for row in audit['assets']:
        sha = row['expected_sha256']
        if sha not in batch:
            continue
        proof = row.get('exact_download') or {}
        if (row.get('status') != 'AVAILABLE_EXACT_ORIGINAL' or row.get('observed_sha256') != sha
                or proof.get('status') != 'EXACT_LOCKED_BYTES' or proof.get('actual_sha256') != sha
                or not proof.get('url') or sha in eligible):
            raise ValueError('ARCHIVED_ASX_BATCH_EVIDENCE_MISMATCH')
        eligible[sha] = proof['url']
    if eligible.keys() != set(batch):
        raise ValueError('ARCHIVED_ASX_BATCH_EVIDENCE_MISMATCH')
    assets = directory / 'assets'
    if assets.is_symlink() or assets.is_dir() and any(path.name not in eligible for path in assets.iterdir()):
        raise ValueError('ARCHIVED_ASX_BATCH_DIRECTORY_HAS_UNEXPECTED_ASSETS')
    acquired = _fetch_archived_asx(root, planned, set(batch), directory, request_budget, timeout, exact_urls=eligible)
    entries = []
    for sha in sorted(batch):
        path = directory / 'assets' / sha
        attempts = acquired['attempts'].get(sha, [])
        row = {'expected_sha256': sha, 'requested_url': eligible[sha], 'attempts': attempts}
        if path.is_file() and not path.is_symlink() and filehash(path) == sha:
            row.update(status='AVAILABLE_EXACT_ORIGINAL', observed_sha256=sha,
                       bytes=path.stat().st_size, asset=f'assets/{sha}')
        else:
            row.update(status='SOURCE_UNAVAILABLE', reason=attempts[-1]['status'] if attempts else 'NOT_ATTEMPTED_BUDGET')
        entries.append(row)
    verified = sum(row['status'] == 'AVAILABLE_EXACT_ORIGINAL' for row in entries)
    result = {'schema': 'phase10-source-batch-v1', 'manifest_sha256': filehash(manifest),
              'status': 'COMPLETE' if verified == len(batch) else 'PARTIAL_SOURCE_UNAVAILABLE',
              'expected': len(batch), 'verified': verified, 'source_unavailable': len(batch) - verified,
              'request_slots_used': acquired['request_slots_used'], 'entries': entries}
    atomic_json(directory / 'reacquire_receipt.json', result)
    return result


def _bindings(planned, sha):
    rows = {}
    projects = set()
    for source, item, role in planned[sha]:
        projects.update(source.get('summary_project_ids') or ())
        detail = public_export({
            'source_key': source['key'], 'kind': source['kind'], 'role': role,
            'original_url': item.get('url') or source.get('url'),
            'source_version': source.get('source_document_version') or source['sha256'],
            'publication_date': source.get('publication_date'), 'available_date': source.get('available_date'),
            'historical_acquired_at': source.get('acquired_at'), 'download_enabled': source.get('enabled') is not False,
        })
        rows[canonical(detail)] = detail
    return [rows[key] for key in sorted(rows)], projects


def _failure(attempts, bindings, reason):
    remote = [item for item in attempts if item.get('url') and item['status'] != 'EXACT_LOCKED_BYTES']
    if not any(row['download_enabled'] for row in bindings):
        return 'LOCKED_SOURCE_DISABLED', bindings[0]['original_url']
    changed = [item for item in remote if item['status'] == 'DISTINCT_VERSION_RETAINED']
    if changed:
        return 'DIFFERENT_EDITION_SHA', changed[-1]['url']
    if remote:
        last = remote[-1]
        return last['status'], last['url']
    return reason or 'EXACT_HISTORICAL_ORIGINAL_UNAVAILABLE', bindings[0]['original_url']


def _verify_receipts(recovered, planned, work):
    rows = {row['locked_sha256']: row for row in recovered['receipts']}
    if set(rows) != set(planned) or len(rows) != len(recovered['receipts']):
        raise ValueError('HISTORICAL_RECOVERY_INVENTORY_MISMATCH')
    exact = {sha for sha, row in rows.items() if row['status'] == 'VERIFIED'}
    if (len(exact) != recovered['verified'] or sorted(rows.keys() - exact) != recovered['missing_sha256']
            or len(rows) != recovered['expected'] or len(rows) - len(exact) != recovered['missing']):
        raise ValueError('HISTORICAL_RECOVERY_COUNTS_MISMATCH')
    if any((work / 'assets' / sha).is_symlink() or filehash(work / 'assets' / sha) != sha for sha in exact):
        raise ValueError('REOPENED_HISTORICAL_ORIGINAL_SHA_MISMATCH')
    return rows, exact


def _frozen_inputs(root, exact):
    path = root / LOCK
    entries = json.loads(path.read_bytes())
    required = {item['sha256'] for row in entries for item in (row, *row.get('original_responses', ()))}
    return {'cutoff': '2026-11-05', 'lock': LOCK, 'lock_sha256': filehash(path),
            'snapshot_entries': len(entries), 'required_source_assets': len(required),
            'verified_source_assets': len(required & exact), 'unavailable_sha256': sorted(required - exact),
            'required_sha256': sorted(required)}


def write_reports(root, output, *, work, recovery, archive=None, previous=None,
                  original_fetch=None, replay=None):
    """Write portable evidence and impact, reopening the reported exact bytes."""
    root, output, work = map(lambda path: Path(path).resolve(), (root, output, work))
    planned, contract = _manifest(root, root / RELEASE)
    if contract != recovery['contract']:
        raise ValueError('HISTORICAL_RECOVERY_CONTRACT_MISMATCH')
    rows, exact = _verify_receipts(recovery, planned, work)
    impact, impact_files = _impact(root, root / RELEASE, set(planned))
    previous_missing = set(previous['missing_sha256']) if previous is not None else set()
    if previous is not None and previous['contract'] != contract:
        raise ValueError('HISTORICAL_COMPARISON_CONTRACT_MISMATCH')
    if original_fetch is not None and original_fetch['contract'] != contract:
        raise ValueError('HISTORICAL_FETCH_RECEIPT_CONTRACT_MISMATCH')
    registry_attempts = {row['locked_sha256']: row for row in (original_fetch or {}).get('receipts', ())}
    archive = archive or {}
    manifest, missing = {}, {}
    for sha in sorted(rows):
        row = rows[sha]
        bindings, declared_projects = _bindings(planned, sha)
        references = impact[sha]
        projects = sorted(declared_projects.union(references['projects']))
        attempts = [*row.get('attempts', ()), *archive.get('attempts', {}).get(sha, ())]
        versions = [item for item in attempts if item['status'] == 'DISTINCT_VERSION_RETAINED']
        record = {'expected_sha256': sha, 'locked_sources': bindings, 'project_ids': projects,
                  'project_ids_in_source_registry': sorted(declared_projects),
                  'project_ids_in_historical_lineage': references['projects'],
                  'new_vs_prior_same_contract': sha in previous_missing and sha in exact}
        if sha in exact:
            confirmed = next((item for item in reversed(attempts) if item['status'] == 'EXACT_LOCKED_BYTES'), None)
            record.update(status='AVAILABLE_EXACT_ORIGINAL', observed_sha256=sha,
                          method='FRESH_APPROVED_PUBLIC_SOURCE' if confirmed else row.get('method'),
                          asset=f'assets/{sha}', exact_download=confirmed)
        else:
            reason = registry_attempts.get(sha, {}).get('reason') or row.get('reason')
            failure_type, failure_url = _failure(attempts, bindings, reason)
            record.update(status='SOURCE_UNAVAILABLE', failure_type=failure_type, failure_url=failure_url,
                          reason=reason, **references)
            missing[sha] = record
        if attempts:
            record['acquisition_attempts'] = attempts
        if versions:
            record['distinct_sha256'] = sorted({item['actual_sha256'] for item in versions})
        manifest[sha] = record
    direct_counts = {field: len({tuple(item) if isinstance(item, (list, tuple)) else item
                                for record in missing.values() for item in record[field]})
                     for field in next(iter(impact.values()))} if impact else {}
    historical_fetch_slots = ((original_fetch or {}).get('request_slots_used', 0)
                              if original_fetch is not None else recovery.get('request_slots_used', 0))
    fresh_asx = {sha: attempt for sha, history in archive.get('attempts', {}).items() for attempt in history
                 if sha in exact and attempt['status'] == 'EXACT_LOCKED_BYTES' and attempt['actual_sha256'] == sha}
    subset_inputs = _frozen_inputs(root, exact)
    audit = {'schema': SCHEMA, 'observed_at': datetime.now(timezone.utc).isoformat(), 'contract': contract,
             'historical_release': RELEASE.as_posix(), 'locked_assets': len(planned),
             'verified_assets': len(exact), 'source_unavailable': len(missing),
             'verified_asset_inventory_sha256': digest(sorted(exact)),
             'prior_verified_assets_same_contract': len(planned) - len(previous_missing) if previous is not None else None,
             'verified_without_fresh_asx_batch': len(exact) - len(fresh_asx),
             'fresh_asx_exact_assets': len(fresh_asx),
             'fresh_asx_asset_sha256': sorted(fresh_asx),
             'fresh_asx_exact_bytes': sum(attempt['content_bytes'] for attempt in fresh_asx.values()),
             'net_new_exact_vs_prior': len(exact & previous_missing) if previous is not None else None,
             'requests': {'registry_slots_used': historical_fetch_slots,
                          'archived_asx_slots_used': archive.get('request_slots_used', 0),
                          'archived_asx_candidates': archive.get('candidate_urls', 0),
                          'registry_proposals_applied': 0},
             'archived_asx_proof_sha256': archive.get('archive_file_sha256', {}),
             'source_unavailable_kind_counts': dict(Counter(record['locked_sources'][0]['kind'] for record in missing.values())),
             'source_unavailable_reason_counts': dict(Counter(record['failure_type'] for record in missing.values())),
             'direct_historical_impacts': direct_counts, 'impact_inputs_sha256': impact_files,
             'historical_93': {
                 'cutoff': contract['cutoff'],
                 'status': 'BLOCKED_MISSING_ASSETS' if missing else 'READY_FOR_SEPARATE_FORMAL_REPLAY',
                 'projects_in_historical_release': 93,
             },
             'verified_subset_source_inputs': subset_inputs,
             'verified_subset_replay': replay or {'status': 'NOT_INVOKED'},
             'assets': [manifest[key] for key in sorted(manifest)], 'missing_assets': missing}
    output.mkdir(parents=True, exist_ok=True)
    atomic_json(output / 'source_recovery_manifest.json', audit)
    (output / 'source_recovery_report.md').write_text(_report(audit), encoding='utf8')
    return audit


def _report(audit):
    requests = audit['requests']
    impacts = audit['direct_historical_impacts']
    counts = {'PDF': 'pdf', '政府 WFS': 'government_wfs', '政府 CSV': 'government_csv'}
    kinds = '、'.join(f'{kind} {audit["source_unavailable_kind_counts"].get(key, 0)} 份' for kind, key in counts.items())
    lines = [
        '# 第十階段歷史來源核驗', '',
        f'2026-11-13 歷史鎖定清單有 **{audit["locked_assets"]} 份**不重複原件。'
        f'本輪由來源或本機庫重開原始位元組核驗 **{audit["verified_assets"]} 份**，其餘 **{audit["source_unavailable"]} 份**維持 `SOURCE_UNAVAILABLE`。',
        '',
    ]
    if audit['net_new_exact_vs_prior'] is not None:
        lines.extend([f'相同鎖定清單相較前一次原件庫多核驗 **{audit["net_new_exact_vs_prior"]} 份**。', ''])
    lines.extend([
        f'登記來源取得使用 {requests["registry_slots_used"]} 個請求額度。歷史 ASX 收據提供 '
        f'{requests["archived_asx_candidates"]} 個待重驗的公開網址，實際使用 {requests["archived_asx_slots_used"]} 個額度。'
        '每個網址依現行核准主機、robots、節流、重試及檔案大小規則取得，再核對鎖定 SHA。歷史 ASX 登記提案維持撤銷。',
        '',
        f'不計本輪 ASX 批次時，已核驗 {audit["verified_without_fresh_asx_batch"]} 份。ASX 批次另取得 '
        f'{audit["fresh_asx_exact_assets"]} 份相符原件，共 {audit["fresh_asx_exact_bytes"]:,} bytes。'
        '原件置於執行工作庫，報告保留可重跑的官方網址、取回時間、檔案大小及原始 SHA。',
        '',
        f'未取得原件包括 {kinds}。同網址的新位元組另以實際 SHA 保存；歷史證據仍引用原 SHA。'
        '清單保留每個缺件的來源鍵、Project ID、版本、日期、原網址、嘗試網址與失敗類型。',
        '',
        f'既有歷史輸出直接引用缺件的範圍包括 **{impacts.get("projects", 0)} 個 Project**、'
        f'{impacts.get("census_fields", 0)} 個 Census 欄位、{impacts.get("resource_observations", 0)} 筆資源觀測、'
        f'{impacts.get("candidates", 0)} 筆影子候選與 {impacts.get("analysis_inputs", 0)} 筆 MCDA 準則來源鏈。'
        f'直接牽涉 {impacts.get("direct_panels", 0)} 個面板，另列可能受影響的重選值範圍。'
        '歷史 C1 參照保留原義，現行正式 C1 依本輪 disabled 政策。',
        '',
        f'完整 93 案 2026-11-13 重建狀態為 `{audit["historical_93"]["status"]}`。',
        '',
    ])
    subset_inputs = audit['verified_subset_source_inputs']
    lines.extend([
        f'截日 **{subset_inputs["cutoff"]}** 的 Phase 22 鎖檔共 '
        f'{subset_inputs["snapshot_entries"]} 筆快照，核驗 '
        f'{subset_inputs["verified_source_assets"]}／{subset_inputs["required_source_assets"]} 份必需原件。', '',
    ])
    subset = audit['verified_subset_replay']
    if subset['status'] == 'COMPLETED':
        lines.extend([
            f'另執行截日 **{subset["cutoff"]}** 的鎖定 Phase 22 可重播範圍，核驗 '
            f'{subset["verified_source_assets"]} 份原件及 {subset["completed_panels"]} 組 MCDA 面板。'
            f'SQLite 完整性為 `{subset["sqlite_integrity"]}`，外鍵違規 {subset["sqlite_foreign_key_violations"]} 筆。'
            'Census、矩陣、排名、Project ID 簽章及實際命令見重播收據。', '',
        ])
    else:
        lines.extend([f'可重播子集執行狀態為 `{subset["status"]}`。', ''])
    lines.extend([
        '附入合法持有的先前資產庫後，可循現行政策重跑完整來源檢查。', '', '```sh',
        'python -m au_ree_v2.phase10_recovery --online --work work/historical-recovery \\',
        '  --library VERIFIED_ASSET_LIBRARY --out work/phase10-recovery-report', '```', '',
        '可獨立重取本輪已核驗的 ASX 批次供保存。', '', '```sh',
        'python -m au_ree_v2.phase10_recovery \\',
        '  --reacquire-archive-manifest results/phase10-2026-11-27/source_recovery_manifest.json \\',
        '  --out work/phase10-original-batch --request-budget 80 --timeout 10', '```', '',
        '[逐件狀態、來源與影響](source_recovery_manifest.json)',
    ])
    return '\n'.join(lines) + '\n'


def run(root, output, *, work, libraries=(), online=False, request_budget=120, timeout=10,
        previous=None, archive_work=None, original_fetch=None, replay=None):
    """Resume the historical byte library and regenerate portable Phase 10 receipts."""
    root, work = Path(root).resolve(), Path(work).resolve()
    if not 1 <= request_budget <= 400 or not 1 <= timeout <= 60:
        raise ValueError('Phase 10 recovery requires bounded requests and timeout')
    selected_archive = (Path(archive_work).resolve() if archive_work is not None
                        else work.with_name(work.name + '-approved-asx'))
    archive_receipt = selected_archive / 'archive_receipt.json'
    archive = json.loads(archive_receipt.read_bytes()) if archive_receipt.is_file() else {}
    libraries = tuple(libraries)
    if (selected_archive / 'assets').is_dir():
        libraries += (selected_archive / 'assets',)
    local = recover_census_assets(root, RELEASE, work, libraries=libraries, request_budget=request_budget, timeout=timeout)
    result = local
    if online and local['missing']:
        planned, _ = _manifest(root, root / RELEASE)
        fresh = _fetch_archived_asx(root, planned, set(local['missing_sha256']), selected_archive, request_budget, timeout)
        old_attempts = archive.get('attempts', {})
        fresh['attempts'] = {sha: [*old_attempts.get(sha, ()), *fresh['attempts'].get(sha, ())]
                             for sha in sorted(old_attempts.keys() | fresh['attempts'].keys())}
        archive = fresh
        atomic_json(archive_receipt, archive)
        remaining = request_budget - archive['request_slots_used']
        result = recover_census_assets(root, RELEASE, work,
                                       libraries=tuple(dict.fromkeys((*libraries, selected_archive / 'assets'))),
                                       online=remaining > 0, request_budget=max(remaining, 1), timeout=timeout)
    return write_reports(root, output, work=work, recovery=result, archive=archive,
                         previous=previous, original_fetch=original_fetch, replay=replay)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', default='.', type=Path)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--work', type=Path)
    parser.add_argument('--reacquire-archive-manifest', type=Path,
                        help='Archive only the explicitly verified public ASX batch recorded by this manifest')
    parser.add_argument('--library', action='append', default=[], type=Path)
    parser.add_argument('--archive-work', type=Path)
    parser.add_argument('--prior-receipt', type=Path)
    parser.add_argument('--registry-receipt', type=Path)
    parser.add_argument('--replay-receipt', type=Path)
    parser.add_argument('--online', action='store_true')
    parser.add_argument('--request-budget', default=120, type=int)
    parser.add_argument('--timeout', default=10, type=int)
    args = parser.parse_args()
    if args.reacquire_archive_manifest:
        if any((args.work, args.library, args.archive_work, args.prior_receipt, args.registry_receipt,
                args.replay_receipt, args.online)):
            parser.error('Archive batch reacquisition accepts only its manifest, output and request limits')
        result = stage_recovered_batch(args.root, args.reacquire_archive_manifest, args.out,
                                       request_budget=args.request_budget, timeout=args.timeout)
        print(canonical({k: result[k] for k in ('status', 'expected', 'verified', 'source_unavailable', 'request_slots_used')}))
        return
    if args.work is None:
        parser.error('Historical recovery requires --work')
    optional = {'previous': args.prior_receipt, 'original_fetch': args.registry_receipt, 'replay': args.replay_receipt}
    result = run(args.root, args.out, work=args.work, libraries=args.library, archive_work=args.archive_work,
                 online=args.online, request_budget=args.request_budget, timeout=args.timeout,
                 **{key: json.loads(path.read_bytes()) for key, path in optional.items() if path is not None})
    print(canonical({k: result[k] for k in ('locked_assets', 'verified_assets', 'source_unavailable', 'historical_93')}))


if __name__ == '__main__':
    main()
