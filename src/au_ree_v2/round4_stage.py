"""Offline round-four stage review with explicit, auditable three-point decisions."""
import json
import re
from collections import defaultdict
from pathlib import Path
from urllib.parse import urlparse

from . import round3_stage as legacy

EVIDENCE = '1.三點判斷 2.Asra Minerals Limited和GoldArc Resources Limited視同家公司改名 3.使用，標註 4.標註NOT_APPLICABLE_STAGE 5,判成X'
RULE = 'STAGE_THREE_POINT_EVIDENCE_REVIEW'
EXIT_RULE = 'STAGE_EXIT_RESEARCHER_DECISION_RELINQUISHMENT'
EXIT_IDS = {
 'AU-97137ef07af49e3607b2': ('e6bed25382926c6dc85a982e9f8831d70f681fe64782283f4825b00947f650e0', 4, 'relinquish'),
 'AU-70fc8a7de18ad8209c32': ('06916f0c5d2b6e1c52d38f04cfcab7f17d95d23f77bf5d12389d351a37b2205a', 3, 'relinquish'),
 'AU-430f216ca620b69af5f9': ('e37750161e156498c0462ab537117037e61d77295243037a0be0fbf720be2757', 3, 'relinquish'),
 'AU-d1e3e2803f3c4287f6db': ('5d4d954c63513e05659c8545630ec2a6b1d0aafeb599c8552d38892a13b2ee59', 3, 'relinquish'),
}


def approve(decisions, decision_id, rule):
    found = [d for d in decisions['decisions'] if d.get('decision_id') == decision_id
             and d.get('rule') == rule and d.get('decided_by') == 'USER_EXPLICIT_APPROVAL'
             and d.get('approval_evidence') == EVIDENCE]
    if len(found) != 1:
        raise ValueError('ROUND4_STAGE_EXPLICIT_APPROVAL_REQUIRED')


def aliases(row, settings):
    names = [row['專案名稱']] + settings.get('project_aliases', {}).get(row['專案ID'], [])
    # Only explicit name components, not inferred issuer/commodity/state aliases.
    for name in list(names):
        names.extend(re.split(r'\s+[—–]\s+|\s*/\s*', name))
        names.append(re.sub(r'\s+(?:REE\s+)?Project\b.*$', '', name, flags=re.I))
    return sorted({n.strip() for n in names if len(n.strip()) >= 4}, key=lambda n: (-len(n), n))


def source_assessment(entry, shared_projects, settings):
    url = urlparse(entry.get('url', ''))
    if url.hostname == 'services.ga.gov.au' and '/gis/rest/services/' in url.path and '/MapServer/' in url.path:
        return 'FAIL', 'NATIONAL_OR_STATE_GIS: ' + settings['source_type_rules']['national_or_state_gis']
    classification = settings.get('source_classifications', {}).get(entry['sha256'])
    if classification and classification['type'] == 'SHARED_GENERAL_DOCUMENT':
        if len(shared_projects) >= classification['minimum_associated_projects']:
            return 'FAIL', classification['evidence'] + '; associated_projects=' + ','.join(sorted(shared_projects))
        return 'UNCLEAR', 'Configured shared source lacks required independent project associations'
    return 'PASS', 'Project-associated original; no documented general-source exclusion'


