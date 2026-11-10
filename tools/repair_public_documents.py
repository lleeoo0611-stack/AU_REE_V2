"""Repair only an explicitly frozen blocked-work plan; no broad discovery/cycle."""
import argparse
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
from au_ree_v2.public_document_repair import RepairSession,atomic_json,public_value,utc


def worker(config,out,action):
    cfg=json.loads(Path(config).read_text('utf8'));session=RepairSession(cfg,out)
    work=next(w for w in cfg['works'] if w['action_id']==action)
    if work.get('reuse'):
        data=work['reuse'];sha=data['sha256']
        if sha not in session.state['documents']:
            session.reuse(work,data['path'],data['url'],sha,data['receipt_path'])
        print(action,'REUSED',flush=True);return
    # Entry, navigation and document requests share this genuine cookie session.
    candidates=[]
    import re
    for entry in work.get('entry_urls',[]):
        result=session.acquire(work,entry,kind='html')
        for link in result.get('links',[]):
            if link==work['url'] or re.search(work['download_link_pattern'],link,re.I):
                candidates.append((link,entry))
    # Always retain the explicitly recorded original identity; never invent a URL.
    if work['url'] not in {u for u,e in candidates}:candidates.insert(0,(work['url'],None))
    for url,entry in list(dict.fromkeys(candidates))[:cfg['policy']['max_documents_per_work']]:
        if __import__('urllib.parse',fromlist=['urlsplit']).urlsplit(url).hostname not in cfg['allowed_hosts']:continue
        result=session.acquire(work,url,kind='pdf',entry_url=entry)
        print(action,result['status'],flush=True)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('command',choices=['run','worker','browser-worker','import','browser','status','verify-identities'])
    p.add_argument('--config',required=True);p.add_argument('--out',required=True)
    p.add_argument('--action-id');p.add_argument('--file');p.add_argument('--metadata')
    p.add_argument('--reviews',help='Reviewed work/edition identities with native evidence; does not admit field values')
    args=p.parse_args();cfg=json.loads(Path(args.config).read_text('utf8'));out=Path(args.out)
    if args.command=='worker':worker(args.config,out,args.action_id);return
    if args.command=='browser-worker':
        from au_ree_v2.public_document_browser import acquire_browser
        session=RepairSession(cfg,out);work=next(w for w in cfg['works'] if w['action_id']==args.action_id)
        print(work['action_id'],acquire_browser(session,work)['status'],flush=True);return
    if args.command in ('run','browser'):
        # Sequential source jobs obey per-domain=1 and global<=2. A process wall
        # deadline also bounds DNS/header stalls and PDF parse, outside urllib.
        out.mkdir(parents=True,exist_ok=True)
        for work in cfg['works']:
            if args.action_id and work['action_id']!=args.action_id:continue
            command='worker' if args.command=='run' else 'browser-worker'
            proc=subprocess.Popen([sys.executable,__file__,command,'--config',args.config,'--out',str(out),'--action-id',work['action_id']],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
            try:
                stdout,stderr=proc.communicate(timeout=cfg['policy']['work_timeout'])
                print(stdout.strip(),flush=True)
                if proc.returncode:
                    state=RepairSession(cfg,out)
                    state.state['attempts'].append(dict(action_id=work['action_id'],method='CONTROLLER',status='WORKER_ERROR',
                        http_status=None,at=utc(),error_summary='Worker failed; inspect private worker stderr; exit='+str(proc.returncode)))
                    private=out/'worker-errors';private.mkdir(exist_ok=True)
                    (private/(str(__import__('hashlib').sha256(work['action_id'].encode()).hexdigest())+'.txt')).write_text(stderr,encoding='utf8')
                    state.save()
            except subprocess.TimeoutExpired:
                proc.kill();proc.communicate();state=RepairSession(cfg,out)
                active=[a for a in state.state['attempts'] if a.get('action_id')==work['action_id'] and a.get('status')=='STARTED']
                for a in active:a.update(status='WORKER_DEADLINE_OUTCOME_UNCERTAIN',http_status=None)
                state.state['attempts'].append(dict(action_id=work['action_id'],method='CONTROLLER',status='WORK_BUDGET_EXHAUSTED',
                    http_status=None,at=utc(),error_summary='No confirmed HTTP response for unfinished attempt; inspect receipts before retry'))
                state.save();print(work['action_id'],'WORK_BUDGET_EXHAUSTED',flush=True)
        return
    session=RepairSession(cfg,out)
    if args.command=='verify-identities':
        if not args.reviews:p.error('verify-identities requires reviews')
        from au_ree_v2.public_document_repair import verify_document_identity
        for review in json.loads(Path(args.reviews).read_text('utf8'))['reviews']:
            work=next(w for w in cfg['works'] if w['action_id']==review['action_id'])
            result=verify_document_identity(session,work,review)
            print(work['action_id'],result['identity_status'],flush=True)
        return
    if args.command=='import':
        if not args.action_id or not args.file or not args.metadata:p.error('import requires action-id, file and metadata')
        work=next(w for w in cfg['works'] if w['action_id']==args.action_id)
        print(json.dumps(public_value(session.manual_import(work,args.file,json.loads(Path(args.metadata).read_text('utf8')))),ensure_ascii=False,indent=2));return
    print(json.dumps(public_value(session.state),ensure_ascii=False,indent=2))


if __name__=='__main__':main()
