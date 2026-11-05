"""Bounded official/issuer link discovery; raw bytes precede any observations."""
import hashlib
import json
import re
import io
from pypdf import PdfReader
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlsplit, urldefrag, quote
from .acquisition import request, failure_details
from .security import sensitive_reference
from .store import append_snapshots, filehash

DOCUMENT_TERMS = {
    'Resource': ['JORC mineral resource', 'mineral resource estimate'],
    'Strategic': ['rare earth oxide composition', 'mineral resource'],
    'Technical': ['metallurgical testwork', 'mineralogy NORM recovery'],
    'Development': ['feasibility study', 'scoping study'],
    'Commercial': ['project financing offtake', 'quarterly activities'],
    'Infrastructure': ['feasibility infrastructure', 'project infrastructure'],
}


def centralized_feasibility(root, fetch=None):
    """Record documentation; a relative example is not an authorized API origin."""
    import time
    from .store import canonical
    fetch=fetch or request;root=Path(root);receipts=[]
    url='https://datadirector.weblink.com.au/knowledge-base/weblink-data-api/'
    start=time.monotonic()
    try:
        raw,headers=fetch(url)
        sha=hashlib.sha256(raw).hexdigest();path=root/'data/snapshots'/(sha+'.html')
        if not path.exists():path.write_bytes(raw)
        if filehash(path)!=sha:raise ValueError('IMMUTABLE_DOCUMENTATION_MISMATCH')
        now=datetime.now(timezone.utc).isoformat()
        entry=dict(key='weblink_api_documentation',kind='source_documentation',url=url,sha256=sha,path=path.relative_to(root).as_posix(),acquired_at=now,available_date=now[:10])
        manifest_path=root/'data/manifest.json';manifest=json.loads(manifest_path.read_text())
        if not any(s['key']==entry['key'] and s['sha256']==sha for s in manifest['snapshots']):manifest['snapshots'].append(entry)
        append_snapshots(manifest_path,manifest['snapshots'])
        text=re.sub('<[^>]+>',' ',raw.decode('utf8'));text=' '.join(text.split())
        receipts.append(dict(url=url,status='DOCUMENTATION_RETRIEVED_NOT_API_SUCCESS',sha256=sha,acquired_at=now,requests=1,elapsed_seconds=time.monotonic()-start,
            pagination_parameters=[p for p in ('year','headlinesPerPage','pageNumber','category','sensitive') if p in text],
            relative_route_documented='/api/headline/' in text,verified_api_base_url=None,authentication=None,research_usage_authorization=None,
            evidence_quote='Let us know your requirements so we can help further.' if 'Let us know your requirements' in text else None,
            conclusion='ACCESS_CONDITIONS_NOT_ESTABLISHED_NO_BATCH_CALL',
            required_provider_information=['service base URL','authentication','licensed research use and redistribution','history coverage','pagination termination semantics'],
            contact_sent=False,purchase=False))
    except Exception as exc:receipts.append(dict(url=url,status='DOCUMENTATION_UNAVAILABLE',**failure_details(exc),elapsed_seconds=time.monotonic()-start))
    targets=[dict(symbol='NTU',year=2025,known_document='Browns Range DFS'),dict(symbol='REE',year=2023,known_document='Cummins enhanced scoping study')]
    result=dict(version='centralized-feasibility-v1',status='BOUNDED_DOCUMENTATION_CHECK',weblink=receipts,predeclared_targets=targets,
        company_year_api_test='NOT_EVALUATED_ACCESS_CONDITIONS_NOT_ESTABLISHED',known_document_recall=None,new_documents=0,new_usable_fields=0,
        efficiency_comparison='NOT_ESTIMABLE_WITHOUT_AUTHORIZED_INDEX; no time-saving claim',investorhub_investi='SUPPLEMENTARY_NOT_NEW_ADAPTERS')
    (root/'data/phase16_centralized_feasibility.json').write_text(canonical(result)+'\n',encoding='utf8')
    return result


