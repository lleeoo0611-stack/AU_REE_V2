"""Reviewed assay statements scoped to a specific sample or survey, independent of scoring."""
import json
from pathlib import Path
import unicodedata

import pymupdf

from .selection import date_end
from .store import canonical, digest
from .tabular import write_csv

COLUMNS = ('assay_id', 'project_id', 'sample', 'matrix', 'sampling', 'preparation', 'method',
           'basis', 'analyte', 'value', 'unit', 'laboratory', 'lod', 'loq', 'crm', 'blank',
           'duplicates', 'controls', 'standard_status', 'adopted_standard', 'standard_scope_review',
           'project_link_observation', 'source_sha256', 'source_key', 'source_url', 'publication_date',
           'physical_pages', 'source_markers', 'verification', 'version')


def normalized(text):
    return ' '.join(unicodedata.normalize('NFKC', text).casefold().split())


def verify_pages(path, pages):
    if not pages:
        return False
    with pymupdf.open(path) as pdf:
        for page, markers in pages.items():
            index = int(page) - 1
            if index < 0 or index >= len(pdf) or len({normalized(m) for m in markers if m and m.strip()}) < 2:
                return False
            text = normalized(pdf[index].get_text())
            if any(normalized(marker) not in text for marker in markers):
                return False
    return True


def standard_evidence(case, catalog):
    status = case['standard_status']
    adopted = case.get('adopted_standard')
    if status == 'SOURCE_EXPLICIT_STANDARD':
        if adopted not in catalog or not any(adopted in markers for markers in case['pages'].values()):
            raise ValueError('Explicit standard requires an edition and source-page witness')
    elif status not in ('METHOD_ONLY_NO_STANDARD_CITED', 'NOT_REPORTED', 'APPLICABILITY_UNVERIFIED') or adopted:
        raise ValueError('Unverified adoption of analytical standard')
    return dict(standard_status=status, adopted_standard=adopted,
                standard_scope_review=canonical([dict(**catalog[edition], assessment=reason)
                    for edition, reason in case.get('standard_comparisons', {}).items()]))


def write_assay_evidence(root, out, rows, sources, db, cutoff, active_ids):
    review = json.loads((Path(root)/'config/assay_evidence.json').read_bytes())
    members = {r['專案ID'] for r in rows}
    results = []
    for case in review['cases']:
        pid, sha = case['project_id'], case['source_sha256']
        if pid not in members:
            continue
        source = sources.get(sha, {})
        published = source.get('publication_date')
        anchor = db.execute('SELECT 1 FROM observations WHERE obs_id=? AND entity_id=? '
                            "AND source_sha=? AND status='AUTO_VALIDATED' AND effective_date<=?",
                            (case['project_link_observation'], pid, sha, cutoff)).fetchone()
        if not anchor or case['project_link_observation'] not in active_ids or not published or date_end(published) > cutoff:
            status = 'SOURCE_OR_PROJECT_LINK_UNVERIFIED'
        elif not verify_pages(source['resolved_path'], case['pages']):
            status = 'PAGE_EVIDENCE_UNVERIFIED'
        else:
            status = 'VERIFIED'
        result = {k: case[k] for k in ('project_id','project_link_observation','source_sha256','source_key','sample')}
        if status == 'VERIFIED':
            result.update({k:case[k] for k in COLUMNS if k in case})
            result.update(standard_evidence(case, {s['edition']:s for s in review['standards']}))
        result.update(assay_id=digest([pid,sha,case['sample']]), verification=status,
                      physical_pages=','.join(case['pages']), source_markers=canonical(case['pages']),
                      version=review['version'], publication_date=published, source_url=source.get('url'))
        results.append(result)
    write_csv(out/'assay_method_evidence.csv', results, COLUMNS)
    return dict(assay_cases_reviewed=len(results),
                assay_cases_verified=sum(row['verification']=='VERIFIED' for row in results))
