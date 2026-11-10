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

## 任務2：分類草稿（尚未核准）

`config/classification_codebook.json` 交付為DRAFT，approved_by與approved_date均為null。工具列出所有非空的完整原文與次數：礦床型態53種／69筆、開發階段40種／54筆；空白不當成類型。提出的助記代碼僅供研究者審查，無權取代既有分類標準或認定當前營運狀態。

只有APPROVED且有核准人、合法核准日的完整對照可填空白代碼。按包含日期的完整原文精確對應，不模糊配對、不改文字、不覆蓋已填值。新代碼的field_provenance包含codebook版本、SHA256、來源欄、原文及原欄完整來源。DRAFT不新增任何值或來源紀錄。本次全部APPROVED情境僅在暫存測試夾具中建立。

重新盤點工具：`tools/draft_classification_codebook.py --table results/asx-current/專案總表.csv --out <新的草稿路徑>`；已有檔案拒絕覆寫，避免刪掉人工審查。6項測試通過。

### UNMAPPED完整清單

| 來源欄 | 完整原文 | 次數 |
|---|---|---:|
| 礦床型態 | Booanya suite granites | 1 |
| 礦床型態 | Clay Saprolite/Granitoid | 1 |
| 礦床型態 | Palaeochannel-hosted rare earth deposits within the same drainage system are also being targeted. | 1 |
| 礦床型態 | REE-bearing quartz sandstone | 1 |
| 礦床型態 | Regolith / granite | 1 |
| 礦床型態 | Regolith and/or carbonatite/ alkaline intrusive host rock | 3 |
| 礦床型態 | Regolith/granite | 1 |
| 礦床型態 | Regolith/oxide-transition | 1 |
| 礦床型態 | TREO enrichment in regolith | 1 |
| 礦床型態 | Tertiary palaeochannel systems | 1 |
| 礦床型態 | The data suggests a clay hosted ionic REE type mineralisation style on the project. This interpretation is subject to amendment with additional data from follow up drilling and metallurgical test work. | 1 |
| 礦床型態 | Trachytic tuff host rock | 1 |
| 礦床型態 | alluvial sand | 1 |
| 礦床型態 | assemblage rich in natural rutile and premium zircon | 1 |
| 礦床型態 | consistent with a highly evolved pegmatite system | 1 |
| 礦床型態 | deeply weathered granites | 1 |
| 礦床型態 | fine-grained heavy mineral (HM) deposits | 1 |
| 礦床型態 | halloysite-kaolinite | 1 |
| 礦床型態 | heavily weathered pegmatites and saprolitic outcrops | 1 |
| 礦床型態 | heavy mineral bearing sandstone unit | 1 |
| 礦床型態 | hydrothermal-related REE mineralisation | 1 |
| 礦床型態 | kaolinitic fine-grained sediments | 1 |
| 礦床型態 | microporphyritic trachyte | 1 |
| 礦床型態 | multiple high-grade strandline systems | 1 |
| 礦床型態 | potential for REE, Niobium–yttrium–fluorine Pegmatites to exist | 1 |
| 礦床型態 | potential for large scale, clay-hosted REE mineralisation | 1 |
| 礦床型態 | prospective for halloysite-kaolinite and rare earth elements (REE) | 1 |
| 開發階段 | Bankable Feasibility Study and optimisation studies（來源揭露：2015-10-30） | 1 |
| 開發階段 | Bankable Feasibility Study（來源揭露：2026-03-31） | 1 |
| 開發階段 | Bankable Feasibility Study（來源揭露：2026-03，月精度） | 1 |
| 開發階段 | Feasibility Study（來源揭露：2026-03，月精度） | 2 |
| 開發階段 | June 2023 aircore drilling program（來源揭露：2023-08-01） | 1 |
| 開發階段 | Preliminary feasibility study work was progressed in 2022（來源揭露：2023-02-21） | 1 |
| 開發階段 | completed the maiden drilling program（來源揭露：2023-02-14） | 1 |
| 開發階段 | continued to follow up on the high-priority target areas（來源揭露：2026-09-29） | 1 |
| 開發階段 | currently the subject of a definitive feasibility study (DFS)（來源揭露：2026-01-29） | 1 |
| 開發階段 | decided to withdraw from the ‘option to acquire’ agreement（來源揭露：2026-07-16） | 1 |
| 開發階段 | exploration and pre-development drilling program（來源揭露：2026-06-16） | 1 |
| 開發階段 | planned and prepared for its Phase 1 drilling programme（來源揭露：2026-05-18） | 1 |
| 開發階段 | ready for immediate drill testing（來源揭露：2023-07-25） | 1 |

## 任務3：未知與結構性空白分開

判斷條件及排除分母放在 `config/blank_classification.json`。`missing_fields.csv` 新增blank_class與blank_rule_id；原reason與補證欄保留。預設UNKNOWN，僅命中明確規則才改類別。每次export重算，分類不填資料格、不寫0，也不改field_provenance。

NOT_APPLICABLE_STAGE僅適用設定中明列且有來源紀錄的歷史勘探原文，並同時沒有選定資源量、品位、TREO總量、資源估計標記、產品或任一年產預測。只有空白或無階段、模糊階段、已有資源或產品均不觸發。這是「在來源揭露階段的分析分母約定」，不是目前現況、永久不適用或證明沒有工程預測。當資料或規則改變必須重算。

NO_COMPARATOR_SOURCE必須是指定HTML差值欄且原診斷為沒有獨立比對來源。PENDING_CODEBOOK為三分類欄等待核准／對照；仍計入調整後分母。UNKNOWN也全部計入。規則次序：PENDING_CODEBOOK、NO_COMPARATOR_SOURCE、NOT_APPLICABLE_STAGE，最後UNKNOWN。只排除空白中的NOT_APPLICABLE_STAGE與NO_COMPARATOR_SOURCE，填值分子不變。

| 類別 | 空白格數 | 從調整分母排除 |
|---|---:|---|
| UNKNOWN | 2584 | 否 |
| PENDING_CODEBOOK | 278 | 否 |
| NO_COMPARATOR_SOURCE | 93 | 是 |
| NOT_APPLICABLE_STAGE | 30（10列×3年產欄） | 是 |

原覆蓋率1944/4929 = **39.44%**；排除123格後1944/4806 = **40.45%**。原表仍93×53、1944已填／2985空白，不把結構分類算成新增填值。完整計算保存在 `results/convergence-codebook/blank_coverage.json` 及當前summary.json；LATEST.md同時呈現兩個分母。來源、總表、inventory仍逐位元組一致。分類及codebook局部測試11項、6個子測試通過。
