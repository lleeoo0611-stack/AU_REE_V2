# Apify ASX／JORC 隔離測試

從 Phase 22 `b5e2a73438e2f3aa9f4adc3ab0f6ff0f898f0fca` 建立測試分支。新程式只寫入指定 work 目錄，不修改正式來源 manifest、claims、研究設定、Project ID、C1 Gate 或 MCDA 結果。

`baseline_master.json` 是先前 SQLite 匯出總表的凍結衍生快照，保留原 33 個 canonical Project、52 欄、逐欄來源、日期、頁碼、SHA 及 SQL 重建紀錄。本測試匯出會核對 Phase 22 canonical membership；未取得及核對新資料時，完整保留原表數值。這個快照不是新的正式資料庫，也不代表每次執行都重新查詢 SQL。

## 執行

目前預設 Actor 為使用者指定的 `nexgendata/asx-company-announcements`（API 路徑使用 `nexgendata~asx-company-announcements`）。官方輸入只有 `tickers`、`marketSensitiveOnly`、`announcementType`、`maxResults`。沒有日期區間、JORC 關鍵字或 PDF 全文查詢參數。它提供近期公告串流，不是歷史技術文件索引。

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

初次測試預設最多回傳 19 筆公告、下載 20 份 PDF，傳送 `maxTotalChargeUsd=1.0` 與 Actor timeout=300 秒。19 筆是全部 tickers 的共同上限，不能解讀為每家公司 19 筆或完整歷史。Actor 頁面於 2026-11-07 顯示每公告 US$0.05、另有 start fee；以實際 run receipt 為準。每次新付費搜尋使用新的 work 目錄。

ASX 代碼只從 SHA 核對過的 Phase 22 原件首頁擷取；目前得到 22 個代碼、28 筆原件定位。這些是來源日期下的搜尋線索，包括共同提及及歷史代碼，不代表現行業主或上市狀態認證。所有定位保存在 `query_plan.json`。可用 `--tickers LYC,NTU,ARU --max-results 19` 指定測試範圍；沒有可用代碼時不自動改抓全市場。

原 Google 歷史文件搜尋保留為補充入口：`--provider google_serp` 使用 `config.google-serp.json`；其預設 16 個 query、每個 query 1 頁，完整現有計畫共 267 個 query，可用 `--max-queries 267` 或 `--query-offset 16` 分批。兩種 provider 使用獨立 work 目錄，不將 SERP 與公告列混成同一輸出契約。

GitHub 執行方式：在 Repository Settings → Secrets and variables → Actions 新增 Secret `APIFY_TOKEN`，於本測試分支的下一次相關 push 執行真實搜尋。缺少 Secret 時明確回報 blocked 並保留原表及紀錄。手動 dispatch 的 live 預設為 false。工作流程只讀取 repository，成果保存於 Actions artifact，沒有自動 merge 或回寫正式資料。新增 workflow 尚未存在 default branch 時，GitHub 可能不提供手動 dispatch 按鈕，可先使用本分支 push 觸發。

Apify start POST 不自動重試。若網路中斷造成啟動結果不明，先核對 Apify Console；已取得 run ID 可用 `--resume-run RUN_ID` 接續，不得直接重新啟動相同批次。`start_intent.json` 防止無意重複計費。完成的 run 保留 run ID、dataset ID、build ID、費用、輸入設定及完整 dataset 分頁收據。

## 文件與數值處理

預設從指定公司取得公告，依 `announcement_id` 保留前導零並去重，將超過截止日的公告標示為不下載。JORC、Mineral Resource Estimate、Ore Reserve、Competent Person、JORC Table 1、PFS／DFS 及 metallurgy 在本機公告標題與下載後 PDF 篩選。標題命中者優先；未命中的 quarterly／annual 等公告仍保留，避免漏掉內文資源表。`announcementType` 留空，不把 JORC 誤當公告類別參數。搜尋結果不能證明專案身分或 JORC 合規。

