# ASX 自我迭代：四輪完成與停止審查

同一隔離分支 `experiment/asx-public-acquisition-20261109`。以 `bc6a901` 的 **55 案 × 53 欄、1,168 格有值／1,747 格空白**為固定起點，沿用 2026-11-05 研究截止日。搜尋、來源擷取與審查於 2026-11-10 完成。

**已完成四輪，第 4 輪新增 1 格，低於 3 格門檻，因此停止。** 每輪兩條搜尋線、來源驗證、測試與重複產出都完成才判停；未完成或被拒絕的搜尋不當作零收益。

## 原案補值與新案分開

| 範圍 | 案數 | 欄數 | 有值 | 空白 |
|---|---:|---:|---:|---:|
| 原始基準 | 55 | 53 | 1,168 | 1,747 |
| 同一批原案更新後 | 55 | 53 | 1,193 | 1,722 |
| 本次新增專案 | 4 | 53 | 44 | 168 |
| 目前總表 | 59 | 53 | 1,237 | 1,890 |

原案新增 **25 格，涵蓋 24 種欄位、3 個專案**，其中 20 格是固定 25 個科學數值欄位。另有來源名稱／網址 2 格更新；對初始基準的最終撤回為 0。四個新案的 44 格另列，沒有算成填掉原 1,747 個空白。

總空白變為 1,890＝原案 1,722＋新案 168；不是原案資料變少。固定原案科學欄位由 351／1,375 增至 371／1,375；擴充後為 371／1,475。資源量／TREO 品位成對列仍 31 案，年產 TREO 仍 6 案、年產 NdPr 由 5 增至 7 案，完整 HREE8 年產仍 0 案。

## 每輪實際結果

| 輪次 | 既有列新填值 | 新案數／新案填值 | 撤回 | 淨增格數 | 判停新增格 | 判斷 |
|---|---:|---:|---:|---:|---:|---|
| 1 | 24 | 1／11 | 1 | 34 | 35 | 繼續 |
| 2 | 1 | 2／22 | 0 | 23 | 23 | 繼續 |
| 3 | 0 | 1／11 | 0 | 11 | 11 | 繼續 |
| 4 | 1 | 0／0 | 0 | 1 | 1 | 停止 |

第 1 輪曾因相同 DFS 的範圍文字不同而暫留白 Yangibana 產品欄；第 2 輪以原件證明對齊後恢復。這一格**不計入**相對初始基準的 25 格新補值。各輪淨增合計 69＝25 格原案補值＋44 格新案資料。

