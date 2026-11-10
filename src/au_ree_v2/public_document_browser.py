"""Optional ordinary Playwright workflow. No stealth, CAPTCHA or login automation."""
import re
import importlib.util
from datetime import datetime,timedelta,timezone
from urllib.parse import urlsplit,urljoin
from .public_document_repair import utc,public_value,html_diagnosis,retry_delay


def response_info(response):
    headers={k.lower():v for k,v in response.headers.items()}
    redirects=[];request=getattr(response,'request',None);seen=set()
    while request is not None and getattr(request,'redirected_from',None) is not None:
        previous=request.redirected_from
        if id(previous) in seen or len(redirects)>=5:raise ValueError('BROWSER_REDIRECT_BUDGET_EXCEEDED')
        seen.add(id(previous));prior=previous.response()
        redirects.append(dict(from_url=previous.url,to_url=request.url,status=prior.status if prior else None))
        request=previous
    redirects.reverse()
    return dict(url=response.url,final_url=response.url,status=response.status,content_type=headers.get('content-type'),
        retry_after=headers.get('retry-after'),content_length=headers.get('content-length'),
        content_encoding=headers.get('content-encoding'),redirects=redirects)


def defer_retry(record,info):
    if info['status'] in (429,503):
        delay=retry_delay(info.get('retry_after'))
        if delay is not None:
            record['next_retry_at']=(datetime.now(timezone.utc)+timedelta(seconds=delay)).isoformat()
            record['retry_scheduling']='NO_EARLY_RETRY;NEXT_JOB_NOT_BEFORE_RETRY_AFTER'


def accept_browser_pdf(session,work,path,url,method,metadata=None):
    """Attachment and inline responses enter the same immutable PDF validator."""
    session.http.guard(url)
    if path.stat().st_size>session.policy['max_bytes']:raise ValueError('DOCUMENT_BYTE_BUDGET_EXCEEDED')
    return session.pdf(path,work,url,method,metadata)


