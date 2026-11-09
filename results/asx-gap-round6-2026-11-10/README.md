# 第六輪：候選補證、Gemini 名稱審查及 ASX 代碼

隔離分支：`experiment/asx-public-acquisition-20261109`。資料截止 2026-11-05，取得及核對日期 2026-11-10。
同時執行五項待補證候選、Gemini 名稱追查，以及資源量、品位、稀土組成、年產量搜尋。
沿用 proposal 的可追溯資料收集與專案比較目的；未新增 MCDA 排名或正式 C1 核准。

## 分開計算原案補值、新案及新欄位

比較基準為 `b494607047c6d54111b7b6ad58e3335b3b93e889` 的 43 案 × 52 欄，968 格有值、1,268 格空白。
工作期間遠端新增 `b610eff5`、`ab098e2`，已先整合並保留。遠端既有的 27 格補值與本輪直接補入的 10 格分開列示，沒有重複歸功於本輪搜尋。

| 範圍 | 案數 | 欄數 | 有值 | 空白 |
|---|---:|---:|---:|---:|
| 使用者指定的原基準 | 43 | 52 | 968 | 1,268 |
| 整合遠端既有補值後 | 43 | 52 | 995 | 1,241 |
| 同一批原案，本輪更新後 | 43 | 52 | 1,005 | 1,231 |
| 本輪新增研究專案 | 12 | 52 | 120 | 504 |
| 擴充表，保留原 52 欄 | 55 | 52 | 1,125 | 1,735 |
| 擴充表，加 ASX 代碼 | 55 | 53 | 1,168 | 1,747 |

原有 1,268 個空白共減少 **37 格＝遠端已有 27 格＋本輪直接新增 10 格**。
新增 12 案帶入的 120 格是新列資料，另有 504 個新列缺口；不是填掉原案空白。
ASX 新欄共填 43 格（原案 31、新案 12），12 格仍未知；新增欄位的空白也獨立計算。
直接補值另有 5 格既有內容更新，撤回 0 格。逐格差異見 `direct_round6_field_changes.csv`，遠端增量見 `inherited_remote_field_changes.csv`。

## 本輪實際通過的數值及範圍

