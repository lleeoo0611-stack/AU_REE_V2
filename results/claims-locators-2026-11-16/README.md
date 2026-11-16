# 第 3 版：ASX PDF 提案完成，等待核准；VIC 診斷受既有程式錯誤阻擋

**尚未寫入標記、替代網址或 SHA；尚未觸發新的 CI。** 沿用分支 `feat/claims-locators-20261116`、Draft PR #11，target `feat/same-sha-fallback-20261116`，不 merge。此次不找舊原件、不重建過去版本、不重跑實驗線、不重產參考清單。

基準仍為 9c067a5。原有 609 格已由 [CI run 43900956815](https://github.com/lleeoo0611-stack/AU_REE_V2/actions/runs/43900956815) 驗收為 609／609；[既有守門證據](ci_t0/ci_t0_summary.json)保留不變。本輪沒有已核准資料變更，因此新增 SAME 格數尚未驗收，不能把提案數當成恢復格數。

## 第一件：標記 CSV 尚無 approved

[identity_marker_proposals.csv](identity_marker_proposals.csv)目前仍沒有 approved 欄，依指示停止本項套用。原 26 筆提案原樣保留。審查建議中的 18 筆 Y、4 筆修訂後 Y、4 筆 N，均未被當成核准；本輪未自行填 Y，也沒有改頁碼、標記、SHA、observations 或 attributes。研究者審核後才套用 approved=Y，提交訊息附核准 CSV 原始位元組 SHA256。

## 第二件：新版宣告核對與 VIC 8 格診斷

claims.json 沒有直接引用這兩個來源的 key、SHA 或網址，故 [declared_value_check.csv](declared_value_check.csv)目前只有欄名。這不是全部一致。另將 sources.json 既有四組、8 個 VIC 礦權號獨立列入 [configured_tenement_check.csv](configured_tenement_check.csv)，使用既有型別與數字正規化規則核對新版：**8／8 找到，0 筆不符**；此項不等於座標、屬性或現行法律權利驗證。WA 沒有同類明確宣告範圍，未提出其 SHA 更新。

依研究者補充，直接呼叫既有 `summary_tenement_centroid`，以 9c067a5 已擷取的新版 VIC 要素計算四個專案的八格座標，僅供診斷。結果：**四案均出現 AttributeError，八格均未算出**。src/au_ree_v2/spatial.py 的 118、120 行讀取不存在的幾何屬性 `.summary_tenement_centroid`；目前 Shapely 2.1.2 提供的是 `.centroid`。函式名稱本身不需改。

已遵守 src 不改：沒有修改檔案，也沒有執行期 monkeypatch、另寫替代算法或略過驗證。[vic_coordinate_diagnostic.csv](vic_coordinate_diagnostic.csv)逐格列出錯誤；[診斷](vic_coordinate_diagnostic.json)與[程式問題](vic_centroid_code_issue.json)列出輸入 SHA、既有參數與兩個屬性位置，等待研究者決定。既有對照表中這八格只有四格有參考值，另四格為空；未補造參考值。

[sources_sha_update_proposal.json](sources_sha_update_proposal.json)目前 proposals 為空：不能以八個礦權號相符或零筆直接引用取代座標比對完成，也不能在計算失敗後提出「全部 match」的更新。

### VIC 連續兩次下載

使用既有 StrictTransport／SameSHAAlternates 的 robots、限速與停止規則，只對已登記的 VIC 查詢連續下載兩次，請求開始間隔 3.000473 秒。兩次皆 HTTP 200、13 個要素。

|次數|SHA256|
|---|---|
|1|`b8b0c1d0d950e0461b6a6254e633152a2868e25956f062d78c14fd5958ce8e01`|
|2|`9b8be1ffd46c75f41d3a4142ee28925ea6389e38c287da23ce7ef30e8f59788f`|

**唯一 JSON 差異為 `$.timeStamp`**；要素屬性、幾何與排序相同。完整差異位置與時間值見 [vic_download_variability.csv](vic_download_variability.csv)，取得收據見 [vic_download_variability.json](vic_download_variability.json)。未改成內容雜湊，未更新來源 SHA。內容雜湊是否可採用仍由研究者決定。

## 第三件：43 筆同 SHA 靜態 ASX PDF 提案

[asxpdf_alternate_proposal.csv](asxpdf_alternate_proposal.csv)共 **43 筆、43 個 www.asx 來源**，每筆 receipt_sha256 都與 sources.json 的 declared_sha256 完全一致。只讀 asx_local_asset_roots.json 指定 work 根目錄中的既有下載收據；去重後共讀取 42 份 downloads.json，沒有讀 PDF、實驗線數值輸出、資料庫或搜尋結果頁。

|項目|本輪結果|
|---|---:|
|同 SHA 提案|43|
|SHA 不符收據配對|0|
|核准數|尚待核准|
|本輪網路請求|0|
|www.asx 頁面讀取|0|
|本輪 CI ALTERNATE_SAME_SHA|尚未執行|

提案只含 announcements.asx.com.au/asxpdf/ 的 HTTPS 靜態 PDF 網址。receipt_path 使用核准根目錄 ID＋相對路徑，不包含個人資料夾名稱或絕對路徑。[收據審計](asxpdf_receipt_audit.json)含原收據 SHA 與 JSON pointer；[不符表](asx_receipt_mismatches.csv)目前只有欄名、0 筆；[逐來源結果](asxpdf_source_outcomes.csv)列出所有 43 個來源。

**停止等待研究者核准這 43 筆提案。** 核准後才加 alternate_urls，保留原 url 與 SAME_SHA_ONLY；正式建置仍以既有流程實際下載、遵守 robots／4xx／限速並驗 SHA。收據相符不是本輪已取得原件或已恢復總表的聲明。

## 比較分類：相對容差另列

只在已發布的 9c067a5 對照表上增加數值欄位相對容差 1e-12 分類；沒有重建任何版本或改動值。1 格改列 NUMERIC_TOLERANCE_SAME，不算進 SAME。見 [numeric_tolerance_review.csv](numeric_tolerance_review.csv)、[分類審計](numeric_tolerance_audit.json)與[分類後完整表](cell_comparison_v3_classified.csv)。

|分類（固定 2,101 格）|9c067a5|本輪僅分類後|增減|
|---|---:|---:|---:|
|SAME|609|609|0|
|KNOWN_STRUCTURAL_DIFFERENCE|42|42|0|
|DIFFERENT|28|27|-1|
|NUMERIC_TOLERANCE_SAME|0|1|+1|
|FORMAL_MISSING|1,422|1,422|0|

上述數字沿用既有 CI 輸出，只改分類；尚未套用三項資料變更，沒有新的 CI 驗收或可歸因的 SAME 增量。既有 609 格參考清單完全不動。

## 本輪核對與下一個停止點

- src 增加／刪除均 0；claims.json、sources.json、其他 config、manifest 與原件快照未變更。輔助腳本與下載原件只在忽略的 work，沒有進 repo。
- 43 筆配對已獨立讀取收據 pointer 核對 SHA／URL；另以 4 個合成反例驗證外部主機偽裝、包裝網址內嵌連結、非 PDF 狀態、互相衝突的收據 SHA 均會被拒絕。發布檔案使用相對收據路徑。見 [v3_validation.json](v3_validation.json)。
- 舊的 CI 基準為 408 項 Python 測試及 R 通過，Phase 20–22 MATCHED；本輪未觸發新 CI，也不把舊結果當成套用後驗收。
- 等待：研究者核准標記 CSV（approved=Y/N）、核准 43 筆 ASX PDF 配對，並決定 VIC 既有程式錯誤如何處理。維持 src 不改時，該座標診斷無法繼續。
- 三項核准且可寫入後，才推一次不帶跳過標記的資料提交，以該次 CI 驗收 609 格與實際增量；少一格即停止。不 merge。

前一版的診斷與審查資料保留供稽核，但舊原件追查已由第 3 版取代，不再要求提供舊原件。
