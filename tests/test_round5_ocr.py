import csv
import io
import json
from pathlib import Path
from unittest.mock import patch

import pytest
from au_ree_v2 import round5_ocr as o
from au_ree_v2 import round5_stage as s

ROOT=Path(__file__).parents[1]

@pytest.fixture
def cfg():
    return o.settings_for(ROOT)


def tsv(words):
    out=io.StringIO(newline='')
    writer=csv.writer(out,delimiter='\t',lineterminator='\n')
    writer.writerow(['level','page_num','block_num','par_num','line_num','word_num','left','top','width','height','conf','text'])
    for i,(text,confidence,line) in enumerate(words):
        writer.writerow([5,1,1,1,line,i+1,0,0,1,1,confidence,text])
    return out.getvalue().encode()

@pytest.mark.parametrize('count,conf,status',[(20,70,'OCR_READABLE'),(19,70,'OCR_NO_TEXT_CONTENT'),(30,69.99,'OCR_LOW_CONFIDENCE'),(0,99,'OCR_LOW_CONFIDENCE')])
def test_page_thresholds(cfg,count,conf,status):
    assert o.parse_tsv(tsv([('word',conf,1)]*count),cfg)['status']==status


def test_valid_word_threshold_does_not_bias_mean(cfg):
    quality=o.parse_tsv(tsv([('word',99,1)]*19+[('a',99,1),('low',59,1)]),cfg)
    assert quality['valid_word_count']==19
    assert quality['word_count']==21
    assert quality['mean_word_confidence']==pytest.approx((99*20+59)/21)
    assert quality['status']=='OCR_NO_TEXT_CONTENT'


def test_recognized_zero_confidence_words_are_not_discarded(cfg):
    assert o.parse_tsv(tsv([('word',0,1)]*20),cfg)['status']=='OCR_LOW_CONFIDENCE'


def test_identical_runs_hash_and_difference_fails():
    assert o.require_matching_runs(b'a',b'a')==o.digest(b'a')
    with pytest.raises(ValueError,match='OCR_NONDETERMINISTIC_OUTPUT'):
        o.require_matching_runs(b'a',b'b')


def test_unknown_dates_never_lifted():
    pages=[('sha',2)]
    blockers=[dict(reason=r,source_sha256='sha',physical_page=2) for r in [
        'ARCHIVED_ORIGINAL_DATE_UNKNOWN',*sorted(o.PAGE_BLOCKERS),'SOURCE_TYPE_UNCLEAR']]
    remaining=o.remove_page_blockers(blockers,pages)
    assert [b['reason'] for b in remaining]==['ARCHIVED_ORIGINAL_DATE_UNKNOWN','SOURCE_TYPE_UNCLEAR']


def test_only_queued_page_gap_scope():
    manifest={'stage_search_manifests':[{'blockers':[
        dict(reason='ARCHIVED_ORIGINAL_DATE_UNKNOWN',source_sha256='bad',physical_page=1),
        dict(reason='IMAGE_DOMINATED_PAGE_REQUIRES_OCR_REVIEW',source_sha256='yes',physical_page=2),
        dict(reason='PAGE_WITHOUT_EXTRACTABLE_TEXT',source_sha256='yes',physical_page=2)]}]}
    assert o.queued_pages(manifest)==[('yes',2)]


def test_heading_nearest_preceding_allcaps_same_page(cfg):
    quality=o.parse_tsv(tsv([('OLD',90,1),('heading',90,2),('NEW',90,3),('production',90,4)]),cfg)
    hit=o.extract_hits(quality,['production'],4)[0]
    assert hit['paragraph_heading']=='NEW'
    assert hit['ocr_confidence']==90
    new_page=o.parse_tsv(tsv([('production',90,1)]),cfg)
    assert o.extract_hits(new_page,['production'],5)[0]['paragraph_heading']==''


def test_keyword_line_confidence_uses_all_words(cfg):
    quality=o.parse_tsv(tsv([('production',90,1),('completed',60,1)]),cfg)
    assert o.extract_hits(quality,['production'],1)[0]['ocr_confidence']==75


