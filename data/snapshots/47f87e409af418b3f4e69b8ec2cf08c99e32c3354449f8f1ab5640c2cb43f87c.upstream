# r983 重構的研究決策（2026-10-29）

| 研究問題 | Pipeline 決策 | 對應欄位／程序 |
|---|---|---|
| 專案母體完整性 | 維持 GA／各州／歷史 Legacy 多來源，來源原文與排除原因保留；非 project 實體進人工審核 | `population_candidates`, `project_master`, `project_aliases` |
| 專案與礦床層級 | Deposit / Prospect / Tenement 不自行升級為 Project | `entity_level`, `population_review_queue.csv` |
| 更新後保留 ID | project ID 一經核准就保持不變；不依排序編號 | `project_id`, `legacy_id_map` |
| 稀土資源資料語意 | TREO、THM、MzEq、magnet REO、REE mineral basis 保留原始計量定義 | `basis`、R1／S1 篩選 |
| 證據時點 | 凍結日期前的公告與資料對應評估快照 | `effective_date`, `publication_date`, `freeze_date` |
| 缺失資料 | Missing 不做零分，源證據不足或衝突保留待審核 | `criterion_values`, `coverage` |
| 開發階段可比性 | 主分析限定活躍的 pre-FID Scoping 至 DFS/BFS/Feasibility | `eligibility.json` |
| GIS 距離 | 官方資料、代表座標經核准、EPSG:3577 最近直線距離、每來源 SHA | `gis_metrics`, `gis_sources` |
| 情境穩健性 | G0 全域非 R/S、R1 嚴格資源、S1 嚴格戰略、RS 同時含兩者 | `eligibility.json`、R MCDA |
| 權重來源 | AHP 問卷為正式權重；研究假設權重獨立標示，Monte Carlo 權重擾動 | `ahp_pairs_*.csv`, `run_mcda.R` |
| 版本重現 | 程式／設定／資料快照 SHA-256 + 各階段 manifest + SQLite checkpoint | `stage_runs`, `manifest.json` |

樣本：歷史 r963 種子為 203 筆，這些母體證據不會自動認定為目前已確認的 MCDA Alternatives。正式個數由第四階段檢驗時點及證據決定。

## v2 研究架構（2026-10-31，設計契約）

依 [RESEARCH_ARCHITECTURE](RESEARCH_ARCHITECTURE.md) 採納以下**研究設計方向**；這些不會自動改動上方的 r983 歷史決策或 v1 程式：

| ID | v2 decision / requirement | 狀態 |
| --- | --- | --- |
| ADR-v2-001 | C0 Census／C1 Primary MCDA／C2 Extended／C3 Historical 分開；主要 Aim A/B/C 共用 C1 的固定六構面準則集合 | FRAMEWORK_ADOPTED，C1 required criteria、正式母體未核定 |
| ADR-v2-002 | Project–Deposit–Resource Statement、JORC resource/reserve／M/I/I、oxide basis、公司／礦權角色與時間／證據追溯 | FRAMEWORK_ADOPTED，schema migration 未實作 |
| ADR-v2-003 | 固定 reference utility＋階層式 domain weights；AHP scenario 實際權重須可回溯；PROMETHEE II／TOPSIS 做互補比較 | FRAMEWORK_ADOPTED，參數與專家判斷未核定 |
| ADR-v2-004 | B1 權重、B2 數據、B3 方法、B4 cohort；Joint uncertainty + SMAA 僅在分布有證據支持時執行 | FRAMEWORK_ADOPTED，分布和 tie rule 未核定 |
| ADR-v2-005 | C1 模型內部敏感度與 C2 外部專案特徵分開；D1 included/excluded；C3 歷史 as-of 無時間洩漏 | FRAMEWORK_ADOPTED，實證尚未執行 |
| ADR-v2-006 | Commercial/ESG 歷史名稱保留；v2 擬以 Commercial & Regulatory Readiness 精確描述 C1–C3 | PROPOSED，需 criteria migration 核定 |

### 後續重大方法變更紀錄（Decision Log）

| Decision ID | Date | Status | Scope / Rationale | Version change | Affected Aim / Tests | Approval |
| --- | --- | --- | --- | --- | --- | --- |
| _於對應 PR 經審核後新增；不得覆寫歷史紀錄_ | | | | | | |

