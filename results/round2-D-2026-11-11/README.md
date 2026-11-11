# 第二輪任務 D

新增 2 格；預期範圍 0–12 格。既有填值與 provenance 全部保留，changed_cells.csv 為空。

依 A → B → C → D 順序套用。此任務兩次從 Census、原始封存來源與既有 review ledger 獨立完整離線重建；四份 CSV、summary.json 與 audit.json 逐位元一致。全程零網路請求。

原 53 欄證據口徑與有 TREO MRE 研究列口徑均見 summary.json；不把總說明呈現變更當作新證據。

決定、來源頁碼／locator 見 new_cells.csv，未決案件與候選見 review_queue.csv。Census、inventory、凍結歷史及 INCOMPLETE／CONTINUE 結論不變。

全套離線回歸：919 tests、568 subtests 通過。

# 第二輪 D：封存原件年產預估審查

本次只讀取 census source-review ledger 內，與指定 15 個研究列相連的封存原件。24 筆專案／原件配對（包含共用政府 prospectus），逐一核對完整 SHA-256；未下載資料、未修改原件。完整 SHA、標題、日期列於 `config/round2_annual_evidence.json` 的 `document_inventory`。

## 可新增兩格

- **Charley Creek：TREO 3,645 t/year。** 2013-04-15 Scoping Study，實體 PDF p5 表 1 明寫「Annual Production – REO Contained in Mixed Carbonate / 3,645 tpa」。p10 明確稱為 refinery nameplate capacity，不能當成 LOM 平均或實際產量。這是來源直接給的 REO 當量，不以碳酸鹽重量乘品位推算。保留 `STAGE_SOURCE_DATED`。p7 顯示研究的啟動採礦計畫含 Exploration Target，不完全等同本列 Total Indicated Resources，provenance 明寫此差異。
- **Goschen Central：TREO 3,041 t/year。** 2025-06-12 Scoping Study，實體 PDF p21 表 10，Phase 1 and 2 欄明寫「Mixed rare earth oxide / Ave tpa / 3,041」。是 14 年研究計畫的平均年產，不是 p3 的 3,800 t/a 設計產能。Phase 1 單獨方案沒有此氧化物產品，Phase 2 另需資本支出。p2 引用同一 2024-12-03 MRE，但 p13 的 77.9 Mt 生產計畫只用部分資源，含 82.5% Indicated、17.5% Inferred；差異與方案完整寫入 provenance。

兩格均保留原始 token、實體頁碼、數值 bbox、整列文字與 bbox、研究名稱及日期、年產口徑、與已選 MRE 的範圍關係。兩張表已逐頁視覺核對。只填原本空格，既有年產數值及 provenance 完全不改。

## 為何不是預期最多 12 格

提示詞所述四案的空白狀態與實際基線不完全相同：Dubbo 已有 NdPr 1,037 t/year，Goschen 已有 NdPr 990 t/year；Donald 亦已有 TREO 與 NdPr。全部保留。

- North Stanmore 2026-08-18 PFS 原件其實已封存（167 頁），不能沿用舊 stage locator 的「未取得完整 PFS」註記作判定。pp4、62、66 是約 29,000 **wet tonnes flotation concentrate/year**，未找到符合本任務的明寫氧化物當量，故不填。
- Dubbo 2025-07-11 Scoping pp5、17、45 的 Dy 49、Tb 11 tpa 不等於本表的八元素 HREO；不把各產品相加成來源未直接公布的 TREO。
- Goschen 2026-09-21 updated economics pp1、2、6 的 8,300 tpa REC 是精礦，115 tpa Dy+Tb 也不是八元素 HREO；不填。
- Cummins Range 2023-08-22 Scoping p77 雖明寫 TREO 年產，卻分別為 Stage 2a：17 ktpa、2b：11 ktpa、3：7 ktpa。不得自行平均、相加或選最大值，也沒有單一方案選擇的研究者決定。因此全部候選留在 review queue，待決定如何把分期年產放入單一欄位。這不是缺來源。
- Sandy Mitchell 2026-10-29 Scoping Update pp7–8 明寫 monazite 7.0 ktpa、xenotime 0.2 ktpa，都是礦物產品，沒有明寫年產 REO 當量。
- Donald 的新增重稀土年產披露限 Dy、Tb，不是八元素完整集合。
- Charley Creek 與 Goschen Central 沒有符合要求的 NdPr 或完整 HREO 年產，不能由元素比例推算。

本表 HREO 八元素為 **Tb、Dy、Ho、Er、Tm、Yb、Lu、Y**，不含 Gd；驗證器與既有 project_summary 定義一致。

## 需要的文件（不自行下載）

- Brockman：primary Scoping Study 與氧化物年產產品表；現有 WA fact sheet／公司報告只有階段與資源摘要。
- Fingerboards：primary Feasibility Study 的氧化物年產表；現有政府 prospectus p36。
- Avonbank：primary Feasibility Study 的氧化物年產表；現有政府 prospectus p46。
- Copi：primary BFS 的氧化物年產表；現有政府 prospectus p47。
- WIM150：primary BFS／optimisation study 的年產氧化物表；現有 2015-10-30 quarterly report 只披露研究狀態。若未來使用該年代的年產，仍須 `STAGE_SOURCE_DATED`。
- Wimmera WIM100：來源明寫的年產氧化物方案；現有 2026-01-29 MRE／季度披露為 DFS 進行中。
- Euston：PFS 年產氧化物產品表；現有 Iluka 2022 annual report p41 只有研究進度，不能挪用集團其他礦山或精煉廠的產量。

## 驗證

`python -m unittest discover -s tests -p test_round2_annual_production.py -v`：12 tests 通過。涵蓋明寫 tpa 接受、ktpa 單位轉換、進料×品位×回收率拒絕、無 REO 當量非氧化物拒絕、Dy+Tb 定義拒絕、決定移除後留白、已填格不變、日期 qualifier 與本地完整 SHA 複驗。完整離線重建與全套回歸由第二輪主流程另外執行。
