# Phase 22 — Evidence-driven national candidates and shared-method MCDA

來源截止日維持 **2026-11-05**，本版發佈目錄日期為 2026-11-06。開發基準為 `bb7da099941eb222c3baa2537e34d137fe3fb208`、Draft PR #6、`feat/phase16-technical-model`。沒有改變正式研究定義、C1 Gate、七項透明度二分規則、固定分母7、效用尺度或情境權重；沒有第二個正式 registry 或評分引擎。凍結 Phase5–21 成果保持原件。

## 實際資料增量

| 計數單位 | Phase21 | Phase22 |
|---|---:|---:|
| 登錄 canonical groups |32|33|
| 政府原始來源列 |149,618|149,618|
| 政府原生廣義 REE/Sc 候選實體 |728|769|
| 可用資源案例 |21|22|
| 完整透明度點分數 |20|20|
| 六構面探索性完整案例 |5|6|
| 正式 C1 核定 |0|0|
| 既有未解決身分關係 |36|36|
| 選入來源快照（含 metadata／擷取 artifact）|278|303|
| R／S／T／D／I／C 點值覆蓋 |21/13/20/8/19/7|22/15/20/8/20/8|

候選增加41筆是**相同政府原始快照的分類規則修正**，並非取得41個新 Project。現在有34個 `PROJECT` 型 source entities，但經 alias／membership 整理為33個 registry groups；兩者均不代表全澳獨立實體 Project 總數。原32群組 ID 保留。當期SITE數779→766，包含41個新規則候選與54個舊producer佔位實體退出當期視圖的效果；這些ID與歷史原件仍在SQLite，沒有刪除或重新編號。`evaluation.json`、`source_version_rule_comparison.csv` 及 `national_source_coverage.csv` 分開記錄規則、來源及實體計數。

- **Kennedy**：從政府 native candidate 查證至發行人2024-07-04原始 MRE，新增穩定群組 `AU-cc4e217a90b7123dce0a`。只採325ppm TREO-Ce cutoff 的150Mt、1000ppm TREO；另一475ppm cutoff列不相加。來源定義 MREO180ppm／TREO1000ppm，S1=18%；四氧化物個別印值之和177.7ppm的四捨五入差異保留。進入資源／組成部分排名。D1引用的 Makuutu DFS 是外部比較，無法作為 Kennedy 開發階段；T七項均 Unknown，沒有融資狀態或代表點推估。政府 GA_ENO／critical-layer 跨來源關係仍為 Candidate，沒有僅靠名稱／6km代表點合併。
- **Wolverine／Browns Range**：2025-01-16原始 MRE 的 p6 **Table5 TOTAL**，Pr60／Nd280／Tb120／Dy840ppm，除以9600ppm TREO，S1=13.5416667%。排除 Table4 underground-only。原7.3Mt／0.96%品位從DFS重印改綁原始MRE，沒有新增資源量。既有DFS p4明列 Project finance discussions，依原 Commercial codebook 採「規劃／非約束」里程碑；沒有簽約、額度、交割或撥款推論。因此既有案例補件使完整樣本5→6。
- **Yangibana**：採官方 GA_AIMR ENO335246 的代表點補 I4；不是廠址、礦床邊界、身分等同或實際運輸路線。相同資源範圍的完整四氧化物 S1仍缺。
- **Dubbo**：取得17June2025 PhaseB 原件並看原始表格。kg/t敘述與g/L表頭、中央／東部粒徑與欄位矛盾仍存在，TD3維持Unknown，TD4／TD5原0不改；沒有借OFS其他方案分數。
- **WAMEX**：動態候選查詢取得 A145591／BLT749066及A134625／BLT706058兩份原件。公開釋出日與報告有效日分開。Mangaroon carbonatite／探索計畫不得移植為Yin ironstone所採資源的揭露或回收率。