狀態使用 `PROPOSED`、`ACCEPTED`、`SUPERSEDED`。上表 `FRAMEWORK_ADOPTED` 代表研究架構的方向已列為後續工作依據，**不代表所有參數、樣本或實作已獲實證核准**。詳細變更流程見 [RESEARCH_IMPLEMENTATION_PLAN](RESEARCH_IMPLEMENTATION_PLAN.md)。

### P0 審查進度（2026-10-31；非正式准入決策）

| Decision ID | 日期 | 狀態 | 內容與科學依據 | 後續核准 Gate |
| --- | --- | --- | --- | --- |
| `ADR-P0-001` | 2026-10-31 | `PROPOSED` | C1 使用逐 Project 的 `ID → ROLE → WINDOW → JORC → PANEL → GIS_RELEASE` 審核；觀察到 review group/target row 與已核准 Project 不同 | [C1 Protocol](P0_COHORT_SELECTION_PROTOCOL.md)，需人工來源核准與 coverage |
| `ADR-P0-002` | 2026-10-31 | `PROPOSED` | 待比較 `PANEL_12_CANDIDATE`（全部 12 準則）與 `PANEL_9_CANDIDATE`（R1 S1 T1 D1 I1–I4 C3）；只按覆蓋/構念效度在看排名前定稿 | 全六構面共同準則/研究審查與樣本 N |
| `ADR-P0-003` | 2026-10-31 | `PROPOSED` | Resource statement 應有 scope/cutoff/edition/M-I-I/oxide/時間；沿用既有 Project ID 和 geological_entity，避免 JORC totals 與 deposit subtotals double count | [Schema Design](P0_PROJECT_RESOURCE_SCHEMA.md)，需增量 migration/test |
| `ADR-P0-004` | 2026-10-31 | `RECORDED_AUDIT` | 39 review groups（32 candidate/7 HOLD），正式 input approvals 及 observations 均空；本盤點 C1 `NOT_RELEASED` | [Readiness Audit](audits/P0_C1_READINESS_2026-10-31.md)，尚未簽核任何 Project |

以上 `PROPOSED` 表示可執行的審查設計，**沒有替研究者預先批准 C1 名單、JORC 數據或排名**；後續依來源記錄決策變更、審查人與日期。

### P0 source verification（2026-10-31；設計討論）

| Decision ID | Date | Status | Proposed change | Scientific basis / tests |
| --- | --- | --- | --- | --- |
| `ADR-P0-005` | 2026-10-31 | `PROPOSED` | 檢討是否將正式主分析定義為 `C1_DIRECT_REO`（可直接比對 JORC REO 的 pre-FID Project），將以 THM/MzEq 與 REE 副產品為主、未能計出可比 R1 的礦砂列於 `C2_HMS_REE_COPRODUCT` | 防止 THM/MzEq 被誤當 TREO；需先統計每 Project 六構面 N，檢查礦床類型偏差及資源範圍。**尚未接受/修改 C1 或 R1** |
| `ADR-P0-006` | 2026-10-31 | `RECORDED_AUDIT` | Nolans 和 Balranald 已有實際 FID/施工或採礦證據，按 2026-10-29 pre-FID window 不納入下一輪 C1 篩選，保留作歷史研究資料 | [39 組來源驗證報告](audits/2026-10-31_project_source_screen_report.md)。正式歷史事件仍需附文件 SHA、有效日期及獨立審核 |
| `ADR-P0-007` | 2026-10-31 | `RECORDED_AUDIT` | Jupiter 的 2026-10-12 JORC MRE、2026-10-20 Scoping 和 Dubbo 的 2026-08-28 母公司收購屬必須版本化的來源變更 | 須保留來源截至日；禁止 MRE 不同年份/Project–Deposit 總量重複相加，母公司收購不能直接推論礦權已轉讓 |

以上是**來源核查及待決定的科學問題**。任何 cohort/panel 實際變更須先有 Stage Gate 核准，不以此 Decision Log 取代正式 observations/evidence approval。

### P0 all-487 source audit（2026-10-31）

