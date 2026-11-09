# ASX 擴大驗證與 Census 總表匯出

本輪在 `experiment/asx-public-acquisition-20261109` 隔離分支開發。研究資料基準仍為
Phase 22、截止日 2026-11-05；2026-11-09 取得的新公告另存測試目錄，不改寫歷史研究結果。

## 固定測試母體與成功率

逐一核對原 manifest 中 46 份不可變 discovery receipts 的 SHA-256，從中找出
48 次 ASX 存取失敗紀錄，去除重複網址後為 **24 個公告網址、8 組發行公司搜尋脈絡**。
全部納入重測，沒有按成功與否挑選文件。

| 項目 | 結果 |
|---|---:|
| 固定母體 | 24 個公告網址 |
| 實際嘗試 | 24 |
| 取得可讀 PDF | 24 |
| 成功率（含所有母體網址） | 100% |
| 不同 PDF SHA-256 | 24 |
| 原正式 source manifest 尚無相同 SHA 的 PDF | 24 |
| 本次下載失敗／延後 | 0／0 |
| PDF 實體頁數 | 801 |
| 歷史失敗原因 | 48 次 `TERMS_INTERSTITIAL_NOT_ACCEPTED` |

這是固定歷史條款中介頁母體的成功率，不代表各類 CAPTCHA、403、429 或全 ASX 歷史公告的成功率。
同一網址重複失敗不重複增加分母；未嘗試／磁碟不足等延後狀態仍留在全母體分母。
`cohort.json` 保留每次失敗的 receipt SHA、頁面脈絡、發布日期與網址；`case_results.csv`
及 `retest.json` 保留逐筆下載結果。原始 PDF 約 69.4 MB，保留在本機測試目錄。

## 能補回的研究資料

既有 v6 文件解析器已完成 24 份文件：**691 筆候選**，包含 642 筆文字揭露、
21 筆資源表總列及 28 筆技術表格儲存格。170 筆通過局部檢查的候選全部為文字揭露；
沒有新數值完成來源、專案歸屬、資源範圍、基準與有效日期的完整核對，因此本輪新增
數值直接填入正式研究／總表的數量仍為 **0**。

| 可優先查核的欄位或構面 | 含相關頁面線索的文件數 |
|---|---:|
| 資源量、TREO 品位、含量 | 23 |
| 磁性稀土或元素組成 | 15 |
| 預估年產量／產品 | 4 |
| 開發階段 | 17 |
| Technical 資訊揭露 | 20 |

這些數字是頁面詞彙線索的文件覆蓋，不是有效數值數量。逐頁定位見
`field_opportunities.csv`，每筆候選及未通過原因見 `candidate_review.csv`。
同一候選可有多個問題，問題次數不可當作不同候選數相加。

主要瓶頸已從下載移至內容判讀：482 筆有專案歸屬歧義，96 筆涉及前瞻事項而非已完成事件，
17 筆尚無法定位 REO 定義，8 筆欄位或單位未解，8 筆屬儲量子集而非資源量。
例：North Stanmore 的更新 MRE/PFS 文件可提供資源表、工程設計與開發階段查核頁面；
Cummins Range 的冶金公告可補 Technical 證據定位；Dazzler 的資源公告不能併入
Browns Range 已選定的 Wolverine 資源範圍。各搜尋脈絡的機會見
`research_recovery_by_project.csv`，其脈絡欄位不構成專案或資源範圍等同的證據。

擴大驗證另發現既有 `number_token()` 接受 Unicode en dash 為符號，卻直接交給
`float()` 而使兩份公告整份解析失敗。本輪修正符號數值轉換，保留原始 token、區間與
負數，不把負百分比修成正數；下游百分比範圍檢查仍會拒收不合理數值。修正後兩份文件
均可解析，並保留原有的範圍／專案歧義。

## 52 欄總表的實際產出

