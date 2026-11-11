# 任務1：同範圍候選元素表比對（2026-11-11）

## 本次結果

基線 93 列、53 欄；填值 1,985、空白 2,944。本次新增 **0 格**、變更 **0 格**，未改任何既有數值或 provenance，未改 source review ledger，也沒有發布 asx-current。Dubbo p26 Table 2 的 Total 列 Y₂O₃ 自動匹配為 75.18 Mt × 1,400 ppm × 0.001 = **105.252 kt**，並通過既有 verify_single_oxide 對原 PDF、SHA、資源範圍及 canonical DB 的驗證。它已在基線中，因此只是同值佐證，不冒稱新增。

24 個有 TREO 且個別氧化物未齊的研究列共有308格缺口。194個候選頁內原始抽取252表；本輪按研究列關聯處理260表次（部分文件同時關聯不同研究範圍），其中1次為Dubbo既有值佐證、259次進待審。實際獨立表數見 summary.json 的 unique_scanned_tables。逐案計數見 project_counts.csv；new_cells.csv、changed_cells.csv 僅有表頭。

**這不代表252張表全部已完成逐格專家審查，也不代表其餘原件沒有可填資料。** 目前自動接入需要已選 resource review 的 native row/section 綁定。canonical DB 選值沒有對應 review 列綁定的81表次仍待補證；沒有用只比數字的方式冒充同範圍驗證。缺少來源明示的同MRE跨文件橋接者73表次待審，CLI未實作任意跨文件自動接受。

## 自動晉升路徑

matcher只產生 source-review 草稿，不直接填CSV。對既有選定資源review的同SHA、同頁、同已驗證列，先比較原文礦石量及TREO品位，容差為最後公布小數位的一半（例如75.18→±0.005），不使用固定百分比。Total/Global或既有相同類別列須唯一，兩個吻合列不自動選。

新氧化物來源標籤、單位、token及儲存格行列交點由原PDF重新讀取，沿用既有scope、statement、有效日、類別及cutoff的review契約。草稿送入既有 asx_validation.validate_reviews，再由 project_summary 的 RESOURCE_ORE_GRADE_OXIDE_PPM 路徑處理。AUTO_MATCHED_SAME_SCOPE_TABLE 標記只在原驗證器通過後加入；native驗證方法、來源SHA、頁、bbox、row/col、原始值、單位及容差皆保留。偽造candidate metadata不能繞過原件驗證。成功fixture已實際驗證這條路徑，並證明原有兩個資源observation的raw字串不變。

支持 ppm、%、kg/t、t、kt：%乘10000，kg/t乘1000；t或kt是同列氧化物**質量**，必須以同列已選礦石Mt轉ppm，重新驗證ore原生儲存格，保留原始token/unit、ore_Mt及轉換方式。未將mass當grade。以原表有效位數傳遞half-width；完整15項時先作閉合檢查，失敗整列不晉升。既有NdPr/HREE8/磁性合計衍生仍由project_summary計算，不另開計算旁路。

## 拒收與待審

- 不在已選資源頁：83表次。
- 缺跨文件同MRE證明：73表次。
- 缺已選review資源列綁定：81表次。
- 沒有缺少的canonical個別氧化物欄：16表次。
- Ce₂O₃非canonical CeO₂：2表次。
- 選定列非native cell：3表次。
- 重複語意欄：1表次。

review_queue.csv保留專案、SHA、頁、表格index/bbox、不符條件、候選氧化物值摘要及本機JSON路徑；不提交整份原PDF、全頁words或完整原表內容。未出現候選表的研究列仍在逐案表中，零待審筆數不能解讀為沒有缺口。

## 測試與重現

21個專項測試＋20子案例：Indicated子集、ppm/%衝突、兩個候選列、cutoff/類別/版本/有效日/REO basis差異、Cummins舊519Mt、Jupiter子區、Goschen缺Ho/Lu、Mount Ridley的Ce₂O₃、CLOSURE_FAIL、Dubbo原生表同值fixture、完整validator正例、五種單位正例與metadata竄改反例。加上既有test_asx_validation.py，共92個測試＋31子案例全部通過。

兩次獨立matcher執行的review草稿、review queue、summary及完整待用source-review配置雜湊相同。**這兩次matcher掃描不冒稱完整來源重建**；正式兩次完整來源重建與整體離線回歸由階段驗收收據另行記錄。

重現：使用 .venv/Scripts/python.exe tools/match_candidate_tables.py --out work/新的唯一輸出目錄。程式強制拒絕socket連線/DNS，不發任何ASX或其他網路請求。工作輸出含完整候選原值供本機審查；本結果資料夾只保留精簡診斷。

## 完整驗收

兩次獨立完整來源重建及Dubbo既有新增投影完成，四CSV與summary/audit逐位元一致；與1,985格基線亦完全相同。完整既有受影響回歸434 tests＋353 subtests通過；本項matcher/保護/重建測試35 tests＋20 subtests通過。詳見acceptance.json及重建收據。
