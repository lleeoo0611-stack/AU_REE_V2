# Phase 11：確定性 MCDA、缺漏驅動取得與研究利用

以 Phase 10 `0a3e566` 為基準；V2 證據截止日維持 **2026-11-03**，本階段成果日期為 **2026-11-04（Asia/Taipei）**。沿用 `work/phase5/canonical.sqlite`、Python CLI、Evidence Selection 與 R 引擎。沒有新增正式資料庫、資料表、評分引擎、人工簽核程序或正式準則。

## 確定性與版本相容

`entity-keyed-rng-v2` 使用長度前綴的 method version、seed、scenario、uncertainty family、Project ID、Criterion ID，初始化六個整數狀態的原生 L'Ecuyer-CMRG stream；draw index 是該 stream 的位置。這是版本化的確定性識別方法，並非密碼學雜湊或測量誤差模型。權重以獨立 stream 的 uniform 經 gamma quantile 產生，source rounding 使用另一 family。保存並還原呼叫端 RNG state。

Python 對新版本的 interchange 排序，R 再以 stable IDs／criterion codes／scenario 排序。新增或刪除 Project 不改變其他 Project 的原始 uniform。列、欄置換與同 seed 重跑的排名、分數、分位數及 Top-k 頻率均須完全一致。

Phase 5–10 的 frozen configuration 不含新 method version，仍走 `legacy-position-rng-v1`。沒有改寫其演算法或凍結輸出。新版本採 seed **20261102**、1,000 draws、Dirichlet concentration **30**；runtime CSV 記錄 R version、RNG kind、normal/sample kind 與方法版本。Source rounding 明確不是 measurement uncertainty；無來源範圍的技術模型仍不量化測量誤差。

相對 Phase 10，36 個矩陣／固定排名／準則／權重檔案通過原有科學比較。新版抽樣改變 132 個權重模擬統計格（最大頻率差 5.1 個百分點、最大排名分位差 1），以及 6 個四捨五入頻率格（最大 1.4 個百分點、排名分位不變）。這是方法版本差異，不是新增證據或專案發展。

## 缺漏驅動取得的實際執行

`discovery.search_tasks` 可讀取既有 `evidence_pipeline_diagnostics.csv`，生成 stable Project × Criterion 任務，保留 alias、company/ASX（無資料則 NULL）、原始證據 SHA、來源入口、預期文件類型、選取／擷取原因、既有失敗與優先級依據。優先級按缺漏 domain 與來源重用效益；不按正式 C1 是否可能准入排序。執行預算以不同 Project 分配，沒有另建永久 queue。

```powershell
au-ree-v2 all --as-of 2026-11-03 --work work/phase5 --refresh --gap-report results/phase11-2026-11-04/evidence_pipeline_diagnostics.csv --task-limit 3
```

這條原有 CLI 路徑依序執行搜尋／下載、content-addressed snapshot、解析、驗證、Selection、Coverage 及 R。僅取得資料可用 `acquire`。失敗來源留在 receipt，其他來源繼續。相同 SHA、parser、layout 與 registry contract 重用既有解析。

實際處理 Donald、Nolans、Jupiter、Redlings 相關缺漏。三個早期入口因環境網路代理失敗；停用失效代理後，Redlings 發行人頁面成功解析並取得 PDF，但內容 SHA 已存在，**沒有新增原始 PDF**。四份既有且未自動解析的原件新增 extraction snapshots；另重用既有 Redlings 技術簡報解析。重跑 receipt 記錄 elapsed time、下載傳輸及來源重用，傳輸數不等於新原件數。

| 指標 | Phase 10 | Phase 11 |
|---|---:|---:|
| Selected source snapshots | 100 | 104 |
| 原始 PDF snapshots | 44 | 44 |
| 自動文件解析覆蓋 | 9 | 13 |
| 文件候選 | 656 | 957 |
| 目前驗證契約下的原始觀測 | 285 | 371 |
| 已驗證數值聲明 | 265 | 265 |
| Canonical registry groups | 31 | 31 |
| Resource-defined scopes | 22 | 22 |
| 未解決 deposit pairs | 36 | 36 |

增加 **86 筆 NULL 數值的文字觀測**：Technical 19、Development 45、Commercial 22；不能當作新的 recovery、資源量或已完成商業事件。首輪有一筆 Donald 詞彙表的 DFS 定義被收為 Development，原頁檢查後改以 `page-context-v2` 列為 REVIEW；歷史原始版本仍保留。沒有把 forward-looking、未知日期或範圍不足的候選補成數值。

公開文件的發布／有效日期與取得日期分開。可明示追溯取得已發布的 PDF／HTML 及其解析，但不將現在的 live government/GIS response 回填到過去；較早的 CLI cutoff 也不自動套用本階段的取得視窗。這項界線有專門回歸測試。

## Technical 與 Aim C

沿用 Phase 10 三類語意與 comparison contract：T-A 礦物／製程、T-B performance、T-C evidence quality。T-C 不加權。原始 Technical inventory **641→668**（包含 REVIEW／不可比較原始紀錄），新狀態分布為 **4 NUMERIC_COMPARABLE／153 DESCRIPTIVE_ONLY／511 NOT_COMPARABLE**。

4 筆可比數值仍是 TC1、TC2 各兩案：Browns Range 與 Yangibana 同為 whole-ore→mineral-concentrate 的 DFS 設計。是兩個獨立 Project／兩個工程案例，不是四個 Project，也不是操作實測。V2 T1 recovery 仍為 0；上游 processing-complexity T1 未被取代。