| Decision ID | Date | Status | Research/engineering decision | Evidence and next gate |
| --- | --- | --- | --- | --- |
| `ADR-P0-008` | 2026-10-31 | `RECORDED_AUDIT` | 精確 `target_id` 將 487 source records 一次整併；不以地名、州別、礦權空間交集推定 Project，也不把工作佇列 Priority 視為評分 | [487 全量審查報告](audits/2026-10-31_census_487_batch_review_report.md)、[37→39 欄逐筆 CSV](audits/2026-10-31_census_487_batch_review.csv)；409 筆尚未建立 Project group，C1 仍未核准 |
| `ADR-P0-009` | 2026-10-31 | `RECORDED_AUDIT` | 留存 source/entity/crosswalk/tenure/evidence locator 當次 status 並產生 P1–P4 review workstream；不同來源、快照、實體層級數不得混計 | [Batch QA Summary](audits/2026-10-31_census_487_batch_review_summary.json)、[Rebuild script](../scripts/build_p0_census_487_audit.py)、pytest；下一 Gate 為關聯核定和 JORC resource basis |

此處的 P1–P4 是**Census 審查工作優先順序**，與研究開發里程碑 P0–P3 **不同**，不可混用。

### P0 all-source claim evidence review（2026-10-31）

| Decision ID | Date | Status | Evidence / decision | Required follow-up |
| --- | --- | --- | --- | --- |
| `ADR-P0-010` | 2026-10-31 | `RECORDED_AUDIT` | 487 個來源列全納入證據深度分類；441-row trace 之原始資料定位與 95-row document locator 採不同層級；原生記錄 `EXACT` 不代表 Project 證明 | [逐筆 Evidence Claim CSV](audits/2026-10-31_487_evidence_claim_review.csv)、[報告](audits/2026-10-31_487_evidence_review_report.md) |
| `ADR-P0-011` | 2026-10-31 | `RECORDED_EVIDENCE_LEAD` | WA 2026-02 官方 REE 清單有 20 Project/resource names；同州完全同名與現有 487 對到 13 種名稱／20 原始列，包括 Cummins Range、Yangibana、North Stanmore | 需 Project scope/JORC statement 原文、期限、類別和 reviewer approval；不自動新增正式 Project ID |
| `ADR-P0-012` | 2026-10-31 | `RECORDED_EVIDENCE_LEAD` | NT EL31225 官方公開 2023 報告明示 Plenty River prospect 屬 Bruce Project，應優先審核 parent relation | 指派獨立來源/關聯審核；尚未新增正式資料庫 Project／Deposit link |

以上新來源和原始已核准觀測屬**不同層級**。本輪新增的 source leads 不能取代正式 `evidence_approvals.csv`。


### P0 evidence recovery round 2（2026-10-31）

| Decision ID | Date | Status | Evidence decision | Follow-up |
| --- | --- | --- | --- | --- |
| `ADR-P0-013` | 2026-10-31 | `RECORDED_AUDIT` | 487 Census source targets 再核查外部政府與公司報告，為 86 筆增加來源文字定位；保持 Round 1 欄位、native ID、Project/Deposit 層級與正式 Gate 不變 | [第二輪報告](audits/2026-10-31_evidence_round2_report.md)、[逐筆 CSV](audits/2026-10-31_487_evidence_round2_review.csv)、[62 筆可追溯來源線索](../inputs/source_review_20261031/round2_external_evidence_leads.csv) |
| `ADR-P0-014` | 2026-10-31 | `RECORDED_AUDIT` | 原無外部文件的 23 筆中 20 筆取得外部來源指標，但原 native bytes 仍缺；Olympic Dam/Clarke 取得政府來源仍保留 4／6 個 source feature row 歧義 | [86 個改變的 target](audits/2026-10-31_evidence_round2_changed_targets.csv)；需 source-native feature discriminator、官方原件 bytes SHA-256 及 independent review 才可能核准 |


### Original source archive replay (2026-10-31)