def search_tasks(root, registry, diagnostics=None, db=None, snapshots=None):
    """Registry-derived jobs reuse issuer endpoints; missing endpoints stay unknown.

    Aliases and company/ASX identifiers are discovery context, never entity
    equivalence or authority to attribute company funds to a project.
    """
    from .pdf_extract import project_registry
    manifest=json.loads((Path(root)/'data/manifest.json').read_text(encoding='utf-8'))['snapshots']
    registered_path=Path(root)/'config/sources.json'
    registered={s['key']:s for s in json.loads(registered_path.read_text(encoding='utf-8'))['sources']} if registered_path.exists() else {}
    sources={s['key']:s for s in manifest};tasks=[]
    own_db=None
    if db is None and registry.get('canonical_store'):
        import sqlite3
        store=Path(root)/registry['canonical_store']
        if store.exists():
            own_db=sqlite3.connect(store.resolve().as_uri()+'?mode=ro',uri=True,timeout=30);own_db.row_factory=sqlite3.Row;db=own_db
    try:projects=project_registry(root,db,snapshots or list(sources.values()))
    finally:
        if own_db is not None:own_db.close()
    for p in projects:
        source={**registered.get(p['identity_source'],{}),**sources.get(p['identity_source'],{})}
        code=source.get('asx_code');code_evidence=None
        if registry.get('task_execution_version') and not code and source.get('kind')=='pdf':
            # Search context only, read from existing verified issuer header.
            try:
                if filehash(Path(root)/source['path'])!=source['sha256']:raise ValueError('SOURCE_HASH_MISMATCH')
                import pymupdf
                with pymupdf.open(Path(root)/source['path']) as pdf:
                    codes=set(re.findall(r'\bASX\s*[:|]\s*([A-Z][A-Z0-9]{1,4})\b',pdf[0].get_text(sort=True)))
                if len(codes)==1:code=next(iter(codes));code_evidence=source['sha256']
            except (ValueError,OSError):pass
        matches=[s for s in registry['seeds'] if s.get('project_id')==p['entity_id'] or
                 any(a.casefold() in json.dumps(s).casefold() for a in p['aliases'])]
        tasks.append(dict(project_id=p['entity_id'],project_name=p['name'],aliases=p['aliases'],
                          state=p.get('state') or source.get('state'),
                          company=source.get('company'),asx_code=code,asx_code_evidence_sha256=code_evidence,
                          source_key=p['identity_source'],source_url=source.get('url'),
                          queries=[a+' '+kind for a in p['aliases'] for kind in ('mineral resource','metallurgical','feasibility','financing')],
                          seed_keys=[s['key'] for s in matches],
                          status='BOUNDED_ISSUER_SEARCH_TASK' if matches else 'SEARCH_ENDPOINT_NOT_CONFIGURED_UNKNOWN'))
    if diagnostics is None:return tasks
    import csv
    with Path(diagnostics).open(encoding='utf-8',newline='') as stream:gaps=list(csv.DictReader(stream))
    coverage={}
    shared_sources={}
    for g in gaps:
        coverage.setdefault(g['project_id'],{})[g['criterion']]=g['status']=='VALID_SCORABLE_EVIDENCE'
        for sha in json.loads(g['source_shas']):shared_sources.setdefault(sha,set()).add((g['project_id'],g['criterion']))
    prior=Path(root)/'data/discovery_latest.json'
    failures=json.loads(prior.read_text()).get('sources',[]) if prior.exists() else []
    versions={s.get('source_sha256') for s in manifest if s['kind']=='document_extraction'}
    by_id={t['project_id']:t for t in tasks};jobs=[]
    for g in gaps:
        if g['status']=='VALID_SCORABLE_EVIDENCE':continue
        t=by_id.get(g['project_id'])
        if not t:continue
        shas=json.loads(g['source_shas']);docs=[s for s in manifest if s['sha256'] in shas and s['kind']=='pdf']
        docs=sorted({s['sha256']:s for s in docs}.values(),key=lambda s:(s['sha256'] in versions,s['key']))
        score={'Resource':90,'Strategic':80,'Technical':85,'Commercial':75,'Infrastructure':65,'Development':70}.get(g['domain'],60)
        score+=10 if g['raw_evidence']=='0' else 0
        components=None
        if registry.get('gap_priority_version')=='evidence-yield-v1':
            # These are transparent search-budget heuristics, not confidence,
            # geological quality, admission or probabilities of successful yield.
            unparsed=sum(s['sha256'] not in versions for s in docs)
            scope=coverage.get(g['project_id'],{})
            joint=bool(scope.get('R1') and g['criterion'] in ('S1','D1','TC1','TC2','C1','I1','I2','I3','I4'))
            prior_failures=sum(f.get('seed_key') in t['seed_keys'] and f['status']=='UNAVAILABLE' for f in failures)
            reuse=len(set().union(*(shared_sources.get(s['sha256'],set()) for s in docs))) if docs else 0
            components=dict(domain_gap=score,unparsed_original=25*min(unparsed,2),
                potential_resource_panel_gain=30*int(joint),shared_source_gaps=2*min(reuse,10),
                registered_primary_document=10*int(bool(docs)),search_endpoint=5*int(bool(t['seed_keys'])),
                repeated_failure_cost=-5*min(prior_failures,3))
            score=sum(components.values())
        jobs.append(dict(t,domain=g['domain'],criterion=g['criterion'],gap_state=g['status'],
            existing_evidence_shas=shas,selection_reason=g['selection_reason'],extraction_failures=json.loads(g['exclusion_reasons']),
            prior_search_failures=[f for f in failures if f.get('seed_key') in t['seed_keys'] and f['status']=='UNAVAILABLE'],
            expected_document_types={'Resource':['JORC_RESOURCE'],'Technical':['METALLURGICAL','DFS','PFS'],'Commercial':['FINANCING','OFFTAKE','QUARTERLY']}.get(g['domain'],['DATED_PRIMARY_DOCUMENT']),
            priority=score,priority_basis='EVIDENCE_YIELD_HEURISTIC_NOT_PREDICTED_SUCCESS_OR_FORMAL_ADMISSION' if components else 'DOMAIN_GAP_AND_EXISTING_EVIDENCE_REUSE_NOT_FORMAL_ADMISSION',
            **({'priority_components':components,'cost_model':'EXISTING_BYTES_BEFORE_NETWORK;FAILURES_PENALIZED_NOT_PERMANENTLY_BLOCKED',
                'potential_joint_sample_gain':int(joint),'unparsed_originals':unparsed} if components else {}),
            queries=[a+' '+term for a in t['aliases'] for term in DOCUMENT_TERMS.get(g['domain'],['technical report'])],
            reusable_documents=[dict(key=s['key'],url=s['url'],sha256=s['sha256'],publication_date=s.get('publication_date')) for s in docs]))
    return sorted(jobs,key=lambda t:(-t['priority'],t['project_id'],t['criterion']))


class Links(HTMLParser):
    def __init__(self):
        super().__init__(); self.links=[]; self.current=None;self.row_text=None;self.row_links=[];self.link_dates={}
    def handle_starttag(self, tag, attrs):
        if tag=='a': self.current=[dict(attrs).get('href',''),'']
        if tag=='tr':self.row_text='';self.row_links=[]
    def handle_data(self, data):
        if self.current is not None:self.current[1]+=data
        if self.row_text is not None:self.row_text+=' '+data
    def handle_endtag(self, tag):
        if tag=='a' and self.current is not None:
            self.links.append(self.current);self.row_links.append(self.current[0]); self.current=None
        if tag=='tr' and self.row_text is not None:
            dates=re.findall(r'\b\d{2}/\d{2}/20\d{2}\b',self.row_text)
            if len(set(dates))==1:
                try:
                    date=datetime.strptime(dates[0],'%d/%m/%Y').date().isoformat()
                    self.link_dates.update({href:date for href in self.row_links})
                except ValueError:pass
            self.row_text=None;self.row_links=[]


def candidates(raw, seed):
    parser=Links(); parser.feed(raw.decode('utf-8',errors='replace'))
    rows={}
    for href,label in parser.links:
        url=urldefrag(urljoin(seed['url'],href))[0]
        host=urlsplit(url).hostname
        if urlsplit(url).scheme!='https' or host not in seed['allowed_hosts'] or sensitive_reference(url):continue
        if seed.get('keywords') and not any(k.casefold() in (url+' '+label).casefold() for k in seed['keywords']):continue
        if not re.search(seed.get('pattern',r'\.pdf(?:[?\s]|$)|displayAnnouncement\.do\?display=pdf'),url+' '+label,re.I):continue
        key=hashlib.sha256(url.encode()).hexdigest()
        rows[key]={'candidate_id':key,'url':url,'title':label.strip(),'seed_key':seed['key'],
                   'publication_date':parser.link_dates.get(href),'status':'DISCOVERED_NOT_OBSERVATION',
                   'authority':'ISSUER_LINKED_DELIVERY_NOT_CONTENT_VERIFIED' if seed.get('authority')=='ISSUER' else 'SOURCE_AUTHORITY_NOT_ESTABLISHED',
                   'project_id':seed.get('project_id'),'identity_status':'SOURCE_CONTEXT_ONLY_NOT_EQUIVALENCE'}
    return list(rows.values())  # Preserve issuer feed order; hashes are not chronology.


