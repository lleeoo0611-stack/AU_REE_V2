> **尚未完成 T6(b)/T7(b)**：本機網路失效；不發布無效結果。T1–T5、Phase20–22 重建、379 項 Python 與 R 測試已完成。PR 維持 Draft，等待乾淨 CI 實際建置。

# Phase 22 主線整合與可重建專案總表

從 `070df10` 建立 `feat/integrated-rebuild-20261115`，以 Phase 22 架構整合來源宣告與既有模組內規則。PR 目標為 `feat/phase16-technical-model`，禁止 merge；未合併實驗分支。

匯出契約與 Phase22 基準總表為 93 列、51 欄；本機新建置因網路失效中止，尚未交付有效新版，包含 Yttria / Mt Stirling 的明確未合併例外。只輸出逐專案資料，沒有全國資源量加總。自動驗證不是正式 C1 核准，也不建立六領域全國排名。

## T0：網路與 ASX 試抓

DNS 預檢 47 個 host，全數通過。完整來源建置網路狀態為 `RUN_INVALID_NETWORK`，NETWORK_ERROR 150/208，門檻為超過 5% 即非零退出。先前受限環境的 WinError 10061 診斷保存在 [prior-network-diagnostics](prior-network-diagnostics/)，不是本次遠端 HTTP 結果。

|host|key|HTTP|結果|原因|
|---|---|---|---|---|
|www.asx.com.au|asx_nolans_clarification202606|200|UNAVAILABLE|NOT_PDF|
|www.asx.com.au|north_dam20230822|200|UNAVAILABLE|NOT_PDF|
|www.asx.com.au|asx_redlings_maiden202501|200|UNAVAILABLE|NOT_PDF|
|announcements.asx.com.au|browns_range_2025|200|FETCHED||
|announcements.asx.com.au|mia_ar2024|200|FETCHED||
|announcements.asx.com.au|yttria_2025|200|FETCHED||

`www` 的 HTTP 200 非 PDF 回應不計為原件成功，也不冒稱 HTTP 403。所有 probe 失敗均未重新請求；成功 bytes 供同次建置沿用。4xx、CAPTCHA、登入頁停止該 host；每 host 3 秒間隔，只有逾時/5xx 重試一次。未更改 User-Agent、參數，未探索新 IR 網址、未建立人工下載資料夾。完整逐筆狀態見 [asx_probe.csv](asx_probe.csv)、[acquisition_report.csv](acquisition_report.csv)。

## T1：來源遷移

驗收來源中「76 份 SHA」實際是 50 個不同的原子 SHA，加上 26 個分號組合的來源參照字串；組合參照不代表另一份原件。396 格關聯與 76 個參照原樣保留於 [source-migration-2.csv](source-migration-2.csv)，另以 [source-migration-2-atomic.csv](source-migration-2-atomic.csv) 逐一列出 50 個原子 SHA。

31 個引用既有已 commit 原件；12 個登記固定政府來源；4 個使用 ledger 中既有確切 PDF 網址；3 個 ASX 統計來源登記但不啟用。只遷移驗收實際引用的來源。轉換程式留在 work，建置不讀取實驗總表、外部本機資料或 ledger 輸出。

## T2：身分與列集合

正式登記保留 99 個 entity，總表為對應的 92 個實驗專案加 Yttria 明確例外，共 93 列。原先列出的 7 個正式獨有項目中，Yttria 依 T2 保留，其餘 6 個 scope/prospect 排除，逐筆見 [excluded-formal-scopes.csv](excluded-formal-scopes.csv)。未新增 same_project relation。Yttria 的總說明標示 `POSSIBLE_DUPLICATE_SAME_MRE_UNRESOLVED` 與共用 MRE 不得加總。

4 個 Charley Creek 已用登記的政府歷史原件恢復來源宣告，實際取得與文字驗證仍依本次 receipts；不是現行礦權延續或資源核准。見 [charley-identity-migration.csv](charley-identity-migration.csv)。

## T3：宣告

