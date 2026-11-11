# 第二輪覆蓋率提升結果（2026-11-11）

本輪已完成可用封存證據的新增與離線驗證，分 A → B → C → D 保存；C 的 NT 轉換驗收仍受阻，未發布至 results/asx-current/。

- A 礦床型態：+38 格；Greater Brothers、Perenjori 留白。
- B 開發階段：+30 格，15 案。
- C 座標：+2 格，Cascade／Zinc of Ireland；54 案待審。
- D 年產預估：+2 格，Charley Creek 3,645 t/年 TREO、Goschen Central 3,041 t/年 TREO。
- 合計：+72 格，2,069 → 2,141／4,929；覆蓋率 41.98% → 43.44%；空白 2,860 → 2,788。
- 有 TREO MRE 研究列口徑：1,276 → 1,307／1,961（37 列），65.07% → 66.65%。

每階段均執行兩次完整離線來源重建，四份 CSV、summary 與 audit 逐位元一致，且 919 tests＋568 subtests 全通過。所有既有數值與 provenance、Census SHA、inventory、凍結歷史及原 INCOMPLETE／CONTINUE 結論保留；既有未提交的 PDF/HTML layout 工作未改動。未推送遠端。

## 尚未完成與發布阻擋

NT 封存 CSV 的 SHA 已驗證，但未找到能確定 CSV MGA datum 的封存 metadata；因此沒有猜測 GDA94／AGD66，也沒有以合成轉換測試取代真實控制點驗證。C 的這項驗收未完成，發布條件不成立，results/asx-current/ 維持原狀。

WA 多數名稱候選缺少可確認一致的公司值，不能放寬公司條件；多 site 代表點與 VIC／TAS 新來源仍待研究者決定。年產資料只接受來源明寫的氧化物或明寫氧化物當量；Cummins Range 分階段產量不擅選，重稀土定義不足與缺件皆列待審。

各階段詳細新增、待審、來源定位、雜湊與收據見相應 results/round2-A、B、C、D-2026-11-11/ 資料夾。最終比較見 coverage_comparison.json；發布狀態見 publication_status.json。
