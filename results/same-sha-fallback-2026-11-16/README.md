# 同 SHA 原件替代流程

從 `12f45f4` 建立 `feat/same-sha-fallback-20261116`，PR 目標為 `feat/phase16-technical-model`；只開 PR，不 merge。

> 本頁數字來自已驗證的乾淨 CI 建置。程式與逐筆報告已交付；47 格全部恢復的數字驗收尚未滿足，PR 保持 Draft，未 merge。

## T0：子表上層驗證

`wa_dmpe_ree_2026_table`、`austrade_2026_ree_catalogue` 原先以子表自身的內容 SHA 尋找上層 PDF，導致上層成功也排除子表。新增明確的 `parent_source_sha256`，子表自身的 SHA、原檔與轉錄內容保持不變。測試涵蓋兩種子表：上層 SHA 正確才採用，錯誤仍排除。

### 47 格基準的核對

逐格比對前次交付的兩份比較表，Phase22 為 SAME、前次新建置不是 SAME 的共有 47 格。其中：

- 38 格舊來源為上述兩份子表：26 格 WA 轉錄表、12 格 Austrade catalogue。
- 7 格舊來源為 Jupiter 原件 `ea4d6aead116a7db9547f251dac5a06c8f237595b4293669a1edab78a289367a`，不是這兩份轉錄表。
- 2 格原本參考值為空白，前次正式表新增 A1／探勘，因此屬 FORMAL_ONLY，不是掉失的非空值。

45 個非空缺漏中包括開發商 23 格。新的實測會逐格列出這 47 格的結果；不把兩個新增值或其他來源問題誤算為 T0 救回。

## T1：來源中繼資料

前次 37 筆 www NOT_PDF 來源均補入 `issuer`、`title_tokens`、`alternate_urls`、`alternate_policy=SAME_SHA_ONLY`。只讀正式 claims／registry 與前次已驗證收據，不讀實驗分支或未登記的外部本機原件。

- 公司名可由既有宣告唯一取得：33／37。
- ASX 代碼可由既有宣告唯一取得：35／37。
- 可沿用既有身分標記的 title_tokens：32／37。
- 已確認首頁直接連至公告列表的來源：14／37，對應 10 家公司。
- 既有收據已確認、又在核准網域內的同 SHA 替代網址：0／37。

無法唯一確認的欄位保持空白。逐筆候選、缺項與確認依據見 [source_metadata.csv](source_metadata.csv)。未把公司名稱、代碼或公告標題憑空補入。

官方首頁與公告頁確認：

|代碼|首頁|首頁直接連結的公告頁|
|---|---|---|
|VTM|https://victorymetalsaustralia.com/|https://investors.victorymetalsaustralia.com/announcements|
|ARU|https://www.arultd.com/|https://www.arultd.com/investor/asx-announcements/asx-announcements-2026/|
|DEV|https://www.devexresources.com.au/|https://www.devexresources.com.au/investors/asx-announcements/|
|ILU|https://www.iluka.com/|https://www.iluka.com/investors-media/asx-releases/|
|AR3|https://ar3.com.au/|https://ar3.com.au/announcements|
|HAS|https://hastingstechmetals.com/|https://hastingstechmetals.com/announcements|
|MEK|https://meekametals.com.au/|https://meekametals.com.au/asx-announcements/|
|REE|https://rarex.com.au/|https://rarex.com.au/announcements|
|VHM|https://www.vhmltd.com.au/|https://www.vhmltd.com.au/investors/asx-announcements/|
|MQR|https://www.marqueeresources.com.au/|https://www.marqueeresources.com.au/asx-announcements|

Astron、Lynas 首頁確認時逾時，Critica 首頁無法存取，未新增其公告列表。其餘公司沒有在現有登記中確認到符合本輪條件的首頁直接連結，維持未登記，不以搜尋引擎 HTML 探索。

## T2：安全與範圍