| Decision ID | Result | Reference |
| --- | --- | --- |
| `ADR-P0-015` | 272 筆 native-only target 全部以 2026-10-29 封存核對至**單一官方來源 feature**；268 無 source Project parent key、4 只有地質 parent/group；仍為 C0 | [272 CSV](audits/2026-10-31_272_native_project_scope_triage.csv) |
| `ADR-P0-016` | 原 23 缺原生列：GA 7 筆來源 JSON，Legacy 16 筆歷史來源列，後者原 project_id 精確等於穩定 Legacy UUID，但不是政府 native ID | [23 CSV](audits/2026-10-31_23_native_source_recovery.csv) |
| `ADR-P0-017` | Olympic Dam MINDEP 3000 的 4 個 `OBJECTID/FID`、Clarke MINDEP 11849 的 6 個來源圖徵一一識別；仍只對應 2 個礦床 | [SA 10 CSV](audits/2026-10-31_sa_10_duplicate_source_features.csv) |
| `ADR-P0-018` | 6 筆跨來源 Project parent 候選，其中 REE project 2 筆，non-REE mine 4 筆，無自動 C1 核准 | [parent 候選](audits/2026-10-31_272_project_parent_candidates_6.csv) |


### P0 Project parent 與原始來源合併審查（2026-10-31）

| Decision | Status | Evidence and frozen schema rule | Next gate |
| --- | --- | --- | --- |
| `ADR-P0-018` | `SOURCE_BYTES_VERIFIED` | 272/272 source-native features 原始資料精確唯一匹配；23/23 原始 GA/Legacy 紀錄 bytes/ID 核對完成；輸出每來源原始 SHA-256 與原始歸檔 JSONL | [本輪完整報告](audits/2026-10-31_p0_native_parent_resolution_report.md) |
| `ADR-P0-019` | `SOURCE_FEATURE_IDS_RESOLVED` | SA MINDEP 3000/11849 各自具有 4/6 列不同 OBJECTID／FID；以 `SA_CRITICAL_REE:MINDEP_NO:OBJECTID` 保持 10 個唯一來源圖徵，仍只有 2 個礦床 | 不能重複建 Project ID 或重複計 JORC |
| `ADR-P0-020` | `PARENT_EVIDENCE_CANDIDATES_ONLY` | 原始 272 筆中 13 新 + 6 既有文件關聯＝15 稀土相關 Project 候選 source rows、4 非稀土項目；92 nonproject entities；2 TAS parent deposit；3 VIC generic category；156 無 Project 母層 | [272 筆 Evidence Queue](audits/2026-10-31_272_project_parent_evidence_queue.csv)；需 source scope、Project 邊界及 reviewer approvals |


### 156 筆未建立 Project 母層的來源審查（2026-10-31）

| Decision ID | Status | Evidence | Next requirement |
| --- | --- | --- | --- |
| `ADR-P0-021` | `FULL_SOURCE_REVIEW` | 156 source-native ID 原始圖徵與 URL／status／REE 商品逐列保留；70 筆同州同名僅是跨來源去重候選 | [156 筆 Evidence Audit](audits/2026-10-31_156_project_parent_evidence_review.csv) |
| `ADR-P0-022` | `NAMED_PROJECT_EVIDENCE_CANDIDATES` | 8 筆政府／公司具名 Project 文獻、3 筆名稱或範圍尚未證明相同、145 筆尚無新增具名 Project 文獻；Project/JORC/C1 approved 全部 0 | [報告](audits/2026-10-31_156_project_parent_review_report.md)；須 original Project extent、時間/礦權與 REE role 核准 |


### P0 第五輪：109 筆未建立 Project 父層的來源證據（2026-10-31）

| Decision ID | Status | Evidence/meaning | Follow-up |
| --- | --- | --- | --- |
| `ADR-P0-023` | `ALL_109_SOURCE_CLAIMS_REVIEWED` | 以 2026-10-29 原始 native feature + 31 個有定位的官方／公司／CSIRO 文獻名稱審核 109 筆；其中 20 筆有歷史 Project 候選、10 筆範圍/礦權/空間 HOLD、9 筆只有 Deposit 文件、70 筆仍只有 native evidence | [109-row CSV](audits/2026-10-31_109_project_evidence_review.csv)、[審核報告](audits/2026-10-31_109_project_parent_review_report.md) |
| `ADR-P0-024` | `SOURCE_SPATIAL_IDENTITY_CONFLICT_HOLD` | 同州同名 44 source rows 中 42 筆雙端原生座標可比，38 筆 ≤1km；兩筆 Ambergate 官方座標相距 38.738km，因此不得基於名稱自動合併 Project/Deposit | [原始來源 JSONL](../data/source_snapshots/2026-10-29_272_native_features.jsonl)，需官方歷史 Project polygon、report effective date 和 reviewer signoff；全部 C1 仍未發布 |


