# 第 9 版：P1 比較規則與 P6 截日前存證驗收

基準 1e0b833；科學程式與資料驗收提交 `955da5d25f4c1c24512e42b9861cfb86a23d2c49`。[乾淨 CI](https://github.com/lleeoo0611-stack/AU_REE_V2/actions/runs/44170481863)。[Draft PR #11](https://github.com/lleeoo0611-stack/AU_REE_V2/pull/11)，target feat/same-sha-fallback-20261116，不 merge。

**609／609 與原 877／877 SAME 全數守住。** 研究離線回歸亦通過，已停止等待審查。

|狀態|第 8 版 CI|本輪 CI|增減|
|---|---:|---:|---:|
|SAME|877|900|+23|
|KNOWN_STRUCTURAL_DIFFERENCE|44|44|+0|
|NUMERIC_TOLERANCE_SAME|13|0|-13|
|DIFFERENT|32|34|+2|
|FORMAL_MISSING|1135|1123|-12|

新增 SAME 23 格，分組 {"P6_PRE_CUTOFF_EVIDENCE": 10, "P1_15_SIGNIFICANT_DIGITS": 13}；離 2,101 格全 SAME 尚差 1201。沒有反事實重建，分組依前次逐格原因與本輪輸出歸因。

|專案|欄位|前次狀態|新增分組|
|---|---|---|---|
|AU-2a3a86a4d971e9f9838d|緯度|FORMAL_MISSING|P6_PRE_CUTOFF_EVIDENCE|
|AU-2a3a86a4d971e9f9838d|經度|FORMAL_MISSING|P6_PRE_CUTOFF_EVIDENCE|
|AU-4286ab9c245effb445ff|緯度|FORMAL_MISSING|P6_PRE_CUTOFF_EVIDENCE|
|AU-4286ab9c245effb445ff|經度|FORMAL_MISSING|P6_PRE_CUTOFF_EVIDENCE|
|AU-447261eed0e81eae88bf|緯度|FORMAL_MISSING|P6_PRE_CUTOFF_EVIDENCE|
|AU-447261eed0e81eae88bf|經度|FORMAL_MISSING|P6_PRE_CUTOFF_EVIDENCE|
|AU-447261eed0e81eae88bf|La2O3_氧化鑭_kt|NUMERIC_TOLERANCE_SAME|P1_15_SIGNIFICANT_DIGITS|
|AU-447261eed0e81eae88bf|CeO2_氧化鈰_kt|NUMERIC_TOLERANCE_SAME|P1_15_SIGNIFICANT_DIGITS|
|AU-447261eed0e81eae88bf|Nd2O3_氧化釹_kt|NUMERIC_TOLERANCE_SAME|P1_15_SIGNIFICANT_DIGITS|
|AU-447261eed0e81eae88bf|Sm2O3_氧化釤_kt|NUMERIC_TOLERANCE_SAME|P1_15_SIGNIFICANT_DIGITS|
|AU-447261eed0e81eae88bf|Eu2O3_氧化銪_kt|NUMERIC_TOLERANCE_SAME|P1_15_SIGNIFICANT_DIGITS|
|AU-447261eed0e81eae88bf|Gd2O3_氧化釓_kt|NUMERIC_TOLERANCE_SAME|P1_15_SIGNIFICANT_DIGITS|
|AU-447261eed0e81eae88bf|Dy2O3_氧化鏑_kt|NUMERIC_TOLERANCE_SAME|P1_15_SIGNIFICANT_DIGITS|
|AU-447261eed0e81eae88bf|Ho2O3_氧化鈥_kt|NUMERIC_TOLERANCE_SAME|P1_15_SIGNIFICANT_DIGITS|
|AU-447261eed0e81eae88bf|Tm2O3_氧化銩_kt|NUMERIC_TOLERANCE_SAME|P1_15_SIGNIFICANT_DIGITS|
|AU-447261eed0e81eae88bf|Yb2O3_氧化鐿_kt|NUMERIC_TOLERANCE_SAME|P1_15_SIGNIFICANT_DIGITS|
|AU-447261eed0e81eae88bf|Lu2O3_氧化鎦_kt|NUMERIC_TOLERANCE_SAME|P1_15_SIGNIFICANT_DIGITS|
|AU-447261eed0e81eae88bf|Y2O3_氧化釔_kt|NUMERIC_TOLERANCE_SAME|P1_15_SIGNIFICANT_DIGITS|
|AU-7537d9555628040fab40|緯度|FORMAL_MISSING|P6_PRE_CUTOFF_EVIDENCE|
|AU-7537d9555628040fab40|經度|FORMAL_MISSING|P6_PRE_CUTOFF_EVIDENCE|
|AU-cc4e217a90b7123dce0a|緯度|FORMAL_MISSING|P6_PRE_CUTOFF_EVIDENCE|
|AU-cc4e217a90b7123dce0a|經度|FORMAL_MISSING|P6_PRE_CUTOFF_EVIDENCE|
|AU-d28382dfa82f1664065e|磁鐵稀土佔TREO_pct|NUMERIC_TOLERANCE_SAME|P1_15_SIGNIFICANT_DIGITS|

## P1 核准比較規則

先提交原比較程式 30479c9，再加入 Decimal 的 15 位有效數字比較。研究者 2026-11-18 核准保留既有顯示精度後備規則，兩側值完全不改。指定 13 格恰好由 NUMERIC_TOLERANCE_SAME 變 SAME，沒有吸收原 DIFFERENT。原有相對容差類別仍獨立列出，不算 SAME。Pr6O11 仍依舊顯示精度分類，Tb4O7 仍為 DIFFERENT。[核准紀錄](p1_researcher_approval.json)、[13 格](ci/p1_reclassified.csv)、[原 877 格流失清單（應為空）](ci/v8_same_losses.csv)。

## P6 存證的 CI 結果

|來源|種類|提交時間 UTC|推送時間 UTC|存證日|驗證|採用|取得狀態|
|---|---|---|---|---|---|---|---|
|reviewed_source_31a205168b6ae647|RAW_FILE|2026-11-12T22:32:46+00:00|||False|False|COMMITTED_SNAPSHOT_SAME_SHA|
|reviewed_source_521f635719be1686|SHA_RECORD|2026-11-10T11:14:45+00:00|2026-11-10T11:14:55+00:00|2026-11-10|True|True|FETCHED_SHA_VERIFIED|
|reviewed_source_9e1ac5bb894d9077|SHA_RECORD|2026-11-10T11:30:14+00:00|2026-11-10T11:42:29+00:00|2026-11-10|True|True|FETCHED_SHA_VERIFIED|
|reviewed_source_a197d77204b48c23|SHA_RECORD|2026-11-10T11:30:14+00:00|2026-11-10T11:42:29+00:00|2026-11-10|True|True|FETCHED_SHA_VERIFIED|

三個 GA 來源全部 HTTP200、SHA相符並採用2026-11-10存證日；這解除22格座標的日期阻擋，但只恢復10格SAME。另12格轉為RULE_INPUT_MISSING：10格的專案queue仍為MISSING_PAGE_OR_TWO_MARKERS，2格（AU-af44c2bd1173b453953f）仍有其他身分／來源未取得。這12格不是GA存證或SHA驗證失敗，不自動改標記或補值。[原26格逐格結果](ci/p6_target_cell_results.csv)。

另有兩格「總說明」由空白變DIFFERENT（AU-7537d9555628040fab40、AU-cc4e217a90b7123dce0a）：現在有GA代表點說明與dataset/datum/feature_id，但參考文字另含尚未具備的開發階段或氧化物一致性句子，且代表點括號內容不同。沒有把這兩格算SAME，也沒有原SAME流失。[完整差異](ci/remaining_differences.csv)。

所有新取得位元組仍必須同 SHA；只有這四個明確宣告來源可使用存證例外。存證檔與 sources.json 完整 SHA 綁定，實際取得時間不回填。VIC 原始 repo 檔案雖同 SHA，但推送時間沒有可綁定 commit 的證明，現有快照與宣告不動，8 格仍受 SOURCE_AFTER_CUTOFF 限制。兩份原件的指定四格座標相同，也不能取代日期證明。[逐來源採用收據](ci/p6_evidence_adoption.csv)、[驗證原件](ci/pre_cutoff_evidence_verified.json)、[PushEvent](ci/pre_cutoff_evidence_events.json)、[VIC 四格診斷](p6_vic_compare.csv)。

## P2 提案停在研究者核准前

117 格／35 專案／30 SHA，227 列定位需求；本輪 CI 只讀同 SHA 快取補齊 25 列，全部定位已提案的格數為 117／117，共131個不同定位提案。所有 approved 空白，claims 沒有寫入；不宣稱提案等於可恢復 SAME。原本機表另存 [提案前版](p2_marker_proposals_pre_ci.csv)，研究者請審 [完整提案](p2_marker_proposals.csv) 並填 approved；[逐格需求](p2_cells.csv)、[摘要](p2_ci_summary.json)。另 110 格混有其他阻擋原因，仍只列報告。

## P3、P4、P8 只讀診斷

[P3](p3_queue_diagnosis.md)：52 格中，44 格另缺身分原件、3 格 context 單標記、4 格 Greater Brothers 被 required_source_keys gate 擋下、1 格 Jupiter 需要另一份原件。不是 52 格都能靠 reason 修正恢復。資料 key 修正估 src 0 行；錯誤歸因改善估 4–8 行，均未套用。

[P4](p4_acdc_treo.md)：0.0584% 已宣告，但 partial bundle 只組 ore_mt 並抑制完整資源旗標。未來受控例外估 8–14 行 src，目前沒有改程式或值，Wimmera 行為不變。

[P8](p8_page_check.csv)：39 格、11 格單一原因、15 個來源×頁。實際 6 個不同 SHA，另有一筆 NULL identity issue 指向已計入的 Rocky Gully。分類：其他 9、正規化差異 1、頁碼偏移 3、標記錯誤 2；保留每頁前 300 字與全文 marker 頁碼。本機沒有已註冊 OCR model，未下載模型、未改門檻或宣告。

## 剩餘缺漏與 ACDC

|缺漏原因|格數|
|---|---:|
|RULE_INPUT_MISSING|323|
|NO_SOURCE_VALUE|62|
|SOURCE_NOT_ACQUIRED|734|
|SOURCE_AFTER_CUTOFF|4|

ACDC 本版新增14格SAME：P1比較分類12格、P6座標2格，並不是14個新換算數值。15個氧化物CI值與第7版Decimal診斷逐一相同，本輪claims、物種係數、兩格推導與既有換算數值不動。[十五筆](ci/acdc_hm_values.csv)、[總說明與合約](ci/acdc_summary.json)、[其他專案逐格變化](ci/other_project_changes.csv)、[全表比較](ci/cell_comparison.csv)。

## 測試、行數與流程失敗紀錄

src +26/-3，增刪 29、淨增 23，累計 **2,157／2,164**，只用於核准的 P6 窄範圍存證。累計相對070df10由2,130增加27；本版相對1e0b833直接增刪29，因重疊修改而不能把兩個基準的增刪直接相加。[行數稽核](src_line_budget.json)。主機停止、robots、B1、OCR 門檻未動；data、claims、R 均與 1e0b833 相同。新增 18 項測試，乾淨 CI Python 470 項與 R 1 項均通過。

研究初次 run [44170481839](https://github.com/lleeoo0611-stack/AU_REE_V2/actions/runs/44170481839) 在測試前因新增步驟位置錯誤而失敗；修補 87b51f6 只移回 heredoc 結尾並加既有測試檢查，不改科學程式或資料。[原始失敗證據](ci/research_initial_failure.json)、[修補](research_workflow_fix.patch)。

經研究者另外核准，只補跑離線研究 CI，[run](https://github.com/lleeoo0611-stack/AU_REE_V2/actions/runs/44173975251)，提交 `87b51f6dd8ad7fcf46bec2de0a4de7f052d45535`。與乾淨建置提交的 src/data/config/R/tools 完全相同；470 項 Python、R 通過，Phase 20、21-a、21-b、22-a、22-b 均 MATCHED。[研究證據](research_ci_checks.json)。沒有重跑來源擷取或乾淨總表建置。
