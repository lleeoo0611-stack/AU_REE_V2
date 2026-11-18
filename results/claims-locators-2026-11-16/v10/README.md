# 第10版：固定存證事件與公司層標記

基準fc8b1b0；比較基準第9版CI 44170481863（SAME900）。PR #11已依研究者先前指示合併，不能恢復Draft；本輪沿用原分支，另開Draft PR，target feat/same-sha-fallback-20261116，不再merge。

## T1 固定事件

config/pre_cutoff_evidence_events.json逐位元組複製第9版CI事件原文，SHA256=a35421e6238b459ec6979a0843b1fa683a3ad1233b63c1dc378e68a1b3c70826，正好兩筆指定PushEvent。驗證工具內固定同一SHA；不符時全部invalid。主要以此檔驗push time，API只作輔助核對：查不到／連不上不推翻存證，同id時間或head不同則EVENT_RECORD_CONFLICT。兩個workflow都指定此檔，額外always步驟對缺失／invalid proof印warning，不讓警告步驟失敗。

本機三個GA來源valid，VIC仍因PUSH_TIME_NOT_PROVEN_FOR_COMMIT而invalid。[本機診斷](t1_local_validation.json)。正式CI尚未執行，最終以CI為準。

## T2 公司層核准標記

研究者2026-11-18明確核准保留舊標記並追加核准兩標記，解除第一筆非空標記的停止點；不同頁碼或SHA仍停止。[追加核准](append_markers_researcher_approval.json)。先前停止報告與衝突另存歷史紀錄，現行[p2_conflicts.csv](p2_conflicts.csv)為空。

[不可變核准帳本](p2_marker_proposals_researcher_approved.csv)：70列Y、22列HOLD，其餘135列空白；第9版原表不改。tools/company_marker_approvals.py固定70個proposal_id且核對原提案檔SHA與每列內容；只能改核准公司欄位的定位，原marker全部保留，頁碼、SHA、觀測值均不改。實際追加70個位置，[套用紀錄](p2_applied_markers.csv)。

[40格公司欄位預期](p2_company_cells_expected.csv)：23格所有提案核准（僅上限），17格至少一列HOLD，不承諾可恢復。CI只讀同SHA快取，用同一extract_page與evidence.py契約核對；找不到標記者輸出FAILED_IN_CI與前300字，不修標記、不修頁碼、不改claims。來源沒取得會另外列NOT_CHECKED_SOURCE_UNAVAILABLE，避免冒充標記已驗。

## 驗收待辦

609與第9版900格SAME都必須守住，任一流失即停、不修值、不重跑。比較規則與src保持不變；本輪src變動0、累計2157。完整本機回歸執行中；通過後才開Draft PR，觸發一次乾淨CI與一次離線研究CI。

核准位置中特別包含bffe8af62feb3459fa68：它雖列在ASX代碼欄，底層位置是/identity_declaration；此位置按研究者明列核准套用。沒有另套用任何專案層提案。若共用身分宣告讓非公司欄位恢復，驗收將逐格列為OTHER，不冒充公司層直接恢復。

本機驗證完成：完整486項Python與R通過；最後調整影響的27項功能測試與1項行數／config範圍測試另跑通過。新增16項測試。正式609／900守門、恢復格數與標記CI結果仍待唯一一次CI。