### P0 第六輪：70 筆沒有新增 Project 文獻的 source-targets（2026-10-31）

| Decision ID | Status | Evidence and approach | Next gate |
| --- | --- | --- | --- |
| `ADR-P0-025` | `SOURCE_EVIDENCE_REVIEW_COMPLETED` | 逐一核對 70 筆 2026-10-29 frozen source-native ID／SHA，補入 25 個官方／公司／WAMEX 來源名稱對 34 個 target 的文件定位：7 直接歷史 Project 文獻、4 WAMEX 報告索引、8 範圍疑慮、15 地質證據；36 仍只含官方原生地質紀錄 | [70-row 審核](audits/2026-10-31_70_project_evidence_review.csv)、[報告](audits/2026-10-31_70_project_parent_review_report.md) |
| `ADR-P0-026` | `CROSS_JURISDICTION_SCOPE_HOLD` | 2 筆 Wingellina 的來源 state 標為 SA，但原生點位位於 128.938°E（129°E 州界以西），需以官方地籍／矿權判定；Benmara South 兩時期 EL/prospect 範圍差異亦保留 HOLD | 先驗證 native 原始地籍／legal owner、當期 Project polygon，再開放 Project／REE role 核准 |
| `ADR-P0-027` | `REE_HM_SEMANTIC_GATE` | 政府礦砂數值 HM/THM、銅／鈾的 resource summary、monazite accessory %, 不等於 TREO 或 NdPr resource。第三方 WAMEX 索引只作待取得政府原件的來源指標 | 原始 JORC source scopes、各氧化物、effective date、source bytes SHA + independent reviewer 簽核 |


## 2026-10-31 — P0 412 HOLD 後續查核界線

- 凍結原始 412 source targets 與 2026-10-29 source as-of；P1 73、P2 28、P3 216、P4 95 不更動 ID。
- P3/P4 311 筆採來源層 provenance 稽核；地質 Occurrence 保持 C0，不能僅憑來源點推論 Project。
- 13 個 P1 正向案例按既有六個 C1 Gate 跨表逐案對證，直到原始文件 bytes、正式資源基準、Project polygon、截止日有效研究與 reviewer sign-off 完備，不予獨立核准。
- Legacy source 與政府 native feature、名稱相同或附近 tenement 交集不可直接當正式 Project 身分；舊版 draft PR #33 的 P2 72 筆與此版本 P2 28 筆需先分辨分母。

## 2026-10-31 — PR #33 historical action_priority=P2 admission separation

- 舊版 487 action_priority=P2 72 筆已精確對回最新 412 原 HOLD：28 筆目前 P2；另 38 筆原 INCLUDE_CANDIDATE 與 6 筆 HOLD_REE_ROLE 均不計入 412 HOLD。
- 兩組標籤只是任務優先級／來源證據分流，未建立新增 72/47 個獨立 Projects；保留原 source ID 和 reviewer signoff=空。
- 舊版 72 筆來源的經濟研究／資源證據僅作已公布且 source-scoped 的文件主張，不得把同一個群組 JORC 合計值分配至不同 source rows。

## 2026-10-31 — P2/P3/P4 documentary closeout scope clarification

- `P234-DOC-CLOSEOUT-20261031-V1` 保留原母體與方法，不修改 Cohort、準則或核准。按使用者指示暫緩 C1、13 案 Gate 與 MCDA。
- 固定原生內容審查完成、限定桌面文件判讀完成、原始技術文件全文驗證及足以核准 Project 為不同狀態；terminal disposition 可以是 HOLD，不能把 URL／索引或 native commodity 當全文或開發資格核准。
- Legacy target UUID 與政府 native feature ID 分層保存；52 個 Legacy target IDs 中 30 筆有政府原生來源，22 筆僅 Legacy 原列。原始 source IDs 和一對多 SA feature 關係不刪除、不升格。
- 原 archive bytes 驗證與衍生選集離線再生分開；本輪外部原始技術文件全文驗證仍為 0，144 個 P3/P4 文件指標的原件／範圍工作保留待辦。


## 2026-10-31：144 HOLD 原件內容與範圍判讀