def official_reports(registry, tasks, fetch, save, originals=()):
    """Official metadata -> candidate documents, within the existing manifest.

    Report IDs are source identities, never Project IDs. Name/company matches
    remain candidate relations; no entity mutation or resource admission here.
    """
    from .acquisition import arcgis,ckan
    from .security import public_export
    reports=[];outcomes=[];seeds=[];documents=[]
    for source in registry.get('official_reports',[]):
        key=source['key'];url=source['url'];page_shas=[]
        def archive(raw):
            sha=save(raw,dict(key=key+'_response_'+hashlib.sha256(raw).hexdigest()[:16],
                kind='discovery_receipt',url=url,metadata_only=True),'.json')
            page_shas.append(sha)
        try:
            if source['protocol']=='arcgis':
                data=arcgis(url,source['where'],archive=archive,fetch=fetch,max_records=source.get('max_records',30))
                records=[dict(native_id='WAMEX:A'+str(f['attributes']['anumber']),
                    title=f['attributes'].get('title'),attributes=f['attributes'],geometry=f.get('geometry'),
                    spatial_reference=data['spatialReference'],
                    detail_url=f['attributes'].get('dpxe_rep'),report_year=f['attributes'].get('report_year'),
                    released_date=(datetime.fromtimestamp(f['attributes']['date_released']/1000,timezone.utc).date().isoformat()
                                   if f['attributes'].get('date_released') else None),
                    resources=[]) for f in data['features']]
            elif source['protocol']=='ckan':
                data=ckan(url,source['query'],source.get('rows',10),source.get('max_pages',2),fetch,archive)
                for item in data['results'][:source.get('max_package_show',2)]:
                    try:
                        raw,_=fetch(url.rstrip('/')+'/package_show',{'id':item['id']});archive(raw)
                        shown=json.loads(raw)
                        if shown.get('success') is not True or shown['result'].get('id')!=item['id']:
                            raise ValueError('CKAN_PACKAGE_IDENTITY_MISMATCH')
                        item.update(shown['result'])
                    except Exception as exc:
                        outcomes.append(dict(seed_key=key+'_package_'+item['id'],url=url,status='UNAVAILABLE',metadata_only=True,**failure_details(exc)))
                records=[dict(native_id='GSQ:'+r['name'],package_id=r['id'],title=r.get('title'),
                    attributes=r,detail_url=urljoin(url,'/dataset/'+r['name']),
                    released_date=r.get('open_file_date'),resources=r.get('resources',[])) for r in data['results']]
            else:raise ValueError('UNSUPPORTED_OFFICIAL_REPORT_PROTOCOL')
            for record in records:
                record.update(source_key=key,metadata_sha256=page_shas,identity_status='OFFICIAL_REPORT_NOT_PROJECT',
                    relation_status='CANDIDATE_ONLY_NO_ENTITY_EQUIVALENCE')
                text=json.dumps(record.get('attributes',{}),ensure_ascii=False).casefold()
                record['project_candidates']=[]
                for task in tasks:
                    aliases=[a for a in task['aliases'] if len(a)>=5 and a.casefold() in text]
                    company=task.get('company');company_match=bool(company and company.casefold() in text)
                    if aliases:record['project_candidates'].append(dict(project_id=task['project_id'],
                        alias_matches=aliases,company_match=company_match,
                        decision='CANDIDATE_REQUIRES_INDEPENDENT_SCOPE_AND_IDENTITY_EVIDENCE'))
                record['document_candidates']=[]
                for resource in record['resources']:
                    if str(resource.get('format','')).upper()!='PDF':continue
                    docurl=resource.get('download_url') or resource.get('url','');rid=resource.get('id')
                    status='DISCOVERED_BUDGET_DEFERRED'
                    # Signed credentials stay out of receipts/manifest/logs.
                    if sensitive_reference(docurl):status='SIGNED_LINK_NOT_PUBLISHED_OR_FETCHED'
                    elif urlsplit(docurl).scheme!='https' or urlsplit(docurl).hostname not in source.get('document_hosts',[]):status='UNCONFIGURED_DOCUMENT_HOST'
                    size=resource.get('resource:size','')
                    match=re.fullmatch(r'([\d.]+)\s*(KB|MB|GB)',size,re.I)
                    estimated=float(match[1])*{'KB':1024,'MB':1024**2,'GB':1024**3}[match[2].upper()] if match else None
                    if estimated is not None and estimated>source.get('max_document_bytes',20000000):status='DOCUMENT_SIZE_BUDGET_DEFERRED'
                    item=dict(resource_id=rid,title=resource.get('name'),status=status,estimated_bytes=estimated)
                    if not sensitive_reference(docurl):item['url']=docurl
                    record['document_candidates'].append(item)
                    if status!='DISCOVERED_BUDGET_DEFERRED' or len(seeds)>=registry.get('max_official_documents',4):continue
                    seeds.append(dict(key=key+'_'+hashlib.sha256((record['native_id']+'|'+str(rid)).encode()).hexdigest()[:16],
                        url=docurl,allowed_hosts=source['document_hosts'],authority='OFFICIAL_PUBLIC_REPORT_DELIVERY',
                        report_native_id=record['native_id'],resource_native_id=rid,project_id=None,
                        max_document_bytes=source.get('max_document_bytes',20000000),
                        source_document_version=hashlib.sha256(json.dumps([resource.get(k) for k in ('id','metadata_modified','last_modified','hash','resource:size')]).encode()).hexdigest(),
                        publication_date=record.get('released_date'),metadata_sha256=page_shas))
                    item['status']='QUEUED_DOCUMENT_ACQUISITION'
                if not record['resources'] and record.get('detail_url'):
                    # WAMEX permanent details are public HTML. No assumed private
                    # download API, terms submission or signed-token persistence.
                    record['document_access']='DETAIL_PAGE_REQUIRES_PUBLIC_LINK_DISCOVERY'
                reports.append(public_export(record))
            outcomes.append(dict(seed_key=key,url=url,status='PARSED',sha256=page_shas[-1],
                metadata_only=True,inventory=data['inventory'],reports=len(records)))
        except Exception as exc:outcomes.append(dict(seed_key=key,url=url,status='UNAVAILABLE',**failure_details(exc)))
    # The public WAMEX UI's ReportDocuments_Read transport is a read-only POST.
    # Signed links are transient: public snapshots retain a declared sanitized
    # derivative and SHA of the ignored original, never the bearer URL.
    for report in sorted(reports,key=lambda r:(-int(bool(re.search(r'metallurg|mineralo|mineral process|recover',str(r.get('attributes',{})),re.I))),
                                              -(r.get('report_year') or 0),r['native_id'])):
        if report.get('resources') or not report.get('detail_url') or not report.get('project_candidates'):continue
        if sum(s.get('report_detail') is True for s in outcomes)>=registry.get('max_official_details',2):break
        key='wamex_'+report['native_id'].split(':')[-1];native=report['attributes']['anumber']
        endpoint='https://wamex.dmp.wa.gov.au/Wamex/Search/ReportDetails/ReportDocuments_Read'
        try:
            raw,_=fetch(endpoint,{'aNumber[0]':native,'page':1,'pageSize':20},method='POST')
            data=json.loads(raw)
            if data.get('Errors') or not isinstance(data.get('Total'),int) or not isinstance(data.get('Data'),list):raise ValueError('WAMEX_DOCUMENT_LIST_INVALID')
            if any(r.get('ANumber')!=native for r in data['Data']):raise ValueError('WAMEX_REPORT_IDENTITY_MISMATCH')
            sha=save(raw,dict(key=key+'_document_list',url=report['detail_url'],kind='discovery_receipt',metadata_only=True,omit_signed_urls=True),'.json')
            report['document_list_sha256']=sha;report['document_list_total']=data['Total']
            report['document_list_complete']=len(data['Data'])==data['Total']
            for resource in data['Data']:
                if str(resource.get('FileType','')).lower()!='.pdf':continue
                rid=str(resource['BLTId']);link=resource.get('Link','');size=resource.get('FileSize','')
                match=re.fullmatch(r'([\d.]+)\s*(KB|MB|GB)',size,re.I)
                estimated=float(match[1])*{'KB':1024,'MB':1024**2,'GB':1024**3}[match[2].upper()] if match else None
                item=dict(resource_id=rid,title=resource.get('FileName'),estimated_bytes=estimated,status='DISCOVERED_BUDGET_DEFERRED')
                report['document_candidates'].append(item)
                if re.search(r'logging.?codes|litholog.?codes',item['title'] or '',re.I):
                    item['status']='METHODOLOGY_APPENDIX_RETAINED_NOT_PRIORITY_TECHNICAL_REPORT';continue
                if estimated is None or estimated>registry.get('max_wamex_document_bytes',20000000):
                    item['status']='DOCUMENT_SIZE_UNKNOWN_OR_BUDGET_DEFERRED';continue
                if len(documents)>=registry.get('max_wamex_documents',2):continue
                if urlsplit(link).scheme!='https' or urlsplit(link).hostname!='warsydprdstagsdspub.blob.core.windows.net':
                    item['status']='UNCONFIGURED_DOCUMENT_HOST';continue
                identity=key+'_'+rid
                resource_version=hashlib.sha256(json.dumps([resource.get(k) for k in ('BLTId','FileName','FileSize','EditDate')]).encode()).hexdigest()
                cached=next((s for s in reversed(originals) if s.get('report_native_id')==report['native_id'] and s.get('resource_native_id')==rid and s.get('source_document_version')==resource_version),None)
                if cached:
                    item.update(status='REUSED_VERIFIED_ORIGINAL',document_sha256=cached['sha256'])
                    documents.append(dict(candidate_id=hashlib.sha256(identity.encode()).hexdigest(),source_key=cached['key'],seed_key=key,
                        url=report['detail_url'],document_sha256=cached['sha256'],status='REUSED_VERIFIED_ORIGINAL'))
                    continue
                try:
                    # A signed link is acquired only from the current public
                    # response; it is not copied into the manifest or receipt.
                    body,_=fetch(link,max_bytes=registry.get('max_wamex_document_bytes',20000000))
                    if not body.startswith(b'%PDF'):raise ValueError('NOT_PDF')
                    pdfsha=save(body,dict(key=identity,url=report['detail_url'],kind='pdf',
                        report_native_id=report['native_id'],resource_native_id=rid,original_filename=item['title'],
                        source_document_version=resource_version,
                        metadata_sha256=[sha],**({'publication_date':report['released_date']} if report.get('released_date') else {}),
                        date_role='OPEN_FILE_RELEASE_NOT_RESOURCE_EFFECTIVE_DATE',authority='OFFICIAL_WAMEX_REPORT'),'.pdf')
                    item.update(status='ORIGINAL_ACQUIRED',document_sha256=pdfsha)
                    documents.append(dict(candidate_id=hashlib.sha256(identity.encode()).hexdigest(),source_key=identity,seed_key=key,
                        url=report['detail_url'],title=item['title'],document_sha256=pdfsha,
                        report_native_id=report['native_id'],resource_native_id=rid,status='SNAPSHOT_REQUIRES_DATED_SCOPE_EXTRACTION'))
                except Exception as exc:
                    item.update(status='DOWNLOAD_UNAVAILABLE',**failure_details(exc))
                    documents.append(dict(candidate_id=hashlib.sha256(identity.encode()).hexdigest(),seed_key=key,
                        url=report['detail_url'],title=item['title'],status='DOWNLOAD_UNAVAILABLE',**failure_details(exc)))
            outcomes.append(dict(seed_key=key,url=report['detail_url'],status='PARSED',sha256=sha,report_detail=True))
        except Exception as exc:outcomes.append(dict(seed_key=key,url=report['detail_url'],status='UNAVAILABLE',report_detail=True,**failure_details(exc)))
    return reports,outcomes,seeds,documents


