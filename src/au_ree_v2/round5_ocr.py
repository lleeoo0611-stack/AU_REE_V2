"""Offline, hash-bound task-2 OCR execution and conservative stage inference.

execute_ocr_pages(repo, entries, pages, executable, traineddata) performs TWO real
Tesseract runs per rendered page, failing closed on any byte difference. `pages`
is the de-duplicated (source_sha256, physical_page) set from queued_pages(extra).
collect_task2 consumes that immutable manifest and TSVs; it never launches OCR,
opens a network connection, or changes native stage values. Run execute once in
each independent source rebuild when testing actual OCR reproducibility.
"""
from __future__ import annotations

import copy
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
from collections import Counter, defaultdict

from . import round3_stage as legacy
from . import round4_stage as previous

RULE = 'STAGE_OFFLINE_OCR_REVIEW'
VERSION = 'round5-ocr-v1'
PAGE_BLOCKERS = {'IMAGE_DOMINATED_PAGE_REQUIRES_OCR_REVIEW', 'PAGE_WITHOUT_EXTRACTABLE_TEXT'}


def settings_for(repo):
    settings = legacy.read_json(Path(repo) / 'config/round5_ocr.json')
    expected = {'version': VERSION, 'page_mean_confidence': 70,
                'valid_word_confidence': 60, 'valid_word_min_length': 2,
                'valid_word_count': 20, 'hit_line_confidence': 80}
    if any(settings.get(k) != v for k, v in expected.items()):
        raise ValueError('OCR_UNAPPROVED_THRESHOLDS')
    if settings['renderer'] != dict(engine='PyMuPDF', dpi=300, colorspace='GRAY', alpha=False, annots=True):
        raise ValueError('OCR_UNAPPROVED_RENDER_RECIPE')
    if settings['ocr'] != dict(engine='Tesseract', language='eng', oem=1, psm=3, format='tsv', OMP_THREAD_LIMIT='1'):
        raise ValueError('OCR_UNAPPROVED_ENGINE_RECIPE')
    return settings


def digest(data):
    return hashlib.sha256(data).hexdigest()


def parse_tsv(data, settings):
    """Average all recognized nonempty words, not just accepted high-confidence ones."""
    words = []
    for row in csv.DictReader(io.StringIO(data.decode('utf-8-sig')), delimiter='\t'):
        if row.get('level') != '5' or not row.get('text', '').strip():
            continue
        try:
            confidence = float(row['conf'])
        except (ValueError, KeyError):
            raise ValueError('OCR_INVALID_WORD_CONFIDENCE')
        if not 0 <= confidence <= 100:
            raise ValueError('OCR_INVALID_WORD_CONFIDENCE')
        words.append(dict(text=row['text'].strip(), confidence=confidence,
                          line=tuple(row[k] for k in ('page_num', 'block_num', 'par_num', 'line_num'))))
    valid = [w for w in words if w['confidence'] >= settings['valid_word_confidence']
             and len(w['text']) >= settings['valid_word_min_length']]
    mean = sum(w['confidence'] for w in words) / len(words) if words else None
    if not words or mean < settings['page_mean_confidence']:
        status = 'OCR_LOW_CONFIDENCE'
    elif len(valid) >= settings['valid_word_count']:
        status = 'OCR_READABLE'
    else:
        status = 'OCR_NO_TEXT_CONTENT'
    line_groups = defaultdict(list)
    for word in words:
        line_groups[word['line']].append(word)
    lines = [dict(text=' '.join(w['text'] for w in group),
                  confidence=sum(w['confidence'] for w in group)/len(group), line=list(key))
             for key, group in line_groups.items()]
    return dict(status=status, mean_word_confidence=mean, word_count=len(words),
                valid_word_count=len(valid), lines=lines)