前三輪已分別推送：[第 1 輪 bb72971](https://github.com/lleeoo0611-stack/AU_REE_V2/commit/bb7297181901791206cc35ac2c4f9c43d9defb7d)、[第 2 輪 641f5d0](https://github.com/lleeoo0611-stack/AU_REE_V2/commit/641f5d05f9243161e5d36901df42f98635bf5333)、[第 3 輪 d1860e1](https://github.com/lleeoo0611-stack/AU_REE_V2/commit/d1860e164b609e8b6b09e9d9808ee86ffee23106)。第 4 輪為本次停止審查提交。各輪僅保留精簡審查索引；權威資料在 [目前總表](../asx-current/專案總表.csv)、[逐格來源](../asx-current/field_provenance.csv) 與 [逐格缺口](../asx-current/missing_fields.csv)。

## 通過驗證的主要數值

- **WIM100／Wimmera：**[Iluka 2026-01-29 原件](https://www.iluka.com/media/0o0novln/29jan26-wim100-mineral-resource-estimate-increase.pdf)，實體第 3、4 頁同一 2026 資源列。540 Mt 是 bulk ore、25 Mt 是 HM；15 稀土氧化物百分比以 HM 為分母，排除 Sc。以同列已報告 HM 噸位計算各氧化物：NdPr **89.75 kt**、模板完整 HREE8 **112.5 kt**、15 項加總 **476.25 kt**。保留每項來源捨入區間；不把 HM 品位當 TREO 品位，也不把元素加總當來源公布的 TREO 總量。WIM100 共新增 23 格。
- **Yangibana：**[2026 年報原件](https://www.asx.com.au/asx/v2/statistics/displayAnnouncement.do?display=pdf&idsId=03146806)，實體第 9 頁同一 Stage 1、19 年 DFS、100% 專案基準，直接揭露平均年產 **3,090 t NdPr**。7 月 13 日研究日期與 9 月 30 日年報重申日期分開保留，未採峰值 37,000 tpa 精礦或按股權縮放。
- **Jupiter：**[2026-10-20 Scoping 原件](https://www.asx.com.au/asx/v2/statistics/displayAnnouncement.do?display=pdf&idsId=03154309)，實體第 21 頁 Table 4.2 同一 Base Case 的礦期平均年產 TREO 8,300 tpa，包含爬坡與排程；第 22 頁 Table 5.3 明列同模型 MREC 中 Nd₂O₃、Pr₆O₁₁ 佔含有 TREO 的 19.27%、5.51%。推導 **8,300 × (19.27%＋5.51%)＝2,056.74 tpa NdPr**。此為模型假設派生值，並非直接公布的 NdPr 年產或實際產量。來源有效位數區間 **2,043.525–2,069.965 tpa**，不包含模型不確定性。不能換用 9,300 tpa 設計欄或總 MREC 百分比。

15 氧化物齊備列由 9 增至 10，其中新增 WIM100 是 HM 基準推導；不宣稱它完成原件 TREO 總量閉合。Jupiter 的產品配分未搬作礦產資源組成，部分重稀土也未冒充完整 HREE8 年產。

## 新案、待補證與 Gemini

新增四案各 11 格身分／來源／ASX 資料，沒有新案 MRE 或年產數字：

| 專案 | 文件日期／ASX | 已驗證範圍 |
|---|---|---|
| Coburn Mineral Sands | 2023-09-06／STA | WA 採礦與含 monazite 的產品；年報簽署 9 月 5 日、ASX URL 發布 9 月 6 日分開記錄 |
| Franklyn Kaolin–REE — Nackara Arc | 2021-10-27／ITM | [iTech 年報](https://www.itechminerals.com.au/wp-content/uploads/2022/07/20211027-iTECH-MINERALS-2021-ANNUAL-REPORT.pdf)實體第 1、5 頁明列 SA 獨立命名的 Franklyn；與 Eyre Peninsula 分開，kaolin 目標與 Al₂O₃ 不作 REE 資源 |
| Southern Cross Li-REE — GCX | 2023-09-22／GCX | E77/3009–3012，與外部錯誤公司配對及同名區域分開；當期未報 MRE |
| Arunta West REE — Norwest | 2023-02-22／NWM | [Norwest 原公告](https://wcsecure.weblink.com.au/pdf/NWM/02634405.pdf)第 1、2、20 頁，WA、E80/5031，與 WA1 Luni／ENR Aileron 分開；鑽探截距不作全球資源品位 |

原四項待補證中 **Franklyn 已解決研究身分收錄，另外三項仍待補證**：Billeroo 地質複合體不能只憑名稱等同 HRE 鈾古河道；Olympic Dam 尾礦研究及 Carrapateena REE 截距尚未建立獨立、可比 REE 資源／回收專案。待補證不等於不存在或沒有 REE 潛力。

Gemini 89 列均有更新處置，**37 列已連到來源驗證身分（34 既有案、3 新案）**，比原來增加 4 列：Coburn、Southern Cross、Arunta West 及 WIM100 別名。其餘 52 列含加工／海外／錯字／區域範圍／公司不符／未驗證等處置，其中 30 列仍為未驗證線索。沒有直接匯入輸入公司的代碼或數值；原始輸入逐項對照僅在本機交付。

ASX 代碼共 **47 案有證據、12 案未知**。維持同一非空已驗證代碼且同名／有證據別名才可合併，實際合併 **0 列**。歷史文件代碼不是即時上市或法律權利認證；相同 ITM 不會把 Franklyn 與 Eyre Peninsula 合併，NWM Arunta West 不併入 WA1 Luni。

## 擷取、剩餘原因與驗證

本次審查資產集核對 15 筆 PDF 取得紀錄，去重為 14 個文件指紋、478 個實體頁面（紀錄頁數合計 511，包含重複原件）。另保留 1 個 HTTP 403 文件拒絕，停止該文件取得，未當成文件不存在。這是已審查資產集的紀錄，不代表所有搜尋命中都已下載或每頁都有獨立人工金標審查。

剩餘原因逐格及按案、按原因列於 `priority_missing_fields.csv`、`project_gap_assessment.csv`、`remaining_gap_reasons.csv`。包括無合格全球 REE MRE、HM／礦物百分比不是 TREO、產品與資源配分不同、截距／勘探目標不能替代資源、不同礦床或公司範圍、精煉廠多料源能力不能分配給單一礦山、完整重稀土元素不足、缺分類代碼簿及獨立 HTML 比較值。Circle Valley 的差值推算尚無已審核的格位推導契約，不冒充直接公布的個別氧化物。

最終相關回歸 **350 項測試＋160 項子測試通過**；Jupiter 與相關來源推導組 **64 項＋29 項子測試通過**，其中含 15 項新模型推導測試，組間有重疊。各輪兩次完整來源重放的四份 CSV 一致；來源、格位、分母、日期、錯誤案例與停止規則均有檢查。

canonical SQLite 指紋保持 `99ed9c0fc004960f92680ee782ef8764c189a08d98bce4d14c2d0e5ad99091d0`，仍為 33 canonical 群組，加 26 個研究擴充列形成總表 59 案。未新增正式 C1 或 MCDA 排名。沒有完整歷史／R 重建、全國窮盡或新遠端 CI 成功的主張。

## 可續跑與交付

操作流程及驗證入口見 [循環說明](../../docs/asx-coverage-cycles.md)。每輪審查索引會拒絕未完成搜尋線、來源／測試／重現失敗或欄位契約改變。停止表示本次完整一輪邊際新增低於門檻；未驗證值仍保持 Unknown。

公開工作樹僅保留一份目前總表及逐格資料；各輪保留精簡審查、來源配置指紋、測試與提交索引，移除本次新建的重複歷史資料副本。既有第六輪等歷史成果未整理或改寫。原 PDF、SQLite、頁面影像／全文、原始 Gemini 列與搜尋全文不公開。
