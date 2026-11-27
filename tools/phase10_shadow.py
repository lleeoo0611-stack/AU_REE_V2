"""Replay the frozen PDF frame through existing retrieval and evidence checks."""

from collections import Counter
import json
from pathlib import Path

from au_ree_v2.derived_cache import atomic_json
from au_ree_v2.document_processing import PdfDocumentCache
from au_ree_v2.formal_resource_admission import _authorized_projects, _evaluate, _source_metadata_issue
from au_ree_v2.nlp import PageIndex
from au_ree_v2.observation_semantics import SemanticEngine
from au_ree_v2.pdf_extract import candidate_value_issues, project_registry, recognize_document
from au_ree_v2.resource_retrieval import apply_parse_receipt, policy, retrieve
from au_ree_v2.resource_source import discover
from au_ree_v2.source_recovery import _manifest, _NetworkRecovery
from au_ree_v2.store import digest, filehash


RELEASE = 'results/ree-project-census/coverage-locked-20261125/'
PHASE22 = 'results/phase22-2026-11-06/snapshot_lock.json'


def _inputs(root, use_phase22):
    catalog = json.loads((root / 'data/manifest.json').read_bytes())['snapshots']
    if use_phase22:
        snapshots = json.loads((root / PHASE22).read_bytes())
        cutoff = '2026-11-05'
    else:
        release = json.loads((root / RELEASE / 'census_release.json').read_bytes())
        acquired = json.loads((root / RELEASE / 'source_acquisition.json').read_bytes())
        # Release summaries describe date roles using objects. Acquisition rows
        # retain the scalar dates used by the formal timing check.
        snapshots = [*release['sources'], *acquired['snapshots']]
        cutoff = release['cutoff']
    local = {(s['key'], s['sha256']): s for s in catalog}
    locked = {}
    for source in snapshots:
        if source['kind'] != 'pdf':
            continue
        key = source['key'], source['sha256']
        metadata = {name: value for name, value in source.items()
                    if name not in ('publication_date', 'available_date', 'acquired_at') or isinstance(value, str)}
        locked[key] = {**local.get(key, {}), **locked.get(key, {}), **metadata}
    return cutoff, locked


def _asset(root, source, sha, assets):
    choices = [assets / sha, assets / f'{sha}.pdf'] if assets else []
    if source and source.get('path'):
        path = (root / source['path']).resolve()
        if path.is_relative_to(root):
            choices.append(path)
    choices.append(root / 'data/snapshots' / f'{sha}.pdf')
    return next((path for path in choices if path.is_file() and filehash(path) == sha), None)


def stage_frozen_pdfs(root, manifest, work, *, request_budget=24):
    """Try only the exact archived source pairs. A failed request leaves its frame unchanged."""
    root, work = Path(root).resolve(), Path(work).resolve()
    frame = json.loads(Path(manifest).read_bytes())
    planned, _ = _manifest(root, root / RELEASE)
    work.mkdir(parents=True, exist_ok=True)
    assets = work / 'assets'
    assets.mkdir(exist_ok=True)
    transport = _NetworkRecovery(root, work, request_budget, 10)
    outcomes = []
    for row in frame['sources']:
        key, sha = row['source_key'], row['source_sha256']
        attempt = []
        exact = [(source, item) for source, item, role in planned.get(sha, ())
                 if role == 'snapshot' and source['key'] == key and source['kind'] == 'pdf']
        target = assets / sha
        if target.is_file() and filehash(target) == sha:
            status = 'EXACT_LOCKED_BYTES'
        elif len(exact) != 1:
            status = 'NO_UNAMBIGUOUS_PINNED_SOURCE'
        else:
            source, item = exact[0]
            url = item.get('url') or source.get('url')
            if source.get('enabled') is False or not url:
                status = 'SOURCE_UNAVAILABLE'
            elif transport.used >= request_budget:
                status = 'REQUEST_BUDGET_EXHAUSTED'
            else:
                status = transport._primary(source, item, url, sha, planned[sha], attempt)['status']
        outcomes.append({'source_key': key, 'source_sha256': sha, 'status': status, 'attempts': attempt})
    atomic_json(work / 'holdout_reacquisition.json', {'outcomes': outcomes, 'request_slots_used': transport.used})
    return assets


