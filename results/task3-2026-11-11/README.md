# 任務 3：開發階段核准閘門

本次只使用既有總表及 provenance，網路請求為零。提案 decided_by 全部預設 null；不得由程式代填。

新增 0 格，既有值變更 0 格；候選專案 35 案，待審 15 案。

研究僅有名稱不等於已完成；無明示完成的 Scoping、PFS、DFS、BFS 或 Feasibility 留待審，因此可能低於預期格數。進行中研究只採同原文明示已完成的上一階；Operating 不推成 D3；退出不推成 X；A3 不自動指派。

礦床型態決定表含 64 個未對照專案（含原文缺失），按原文彙總；候選代碼只列可選詞彙，不是分類結論。

projection/ 保存四份 canonical CSV 及 summary／audit。未核准時逐位元保留基線；task summary.json 是診斷摘要，與 canonical summary 分開。核准後必須由既有 canonical exporter 重建，再用 --projected 指定結果，不能由此工具直接改表。


## 核准前與假設核准預覽

正式 production 新增 0 格；35 案、最多 70 格僅是假設研究者核准全部適用規則後的候選預覽，並非已填結果。39 案沒有階段原文，另有15案待審。未核准六檔 byte-copy 在 work/coverage-task3/diagnostics-delivery/projection，未重複提交整份基線。獨立完整重建驗收由主流程補入 acceptance.json；目前僅完成本模組16項測試。

## 日期與來源範圍

54筆階段來源皆有SHA、頁碼locator、publication date。45筆原scope空白，屬來源日期的metadata；9筆study observation有效日期欄空白，但已完成原文字串保留日期。所有provenance逐項保留，不把publication date當完成日期。新規則輸出附AT_NATIVE_SOURCE_DATE_NOT_CURRENT_STATUS與完整原文／來源provenance／MRE判據；缺來源定位或合法日期時拒絕填值。


## 已核實的隔離核准模擬（不是研究者核准）

使用 work 中標記 TEST_FIXTURE_ONLY_NOT_RESEARCHER_APPROVAL 的決定副本，完成一次離線完整 export_summary → extend_summary → apply_archived_additions 重建。實測可新增70格（35案階段代碼與類別），填值1985→2055，空白2944→2874。new_cells_preview.csv 逐格列出，正式 new_cells.csv 仍為0。compare_projections 已驗證所有既有值與provenance不變，Census與正式決定檔SHA不變。

此模擬僅一次，用於驗證 opt-in 分支，不取代正式全 null 的雙重獨立重建驗收；未 publish-current，沒有把測試批准人寫入正式config。stage+既有分類回歸測試35項、29個subtests通過，見task3-tests.xml。


## 個別研究完成狀態防護修正

完成證據改為只綁定相鄰的特定研究名稱，不再套用整個子句。completed PFS before DFS 不會升為 B2；前階已完成、後階明確進行中時可依獨立核准保留 B1。含 planned／expected／will 等未來或條件語氣的 FID／建設描述不自動晉升。新增反例後37項測試、45個subtests通過。重新逐列核對全部93案的原文及provenance，70個模擬新增格的鍵和值與先前完整重建完全一致，因此未重跑一次完整source preview。見parser_repair_preview_check.json。


## 完整驗收

以task1正式輸出為基線，兩次獨立完整來源重建並重播既有Dubbo新增，四CSV與summary/audit逐位元相同，未核准輸出與前項六檔也逐位元相同。434項既有受影響回歸及353子案例全過；跨項新測試詳見integrated-tests.xml。決定檔雜湊已綁入core_rebuild_receipt.json，保護檢查及數字見acceptance.json。
