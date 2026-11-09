# ASX 候選驗證與實際補值（2026-11-09）

本輪沿用 `experiment/asx-public-acquisition-20261109`，將前輪 691 筆候選逐筆記錄
專案、單位、資源範圍與日期檢查，並重新核對可用原表，讓通過來源審查的資料實際補入總表。
33 個既有 canonical 群組及 52 欄契約保持相同。

## 實際增量

| 項目 | 前版 | 補值後 |
|---|---:|---:|
| 總表列數／欄數 | 33／52 | 33／52 |
| 已填欄格 | 523 | 601 |
| 有相容礦石量與 TREO 品位的群組 | 22 | 23 |
| 完整 15 項資源氧化物資料 | 0 | 3 |
| 可計算 NdPr 資源氧化物含量 | 1 | 3 |
| 可計算模板定義 HREE8 含量 | 0 | 3 |
| 有預估年產 TREO | 1 | 4 |
| 有預估年產 NdPr | 0 | 1 |
| 有工程產品資料 | 5 | 7 |

**新增 78 個原空白欄格，涵蓋 35 類欄位、6 個群組，其中 63 個是數值欄格。**
另外有 14 個既有值／來源更新，1 個單純數字格式變化未算成新資料。
逐格前後值、來源、頁碼、方法與日期角色見 `field_changes.csv`；所有新舊欄位的來源見
`field_provenance.csv`。`專案總表_補值前.csv` 保留比較基準。

補值來自 9 組來源審查，涉及 7 份不同 PDF，形成 55 筆資源觀測及 5 個工程年產參數。
完整來源審查資料見版控中的 `config/asx_source_reviews.json`，成果包另附 `source_reviews.json`。
這包括對原解析器未完整辨識的表格重新擷取，不把全部新增值冒稱為原 691 筆候選直接通過。

本輪重要處理如下：

- North Stanmore：選用明列的 August 2026 全球 MRE，不將高品位子集與全球資源相加。
  以物理第 136 頁原始影像總列核對 15 項氧化物，並以第 97 頁原生文字總表交叉核對。
  全球資源為 278.802 Mt、482.64 ppm TREO；原始噸轉 Mt、品位轉百分比及含量推算均有紀錄。
  這是明示的全球資源選用規則，不是跨範圍自動挑最新日期。
- Koppamurra：採全球 243 Mt 資源表的 15 項氧化物，不採 26 Mt Ore Reserve 或 Exploration
  Target 的成分表。工程年產量則綁定另一個 12 年 PFS 礦山計畫及最終煅燒氧化物產品。
- Wolverine：採 Total Mineral Resource 表，包含露天及地下，排除 Dazzler 和試驗廠庫存。
  同來源明列的 70.5 kt TREO 取代原來依捨入輸入推算的 70.08 kt；相容性按來源有效位數檢查。
  不將 Dazzler 的更新 MRE 或 Wolverine–Dazzler 混合試驗變成 Wolverine 資源成分。
- 工程產出：Yangibana 用修訂版 DFS 的平均每年 8,524 t **含於精礦中的 TREO**，不採
  37,000 tpa 高峰精礦量。Browns Range 用表列 4,350 tpa TREO；Jupiter 用 Base Case
  8,300 tpa，而非 nominal process-design 的 9,300 tpa。兩者均保留各自計畫、產品與尺度。

上述數值的原始頁面、表頭／總列標記、源 SHA、單位轉換及日期角色均在審查檔中。
影像表格採原頁視覺核對、重算影像雜湊及獨立原生總表交叉檢查；SHA 本身不證明抄錄正確。
本輪審查不是獨立第三方核准，也沒有新增正式 C1 核定或重算 MCDA。

## 691 筆原候選的判定

| 判定 | 筆數 |
|---|---:|
| 可定位的局部文字脈絡，不能直接當數值總表欄位 | 524 |
| 前瞻事項，不能當已完成開發階段 | 88 |
| 試驗儲存格，不能直接作專案資源或年產量 | 28 |
| 與已審查全球資源總列相符的佐證 | 2 |
| 儲量子集，排除於資源欄位 | 8 |
| 資源單位、範圍或有效日期仍待核對 | 10 |
| 專案歸屬仍待核對 | 30 |
| 其他科學語境仍待核對 | 1 |

共 691 個不同候選 ID，沒有刪除原始問題。`candidate_validation.csv` 每筆保留四項檢查、
原問題、後續問題、審查連結與最終用途。局部文字脈絡可定位不等於完整科學數值驗證。
發布日期亦分成標頭確認或不可變公告索引紀錄；不直接當成資源估計的有效日。

## 擴大技術公告取得

