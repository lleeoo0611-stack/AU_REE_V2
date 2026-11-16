# Claims locators：CI T0 通過，提案待研究者審核

**本輪 T1 提案待審，T2 因缺少舊原件受阻：尚未修改 claims.json 或 sources.json。** T4 的寫入後 CI 與恢復格數驗收，等待標記核准及圖層比對完成後才執行。PR #11 保持 Draft，target `feat/same-sha-fallback-20261116`，不 merge。

## T0：以 CI 驗收固定 609 格

T0 以 [CI run 43900956815](https://github.com/lleeoo0611-stack/AU_REE_V2/actions/runs/43900956815) 驗收通過：**609／609 保留，流失 0 格**。驗收提交為 `b690e6b1184d63082e177fa1925d6510d594dfd8`，src 與宣告和 e84c0e0 相同。原始參考清單不重產，與提交 58865e2 的位元組完全一致。

- [ci_609_guard.csv](ci_t0/ci_609_guard.csv)：609 列，含 CI 值、參考值、比較規則及來源。
- [ci_t0_summary.json](ci_t0/ci_t0_summary.json)：run／提交／artifact SHA／工具版本／測試與逐格結果。
- 固定清單檔 SHA256：`02acc91760c8774f7377d12f2a428d1a1d6b6fba6f1620237e267101cdb0ff4e`。原始已發布比較表 SHA256：`a131cf6086242b53f0d6c8e1d5f9e420b540f7b21fe9c4671f2f31370d7eae26`。
- Ubuntu `tesseract-ocr-eng` 語言包版本：`1:4.1.0-2`；`tesseract-ocr` 執行檔套件版本：`5.3.4-1build5`。版本引文見 [安裝紀錄](ci_t0/api-log-evidence.json)。

本機 599 格的落差確認為 OCR 執行檔缺失：原先流失的 10 格在 CI 全部保留，原先受阻的 6 份同 SHA 原件也被 CI 採用，且同 5 案不再出現缺少 OCR 執行檔的 blocker。本機結果僅供診斷，舊資料原樣保留在 baseline-*、baseline_*、t0_* 檔案；[PR #11 原始診斷](https://github.com/lleeoo0611-stack/AU_REE_V2/blob/58865e2/results/claims-locators-2026-11-16/README.md)與 [t0_stop_diagnosis.json](t0_stop_diagnosis.json)可追溯。沒有在 Windows 安裝其他版本的 Tesseract。

## CI 總表與比較分類（固定 2,101 格）

下列是未寫入任何新標記／SHA 的 CI 基準，T3 僅改比較分類。KNOWN_STRUCTURAL_DIFFERENCE 不算 SAME。完整 93×51 格仍逐格保留，不把 ID、參考空白格及原有結構差異加入 2,101 格分母。

|分類|e84c0e0 已發布 CI|本次 CI＋T3 分類|增減|
|---|---:|---:|---:|
|SAME|609|609|+0|
|DIFFERENT|70|28|-42|
|KNOWN_STRUCTURAL_DIFFERENCE|0|42|+42|
|FORMAL_MISSING|1422|1422|+0|

CI 原始比較見 [ci_t0/cell_comparison.csv](ci_t0/cell_comparison.csv)，分類後見 [cell_comparison_classified.csv](cell_comparison_classified.csv)。[分類審計](comparison_classification_audit.json)列出每一格採用的已驗證來源；所有儲存格值維持不變。

## T1：文字層標記提案，未套用

[identity_marker_proposals.csv](identity_marker_proposals.csv)共 26 列（A 22、B 4）；[綁定審計](identity_marker_proposal_bindings.json)含 JSON pointer、頁碼、原件 SHA、文字層方法與逐列雜湊。`group` 欄值為 A／B，`page_text_kind` 為 TEXT_LAYER／NEEDS_OCR。本機只呼叫同一套 extract_page 的文字層，不提供 OCR 模型；需 OCR 的列不提案。

|status|列數|
|---|---:|
|PROPOSED|26|
|NEEDS_OCR|0|
|EXISTING_MARKER_NOT_ON_PAGE|0|
|NO_CANDIDATE|0|
|PAGE_TEXT_EMPTY|0|

每個專案的恢復格數尚未驗收：本輪 0 筆標記寫入。研究者在 CSV 新增 approved 欄、填 Y／N 後，才套用 Y；後續提交訊息須附審核 CSV 原始位元組 SHA256，再以新 CI 同時驗收原 609 格及實際恢復格數。

|project_id|專案|組|頁|提案標記|規則|狀態|
|---|---|---|---:|---|---|---|
|AU-3a0020b6daf659f62138|Euston Mineral Sands Project|A|41|ILUKA RESOURCES LIMITED - ANNUAL REPORT 2022|d|PROPOSED|
|AU-3eaa906d8230334ef698|Mukinbudin REE Project|A|4|DIRECTORS’ REPORT (continued)|d|PROPOSED|
|AU-2ab3e8eb7b5784e64f9b|Duke Rare Earth Project|A|11|Mineral Resources Statement|d|PROPOSED|
|AU-d1394abdef4c8d971c78|Condingup REE Project|A|1|EMU NL|a|PROPOSED|
|AU-cae6c11543b0da5f840d|West Arunta Project — Luni Niobium–REE scope|A|4|WA1 RESOURCES LTD 2026 ANNUAL REPORT 3|d|PROPOSED|
|AU-73549b8a9b1c6faf55eb|Coburn Mineral Sands Project|A|4|Strandline Resources Limited|a|PROPOSED|
|AU-d99cf357d160df73387c|Southern Cross Li-REE Project — GCX|A|52|GCX Metals Limited|a|PROPOSED|
|AU-a9b72e86940271be45a3|Diemals Li–REE Project|A|4|White Cliff Minerals Limited|a|PROPOSED|
|AU-70cc41e3a7106f983f73|Lake Tay REE Project|A|4|White Cliff Minerals Limited|a|PROPOSED|
|AU-b3ae34ac85d16018bd4b|Barballin REE Project|A|4|White Cliff Minerals Limited|a|PROPOSED|
|AU-f81823bd8ba271840345|Munbinia REE Project|A|4|White Cliff Minerals Limited|a|PROPOSED|
|AU-ee34781b030807146e64|Ravensthorpe REE Exploration Project — Young River, Dalyup and Bremer|A|13|RAVENSTHORPE PROJECT|c|PROPOSED|
|AU-b50a5b57669586191c33|Wandagee REE Exploration Project — Consolidated Zinc|A|4|Wandagee Project|c|PROPOSED|
|AU-68da41afe874c3bd66d4|Voyager Rare Earth Project — Tasmania|A|91|- 78 - Lithium Universe Limited Annual Report 2023|d|PROPOSED|
|AU-2af694147ae21c393820|Lake Campion REE Exploration Project — IGO|A|18|16 — IGO ANNUAL REPORT 2022|d|PROPOSED|
|AU-203b4d90e5c23a323610|Harts Range REE–Nb Exploration Project — New Frontier|A|1|New Frontier Minerals Limited|a|PROPOSED|
|AU-447261eed0e81eae88bf|Goschen Central Rare Earths and Mineral Sands Project — ACDC|A|1|ACDC Metals Limited|a|PROPOSED|
|AU-410159af7b79ea498ec2|Cannie Critical Mineral Project — VHM|A|1|VHM Limited|a|PROPOSED|
|AU-c5e94422a89a23f82408|Mt Craig Copper–REE Exploration Project — Taruga|A|5|Taruga Minerals Limited|a|PROPOSED|
|AU-7135b2eb1d3f193da9a6|Gilberton REE Exploration Project — ActivEX|A|8|ActivEX Limited|a|PROPOSED|
|AU-88dfe58aac214c33e576|Aramac Rare Earth Element Project — ActivEX|A|18|ActivEX Limited|a|PROPOSED|
|AU-75fe0f1a81005bd19586|Durack REE–Ti–Zr Exploration Project — historical BPM option|A|1|BPM Minerals Ltd|a|PROPOSED|
|AU-97137ef07af49e3607b2|Charley Creek North Project — historical URO EL33004 exploration|B|1|URO Corporation Pty Ltd|a|PROPOSED|
|AU-70fc8a7de18ad8209c32|Charley Creek North-East Project — historical URO EL33000 exploration|B|1|URO Corporation Pty Ltd|a|PROPOSED|
|AU-430f216ca620b69af5f9|Charley Creek South-East Project — historical URO EL33006 exploration|B|1|URO Corporation Pty Ltd|a|PROPOSED|
|AU-d1e3e2803f3c4287f6db|Charley Creek South Project — historical URO EL33054 and EL33055 exploration|B|1|URO Corporation Pty Ltd|a|PROPOSED|

非 PROPOSED 的詳細原因在綁定審計。NEEDS_OCR 留待後續處理；不以找不到候選或不存在證據替代。既有頁碼、標記、SHA、observations、attributes 均未改動。

## C 組 7 案：保持原狀

[group_C_status.csv](group_C_status.csv)直接引用本次 CI 的取得收據，沒有額外請求這些來源。

|project_id|專案|host|狀態|原因|
|---|---|---|---|---|
|AU-ff758cad5beb276d327d|Wimmera Mineral Sands Project — Iluka WIM100|www.asx.com.au|HOST_STOPPED|HOST_STOPPED:NOT_PDF|
|AU-02d486d425ca0792bdc5|Comet REE Project|www.asx.com.au|HOST_STOPPED|HOST_STOPPED:NOT_PDF|
|AU-9d967ecaac6e02fc76a5|Rankin Dome Rare Earth Project|www.asx.com.au|HOST_STOPPED|HOST_STOPPED:NOT_PDF|
|AU-81b21bdd06796fa2217d|Merredin REE Project|www.asx.com.au|HOST_STOPPED|HOST_STOPPED:NOT_PDF|
|AU-6f0ecda27d291720036d|Nutgrove REE Project|investorpa.com|UNAVAILABLE|ROBOTS_DISALLOWED|
|AU-176852ef1348ac10d154|Nowie Rare Earths and Mineral Sands Project — VHM|www.asx.com.au|HOST_STOPPED|HOST_STOPPED:NOT_PDF|
|AU-3651cf8448b9227adcf5|Mount Ridley|www.asx.com.au|HOST_STOPPED|HOST_STOPPED:NOT_PDF|

## T2：舊快照缺失，未完成逐要素比對

**兩個舊 SHA 都不在目前 repo 的 298 份已提交 JSON／GeoJSON 快照，也未在 manifest 正式歷史中找到登記。** [舊快照查核](old_layer_snapshot_search.json)列出搜尋範圍及逐檔 SHA；未讀實驗分支或未登記的本機原件資料夾。

已依既有限速、robots 與停止規則取得兩個既有 fixed_query 的新版，原件只放在忽略的 work 快取。[摘要](sha_changed_diff_summary.json)記錄完整新舊 SHA、新版要素數、HTTP 嘗試與已登記範圍。缺少舊版位元組，不能判定哪些欄位或本專案要素被修改；[sha_changed_diff.csv](sha_changed_diff.csv)因此只有欄名、沒有資料列，**不代表零差異**。目前不得據此核准更新 SHA。

|來源|舊 SHA（前 12 碼）|新 SHA（前 12 碼）|舊／新要素|變動要素|幾何變動要素|新 SHA 與 CI 觀測一致|
|---|---|---|---:|---:|---:|---|
|reviewed_source_31a205168b6ae647|31a205168b6a|c64e13a6f568|未取得／13|未比對|未比對|False|
|reviewed_source_8a0240c46bbfaa5b|8a0240c46bbf|d96ee2e5f587|未取得／415|未比對|未比對|True|

**reviewed_source_31a205168b6ae647**：CI 目前實際使用舊 SHA 的座標格 0；舊要素缺失，影響評估為未知。已登記礦權對新版的命中只列在摘要，不等於完成新舊比對或取得正式座標。

此來源同一既有查詢在本次抓取與 CI 的實際 SHA 不同，已保留兩個雜湊；尚不能判定是內容或回應格式變動，不提出可直接寫入的替代 SHA。

**reviewed_source_8a0240c46bbfaa5b**：CI 目前實際使用舊 SHA 的座標格 0；舊要素缺失，影響評估為未知。已登記礦權對新版的命中只列在摘要，不等於完成新舊比對或取得正式座標。

倫敦證交所、markitdigital、NT STRIKE 三筆依指定保持只列報告，不執行本輪 T2 下載。以下 HTTP 是本次 CI 收據實際值；即使與提示詞預期不同，也不變更排除範圍。

|來源 key|host|HTTP|CI 狀態|
|---|---|---|---|
|wudinna_desorption20260916|www.londonstockexchange.com|200|SOURCE_SHA_CHANGED|
|browns_wolverine_mre20250116|cdn-api.markitdigital.com|200|SOURCE_SHA_CHANGED|
|reviewed_source_013de14181fdf89d|strike.nt.gov.au|200|SOURCE_SHA_CHANGED|

## T3：其餘差異與缺漏

[remaining_differences.csv](remaining_differences.csv)共 28 格，列出兩邊值、來源 SHA／URL、頁碼及 locator。參考側有 20 格未在前次已發布對照表記錄頁碼，明列 NOT_RECORDED_IN_PUBLISHED_REFERENCE，未讀實驗分支或由值反推頁碼。

本次 CI 全部 93×51 格的缺漏原因（與 robots-fix-rerun 相同範圍）：

|reason|格數|
|---|---:|
|HOST_STOPPED_4XX|199|
|NOT_APPLICABLE_NO_MRE|1230|
|NOT_APPLICABLE_STAGE|15|
|NO_SOURCE_VALUE|192|
|RULE_INPUT_MISSING|905|
|SOURCE_NOT_ACQUIRED|1407|
|SOURCE_SHA_CHANGED|8|

完整覆蓋率與層級統計見 [ci_t0/rebuild/coverage.json](ci_t0/rebuild/coverage.json)，逐格缺漏理由見 [missing_fields.csv](ci_t0/rebuild/missing_fields.csv)。根目錄舊的 missing_reason_counts.csv 屬 Windows 診斷；本次驗收統計另存 ci_t0/missing_reason_counts.csv。

## 驗證與下一個停止點

- src 新增 0 行、刪除 0 行；claims.json、sources.json、evidence_policy、原件快照、manifest 與凍結結果均未改動。沒有新增 src 模組或 config 檔案，沒有下載原件進入提交。
- 本次來源 CI：408 Python 測試，失敗／錯誤／跳過均 0；R 檢查通過。版本、來源與雜湊證據在 ci_t0/。
- [研究 CI 43900956953](https://github.com/lleeoo0611-stack/AU_REE_V2/actions/runs/43900956953) 成功，408 測試與 R 通過，Phase 20、21、22 均 MATCHED。Phase 21／22 第二次獨立重建本輪依工作流程範圍被跳過，不記為 PASS；見 [research-evidence.json](ci_t0/research-evidence.json)。
- 本輪報告更新使用 [skip ci]，程式與宣告仍等同已驗證的 b690e6b；待核准資料寫入後才推不帶跳過標記的提交，執行新的 CI 驗收。
- **停止等待研究者**：請在 T1 提案 CSV 新增 approved=Y／N；另請指出 repo 中舊 SHA 原件的位置，或提供 SHA 完全一致的兩份舊原件供核對。T2 尚不能提出更新 SHA 的審核結論。未取得核准不寫入宣告，不執行 T4，不 merge。
