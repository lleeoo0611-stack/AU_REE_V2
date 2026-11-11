"""Validated round-three publication with preserved historical notes and rollback."""
import json
import csv
import html
import re
from urllib.parse import unquote
import shutil
from pathlib import Path
from au_ree_v2.round3_publication import (check_task_receipts, publish_transaction,
    tree_hashes, file_sha, json_read)
from au_ree_v2.round3_schema import unpack
from au_ree_v2.security import sensitive_reference


def verify_public_tree(folder):
    """Inspect readable artifacts AND recursively decoded historical payloads.

    This never redacts scientific/historical artifacts: any finding blocks release.
    Error messages contain location/type only, never the credential or URL.
    """
    folder=Path(folder); files=0; payloads=0
    def inspect(raw, label, depth=0):
        nonlocal payloads
        if depth>16 or len(raw)>64*1024*1024:
            raise ValueError('ROUND3_PUBLICATION_ARCHIVE_LIMIT:'+label)
        text=raw.decode('utf-8-sig',errors='backslashreplace')
        decoded_text=text
        for _ in range(8):decoded_text=html.unescape(unquote(decoded_text))
        if sensitive_reference(text) or re.search(r'[?&]__cf_chl_(?:f_)?tk=',decoded_text,re.I):
            raise ValueError('ROUND3_PUBLICATION_CREDENTIAL_REFERENCE:'+label)
        try: value=json.loads(text)
        except (ValueError,TypeError):return
        def walk(node):
            nonlocal payloads
            if isinstance(node,dict):
                if node.get('encoding')=='gzip-base64':
                    decoded=unpack(node);payloads+=1
                    inspect(decoded,label+'/decoded-archive',depth+1)
                else:
                    for child in node.values():walk(child)
            elif isinstance(node,list):
                for child in node:walk(child)
        walk(value)
    for path in sorted(folder.rglob('*')):
        if path.is_symlink() or (hasattr(path,'is_junction') and path.is_junction()):
            raise ValueError('ROUND3_PUBLICATION_LINK_NOT_ALLOWED')
        if path.is_file():
            inspect(path.read_bytes(),path.relative_to(folder).as_posix());files+=1
    return dict(credential_query_references=0,files_scanned=files,
                decoded_payloads_scanned=payloads,method='RECURSIVE_DECODED_ARCHIVE_SCAN_V1')


