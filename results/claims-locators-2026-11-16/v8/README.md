# 第 8 版：404 不停止主機（B2）與第 7 版正式驗收

研究者賴力維 2026-11-17 23:42 核准。程式基準 56bf4dc（第 7 版程式 ed98e0d），比較基準 ac65aaf 的第 6 版 CI。沿用 [Draft PR #11](https://github.com/lleeoo0611-stack/AU_REE_V2/pull/11)，target feat/same-sha-fallback-20261116，不 merge。

驗收提交 `3e7c24eb983fa0b1570b7aa4fcf62b637d00db03`；[乾淨 CI](https://github.com/lleeoo0611-stack/AU_REE_V2/actions/runs/44119315118)、[研究 CI](https://github.com/lleeoo0611-stack/AU_REE_V2/actions/runs/44119314969)。

**609／609 守門通過，沒有主機因 404 停止。** 驗收完成，維持 Draft，等待審查。

## 與第 6 版 CI 比較

固定 2,101 個非 ID、參考有值的格子。數值容差與結構差異獨立列出，均不算 SAME。

|狀態|ac65aaf CI|本輪|增減|
|---|---:|---:|---:|
|SAME|876|877|+1|
|KNOWN_STRUCTURAL_DIFFERENCE|44|44|+0|
|NUMERIC_TOLERANCE_SAME|1|13|+12|
|DIFFERENT|27|32|+5|
|FORMAL_MISSING|1153|1135|-18|

新增 SAME 4 格，原 SAME 失去 3 格，淨增 1；離 2,101 格全 SAME 尚差 1224。

|新增 SAME 專案|欄位|原分類|分組|
|---|---|---|---|
|AU-447261eed0e81eae88bf|已公布元素數_共15項|FORMAL_MISSING|ACDC_HM_SPECIES_AND_MASS|
|AU-447261eed0e81eae88bf|四項磁性元素皆公布|FORMAL_MISSING|ACDC_HM_SPECIES_AND_MASS|
|AU-447261eed0e81eae88bf|Pr6O11_氧化鐠_kt|FORMAL_MISSING|ACDC_HM_SPECIES_AND_MASS|
|AU-447261eed0e81eae88bf|Er2O3_氧化鉺_kt|FORMAL_MISSING|ACDC_HM_SPECIES_AND_MASS|

ACDC_HM_SPECIES_AND_MASS 表示兩格推導與物種換算；OTHER 為其他專案，按實際收據說明，沒有另跑反事實建置。

|原 SAME 流失專案|欄位|本輪值|本輪分類|原因|
|---|---|---|---|---|
|AU-447261eed0e81eae88bf|TREO品位_pct|（空白）|FORMAL_MISSING|RULE_INPUT_MISSING|
|AU-447261eed0e81eae88bf|總TREO蘊藏量_kt|（空白）|FORMAL_MISSING|RULE_INPUT_MISSING|
|AU-447261eed0e81eae88bf|有TREO資源估計|（空白）|FORMAL_MISSING|RULE_INPUT_MISSING|

其他專案共有 0 格的值、分類或原因改變，完整兩側值與原因見 [other_project_changes.csv](ci/other_project_changes.csv)。

|專案|變動類型|格數|
|---|---|---:|
|無|

## ACDC 第 7 版功能正式驗收

HM 合約通過，15／15 氧化物均有值，CI 值逐一等於原件診斷的 Decimal 結果。礦石 620 Mt × HM 2.2% ÷ 100 = 13.64 Mt；兩個原生格分別驗證。

|氧化物|原始物種|原始 token %HM|完整係數|換算後 %HM|CI kt|比較|
|---|---|---:|---:|---:|---:|---|
|Y2O3|Y2O3|0.45|1|0.45|61.38|NUMERIC_TOLERANCE_SAME|
|Nd2O3|Nd2O3|0.38|1|0.38|51.832|NUMERIC_TOLERANCE_SAME|
|Dy2O3|Dy2O3|0.066|1|0.066|9.0024|NUMERIC_TOLERANCE_SAME|
|La2O3|La2O3|0.44|1|0.44|60.016|NUMERIC_TOLERANCE_SAME|
|CeO2|CeO2|0.9|1|0.9|122.76|NUMERIC_TOLERANCE_SAME|
|Sm2O3|Sm2O3|0.071|1|0.071|9.6844|NUMERIC_TOLERANCE_SAME|
|Eu2O3|Eu2O3|0.0036|1|0.0036|0.49104|NUMERIC_TOLERANCE_SAME|
|Gd2O3|Gd2O3|0.070|1|0.070|9.548|NUMERIC_TOLERANCE_SAME|
|Ho2O3|Ho2O3|0.014|1|0.014|1.9096|NUMERIC_TOLERANCE_SAME|
|Er2O3|Er2O3|0.045|1|0.045|6.138|SAME|
|Tm2O3|Tm2O3|0.007|1|0.007|0.9548|NUMERIC_TOLERANCE_SAME|
|Yb2O3|Yb2O3|0.048|1|0.048|6.5472|NUMERIC_TOLERANCE_SAME|
|Lu2O3|Lu2O3|0.008|1|0.008|1.0912|NUMERIC_TOLERANCE_SAME|
|Pr6O11|Pr2O3|0.11|1.032339537859332409577548490|0.1135573491645265650535303339|15.48922242604142347330153754|SAME|
|Tb4O7|Tb2O3|0.011|1.021865697955702793790846993|0.01124052267751273073169931692|1.533207293212736471803786828|DIFFERENT|

Tb4O7：1.533207293212736471803786828 kt，參考 1.24 kt，差 0.293207293212736471803786828 kt，保留 **DIFFERENT**。參考採第 3 頁捨入後 2 ppm；本輪依第 12 頁原始 Tb2O3 換算，不改值對齊。Pr6O11 亦依既有比較規則，沒有額外放寬。

係數由 Pr 140.908、Tb 158.925、O 15.999 以 Decimal 重算；四位顯示係數不參與運算。[原件與質量驗算](../v7/acdc_hm_diagnostic.csv)、[CI 十五筆](ci/acdc_hm_values.csv)。

總說明：「以來源HM噸位與氧化物百分比推算；排除Sc；非來源公布TREO總量或品位；保留來源捨入區間；開發階段依來源原文及其揭露日期：Scoping Study（來源揭露：2025-06-12）；分類僅對應該來源時點，不代表目前營運、法律或許可狀態。」。

既有 partial 模式保留 claims 的 grade 與原值，但不輸出完整 TREO 品位、總量與完整資源旗標；因此有原 SAME 流失，沒有修改既有行為去追平。[ACDC 全部變化](ci/acdc_all_changes.csv)。

## 剩餘缺漏

|原因|格數|
|---|---:|
|RULE_INPUT_MISSING|311|
|NO_SOURCE_VALUE|63|
|SOURCE_NOT_ACQUIRED|735|
|SOURCE_AFTER_CUTOFF|26|

[完整比較](ci/cell_comparison.csv)、[差異](ci/remaining_differences.csv)、[609 守門](ci/ci_609_guard.csv)、[partial 專案回歸](ci/partial_project_regression.json)。

## 主機停止紀錄

|主機|HOST_STOPPED 來源數|觸發原因|HTTP 狀態紀錄|因 404 停止|
|---|---:|---|---|---|
|gsq-prod-ckan-horizon-public.s3.ap-southeast-2.amazonaws.com|4|["HOST_STOPPED:403"]|[]|False|
|www.asx.com.au|40|["HOST_STOPPED:NOT_PDF"]|[200, 200, 200, 200, 200, 200, 429, 200, 200, 429, 429, 429, 200, 200, 200]|False|

mt_weld_2024 最後狀態 **SNAPSHOT_FALLBACK_SAME_SHA**；HTTP 狀態 404；SHA 相符 True；原因 HTTP Error 404: Not Found。robots 404 與資料 404 分別保留在嘗試紀錄。[全部取得收據](ci/acquisition_report.csv)、[主機彙總](ci/host_stops.csv)。

停止原因追溯：S3 的 gsq_ree_metallurgy_2a4d3b5419605366 回 HTTP 403；www.asx.com.au 的 asx_nolans_clarification202606 在前置 probe 回 HTTP 200／NOT_PDF，後續依原規則停止（見 asx_probe.csv）。兩者都不是 404。Lyons 與 ACDC 原件本輪均 FETCHED_SHA_VERIFIED、SHA 相符；ACDC 經 302 到 200，Lyons 直接 200。

## 範圍、行數與測試

只有 acquisition.py 一個停止條件改動，src +1/-1、淨增 **0**；其他 src 不動。B1、第 817 行順序、robots 403/404/410、快照分支不變，未新增 weblink 快照。第 7 版 claims、係數、推導、sources 與所有 data 均與 56bf4dc 相同。

依歷來 git diff 070df10 新增＋刪除算法，累計實測 **2,130／2,134**；條件替換計 2 行增刪，所以與提示詞預估 2,128 不同，實體 src 行數仍未增加。

新增 **4** 項離線測試，26 項相關測試及本機完整 452 項 Python、R 通過；本次 CI 452 項 Python、R 通過。Phase 20、21-a、21-b、22-a、22-b 均 MATCHED。[研究 CI 證據](research_ci_checks.json)、[artifact 雜湊](ci/artifact_verification.json)。只推一次實作提交；收尾只含報告並使用 skip ci，不重跑。

## 已知限制

VIC 8 格座標因可取得日 2026-11-16 晚於研究截日 2026-11-13，維持 FORMAL_MISSING／SOURCE_AFTER_CUTOFF。政府 WFS 可取得日依取得日記錄，重新取得仍晚於截日；研究者 2026-11-17 決定不移動截日。快照與宣告不動。
