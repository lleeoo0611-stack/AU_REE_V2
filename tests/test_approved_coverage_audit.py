"""Isolated acceptance tests; no published filled-count assumptions."""
import copy
import csv
import json
import shutil
from pathlib import Path

import pytest
from au_ree_v2.approved_coverage_audit import audit_approved_coverage, validate_decisions, NULL_IDS
from au_ree_v2.coverage_task_audit import read_csv
from au_ree_v2.iteration_review import audit_summary
from au_ree_v2.blank_classification import classify_blanks, load_blank_rules
from au_ree_v2.stage_rules import stage_rule_fills
from au_ree_v2.store import filehash

ROOT=Path(__file__).resolve().parents[1]

@pytest.fixture
def decisions():
    data=json.loads((ROOT/'config/researcher_rule_decisions.json').read_text('utf8'))
    # Independent of whether the production registry subsequently changes status.
    for d in data['decisions']:
        d['decided_by']=None if d['decision_id'] in NULL_IDS else 'USER_EXPLICIT_APPROVAL'
        # Round-three extensions bind the exact quote; retain it while testing the historical gate.
        if d['decided_by'] and not d['decision_id'].startswith('round3-'): d['approval_evidence']='Explicit approval fixture'
    return data

@pytest.fixture
def projections(tmp_path):
    a=tmp_path/'before'; b=tmp_path/'after'
    a.mkdir()
    columns=json.loads((ROOT/'config/project_summary_columns_legacy52.json').read_text('utf8'))+['ASX代碼']
    row=dict.fromkeys(columns,'');row.update({'專案ID':'test','專案名稱':'Test Project','開發階段':'Exploration'})
    write(a/'專案總表.csv',[row])
    traces=[dict(project_id='test',column=c,value=v,source_sha256='a'*64,source_url='https://example.org/source',
        locator='page 1',method='SOURCE_REPORTED',scope='',publication_date='2026-01-01') for c,v in row.items() if v]
    write(a/'field_provenance.csv',traces)
    write(a/'missing_fields.csv',[dict(project_id='test',column=c,reason='NO_SOURCE_VALUE',blank_class='',blank_rule_id='') for c,v in row.items() if not v])
    write(a/'census_inventory.csv',[dict(entity_id='test',kind='project',name='Test Project')])
    summary=dict(version='census-project-summary-v3-asx-identity',base_contract_columns=52,identity_ledger_sha256='a'*64,
        output_hashes={n:'' for n in ('專案總表.csv','field_provenance.csv','missing_fields.csv','census_inventory.csv')})
    (a/'summary.json').write_text(json.dumps(summary),encoding='utf8')
    seal(a);shutil.copytree(a,b)
    return a,b


def write(path, rows):
    with path.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)


def seal(folder):
    rows=read_csv(folder/'專案總表.csv'); provenance=read_csv(folder/'field_provenance.csv')
    missing=read_csv(folder/'missing_fields.csv')
    filled={(r['專案ID'],c) for r in rows for c,v in r.items() if v}
    missing=[m for m in missing if (m['project_id'],m['column']) not in filled]
    summary=json.loads((folder/'summary.json').read_text('utf8'))
    summary['filled_counts']={c:sum(bool(r[c]) for r in rows) for c in rows[0]}
    summary['blank_coverage']=classify_blanks(rows,missing,provenance,load_blank_rules(ROOT/'config/blank_classification_legacy53.json'))
    write(folder/'missing_fields.csv',missing)
    summary['output_hashes']={name:filehash(folder/name) for name in summary['output_hashes']}
    (folder/'summary.json').write_text(json.dumps(summary,ensure_ascii=False),encoding='utf8')
    (folder/'audit.json').write_text(json.dumps(audit_summary(folder),ensure_ascii=False),encoding='utf8')


def test_exact_decisions(decisions):
    assert len(validate_decisions(decisions))==19

