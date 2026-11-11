# 研究者核准的兩項氧化物例外

預設為關閉。`export_summary(..., researcher_decisions=...)` 接受 Path、字典（`decisions` 陣列）或陣列。未傳入、`decided_by=null`、空字串均不套用；不得把測試夾具中的核准者當成研究者核准。

## Splinter

僅限 `AU-574465211976ec57b1ef` / `splinter-inferred500-r254-20151109`，不是 Splinter Rock。原件 SHA `428c8f759ec2f4dc393177f0fccce12cc96c9b1359638d003f7ea30b6d388df7`。

物理頁69（印刷頁57）說明資源量以表33元素轉氧化物係數計算；Ce2O3 = 1.171，Y2O3 另列。物理頁72表35的500ppm cutoff、Inferred列：22,849千噸、TREO+Y2O3 1,056ppm、TREO不含Y為943ppm、Ce2O3 397ppm、Y2O3 113ppm。以含Y的1,056ppm為起點，不把943ppm誤當canonical TREO。

係數使用 Ce=140.116、O=15.999 計算 `2×M(CeO2)/M(Ce2O3)`，不硬編碼捨入值。Canonical TREO = 1,056 − 397 + 397×係數。原始cutoff仍為來源定義500ppm，不能重新分類為canonical cutoff。來源有效日期／技術報告發行日期角色不改。

舊 `ORE_AND_COMPATIBLE_OXIDES_ONLY` 模式保持原狀。新模式為 `CERIUM_STOICHIOMETRIC_CONVERSION`，額外原生欄讀取綁定同一選定列、表頭、ppm、bbox，重用既有native-cell與partial-resource驗證器，確認原件SHA及選定bundle後才衍生。

## Circle Valley

僅限 `AU-785536db5ff12c25350d` / `circle_valley_global_202306`，原件 SHA `259ebe012c6b6e2048ca2f50f5b47e4c91d9a56e520c97f6deee554d069a54ad`。物理頁2表1 Total列98Mt、220ppm NdPr；表下注明 `NdPr = Nd2O3 + Pr6O11`，Inferred、US$145/kg basket pit、430ppm TREO-CeO2 cutoff與既有資源完全相同。

`NdPr蘊藏量_kt_需兩者皆公布` 在研究者核准下可接受來源公布的合計氧化物品位，以 provenance 的 `method=SOURCE_COMBINED_NDPR_OXIDE_PPM_X_ORE_MT` 區分；欄名不變。98×220×0.001 = 21.56kt。不拆分Nd與Pr、不增加元素數、不改四項磁性元素規則。

新值provenance的locator以JSON記錄decision_id、statement、scope、原始值、頁碼、bbox及換算。只允許更新元素數、元素總和、元素總和/TREO及一致性說明；其他既有值／provenance均保護。
