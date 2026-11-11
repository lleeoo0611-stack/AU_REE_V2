# 核准後政府座標：獨立離線重播

以已核准規則核心輸出（2,063 格填值）為基線，從封存完整官方快照兩次獨立重播，兩份輸出的四 CSV 與 summary／audit 逐位元一致。新增 6 格座標、未改任何既有非空值及 provenance；最終填值 2,069、空白 2,860。未更新 results/asx-current/。

新增案：Splinter、Bencubbin REE Project、Hines Hill REE Project，各一對 GDA2020 經緯度，來源皆 WA MINEDEX。55 列待審／無端點；不以湊格數放寬匹配。未提供已核實距離比較器，新增值的 provenance 明記 NO_VERIFIED_DISTANCE_COMPARATOR。位置只是政府礦點代表點，不是 MRE 範圍邊界。

完整候選共 985 筆：WA 415、QLD 19、NSW 79、GA 472。SA HTTP 400 維護／不存在泛用頁後停止；NT 僅 ZIP 欄位報告，不填座標。原始取得共 10 次 HTTP 請求，本次兩次重播均零網路請求。

公開原始快照、來源版本與取得收據、失敗證據、NT 欄位與 CC BY 4.0 授權歸屬均在 ../government/。本目錄不重複原始檔；replay_receipt.json 綁定決定檔、原始快照 manifest、acquisitions 及全部輸出 SHA。

重播入口：tools/integrate_official_locations.py，--before 指向核准核心、--decisions config/researcher_rule_decisions.json、--acquisitions results/coverage-approved-2026-11-11/government/acquisitions.json、--out 使用新目錄。檢查細節見 replay_receipt.json。

相關離線測試：36 passed、6 subtests；fixtures 僅測功能，實際新增數來自上述封存官方資料。