`tools/export_project_summary.py` 已可直接讀取既有 Census SQLite，使用凍結的
snapshot lock、claims 與工程案例，依上傳 CSV 的 **52 欄順序**輸出。
範本含 92 列跨國資料，本輪不複製範本資料值，也不藉名稱相似把外國或未認定候選納入澳洲專案。

本輪明確使用：

`work/phase22/verified-performance-v3/isolated-round-0/after/canonical.sqlite`

搭配 `results/phase22-2026-11-06` 的鎖定設定。資料庫 34 個歷史 PROJECT 實體，
沿用已有證據支持的專案關係後輸出 **33 個 canonical 專案群組**，不是新增獨立專案認定。
其他原生場址、候選、礦床及礦權仍保留在 `census_inventory.csv`，不自動提升成專案。

| 總表欄位 | 已填專案群組數 |
|---|---:|
| 礦石量與 TREO 品位 | 22 |
| TREO 含量 | 22（4 案同來源明列，18 案由礦石量與品位推算） |
| 磁性 REO 比例與含量 | 12 |
| NdPr 與四項磁性元素的同範圍含量 | 1 |
| 預估年產 TREO | 1 |
| 工程案例所述產品 | 5 |
| 開發商 | 25 |
| 經緯度成對來源 | 24 |

年產量為 Koppamurra PFS 特定 12 年礦山計畫的平均 1,860 t TREO/年，
不是其全球資源的產率或已發生營運量。產品欄位保留工程案例尺度。
未上市狀態、範本分類代碼及尚無完整證據的元素／年產資料保留空白，逐格原因見
`missing_fields.csv`。不將空白寫成「否」或零。

資源數值只使用同來源、同 statement、同範圍及同有效日期的已驗證觀測；不同或嵌套範圍
不加總，也不以較新日期跨範圍挑選。推算的 TREO 含量與磁性元素量均有公式及輸入觀測 ID，
見 `field_provenance.csv`。範本「蘊藏量」欄名沿用，但資料是來源所述 Mineral Resource，
不因此轉為 JORC Ore Reserve。HREE8 沿用範本可核對的 Tb、Dy、Ho、Er、Tm、Yb、Lu、Y，
不包含 Gd；需八者皆有相容資料才計算。

本輪沒有重新計算 MCDA 或宣稱增加正式 C1 核定數。總表數值來自既有已選證據；
新下載文件的候選與總表正式欄位分開保留。

## 重跑方式

從此分支執行，`--root` 指向含完整 Phase 22 資料的既有 checkout；此測試 checkout
可保持 sparse。下載可續跑，已完成的測試不重複下載；要做另一時間點的新測試，使用新的輸出目錄。

```powershell
.venv/Scripts/python.exe tools/audit_asx_history.py --root ../AU_REE_V2 --out work/asx-expanded-20261109

.venv/Scripts/python.exe tools/export_project_summary.py --root ../AU_REE_V2 --database ../AU_REE_V2/work/phase22/verified-performance-v3/isolated-round-0/after/canonical.sqlite --run-dir ../AU_REE_V2/results/phase22-2026-11-06 --out work/census-summary-20261109 --template C:/Users/whatt/Documents/115-1_AU_REE/rare_earth_projects_classified_no_scores_2026-07-20.csv

.venv/Scripts/python.exe tools/package_asx_evaluation.py --root ../AU_REE_V2 --audit-dir work/asx-expanded-20261109 --summary-dir work/census-summary-20261109 --out results/asx-experiment-2026-11-09
```

不提供 `--template` 時使用版控中的相同 52 欄契約；提供時會檢查欄位與順序完全一致。
總表匯出採 SQLite 唯讀模式，匯出前後重新計算資料庫 SHA，來源快照亦核對雜湊。
紀錄與輸出位於 [results/asx-experiment-2026-11-09](../results/asx-experiment-2026-11-09/)。
新功能與回歸的測試紀錄見同目錄的 `validation.json`；全庫歷史重建未重跑。
