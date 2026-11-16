# 同 SHA 原件替代流程

從 `12f45f4` 建立 `feat/same-sha-fallback-20261116`，PR 目標為 `feat/phase16-technical-model`；只開 PR，不 merge。

> 目前為待乾淨 CI 建置的版本。以下已驗證的程式／資料契約與尚待實測的來源結果分列，未宣告 T4 完成。

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

## T4／T5：驗證與待交付實測

本機 HTTP 測試涵蓋相同／不同 SHA、robots UTF-8 BOM 與 disallow、4xx 後停止、跨來源請求上限、候選上限、條款／登入頁不解析、不提交表單、外域 redirect 不跟隨，以及合法 redirect 仍驗證目的端 robots。所有測試只連 127.0.0.1。

既有完整測試第一輪 398 項通過，新增最後案例另行驗證；最終以本 PR 乾淨 CI 的 XML 為準。Phase20–22 的新重建證據會保存在本目錄，凍結原檔不變。

目前 src 新增加刪除合計：對 `12f45f4` 為 182 行，對 `070df10` 累計 1,997 行；未新增 src 模組、config 檔或原件 PDF。T4 的實際 fallback_report、proposed patch、新總表與逐格增量尚待乾淨 CI，尚未計入找到同 SHA 或恢復格數。
