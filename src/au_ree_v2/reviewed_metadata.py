"""Exact issuer/listing and project-ownership statements in one reviewed PDF."""
import re
from .source_cells import norm, region_text


def validate_descriptive_attribute(doc, attribute, aliases, evidence, review):
    """Bind a short literal description to a reviewed project heading and region.

    This admits no classification codes, coordinates, resource quantities or
    forecasts. The reviewer still checks the meaning and layout of the PDF.
    """
    import pymupdf
    from urllib.parse import urlsplit
    def fail(code):
        raise ValueError('REVIEW_DESCRIPTION_' + code)
    column = attribute['column']
    if column not in ('礦床型態', '開發階段', '未上市公司'):
        fail('COLUMN')
    binding = attribute.get('description_binding', {})
    page_number = attribute['evidence']['page']
    if binding.get('page') != page_number:
        fail('PAGE')
    evidence(attribute['evidence'])
    page = doc[page_number-1]
    def extract(key):
        box = pymupdf.Rect(binding[key])
        if box.is_empty or box.is_infinite or not page.rect.contains(box):
            fail('REGION')
        return norm(region_text(page, box))
    header = extract('project_bbox')
    marker = norm(binding.get('project_marker', ''))
    def project_label(value):
        return re.sub(r'\bmt\.?\s+', 'mount ', norm(value))
    if len(marker) < 4 or not re.search(r'(?<!\w)'+re.escape(marker)+r'(?!\w)',header) or not any(
            project_label(marker) == project_label(a) for a in aliases):
        fail('PROJECT')
    statement = norm(binding.get('statement', ''))
    if not statement or extract('value_bbox') != statement:
        fail('STATEMENT')
    if column == '未上市公司':
        if (attribute['value'] != '是' or review.get('source_kind') != 'GOVERNMENT_PROJECT_CATALOGUE'
                or not (urlsplit(review['url']).hostname or '').endswith('.gov.au')
                or not re.search(r'\bunlisted (?:private|public) company\b', statement)):
            fail('UNLISTED')
        # Company and project are explicitly paired in the same catalogue panel.
        issuer = norm(binding.get('issuer', ''))
        if not issuer or issuer not in statement or marker not in statement:
            fail('ISSUER_PROJECT_PANEL')
    else:
        token = norm(binding.get('literal_value', ''))
        if not token or token not in statement:
            fail('VALUE')
        expected = binding['literal_value']
        if column == '開發階段':
            label = (review['publication_date'][:7]+'，月精度' if review.get('publication_date_precision')=='MONTH'
                     else review['publication_date'])
            expected += '（來源揭露：' + label + '）'
        if attribute['value'] != expected:
            fail('VALUE_OR_DATE')
    return 'SOURCE_BOUND_LITERAL_DESCRIPTION_AT_DISCLOSURE_DATE'


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