def assess_hit(hit, row, entry, shared_projects, settings):
    p1, r1 = source_assessment(entry, shared_projects, settings)
    sentence = hit.get('sentence', hit.get('text', ''))
    heading = hit.get('paragraph_heading', '')
    # A heading must be a concise standalone label, not an arbitrary first prose line.
    if len(heading.split()) > 10 or re.search(r'\b(?:is|was|has|have|will|completed|plans)\b', heading, re.I):
        heading = ''
    context = sentence + ' ' + heading
    matched = [a for a in aliases(row, settings) if re.search(r'(?<!\w)' + re.escape(a) + r'(?!\w)', context, re.I)]
    p2, r2 = ('PASS', 'Explicit project name/alias/tenement: ' + '; '.join(matched)) if matched else ('FAIL', 'No explicit project name/alias/tenement in the complete sentence or documented paragraph heading')
    if not matched and any(re.search(r'(?<!\w)' + re.escape(a) + r'(?!\w)', hit.get('paragraph_text', ''), re.I) for a in aliases(row, settings)):
        p2, r2 = 'UNCLEAR', 'Project occurs elsewhere in extracted paragraph; heading/sentence attribution needs manual verification'
    future = [p for p in settings['future_patterns'] if re.search(p, sentence, re.I)]
    complete = [p for p in settings['completed_patterns'] if re.search(p, sentence, re.I)]
    if future and complete:
        p3, r3 = 'UNCLEAR', 'Mixed completed/current and planned/negated/conditional language requires manual scope review'
    elif future:
        p3, r3 = 'FAIL', 'Future/intention/nominal/conditional/negated phrase: ' + '; '.join(future)
    elif complete:
        p3, r3 = 'PASS', 'Completed/current activity wording: ' + '; '.join(complete)
    else:
        p3, r3 = 'UNCLEAR', 'No unambiguous completed/current or explicitly excluded wording'
    # Excluded originals have no project-stage meaning and no blocking UNCLEAR.
    if p1 == 'FAIL':
        p2 = p3 = 'FAIL'
        r2 = r3 = 'Not applicable to this project: original excluded under point 1'
    return dict(project_id=row['專案ID'], project=row['專案名稱'], source_sha256=entry['sha256'],
                physical_page=hit.get('physical_page'), keyword=hit['keyword'], sentence=sentence,
                paragraph_heading=hit.get('paragraph_heading', ''), point1=p1, point2=p2, point3=p3,
                reason1=r1, reason2=r2, reason3=r3,
                outcome='UNCLEAR' if 'UNCLEAR' in (p1,p2,p3) else ('PASS' if (p1,p2,p3)==('PASS','PASS','PASS') else 'FAIL'))


def complete_hits(entry, keywords):
    """Read complete physical-page sentences, never classify clipped legacy snippets."""
    path = next((Path(p) for p in entry.get('paths', [entry['path']]) if Path(p).is_file()), None)
    if path is None or legacy.sha256(path) != entry['sha256']:
        return []
    if entry.get('kind') == 'pdf' or path.suffix.lower() == '.pdf':
        import fitz
        with fitz.open(path) as doc:
            pages = [(i+1, p.get_text(sort=True)) for i,p in enumerate(doc)]
    else:
        text = path.read_text(encoding='utf-8-sig')
        if entry.get('kind') in ('html','htm') or path.suffix.lower() in ('.html','.htm'):
            parser = legacy.VisibleHTML(); parser.feed(text); text='\n'.join(parser.text)
        pages = [(None,text)]
    hits=[]
    for page,text in pages:
        text = re.sub(r'(?<=\w)[-‐‑]\s*\n\s*(?=\w)', '', text)
        # Paragraph boundaries retained. No assumption that a page header names every project on a page.
        for paragraph in re.split(r'\n\s*\n',text):
            lines=[l.strip() for l in paragraph.splitlines() if l.strip()]
            heading = lines[0] if len(lines)>1 and len(lines[0])<100 and not re.search(r'[.!?]$',lines[0]) else ''
            flat=' '.join(paragraph.split())
            for sentence in re.split(r'(?<=[.!?])\s+(?=[A-Z0-9])',flat):
                for keyword in keywords:
                    pattern=r'\b'+re.escape(keyword)+(r'\b' if keyword.upper() in ('PFS','DFS','BFS','FID') else '')
                    for _ in re.finditer(pattern,sentence,re.I):
                        hits.append(dict(source_sha256=entry['sha256'],physical_page=page,keyword=keyword,sentence=sentence,paragraph_heading=heading,paragraph_text=flat))
    return hits


def make_fills(row, code, rule, decision_id, source, scope, locator, category):
    output=[]
    for column,value in [('開發階段代碼',code),('開發階段類別',category)]:
        if row.get(column):
            continue
        p=dict(project_id=row['專案ID'],column=column,value=value,method=rule,source_sha256=source['sha256'],
               source_url=source.get('url',''),publication_date=max(source.get('dates',[]),default=''),locator=locator,
               scope=json.dumps(scope,ensure_ascii=False,sort_keys=True),observation_ids='[]',review_ids=json.dumps([decision_id]),
               review_methods=json.dumps([rule]),source_kind='ARCHIVED_RESEARCHER_REVIEW')
        output.append(dict(project_id=row['專案ID'],column=column,value=value,method=rule,decision_id=decision_id,provenance=p))
    return output