def extract_hits(quality, keywords, physical_page):
    """Reconstruct complete cross-line sentences, retaining exact keyword-line confidence.

    TSV line layout is not a paragraph model. Only an actual preceding ALLCAPS
    line can supply heading attribution; no preceding paragraph is invented.
    Line-end hyphenation is joined with a character-to-line map so confidence is
    still attached to the physical OCR line containing the matched keyword.
    """
    lines = quality['lines']
    text_parts, owners, headings = [], [], []
    heading = ''
    for index, line in enumerate(lines):
        headings.append(heading)
        text=line['text']
        letters=''.join(c for c in text if c.isalpha())
        if len(letters)>=2 and letters.isupper(): heading=text
        dehyphenate=(index+1<len(lines) and len(text)>1 and text[-1] in '-‐‑'
                     and text[-2].isalnum() and lines[index+1]['text'][:1].isalnum())
        piece=text[:-1] if dehyphenate else text+' '
        text_parts.append(piece); owners.extend([index]*len(piece))
    text=''.join(text_parts)
    # Same sentence separator as the native complete-hit scanner. Ambiguous
    # OCR punctuation is not promoted to a paragraph-heading inference.
    bounds=[0]+[m.end() for m in re.finditer(r'(?<=[.!?])\s+',text)]+[len(text)]
    hits=[]
    for keyword in keywords:
        pattern=r'\b'+re.escape(keyword)+(r'\b' if keyword.upper() in ('PFS','DFS','BFS','FID') else '')
        for match in re.finditer(pattern,text,re.I):
            line_index=owners[match.start()]
            line=lines[line_index]
            begin=max(b for b in bounds if b<=match.start())
            end=min(b for b in bounds if b>match.start())
            involved={owners[i] for i in range(match.start(),match.end())}
            confidence=min(lines[i]['confidence'] for i in involved)
            hits.append(dict(physical_page=physical_page,keyword=keyword,sentence=text[begin:end].strip(),
                             paragraph_text=text[begin:end].strip(),paragraph_heading=headings[line_index],ocr=True,
                             text_source='OCR',ocr_confidence=confidence,ocr_line=line['line'],
                             ocr_keyword_lines=[lines[i]['line'] for i in sorted(involved)],match_start=match.start()))
    return sorted(hits,key=lambda h:(h['match_start'],h['keyword']))

def queued_pages(task1_extra):
    return sorted({(b['source_sha256'], b['physical_page'])
                   for m in task1_extra['stage_search_manifests']
                   for b in m.get('blockers', [])
                   if b.get('reason') in PAGE_BLOCKERS and type(b.get('physical_page')) is int})


def require_matching_runs(first, second):
    if first != second:
        raise ValueError('OCR_NONDETERMINISTIC_OUTPUT:' + digest(first) + ':' + digest(second))
    return digest(first)


def execute_ocr_pages(repo, entries, pages, executable, traineddata, settings=None):
    """All files local. Caller supplies installed binary/model; never installs anything.

    entries maps source SHA to inventory entry. A mismatch aborts before manifest
    publication, with both run hashes in the error. Existing hash artifacts are
    verified before reuse; both independent OCR runs are always actually executed.
    """
    import fitz
    repo = Path(repo)
    settings = settings or settings_for(repo)
    executable, traineddata = Path(executable).resolve(), Path(traineddata).resolve()
    if not executable.is_file() or not traineddata.is_file() or traineddata.name != 'eng.traineddata':
        raise ValueError('OFFLINE_OCR_ENGINE_OR_ENG_MODEL_MISSING')
    env = dict(os.environ, OMP_THREAD_LIMIT='1')
    version = subprocess.run([str(executable), '--version'], env=env, capture_output=True, check=True).stdout.decode('utf-8', errors='replace').strip()
    output = repo / settings['output_dir']; output.mkdir(parents=True, exist_ok=True)
    records = []
    for source_sha, page_number in sorted(set(pages)):
        entry = entries[source_sha]
        path = next((Path(p) for p in entry.get('paths', [entry['path']]) if Path(p).is_file()), None)
        if path is None or legacy.sha256(path) != source_sha:
            raise ValueError('OCR_ORIGINAL_SHA_MISMATCH:' + source_sha)
        with fitz.open(path) as pdf:
            if type(page_number) is not int or not 1 <= page_number <= len(pdf):
                raise ValueError('OCR_PHYSICAL_PAGE_INVALID')
            png = pdf[page_number-1].get_pixmap(dpi=300, colorspace=fitz.csGRAY, alpha=False, annots=True).tobytes('png')
        with tempfile.TemporaryDirectory(prefix='round5-offline-ocr-') as temp:
            image = Path(temp) / 'page.png'; image.write_bytes(png)
            command = [str(executable), str(image), 'stdout', '--tessdata-dir', str(traineddata.parent),
                       '-l', 'eng', '--oem', '1', '--psm', '3', 'tsv']
            first = subprocess.run(command, env=env, capture_output=True, check=True).stdout
            second = subprocess.run(command, env=env, capture_output=True, check=True).stdout
        ocr_sha = require_matching_runs(first, second)
        target = output / (ocr_sha + '.tsv')
        if target.exists() and target.read_bytes() != first:
            raise ValueError('OCR_ARCHIVE_HASH_COLLISION')
        target.write_bytes(first)
        quality = parse_tsv(first, settings)
        records.append(dict(source_sha256=source_sha, physical_page=page_number,
                            render_png_sha256=digest(png), ocr_sha256=ocr_sha,
                            independent_run_sha256=[digest(first), digest(second)],
                            ocr_file=target.relative_to(repo).as_posix(),
                            **{k:v for k,v in quality.items() if k != 'lines'}))
    manifest = dict(version=VERSION, keyword_rule=settings['keyword_rule'],
                    engine=dict(name='Tesseract', version=version,
                                executable_sha256=legacy.sha256(executable),
                                eng_traineddata_sha256=legacy.sha256(traineddata)),
                    renderer=dict(settings['renderer'], version=fitz.VersionBind),
                    parameters=settings['ocr'], pages=records, network_requests=0)
    target = repo / settings['manifest_path']; target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True)+'\n', encoding='utf-8')
    return manifest


