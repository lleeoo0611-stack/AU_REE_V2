# 第 5 版：GA robots、ACDC 停止證據與 VIC 原始回應診斷

基準 `e8dc840`；分支 `feat/claims-locators-20261116`；[Draft PR #11](https://github.com/lleeoo0611-stack/AU_REE_V2/pull/11)，維持 Draft、不 merge。研究者：賴力維，2026-11-17。

[乾淨 CI 43948787479](https://github.com/lleeoo0611-stack/AU_REE_V2/actions/runs/43948787479)，609 守門 **609／609**。

## GA robots 403

src 僅將 `/robots.txt` 專用例外 `(404,410)` 改為 `(403,404,410)`，**一行內容替換、src 淨行數 0**，累計仍 2,074／2,074。401、429 及其他狀態未加入；非 robots 資料請求的 403 仍停止主機；200 Disallow 仍禁止。限速、URL、SHA、User-Agent 與登入／CAPTCHA 等規則均未改。

收據標記由 workflow 的既有報告步驟產生，使用既有 `stop_reason` 欄位附記 `ROBOTS_HTTP_403_TREATED_AS_UNAVAILABLE`，不新增 src 欄位或行數。判定依據是共用 before_request 在首次 GA 資料請求之前先請求 robots，收據第一個 GA HTTP 嘗試實際為 403；保留原有資料錯誤原因與所有 HTTP 嘗試。標記是主機 robots 背景，並不宣稱每一筆已保存快照都有新網路請求。

GA 共 10 筆登記來源；本輪重點為上輪 9 筆 UNAVAILABLE／HOST_STOPPED，原先 COMMITTED_SNAPSHOT_SAME_SHA 的 ga_aimr 另列對照。未設定宣告 SHA 的既有政府來源，SHA 比對列為未宣告，不能稱為 SHA 驗證成功。

## ACDC：依原件停止，claims 不改

對來源 SHA `22016f67e614f73963e5a2252e0ec78184ed3906d668649e0dbdb17c365dba59` 的實體第 12 頁，同時核對原生文字與視覺表格。表頭實際為 **Pr2O3、Tb2O3**，Total 格為 **0.11 %HM、0.011 %HM**；不是合約要求的 Pr6O11、Tb4O7。不能直接替換或改化學物種，也沒有用 620×2.2% 的推算量填作原件報告 HM 量。

依明定停止點，本輪 **不套用 partial_resource_projection、不改任何 ACDC 觀測或 ppm，也不刪第 3 頁觀測**。未進入 HM 換算驗算，因此不能宣稱合約通過或 15 個氧化物已採用。[停止證據及原生格子座標](acdc_contract_stop.json)、[15 筆既有宣告](acdc_existing_oxide_declarations.csv)。GA 與 VIC 按獨立工作例外繼續。

## VIC：保留原始位元組再比對

workflow 從本次正式建置的 strict 快取取出指定 VIC 原始回應，驗證原始 SHA 後，以 `<raw_sha256>.json` 放入單獨 `vic-raw-<run_id>` artifact。未新增資料請求、未改 src、未修改原始 JSON 或 sources.json，原件不提交 repo。

本次分類 **D**；[vic_json_diff.json](vic_json_diff.json)逐項列出頂層鍵、要素數量、依 tno 對齊的屬性／幾何差異與順序。重複 tno 先配對相同屬性／幾何部分，再配對剩餘部分，不按回應位置直接 zip。

本次 CI 內容 SHA `5daeadabe8517a775f14eef1df5ef45ba7ee172a6ac233b2f5491da6e172ce8b`；與第 4 版不符的 5daeadab… 是否為同一內容：**True**。本機重算與 CI 收據是否一致：**True**。若不是同一內容，不能用本次回應聲稱已完全重現第 4 版原因。

原始回應只保存在 [VIC CI artifact](https://github.com/lleeoo0611-stack/AU_REE_V2/actions/runs/43948787479/artifacts/14273467527), 不提交 repo。宣告內容 SHA 仍為 `6547bf2c221ed8b58f37b40123bfa43465973f0478a1cca99b67e5ced6413885`，hash_policy 與 hash_drop_keys 均不變；等待研究者決定下一步。


分類標準：A 為屬性／實際幾何或要素集合更新；B 為除 timeStamp 外僅頂層計數變動；C 為除 timeStamp 外僅要素順序變動；其他或混合情形為 D。任何分類都不自動更新宣告值或擴大刪鍵。

## CI 統計與證據

固定參考有值、非 ID 的 2,101 格；609 參考清單不修改，SHA 仍為 `02acc91760c8774f7377d12f2a428d1a1d6b6fba6f1620237e267101cdb0ff4e`。

|分類|e8dc840|本次 CI|增減|
|---|---:|---:|---:|
|SAME|807|876|69|
|KNOWN_STRUCTURAL_DIFFERENCE|48|44|-4|
|NUMERIC_TOLERANCE_SAME|1|1|0|
|DIFFERENT|28|27|-1|
|FORMAL_MISSING|1217|1153|-64|

本次新增 SAME：GA 直接可追溯恢復取得 **8** 格；ACDC HM 合約 **0** 格（未套用）；其他 **61** 格。這是單次 CI 與基準的逐格來源分組，沒有另跑反事實建置。見 [逐格增量](ci/same_increments.csv)。

[GA 九筆受阻來源結果](ci/ga_recovery_9.csv)與[原本可用來源對照](ci/ga_control_sources.csv)分開列出取得狀態、宣告／實際 SHA、是否一致、robots 標記與請求記錄。SHA 不符維持拒絕，沒有更新 sources.json。

[ACDC 全部欄位與參考比較](ci/acdc_fields.csv)、[15 氧化物 CI 值](ci/acdc_15_oxides.csv)及[合約狀態與總說明](ci/acdc_summary.json)。合約未套用，不將其他 GA 或取得狀態改善當作 HM 合約效果。

[其餘 DIFFERENT](ci/remaining_differences.csv)、[缺漏原因](ci/missing_reason_counts.csv)、[逐格比較](ci/cell_comparison.csv)、[609 格守門](ci/ci_609_guard.csv)。


本機 **430 項 Python 測試與 R 測試通過**。新增 **8 項離線測試**，驗證 robots 403 放行及收據標記、資料 403 停止、401／429 不變、200 Disallow、不誤標資料 403，以及原始回應保存／SHA 檢查／不可取得時不造檔。VIC 輔助腳本另通過 6 個分類與重複 tno 合成檢查。CI 結果以本輪紀錄為準。

只推送一次不帶 skip 標記的驗收提交；其後只補報告，不另建置。609 少一格立即停止；CI 完成後停止等待審查，VIC 宣告由研究者另行決定。

## 本次驗收明細

驗收程式提交為 `a00b51557b5f055a2a257762b72a1363d317d24b`；[乾淨建置 CI](https://github.com/lleeoo0611-stack/AU_REE_V2/actions/runs/43948787479)及[研究測試 CI](https://github.com/lleeoo0611-stack/AU_REE_V2/actions/runs/43948787210) 均成功。兩者均為同一提交自動啟動，沒有另跑第二次驗收建置。CI Python **430 項通過**、R 通過；新增測試 **8 項**。Phase 20、21-a、21-b、22-a、22-b 均 **MATCHED**，見 [CI 核對紀錄](research_ci_checks.json)。獨立的 Live official discovery 工作為條件式 SKIPPED，未當作通過。

既有 SAME 807 格全數保留（含固定 609），新增 69 格，無流失。距離 2,101 格全為 SAME 尚差 **1225 格**：FORMAL_MISSING 1,153、KNOWN_STRUCTURAL_DIFFERENCE 44、DIFFERENT 27、NUMERIC_TOLERANCE_SAME 1，後三者均不算 SAME。

### GA 九筆結果

|來源 key|CI 取得狀態|宣告 SHA 比對|robots 403 標記|
|---|---|---|---|
|ga_ports|FETCHED_UNBOUND_GOVERNMENT_OR_SOURCE|未宣告，N/A|有|
|ga_roads_250k|FETCHED_UNBOUND_GOVERNMENT_OR_SOURCE|未宣告，N/A|有|
|ga_rail_operational|FETCHED_UNBOUND_GOVERNMENT_OR_SOURCE|未宣告，N/A|有|
|ga_power_lines|FETCHED_UNBOUND_GOVERNMENT_OR_SOURCE|未宣告，N/A|有|
|ga_critical|COMMITTED_SNAPSHOT_SAME_SHA|一致|有|
|ga_power|FETCHED_UNBOUND_GOVERNMENT_OR_SOURCE|未宣告，N/A|有|
|reviewed_source_521f635719be1686|FETCHED_SHA_VERIFIED|一致|有|
|reviewed_source_9e1ac5bb894d9077|FETCHED_SHA_VERIFIED|一致|有|
|reviewed_source_a197d77204b48c23|FETCHED_SHA_VERIFIED|一致|有|

五筆來源原先未宣告 SHA，僅表示正式流程取得，不能稱為 SHA 一致。另三筆 FETCHED_SHA_VERIFIED 及一筆已提交快照均與宣告 SHA 相符；無 GA SHA 不符。ga_critical 採已保存快照，非重新下載。原本即可用的 ga_aimr 仍為 COMMITTED_SNAPSHOT_SAME_SHA，另列對照。

GA 直接追溯新增為四個專案的經緯度共 8 格。其餘 61 格依 [含來源狀態的增量表](ci/same_increments_with_sources.csv) 列為 OTHER；包括本輪其他主機取得狀態變動，以及相同來源下的規則輸出變動。未跑反事實建置，不能將全部 69 格都歸因於這一行 GA 修改。

### ACDC 正式輸出

合約未套用、HM 合約新增 SAME **0 格**，15 個氧化物均為 FORMAL_MISSING／RULE_INPUT_MISSING；既有 ppm 宣告保持不變。表中參考值僅作比較，沒有寫回宣告或正式輸出。

|氧化物|CI 正式值（kt）|參考值（kt）|比較|
|---|---:|---:|---|
|La2O3|未取得|60.016000000000005|FORMAL_MISSING|
|CeO2|未取得|122.76000000000002|FORMAL_MISSING|
|Pr6O11|未取得|15.5|FORMAL_MISSING|
|Nd2O3|未取得|51.83200000000001|FORMAL_MISSING|
|Sm2O3|未取得|9.684400000000002|FORMAL_MISSING|
|Eu2O3|未取得|0.49104000000000003|FORMAL_MISSING|
|Gd2O3|未取得|9.548000000000002|FORMAL_MISSING|
|Tb4O7|未取得|1.24|FORMAL_MISSING|
|Dy2O3|未取得|9.002400000000002|FORMAL_MISSING|
|Ho2O3|未取得|1.9096000000000004|FORMAL_MISSING|
|Er2O3|未取得|6.138|FORMAL_MISSING|
|Tm2O3|未取得|0.9548000000000002|FORMAL_MISSING|
|Yb2O3|未取得|6.547200000000001|FORMAL_MISSING|
|Lu2O3|未取得|1.0912000000000002|FORMAL_MISSING|
|Y2O3|未取得|61.38000000000001|FORMAL_MISSING|

總說明與 e8dc840 相同：「開發階段依來源原文及其揭露日期：Scoping Study（來源揭露：2025-06-12）；分類僅對應該來源時點，不代表目前營運、法律或許可狀態。」；參考側另含氧化物總和一致及政府座標說明，故此格仍 DIFFERENT。GA 的 reviewed_source_521f635719be1686 已 FETCHED_SHA_VERIFIED，但 ACDC 兩格座標仍因 **SOURCE_AFTER_CUTOFF** 不採用，沒有放寬日期規則。

### VIC 已定位原因

分類 **D（其他）**。兩份本機回應與 CI 都有 13 個要素；依 tno 與相同屬性／幾何配對後，屬性差異 **0**、幾何差異 **0**。頂層只差 timeStamp，計數與 crs 無變動；tno 列表順序相同，但 EL006666 的兩個不同部分順序互換。另有 **12／13 筆頂層 feature id 改變**（例如同一 EL006664 的 minten.690 → minten.691）。因此不屬於「只有要素順序不同」的 C，也沒有證據顯示礦權屬性或幾何更新。

原始回應 **31,792 bytes**，檔名 `2816f156f01c428a5af95bc5ee58ec8d1a24d87afecdaef9e2352e1940930b54.json`；[artifact](https://github.com/lleeoo0611-stack/AU_REE_V2/actions/runs/43948787479/artifacts/14273467527) 已下載並驗證 ZIP 摘要與原始檔 SHA。內容雜湊與第 4 版紀錄的 5daeadab… 完全相同，本機重算也相同，因此本次已重現造成不符的內容。現行規則只刪 timeStamp，仍會保留 feature id 及要素順序差異。**不改宣告值、不改刪鍵、不改雜湊規則**，交由研究者另行決定。

### 缺漏原因

|正式缺漏原因|格數|
|---|---:|
|RULE_INPUT_MISSING|329|
|NO_SOURCE_VALUE|63|
|SOURCE_NOT_ACQUIRED|735|
|SOURCE_SHA_CHANGED|4|
|SOURCE_AFTER_CUTOFF|22|

詳細到專案、欄位、頁碼與來源的結果均保留於 ci/。原件僅在 CI artifact 與被忽略的本機診斷區，未提交進 repo。驗收結束，PR 維持 Draft，等待審查，未 merge。