新增 10 個個別氧化物 variable，157 筆元素宣告原值/原單位/頁碼/兩個以上 markers 保留；另將一筆 Dubbo 已存在的同來源 Y2O3 補入審查資訊，沒有重複新增觀測。Ce2O3 保留原物種與原單位，僅在逐格核准規則中轉換。

文字屬性轉換 350 筆，未轉換 87 筆。原因：{"MISSING_PAGE_OR_TWO_REVIEWED_MARKERS": 86, "COLUMN_NOT_IN_APPROVED_ATTRIBUTE_SCHEMA": 1}。只有核准的七欄可宣告；markers/SHA 或政府 feature 原欄位不符均進 review_queue，不填值。見 [element-declaration-migration.csv](element-declaration-migration.csv)、[attribute-declaration-migration.csv](attribute-declaration-migration.csv)。

## T4：既有模組規則

src 新增與刪除合計 **1780 行 / 2,000 行**；未新增 src 模組。只新增三個 config，每個規則參數都有 source_file 與 source_key。研究者決策的 decided_by 空白不生效。

|實驗函式|既有模組|正式函式|
|---|---|---|
|project_summary.resource_bundle|census.py|summary_resource_bundle|
|project_summary.complete_sum|census.py|summary_complete_sum|
|project_summary.reported_magnet_group|census.py|summary_reported_magnet_group|
|numeric_presentation.token|census.py|summary_decimal_token|
|numeric_presentation.text|census.py|summary_decimal_text|
|stage_rules.classify_stage|census.py|summary_classify_stage|
|stage_rules.round2_stage_proposal|census.py|summary_stage_case|
|template_mapping.template_mapping_fills|census.py|summary_template_fills|
|scoped_oxide_exceptions._column|census.py|summary_native_column|
|round4_tenements.identifier_key|spatial.py|summary_identifier_key|
|round4_tenements.centroid|spatial.py|summary_tenement_centroid|
|round4_tenements.read_shapefile_zip|spatial.py|summary_read_shapefile_zip|
|round3_locations.assess_controls|spatial.py|summary_assess_controls|
|round5_ocr.parse_tsv|pdf_extract.py|summary_parse_tsv|
|round5_ocr.extract_hits|pdf_extract.py|summary_ocr_hits|
|round5_stage.priority|pdf_extract.py|summary_hit_priority|
|round5_stage.normalize|pdf_extract.py|summary_alias_normalize|
|round5_stage.alias_index|pdf_extract.py|summary_alias_index|
|round4_stage.source_assessment|pdf_extract.py|summary_source_assessment|
|round4_stage.aliases|pdf_extract.py|summary_stage_aliases|
|round4_stage.assess_hit|pdf_extract.py|summary_assess_hit|
|round5_stage.reassess_hit|pdf_extract.py|summary_review_hit|
|round3_annual.select_first_full|technical.py|summary_select_first_full|
|round2_annual_production.validate_candidate|technical.py|summary_annual_candidate|
|round2_annual_production._verify_cell|technical.py|summary_verify_annual_cell|
|model_annual_derivation.validate_model_annual_derivation|technical.py|summary_model_annual|
|asx_validation.annual_product_derivation|technical.py|summary_product_annual|

其餘適配函式將同 SHA/statement/scope/effective_date 的 canonical observations 與 attributes 接到上述函式。未搬入需要外部 review_ledger / asset_roots 的 asx_validation、reviewed_discovery、reviewed_metadata 分支；原件審查資訊已轉為宣告，每次建置重新驗證。未採用凍結人工 PASS 直接取代三點判斷的分支。

階段原生全文掃描、圖像頁的人工 render hash/關鍵詞版本核對，以及本機兩次一致 OCR 均保留；OCR 品質不足、缺 OCR 或缺原件會阻擋「證據不存在」推定。位置用原生 feature 或完整礦權聯集，並保留代表點、基準與日期限制。年產保留工程情境、產出物種、來源單位、第一完整階段及模型假設；不用 feed、回收率或 HM 資料冒充 TREO 產量。HM 以原始十進位 token 計算，不增加有效精度。

## T5–T6：同一個匯出與實際建置

