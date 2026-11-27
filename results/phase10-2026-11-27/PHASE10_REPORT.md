# Phase 10 自動證據品質、來源恢復與研究增益

## 封存基準與重播界線

研究截日為 **2026-11-13**。封存 Census 有 **93 案、51 欄**，適用覆蓋率 82.56%，缺值 528 格。保留原發布固定分母時為 82.40%。已核對 16 份封存面板排名。 [基準](phase10_baseline.md)

## 原件恢復

696／715 份原件已核對。相對前次同鎖檔增 28 份，尚缺 19 份。完整 93 案歷史重建狀態為 `BLOCKED_MISSING_ASSETS`。不同 SHA 的回應及逐件阻礙另有紀錄。 [來源恢復](source_recovery_report.md)

## 留出、Silver 參照與品質

留出驗證 7／7 份原件，3 列資源與 0 列技術候選。留出原件於研究截日之後收錄，保留在影子評估。數值真值不足的指標列為未量測。 [留出](holdout_manifest.json) · [留出量測](quality_holdout/quality_measurement.json)

另在封存校準範圍取得 22 筆可驗證參照。數值與單位的一致率分別為 2／2、2／2。這兩個分母都是可配對參照。解析器一致、合成案例及未量測的獨立準確率分開列出。 [校準量測](quality_regression/quality_measurement.json)

## 缺值、正式選值與研究增益

已計算 1302 個專案與準則的優先序，自動填入的正式值為 0。面板可能增加的條件式樣本另列。缺件恢復先改善可重播性，完整歷史面板的可用資料增減仍取決於同口徑重播。 [優先序](research_gap_priority.csv) · [阻礙](project_criterion_blockers.json)

## 因素與工程驗證

- 封存 Phase 22 的 C1 政策對照涵蓋 16 個面板，名次變動 0 格。採納啟用單獨改動 1 個選值、11 個矩陣格及 312 個分數，名次變動 0 格。檢索、換算和聯合規則遷移另列。 [封存因素對照](reference-effects.json)
- 停用、冷、暖快取各耗時 158.98／156.75／50.97 秒。282 項科學產物的快取等價性為 `EQUAL`。 [效能](performance.json)
- 封存快取驗證為 `EXACT_SCIENTIFIC_REPLAY`，已比對 139 項科學產物。 [封存效能](reference-performance.json)

已盤點 23 個遠端分支。封存圖和新工具的相依、複雜度及重複群組另有收據。CI 依變更區分單元、PDF 至 R 整合與完整歷史重播，發布路徑保留公開來源驗證。 [分支](repository_integration.json) · [模組](phase10_module_audit.json) · [CI 效能](ci-performance.json)

尚未分離的正式效果及缺少獨立真值的指標維持未量測。
