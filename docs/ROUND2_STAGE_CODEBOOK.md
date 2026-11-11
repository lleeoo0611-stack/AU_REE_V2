# 第二輪開發階段研究者核准補充（2026-11-11）

總體 codebook 狀態仍為 DRAFT，本文件不核准整份 codebook。僅下列研究者明確核准的規則可經 researcher_rule_decisions.json 閘門補空白，既有值與 provenance 不修改。

- 研究名稱已揭露視為完成：Scoping／Scoping Study Update／PFS 為 B1，Feasibility Study／BFS／DFS 為 B2。限定本輪九案。
- 研究進行中且無已完成前階證據：Wimmera、Euston 為 B1，附 IN_PROGRESS_STUDY。
- 新代碼 D，類別「生產」：Mt Weld、Balranald、Coburn。僅代表來源揭露時點已開始生產，不表示達到設計產能。取代舊 OPERATING_REQUIRES_DESIGN_CAPACITY_REVIEW；舊決定保留並以 superseded_by 連結新決定。
- 新代碼 X，類別「退出」：Durack。研究列保留，分母不變，其他欄位不清空。
- Charley Creek（2013-04-15）、WIM150（2015-10-30）附 STAGE_SOURCE_DATED，值不因資料較舊而改變。

沒有對應有效決定時不補值；無原文的 39 案不從名稱推定階段。每個新欄位沿用來源 SHA、locator 與原 provenance，scope 記錄 decision_id、原文、qualifier 及日期語義。