`au-ree-v2 export-summary --database <db> --out <dir>` 以唯讀方式讀取已完成的 canonical run；`all` 也呼叫同一函式。每一格都有追溯列，每個空格都有允許的原因碼。兩層分母僅扣除 `NOT_APPLICABLE_NO_MRE`；來源缺失不冒稱沒有 MRE。

(a) [phase22-baseline](phase22-baseline/) 來自 Phase 22 snapshot lock 實際重建的資料庫。(b) 實際執行 `all --refresh --as-of 2026-11-13 --work work/clean`，開始時沒有該快取目錄；中途連線重設，之後大量 DNS 解析失敗，150/208 筆 NETWORK_ERROR（72.12%）。以非零退出，尚未建立正式資料庫，未匯出新版總表。不得把此診斷當作研究結果，待乾淨 CI 環境驗證。原件只留在 work，未 commit 新 PDF，未修改 data/manifest 或 Phase 19–22 凍結結果。

|host|來源筆數|SHA一致含既有原件|SHA變動|HOST_STOPPED|NETWORK_ERROR|原始HTTP/傳輸|
|---|---|---|---|---|---|---|
|announcements.asx.com.au|52|8|0|0|44|{"200": 2, "NETWORK_ERROR": 44}|
|api.investi.com.au|3|0|0|0|3|{"NETWORK_ERROR": 3}|
|asm-au.com|3|2|0|0|1|{"NETWORK_ERROR": 1}|
|assets.birdsoftware.io|1|0|0|0|1|{"NETWORK_ERROR": 1}|
|assets.ctfassets.net|1|1|0|0|0|{}|
|cdn-api.markitdigital.com|3|0|0|0|1|{"NETWORK_ERROR": 1}|
|cdn.financialreports.eu|2|1|0|0|1|{"NETWORK_ERROR": 1}|
|company-announcements.afr.com|6|0|0|0|6|{"NETWORK_ERROR": 6}|
|dasc.dmirs.wa.gov.au|1|0|0|0|1|{"NETWORK_ERROR": 1}|
|data-api.marketindex.com.au|2|2|0|0|0|{}|
|data.stategrowth.tas.gov.au|1|0|0|0|1|{"NETWORK_ERROR": 1}|
|dem-sdp.s3-ap-southeast-2.amazonaws.com|1|0|0|0|1|{"NETWORK_ERROR": 1}|
|geology.data.nt.gov.au|1|0|0|0|1|{"NETWORK_ERROR": 1}|
|geoscience.data.qld.gov.au|2|0|0|0|0|{"200": 16}|
|geoscience.nt.gov.au|5|0|0|0|5|{"NETWORK_ERROR": 5}|
|gsq-prod-ckan-horizon-public.s3.ap-southeast-2.amazonaws.com|5|0|0|4|0|{}|
|hermes-cdn.investorhub.com|10|4|0|0|4|{"NETWORK_ERROR": 4}|
|international.austrade.gov.au|2|1|0|0|1|{"NETWORK_ERROR": 1}|
|investornews.com|1|1|0|0|0|{}|
|investorpa.com|3|0|0|0|3|{"NETWORK_ERROR": 3}|
|majorprojects.planningportal.nsw.gov.au|1|0|0|0|1|{"NETWORK_ERROR": 1}|
|newswire.iguana2.com|1|0|0|0|1|{"NETWORK_ERROR": 1}|
|opendata.maps.vic.gov.au|2|0|0|0|2|{"NETWORK_ERROR": 2}|
|orbitresources.au|1|0|0|0|1|{"NETWORK_ERROR": 1}|
|public-gs.geoscience.nsw.gov.au|1|0|0|0|1|{"NETWORK_ERROR": 1}|
|public-services.slip.wa.gov.au|3|0|0|0|2|{"NETWORK_ERROR": 2}|
|raw.githubusercontent.com|2|2|0|0|0|{}|
|services.ga.gov.au|10|2|0|0|7|{"200": 91, "TIMEOUT": 1, "NETWORK_ERROR": 7}|
|services.sarig.sa.gov.au|2|2|0|0|0|{}|
|spatial-gis.information.qld.gov.au|5|0|0|0|5|{"NETWORK_ERROR": 5}|
|staff-web.automicgroup.com.au|1|0|0|0|1|{"NETWORK_ERROR": 1}|
|strike.nt.gov.au|1|0|0|0|1|{"NETWORK_ERROR": 1}|
|victorymetalsaustralia.com|1|1|0|0|0|{}|
|wamex.dmp.wa.gov.au|3|0|0|0|1|{"NETWORK_ERROR": 1}|
|wcsecure.weblink.com.au|10|2|0|0|8|{"200": 1, "NETWORK_ERROR": 8}|
|www.annualreports.com|1|1|0|0|0|{}|
|www.arultd.com|1|1|0|0|0|{}|
|www.aspecthuntley.com.au|1|0|0|0|0|{}|
|www.astronlimited.com.au|1|0|0|0|1|{"NETWORK_ERROR": 1}|
|www.asx.com.au|43|0|0|0|37|{"200": 3, "NETWORK_ERROR": 37}|
|www.devexresources.com.au|1|1|0|0|0|{}|
|www.gippslandcriticalminerals.com|2|0|0|0|0|{}|
|www.iluka.com|1|0|0|0|1|{"NETWORK_ERROR": 1}|
|www.industry.gov.au|1|0|0|0|1|{"NETWORK_ERROR": 1}|
|www.itechminerals.com.au|1|0|0|0|1|{"NETWORK_ERROR": 1}|
|www.londonstockexchange.com|2|1|0|0|1|{"NETWORK_ERROR": 1}|
|www.marketindex.com.au|1|0|0|0|1|{"NETWORK_ERROR": 1}|
|www.wa.gov.au|3|1|0|0|2|{"NETWORK_ERROR": 2}|