def discover(root, registry, fetch=request, diagnostics=None, task_limit=3):
    import time
    started=time.monotonic()
    root=Path(root);registry=json.loads(json.dumps(registry)); path=root/'data/manifest.json'
    manifest=json.loads(path.read_text(encoding='utf-8')); outcomes=[]; found=[]
    captured_urls={s['url'] for s in manifest['snapshots'] if s['kind']=='pdf'}
    captured={s['url']:s for s in manifest['snapshots'] if s['kind']=='pdf'}
    def save(raw, meta, suffix):
        from .security import public_snapshot
        omit_signed=meta.pop('omit_signed_urls',False)
        signed_fields=[]
        if omit_signed:
            signed_fields=[i for i,r in enumerate(json.loads(raw).get('Data',[])) if sensitive_reference(r.get('Link',''))]
        raw,redaction=public_snapshot(root,raw,suffix)
        if signed_fields:
            data=json.loads(raw)
            for i in signed_fields:data['Data'][i]['Link']='EPHEMERAL_SIGNED_URL_OMITTED'
            raw=(json.dumps(data,sort_keys=True,ensure_ascii=False)+'\n').encode()
            redaction['publication_transform']='SIGNED_DOWNLOAD_URLS_OMITTED_V1'
        meta={**meta,**redaction}
        sha=hashlib.sha256(raw).hexdigest(); dest=root/'data/snapshots'/(sha+suffix)
        if meta.get('kind')=='discovery_receipt':meta['key']='discovery_execution_'+sha[:16]
        if not dest.exists():dest.write_bytes(raw)
        if filehash(dest)!=sha:raise ValueError('IMMUTABLE_SNAPSHOT_CONTENT_MISMATCH')
        now=datetime.now(timezone.utc).isoformat()
        entry={**meta,'sha256':sha,'path':dest.relative_to(root).as_posix(),'acquired_at':now,'available_date':now[:10]}
        if not any(s['key']==entry['key'] and s['sha256']==sha and s.get('source_document_version')==entry.get('source_document_version') for s in manifest['snapshots']):manifest['snapshots'].append(entry)
        return sha
    tasks=search_tasks(root,registry,diagnostics) if registry.get('registry_tasks') or diagnostics else []
    if registry.get('incremental_tasks') and not diagnostics:
        # Resume from the existing immutable execution receipts. No second
        # queue/registry; missing endpoints are attempts, never completed search.
        last={}
        for receipt in manifest['snapshots']:
            if receipt['kind']!='discovery_receipt':continue
            if filehash(root/receipt['path'])!=receipt['sha256']:raise ValueError('DISCOVERY_RECEIPT_HASH_MISMATCH')
            prior=json.loads((root/receipt['path']).read_text(encoding='utf8'))
            for task in prior.get('search_tasks',[]):
                last[task['project_id']]=max(last.get(task['project_id'],''),receipt['acquired_at'])
        ordered=sorted(tasks,key=lambda t:(last.get(t['project_id'],''),t.get('state') or '',t['project_id']))
        selected=[];states=set()
        for task in ordered:
            state=task.get('state') or 'UNKNOWN'
            if state in states:continue
            selected.append(task);states.add(state)
            if len(selected)>=task_limit:break
        tasks=selected
    if diagnostics:
        selected=[];seen_projects=set()
        for task in tasks:
            if task['project_id'] not in seen_projects:
                selected.append(task);seen_projects.add(task['project_id'])
            if len(selected)>=task_limit:break
        tasks=selected
        keys={k for t in tasks for k in t['seed_keys']}
        seeds=[s for s in registry['seeds'] if s['key'] in keys]
        for t in tasks:
            for doc in t['reusable_documents'][:2]:
                seeds.append(dict(key='gap_'+doc['key'],url=doc['url'],allowed_hosts=[urlsplit(doc['url']).hostname],project_id=t['project_id'],reuse_sha256=doc['sha256'],publication_date=doc.get('publication_date')))
        registry=dict(registry,seeds=seeds)
    if registry.get('official_archive_template'):
        codes=set()
        for task in tasks:
            code=task.get('asx_code')
            if not code or code in codes or len(codes)>=registry.get('max_official_archives',2):continue
            codes.add(code);key='asx_archive_'+code
            registry['seeds'].append(dict(key=key,url=registry['official_archive_template'].format(code=quote(code)),
                allowed_hosts=['www.asx.com.au','announcements.asx.com.au'],project_id=task['project_id'],
                authority='EXCHANGE',keywords=['resource','metallurg','feasibility','quarter','annual','financ','scoping','MRE','PFS','DFS','mineral','recovery']))
            task['seed_keys'].append(key)
    if registry.get('public_mirror_index_template'):
        companies=set()
        for task in tasks:
            company=task.get('company')
            if not company or company in companies or len(companies)>=registry.get('max_mirror_indexes',2):continue
            companies.add(company);slug=re.sub(r'[^a-z0-9]+','-',company.casefold()).strip('-')
            key='public_mirror_'+slug
            registry['seeds'].append(dict(key=key,url=registry['public_mirror_index_template'].format(company_slug=slug),
                project_id=task['project_id'],allowed_hosts=['financialfilings.com','cdn.financialreports.eu'],
                authority='PUBLIC_MIRROR_NOT_ISSUER',detail_pattern=r'/filings/[^?#]+/',
                keywords=['resource','metallurg','MRE','PFS','DFS','Scoping','Annual','Quarter','Open in viewer']))
            task['seed_keys'].append(key)
    official_originals=[]
    metadata_by_sha={s['sha256']:s for s in manifest['snapshots']}
    for original in manifest['snapshots']:
        if original['kind']!='pdf' or not original.get('report_native_id') or not registry.get('official_reports'):continue
        if not (root/original['path']).exists() or filehash(root/original['path'])!=original['sha256']:
            outcomes.append(dict(seed_key=original['key'],status='UNAVAILABLE',failure_status='IMMUTABLE_SNAPSHOT_CONTENT_MISMATCH'));continue
        cached=dict(original)
        # Earlier source-bound originals already reference the precise document
        # list used for download. Derive a cache fingerprint from those immutable
        # bytes, without rewriting old manifest entries or redownloading a PDF.
        if cached.get('report_native_id','').startswith('WAMEX:') and not cached.get('source_document_version'):
            for sha in cached.get('metadata_sha256',[]):
                meta=metadata_by_sha.get(sha)
                if not meta or filehash(root/meta['path'])!=sha:raise ValueError('OFFICIAL_METADATA_HASH_MISMATCH')
                for r in json.loads((root/meta['path']).read_text()).get('Data',[]):
                    if str(r.get('BLTId'))==cached.get('resource_native_id'):
                        cached['source_document_version']=hashlib.sha256(json.dumps([r.get(k) for k in ('BLTId','FileName','FileSize','EditDate')]).encode()).hexdigest()
        official_originals.append(cached)
    reports,official_outcomes,official_seeds,official_documents=official_reports(registry,tasks,fetch,save,official_originals)
    outcomes.extend(official_outcomes);registry['seeds'].extend(official_seeds)
    found.extend(official_documents)
    queue=[]
    for seed in registry['seeds']:
        queue.append(dict(seed,pagination_family=seed['key']))
        for url in seed.get('fallback_urls',[]):
            if urlsplit(url).scheme=='https' and urlsplit(url).hostname in seed['allowed_hosts'] and not sensitive_reference(url):
                queue.append(dict(seed,url=url,pagination_family=seed['key'],key=seed['key']+'_alternative_'+hashlib.sha256(url.encode()).hexdigest()[:12],
                                  fallback_urls=[],original_discovery_url=seed['url']))
        queries=list(seed.get('queries',[]))
        if seed.get('search_url_template'):
            queries += [q for t in tasks if seed['key'] in t['seed_keys'] for q in t['queries']]
        for query in list(dict.fromkeys(queries))[:registry.get('max_queries_per_seed',2)]:
            if seed.get('search_url_template'):
                url=seed['search_url_template'].format(query=quote(query))
                if urlsplit(url).scheme=='https' and urlsplit(url).hostname in seed['allowed_hosts'] and not sensitive_reference(url):
                    queue.append(dict(seed,url=url,pagination_family=seed['key'],search_query=query,
                        key=seed['key']+'_search_'+hashlib.sha256(query.encode()).hexdigest()[:12]))
    seen_pages=set();seen_documents=set();page_counts={};document_counts={}
    for seed in queue:
        if seed['url'] in seen_pages:continue
        seen_pages.add(seed['url'])
        family=seed.get('pagination_family',seed['key'])
        page_counts[family]=page_counts.get(family,0)+1
        if page_counts[family]>registry.get('max_pages_per_seed',3):continue
        try:
            cached=next((s for s in manifest['snapshots'] if s['sha256']==seed.get('reuse_sha256')),None)
            if cached and (not seed.get('source_document_version') or seed['source_document_version']==cached.get('source_document_version')):
                if filehash(root/cached['path'])!=cached['sha256']:raise ValueError('IMMUTABLE_SNAPSHOT_CONTENT_MISMATCH')
                found.append(dict(candidate_id=hashlib.sha256(seed['url'].encode()).hexdigest(),url=seed['url'],seed_key=seed['key'],document_sha256=cached['sha256'],source_key=cached['key'],status='REUSED_VERIFIED_ORIGINAL',project_id=seed.get('project_id')))
                outcomes.append(dict(seed_key=seed['key'],status='REUSED_VERIFIED_ORIGINAL',sha256=cached['sha256']));continue
            # Existing verified bytes precede network even for archive links.
            cached=captured.get(seed['url'])
            if cached and (not seed.get('source_document_version') or seed['source_document_version']==cached.get('source_document_version')):
                if filehash(root/cached['path'])!=cached['sha256']:raise ValueError('IMMUTABLE_SNAPSHOT_CONTENT_MISMATCH')
                found.append(dict(candidate_id=hashlib.sha256(seed['url'].encode()).hexdigest(),url=seed['url'],seed_key=seed['key'],source_key=cached['key'],document_sha256=cached['sha256'],status='REUSED_VERIFIED_ORIGINAL',project_id=seed.get('project_id')))
                outcomes.append(dict(seed_key=seed['key'],project_id=seed.get('project_id'),url=seed['url'],status='REUSED_VERIFIED_ORIGINAL',sha256=cached['sha256']));continue
            raw,_=(fetch(seed['url'],max_bytes=seed['max_document_bytes']) if seed.get('max_document_bytes') else fetch(seed['url']))
            if seed.get('resource_native_id') and not raw.startswith(b'%PDF'):
                save(raw,dict(key='non_pdf_'+seed['key'],url=seed['url'],kind='discovery_html'),'.html')
                raise ValueError('NOT_PDF')
            if raw.startswith(b'%PDF'):
                sha=save(raw,{'key':'discovery_'+seed['key'],'url':seed['url'],'kind':'pdf','project_id':seed.get('project_id'),
                    **{k:seed[k] for k in ('report_native_id','resource_native_id','metadata_sha256','source_document_version') if k in seed},
                    'authority':seed.get('authority','SOURCE_AUTHORITY_NOT_ESTABLISHED'),**({'publication_date':seed['publication_date']} if seed.get('publication_date') else {})},'.pdf')
                found.append({'candidate_id':hashlib.sha256(seed['url'].encode()).hexdigest(),'url':seed['url'],'seed_key':seed['key'],'publication_date':seed.get('publication_date'),'document_sha256':sha,'source_key':'discovery_'+seed['key'],'project_id':seed.get('project_id'),'status':'DIRECT_PDF_REQUIRES_DATED_SCOPE_EXTRACTION'})
                outcomes.append({'seed_key':seed['key'],'status':'DIRECT_PDF_CAPTURED','sha256':sha});continue
            sha=save(raw,{'key':'discovery_'+seed['key'],'url':seed['url'],'kind':'discovery_html'},'.html')
            parser=Links();parser.feed(raw.decode('utf-8',errors='replace'))
            if registry.get('task_execution_version'):
                from .pdf_extract import classify
                parser.links.sort(key=lambda link:-sum(label in classify(link[1]) for label in ('JORC_RESOURCE','SCOPING','PFS','DFS','METALLURGICAL')))
            for href,label in parser.links:
                url=urldefrag(urljoin(seed['url'],href))[0]
                if (urlsplit(url).scheme=='https' and urlsplit(url).hostname in seed['allowed_hosts'] and not sensitive_reference(url)
                    and not re.search(r'\.pdf(?:\?|$)|displayAnnouncement\.do\?display=pdf',url,re.I)
                    and (re.search(r'\b(?:next|older)\b',label,re.I) or re.search(r'/page/\d|[?&]page=',url))):
                    queue.append(dict(seed,url=url,key=family+'_page_'+hashlib.sha256(url.encode()).hexdigest()[:12],pagination_family=family,queries=[]))
                elif (seed.get('detail_pattern') and urlsplit(url).scheme=='https'
                      and urlsplit(url).hostname in seed['allowed_hosts'] and not sensitive_reference(url)
                      and re.search(seed['detail_pattern'],url)
                      and any(k.casefold() in (label+' '+url).casefold() for k in seed.get('keywords',[]))):
                    queue.append(dict(seed,url=url,key=family+'_detail_'+hashlib.sha256(url.encode()).hexdigest()[:12],pagination_family=family,queries=[]))
            rows=candidates(raw,seed)
            rows=[r for r in rows if r['url'] not in seen_documents]
            terms=[term for t in tasks if seed.get('project_id')==t['project_id'] or family in t['seed_keys'] for term in DOCUMENT_TERMS.get(t.get('domain'),[])]
            def relevance(row):
                from .pdf_extract import classify
                title=row['title'];labels=classify(title)
                primary=sum(label in labels for label in ('JORC_RESOURCE','SCOPING','PFS','DFS','METALLURGICAL'))
                routine=bool(re.search(r'notice|proxy|webinar|rebalance|annual general meeting',title,re.I))
                return (row['url'] in captured_urls,routine,-primary,-sum(term.casefold() in title.casefold() for term in terms))
            rows.sort(key=relevance)
            budget=max(0,registry.get('max_documents_per_seed',10)-document_counts.get(family,0))
            # Record every discovered identity, including budget deferrals.
            for row in rows:
                if row['url'] in captured:
                    cached=captured[row['url']]
                    if filehash(root/cached['path'])!=cached['sha256']:raise ValueError('IMMUTABLE_SNAPSHOT_CONTENT_MISMATCH')
                    row.update(status='REUSED_VERIFIED_ORIGINAL',document_sha256=cached['sha256'],source_key=cached['key'])
                    found.append(row);seen_documents.add(row['url']);continue
                if document_counts.get(family,0)>=registry.get('max_documents_per_seed',10):
                    if registry.get('task_execution_version'):
                        row['status']='DISCOVERED_BUDGET_DEFERRED';found.append(row)
                    continue
                document_counts[family]=document_counts.get(family,0)+1
                seen_documents.add(row['url'])
                row['discovery_sha256']=sha
                try:
                    doc,_=fetch(row['url'])
                    if not doc.startswith(b'%PDF'):
                        if b'announcementTerms.do' in doc:
                            row['restricted_response_sha256']=save(doc,dict(key='terms_'+row['candidate_id'],url=row['url'],kind='discovery_html'),'.html')
                            row['primary_access_status']='TERMS_INTERSTITIAL_NOT_ACCEPTED'
                            # Never submit terms or infer an unverified distributor URL
                            # from an ASX ID. Other registered endpoints continue.
                            raise ValueError('TERMS_INTERSTITIAL_NOT_ACCEPTED')
                        if not doc.startswith(b'%PDF'):raise ValueError('NOT_PDF')
                    row['document_sha256']=save(doc,{'key':'discovered_'+row['candidate_id'],'url':row['url'],'kind':'pdf','discovery_sha256':sha,
                        'project_id':row.get('project_id'),'authority':row['authority'],'document_identity':row['candidate_id']},'.pdf')
                    captured[row['url']]=next(s for s in manifest['snapshots'] if s['sha256']==row['document_sha256'] and s['url']==row['url'])
                    # A dated original header is a disclosure date, not resource effectiveness.
                    from .pdf_extract import publication_date
                    import pymupdf
                    try:
                        with pymupdf.open(stream=doc,filetype='pdf') as pdf:date=publication_date(pdf[0].get_text(sort=True))
                    except Exception:date=None  # Original bytes survive parser failure below.
                    if date and row.get('publication_date') and date!=row['publication_date']:
                        row['date_conflict']=[date,row['publication_date']];date=None
                        captured[row['url']]['date_conflict']=row['date_conflict']
                    else:date=date or row.get('publication_date')
                    if date:
                        row['publication_date']=date
                        captured[row['url']]['publication_date']=date
                    row['status']='SNAPSHOT_REQUIRES_DATED_SCOPE_EXTRACTION'
                    try:
                        reader=PdfReader(io.BytesIO(doc));row['physical_pages']=len(reader.pages)
                        row['text_quality']='REQUIRES_PAGE_VALIDATION_NO_AUTOMATIC_NUMERIC_EXTRACTION'
                    except Exception:
                        try:
                            import pymupdf
                            with pymupdf.open(stream=doc,filetype='pdf') as reader:row['physical_pages']=len(reader)
                            row['text_quality']='NATIVE_PYPDF_UNAVAILABLE_MUPDF_READABLE_REQUIRES_PAGE_VALIDATION'
                        except Exception:row['status']='SNAPSHOT_PDF_PARSE_FAILED'
                except Exception as exc:row.update(status='DOWNLOAD_UNAVAILABLE',**failure_details(exc))
                found.append(row)
            outcomes.append({'seed_key':seed['key'],'project_id':seed.get('project_id'),'url':seed['url'],'search_query':seed.get('search_query'),'status':'PARSED','links_found':len(rows),'links_attempted':min(len(rows),budget),'sha256':sha,'limitation':'BOUNDED_STATIC_HTML_SEARCH_AND_LINKED_PAGINATION_NO_JAVASCRIPT'})
        except Exception as exc:
            outcomes.append({'seed_key':seed['key'],'project_id':seed.get('project_id'),'url':seed['url'],'search_query':seed.get('search_query'),'status':'UNAVAILABLE',**failure_details(exc)})
            if seed.get('resource_native_id'):
                found.append(dict(candidate_id=hashlib.sha256(seed['url'].encode()).hexdigest(),seed_key=seed['key'],url=seed['url'],
                    report_native_id=seed['report_native_id'],resource_native_id=seed['resource_native_id'],
                    status='DOWNLOAD_UNAVAILABLE',**failure_details(exc)))
    append_snapshots(path,manifest['snapshots'])
    result={'version':'discovery-v4-evidence-gaps' if diagnostics else 'discovery-v3-registry-tasks' if tasks else 'discovery-v2',
            'execution_mode':registry.get('execution_mode','PUBLIC_ENDPOINTS'), 'sources':outcomes,'documents':found}
    if reports:result['official_reports']=reports
    if registry.get('official_reports'):
        result['official_search_configuration']={k:registry.get(k) for k in ('official_reports','max_official_documents','max_official_details','max_wamex_documents','max_wamex_document_bytes')}
    if tasks:result['search_tasks']=tasks
    if registry.get('task_execution_version'):
        for task in tasks:
            task['executed_requests']=[s for s in outcomes if s.get('project_id')==task['project_id'] or any(s['seed_key']==k or s['seed_key'].startswith(k+'_') for k in task['seed_keys'])]
            task['execution_status']=('BOUNDED_ENDPOINTS_ATTEMPTED' if any(a['status']!='REUSED_VERIFIED_ORIGINAL' for a in task['executed_requests']) else
                                      'EXISTING_ORIGINAL_REUSED_NO_NEW_SEARCH' if task['executed_requests'] else 'NO_EXECUTABLE_ENDPOINT_UNKNOWN')
        # One immutable run receipt in the existing manifest, not a persistent queue.
        result['version']='discovery-v6-executed-tasks'
        save((json.dumps(result,sort_keys=True,ensure_ascii=False)+'\n').encode(),
             dict(key='discovery_execution',kind='discovery_receipt',url='local:bounded-discovery-execution'),'.json')
        append_snapshots(path,manifest['snapshots'])
    if diagnostics:result['execution_metrics']=dict(elapsed_seconds=round(time.monotonic()-started,3),
        source_items=len(outcomes),search_pages=sum(s['status']=='PARSED' for s in outcomes),
        downloaded_documents=len({r['document_sha256'] for r in found if r['status'] in ('SNAPSHOT_REQUIRES_DATED_SCOPE_EXTRACTION','DIRECT_PDF_REQUIRES_DATED_SCOPE_EXTRACTION')}),
        document_attempts=sum(r['status'] not in ('REUSED_VERIFIED_ORIGINAL','DISCOVERED_BUDGET_DEFERRED') for r in found),
        reused_originals=len({r.get('document_sha256') for r in found if r['status']=='REUSED_VERIFIED_ORIGINAL'}),
        failures=sum(r['status']=='UNAVAILABLE' for r in outcomes),scope='BOUNDED_SOURCE_ATTEMPTS_NOT_EXHAUSTIVE_SEARCH')
    (root/'data/discovery_latest.json').write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    return result


