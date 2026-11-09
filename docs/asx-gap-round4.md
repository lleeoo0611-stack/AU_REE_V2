# 澳洲 REE 專案擴搜與第四輪總表驗證

沿用 `experiment/asx-public-acquisition-20261109`，研究資料截止 2026-11-05，取得與核對日期為 2026-11-10。
本輪兩項工作都有進行：查找未列入總表的澳洲 REE 專案，以及核對六個資源缺口、稀土組成和年產量。
遵循 proposal 的可追溯資料收集與比較目的；沒有改算 MCDA，也沒有把研究收錄當成正式 C1、採礦權或全國完整性認證。

## 已驗證結果與分母

使用者指定基準為 `b1625cf`：33 列 × 52 欄，793 格有值、923 格空白。
期間遠端加入 `9b85c84` 的 Nolans 與 `bf58182` 的 Ridley 審查；本輪完整保留並去重。

| 比較範圍 | 列數 | 已填格 | 空白格 | 25 個科學數值欄位 |
|---|---:|---:|---:|---:|
| 原基準 | 33 | 793 | 923 | 276 / 825 |
| 同一批原專案，整合後 | 33 | 830 | 886 | 302 / 825 |
| 新收錄專案 | 4 | 70 | 138 | 22 / 100 |
| 擴充總表 | 37 | 900 | 1,024 | 324 / 925 |

原 923 個缺口合計補回 **37 格，其中 30 格為數值**，撤回 0 格。另有 17 格既有值更新，來自 Ridley 選用資源範圍的改變。
四個新專案的 70 格另計，不能說成補掉原本的 923 格。總表空白 1,024 格包括原案 886 格與新案 138 格。
相對最新遠端 `bf58182`，本輪另補 **Goschen 1 格**及四個新專案 70 格；沒有把重複的 Nolans 成分再算一遍。

原群組完整 15 氧化物組由 7 增為 8，加入 Deep Leads 後為 9 組；年產 NdPr 由 4 增為 5 組。
年產 TREO 仍為 6 組，完整模板 HREE8 年產仍為 0 組。HREE8 沿用 Tb、Dy、Ho、Er、Tm、Yb、Lu、Y，不用 Dy＋Tb 或其他 HREO 定義替代。

## 未列入專案的搜尋與收錄

搜尋使用政府目錄／地質調查、發行公司原件與完整 ASX 公告索引。
29 個名稱逐案留有 URL、SHA、頁面或網頁標記及處置：4 個收錄、16 個保留候選、4 個母子範圍／別名、4 個既有專案、1 個加工設施。
底層資料已出現的名稱，不算全新發現；候選記錄不等於獨立專案數。

