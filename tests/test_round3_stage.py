import importlib.util
import json
from pathlib import Path
import pytest
import fitz

from au_ree_v2 import round3_stage as s


def source(tmp_path,text,ext='.txt',dates=None):
    p=tmp_path/('source'+ext);p.write_text(text,encoding='utf8')
    return dict(path=str(p),sha256=s.sha256(p),kind=ext[1:],dates=['2026-01-02'] if dates is None else dates,associations=['test'],url='https://example.test/source')


def test_literal_keywords_and_acronym_boundaries(tmp_path):
    e=source(tmp_path,'No PFS. Withdrawal proposed; production not achieved. profile FIDELITY.')
    hits,issues,pages=s.scan_original(e,s.DEFAULT_KEYWORDS)
    assert not issues and pages==1
    assert {h['keyword'] for h in hits}=={'PFS','withdraw','production'}
    assert all(h['physical_page'] is None for h in hits)


def test_scan_later_pdf_page(tmp_path):
    p=tmp_path/'source.pdf';doc=fitz.open()
    for text in ['Early exploration of a mineral deposit with no published resource.', 'Feasibility studies are planned for the next reporting period.']:
        page=doc.new_page();page.insert_text((70,70),text)
    doc.save(p);doc.close()
    e=dict(path=str(p),sha256=s.sha256(p),kind='pdf')
    hits,issues,pages=s.scan_original(e,s.DEFAULT_KEYWORDS)
    assert pages==2 and not issues
    assert hits[0]['physical_page']==2 and hits[0]['keyword']=='Feasibility'


def test_blank_pdf_page_blocks_absence(tmp_path):
    p=tmp_path/'blank.pdf';doc=fitz.open();doc.new_page();doc.save(p);doc.close()
    hits,issues,pages=s.scan_original(dict(path=str(p),sha256=s.sha256(p),kind='pdf'),s.DEFAULT_KEYWORDS)
    assert not hits and issues[0]['reason']=='PAGE_WITHOUT_EXTRACTABLE_TEXT'


def test_missing_and_changed_originals_fail_closed(tmp_path):
    e=source(tmp_path,'exploration')
    Path(e['path']).write_text('changed')
    assert s.scan_original(e,s.DEFAULT_KEYWORDS)[1][0]['reason']=='ARCHIVED_ORIGINAL_SHA_MISMATCH'
    Path(e['path']).unlink()
    assert s.scan_original(e,s.DEFAULT_KEYWORDS)[1][0]['reason']=='ARCHIVED_ORIGINAL_MISSING'


def test_html_hidden_script_is_not_original_prose(tmp_path):
    e=source(tmp_path,'<script>production</script><p>Scoping report</p>','.html')
    hits,issues,_=s.scan_original(e,s.DEFAULT_KEYWORDS)
    assert not issues and [h['keyword'] for h in hits]==['Scoping']


def settings():return dict(keywords=s.DEFAULT_KEYWORDS,keyword_version='v1',decision_id='test-decision')
def decisions():return {'decisions':[dict(decision_id='test-decision',rule=s.RULE,decided_by='USER_EXPLICIT_APPROVAL',approval_evidence=s.EVIDENCE)]}
def row(pid='p',stage=''):return {'專案ID':pid,'專案名稱':'Test project','開發階段':stage,'開發階段代碼':'','開發階段類別':''}


@pytest.mark.parametrize('has_mre,code',[(True,'A2'),(False,'A1')])
def test_only_code_and_category_and_manifest(tmp_path,monkeypatch,has_mre,code):
    import au_ree_v2.stage_rules
    e=source(tmp_path,'Early exploration only.')
    monkeypatch.setattr(s,'original_inventory',lambda *a:({'p':[e]},{}))
    monkeypatch.setattr(au_ree_v2.stage_rules,'selected_mre',lambda *a:(has_mre,{}))
    fills,review,extra=s.collect_stage_absence([row()],[],decisions(),tmp_path,tmp_path,settings())
    assert not review and len(fills)==2
    assert [f['column'] for f in fills]==['開發階段代碼','開發階段類別'] and fills[0]['value']==code
    scope=json.loads(fills[0]['provenance']['scope'])
    assert scope['original_sha256s']==[e['sha256']] and scope['latest_original_date']=='2026-01-02'
    assert scope['qualifier']==s.RULE