def remove_page_blockers(blockers, lifted_pages):
    """Whitelist removal makes unknown dates and all other blockers immutable."""
    lifted_pages = set(lifted_pages)
    return [b for b in blockers if not (b.get('reason') in PAGE_BLOCKERS and
            (b.get('source_sha256'), b.get('physical_page')) in lifted_pages)]


def collect_task2(rows, provenance, decisions, repo, census_root, task1_extra, settings=None):
    from .round5_stage import reassess_hit, load_aliases
    from .stage_rules import selected_mre
    import fitz
    repo = Path(repo); settings = settings or settings_for(repo)
    approved = [d for d in decisions['decisions'] if d.get('decision_id') == settings['decision_id']
                and d.get('rule') == RULE and d.get('decided_by') == 'USER_EXPLICIT_APPROVAL']
    if len(approved) != 1:
        raise ValueError('OCR_EXPLICIT_APPROVAL_REQUIRED')
    manifest_path = repo/settings['manifest_path']
    archive = legacy.read_json(manifest_path) if manifest_path.exists() else None
    expected_pages = set(queued_pages(task1_extra))
    records = {}
    if archive is not None:
        if archive.get('version') != VERSION or archive.get('parameters') != settings['ocr'] or archive.get('keyword_rule') != settings['keyword_rule']:
            raise ValueError('OCR_MANIFEST_RECIPE_MISMATCH')
        renderer = archive.get('renderer', {})
        if any(renderer.get(k) != v for k,v in settings['renderer'].items()) or not renderer.get('version'):
            raise ValueError('OCR_MANIFEST_RENDERER_MISMATCH')
        if renderer['version'] != fitz.VersionBind:
            raise ValueError('OCR_RENDERER_VERSION_CHANGED')
        engine = archive.get('engine', {})
        if engine.get('name') != 'Tesseract' or not engine.get('version') or any(not re.fullmatch(r'[0-9a-f]{64}', engine.get(k, '')) for k in ('executable_sha256','eng_traineddata_sha256')):
            raise ValueError('OCR_ENGINE_PROVENANCE_MISSING')
        for record in archive['pages']:
            key = record['source_sha256'], record['physical_page']
            if key in records or key not in expected_pages:
                raise ValueError('OCR_MANIFEST_DUPLICATE_OR_OUT_OF_SCOPE_PAGE')
            records[key] = record
    inventories, _, alias_map = previous.round4_original_inventory(repo,census_root,{r['專案ID'] for r in rows})
    stage_settings = legacy.read_json(repo/'config/round4_stage_hit_rules.json')
    baseline = legacy.read_json(repo/stage_settings['baseline_manifests'])
    shared = previous.canonical_shared_projects(inventories, baseline, alias_map)
    alias_data = load_aliases(repo)
    keywords = legacy.read_json(repo/stage_settings['legacy_settings'])['keywords']
    by_id = {r['專案ID']:r for r in rows}
    fills, reviews, manifests, hit_reviews, page_audit = [], [], [], [], []
    cache = {}
    for original in task1_extra['stage_search_manifests']:
        m = copy.deepcopy(original); pid=m['project_id']; row=by_id[pid]
        if any(row.get(k) for k in ('開發階段','開發階段代碼','開發階段類別')):
            continue
        entries = {e['sha256']:e for e in inventories.get(pid,[])}
        all_hits = list(m.get('hits',[])); lifted=[]
        pages = sorted({(b['source_sha256'],b['physical_page']) for b in m.get('blockers',[])
                        if b.get('reason') in PAGE_BLOCKERS and type(b.get('physical_page')) is int})
        for key in pages:
            record=records.get(key)
            if record is None:
                page_audit.append(dict(project_id=pid,source_sha256=key[0],physical_page=key[1],status='OCR_NOT_EXECUTED'))
                continue
            if key not in cache:
                entry = entries[key[0]]
                source_path = next((Path(p) for p in entry.get('paths', [entry['path']]) if Path(p).is_file()), None)
                if source_path is None or legacy.sha256(source_path) != key[0]:
                    raise ValueError('OCR_ORIGINAL_SHA_MISMATCH')
                with fitz.open(source_path) as pdf:
                    png = pdf[key[1]-1].get_pixmap(dpi=300, colorspace=fitz.csGRAY, alpha=False, annots=True).tobytes('png')
                if digest(png) != record['render_png_sha256']:
                    raise ValueError('OCR_RENDER_PNG_SHA_MISMATCH')
                path = (repo/record['ocr_file']).resolve()
                if not path.is_relative_to((repo/settings['output_dir']).resolve()):
                    raise ValueError('OCR_ARCHIVE_PATH_ESCAPE')
                data=path.read_bytes()
                if digest(data)!=record['ocr_sha256'] or record['independent_run_sha256']!=[digest(data)]*2:
                    raise ValueError('OCR_ARCHIVE_SHA_MISMATCH')
                quality=parse_tsv(data,settings)
                if any(quality[k] != record[k] for k in ('status','mean_word_confidence','word_count','valid_word_count')):
                    raise ValueError('OCR_MANIFEST_QUALITY_MISMATCH')
                cache[key]=(quality,extract_hits(quality,keywords,key[1]))
            quality,hits=cache[key]
            page_audit.append(dict(record,project_id=pid,ocr_hit_count=len(hits)))
            if quality['status']=='OCR_READABLE' or (quality['status']=='OCR_NO_TEXT_CONTENT' and not hits):
                lifted.append(key)
            for hit in hits:
                reviewed=reassess_hit(hit,row,entries[key[0]],shared[key[0]],stage_settings,alias_data)
                reviewed.update(text_source='OCR',ocr_confidence=hit['ocr_confidence'],ocr_sha256=record['ocr_sha256'],
                                ocr_line=hit['ocr_line'],paragraph_heading=hit['paragraph_heading'])
                if hit['ocr_confidence'] < settings['hit_line_confidence'] and reviewed['point3']!='UNCLEAR':
                    raise ValueError('OCR_LOW_CONFIDENCE_HIT_POINT3_NOT_UNCLEAR')
                all_hits.append(reviewed)
        m['blockers']=remove_page_blockers(m.get('blockers',[]),lifted)
        for blocker in m['blockers']:
            record=records.get((blocker.get('source_sha256'),blocker.get('physical_page')))
            if blocker.get('reason') in PAGE_BLOCKERS and record:
                blocker.update(ocr_status=record['status'],ocr_mean_word_confidence=record['mean_word_confidence'],
                               ocr_word_count=record['word_count'],ocr_valid_word_count=record['valid_word_count'],ocr_sha256=record['ocr_sha256'])
        m.update(hits=all_hits,keyword_rule=settings['keyword_rule'],ocr_rule=VERSION,
                 ocr_lifted_pages=[records[k] for k in lifted])
        meaningful=[h for h in all_hits if h['outcome']!='FAIL']
        has_mre,detail=selected_mre(row,provenance)
        if has_mre is None and not any(b['reason']=='SELECTED_MRE_STATE_UNRESOLVED' for b in m['blockers']):
            m['blockers'].append(dict(reason='SELECTED_MRE_STATE_UNRESOLVED',detail=detail))
        dated=[e for e in entries.values() if e['dates'] and previous.source_assessment(e,shared[e['sha256']],stage_settings)[0]=='PASS']
        if not dated and not any(b['reason']=='NO_DATED_PROJECT_SPECIFIC_ORIGINAL_FOR_INFERENCE' for b in m['blockers']):
            m['blockers'].append(dict(reason='NO_DATED_PROJECT_SPECIFIC_ORIGINAL_FOR_INFERENCE'))
        manifests.append(m); hit_reviews.extend(all_hits)
        if meaningful or m['blockers']:
            reviews.append(dict(project_id=pid,project=row['專案名稱'],reason='STAGE_OCR_HIT_OR_UNCLEAR' if meaningful else 'STAGE_SEARCH_INCOMPLETE',
                                hits=meaningful,blockers=m['blockers'],original_sha256s=m['original_sha256s']))
            continue
        source=max(dated,key=lambda e:(max(e['dates']),e['sha256']))
        scope=dict(m,qualifier=legacy.RULE,decision_id=settings['decision_id'],selected_mre=has_mre,
                   interpretation='SOURCE_SET_AS_OF_DATE_INFERENCE_NOT_NATIVE_STAGE_STATEMENT_OR_CURRENT_STATUS')
        new=previous.make_fills(row,'A2' if has_mre else 'A1',legacy.RULE,settings['decision_id'],source,scope,
                               'All originals and hash-bound offline OCR pages; round5-three-point-v2','探勘')
        fills.extend(new)
    unique={ (p['source_sha256'],p['physical_page']):p for p in page_audit }
    bins=Counter()
    for p in unique.values():
        mean=p.get('mean_word_confidence')
        bins['NO_RECOGNIZED_WORDS_OR_NOT_EXECUTED' if mean is None else f'{min(int(mean//10)*10,90):02d}-{int(mean//10)*10+9 if mean < 90 else 100}']+=1
    readme=['## 離線 OCR 與階段推定',
            f'指定頁面 {len(expected_pages)}；實際完成 OCR {len(records)}。未執行的頁面保留原有阻擋，不視為通過。',
            '固定門檻：頁面平均 70、有效字信心度 60、至少 20 個有效字、命中行平均 80。零辨識字一律 LOW_CONFIDENCE。',
            '只採同頁上方最近全大寫行為候選標題；TSV 無粗體資訊，不推測粗體。NO_TEXT_CONTENT 有命中時保守保留頁面阻擋。',
            'OCR 使用本機 Tesseract eng，300 dpi 灰階、OMP_THREAD_LIMIT=1、--oem 1 --psm 3；每頁兩次真實執行須逐位元相同。']
    if archive:
        readme += ['引擎與模型：'+json.dumps(archive['engine'],ensure_ascii=False,sort_keys=True),
                   '渲染器：'+json.dumps(archive['renderer'],ensure_ascii=False,sort_keys=True)]
    readme += ['信心度分布：'+json.dumps(dict(sorted(bins.items())),ensure_ascii=False,sort_keys=True),'### 逐列阻擋與命中']
    for m in manifests:
        relevant=[p for p in page_audit if p['project_id']==m['project_id']]
        remaining=[h for h in m['hits'] if h['outcome']!='FAIL']
        readme.append(f"- {m['project_id']} {m['project']}: 保留阻擋 {len(m['blockers'])}；PASS/UNCLEAR 命中 {len(remaining)}；解除 OCR 頁 {len(m['ocr_lifted_pages'])}")
        for page in relevant:
            if page['status'] not in ('OCR_READABLE','OCR_NO_TEXT_CONTENT'):
                readme.append(f"  - {page['source_sha256']} p.{page['physical_page']}: {page['status']}, 平均 {page.get('mean_word_confidence')}, 字數 {page.get('word_count')}")
        for h in remaining:
            if h.get('text_source')=='OCR':
                readme.append(f"  - OCR {h['source_sha256']} p.{h['physical_page']} {h['keyword']}: {h['outcome']}; {h.get('sentence',h.get('text',''))}")
        for b in m['blockers']:
            if b.get('reason') not in PAGE_BLOCKERS: readme.append('  - '+json.dumps(b,ensure_ascii=False,sort_keys=True))
    return fills,reviews,dict(readme_lines=readme,stage_search_manifests=manifests,hit_reviews=hit_reviews,ocr_page_audit=page_audit,
            ocr_manifest=archive,ocr_classification_counts=dict(sorted(Counter(p['status'] for p in unique.values()).items())),
            ocr_confidence_histogram=dict(sorted(bins.items())),ocr_pages_expected=len(expected_pages),
            ocr_pages_executed=len(records),ocr_projects_unblocked=len({f['project_id'] for f in fills}),network_requests=0)
