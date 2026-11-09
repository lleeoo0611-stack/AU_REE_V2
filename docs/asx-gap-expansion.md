# ASX 剩餘空白擴大擷取與補值（2026-11-09，第二輪）

沿用 `experiment/asx-public-acquisition-20261109` 及既有 Census 唯讀投影。
比較基準為前輪提交 `1c57c96` 的 33 列 × 52 欄總表：601 格已填、1,115 格空白。
本輪仍以 proposal 的原始技術資料收集及可追溯比較為目的；沒有另建研究資料庫、改變專案核定規則或重算 MCDA。

## 實際補值

新增 **126 個原空白欄格**，其中 **108 個為數值**，涉及 **32 類欄位、10 個專案群組**。
另更新 24 個既有值／來源。Cummins Range 改採同一全球範圍的 2024 MRE 後，撤下不能跨資源日期沿用的
2 個舊磁性比例／含量欄格。因此淨增加 **124 格**，已填 **725 格**、剩餘 **991 格**。
所有變動及撤值原因見 `field_changes.csv`；每個填值的來源、頁碼、範圍、轉換、日期見 `field_provenance.csv`。

| 指標 | 前輪 | 本輪 |
|---|---:|---:|
| 礦石量與 TREO 品位相容的資源組 | 23 | 26 |
| 完整 15 項資源氧化物 | 3 | 5 |
| 個別 Nd、Pr 都有資源數值 | 3 | 10 |
| 模板 HREE8 完整組合 | 3 | 5 |
| 預估年產 TREO／REO | 4 | 5 |
| 預估年產 NdPr 氧化物 | 1 | 3 |
| 預估年產完整 HREE8 | 0 | 0 |

| 群組 | 新增原空白欄格 | 核對重點 |
|---|---:|---|
| Barkly | 29 | 完整說明書內的獨立技術報告，資源總表與 15 氧化物總列 |
| Cowalinya | 25 | 同一全球資源的詳細噸位、品位與 15 氧化物，不採分層子集 |
| Donald | 19 | 明確標記 MIN5532 資源範圍，將 HM 基準換回整體礦石基準 |
| Splinter Rock | 13 | 全部資源總列的四個磁性氧化物，不只 Inside Centre |
| Salazar | 13 | Newmont＋O'Connor 全球總列，四個磁性氧化物 |
| Mount Ridley | 11 | Central Mia 固定資源範圍，四個磁性氧化物 |
| Cummins Range | 7 | 更新後 524.3 Mt 全球資源，個別 Nd、Pr 品位 |
| Circle Valley | 4 | 98 Mt、890 ppm 的正式 Inferred MRE，不採 13 Mt 子集 |
| Nolans | 3 | 2026 澄清公告的平均年產 REO 5,013 t、NdPr 4,440 t 與產品 |
| Dubbo | 2 | 2025 Scoping Study 的 LOM 平均 NdPr 氧化物 1,037 t/年與產品 |

這些欄位仍是來源限定的 Mineral Resources／工程預測；模板既有「蘊藏量」欄名不表示一律為 Ore Reserves。
HREE8 沿用模板定義 Tb、Dy、Ho、Er、Tm、Yb、Lu、Y，不能用來源其他 HREO 定義直接代替。

## 來源與驗證

25 組累積來源審查中，本輪新增 16 組，包括明確拒填的來源審查；累積形成 128 筆資源觀測及
8 個年產工程參數，這些數字不是 128 個新欄格或獨立第三方核准數。

- Barkly：完整技術報告物理第 189 頁表 9-2／9-3，資源生效日為 2025-11-17。
  40 Mt、2,100 ppm 與 82,000 t 都保留原報告的捨入精度；不把由捨入輸入乘出的 84,000 t 當成來源更正。
  15 氧化物加總與 TREO 的差異按原表有效位數檢查。說明書發行日 2025-12-01、ASX 上架日
  2026-01-28 分別記錄；ASX 日期必須在已雜湊的原始索引中與同一文件網址相符。
  亦查閱 2026-01-08 補充說明書，其內容調整發行條件，未以其取代技術資源表。
