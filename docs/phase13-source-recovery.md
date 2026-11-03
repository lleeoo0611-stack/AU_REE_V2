# Phase 13：來源搜尋與有效證據回復

由 Phase12 `97ea5e84add91e35e4c6c879e7a4c5c730abc7f7` 建立 `feat/phase13-source-recovery`，獨立 Draft PR 以 Phase12 分支為base，不合併既有PR。沿用 `work/phase5/canonical.sqlite`、Python CLI與R引擎。研究截止2026-11-03、取得視窗至2026-11-04、正式Gate cutoff2026-10-29不變。

## 實際增量

| 指標 | Phase12 | Phase13 |
|---|---:|---:|
| Canonical registry groups | 31 | 31 |
| Resource-defined分析案例 | 22 | 21 |
| 選定來源快照，含搜尋／解析版本 | 121 | 204 |
| PDF entries／不同PDF SHA | 49／47 | 54／52 |
| 辨識文件／候選 | 25／1330 | 27／1761 |
| 現行文件驗證觀測，含文字NULL | 442 | 528 |
| Selected validated numeric statements | 292 | 315 |
| 結構化事件 | 21 | 21 |
| 可評分R／S／T／D／I／C | 22／10／0／9／20／8 | 21／10／0／9／19／8 |
| Strict Development／Full evidence／Formal C1 | 0／0／0 | 0／0／0 |

**總新增25個核實的原始數值，排除2個既有錯誤分類，淨增23。** 16個由AI協助定位轉錄，再由工具及原頁檢查，不宣稱獨立人工審查或簽核；9個是自動raw observations，不是正式準則。

- 原文件找回8格：Cummins MRE2023 p2的Rare Dyke／Phos Dyke／Combined各自tonnage與正確TREO，共6格；Browns Range2025 p55的DFS＋stockpile scope共2格。不同範圍不相加。
- 新文件自動1格：Cummins2026 p2引述BTMR歷史最高48.74%浮選回收率，僅為歷史披露，不是目前整體回收率。
- 新轉錄16格：North Stanmore新版全球MRE tonnage／grade2格；Cummins SGS六種test/product的品位／回收率12格，以及feed grade／test count2格。
- Wudinna含水率13.3%、Mt Weld尾礦品位7.3%不再作extraction。Circle Valley最高82%、平均76%的並列句有效觀測保留；敏感度圖百分比不作回收率。

### 文件身分

