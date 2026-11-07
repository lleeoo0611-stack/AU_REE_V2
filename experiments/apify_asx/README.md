# Apify ASX／JORC 隔離測試

從 Phase 22 `b5e2a73438e2f3aa9f4adc3ab0f6ff0f898f0fca` 建立測試分支。新程式只寫入指定 work 目錄，不修改正式來源 manifest、claims、研究設定、Project ID、C1 Gate 或 MCDA 結果。

`baseline_master.json` 是先前 SQLite 匯出總表的凍結衍生快照，保留原 33 個 canonical Project、52 欄、逐欄來源、日期、頁碼、SHA 及 SQL 重建紀錄。本測試匯出會核對 Phase 22 canonical membership；未取得及核對新資料時，完整保留原表數值。這個快照不是新的正式資料庫，也不代表每次執行都重新查詢 SQL。

## 執行

不需要憑證即可列出查詢並重建總表：

```sh
python -m pip install .
python experiments/apify_asx/pipeline.py --mode plan --work work/apify-plan --as-of 2026-11-07
python -m unittest discover -s experiments/apify_asx -p 'test_*.py' -v
```

將 Apify token 設定於執行環境的 `APIFY_TOKEN`，不要放入程式、設定檔、URL、commit 或命令列參數。執行真實搜尋：

```sh
python experiments/apify_asx/pipeline.py --mode live --work work/apify-live-001 --as-of 2026-11-07
```

初次測試預設 16 個 query、每個 query 1 頁、最多下載 20 份 PDF，傳送 `maxTotalChargeUsd=1.0` 與 Actor timeout=300 秒。費用參數依 Apify Actor 的計價模式生效；它不保證搜尋覆蓋率。267 個 query 涵蓋目前設定的 3 組全國搜尋及 33 專案 × 8 詞組，可用 `--max-queries 267 --max-documents 100` 擴大；也可用 `--query-offset 16` 分批接續。每次新付費搜尋使用新的 work 目錄。

GitHub 執行方式：在 Repository Settings → Secrets and variables → Actions 新增 Secret `APIFY_TOKEN`；另將 Repository Variable `APIFY_LIVE_ENABLED` 設為 `true`，於本測試分支的下一次相關 push 執行真實搜尋。未開啟該變數時僅產生 plan／原表。工作流程只讀取 repository，成果保存於 Actions artifact，沒有自動 merge 或回寫正式資料。新增 workflow 尚未存在 default branch 時，GitHub 可能不提供手動 dispatch 按鈕，可先使用本分支 push 觸發。

Apify start POST 不自動重試。若網路中斷造成啟動結果不明，先核對 Apify Console；已取得 run ID 可用 `--resume-run RUN_ID` 接續，不得直接重新啟動相同批次。`start_intent.json` 防止無意重複計費。完成的 run 保留 run ID、dataset ID、build ID、費用、輸入設定及完整 dataset 分頁收據。

## 文件與數值處理

搜尋 JORC、Mineral Resource Estimate、Ore Reserve、Competent Person、JORC Table 1、PFS、DFS 及 metallurgy，配合 rare earth／TREO、專案名稱與截止日。搜尋服務使用 Apify 官方 `apify/google-search-scraper`，不是 ASX 官方站內搜尋 API。搜尋結果不能證明文件發布日期、專案身分或 JORC 合規。

只下載兩個設定的 ASX HTTPS 原始網域。跨域重新導向、帶憑證 URL、非 PDF、超過容量限制及失敗的文件保留待查原因。URL 去重後再用內容 SHA 去重，區分「首次發現 URL」和「基線不存在的新文件 SHA」。查詢所用 Project ID 不授權文件歸屬。

解析直接重用 `au_ree_v2.pdf_extract.recognize_document`、現有 canonical mapping 與候選值檢查；實驗 `staging.sqlite` 只含文件及候選資料，不是正式 evidence store。未能確認的專案與新候選身分留待審查，不自動擴充正式母體。

