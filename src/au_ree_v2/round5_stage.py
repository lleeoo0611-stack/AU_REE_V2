"""Offline round-five attribution review. Frozen round-four evidence is never mutated."""
import copy
import csv
import json
import re
from pathlib import Path
from . import round4_stage as previous

VERSION = 'round5-three-point-v2'
DECISION_ID = 'round5-stage-priority-aliases-20261113'
RULE = 'STAGE_THREE_POINT_PRIORITY_ALIAS_REVIEW'
EVIDENCE = '1.修正優先邏輯，補上別名表 2.離線OCR套三點判斷 3.拿掉sortby'
FORBIDDEN = {'north','south','east','west','lake','mount','mt','creek','hill','range','well','eyre peninsula','arunta','pilbara','goldfields','western australia','south australia','northern territory','victoria','tasmania','queensland','new south wales'}


def priority(*points):
    if 'FAIL' in points: return 'FAIL'
    if 'UNCLEAR' in points: return 'UNCLEAR'
    if points and all(p == 'PASS' for p in points): return 'PASS'
    raise ValueError('Invalid three-point values')


def normalize(value):
    return re.sub(r'\s+', ' ', str(value).replace('–','-').replace('—','-')).strip().casefold()


def core_name(name):
    value = re.split(r'\s+—\s+', name)[0].strip()
    # Commodity and scope suffixes only. Never derive an alias from an issuer name.
    value = re.sub(r'\s+(?:Rare Earths? and Mineral Sands Project|Rare Earths? Project|REE[-–]Kaolin Project|REE Project|Project|Prospect)$', '', value, flags=re.I)
    return value.strip()


def valid_alias(alias, explicit_project=False):
    return len(alias.strip()) >= 4 and (normalize(alias) not in FORBIDDEN or explicit_project)


def build_aliases(rows, repo):
    repo=Path(repo)
    old=json.loads((repo/'results/round4-3-2026-11-13/hit_reviews.json').read_text('utf8'))
    tenements=json.loads((repo/'config/round4_tenements.json').read_text('utf8')).get('projects',[])
    if isinstance(tenements,dict): tenements=[dict(v,project_id=k) for k,v in tenements.items()]
    projects=[]
    for row in rows:
        pid=row['專案ID']; name=row['專案名稱']; core=core_name(name)
        aliases=[]
        for text in dict.fromkeys((name,core)):
            if valid_alias(text): aliases.append(dict(alias=text,source='ROW_FULL_NAME_SUFFIX_REMOVAL',original_name=name))
        # Only explicit project labels agreeing with this row's own core may add variants.
        for hit in old:
            if hit['project_id'] != pid: continue
            text=hit.get('sentence','')+' '+hit.get('paragraph_heading','')
            for match in re.finditer(r'(?<!\w)'+re.escape(core)+r'(?:\s+(?:Rare Earths?|REE|Mineral Sands|Critical Minerals?))*\s+Project\b', text, re.I):
                alias=match.group(0)
                if valid_alias(alias,True) and not any(normalize(a['alias'])==normalize(alias) for a in aliases):
                    aliases.append(dict(alias=alias,source='ARCHIVED_ORIGINAL_PROJECT_LABEL',source_sha256=hit['source_sha256'],physical_page=hit['physical_page'],quote=hit['sentence']))
        for item in tenements:
            if item.get('project_id') != pid: continue
            for tid in item.get('tenement_ids',[]):
                refs=[r for r in item.get('original_references',[]) if normalize(tid) in normalize(r.get('quote',''))]
                if refs and valid_alias(tid): aliases.append(dict(alias=tid,source='ROUND4_ORIGINAL_TENEMENT_REFERENCE',original_references=refs))
        projects.append(dict(project_id=pid,project=name,aliases=aliases))
    return dict(version=VERSION,network_requests=0,projects=projects)


def load_aliases(repo):
    return json.loads((Path(repo)/'config/round5_project_aliases.json').read_text('utf8'))


def alias_index(alias_data):
    owners={}
    for project in alias_data['projects']:
        for record in project['aliases']:
            owners.setdefault(normalize(record['alias']),set()).add(project['project_id'])
    return owners


def reassess_hit(hit,row,entry,shared,settings,alias_data):
    result=previous.assess_hit(hit,row,entry,shared,settings)
    # Frozen review provides exact original point 1/3 assessments for full audit replay.
    if hit.get('_frozen_review'):
        for key in ('point1','point3','reason1','reason3'): result[key]=hit[key]
    records=next((p['aliases'] for p in alias_data['projects'] if p['project_id']==row['專案ID']),[])
    sentence=hit.get('sentence',hit.get('text','')); heading=hit.get('paragraph_heading','')
    if len(heading.split())>10 or re.search(r'\b(?:is|was|has|have|will|completed|plans)\b',heading,re.I): heading=''
    text=sentence+' '+heading
    matched=[a for a in records if re.search(r'(?<!\w)'+re.escape(a['alias'])+r'(?!\w)',text,re.I)]
    owners=alias_index(alias_data)
    # Any ambiguous alias match remains UNCLEAR, including alongside unique matches.
    unique=[a for a in matched if len(owners[normalize(a['alias'])])==1]
    if matched and len(unique)!=len(matched):
        result['point2']='UNCLEAR';result['reason2']='AMBIGUOUS_ALIAS'
    elif unique:
        result['point2']='PASS';result['reason2']='UNIQUE_PROJECT_ALIAS_IN_SENTENCE_OR_HEADING'
        matched=unique
    elif matched:
        result['point2']='UNCLEAR';result['reason2']='AMBIGUOUS_ALIAS'
    elif hit.get('point2')=='UNCLEAR':
        result['point2']='UNCLEAR';result['reason2']=hit.get('reason2','PROJECT_ATTRIBUTION_UNCLEAR')
    else:
        result['point2']='UNCLEAR' if hit.get('ocr') and not heading else 'FAIL'
        result['reason2']='OCR_NO_PROJECT_ATTRIBUTION' if result['point2']=='UNCLEAR' else 'NO_PROJECT_ALIAS_IN_SENTENCE_OR_HEADING'
    result['alias_matched']=[a['alias'] for a in matched]
    result['alias_source']=[a for a in matched]
    if hit.get('ocr_confidence') is not None and float(hit['ocr_confidence'])<80:
        result['point3']='UNCLEAR';result['reason3']='OCR_LOW_CONFIDENCE'
    result['outcome']=priority(result['point1'],result['point2'],result['point3'])
    result['rule_version']=VERSION
    return result


