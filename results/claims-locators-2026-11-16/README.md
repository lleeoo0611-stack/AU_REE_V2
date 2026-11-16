# Claims locators：T0 未通過，停止待決定

狀態：`T0_FAILED_STOP_REQUIRED`。依任務「少任何一格就停下來」停止 T1–T4。沒有產生標記提案、沒有更新 SHA，也沒有修改宣告。

本次在指定 `e84c0e01e1062882d2b3357e27f66189dc52e453` 的獨立乾淨工作樹起跑；起始沒有 work 資料，也沒有未提交變更。`all --refresh --as-of 2026-11-13` 成功完成，run ID：`20261116T153547-12e4d380`。這是一次本機 Windows 重建，尚非 T4 的乾淨 CI 驗收。

## T0：609 格保護結果

**599／609 格仍為 SAME，10 格流失。** 完整保護清單見 [baseline_609_guard.csv](baseline_609_guard.csv)，流失清單見 [baseline_609_losses.csv](baseline_609_losses.csv)，附逐格原因的表見 [t0_lost_cell_causes.csv](t0_lost_cell_causes.csv)。

|分類（固定 2,101 格）|e84c0e0 已發布結果|本次乾淨重建|增減|
|---|---:|---:|---:|
|SAME|609|599|-10|
|DIFFERENT|70|66|-4|
|KNOWN_STRUCTURAL_DIFFERENCE|0|0|0|
|FORMAL_MISSING|1,422|1,436|+14|

DIFFERENT 減少的 4 格全部轉成 FORMAL_MISSING，並非修正成功。T3 未執行，來源名稱／URL 的既知差異仍未重新分類。完整比較表另外有空白格、ID 及既有結構差異，不納入 2,101 格分母。狀態轉換見 [baseline_status_transitions.csv](baseline_status_transitions.csv)。

## 流失的 10 格與直接原因

每個下列專案均流失兩格：「開發階段代碼」原為 `A1`、「開發階段類別」原為 `探勘`，本次均為空白，缺漏碼均為 `RULE_INPUT_MISSING`。

|project_id|專案|流失格數|OCR 受阻的實體 PDF 頁碼|
|---|---|---:|---|
|AU-2ab3e8eb7b5784e64f9b|Duke Rare Earth Project|2|r6_identity_duke：1, 5, 6, 7, 8|
|AU-3eaa906d8230334ef698|Mukinbudin REE Project|2|r6_identity_mukinbudin：1；r17_primary_18：1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12|
|AU-794821a2df9b7a244f96|Perenjori Uranium–REE Exploration Project — HRE|2|hre_perenjori20250613：2, 3, 8, 9, 10, 11, 12, 13, 14|
|AU-b31d00e2272ffa6ccbd3|Peak Charles REE Project|2|r6_identity_peak_charles：1, 12, 15, 16, 18, 23, 25, 27|
|AU-d99cf357d160df73387c|Southern Cross Li-REE Project — GCX|2|auto2_identity_southern_cross：1, 3, 5, 6, 7, 19, 45, 46, 47, 48, 55|

直接阻擋原因是 `LOCAL_OCR_EXECUTABLE_NOT_AVAILABLE`，共 46 筆專案×原件×頁面紀錄。這次本機環境準備不完整：雖已取得與既有 CI 相同套件的英文模型，卻沒有 Tesseract 執行檔。既有階段掃描另以獨立執行檔重複 OCR；模型檔無法取代該執行檔。`summary_stage_fields` 遇到任何 blocker 就保留階段代碼／類別為空白，規則按原設定生效。這些格原來由「完整掃描後沒有可採用的進階階段證據」規則產生，不能在掃描未完成時補回 A1。

**受影響的 6 份原件全部已 fresh HTTP 200 取得且 SHA 一致**（Mukinbudin 涉及 2 份），不是這些原件下載失敗或 SHA 改變。完整來源、SHA、頁碼、採用收據在 [t0_stop_diagnosis.json](t0_stop_diagnosis.json) 與 [t0_ocr_blocked_pages.csv](t0_ocr_blocked_pages.csv)。既有 `MISSING_PAGE_OR_TWO_MARKERS` 審查項也保留在逐格缺漏說明，未被改寫或忽略。尚未修補環境或重跑，不能宣稱裝好 OCR 後必然恢復 609 格。

## 取得狀態與缺漏統計

203 筆來源，47 個主機 DNS 全部成功；`NETWORK_VALID`，2／203 筆網路錯誤（0.985%，低於既有 5% 閘門）。兩筆分別為 `disr_remp_2025` 讀取逾時、`qld_minocc_status_live` 連線遭遠端關閉。它們不是這 10 格的直接阻擋原因。收據見 baseline_acquisition_report.csv、baseline_asx_probe.csv、baseline_dns_preflight.csv、baseline_network_status.json、baseline_fallback_report.csv。

全部 93×51 格總表的缺漏理由（與前次相同統計範圍；不只 2,101 格）：

|reason|格數|
|---|---:|
|HOST_STOPPED_4XX|199|
|NOT_APPLICABLE_NO_MRE|1230|
|NOT_APPLICABLE_STAGE|7|
|NO_SOURCE_VALUE|200|
|RULE_INPUT_MISSING|921|
|SOURCE_NOT_ACQUIRED|1407|
|SOURCE_SHA_CHANGED|8|

## 範圍與後續

- src 新增 0 行、刪除 0 行；claims、sources、evidence_policy、原件快照、manifest 與 Phase 凍結結果均未變更。沒有新增研究網路來源。
- T1／T2／T3／T4 均未執行。33 筆身分宣告的 A／B／C 分組僅做資料格式盤點，未讀頁面產生提案；C 組 7 案未改動。本輪尚無可供 approved=Y/N 的提案 CSV。
- 本次未執行 T4 的測試與 Phase 20–22 重建。前次已發布 CI 的 408 測試及 Phase 20–22 MATCHED 為歷史證據，不代表本輪已驗收。
- 建議經研究者決定後，使用既有 CI 的完整 OCR 環境重跑 T0；不需修改 src、頁碼、SHA 或任何驗證規則。仍須實際檢查原始 609 格，不能只以 CI build 成功取代。
- 本報告以 Draft PR 發布，target 為 `feat/same-sha-fallback-20261116`，不 merge。提交使用 `[skip ci]`，避免在 T0 停止期間觸發另一輪自動建置；未執行與跳過均不記為 PASS。

待研究者決定是否改用完整 CI OCR 環境重跑 T0；在獲得方向前不繼續 T1–T4。
