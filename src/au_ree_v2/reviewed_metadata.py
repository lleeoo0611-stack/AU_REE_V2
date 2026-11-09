"""Exact issuer/listing and project-ownership statements in one reviewed PDF."""
import re
from .source_cells import norm, region_text


def validate_listing_proof(doc, proof, evidence):
    import pymupdf
    def fail(code):
        raise ValueError('REVIEW_LISTING_' + code)
    exchange=proof.get('exchange');ticker=proof.get('ticker','')
    issuer=proof.get('issuer','');alias=proof.get('issuer_alias','');project=proof.get('project_marker','')
    if exchange not in ('ASX','LSE') or not re.fullmatch(r'[A-Z0-9]{2,6}',ticker):fail('EXCHANGE_OR_TICKER')
    if not issuer or not alias or not project or norm(alias) not in norm(issuer):fail('ISSUER_OR_PROJECT_REQUIRED')
    listing=evidence(proof['listing_evidence'])
    if norm(issuer) not in listing or not re.search(r'\b'+exchange+r'\s*:\s*'+re.escape(ticker)+r'\b',doc[proof['listing_evidence']['page']-1].get_text()):fail('ISSUER_TICKER_NOT_BOUND')
    ownership=proof['ownership_evidence'];evidence(ownership)
    page=doc[ownership['page']-1];box=pymupdf.Rect(proof['ownership_bbox'])
    if box.is_empty or box.is_infinite or not page.rect.contains(box):fail('OWNERSHIP_REGION_INVALID')
    statement=norm(proof.get('ownership_statement',''))
    if not statement or norm(region_text(page,box))!=statement:fail('OWNERSHIP_STATEMENT_MISMATCH')
    if norm(alias) not in statement or norm(project) not in statement:fail('OWNERSHIP_ISSUER_PROJECT_MISMATCH')
    if re.search(r'\bnot\b|\bno longer\b|\bless than\b',statement):fail('OWNERSHIP_NOT_AFFIRMED')
    if not re.search(r'100%\s*(?:[-\u2010\u2011]\s*owned|ownership)|owned\s+100%',statement):fail('FULL_OWNERSHIP_REQUIRED')
    if proof.get('project_scope_evidence'):evidence(proof['project_scope_evidence'])
    return 'SOURCE_BOUND_LISTED_ISSUER_AND_PROJECT_OWNERSHIP'