def acquire_browser(session,work,runtime=None):
    previous=[a for a in session.state['attempts'] if a.get('action_id')==work['action_id'] and a.get('method')=='NORMAL_BROWSER']
    if previous:
        if previous[-1]['status']=='STARTED':
            previous[-1]['status']='INTERRUPTED_BROWSER_OUTCOME_UNCERTAIN_REVIEW_BEFORE_RETRY';session.save()
        missing=previous[-1]['status']=='ENV_BROWSER_RUNTIME_UNAVAILABLE'
        available=runtime is not None or importlib.util.find_spec('playwright') is not None
        due=(previous[-1].get('next_retry_at') and datetime.fromisoformat(previous[-1]['next_retry_at'])<=datetime.now(timezone.utc)
             and len([p for p in previous if p['status']!='ENV_BROWSER_RUNTIME_UNAVAILABLE'])<session.policy['max_retries']+1)
        if not (missing and available) and not due:return dict(previous[-1],cache_hit=True)
    record=dict(action_id=work['action_id'],method='NORMAL_BROWSER',at=utc(),http_status=None,
                status='STARTED',automatic_challenge_solving=False,authenticated_or_paid_access=False,
                chromium_sandbox=True,tls_verification=True,browser_channel=session.config.get('browser_channel'))
    if previous:record['retry_basis']='NEW_INSTALLED_CAPABILITY_AFTER_NO_EXECUTION_OR_ELAPSED_RETRY_AFTER'
    session.state['attempts'].append(record);session.save()
    if any(d['key']==work['action_id'] for d in session.state['documents'].values()):
        record['status']='BROWSER_NOT_NEEDED_VALIDATED_BYTES_PRESENT';session.save();return record
    if runtime is None:
        try:
            from playwright.sync_api import sync_playwright
            runtime=sync_playwright()
        except ImportError:
            record['status']='ENV_BROWSER_RUNTIME_UNAVAILABLE';session.save();return record
    entry=next(iter(work.get('entry_urls',[])),work['url']);record['entry_url']=entry
    session.http.guard(entry)
    host=urlsplit(entry).hostname
    browser_domains=session.state.setdefault('browser_domains',{})
    if browser_domains.get(host,{}).get('paused'):
        record['status']='BROWSER_NOT_REQUESTED_DOMAIN_PAUSED';session.save();return record
    accepted=[];responses=[];started=session.clock()
    def remaining_ms():
        remaining=session.policy['job_timeout']-(session.clock()-started)
        if remaining<=0:raise TimeoutError('BROWSER_JOB_BUDGET_EXHAUSTED')
        return max(1,int(remaining*1000))
    def bound_source(info):
        chain=[r['from_url'] for r in info['redirects']]+[info['url']]
        return next((u for u in chain if u==work['url'] or re.search(work['download_link_pattern'],u,re.I)),None)
    def permitted_pdf(info):
        length=info.get('content_length')
        return (info['status']==200 and length and length.isdigit() and int(length)<=session.policy['max_bytes']
                and (info.get('content_encoding') or 'identity').lower()=='identity')
    try:
        with runtime as api:
            launch=dict(headless=True,chromium_sandbox=True,timeout=remaining_ms())
            if session.config.get('browser_channel'):launch['channel']=session.config['browser_channel']
            browser=api.chromium.launch(**launch)  # Genuine installed browser; no fingerprint modifications.
            record['browser_version']=browser.version if hasattr(browser,'version') else None
            try:
                context=browser.new_context(accept_downloads=True,ignore_https_errors=False)
                def scoped_navigation(route):
                    request=route.request
                    if request.is_navigation_request() and urlsplit(request.url).hostname not in session.config['allowed_hosts']:
                        record.setdefault('blocked_navigation_destinations',[]).append(public_value(request.url));route.abort()
                    else:route.continue_()
                context.route('**/*',scoped_navigation)
                page=context.new_page();page.set_default_timeout(min(session.policy['read_timeout']*1000,remaining_ms()))
                def attachment_received(download):
                    url=download.url
                    if urlsplit(url).hostname not in session.config['allowed_hosts']:
                        download.cancel();return
                    info=next((r for r in reversed(responses) if r['url']==url or bound_source(r)==url),None)
                    if not info or not permitted_pdf(info):
                        download.cancel();record['attachment_or_inline_result']='NON_200_UNKNOWN_LENGTH_OR_COMPRESSED_BROWSER_BODY_NOT_ADMITTED';return
                    remaining_ms();path=session.stage();download.save_as(str(path))
                    accepted.append(accept_browser_pdf(session,work,path,bound_source(info),'BROWSER_ATTACHMENT_DOWNLOAD_EVENT',dict(entry_url=entry,final_url=info['final_url'],http_response=public_value(info))))
                def response_received(response):
                    info=response_info(response)
                    if 'application/pdf' not in (info['content_type'] or '').lower():return
                    if urlsplit(response.url).hostname not in session.config['allowed_hosts'] or not bound_source(info):return
                    responses.append(info);record['pdf_responses']=public_value(responses);defer_retry(record,info);session.save()
                    # Unknown-length browser bodies are deferred to the bounded HTTP route.
                    if not permitted_pdf(info):return
                    try:
                        remaining_ms();raw=response.body()
                        if len(raw)>session.policy['max_bytes']:return
                        path=session.stage();path.write_bytes(raw)
                        doc=accept_browser_pdf(session,work,path,bound_source(info),'BROWSER_INLINE_PDF_RESPONSE',dict(entry_url=entry,final_url=info['final_url'],http_response=public_value(info)))
                        accepted.append(doc)
                    except Exception as exc:
                        # Attachment responses may have no readable body; download event handles those.
                        record.setdefault('pdf_body_notes',[]).append(type(exc).__name__+':BODY_UNAVAILABLE_OR_VALIDATION_FAILED');return
                page.on('response',response_received)
                page.on('download',attachment_received)
                try:
                    navigation=page.goto(entry,wait_until='domcontentloaded',timeout=remaining_ms())
                    if navigation:
                        info=response_info(navigation);session.http.guard(info['final_url'])
                        record.update(http_status=info['status'],final_url=info['final_url'],content_type=info['content_type'],
                                      retry_after=info['retry_after'],redirects=public_value(info['redirects']))
                        defer_retry(record,info);session.save()
                        if navigation.status in (401,403,429,503):
                            record['status']='NORMAL_BROWSER_HTTP_'+str(navigation.status)+'_NO_BYPASS'
                            if navigation.status in (401,403):browser_domains[host]=dict(paused=True,reason=record['status'])
                            return record
                except Exception:
                    # PDF navigation can raise "Download is starting" after its legitimate event.
                    if not accepted and not responses:raise
                content=page.content()
                if html_diagnosis(content)=='WEBSITE_VERIFICATION_PAGE':
                    record['status']='MANUAL_VERIFICATION_REQUIRED';return record
                if re.search(r'password.{0,30}input|type=["\']password',content,re.I):
                    record['status']='MANUAL_LOGIN_REQUIRED_NOT_AUTOMATED';return record
                if not accepted:
                    wait=min(int(session.policy.get('link_wait_timeout',10)*1000),remaining_ms());record['dynamic_link_wait_budget_ms']=wait
                    try:
                        page.wait_for_function('cfg => Array.from(document.querySelectorAll("a[href]")).some(a => a.href === cfg.original || new RegExp(cfg.pattern,"i").test(a.href))',
                            arg=dict(original=work['url'],pattern=work['download_link_pattern']),timeout=wait)
                        record['dynamic_link_wait']='READY'
                    except Exception as exc:record['dynamic_link_wait']='BOUNDED_WAIT_ENDED:'+type(exc).__name__
                if html_diagnosis(page.content())=='WEBSITE_VERIFICATION_PAGE':record['status']='MANUAL_VERIFICATION_REQUIRED';return record
                links=page.locator('a[href]').evaluate_all('(nodes) => nodes.map(n => n.href)')
                candidates=[u for u in links if u==work['url'] or re.search(work['download_link_pattern'],u,re.I)]
                candidates=list(dict.fromkeys(u for u in candidates if urlsplit(u).hostname in session.config['allowed_hosts']))
                for url in candidates[:1]:
                    if accepted:break
                    record['actual_download_url']=url
                    try:
                        # Click an actual page link; do not synthesize endpoints or signed URLs.
                        with page.expect_download(timeout=min(10000,remaining_ms())) as event:
                            link=next(n for n in page.locator('a[href]').all() if urljoin(page.url,n.get_attribute('href'))==url)
                            link.click()
                        # The registered download event persists the attachment.
                        if not accepted:attachment_received(event.value)
                    except Exception as exc:
                        if not accepted:record['attachment_or_inline_result']='NO_DOWNLOAD_EVENT_OR_PDF_VALIDATION_FAILED'
                if not accepted and candidates and not record.get('next_retry_at') and session.config.get('browser_context_request_enabled') is True:
                    url=candidates[0];redirects=[]
                    record['context_request_behavior']='SHARED_CONTEXT_COOKIES_DISTINCT_NETWORK_CLIENT_NOT_BROWSER_EQUIVALENCE'
                    for step in range(6):
                        session.http.guard(url)
                        response=context.request.get(url,timeout=min(session.policy['read_timeout']*1000,remaining_ms()),max_redirects=0)
                        info=response_info(response)
                        if response.status in (301,302,303,307,308) and response.headers.get('location'):
                            if step==5:raise ValueError('BROWSER_REDIRECT_BUDGET_EXCEEDED')
                            target=urljoin(response.url,response.headers['location']);session.http.guard(target)
                            redirects.append(dict(from_url=url,to_url=target,status=response.status));url=target;continue
                        info['redirects']=redirects;record['context_request_response']=public_value(info);defer_retry(record,info)
                        if permitted_pdf(info) and 'application/pdf' in (info['content_type'] or ''):
                            raw=response.body()
                            if len(raw)<=session.policy['max_bytes']:
                                path=session.stage();path.write_bytes(raw)
                                accepted.append(accept_browser_pdf(session,work,path,candidates[0],'BROWSER_CONTEXT_REQUEST_DISTINCT_CLIENT',dict(entry_url=entry,final_url=info['final_url'])))
                        break
                record['pdf_responses']=public_value(responses)
                record['document_sha256s']=sorted({d['document_sha256'] for d in accepted})
                record['status']='PDF_ACQUIRED_BROWSER_PENDING_IDENTITY' if accepted else 'BROWSER_DOCUMENT_RETRY_DEFERRED' if record.get('next_retry_at') else 'BROWSER_NO_QUALIFIED_PDF'
            finally:browser.close()
    except Exception as exc:
        message=str(exc)
        status=('BROWSER_TLS_ERROR_NO_CONFIRMED_RESPONSE' if re.search('ERR_CERT|SSL|TLS',message) else
                'BROWSER_DNS_ERROR_NO_CONFIRMED_RESPONSE' if 'ERR_NAME_NOT_RESOLVED' in message else
                'ENV_BROWSER_NETWORK_PROXY_ERROR' if 'ERR_PROXY' in message else
                ('BROWSER_TIMEOUT_AFTER_HTTP_RESPONSE' if record.get('http_status') is not None else 'BROWSER_TIMEOUT_NO_CONFIRMED_RESPONSE') if type(exc).__name__=='TimeoutError' else
                'ENV_BROWSER_ERROR_OR_NAVIGATION_UNCONFIRMED')
        record.update(status=status,error_summary=type(exc).__name__+':'+status,http_status=record.get('http_status'))
    finally:session.save()
    return record