def run(root, manifest, output, *, assets=None, use_phase22=False, full_text=False):
    """Record shadow dispositions. No observations are written to canonical SQLite."""
    root, manifest = Path(root).resolve(), Path(manifest)
    assets = Path(assets).resolve() if assets else None
    frame = json.loads(manifest.read_bytes())
    cutoff, locked = _inputs(root, use_phase22)
    settings = policy(frame.get('retrieval'), override_mode='full-text')
    claims = json.loads((root / 'data/claims.json').read_bytes())
    registry = project_registry(root, claims_data=claims)
    projects = {row['entity_id']: row for row in registry}
    entries = {}
    for frame_source in frame['sources']:
        key, sha = frame_source['source_key'], frame_source['source_sha256']
        if sha in entries:
            raise ValueError('DUPLICATE_PHASE10_SHADOW_ORIGINAL')
        source = locked.get((key, sha))
        entries[sha] = (frame_source, source, _asset(root, source, sha, assets))
    dispositions, technical, searches, source_reports = [], [], [], []
    engine = SemanticEngine(root)
    with PdfDocumentCache(root, source_paths={sha: path for sha, (_, _, path) in entries.items() if path}) as documents:
        for sha, (frame_source, source, path) in sorted(entries.items()):
            key = frame_source['source_key']
            metadata = frame_source.get('validation') or {}
            declared = frame_source.get('project_id') or metadata.get('project_id')
            allowed = [declared] if declared in projects else []
            if not allowed and source:
                allowed = _authorized_projects(claims, registry, {sha: source})[sha]
            if not allowed:
                allowed = [row['entity_id'] for row in registry if row['identity_source'] == key]
            aliases = sorted({name for pid in allowed for name in [projects[pid]['name'], *projects[pid]['aliases']]})
            if not aliases and (name := frame_source.get('project_name') or metadata.get('project_name')):
                aliases = [name]
            source_issue = ('PINNED_SOURCE_EDITION_NOT_SELECTED' if source is None else
                            'SOURCE_UNAVAILABLE' if path is None else
                            _source_metadata_issue(source, cutoff, None, cutoff))
            search = retrieve(documents, frame_source, aliases, settings,
                              blocked_reason='SOURCE_UNAVAILABLE' if path is None else None)
            if not full_text:
                search['selected_pages'] = frame_source['pages']
                search['selected_context_pages'] = frame_source.get('context_pages', [])
            searches.append(search)
            source_reports.append({'source_key': key, 'source_sha256': sha, 'sha_verified': path is not None,
                                   'authorized_projects': allowed, 'source_verification_status': source_issue})
            if source is None or not path or search['status'] != 'SEARCHED':
                continue
            source = {**source, 'path': str(path), 'summary_project_ids': allowed}
            index = PageIndex.from_documents(documents, [sha])
            technical_rank = [page for _, page in index.rank_pair(aliases, 'technical', k=24)['rules_nlp']]
            search['candidate_pages']['technical'] = technical_rank
            pages = technical_rank[:5]
            if pages:
                result = recognize_document(root, source, registry, page_numbers=set(pages))
                for item in result['candidates']:
                    if 'TECHNICAL' in item['kind'] or item['kind'] == 'LEACH_TABLE_ROW':
                        technical.append({'source_key': key, 'source_sha256': sha, 'physical_page': item['physical_page'],
                                          'candidate': item, 'numeric_issues': candidate_value_issues(item),
                                          'status': 'SHADOW_TECHNICAL_CANDIDATE', 'source_issue': source_issue})
            if not search['selected_pages']:
                continue
            result = discover(root, source, registry, page_numbers=search['selected_pages'], document_cache=documents,
                              context_pages=search['selected_context_pages'])
            apply_parse_receipt(search, result)
            for candidate in result['candidates']:
                row, _, _ = _evaluate(candidate, source, allowed, cutoff, engine, registry=registry)
                if source_issue:
                    row['reasons'] = sorted(set(row['reasons']) | {source_issue})
                    row['status'] = 'NOT_ADMITTED'
                dispositions.append(row)
    receipt = {'schema': 'phase10-shadow-v1', 'purpose': 'OFFLINE_QUALITY_ADMISSIONS_SIMULATION', 'cutoff': cutoff,
               'manifest_sha256': filehash(manifest), 'retrieval_policy': settings,
               'resource_extraction_scope': 'RANKED_WITH_FROZEN_SEEDS' if full_text else 'FROZEN_PAGES',
               'technical_extraction_scope': 'BM25_TOP_5_SEPARATE_DIAGNOSTIC',
               'source_dispositions': source_reports, 'retrieval_sources': searches,
               'dispositions': dispositions, 'technical_dispositions': technical,
               'counts': {'source_count': len(entries), 'verified_sources': sum(x['sha_verified'] for x in source_reports),
                          'canonical_observations_written': 0, 'candidate_rows': len(dispositions),
                          'shadow_status_counts': dict(Counter(x['status'] for x in dispositions)),
                          'technical_candidate_rows': len(technical)}}
    receipt['scientific_sha256'] = digest(receipt)
    atomic_json(Path(output), receipt)
    return receipt