def live_status(discovery, acquisition=(), recognized=()):
    """Transport/parser success is separate from validated scientific yield."""
    from collections import Counter
    sources=discovery.get('sources',[]);docs=discovery.get('documents',[])
    failed_docs={r['seed_key'] for r in docs if r.get('status')=='DOWNLOAD_UNAVAILABLE'}
    source_failures=[r for r in sources if r['status']=='UNAVAILABLE' and r['seed_key'] not in failed_docs]
    failures=[*source_failures,*[r for r in docs if r.get('status')=='DOWNLOAD_UNAVAILABLE'],
              *[r for r in acquisition if r.get('status')=='UNAVAILABLE']]
    failures.extend(r for r in recognized if r['status']=='EXTRACTION_FAILED')
    searched=[r for r in sources if r['status']=='PARSED']
    return dict(status='PARTIAL_FAILURE' if failures else 'COMPLETED_BOUNDED_ATTEMPTS' if searched else 'NO_LIVE_SEARCH_PERFORMED',
        valid_source_searches=len(searched),source_failures=len(source_failures),
        downloaded_originals=len({r['document_sha256'] for r in docs if r['status'] in ('DIRECT_PDF_REQUIRES_DATED_SCOPE_EXTRACTION','SNAPSHOT_REQUIRES_DATED_SCOPE_EXTRACTION')}),
        reused_originals=len({r.get('document_sha256') for r in docs if r['status']=='REUSED_VERIFIED_ORIGINAL'}),
        download_failures=sum(d['status']=='DOWNLOAD_UNAVAILABLE' for d in docs),
        parsed_documents=sum(r['status']=='CAPTURED' for r in recognized),
        reused_extractions=sum(r['status']=='REUSED_VERIFIED_EXTRACTION' for r in recognized),
        parse_failures=sum(r['status']=='EXTRACTION_FAILED' for r in recognized),
        failure_reasons=dict(Counter(r.get('failure_status',r.get('reason','UNKNOWN')) for r in failures)),
        validated_numeric_observations=None,new_scorable_project_criteria=None,
        scientific_yield_status='NOT_EVALUATED_UNTIL_EXISTING_EVIDENCE_SELECTION_AND_DATABASE_REBUILD',
        reconstruction_status='SEPARATE_OFFLINE_SCIENTIFIC_JOB',no_document_absence_inference=True)