@pytest.mark.parametrize('mutation',['extra','duplicate','null_enabled','approved_null','scope','rule','date','evidence'])
def test_reject_decision_mutations(decisions,mutation):
    d=decisions['decisions'][0]
    if mutation=='extra':decisions['decisions'].append(dict(d,decision_id='unapproved'))
    if mutation=='duplicate':decisions['decisions'].append(copy.deepcopy(d))
    if mutation=='null_enabled':next(x for x in decisions['decisions'] if x['decision_id'] in NULL_IDS)['decided_by']='USER_EXPLICIT_APPROVAL'
    if mutation=='approved_null':d['decided_by']=None
    if mutation=='scope':d['scope']='ANY'
    if mutation=='rule':d['rule']='ANY'
    if mutation=='date':d['decided_date']='2027-01-01'
    if mutation=='evidence':d['approval_evidence']=''
    with pytest.raises(ValueError):validate_decisions(decisions)


def test_unchanged_accepts_without_required_addition_count(projections,decisions):
    result=audit_approved_coverage(*projections,decisions)
    assert result['new_cells']==result['changed_cells']==0


def add_stage(folder,decisions):
    rows=read_csv(folder/'專案總表.csv'); traces=read_csv(folder/'field_provenance.csv')
    row,fills=next((r,f) for r in rows if (f:=stage_rule_fills(r,traces,decisions)))
    for fill in fills:
        row[fill['column']]=fill['value']; trace=dict.fromkeys(traces[0],'')
        trace.update(project_id=row['專案ID'],column=fill['column'],value=fill['value'],source_sha256=fill['sha'],
            locator=fill['locator'],method=fill['method'],scope=fill['scope'],source_url=json.loads(fill['scope'])['source_provenance']['source_url'])
        traces.append(trace)
    write(folder/'專案總表.csv',rows);write(folder/'field_provenance.csv',traces);seal(folder)
    return row,fills


def test_stage_exact_replay(projections,decisions):
    row,fills=add_stage(projections[1],decisions)
    assert audit_approved_coverage(*projections,decisions)['new_cells']==len(fills)

@pytest.mark.parametrize('field,value',[('method','UNREVIEWED'),('scope','{}'),('locator','wrong'),('source_sha256','0'*64)])
def test_stage_tamper_rejected(projections,decisions,field,value):
    row,fills=add_stage(projections[1],decisions)
    traces=read_csv(projections[1]/'field_provenance.csv');traces[-1][field]=value
    write(projections[1]/'field_provenance.csv',traces);seal(projections[1])
    with pytest.raises(ValueError,match='STAGE_REPLAY'):audit_approved_coverage(*projections,decisions)


def test_duplicate_provenance_rejected(projections,decisions):
    traces=read_csv(projections[1]/'field_provenance.csv');traces.append(traces[0])
    write(projections[1]/'field_provenance.csv',traces)
    with pytest.raises(ValueError,match='DUPLICATE'):audit_approved_coverage(*projections,decisions)


def test_protected_provenance_rejected(projections,decisions):
    traces=read_csv(projections[1]/'field_provenance.csv');traces[0]['locator']='tampered'
    write(projections[1]/'field_provenance.csv',traces);seal(projections[1])
    with pytest.raises(ValueError,match='PROVENANCE_CHANGED'):audit_approved_coverage(*projections,decisions)


def test_stale_audit_rejected(projections,decisions):
    (projections[1]/'audit.json').write_text('{}',encoding='utf8')
    with pytest.raises(ValueError,match='STALE_AUDIT'):audit_approved_coverage(*projections,decisions)


def test_unapproved_blank_fill_rejected(projections,decisions):
    rows=read_csv(projections[1]/'專案總表.csv');traces=read_csv(projections[1]/'field_provenance.csv')
    row=next(r for r in rows if not r['礦床型態代碼']); row['礦床型態代碼']='iac'
    p=dict.fromkeys(traces[0],'');p.update(project_id=row['專案ID'],column='礦床型態代碼',value='iac',method='APPROVED_RESEARCHER_STAGE_RULE');traces.append(p)
    write(projections[1]/'專案總表.csv',rows);write(projections[1]/'field_provenance.csv',traces);seal(projections[1])
    with pytest.raises(ValueError):audit_approved_coverage(*projections,decisions)

