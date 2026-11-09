# ASX 第三輪搜尋、驗證與總表補值

沿用 `experiment/asx-public-acquisition-20261109`。本輪基準為 `7ca6047` 的 33 列 × 52 欄總表，
原已填 725 格、空白 991 格。研究目的仍是 proposal 所需的來源可追溯資料收集、資源／產品範圍比較，
不是新增正式核准專案或改算 MCDA。研究資料截止 2026-11-05，取得／審查跨午夜至 2026-11-10。

## 補值結果

新增 **68 個原空白格**，其中 **58 個為數值**，涉及 **33 類欄位、5 個專案群組**。
另有 **12 格既有值／來源更新**及 3 格純數字格式差異，撤回 0 格。淨增加 68 格，
總表現為 **793 格已填、923 格空白**，列數、專案 ID 與 52 個欄名都不變。

| 專案 | 新增空白格 | 核對後採用的內容 |
|---|---:|---|
| Redlings | 25 | 2025-01-22 原始 MRE 的 800 ppm cutoff 全球 Inferred 總列、15 項氧化物 |
| Kennedy | 24 | 2025 年報重新確認未變的 150 Mt／1,000 ppm MRE，15 項氧化物與開發商 |
| Yttria | 12 | 日期明確的 2024 原始 MRE，個別 Pr、Nd、Dy、Tb 與開發商；2025／2026 刊載資料核對相同表 |
| Fingerboards | 5 | 政府 prospectus 所載 2022 年 8 月全球 Mineral Resources：1,170 Mt、0.05% TREO＋Y₂O₃、580 kt |
| Donald | 2 | 同產品表年產精礦量、TREO 品位、Nd／Pr 氧化物比例換算的年產 TREO、NdPr |

| 指標 | 本輪前 | 本輪後 |
|---|---:|---:|
| 資源量／TREO 品位可用組 | 26 | 27 |
| 完整 15 項資源氧化物組 | 5 | 7 |
| 個別 Nd、Pr 皆有數值的組 | 10 | 13 |
| 模板 HREE8 完整組合 | 5 | 7 |
| 預估年產 TREO／REO | 5 | 6 |
| 預估年產 NdPr 氧化物 | 3 | 4 |
| 預估年產完整 HREE8 | 0 | 0 |

HREE8 沿用模板的 Tb、Dy、Ho、Er、Tm、Yb、Lu、Y，不以其他 HREO 定義或 Dy＋Tb 代替。
模板的「蘊藏量」仍可涵蓋來源限定的 Mineral Resources，不表示所有數值都是 Ore Reserves。

## 七個資源缺口的處置

| 專案 | 處置與仍空白原因 |
|---|---|
| Fingerboards | 已補。來源是政府項目目錄，清楚保留 `GOVERNMENT_PROJECT_CATALOGUE`；不是重新完成發行公司的原始 JORC 技術驗證。選資源總列，沒有取 173 Mt reserve。 |
| Burracoppin | 保留空白。原表 35.709 Mt 是 bulk，14.731 Mt 是 -45 µm 細粒；1,356.4 ppm 與 20,000 t 對應細粒。不能直接與 bulk 噸位相乘，也未將細粒產品量改稱整體礦石量。 |
| Greater Brothers | 保留空白。Jupiter 是 Brothers 六個發現之一；沒有另外選用可與 Jupiter 分開計數的母專案資源總量。 |
| Splinter | 保留空白。政府表確有 22.90 Mt／0.11%／25 kt 與 2015 日期，但尚未取得可核對原始技術報告及日期的發行公司來源；不借用 OD6 Splinter Rock。 |
| Lyons | 保留空白。原表 2,266＋670＝2,936 t，與總列 3,221 t 不符；2026 Fortuna 年報僅在管理層經歷重述 0.99 Mt／0.32%，未提供解決衝突的更正表。 |
| Mt Stirling | 保留空白。原始 MRE 與較新 GoldArc 年報確認 15 Mt／490 ppm 是 Yttria 已計數資源；110–300 Mt 則是 Exploration Target，不能再填作另一資源。 |
| Kalkaroo | 保留空白。核對原件為 REE 潛力與擬進行的礦物／冶金研究，未選用相容的 REE MRE；沒有轉用 Cu／Au／Co 噸位或局部樣品品位。 |

因此七個原缺口補齊一個，仍缺資源量／品位六個。保留空白不代表沒有資源或沒有後續公告。
全部七案及成分／年產審查，共 17 組搜尋處置、19 次來源引用，均重新核對 URL、PDF SHA 與實際頁面標記。
逐案見 `research_gap_reviews.csv`；923 個欄格的原因見 `missing_fields.csv`，兩者須一起讀。

## 關鍵驗證與限制

- Kennedy 早期原始表把 Ho₂O₃ 誤印為 H₂O₃；本輪另找 DevEx 2025 年報，物理第 65 頁改為正確 Ho₂O₃，
  並明確聲明原 2024 MRE 未變。選 325 ppm cutoff 的 150 Mt 總列，不選 88 Mt 高 cutoff 子集。
- Redlings 第 2 頁 800 ppm cutoff 列：11 Mt、1,130 ppm，15 氧化物加總 1,132.12 ppm，按原表捨入精度檢查。
  原表 Y₂O₃ 為 0.05 ppm，保留原值，不因數值不尋常而自行替換；204–306 Mt Exploration Target 不納入。
- Yttria 2025 季報封面「季度截至 30 June 2025」曾被解析器誤作公告日，本輪改為排除這種期間標題。
  採日期明確的 2024 原 MRE，並以後續季報／GoldArc 年報的相同表作佐證；未偽造季報公告日期。
