# 第 6 版：全主機 robots 標記、ACDC 可行性與 VIC 已保存快照

基準 `4dca63faecbd98b9bd170ec01f6af4a4f9067031`；分支 `feat/claims-locators-20261116`；[Draft PR #11](https://github.com/lleeoo0611-stack/AU_REE_V2/pull/11)，target `feat/same-sha-fallback-20261116`。研究者：賴力維，2026-11-17。

工作流程、快照與可行性報告已準備；等待一次 CI 驗收。

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
|SAME|876|待 CI|待 CI|
|KNOWN_STRUCTURAL_DIFFERENCE|44|待 CI|待 CI|
|NUMERIC_TOLERANCE_SAME|1|待 CI|待 CI|
|DIFFERENT|27|待 CI|待 CI|
|FORMAL_MISSING|1153|待 CI|待 CI|



本機完整 Python 與 R 檢查紀錄留在 work/；最終測試數、CI 連結以本輪驗收紀錄為準。只推一次不帶 skip 標記的程式／資料提交，其後報告提交使用 skip ci。609 若少一格立即停止；驗收完成後停止等審查。