- Cowalinya：2023 原公告第 16／17 頁的 All 總列，158.9 Mt、870.3 ppm。
  保留與後續年報相同的資源範圍，採詳細精度；未把 159 Mt／870 ppm 與另一範圍成分混用。
- Donald：第 6 頁表 6 的 530 Mt 是 MIN5532，並非整個 Donald／Jackson 礦區。
  原表 1.4% TREO 是 **HM 內的比例**；總 HM 為整體礦石的 4.0%，所以整體 TREO 品位為
  `4.0 × 1.4 / 100 = 0.056%`。六個個別氧化物亦以同一 HM 比例換算。
  新增名稱尾註 `MIN5532 resource scope`，防止將此範圍誤讀為全部專案。
  公告標頭日期 2026-02-27 與索引日期 2026-03-02 的差別保留在來源審查檔。
- Nolans：採 2026-06-17 澄清公告第 15 頁 Average REO 總列，屬來源報告的 REO 產品基準，
  不自行以未定純度推算更多小數。其平均排除兩年 ramp-up 及末期低品位庫存處理；不是設計值 4,518 tpa
  或高峰值 4,700 tpa，也不是整個 38 年含啟停期的算術平均。
- Dubbo：採第 17 頁 LOM 的 1,037 tpa，不採第 3–15 年的 1,157 tpa；不將 Dy＋Tb 直接當作 HREE8。
- Jupiter：補查 2026-10-12 最新資源公告。來源將部分氧化物分別列在 Indicated／Inferred 類別，
  沒有可直接選用的全球成分總列；不把捨入的分類噸位拼成精確的全球元素表，也不借用已被更新的 2025 成分。
  因此這次補查增加來源限定的拒填原因，沒有再增加填值。

原始表頁均以原生文字定位，關鍵資源總列與 Nolans 工程表另做視覺核對。
Barkly 的旋轉原表以固定渲染雜湊綁定；初次審查檔多輸入一個雜湊字元時，匯出器確實停止，修正後才通過。
SHA 綁定能防止來源被替換，本身不能證明人工抄錄正確；本輪不是獨立人工金標驗收。

## 取得統計及範圍

搜尋 27 個發行公司、2023–2026 年共 108 個索引頁：96 頁可解析，12 頁回傳 HTTP 200 的
`Request Rejected` HTML。這 12 頁屬 ASR、GRL、LNR 各四年，明確列為失敗，不能當成沒有公告。
修正亦重查先前快取的索引頁，保留原始回應 SHA 及原有狀態。

技術標題關鍵字清單內找到 118 個網址，全部取得可讀 PDF；另補查 7 個明確找到的 ASX 網址，
包括 Nolans、Barkly 與 Jupiter。相較前輪 61 個已取得網址，本輪新增嘗試 **80 個網址，80 個成功、0 個 PDF 失敗**；
累積 **141 個不同網址、141 個不同 PDF SHA**。118 份技術關鍵字 PDF 擷取 4,247 頁原生文字。
索引失敗與 PDF 成功使用不同母體，不合併宣稱所有 ASX 存取都成功。

這是固定公司、年度與標題條件的搜尋範圍，不是 ASX 全歷史普查。原標題條件包含 Mineral Resource、MRE、
metallurgy、feasibility、PFS、DFS、scoping、JORC、recovery、production；只寫 Resource、季度報告、年報或
一般簡報的文件可能漏出該條件，本輪亦因此補查完整索引中的明確候選。
結果中含金礦、銻礦、鋰礦、其他資產與設施；`document_dispositions.csv` 區分已審查來源、
其他資產標題及未完成內容審查，取得文件並不自動獲准補值。

## 剩餘 991 格

41 個仍空白的欄格附有已核對原文的特定拒填原因，其餘保留未知／尚無相容驗證來源等原因。
`missing_fields.csv` 是全部 991 格；`priority_missing_fields.csv` 是本輪資源、組成與年產量優先欄位；
`project_gap_assessment.csv` 涵蓋全部 33 個群組。空白不等於來源未揭露或專案不存在。