新增5份原始PDF：Kennedy MRE、Wolverine MRE、Dubbo PhaseB、兩份WAMEX報告；另2份HTML為公告索引／官方範圍說明。**12個新原始數值cell**＝Kennedy8（含pH、四組分及MREO，TREO分母重複不重計）＋Wolverine4；另2個既有資源cell重新綁定。`source_cell_binding_check.csv` 的19列包含轉換及重複分母，不能稱19筆新量測。Browns的融資里程碑是文字事件，另列。所有來源SHA、頁碼、原值、範圍與轉換仍在原 SQLite／claims／快照。

**全國新發現形成六構面完整排名案例尚未完成**；Kennedy只完成部分準則排名。Barkly原40Mt／2100ppm／82kt衝突與詳細prospectus403仍待解，未放寬精度。Cowalinya／Mount Ridley／Salazar／Yttria的缺項未因未揭露而補0。

## 程式整合與全國範圍

`search_tasks()` 現在同時處理未登錄 native candidates、來源內父專案與既有群組。工作ID綁 native entity／來源SHA／工作類型，保留 alias、州別、公司、來源定位與阻塞原因。`register-candidate --registration` 驗證明示 Project 文件與SHA／頁碼、使用穩定ID，預設政府候選crosswalk未確認。既有 claims／identity_links 為版本化輸入，並未建立另一本正式名單。

WAMEX由所選WA候選、別名及REE／選冶條件產生查詢，移除六舊案及任意2015下限。ArcGIS與CKAN分頁保留matched、remaining、cursor及額度結束資訊；來源失敗隔離。QLD優先使用metadata提供且限官方host的原件URL。共用 `ree-candidate-v3` 接上workbook與政府入口；Sc符號僅在結構化commodity欄位納入，BSc等學位不算Sc。舊v2規則及歷史重建保留。

`current_evidence_view` 共用選入來源、有效claims／擷取版本與scope-source配對，避免同SHA舊編碼及同scope改綁來源的歷史關係污染當期輸出。歷史觀測與稽核紀錄保留。PDF明確page artifact先於需要AES支援的原生讀取，校驗原件SHA／頁碼／artifactSHA；沒有改寫數值、全面OCR或新增依賴。正式SQLite Schema未變。

R核心面板與真正讀取其他panel的比較分開快取。核心鍵只包含自身科學相依項；跨panel比較鍵仍涵蓋實際讀取的所有peer輸入。移除重複PROMETHEE抽樣評分，沒有改動RNG呼叫順序。

各州原始來源見 `national_source_coverage.csv`。ACT官方GA礦業範圍頁已封存，並未取得獨立ACT礦產API；官方說明缺採礦活動不等於REE occurrence為零。外部領地與南極的行政／地理適用性查核已進行，但來源頁下載超時、專用adapter及超出目前GIS範圍的支援仍缺。REMP2025官方目錄可查，但原始workbook下載reset／timeout，不能宣稱已讀取其Project列。QLD部分403及非PDF回應也保留為運輸失敗，沒有轉為不存在。網路重試收據另存，計算效能不包含網路等待。

## 品質與研究結果

先封存52列／46 native groups參考集，發現Sc與敘述元素漏判後，明確將其改列**已使用驗證資料**。另封存未重用native ID／名稱的25列／24群組測試集，標註先於v3預測。新規則TP14／TN11／FP0／FN0；相同新測試集舊v2為TP11／FN3／FP0／TN11。抽樣框、比例、原欄位、理由及SHA在 `data/census_validation_v3.json`。單一代理標註未獨立複核，小型分層樣本不能推論全國recall或宣稱獨立gold。

`quality_validation.json` 分開候選辨識、4組既有官方foreign-ID關係的候選保留測試、1976組關係候選及19列數值綁定QA。空白原生父識別碼的21條歷史關係被排除於當期視圖，歷史列未刪除；當期明示父群組129個，不將空白代碼當成共同Project。這4組官方foreign-ID是已使用的回歸參考，不是新盲測。沒有新的自動identity合併；錯誤合併／拆分率缺獨立完整真值，保持NULL。數值QA是同代理原表查核與入庫比對，不能冒稱獨立擷取準確率。

