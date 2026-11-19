# Phase 22 × ASX Census 缺值修復

本版 Census 維持 93 個專案、51 欄，截日 2026-11-13。前版的 732 格待補證中，本次填入 **95 格**，17 格改判不適用，620 格待補證。全表有值 2,414 格，空白 2,329 格，其中 1,709 格不適用。

[新版 Census](REE%20project%20census.csv) · [732 格逐格處置與補證條件](gap_disposition.csv) · [所有變動與來源](coverage_delta.csv) · [欄位證據](field_provenance.csv)

## 實際補入的欄位

| 欄位 | 原待補證中填入的格數 |
|---|---:|
| 開發階段 | 29 |
| 總說明 | 17 |
| 開發階段代碼 | 14 |
| 開發階段類別 | 14 |
| 預估年產TREO_t_per_year | 2 |
| 未上市公司 | 1 |
| 緯度 | 2 |
| 經度 | 2 |
| 產品/產出 | 6 |
| 礦床型態 | 6 |
| 預估年產NdPr_t_per_year | 1 |
| 礦床型態代碼 | 1 |

另有 0 格在上一版被判為不適用、本版取得值。原已有值的欄位共更新 14 格（總說明 14 格），可在逐格變動表以 `UPDATED` 篩選。原有值轉為空白共 0 格。

- Fingerboards 的 7,280 噸 TREO／年來自規劃重礦物精礦每年 280,000 噸 × 2.6%。發行人另列其中約 1,800 噸 NdPr 氧化物／年。兩筆均保留預估產量與精礦基準。[Austrade 專案頁，實體第 36 頁](https://international.austrade.gov.au/content/dam/austrade-assets/international/documents/reports/critical-minerals/australian-critical-minerals-prospectus-march-2026.pdf) · [開發商原件，實體第 5 頁](https://www.gippslandcriticalminerals.com/wp-content/uploads/2026/04/GCM-Jobs-Guide.pdf)
- Dubbo 的 1,097 噸／年是研究中全礦期平均的分離氧化物產品合計。已填的 1,037 噸／年 NdPr 維持原值。
- Donald 與 WIM100 代表點以政府原生圖徵及發行人資源圖比對，座標僅表示代表位置。Rankin Dome 的礦床描述保留不同岩性，Charley Creek 歷史探區保留勘探模型與範圍。[座標與用途](spatial_point_quality.csv)

## 剩餘缺值

| 待補證類型 | 格數 |
|---|---:|
| 資源估算 | 368 |
| 專案座標 | 86 |
| 預估年產 | 57 |
| 礦床型態 | 43 |
| 開發階段 | 28 |
| 產品 | 18 |
| 公司與上市資訊 | 12 |
| 總說明 | 8 |

17 格改判不適用中，14 格是勘探階段產品欄，3 格是原件明示未上市的開發商 ASX 代碼，涉及 Avonbank、Copi 和 Fingerboards。

每格的具體原因、對應原件與所需證據見[逐格處置表](gap_disposition.csv)。資源欄沿用同估算、日期、截限、地質範圍及材料基準的要求。Sandy Mitchell 的政府同名點落在所選資源圖範圍外，Mt Weld 的儲量成分表與本次原位資源範圍不同。公司欄保留原件對業主與合資方的區分，未上市開發商的 ASX 代碼保留空白並註明適用性。

## 排名與驗收

16 份 MCDA 排名中，16 份與上一版逐位元相同。六構面排名涵蓋 5 案。Phase 22 的 64 個凍結檔案重播比對通過，完整測試通過 515 項。[MCDA 排名](MCDA) · [資料庫、截日、排名與第 9 版核對](verification_core.json) · [格數驗收](gap_verification.json)

在第 9 版的 2,101 格實驗對照中，空白由 6 降至 4，仍缺 Nowie 與 Mount Ridley 各一對經緯度。WIM100 的官方代表點與實驗線的座標不同。Donald 的總說明新增座標限定，因此相同格由 2,022 變為 2,021。609 格保護清單中，604 格相同，原有 5 格差異持平。38 組已選資源估算均維持原版本與範圍。[第 9 版殘餘空白](v9_remaining_missing.csv) · [文字差異](v9_new_regressions.csv)

## 從同一入口重播

這份[來源收據](source_acquisition.json)固定了本版輸入。完整的本機來源庫已在忽略原始路徑的條件下核驗，共 660 個不同的原件與附檔，含 Phase 22 凍結來源。重播需具備相同位元組的原件及專案所需的 R 與 OCR 環境。來源庫檔名為 SHA-256，以下路徑可換為另一台電腦上的位置。

```sh
au-ree-v2 all --source-mode offline --as-of 2026-11-13 \
  --source-replay results/ree-project-census/evidence-repair-732-20261119/source_acquisition.json \
  --replay-assets work/phase22-census-replay-bundle/assets --work work/census-evidence-replay
```

來源選取採用原件日期的實際精度。2026 年 3 月版 Austrade 名錄取 3 月 31 日，西澳 2 月版文件取 2 月 28 日。NSW 地圖標示 2025 年 7 月的專案階段，其官方發行證據為 9 月。數值、來源與處置皆可依專案 ID 連接。[逐件來源選取](source_selection.csv)
