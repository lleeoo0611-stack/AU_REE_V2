"""Apply only researcher-approved company locators, preserving every old marker."""
import argparse
import copy
import csv
import hashlib
import json
import subprocess
from pathlib import Path
from au_ree_v2.store import digest

ROOT=Path(__file__).resolve().parents[1]
BASE=Path('results/claims-locators-2026-11-16')
BASELINE='fc8b1b05dee2ff9db8fb75fe35ac9ba44c267a8d'
PROPOSAL_SHA256='478d89cd43259bd8e1f4ef57f5d539e94d26802f0dc5362d2569836744f02c09'
APPROVED_IDS=frozenset({
    '0219c1191a1f9eab0363','0587804e74b3c7df655d','08a9c376a4fce11e016d',
    '17f97d16dea43b1de13b','1aae6b04ef6b36236bc1','1abe56e73e0e873b9177',
    '26ea20475f81cbd785ee','26fdc85f4b545448adcf','2759b66774123c58ac8a',
    '27a3de85505063c14d67','2a7514204df6fec21699','2bf2eb7bd5ac91992818',
    '3376cc3e6f0de4eaf1b3','36110d1400845dc379f9','365446faabc8bd08d19d',
    '3c5c972564feb35d2790','4191f68329ecec567825','430224274e95e67c1c2e',
    '466ccaed064b5e7c70c1','4eb2ad8e9d3cc1da34c0','4ebe761f9ee28fb1c91c',
    '53b7b8273b0052e8cf1a','53c7274eb2e217c6474c','55877f24194314c7da04',
    '5843adf6632b06a84587','5925cbfdc87e4ddcffc8','597ea53de66f29966608',
    '5d0887debd2337e178e8','6578ed45124e1998367f','66c1ed785094684482a2',
    '66e4e3978cb5f5c90222','70ff5a99820f053dbc46','722bae721c7a3bfdb0a1',
    '74a4adea0d5046b80b76','75f3091d0ebc1c2d56ff','794e0ce6c43fcfb59eb5',
    '85fa0b786e195b7833b7','89f5d991fba22fc0b351','8b1be91dd627faba9c07',
    '8cff27acf8aaec6f2f23','925bbf879fdf29acc085','95bac1efcfd64895d113',
    '9ada1b2ab559b5aaceb4','9cadb348af188786758a','9d6bb83cc398ce6effa3',
    'a3559f7622230839a349','a5f1b1c694afe7534bf5','a5f85c7f1a5bc07a51bb',
    'aeb6dee4b5561dc9b4c9','b1391083140ec5e7ffaf','b7b63d1d9f5a3fdc97cf',
    'bcf100c1be5b72eba24d','bffe8af62feb3459fa68','c0deb2cf01601f1c4b71',
    'c2924b73311278079881','c5f51f4a82c8bd9c48b4','cb8125a332a8f6ba234b',
    'cc2eb7611b38cbdd67ee','d265879b9b16a79166e6','d61d3892378b51ab8a0d',
    'e23af29b0eef38722fbf','e3320bf6b6ad69b11ec7','e66324425dc64eb86c32',
    'e6ba5b4d5936ed25b4b0','e731b9147a0558ecf3ad','eac09aa3193bdd195556',
    'ee780f8d19986a0486a1','fbc2860a60e1a7b7ff1a','fd48b7e16b2fca0d4550',
    'fd5ace0f51a299c210fd',
})
HOLD_IDS=frozenset({
    '03178ad50073a389fdc6','0d5b7033a1987ba114ee','2bea7436a6168e73d302',
    '44eb80a82ec452c0bf16','59a562aa272eff65e74a','5c0df6a2c14fc39008d4',
    '65ad70f8e7e0294e9fb8','672c4a734422ee4d0592','78c2ccf4953882928a75',
    '80e33dbdf9fbb25bc28a','8b4dc3ee9099891bdfc7','9058afe5131c73739bc2',
    'a8c9aebb28e797411c0d','c78d798ad99341346b15','cc854a55d8bcbede950e',
    'd85aa7345501657951bb','e10d23e901a234c4b18b','e381084c8b6b3c9cacdd',
    'f1a6df51baffce7cff4a','f435149f752a22cf7a67','f9cebe076af864e53f27',
    'fd67aedd657a1d6194da',
})
CONFLICT_FIELDS=['proposal_id','project_id','column','source_key','declaration_pointer','pdf_page',
                 'field','existing_value','proposed_value','reason','action']


def read_rows(path):
    with Path(path).open(encoding='utf-8-sig',newline='') as stream:
        return list(csv.DictReader(stream))


def write_rows(path,rows,fields):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('w',encoding='utf-8-sig',newline='') as stream:
        writer=csv.DictWriter(stream,fields);writer.writeheader();writer.writerows(rows)


def project_map(claims):
    return {'AU-'+digest([p.get('entity_namespace','project_registry_v1'),str(p['id'])])[:20]:p
            for p in claims['projects']}


