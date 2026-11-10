"""Rejudge rounds 19/20 offline; do not alter historical manifests or acquire data."""
import copy
import csv
import json
from pathlib import Path
from au_ree_v2.convergence import POLICY
from au_ree_v2.iteration_review import review_coverage_cycle
from au_ree_v2.store import filehash

ROOT=Path(__file__).resolve().parents[1]
HISTORY=ROOT/'results/asx-full-scope-2026-11-10'
OUT=ROOT/'results/convergence-codebook'


def backlog(number):
    folder=HISTORY/f'round-{number}-report'
    checks=json.loads((folder/'government_checks.json').read_text('utf8'))
    ids=['NT-REE-October2025-original','REMP2025-native-original','TAS-December2025-prospectus',
         'Victoria-critical-minerals-roadmap','TAS-Windbreak-May2024-original',
         'TAS-Voyager-October2024-original','GOV_VIC_ROADMAP_UPDATE2026_ORIGINAL',
         'Round17-Fingerboards-new-referral-original']
    checks.append(dict(source_key='Fingerboards-2026-referral',
        url='https://www.planning.vic.gov.au/__data/assets/pdf_file/0031/763447/GCM-Fingerboards-Critical-Minerals-Project-EES-referral-form.pdf',
        last_acquisition_status='HTTP_403_RESTRICTED'))
    # First documented blocking rounds in the committed source-action history.
    first=[1,1,1,1,4,4,11,17]
    states=['NT',None,'TAS','VIC','TAS','TAS','VIC','VIC']
    names={'NT':'北領地','TAS':'塔斯馬尼亞州','VIC':'維多利亞州'}
    with (ROOT/'results/asx-current/專案總表.csv').open(encoding='utf-8-sig',newline='') as f:
        rows=list(csv.DictReader(f))
    columns=list(rows[0])
    result=[]
    for i,source in enumerate(checks):
        projects=[r['專案ID'] for r in rows if states[i] is None or r['州省地區']==names[states[i]]]
        if i==7:projects=['AU-7537d9555628040fab40']
        relevant=[r for r in rows if r['專案ID'] in projects]
        fields=[c for c in columns if any(not r[c] for r in relevant)]
        result.append(dict(action_id=ids[i],work_id=source['source_key'],url=source['url'],
            failure_type='BOUNDED_TIMEOUT' if i==1 else 'HTTP_403',
            first_blocked_round=first[i],project_ids=projects,columns=fields,
            impact_scope='Potential evidence within source jurisdiction; field impact not established. No automatic fill or project admission.',
            manual_route='Request an accessible same-work/same-edition copy from the government publisher or a public library; no login, payment or access-control bypass.',
            same_work_edition_copy_available=source.get('same_work_edition_alternative_locally_acquired',False),
            alternative_url=source.get('alternative_url'),
            content_backlog=not source.get('same_work_edition_alternative_locally_acquired',False),
            evidence_refs=[str((folder/'government_checks.json').relative_to(ROOT))+':sha256:'+filehash(folder/'government_checks.json'),
                str((folder/'source_actions.csv').relative_to(ROOT))+':sha256:'+filehash(folder/'source_actions.csv')]+([
                    'results/asx-full-scope-2026-11-10/round-17-report/source_acquisition.csv:sha256:'+filehash(HISTORY/'round-17-report/source_acquisition.csv')] if i==7 else []),
            observed_status=source['last_acquisition_status']))
    return result


def main():
    reports=[];history=[]
    local=ROOT/'work/convergence-engineering'
    local.mkdir(parents=True,exist_ok=True);OUT.mkdir(parents=True,exist_ok=True)
    for number in (19,20):
        old_path=HISTORY/f'round-{number}-report/audit/cycle_review.json'
        old=json.loads(old_path.read_text('utf8'))
        before=ROOT/f'work/asx-fullscope{number}-20261110/baseline'
        after=ROOT/f'work/auto-iteration/fullscope{number}-final-a-53'
        assert filehash(before/'專案總表.csv')==old['baseline_csv_sha256']
        assert filehash(after/'專案總表.csv')==old['current_csv_sha256']
        replay=review_coverage_cycle(before,after,old['review_manifest'])
        assert replay==old, 'LEGACY_REPLAY_CHANGED'
        manifest=copy.deepcopy(old['review_manifest'])
        manifest.update(stopping_policy=POLICY,round_number=number,consecutive_zero_rounds=2,
                        previous_cycle_reviews=history,blocked_acquisitions=backlog(number))
        new=review_coverage_cycle(before,after,manifest)
        (local/f'round-{number}-rejudged-full.json').write_text(json.dumps(new,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
        history=[{k:new[k] for k in ('round_number','cycle_id','baseline_csv_sha256','current_csv_sha256','stopping_rule')}]
        reports.append(dict(round_number=number,original_report_sha256=filehash(old_path),
            legacy_replay_identical=True,original_stopping_rule=old['stopping_rule'],
            rejudged_stopping_rule=new['stopping_rule'],blocked_acquisitions=new['blocked_acquisitions'],
            baseline_csv_sha256=new['baseline_csv_sha256'],current_csv_sha256=new['current_csv_sha256']))
    result=dict(version='offline-historical-convergence-rejudgment-v1',new_acquisition_or_search=False,
        policy=POLICY,required_zero_rounds=2,history_window='19-20; round19 has gain4 and resets all prior streaks',
        rounds=reports,limitations='Stopping is not source exhaustion. Six original target works lack qualified same-edition copies; VIC2024 content copy is available although original URL is blocked; Fingerboards adds one separate unavailable work. Eight blocked URL/actions: seven HTTP403 and one bounded timeout. Not all are403.')
    (OUT/'historical_rejudgment.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps([{k:r[k] for k in ('round_number','rejudged_stopping_rule')} for r in reports],indent=2))


if __name__=='__main__':main()
