# 第二輪任務 C

新增 2 格；預期範圍 10–24 格。既有填值與 provenance 全部保留，changed_cells.csv 為空。

依 A → B → C → D 順序套用。此任務兩次從 Census、原始封存來源與既有 review ledger 獨立完整離線重建；四份 CSV、summary.json 與 audit.json 逐位元一致。全程零網路請求。

原 53 欄證據口徑與有 TREO MRE 研究列口徑均見 summary.json；不把總說明呈現變更當作新證據。

決定、來源頁碼／locator 見 new_cells.csv，未決案件與候選見 review_queue.csv。Census、inventory、凍結歷史及 INCOMPLETE／CONTINUE 結論不變。

## 待研究者決定與阻礙
多 site 代表點、VIC／TAS 新來源尚未核准，維持空白。實際增量低於預期：WA 有公司欄位但來源未填公司時亦拒絕自動匹配，不把缺公司當作無公司欄位；多點與同名不同公司仍保守留白。NT ZIP 的 CSV SHA 已驗證，但封存 metadata 未能確認 MGA datum（GDA94／AGD66），因此不填 NT 座標；真實控制點誤差驗收未完成，不能聲稱 NT 轉換完成。

全套離線回歸：919 tests、568 subtests 通過。這是程式與既有回歸測試通過，不代表 NT 真實控制點驗收完成。僅 Cascade／Zinc of Ireland 的 2 格符合公司一致條件；Rankin Dome、East Laverton、Viper、Graceland、Coondina 的 WA proj_title 無公司值，不能以 NO_OPERATOR_FIELD 放行。54 案保留待審。
