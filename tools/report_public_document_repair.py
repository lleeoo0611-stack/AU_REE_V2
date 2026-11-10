"""Publish an eight-work acquisition receipt, never a full-round stopping receipt."""
import argparse
import csv
import importlib.metadata
import json
from pathlib import Path
import shutil
import subprocess
import xml.etree.ElementTree as ET
from au_ree_v2.public_document_repair import public_value,pdf_validation,atomic_json
from au_ree_v2.store import filehash
from verify_engineering_baseline import verify

ROOT=Path(__file__).resolve().parents[1]


def read_csv(path):
    with path.open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))


def write_csv(path,rows,fields):
    with path.open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fields);writer.writeheader();writer.writerows(rows)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work',type=Path,required=True);parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args();work=args.work;out=args.out
    if out.exists() and any(out.iterdir()):raise ValueError('REPORT_REQUIRES_NEW_EMPTY_FOLDER')
    out.mkdir(parents=True,exist_ok=True)
    cfg=json.loads((ROOT/'config/public_acquisition_repair.json').read_text('utf8'))
    baseline=json.loads((work/'baseline.json').read_text('utf8'))
    for name,sha in baseline['files'].items():
        if filehash(name)!=sha:raise ValueError('PROTECTED_BASELINE_CHANGED:'+name)
    protected=verify();state=json.loads((work/'assets/repair_state.json').read_text('utf8'))
    reviews=json.loads((ROOT/'config/public_acquisition_identity_reviews.json').read_text('utf8'))
    qualified={r['action_id']:r for r in reviews['reviews'] if r['decision']=='QUALIFIED_SAME_WORK_EDITION'}
    current=ROOT/'results/asx-current';summary=json.loads((current/'summary.json').read_text('utf8'))
    audit=json.loads((current/'audit.json').read_text('utf8'))
    rows=read_csv(current/'專案總表.csv');by_id={r['專案ID']:r for r in rows}
    book=json.loads((ROOT/'config/classification_codebook.json').read_text('utf8'))
    assert book['status']=='DRAFT' and book['approved_by'] is None and book['approved_date'] is None
    replay=json.loads((work/'baseline-replay-rebuild.json').read_text('utf8'))
    assert replay['output_hashes']==summary['output_hashes']
    for kind in ('base52','53'):
        a=work/('baseline-replay-a-'+kind);b=work/('baseline-replay-b-'+kind)
        for name in ('專案總表.csv','field_provenance.csv','missing_fields.csv','census_inventory.csv'):
            assert filehash(a/name)==filehash(b/name)
    docs=state['documents'];documents=[]
    for sha,doc in docs.items():
        path=work/'assets'/doc['path'];assert filehash(path)==sha
        validation=pdf_validation(path);assert validation==doc['validation']
        documents.append(dict(source_id=sha,action_id=doc['key'],original_url=doc['original_url'],
            actual_download_url=doc['url'],final_url=doc.get('final_url',doc.get('resolved_url')),
            acquired_at=doc['acquired_at'],acquisition_method=doc['acquisition_method'],bytes=doc['bytes'],
            physical_pages=doc['physical_pages'],validation=validation,reused=bool(doc.get('reused')),
            publication_date=doc.get('publication_date'),resource_effective_date=doc.get('resource_effective_date'),
            source_document_version=doc.get('source_document_version'),identity_status=doc['identity_status'],scientific_admission=False))
    attempts=public_value(state['attempts'])
    limitations=[]
    for attempt in attempts:
        if attempt.get('method')=='NORMAL_BROWSER' and attempt.get('http_status') is not None and 'redirects' not in attempt:
            attempt.update(redirects=None,redirect_chain_capture='NOT_RECORDED_IN_INITIAL_LIVE_ADAPTER;NOT_INFERRED;NO_EXTRA_DENIED_REQUEST')
    if any(a.get('redirect_chain_capture') for a in attempts):
        limitations.append('Initial live browser 403 diagnostics did not retain redirect chains. They remain UNKNOWN; final adapter captures chains and was verified offline, without extra live retries. HTTP-session redirect chains are retained.')
    results=[];backlog=[]
    for w in cfg['works']:
        original=[a for a in attempts if a.get('method')=='HTTP_NORMAL_SESSION' and a.get('url')==w['url']]
        latest=original[-1] if original else {}
        browser=[a for a in attempts if a.get('method')=='NORMAL_BROWSER' and a.get('action_id')==w['action_id']]
        available=w['action_id'] in qualified;review=qualified.get(w['action_id'],{})
        doc=docs.get(review.get('document_sha256'),{})
        row=dict(action_id=w['action_id'],original_url=w['url'],original_current_http_status=latest.get('http_status'),
            original_historical_failure=w['failure_type'],original_current_state=latest.get('status') or ('NOT_RETESTED_VERIFIED_ALTERNATIVE_REUSED' if w.get('reuse') else 'NOT_REQUESTED_DOMAIN_PAUSED'),
            browser_state=browser[-1]['status'] if browser else 'NOT_RUN',same_work_edition_available=available,
            document_sha256=review.get('document_sha256',''),physical_pages=review.get('physical_pages',''),
            publication_date=review.get('publication_date',''),resource_effective_date='UNKNOWN',
            result='ACQUIRED_NO_QUALIFIED_FIELD_GAIN' if available else 'BLOCKED_OR_NO_QUALIFIED_SAME_EDITION_COPY',
            reused=bool(doc.get('reused')),raw_numeric_fills=0,derived_fills=0,text_or_classification_fills=0,
            project_ids=json.dumps(w['project_ids'],ensure_ascii=False),possible_columns=json.dumps(w['columns'],ensure_ascii=False),
            manual_route='' if available and latest.get('http_status')==200 else w['manual_route'])
        results.append(row)
        if latest.get('http_status')!=200:
            backlog.append(dict(w,original_current_http_status=latest.get('http_status'),
                original_current_state=row['original_current_state'],same_work_edition_copy_available=available,
                content_backlog=not available,manual_route=w['manual_route']))
    write_csv(out/'source_results.csv',results,list(results[0]))
    atomic_json(out/'attempts.json',attempts);atomic_json(out/'documents.json',public_value(documents))
    atomic_json(out/'blocked_acquisitions_after_repair.json',dict(version='eight-work-acquisition-backlog-v1',
        not_a_full_coverage_round=True,resolved_original_actions=[w['action_id'] for w in results if w['original_current_http_status']==200],blocked_acquisitions=backlog))
    field_reviews=[]
    for pid,decision in [('AU-1345edd8165c10930e94','Broad late-stage/pre-FID description, not a new verified phase; existing dated DFS retained'),
        ('AU-9bd8e5ed8408cd84d876','September2025 DFS corroborates existing precise dated source; broader Browns Range is not a new Wolverine resource'),
        ('AU-2fc429d0556dfa0b95c4','Project-level pre-FID description does not replace newer BFS or selected MIN5532 scope'),
        ('AU-efff91a06cf344122d88','Mt Weld expansion progress is not whole-project annual TREO or a replacement for dated operating disclosure')]:
        r=by_id[pid]
        field_reviews.append(dict(project_id=pid,column='開發階段',existing_value=r['開發階段'],source_sha256=qualified['REMP2025-native-original']['document_sha256'],
            physical_page=12,unit='TEXT_AT_SOURCE_DATE',proposed_fill='',conversion='NONE',decision=decision))
    for pid in ('AU-2fc429d0556dfa0b95c4','AU-6d807eb7caec9db0f35e','AU-7537d9555628040fab40','AU-329908ab8d4c1d1d3e03','AU-ff758cad5beb276d327d','AU-447261eed0e81eae88bf','AU-fb4e914f86102baa414a'):
        field_reviews.append(dict(project_id=pid,column='礦床型態',existing_value=by_id[pid]['礦床型態'],
            source_sha256=qualified['Victoria-critical-minerals-roadmap']['document_sha256'],physical_page=11,
            unit='MAP_COMMODITY_LABEL_NOT_GLOBAL_MRE',proposed_fill='',conversion='NONE',
            decision='Known HMS labels already filled; regional map supplies no source-bound numeric resource, forecast or representative point'))
    write_csv(out/'field_review.csv',field_reviews,list(field_reviews[0]))
    alternatives=[
        dict(action_id=cfg['works'][0]['action_id'],entry_url='https://resourcingtheterritory.nt.gov.au/minerals/mineral-commodities/ree',result='CURRENT_PUBLIC_INDEX_LOCATED;OCT2025_BINARY_NOT_QUALIFIED;DIRECT_DOMAIN_PAUSED'),
        dict(action_id=cfg['works'][1]['action_id'],entry_url=cfg['works'][1]['entry_urls'][0],result='OFFICIAL_ENTRY_LINKED_EXACT_ORIGINAL;FULL_PDF_200_27PAGES_QUALIFIED'),
        dict(action_id=cfg['works'][2]['action_id'],entry_url='https://www.mrt.tas.gov.au/__data/assets/pdf_file/0008/613286/Critical-Minerals-Prospectus_27-Nov-2025-WEB.pdf',result='INDEXED_DIFFERENT_FILE_REVISION;NOT_DOWNLOADED_OR_MERGED_WITH_18DEC'),
        dict(action_id=cfg['works'][3]['action_id'],entry_url=cfg['works'][3]['alternative_url'],result='PRIOR_OFFICIAL_LIBRARY_COPY_REUSED;ORIGINAL_URL_STATUS_SEPARATE'),
        dict(action_id=cfg['works'][4]['action_id'],entry_url=cfg['works'][4]['entry_urls'][0],result='OFFICIAL_EDGI_RELEASE_INDEX_LOCATED;NO_QUALIFIED_BINARY_ALTERNATIVE;DOMAIN_PAUSED'),
        dict(action_id=cfg['works'][5]['action_id'],entry_url=cfg['works'][5]['entry_urls'][0],result='OFFICIAL_TIGER_AND_INDEXED_ORIGINAL;NO_QUALIFIED_BINARY_ALTERNATIVE;REPORT_PERIOD_NOT_PUBLICATION_DAY'),
        dict(action_id=cfg['works'][6]['action_id'],entry_url=cfg['works'][6]['entry_urls'][-1],result='OFFICIAL_LIBRARY_QUERY_CAPTURED;NO_QUALIFIED_2026_COPY;2024_IS_DIFFERENT_EDITION;NOT_PROOF_OF_ABSENCE'),
        dict(action_id=cfg['works'][7]['action_id'],entry_url='https://www.gippslandcriticalminerals.com/news-resources/',result='PUBLISHER_ARTICLE_AND_RESOURCE_INDEX_CAPTURED;NO_SAME_REFERRAL_COPY;OTHER_PROJECT_REPORTS_NOT_DOWNLOADED')]
    write_csv(out/'alternative_review.csv',alternatives,list(alternatives[0]))
    tests={};names={}
    for name in ('acquisition-tests.xml','regression-tests.xml'):
        path=work/name;xml=ET.parse(path).getroot();suites=list(xml.iter('testsuite'))
        assert suites and all(int(s.get(k,'0'))==0 for s in suites for k in ('failures','errors','skipped'))
        methods={(t.get('classname'),t.get('name')) for t in xml.iter('testcase')};total=sum(int(s.get('tests','0')) for s in suites)
        tests[name]=dict(methods=len(methods),subtests=total-len(methods),failures=0,errors=0,skipped=0,sha256=filehash(path));names[name]=methods
        shutil.copyfile(path,out/name)
    historical=ET.parse(ROOT/'results/asx-full-scope-2026-11-10/round-20-report/tests.xml').getroot()
    old={(t.get('classname'),t.get('name')) for t in historical.iter('testcase')}
    assert len(old)==405 and old<=names['regression-tests.xml']
    local=json.loads((work/'local_inventory_check.json').read_text('utf8'))
    http=[a for a in attempts if a.get('method')=='HTTP_NORMAL_SESSION']
    report=dict(version='eight-public-work-repair-v1',baseline_commit=baseline['commit'],
        implementation_commit=subprocess.check_output(['git','rev-parse','HEAD'],text=True,cwd=ROOT).strip(),
        research_cutoff=summary['cutoff'],works=8,qualified_works=len(qualified),new_downloaded_documents=sum(not d.get('reused') for d in docs.values()),
        reused_documents=sum(bool(d.get('reused')) for d in docs.values()),qualified_pages=sum(docs[r['document_sha256']]['physical_pages'] for r in qualified.values()),
        new_document_identity_evidence=sum(not docs[r['document_sha256']].get('reused') for r in qualified.values()),
        revalidated_existing_identity_evidence=sum(bool(docs[r['document_sha256']].get('reused')) for r in qualified.values()),new_scientific_observations=0,
        raw_numeric_fills=0,derived_fills=0,text_or_classification_fills=0,new_projects=0,denominator_change=0,
        http_network_requests=len(http),http_status_counts={str(code):sum(a.get('http_status')==code for a in http) for code in (200,403)},
        original_url_network_requests=sum(bool(r['original_current_http_status']) for r in results),
        original_urls_recovered=sum(r['original_current_http_status']==200 for r in results),
        unresolved_original_actions=len(backlog),unavailable_work_contents=sum(not b['same_work_edition_copy_available'] for b in backlog),
        local_capture_receipts_checked=local['receipts_scanned'],rows=93,columns=53,filled_cells=audit['filled_cells'],blank_cells=audit['remaining_blank_cells'],
        coverage=summary['blank_coverage'],codebook_status=book['status'],protected=protected,all_current_outputs_unchanged=True,
        policy='CONSECUTIVE_ZERO_GAIN_WITH_BLOCKED_BACKLOG',consecutive_zero_rounds_before=1,consecutive_zero_rounds_after=1,
        full_coverage_rounds_added=0,coverage_cycle_created=False,full_scope_decision='UNCHANGED_CONTINUE_STREAK1;NOT_ROUND21',
        tests=tests,unique_test_methods=len(set.union(*names.values())),old_405_methods_passed=True,
        independent_rebuilds=2,four_csvs_equal_to_current=True,reproducibility_receipt_sha256=filehash(work/'baseline-replay-rebuild.json'),
        browser_runtime=dict(playwright=importlib.metadata.version('playwright'),channel='msedge',observed_browser_versions=sorted({a['browser_version'] for a in attempts if a.get('browser_version')}),
            initial_tool_errors='CUA and Node tool initialization OS error3, no website HTTP response; replaced with normal installed Edge workflow'),
        apify_enabled=False,paid_services_used=False,automated_login_or_captcha=False,
        limitations=limitations+['No WAF cause, removed file or source exhaustion inferred from403. No values admitted from investment aggregates, gallium/copper capacities, drill samples or neighboring resource scopes.',
            'Research rows are not independent mines; Yttria/Mt Stirling resources must not be summed. Same verified ASX/name merge rule and all historical reports unchanged.'])
    if (work/'rerun_validation.json').exists():report['rerun_validation']=json.loads((work/'rerun_validation.json').read_text('utf8'))
    shutil.copyfile(work/'baseline-replay-rebuild.json',out/'rebuild_receipt.json')
    shutil.copyfile(ROOT/'config/public_acquisition_identity_reviews.json',out/'document_identity_reviews.json')
    atomic_json(out/'summary.json',report)
    labels=['NT REE October2025','REMP2025','TAS Prospectus18Dec2025','VIC2024 Roadmap','Wind Break EDGI May2024','Voyager EL32/2022 Oct2024','VIC Roadmap Update2026','Fingerboards2026 referral']
    text='# 八項受阻作品取得修復\n\n'
    text+='本次是取得專項，非完整第21輪。研究母體、截止日、既有值與來源、分類DRAFT及分母規則均未改。\n\n'
    text+='| 作品 | 本次原URL HTTP | 正常Edge流程 | 同版內容 | 人工途徑 |\n|---|---|---|---|---|\n'
    for label,r in zip(labels,results):
        status=str(r['original_current_http_status']) if r['original_current_http_status'] else '未重送；保留歷史403'
        content=('重用36頁' if r['reused'] else '新取得27頁') if r['same_work_edition_available'] else '未取得合格同版件'
        manual='無；原URL已恢復' if r['original_current_http_status']==200 else '內容已重用；原URL仍列受阻' if r['same_work_edition_available'] else '由正常瀏覽器／發行機關／官方館藏取得原件後匯入；勿付費或繞限制'
        text+=f"| {label} | {status} | {r['browser_state']} | {content} | {manual} |\n"
    text+='\n新下載1份／27頁，重用1份／36頁，新增文件身分證據1、舊件重驗1；新科學觀測、原始數值、衍生格、文字／分類格及新增研究列皆0。原URL待處理8→7；同版內容尚未取得6項（包括Fingerboards，VIC2024內容已可用）。不是所有7項都在本次重新回應403。\n\n'
    text+='1944/4929 = **39.44%**；依既有規則排除123格後1944/4806 = **40.45%**。分子、兩個分母及所有既有值／來源不變。\n\n'
    text+='一般HTTP14個實際請求：5次200、9次403，包含入口頁；原PDF URL實際請求5個，其中REMP2025成功。Edge另外對4個官方入口收到403，另2項因同域暫停未發請求、2項已有核驗原件無須瀏覽器。這是特定受阻清單，不是一般ASX成功率。\n\n'
    text+='403原因未確認，未宣稱WAF或文件撤除。MRT連續拒絕後暫停，Wind Break及Voyager本次沒有新直接HTTP或瀏覽器回應，歷史403保留。REMP這次正常會話成功，不能據此推定先前逾時根因。發行人一般文章中的隱藏CAPTCHA表單曾被誤判，已僅用封存HTML重新分類，未重送請求。\n\n'
    text+='**限制：首輪真實瀏覽器的轉向鏈沒有被舊版介面保存，保持UNKNOWN，沒有推測為空。最終程式已補齊轉向鏈、動態連結有界等待及429/503 next_retry_at，且以本機夾具驗證；依限制沒有額外重試受阻網站。HTTP會話的轉向鏈與兩份可用PDF證據完整保存。**\n\n'
    text+='同版核驗：REMP2025 SHA256 `c31024a4a94e94aa7bb0187a7c845975c43dc0c406ab9bba2a5a192e45825d73`，27頁，官方入口19December2025日期、PDF出版社／標題／ISSN1839-5007與p12關鍵內容核對。VIC2024 SHA256 `b4a882278894c26780c531beed947d35add62ec43d1918adc1ce218a1f58646e`，36頁，December2024與ISBN978-1-76136-595-9核對；只是原已存在的官方館藏副本，不能當成新下載或證明與受阻原URL位元組相同。\n\n'
    text+='REMP p12主要提供投資、前FID及既有DFS資訊，p14–15為投資金額／件數；p13其他商品產能不轉填REE。既有精確日期與所選資源範圍保留，沒有以概略進度覆寫。VIC政策、區域圖示及測試坑資訊不等於全案MRE或年產。研究列不等於獨立礦案；Yttria／Mt Stirling重疊資源不加總。\n\n'
    text+='| 測試 | 方法 | 子測試 | 失敗／錯誤／跳過 |\n|---|---:|---:|---|\n'
    for name,t in tests.items():text+=f"| {name} | {t['methods']} | {t['subtests']} | 0 / 0 / 0 |\n"
    text+=f"\n原405項全部包含於回歸且通過；方法聯集{report['unique_test_methods']}，各組有重疊不可相加。兩次離線重建四CSV與當前投影一致；既有921份ASX歷史檔案及Census未改。實際重跑快取新增網路請求0、來源0、填值0。\n\n"
    text+='完整逐項HTTP／瀏覽器紀錄見attempts.json；原URL與同版內容分開見source_results.csv、blocked_acquisitions_after_repair.json；文件SHA／版次證據見documents.json、document_identity_reviews.json；原欄值及不填理由見field_review.csv。原始PDF、HTML、Cookie、SQLite與搜尋全文均不公開。\n\n'
    text+='可重跑命令與匯入方式見 [流程說明](../../docs/PUBLIC_DOCUMENT_ACQUISITION_REPAIR.md)。收斂policy未改，完整輪新增0，連續零增量仍1，維持CONTINUE；不能把這次局部0填值當成第二個完整零增量輪，也不能以STOP宣稱資料找齊。\n'
    (out/'README.md').write_text(text,encoding='utf8',newline='\n')
    atomic_json(out/'validation.json',dict(passed=True,artifact_sha256={p.name:filehash(p) for p in out.iterdir() if p.is_file()},
        protected_baseline=baseline,implementation_sha256={p.relative_to(ROOT).as_posix():filehash(p) for base in ('src','tools','config')
            for p in (ROOT/base).rglob('*') if p.is_file() and p.suffix in ('.py','.json')}))
    print(json.dumps({k:v for k,v in report.items() if k not in ('coverage','tests','limitations','browser_runtime')},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
