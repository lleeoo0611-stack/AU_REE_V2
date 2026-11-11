# WIM100 原件與第三輪分支核對

本次核對基準：本機 `experiment/round3-researcher-approved-20261111` 的 `f2d657c`；檢查時遠端 `experiment/asx-public-acquisition-20261109` 仍為 `cde12ab`。任務 1–5 已存在於本機第三輪六個提交，不是尚未執行；本次不重做任務 0，不重複計入新增。

## Iluka 資源口徑

- 研究列：`AU-ff758cad5beb276d327d`，Wimmera Mineral Sands Project — Iluka WIM100。
- 原件：Iluka，2026-01-29，WIM100 Mineral Resource estimate increase。
- 原件 SHA-256：`54ae6be3b275f744e627c0ae5dd542fe2fdaab7404649c809cdc48d97ff11732`。本次直接讀取封存原件、驗證雜湊並目視第 3、4 頁，未新增網路資料取得。
- 第 3 頁 Table 1 的 **2026** Total 列：Resource Tonnes **540 Mt**、In situ HM Tonnes **25 Mt**；Measured+Indicated+Inferred，cutoff **1.0% HM**。540 Mt 是礦砂礦床的總礦石資源量，不是 540 Mt TREO，也不是 25 Mt HM。
- 第 4 頁 Table 2 Total 列的 Nd₂O₃ **0.28%**、Pr₆O₁₁ **0.079%**，註腳明示氧化物百分比以 HM 含量為分母。兩表範圍與截止品位一致。
- 因而 NdPr 中央推導值為 `25 × (0.28 + 0.079) × 10 = 89.75 kt`。不可乘 540 Mt。來源捨入、HM 質量和氧化物百分比的不確定性仍保留；89.75 不是宣稱量測精度達 0.01 kt。
- 來源未直接列出 bulk TREO 品位／總量。既有模式 `BULK_ORE_AND_HM_HOSTED_OXIDES_ONLY` 故意保留這兩欄及「有TREO資源估計」空白，並未標成「否」。不應把空白解讀為沒有 MRE，也不應僅因15個元素值齊全便把來源未報告的 TREO 旗標改成「是」。
- 第三輪 `selected_mre` 依已選定礦石量及其完整 provenance 判定，因此 WIM100 已納入有已選 MRE 的組別。實際分組為 **38／55 案**，與用 TREO 旗標分組的 37／56 不同。

## 浮點尾數

`89.75000000000001` 及部分同來源衍生數值是二進位浮點運算尾數。輸出修正必須與來源十進位 token 計算相容，保留原值、完整 provenance 及來源捨入資訊，不新增資料、不改分母、不用固定小數位把所有科學值任意截斷。修正的前後映射及驗證由相應精度呈現收據記錄。

## 第三輪已完成成果

- 本機任務提交：0 `934e02e`、1 `9a8b77e`、2 `ccb2619`、3 `77077b1`、4 `946f0f5`、5 `f2d657c`。
- 新增資料29格：階段12、座標16、Cummins年產1。刪除兩個全空欄及分母重分類不是新增資料。
- 93列×51欄；標準證據口徑2170/4743（45.75%）；兩層口徑2170/3038（71.43%）；含總說明的展示格數另列。
- 詳見 `results/round3-summary-2026-11-11/` 及各任務的雙重重建、測試與發布收據。VIC無合格新增、TAS403後停止，不宣稱資料搜齊。
