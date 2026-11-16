# 第 4 版：核准標記、座標修正與 VIC 內容雜湊

基準 `09ace21`；分支 `feat/claims-locators-20261116`；[Draft PR #11](https://github.com/lleeoo0611-stack/AU_REE_V2/pull/11)，target `feat/same-sha-fallback-20261116`。維持 Draft，不 merge。研究者：賴力維，2026-11-17。

最終 CI 尚未啟動；資料與程式已完成並在本機測試，待推送後以該次 CI 驗收。

## 研究者核准與套用範圍

- 標記：18 筆原提案 Y、4 筆指定修訂後 Y、4 筆 N。全部 **22 筆 Y** 重新由正式建置快取中 SHA 一致的原件、同頁、既有 extract_page 文字層及 WHITESPACE_ONLY_V1 正規化核對成功；既有標記仍在頁上、新標記實際出現且非其子字串。失敗 0，寫入 22，N 未動 4。
- 行數：原上限 2,005 先停止後，研究者明確核准提高至 **2,074**；目前 src 累計增加刪除 **2,074／2,074**（基準 070df10）。沒有新增 src 模組，沒有用長行、分號或刪除安全檢查擠入上限。
- 官網替代：研究者接受 43 份全部 NOT_FOUND、0 筆可採用提案；不加任何 alternate_urls，並明確授權其餘實作與測試完成後進行一次最終 CI。
- 舊 43 筆 ASX 靜態網址提案 **作廢，0 筆寫入**；[作廢紀錄](asxpdf_proposals_revoked.json)為準。舊 asxpdf_alternate_proposal.csv 僅供歷史稽核，不可採用。

[核准標記 CSV](identity_marker_proposals_approved.csv) SHA256：`e9cd0936b891f3d9e5a3e90599e41486e0068420b21b095be05d12e54571d2c1`；提交訊息附此 SHA 與「研究者 2026-11-17 核准」。[逐筆套用收據](identity_marker_application.json)記錄來源 SHA、頁碼、宣告路徑及文字層方法。A 組加入 identity_declaration.page_markers；B 組 context_evidence 保留原 page、markers、SHA，另以 page_markers 保留舊標記並加入核准文字。所有既有頁碼、SHA、observations、attributes 不變；四筆 N 未另找新標記。

## 發行公司官網同 SHA 搜尋

[全部 43 份結果](same_sha_source_outcomes.csv)、[提案表](same_sha_alternate_proposal.csv)、[拒絕候選](same_sha_candidates_rejected.csv)、[請求與頁面審計](same_sha_official_search.json)。**同 SHA 提案 0、核准／寫入 0、NOT_FOUND 43、拒絕候選配對 10**；其中 SHA 不符的筆數依拒絕表原因逐列保留，不將一般存取失敗稱為 SHA 不符。

搜尋依既有 issuer 資訊、已登記 IR 索引與待確認公司網域，先以公司首頁上的發行公司名稱／ASX 代碼確認身分，再考慮官網公開 PDF。每家公司每輪最多 4 頁、每來源每輪最多 8 個候選，全部請求最多 400；補查沿用已停止主機、已用請求額度並優先公告／年報入口。共 **117 次 HTTP 嘗試**（含 robots 與轉向）；**任何 ASX 主機 0、第三方主機 0**。NOT_FOUND 表示本輪有限搜尋未找到，不代表全網不存在。

遵守既有 robots 保守規則、每 host 至少 3 秒、4xx／登入／CAPTCHA／同意頁停止，不送表單或 cookie；排除 ASX、第三方以及跨公司轉向。下載原件僅留忽略的 work，不進 repo。來源 url 與 alternate_urls 完全未變；evidence_policy.json 也未變。上述 ASX 請求為 **官網提案搜尋範圍**；正式 CI 沿用既有取得流程與停止規則，實際請求以其收據為準。

|NOT_FOUND 最後原因|來源數|
|---|---:|
|ValueError:ISSUER_OWNERSHIP_NOT_CONFIRMED_FROM_HOME_PAGE|1|
|HTTPError:HTTP Error 403: Forbidden|2|
|ValueError:CAPTCHA_OR_LOGIN|7|
|HTTPError:HTTP Error 429: Too Many Requests|8|
|ISSUER_HOST_STOPPED|2|
|URLError:<urlopen error [SSL: TLSV1_ALERT_INTERNAL_ERROR] tlsv1 alert internal error (_ssl.c:1032)>|1|
|NO_IDENTIFIED_ISSUER_OWNED_SITE_FROM_AVAILABLE_METADATA|7|
|ValueError:REDIRECT_DESTINATION_NOT_APPROVED|3|
|NO_PUBLIC_ISSUER_PDF_LINK|10|
|ALTERNATE_SHA_MISMATCH|2|

## 座標修正與 VIC 8 格

spatial.py 兩處幾何屬性改回 `.centroid`，函式 summary_tenement_centroid 名稱不變；這兩處修正本身無行數增長。新增 3 個幾何測試：相鄰多邊形聯集內中心、聯集中心在空隙時採最大礦權中心、C 形最大礦權中心仍在外時拒絕。

依既有函式、礦權集合與 25 公里規則，在內容雜湊宣告完成後再次運算原已取得的 VIC 新版快照。[逐格診斷](vic_coordinate_diagnostic.csv)、[運算與輸入紀錄](vic_coordinate_diagnostic.json)：8 格均算出；Wimmera（AU-ff758cad5beb276d327d）、Nowie（AU-176852ef1348ac10d154）共 4 格 accepted，與參考公布精度一致；Donald 約 26.8 公里、Cannie 約 31.6 公里，共 4 格超過 25 公里不採用，參考側原為空白，不補造。原始浮點值保留，沒有聲稱原始浮點完全相等。

此診斷不跳過身分／礦權原件證明閘門，也不等同正式總表已恢復；正式結果以本次 CI 為準。

## VIC 來源層級內容雜湊

**研究者 2026-11-17 核准改用內容雜湊**。僅來源 reviewed_source_31a205168b6ae647 宣告 JSON_DROP_TOP_LEVEL_KEYS_V1，hash_drop_keys 僅 timeStamp。解析成頂層 JSON 物件、只刪宣告鍵、UTF-8、鍵排序、固定分隔符號、拒絕非有限 JSON 數值後計算 SHA256；其他來源行為不變。

- 舊整檔 SHA：`31a205168b6ae64719924940dfa50e4899cf625ca9f90167dbdd3c452d433953`，保留於 sources.json.previous_source_sha256 及[核准收據](vic_content_hash_application.json)。
- 新宣告內容 SHA：`6547bf2c221ed8b58f37b40123bfa43465973f0478a1cca99b67e5ced6413885`。兩份不同原始 SHA 的既有回應，以及座標診斷所用快照，內容 SHA 全部一致。
- 原始位元組照存，檔名與 snapshot.sha256 仍使用原始 SHA。取得收據同時記錄 raw_sha256、content_sha256、hash_policy、hash_drop_keys；座標來源追溯仍指向原始 SHA。
- 非 JSON、頂層鍵不存在、無效政策／鍵清單皆拒絕；不回退原始 SHA、已提交快照或替代下載。要素屬性、幾何、陣列排序、巢狀 timeStamp 改動都影響內容 SHA。
- WA、其他來源與原件快照均未改。未提交任何下載原件。

原先行數停止時的 [預估紀錄](vic_content_hash_budget.json)與[未套用階段提案](vic_content_hash_unapplied.patch)保留為歷史；目前以核准收據與實際 src 為準，實作另補上禁止 committed-snapshot／alternate 跳過政策檢查及拒絕非有限 JSON 數值。

## 比較、守門與驗證

固定參考清單 609 格未重產，SHA256 仍為 `02acc91760c8774f7377d12f2a428d1a1d6b6fba6f1620237e267101cdb0ff4e`。原基準 [CI run 43900956815](https://github.com/lleeoo0611-stack/AU_REE_V2/actions/runs/43900956815)為 609／609。本輪不重跑實驗線、不找舊原件、不重建過去版本。

|分類（參考有值、非 ID 的 2,101 格）|09ace21|本次 CI|增減|
|---|---:|---:|---:|
|SAME|609|待 CI|待 CI|
|KNOWN_STRUCTURAL_DIFFERENCE|42|待 CI|待 CI|
|NUMERIC_TOLERANCE_SAME|1|待 CI|待 CI|
|DIFFERENT|27|待 CI|待 CI|
|FORMAL_MISSING|1422|待 CI|待 CI|

KNOWN_STRUCTURAL_DIFFERENCE、NUMERIC_TOLERANCE_SAME 各自列計，不計入 SAME。各件 SAME 增量、仍缺原因與距離 2,101 格的差距，待 CI 輸出逐格核對；不把核准標記數或診斷格數當作恢復格數。

本機 **422 項 Python 測試通過**，較基準新增 **14 項**（幾何 3、內容雜湊 11）；R 測試通過。內容雜湊測試涵蓋時間戳穩定、內容變動、原始檔與雙雜湊收據、未宣告來源行為、無效 JSON、缺鍵、不得用 committed snapshot 或 alternate 繞過政策，以及座標保留原始 SHA 追溯。[範圍驗證](v4_validation.json)。

src 相對 09ace21 的增加刪除如下；累計上限另依 070df10 計算：

```text
63	6	src/au_ree_v2/acquisition.py
13	2	src/au_ree_v2/spatial.py
```

Phase 20–22 的既有 MATCHED 證據保留；本輪的 CI 步驟結果會分別記錄，未執行或 skipped 不算通過。只推送一次不帶 skip 的程式／資料提交取得最終 CI；驗收報告後續提交使用 skip 標記。609 守門少一格立即停止；完成後等待審查，不 merge。
