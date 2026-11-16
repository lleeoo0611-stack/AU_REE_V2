# 第 5 版：GA robots、ACDC 停止證據與 VIC 原始回應診斷

基準 `e8dc840`；分支 `feat/claims-locators-20261116`；[Draft PR #11](https://github.com/lleeoo0611-stack/AU_REE_V2/pull/11)，維持 Draft、不 merge。研究者：賴力維，2026-11-17。

程式修改與原件檢查已完成；等待一次最終 CI 驗收，不以本機結果代替守門。

## GA robots 403

src 僅將 `/robots.txt` 專用例外 `(404,410)` 改為 `(403,404,410)`，**一行內容替換、src 淨行數 0**，累計仍 2,074／2,074。401、429 及其他狀態未加入；非 robots 資料請求的 403 仍停止主機；200 Disallow 仍禁止。限速、URL、SHA、User-Agent 與登入／CAPTCHA 等規則均未改。

收據標記由 workflow 的既有報告步驟產生，使用既有 `stop_reason` 欄位附記 `ROBOTS_HTTP_403_TREATED_AS_UNAVAILABLE`，不新增 src 欄位或行數。判定依據是共用 before_request 在首次 GA 資料請求之前先請求 robots，收據第一個 GA HTTP 嘗試實際為 403；保留原有資料錯誤原因與所有 HTTP 嘗試。標記是主機 robots 背景，並不宣稱每一筆已保存快照都有新網路請求。

GA 共 10 筆登記來源；本輪重點為上輪 9 筆 UNAVAILABLE／HOST_STOPPED，原先 COMMITTED_SNAPSHOT_SAME_SHA 的 ga_aimr 另列對照。未設定宣告 SHA 的既有政府來源，SHA 比對列為未宣告，不能稱為 SHA 驗證成功。

## ACDC：依原件停止，claims 不改

對來源 SHA `22016f67e614f73963e5a2252e0ec78184ed3906d668649e0dbdb17c365dba59` 的實體第 12 頁，同時核對原生文字與視覺表格。表頭實際為 **Pr2O3、Tb2O3**，Total 格為 **0.11 %HM、0.011 %HM**；不是合約要求的 Pr6O11、Tb4O7。不能直接替換或改化學物種，也沒有用 620×2.2% 的推算量填作原件報告 HM 量。

依明定停止點，本輪 **不套用 partial_resource_projection、不改任何 ACDC 觀測或 ppm，也不刪第 3 頁觀測**。未進入 HM 換算驗算，因此不能宣稱合約通過或 15 個氧化物已採用。[停止證據及原生格子座標](acdc_contract_stop.json)、[15 筆既有宣告](acdc_existing_oxide_declarations.csv)。GA 與 VIC 按獨立工作例外繼續。

## VIC：保留原始位元組再比對

workflow 從本次正式建置的 strict 快取取出指定 VIC 原始回應，驗證原始 SHA 後，以 `<raw_sha256>.json` 放入單獨 `vic-raw-<run_id>` artifact。未新增資料請求、未改 src、未修改原始 JSON 或 sources.json，原件不提交 repo。

尚未取得本次 CI 原始回應，不能先填 A／B／C／D。

分類標準：A 為屬性／實際幾何或要素集合更新；B 為除 timeStamp 外僅頂層計數變動；C 為除 timeStamp 外僅要素順序變動；其他或混合情形為 D。任何分類都不自動更新宣告值或擴大刪鍵。

## CI 統計與證據

固定參考有值、非 ID 的 2,101 格；609 參考清單不修改，SHA 仍為 `02acc91760c8774f7377d12f2a428d1a1d6b6fba6f1620237e267101cdb0ff4e`。

|分類|e8dc840|本次 CI|增減|
|---|---:|---:|---:|
|SAME|807|待 CI|待 CI|
|KNOWN_STRUCTURAL_DIFFERENCE|48|待 CI|待 CI|
|NUMERIC_TOLERANCE_SAME|1|待 CI|待 CI|
|DIFFERENT|28|待 CI|待 CI|
|FORMAL_MISSING|1217|待 CI|待 CI|



本機 **430 項 Python 測試與 R 測試通過**。新增 **8 項離線測試**，驗證 robots 403 放行及收據標記、資料 403 停止、401／429 不變、200 Disallow、不誤標資料 403，以及原始回應保存／SHA 檢查／不可取得時不造檔。VIC 輔助腳本另通過 6 個分類與重複 tno 合成檢查。CI 結果以本輪紀錄為準。

只推送一次不帶 skip 標記的驗收提交；其後只補報告，不另建置。609 少一格立即停止；CI 完成後停止等待審查，VIC 宣告由研究者另行決定。