- 延續原對話「整理母體證據查核」最新指示：C1 暫緩，集中 P2/P3/P4。此批補原始文件相關頁，為 proposal Aim A 建立正確 Project 身分與計量基礎；不提前進入 Aim B/C 排名。
- 判讀 144 個固定 ID，分清本機原件、網頁原件、替代原件與未讀原件。保留原始 339 帳本與凍結來源，以 overlay 更新本批處置，不用重複來源列推算獨立 Project 數。
- 原件讀到的 commodity/resource 數值、礦權與地理關係僅在相同範圍內使用；鄰接、同名、同公司、群組總量或地區名稱均不構成資源繼承。THM/HM、礦物比例與 TREO 不互換。
- 保存原件雜湊與頁碼，但完整受限制第三方原件留在本機。公開 CI 驗證研究紀錄，與本機讀原件的驗證明確分開；兩者皆不等同獨立核准。詳見 [本批報告](audits/2026-10-31_p234_144_primary_scope_report.md)。


## 2026-10-31：P2/P3/P4 逐筆分類與有界查核收斂

- 研究 Aim A 的來源證據工作以 339 個固定來源 ID 收斂為 8 個明確狀態，不能將分類完成等同 Project、JORC 或 C1 核准。保留來源點／歷史礦權／重複關係，避免未證實實體直接影響 proposal 母體與後續 Aim B/C。
- 原引用原件、替代官方原件、快取擷取文字、原生內容與沿用桌面審查分開計數。9 筆跟進中 5 筆原引用取件、3 筆替代原件、1 筆 Scaddan 存取 HOLD；4 筆舊引用實體取件殘餘不隱藏。
- 缺原件不得當作無礦化；獨居石成分不能當整體 TREO；歷史截距不能當 MRE；相鄰近岸／離岸礦權不能繼承資源。沒有新的可驗證原件、入口或範圍證據時停止相同失敗取件，依逐筆重開條件恢復。
- C1、13 案 Gate、MCDA 暫緩，零核准改動。見 [最終證據分類報告](audits/2026-10-31_p234_final_evidence_report.md)，包含實際內容覆蓋與公開 CI 限制。

## Evidence batch decision EXT-TECH-B01（2026-10-31）

本批採用「原始發行人文件的公開文字定位」與「已保存 PDF 位元組 + 頁面驗證」分層記錄；只有前者時 `original_byte_sha256` 留空。2017 Ketchowla JORC 2012 *Exploration Results* 不代表資源量；2011 Victory REE+Y grab assay、2025 Johnson Dam Nd 截距不能轉換成 TREO MRE。Scaddan 2024/2025 vendor clay 型態衝突另記為 evidence conflict，不憑行銷文案判定 IAC。資料判讀與原始 C1/13 案 Gate 分離；所有已建立正式資格及歷史快照保持不變。[本批報告](audits/2026-10-31_external_primary_batch01_review.md)。

## Evidence batch decision EXT-TECH-B02（2026-10-31）

新增「區域地質分區（Murray Basin）≠ Project」、「歷史地球化學異常（Pindari）≠ REO MRE」、「IOCG 伴生 REE 化學訊號（Acropolis）≠ REE 產品資源」的來源範圍證據。公開 PDF 索引文字、政府目錄／資料庫與研究摘要只能標為有界來源複核，不得冒充已下載／全篇核對原始 PDF；保留 `original_document_sha256` 空白。新增 [167 筆進度追蹤](audits/2026-10-31_external_primary_progress_167.csv) 只補充查核記錄，不覆寫 frozen source 或變更 C1／13 案 Gate／MCDA。


## 2026-10-31 — ADR-P0-028: Source review freeze vs cohort admission（**PROPOSED — 待使用者決定**）

