# Phase 15：來源限定的 Technical 擷取與實證分析

本次將已封存原件接通到 `recognize → ingest_recognized → observations → Selection → Technical analysis`，不再只保留技術描述。使用同一 `work/phase5/canonical.sqlite`、Python CLI 與 R 引擎；沒有 Schema migration、第二正式資料庫、新佇列或正式評分替換。

基準為 Phase14 `e97272b`／Draft PR#4。最終 run `20261104T100827-bb0d2956`，研究 cutoff2026-11-03、取得窗口至2026-11-04、上游正式 cutoff2026-10-29。四份新下載均記錄實際取得時間，沒有回填歷史取得日。Phase5–14 凍結檔案及369筆既有 Manifest 紀錄未改動。

## 實際增量與計數口徑

| 指標 | Phase14 | Phase15 |
|---|---:|---:|
| canonical registry groups／resource-defined cases |31／21|31／21|
| 選取來源快照／已辨識文件 |242／32|251／37|
| 有效來源數值觀測列 |321|703|
| 上述可歸屬並通過 Project selection 的列 |319|701|
| Project-selected Technical 數值列 |168|550|
| 全 registry 六構面可評分覆蓋 R/S/T/D/I/C |21/10/0/9/19/8|21/10/0/9/19/8|
| Development／Full-evidence／正式 C1 |0/0/0|0/0/0|
| 九個 MCDA 面板 n |19/7/8/2/2/10/6/17/2|相同|

321／703 包含兩筆有效但未准入 Project selection 的來源觀測；40筆 Study Parameter 另計。D9/C8 是全 registry 可評分數，resource-defined cohort 中對應 D8/C6，不能混用母體。Commercial 的 C1 criterion code 與正式 C1 cohort 是不同概念。

新取得四份不同 SHA 原件：Donald2026 BFS、Yangibana更新DFS、Goschen Central2025 Scoping、Nolans2019 DFS。Nolans指定舊網址404，改由ASX取得178頁原件；沒有宣稱是同一失效URL的逐位元副本。[取得紀錄及SHA](../data/phase15_source_acquisition.json)。Goschen Central的ADC專案身分與既有VHM Goschen未建立可靠關係，候選保留、不合併。

五份文件自動產生379個表格格位：373個數值、6個明示缺值；371個數值通過原始觀測驗證，另保留Dubbo負值與Nolans氧化物方程標籤衝突。它們屬四個既有Project、九個來源表格範圍，不是379個實驗或新增Project。既有三份核心原件提供313格，其中指定目標表308格，另5格來自同份Cummins2023 Stage3設計表；新Donald／Nolans原件提供66格。

Cummins2026十二格TREO產品品位／回收率及一格給料品位已在curated observations中出現；新表格紀錄屬更細定位的佐證，不計為新測量。其餘相同數值也可能佐證既有設計參數，不宣稱371個新獨立測量。來源試驗數、選定結果、資料格、typed Study Cases、Project及可評分 Project×Criterion 分開統計。[量化結果](../data/phase15_research_summary.json)。

## 擷取與資料流修復

新解析版本為 `document-recognition-v5-technical-cells`，歷史v1–4保留原路徑。技術表頭可先觸發原生表格偵測，無須先命中JR／Avg或Resource total。以原生矩形對齊合併表頭、資料格與單位，不依稀疏表格的固定陣列欄號；From／To表身缺格線時採文字位置。只處理選定文件中有線索的頁面，重用具有來源SHA、頁碼、後端與解析版本的快取；v5遇舊快取缺幾何資訊會重新解析。本次核心原生文字可讀，未執行全面OCR。

每格保留原token、表頭路徑、row/column、bbox、頁碼、來源SHA、發布日角色、樣本／階段／端點及擷取版本。負號、range與N/A不改寫；範圍不取中點，明示缺值保持NULL。`X% recovery`、`recovery of X%`及具元素的extraction語句綁定各自數量、basis與限定詞；不將grade、moisture、IRR、採礦／core recovery誤升。直接語句缺少試驗尺度或basis時仍保留未確定性，並非整體性能。

Project歸屬重用既有來源SHA關係、穩定ID及來源標題核對；多重或不同專案關係不強制綁定。代表性僅在同一原件、明示命名樣本、原頁敘述與目標母體可連結時傳遞。來源的「representative」聲明仍是來源聲明，不是整體資源外推的證明。

`selection`原有三個Technical函式移至共用`technical.py`並重匯出，Selection與分析沿用同一判定。v2用途契約按物理／化學製程需要條件：同composite flotation不要求酸濃度；具體浸出條件不足時只能作欄位限定描述，不取得酸效應或Project外推資格。相對TC1的`NOT_COMPARABLE`不再意味沒有其他研究用途。正式T1、TC1/TC2、六項C1 Gate及權重未變。

## 已可回答的技術問題

