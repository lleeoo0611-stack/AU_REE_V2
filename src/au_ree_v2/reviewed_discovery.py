"""Explicit research-project additions; never mutate or silently merge the Census."""
import json, re
from datetime import date, datetime
from pathlib import Path
from .store import digest, filehash


def project_id(key):
    return 'AU-'+digest(['reviewed_project_extension_v1',key])[:20]


def calendar_date_text(text):
    """Normalize ordinal day and a comma after a spelled-out month only."""
    text=re.sub(r'\b(\d{1,2})(?:st|nd|rd|th)\b',r'\1',text,flags=re.I)
    months='January February March April May June July August September October November December'.split()
    return re.sub(r'\b('+'|'.join(months)+r'),(?=\s+20\d{2}\b)',r'\1',text,flags=re.I)


def validate_issue_date(identity, source, cutoff, text):
    """Separate a PDF's signed issue date from its ASX dated-URL release date.

    The caller must already have verified source bytes and URL/hash receipt.
    This never treats a signature as a PDF release header.
    """
    from urllib.parse import urlsplit
    if identity.get('date_evidence_role') != 'DOCUMENT_ISSUE_DATE_WITH_ASX_URL_RELEASE_DATE':
        raise ValueError('DISCOVERY_ISSUE_DATE_ROLE')
    if identity.get('publication_date_role') != 'ASX_DATED_URL':
        raise ValueError('DISCOVERY_RELEASE_DATE_ROLE')
    u = urlsplit(source['url'])
    m = re.fullmatch(r'/asxpdf/(\d{8})/pdf/[A-Za-z0-9]+\.pdf', u.path)
    if (u.scheme != 'https' or u.netloc != 'announcements.asx.com.au'
            or u.query or u.fragment or not m or source.get('kind') != 'pdf'):
        raise ValueError('DISCOVERY_RELEASE_URL_PROOF')
    released = datetime.strptime(m.group(1), '%Y%m%d').date()
    published = date.fromisoformat(identity['publication_date'])
    issued = date.fromisoformat(identity['document_issue_date'])
    if released != published or issued > released or released > date.fromisoformat(cutoff):
        raise ValueError('DISCOVERY_ISSUE_RELEASE_DATE_ORDER')
    proof = identity['date_evidence']
    label = issued.strftime('%d %B %Y').lstrip('0').casefold()
    if not proof.get('markers') or label not in calendar_date_text(text) or any(m.casefold() not in text for m in proof['markers']):
        raise ValueError('DISCOVERY_DOCUMENT_ISSUE_DATE_PROOF')


def validate_state_bridge(identity, sources, primary_project_text, assets, cutoff):
    """Location-only bridge between explicitly named, same-issuer originals.

    The dated identity original still proves project and issuer. A second,
    captured ASX original may supply a literal state, never quantities or title.
    """
    import pymupdf
    from urllib.parse import urlsplit
    bridge=identity['state_bridge']
    def fail(code):raise ValueError('DISCOVERY_STATE_BRIDGE_'+code)
    idx=bridge.get('source_index')
    if (bridge.get('mode')!='DATED_ASX_SAME_PROJECT_AND_ISSUER_STATE_ONLY'
            or not isinstance(idx,int) or not 0<=idx<len(sources)
            or idx==identity['source_index'] or not bridge.get('source_key')):fail('CONTRACT')
    source=sources[idx];u=urlsplit(source['url'])
    match=re.fullmatch(r'/asxpdf/(\d{8})/pdf/[A-Za-z0-9]+\.pdf',u.path)
    if (source['kind']!='pdf' or u.scheme!='https' or u.netloc!='announcements.asx.com.au'
            or u.query or u.fragment or not match):fail('DATED_URL')
    day=datetime.strptime(match[1],'%Y%m%d').date().isoformat()
    if day>identity['publication_date'] or day>cutoff:fail('DATE_ORDER')
    marker=identity['name_marker'].casefold()
    issuer=re.sub(r'\s+(?:limited|ltd\.?)$','',identity.get('developer',{}).get('value','').casefold())
    if (len(marker)<4 or len(issuer)<3 or bridge.get('issuer_marker','').casefold()!=issuer
            or not re.search(r'(?<!\w)'+re.escape(marker)+r'(?!\w)',primary_project_text)
            or not re.search(r'(?<!\w)'+re.escape(issuer)+r'(?!\w)',primary_project_text)):fail('PRIMARY_PROJECT_ISSUER')
    with pymupdf.open(Path(assets[source['asset_set']])/source['path']) as doc:
        proof=bridge['project_evidence'];pn=proof['page']
        if not isinstance(pn,int) or not 1<=pn<=len(doc):fail('PAGE')
        text=' '.join(doc[pn-1].get_text(sort=True).split()).casefold()
        from .pdf_extract import publication_date
        header=publication_date(doc[0].get_text(sort=True))
        if header and header!=day:fail('HEADER_DATE_CONFLICT')
        if (not proof.get('markers') or any(' '.join(m.split()).casefold() not in text for m in proof['markers'])
                or any(not re.search(r'(?<!\w)'+re.escape(token)+r'(?!\w)',text)
                       for token in (marker,issuer,identity['state_marker'].casefold()))):fail('NAMED_PROJECT_ISSUER_STATE')
    return dict(source=source,publication_date=day,source_key=bridge['source_key'],page=pn)


