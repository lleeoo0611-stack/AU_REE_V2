# robots 404／410 修正與重跑

本次修正機器人規則檔的 HTTP 狀態處理。PR #10 保持 Draft，不轉 Ready、不 merge。前次 93f3aac 的報告與資料保留在[上層目錄](../README.md)，本目錄另存修正後的乾淨建置結果。

## 修正與政策

只對請求路徑 /robots.txt 的 404／410 視為沒有規則，繼續取得主要文件並快取空規則。原始 HTTP 狀態仍保留在請求紀錄，不改寫為 HTTP 200。其他安全規則未刪減。

|robots 結果|本次行為|
|---|---|
|200 且有規則|遵守 Allow／Disallow|
|404／410|沒有規則，允許繼續取得文件|
|401／403／429 及其他 4xx|維持停止該 host|
|5xx／連線失敗|全部禁止，維持原重試與網路失效判準|
|主要文件回任何 4xx|仍停止該 host，不適用 robots 例外|

[RFC 9309 §2.3.1.3](https://www.rfc-editor.org/rfc/rfc9309.html#section-2.3.1.3)容許 robots 回 4xx 時繼續取得資源；[§2.3.1.4](https://www.rfc-editor.org/rfc/rfc9309.html#section-2.3.1.4)要求伺服器或連線錯誤時全部禁止。只放行 404／410、保留 401／403 停止是本專案的保守選擇，沒有宣稱規範要求放行所有 4xx。

www 首次 NOT_PDF 後仍完全停止；不解析條款頁、不提交表單、不建立同意狀態。精確 SHA、每 host 至少 3 秒、redirect allowlist、每來源 8 個候選、每次建置 400 個 fallback 請求及搜尋關閉均維持。

## 實測覆蓋率

|版本|SAME|DIFFERENT|FORMAL_MISSING|
|---|---|---|---|
|原整合版 12f45f4|661|53|1387|
|修正前 93f3aac|377|78|1646|
|robots 修正重跑|609|70|1422|

固定對照 2,101 個非 ID 非空參考格。相對修正前新增 SAME 232 格、流失 SAME 0 格；狀態淨變化 `{"DIFFERENT": -8, "FORMAL_MISSING": -224, "SAME": 232}`。總表維持 93×51、4,743 格，本次填入 787 格。比較資料僅讀前次已發布的正式 CSV，沒有讀實驗線或外部本機原件。

相對原整合版仍少 52 個 SAME：原有 SAME 流失 94 格、T0 補回 42 格。94 格中有 87 格變成缺漏（51 格 HOST_STOPPED_4XX、27 格 SOURCE_NOT_ACQUIRED、8 格 RULE_INPUT_MISSING、1 格 NO_SOURCE_VALUE），另 7 格為不同值。保留的 401／403 停止及其他取得／驗證限制仍會影響覆蓋率，未放寬其條件湊回原數字。

以下數字是來源登記中的 PDF 筆數，不等同文件去重後數量。

|主機|PDF 登記筆數|修正前狀態|修正後狀態|
|---|---|---|---|
|announcements.asx.com.au|52|{"HOST_STOPPED": 52}|{"COMMITTED_SNAPSHOT_SAME_SHA": 6, "FETCHED_SHA_VERIFIED": 46}|
|wcsecure.weblink.com.au|10|{"HOST_STOPPED": 9, "SNAPSHOT_FALLBACK_SAME_SHA": 1}|{"CACHED_UNBOUND_SOURCE_NOT_ADOPTED": 1, "COMMITTED_SNAPSHOT_SAME_SHA": 1, "FETCHED_SHA_VERIFIED": 7, "UNAVAILABLE": 1}|
|api.investi.com.au|3|{"HOST_STOPPED": 2, "SNAPSHOT_FALLBACK_SAME_SHA": 1}|{"CACHED_UNBOUND_SOURCE_NOT_ADOPTED": 1, "FETCHED_SHA_VERIFIED": 2}|
|hermes-cdn.investorhub.com|9|{"HOST_STOPPED": 8, "SNAPSHOT_FALLBACK_SAME_SHA": 1}|{"HOST_STOPPED": 8, "SNAPSHOT_FALLBACK_SAME_SHA": 1}|

hermes 的 401／403 沒有放行。新舊差異也可能包含來源當下的可用性變化，逐筆結果以 [source_host_comparison.csv](source_host_comparison.csv) 為準，不把所有變動一概當成 robots 修正的因果證明。

announcements 的 52 筆都可採用，46 筆是本次下載且 SHA 一致，6 筆是設定中既有登記的同 SHA 快照，沒有宣稱 52 筆全部重新下載。weblink 的另一筆文件 `norwest_arunta_20230222` 本體回 404，仍為 UNAVAILABLE；Donald 與 Yangibana 的兩筆未綁定來源僅快取、沒有採用。這些均未新增人工原件或替代宣告。

T0 基準原本 45 個非空格，目前恢復 SAME 42 格，含開發商 23 格。47 格的狀態為 `{"DIFFERENT": 2, "FORMAL_MISSING": 1, "FORMAL_ONLY": 2, "SAME": 42}`；兩個原參考空白格不計為非空恢復。逐格見 [t0_baseline_47_cells.csv](t0_baseline_47_cells.csv)。

剩餘 3 個非空格仍是 Greater Brothers 的「有來源文件」及來源名稱／URL；Jupiter 原件所在 hermes 仍受 403 停止政策約束。另 2 個階段欄已有有效值，對空白參考列為 FORMAL_ONLY，不算 T0 失敗或缺漏。

37 筆舊 NOT_PDF 來源皆有結果，同 SHA 命中 0 筆；整體 fallback 觸發 64 筆，PDF 候選嘗試 0 次，請求配額 19／400，建議修補 0 筆。未新增公司公告頁，也未引入人工下載。

|37 筆停止原因|數量|
|---|---|
|CAPTCHA_OR_LOGIN|3|
|HTTP Error 429: Too Many Requests|4|
|INDEX_PREVIOUSLY_UNAVAILABLE|1|
|NO_ELIGIBLE_INDEX_PDF_LINK|6|
|NO_REGISTERED_IR_INDEX_OR_CANDIDATE|23|

www 實際記錄 2 次 HTTP 嘗試；首次 NOT_PDF 後的 www 請求為 0。probe 重用沒有重複計數。

## 驗證與交付

來源程式提交 `8e71d6a15051fa217383370be9696abbde26bf84`。本次 src 相對 93f3aac 只新增 2 行；相對 12f45f4 增加刪除合計 185 行；相對 070df10 累計 2,000／2,005 行，仍通過原本 2,000 行的較嚴格檢查。研究者已核准 2,005 行上限，本次未使用增加的 5 行額度，也沒有刪減其他安全規則、新增 src 模組、config 檔或原件 PDF。

先用新增測試重現錯誤，再套用修正。本機 22 項同 SHA／robots 安全測試通過；乾淨 CI Python 測試 408 項、失敗 0、錯誤 0、略過 0，R 分析腳本通過。Phase 20–22 凍結重建結果見 [CI 驗證](ci-validation.json)。

- [乾淨來源建置 43867773093](https://github.com/lleeoo0611-stack/AU_REE_V2/actions/runs/43867773093)；[完整研究 CI 43867773309](https://github.com/lleeoo0611-stack/AU_REE_V2/actions/runs/43867773309)。
- [新總表](rebuild/專案總表.csv)、[來源追溯](rebuild/field_provenance.csv)、[缺格理由](rebuild/missing_fields.csv)。
- [對原整合版逐格比較](cell_comparison.csv)、[對 93f3aac 的變動](cell_increment_vs_93f3aac.csv)、[統計](comparison-summary.json)、[逐主機來源比較](source_host_comparison.csv)。
- [37 筆結果](prior_not_pdf_37_outcomes.csv)、[fallback 收據](fallback_report.csv)、[建議修補](proposed_sources_patch.json)、[擷取收據](acquisition_report.csv)、[ASX probe](asx_probe.csv)。
- [來源與設定雜湊驗證](ci-build-origin.json)、[行數與凍結資料檢查](source-budget.json)、[測試 XML](test-xml/)、[R 測試記錄](r-tests.log)。

測試 XML 的附件檔名已縮短，以支援 Windows 的路徑長度；內容位元組與 SHA 未改變。原始 CI 檔名與 SHA 對照見 [test-xml/index.json](test-xml/index.json)。