**Dubbo Tables4–6，實體30–32頁。** 重建270格、269格具有效百分比範圍。Central最後粒徑仍印25mm，East六欄仍印50g/L HCl，East Er第4欄仍為−0.5%。不修成推測設計、不截零。West依明示欄標提供45個附條件的高／低酸標籤對照差值；表內g/L與敘述kg/t尚未調和，因此不是酸用量的因果估計。Central／East按原始欄位位置描述。三個複合樣、元素列及六欄均不充作獨立重複，未做顯著性檢定。

[來源長表](../results/phase15-2026-11-04/technical_cells.csv) · [矩陣圖](../results/phase15-2026-11-04/technical_element_matrix.svg)。

**Cummins2023 Table10-3，實體60頁。** Stage2a／2b各2.0Mtpa乾給料，年度collector600t、NaOH4000t、silicate3600t、flocculant40t。十個來源參數支持八個衍生強度，每階段依序為0.30／2.00／1.80／0.020kg/t乾給料。公式為年度t×1000／(乾給料Mt×10^6)。同份文件63頁Stage3另有五個來源參數及四個同定義衍生量，保持獨立階段。商品配方／溶液質量不自動換成純活性物質；不將此乾給料分母改稱whole ore，也不與2026選定composite結果拼成一個性能—負擔點。

[試劑圖](../results/phase15-2026-11-04/technical_reagent_intensity.svg) · [65個可追溯衍生值](../results/phase15-2026-11-04/technical_derived.csv)。

**Cummins2026 Table2，實體3頁；樣本限制在2頁。** 28格保留TREO與Ce原標籤；Ce不改稱CeO2。CRCS-10是選定高品位樣，不必然代表長期給料。三個較佳試驗是從11次flotation挑出，並非每列11次重複。四個Feed格包含兩個100%回收率參考值，不當成實測回收率。

F7／F8二次精選對粗選的附條件累積保留比為29.2/68=0.4294118、37.6/74.6=0.5040214。使用前提是兩者相對同一表列原始給料，不相乘兩個累積率。另計六個TREO富集比；F7的25.15/2.85=8.8245614倍，與9.5倍敘述保持未解的scope／分母差異。同一二次精選端點，F11在表列點值上被F7、F8名義支配；未知測量誤差，不是統計結論或全Project技術排名。

[品位—回收率圖](../results/phase15-2026-11-04/technical_grade_recovery.svg) · [可編輯數據](../results/phase15-2026-11-04/technical_grade_recovery.csv) · [衝突](../results/phase15-2026-11-04/technical_conflicts.csv)。

**Donald2026 Table10-1，實體45／印刷33頁。** 50格含6個缺值，保留MUP→WCP→Raw HMC及CUP的HMC／REEC分支。五個礦物／氧化物各列兩個分支檢查，共10列；其中五個分支與報告overall在顯示精度區間內相容。例如CeO2：99.5%×94.5%×97.5%=91.6793%，與91.7%相容。容差由三個0.1%精度的因子及overall顯示精度推得，沒有任意放大。原表「Overall Recovery to HMC」表頭與「HMC/REEC」目的地都保留；相容的REEC分支只作條件式來源一致性解釋。不同分支不相乘，限定在in-THM／in-size，不能改稱whole-ore TREO。

[流程一致性表](../results/phase15-2026-11-04/technical_flow_consistency.csv)。

**Nolans2019，實體44–45頁。** 保留828.7kg H2SO4/t concentrate及15個分氧化物設計係數；Yb2O3列右側印Tb2O3的衝突保留為REVIEW。其餘14列僅准來源設計參數剖面，不表示全部適用於base case：La參數受分離廠是否含La回收迴路的腳註限制，base case排除該迴路。未推導加權TREO回收、whole-ore耗酸或實際運轉績效；細緻的腳註／scenario mapping仍未自動完成，原頁及完整文字在來源快照中保留。

## Technical 定義、Aim與限制

現有資料已能操作化指定樣本／mine-plan內的元素浸出、產品品位、階段／累積回收、乾給料試劑強度及來源流程一致性。原先8個resource-defined Project具有來源限定性能，更新後9個；全registry相關性能來源達11個Project，仍不可解讀為Project平均性能。348格取得本階段某一案例用途契約，另有乾給料等支援參數；「未取得所列契約」不等於無效原文。

這些構念適用於明示碳酸岩／磷酸鹽、鹼性多金屬及礦砂等來源流程；不同礦物賦存、給料、REO basis、終點及尺度不能跨群正規化後拼成全澳排名。**目前不建議直接替換正式T1。** 已成立的是用途限定的性能剖面與同端點比較，不是已驗證的普遍效用函數。Processing Complexity、V2 Recovery與處理負擔分開；代表性／品質作適用範圍及未量化不確定性，不按DFS、文件數或流程步驟加分，避免重複D1。

Aim A沿用既有九面板，沒有新增正式共同MCDA樣本；142個面板CSV與Phase14一致。Aim B原AHP／SAW／PROMETHEE II／TOPSIS、Monte Carlo及敏感度結果未變；技術案例補充名義支配和報告顯示精度，不任意設定測量誤差。Aim C擴充可查詢的礦物、樣本、流程／階段與來源限定剖面；未因小樣本增加無解釋力的多變量檢定，也不將對照差值解釋成因果。