| 新增研究列 | 依據與數值限制 |
|---|---|
| Deep Leads – Rubble Mound – Wind Break | [ABx 2024-05-02 原件](https://www.asx.com.au/asx/v2/statistics/displayAnnouncement.do?display=pdf&idsId=02803111)。三個礦床合為一列；採附件實體第 6 頁的 88.6 Mt、844 ppm、15 氧化物總列，不採封面捨入 89 Mt，也不把三個礦床重複加總。資源有效日 2024-04-30。 |
| Sandy Mitchell | [2026-10-29 新 Scoping Study](https://www.asx.com.au/asx/v2/statistics/displayAnnouncement.do?display=pdf&idsId=03159067) 確認昆士蘭獨立專案。公告表為 379.4 Mt，後又修訂至 373.3 Mt，但未給相配的修訂 TREO 品位，因此資源欄留白。5,430 ppm MzEq 不是 TREO。年產獨居石／磷釔礦質量不能直接當氧化物量。 |
| Avonbank | [Austrade 政府目錄](https://international.austrade.gov.au/content/dam/austrade-assets/international/documents/reports/critical-minerals/australian-critical-minerals-prospectus-march-2026.pdf) 實體第 46 頁，維州、WIM Resource。確認是含 REE 副產品的採礦專案；THM 和礦物比例未換算成 TREO。 |
| Copi | 同一政府目錄實體第 47 頁，新州、RZ Resources。採礦專案與布里斯本加工廠分開；未把獨居石／磷釔礦比例或前十年產率當 TREO／完整重稀土。 |

四列使用穩定的研究擴充 ID，來源和候選 crosswalk 明列於 `project_discovery_reviews.json`。
原有 SQLite 中的 33 個 canonical 群組與關聯沒有被改寫，四列不宣稱已完成正式身分／權利核准。

保留候選包括 Charley Creek、Wimmera、Balranald、Euston、Caralue Bluff、Dickson Well、Franklyn、Minos、Target 21、Comet、Morgan’s Creek、Billeroo、Olympic Dam、Carrapateena、Aileron、Eneabba。
各自仍須核對專案／礦床／加工範圍及原始資源依據。Charley Creek 的歷史 805 Mt 標題沒有與較新的 Cattle Creek 資源界定工作混用。
另輸出全部 **129 筆凍結 PROJECT_CANDIDATE 記錄**；7 筆連結到本輪逐案審查，122 筆仍待來源與專案歸屬核對。
這份隊列不能解讀成 129 個未收錄的獨立澳洲專案，也沒有宣稱已逐一完成技術報告驗證。

## 六個既有資源缺口

| 專案 | 仍未填值原因 |
|---|---|
| Burracoppin | bulk 35.709 Mt 與 -45 µm 細粒 14.731 Mt 的基準不同；1,356.4 ppm 對應細粒。政府摘要不能解除這項混用問題。 |
| Greater Brothers | Jupiter 已在總表；沒有取得可與已計數 Jupiter 分開使用的母專案資源，避免重複。 |
| Splinter | 政府表列 22.90 Mt／0.11%，但私人發行方原始技術報告、類別與日期仍未核清；與 OD6 Splinter Rock 分開。 |
| Lyons | 目前公司網頁仍列 2,266＋670 t，而總列是 3,221 t；未找到可解除衝突的更正。 |
| Mt Stirling | 15 Mt／490 ppm 屬已列 Yttria；110–300 Mt 是 Exploration Target，不再建一份資源。 |
| Kalkaroo | REE 仍屬潛力／研究資訊；沒有轉用 Cu／Au／Co 資源噸位或局部樣品品位。 |

原六案均維持未知值。新增 Sandy Mitchell、Avonbank、Copi 尚無可採用配對，故擴充表合計九列缺資源量／品位。
逐欄原因見 `missing_fields.csv`，逐案處置見 `project_gap_assessment.csv`；未知不是零，也不代表沒有後續公告。

## 成分、年產量與日期的重要驗證

- **Nolans：**整合遠端既有的完整來源儲存格審查，15 氧化物的 `%TREO` 以同一資源已驗證的 2.6% TREO 品位換算。
  保留獨立的總資源品位輸入綁定，拒絕借用礦石儲量、精礦或樣品品位。此套與本輪重複，僅計一次。
- **Ridley：**保留遠端選用的 Blocks 1、2，共 122,546,251 t、889 ppm。這是範圍改變，不是把 Mia 168 Mt 降級或與之相加。
  12 個氧化物按實體第 6 頁精確儲存格核對；Ce 的化學式矛盾，以及 Y、Yb 超出捨入界限的含量衝突，維持隔離。
  原 Mia 仍經驗證但標為 `CONTEXT_ONLY`，不會作為目前數值的備援。
- **Goschen：**原 DFS 更新第 2 頁列「Nd-Pr contained in REC」990 tpa；本輪再核對第 6 頁附錄，明載年產量是精礦量 × TREO 品位 × 相應氧化物占 TREO 比例。
  因此可填 **990 t NdPr 氧化物／年**。數字列、年度分母和跨頁氧化物定義都須一致；8,300 tpa REC 仍不當成 TREO，115 tpa Dy＋Tb 也不是 HREE8。
- **政府目錄出版日期：**實體第 2 頁明列 `Publication date: March 2026`，優先於前言的 February edition。
  Fingerboards 與新增政府來源列改保留出版區間 **2026-03-01～03-31**；3 月 31 日只是排序上界，不宣稱精確出版日。
  Fingerboards 資源有效區間仍為 2022 年 8 月，數值沒有改動。
- **Sandy Mitchell：**新研究明確取代 2024 舊研究；不借回舊年產預測。2026 MRE PDF 字型編碼異常，未猜字碼，改核對可讀的新 Scoping 原件。
  試驗樣品的 51.9% REO 也沒有配上年度礦物產量。
- North Stanmore 的舊 Scoping 產量不覆蓋新 PFS；未以約略年數或 offtake 百分比倒推精確年產。
  其餘未公開個別成分、分階段產量、樣品與資源基準不同、未核清的元素／氧化物定義，繼續保留缺口。

## 取得、測試與重現

新增 ABX／AHK／KTA × 2022、2024、2026 共九個索引，九個均可解析，459 個不同帶日期公告連結，未全部下載。
明確定位來源共 25 個網址：10 個 HTML 已保存、9 個 PDF 取得、6 個拒絕／未取得。HTML 保存成功不等於內容已可作證據；QIC 的頁面殼未作來源收錄依據。
PDF 為 **9／10 成功**，共 **668 頁**；其中 ASX 公開原件 **8／8 成功**，其餘為政府文件。
Ridley 與平行遠端的同一 PDF 按 SHA 計一份。頁數是文件總長，不是逐頁人工金標驗收數。
沒有使用付費服務、代理輪替、CAPTCHA、憑證或受限制內容的繞過。

遠端更新過的 Barkly、Kennedy 索引收據改保留本機已核對的同網址／日期捕獲，並記錄遠端捕獲 SHA；沒有放寬 URL、雜湊或公告日期檢查。
來源數值仍須通過 v2 列／欄／語意標頭／單位／資源範圍檢查。新增身分收錄另外驗證國別、州、原件日期和別名衝突。

整合後 255 項相關回歸測試及 27 個子案例通過；針對性測試 114 項及 19 個子案例通過，兩組有重疊，不能相加當獨立測試數。
測試收據與 SHA 在 `validation.json`。兩次完整匯出的四個 CSV 逐位元一致，所有已填欄格恰有一筆目前來源，每個空白有診斷。
原 SQLite SHA 保持 `99ed9c0fc004960f92680ee782ef8764c189a08d98bce4d14c2d0e5ad99091d0`。
這是相關回歸驗證，沒有宣稱重建所有歷史研究、完成 R／MCDA 或通過遠端 CI。

重現入口為 `tools/capture_research_sources.py`、`tools/discover_asx_archives.py`、`tools/export_project_summary.py`、
`tools/audit_project_discovery.py`、`tools/validate_asx_candidates.py --allow-cohort-expansion` 與 `tools/package_asx_round4.py`。
匯出時同時指定 `--review-ledger config/asx_source_reviews.json`、`--discovery-ledger config/asx_discovery_reviews.json`，並提供各 `--asset-root` 的本機受控原件。
本輪派生成果在 `results/asx-gap-round4-2026-11-10`；`results/asx-current` 更新為目前版本。原始 PDF、完整頁面文字、影像和 SQLite 不公開推送。
