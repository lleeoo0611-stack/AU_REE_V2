# Phase 22 integration checkpoint — T0 only, stopped at the line-budget gate

本次尚未完成完整專案總表。已從指定的 `070df10` 建立 `feat/integrated-rebuild-20261115`，完成網路防呆與一次 ASX 試抓；規則移植預估超過 1,500 行，依任務的明確停止條件，在 T1–T5 實作前停下。沒有 push、開 PR 或 merge。

## T0：網路有效性

`dns_preflight.csv` 包含來源登記與固定官方查詢的 44 個 host，全部為 `DNS_OK`。解析成功不代表 HTTP 連線成功。

`asx_probe.csv` 逐筆保存兩個 ASX host 各三份已登記 PDF 的 URL、狀態、SHA（若有）、HTTP 狀態及每次請求紀錄。結果如下：

| host | 已登記文件數 | NETWORK_ERROR | HTTP 回應 | HOST_STOPPED |
| --- | ---: | ---: | --- | ---: |
| www.asx.com.au | 3 | 3 | 未取得 | 0 |
| announcements.asx.com.au | 3 | 3 | 未取得 | 0 |

六筆均為 `WinError 10061` 連線遭拒；這不能證明遠端網站回了 4xx，也不能判定 `www.asx.com.au` 已封鎖本研究。沒有改 User-Agent、URL、參數，沒有重新試抓或人工下載。`probe_host_state.json` 保存原始請求紀錄及停止狀態。

試抓後以既有六筆紀錄離線判定有效性，結束碼為 1；未再送出網路請求。`network_status.json` 的範圍為這六筆診斷，狀態為 `RUN_INVALID_NETWORK`，網路錯誤比例為 6/6，`valid_for_delivery=false`。這不是 185 份來源的完整建置或可交付研究結果；完整建置未開始。

實作位於既有模組：

- `acquisition.py`：`strict_dns_preflight`、`strict_failure_status`、`strict_network_report`、`strict_asx_probe`；`StrictTransport` 與 `strict_refresh` 延續原本 3 秒間隔、4xx／CAPTCHA／登入頁停 host、逾時或 5xx 最多重試一次的策略。DNS／連線錯誤獨立記為 `NETWORK_ERROR`，不以既有 snapshot 掩蓋。網路錯誤來源超過 5% 即拋出 `InvalidNetworkRun`，先保存報告再拒絕研究建置。
- `cli.py`：strict 建置先檢查 DNS，再試抓 ASX；試抓網路異常超過門檻時以非零結束碼停止，尚未建立資料庫。成功試抓的 bytes 留在同次程序記憶體供正式抓取沿用；失敗試抓不重新送出請求，停止狀態由同一 transport 延續。
- `failure_details` 僅對 strict transport 標記過的例外增加網路錯誤旗標，避免官方查詢包裝例外後遺失分類；既有非 strict 例外輸出不增加此欄位。
- 擴充既有禁用字串測試，包含任務指定字串，並檢查 automated-build workflow。

## 行數停止條件

目前 `git diff --stat 070df10 -- src` 為兩個既有檔案、122 行新增與 11 行刪除，合計 **133 行**；沒有新增 `src/au_ree_v2/*.py` 或 config 檔。

`rule-budget-inventory.csv` 透過 `git show` 與語法樹盤點 58 個相關函式，記錄來源檔、函式、起訖行號及預定目標模組。原始函式範圍共 1,548 行。`rule-budget-estimate.json` 另列接線估計與可刪除的舊流程：

| 項目 | 行數 |
| --- | ---: |
| 目前 T0 變更 | 133 |
| 相關函式原始範圍 | 1,548 |
| 預估沿用既有 helper、移除實驗檔案讀寫的節省 | −300 至 −500 |
| 資料庫匯出與逐格追溯接線 | 180 至 240 |
| attributes、詞彙及 CLI 接線 | 140 至 220 |
| 預估全部 src 變更 | 約 1,500 至 1,850；中點 1,671 |

此為工程估計，並非證明任何設計都不可能在 1,500 行內完成。已排除 `asx_validation`、`reviewed_discovery`、`reviewed_metadata` 的 ledger 驗證分支與實驗發布／封存／審計 wrappers；沒有把整個實驗模組照單計入。按目前優先保留已審查函式及全部規則的方案，預期會超過上限，因此未靠壓縮程式或刪減規則繼續實作。

## 驗證

針對性網路與來源驗證：32 項測試通過（後續新增 CLI 與官方例外測試另由全套測試驗證）。

**最終全套 unittest：370 項通過，0 failures、0 errors，耗時 332.961 秒，結束碼 0。** XML 位於 `test-xml-final/`，包含新增的 CLI 非零結束碼與官方查詢例外分類測試。

第一輪全套 unittest 啟動早於獨立環境套件安裝完成，跑了 93 項、26 個環境載入錯誤（包含 `openpyxl` 未就緒）；該輪不是通過結果，失敗 XML 保留於 `test-xml/`。最終重跑前已逐一確認全部必要依賴可成功匯入。沒有刪除或將第一輪失敗偽裝成通過。

R 既有分析回歸：結束碼 0，所有 invariants 通過；`R-tests.xml` 與 `R-tests.log` 保存結果。啟動時有 Windows locale 設定警告，無測試失敗。

`git diff --check` 通過。既有 snapshots、manifest 及 Phase 19–22 結果沒有改動；本次沒有重跑 Phase 20–22 凍結重建，不能把既有結果當成本次重建驗證。

## 尚未執行

- T1：76 份來源的第二次遷移；沒有產出或虛構 source-migration-2.csv。
- T2–T4：列集合、重複 MRE 防重算、Charley 身分恢復、157 筆元素與文字屬性宣告、所有規則的正式移植。
- T5：51 欄總表匯出、逐格追溯、空值原因與兩層覆蓋率。
- T6–T7：兩份總表、乾淨完整建置、逐格比對、PR 與乾淨 runner CI。

沒有將未實作的欄位統一歸成 `SOURCE_NOT_ACQUIRED` 或其他原因；尚未取得足夠建置結果判定這些格子。實驗線的 73.29%（2159/2946）僅是任務給定的對照文字，不是本次覆蓋率，也沒有寫入建置設定。

## 研究者需決定

先決定是否調整 1,500 行上限；建議上限 2,000 行以保留估計餘裕，其餘硬限制維持。若維持原上限，需重新設計並重新估算，不能宣稱目前已完成整合。

實際網路目前沒有取得任何 ASX HTTP 回應；本次不自行重試。ASX 統計頁啟用、網站確實回 4xx 後的處理、逐格 DIFFERENT 判定，仍屬尚未到達的後續決策，沒有代研究者裁定。