新的前瞻封存集主要驗證候選與角色辨識。改名／同名異地／母子範圍、Exploration Target／Mineral Resource／Ore Reserve混淆，目前仍由既有關係、原件綁定查核與回歸案例覆蓋，尚未形成另一份獨立、未見的身分及數值保留集；不能將候選25/25或官方關係4/4擴張解讀為這些工作的獨立準確率。

Aim A：6案三方法重算。資源與戰略情境三方法首位皆Nolans；開發情境SAW／PROMETHEE首位Nolans，TOPSIS首位Goschen。這是含揭露透明度與融資披露里程碑的探索性綜合評估，並非技術能力、純開發可行性或全國排名。原五案效用與SAW／TOPSIS分數不變；插入新案例、共同次序變化與PROMETHEE比較母體效應見 `cohort_rank_changes.csv`。

Aim B：相同draw_id／權重／準則值送入三方法，每情境1000次、seed20261102，保留PROMETHEE舊抽樣契約。`six_domain/shared_draw_ranks.csv`、`shared_draw_contract.csv`、`uncertainty_by_method.csv` 及 `shared_draw_pairwise_order.csv` 保留逐次及摘要。開發情境權重抽樣共同首位頻率：Nolans SAW65.0%／PROMETHEE62.0%／TOPSIS47.5%；Goschen30.1%／25.4%／43.9%。這是模型頻率，非開發成功率。1000次二項頻率最大Monte Carlo標準誤約1.58百分點。來源印值四捨五入與權重分開；沒有可信精度的S1不任配範圍，Unknown透明度只給界限、不給機率。

42項透明度逐項翻轉仍是反事實壓力測試，31個情境／方法／項目組合可改變首位集合。**Nolans／Goschen／Jupiter獨立於原判讀的重編碼尚未取得**；同代理重看來源不能冒充獨立複核，沒有為此改正式編碼。

Aim C：`cohort_balance.csv`／`research_analysis.json` 描述6完整案與27其他登錄群組的州別、礦床型、已驗證資源規模、成熟度與來源可得性。完整案集中WA3、NT1、SA1、VIC1，部分群組礦床型未知；採樣與文件可得性會影響完整性。小樣本／巢狀範圍不支持全國代表性、因果機制或有說服力的多變量推論。

## Proposal與解讀應調整

已讀同步proposal研究目的及相關既有決策；`sources/`保持唯讀。proposal研究問題、準則表與結果文字中的「Technical Feasibility／技術表現」需改為「Technical Disclosure Transparency／技術資訊揭露透明度」。七項與權重是本研究操作化設計，JORC Table1只作整理骨架，不是JORC官方評分或合規認證。沒有試驗但充分交代限制可以得透明度分，漂亮績效但揭露模糊不能自動得分。原選冶數據保留為補充技術證據，不混入T1。

Aim A總排名須稱包含資訊透明度的綜合評估；Commercial是披露里程碑，非資金已到位。Aim B權重為研究者情境假設，非專家elicitation；頻率與未知界限不稱成功機率／信賴區間。Aim C與全國Census需區分選定群組、部分準則研究母體、獨立Project及正式C1；目前未完成原proposal的共同製程技術可行性評估。

## 重現入口

```sh
au-ree-v2 rebuild --as-of 2026-11-05 --snapshot-lock results/phase22-2026-11-06/snapshot_lock.json --work work/phase22-replay
python tools/check_replay.py results/phase22-2026-11-06 work/phase22-replay/latest.json
python -m unittest discover -s tests -v
Rscript tests/test_methods.R
python tools/benchmark_pipeline.py --current-suite --out work/phase22/performance-replay --rounds 3 --rscript Rscript
```

Python與R測試、歷史／增量一致性及效能收據見本版 `release_validation.json`、`performance.json`；GitHub Actions按本次Commit檢查，PR維持Draft，不自動合併。
