"""Recover byte-pinned Census replay inputs in disposable local storage."""

from collections import Counter, defaultdict
from datetime import datetime, timezone
from hashlib import file_digest, sha256
import json
from pathlib import Path, PurePosixPath
import re
from shutil import copyfile
from tempfile import NamedTemporaryFile
from urllib.parse import urlsplit
from zipfile import BadZipFile, ZipFile

from .acquisition import (
    ASIC_REGISTER_KIND, STRICT_HOSTS, SameSHAAlternates, StrictTransport,
    asic_capture_date, declared_json_hash, strict_failure_status, wamex_report_documents,
)
from .derived_cache import atomic_json
from .security import public_export, sensitive_reference
from .store import digest, filehash
from .tabular import read_csv


VERSION = "census-source-recovery-v1"
LOCK = "results/phase22-2026-11-06/snapshot_lock.json"
SHA = re.compile(r"[0-9a-f]{64}")
PUBLIC_ORIGINALS = {"pdf", "html", "government_csv", "government_wfs", ASIC_REGISTER_KIND}
EVIDENCE_HASHES = {
    "source_sha", "source_sha256", "coordinate_source_sha256", "layer_sha256", "page_extraction_sha256",
}


def _now():
    return datetime.now(timezone.utc).isoformat()


def _sha(path):
    with path.open('rb') as stream:
        return file_digest(stream, 'sha256').hexdigest()


def _manifest(root, release):
    seal = json.loads((release / 'bundle_verification.json').read_bytes())
    paths = {'manifest_sha256': release / 'asset_manifest.json',
             'receipt_sha256': release / 'source_acquisition.json', 'lock_sha256': root / LOCK}
    if seal['manifest_version'] != 2 or any(filehash(path) != seal[key] for key, path in paths.items()):
        raise ValueError('Census recovery bundle checksum or format mismatch')
    receipt = json.loads(paths['receipt_sha256'].read_bytes())
    sources = defaultdict(list)
    counts = Counter()
    for collection, rows in (('receipt', receipt['snapshots']), ('frozen', json.loads(paths['lock_sha256'].read_bytes()))):
        for source in rows:
            entries = [('snapshot', source), *(('original_response', item) for item in source.get('original_responses', ()))]
            for role, item in entries:
                sha = item['sha256']
                if not SHA.fullmatch(sha):
                    raise ValueError('Invalid locked asset fingerprint')
                counts[collection, role, source['key'], source['kind'], source['sha256'], sha] += 1
                sources[sha].append((source, item, role))
    manifest = json.loads(paths['manifest_sha256'].read_bytes())
    actual = Counter((r['collection'], r['role'], r['key'], r['kind'], r['owning_snapshot_sha256'],
                      r['sha256']) for r in manifest)
    if (counts != actual or len(manifest) != seal['references'] or len(sources) != seal['assets']
            or any(r['asset'] != 'assets/' + r['sha256'] for r in manifest)):
        raise ValueError('Census asset manifest differs from the replay locks')
    return sources, {key: seal[key] for key in paths} | {'cutoff': receipt['cutoff']}


def _contained(path, anchor):
    return path.resolve().is_relative_to(anchor)


