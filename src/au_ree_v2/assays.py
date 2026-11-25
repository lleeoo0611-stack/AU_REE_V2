"""Reviewed assay statements scoped to a specific sample or survey, independent of scoring."""
import json
from pathlib import Path
import re
import unicodedata

import pymupdf

from .selection_rules import date_end
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


def adoption_witness(case):
    """Accept a reviewed affirmative clause about this sample and matrix only.

    Project-wide citations, comparisons and proposed future methods require review.
    The subject and edition must be in the same verbatim located statement.
    """
    scope = case.get('adoption_scope') or {}
    quote = normalized(case.get('adoption_quote') or '')
    sample, matrix = (normalized(case.get(k) or '') for k in ('sample','matrix'))
    page = str(scope.get('physical_page') or '')
    if (not sample or not matrix or normalized(scope.get('sample') or '') != sample or
            normalized(scope.get('matrix') or '') != matrix or not quote or
            quote not in {normalized(marker) for marker in case.get('pages', {}).get(page, ())}):
        raise ValueError('Standard adoption requires a located quotation and matching sample and matrix')
    s, m, edition = map(re.escape, (sample, matrix, normalized(case['adopted_standard'])))
    # Constrain the entire sentence. A standard name beside a sample list or another
    # sample's method, or a negated/hypothetical phrase, cannot satisfy this contract.
    subject = rf'(?:{s}\s*\({m}\)|{s}, {m},|{m} {s}|{s} {m})'
    verb = r'(?:was|were) (?:analysed|analyzed|tested|assayed|measured) (?:according to|in accordance with|using|following)'
    english = rf'(?:the )?{subject} {verb} {edition}'
    chinese = rf'{s}\s*[（(]{m}[)）]\s*(?:已)?(?:依據|依照|按照|依据)\s*{edition}\s*(?:進行|进行)?(?:分析|測定|测定)'
    if not re.fullmatch(rf'(?:{english}|{chinese})[.。]?', quote):
        raise ValueError('Review the affirmative sample-specific adoption statement')
    return dict(physical_page=page, sample=scope['sample'], matrix=scope['matrix'],
                adoption_quote=case['adoption_quote'])


def verify_adoption_sentence(path, witness):
    """A matching substring of a denied, hypothetical or quoted claim is insufficient."""
    quote = normalized(witness['adoption_quote']).rstrip('.。')
    with pymupdf.open(path) as doc:
        text = normalized(doc[int(witness['physical_page'])-1].get_text())
    for clause in re.split(r'[.!?。！？]', text):
        if (normalized(witness['sample']) in clause and normalized(witness['matrix']) in clause
                and normalized(witness['edition']) in clause and
                re.search(r'\b(?:not|never|without)\b|不採用|未採用|不采用|未采用|未依據|未依据', clause)):
            return False
    return bool(re.search(r'(?:^|[.!?。！？]\s*)'+re.escape(quote)+r'(?=$|[.。](?:\s|$)|[。！？])', text))


def standard_evidence(case, catalog, source_path=None):
    status = case['standard_status']
    adopted = case.get('adopted_standard')
    comparisons = [dict(**catalog[edition], assessment=reason)
                   for edition, reason in case.get('standard_comparisons', {}).items()]
    if status == 'SOURCE_EXPLICIT_STANDARD':
        if adopted not in catalog:
            raise ValueError('Unregistered analytical standard edition')
        witness = adoption_witness(case)
        if source_path is not None and not verify_adoption_sentence(source_path, dict(witness,edition=adopted)):
            raise ValueError('The quoted clause is not a full sentence on its verified source page')
        comparisons.append(dict(edition=adopted, assessment='SOURCE_EXPLICIT_STANDARD', **witness))
    elif status not in ('METHOD_ONLY_NO_STANDARD_CITED', 'NOT_REPORTED', 'APPLICABILITY_UNVERIFIED') or adopted:
        raise ValueError('Unverified adoption of analytical standard')
    return dict(standard_status=status, adopted_standard=adopted,
                standard_scope_review=canonical(comparisons))


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
            catalog = {s['edition']:s for s in review['standards']}
            if case['standard_status'] == 'SOURCE_EXPLICIT_STANDARD':
                try:
                    standard = standard_evidence(case, catalog, source['resolved_path'])
                except ValueError as error:
                    # A valid measured result survives an unsupported standard citation.
                    standard = dict(standard_status='APPLICABILITY_UNVERIFIED', adopted_standard=None,
                                    standard_scope_review=canonical([dict(edition=case.get('adopted_standard'),
                                        assessment='ADOPTION_EVIDENCE_UNVERIFIED', reason=str(error))]))
            else:
                standard = standard_evidence(case, catalog)
            result.update(standard)
        result.update(assay_id=digest([pid,sha,case['sample']]), verification=status,
                      physical_pages=','.join(case['pages']), source_markers=canonical(case['pages']),
                      version=review['version'], publication_date=published, source_url=source.get('url'))
        results.append(result)
    write_csv(out/'assay_method_evidence.csv', results, COLUMNS)
    return dict(assay_cases_reviewed=len(results),
                assay_cases_verified=sum(row['verification']=='VERIFIED' for row in results))