從既有 Census 原始身份文件可直接建立 ASX 代碼的 18 個發行公司出發，查閱 2025、2026 年
共 36 個公告頁。45 個符合技術關鍵字的公告網址全部取得可讀 PDF，其中 37 個為前輪 24 個
網址以外的新下載網址。合併兩輪為 61 個不同網址、61 個 PDF SHA；本輪 45 份共擷取 1,350 頁
原生文字。

這是既有發行公司、兩個年度與技術標題關鍵字下的固定搜尋範圍，不是 ASX 全歷史普查。
關鍵字結果含其他礦種、其他資產及海外設施，例如 Mt Lindsay、Star of Mangaroon 或 Thailand
產能消息；公司代碼不能證明其屬於 Census 中某個 REE 專案，這些結果不自動補入總表。
`technical_discovery.json` 保留完整搜尋母體及結果，`technical_downloads.json` 保留逐筆取得狀態，
`technical_native_inventory.json` 保留原文頁數、雜湊與名稱脈絡；名稱脈絡不構成實體等同。

## 剩餘缺口

仍有 **1,115 個空白欄格**，包含尚無相容來源、分類交叉表未定及原 HTML 專屬比較欄；
不能將所有空白都視為公告未揭露。其中：

- 10 個群組仍無可選用的完整資源數值組；30 個仍無完整 15 項／HREE8 組合。
- 年產 TREO、NdPr、HREE8 分別仍有 29、32、33 個空白。
- North Stanmore 的 production 表用 `dt` 與 Average，未在該表明示年度時間基準，
  不把乾噸平均值逕填 t/年。Goschen 的 8,300 tpa 是精礦質量，不是含 TREO 質量；
  其 Nd-Pr 表格也尚未明確區別元素與氧化物基準。
- 礦石／Ore Reserve 的 NdPr 比例不能直接乘上平均年產 TREO，作為年度產品組成；
  Dy/Tb 合計或其比例亦不等於模板的完整八項 HREE。
- 新增 `iac` 僅採 Koppamurra 明確的 ionic adsorption clay 描述；不把一般 mixed-clay
  或 regolith-hosted 資源直接歸為離子吸附型。開發階段代碼仍不從過去完成的研究日期推定。

逐格原因見 `missing_fields.csv`，已查核但不適合換算的 12 格另保留源 SHA、頁碼與審查 ID。
有效日期角色明確區分估計生效日、發布時重申以及工程預測發布日；只有月份／年份可確認時，
保留精度及截至發布日的區間，不捏造精確估計日。

## 架構與重跑

正式 SQLite 及 Phase 22 截止日／結果保持不變。匯出器使用同一 Census 的唯讀資料，
加上逐次執行均會重新驗證的來源審查紀錄，形成可重跑的表格投影；沒有第二個研究資料庫。
新原文的取得日為 2026-11-09，來源發布及數據時間仍受 2026-11-05 截日限制。

```powershell
.venv/Scripts/python.exe tools/expand_asx_technical.py --root ../AU_REE_V2 --out work/asx-technical-census-expansion --max-documents 60

.venv/Scripts/python.exe tools/export_project_summary.py --root ../AU_REE_V2 --database ../AU_REE_V2/work/phase22/verified-performance-v3/isolated-round-0/after/canonical.sqlite --run-dir ../AU_REE_V2/results/phase22-2026-11-06 --out work/census-validated-asx --review-ledger config/asx_source_reviews.json --asset-root historical=work/asx-expanded-20261109 --asset-root technical=work/asx-technical-census-expansion

.venv/Scripts/python.exe tools/validate_asx_candidates.py --root ../AU_REE_V2 --audit-dir work/asx-expanded-20261109 --review-ledger config/asx_source_reviews.json --before work/census-summary-20261109 --after work/census-validated-asx --out work/asx-validation-results
```

原 24 份與 691 候選可用前輪 `audit_asx_history.py` 重建；新下載可續跑。原始 PDF、
原頁影像、完整文字及 SQLite 保留本機，不包含在公開成果包。若 ASX 後續改換位元組，
來源 SHA 或影像雜湊不符時會停止審查，不自動沿用舊抄錄。

成果目錄：[asx-validated-summary-2026-11-09](../results/asx-validated-summary-2026-11-09/)。
174 項相關回歸及 8 個子案例通過；後續來源審查／匯出測試另通過 34 項，包含錯單位、
日期不符、跨專案、影像不符、氧化物總和衝突與缺少年產時間基準的拒收案例。
重跑總表的四個 CSV 雜湊一致；測試與來源驗證收據見 `validation.json`。全庫歷史重建未重跑。
