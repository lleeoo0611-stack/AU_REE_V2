# 第 7 版：ACDC 兩格 HM 推導與限定氧化物物種換算

基準 `ac65aafbbaaa6d793af988d61340988172665d00`（程式 `4ebcb80`）。分支 `feat/claims-locators-20261116`，[Draft PR #11](https://github.com/lleeoo0611-stack/AU_REE_V2/pull/11)，target `feat/same-sha-fallback-20261116`。研究者賴力維 2026-11-17 21:25 核准；不 merge。

**已停止：固定守門僅 596／609，流失 13 格，全部屬於 Lyons。** 實作提交 `ed98e0d` 的兩個 CI workflow 成功，但業務守門未通過，不能宣告驗收成功。依研究者停止點，不改值、不重跑 CI；PR 維持 Draft，等待審查。

## 限定實作與行數

僅 census.py 的 summary_partial_contract、summary_resource_fields 及兩者直接呼叫的新 helper summary_hm_percent 改變。新增 **57**、刪除 **3**，本輪增刪合計 **60／60**，淨增 **54**。依既有 git diff 070df10 累計算法為 **2,128／2,134**；不是將本輪增刪總數直接加到先前淨差。未壓縮長行、未新增分號、未順手重構。src 其他函式 AST 不變；config、R、workflow、VIC 快照與 manifest 不動。

兩格推導逐格核對原始 token、原生單位、同頁與至少兩個標記；礦石量須與主 ore_mt 一致，Decimal 乘積須完全等於宣告值。無 derivation 的原生單格分支保留。

物種換算只允許 Pr2O3→Pr6O11 與 Tb2O3→Tb4O7；原子量固定 Pr 140.908、Tb 158.925、O 15.999，由 Decimal 重算。附帶係數超出 1e-12、其他物種對、目標不符均拋錯。質量驗算及 HM 輸出都用換算後百分比；沒有換算宣告者使用原 token。

## 原件與 ACDC 宣告

來源 SHA `22016f67e614f73963e5a2252e0ec78184ed3906d668649e0dbdb17c365dba59`，只讀既有正式建置快取，不新請求 ASX。

- HM 量 = 第 3 頁原礦石格 620 Mt × 第 12 頁 Total HM 格 2.2% ÷ 100 = **13.64 Mt**。兩個格都有獨立頁碼、row/column/unit bbox 與來源標記；13.64 明確宣告為推導值，沒有冒稱原生單格。
- 十三筆既有 %HM 觀測補 normalization 與 material_basis，原數值、頁碼、來源 SHA、標記與格子不動。
- 原第 3 頁 Pr6O11 25 ppm、Tb4O7 2 ppm 保留，僅分離為 context statement 並明記不參與 HM 合約；透過既有同 statement 選取排除。
- 新增兩筆第 12 頁的衍生觀測，保存 Pr2O3 0.11、Tb2O3 0.011 原始物種、token、%HM、格子及完整係數。新 ppm 由原格與原子量公式算出，未修改舊 25／2 ppm 以通過驗算。
- ore_mt 620 與 grade 0.0584 及其他專案所有宣告均未改值。

[原件格子與質量驗算](acdc_hm_diagnostic.csv)、[合約前置紀錄](acdc_contract_preflight.json)、[入庫與本機頁面流程診斷](local_acdc_diagnostic.json)、[Wimmera 本機資源函式回歸](local_legacy_regression.json)、[範圍與預算核對](preflight.json)。

## 十五個氧化物

以下僅是 SHA 一致原件及現有流程的本機診斷，尚未當作 CI 驗收。 係數欄保留完整 Decimal 精度；不採四位係數運算。

|目標氧化物|原始物種|原始 token %HM|係數|換算後 %HM|kt|比較|
|---|---|---:|---:|---:|---:|---|
|Y2O3|Y2O3|0.45|1|0.45|61.3800|本機診斷|
|Nd2O3|Nd2O3|0.38|1|0.38|51.8320|本機診斷|
|Dy2O3|Dy2O3|0.066|1|0.066|9.00240|本機診斷|
|La2O3|La2O3|0.44|1|0.44|60.0160|本機診斷|
|CeO2|CeO2|0.9|1|0.9|122.760|本機診斷|
|Sm2O3|Sm2O3|0.071|1|0.071|9.68440|本機診斷|
|Eu2O3|Eu2O3|0.0036|1|0.0036|0.491040|本機診斷|
|Gd2O3|Gd2O3|0.070|1|0.070|9.54800|本機診斷|
|Ho2O3|Ho2O3|0.014|1|0.014|1.90960|本機診斷|
|Er2O3|Er2O3|0.045|1|0.045|6.13800|本機診斷|
|Tm2O3|Tm2O3|0.007|1|0.007|0.95480|本機診斷|
|Yb2O3|Yb2O3|0.048|1|0.048|6.54720|本機診斷|
|Lu2O3|Lu2O3|0.008|1|0.008|1.09120|本機診斷|
|Pr6O11|Pr2O3|0.11|1.032339537859332409577548490|0.1135573491645265650535303339|15.48922242604142347330153754|本機診斷|
|Tb4O7|Tb2O3|0.011|1.021865697955702793790846993|0.01124052267751273073169931692|1.533207293212736471803786828|本機診斷|

## 與基準 CI 比較

固定非 ID、參考有值的 2,101 格；609 清單 SHA 保持 02acc91760c8774f7377d12f2a428d1a1d6b6fba6f1620237e267101cdb0ff4e。

|分類|ac65aaf CI|本輪 CI|增減|
|---|---:|---:|---:|
|SAME|876|守門停止，未續算|未續算|
|KNOWN_STRUCTURAL_DIFFERENCE|44|守門停止，未續算|未續算|
|NUMERIC_TOLERANCE_SAME|1|守門停止，未續算|未續算|
|DIFFERENT|27|守門停止，未續算|未續算|
|FORMAL_MISSING|1153|守門停止，未續算|未續算|



## 測試

新增 **14** 項離線測試，含兩格推導正確／錯值／錯區域／單位／兩個礦石量不一致、兩個物種係數、四位係數拒絕、不支援或目標不符拒絕、質量不符不改數值，以及原生 HM 與其他 partial 模式逐欄比對基準函式。原預算測試同步研究者核准的 2,134，另檢查本輪 ≤60 行及只改 census.py。

本機最後完整 **448 項 Python 與 R 通過**。最初完整測試唯一失敗是尚寫舊 2,074 的預算測試；同步核准值後重跑全部通過，未改實作湊測試。本機 Wimmera 資源函式 51 欄與基準相同；本機沒有註冊快取內的 Splinter 原件，不假稱重新驗原件，正式兩案及所有其他專案逐格回歸以 CI 結果為準。

## 已知限制

VIC **8 格座標**因可取得日 **2026-11-16** 晚於研究截日 **2026-11-13**，維持 FORMAL_MISSING。政府 WFS 的可取得日依取得日記錄，重新取得仍晚於截日，這不是快照機制問題。研究者 **2026-11-17 決定不移動截日**；已提交快照與 sources.json 宣告完全不動。

已推一次不帶 skip ci 的實作／資料提交；本次收尾只提交報告並使用 skip ci。守門失敗後未修改程式、宣告或數值，未再啟動 CI；維持 Draft、未 merge，等待審查。


## CI 停止報告

[乾淨建置 44098964236](https://github.com/lleeoo0611-stack/AU_REE_V2/actions/runs/44098964236) 與 [研究回歸 44098964179](https://github.com/lleeoo0611-stack/AU_REE_V2/actions/runs/44098964179) 都在 `ed98e0ddd28c49971530f85d24cffd8545576719` 完成且 workflow conclusion 為 success。CI 的 448 項 Python、R 通過；Phase 20、21-a、21-b、22-a、22-b 五份凍結重建均 MATCHED。[研究 CI 證據](research_ci_checks.json)、[artifact 雜湊核對](ci/artifact_verification.json)。workflow 綠燈沒有取代本機讀取同一次 CI artifact 所做的固定 609 守門。

### 守門與原因

固定清單 **596／609 SAME**，其餘 **11 格 FORMAL_MISSING、2 格 DIFFERENT**；全部為 Lyons（AU-7c198d219aa1db3e291f）。[完整 609 格守門](ci/ci_609_guard.csv)、[13 格流失明細](ci/ci_609_losses.csv)、[停止核對](stop_validation.json)。

本輪 `wcsecure.weblink.com.au` 的 `mt_weld_2024` 嘗試紀錄為 404、404：既有 before_request 先請求 robots，robots 404 依規則放行；資料請求 404 觸發原有停止主機。該來源本身可用同 SHA 快照，但不會解除停止狀態。後續 `lyons_mre2023` 的 http_attempts 為空，狀態 HOST_STOPPED:404；基準 CI 兩來源原件均取得且 SHA 一致。[該主機前後收據](ci/weblink_receipts_before_after.csv)。

因此 Lyons 的資源、型態與階段所需宣告無法採用，名稱及主要來源退回既有政府表：名稱變成 Lyons，來源名稱變成 wa_dmpe_ree_2026_table；開發階段衍生文字缺少可用輸入，顯示 RULE_INPUT_MISSING。[來源切換與階段追溯](ci/lyons_loss_provenance.csv)。這是收據可直接支持的失敗鏈；未對外重新請求，也未推論遠端 404 的根本原因。

|欄位|固定參考值|本次 CI 值|分類|原因|
|---|---|---|---|---|
|專案名稱|Lyons — 12&13 resource scope|Lyons|DIFFERENT|FORMAL_VALUE_CHANGED|
|礦床型態代碼|hard|（空白）|FORMAL_MISSING|HOST_STOPPED_4XX|
|礦床型態|Ironstone|（空白）|FORMAL_MISSING|HOST_STOPPED_4XX|
|開發階段代碼|A2|（空白）|FORMAL_MISSING|HOST_STOPPED_4XX|
|開發階段類別|探勘|（空白）|FORMAL_MISSING|HOST_STOPPED_4XX|
|開發階段|Exploration（來源揭露：2026-02，月精度）|（空白）|FORMAL_MISSING|RULE_INPUT_MISSING|
|礦石蘊藏量_Mt|0.69|（空白）|FORMAL_MISSING|HOST_STOPPED_4XX|
|TREO品位_pct|0.33|（空白）|FORMAL_MISSING|HOST_STOPPED_4XX|
|總TREO蘊藏量_kt|2.266|（空白）|FORMAL_MISSING|HOST_STOPPED_4XX|
|有TREO資源估計|是|（空白）|FORMAL_MISSING|HOST_STOPPED_4XX|
|有來源文件|是|（空白）|FORMAL_MISSING|HOST_STOPPED_4XX|
|資料來源名稱|lyons_mre2023|wa_dmpe_ree_2026_table|DIFFERENT|FORMAL_VALUE_CHANGED|
|總說明|開發階段依來源原文及其揭露日期：Exploration（來源揭露：2026-02，月精度）；分類僅對應該來源時點，不代表目前營運、法律或許可狀態。|（空白）|FORMAL_MISSING|HOST_STOPPED_4XX|

### 停止後未宣告的結果

已在第一個守門停止，沒有續算全部 2,101 格分類、SAME 增減或完成所有其他專案逐格回歸，前表明列「未續算」；不能以本機 ACDC 診斷補成 CI 成功。ACDC 的 goschen_central_mre2024 本輪也為 HOST_STOPPED:404，沒有正式 CI 合約通過或新增 SAME 的驗收結論。十五個氧化物、完整係數與總說明仍以本報告連結的本機診斷保存；Tb 本機約 1.533207 kt 與參考 1.24 kt 的差異不改值對齊。

src 本輪 +57/-3，增刪 60／60、淨增 54，累計 2,128／2,134；守門失敗後 src、claims、sources、測試與 workflow 均未修改。VIC 快照、宣告與研究截日不動，8 格 SOURCE_AFTER_CUTOFF 仍為研究者接受的已知限制，未以停止後的新驗收取代。