| 決策項目 | 內容 |
| --- | --- |
| Decision ID / Status | `ADR-P0-028` / **PROPOSED**；尚未 `ACCEPTED`、沒有實際來源凍結 |
| Scope | P2–P4 339 筆的 **C0 source-level review workflow**，不涉及 C1 六層 Gate 或 MCDA cohort |
| 背景證據 | 2026-10-29 固定 339 source IDs；最新 public-text P2 16、P2 desk 12；P3/P4 native-only 151 source rows = 100 州別＋原生 ID 工作群組，51 組來源重複定位；119 筆保存原件相關內容且有明確 non-target/geology/scope-transfer bounded finding |
| F1 保守方案 | 原件有相關內容、來源精確定位、可重開條件及獨立簽核後才 `SOURCE_SCOPE_FROZEN`；先逐案審 119 候選 |
| **F2 建議方案** | F1 + 對剩餘 C0 native-only 來源允許 `NATIVE_ONLY_ARCHIVED_PENDING_EXTERNAL_EVIDENCE`，但只表示停止無新線索的重複爬查，**不聲稱 fulltext、無 REE、無 Project 或 C1 EXCLUDE**。兩類都須來源 ID/日期/再開條件/審核與版本；可因新原件或新 Project 規劃重開 |
| F3 嚴格方案 | 一律要求新技術 PDF 或原始報告全文後才 C0 結案；留作比較，不自動採納 |
| Source freeze vs raw snapshot | 2026-10-29 原始政府快照已凍結；此 ADR 僅決定 **source review 結案／中止搜尋規則**，必須透過後續簽章與版本覆蓋，不改歷史 row |
| 單筆最小核對 | `target_id`、官方原生 ID、來源版本/SHA、頁碼或政府 HTML 段落、scoped finding、closure reason、reviewer、reviewed_at、reopen trigger、freeze_rule_version；缺一者保持 HOLD |
| C1 Gate | 永遠獨立使用 ID/ROLE/WINDOW/JORC/PANEL/GIS_RELEASE，所有 B05 339 筆仍 `NOT_ADMITTED` |
| 影響／測試 | 影響 Aim A 來源母體清理，避免同一 source-native ID 重複取件；Aim B/C 不得由 C0 freeze 產生正式排名。參見 [B05 總報告](audits/2026-10-31_p234_b05_triage_and_freeze_proposal.md) 與可重跑 Python/tests |
| Approval | **未填／待使用者明確決定凍結層級與最小證據門檻** |



## 2026-10-31 — ADR-P0-029: Cross-tier resource/identity source reconciliation（**PROPOSED / unsigned**）

| 欄位 | 判讀與規範 |
| --- | --- |
| Scope | 339 個凍結來源 ID 的證據判讀 overlay，原 `source_snapshot=2026-10-29` 不變。 |
| Elaine Dorothy resource contrast | 既有 P3 兩筆明確保留 2010 年 **83,000 tonnes Inferred @ 3,200ppm TREO，280ppm U₃O₈，cutoff 200ppm U₃O₈** 的歷史 JORC 文獻，P2 同名 Legacy 原文字摘要過度概括。由 2010 CYU 原始發行人年報/簡報更新 P2 衍生判讀，不改源表。歷史 REO 資源仍無 current as-of C1 approval。 |
| Bell's Monazite identity | 與 NTGS Mt Todd/Wolfram Hill Monazite 地質目標不同的 Bynoe/Cox Peninsula `Bells Mona` 是 Sn/Ta pegmatite 礦點；錯誤同名候選要分開，在官方地理/礦權/原生座標與人工簽核前不得 alias merge。 |
| Other bounded findings | Arthur Popes carbonatite REE-Y veins、Blueys Folley REE anomaly、Edwards Creek/Edwards Creek South 分離、Spartacus 單次樣本陰性、Skyfall 2015 歷史 preliminary scoping/surrender、Pyramid Lake gypsum，均保留原始 scope。 |
| Implementation / Impact | [B06 原因分類報告](audits/2026-10-31_p234_b06_reasons_and_followups_report.md)、[339 可編輯原因表](audits/2026-10-31_p234_b06_reason_classification_339.csv)。新增 4 筆 P2 source text scope reviews、8 筆非獨立確認 native-ID 的 locator；P2 desk queue 剩 8、P3/P4 native-only 151。Aim A 證據語意更清楚，B/C 尚未進入真實排名。 |
| Freeze and Gate | 前輪 ADR-P0-028 **仍為 PROPOSED**，119 份 C0 closure candidates 沒有任何人工簽核；C1 ID/ROLE/WINDOW/JORC/PANEL/GIS_RELEASE、資料庫核准和 MCDA 一律 HOLD。 |
| Approval | **尚未核准**；需要原始法定礦權、Competent Person/JORC 表、官方 native feature／Project 範圍及審查簽名才可進入其他 Gate。 |



