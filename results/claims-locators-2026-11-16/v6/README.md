# 第 6 版：全主機 robots 標記、ACDC 可行性與 VIC 已保存快照

基準 `4dca63faecbd98b9bd170ec01f6af4a4f9067031`；分支 `feat/claims-locators-20261116`；[Draft PR #11](https://github.com/lleeoo0611-stack/AU_REE_V2/pull/11)，target `feat/same-sha-fallback-20261116`。研究者：賴力維，2026-11-17。

固定守門 **609／609**，程式提交 `4ebcb8008cb9ac0c242b20c659381396d452a478`，見 [乾淨 CI](https://github.com/lleeoo0611-stack/AU_REE_V2/actions/runs/44036943032)。

## 範圍與 src

**src 位元組完全不改，淨行數 0，累計仍 2,074／2,074**。robots 的 (403,404,410) 全域規則不變。只改 workflow 的報告標記、測試，以及核准的 VIC sources 宣告／快照／manifest。data/claims.json 與固定 609 格清單不改，不新請求 ASX；既有正式流程照舊。PR 維持 Draft，不 merge。

## robots 標記

workflow 不再寫死 GA。依來源列順序找各主機第一次 HTTP 嘗試；首次 403 且之後有成功取得的來源時，該主機全部收據列的既有 stop_reason 附記 ROBOTS_HTTP_403_TREATED_AS_UNAVAILABLE。失敗的資料端 403、沒有成功來源的主機不標；首次 robots 200 不標。其他主機的替代下載成功不當作原主機成功。

每次 CI 另輸出 robots_403_hosts.csv，含主機、首次狀態、其後成功來源數、是否標記及標記文字。[第 5 版收據的離線診斷](robots_403_hosts_baseline_diagnostic.csv) 僅測報告邏輯，不冒充本輪 CI；其中 investorhub 8、AFR 6 個其後成功來源都會標記，正式結果見本次 CI。

新增 **4 項離線測試**：兩主機 robots 403 後成功皆標；403 資料失敗及 robots 200 不標；報告檔與全來源列標記；跨主機替代不誤證原主機成功。原有測試依本輪規則更新預期，不改擷取邏輯。

## ACDC：先確認可行性，依停止點不套用

只讀確認 census.py 的 summary_partial_contract 與 summary_resource_fields 後，兩個條件都無法只靠資料宣告做到：

1. HM 量必須綁定單一原生格，unit 必須 Mt，original_token 必須等於該格文字；沒有兩格乘積的驗證分支。
2. 氧化物驗算與輸出均直接採 original_token，額外物種與係數欄位不生效；用換算後 token 假冒原文也不符合要求。

因此 **不套用合約、不改任何 claims、ppm、原 token、頁碼或標記**。預估需要在質量驗證、物種驗證與輸出三處另增 **45–60 行**；這是只讀設計估算，未實作、不是量測後的修補行數。現行上限不容許，本輪不申請或自行放寬。逐項位置與估算見 [可行性報告](acdc_feasibility.json)。

已用指定原子量重算：Pr 係數 **1.032339537859332409577548490**、Tb 係數 **1.021865697955702793790846993**。指定的四位係數及四捨五入分子量與原子量重算略有差異，將來實作須明定精度慣例，不能默默混用以通過 1e-12 驗算。

純算術診斷：620 × 2.2% = 13.64 Mt；按指定原子量推導 Pr6O11 約 **15.4892224260 kt**、Tb4O7 約 **1.5332072932 kt**，後者與參考 1.24 kt 不同。這些**不是已驗證或已採用的正式宣告**，本輪未進入 HM 合約驗算，不能稱合約通過。

## VIC：提交第 5 版 CI 原始回應快照

已驗證 run 43948787479／artifact 14273467527 的原件 **31,792 bytes**：

- 原始回應 SHA：`2816f156f01c428a5af95bc5ee58ec8d1a24d87afecdaef9e2352e1940930b54`
- 實際提交快照 SHA：`2816f156f01c428a5af95bc5ee58ec8d1a24d87afecdaef9e2352e1940930b54`
- public_snapshot 本次無需去識別轉換，兩份位元組完全相同。
- 經既有 public_snapshot、data/snapshots 寫入及 append_snapshots 更新 manifest；未手動拼寫 manifest、未改 src、無新網路請求。
- source_sha256 與 committed_snapshot_sha256 相同；移除 hash_policy、hash_drop_keys 及舊內容雜湊核准文字。
- previous_source_sha256 保留 6547bf2c…；更早的 31a20516… 原始宣告保留於 snapshot_provenance。
- fixed_query、summary_spatial_source、summary_tenements 等既有欄位不動。

快照凍結在 **2026-11-16 UTC（臺灣 11-17）** 的第 5 版 CI。acquired_at 用 artifact 建立時間作取得完成上界，並未假稱那是政府發布時間；available_date 如實為 2026-11-16。VIC 礦權日後更新須人工重新核對、提交快照，本輪不自動更新。完整 [SHA 對應與核准紀錄](vic_snapshot_adoption.json)。

## 與基準比較

固定參考有值、非 ID 共 2,101 格；固定 609 清單 SHA 02acc91760c8774f7377d12f2a428d1a1d6b6fba6f1620237e267101cdb0ff4e 不變。

|狀態|4dca63f 的 CI|本輪 CI|增減|
|---|---:|---:|---:|
|SAME|876|876|0|
|KNOWN_STRUCTURAL_DIFFERENCE|44|44|0|
|NUMERIC_TOLERANCE_SAME|1|1|0|
|DIFFERENT|27|27|0|
|FORMAL_MISSING|1153|1153|0|


## 一次 CI 驗收結果

新增 SAME 分組：ACDC 物種換算 **0**（未套用）、VIC 快照 **0**、其他 **0**。新增合計 0，基準非守門 SAME 流失 0，淨增加 0。未跑反事實建置；逐格見 [增量表](ci/same_increments.csv)。距離 2,101 格全部 SAME 尚差 **1225**，其他分類不算 SAME。

### robots 403 主機

完整 [robots_403_hosts.csv](ci/robots_403_hosts.csv) 保留所有主機的首次狀態，這裡僅列首次為 403 的主機。成功來源數只計首次嘗試開始之後成功的來源；標記套用至該主機所有來源列，含較早採用的已提交快照與失敗列。這是主機 robots 背景，並非宣稱所有來源都成功下載。

|主機|首次狀態|其後成功來源數|標記|有標記／該主機來源列數|
|---|---:|---:|---|---:|
|company-announcements.afr.com|403|6|True|6/6|
|geoscience.data.qld.gov.au|403|0|False|0/2|
|hermes-cdn.investorhub.com|403|8|True|10/10|
|services.ga.gov.au|403|9|True|10/10|
|wamex.dmp.wa.gov.au|403|0|False|0/3|

### VIC 八格座標

CI 取得狀態 **COMMITTED_SNAPSHOT_SAME_SHA**，收據與已選快照見 [vic_snapshot_receipt.json](ci/vic_snapshot_receipt.json)。快照可用日如實保留 2026-11-16，不提前成研究截日 2026-11-13；被日期或其他規則擋下時不放寬。

本輪八格正式值均未取得，原因全為 SOURCE_AFTER_CUTOFF，沒有新增 VIC SAME。參考側有值的四格由 SOURCE_SHA_CHANGED 改為日期受阻；另四格參考側本來空白，不把空白對空白算作恢復 SAME。提交快照的採用已成功，不代表跨過研究日期規則；本輪不重新請求 VIC 原件。

|專案 ID|欄位|正式值|參考值|正式狀態|參考比較|原因|
|---|---|---:|---:|---|---|---|
|AU-176852ef1348ac10d154|緯度|未取得|-35.4287263|FORMAL_MISSING|FORMAL_MISSING|SOURCE_AFTER_CUTOFF|
|AU-176852ef1348ac10d154|經度|未取得|143.4183513|FORMAL_MISSING|FORMAL_MISSING|SOURCE_AFTER_CUTOFF|
|AU-2fc429d0556dfa0b95c4|緯度|未取得|參考側空白|FORMAL_MISSING|空白參考不計 SAME|SOURCE_AFTER_CUTOFF|
|AU-2fc429d0556dfa0b95c4|經度|未取得|參考側空白|FORMAL_MISSING|空白參考不計 SAME|SOURCE_AFTER_CUTOFF|
|AU-410159af7b79ea498ec2|緯度|未取得|參考側空白|FORMAL_MISSING|空白參考不計 SAME|SOURCE_AFTER_CUTOFF|
|AU-410159af7b79ea498ec2|經度|未取得|參考側空白|FORMAL_MISSING|空白參考不計 SAME|SOURCE_AFTER_CUTOFF|
|AU-ff758cad5beb276d327d|緯度|未取得|-36.9493024|FORMAL_MISSING|FORMAL_MISSING|SOURCE_AFTER_CUTOFF|
|AU-ff758cad5beb276d327d|經度|未取得|141.9153047|FORMAL_MISSING|FORMAL_MISSING|SOURCE_AFTER_CUTOFF|

### ACDC 十五個氧化物與總說明

ACDC 可行性未通過，合約未套用；以下為 CI 實際輸出，參考側數字不寫回 claims。Tb4O7 也沒有採用換算診斷值，故不能把本輪結果稱作物種換算後的 DIFFERENT。

|氧化物|正式值 kt|參考值 kt|比較|
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

總說明：「開發階段依來源原文及其揭露日期：Scoping Study（來源揭露：2025-06-12）；分類僅對應該來源時點，不代表目前營運、法律或許可狀態。」。與基準是否相同：**True**。全部欄位見 [ACDC 比較](ci/acdc_fields.csv)。

### 缺漏原因

|原因|格數|
|---|---:|
|RULE_INPUT_MISSING|329|
|NO_SOURCE_VALUE|63|
|SOURCE_NOT_ACQUIRED|735|
|SOURCE_AFTER_CUTOFF|26|

[完整逐格比較](ci/cell_comparison.csv)、[609 格守門](ci/ci_609_guard.csv)、[其餘 DIFFERENT](ci/remaining_differences.csv)、[測試與來源驗收](ci/acceptance.json)。


本機完整 Python 與 R 檢查紀錄留在 work/；最終測試數、CI 連結以本輪驗收紀錄為準。只推一次不帶 skip 標記的程式／資料提交，其後報告提交使用 skip ci。609 若少一格立即停止；驗收完成後停止等審查。

CI 已驗證 **434 項 Python 與 R 通過**；新增 4 項測試，src 淨增 0。Phase 20、21-a、21-b、22-a、22-b 均 **MATCHED**，見 [研究 CI](https://github.com/lleeoo0611-stack/AU_REE_V2/actions/runs/44036943021) 與 [逐項紀錄](research_ci_checks.json)。條件式 Live official discovery 工作為 SKIPPED，未列為通過。兩條 workflow 由同一提交自動啟動，未另跑第二次驗收建置。
