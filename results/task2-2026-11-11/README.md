# 任務 2：政府座標

新增 0 格。未核准時零網路請求，projection/ 六份基線檔逐位元一致。

只接受同州、確定名稱、唯一官方礦點；位置為代表點，非資源邊界。QLD 僅採 GDA94 屬性對，不混用 EPSG3857 geometry。NT 僅欄位報告，SA projects 僅輔助連結。VIC／TAS 無文件端點，維持空白。

核准後數量尚未測得，不能估算為已補值。每次正式取得須明確傳 --acquire；離線重播使用 --acquisitions。

## 授權
- WA_MINEDEX：CC BY 4.0，https://catalogue.data.wa.gov.au/dataset/minedex-dmirs-001
- GA_OZMIN：CC BY 4.0，https://dev.ecat.ga.gov.au/geonetwork/srv/api/records/7fb71158-fc8b-4de6-af81-ae8afcaea1da
- SA_SARIG：CC BY 4.0，https://www.energymining.sa.gov.au/industry/geological-survey/products-and-services/map-viewers-databases-and-services/data-services
- QLD_MINOCC：CC BY 4.0，https://www.data.qld.gov.au/dataset/queensland-resource-web-map-service-json
- NSW_MINVIEW：CC BY 4.0，https://www.resources.nsw.gov.au/geological-survey/minview
- NT_STRIKE：CC BY 4.0，https://www.ntlis.nt.gov.au/metadata/export_data?metadata_id=FA9776DB9DFB9746E040CD9B2144298B&type=html
- SA_PROJECTS_MAJOR：CC BY 4.0，https://www.energymining.sa.gov.au/industry/geological-survey/products-and-services/map-viewers-databases-and-services/data-services
- SA_PROJECTS_DEVELOPING：CC BY 4.0，https://www.energymining.sa.gov.au/industry/geological-survey/products-and-services/map-viewers-databases-and-services/data-services

## 本次實測結果

全部資料集未核准，新增 0 格、變更 0 格、待審 58 列。總表仍為 1,985 格填值、2,944 格空白（總共 4,929 格）。尚未下載真實政府資料，核准後可新增的實際格數無法定量；測試中的合成資料只證明功能，絕不算作研究成果。

已執行兩次獨立離線任務投影，原始投影檔與基線逐位元一致。原始檔留在 work/，不提交。完整管線雙重重建由主整合流程另驗證，本報告不把投影複製冒稱完整重建。

33 個離線單元測試通過，詳見 tests.xml。提案決定檔尚需併入主決定檔，所有 decided_by 維持 null。

## 可驗證距離比較與確定別名

`--references <mapping.json>` 接受以專案 ID 為鍵的已審核位置對照。每筆必須包含 `source_path`、實際檔案的 `source_sha256`、`locator`、`reviewed_by`、`longitude`、`latitude`、`crs="EPSG:7844"` 與明示的正數 `max_distance_m`。來源雜湊、datum 或門檻缺失均拒絕；不推測門檻。CLI 比對與最後成對驗證器都重算距離，超距候選列入待審且不填值。有比較器時 provenance 記錄來源證據、距離及門檻；無比較器時明記 `NO_VERIFIED_DISTANCE_COMPARATOR`，不宣稱檢查過距離。

`--aliases <mapping.json>` 接受以專案 ID 為鍵的確定別名表，每筆必須含上述來源證據四欄及 `aliases` 字串陣列。僅正規化後的完全相等比對；沒有模糊比對自動晉升。別名證據亦寫入 provenance。這些對照檔的 SHA 會記在任務收據。

## 完整候選集合防篡改驗證

離線重播從每一份 SHA 驗證的原始 response 重建全部 feature，不信任 cache 選出的子集合。每頁必須與封存取得收據一致，dataset、layer、decision ID、完整 URL query、預定稀土商品 filter、排序鍵、從 0 開始的連續 offset 及固定 page size 全部核實。WFS 原始 total 必須一致；ArcGIS 須有原始終止旗標或空白終止頁。省略同名競爭候選、整頁、改 total/count、offset、filter 或 receipt scope 均拒絕，不得將子集合宣稱唯一。最後才做專案唯一匹配。正式快照的原始 response 與取得收據應一起納入受保護重建證據。

## 完整驗收

以task3正式輸出為基線，兩次獨立完整來源重建並重播既有Dubbo新增，四CSV與summary/audit逐位元相同，未核准輸出與前項六檔也逐位元相同。434項既有受影響回歸及353子案例全過；跨項新測試詳見integrated-tests.xml。決定檔雜湊已綁入core_rebuild_receipt.json，保護檢查及數字見acceptance.json。