SHA 一致欄包含明確引用的既有原件與允許的同 SHA fallback，實際新抓成功及 fallback 的差別保留在 statuses；不能將其視為全部遠端新抓成功。HTTP 計數按原始 request attempts，包含一次允許的重試與成功 probe 沿用的原請求，詳見 [acquisition-by-host.json](acquisition-by-host.json)。

## T7：逐格驗收

驗收腳本只放 work，透過 git show 讀取實驗參考，完全不進 src 或 CI build。下表只計 2,101 個實驗非 ID 非空格；數值依實驗呈現位數比較，不自動修正 DIFFERENT。Phase22 與實驗的 SHA / locator 已逐格寫入 [cell_comparison_phase22.csv](cell_comparison_phase22.csv)；新版 cell_comparison.csv 因沒有有效資料庫尚未產出，遷移增量也尚未計算。完整表也列出雙方空白、FORMAL_ONLY 及 51 個 Yttria 結構差異格。

|資料|SAME|DIFFERENT|FORMAL_MISSING|
|---|---|---|---|
|phase22|454|51|1596|
|rebuild|未產出有效資料庫|不計數|不計數|

增量（新建置減 Phase22）：`"NOT_COMPUTED_INVALID_NETWORK"`。

|原因|Phase22|新建置|
|---|---|---|
|NO_SOURCE_VALUE|39|未計算|
|RULE_INPUT_MISSING|204|未計算|
|SOURCE_NOT_ACQUIRED|1353|未計算|

## 覆蓋率

|資料|列數|51欄已填/全格|51欄原始覆蓋率|T1已填/調整分母|T1|T2已填/調整分母|T2|
|---|---|---|---|---|---|---|---|
|phase22|93|611/4743|12.88%|186/510|36.47%|425/4083|10.41%|

實驗線 73.29%（2159/2946）僅在此當作研究背景對照，沒有作為正式建置輸入或完成門檻。各欄完整數據見兩份 coverage.json：

