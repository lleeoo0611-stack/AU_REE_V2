"""Source-bound review ledger: projections over the Census, never identity merges.

Native row/heading markers or an explicitly reviewed rendered image bind each
transcription. Date roles, ranges and engineering endpoints remain explicit.
"""
import hashlib,json,math,re,calendar
from datetime import date,datetime
from collections import Counter
import csv
from pathlib import Path
from .store import canonical,digest,filehash
from .pdf_extract import publication_date
from .project_summary import ELEMENTS,MAGNET

def normalized(text):return re.sub(r'\s+',' ',text).strip().casefold()

def month_interval(day):
    value=date.fromisoformat(day)
    return [value.replace(day=1).isoformat(),value.replace(day=calendar.monthrange(value.year,value.month)[1]).isoformat()]


def catalogue_month_proof(doc,pub,content,role='EDITION_MONTH'):
    """A labelled publication month takes precedence over an earlier edition month."""
    label=normalized(datetime.strptime(pub,'%Y-%m-%d').strftime('%B %Y'))
    front=' '.join(normalized(doc[i].get_text(sort=True)) for i in range(min(3,len(doc))))
    months='January February March April May June July August September October November December'.split()
    explicit={normalized(m+' '+y) for m,y in re.findall(r'publication\s+date\s*:\s*('+'|'.join(months)+r')\s+(20\d{2})',front,re.I)}
    if explicit and explicit!={label}:raise ValueError('REVIEW_EDITION_CANNOT_OVERRIDE_PUBLICATION_MONTH')
    if role=='PUBLISHER_PUBLICATION_MONTH':
        if 'publication date: '+label not in content:raise ValueError('REVIEW_PUBLICATION_LABEL_MONTH_MISMATCH')
    elif role=='EDITION_MONTH':
        if label not in content or 'edition' not in content:raise ValueError('REVIEW_PUBLICATION_EDITION_MONTH_MISMATCH')
    else:raise ValueError('REVIEW_PUBLICATION_MONTH_ROLE_REQUIRED')


def annual_product_derivation(derivation,value,annual_page,evidence):
    """Only same-table, explicitly annual, oxide-based product conversions."""
    from .technical_tables import number_token
    methods={'ANNUAL_PRODUCT_MASS_X_TREO_FRACTION':{'annual_product_t','treo_percent'},
             'ANNUAL_PRODUCT_MASS_X_TREO_FRACTION_X_NDPR_SHARE':{'annual_product_t','treo_percent','nd_percent_of_treo','pr_percent_of_treo'}}
    method=derivation.get('method');inputs=derivation.get('inputs',[])
    if method not in methods or {i['name'] for i in inputs}!=methods[method] or len(inputs)!=len(methods[method]):
        raise ValueError('REVIEW_ANNUAL_DERIVATION_INPUT_CONTRACT')
    values={};table_rows=set()
    for item in inputs:
        if item['evidence']['page']!=annual_page:raise ValueError('REVIEW_ANNUAL_DERIVATION_REQUIRES_SAME_TABLE')
        row=item['evidence'].get('table_row');render=item['evidence'].get('render_sha256','')
        if not row or not re.fullmatch('[0-9a-f]{64}',render):raise ValueError('REVIEW_ANNUAL_DERIVATION_RENDERED_ROW_REQUIRED')
        table_rows.add((normalized(row),render))
        content=evidence(item['evidence']);parsed=number_token(item['original_token'])
        if normalized(row) not in content:raise ValueError('REVIEW_ANNUAL_DERIVATION_ROW_NOT_IN_SOURCE')
        v=item['value'];name=item['name']
        if (isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or v<=0 or not parsed or
            parsed['value']!=v or not re.search(r'(?<![\d.])'+re.escape(normalized(item['original_token']))+r'(?![\d.])',content)):
            raise ValueError('REVIEW_ANNUAL_DERIVATION_TOKEN_MISMATCH')
        expected='t/year' if name=='annual_product_t' else '%' if name=='treo_percent' else '%TREO'
        if item['unit']!=expected or name!='annual_product_t' and v>100:raise ValueError('REVIEW_ANNUAL_DERIVATION_UNIT_OR_RANGE')
        if not re.search(r'\bannual\b',content) or not re.search(r'\btreo\b',content):raise ValueError('REVIEW_ANNUAL_DERIVATION_BASIS_MISSING')
        if name.startswith(('nd_','pr_')) and not all(normalized(m) in content for m in ['As a % of TREO','Nd2O3','Pr6O11']):
            raise ValueError('REVIEW_ANNUAL_DERIVATION_NDPR_OXIDE_BASIS_MISSING')
        values[name]=v
    if len(table_rows)!=1:raise ValueError('REVIEW_ANNUAL_DERIVATION_ROW_CONFLICT')
    result=values['annual_product_t']*values['treo_percent']/100
    if method.endswith('_X_NDPR_SHARE'):
        share=values['nd_percent_of_treo']+values['pr_percent_of_treo']
        if share>100:raise ValueError('REVIEW_ANNUAL_DERIVATION_NDPR_SHARE_OUT_OF_RANGE')
        result*=share/100
    if not math.isclose(result,value,rel_tol=1e-12,abs_tol=1e-9):raise ValueError('REVIEW_ANNUAL_DERIVATION_RESULT_MISMATCH')
    return result

