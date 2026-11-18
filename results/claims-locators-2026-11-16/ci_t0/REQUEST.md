# T0：改以 CI 驗收（第 2 版指示）

研究者於 2026-11-16 授權沿用 Draft PR #11，在既有 CI 的完整 OCR 環境重新驗收。前次 Windows 重建僅供診斷，不計為驗收，也不安裝其他版本的 Tesseract。

這次提交只新增本狀態紀錄，src、claims、sources 與 e84c0e0 相同。因連接器未提供 workflow_dispatch，依指示推送不帶跳過標記的提交，讓 pull_request 工作流程執行 Clean automated public build。

固定沿用 `../baseline_reference_609.csv`，不重產參考清單。其來源是前次已發布比較表，來源 SHA256 為 `a131cf6086242b53f0d6c8e1d5f9e420b540f7b21fe9c4671f2f31370d7eae26`。另外核對 PR #11 的參考清單原始位元組未變。

待本次 artifact 的 project-summary 輸出完成後，寫入 ci_609_guard.csv 與 ci_t0_summary.json；目前尚未通過 CI T0。若少於 609 格則停止，若全部保留則只準備 T1 提案與 T2 比對，不自行修改宣告。

T1 提案只使用同 SHA 原件的文字層；需要 OCR 的頁面標 NEEDS_OCR，不在本機 OCR。提案與圖層比對完成後等待研究者逐筆核准，PR 保持 Draft，不 merge。