def publish_round3(repo,date,work,out,summary_out,expected_current_hashes,schema,tests_pass,verify_nt):
    repo,work,out,summary_out=map(Path,(repo,work,out,summary_out))
    current=repo/'results/asx-current'
    if expected_current_hashes is None:
        raise ValueError('ROUND3_PUBLICATION_RUNNER_START_BASELINE_REQUIRED')
    if tree_hashes(current)!=expected_current_hashes:
        raise ValueError('ROUND3_PUBLICATION_CURRENT_CHANGED_DURING_REBUILD')
    gates=check_task_receipts(repo,date,tests_pass,verify_nt)
    core=json_read(out/'projection/summary.json')
    presentation_a=work/'presentation-a';presentation_b=work/'presentation-b'
    schema.present(out/'projection',presentation_a,repo)
    schema.present(out/'projection',presentation_b,repo)
    # All presentation files, including embedded historical archives, not just six.
    if tree_hashes(presentation_a)!=tree_hashes(presentation_b):
        raise ValueError('ROUND3_PUBLICATION_PRESENTATION_REPLAY_MISMATCH')
    presentation_hashes=tree_hashes(presentation_a)
    with (presentation_a/'專案總表.csv').open(encoding='utf-8-sig',newline='') as handle:
        reader=csv.DictReader(handle);display_columns=list(reader.fieldnames or []);display_rows=list(reader)
    if len(display_columns)!=51 or not display_rows:raise ValueError('ROUND3_PRESENTATION_COVERAGE_SHAPE')
    display_filled=sum(row.get(column,'')!='' for row in display_rows for column in display_columns)
    display_total=len(display_rows)*len(display_columns)
    display_coverage=dict(filled=display_filled,denominator=display_total,coverage=display_filled/display_total,
        projects=len(display_rows),columns=len(display_columns),basis='DISPLAYED_TABLE_WITH_PRESERVED_TOTAL_NOTES')
    staged=current.with_name('asx-current.round3-staged-'+date)
    backup=current.with_name('asx-current.pre-round3-'+date)
    if staged.exists() or backup.exists():
        raise ValueError('ROUND3_PUBLICATION_FRESH_SIBLING_REQUIRED')
    shutil.copytree(presentation_a,staged)
    # Keep immutable source support for the unchanged preexisting notes.
    preserved={}
    for name in ('source_consistency.csv','retired_consistency_trace.json'):
        if (current/name).is_file():
            shutil.copyfile(current/name,staged/name);preserved[name]=file_sha(staged/name)
    records=gates['tasks'];total=sum(r['new_cells'] for r in records)
    cov={k:core[k] for k in ('original_53_columns','all_retained_columns','tiered_coverage')}
    status=dict(published=True,status='ROUND3_RESEARCHER_APPROVED_PUBLISHED',
                new_cells=total,accepted_tasks=list(range(6)),
                existing_conclusion='INCOMPLETE/CONTINUE_UNCHANGED',
                note_policy='PRESERVE_PREEXISTING_VALUES_AND_PROVENANCE_NO_REFRESH',
                backup=backup.relative_to(repo).as_posix(),
                swap_semantics='TWO_SAME_FILESYSTEM_RENAMES_WITH_ROLLBACK_NOT_ATOMIC_EXCHANGE')
    validation=dict(version='round3-publication-validation-v1',
        census_sha256=gates['census_sha256'],accepted_tasks=[dict(task=r['task'],tests=r['tests'],
        independent_full_rebuilds=r['independent_full_rebuilds'],output_hashes=r['bitwise_identical_files']) for r in records],
        presentation_output_hashes=presentation_hashes,publication_audit=schema.audit(staged),
        preserved_historical_note_support=preserved,nt_datum_controls=gates['nt_datum_controls'],
        coverage_basis='CANONICAL_EVIDENCE_VIEW_WITH_ELEMENT_CONSISTENCY_COLUMN',presentation_table_coverage=display_coverage,**cov)
    def write(path,obj):path.write_text(json.dumps(obj,ensure_ascii=False,sort_keys=True,indent=2)+'\n',encoding='utf-8')
    write(staged/'publication_status.json',status);write(staged/'validation.json',validation)
    lines=['# 第三輪已驗證總表','',f'本輪新增 {total} 格。保留 93 個專案、51 欄；先前已填值、總說明與其來源不改。','']
    lines.append('以下三種必要覆蓋率採標準證據表口徑（含元素數據一致性檢查欄），不是把展示總表的總說明欄混入計算。')
    for label,key in [('原53欄歷史口徑','original_53_columns'),('保留51欄全表','all_retained_columns')]:
        c=cov[key];lines.append(f'{label}：{c["filled"]}／{c["denominator"]}（{c["coverage"]:.2%}）。')
    c=cov['tiered_coverage']['combined'];lines.append(f'兩層口徑：{c["filled"]}／{c["denominator"]}（{c["coverage"]:.2%}）。')
    lines.append(f'展示總表另計：{display_filled}／{display_total}（{display_coverage["coverage"]:.2%}），一致性欄換為保留的總說明，因此可與標準證據表已填格數不同。')
    lines+=['','任務0至5各自完成兩次獨立完整離線重建、逐位元比對與全套測試。發布前重新計算 NT datum 控制點，原始封存檔與嵌入歷史檔均通過憑證網址檢查。',
        '無 MRE 排除僅為分母慣例，不代表不存在資源。INCOMPLETE／CONTINUE 結論不變。',
        'WA 的唯一候選／單一 site 判定限於已核准的 REE／稀土／獨居石／磷釔礦篩選封存快照，不宣稱完整涵蓋 MINEDEX 全商品礦點或所有現況。',
        '階段推定原可處理39列（最多78格）；33列命中進階階段或退回相關關鍵字，只有6列符合，新增12格。33列中有31列另有圖像／日期等未解問題，兩者重疊，不能相加；不為湊預期格數放寬條件。',
        '總說明為既有內容，不因新增證據改寫。source_consistency.csv 與 retired_consistency_trace.json 僅為既有說明的歷史支持，未重新估算。',
        'validation.json 保存本次驗收與來源雜湊；各任務的新增格、變更格、待審清單及中文說明在相應 round3 結果目錄。',
        '發布採同一檔案系統兩次重新命名，並非單一步驟原子交換；失敗會回復原 current，原版本保留在 publication_status.json 指定的備份。','']
    (staged/'README.md').write_text('\n'.join(lines),encoding='utf-8')
    review=['# 第三輪待審與限制','', '未讀原件、日期未知、進階階段詞或礦權退回資訊均保留待審；不把未命中搜尋當成現況保證。',
            '資料不足的欄位保持空白，不為提高覆蓋率猜填。部分礦權退回不等於整個專案退出。',
            '階段推定39個候選列中，33列命中關鍵字、6列符合而新增12格；33列中31列另有未解的圖像／日期問題（重疊計數，不可相加）。','']
    for r in records:
        review.append(f'- 任務 {r["task"]}：新增 {r["new_cells"]} 格；詳見 ../round3-{r["task"]}-{date}/review_queue.csv。')
    review+=['','Mt Stirling／Yttria 若共享礦床估計，不可將資源直接加總。NT座標的datum限制、官方來源存取結果與精確配對紀錄見任務3。','']
    (staged/'REVIEW.md').write_text('\n'.join(review),encoding='utf-8')
    def validate(folder):
        folder=Path(folder)
        if any(file_sha(folder/name)!=sha for name,sha in presentation_hashes.items()):
            raise ValueError('ROUND3_PUBLICATION_PRESENTATION_CHANGED')
        if any(file_sha(folder/name)!=sha for name,sha in preserved.items()):
            raise ValueError('ROUND3_PUBLICATION_HISTORICAL_SUPPORT_CHANGED')
        if json_read(folder/'validation.json')!=validation or json_read(folder/'publication_status.json')!=status:
            raise ValueError('ROUND3_PUBLICATION_METADATA_CHANGED')
        audit=schema.audit(folder)
        if audit!=validation['publication_audit']:
            raise ValueError('ROUND3_PUBLICATION_AUDIT_MISMATCH')
        return dict(audit=audit,security=verify_public_tree(folder))
    # Scan all newly produced task artifacts, including decoded archives.
    for n in range(6):verify_public_tree(repo/f'results/round3-{n}-{date}')
    government=repo/f'results/round3-government-{date}'
    if government.exists():verify_public_tree(government)
    result=publish_transaction(current,staged,backup,expected_current_hashes,validate)
    write(summary_out/'publication_status.json',status)
    write(summary_out/'publication_receipt.json',result)
    summary_lines=['# 第三輪彙總','',f'研究者核准任務0至5完成，累計新增 {total} 格。各任務新增格數：']
    summary_lines.extend(f'- 任務 {record["task"]}：+{record["new_cells"]} 格。' for record in records)
    summary_lines += ['', '三種必要覆蓋率與兩層各自分子／分母詳見 coverage_comparison.json，採標準證據表口徑；展示表另計的填格數見 ../asx-current/validation.json 的 presentation_table_coverage。',
        '階段推定39個候選列中，33列命中關鍵字、6列符合而新增12格；33列中31列另有圖像／日期等未解問題，屬重疊計數，不可相加。',
        'VIC成功取得官方資料但沒有通過全部比對條件的新座標；TAS存取限制後立即停止。這不是沒有專案或資料的證明。',
        '已發布總表位於 ../asx-current/；既有填值、來源與總說明保留。發布與備份驗證詳見 publication_receipt.json。INCOMPLETE／CONTINUE 不變。','']
    (summary_out/'README.md').write_text('\n'.join(summary_lines),encoding='utf-8')
    return result