def validate_discovery(path, assets, existing, cutoff):
    import pymupdf
    cfg=json.loads(Path(path).read_text('utf8'))
    if cfg.get('version')!='reviewed-project-discovery-v1':raise ValueError('DISCOVERY_VERSION')
    if cfg.get('cutoff')!=cutoff:raise ValueError('DISCOVERY_CUTOFF_MISMATCH')
    date.fromisoformat(cfg['acquired_through'])
    names={re.sub(r'\W+','',a.casefold()) for p in existing for a in [p['name'],*p['aliases']]}
    ids={p['entity_id'] for p in existing};seen=set();projects=[];records=[];sources={};receipts=[];deferred={}
    for r in cfg['candidates']:
        key=r['candidate_key']
        if key in seen:raise ValueError('DISCOVERY_DUPLICATE_CANDIDATE')
        seen.add(key)
        if not r.get('sources'):raise ValueError('DISCOVERY_SOURCE_REQUIRED')
        if r['decision'] not in ('ADMIT_PROJECT','CANDIDATE_ONLY','EXISTING_PROJECT','ALIAS_OR_CHILD','PROCESSING_ONLY','OUTSIDE_AU'):
            raise ValueError('DISCOVERY_DISPOSITION_REQUIRED')
        for s in r['sources']:
            root=Path(assets[s['asset_set']]).resolve();pdf=(root/s['path']).resolve()
            if root not in pdf.parents or filehash(pdf)!=s['sha256']:raise ValueError('DISCOVERY_SOURCE_HASH_OR_PATH')
            if (root/'downloads.json').exists():
                captured=json.loads((root/'downloads.json').read_text('utf8'))
                matches=[c for c in captured if c['url']==s['url'] and c.get('document_sha256')==s['sha256'] and c['status'] in ('PDF_ACQUIRED','HTML_CAPTURED')]
            elif (root/'data/manifest.json').exists():
                captured=json.loads((root/'data/manifest.json').read_text('utf8'))['snapshots']
                matches=[c for c in captured if c['url']==s['url'] and c['sha256']==s['sha256']]
            else:raise ValueError('DISCOVERY_RECEIPT_MISSING')
            if not matches:raise ValueError('DISCOVERY_URL_HASH_NOT_CAPTURED')
            if s['kind']=='pdf':
                with pymupdf.open(pdf) as d:
                    for e in s['evidence']:
                        if not 1<=e['page']<=len(d):raise ValueError('DISCOVERY_PAGE_INVALID')
                        text=' '.join(d[e['page']-1].get_text(sort=True).split()).casefold()
                        if not e['markers'] or any(' '.join(m.split()).casefold() not in text for m in e['markers']):raise ValueError('DISCOVERY_MARKER_MISMATCH:'+key)
            else:
                text=' '.join(pdf.read_text('utf8').split()).casefold()
                if not s['evidence'] or any(not e['markers'] or any(' '.join(m.split()).casefold() not in text for m in e['markers']) for e in s['evidence']):raise ValueError('DISCOVERY_MARKER_MISMATCH:'+key)
        receipt=dict(candidate_key=key,name=r['name'],decision=r['decision'],reason=r['reason'],
            existing_candidate_ids=r.get('existing_candidate_ids',[]),sources=r['sources'])
        if r.get('round5_review'):receipt['followup_review']=r['round5_review']
        if r.get('round6_review'):receipt['round6_review']=r['round6_review']
        if r['decision']=='ADMIT_PROJECT':
            identity=r['identity'];s=r['sources'][identity['source_index']]
            if s['kind']!='pdf' or not r.get('scope') or r.get('country')!='AU':raise ValueError('DISCOVERY_ADMISSION_SCOPE_REQUIRED')
            state_labels={'TAS':'Tasmania','QLD':'Queensland','WA':'Western Australia','SA':'South Australia','NT':'Northern Territory','NSW':'New South Wales','VIC':'Victoria','ACT':'Australian Capital Territory'}
            if identity['state'] not in state_labels or identity['state_marker'] not in (identity['state'],state_labels[identity['state']]):raise ValueError('DISCOVERY_STATE_LABEL_MISMATCH')
            day=identity['publication_date'];date.fromisoformat(day)
            if day>cutoff:raise ValueError('DISCOVERY_ADMISSION_AFTER_CUTOFF')
            # Admission requires a dated original, not today's undated project webpage.
            with pymupdf.open(Path(assets[s['asset_set']])/s['path']) as d:
                proof=identity['date_evidence'];text=' '.join(d[proof['page']-1].get_text(sort=True).split()).casefold()
                value=datetime.strptime(day,'%Y-%m-%d')
                label=value.strftime('%d %B %Y').lstrip('0').casefold()
                if identity.get('publication_date_precision')=='MONTH':
                    from urllib.parse import urlsplit
                    from .asx_validation import month_interval,catalogue_month_proof
                    interval=month_interval(day);label=value.strftime('%B %Y').casefold()
                    archived_report = identity.get('source_kind')=='GOVERNMENT_ARCHIVED_TECHNICAL_REPORT'
                    if (identity.get('source_kind') not in ('GOVERNMENT_PROJECT_CATALOGUE','GOVERNMENT_ARCHIVED_TECHNICAL_REPORT') or
                        not (urlsplit(s['url']).hostname or '').endswith('.gov.au') or
                        identity.get('publication_date_interval')!=interval or day!=interval[1]):
                        raise ValueError('DISCOVERY_EDITION_MONTH_REQUIRED')
                    if archived_report:
                        # A report's stated month bounds its dated evidence; it
                        # is never an invented exact public release day.
                        if (identity.get('publication_month_role')!='REPORT_MONTH'
                            or identity.get('publication_date_role')!='REPORT_MONTH_UPPER_BOUND_NOT_RELEASE_DATE'
                            or not re.search(r'\bdate\s+of\s+report\s*:\s*'+re.escape(label)+r'\b',text)):
                            raise ValueError('DISCOVERY_REPORT_MONTH_PROOF')
                    else:
                        catalogue_month_proof(d,day,text,identity.get('publication_month_role','EDITION_MONTH'))
                if identity.get('date_evidence_role') == 'DOCUMENT_ISSUE_DATE_WITH_ASX_URL_RELEASE_DATE':
                    if identity.get('publication_date_precision', 'DAY') != 'DAY':raise ValueError('DISCOVERY_ISSUE_DATE_PRECISION')
                    validate_issue_date(identity, s, cutoff, text)
                elif identity.get('date_evidence_role') or identity.get('document_issue_date'):
                    raise ValueError('DISCOVERY_UNSUPPORTED_DATE_ROLE')
                elif label not in calendar_date_text(text) or any(m.casefold() not in text for m in proof['markers']):raise ValueError('DISCOVERY_PUBLICATION_DATE_PROOF')
                e=identity['project_evidence'];text=' '.join(d[e['page']-1].get_text(sort=True).split()).casefold()
                if (not e['markers'] or not identity.get('name_marker') or identity['name_marker'].casefold() not in text or
                    any(m.casefold() not in text for m in e['markers'])):
                    raise ValueError('DISCOVERY_PROJECT_STATE_PROOF')
                state_bridge=None
                if identity.get('state_bridge'):
                    state_bridge=validate_state_bridge(identity,r['sources'],text,assets,cutoff)
                elif identity['state_marker'].casefold() not in text:
                    raise ValueError('DISCOVERY_PROJECT_STATE_PROOF')
                developer=identity.get('developer');raw={}
                if developer:
                    proof=developer['evidence'];content=' '.join(d[proof['page']-1].get_text(sort=True).split()).casefold()
                    if not developer['value'] or developer['value'].casefold() not in content or not proof['markers'] or any(m.casefold() not in content for m in proof['markers']):raise ValueError('DISCOVERY_DEVELOPER_PROOF')
                    raw['developer']=developer['value']
                pending=[]
                from .iteration_review import SCIENCE_INDEXES
                columns=json.loads((Path(__file__).resolve().parents[2]/'config/project_summary_columns_legacy52.json').read_text('utf8'))
                for field in r.get('deferred_fields',[]):
                    proof=field['evidence'];content=' '.join(d[proof['page']-1].get_text(sort=True).split()).casefold()
                    if field['column'] not in {columns[i] for i in SCIENCE_INDEXES} or not proof['markers'] or any(m.casefold() not in content for m in proof['markers']):raise ValueError('DISCOVERY_DEFERRED_FIELD_PROOF')
                    pending.append(field)
            aliases=r['aliases'];pid=project_id(key)
            normalized={re.sub(r'\W+','',a.casefold()) for a in [r['name'],*aliases]}
            if pid in ids or normalized & names:raise ValueError('DISCOVERY_DUPLICATE_PROJECT_OR_ALIAS')
            ids.add(pid);names.update(normalized)
            source_key=identity['source_key'];sha=s['sha256']
            if sha in sources and sources[sha]['key']!=source_key:
                raise ValueError('DISCOVERY_SHARED_SOURCE_KEY_CONFLICT')
            sources[sha]=dict(sha256=sha,key=source_key,url=s['url'],path=s['path'],kind='pdf',publication_date=day,
                document_issue_date=identity.get('document_issue_date'),publication_date_role=identity.get('publication_date_role'),
                date_evidence_role=identity.get('date_evidence_role'),
                publication_date_precision=identity.get('publication_date_precision','DAY'),publication_date_interval=identity.get('publication_date_interval'),
                available_date=cfg['acquired_through'],source_kind=identity.get('source_kind','ISSUER_PROJECT_IDENTITY'),asset_root=str(Path(assets[s['asset_set']]).resolve()))
            projects.append(dict(entity_id=pid,native_id=key,name=r['name'],aliases=aliases,identity_source=source_key,reviewed_extension=True))
            records.append(dict(entity_id=pid,source_sha=sha,state=None if state_bridge else identity['state'],latitude=None,longitude=None,deposit_type=None,
                raw=json.dumps(raw),kind='PROJECT',native_id=key))
            if state_bridge:
                ss=state_bridge['source'];state_sha=ss['sha256'];state_key=state_bridge['source_key']
                if state_sha in sources and sources[state_sha]['key']!=state_key:raise ValueError('DISCOVERY_SHARED_SOURCE_KEY_CONFLICT')
                sources[state_sha]=dict(sha256=state_sha,key=state_key,url=ss['url'],path=ss['path'],kind='pdf',
                    publication_date=state_bridge['publication_date'],available_date=cfg['acquired_through'],
                    source_kind='LOCATION_ONLY_SAME_NAMED_PROJECT_AND_ISSUER',asset_root=str(Path(assets[ss['asset_set']]).resolve()))
                records.append(dict(entity_id=pid,source_sha=state_sha,state=identity['state'],latitude=None,longitude=None,
                    deposit_type=None,raw=json.dumps(dict(state_only_evidence_page=state_bridge['page'])),kind='PROJECT',native_id=key))
            deferred[pid]={f['column']:dict(f,source_sha256=sha,review_id='discovery:'+key) for f in pending}
            receipt.update(project_id=pid,scope=r['scope'],identity=identity,deferred_fields=pending)
        receipts.append(receipt)
    return dict(projects=projects,records=records,sources=sources,receipts=receipts,deferred_fields=deferred,ledger_sha256=filehash(path),acquired_through=cfg['acquired_through'])