`aim_c_technical_features.csv` 以 Project 彙整語意類別、狀態、endpoint、scale、source SHA、工程流程敘述、缺漏原因與各面板 rank links。來源段落 scope keys 與已驗證工程 Study Cases 分開計數。Asra 的多個試驗列／元素仍只有一個 Project，不能增加獨立樣本。

| 案例 | 可用的研究描述／限制 |
|---|---|
| Browns Range／Yangibana | 同終點設計比較；不推出下游或實測整體 recovery |
| Jupiter | Scoping MREC 的 58／63 為不同流程設計，與 concentrate 分開 |
| Koppamurra | PFS resource-to-calcined MREO 68%，保持其 mine-plan scope |
| Dubbo | 三礦區 Nd 浸出值，非三 Project、非可相乘步驟 |
| Cowalinya | 選擇性 composites 與產品 grade 分開，代表性未建立 |
| Circle Valley | Bench 條件及 mean／maximum 分開 |
| Donald | 已驗證技術文字可描述；沒有同定義 performance panel |
| Asra | 試驗酸系、oxide basis、sample/statistic 保留，單一 Project |

可描述跨專案製程、辨識可比群組及缺漏型態，也可連結探索性排名；目前不能據此識別 MCAR/MAR/MNAR、做具代表性的多變量推論或提出因果機制。

## Commercial 與 Aim A／B

`commercial_event_semantics.csv` 是現有 typed events 的視圖，不是新來源表。保留 instrument／agreement state、CPs、attribution、effectivity／expiry、currentness、source/page 與原事件。Conditional credit approval、subscription、JV earn-in、convertible note、corporate equity、payment、offtake 不因相同 ordinal 而等價。缺 counterparty／期限等資訊保留 NULL／Unknown。

Financing milestone 覆蓋 6 Project；Offtake 3；兩者交集 3，但有可比 Resource 的交集只有 **2**。Resource＋Financing 原面板 **5** 案；沒有從目前來源確認完整 financial close 或 project drawdown。已知歷史付款、CAPEX、公司資金或承購不等於可用 project funding。完整商業資訊的描述性檢查要求 counterparty、期限及 conditions state 全有揭露；目前 0，並非新的 Eligibility Gate。

固定原來 R1/C1 數值，使用現有三個 R 方法掃描 Commercial 權重，並獨立比較 5 案與 2 案交集：

| Cohort／Commercial 權重 | SAW 第一 | PROMETHEE II 第一 | TOPSIS 第一 |
|---|---|---|---|
| 5 案／9.0909% | Jupiter | Jupiter | Jupiter |
| 5 案／14% | Nolans | Jupiter | Jupiter |
| 2 案具承購證據／上述兩權重 | Nolans | Nolans | Nolans |

SAW 的 Jupiter／Nolans pairwise equality 為 **13.8599128249766%**。不是推薦權重、普遍方法臨界值或正式排名。承購只用於描述／分層，未被評分或補零；2 案交集移除了原先第一的 Jupiter，明顯呈現資料選樣效果。

九個既有面板樣本仍為 **20／7／9／5／2／2／5／2／17**（依 comparison_cohorts.csv 的 panel ID 閱讀）。六構面可評分覆蓋仍為 **R22／S9／T0／D5／I20／C6**；沒有新增 MCDA alternative、完整六域或正式 C1。

## 正式 Eligibility

讀取上游 `AU_REE@093d724cc25fc319725bf347fc4d8ab196aadaf3` 的政策、準則、研究決策及兩份核准帳本，原始文字保存 SHA-256，configuration 凍結其引用。六項 Gate 保持 `ID／ROLE／WINDOW／JORC／PANEL／GIS_RELEASE`。

既有 `formal_gate_compatibility.csv` 擴充客觀證據、原生 IDs、source/page、發布／有效／取得日期、範圍、缺漏及 formal status。31×6＝186 格：ID 31、ROLE 9、WINDOW 8、JORC 22 格有**部分來源事實**；PANEL 與 GIS_RELEASE 未具完整客觀證據。所有正式狀態均未准入。

上游正式 cutoff **2026-10-29** 與 V2 cutoff **2026-11-03** 獨立；10/30 公告不能滲入上游 Gate。上游簽核及 identity metadata CSV 都只有表頭；approved crosswalk 為 0。沒有將上游 39 群組與 V2 31 群組按名稱合併。C0／C1／C2／C3 與探索性面板保留上游政策意義；PANEL 9／12 未選定、正式簽核、Project footprint／role／activity 與 GIS release 尚缺。客觀來源事實不等於 formal PASS。

## 驗證與重建紀錄

重建命令與實測結果見 frozen summary、`data/phase11_research_summary.json`、`data/phase11_reproducibility.json` 及 PR。`tools/check_phase11.py` 對所有 panel CSV 的科學輸出使用 **零數值容差、CSV 內容精確比較（只正規化 CRLF/LF 行尾）**，涵蓋分數、排名、Monte Carlo 與 Top-k；僅 runtime 的平台版 R_version 描述字串例外，其餘方法／seed／RNG metadata 仍須一致。

歷史 Phase 5–10 延用舊版 replay checker；新方法不覆寫凍結的模擬。獨立重建只使用 `work/` 下的拋棄式驗證資料庫；正式操作仍只有原 canonical SQLite。完整 observation-version history 與 clean bootstrap 的版本數不是 byte-equivalence 契約；不將科學輸出一致宣稱為全部歷史資料庫位元組相等。

仍缺共同實測 technical endpoint、樣本代表性、明確試驗條件、完整商業條件及正式准入證據。36 個 deposit pairs、112 個政府關係候選及 Splinter 技術原件缺口未因本階段自動消失；本階段沒有新的 National Census Project 增量。