def validate_reviews(ledger_path,asset_roots,projects,cutoff='2026-11-05'):
    import pymupdf
    ledger_path=Path(ledger_path);ledger=json.loads(ledger_path.read_text('utf8'))
    if ledger.get('version')!='asx-source-review-v2':raise ValueError('REVIEW_VERSION_UNSUPPORTED')
    registry={p['entity_id']:p for p in projects};sources={};observations={};studies={};preferences={};receipts=[];attributes={};seen_reviews=set();resource_contracts={};deferred={};resource_labels={};partial_contracts={}
    for review in ledger['reviews']:
        if review['review_id'] in seen_reviews:raise ValueError('REVIEW_DUPLICATE_ID')
        seen_reviews.add(review['review_id'])
        pid=review['project_id'];sha=review['source_sha256']
        if pid not in registry:raise ValueError('REVIEW_PROJECT_NOT_IN_CENSUS')
        asset=Path(asset_roots[review['asset_set']]).resolve();path=(asset/review['path']).resolve()
        if asset not in path.parents:raise ValueError('REVIEW_SOURCE_PATH_ESCAPES_ASSET_ROOT')
        if filehash(path)!=sha:raise ValueError('REVIEW_SOURCE_HASH_MISMATCH')
        receipt_path=asset/'retest.json' if (asset/'retest.json').exists() else asset/'downloads.json'
        if receipt_path.exists():
            captured=json.loads(receipt_path.read_text('utf8'));captured=captured.get('outcomes',[]) if isinstance(captured,dict) else captured
        elif (asset/'data/manifest.json').exists():
            # Re-review an immutable original already controlled by the Census.
            # This is manifest membership, not a newly fabricated download receipt.
            manifest=json.loads((asset/'data/manifest.json').read_text('utf8'))['snapshots']
            captured=[dict(url=s['url'],document_sha256=s['sha256'],status='PDF_ACQUIRED') for s in manifest
                      if s['kind']=='pdf' and (asset/s['path']).resolve()==path]
        else:raise ValueError('REVIEW_SOURCE_RECEIPT_MISSING')
        if not any(r.get('url')==review['url'] and r.get('document_sha256')==sha and r.get('status')=='PDF_ACQUIRED' for r in captured):
            raise ValueError('REVIEW_DOWNLOAD_RECEIPT_BINDING_FAILED')
        pub=review['publication_date'];effective=review['effective_date']
        date.fromisoformat(pub);date.fromisoformat(effective)
        if effective>pub or pub>cutoff:raise ValueError('REVIEW_DATE_OUTSIDE_PUBLICATION_OR_CUTOFF')
        role=review['effective_date_role']
        if role not in ('RESOURCE_EFFECTIVE_DATE','RESOURCE_REAFFIRMED_AT_PUBLICATION','DATED_ENGINEERING_FORECAST','DATED_ISSUER_METADATA','TECHNICAL_REPORT_RESOURCE_AS_REPORTED'):
            raise ValueError('REVIEW_EFFECTIVE_DATE_ROLE_REQUIRED')
        if role=='DATED_ISSUER_METADATA' and (review.get('observations') or review.get('study') or not review.get('attributes')):
            raise ValueError('REVIEW_METADATA_ROLE_REQUIRES_ATTRIBUTES_ONLY')
        with pymupdf.open(path) as doc:
            texts={};rendered={}
            def text(page):
                if not 1<=page<=len(doc):raise ValueError('REVIEW_PAGE_OUTSIDE_DOCUMENT')
                if page not in texts:texts[page]=doc[page-1].get_text(sort=True)
                return texts[page]
            def evidence(item):
                page=item['page'];content=normalized(text(page))
                markers=item.get('markers',[])
                if not markers:raise ValueError('REVIEW_PAGE_MARKERS_REQUIRED')
                if any(normalized(m) not in content for m in markers):raise ValueError('REVIEW_PAGE_MARKER_MISMATCH')
                expected=item.get('render_sha256')
                if expected:
                    if not re.fullmatch(r'[0-9a-f]{64}',expected):raise ValueError('REVIEW_INVALID_RENDER_SHA256')
                    if page not in rendered:rendered[page]=hashlib.sha256(doc[page-1].get_pixmap(matrix=pymupdf.Matrix(2,2)).tobytes('png')).hexdigest()
                    if rendered[page]!=expected:raise ValueError(f"REVIEW_RENDER_BINDING_MISMATCH:{review['review_id']}:p{page}:{rendered[page]}")
                return content
            from .partial_resource import validate_technical_report_dates
            technical_report_date=validate_technical_report_dates(review,doc,evidence)
            parsed_publication=pub if technical_report_date else publication_date(text(1))
            month=review.get('publication_month_evidence')
            if month:
                # Retain edition-month precision; never infer a release day
                # from a URL, filename, or acquisition timestamp.
                interval=month_interval(pub)
                if (review.get('source_kind')!='GOVERNMENT_PROJECT_CATALOGUE' or
                    review.get('publication_date_precision')!='MONTH' or
                    review.get('publication_date_interval')!=interval or pub!=interval[1]):
                    raise ValueError('REVIEW_PUBLICATION_MONTH_INTERVAL_REQUIRED')
                from urllib.parse import urlsplit
                if not (urlsplit(review['url']).hostname or '').endswith('.gov.au'):
                    raise ValueError('REVIEW_GOVERNMENT_CATALOGUE_HOST_REQUIRED')
                content=evidence(month)
                catalogue_month_proof(doc,pub,content,review.get('publication_month_role','EDITION_MONTH'))
                if parsed_publication is not None:raise ValueError('REVIEW_MONTH_CANNOT_OVERRIDE_EXPLICIT_DAY')
                parsed_publication=pub
            if parsed_publication!=pub:
                header=review.get('publication_header_evidence')
                archive=review.get('publication_archive_evidence')
                if parsed_publication is None and archive:
                    from urllib.parse import urljoin,urldefrag
                    from .discovery import Links
                    index_root=Path(asset_roots[archive['asset_set']]).resolve();index_path=(index_root/archive['path']).resolve()
                    if index_root not in index_path.parents or filehash(index_path)!=archive['sha256']:raise ValueError('REVIEW_PUBLICATION_ARCHIVE_HASH_MISMATCH')
                    links=Links();links.feed(index_path.read_text('utf8'))
                    if not any(urldefrag(urljoin(archive['url'],href))[0]==review['url'] and links.link_dates.get(href)==pub for href,_ in links.links):
                        raise ValueError('REVIEW_PUBLICATION_ARCHIVE_DATE_BINDING_FAILED')
                    issue=review['document_issue_date'];date.fromisoformat(issue)
                    issue_content=evidence(review['document_issue_evidence'])
                    if issue>pub or normalized(datetime.strptime(issue,'%Y-%m-%d').strftime('%d %B %Y').lstrip('0')) not in issue_content:
                        raise ValueError('REVIEW_DOCUMENT_ISSUE_DATE_MISMATCH')
                    parsed_publication=pub
                # Some releases place the address before the dated title. Require
                # an explicit reviewed first-page header, never a body citation.
                if parsed_publication!=pub:
                    if parsed_publication is not None or not header or header['page']!=1:raise ValueError('REVIEW_PUBLICATION_DATE_MISMATCH')
                    content=evidence(header)
                    label=normalized(datetime.strptime(pub,'%Y-%m-%d').strftime('%d %B %Y').lstrip('0'))
                    header_content=re.sub(r'\b(\d{1,2})(?:st|nd|rd|th)\b',r'\1',content)
                    if label not in header_content or not header.get('header_title'):raise ValueError('REVIEW_PUBLICATION_HEADER_DATE_MISMATCH')
                    if normalized(header['header_title']) not in content:raise ValueError('REVIEW_PUBLICATION_HEADER_TITLE_MISMATCH')
            identity=evidence(review['identity_evidence'])
            aliases=registry[pid]['aliases']+[registry[pid]['name']]
            if not any(normalized(a) in identity for a in aliases if len(a)>4):raise ValueError('REVIEW_PROJECT_NAME_NOT_IN_IDENTITY_PAGE')
            date_content=evidence(review['date_evidence'])
            if review['date_precision'] not in ('DAY','MONTH','YEAR'):raise ValueError('REVIEW_DATE_PRECISION_REQUIRED')
            effective_day=datetime.strptime(effective,'%Y-%m-%d')
            date_labels=[normalized(effective_day.strftime(fmt).lstrip('0')) for fmt in ('%d %B %Y','%d %b %Y')]
            if role=='RESOURCE_EFFECTIVE_DATE' and review['date_precision']=='MONTH':
                interval=month_interval(effective)
                if review.get('effective_date_interval')!=interval or effective!=interval[1]:
                    raise ValueError('REVIEW_RESOURCE_MONTH_INTERVAL_REQUIRED')
                date_labels=[normalized(effective_day.strftime(fmt)) for fmt in ('%B %Y','%b-%y')]
            if role=='RESOURCE_EFFECTIVE_DATE' and not any(label in date_content for label in date_labels):
                raise ValueError('REVIEW_EFFECTIVE_DATE_NOT_IN_SOURCE')
            if role!='RESOURCE_EFFECTIVE_DATE' and effective!=pub:raise ValueError('REVIEW_DISCLOSURE_DATE_ROLE_MISMATCH')
            interval=review.get('effective_date_interval')
            if interval and not interval[0]<=effective==interval[1]<=pub:raise ValueError('REVIEW_EFFECTIVE_DATE_INTERVAL_MISMATCH')
            for e in review.get('scope_evidence',[]):evidence(e)
            from .partial_resource import validate_partial_resource
            partial_contract=validate_partial_resource(review,doc,evidence)
            hm=review.get('bulk_hm_percent')
            if hm:
                content=evidence(hm['evidence'])
                from .technical_tables import number_token
                parsed=number_token(hm['original_token'])
                if not parsed or parsed['value']!=hm['value'] or not 0<hm['value']<=100 or normalized(hm['original_token']) not in content:
                    raise ValueError('REVIEW_HM_FRACTION_TOKEN_MISMATCH')
                if not hm.get('basis_markers') or any(normalized(m) not in content for m in hm['basis_markers']):
                    raise ValueError('REVIEW_HM_BASIS_EVIDENCE_REQUIRED')
                from .source_cells import validate_cell
                validate_cell(doc,hm.get('cell_binding'),'bulk_hm_percent',hm['original_token'],'%',review['scope'],selected_sections=review.get('selected_resource_sections'))
            treo_grade=review.get('bulk_treo_grade_pct')
            if treo_grade:
                content=evidence(treo_grade['evidence'])
                from .technical_tables import number_token
                parsed=number_token(treo_grade['original_token'])
                if not parsed or parsed['value']!=treo_grade['value'] or not 0<treo_grade['value']<=100:
                    raise ValueError('REVIEW_TREO_GRADE_TOKEN_MISMATCH')
                matching=[v for v in review.get('observations',[]) if v['variable']=='grade' and
                    v['basis']=='TREO' and v['unit']=='%' and v['value']==treo_grade['value'] and
                    v.get('cell_binding')==treo_grade.get('cell_binding')]
                if len(matching)!=1:raise ValueError('REVIEW_TREO_FACTOR_REQUIRES_SELECTED_RESOURCE_GRADE')
                from .source_cells import validate_cell
                validate_cell(doc,treo_grade.get('cell_binding'),'grade',treo_grade['original_token'],'%',review['scope'],selected_sections=review.get('selected_resource_sections'))
            rows=[]
            for value in review.get('observations',[]):
                if not isinstance(value['value'],(int,float)) or isinstance(value['value'],bool) or not math.isfinite(value['value']) or value['value']<0:
                    raise ValueError('REVIEW_NONFINITE_OR_NEGATIVE_VALUE')
                e=value['evidence'];content=evidence(e)
                if not e.get('render_sha256'):
                    token=normalized(str(value.get('original_token',value['value'])))
                    if not re.search(r'(?<![\d.])'+re.escape(token)+r'(?![\d.])',content):raise ValueError('REVIEW_NUMERIC_TOKEN_NOT_ON_PAGE')
                variable=value['variable'];unit=value['unit'];basis=value['basis']
                from .technical_tables import number_token
                token_value=number_token(value.get('original_token',value['value']))
                original_unit=value.get('original_unit',unit)
                factors={('t','Mt'):1e-6,('kt','Mt'):.001,('t','kt TREO'):.001,('kg','kt TREO'):1e-6,('kt','kt TREO'):1,('ppm','%'):.0001}
                factor=1 if original_unit==unit else factors.get((original_unit,unit))
                if original_unit=='%' and unit=='ppm' and basis in ELEMENTS and variable.startswith('reported_resource_'):
                    factor=10000
                if original_unit=='%HM':
                    if not hm or value['evidence']['page']!=hm['evidence']['page']:raise ValueError('REVIEW_HM_NORMALIZATION_REQUIRES_SAME_TABLE')
                    if not token_value or token_value['value'] is None or not 0<=token_value['value']<=100:raise ValueError('REVIEW_HM_PERCENT_OUT_OF_RANGE')
                    factor=hm['value']/100 if variable=='grade' and unit=='%' else hm['value']*100 if basis in ELEMENTS and unit=='ppm' else None
                if original_unit=='%TREO':
                    if not treo_grade:raise ValueError('REVIEW_TREO_NORMALIZATION_REQUIRES_SELECTED_GRADE')
                    if not token_value or token_value['value'] is None or not 0<=token_value['value']<=100:raise ValueError('REVIEW_TREO_PROPORTION_OUT_OF_RANGE')
                    factor=treo_grade['value']*100 if basis in ELEMENTS and unit=='ppm' else None
                if not token_value or token_value['value'] is None or factor is None or not math.isclose(token_value['value']*factor,value['value'],rel_tol=1e-12,abs_tol=1e-10):
                    raise ValueError('REVIEW_ORIGINAL_TOKEN_UNIT_TRANSFORM_MISMATCH')
                if variable=='ore_mt' and (unit!='Mt' or basis!='TREO' or value['value']<=0):raise ValueError('REVIEW_ORE_UNIT_OR_BASIS')
                if variable=='grade' and (unit not in ('ppm','%') or basis!='TREO' or value['value']<=0 or value['value']>(100 if unit=='%' else 1000000)):
                    raise ValueError('REVIEW_GRADE_UNIT_OR_BASIS')
                if variable=='contained_treo_kt' and (unit!='kt TREO' or basis!='TREO'):raise ValueError('REVIEW_CONTAINED_UNIT_OR_BASIS')
                group=variable=='reported_resource_magnet_ppm' and basis=='PrNdDyTb_OXIDES'
                if variable.startswith('reported_resource_') and ((basis not in ELEMENTS and not group) or unit!='ppm' or value['value']>1000000):raise ValueError('REVIEW_RESOURCE_OXIDE_UNIT_OR_BASIS')
                if basis in ELEMENTS and not e.get('render_sha256') and normalized(basis) not in content:
                    raise ValueError('REVIEW_OXIDE_HEADER_NOT_ON_PAGE')
                if variable not in ('ore_mt','grade','contained_treo_kt') and not variable.startswith('reported_resource_'):
                    raise ValueError('REVIEW_UNSUPPORTED_OBSERVATION')
                from .source_cells import validate_cell
                binding=value.get('cell_binding')
                if binding and binding.get('page')!=e['page']:raise ValueError('REVIEW_CELL_EVIDENCE_PAGE_MISMATCH')
                if binding and basis in ELEMENTS and binding.get('basis')!=basis:raise ValueError('REVIEW_CELL_BASIS_MISMATCH')
                cell_method=validate_cell(doc,binding,variable,str(value.get('original_token',value['value'])),original_unit,review['scope'],selected_sections=review.get('selected_resource_sections'))
                raw=dict(review_id=review['review_id'],variable=variable,value=value['value'],unit=unit,basis=basis,
                    source_sha256=sha,source_key=review['source_key'],scope=review['scope'],statement_id=review['statement_id'],
                    effective_date=effective,effective_date_role=role,date_precision=review['date_precision'],
                    effective_date_interval=review.get('effective_date_interval'),rounding_half_width=value.get('rounding_half_width'),
                    source_kind=review.get('source_kind','ISSUER_TECHNICAL_DISCLOSURE'),
                    original_token=value.get('original_token'),evidence=e,cell_binding=binding,
                    original_unit=original_unit,bulk_hm_percent=hm,
                    grade_input=value.get('grade_input'),
                    normalization='RESOURCE_TREO_GRADE_X_REPORTED_OXIDE_PERCENT_OF_TREO' if original_unit=='%TREO' else None,
                    **({'bulk_treo_grade_pct':treo_grade,'basis_transform':'TREO_PROPORTION_TO_BULK_PPM'} if original_unit=='%TREO' else {}),
                    material_basis='RESOURCE_ORE_GRADE_MAGNET_OXIDE_GROUP_PPM' if group else 'RESOURCE_ORE_GRADE_OXIDE_PPM' if basis in ELEMENTS else 'RESOURCE_BULK_ORE',
                    review_method=cell_method,
                    **({'partial_resource_projection':partial_contract} if partial_contract else {}))
                row=dict(obs_id=digest([pid,sha,raw]),entity_id=pid,variable=variable,value=value['value'],unit=unit,basis=basis,
                    source_sha=sha,scope=review['scope'],statement_id=review['statement_id'],effective_date=effective,
                    category='MEASURED_INDICATED_INFERRED_TOTAL',status='AUTO_VALIDATED',locator='physical PDF p'+str(e['page']),raw=canonical(raw))
                rows.append(row)
            if rows:
                if not review.get('scope_evidence'):raise ValueError('REVIEW_RESOURCE_SCOPE_EVIDENCE_REQUIRED')
                scope_content=' '.join(evidence(e) for e in review['scope_evidence'])
                categories=review.get('resource_categories',['MEASURED','INDICATED','INFERRED'])
                if not categories or len(set(categories))!=len(categories) or not set(categories)<={'MEASURED','INDICATED','INFERRED'}:
                    raise ValueError('REVIEW_RESOURCE_CATEGORY_INVALID')
                if 'resource' not in scope_content or not all(word.lower() in scope_content for word in categories):
                    raise ValueError('REVIEW_RESOURCE_CATEGORY_EVIDENCE_REQUIRED')
                for row in rows:row['category']='_'.join(categories)+'_TOTAL'
                from .project_summary import resource_bundle
                bundle,reason=resource_bundle(rows,partial_resource=partial_contract)
                if bundle is None:raise ValueError('REVIEW_RESOURCE_BUNDLE_'+reason)
                grades={r['basis']:r['value'] for r in rows if r['basis'] in ELEMENTS}
                if not partial_contract and all(e in grades for e in ELEMENTS):
                    grade_ppm=bundle['value']['grade_pct']*10000
                    tolerance=review['oxide_sum_tolerance_ppm']
                    if tolerance<0 or tolerance>max(150,grade_ppm*.02):raise ValueError('REVIEW_OXIDE_TOLERANCE_EXCESSIVE')
                    if abs(sum(grades.values())-grade_ppm)>tolerance:raise ValueError('REVIEW_OXIDE_SUM_CONFLICT')
                if not partial_contract and all(e in grades for e in MAGNET):
                    pct=sum(grades[e] for e in MAGNET)/(bundle['value']['grade_pct']*10000)*100
                    if not 0<=pct<=100:raise ValueError('REVIEW_MAGNET_RATIO_OUT_OF_RANGE')
                    raw=dict(json.loads(rows[0]['raw']),variable='magnet_reo_share_pct',value=pct,unit='%',
                        basis='PrNdDyTb_OXIDES_OVER_TREO',transform='SUM_FOUR_RESOURCE_OXIDE_PPM_DIVIDED_BY_MATCHED_TREO_PPM')
                    rows.append(dict(rows[0],obs_id=digest([pid,sha,raw]),variable='magnet_reo_share_pct',value=pct,unit='%',
                        basis='PrNdDyTb_OXIDES_OVER_TREO',raw=canonical(raw)))
                selection_role=review.get('resource_selection_role','PREFERRED')
                if selection_role not in ('PREFERRED','CONTEXT_ONLY'):raise ValueError('REVIEW_RESOURCE_SELECTION_ROLE_INVALID')
                if selection_role=='CONTEXT_ONLY' and not review.get('context_selection_reason'):
                    raise ValueError('REVIEW_CONTEXT_SELECTION_REASON_REQUIRED')
                if selection_role=='PREFERRED':
                    observations.setdefault(pid,[]).extend(rows)
                    contract=(sha,review['scope'],review['statement_id'],effective)
                    if pid in resource_contracts and resource_contracts[pid]!=contract:raise ValueError('REVIEW_MULTIPLE_PREFERRED_RESOURCE_SOURCES')
                    resource_contracts[pid]=contract
                    if not review.get('selection_reason'):raise ValueError('REVIEW_RESOURCE_SELECTION_REASON_REQUIRED')
                    preferences[pid]=sha
                    if partial_contract:
                        if pid in partial_contracts and partial_contracts[pid]!=partial_contract:raise ValueError('REVIEW_MULTIPLE_PARTIAL_RESOURCE_CONTRACTS')
                        partial_contracts[pid]=partial_contract
                    label=review.get('summary_resource_scope_label')
                    if label:
                        if normalized(label) not in scope_content:raise ValueError('REVIEW_SUMMARY_SCOPE_LABEL_NOT_IN_SOURCE')
                        resource_labels[pid]=dict(label=label,source_sha256=sha,scope=review['scope'])
            study=review.get('study');parameter_methods={}
            if study:
                if study['scale'] not in ('PFS_MODEL','DFS_MODEL','SCOPING_MODEL'):raise ValueError('REVIEW_STUDY_SCALE_NOT_FORECAST')
                for e in study['evidence']:evidence(e)
                for key,value in study['parameters'].items():
                    if key not in ('average_annual_treo_product_t','average_annual_ndpr_product_t','average_annual_hreo_product_t'):
                        raise ValueError('REVIEW_UNSUPPORTED_FORECAST_PARAMETER')
                    if not isinstance(value,(int,float)) or not math.isfinite(value) or value<0:raise ValueError('REVIEW_INVALID_FORECAST_VALUE')
                    if not study.get('annual_basis_evidence'):raise ValueError('REVIEW_ANNUAL_TIME_BASIS_REQUIRED')
                    evidence(study['annual_basis_evidence'])
                    # Every declared forecast number is independently located on
                    # an evidence page, rather than copied from the review file alone.
                    token=str(value) if not float(value).is_integer() else f'{int(value):,}'
                    annual_page=text(study['annual_basis_evidence']['page'])
                    derivation=study.get('parameter_derivations',{}).get(key)
                    if derivation:
                        expected='ANNUAL_PRODUCT_MASS_X_TREO_FRACTION' if key=='average_annual_treo_product_t' else 'ANNUAL_PRODUCT_MASS_X_TREO_FRACTION_X_NDPR_SHARE' if key=='average_annual_ndpr_product_t' else None
                        if derivation.get('method')!=expected:raise ValueError('REVIEW_ANNUAL_DERIVATION_PARAMETER_MISMATCH')
                        annual_product_derivation(derivation,value,study['annual_basis_evidence']['page'],evidence)
                        from .source_cells import validate_cell
                        for item in derivation['inputs']:
                            field='annual_input_'+item['name'];unit='t' if item['name']=='annual_product_t' else '%'
                            binding=item.get('cell_binding')
                            if binding and binding.get('page')!=study['annual_basis_evidence']['page']:raise ValueError('REVIEW_CELL_EVIDENCE_PAGE_MISMATCH')
                            validate_cell(doc,binding,field,item['original_token'],unit,review['scope'],selected_sections=study.get('selected_input_sections'))
                        parameter_methods[key]='DERIVED_FROM_SOURCE_BOUND_PRODUCT_CELLS'
                    else:
                        if token not in annual_page and str(value) not in annual_page:raise ValueError('REVIEW_FORECAST_NUMBER_NOT_ON_PAGE')
                        from .source_cells import validate_cell
                        binding=study.get('parameter_bindings',{}).get(key)
                        if binding and binding.get('page')!=study['annual_basis_evidence']['page']:raise ValueError('REVIEW_CELL_EVIDENCE_PAGE_MISMATCH')
                        parameter_methods[key]=validate_cell(doc,binding,key,str(value),binding.get('original_unit') if binding else 'tpa',review['scope'],study.get('selected_scenario'))
                    if key=='average_annual_ndpr_product_t' and not re.search(r'NdPr|Nd.Pr|Neodymium',annual_page,re.I):raise ValueError('REVIEW_NDPR_FORECAST_HEADER_MISSING')
                d=dict(case_id=review['review_id'],locator='physical PDF '+','.join(str(e['page']) for e in study['evidence']),
                    parameters=study['parameters'],parameter_derivations=study.get('parameter_derivations',{}),parameter_bindings=study.get('parameter_bindings',{}),parameter_review_methods=parameter_methods,review_id=review['review_id'],scope=review['scope'],effective_date_role=role)
                studies.setdefault(pid,[]).append(dict(case_id=review['review_id'],project_id=pid,source_sha=sha,
                    effective_date=effective,scope=review['scope'],stage=study['stage'],endpoint=study['endpoint'],
                    element=study['element'],scale=study['scale'],status='PRIMARY_SCOPED_CASE_NOT_OPERATING_OUTCOME',raw=canonical(d)))
            for attribute in review.get('attributes',[]):
                content=evidence(attribute['evidence']);column=attribute['column'];value=attribute['value']
                if column=='未上市公司':
                    proof=attribute.get('listing_proof')
                    if proof:
                        if value!='否':raise ValueError('REVIEW_LISTING_VALUE_INVALID')
                        from .reviewed_metadata import validate_listing_proof
                        validate_listing_proof(doc,proof,evidence)
                    elif value!='否' or not re.search(r'\bASX\s*:\s*[A-Z0-9]+',text(attribute['evidence']['page'])) or not re.search(r'100%\s*[-\u2010\u2011]\s*owned',content):
                        raise ValueError('REVIEW_LISTING_AND_PROJECT_OWNERSHIP_NOT_ESTABLISHED')
                elif column=='開發商':
                    if normalized(value) not in content:raise ValueError('REVIEW_DEVELOPER_NOT_ON_PAGE')
                elif column=='礦床型態代碼':
                    if value!='iac' or not re.search('ionic adsorption clay|ionic-adsorption clay',content):raise ValueError('REVIEW_IAC_CLASSIFICATION_NOT_EXPLICIT')
                else:raise ValueError('REVIEW_UNSUPPORTED_ATTRIBUTE')
                old=[a for a in attributes.get(pid,[]) if a['column']==column]
                if old and old[0]['value']!=value:raise ValueError('REVIEW_CONFLICTING_ATTRIBUTES')
                attributes.setdefault(pid,[]).append(dict(attribute,source_sha=sha,review_id=review['review_id'],effective_date=effective))
            for field in review.get('deferred_fields',[]):
                evidence(field['evidence'])
                deferred.setdefault(pid,{})[field['column']]=dict(field,source_sha256=sha,review_id=review['review_id'])
            sources[sha]=dict(key=review['source_key'],kind='pdf',sha256=sha,path=str(path),url=review['url'],
                publication_date=pub,available_date=ledger['acquired_through'],review_id=review['review_id'],
                publication_date_role=review.get('publication_date_role','REVIEWED_RELEASE_HEADER'),document_issue_date=review.get('document_issue_date'),
                publication_date_precision=review.get('publication_date_precision','DAY'),publication_date_interval=review.get('publication_date_interval'),
                source_kind=review.get('source_kind','ISSUER_TECHNICAL_DISCLOSURE'),
                effective_date_role=role,date_precision=review['date_precision'],
                resource_effective_date_unknown=review.get('resource_effective_date_unknown',False),
                public_release_date_unknown=review.get('public_release_date_unknown',False))
            receipts.append(dict(review_id=review['review_id'],project_id=pid,source_sha256=sha,status='VALIDATED',scope=review['scope'],
                review_methods=sorted({json.loads(row['raw'])['review_method'] for row in rows}|set(parameter_methods.values())),
                resource_selection_role=review.get('resource_selection_role','PREFERRED') if rows else None,
                partial_resource_projection=partial_contract,
                resource_effective_date_unknown=review.get('resource_effective_date_unknown',False),
                public_release_date_unknown=review.get('public_release_date_unknown',False),
                publication_date_role=review.get('publication_date_role','REVIEWED_RELEASE_HEADER'),
                new_observations=len(rows),forecast_parameters=len(study['parameters']) if study else 0,
                effective_date=effective,effective_date_role=role,date_precision=review['date_precision'],
                effective_date_interval=review.get('effective_date_interval')))
    return dict(sources=sources,observations=observations,studies=studies,resource_preferences=preferences,resource_contracts=resource_contracts,receipts=receipts,attributes=attributes,deferred_fields=deferred,resource_labels=resource_labels,partial_resource_contracts=partial_contracts,
        ledger_sha256=filehash(ledger_path),acquired_through=ledger['acquired_through'])