- Fingerboards 政府文件網址含 March 2026，前言卻明載 February 2026 edition。本輪按文件內容保留
  發行區間 2026-02-01～02-28；資源日期 Aug-22 保留 2022-08-01～08-31。
  系統選用區間上界作排序值，來源明細同時輸出完整區間，不宣稱知道精確發行／資源日。
- Donald 2026-02-27 公告第 3 頁表 4 的 **2025 REEC Product** 同列：年產精礦 7,100 t、
  TREO 60.6%，Pr₆O₁₁ 與 Nd₂O₃ 分別占 TREO 的 3.9%／13.9%。
  `7,100 × 60.6% = 4,302.6 t TREO/年`；再乘 `(3.9%＋13.9%)` 得 `765.8628 t NdPr 氧化物/年`。
  這是從捨入輸入算出的未捨入算術值，多餘小數不代表測量精度。來源明細保留公式、輸入、單位、頁碼及渲染 SHA。
  沒有拿 2023 產品列、礦石資源品位、前五年 Dy／Tb 產量或 Phase 2 混算。三月報告佐證 7.1 ktpa，
  沒有提供替代的產品品位，故明確選二月完整匹配表。Dy＋Tb 仍不足以填 HREE8。

其餘年產缺口包括 North Stanmore 的 Average/dt 表沒有明確年度分母、Goschen 精礦質量與 NdPr
元素／氧化物基準仍未核清、Cummins Range 分階段年產數字沒有可選的單一 LOM 平均、Nolans 的 SEG/HRE
不是模板 HREE8，以及 Fingerboards 產品表的設計產率／未明元素基準，均保留原因與未知值。
完整 15 項成分仍缺 26 組；年產 TREO、NdPr、HREE8 分別仍空白 27、29、33 組。
分類代碼、HTML 比較值與未取得證據的欄位不由技術數字推造。

## 搜尋與取得統計

原有 27 個公司代碼 × 四年的 108 頁索引保持歷史收據：96 可解析、12 次 HTTP200 拒絕。
本輪新增 FUN／GA8 × 2023–2026 共 8 頁，8 頁可解析；其中四個舊年度頁沒有帶日期的 PDF 連結，
這是該代碼／年度索引的結果，不能解讀為沒有歷史公告。新索引找到 225 個不同的帶日期公告連結，未全部下載。

本輪選取 6 個新 ASX 公開原件網址，**6／6 取得可讀 PDF、0 PDF 失敗**，共 410 頁：
Redlings MRE、Narraburra MRE、Redlings 新簡報、DevEx 年報、Fortuna 年報、GoldArc 年報。
與前輪合計 **147 個不同網址／147 個不同 PDF SHA**。部分新文件只提供佐證或拒填原因，不等於增加六個資源案。
舊技術關鍵字集合仍為 118 PDF／4,247 頁，不把本輪 410 頁混列成舊集合的新擷取數。
17 份被搜尋審查引用的不同文件共有 1,116 頁，表示文件長度，並非逐頁人工金標驗收頁數。

## 測試與重現

200 項相關回歸測試及 11 個子案例通過；最後針對性測試 84 項及 11 個子案例通過，兩組有重疊。
覆蓋月份上下界、網址月份誤用、季度截止日、來源 URL／SHA／頁面標記、精礦量與含氧化物量、
百分比分母、缺 Pr、錯產品列／頁面、未審查渲染列、HTTP200 拒絕、索引快取竄改與既有研究流程。
兩次匯出的四個 CSV SHA 一致。原始 SQLite SHA 維持
`99ed9c0fc004960f92680ee782ef8764c189a08d98bce4d14c2d0e5ad99091d0`，未修改。
沒有宣稱重建全部歷史研究或通過遠端 CI。原始 PDF、整頁文字、影像及 SQLite 不公開推送。

```powershell
.venv/Scripts/python.exe tools/discover_asx_archives.py --issuer-code FUN --issuer-code GA8 --years 2023 2024 2025 2026 --out work/asx-round3-archives
.venv/Scripts/python.exe tools/fetch_asx_selected.py --requests config/asx_round3_selected_urls.json --out work/asx-round3-selected
.venv/Scripts/python.exe tools/export_project_summary.py --root ../AU_REE_V2 --database ../AU_REE_V2/work/phase22/verified-performance-v3/isolated-round-0/after/canonical.sqlite --run-dir ../AU_REE_V2/results/phase22-2026-11-06 --out work/census-asx-round3 --review-ledger config/asx_source_reviews.json --asset-root historical=work/asx-expanded-20261109 --asset-root technical=work/asx-technical-census-expansion --asset-root selected=work/asx-round2-selected --asset-root round3=work/asx-round3-selected --asset-root canonical=../AU_REE_V2
.venv/Scripts/python.exe tools/validate_asx_candidates.py --root ../AU_REE_V2 --audit-dir work/asx-expanded-20261109 --review-ledger config/asx_source_reviews.json --before results/asx-gap-expansion-2026-11-09 --after work/census-asx-round3 --out work/asx-round3-comparison
.venv/Scripts/python.exe tools/audit_asx_gap_sources.py --config config/asx_round3_gap_research.json --asset-root historical=work/asx-expanded-20261109 --asset-root technical=work/asx-technical-census-expansion --asset-root selected=work/asx-round2-selected --asset-root round3=work/asx-round3-selected --asset-root canonical=../AU_REE_V2 --out work/asx-round3-research
```

重複匯出改 `--out work/census-asx-round3-repeat`。派生表、變動清單、完整缺口、逐案審查與測試／雜湊收據
在 [`results/asx-gap-round3-2026-11-10`](../results/asx-gap-round3-2026-11-10/)。