@pytest.fixture
def location_case():
    from au_ree_v2.official_location_adapters import normalize_feature, validate_candidate_pair
    from au_ree_v2.approved_coverage_audit import _location
    candidate=normalize_feature('WA_MINEDEX',{'attributes':{'site_code':'1','site_title':'Test Project','site_commo':'Rare earth','longitude':120,'latitude':-30}},
        {'sha256':'a'*64,'url':'https://public-services.slip.wa.gov.au/public/rest/services/SLIP_Public_Services/Industry_and_Mining_WFS/MapServer/0/query?where=test','acquired_at':'2026-11-11'})
    did='official-location-wa_minedex-20261111';candidate['decision_id']=did
    old={'專案ID':'test','專案名稱':'Test Project','州省地區':'西澳','緯度':'','經度':''}
    new=dict(old,緯度='-30',經度='120');traces={}
    for c in ('緯度','經度'):
        traces['test',c]=dict(scope=json.dumps(candidate),method='AUTO_MATCHED_OFFICIAL_POINT',source_kind='GOVERNMENT_SPATIAL_CATALOGUE',
            source_sha256='a'*64,source_url=candidate['source_url'],acquired_through='2026-11-11',review_ids=json.dumps([did]),
            value=new[c],locator='0; feature 1; OFFICIAL_OCCURRENCE_REPRESENTATIVE_POINT')
    return old,new,traces,{did:{}},candidate


def test_location_pair_valid(location_case):
    from au_ree_v2.approved_coverage_audit import _location
    assert _location(*location_case[:4])=='official-location-wa_minedex-20261111'

@pytest.mark.parametrize('field,value',[('dataset','NT_STRIKE'),('decision_id','unapproved'),('state','SA'),('output_crs','EPSG:4326'),('names',['Other']),('longitude',121),('layer','9'),('source_url','https://evil.example/query')])
def test_location_rejects_wrong_scope(location_case,field,value):
    from au_ree_v2.approved_coverage_audit import _location
    old,new,traces,registry,c=location_case;c[field]=value
    for p in traces.values():p['scope']=json.dumps(c)
    with pytest.raises(ValueError):_location(old,new,traces,registry)


def test_location_rejects_unpaired_scope(location_case):
    from au_ree_v2.approved_coverage_audit import _location
    old,new,traces,registry,c=location_case;traces['test','經度']['scope']='{}'
    with pytest.raises(ValueError,match='PAIR_SCOPE'):_location(old,new,traces,registry)


def test_circle_source_scope_and_arithmetic():
    from au_ree_v2.approved_coverage_audit import _chemistry, CIRCLE, SCOPED_IDS
    pid,sid,sha=CIRCLE;column='NdPr蘊藏量_kt_需兩者皆公布'
    old={'專案ID':pid,'礦石蘊藏量_Mt':'10','元素數據一致性檢查':'old'};new=dict(old);new[column]='2'
    meta=dict(decision_id=SCOPED_IDS[pid],statement_id=sid,source_sha256=sha,scope='exact resource',effective_date='2023-06',ore_cell={'page':2},ore_mt=10,
        definition='NdPr = Nd2O3 + Pr6O11',definition_page=2,native_ndpr=dict(unit='ppm',page=2,bbox=[1,2,3,4],row_bbox=[1,2,3,4],section_id='selected',value=200,original_token='200'))
    trace=dict(locator=json.dumps(meta),source_sha256=sha,scope='exact resource',method='SOURCE_COMBINED_NDPR_OXIDE_PPM_X_ORE_MT')
    assert _chemistry(old,new,trace,column,{})==SCOPED_IDS[pid]
    new[column]='3'
    with pytest.raises(ValueError,match='CHEMISTRY_VALUE'):_chemistry(old,new,trace,column,{})
    new[column]='2';meta['statement_id']='other';trace['locator']=json.dumps(meta)
    with pytest.raises(ValueError,match='CHEMISTRY_SCOPE'):_chemistry(old,new,trace,column,{})
