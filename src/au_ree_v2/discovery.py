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
from .store import filehash

DOCUMENT_TERMS = {
    'Resource': ['JORC mineral resource', 'mineral resource estimate'],
    'Strategic': ['rare earth oxide composition', 'mineral resource'],
    'Technical': ['metallurgical testwork', 'mineralogy NORM recovery'],
    'Development': ['feasibility study', 'scoping study'],
    'Commercial': ['project financing offtake', 'quarterly activities'],
    'Infrastructure': ['feasibility infrastructure', 'project infrastructure'],
}


def search_tasks(root, registry, diagnostics=None):
    """Registry-derived jobs reuse issuer endpoints; missing endpoints stay unknown.

    Aliases and company/ASX identifiers are discovery context, never entity
    equivalence or authority to attribute company funds to a project.
    """
    from .pdf_extract import project_registry
    manifest=json.loads((Path(root)/'data/manifest.json').read_text(encoding='utf-8'))['snapshots']
    registered_path=Path(root)/'config/sources.json'
    registered={s['key']:s for s in json.loads(registered_path.read_text(encoding='utf-8'))['sources']} if registered_path.exists() else {}
    sources={s['key']:s for s in manifest};tasks=[]
    for p in project_registry(root):
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


def discover(root, registry, fetch=request, diagnostics=None, task_limit=3):
    import time
    started=time.monotonic()
    root=Path(root); path=root/'data/manifest.json'
    manifest=json.loads(path.read_text(encoding='utf-8')); outcomes=[]; found=[]
    captured_urls={s['url'] for s in manifest['snapshots'] if s['kind']=='pdf'}
    captured={s['url']:s for s in manifest['snapshots'] if s['kind']=='pdf'}
    def save(raw, meta, suffix):
        from .security import public_snapshot
        raw,redaction=public_snapshot(root,raw,suffix)
        meta={**meta,**redaction}
        sha=hashlib.sha256(raw).hexdigest(); dest=root/'data/snapshots'/(sha+suffix)
        if meta.get('kind')=='discovery_receipt':meta['key']='discovery_execution_'+sha[:16]
        if not dest.exists():dest.write_bytes(raw)
        if filehash(dest)!=sha:raise ValueError('IMMUTABLE_SNAPSHOT_CONTENT_MISMATCH')
        now=datetime.now(timezone.utc).isoformat()
        entry={**meta,'sha256':sha,'path':dest.relative_to(root).as_posix(),'acquired_at':now,'available_date':now[:10]}
        if not any(s['key']==entry['key'] and s['sha256']==sha for s in manifest['snapshots']):manifest['snapshots'].append(entry)
        return sha
    tasks=search_tasks(root,registry,diagnostics) if registry.get('registry_tasks') or diagnostics else []
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
            if cached:
                if filehash(root/cached['path'])!=cached['sha256']:raise ValueError('IMMUTABLE_SNAPSHOT_CONTENT_MISMATCH')
                found.append(dict(candidate_id=hashlib.sha256(seed['url'].encode()).hexdigest(),url=seed['url'],seed_key=seed['key'],document_sha256=cached['sha256'],source_key=cached['key'],status='REUSED_VERIFIED_ORIGINAL',project_id=seed.get('project_id')))
                outcomes.append(dict(seed_key=seed['key'],status='REUSED_VERIFIED_ORIGINAL',sha256=cached['sha256']));continue
            # Existing verified bytes precede network even for archive links.
            cached=captured.get(seed['url'])
            if cached:
                if filehash(root/cached['path'])!=cached['sha256']:raise ValueError('IMMUTABLE_SNAPSHOT_CONTENT_MISMATCH')
                found.append(dict(candidate_id=hashlib.sha256(seed['url'].encode()).hexdigest(),url=seed['url'],seed_key=seed['key'],source_key=cached['key'],document_sha256=cached['sha256'],status='REUSED_VERIFIED_ORIGINAL',project_id=seed.get('project_id')))
                outcomes.append(dict(seed_key=seed['key'],project_id=seed.get('project_id'),url=seed['url'],status='REUSED_VERIFIED_ORIGINAL',sha256=cached['sha256']));continue
            raw,_=fetch(seed['url'])
            if raw.startswith(b'%PDF'):
                sha=save(raw,{'key':'discovery_'+seed['key'],'url':seed['url'],'kind':'pdf','project_id':seed.get('project_id'),
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
        except Exception as exc:outcomes.append({'seed_key':seed['key'],'project_id':seed.get('project_id'),'url':seed['url'],'search_query':seed.get('search_query'),'status':'UNAVAILABLE',**failure_details(exc)})
    path.write_text(json.dumps(manifest,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    result={'version':'discovery-v4-evidence-gaps' if diagnostics else 'discovery-v3-registry-tasks' if tasks else 'discovery-v2',
            'execution_mode':registry.get('execution_mode','PUBLIC_ENDPOINTS'), 'sources':outcomes,'documents':found}
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
        path.write_text(json.dumps(manifest,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    if diagnostics:result['execution_metrics']=dict(elapsed_seconds=round(time.monotonic()-started,3),
        source_items=len(outcomes),search_pages=sum(s['status']=='PARSED' for s in outcomes),
        downloaded_documents=len({r['document_sha256'] for r in found if r['status'] in ('SNAPSHOT_REQUIRES_DATED_SCOPE_EXTRACTION','DIRECT_PDF_REQUIRES_DATED_SCOPE_EXTRACTION')}),
        document_attempts=sum(r['status'] not in ('REUSED_VERIFIED_ORIGINAL','DISCOVERED_BUDGET_DEFERRED') for r in found),
        reused_originals=len({r.get('document_sha256') for r in found if r['status']=='REUSED_VERIFIED_ORIGINAL'}),
        failures=sum(r['status']=='UNAVAILABLE' for r in outcomes),scope='BOUNDED_SOURCE_ATTEMPTS_NOT_EXHAUSTIVE_SEARCH')
    (root/'data/discovery_latest.json').write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    return result


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