流程先嘗試已宣告的 alternate_urls，再讀單一核准公司公告頁，僅挑標記或日期 ±7 天相符的 PDF 候選。每來源最多 8 個候選，整次建置最多 400 個 fallback 請求配額；robots、redirect、retry 均消耗配額。未發送的受阻候選也可能占用配額，實際 HTTP 次數不會超過此保守上限。

- 所有 strict 新請求與 redirect 先驗證 robots。robots 無法確認時不取用該路徑；disallow 記錄 ROBOTS_DISALLOWED。4xx、登入頁、CAPTCHA 共享同一個 host 停止狀態。
- robots 取得也沿用誠實 User-Agent 與每主機至少 3 秒間隔；僅 timeout／5xx 重試一次。
- www 第一次 NOT_PDF 後停止該 host，後續連 robots 也不再請求。最多一次起始 robots 檢查及一次被 robots 允許的主要 PDF 請求；若 robots 先禁止，PDF 請求為零。
- 不提交表單、不處理同意頁、不建立已同意狀態。主要 www HTML 不交給連結解析器；登入／條款索引也不解析。
- 不跟隨離開核准第三方或該發行者明列網域的 redirect；不採用敏感查詢網址。
- 唯有 SHA256 完全一致且為 PDF 的副本才採用，狀態 ALTERNATE_SAME_SHA。其他位元組不存成原件；異 SHA 候選進 review_queue，原因 ALTERNATE_SHA_MISMATCH。
- 建置僅輸出 proposed_sources_patch.json，不改 sources.json；更新 alternate_urls 仍需研究者審核後 commit。

## T3：外部搜尋暫緩

`search_api.enabled=false`、provider=null。保留關閉的設定介面；本輪未實作 provider，若誤開會在請求前以 SEARCH_API_PROVIDER_NOT_IMPLEMENTED 明確停止。剩餘 src 預算不足以安全實作 provider、憑證與測試，依任務允許將此項留為待辦，未連外搜尋引擎或 API。

## T4：乾淨建置實測

