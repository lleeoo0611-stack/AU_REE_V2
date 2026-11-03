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
from .acquisition import request
from .security import sensitive_reference
from .store import filehash


def search_tasks(root, registry, diagnostics=None):
    """Registry-derived jobs reuse issuer endpoints; missing endpoints stay unknown.

    Aliases and company/ASX identifiers are discovery context, never entity
    equivalence or authority to attribute company funds to a project.
    """
    from .pdf_extract import project_registry
    manifest=json.loads((Path(root)/'data/manifest.json').read_text(encoding='utf-8'))['snapshots']
    sources={s['key']:s for s in manifest};tasks=[]
    for p in project_registry(root):
        source=sources.get(p['identity_source'],{})
        matches=[s for s in registry['seeds'] if s.get('project_id')==p['entity_id'] or
                 any(a.casefold() in json.dumps(s).casefold() for a in p['aliases'])]
        tasks.append(dict(project_id=p['entity_id'],project_name=p['name'],aliases=p['aliases'],
                          company=source.get('company'),asx_code=source.get('asx_code'),
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
            queries=[a+' '+g['domain']+' '+g['criterion'] for a in t['aliases']],
            reusable_documents=[dict(key=s['key'],url=s['url'],sha256=s['sha256'],publication_date=s.get('publication_date')) for s in docs]))
    return sorted(jobs,key=lambda t:(-t['priority'],t['project_id'],t['criterion']))


class Links(HTMLParser):
    def __init__(self):
        super().__init__(); self.links=[]; self.current=None
    def handle_starttag(self, tag, attrs):
        if tag=='a': self.current=[dict(attrs).get('href',''),'']
    def handle_data(self, data):
        if self.current is not None:self.current[1]+=data
    def handle_endtag(self, tag):
        if tag=='a' and self.current is not None:
            self.links.append(self.current); self.current=None


def candidates(raw, seed):
    parser=Links(); parser.feed(raw.decode('utf-8',errors='replace'))
    rows={}
    for href,label in parser.links:
        url=urldefrag(urljoin(seed['url'],href))[0]
        host=urlsplit(url).hostname
        if urlsplit(url).scheme!='https' or host not in seed['allowed_hosts'] or sensitive_reference(url):continue
        if seed.get('keywords') and not any(k.casefold() in (url+' '+label).casefold() for k in seed['keywords']):continue
        if not re.search(seed.get('pattern',r'\.pdf(?:[?\s]|$)'),url+' '+label,re.I):continue
        key=hashlib.sha256(url.encode()).hexdigest()
        rows[key]={'candidate_id':key,'url':url,'title':label.strip(),'seed_key':seed['key'],
                   'publication_date':None,'status':'DISCOVERED_NOT_OBSERVATION',
                   'project_id':seed.get('project_id'),'identity_status':'SOURCE_CONTEXT_ONLY_NOT_EQUIVALENCE'}
    return list(rows.values())  # Preserve issuer feed order; hashes are not chronology.