@pytest.mark.parametrize('cause',['keyword','unknown-date','unknown-mre','no-originals'])
def test_fail_closed_before_inference(tmp_path,monkeypatch,cause):
    import au_ree_v2.stage_rules
    e=source(tmp_path,'Scoping planned' if cause=='keyword' else 'Early exploration',dates=[] if cause=='unknown-date' else None)
    monkeypatch.setattr(s,'original_inventory',lambda *a:({'p':[] if cause=='no-originals' else [e]},{}))
    monkeypatch.setattr(au_ree_v2.stage_rules,'selected_mre',lambda *a:(None if cause=='unknown-mre' else False,{}))
    fills,review,_=s.collect_stage_absence([row()],[],decisions(),tmp_path,tmp_path,settings())
    assert not fills and len(review)==1


def test_existing_native_or_codes_are_not_touched(tmp_path,monkeypatch):
    rows=[row(stage='Exploration'),dict(row(),開發階段代碼='A1'),dict(row(),開發階段類別='探勘')]
    monkeypatch.setattr(s,'original_inventory',lambda a,b,ids: ({}, {}) if not ids else (_ for _ in ()).throw(AssertionError()))
    fills,review,extra=s.collect_stage_absence(rows,[],decisions(),tmp_path,tmp_path,settings())
    assert not fills and not review and extra['scanned_projects']==0


def test_approval_required(tmp_path):
    with pytest.raises(ValueError,match='APPROVAL'):
        s.collect_stage_absence([],[],{'decisions':[]},tmp_path,tmp_path,settings())

def test_inventory_includes_unselected_census_and_discovery_sources(tmp_path):
    import sqlite3
    from au_ree_v2.reviewed_discovery import project_id
    repo=tmp_path/'repo';census=tmp_path/'census';(repo/'config').mkdir(parents=True)
    dbp=census/'work/phase22/verified-performance-v3/isolated-round-0/after/canonical.sqlite';dbp.parent.mkdir(parents=True)
    db=sqlite3.connect(dbp)
    db.executescript('''CREATE TABLE sources(sha TEXT,path TEXT,kind TEXT,publication_date TEXT,metadata TEXT,url TEXT);
    CREATE TABLE records(entity_id TEXT,source_sha TEXT);
    CREATE TABLE observations(entity_id TEXT,source_sha TEXT);
    CREATE TABLE study_cases(project_id TEXT,source_sha TEXT);
    CREATE TABLE review_queue(entity_id TEXT,source_sha TEXT);
    CREATE TABLE relations(parent_id TEXT,child_id TEXT,source_sha TEXT,relation TEXT);
    CREATE TABLE census_screen_index(selection_entity_id TEXT,parent_candidate_id TEXT,source_sha TEXT);''')
    e=source(census,'Early exploration');db.execute('INSERT INTO sources VALUES (?,?,?,?,?,?)',(e['sha256'],'source.txt','txt','2025-01-01','{}','https://example.test/source'))
    db.execute('INSERT INTO observations VALUES (?,?)',('child',e['sha256']))
    db.execute('INSERT INTO relations VALUES (?,?,?,?)',('p','child',e['sha256'],'DOCUMENT_SUPPORTED_SAME_PROJECT'));db.commit();db.close()
    configs={'asx_local_asset_roots.json':{'roots':{'test':str(census)}},
             'asx_source_reviews.json':{'reviews':[]},
             'asx_discovery_reviews.json':{'candidates':[{'candidate_key':'d','decision':'ADMIT_PROJECT','sources':[{'asset_set':'test','path':'source.txt','sha256':e['sha256'],'kind':'txt'}],'identity':{'source_index':0,'publication_date':'2025-01-01'}}]},
             'asx_project_identity_reviews.json':{'sources':{},'codes':[],'merges':[]},
             'asx_location_reviews.json':{'sources':{},'reviews':[]}}
    for name,value in configs.items():(repo/'config'/name).write_text(json.dumps(value),encoding='utf8')
    inv,issues=s.original_inventory(repo,census,{'p',project_id('d')})
    assert not issues
    assert inv['p'][0]['sha256']==e['sha256']
    assert 'census:observations' in inv['p'][0]['associations']
    assert inv[project_id('d')][0]['sha256']==e['sha256']

