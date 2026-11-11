# 已核准政府座標來源快照

2026-11-11 依核准取得公開官方資料，未取得 SA project helper 層。WA MINEDEX 415 筆、QLD MINOCC 19 筆、NSW MinView 79 筆、GA OZMIN 472 筆，共 985 筆完整候選；NT 僅 ZIP 與欄位報告，不填座標。

共 10 次 HTTP 請求。SA SARIG 官方既定端點回 HTTP 400，內容為 MyPIRSA 泛用維護／不存在頁，已停止且未猜替代端點。NSW、GA 初次回 HTTP 400，明示 CQL 無 UPPER 函式；於相同端點更正為原生 ILIKE 後各一次成功，未繞過任何存取限制。原始失敗及請求收據全部保留。

原始 response 以 SHA-256 命名，配對 .receipt.json 記錄完整 URL、取得時間、來源版本、資料集／圖層／決定 ID。acquisitions.json 使用 repo-relative paths，完整頁與分頁終止驗證後才匹配。manifest.json 列出公開快照及收據雜湊。沒有專有 PDF。

離線重播：python tools/integrate_official_locations.py --before <核准後核心輸出> --out <全新目錄> --decisions config/researcher_rule_decisions.json --acquisitions results/coverage-approved-2026-11-11/government/acquisitions.json

未提供已審核距離參照時，provenance 明記 NO_VERIFIED_DISTANCE_COMPARATOR；不宣稱檢查過距離，也不把官方代表點當資源範圍邊界。資料集更新／取得日期不是 MRE 生效日期。初評僅三案的成對座標通過確定匹配，正式新增值以核心後重播報告為準。

## 授權與出處
- WA_MINEDEX：CC BY 4.0，https://catalogue.data.wa.gov.au/dataset/minedex-dmirs-001
- SA_SARIG：CC BY 4.0，https://www.energymining.sa.gov.au/industry/geological-survey/products-and-services/map-viewers-databases-and-services/data-services
- QLD_MINOCC：CC BY 4.0，https://www.data.qld.gov.au/dataset/queensland-resource-web-map-service-json
- NSW_MINVIEW：CC BY 4.0，https://www.resources.nsw.gov.au/geological-survey/minview
- GA_OZMIN：CC BY 4.0，https://dev.ecat.ga.gov.au/geonetwork/srv/api/records/7fb71158-fc8b-4de6-af81-ae8afcaea1da
- NT_STRIKE：CC BY 4.0，https://www.ntlis.nt.gov.au/metadata/export_data?metadata_id=FA9776DB9DFB9746E040CD9B2144298B&type=html