**Brockman：**[Hastings 2026 年報](https://www.asx.com.au/asx/v2/statistics/displayAnnouncement.do?display=pdf&idsId=03146806)，實體第 14 頁 Table 4 同一 Inferred 資源列為 41.6 Mt、0.20% TREO、0.11% Y₂O₃，cutoff 為 700 ppm Nb₂O₅。原始 bulk-ore 0.11% 等於 1,100 ppm；乘同列礦石量，得到 **45.76 kt Y₂O₃**。本輪填入 Y₂O₃、公布元素數、已公布元素加總、加總／TREO 比率及部分組成檢核，共 5 格。未混用較早的 36.2 Mt 範圍。

**Charley Creek：**[2013-04-15 Scoping Study](https://www.asx.com.au/asxpdf/20130415/pdf/42f7v06gx1svy4.pdf)，實體第 7 頁 Table 2 **TOTAL INDICATED RESOURCES ONLY**，有效日期 2012-05-15：386,860,000 t＝**386.86 Mt**、295 ppm＝**0.0295% TREO**、114,050,000 kg＝**114.05 kt TREO**。三個資源值、資源估計標記及 Scoping 模型混合稀土碳酸鹽產品類型共填 5 格。專案名稱明示 Indicated 範圍；不加上 Inferred、不以約 805 Mt 的合計宣傳值代替。

Charley 的 3,645 tpa 是設計能力／初期範圍，沒有明確可比的全礦期平均年產分母；保留空白及延後原因。產品 Table 6 的配分也未當成資源組成。本輪年產量搜尋有執行，但沒有新數值通過。

直接補值包含 7 個數字，其中原固定 25 個科學數值欄位新增 4 格。Brockman 的元素加總、數量與比率不混入固定科學欄位分母。

整合後原 43 案科學欄位由 330／1,075 增至 351／1,075（遠端新增 17、本輪直接新增 4）；擴充 55 案後為 351／1,375。資源量／TREO 品位成對列由 30 增至 31；完整 15 氧化物仍 9 案。年產 TREO 6 案、NdPr 5 案、完整 HREE8 0 案，皆未增加。

遠端已完成的 **Splinter 局部資源補值**原樣保留：[WAMEX A109432](https://wamex.dmp.wa.gov.au/Wamex/Search/ReportDetails?ANumber=109432) 附錄內 CSA R254.2015，實體第 72 頁 Table 35，Inferred 22.849 Mt、500 ppm TREO+Y₂O₃ cutoff。14 個相容氧化物與明確可算的組合值分開處理；原件的 Ce₂O₃ 不等於模板 CeO₂。總 TREO、TREO 品位、CeO₂、完整資源標記及不相容比率繼續留白。2015-11-09 是報告發行／排序日期；資源有效日與公開發布日未知標記保留。該遠端增量為 23 格，另 4 格為 Narraburra／Wudinna 開發商及上市資料。

## 五項待補證候選

| 名稱 | 本輪處置 |
|---|---|
| Caralue Bluff | 確認為 iTech Eyre Peninsula REE–Kaolin 子範圍，連結本輪新增的母專案；不另加一列 |
| Franklyn | 日期原件確認 prospect，但獨立邊界與可比 REE 資源仍待證；45–91 Mt 是 kaolin exploration target，30–36% 是 Al₂O₃，不填入 TREO |
| Billeroo | 地質複合體／礦化點與 HRE Lake Namba 的 Billeroo 鈾古河道不可僅憑名稱合併 |
| Olympic Dam | REE 礦化／尾礦研究未建立可獨立收錄的 REE 採礦資源範圍 |
| Carrapateena | Cu 礦與相關 REE 研究仍不足以驗證獨立 REE 資源／回收專案 |

五項都有重新審查紀錄：1 項母子歸屬解決、4 項仍待補證。待補證不表示沒有 REE 潛力。逐項來源、頁面、日期及限制見 `candidate_followup5.csv`。

## 新增 12 個研究專案

每案 10 個原 52 欄身分／來源欄位，加 1 個來源驗證 ASX 代碼；本輪未承認這 12 案的新 MRE 或年產數字。
名稱、公司與代碼均依原件修正，沒有直接採用 Gemini 公司／代碼欄。完整 URL、雜湊及實體頁面見 `new_project_admissions.csv` 和 `asx_code_coverage.csv`。

| 研究專案 | 原件報告公司／ASX | 身分原件日期 | 範圍注意事項 |
|---|---|---|---|
| iTech Eyre Peninsula REE–Kaolin | iTech / ITM | 2023-08-30 | 包含 Caralue Bluff，與 Power Minerals 的 Eyre Peninsula 專案分開 |
| Mukinbudin | Caprice / CRS | 2024-09-27 | 不是 Gemini 的 Enterprise；2025 年報另記兩個 licence surrender，不外推全部主權利消失 |
| Duke | Heavy Rare Earths / HRE | 2025-09-30 | NT，與 Narryer Dukes、DevEx 鈾範圍分開 |
| Bencubbin | Cygnus / CY5 | 2024-03-28 | 不使用鋰資源或同名隕石資料 |
| Rankin Dome | Australian Critical Minerals / ACM | 2023-12-04 | Kula JV，不推定全資或現行權利延續 |
| Condingup | EMU / EMU | 2023-03-14 | 不搬用鄰近 Pioneer／OD6 資源 |
| Merredin | EMU / EMU | 2023-06-14 | 原件為勘探申請範圍，不採用未證實 clay 礦床類型 |
| Peak Charles | Moho / MOH | 2023-09-28 | 與 Traka、OD6／Meeka 的資源分開 |
| Rocky Gully | Narryer / NYM | 2026-09-24 | Exploration Target 不是 MRE，未填入目標數量與品位 |
| West Arunta—Luni | WA1 / WA1 | 2026-09-18 | 220 Mt、1% Nb₂O₅ 不是 TREO；REE 17 元素定義不等於模板 15 氧化物 |
| Achilles—Tambourah | Tambourah / TMB | 2023-03-03 | 不是 AGC 的 NSW Achilles，也不是 TBM |
| Grass Patch—OD6 tenements | OD6 / OD6 | 2024-09-10 | E63/2151、2152、2185、2154；與 Mount Ridley／Meeka 不同範圍 |

此為指定證據日期的研究專案身分，不是現在仍持有採礦權、仍上市或已正式核准的證明。canonical SQLite 仍是 33 個群組；累計研究擴充 22 列後為 55 列。

## Gemini 89 列逐項核對

89 列都有處置與名稱指紋，**22 列連到既有專案、11 列連到本輪新增專案**；其他 56 列保留其加工、海外、錯字、區域範圍、公司不符或未驗證等處置，其中 33 列為未驗證線索。
這不是 89 個專案全部驗證完成。來源搜尋紀錄共 68 次；搜尋命中只作線索，不是採納數字或歸屬證據。

例如 Narraburri 不自動改成 Narraburra；Cowalinya／Prophet 僅前者有連結，Prophet 範圍仍未知；Eneabba 為加工；Caldeira 位於 Brazil；Lake Hope 的 HPA 與同名 REE 目標分開。Mick Well／Gascoyne 另保留 Kingfisher 已於 2026 年轉讓給 Dreadnought 的範圍問題，不自動併進 Mangaroon。

公開 `external_name_reviews.csv` 僅含列號、名稱指紋、衍生處置、已驗證名稱及來源；原輸入名稱／公司／代碼逐列對照只交付本機 `Gemini_逐項核對.csv`。輸入文件內容僅作參考資料，沒有當成操作指令或自動填值。

## ASX 欄位與合併規則

原 52 欄規格保留，擴充輸出第 53 欄為 `ASX代碼`。每個代碼均須具備文件指紋、擷取紀錄、日期、專案、公司及代碼原件證明。代碼代表證據日期的專案報告公司，不保證即時股權或上市狀態。

合併須同時符合：**非空且相同的已驗證 ASX 代碼，以及同名或明確有證據的別名**。一般 `Rare Earth Project` 字尾與大小寫可標準化；Splinter／Splinter Rock 這類別名可明列，但代碼與同一專案證據仍須成立。同公司不同專案、名稱子字串、缺代碼、輸入清單代碼均不觸發合併。

本次實際合併 **0 列**。現有私有 Splinter 與 OD6 Splinter Rock 未取得相同已驗證 ASX 代碼及同一專案證明，維持分開。Grass Patch—OD6 與 MRD Grass Patch 也不因地名相似合併。未來合併保留目標列的資源範圍，不加總或跨範圍搬數字；被吸收列與衝突另留紀錄。

Narraburra 依 [2026-10-30 Orbit 公告](https://orbitresources.au/downloads/announcements/obt_2026103001.pdf) 填 **OBT**。Wudinna 的 Cobra 為 LSE 公司，不能填成 ASX；ASX 未知也不等於未上市。

## 擷取、驗證及剩餘缺口

本輪明列 46 個 URL：取得 42 份 PDF（1,752 個實體頁面）、2 份 HTML，另 2 項為 HTTP 403 未取得。取得率 44／46＝95.7%；PDF 42／43＝97.7%；ASX PDF 39／39＝100%。NT REE factsheet 與 BHP Olympic Dam 網頁的拒絕紀錄保留，沒有將拒絕頁當成內容。
另重取遠端已採納的 3 份原件，共 431 頁，指紋與遠端證據一致；不混進 46 URL 的成功率分母。Splinter 從官方 WAMEX 公開文件清單選定 appendix.zip，再以精確 PDF SHA-256 找出指定附錄，未使用地球物理大檔，也不公開暫時儲存連結。

公告索引共 22 頁成功解析，包含 18 頁名稱／公司擴展及 4 頁整合重驗，共 1,064 個不重複公告連結。BAK／DEV 索引內容更新後保留舊指紋，重新捕獲並驗證相同公告 URL、日期及文件發行日期，不偽造舊索引內容。文件取得、索引命中及完整科學資料採納的分母不同；不宣稱每頁都完成獨立人工金標審查。

剩餘原因逐格列在 `missing_fields.csv`，按原因、專案及優先欄位另附 `remaining_gap_reasons.csv`、`project_gap_assessment.csv`、`priority_missing_fields.csv`。主要為未取得來源支持的 MRE、資源與產品組成分母不同、部分元素或氧化態不相容、勘探目標／截距不能代替資源、設計能力與平均年產不同、歷史範圍／日期不完整，以及未知公司代碼。空白保留 Unknown，不推算為零。

## 驗證與重建

詳見[結果包 validation.json](validation.json)：分開記錄固定原案、新列、ASX 新欄、遠端增量與本輪直接增量；每個已填欄位有來源紀錄，每個空白有原因。兩次完整產出的四份 CSV 均逐位元一致，原 52 欄與擴充 53 欄兩種輸出都通過稽核。

相關回歸測試 **317 項＋107 項子測試通過**；新規則針對性測試 **18 項＋21 項子測試通過**，零失敗／錯誤，兩組有重疊，不加總為獨立測試量。早先並行執行發生記憶體不足，修正後依序重跑成功；收據只使用最後通過的測試報告。

唯讀 SQLite 保持 `99ed9c0fc004960f92680ee782ef8764c189a08d98bce4d14c2d0e5ad99091d0`，未改動 canonical 資源、權利或核准紀錄。針對記憶體受限環境改採分段文件指紋及逐份 PDF 釋放圖像快取；圖像指紋、單位、來源格位與日期條件不變。測試與大型 PDF 重驗依序執行。

公開程式的重建入口：

```text
python tools/capture_research_sources.py --help
python tools/discover_asx_archives.py --help
python tools/capture_wamex_appendix.py --report 109432 --archive-name appendix.zip --expected-sha256 428c8f759ec2f4dc393177f0fccce12cc96c9b1359638d003f7ea30b6d388df7 --out work/asx-round6-splinter-replay
python tools/export_project_summary.py --help
python tools/extend_project_identity.py --help
python tools/review_external_project_names.py --help
python tools/package_asx_round6.py --help
```

數值驗證使用 `config/asx_source_reviews.json`，專案收錄使用 `config/asx_discovery_reviews.json`，ASX 與合併使用 `config/asx_project_identity_reviews.json`。資產根目錄對應見結果包的來源紀錄；WAMEX 及公開 issuer PDF、ASX 索引須重新取得並符合指定指紋。公開結果包不含原始 PDF、SQLite、頁面影像或 Gemini 原輸入列，故不是離線原件完整封裝。來源下架或變更時不得靜默替換。

已有本機證據庫時，可從隔離 repo 目錄直接執行以下 PowerShell 流程。先產原 52 欄，再附加來源驗證代碼；兩個輸出目錄必須不同。

```powershell
$assetMap = @{
  historical='work/asx-expanded-20261109'
  technical='work/asx-technical-census-expansion'
  selected='work/asx-round2-selected'
  round3='work/asx-round3-selected'
  round4='work/asx-round4-sources'
  round5='work/asx-round5-sources'
  round6='work/asx-round6-sources'
  'asx-round5-archives'='work/asx-round5-archives'
  'round6-more-archives'='work/asx-round6-more-archives'
  'round6-integration-archives'='work/asx-round6-integration-archives'
  gap_ridley='work/asx-round4-sources'
  canonical='../AU_REE_V2'
  metadata='work/asx-round6-remote-metadata'
  gap_splintercandidate='work/asx-round6-splinter-replay'
}
$assetArgs = @()
foreach ($key in $assetMap.Keys) { $assetArgs += @('--asset-root', "$key=$($assetMap[$key])") }
python tools/export_project_summary.py --root ../AU_REE_V2 --database ../AU_REE_V2/work/phase22/verified-performance-v3/isolated-round-0/after/canonical.sqlite --run-dir ../AU_REE_V2/results/phase22-2026-11-06 --as-of 2026-11-05 --review-ledger config/asx_source_reviews.json --discovery-ledger config/asx_discovery_reviews.json --out work/census-round6-base52 @assetArgs
if ($LASTEXITCODE -ne 0) { throw '來源驗證未通過' }
python tools/extend_project_identity.py --input work/census-round6-base52 --out work/census-round6-53 --identity-ledger config/asx_project_identity_reviews.json @assetArgs
if ($LASTEXITCODE -ne 0) { throw '代碼或合併驗證未通過' }
```

本輪只主張本機相關回歸與來源重放驗證；不主張整套歷史資料／R 重建、獨立全國金標驗證或新的遠端 CI 成功。所有來源取得與本機驗證詳細收據保留於結果包。