def source_coverage(root, snapshots, selection, prepared, out):
    """Rebuild Project x document-type stages from locked bytes, not live state."""
    from collections import defaultdict
    from .analysis import write_csv
    from .pdf_extract import classify,project_registry
    from .store import canonical
    root=Path(root);mapping=selection['mapping'];by_project=defaultdict(list);receipts=[];receipt_shas=set()
    originals={s['sha256']:s for s in snapshots if s['kind'] in ('pdf','html')}
    restricted_pages={s['sha256'] for s in snapshots if s['kind']=='discovery_html' and b'announcementTerms.do' in (root/s['path']).read_bytes()}
    identity={mapping.get(p['entity_id'],p['entity_id']):p['identity_source'] for p in project_registry(root)}
    owners=defaultdict(set)
    for c in selection['inventory']:
        if not c['raw'].get('parser_version'):owners[c['source_sha256']].add(c['project_id'])
    for s in snapshots:
        if s['kind']=='discovery_receipt' and s['sha256'] not in receipt_shas:
            receipts.append(json.loads((root/s['path']).read_text(encoding='utf-8')));receipt_shas.add(s['sha256'])
        if s['kind']!='document_extraction':continue
        data=json.loads((root/s['path']).read_text(encoding='utf-8'))
        pids={mapping.get(c['project_id'],c['project_id']) for c in data['candidates'] if c.get('project_id')}
        known=owners[data['source_sha256']]|{pid for pid,key in identity.items() if originals.get(data['source_sha256'],{}).get('key')==key}
        # A comparative mention of another mine does not assign that report to it.
        pids=known if known else pids if len(pids)==1 else set()
        for pid in pids:by_project[pid].append(data)
    domains={'JORC_RESOURCE':'Resource','SCOPING':'Development','PFS':'Development','DFS':'Development',
             'METALLURGICAL':'Technical','MINERALOGY':'Technical','NORM':'Technical','FINANCING':'Commercial','OFFTAKE':'Commercial'}
    resource={r['canonical_project_id'] for r in prepared['coverage'] if r.get('resource_defined')}
    # Coverage CSV uses integer/bool resource fields; do not infer from row count.
    resource.update(r['canonical_project_id'] for r in prepared['coverage'] if r.get('R1'))
    rows=[]
    for pid in sorted(selection['projects']):
        attempts=[a for receipt in receipts for task in receipt.get('search_tasks',[]) if mapping.get(task['project_id'],task['project_id'])==pid for a in task.get('executed_requests',[]) if a['status'] in ('PARSED','UNAVAILABLE') and a.get('sha256') not in restricted_pages]
        for receipt in receipts:
            for report in receipt.get('official_reports',[]):
                if any(mapping.get(c['project_id'],c['project_id'])==pid for c in report.get('project_candidates',[])):
                    attempts.append(dict(seed_key=report['source_key'],url=report.get('detail_url'),status='PARSED',
                        relation_status='OFFICIAL_METADATA_CANDIDATE_NOT_REPORT_OWNERSHIP'))
        seed_keys={a['seed_key'] for a in attempts}
        found=[d for receipt in receipts for d in receipt.get('documents',[]) if mapping.get(d.get('project_id'),d.get('project_id'))==pid or d.get('seed_key') in seed_keys]
        for kind,domain in domains.items():
            docs=[]
            for data in by_project[pid]:
                labels=set(data.get('mentioned_labels',data.get('labels',[])))
                text=' '.join(p['text'] for p in data['pages'])
                if kind=='MINERALOGY' and re.search(r'mineralog|monazite|xenotime',text,re.I):labels.add(kind)
                if kind=='NORM' and re.search(r'\bNORM\b|thorium|uranium',text,re.I):labels.add(kind)
                if kind in labels:docs.append(data)
            matches=[d for d in found if kind in classify(d.get('title',''))]
            shas={d['source_sha256'] for d in docs}
            raw=[c for c in selection['inventory'] if c['project_id']==pid and c.get('domain')==domain and c['source_sha256'] in shas]
            valid=[c for c in raw if not c.get('reason')]
            selected_ids={eid for d in selection['decisions'] if d['canonical_project_id']==pid and d['value'] is not None for eid in json.loads(d['evidence_ids'])}
            usable=[c for c in valid if c['evidence_id'] in selected_ids]
            downloaded=[d for d in matches if d.get('document_sha256')]
            failed=[d for d in matches if d['status']=='DOWNLOAD_UNAVAILABLE']
            if usable:state='VERIFIED_USABLE_FOR_SPECIFIED_ANALYSIS'
            elif valid:state='VERIFIED_NOT_CURRENTLY_COMPARABLE'
            elif raw:state='PARSED_VALUES_OR_SCOPE_NOT_VALIDATED'
            elif docs:state='PARSED_NO_VALIDATED_OBSERVATION'
            elif downloaded:state='ORIGINAL_ACQUIRED_NOT_PARSED'
            elif failed:state='DISCOVERED_DOWNLOAD_FAILED'
            elif matches:state='DISCOVERED_BUDGET_DEFERRED'
            elif attempts:state='SEARCHED_NO_CANDIDATE_IN_BOUNDED_COVERAGE'
            else:state='NOT_SEARCHED_OR_ENDPOINT_NOT_CONFIGURED'
            rows.append(dict(project_id=pid,resource_defined=int(pid in resource),document_type=kind,domain=domain,status=state,
                search_requests=len({a.get('url',a['seed_key']) for a in attempts}),matching_discovered=len(matches),download_failures=len(failed),
                acquired_unparsed=len(downloaded) if not docs else 0,parsed_originals=len(shas),validated_observations=len(valid),scored_observations=len(usable),
                source_shas=canonical(sorted(shas)),failure_states=canonical(sorted({d.get('failure_status','UNKNOWN') for d in failed})),
                limitation='DOCUMENT_LABEL_MENTION_NOT_STUDY_COMPLETION;BOUNDED_SEARCH_NOT_ABSENCE;ONE_PROJECT_MAY_HAVE_MULTIPLE_STAGES'))
    write_csv(Path(out)/'source_document_coverage.csv',rows,list(rows[0]) if rows else [])
    return rows