def audit_candidate_cohort(root,audit_dir,ledger_path,out):
    """Record four checks for every original candidate without deleting old issues."""
    from .pdf_extract import project_registry,_matches,candidate_value_issues,narrative_context_issues
    root=Path(root);audit_dir=Path(audit_dir);out=Path(out);out.mkdir(parents=True,exist_ok=True)
    registry=project_registry(root);reviews=json.loads(Path(ledger_path).read_text('utf8'))['reviews']
    assessment=json.loads((audit_dir/'assessment.json').read_text('utf8'))['documents']
    cohort={c['case_id']:c for c in json.loads((audit_dir/'cohort.json').read_text('utf8'))['cases']}
    rows=[]
    for source in assessment:
        path=audit_dir/source['extraction_path']
        if filehash(path)!=source['extraction_sha256']:raise ValueError('CANDIDATE_ARTIFACT_HASH_MISMATCH')
        data=json.loads(path.read_text('utf8'));pages={p['physical_page']:p for p in data['pages']}
        header_date=publication_date(data['pages'][0]['text'])
        disclosure_date_check=('HEADER_DATE_CONFIRMED' if header_date==source['publication_date'] else
            'IMMUTABLE_ARCHIVE_DATE_ONLY' if header_date is None else 'PUBLICATION_DATE_CONFLICT')
        primary=_matches(data['pages'][0]['text'][:2500],registry)
        primary_id=primary[0]['entity_id'] if len(primary)==1 else None
        doc_reviews=[r for r in reviews if r['source_sha256']==source['source_sha256']]
        review_pid={r['project_id'] for r in doc_reviews}
        if len(review_pid)==1:primary_id=next(iter(review_pid))
        for original in data['candidates']:
            c=dict(original);page=pages[c['physical_page']];pid=c.get('project_id')
            local=_matches(c.get('context','')+' '+c['raw_text'],registry)
            local_ids={p['entity_id'] for p in local}
            binding=normalized(c['raw_text']) in normalized(page['text'])
            if not pid and primary_id and (not local_ids or local_ids=={primary_id}):pid=primary_id
            project_state='EXPLICIT_PROJECT_CONTEXT' if pid and (local_ids in ({pid},set())) and (not primary_id or primary_id==pid) else 'UNRESOLVED_OR_PEER_PROJECT_CONTEXT'
            c['project_id']=pid
            alias=next((p['aliases'] for p in registry if p['entity_id']==pid),[])
            remaining=set(original.get('issues',[])+candidate_value_issues(c)+narrative_context_issues(c,page,version='scientific-context-v5-peer-boundary',project_aliases=alias))
            if project_state=='EXPLICIT_PROJECT_CONTEXT':remaining.discard('PROJECT_ATTRIBUTION_AMBIGUOUS')
            if not binding:remaining.add('PAGE_TEXT_BINDING_FAILED')
            matches=[]
            if c['kind']=='RESOURCE_TABLE_TOTAL':
                for r in doc_reviews:
                    observations=r.get('observations',[])
                    values={o['variable']:o for o in observations}
                    evidence_pages={o['evidence']['page'] for o in observations}|{e['page'] for e in r.get('scope_evidence',[])}
                    if not {'ore_mt','grade'}<=values.keys() or c['physical_page'] not in evidence_pages:continue
                    parsed=c.get('values',{});units=c.get('units',{})
                    ore=parsed.get('ore_mt');grade=parsed.get('grade')
                    expected_grade=values['grade']['value'];expected_unit=values['grade']['unit']
                    if not isinstance(ore,(int,float)) or not isinstance(grade,(int,float)):continue
                    if units.get('grade')!=expected_unit or units.get('ore_mt')!='Mt':continue
                    if abs(ore-values['ore_mt']['value'])<=.05 and abs(grade-expected_grade)<=.5:matches.append(r['review_id'])
            if matches:
                decision='SOURCE_REVIEWED_RESOURCE_CORROBORATION';project_state='REVIEW_IDENTITY_CONFIRMED'
                unit_state='REVIEW_ROW_AND_HEADER_CONFIRMED';scope_state='REVIEWED_GLOBAL_OR_FIXED_DEPOSIT_SCOPE';date_state='REVIEW_RESOURCE_DATE_ROLE_CONFIRMED'
                # Preserve the initial problems alongside the separate, stronger review.
                pid=next(r['project_id'] for r in doc_reviews if r['review_id']==matches[0])
            else:
                unit_state='NOT_NUMERIC' if c['kind']=='SCOPED_TEXT_DISCLOSURE' else 'NUMERIC_TOKEN_CHECK_PASSED' if not candidate_value_issues(c) else 'UNRESOLVED_NUMERIC_TOKEN_OR_UNIT'
                scope_state='RESOURCE_SCOPE_REQUIRES_SOURCE_REVIEW' if c['kind']=='RESOURCE_TABLE_TOTAL' else 'LOCAL_TEST_OR_DISCLOSURE_SCOPE_ONLY'
                date_state='DISCLOSURE_DATE_NOT_RESOURCE_EFFECTIVE_DATE'
                if not binding:decision='UNRESOLVED_PAGE_BINDING'
                elif 'RESERVE_SUBSET_NOT_RESOURCE' in remaining:decision='EXCLUDED_RESERVE_FROM_RESOURCE_FIELDS'
                elif project_state!='EXPLICIT_PROJECT_CONTEXT':decision='UNRESOLVED_PROJECT_ATTRIBUTION'
                elif c['kind']=='RESOURCE_TABLE_TOTAL':decision='UNRESOLVED_RESOURCE_UNIT_SCOPE_OR_EFFECTIVE_DATE'
                elif c['kind']=='TECHNICAL_TABLE_CELL':decision='TESTWORK_CELL_NOT_PROJECT_RESOURCE_OR_ANNUAL_OUTPUT'
                elif 'FORWARD_LOOKING_NOT_COMPLETED_EVENT' in remaining:decision='FORWARD_LOOKING_NOT_COMPLETED_STAGE'
                elif remaining:decision='UNRESOLVED_SCIENTIFIC_CONTEXT'
                else:decision='VALIDATED_LOCAL_TEXT_CONTEXT_NOT_A_NUMERIC_SUMMARY_FIELD'
            rows.append(dict(candidate_id=original['candidate_id'],source_sha256=source['source_sha256'],case_id=source['case_id'],
                physical_page=c['physical_page'],kind=c['kind'],project_id=pid or '',project_check=project_state,unit_check=unit_state,
                scope_check=scope_state,effective_date_check=date_state,decision=decision,review_ids=canonical(matches),
                publication_date=source['publication_date'],publication_date_check=disclosure_date_check,
                original_issues=canonical(original.get('issues',[])),remaining_issues=canonical(sorted(remaining)),
                summary_admission='ONLY_EXPLICIT_VALIDATED_LEDGER_VALUES;NO_BULK_CANDIDATE_PROMOTION'))
    with (out/'candidate_validation.csv').open('w',encoding='utf-8-sig',newline='') as stream:
        writer=csv.DictWriter(stream,list(rows[0]));writer.writeheader();writer.writerows(rows)
    result=dict(original_candidates=len(rows),unique_candidate_ids=len({r['candidate_id'] for r in rows}),
        decisions=dict(Counter(r['decision'] for r in rows)),reviewed_resource_candidate_corrobations=sum(bool(json.loads(r['review_ids'])) for r in rows),
        source_review_ledger_sha256=filehash(ledger_path),interpretation='CHECKED_AND_CLASSIFIED;UNRESOLVED_IS_NOT_ABSENCE_OR_APPROVAL')
    (out/'candidate_validation.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf8')
    return result