def verify_source_hits(rows,trace,decisions,repo,census,old):
    if census is None: raise ValueError('ROUND5_FULL_SOURCE_REPLAY_REQUIRES_CENSUS')
    _,_,extra=previous.collect_stage_three_point(rows,trace,decisions,repo,census)
    def identity(h):
        return (h['project_id'],h['source_sha256'],str(h['physical_page']),h['keyword'],h['sentence'],h.get('paragraph_heading',''))
    from collections import Counter
    if Counter(map(identity,old)) != Counter(map(identity,extra['hit_reviews'])):
        raise ValueError('ROUND5_REEXTRACTED_812_HIT_IDENTITY_MISMATCH')
    return dict(status='ALL_HIT_IDENTITIES_VERIFIED_AGAINST_FRESH_SOURCE_EXTRACTION',count=len(old),network_requests=0)


def collect_task1(rows,trace,decisions,repo,census):
    repo=Path(repo); aliases=load_aliases(repo)
    approved=[d for d in decisions.get('decisions',[]) if d.get('decision_id')==DECISION_ID and d.get('rule')==RULE and d.get('decided_by')=='USER_EXPLICIT_APPROVAL' and d.get('approval_evidence')==EVIDENCE]
    if len(approved)!=1: raise ValueError('ROUND5_STAGE_EXPLICIT_APPROVAL_REQUIRED')
    settings=json.loads((repo/'config/round4_stage_hit_rules.json').read_text('utf8'))
    old=json.loads((repo/'results/round4-3-2026-11-13/hit_reviews.json').read_text('utf8'))
    verification=verify_source_hits(rows,trace,decisions,repo,census,old)
    manifests=copy.deepcopy(json.loads((repo/'results/round4-3-2026-11-13/stage_search_manifests.json').read_text('utf8')))
    byid={r['專案ID']:r for r in rows}; hits=[]; diff=[]
    for h in old:
        frozen=dict(h,_frozen_review=True)
        entry=dict(sha256=h['source_sha256'],url='')
        r=reassess_hit(frozen,byid[h['project_id']],entry,set(),settings,aliases)
        r.update(row_number=h['row_number'],round4_outcome=h['outcome'])
        hits.append(r)
        if r['outcome']!=h['outcome']:
            reason='ALIAS_ADDED' if r['point2']!=h['point2'] else 'PRIORITY_FIX'
            diff.append(dict(r,change_reason=reason,round4_point1=h['point1'],round4_point2=h['point2'],round4_point3=h['point3']))
    reviews=[]; statuses=[]
    for m in manifests:
        own=[h for h in hits if h['project_id']==m['project_id']]
        m.update(hits=own,hit_review_rows=[h['row_number'] for h in own],keyword_rule=VERSION)
        status='HAS_PASS' if any(h['outcome']=='PASS' for h in own) else 'HAS_UNCLEAR' if any(h['outcome']=='UNCLEAR' for h in own) else 'ALL_FAIL' if own else 'NO_HITS'
        statuses.append(dict(project_id=m['project_id'],project=m['project'],status=status,hit_count=len(own),blockers=m['blockers']))
        reviews.append(dict(project_id=m['project_id'],reason='ROUND5_TASK1_REVIEW_ONLY_NO_FILL',hits=[h for h in own if h['outcome']!='FAIL'],blockers=m['blockers']))
    readme_lines=['## 任務1階段核查', '全部812筆命中已以原件重新擷取核對並重判；不填階段，保留全部既有阻擋。', '### 逐專案狀態（ALL_FAIL=全部FAIL；HAS_UNCLEAR=仍有UNCLEAR；HAS_PASS=有PASS；NO_HITS=無命中）']
    readme_lines += [f"- {s['project_id']} {s['project']}: {s['status']} ({s['hit_count']} hits)" for s in statuses]
    readme_lines.append('### 別名導致FAIL轉為PASS或UNCLEAR')
    alias_changes=[d for d in diff if d['round4_outcome']=='FAIL' and d['outcome'] in ('PASS','UNCLEAR')]
    readme_lines += [f"- Row {d['row_number']}, {d['project_id']}, {d['source_sha256']} p.{d['physical_page']}: {d['alias_matched']} → {d['outcome']}" for d in alias_changes]
    return [],reviews,dict(source_reextraction_verification=verification,readme_lines=readme_lines,stage_search_manifests=manifests,hit_reviews=hits,hit_review_diff=diff,project_stage_status=statuses,project_aliases=aliases,scanned_projects=len(manifests),network_requests=0)