def collect_stage_three_point(rows, provenance, decisions, repo, census_root, settings=None):
    from .stage_rules import selected_mre
    repo=Path(repo)
    settings=settings or legacy.read_json(repo/'config/round4_stage_hit_rules.json')
    approve(decisions, settings['decision_id'], RULE)
    old=legacy.read_json(repo/settings['legacy_settings'])
    baseline=legacy.read_json(repo/settings['baseline_manifests'])
    old_by_id={m['project_id']:m for m in baseline}
    targets=[r for r in rows if r['專案ID'] in old_by_id and r['專案ID'] not in EXIT_IDS
             and not any(r.get(k) for k in ('開發階段','開發階段代碼','開發階段類別'))]
    # Complete row set prevents two-project general sources becoming apparently single-project
    # merely because one project already has a stage.
    inventories,issues=legacy.original_inventory(repo,census_root,{r['專案ID'] for r in rows})
    shared=defaultdict(set)
    for pid,entries in inventories.items():
        for e in entries:shared[e['sha256']].add(pid)
    for m in baseline:
        for sha in m['original_sha256s']:shared[sha].add(m['project_id'])
    proof=legacy.read_json(repo/old['visual_review_file']) if old.get('visual_review_file') else {}
    fills,reviews,manifests,hit_reviews=[],[],[],[]
    cache={}
    for row in targets:
        pid=row['專案ID']; entries=inventories.get(pid,[])
        blockers=list(issues.get(pid,[])); scans=[]; row_hits=[]
        if not entries:blockers.append(dict(reason='NO_ASSOCIATED_ARCHIVED_ORIGINALS'))
        for e in entries:
            excluded,reason=source_assessment(e,shared[e['sha256']],settings)
            if excluded == 'UNCLEAR':
                blockers.append(dict(reason='SOURCE_TYPE_UNCLEAR',source_sha256=e['sha256'],detail=reason))
            key=(e['sha256'],tuple(e.get('paths',[e['path']])))
            if key not in cache:
                scan=legacy.scan_original(e,old['keywords'])
                checked=legacy.verify_visual_reviews(e,scan,proof,old['keywords'],old['keyword_version'])
                found=complete_hits(e,old['keywords']) if not any(i['reason'] in ('ARCHIVED_ORIGINAL_MISSING','ARCHIVED_ORIGINAL_SHA_MISMATCH','ARCHIVED_ORIGINAL_UNREADABLE') for i in checked[1]) else []
                # Hash-bound visual hits are explicit full-page reviews, retained separately.
                found += [dict(h,sentence=h['text']) for h in checked[0] if h.get('method')=='DIRECT_VISUAL_REVIEW']
                cache[key]=(found,checked[1],checked[2],checked[3])
            found,problems,pages,visual=cache[key]
            if excluded!='FAIL':
                blockers.extend(problems)
                if not e['dates']:blockers.append(dict(reason='ARCHIVED_ORIGINAL_DATE_UNKNOWN',source_sha256=e['sha256']))
            scans.append(dict(source_sha256=e['sha256'],source_url=e['url'],dates=e['dates'],associations=e['associations'],
                              point1=excluded,source_type_reason=reason,physical_pages_scanned=pages,
                              ignored_blockers=problems if excluded=='FAIL' else [],verified_visual_page_reviews=visual))
            for h in found:
                r=assess_hit(h,row,e,shared[e['sha256']],settings)
                r['row_number']=len(hit_reviews)+2  # CSV header is physical row 1.
                hit_reviews.append(r);row_hits.append(r)
        has_mre,mre=selected_mre(row,provenance)
        if has_mre is None:blockers.append(dict(reason='SELECTED_MRE_STATE_UNRESOLVED',detail=mre))
        meaningful=[h for h in row_hits if h['outcome'] in ('PASS','UNCLEAR')]
        # Excluding generic evidence does not supply positive project coverage.
        # A dated, non-excluded own-project original is required for absence inference.
        dated=[e for e in entries if e['dates'] and source_assessment(e,shared[e['sha256']],settings)[0]=='PASS']
        if not dated:blockers.append(dict(reason='NO_DATED_PROJECT_SPECIFIC_ORIGINAL_FOR_INFERENCE'))
        manifest=dict(project_id=pid,project=row['專案名稱'],originals=scans,original_sha256s=sorted(e['sha256'] for e in entries),
                      keyword_rule=settings['version'],hit_review_rows=[h['row_number'] for h in row_hits],hits=row_hits,blockers=blockers,
                      latest_original_date=max((d for e in dated for d in e['dates']),default=None),
                      search_scope='ALL_ASSOCIATED_ORIGINALS_WITH_DOCUMENTED_GENERAL_SOURCE_EXCLUSIONS')
        manifests.append(manifest)
        if meaningful or blockers:
            reviews.append(dict(project_id=pid,project=row['專案名稱'],reason='STAGE_THREE_POINT_HIT_OR_UNCLEAR' if meaningful else 'STAGE_SEARCH_INCOMPLETE',hits=meaningful,blockers=blockers,original_sha256s=manifest['original_sha256s']))
            continue
        source=max(dated,key=lambda e:(max(e['dates']),e['sha256']))
        scope=dict(manifest,qualifier=legacy.RULE,decision_id=settings['decision_id'],selected_mre=has_mre,
                   interpretation='SOURCE_SET_AS_OF_DATE_INFERENCE_NOT_NATIVE_STAGE_STATEMENT_OR_CURRENT_STATUS')
        fills.extend(make_fills(row,'A2' if has_mre else 'A1',legacy.RULE,settings['decision_id'],source,scope,
                               'All originals, documented exclusions, and complete sentences; hit_reviews.csv rows '+str(manifest['hit_review_rows']),'探勘'))
    return fills,reviews,dict(stage_search_manifests=manifests,hit_reviews=hit_reviews,scanned_projects=len(targets),network_requests=0)