來源程式提交 `62ddd1391ee77d140baa0d6089b90eecf02d4085`；[建置 run 43862415397](https://github.com/lleeoo0611-stack/AU_REE_V2/actions/runs/43862415397)。壓縮檔 SHA256、程式內容 SHA、設定與宣告皆已逐項核對，見 [ci-build-origin.json](ci-build-origin.json)。網路狀態為 NETWORK_VALID，未降低 5% 失效門檻。

|項目|前次|本次|增減|
|---|---|---|---|
|SAME|661|377|-284|
|DIFFERENT|53|78|25|
|FORMAL_MISSING|1387|1646|259|

固定對照 2,101 個非 ID 非空參考格；新總表為 93 × 51，共 4,743 格，填入 550 格。新增 SAME 的來源分類：`{"T0_CHILD_TRANSCRIPTION": 42}`；原有 SAME 流失 326 格。此為實際新舊輸出的比較，不把新增與流失互相掩蓋。

47 格基準中，原本非空的 45 格恢復 SAME：42 格；47 格目前狀態：`{"DIFFERENT": 2, "FORMAL_MISSING": 1, "SAME": 44}`。指定子表原先對應的 38 格全部恢復，另有 Greater Brothers 的名稱／地區 4 格改由 WA 子表恢復。兩個原本參考空白的階段欄目前也空白，列為 SAME，但不計入 T0 救回的非空值。逐格見 [t0_baseline_47_cells.csv](t0_baseline_47_cells.csv)。

尚未滿足的 3 格皆屬 Greater Brothers：有來源文件仍缺值，資料來源名稱／URL 改為實際可驗證的 WA 子表，與參考的 Jupiter 原件不同。Jupiter 所在 hermes 主機本輪遇 403 後停止，不能宣告已取得該原件，也不能為了數字驗收改回未驗證的來源名稱／URL。故不宣告「47 格全部恢復」。

37 筆受阻來源均列出結果，同 SHA 命中 0 筆。整體觸發 fallback 129 筆、PDF 候選嘗試 0 次、保守請求配額使用 18／400、異 SHA 0 筆。建議修補 0 筆，沒有自動修改 sources.json。

|37 筆來源停止原因|筆數|
|---|---|
|CAPTCHA_OR_LOGIN|2|
|HOST_STOPPED:404|1|
|HTTP Error 429: Too Many Requests|4|
|INDEX_PREVIOUSLY_UNAVAILABLE|1|
|NO_ELIGIBLE_INDEX_PDF_LINK|6|
|NO_REGISTERED_IR_INDEX_OR_CANDIDATE|23|

www 實際 HTTP 嘗試 2 次：起始 robots 與第一份主要網址；首次 NOT_PDF 之後的 www 請求為 0。新收據已按時間順序檢查，probe 重用的請求不重複計數。

遵守 robots 與「任何 4xx 停主機」後，本次覆蓋率低於前次未加入 robots 檢查的建置。announcements 主機的 robots 回 404，52 筆直接 PDF 來源均為 HOST_STOPPED:404；hermes 首次 403 後，後續 9 筆來源停止。原有 SAME 流失 326 格中，299 格變成缺漏（241 格 HOST_STOPPED_4XX、29 格 SOURCE_NOT_ACQUIRED、28 格 RULE_INPUT_MISSING、1 格 NO_SOURCE_VALUE），另外 27 格變成不同值，集中於專案名稱 12 格、來源名稱 8 格、URL 7 格。

HTTP 拒絕、主機停止與缺少候選分開記錄，不將其寫成已找到相同原件。一般政府分頁保留原有逐次狀態紀錄，www 與替代來源另記完整網址；避免長查詢網址令 CSV 收據超過既有讀取上限，未刪除請求次數。INDEX_PREVIOUSLY_UNAVAILABLE 的 Hastings 年報沿用先前同一公告索引 HTTP 429 的失敗結果，不重複請求。NO_ELIGIBLE_INDEX_PDF_LINK 僅表示這一頁沒有直接提供符合標記／日期的 PDF 連結，不代表全站沒有原件。

前次 53 格差異目前去向：`{"UNRESOLVED_DIFFERENCE": 38, "VALUE_UNAVAILABLE_NOT_A_CORRECTION": 15}`。VALUE_UNAVAILABLE_NOT_A_CORRECTION 代表值未取得，不是修正。

- [新總表](rebuild/專案總表.csv)、[逐格來源](rebuild/field_provenance.csv)、[缺格理由](rebuild/missing_fields.csv)。
- [完整逐格比較](cell_comparison.csv)、[變動與歸因](cell_increment.csv)、[比較統計](comparison-summary.json)、[前次 53 格差異](prior_53_differences.csv)。
- [37 筆結果](prior_not_pdf_37_outcomes.csv)、[全部 fallback 收據](fallback_report.csv)、[建議修補](proposed_sources_patch.json)、[擷取收據](acquisition_report.csv)、[ASX probe](asx_probe.csv)。

## T5：驗證

乾淨 CI Python 測試 404 項，錯誤 0、失敗 0、略過 0；R 分析腳本通過。測試 XML 保存在 [test-xml](test-xml/)，R 記錄見 [r-tests.log](r-tests.log)。本機 HTTP 測試僅連 127.0.0.1，涵蓋同 SHA 採用、異 SHA review_queue、robots、4xx／登入停止、請求與候選上限、禁止條款解析／提交、外域 redirect、長政府查詢收據，以及 T0 上層驗證。

Phase 20–22 本機凍結重建皆 MATCHED；[Phase 20](phase20-replay.json)、[Phase 21](phase21-replay.json)、[Phase 22](phase22-replay.json)。乾淨研究 CI 的各階段結果另見 ci-validation.json。

src 對 12f45f4 新增加刪除合計 183 行，對 070df10 累計 1,998／2,000 行；本輪沒有新增 src 模組、config 檔或原件 PDF，原件與 Phase 20–22 凍結資料未修改。T3 provider 依預算限制留為待辦。