資源量／品位仍空白的七個群組如下：

- Burracoppin：原表的 -45 µm 細粒分率、整體噸位與含量仍需協調，未強配數值組。
- Greater Brothers：已有 Jupiter 位於 Brothers 的脈絡，不代表 Brothers 與 Jupiter 的資源可重複填列。
- Splinter：沿用其獨立 Census 身份，未以 OD6 Splinter Rock 的同名片段替代。
- Fingerboards：現有規劃產能／流程資料尚不能代替本輪所需的相容資源噸位與 TREO 品位。
- Lyons：原始表列 `2,266 + 670 = 2,936 t`，不等於其總列 `3,221 t`，沒有擅改來源數字。
- Mt Stirling：目前仍缺本輪可核對並選用的原始技術資源組。
- Kalkaroo：現有 REE 潛力／勘探資料尚不能當作正式 REE MRE。

完整 15 項成分仍缺 28 組；年產 TREO、NdPr、HREE8 分別仍有 28、30、33 個空白。
其他關鍵拒填包括：精礦質量不等於含 TREO 質量、NdPr 元素／氧化物基準不明、SEG/HRE 不等於 HREE8、
只有擴產設計能力而沒有平均年產量、不同生產階段未提供單一 LOM 年產量，以及只披露合併 NdPr 而沒有
符合模板「兩者皆公布」的個別 Nd、Pr 資源數值。分類代碼及 HTML 比較欄亦不能由技術數字推造。

## 測試及重跑

184 項相關回歸測試及 8 個子案例通過；最終針對性重跑為 67 項及 8 個子案例，屬重疊測試，不能相加成獨立測試數。
包括錯單位、HM 基準換算、資源類別、來源及索引竄改、日期角色、錯誤渲染雜湊、來源範圍標示、
同一 PDF 不同 statement 的選用、撤值與淨新增計算。兩次匯出的四個 CSV 雜湊完全一致。
正式 SQLite SHA 仍為 `99ed9c0fc004960f92680ee782ef8764c189a08d98bce4d14c2d0e5ad99091d0`，未修改。
資料時間截止仍為 2026-11-05；本輪取得／審查截至 2026-11-09，屬原始歷史文件的回溯補充。
原始 PDF、整頁文字、渲染影像及 SQLite 都留在本機，公開成果只含程式、測試及派生表／來源紀錄。

```powershell
.venv/Scripts/python.exe tools/expand_asx_technical.py --root ../AU_REE_V2 --out work/asx-technical-census-expansion --max-documents 130 --years 2026 2025 2024 2023 --issuer-code ARU --issuer-code ATR --issuer-code MRD --issuer-code HRE --issuer-code KTA --issuer-code MQR --issuer-code GRL --issuer-code LNR --issuer-code MEK
.venv/Scripts/python.exe tools/fetch_asx_selected.py --requests config/asx_round2_selected_urls.json --out work/asx-round2-selected
.venv/Scripts/python.exe tools/export_project_summary.py --root ../AU_REE_V2 --database ../AU_REE_V2/work/phase22/verified-performance-v3/isolated-round-0/after/canonical.sqlite --run-dir ../AU_REE_V2/results/phase22-2026-11-06 --out work/census-asx-round2 --review-ledger config/asx_source_reviews.json --asset-root historical=work/asx-expanded-20261109 --asset-root technical=work/asx-technical-census-expansion --asset-root selected=work/asx-round2-selected --asset-root canonical=../AU_REE_V2
.venv/Scripts/python.exe tools/validate_asx_candidates.py --root ../AU_REE_V2 --audit-dir work/asx-expanded-20261109 --review-ledger config/asx_source_reviews.json --before results/asx-validated-summary-2026-11-09 --after work/census-asx-round2 --out work/asx-round2-comparison
```

重複匯出時改用 `work/census-asx-round2-repeat`。結果包與驗證收據位於
[`results/asx-gap-expansion-2026-11-09`](../results/asx-gap-expansion-2026-11-09/)，測試 XML 雜湊、程式指紋及所有成果雜湊見 `validation.json`。