原表更新需提供 `--decisions decisions.json`。此版支援既有 Project 的同範圍資源替換：選擇無解析 issues 的 Mineral Resource total 候選，核對原檔及 extraction SHA、資源有效日期、總量類別、TREO 基準、原始頁面與取代範圍證據。Reserve／Exploration Target 不能代替 Mineral Resource。資源更新會清空舊資源的所有元素配分及磁性／重稀土衍生量，避免不同日期和範圍混用。新專案收錄、全 15 元素更新與技術／年產欄位更新仍需後續沿既有正式流程處理，本分支沒有自動推定。

Decision 格式：

```json
[
  {
    "candidate_id": "從 candidate_review.json 選取",
    "project_id": "既有穩定ID",
    "decision": "VERIFIED_REPLACE_RESOURCE",
    "reviewer": "核對者",
    "reason": "取代舊版同範圍資源的原始證據與理由",
    "supersedes_same_scope": true,
    "scope": "與候選原文相同的資源範圍",
    "source_sha256": "原始PDF的SHA256",
    "effective_date": "2026-11-01",
    "evidence": [
      {"role": "effective_date", "physical_page": 1, "marker": "原文日期證據"},
      {"role": "same_scope_replacement", "physical_page": 2, "marker": "原文範圍與更新證據"}
    ]
  }
]
```

## 離線重播

先保存 Apify SERP page-array JSON，另建立 URL → 本機 PDF 路徑的 `pdf_index.json`，相對路徑以 index 所在目錄為基準。replay 不呼叫 Apify，也不下載文件：

```sh
python experiments/apify_asx/pipeline.py --mode replay --dataset retained/dataset.json --pdf-index retained/pdf_index.json --work work/apify-replay --as-of 2026-11-07
```

每次產生 `query_plan.json`、`run_summary.json`、搜尋結果、文件 inventory、逐候選審查資料及原 52 欄 CSV／XLSX。Excel 保留「專案總表」「資源範圍與檢核」「逐欄來源」「欄位與版本說明」，另加「ASX文件搜尋」。缺值留白，不以零補值。各次執行記錄固定基線、設定、正式輸入及輸出雜湊，不能把文件數當成新增 Project 或 MCDA 可用樣本數。

## 2026-11-07 驗證

- 新增的隔離測試涵蓋 Bearer header、費用參數、分頁完整性、不明啟動結果防重試、URL／內容去重、非 PDF、日期／scope、Reserve 排除、資源換版清除舊配分及表格公式。
- 真實留存 ASX 原件 `yttria_2025`（2025-07-31，SHA `eb73f28443e453f9663f7957b0b9d3950d8734cf910543acc213d5ef6742a668`）離線重播取得 4 個候選，其中 1 個資源總量候選無解析 issues；這是既有文件的解析驗證，新增文件為 0。
- 33 × 52 的 CSV 與先前總表逐格完全相同。原正式 manifest、claims、research config、source config SHA 均未改變。
- 真實 live 入口回報 `BLOCKED_APIFY_TOKEN_MISSING`。目前沒有成功 Apify run、沒有新增文件或資源更新。
- 曾執行既有完整 Python 回歸：206 項，3 failures、56 errors、3 skipped。錯誤包含本機 sparse checkout 未取回的歷史 results、benchmark、disclosure 及其他快照；未將此結果宣稱為完整回歸通過。正式核心程式及其設定未修改。

## 官方參考

- [Apify Actor 輸入](https://apify.com/apify/google-search-scraper/input-schema)：queries、maxPagesPerQuery。
- [Run Actor](https://docs.apify.com/api/v2/actors-runs-post)：start、timeout、maxTotalChargeUsd。
- [Dataset items](https://docs.apify.com/api/v2/dataset-items-get)：offset／limit 與 pagination headers。
- [Apify API 認證](https://docs.apify.com/api/v2)：Authorization Bearer。
