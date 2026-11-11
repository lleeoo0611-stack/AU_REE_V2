# 核准後覆蓋與總說明更新（2026-11-11）

## 交付結果

總表維持 93 案、53 欄。依使用者確認，整欄移除「元素數據一致性檢查」，在相同位置改用「總說明」。59 案有可追溯的適用說明，其餘留白。總表與完整 provenance 見 presentation/；正式 current 採同一份輸出。舊說明與原始 trace 封存在 retired_consistency_trace.json，不會把「相關數值留白」的過期敘述與核准新數值一起呈現。

資料新增 **84 格**：開發階段 70 格、氧化物與相關資源欄 8 格、政府座標 6 格。Splinter 另有 2 格經明確核准的既有數值更新（元素數 14→15、元素總和）。其他既有資料及 provenance 保留。retained_data_changes.csv 列出這 86 個資料變動；new_cells.csv／changed_cells.csv 是原 53 欄核心稽核，其中兩個一致性文字更新已納入新總說明，不是額外數據。

## 覆蓋口徑分開計算

- 原 53 欄證據口徑：1,985→2,069／4,929，40.27%→41.98%；新增 84 格。
- 保留的 52 個資料欄：1,960→2,044／4,836，更新後 42.27%。
- 最終 53 欄呈現表：2,103／4,929，42.67%，空白 2,826。
- 原說明有值 25 格，新總說明 59 格，淨增加的 34 格僅為敘述整理，不是新研究證據。不得把整張呈現表淨增加的 118 格說成資料新增。
- 原核心依既有結構空白排除規則：2,069／4,806，43.05%。規則與分母未改。

詳見 coverage_comparison.json、presentation_receipt.json 及 summary.json 的 coverage_metrics。TREO 研究列由 36 增為 37；原核心該子集填值為 1,276／1,961。這些是研究列資料覆蓋，不是獨立礦產庫存完整率。

## 核准與來源限制

使用者明確核准階段規則、Splinter Ce₂O₃→CeO₂、Circle Valley 合計 NdPr、指定政府座標來源。正式記錄 15 項核准；Operating／退出仍待審，未列入核准的兩個 SA project 輔助圖層未啟用。礦床分類 codebook 未因此全面核准。

Splinter 以係數 1.0487434078036981 換算，CeO₂ 為 9.513207035587959 kt，換算後 TREO 為 24.570698035587956 kt；來源有效位數閉合檢查通過。Circle Valley 接受同列來源的合計 NdPr 21.56 kt，不拆成個別 Nd、Pr，不虛增元素數。階段分類只對應來源揭露時點，不代表目前營運、法律或許可狀態。

WA 415、QLD 19、NSW 79、GA 472 筆完整官方候選中，僅 Splinter、Bencubbin REE Project、Hines Hill REE Project 通過唯一同州同名匹配，共補 6 個緯經度格。55 研究列仍待審。NT 僅欄位報告；SA 原端點 HTTP 400，未猜補。NSW／GA 的 WFS 篩選函式錯誤已於同端點更正；全部失敗及成功收據保留。共 10 次 HTTP 請求，來源重建與快照重播皆離線。

政府座標為官方代表點，不是資源或礦權邊界；沒有已審核距離比較器，限制 NO_VERIFIED_DISTANCE_COMPARATOR 保留於總說明及 provenance。資料集日期不是 MRE 日期。公開原始回應、完整分頁檢驗、SHA、授權及重播入口見 government/，雙重重播結果見 government-replay/。

## 重建與驗收

兩次獨立完整來源重建，分別重播原 Dubbo 驗證補值及相同凍結政府快照；最終六檔逐位元一致。再獨立轉換兩次總說明呈現，全部七檔逐位元一致。其餘 52 欄逐格與 provenance 相同。新版 audit 可由封存欄位與順序重建原主表、provenance、missing CSV，逐份比對原核心 SHA，不只比對填值數。

重建核心：先用 tools/rebuild_asx_census.py --census-root ../AU_REE_V2 --out-prefix <全新前綴>，再對 a/b 各用 tools/apply_archived_element_additions.py，最後以 tools/integrate_official_locations.py --decisions config/researcher_rule_decisions.json --acquisitions results/coverage-approved-2026-11-11/government/acquisitions.json 離線重播。不要加 --acquire。

呈現轉換：python -m au_ree_v2.presentation_notes --source <核准核心> --output <全新目錄>。不覆寫來源、不更改凍結歷史欄位配置。已核准核心逐格驗收見 approved_core_acceptance.json；呈現驗收見 presentation_receipt.json。最終回歸結果由 validation.json 與 release-offline-tests.xml 記錄。

## 保留事項

Census、凍結歷史結果、原有未提交工作均保留。source_consistency.csv 仍是原歷史證據，不冒稱本次重做。此更新不是新一輪全範圍搜尋或收斂宣告；既有 INCOMPLETE／CONTINUE 結論保留。

Yttria 與 Mt Stirling--Yttria 共用同一份 2024-04-16 礦床估計，不可直接加總；研究列覆蓋不等於獨立礦產庫存。

## 最終驗證結果

最終 current schema 的整個 repository 離線回歸：**878 tests＋532 subtests 全部通過，0失敗、0錯誤、0跳過**。原有18個未提交檔內容未改；Census及971個仍受保護檔雜湊不變。核准決定檔設定為 Git 保留原始 bytes，確保跨平台重播收據雜湊相同。
