"""Explicit research-project additions; never mutate or silently merge the Census."""
import json, re
from datetime import date, datetime
from pathlib import Path
from .store import digest, filehash


def project_id(key):
    return 'AU-'+digest(['reviewed_project_extension_v1',key])[:20]


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
    if not proof.get('markers') or label not in text or any(m.casefold() not in text for m in proof['markers']):
        raise ValueError('DISCOVERY_DOCUMENT_ISSUE_DATE_PROOF')


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
                    if (identity.get('source_kind')!='GOVERNMENT_PROJECT_CATALOGUE' or
                        not (urlsplit(s['url']).hostname or '').endswith('.gov.au') or
                        identity.get('publication_date_interval')!=interval or day!=interval[1]):
                        raise ValueError('DISCOVERY_EDITION_MONTH_REQUIRED')
                    catalogue_month_proof(d,day,text,identity.get('publication_month_role','EDITION_MONTH'))
                if identity.get('date_evidence_role') == 'DOCUMENT_ISSUE_DATE_WITH_ASX_URL_RELEASE_DATE':
                    if identity.get('publication_date_precision', 'DAY') != 'DAY':raise ValueError('DISCOVERY_ISSUE_DATE_PRECISION')
                    validate_issue_date(identity, s, cutoff, text)
                elif identity.get('date_evidence_role') or identity.get('document_issue_date'):
                    raise ValueError('DISCOVERY_UNSUPPORTED_DATE_ROLE')
                elif label not in re.sub(r'\b(\d{1,2})(?:st|nd|rd|th)\b',r'\1',text) or any(m.casefold() not in text for m in proof['markers']):raise ValueError('DISCOVERY_PUBLICATION_DATE_PROOF')
                e=identity['project_evidence'];text=' '.join(d[e['page']-1].get_text(sort=True).split()).casefold()
                if (not e['markers'] or not identity.get('name_marker') or identity['name_marker'].casefold() not in text or
                    any(m.casefold() not in text for m in e['markers']) or identity['state_marker'].casefold() not in text):
                    raise ValueError('DISCOVERY_PROJECT_STATE_PROOF')
                developer=identity.get('developer');raw={}
                if developer:
                    proof=developer['evidence'];content=' '.join(d[proof['page']-1].get_text(sort=True).split()).casefold()
                    if not developer['value'] or developer['value'].casefold() not in content or not proof['markers'] or any(m.casefold() not in content for m in proof['markers']):raise ValueError('DISCOVERY_DEVELOPER_PROOF')
                    raw['developer']=developer['value']
                pending=[]
                from .iteration_review import SCIENCE_INDEXES
                columns=json.loads((Path(__file__).resolve().parents[2]/'config/project_summary_columns.json').read_text('utf8'))
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
            records.append(dict(entity_id=pid,source_sha=sha,state=identity['state'],latitude=None,longitude=None,deposit_type=None,
                raw=json.dumps(raw),kind='PROJECT',native_id=key))
            deferred[pid]={f['column']:dict(f,source_sha256=sha,review_id='discovery:'+key) for f in pending}
            receipt.update(project_id=pid,scope=r['scope'],identity=identity,deferred_fields=pending)
        receipts.append(receipt)
    return dict(projects=projects,records=records,sources=sources,receipts=receipts,deferred_fields=deferred,ledger_sha256=filehash(path),acquired_through=cfg['acquired_through'])
