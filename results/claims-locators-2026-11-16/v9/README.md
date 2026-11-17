# 第 9 版：P1／P6 準備與只讀診斷，因 SAME 流失停止

基準 `1e0b833`（程式 `3e7c24e`）；比較基準第 8 版 CI。沿用 [Draft PR #11](https://github.com/lleeoo0611-stack/AU_REE_V2/pull/11)，不 merge。

**已停止，未啟動本輪正式 CI。** 嚴格採研究者指定的 15 位有效數字後，指定的 13 格可新增 SAME，但第 8 版的一格 SAME 會流失：ACDC Pr6O11。這與「第 8 版 SAME 任一格流失就停」衝突；沒有改數值、沒有自行保留舊規則去通過守門。[停止核對](preflight_stop.json)。

## P1：兩項要求的衝突

現行未追蹤比較程式已先原樣保存為 tools/compare_ci_cells.py，提交 `30479c9`，再修改；Git 僅正規化 CRLF 為 LF，程式內容未改。可由該提交稽核原先的 equal 函式，其中有未公開記在比較 CSV 的 REFERENCE_PRESENTATION_PRECISION 規則：按參考值的小數位數四捨五入正式值。

新比較規則使用 Decimal(format(Decimal(x), '.15g')) 比較數值（格式化後尾端零不改變數值），非數值照字串，原 1e-12 類別保留給 15 位仍不同但落在容差內者。**不保留舊參考顯示位數四捨五入規則。**

指定 13 格的重分類集合完全吻合，沒有任何原 DIFFERENT 被吸收；Tb4O7 維持 DIFFERENT。參見 [p1_reclassified.csv](ci/p1_reclassified.csv)。

|流失格|參考值|正式值|15 位後參考|15 位後正式|新分類|
|---|---:|---:|---:|---:|---|
|ACDC Pr6O11_氧化鐠_kt|15.5|15.48922242604142347330153754|15.5|15.4892224260414|DIFFERENT|

舊規則將正式值四捨五入到一位小數，因此原本判 SAME；新規則不會。13 格新增、1 格流失，**本機重分類預覽**淨增 12，SAME 為 889；不是 CI 驗收結果。固定 609 清單預覽仍 609／609，但第 8 版 877 格 SAME 只剩 876／877，依較嚴格的新守門停止。

|分類|第 8 版 CI|僅 P1 本機重分類預覽|
|---|---:|---:|
|SAME|877|889|
|KNOWN_STRUCTURAL_DIFFERENCE|44|44|
|NUMERIC_TOLERANCE_SAME|13|0|
|DIFFERENT|32|33|
|FORMAL_MISSING|1135|1135|

[完整預覽](ci/p1_comparison.csv)、[原 SAME 流失](ci/p1_v8_same_losses.csv)、[驗證紀錄](ci/p1_validation.json)。需要研究者決定：保留舊顯示精度規則作後備，或嚴格採 15 位並明確核准這一格的分類改變；兩者都不修改參考值或正式值。在決定前不推執行 CI 的提交。

## P2：停在核准前

已對上 117 格／35 專案／30 個來源 SHA；227 列定位需求中，202 列有兩個頁面實際存在的標記（122 個不同提案），110 格的所有定位已備齊。其餘 7 格的 25 列都缺同一份已在 CI 取得、但正式本機快取未保留的 zmi_cascade20230725（9e3227e2cfbc…）原件；沒有改讀實驗原件或人工資料，也沒有向 ASX 補抓。

[p2_marker_proposals.csv](p2_marker_proposals.csv) 的 approved **全部空白**。同一定位可能對應多格，proposal_id 相同者是重複定位，不應把列數當可恢復格數。[117 格盤點](p2_cells.csv)；另有其他原因的 110 格列於 [p2_additional_blockers.csv](p2_additional_blockers.csv)，未處理它們。

tools/locators_from_ci_cache.py 已準備在唯一一次正式 CI 取得同 SHA 原件後，只讀既有快取補缺的提案；不另發 HTTP、不改 claims。因 P1 停止，這一步尚未在 CI 執行。目前可備齊的上限是 110 格；若取得缺少原件並完成全部定位，才可提高到 117 格，仍須研究者逐列核准與日後建置驗證，不保證全變 SAME。

## P3、P4、P8：只讀結論

- [P3 診斷](p3_queue_diagnosis.md)、[52 格逐格表](p3_cells.csv)：4 格在解除 alias／required_source_keys gate 後有可用輸入（未 CI 驗證、不保證 SAME）；3 格仍卡 context 單標記；45 格仍卡不同的身分或其他原件。不是舊 manifest，也不是 52 格都能靠改 reason 恢復。資料 key 提案可為 src 0 行，但本輪不套用；改善錯誤歸因估 4–8 行，通用 alias 重用需另審。
- [P4 ACDC TREO](p4_acdc_treo.md)：0.0584% 已宣告於同 SHA 原件第 3 頁。partial bundle 只組 ore_mt，並抑制完整資源旗標；現行程式不讀例外旗標，因此只加資料無效。另核准受控旗標加約 8–14 行 src，最多可恢復原三格；Wimmera 必須在旗標缺席／無原礦品位時逐格保持不變。未改任何數值或程式。
- [P8 頁面表](p8_page_check.csv)：39 格（其中 11 格 queue 只含這原因）、15 個來源×頁。實際有 6 個不同 SHA，另有一筆 NULL 身分 issue 對應已計入的 Rocky Gully 原件，所以沒有捏造第 7 個 SHA。逐頁保留原始／正規化前 300 字與全文標記頁碼。分類為：{"其他": 9, "正規化差異": 1, "頁碼偏移": 3, "標記錯誤": 2}。本機使用同一 extract_page 的原生與定位文字層；沒有已註冊 OCR model，未下載模型、未降低標準。queue 是專案級，不代表所列每個 binding 都失敗；本機通過而 CI queue 有錯誤者明列「其他」。11 格只是待診斷上限，不保證更正頁碼即可恢復。

## P6：窄範圍存證準備，尚未 CI 採用

tools/verify_pre_cutoff_evidence.py 負責 fetch 指定實驗分支、確認 commit 在該 ref、檢查 repo 檔案含 SHA 或 RAW_FILE 的完整 SHA、核對可綁定該 commit／後繼 head 的 GitHub PushEvent，並取 max（committer 時間、最早可證 PushEvent 時間）的 UTC 日期。輸出綁定 sources.json SHA 的驗證檔，src 只有 valid=true、同 key／SHA 且日期在截日前才採 min（原可取得日、存證日）；取得時間不變。其他來源不套用此例外。實際 CI 會重查，不把本機診斷當 CI 成立。

|來源|存證種類|commit|提交時間 UTC|推送時間 UTC|evidence_date|本機診斷|
|---|---|---|---|---|---|---|
|reviewed_source_31a205168b6ae647|RAW_FILE|8d57b53|2026-11-12T22:32:46+00:00|未證明|不成立|PUSH_TIME_NOT_PROVEN_FOR_COMMIT|
|reviewed_source_521f635719be1686|SHA_RECORD|aeaed57|2026-11-10T11:14:45+00:00|2026-11-10T11:14:55+00:00|2026-11-10|成立|
|reviewed_source_9e1ac5bb894d9077|SHA_RECORD|3a0f124|2026-11-10T11:30:14+00:00|2026-11-10T11:42:29+00:00|2026-11-10|成立|
|reviewed_source_a197d77204b48c23|SHA_RECORD|3a0f124|2026-11-10T11:30:14+00:00|2026-11-10T11:42:29+00:00|2026-11-10|成立|

[逐項存證診斷](p6_local_validation.json)、[PushEvent 原件](p6_push_events.json)。三個 GA 來源的本輪回應還須 SHA 完全相同；不一致依舊 SOURCE_SHA_CHANGED，不能用存證覆蓋。在未執行 CI 前，P6 正式新增 SAME **尚未驗收**，可用存證的目前上限為 GA 22 格。

VIC 8d57b53 的 repo RAW_FILE SHA 驗證通過，但查不到可綁定該提交的 PushEvent 或當時 CI。CreateEvent 只有 ref，沒有初始 head，不能自行推論該提交當時已上傳。因此 **VIC 存證不成立，現有 2816f156…、previous_source_sha256、快照與截日都未改，也未提交 31a205… 原件**。兩份原始資料算出的指定四格座標完全一致，見 [p6_vic_compare.csv](p6_vic_compare.csv)，但值相同不能代替推送證明。

補齊方法：提供／找到截日前 head 等於 8d57b53 或其後繼提交的 GitHub PushEvent／CI 紀錄，再依相同驗證器重驗；或由研究者另行決定是否接受其他能綁定歷史 head 的 repo 存證。不能用提交日期、檔案 mtime、現在補存或相同座標反推取得日。在此以前維持 SOURCE_AFTER_CUTOFF，不移動研究截日。

## 行數、測試與停止狀態

src 僅 acquisition.py 日期證據 helper、三個呼叫點與註解：+26/-3，增刪合計 29、淨增 23；歷來 git diff 070df10 算法累計 **2,157／2,164**。主機停止與 robots 的 StrictTransport AST 完全相同，第 817 行檢查順序不動；claims、係數、推導、data、R 不變。config 只有四筆選填 pre_cutoff_evidence，其他欄位逐項不變。

本機完整 470 項回歸 PASSED；嚴格 P1 規則定稿後，受影響的 5 項比較測試另行重跑通過。新增 18 項測試（比較 5、存證 11、快取 2），R 通過。先前 468 項的兩個失敗只因舊測試禁止所有實驗線路徑，現僅對四筆已核准存證 metadata 精確豁免，乾淨建置 5 項亦重跑通過。

本輪正式 CI、正式狀態增減與 Phase 20–22 MATCHED **未執行／未驗收**，因 P1 已在送 CI 前證明會違反原 SAME 守門。第 8 版成功 CI 不能當作本版結果。準備變更以 skip ci 保存、PR 維持 Draft，不 merge，等待研究者對 P1 的決定與 P2 的逐列核准。