## 評估、維護性與重建

修復前實際函式測試為3個FAIL／1個ERROR，[紀錄](../data/phase15_pre_repair_tests.txt)。修復後新增16項回歸／整合測試。逐格答案由原件頁面AI輔助目視核對及原生文字交叉確認，不是獨立人工審核；Central Ce曾誤抄73.4，放大原頁確認74.3後修正標註，沒有修改解析器遷就答案。

| 固定評估範圍 | TP/FP/FN | 說明 |
|---|---|---|
| 三份核心原件、指定五個表格頁 |308/0/0|開發／回歸集；含正確轉錄的負值，非308個合格測量|
| 新Donald的CeO2/Y2O3十格 |10/0/0|僅此十格，不宣稱50格均有獨立標註|
| 新Nolans十五個係數 |15/0/0|忠實轉錄不代表方程／scenario皆可用|
| Browns Range116頁兩個Technical格 |0/0/2|未參與本階段規則調整；既有已知檔案，不宣稱盲測|

匹配要求數值、單位、數量及該表適用的元素／樣本／階段／欄位條件；已匹配格定位完整。Project身分另由來源SHA關係、標題及ID穩定性測試檢查，不把逐格結果誇稱獨立身分審核或全澳準確率。舊v4對上述新table-cell類型的指定核心格為0TP/0FP/308FN（precision未定義，非準確率100%）；新增原件分開記錄，不混成Phase14原有來源的增益。[逐文件評估](../data/phase15_document_benchmark.json) · [修復前](../data/phase15_document_benchmark_before.json)。

共用Technical gate只保留一份實作；新`technical_tables.py`負責幾何／數量辨識，`technical.py`承接從Selection移出的技術責任及來源限定計算。依賴為parser→table recognition→store primitives，以及selection→technical→store primitives；沒有反向收集來源或第二個控制器。`analysis.prepare`維持105行，CLI execute370→377行；新native dispatcher10行、各表格family21–28行、analysis assembler65行。`recognize_document`因來源／快取／幾何處理由67行23個分支節點增至116行45節點，是仍集中之處，不能宣稱整體分支數下降。比較gate26→32行，增加的是版本化用途規則；52行共同比較器移動後維持單一實作。[AST量測](../data/phase15_maintainability.json)。

本機215項Python通過（441.381秒）；R三組不變量通過。試劑圖長標籤裁切在視覺檢查中修正後，重跑R及最終主程式／兩次clean reconstruction。最終兩次clean：142個panel CSV、7份既有evidence及7份新technical輸出完全一致；canonical與clean亦一致。Phase14 historical replay142+7一致，無浮點差異；493個來源／原始回應檔SHA、7,555個ID、SQLite integrity／foreign keys通過。7份final extraction全部重用，Manifest位元未變。[重用紀錄](../data/phase15_extraction_reuse.json)。Phase5–14原lock與既有容差／六個Phase5 R.log例外保留；CI再執行完整Python、R、Phase5–15重建，結果以本PR checks為準，沒有把離線CI冒稱Live取件。

重現命令見[凍結結果](../results/phase15-2026-11-04/README.md)。表格與SVG由既有CLI產生，`R/technical_plots.R`可從CSV重繪。沒有使用私人CSV、審核ZIP或使用者頁面影像作研究輸入。完成Phase15後停止，不合併先前Draft、不自動啟動下一階段。

## 文獻閱讀界線

沿用[Phase12閱讀紀錄](phase12-literature.md)，本次再讀固定版[JORC2012 Table1 Sections3–4](https://www.jorc.org/docs/JORC_code_2012.pdf)的冶金假設／代表性（PDF30、32頁）；它支持區分試驗量、代表性、礦物域及回收假設，不能自動替自訂權重或專案數值背書。這是2012指定版本，不稱最新規範。

再讀[Borst et al.2020機構保存全文](https://nora.nerc.ac.uk/id/eprint/529134/1/s41467-020-17801-5.pdf) Discussion（文章7–8頁）的賦存與難處理礦物差異；未重做光譜或以礦床標籤推認澳洲樣本機制。[McNulty et al.2022](https://doi.org/10.1557/s43577-022-00288-4)本次僅可讀出版社摘要，全文需訂閱；[Jordens et al.2013](https://doi.org/10.1016/j.mineng.2012.10.017)本次DOI入口不可取，未宣稱全文審查。文獻不替代本次原件頁面、可比性契約或程式測試。

另保留14份canonical歷史紀錄所引用、但未選入研究lock的開發擷取快照（各自SHA驗證）；它們不計入251個研究輸入、四份新原件或有效測量增量。15份從未入庫且未選取的中間擷取檔移至忽略的工作目錄，未刪除原件。最終程式bytes已與Git index核對，避免Windows換行轉換造成程式雜湊錯配。