|欄位|Phase22已填/93|新建置已填/93|
|---|---|---|
|專案ID|93|未產出|
|開發商|25|未產出|
|未上市公司|0|未產出|
|專案名稱|33|未產出|
|所在地_中文|33|未產出|
|所在地_英文|33|未產出|
|國家|93|未產出|
|州省地區|33|未產出|
|緯度|23|未產出|
|經度|23|未產出|
|礦床型態代碼|18|未產出|
|礦床型態|18|未產出|
|開發階段代碼|9|未產出|
|開發階段類別|9|未產出|
|開發階段|9|未產出|
|礦石蘊藏量_Mt|10|未產出|
|TREO品位_pct|10|未產出|
|總TREO蘊藏量_kt|10|未產出|
|磁鐵稀土氧化物蘊藏量_kt|4|未產出|
|磁鐵稀土佔TREO_pct|4|未產出|
|NdPr蘊藏量_kt_需兩者皆公布|0|未產出|
|完整重稀土組合蘊藏量_kt_需8元素皆公布|0|未產出|
|預估年產TREO_t_per_year|2|未產出|
|預估年產NdPr_t_per_year|0|未產出|
|產品/產出|5|未產出|
|有TREO資源估計|10|未產出|
|有來源文件|28|未產出|
|資料來源名稱|33|未產出|
|資料來源URL|33|未產出|
|已公布元素數_共15項|0|未產出|
|已公布元素總和_kt|0|未產出|
|元素總和/TREO|0|未產出|
|總說明|10|未產出|
|四項磁性元素皆公布|0|未產出|
|磁性元素重算值_NdPrTbDy_kt|0|未產出|
|La2O3_氧化鑭_kt|0|未產出|
|CeO2_氧化鈰_kt|0|未產出|
|Pr6O11_氧化鐠_kt|0|未產出|
|Nd2O3_氧化釹_kt|0|未產出|
|Sm2O3_氧化釤_kt|0|未產出|
|Eu2O3_氧化銪_kt|0|未產出|
|Gd2O3_氧化釓_kt|0|未產出|
|Tb4O7_氧化鋱_kt|0|未產出|
|Dy2O3_氧化鏑_kt|0|未產出|
|Ho2O3_氧化鈥_kt|0|未產出|
|Er2O3_氧化鉺_kt|0|未產出|
|Tm2O3_氧化銩_kt|0|未產出|
|Yb2O3_氧化鐿_kt|0|未產出|
|Lu2O3_氧化鎦_kt|0|未產出|
|Y2O3_氧化釔_kt|0|未產出|
|ASX代碼|0|未產出|

## 測試、凍結重建與 CI

Python 379 項，errors=0、failures=0、skipped=0；XML 見 [unittest-final](unittest-final/)。報告核對另發現 columns 計數遮蔽逐欄覆蓋率，已改為 column_count，重新匯出並通過 15 項針對性驗證，見 [export-contract-followup-xml](export-contract-followup-xml/)。R 分析回歸通過，見 [R-tests.xml](R-tests.xml)；Windows 的 C.UTF-8 locale 設定警告保留在紀錄。最初全測試 379 項曾有兩項失敗：唯讀 SQLite URI 被測試檢查器誤讀，以及重複 Dubbo Y2O3 宣告；已修正，最初紀錄見 [unittest-first-attempt.log](unittest-first-attempt.log)。

Phase 20（8 檔）、Phase 21（64 檔）、Phase 22（64 檔）凍結重建均 MATCHED：數值容差 1e-12、身分與文字完全相符。見 [phase20-replay.json](phase20-replay.json)、[phase21-replay.json](phase21-replay.json)、[phase22-replay.json](phase22-replay.json)。驗證輸入 SHA 與 src 統計見 [validation-summary.json](validation-summary.json)。

CI 執行連結在 ci-validation.json（開 PR 後補入）；automated-build job 在乾淨 runner 從空 work 重新建置，檢查每格、來源原件與凍結歷史，並上傳 receipts 與總表。

## 研究者待決

- 3 個 ASX 統計來源是否啟用；目前停用。
- www.asx.com.au 非 PDF 或停止回應的後續政策；目前不繞過、不搜尋替代網址。
- DIFFERENT 格的研究判定；保留兩邊原件 SHA/locator，沒有為一致性改值。
- 來源尚缺、SHA 變動、markers/OCR/情境條件不足的格子持續列為未取得，不推定不存在或正式核准。