def test_semantic_source_kind_still_scans_json_bytes(tmp_path):
    e=source(tmp_path,'{"activity":"Construction"}','.json');e['kind']='arcgis_census'
    hits,issues,pages=s.scan_original(e,s.DEFAULT_KEYWORDS)
    assert not issues and pages==1 and hits[0]['keyword']=='construction'

def test_image_dominated_page_blocks_despite_native_letterhead(tmp_path):
    p=tmp_path/'image.pdf';doc=fitz.open();page=doc.new_page()
    page.insert_textbox(fitz.Rect(40,20,550,100),'Company project information with an otherwise complete native letterhead and footer. '*3)
    pix=fitz.Pixmap(fitz.csRGB,fitz.IRect(0,0,20,20),False);pix.clear_with(255)
    page.insert_image(fitz.Rect(20,120,575,800),stream=pix.tobytes('png'));doc.save(p);doc.close()
    hits,issues,pages=s.scan_original(dict(path=str(p),sha256=s.sha256(p),kind='pdf'),s.DEFAULT_KEYWORDS)
    assert not hits and pages==1
    assert any(x['reason']=='IMAGE_DOMINATED_PAGE_REQUIRES_OCR_REVIEW' for x in issues)

def test_line_wrapped_keywords_are_not_missed(tmp_path):
    e=source(tmp_path,'Earlier construc-\ntion and produc-\ntion were discussed.')
    hits,issues,_=s.scan_original(e,s.DEFAULT_KEYWORDS)
    assert not issues
    assert {h['keyword'] for h in hits}=={'construction','production'}

def visual_case(tmp_path):
    p=tmp_path/'visual.pdf';d=fitz.open();d.new_page();d.save(p);d.close()
    e=dict(path=str(p),sha256=s.sha256(p),kind='pdf')
    with fitz.open(p) as d: digest=s.hashlib.sha256(d[0].get_pixmap(dpi=150,colorspace=fitz.csRGB,alpha=False,annots=True).tobytes('png')).hexdigest()
    record=dict(source_sha256=e['sha256'],physical_page=1,render_sha256=digest,coverage='FULL_PAGE',outcome='NO_STAGE_KEYWORDS_VISIBLE',hits=[],visible_findings='Blank physical page, fully inspected')
    proof=dict(version='round3-stage-visual-v1',keyword_version='test',keywords=s.DEFAULT_KEYWORDS,renderer=dict(engine='PyMuPDF',version=fitz.VersionBind,dpi=150,colorspace='RGB',alpha=False,annots=True),reviews=[record])
    return e,proof

def test_visual_review_resolves_only_image_gaps(tmp_path):
    e,p=visual_case(tmp_path);scan=s.scan_original(e,s.DEFAULT_KEYWORDS)
    scan[1].append(dict(reason='ARCHIVED_ORIGINAL_DATE_UNKNOWN',physical_page=1))
    hits,issues,pages,proof=s.verify_visual_reviews(e,scan,p,s.DEFAULT_KEYWORDS,'test')
    assert not hits and pages==1 and len(proof)==1
    assert [i['reason'] for i in issues]==['ARCHIVED_ORIGINAL_DATE_UNKNOWN']

@pytest.mark.parametrize('mutation', ['sha','keyword','coverage','duplicate','outcome','recipe'])
def test_visual_review_tamper_rejected(tmp_path,mutation):
    e,p=visual_case(tmp_path)
    if mutation=='sha':p['reviews'][0]['render_sha256']='0'*64
    elif mutation=='keyword':p['keywords']=[]
    elif mutation=='coverage':p['reviews'][0]['coverage']='PARTIAL'
    elif mutation=='duplicate':p['reviews']*=2
    elif mutation=='outcome':p['reviews'][0]['outcome']='UNKNOWN'
    else:p['renderer']['dpi']=144
    with pytest.raises(ValueError):s.verify_visual_reviews(e,s.scan_original(e,s.DEFAULT_KEYWORDS),p,s.DEFAULT_KEYWORDS,'test')

def test_visual_hit_prevents_absence(tmp_path):
    e,p=visual_case(tmp_path);p['reviews'][0].update(outcome='STAGE_KEYWORDS_VISIBLE',hits=[dict(keyword='DFS',text='DFS figure')])
    hits,issues,_,_=s.verify_visual_reviews(e,s.scan_original(e,s.DEFAULT_KEYWORDS),p,s.DEFAULT_KEYWORDS,'test')
    assert not issues and hits[0]['keyword']=='DFS'