## 2026-10-31 — ADR-P0-030: 雙層 C0 Source Freeze Rule（**ACCEPTED policy; per-source signoff pending**）

| 欄位 | 決策 |
| --- | --- |
| Decision | 採用 F1 來源範圍結案 + F2 原生圖徵暫停搜尋的雙層 C0 規則；凍結的是**某日來源判讀/暫停取件工作**，不更改原始檔案或真實地質潛力 |
| 前置草案 | `ADR-P0-028` 討論的 F2 方案被核定為正式政策；原決策歷史不刪改 |
| Source snapshot | 2026-10-29 的 frozen source IDs 與 `selected_feature_sha256` 永久保留，不回寫舊 approval |
| F1 | 只接受原件相關頁面有界的地質、歷史/非 REE 或跨範圍轉移不成立的判讀；證據定位、原始 SHA、審核人及重開條件必需 |
| F2 | 只有 native-only source 可以申請；附明確、可重現的「負向查詢紀錄」，有尚待精確來源對應的新報告 locator 者不得暫停 |
| Current inventory | F1 119 審核候選；F2 151 預審（其中 6 有未解 source locator）；實際 signed F1 0、F2 0 |
| Governance | `config/c0_freeze_policy_v1.json`、`inputs/review_decisions/c0_source_freeze_signoffs_v1.csv`、[操作規範](C0_FREEZE_AND_C1_C2_POLICY.md)；未簽核者一律待審，不得宣稱完成 |
| Reopen | 新官方原件/礦權/REE Resource/Project footprint/重要反證新增版本，舊資料不刪除 |
| Cohort/MCDA | F1/F2 不修改 C1/C2、不產出 JORC 或 MCDA 主排名；研究 Aim A 資料查核與 Aim B/C 後續模型隔離 |

## 2026-10-31 — ADR-P0-031: Strict C1, verified-identity C2 and changed research priority（**ACCEPTED cohort definition**）

| 欄位 | 決策 |
| --- | --- |
| C1 | 限經獨立核准的澳洲 active pre-FID REE Project，必須通過 ID / ROLE / WINDOW / JORC / PANEL / GIS_RELEASE 六 Gate；同範圍稀土氧化物資源、原始經濟研究與截止日版本必須核准 |
| C2 | 具**獨立 Project ID 與 REE 產品角色簽核**、但未滿足 C1 其他條件的 verified extended Project，僅供 coverage 與獨立探索性分析；不因名稱/來源圖徵/群組自動納入 |
| C3 | 超出 2026-10-29 pre-FID 但有可核歷史時點者，另建歷史/事件研究；不能混入 C1 |
| Panel | 六構面研究要求維持；9/12 準則仍是候選，尚待事前 selection decision，不能看排名後調整 |
| Priority | **C1 主線，P2–P4 補查為支線**；先 7 個已有 Study 線索群組、8 個時窗待驗證群組，P1 13 source cases 維持獨立 identity crosswalk queue |
| Current data state | 39 group reviews，28 初步 C2 身分審查候選（未准入），13 個 P1 正向 source-case 另列；**C1 0、C2 0 signed**，皆待獨立來源文件與審核 |
| Inputs/outputs | [C1/C2 39 groups](audits/2026-10-31_c1_c2_project_review_39.csv)、[P1 crosswalk 13](audits/2026-10-31_c1_p1_positive_case_crosswalk_13.csv)、`config/cohort_c1_c2_policy_v1.json` |
| QA | 可重跑 `python scripts/build_c0_freeze_c1_c2_v1.py --check`；任何後續 signed `C1_PASS` 先驗證 Project identity、當期 Study、REE JORC、approved panel 與 GIS 原件，否則程式阻止 |
# 2026-11-01 implementation verification note

`CENSUS-ENTITY-20261101` integrates the existing 487-source Census and 39-group documentary review through `csv-build --review-dir`. This is an implementation of existing identity/cutoff/approval constraints; it changes no Project definition, evidence decision, cohort, criterion or weight. Stable candidate IDs are retained, independent approval remains required, C1/C2 stay 0. [Acceptance and reproducible commands](audits/2026-11-01_census_entity_acceptance.md).
