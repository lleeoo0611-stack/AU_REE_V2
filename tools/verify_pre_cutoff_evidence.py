"""Verify only explicit repo evidence; never infer dates from local file times."""
import argparse
import hashlib
import json
import os
import re
import subprocess
import urllib.request
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

ROOT=Path(__file__).resolve().parents[1]
REPO='lleeoo0611-stack/AU_REE_V2'
REF='origin/experiment/round5-researcher-approved-20261113'
ALLOWED={'reviewed_source_521f635719be1686','reviewed_source_a197d77204b48c23',
         'reviewed_source_9e1ac5bb894d9077','reviewed_source_31a205168b6ae647'}
EVENTS_FILE_SHA256='a35421e6238b459ec6979a0843b1fa683a3ad1233b63c1dc378e68a1b3c70826'
EVENT_IDS={'26796705284','26823267883'}

def git(*args):
    return subprocess.check_output(['git',*args],cwd=ROOT,stderr=subprocess.DEVNULL)

def ancestor(left,right):
    return subprocess.run(['git','merge-base','--is-ancestor',left,right],cwd=ROOT,
                          stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode==0

def events_from_api():
    events=[];errors=[]
    for page in range(1,4):
        url=f'https://api.github.com/repos/{REPO}/events?per_page=100&page={page}'
        headers={'User-Agent':'AU_REE_V2/0.1 public research','Accept':'application/vnd.github+json'}
        if os.environ.get('GITHUB_TOKEN'):
            headers['Authorization']='Bearer '+os.environ['GITHUB_TOKEN']
        try:
            with urllib.request.urlopen(urllib.request.Request(url,headers=headers),timeout=30) as response:
                batch=json.load(response)
            if not isinstance(batch,list):raise ValueError('EVENT_ARRAY_REQUIRED')
            events.extend(batch)
            if len(batch)<100:break
        except Exception as exc:
            errors.append(dict(endpoint=url,error=type(exc).__name__))
            break
    return events,errors

def timestamp(value):
    return datetime.fromisoformat(value.replace('Z','+00:00')).astimezone(timezone.utc)

def validate(source,events,cutoff,branch_fetched=True):
    declaration=source['pre_cutoff_evidence']
    result=dict(source_key=source['key'],declaration=declaration,valid=False,reasons=[],
                commit_time='',push_time='',computed_evidence_date='',push_event_id='',push_head='',
                commit_on_ref=False,record_file_verified=False,
                current_declared_sha_matches=source.get('source_sha256')==declaration.get('recorded_sha256'))
    try:
        if source['key'] not in ALLOWED or not source['kind'].startswith('government_'):
            raise ValueError('SOURCE_OUTSIDE_APPROVED_FOUR')
        if not branch_fetched:raise ValueError('BRANCH_FETCH_NOT_VERIFIED')
        if declaration['ref']!=REF:raise ValueError('REF_NOT_APPROVED')
        commit=declaration['commit']
        if not re.fullmatch('[0-9a-f]{40}',commit) or not ancestor(commit,REF):
            raise ValueError('COMMIT_NOT_ON_DECLARED_REF')
        result['commit_on_ref']=True
        relative=PurePosixPath(declaration['path'])
        if relative.is_absolute() or '..' in relative.parts:raise ValueError('INVALID_EVIDENCE_PATH')
        sha=declaration['recorded_sha256']
        if not re.fullmatch('[0-9a-f]{64}',sha):raise ValueError('INVALID_RECORDED_SHA')
        raw=git('cat-file','blob',commit+':'+relative.as_posix())
        if declaration['kind']=='SHA_RECORD':
            if sha.encode() not in raw:raise ValueError('SHA_RECORD_NOT_IN_COMMITTED_FILE')
        elif declaration['kind']=='RAW_FILE':
            if hashlib.sha256(raw).hexdigest()!=sha:raise ValueError('RAW_FILE_SHA_MISMATCH')
        else:raise ValueError('UNSUPPORTED_EVIDENCE_KIND')
        result['record_file_verified']=True
        committed=timestamp(git('show','-s','--format=%cI',commit).decode().strip())
        result['commit_time']=committed.isoformat()
        matches=[]
        for event in events:
            if event.get('type')!='PushEvent':continue
            head=event.get('payload',{}).get('head','')
            if re.fullmatch('[0-9a-f]{40}',head) and ancestor(commit,head):
                matches.append((timestamp(event['created_at']),event,head))
        if not matches:
            # A CreateEvent lacks its original head; it alone cannot bind a commit.
            raise ValueError('PUSH_TIME_NOT_PROVEN_FOR_COMMIT')
        pushed,event,head=min(matches,key=lambda item:item[0])
        day=max(committed,pushed).date().isoformat()
        result.update(push_time=pushed.isoformat(),push_event_id=event['id'],push_head=head,
                      computed_evidence_date=day)
        if day!=declaration['evidence_date']:raise ValueError('DECLARED_EVIDENCE_DATE_MISMATCH')
        if day>cutoff:raise ValueError('EVIDENCE_AFTER_CUTOFF')
        if source.get('source_sha256')!=sha:raise ValueError('DECLARED_SOURCE_SHA_NOT_EVIDENCED_BYTES')
        result['valid']=True
    except (ValueError,KeyError,TypeError,OSError,subprocess.CalledProcessError) as exc:
        result['reasons'].append(str(exc) if isinstance(exc,ValueError) else type(exc).__name__)
    return result

def verify_sources(sources, events_file, cutoff, branch_fetched=True):
    """Sealed repo events establish time; the live window can only cross-check."""
    declarations=[s for s in sources if s.get('pre_cutoff_evidence')]
    result=dict(events_file_sha256='',expected_events_file_sha256=EVENTS_FILE_SHA256,
                events_file_sha_match=False,api_errors=[],event_count=0,sources={})
    failure=None
    try:
        raw=Path(events_file).read_bytes()
        result['events_file_sha256']=hashlib.sha256(raw).hexdigest()
        if result['events_file_sha256']!=EVENTS_FILE_SHA256:
            raise ValueError('EVENTS_FILE_SHA_MISMATCH')
        result['events_file_sha_match']=True
        events=json.loads(raw)
        if len(events)!=2 or {e['id'] for e in events}!=EVENT_IDS or any(e['type']!='PushEvent' for e in events):
            raise ValueError('EVENT_RECORD_SET_MISMATCH')
    except (OSError,ValueError,KeyError,TypeError) as exc:
        failure=str(exc) if isinstance(exc,ValueError) else 'EVENTS_FILE_UNAVAILABLE'
        events=[]
    live=[];errors=[]
    if not failure:
        try:
            live,errors=events_from_api()
        except Exception as exc:
            errors=[dict(error=type(exc).__name__)]
    result.update(api_errors=errors,event_count=len(events))
    conflicts=set()
    for archived in events:
        for actual in live:
            if str(actual.get('id'))==str(archived['id']) and (
                    actual.get('created_at')!=archived['created_at'] or
                    actual.get('payload',{}).get('head')!=archived['payload']['head']):
                conflicts.add(archived['id'])
    for source in declarations:
        if failure:
            record=dict(source_key=source['key'],declaration=source['pre_cutoff_evidence'],
                        valid=False,reasons=[failure],push_event_id='',push_time='',commit_time='',
                        computed_evidence_date='',api_crosscheck='NOT_CHECKED_INVALID_EVENT_FILE')
        else:
            record=validate(source,events,cutoff,branch_fetched)
            event_id=record['push_event_id']
            present=any(str(e.get('id'))==str(event_id) for e in live) if event_id else False
            record['api_crosscheck']='MATCHED' if present else 'API_UNAVAILABLE' if errors else 'EVENT_NOT_IN_API_WINDOW'
            if conflicts:
                record['valid']=False
                record['reasons'].append('EVENT_RECORD_CONFLICT')
                record['api_crosscheck']='EVENT_RECORD_CONFLICT'
                record['conflicting_event_ids']=sorted(conflicts)
        result['sources'][source['key']]=record
    return result,events


def warn_invalid(output, sources):
    try:
        proof=json.loads(Path(output).read_bytes())
        records=proof['sources']
    except (OSError,ValueError,KeyError,TypeError):
        records={}
    if not isinstance(records,dict):records={}
    for source in sources:
        if not source.get('pre_cutoff_evidence'):continue
        record=records.get(source['key'])
        if not isinstance(record,dict):record=None
        if not record or record.get('valid') is not True:
            reasons=record.get('reasons',[]) if record else ['VERIFICATION_FILE_MISSING_OR_INVALID']
            print('::warning::'+source['key']+': '+','.join(reasons))


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--events-file',type=Path,default=ROOT/'config/pre_cutoff_evidence_events.json')
    parser.add_argument('--no-fetch',action='store_true')
    parser.add_argument('--warn-only',action='store_true')
    parser.add_argument('--output',type=Path,default=ROOT/'work/pre_cutoff_evidence_verified.json')
    args=parser.parse_args()
    registry=ROOT/'config/sources.json'
    sources=json.loads(registry.read_text(encoding='utf8'))['sources']
    declarations=[s for s in sources if s.get('pre_cutoff_evidence')]
    if {s['key'] for s in declarations}-ALLOWED:raise ValueError('UNAPPROVED_SOURCE_DECLARATION')
    if args.warn_only:
        warn_invalid(args.output,sources)
        return
    fetched=True
    if not args.no_fetch:
        fetched=subprocess.run(['git','fetch','--no-tags','origin',
            'refs/heads/experiment/round5-researcher-approved-20261113:refs/remotes/'+REF],
            cwd=ROOT,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode==0
    result,events=verify_sources(sources,args.events_file,'2026-11-13',fetched)
    proof=dict(version='REPO_PRE_CUTOFF_EVIDENCE_V1',retrieved_at=datetime.now(timezone.utc).isoformat(),
               sources_sha256=hashlib.sha256(registry.read_bytes()).hexdigest(),cutoff='2026-11-13',
               branch_fetched=fetched,**result)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(proof,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    evidence=[event for event in events if event.get('id') in {r['push_event_id'] for r in proof['sources'].values()}]
    args.output.with_name('pre_cutoff_evidence_events.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps({key:dict(valid=value['valid'],push_time=value['push_time'],reasons=value['reasons'])
                      for key,value in proof['sources'].items()},ensure_ascii=False))

if __name__=='__main__':main()