def discover(root, registry, fetch=request, diagnostics=None, task_limit=3):
    import time
    started=time.monotonic()
    root=Path(root); path=root/'data/manifest.json'
    manifest=json.loads(path.read_text(encoding='utf-8')); outcomes=[]; found=[]
    captured_urls={s['url'] for s in manifest['snapshots'] if s['kind']=='pdf'}
    def save(raw, meta, suffix):
        from .security import public_snapshot
        raw,redaction=public_snapshot(root,raw,suffix)
        meta={**meta,**redaction}
        sha=hashlib.sha256(raw).hexdigest(); dest=root/'data/snapshots'/(sha+suffix)
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
    queue=[]
    for seed in registry['seeds']:
        queue.append(dict(seed))
        for url in seed.get('fallback_urls',[]):
            if urlsplit(url).scheme=='https' and urlsplit(url).hostname in seed['allowed_hosts'] and not sensitive_reference(url):
                queue.append(dict(seed,url=url,key=seed['key']+'_alternative_'+hashlib.sha256(url.encode()).hexdigest()[:12],
                                  fallback_urls=[],original_discovery_url=seed['url']))
        queries=list(seed.get('queries',[]))
        if seed.get('search_url_template'):
            queries += [q for t in tasks if seed['key'] in t['seed_keys'] for q in t['queries']]
        for query in sorted(set(queries)):
            if seed.get('search_url_template'):queue.append(dict(seed,url=seed['search_url_template'].format(query=quote(query)),key=seed['key']+'_search_'+hashlib.sha256(query.encode()).hexdigest()[:12]))
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
            raw,_=fetch(seed['url'])
            if raw.startswith(b'%PDF'):
                sha=save(raw,{'key':'discovery_'+seed['key'],'url':seed['url'],'kind':'pdf',**({'publication_date':seed['publication_date']} if seed.get('publication_date') else {})},'.pdf')
                found.append({'candidate_id':hashlib.sha256(seed['url'].encode()).hexdigest(),'url':seed['url'],'seed_key':seed['key'],'publication_date':None,'document_sha256':sha,'status':'DIRECT_PDF_REQUIRES_DATED_SCOPE_EXTRACTION'})
                outcomes.append({'seed_key':seed['key'],'status':'DIRECT_PDF_CAPTURED','sha256':sha});continue
            sha=save(raw,{'key':'discovery_'+seed['key'],'url':seed['url'],'kind':'discovery_html'},'.html')
            parser=Links();parser.feed(raw.decode('utf-8',errors='replace'))
            for href,label in parser.links:
                url=urldefrag(urljoin(seed['url'],href))[0]
                if urlsplit(url).scheme=='https' and urlsplit(url).hostname in seed['allowed_hosts'] and not sensitive_reference(url) and (re.search(r'next|older',label,re.I) or re.search(r'/page/\d|[?&]page=',url)):
                    queue.append(dict(seed,url=url,key=family+'_page_'+hashlib.sha256(url.encode()).hexdigest()[:12],pagination_family=family,queries=[]))
                elif (seed.get('detail_pattern') and urlsplit(url).scheme=='https'
                      and urlsplit(url).hostname in seed['allowed_hosts'] and not sensitive_reference(url)
                      and re.search(seed['detail_pattern'],url)
                      and any(k.casefold() in (label+' '+url).casefold() for k in seed.get('keywords',[]))):
                    queue.append(dict(seed,url=url,key=family+'_detail_'+hashlib.sha256(url.encode()).hexdigest()[:12],pagination_family=family,queries=[]))
            rows=candidates(raw,seed)
            rows=[r for r in rows if r['url'] not in seen_documents]
            rows.sort(key=lambda row:row['url'] in captured_urls)
            budget=max(0,registry.get('max_documents_per_seed',10)-document_counts.get(family,0))
            for row in rows[:budget]:
                document_counts[family]=document_counts.get(family,0)+1
                seen_documents.add(row['url'])
                row['discovery_sha256']=sha
                try:
                    doc,_=fetch(row['url'])
                    if not doc.startswith(b'%PDF'):raise ValueError('NOT_PDF')
                    row['document_sha256']=save(doc,{'key':'discovered_'+row['candidate_id'],'url':row['url'],'kind':'pdf','discovery_sha256':sha},'.pdf')
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
                except Exception as exc:row['status']='DOWNLOAD_UNAVAILABLE';row['reason']=type(exc).__name__+('_'+str(exc.code) if hasattr(exc,'code') else '')
                found.append(row)
            outcomes.append({'seed_key':seed['key'],'status':'PARSED','links_found':len(rows),'links_attempted':min(len(rows),budget),'sha256':sha,'limitation':'BOUNDED_STATIC_HTML_SEARCH_AND_LINKED_PAGINATION_NO_JAVASCRIPT'})
        except Exception as exc:outcomes.append({'seed_key':seed['key'],'status':'UNAVAILABLE','reason':type(exc).__name__+('_'+str(exc.code) if hasattr(exc,'code') else '')})
    path.write_text(json.dumps(manifest,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    result={'version':'discovery-v4-evidence-gaps' if diagnostics else 'discovery-v3-registry-tasks' if tasks else 'discovery-v2','sources':outcomes,'documents':found}
    if tasks:result['search_tasks']=tasks
    if diagnostics:result['execution_metrics']=dict(elapsed_seconds=round(time.monotonic()-started,3),search_pages=len(outcomes),downloaded_documents=sum(r['status'] in ('SNAPSHOT_REQUIRES_DATED_SCOPE_EXTRACTION','DIRECT_PDF_REQUIRES_DATED_SCOPE_EXTRACTION') for r in found),reused_originals=sum(r['status']=='REUSED_VERIFIED_ORIGINAL' for r in found),failures=sum(r['status']=='UNAVAILABLE' for r in outcomes),scope='BOUNDED_SOURCE_ATTEMPTS_NOT_EXHAUSTIVE_SEARCH')
    (root/'data/discovery_latest.json').write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    return result
