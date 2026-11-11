"""Cummins-only annual TREO forecast selected by source-bound full design throughput."""
import json,re
from pathlib import Path
import fitz
from .store import filehash
RULE='STAGED_ANNUAL_USE_FIRST_FULL_PRODUCTION_STAGE'
QUALIFIER='STAGED_PRODUCTION_FIRST_FULL_STAGE'
APPROVAL_SCOPE='CUMMINS_RANGE_FIRST_FULL_PRODUCTION_STAGE_ONLY'
APPROVAL_EVIDENCE='甲1 甲2 刪掉 乙1 (a) 放寬條件、(c) Mt Stirling 共點、(d) VIC／TAS核准 乙2 可以，核准 乙5 第一個全產期'

def select_first_full(stages):
    for stage in stages:
        if stage.get('annual_treo_t') is None:continue
        if stage.get('full_design_throughput') is True and stage.get('ramp_up') is False:return stage
        if stage.get('full_design_throughput') is None or (stage.get('full_design_throughput') is True and stage.get('ramp_up') is None):return None
    return None

def collect(rows,trace,decisions,repo):
    repo=Path(repo);cfg=json.loads((repo/'config/round3_annual.json').read_text('utf8'))
    if cfg.get('approval_evidence')!=APPROVAL_EVIDENCE:raise ValueError('ROUND3_ANNUAL_APPROVAL_EVIDENCE_MISMATCH')
    records=[d for d in decisions['decisions'] if d.get('decision_id')==cfg['decision_id'] and d.get('rule')==RULE and d.get('decided_by')=='USER_EXPLICIT_APPROVAL' and d.get('approval_evidence')==cfg['approval_evidence']]
    if len(records)!=1:raise ValueError('ROUND3_ANNUAL_EXPLICIT_APPROVAL_REQUIRED')
    if records[0].get('scope')!=APPROVAL_SCOPE:raise ValueError('ROUND3_ANNUAL_APPROVAL_SCOPE_MISMATCH')
    row=next(r for r in rows if r['專案ID']==cfg['project_id'])
    if row['專案名稱']!='Cummins Range Rare Earths-Phosphate Project':raise ValueError('CUMMINS_ONLY_RULE')
    path=repo/cfg['source_path']
    if filehash(path)!=cfg['source_sha256']:raise ValueError('CUMMINS_SOURCE_SHA')
    with fitz.open(path) as doc:
        text={page:' '.join(doc[page-1].get_text(sort=True).split()) for page in (60,76,77)}
    checks=[(60,'Table 10-3: Stage 2 bene plant process design basis'),(60,'Availability % 91.3% 91.3%'),(60,'Actual operating hours h/annum 8,000 8,000'),(60,'Annual tonnage (dry) Mtpa 2.0 2.0'),(76,'Stage 2a – Considers high grade bene feed.'),(76,'Stage 2b – Considers low grade bene feed for the remainder of the regolith resource.'),(76,'This is preferentially mined to increase revenues in earlier periods to payback the cost of Stage 2 as quick as possible.'),(76,'Duration (yr) 3.0 2.0 8.0 5.0'),(77,'Production outcomes Stage 1 Stage 2a Stage 2b Stage 3')]
    problems=[dict(page=p,quote=q) for p,q in checks if q not in text[p]]
    production=re.search(r'Average annual TREO production \(ktpa\)\s+-\s+17\s+11\s+7(?!\d)',text[77])
    ramp=bool(re.search(r'stage 2a.{0,80}ramp|ramp.{0,80}stage 2a',text[76],re.I))
    if problems or not production or ramp:
        return [],[dict(project_id=row['專案ID'],reason='FIRST_FULL_PRODUCTION_STAGE_NOT_VERIFIED',missing_quotes=problems,ramp_up_2a=ramp)],{}
    stages=[dict(stage='1',annual_treo_t=None,full_design_throughput=None,ramp_up=None),dict(stage='2a',annual_treo_t=17000,full_design_throughput=True,ramp_up=False,annual_feed_mt=2.0,actual_hours=8000),dict(stage='2b',annual_treo_t=11000,full_design_throughput=True,ramp_up=False,annual_feed_mt=2.0,actual_hours=8000),dict(stage='3',annual_treo_t=7000,full_design_throughput=None,ramp_up=None)]
    selected=select_first_full(stages)
    if selected is None:return [],[dict(project_id=row['專案ID'],reason='FIRST_FULL_PRODUCTION_STAGE_UNRESOLVED')],{}
    scope=dict(qualifier=QUALIFIER,decision_id=cfg['decision_id'],all_stages=stages,selected_stage=selected['stage'],source_unit='ktpa',unit_conversion='17 ktpa * 1000 = 17000 t/year',evidence=[dict(physical_page=p,quote=q) for p,q in checks]+[dict(physical_page=77,quote=production.group())],full_stage_basis='Both Stage 2a and 2b use the same 2.0 Mtpa annual design feed, 8000 actual operating hours and 91.3% availability. The phase distinction is high-grade versus lower-grade feed, not ramp-up. Stage 1 has no reported TREO annual output. Earliest full-design TREO-producing stage is 2a.',limitation='SCOPING_STUDY_FORECAST_NOT_OPERATING_OUTPUT;CUMMINS_RANGE_ONLY')
    fills=[];column='預估年產TREO_t_per_year'
    if not row[column]:
        p=dict(project_id=row['專案ID'],column=column,value='17000',source_sha256=cfg['source_sha256'],source_url=cfg['source_url'],locator='physical PDF p60 Table10-3 design basis; p76 phase definitions; p77 Table12-6 production outcomes',method=RULE,scope=json.dumps(scope,ensure_ascii=False,sort_keys=True),observation_ids='[]',review_ids=json.dumps([cfg['decision_id']]),review_methods=json.dumps([RULE]),publication_date='2023-08-22',source_kind='ISSUER_SCOPING_STUDY_FORECAST',forecast_derivation='FIRST_FULL_DESIGN_PRODUCTION_STAGE_2A')
        fills.append(dict(project_id=row['專案ID'],column=column,value='17000',decision_id=cfg['decision_id'],provenance=p))
    reviews=[dict(project_id=row['專案ID'],project=row['專案名稱'],column='預估年產NdPr_t_per_year',reason='NO_EXPLICIT_SAME_STAGE_NDPR_ANNUAL_OUTPUT; p77 NdPr oxide basis US$/kg is a price, not output')]
    return fills,reviews,dict(cummins_production_stage_evidence=scope)
