"""Run only after round-five tasks 1 and 2 have been accepted. Never retries."""
import sys
from pathlib import Path
import urllib.request
import urllib.error
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from au_ree_v2.round5_wa import acquire, DECISION, RULE
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None

def fetch(url):
    opener=urllib.request.build_opener(NoRedirect)
    try:
        with opener.open(url,timeout=90) as response:return response.status,response.read()
    except urllib.error.HTTPError as error:return error.code,error.read()

if __name__=='__main__':
    if '--tasks-1-2-accepted' not in sys.argv:raise SystemExit('Required: --tasks-1-2-accepted')
    import json
    repo=Path(__file__).resolve().parents[1]
    decisions=json.loads((repo/'config/researcher_rule_decisions.json').read_text('utf8'))['decisions']
    if not any(d.get('decision_id')==DECISION and d.get('rule')==RULE and d.get('decided_by')=='USER_EXPLICIT_APPROVAL' for d in decisions):raise SystemExit('ROUND5_WA_APPROVAL_REQUIRED')
    print(json.dumps(acquire(repo,fetch),indent=2))
