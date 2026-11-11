from au_ree_v2.round3_annual import select_first_full

def stage(name,value,full,ramp):return dict(stage=name,annual_treo_t=value,full_design_throughput=full,ramp_up=ramp)
def test_first_full_is_not_assumed_to_be_2a():
    rows=[stage('2a',17000,False,True),stage('2b',11000,True,False)]
    assert select_first_full(rows)['stage']=='2b'
def test_earlier_unknown_production_stage_blocks_selection():assert select_first_full([stage('2a',17000,None,None),stage('2b',11000,True,False)]) is None
def test_non_treo_dso_phase_is_not_a_treo_annual_zero():assert select_first_full([stage('1',None,None,None),stage('2a',17000,True,False)])['stage']=='2a'
def test_no_full_stage_stays_unresolved():assert select_first_full([stage('2a',17000,False,True)]) is None

def test_unknown_ramp_status_of_earlier_full_stage_blocks_selection():assert select_first_full([stage("2a",17000,True,None),stage("2b",11000,True,False)]) is None

# Source-bound collector contract tests. PDF extraction is isolated; all SHA and
# authorization checks use real fixture bytes/config rather than bypassing gates.
import hashlib,json
import pytest
import au_ree_v2.round3_annual as annual

@pytest.fixture
def collector_case(tmp_path,monkeypatch):
    (tmp_path/'config').mkdir();source=tmp_path/'source.pdf';source.write_bytes(b'fixture original bytes')
    cfg=dict(decision_id='fixture-annual',project_id='fixture-cummins',source_path='source.pdf',
             source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),source_url='https://example.invalid/source.pdf',approval_evidence=annual.APPROVAL_EVIDENCE)
    decisions=dict(decisions=[dict(decision_id=cfg['decision_id'],rule=annual.RULE,scope=annual.APPROVAL_SCOPE,decided_by='USER_EXPLICIT_APPROVAL',approval_evidence=annual.APPROVAL_EVIDENCE)])
    row={'專案ID':'fixture-cummins','專案名稱':'Cummins Range Rare Earths-Phosphate Project','預估年產TREO_t_per_year':'','預估年產NdPr_t_per_year':''}
    pages={60:'Table 10-3: Stage 2 bene plant process design basis Availability % 91.3% 91.3% Actual operating hours h/annum 8,000 8,000 Annual tonnage (dry) Mtpa 2.0 2.0',
      76:'Stage 2a – Considers high grade bene feed. This is preferentially mined to increase revenues in earlier periods to payback the cost of Stage 2 as quick as possible. Stage 2b – Considers low grade bene feed for the remainder of the regolith resource. Duration (yr) 3.0 2.0 8.0 5.0',
      77:'Production outcomes Stage 1 Stage 2a Stage 2b Stage 3 Average annual TREO production (ktpa) - 17 11 7 NdPr oxide basis US$/kg 100'}
    class Page:
        def __init__(self,n):self.n=n
        def get_text(self,sort=True):return pages[self.n]
    class Document:
        def __enter__(self):return self
        def __exit__(self,*args):return False
        def __getitem__(self,n):return Page(n+1)
    monkeypatch.setattr(annual.fitz,'open',lambda _:Document())
    def run():
        (tmp_path/'config/round3_annual.json').write_text(json.dumps(cfg,ensure_ascii=False),encoding='utf8')
        return annual.collect([row],[],decisions,tmp_path)
    return run,cfg,decisions,row,pages

def test_collector_source_bound_full_stage_and_unit_conversion(collector_case):
    run,cfg,decisions,row,pages=collector_case;fills,reviews,extra=run()
    assert len(fills)==1 and fills[0]['value']=='17000'
    assert fills[0]['column']=='預估年產TREO_t_per_year'
    scope=json.loads(fills[0]['provenance']['scope'])
    assert scope['selected_stage']=='2a' and scope['source_unit']=='ktpa'
    assert any(e['quote']=='Availability % 91.3% 91.3%' for e in scope['evidence'])
    assert reviews[0]['column']=='預估年產NdPr_t_per_year'
    assert row['預估年產TREO_t_per_year']==''

def test_collector_source_sha_mismatch_blocks(collector_case):
    run,cfg,*_=collector_case;cfg['source_sha256']='0'*64
    with pytest.raises(ValueError,match='CUMMINS_SOURCE_SHA'):run()

@pytest.mark.parametrize('page,quote',[(60,'Availability % 91.3% 91.3%'),(60,'Annual tonnage (dry) Mtpa 2.0 2.0'),(76,'Duration (yr) 3.0 2.0 8.0 5.0')])
def test_collector_missing_design_or_phase_proof_stays_review(collector_case,page,quote):
    run,cfg,decisions,row,pages=collector_case;pages[page]=pages[page].replace(quote,'MISSING')
    fills,reviews,_=run();assert not fills and reviews[0]['reason']=='FIRST_FULL_PRODUCTION_STAGE_NOT_VERIFIED'
    assert dict(page=page,quote=quote) in reviews[0]['missing_quotes']

def test_collector_existing_annual_value_preserved(collector_case):
    run,cfg,decisions,row,pages=collector_case;row['預估年產TREO_t_per_year']='9000'
    fills,_,_=run();assert fills==[] and row['預估年產TREO_t_per_year']=='9000'

def test_collector_wrong_project_rejected(collector_case):
    run,cfg,decisions,row,pages=collector_case;row['專案名稱']='Other Rare Earth Project'
    with pytest.raises(ValueError,match='CUMMINS_ONLY_RULE'):run()

def test_collector_wrong_approval_scope_rejected(collector_case):
    run,cfg,decisions,*_=collector_case;decisions['decisions'][0]['scope']='ALL_PROJECTS'
    with pytest.raises(ValueError,match='APPROVAL_SCOPE_MISMATCH'):run()

def test_collector_approval_evidence_cannot_be_changed_together(collector_case):
    run,cfg,decisions,*_=collector_case;cfg['approval_evidence']='synthetic approval';decisions['decisions'][0]['approval_evidence']='synthetic approval'
    with pytest.raises(ValueError,match='APPROVAL_EVIDENCE_MISMATCH'):run()

@pytest.mark.parametrize('change',['unapproved','wrong_rule','duplicate'])
def test_collector_explicit_single_rule_required(collector_case,change):
    run,cfg,decisions,*_=collector_case
    if change=='unapproved':decisions['decisions'][0]['decided_by']='INFERRED'
    elif change=='wrong_rule':decisions['decisions'][0]['rule']='OTHER_RULE'
    else:decisions['decisions'].append(dict(decisions['decisions'][0]))
    with pytest.raises(ValueError,match='EXPLICIT_APPROVAL_REQUIRED'):run()

def test_collector_ambiguous_output_or_ramp_stays_review(collector_case):
    run,cfg,decisions,row,pages=collector_case;pages[77]=pages[77].replace('- 17 11 7','- 70 11 7')
    assert not run()[0]
    pages[77]=pages[77].replace('- 70 11 7','- 17 11 7');pages[76]+=' Stage 2a is a ramp-up phase.'
    assert not run()[0] and run()[1][0]['ramp_up_2a'] is True
