# 收斂、分類草稿、空白語義與報告體積工程修改

本次只改規則與程式結構，無新一輪蒐集、來源搜尋、下載、登入或付費。原始基準為 `37665aa1`：93研究列 × 53欄，1944已填、2985空白。研究列不等於獨立礦案；Yttria／Mt Stirling同一資源範圍不加總，不跨案轉填，未知不填0。Census與已提交歷史報告保持原樣。

## 任務1：有受阻清單的連續零增量停止規則

新增明確選用的 `CONSECUTIVE_ZERO_GAIN_WITH_BLOCKED_BACKLOG`。manifest的 `consecutive_zero_rounds` 預設2，必須為正整數。完整範圍、雙軌紀錄、來源、測試、重建及全部非取得動作均通過，且連續N輪新增合格格數為0，才停止。既有四種policy與歷史重播不變。

`blocked_acquisitions` 每筆保存 action_id、URL或作品、限定的失敗類型、首次受阻輪次、可能影響的project_ids及columns、影響範圍說明、人工途徑與證據引用。未分類取得動作、無證據受阻、未完成審查、測試失敗、重建不一致都不能豁免。範圍未完成仍為INCOMPLETE，計數歸零。有增量也歸零。

`previous_cycle_reviews` 必須按輪次連續、表格雜湊首尾相接並使用相同policy；由歷史receipt的實際增量與完整性重算計數，不接受外部聲稱的累積計數。這些receipt和來源/測試宣告一樣是審查證據，計數器不獨立重新執行歷史測試或判讀PDF。沒有歷史receipt時只算當輪，不能憑空補輪次。

停止分為STOP（無受阻）與STOP_WITH_BLOCKED_BACKLOG（留有取得障礙）；未達連續輪數為CONTINUE；其他不完整為INCOMPLETE。**停止不代表來源已窮盡，也不代表全國收錄完整。** 不會自動發出網路請求。

### 第19、20輪離線重新判定

`tools/rejudge_convergence.py` 先以舊policy重播並要求結果與原報告完全一致，再另作新policy判定；原檔不改。只使用本機凍結輸出。

| 輪次 | 實際新增合格格數 | 非取得完整性 | 連續零增量輪數 | 新判定 |
|---|---:|---|---:|---|
| 19 | 4 | 通過 | 0 | CONTINUE |
| 20 | 0 | 通過 | 1 | CONTINUE |

預設N=2，因此不能宣稱目前已收斂停止。詳細證據在 `results/convergence-codebook/historical_rejudgment.json`。八項取得障礙是七項HTTP403與一項REMP有界逾時；不是八項都403。六份原訂作品缺同版替代；VIC2024已有同作品同版官方館藏但原URL仍受阻；Fingerboards另有一份受阻作品。影響欄位僅是待補證的可能範圍，不能宣稱原件必有可填數值。

## 驗證與提交安排

四項任務依序各一個commit。不可變基準及驗證工具保存1944格總表、完整field_provenance、inventory、審查ledger、Census及既有ASX歷史檔案SHA256。後三項結果與最終完整回歸、兩次獨立重建和差異鏈還原證據會在相應commit補入本文件。

任務1針對停止規則測試：28 passed、67 subtests passed。第一次在受限暫存目錄執行因WinError5失敗；在正常本機權限重跑全數通過，沒有改小測試範圍或放寬規則。
