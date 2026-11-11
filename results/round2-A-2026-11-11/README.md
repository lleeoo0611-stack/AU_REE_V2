# 第二輪任務 A

新增 38 格；預期範圍 35–40 格。既有填值與 provenance 全部保留，changed_cells.csv 為空。

依 A → B → C → D 順序套用。此任務兩次從 Census、原始封存來源與既有 review ledger 獨立完整離線重建；四份 CSV、summary.json 與 audit.json 逐位元一致。全程零網路請求。

原 53 欄證據口徑與有 TREO MRE 研究列口徑均見 summary.json；不把總說明呈現變更當作新證據。

決定、來源頁碼／locator 見 new_cells.csv，未決案件與候選見 review_queue.csv。Census、inventory、凍結歷史及 INCOMPLETE／CONTINUE 結論不變。

全套離線回歸：919 tests、568 subtests 通過。首次測試因新測試的 overlay 封存路徑配置需修正而中止，修正後以新 overlay 完整重跑通過；未省略測試。

G4 的 Greater Brothers 與 Perenjori 來源無法確定整體礦化主體，因此保留空白，其餘 38 格新增；24 案無原文不處理。完整規則與原件 locator 見 docs/ROUND2_DEPOSIT_CODEBOOK.md。
