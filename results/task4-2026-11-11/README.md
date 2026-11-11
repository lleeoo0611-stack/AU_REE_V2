# 任務4：兩項研究者核准的例外（預設關閉）

## 狀態與數字

正式決定檔的 `decided_by` 保持 `null`，正式新增0格、變更0格，未發布至 `results/asx-current/`。`new_cells.csv`、`changed_cells.csv` 均只有標頭。

`preview_new_cells.csv`、`preview_changed_cells.csv` 是以工作目錄內 `TEST_FIXTURE_ONLY_NOT_RESEARCHER_APPROVAL` 決定檔執行的離線試驗，不代表研究者核准或正式資料。試驗新增8格（Splinter 7、Circle Valley 1），只變更4個允許的衍生欄。待研究者決定2項，列於 `review_queue.csv`。

正式基線：1,985填值、2,944空白；全表1,985/4,929=40.2719%；沿用結構空白排除後1,985/4,806=41.3025%；有TREO資源量36列，1,181/1,908=61.8973%。

試驗核准後：1,993填值、2,936空白；全表1,993/4,929=40.4342%；排除後1,993/4,806=41.4690%；有TREO資源量37列，1,224/1,961=62.4171%。資源列分母增加是Splinter取得canonical TREO，並非修改分母規則。

## Splinter來源、換算與閉合

僅限 AU-574465211976ec57b1ef，statement `splinter-inferred500-r254-20151109`，原件SHA `428c8f759ec2f4dc393177f0fccce12cc96c9b1359638d003f7ea30b6d388df7`；不是Splinter Rock。

物理頁69（印刷頁57）說明使用表33的元素轉氧化物係數計算資源量，Cerium列明示Ce2O3、1.171。物理頁72表35選定500ppm來源TREO+Y2O3 cutoff、Inferred、22,849千噸列：Ce2O3 397ppm、TREO+Y2O3 1,056ppm、TREO（不含Y）943ppm、Y2O3 113ppm。原文資源類別、截止品位、日期角色與表列範圍均保留。

Ce=140.116、O=15.999，以程式計算 `2×(Ce+2O)/(2Ce+3O)`，得1.048743407803698。來源元素轉Ce2O3的計算係數 `(2Ce+3O)/(2Ce)` 約1.1713，落在原文1.171有效位數的±0.0005內。canonical CeO2為416.351132898068ppm、9.513207035587959kt。

來源明確可確認TREO口徑，因此以含Y的1,056ppm起算：1,056−397+416.351132898068=1,075.351132898068ppm，品位0.1075351132898068%、canonical TREO 24.570698035587956kt。不把不含Y的943ppm直接當總量。

原生14個相容氧化物精確加總659ppm；加上Ce2O3 397ppm恰為1,056ppm。換算後15項氧化物合計24.57069803558796kt，與canonical TREO差異僅浮點表示約3.55×10^-15kt；以原始數字Decimal算的差值為0。

閉合容差依每個來源整數ppm的±0.5有效位數計算，**沒有固定百分比**。相同Ce換算輸入同時出現在加總與重算TREO中，會抵消；因此比較的是14項原生氧化物+原生Ce2O3−來源TREO+Y2O3，半寬為14×0.5+0.5+0.5=8ppm，即0.182792kt。不是把共享換算Ce的不確定度算兩次。相同礦石量也是共同乘數。

新增CeO2、TREO品位、TREO總量、有TREO資源估計、磁鐵氧化物總量、磁鐵佔TREO比率、元素總和/TREO，共7格。更新元素數14→15、元素總和及一致性說明，共3個衍生欄。既有14個氧化物、NdPr、HREE8、磁性元素重算值與provenance保持原樣。

## Circle Valley合計NdPr

僅限 AU-785536db5ff12c25350d，statement `circle_valley_global_202306`，原件SHA `259ebe012c6b6e2048ca2f50f5b47e4c91d9a56e520c97f6deee554d069a54ad`。物理頁2表1 Total列同時列98Mt與220ppm NdPr；表下注明 `NdPr = Nd2O3 + Pr6O11`，全部Inferred，US$145/kg basket pit、430ppm TREO-CeO2 cutoff。沒有使用13Mt高品位子集。

98×220×0.001=21.56kt，僅新增 `NdPr蘊藏量_kt_需兩者皆公布`，method為 `SOURCE_COMBINED_NDPR_OXIDE_PPM_X_ORE_MT`，並更新一致性說明。不拆分Nd或Pr、不增加元素數、不改四項磁性元素門檻。欄名與輸出結構不變，欄位說明見 `docs/RESEARCHER_SCOPED_OXIDE_EXCEPTIONS.md`。

## 驗證與保護

先由既有 `validate_reviews` 驗證來源，再由既有native-cell／partial-resource驗證器確認原選定列、類別、cutoff與全部原生輸入。額外欄位綁定exact source SHA、statement、同一row bbox、唯一表頭、ppm單位及唯一數字token。每個新值的provenance包含decision_id、method、原始值、頁碼、bbox、係數與原子量；原始review ledger與舊partial-resource模式不變。

試驗投影先extend至53欄，再執行既有 `apply_archived_element_additions`，保留Dubbo既有Y2O3及其衍生欄。`coverage_task_audit.compare_projections(..., allow_derived=True)`通過：所有未變更既有值／provenance、93列cohort與inventory均保留。

`tests.xml` 包含新模組14個測試及既有partial-resource 22個測試。測試含null決定檔與未傳決定檔之四份CSV和summary逐位元一致；未核准時不讀額外原件；錯誤statement/SHA、未驗證bundle、不同scope、cutoff篡改及既有值覆寫均拒絕。所有操作離線，網路請求0。正式雙重離線重建及保護雜湊由本次總任務的共用重建收據記錄。

## 完整驗收

以task2正式輸出為基線，兩次獨立完整來源重建並重播既有Dubbo新增，四CSV與summary/audit逐位元相同，未核准輸出與前項六檔也逐位元相同。434項既有受影響回歸及353子案例全過；跨項新測試詳見integrated-tests.xml。決定檔雜湊已綁入core_rebuild_receipt.json，保護檢查及數字見acceptance.json。