def _store(path, data):
    """Publish validated bytes atomically. Existing exact files are immutable."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise ValueError('Recovery target must not be a symbolic link')
    with NamedTemporaryFile(dir=path.parent, prefix='.recover-', delete=False) as stream:
        staging = Path(stream.name)
    try:
        if isinstance(data, bytes):
            staging.write_bytes(data)
        else:
            copyfile(data, staging)
        if _sha(staging) != path.name:
            raise ValueError('Recovery input changed while copying')
        if path.exists() and _sha(path) != path.name:
            raise ValueError('Refuse to overwrite differently hashed recovery bytes')
        if not path.exists():
            staging.replace(path)
    finally:
        staging.unlink(missing_ok=True)


def _archive_members(path, planned, paths):
    """Read only bounded SHA-named members by bytes, without extracting ZIP paths."""
    with ZipFile(path) as archive:
        for entry in archive.infolist():
            address = PurePosixPath(entry.filename)
            name = address.stem
            if (entry.is_dir() or address.is_absolute() or '..' in address.parts or '\\' in entry.filename
                    or name not in planned or name in paths or entry.file_size > 256 * 1024**2):
                continue
            try:
                with archive.open(entry) as stream:
                    if file_digest(stream, 'sha256').hexdigest() == name:
                        paths[name] = (path, entry.filename)
            except (BadZipFile, OSError, RuntimeError):
                continue


def _local_paths(root, planned, libraries):
    """Index explicit, shallow archive libraries and tracked snapshot paths."""
    paths = {}
    checked = set()
    for library in (*libraries, root / 'data/snapshots'):
        if library.is_file():
            try:
                actual = _sha(library)
                if actual in planned:
                    paths.setdefault(actual, library)
                else:
                    _archive_members(library, planned, paths)
            except (BadZipFile, OSError):
                pass
            continue
        if not library.is_dir():
            continue
        for candidate in sorted(library.iterdir()):
            if not candidate.is_file() or not _contained(candidate, library):
                continue
            if SHA.fullmatch(candidate.stem) and candidate.stem not in planned:
                continue
            checked.add(candidate)
            if candidate.stem in paths:
                continue
            sha = _sha(candidate)
            if sha in planned:
                paths.setdefault(sha, candidate)
    for bindings in planned.values():
        for _, item, _ in bindings:
            candidate = root / item['path']
            if candidate not in checked and _contained(candidate, root) and candidate.is_file():
                checked.add(candidate)
                actual = _sha(candidate)
                if actual in planned:
                    paths.setdefault(actual, candidate)
    return paths


def _document_format(raw, kind, headers):
    """Reject intermediate landing/interstitial responses as documents."""
    if kind == 'pdf':
        return raw.startswith(b'%PDF')
    if kind == ASIC_REGISTER_KIND:
        return raw.startswith(b'PK')
    if kind == 'government_wfs':
        return raw.lstrip().startswith((b'{', b'[', b'<?xml', b'<wfs:'))
    if kind == 'government_csv':
        return bool(raw.strip()) and not raw.lstrip().startswith(b'<')
    content = str(headers.get('Content-Type', '')).casefold()
    sample = raw[:200000]
    return ('html' in content and not re.search(
        br'<form[^>]*(?:login|consent|terms)|terms\s+(?:and\s+conditions|of\s+use)|'
        br'<(?:title|h1)[^>]*>[^<]*(?:consent|log.?in|sign.?in)', sample, re.I))


def _policy_result(raw, source, item):
    rule = item.get('hash_policy') or source.get('hash_policy')
    if not rule:
        return {'hash_policy': 'BYTE_SHA256'}
    keys = item.get('hash_drop_keys') or source.get('hash_drop_keys')
    content, metadata = declared_json_hash(raw, {'hash_policy': rule, 'hash_drop_keys': keys})
    expected = item.get('content_sha256') or source.get('content_sha256')
    return {**metadata, 'locked_content_sha256': expected,
            'content_policy_match': content == expected if expected else None}


def _verify_policy(data, bindings):
    policies = {}
    for source, item, _ in bindings:
        if not (source.get('hash_policy') or item.get('hash_policy')):
            continue
        detail = _policy_result(data, source, item)
        if detail.get('content_policy_match') is False:
            raise ValueError('RECOVERED_ASSET_CONTENT_POLICY_MISMATCH')
        policies[source['key']] = detail
    return policies


def _record_inputs(bindings):
    fields = ('source_key', 'kind', 'role', 'locked_sha256', 'url', 'publication_date',
              'available_date', 'historical_acquired_at')
    values = {(source['key'], source['kind'], role, item['sha256'], item.get('url') or source.get('url') or '',
               source.get('publication_date') or '', source.get('available_date') or '', source.get('acquired_at') or '')
              for source, item, role in bindings}
    return public_export([dict(zip(fields, row, strict=True)) for row in sorted(values)])


class _NetworkRecovery:
    def __init__(self, root, output, request_budget, timeout):
        self.root = root
        self.output = output
        self.used = 0
        self.budget = request_budget
        self.timeout = timeout
        self.primary = StrictTransport({**STRICT_HOSTS, 'publicdata.au': 'pinned-asic-archive'})
        self.alternates = SameSHAAlternates(root, self.primary)
        if not self.alternates.policy.get('enabled'):
            self.primary.before_request = lambda url: self.alternates.check(url, self.primary, False)
        for transport in (self.primary, self.alternates.transport):
            before = transport.before_request

            def bounded(url, authorize=before):
                parsed = urlsplit(url)
                if parsed.username or parsed.password or sensitive_reference(url):
                    raise ValueError('SENSITIVE_OR_AUTHENTICATED_SOURCE_URL')
                if self.used >= self.budget:
                    raise ValueError('RECOVERY_REQUEST_BUDGET_EXHAUSTED')
                self.used += 1
                authorize(url)

            transport.before_request = bounded
        self.seen = {}

    def observe(self, raw, source, item, url, headers, expected, bindings, receiver):
        actual = sha256(raw).hexdigest()
        detail = {'url': url, 'observed_at': _now(), 'source_key': source['key'],
                  'actual_sha256': actual, 'content_bytes': len(raw),
                  'http_last_modified': headers.get('Last-Modified'), 'content_type': headers.get('Content-Type')}
        try:
            detail.update(_policy_result(raw, source, item))
        except ValueError as exc:
            detail['content_policy_error'] = str(exc)
        if not _document_format(raw, source['kind'], headers):
            detail.update(status='NOT_PDF' if source['kind'] == 'pdf' else 'NOT_SOURCE_PAYLOAD',
                          historical_eligible=False)
        elif actual == expected:
            _verify_policy(raw, bindings)
            if source['kind'] == ASIC_REGISTER_KIND:
                local = self.output / 'versions' / actual
                _store(local, raw)
                detail['archived_capture_date'] = asic_capture_date(self.root, source, local, actual)
            _store(self.output / 'assets' / expected, raw)
            detail.update(status='EXACT_LOCKED_BYTES', historical_eligible=True,
                          locked_publication_date=source.get('publication_date'))
        else:
            _store(self.output / 'versions' / actual, raw)
            detail.update(status='DISTINCT_VERSION_RETAINED', historical_eligible=False,
                          candidate_publication_date=None, version_path='versions/' + actual)
        receiver.append(public_export(detail))
        return actual

    def _primary(self, source, item, url, expected, bindings, attempts):
        if url in self.seen:
            cached = self.seen[url]
            for record in sorted(cached, key=lambda row: row.get('actual_sha256') != expected):
                if record['status'] not in {'EXACT_LOCKED_BYTES', 'DISTINCT_VERSION_RETAINED'}:
                    continue
                relative = record.get('version_path') or ('assets/' + record['actual_sha256'])
                data = (self.output / relative).read_bytes()
                self.observe(data, source, item, record['url'],
                             {'Content-Type': record.get('content_type'), 'Last-Modified': record.get('http_last_modified')},
                             expected, bindings, attempts)
                attempts[-1]['reused_network_response'] = True
                return attempts[-1]
            attempts.extend(cached)
            return attempts[-1]
        checkpoint = len(attempts)
        host = urlsplit(url).hostname
        self.primary.http.pop(host, None)
        try:
            maximum = 100_000_000 if source['kind'] == ASIC_REGISTER_KIND else 30_000_000
            if host == 'wamex.dmp.wa.gov.au' and '/ReportDetails' in url:
                for raw, headers, document_url in wamex_report_documents(self.primary, url, timeout=self.timeout):
                    resolved = getattr(self.primary, 'resolved_url', document_url)
                    self.observe(raw, source, item, resolved, headers, expected, bindings, attempts)
                    if attempts[-1]['status'] == 'EXACT_LOCKED_BYTES':
                        break
                if len(attempts) == checkpoint:
                    raise ValueError('WAMEX_NO_ELIGIBLE_DOCUMENT')
            else:
                raw, headers = self.primary(url, timeout=self.timeout,
                                            max_bytes=min(source.get('max_bytes', maximum), maximum))
                self.observe(raw, source, item, self.primary.resolved_url, headers, expected, bindings, attempts)
            if host == 'www.asx.com.au' and attempts[-1]['status'] == 'NOT_PDF':
                self.primary.stopped[host] = 'NOT_PDF'
        except (OSError, ValueError) as exc:
            attempts.append(public_export({
                'url': url, 'observed_at': _now(), 'source_key': source['key'],
                'status': strict_failure_status(exc), 'reason': str(exc),
                'http_status': self.primary.http.get(host), 'historical_eligible': False,
            }))
        self.seen[url] = attempts[checkpoint:]
        return attempts[-1]

    def recover(self, expected, bindings, attempts):
        seen = set()
        start = len(attempts)
        for source, item, role in bindings:
            if self.used >= self.budget:
                return 'RECOVERY_REQUEST_BUDGET_EXHAUSTED'
            url = item.get('url') or source.get('url')
            if (source['kind'] not in PUBLIC_ORIGINALS or source.get('enabled') is False
                    or not url or url in seen or urlsplit(url).hostname not in self.primary.hosts
                    or (role == 'snapshot' and source['kind'] == 'government_wfs' and not source.get('fixed_query'))):
                continue
            seen.add(url)
            primary = self._primary(source, item, url, expected, bindings, attempts)
            if primary['status'] == 'EXACT_LOCKED_BYTES':
                return None
            if source['kind'] == ASIC_REGISTER_KIND:
                manifest = source.get('archive_manifest_url', '')
                stamp = source.get('publication_date', '')
                metadata = self.root / 'data/snapshots' / (source.get('archive_manifest_sha256', '') + '.json')
                base = f'https://publicdata.au/d/asic-companies/v/{stamp}/'
                if (manifest == base + 'manifest.json' and metadata.is_file()
                        and _sha(metadata) == source['archive_manifest_sha256']
                        and json.loads(metadata.read_bytes()).get('sha256') == expected):
                    archive = self._primary(source, item, base + 'source.zip', expected, bindings, attempts)
                    if archive['status'] == 'EXACT_LOCKED_BYTES':
                        return None
            if role != 'snapshot' or source['kind'] != 'pdf':
                continue
            report = {'stop_reason': primary.get('reason', primary['status']), 'status': primary['status'],
                      'http_status': primary.get('http_status'), 'network_error': False}
            count = len(self.alternates.reports)

            def observe(raw, resolved, headers):
                self.observe(raw, source, item, resolved, headers, expected, bindings, attempts)

            alternate_staging = self.output / 'alternate-staging'
            alternate_staging.mkdir(exist_ok=True)
            self.alternates.find(source, report, {expected}, alternate_staging, observe=observe, timeout=self.timeout)
            for fallback in self.alternates.reports[count:]:
                attempts.append(public_export({'status': 'POLICY_ALTERNATES_SCANNED', 'source_key': source['key'],
                                               'observed_at': _now(), 'reason': fallback['stop_reason'],
                                               'report': fallback}))
            if (self.output / 'assets' / expected).is_file():
                return None
        return (attempts[-1].get('reason') or attempts[-1]['status'] if len(attempts) > start
                else 'NO_POLICY_AUTHORIZED_SOURCE')


def _references(value):
    if isinstance(value, dict):
        for key, nested in value.items():
            if key in EVIDENCE_HASHES and isinstance(nested, str):
                yield from re.findall(r'[0-9a-f]{64}', nested)
            if isinstance(nested, (dict, list)):
                yield from _references(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from _references(nested)


def _impact(root, release, missing):
    """Link direct references and label broader panel relations as potential."""
    rows = {sha: defaultdict(set) for sha in missing}
    panels = defaultdict(set)
    input_hashes = {}

    def read(name):
        path = release / name
        if not path.is_file():
            return ()
        input_hashes[name] = filehash(path)
        return read_csv(path)

    for line in read('mcda_panel_decisions.csv'):
        for project in (line['project_id'], line.get('canonical_project_id')):
            if project:
                panels[project].add(line['panel'])
    for filename, source, key, columns in (
        ('field_provenance.csv', 'source_sha256', 'census_fields', ('project_id', 'column')),
        ('resource_statement_observations.csv', 'source_sha256', 'resource_observations', ('project_id', 'observation_id', 'variable')),
        ('mcda_criterion_lineage.csv', 'evidence', 'analysis_inputs', ('project_id', 'panel', 'criterion')),
        ('formal_c1_gates.csv', 'evidence', 'eligibility_gates', ('project_id', 'gate')),
    ):
        for line in read(filename):
            refs = (set(_references(json.loads(line[source] or '[]'))) if source == 'evidence'
                    else set(re.findall(r'[0-9a-f]{64}', line[source])))
            for sha in refs.intersection(missing):
                rows[sha][key].add(tuple(line[field] for field in columns))
                rows[sha]['projects'].add(line['project_id'])
    shadow = root / 'results/observation-shadow-20261126/decisions.jsonl'
    if shadow.is_file():
        input_hashes[shadow.relative_to(root).as_posix()] = filehash(shadow)
        with shadow.open(encoding='utf8') as records:
            for line in records:
                item = json.loads(line)
                sha = item['source_sha256']
                if sha in missing:
                    rows[sha]['candidates'].add((item['project_id'], item['candidate_id'], item['profile_id']))
                    rows[sha]['projects'].add(item['project_id'])
    for detail in rows.values():
        direct = {panel for _, panel, _ in detail['analysis_inputs']}
        detail['direct_panels'] = direct
        detail['potential_selection_panels'] = {
            panel for project in detail['projects'] for panel in panels[project]
        } - direct
    keys = ('projects', 'candidates', 'resource_observations', 'census_fields', 'analysis_inputs',
            'eligibility_gates', 'direct_panels', 'potential_selection_panels')
    return {sha: {name: sorted(rows[sha][name]) for name in keys} for sha in sorted(rows)}, input_hashes


def recover_census_assets(root, release, output, *, libraries=(), online=False, request_budget=80, timeout=12):
    """Resume an immutable replay library. Distinct captures stay outside it."""
    root = Path(root).resolve()
    release = (root / release).resolve()
    output = Path(output).resolve()
    libraries = tuple(Path(library).resolve(strict=True) for library in libraries)
    if not 1 <= request_budget <= 400 or not 1 <= timeout <= 60:
        raise ValueError('Source recovery requires bounded requests and timeout')
    for protected in (root / 'data', root / 'config', root / 'results', release, *libraries):
        if output.is_relative_to(protected) or protected.is_relative_to(output):
            raise ValueError('Recovery output must be separate from the repository inputs and libraries')
    planned, contract = _manifest(root, release)
    assets, records = output / 'assets', output / 'records'
    for path in (assets, records, output / 'versions', output / 'alternate-staging', output / '.recovery.lock'):
        if path.is_symlink():
            raise ValueError('Recovery directories must not be symbolic links')
    assets.mkdir(parents=True, exist_ok=True)
    records.mkdir(exist_ok=True)
    with (output / '.recovery.lock').open('a+b') as lock:
        import fcntl
        fcntl.flock(lock, fcntl.LOCK_EX)
        return _recover(root, release, output, assets, records, planned, contract, libraries,
                        online, request_budget, timeout)


def _recover(root, release, output, assets, records, planned, contract, libraries, online, budget, timeout):
    plan_id = digest(contract)
    remote = _NetworkRecovery(root, output, budget, timeout) if online else None
    valid, all_rows, need = {}, {}, {}
    for sha, bindings in sorted(planned.items()):
        path = assets / sha
        prior_path = records / (sha + '.json')
        if path.is_symlink() or prior_path.is_symlink():
            raise ValueError('Recovery assets and receipts must not be symbolic links')
        prior = None
        if prior_path.is_file():
            try:
                prior = json.loads(prior_path.read_bytes())
            except ValueError:
                prior = None
        prior_valid = (isinstance(prior, dict) and prior.get('contract') == plan_id
                       and prior.get('locked_sha256') == sha and isinstance(prior.get('attempts'), list))
        row = prior if prior_valid else {'locked_sha256': sha, 'contract': plan_id, 'attempts': []}
        row['references'] = _record_inputs(bindings)
        if path.is_file():
            actual = _sha(path)
            if actual == sha:
                row.update(status='VERIFIED', reused=True, method=row.get('method', 'EXISTING_WORK_LIBRARY'))
                valid[sha] = path
            else:
                _store(output / 'versions' / actual, path)
                path.unlink()
                row['attempts'].append({'status': 'CORRUPT_LOCAL_ASSET_QUARANTINED', 'actual_sha256': actual,
                                        'version_path': 'versions/' + actual, 'observed_at': _now()})
        if sha not in valid:
            need[sha] = bindings
        all_rows[sha] = row
    local = _local_paths(root, need, libraries) if need else {}
    for sha in sorted(need, key=lambda value: (value not in local, value)):
        bindings, row = need[sha], all_rows[sha]
        reason = 'EXACT_LOCAL_BYTES_NOT_FOUND'
        if sha in local:
            try:
                location = local[sha]
                if isinstance(location, tuple):
                    path, member = location
                    with ZipFile(path) as archive:
                        raw = archive.read(member)
                    label = str(path) + '::' + member
                else:
                    raw, label = location, str(location)
                policy = _verify_policy(raw if isinstance(raw, bytes) else raw.read_bytes(), bindings) if any(
                    src.get('hash_policy') or item.get('hash_policy') for src, item, _ in bindings) else {}
                _store(assets / sha, raw)
                row.update(status='VERIFIED', method='EXACT_LOCAL_SNAPSHOT_OR_ARCHIVE', reused=False,
                           reason=None, observed_at=_now(), local_path=label, content_policies=policy)
                valid[sha] = assets / sha
            except (BadZipFile, OSError, ValueError, RuntimeError) as exc:
                reason = str(exc)
                row['attempts'].append({'status': 'LOCAL_ASSET_REJECTED', 'reason': reason, 'observed_at': _now()})
        if sha not in valid and remote is not None:
            try:
                reason = remote.recover(sha, bindings, row['attempts'])
                if reason is None:
                    if _sha(assets / sha) != sha:
                        raise ValueError('RECOVERY_PUBLISHED_SHA_MISMATCH')
                    row.update(status='VERIFIED', method='EXACT_PUBLIC_SOURCE_OR_ARCHIVE', reused=False,
                               reason=None, observed_at=_now())
                    valid[sha] = assets / sha
            except (OSError, ValueError) as exc:
                reason = str(exc)
                row['attempts'].append({'status': 'REMOTE_RECOVERY_ERROR', 'reason': reason, 'observed_at': _now()})
        if sha not in valid:
            row.update(status='MISSING', reason=reason, reused=False)
        atomic_json(records / (sha + '.json'), row)
    missing = set(planned) - valid.keys()
    impact, impact_inputs = _impact(root, release, missing) if missing else ({}, {})
    counts = {key: len({item for row in impact.values() for item in row[key]})
              for key in next(iter(impact.values()), {})}
    potential = counts.pop('potential_selection_panels', 0)
    for sha, fields in impact.items():
        fields.update(reason=all_rows[sha]['reason'], source_references=all_rows[sha]['references'])
    impact_path, receipt_path = output / 'missing_impact.json', output / 'recovery.json'
    atomic_json(impact_path, {'version': VERSION, 'contract': contract, 'impact_inputs_sha256': impact_inputs,
                             'sources': impact, 'direct_reference_counts': counts,
                             'potential_selection_panel_count': potential})
    result = {'version': VERSION, 'contract': contract, 'status': 'BLOCKED_MISSING_ASSETS' if missing else 'COMPLETE',
              'expected': len(planned), 'verified': len(valid), 'missing': len(missing),
              'missing_sha256': sorted(missing), 'assets': str(assets), 'receipt_path': str(receipt_path),
              'impact_path': str(impact_path), 'online': online, 'request_budget': budget,
              'request_slots_used': remote.used if remote else 0, 'receipts': list(all_rows.values())}
    atomic_json(receipt_path, result)
    return result