只下載兩個設定的 ASX HTTPS 原始網域。`file_url` 缺少時嘗試從 `source_url` 的公告頁解析單一 PDF 連結，保留公告 ID、原公告列雜湊、公告日期、wrapper HTML、resolved PDF URL 與內容 SHA。需要同意條款、連結不唯一或沒有下載 URL 時保留待查原因，不將 HTML 當 PDF。跨域重新導向、帶憑證 URL、超過容量限制的文件不下載。URL 去重後再用內容 SHA 去重，區分「首次發現 URL」和「基線不存在的新文件 SHA」。公司代碼不授權文件歸屬。

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

先保存 Actor 的公告 record-array JSON，另建立 URL → 本機 PDF 路徑的 `pdf_index.json`，相對路徑以 index 所在目錄為基準。replay 不呼叫 Apify，也不下載文件。Google 補充入口則使用其 SERP page-array 並指定 `--provider google_serp`：

```sh
python experiments/apify_asx/pipeline.py --mode replay --dataset retained/dataset.json --pdf-index retained/pdf_index.json --work work/apify-replay --as-of 2026-11-07
```

每次產生 `query_plan.json`、`run_summary.json`、搜尋結果、文件 inventory、逐候選審查資料及原 52 欄 CSV／XLSX。Excel 保留「專案總表」「資源範圍與檢核」「逐欄來源」「欄位與版本說明」，另加「ASX文件搜尋」。缺值留白，不以零補值。各次執行記錄固定基線、設定、正式輸入及輸出雜湊，不能把文件數當成新增 Project 或 MCDA 可用樣本數。

## 2026-11-07 驗證

- 20 項隔離測試通過：涵蓋 NexGenData 四欄輸入、缺少 file_url 的公告定位、公告 ID 去重衝突、日期排除、JORC 優先而不丟棄 quarterly、wrapper 連結／條款限制，以及原 13 項 API／資源／匯出測試。
- 真實留存 ASX 原件 `yttria_2025`（2025-07-31，SHA `eb73f28443e453f9663f7957b0b9d3950d8734cf910543acc213d5ef6742a668`）離線重播取得 4 個候選，其中 1 個資源總量候選無解析 issues；這是既有文件的解析驗證，新增文件為 0。
- 33 × 52 的 CSV 與先前總表逐格完全相同。原正式 manifest、claims、research config、source config SHA 均未改變。
- 真實 live 入口回報 `BLOCKED_APIFY_TOKEN_MISSING`。目前沒有成功 Apify run、沒有新增文件或資源更新。
- 曾執行既有完整 Python 回歸：206 項，3 failures、56 errors、3 skipped。錯誤包含本機 sparse checkout 未取回的歷史 results、benchmark、disclosure 及其他快照；未將此結果宣稱為完整回歸通過。正式核心程式及其設定未修改。

## 官方參考

- [Apify Actor 輸入](https://apify.com/apify/google-search-scraper/input-schema)：queries、maxPagesPerQuery。
- [NexGenData Actor 說明與限制](https://apify.com/nexgendata/asx-company-announcements)：近期公告、非全文、file_url 可缺、無歷史日期區間。
- [NexGenData 輸入](https://apify.com/nexgendata/asx-company-announcements/input-schema)：tickers、marketSensitiveOnly、announcementType、maxResults。
- [NexGenData API](https://apify.com/nexgendata/asx-company-announcements/api)：一般 Apify API 仍需 account／token；頁面上的 No API key 不等於一般 API 的無憑證執行。
- [Run Actor](https://docs.apify.com/api/v2/actors-runs-post)：start、timeout、maxTotalChargeUsd。
- [Dataset items](https://docs.apify.com/api/v2/dataset-items-get)：offset／limit 與 pagination headers。
- [Apify API 認證](https://docs.apify.com/api/v2)：Authorization Bearer。