def compare_summaries(before,after,out,allow_expansion=False):
    before=Path(before);after=Path(after);out=Path(out);out.mkdir(parents=True,exist_ok=True)
    def read(path):
        with (path/'專案總表.csv').open(encoding='utf-8-sig',newline='') as f:
            reader=csv.DictReader(f);rows=list(reader);return reader.fieldnames,{r['專案ID']:r for r in rows}
    columns,old=read(before);other,new=read(after)
    if columns!=other or (not set(old)<=set(new) if allow_expansion else set(old)!=set(new)):
        raise ValueError('SUMMARY_COMPARISON_COHORT_OR_COLUMNS_CHANGED')
    provenance={}
    with (after/'field_provenance.csv').open(encoding='utf-8-sig') as f:
        for row in csv.DictReader(f):provenance[row['project_id'],row['column']]=row
    changes=[];filled=Counter();updated=Counter();withdrawn=Counter();format_only=0;remaining=Counter()
    gaps={}
    if (after/'missing_fields.csv').exists():
        with (after/'missing_fields.csv').open(encoding='utf-8-sig') as f:gaps={(r['project_id'],r['column']):r for r in csv.DictReader(f)}
    for pid in old:
        for column in columns:
            a=old[pid][column];b=new[pid][column]
            if b=='':remaining[column]+=1
            if a==b:continue
            numeric_equal=False
            if a and b:
                try:numeric_equal=math.isclose(float(a),float(b),rel_tol=1e-12,abs_tol=1e-12)
                except ValueError:pass
            status='NEWLY_FILLED' if not a and b else 'NUMERIC_FORMAT_ONLY' if numeric_equal else 'UPDATED_VALUE' if b else 'BECAME_UNKNOWN'
            if status=='NEWLY_FILLED':filled[column]+=1
            elif status=='UPDATED_VALUE':updated[column]+=1
            elif status=='NUMERIC_FORMAT_ONLY':format_only+=1
            elif status=='BECAME_UNKNOWN':withdrawn[column]+=1
            p=provenance.get((pid,column),{});gap=gaps.get((pid,column),{})
            changes.append(dict(project_id=pid,project_name=new[pid]['專案名稱'],column=column,before=a,after=b,status=status,
                source_sha256=p.get('source_sha256',''),source_url=p.get('source_url',''),locator=p.get('locator',''),method=p.get('method',''),
                scope=p.get('scope',''),effective_date=p.get('effective_date',''),effective_date_role=p.get('effective_date_role',''),review_ids=p.get('review_ids',''),
                withdrawal_reason=gap.get('reason','') if status=='BECAME_UNKNOWN' else ''))
    with (out/'field_changes.csv').open('w',encoding='utf-8-sig',newline='') as f:
        fields=list(changes[0]) if changes else ['project_id','project_name','column','before','after','status','source_sha256','source_url','locator','method','scope','effective_date','effective_date_role','review_ids','withdrawal_reason']
        w=csv.DictWriter(f,fields);w.writeheader();w.writerows(changes)
    result=dict(rows=len(old),columns=len(columns),newly_filled_cells=sum(filled.values()),newly_filled_column_types=len(filled),
        projects_with_new_values=len({r['project_id'] for r in changes if r['status']=='NEWLY_FILLED'}),new_cells_by_column=dict(filled),
        updated_value_cells=sum(updated.values()),updated_cells_by_column=dict(updated),numeric_format_only_cells=format_only,
        became_unknown_cells=sum(withdrawn.values()),became_unknown_by_column=dict(withdrawn),net_filled_cell_increase=sum(filled.values())-sum(withdrawn.values()),
        remaining_blank_cells=sum(remaining.values()),remaining_blanks_by_column=dict(remaining),
        baseline_csv_sha256=filehash(before/'專案總表.csv'),updated_csv_sha256=filehash(after/'專案總表.csv'))
    if allow_expansion:
        added=[new[k] for k in sorted(set(new)-set(old))]
        result.update(comparison_scope='FIXED_BASELINE_COHORT;NEW_PROJECT_CELLS_REPORTED_SEPARATELY',expanded_rows=len(new),
            added_project_ids=[r['專案ID'] for r in added],added_project_filled_cells=sum(v!='' for r in added for v in r.values()),
            added_project_blank_cells=sum(v=='' for r in added for v in r.values()),
            expanded_remaining_blank_cells=sum(v=='' for r in new.values() for v in r.values()),
            expanded_filled_cells=sum(v!='' for r in new.values() for v in r.values()))
    (out/'field_increment.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    return result