@pytest.mark.parametrize('confidence,point3',[(79.99,'UNCLEAR'),(80,'PASS')])
def test_ocr_line_80_rule(confidence,point3):
    settings=json.loads((ROOT/'config/round4_stage_hit_rules.json').read_text('utf8'))
    aliases={'projects':[{'project_id':'p','aliases':[{'alias':'Alpha','source':'NAME_SUFFIX_REMOVAL'}]}]}
    row={'專案ID':'p','專案名稱':'Alpha Project'}
    entry={'sha256':'sha','url':'https://example.test/project'}
    hit={'sentence':'Alpha Project completed the Scoping Study.','keyword':'Scoping','physical_page':1,'ocr':True,'ocr_confidence':confidence}
    assert s.reassess_hit(hit,row,entry,{'p'},settings,aliases)['point3']==point3


def test_ocr_fail_precedes_unclear():
    assert s.priority('PASS','FAIL','UNCLEAR')=='FAIL'


def test_execute_runs_twice_and_records_render(tmp_path,cfg):
    import fitz
    original=tmp_path/'source.pdf'
    doc=fitz.open(); page=doc.new_page();page.insert_text((50,50),'ALPHA PROJECT');doc.save(original);doc.close()
    sha=o.legacy.sha256(original)
    executable=tmp_path/'tesseract.exe';executable.write_bytes(b'fixture-engine')
    model=tmp_path/'eng.traineddata';model.write_bytes(b'fixture-model')
    output=tsv([('word',95,1)]*20)
    calls=[]
    class Result:
        def __init__(self,data): self.stdout=data
    def fake_run(command,**kwargs):
        calls.append((command,kwargs))
        return Result(b'tesseract TEST FIXTURE' if '--version' in command else output)
    with patch.object(o.subprocess,'run',side_effect=fake_run):
        manifest=o.execute_ocr_pages(tmp_path,{sha:dict(path=str(original))},[(sha,1)],executable,model,cfg)
    assert len(calls)==3
    assert calls[1][0]==calls[2][0]
    assert calls[1][1]['env']['OMP_THREAD_LIMIT']=='1'
    record=manifest['pages'][0]
    assert record['independent_run_sha256']==[o.digest(output)]*2
    assert record['render_png_sha256']
    assert record['status']=='OCR_READABLE'
    assert (tmp_path/record['ocr_file']).read_bytes()==output
    assert manifest['engine']['eng_traineddata_sha256']==o.digest(b'fixture-model')


def test_unapproved_threshold_rejected(tmp_path,cfg):
    (tmp_path/'config').mkdir()
    cfg['page_mean_confidence']=69
    (tmp_path/'config/round5_ocr.json').write_text(json.dumps(cfg))
    with pytest.raises(ValueError,match='OCR_UNAPPROVED_THRESHOLDS'):
        o.settings_for(tmp_path)


def test_complete_sentence_preserves_prior_line_project_and_future(cfg):
    quality=o.parse_tsv(tsv([('Alpha Project will',95,1),('commence production.',90,2)]),cfg)
    hit=o.extract_hits(quality,['production'],1)[0]
    assert hit['sentence']=='Alpha Project will commence production.'
    assert hit['ocr_confidence']==90

def test_line_hyphenated_keyword_searched(cfg):
    quality=o.parse_tsv(tsv([('Alpha Project completed Feasi-',95,1),('bility Study.',75,2)]),cfg)
    hit=o.extract_hits(quality,['Feasibility'],1)[0]
    assert hit['sentence']=='Alpha Project completed Feasibility Study.'
    assert hit['ocr_confidence']==75
    assert len(hit['ocr_keyword_lines'])==2

def test_sentence_does_not_import_previous_sentence_project(cfg):
    quality=o.parse_tsv(tsv([('Alpha Project is mentioned.',95,1),('Other project completed production.',95,2)]),cfg)
    hit=o.extract_hits(quality,['production'],1)[0]
    assert hit['sentence']=='Other project completed production.'
