"""Exact issuer/listing and project-ownership statements in one reviewed PDF."""
import re
from .source_cells import norm, region_text


def validate_metadata_issue_date(review, evidence, cutoff):
    """Signed-issue/ASX-release proof for literal descriptions only."""
    if (review.get('effective_date_role')!='DATED_ISSUER_METADATA'
            or review.get('observations') or review.get('study')
            or not review.get('attributes')
            or not all(a.get('description_binding') for a in review['attributes'])):
        raise ValueError('REVIEW_ISSUE_DATE_LITERAL_METADATA_ONLY')
    from .reviewed_discovery import validate_issue_date
    proof=review['document_issue_evidence']
    identity=dict(review,date_evidence=proof)
    validate_issue_date(identity,dict(url=review['url'],kind='pdf'),cutoff,evidence(proof))


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
    known=any(project_label(marker)==project_label(a) for a in aliases)
    if not known and binding.get('qualified_alias_proof'):
        proof=binding['qualified_alias_proof']
        qualified=project_label(proof.get('ticker','')+' '+marker)
        if (proof.get('exchange')!='ASX' or norm(proof.get('project_marker',''))!=marker
                or not any(qualified==project_label(a) for a in aliases)):
            fail('QUALIFIED_PROJECT_ALIAS')
        validate_listing_proof(doc,proof,evidence)
        known=True
    if len(marker) < 4 or not re.search(r'(?<!\w)'+re.escape(marker)+r'(?!\w)',header) or not known:
        fail('PROJECT')
    statement = norm(binding.get('statement', ''))
    if not statement or extract('value_bbox') != statement:
        fail('STATEMENT')
    legend = binding.get('legend_binding')
    if legend:
        if (column!='礦床型態' or review.get('source_kind')!='GOVERNMENT_PROJECT_CATALOGUE'
                or not (urlsplit(review['url']).hostname or '').endswith('.gov.au')):
            fail('LEGEND_SCOPE')
        row_box=pymupdf.Rect(legend['row_swatch_bbox']);key_box=pymupdf.Rect(legend['legend_swatch_bbox'])
        heading=pymupdf.Rect(binding['project_bbox']);label=pymupdf.Rect(binding['value_bbox'])
        if (not row_box.y0 < (heading.y0+heading.y1)/2 < row_box.y1 or row_box.x1>heading.x0
                or not key_box.y0 < (label.y0+label.y1)/2 < key_box.y1
                or not 0 <= label.x0-key_box.x1 < 15):
            fail('LEGEND_ROW_OR_LABEL_ALIGNMENT')
        def swatch(box):
            matches=[]
            for drawing in page.get_drawings():
                rect=drawing['rect']
                if (drawing.get('fill') is not None and len(drawing['items'])==1
                        and drawing['items'][0][0]=='re'
                        and max(abs(a-b) for a,b in zip(rect,box))<.1):
                    matches.append(drawing['fill'])
            if len(matches)!=1 or max(matches[0])-min(matches[0])<.1:
                fail('LEGEND_NATIVE_RECTANGLE')
            return matches[0]
        if max(abs(a-b) for a,b in zip(swatch(row_box),swatch(key_box)))>1e-5:
            fail('LEGEND_COLOUR_MISMATCH')
        if norm(attribute['value'])!=statement or norm(binding.get('literal_value',''))!=statement:
            fail('LEGEND_LITERAL_LABEL')
        return 'SOURCE_GOVERNMENT_NATIVE_VECTOR_LEGEND_CLASSIFICATION'
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
    if not re.search(r'100%\s*(?:[-\u2010\u2011]?\s*owned\b|ownership\b)|owned\s+100%',statement):fail('FULL_OWNERSHIP_REQUIRED')
    if proof.get('project_scope_evidence'):evidence(proof['project_scope_evidence'])
    return 'SOURCE_BOUND_LISTED_ISSUER_AND_PROJECT_OWNERSHIP'