1. Cummins metallurgical program，2026-07-13，13頁。[發行人公告](https://rarex.com.au/announcements/RQE895-cummins-range-metallurgy-program-delivers-strongest-results)連結的[公開PDF](https://hermes-cdn.investorhub.com/announcement-pdfs/asx/7629289.pdf?v=63951121196)，SHA `8f549e413628e9ff57471f039d909e8ef7fad226660dd0c717a959b2441e9d46`。
2. North Stanmore MRE／Reserve／PFS，2026-08-18，167頁。[公開申報頁](https://financialfilings.com/filings/victory-metals-limited/regulatory-filings/2026/56486208/)的[報告副本](https://cdn.financialreports.eu/financialreports/media/filings/66026/2026/RNS/66026_rns_2026-08-18_945f843e-1282-40b7-9382-0f85251f5650.pdf)，SHA `de5b5c737eb582bb2092d84bb900ecb7a27fb321fe7ecd58d38f2b5c834a5831`。發行人撰寫、公開鏡像保存；host不是發行人或ASX，不宣稱與交易所下載位元組相同。

兩個成功入口由本次實際工具搜尋補得，再進入原有acquisition／manifest；North Stanmore回復先前逾時的文件身分。不能宣稱這是CLI自動網搜成功。另3份VHM環境／許可PDF未形成有效數值，保留原件，不以下載數擴大樣本。

## Discovery及下載恢復

`search_tasks()`重用Project、alias及Source Registry，從已驗證PDF首頁讀取單一明示ASX code；多code或無code保持Unknown。Criterion轉成技術文件詞，不把R1／T1當有效網搜。公司端點、WordPress查詢、官方ASX年度索引與已知公司名稱的公開申報索引共用 `discover()`／`candidates()`。

設定每來源3頁／3文件、最多2查詢、10個官方年度索引及2個公開鏡像索引；首頁、搜尋、分頁、detail與fallback共用預算。年度視窗保留2026，沒有搜尋所有年份的宣稱。

初次live receipt有84個來源項目、131個文件候選：42 PARSED、32個原件重用項目、10個來源失敗；3份新PDF、24個文件失敗、65個預算暫緩。**84不是84個有效搜尋頁**，其中還含重用及16個曾由`Shareholders`子字串誤作`older`的terms頁。已改單字界線並排除PDF／公告下載連結，加入回歸測試；診斷排除terms頁及原件重用的搜尋頁計數。

最後以相同已存頁面與文件預算對照：10個年度索引、24個文件候選、0次網路傳輸，標明 `ARCHIVED_SOURCE_PAGE_REPLAY_NO_NETWORK`。不是新搜尋或取得。MRE／PFS／DFS／選冶排序優先於AGM／proxy／webinar；這是檢索啟發式，不是科學品質分數。

公司網站429、鏡像HTML索引403、ASX條款頁與配送入口404均有紀錄。ASX ID推組配送URL的試驗無成功，已移除未獲證實的映射。沒有接受條款、使用隱藏保護連結、繞過CAPTCHA／反自動化保護，也未呼叫缺乏權限的一般網搜API。

`request()`區分429／403／404／timeout／非PDF／terms。暫時失敗最多3次，遵守 `Retry-After`秒數或HTTP日期；超過30秒要求直接延後，不截短後提前重試。同host至少間隔0.25秒。失敗局部隔離，既有原件先驗SHA再重用，保留來源、日期與失敗紀錄。

## 解析、可比較性與評估

新parser／layout版本綁定native cell、header、token、unit及bbox，處理空白前置欄、分類欄與TREO＋Y₂O₃，避免P₂O₅、density、TREO−Ce等錯配。舊版本保留。SHA及backend相同的native table cache可重用，測試確認與fresh parse完全一致，減少重複表格偵測。

百分比必須有直接數量語意或明確最高／平均並列句。粗選、一次／二次精選及feed分開；Cummins CRCS-10是選擇性高品位複合樣，LABORATORY scale、未完整定義的test REO sum及代表性限制均保留，不進DFS／整體T1。

North Stanmore p136的個別REO數值是低解析度內嵌影像。僅針對該頁試200／600dpi，再針對必要區域試400dpi OCR；小數點仍不可靠，保留失敗衍生版本、model SHA、clip及原文字，**不補小數點、不推算S1**。沒有對全PDF全面OCR。

| 同一開發集22格 | Phase12 | Phase13 |
|---|---:|---:|
| TP／FP／FN | 5／0／17 | 13／0／9 |
| precision／recall | 1／22.7% | 1／59.1% |

13格的Project/table-heading scope、unit及locator指標為1，不代表canonical resource admission。額外Salazar／Burracoppin兩份文件有6個正例格：0TP／0FP／6FN，另1個粒徑／kaolin負例正確拒絕。它們未用於此次欄位修復，但不是獨立人工標註盲測；不合併成全澳準確率。Wudinna及Mt Weld原頁錯誤候選各1→0，p21另一尾礦負例保持0。

## Coverage、研究結果與實體

`source_document_coverage.csv`重用Selection、Manifest、Document Inventory與不可變receipt：31組×9類文件共279列；Phase12的22個canonical resource案例對照198列，17個有可追溯的有界來源嘗試。未搜尋、無候選、下載失敗、解析未驗證、已驗證不可比較及可供指定分析分開。類型標籤可能只是文件提及，不等於研究完成；未分類環境文件仍在manifest，不冒稱完成擷取。未找到不等於不存在。

North Stanmore新版278.80Mt／483ppm有分類與dry-basis支持，但2025的330ppm TREO＋Sc cutoff與2026的300ppm TREO cutoff、足跡不同。兩版原觀測保留，既有 `MULTIPLE_SCOPES_REQUIRE_DEFINITION`規則保守排除此案，沒有日期覆寫或加總。因此Resource22→21、Resource＋port20→19、Study9→8、Financing7→6；D1／C1原證據仍有效，其他案例照常。I20→19是resource cohort評分覆蓋，不是GIS原件遺失。

Resource＋Strategic10、四類Infrastructure7、三個DFS concentrate面板各2、官方WA screen17不變。新增可比較Project×Criterion及共同MCDA樣本為0。正式準則、六Gate、權重、評分與R引擎未改。

共同案例169個準則點分數不變；92個scientific panel CSV與Phase12相同。Study strategic情境的PROMETHEE有1組共同案例順序反轉，其他許多名次上移只是少了一個案例。這是研究母體／方法效應，不是地質優勢。Aim C新增選礦階段、feed、scale、代表性與來源限定的礦物提及，維持描述性分析，不作不足樣本的因果／多變量推論。

全部7,554個既有實體ID保留；新增1個 `DEPOSIT_SCOPE` ID，是新版文件資源範圍，不是新增Project或物理礦床。31個groups、36組配對、112個政府候選及Splinter缺口均未冒稱解決。

## 相容性與重建

修改既有discovery、acquisition、pdf_extract及CLI，重用Evidence／Selection／R。新增1個測試檔與必要設定，沒有新增生產模組、套件、Schema、第二正式資料庫、Project清單或引擎。共用下載錯誤helper與文件覆蓋view不增加人工核准流程。

```sh
au-ree-v2 rebuild --as-of 2026-11-03 --snapshot-lock results/phase13-2026-11-04/snapshot_lock.json --work work/source-recovery
python tools/evaluate_documents.py work/phase13-benchmark.json --phase13
python -m unittest discover -s tests -v
Rscript tests/test_methods.R
```

實際測試、SQLite、SHA與clean replay見 `data/phase13_research_summary.json`；CI以本階段PR checks為準。凍結run的Git commit欄是開發時parent97ea5e8，實作位元組由content SHA綁定，不把parent稱為Phase13實作commit。Phase5–12凍結輸出未改。

剩餘瓶頸：429／403／terms、CLI無一般網搜API、低解析度影像、多層表格、未分類文件、試驗代表性與不同cutoff的比較政策。完成本階段後停止，不啟動下一階段。