def load_ledger(root=ROOT):
    root=Path(root)
    original=root/BASE/'v9/p2_marker_proposals.csv'
    if hashlib.sha256(original.read_bytes()).hexdigest()!=PROPOSAL_SHA256:
        raise ValueError('PROPOSAL_BASELINE_CHANGED')
    baseline=read_rows(original)
    rows=read_rows(root/BASE/'v10/p2_marker_proposals_researcher_approved.csv')
    if len(rows)!=len(baseline):raise ValueError('APPROVAL_ROW_COUNT_CHANGED')
    for old,new in zip(baseline,rows):
        if any(old[k]!=new[k] for k in old if k!='approved'):
            raise ValueError('APPROVAL_CHANGED_PROPOSAL_CONTENT')
        expected='Y' if new['column'] in ('ASX代碼','未上市公司') and new['proposal_id'] in APPROVED_IDS else (
                 'HOLD' if new['column'] in ('ASX代碼','未上市公司') and new['proposal_id'] in HOLD_IDS else '')
        if new['approved']!=expected:raise ValueError('UNAPPROVED_PROPOSAL_ID_OR_SCOPE')
    selected=[r for r in rows if r['approved']=='Y']
    if len(selected)!=70 or {r['proposal_id'] for r in selected}!=APPROVED_IDS:
        raise ValueError('APPROVED_SET_NOT_EXACTLY_SEVENTY')
    return rows,selected


class MarkerConflict(ValueError):
    def __init__(self,row,field,existing,proposed,reason):
        self.record={k:row[k] for k in CONFLICT_FIELDS[:6]}
        self.record.update(field=field,existing_value=json.dumps(existing,ensure_ascii=False),
            proposed_value=json.dumps(proposed,ensure_ascii=False),reason=reason,action='NOT_APPLIED')
        super().__init__(reason)


def binding_for(project,row):
    pointer=row['declaration_pointer']
    if pointer=='/identity_declaration':
        parent=project;source_key=parent['identity_source'];sha=parent['identity_declaration']['source_sha256']
    elif pointer.startswith('/attributes/'):
        parts=pointer.strip('/').split('/')
        parent=project['attributes'][int(parts[1])]
        if parent.get('column')!=row['column']:raise ValueError('NON_COMPANY_DECLARATION_SCOPE')
        source_key=parent['source_key'];sha=parent['source_sha256']
    else:raise ValueError('NON_COMPANY_DECLARATION_POINTER')
    if source_key!=row['source_key'] or sha!=row['source_sha256']:
        raise MarkerConflict(row,'source_key/source_sha256',[source_key,sha],
            [row['source_key'],row['source_sha256']],'SOURCE_BINDING_CONFLICT')
    binding=project
    for token in pointer.strip('/').split('/'):
        binding=binding[int(token)] if isinstance(binding,list) else binding[token]
    return binding


def apply_rows(claims,rows):
    result=copy.deepcopy(claims);projects=project_map(result);seen=set();log=[]
    for row in rows:
        if row.get('approved')!='Y' or row['proposal_id'] not in APPROVED_IDS or row['column'] not in ('ASX代碼','未上市公司'):
            raise ValueError('UNAPPROVED_PROPOSAL_ID_OR_SCOPE')
        location=row['project_id'],row['declaration_pointer']
        if location in seen:
            raise MarkerConflict(row,'declaration_pointer',location,location,'DUPLICATE_APPROVED_LOCATION')
        seen.add(location)
        binding=binding_for(projects[row['project_id']],row)
        page_key='pdf_page' if 'pdf_page' in binding else 'page'
        marker_key='page_markers' if 'page_markers' in binding else 'markers'
        if type(binding.get(page_key)) is not int or binding[page_key]!=int(row['pdf_page']):
            raise MarkerConflict(row,page_key,binding.get(page_key),int(row['pdf_page']),'PAGE_CONFLICT')
        old=binding.get(marker_key)
        if not isinstance(old,list) or any(not isinstance(m,str) for m in old):
            raise MarkerConflict(row,marker_key,old,None,'MARKER_TYPE_CONFLICT')
        proposed=[row['marker_1'],row['marker_2']]
        if any(not m for m in proposed):raise ValueError('EMPTY_APPROVED_MARKER')
        binding[marker_key]=old+[m for m in proposed if m not in old]
        log.append(dict(proposal_id=row['proposal_id'],project_id=row['project_id'],column=row['column'],
            declaration_pointer=row['declaration_pointer'],source_key=row['source_key'],
            source_sha256=row['source_sha256'],pdf_page=row['pdf_page'],
            existing_markers=json.dumps(old,ensure_ascii=False),
            resulting_markers=json.dumps(binding[marker_key],ensure_ascii=False)))
    return result,log


def expected_claims(root=ROOT):
    _,rows=load_ledger(root)
    original=subprocess.check_output(['git','show',BASELINE+':data/claims.json'],cwd=root)
    return apply_rows(json.loads(original),rows)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--apply',action='store_true')
    args=parser.parse_args();out=ROOT/BASE/'v10'
    current=json.loads((ROOT/'data/claims.json').read_bytes())
    try:
        result,log=expected_claims()
        original=json.loads(subprocess.check_output(['git','show',BASELINE+':data/claims.json'],cwd=ROOT))
        if current not in (original,result):raise ValueError('CLAIMS_CONTAIN_UNEXPECTED_CHANGES')
    except MarkerConflict as exc:
        write_rows(out/'p2_conflicts.csv',[exc.record],CONFLICT_FIELDS)
        raise SystemExit(exc.args[0])
    if args.apply:
        (ROOT/'data/claims.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    write_rows(out/'p2_conflicts.csv',[],CONFLICT_FIELDS)
    write_rows(out/'p2_applied_markers.csv',log,list(log[0]))
    print(json.dumps(dict(approved_locations=len(log),applied=args.apply,
        original_markers_preserved=True,source_and_page_unchanged=True)))


if __name__=='__main__':main()