def collect_charley_exit(rows, provenance, decisions, repo, census_root=None, settings=None):
    settings=settings or {}
    decision_id=settings.get('decision_id','round4-charley-exit-20261113')
    approve(decisions,decision_id,EXIT_RULE)
    baseline=legacy.read_json(Path(repo)/'results/round3-2-2026-11-11/stage_search_manifests.json')
    manifests={m['project_id']:m for m in baseline}
    fills,reviews,evidence=[],[],[]
    for row in rows:
        pid=row['專案ID']
        if pid not in EXIT_IDS:continue
        if any(row.get(k) for k in ('開發階段','開發階段代碼','開發階段類別')):continue
        sha,page,keyword=EXIT_IDS[pid]; m=manifests[pid]
        hits=[h for h in m['hits'] if h['source_sha256']==sha and h['physical_page']==page and h['keyword']==keyword]
        if not hits:
            reviews.append(dict(project_id=pid,reason='CHARLEY_RELINQUISHMENT_EVIDENCE_MISSING'));continue
        orig=next(e for e in m['originals'] if e['source_sha256']==sha)
        scope=dict(qualifier=EXIT_RULE,decision_id=decision_id,approval_evidence=EVIDENCE,hits=hits,
                   superseded_blockers=m['blockers'],interpretation='RESEARCHER_DECISION_FOR_SPECIFIED_HISTORICAL_TENEMENT_SCOPE_NOT_FULL_PROJECT_EXIT_ASSERTION')
        source=dict(sha256=sha,url=orig['source_url'],dates=orig['dates'])
        fills.extend(make_fills(row,'X',EXIT_RULE,decision_id,source,scope,f'Round3 archived review; physical page {page}; relinquishment decision','退出'))
        evidence.append(dict(project_id=pid,source_sha256=sha,physical_page=page,hits=hits,superseded_blockers=m['blockers']))
    return fills,reviews,dict(charley_exit_evidence=evidence,network_requests=0)
