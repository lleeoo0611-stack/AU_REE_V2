# Phase 22 × ASX 資源欄位複核

資料截日為 2026-11-13。逐格複核[上一版](../current-20261119/README.md)中 25 個專案的 452 個資源缺值。每個新增值綁定單一原件版本、資源估算、有效日期、範圍與材料基準。

## 採入欄位

| 專案與估算 | 採入欄位 | 核驗來源 |
|---|---|---|
| Sandy Mitchell，2026-09-22 全礦資源 | 磁鐵稀土氧化物 34.14789 kt，佔 TREO 26.47059% | 年報實體頁 6、55。同列 379.421 Mt、90 ppm MagREO、340 ppm TREO。以公告的四項氧化物合計定義換算。 |
| Mons Block 3 East，2025-10 推定資源 | NdPr 氧化物合計 0.75192 kt | 公告實體頁 7、14。同列 7.23 Mt、104 ppm NdPr。說明頁確認為氧化物合計。 |
| Wimmera WIM100，2026-01-29 資源 | 磁鐵稀土氧化物 104.5 kt | 公告實體頁 3、4。以同一估算的 25 Mt 重礦物與四項氧化物品位計算。 |

表列結果由公告數字換算，有效精度受公告原始位數限制。Sandy Mitchell 和 Mons 的合計只用於對應的合計欄。Wimmera 的 TREO 比例仍留空，因所選估算缺同基準的 TREO 分母。

## 續查原因

| 原因 | 格數 |
|---|---:|
| 所選估算中未驗得可填的輸入 | 300 |
| 需完整組分的合計或比例缺少組分 | 90 |
| 選用的歷史 HTML 缺可綁定到同一估算的靜態 PDF | 22 |
| 已找到的數值屬不同範圍或材料基準 | 15 |
| 原件只給合計，個別組分待查 | 10 |
| 所選估算缺同基準的原位 TREO 分母 | 5 |
| 氧化物口徑或化學型式待確認 | 3 |
| 同一估算的來源數值衝突 | 3 |

Mangaroon Yin 同一公告兩表的 NdPr 量分別為 89,900 與 89,300 t。Mount Ridley 的 Y₂O₃、Yb₂O₃ 品位和公告噸數超出原表的四捨五入範圍，Ce 欄也待確認化學型式。Lyons 12&13 的 NdPr 欄待確認氧化物口徑。Mt Weld 的部分元素數值來自礦石儲量或分區，無法直接配對到選用的全礦資源估算。其餘逐格原因、缺少的組分及所選估算收在複核表。

## 驗收

- Census 維持 93 個專案與 51 欄。有值格由 2,233 增至 2,237，空白格剩 2,506。452 個待查資源格補 4 格，剩 448 格。
- v9 的 609 個保護格全數通過。固定 2,101 格對照中，2,032 格相同、6 格空白、63 格有內容或結構差異。
- 16 份 MCDA 排名與上一版逐位元一致。六構面保留 5 案。
- 來源覆疊階段通過 115 筆額外來源的版本與時間驗證。另有 2 筆來源因截日排除。
- SQLite 結構符合 Phase 22，完整性檢查通過，外鍵違規為 0。Phase 22 的 64 個凍結檔通過重播比對。本次程式的 504 個案例通過測試及複驗，補上館藏日期後重跑的 144 個相關案例全數通過。

## 單一流程

`au-ree-v2 all` 先驗證來源位元組、宣告版本及截日，再將合格證據送入既有 SQLite。對已凍結的來源鍵沿用 Phase 22 原件。文件以可核對的發布日判定，其他來源以可用日判定。Census 完成後依既有條件篩選，再執行 MCDA。

Charley Creek South 的兩個既有階段欄使用北領地 GEMIS 的同版報告。官方 `dc.date.available` 為 2026-02-26，本機取得日為 2026-11-17。已核對此館藏檔與本機 PDF 的 SHA-256。日期證據與指定版本一併記在來源登錄。 [GEMIS 館藏 1/94489](https://geoscience.nt.gov.au/web/handle/1/94489) · [官方時間紀錄](https://geoscience.nt.gov.au/gemis/server/api/core/items/747e363a-ffa4-431a-8ea8-0d8d583dd074)

本機可從先前驗證的靜態來源套件重播。本次用 Tesseract 處理需要 OCR 的頁面，並用 R 執行現有 MCDA 方法。

```sh
au-ree-v2 all --source-mode offline --as-of 2026-11-13 \
  --source-replay work/resource-date-proof/source_acquisition.json \
  --replay-assets work/phase22-census-replay-bundle/assets \
  --work work/census-resource-repair-final
```

- [Census CSV](REE%20project%20census.csv) · [452 格複核表](resource_gap_review.csv) · [全表差異](coverage_delta.csv)
- [來源版本與截日](source_selection.csv) · [資源估算觀測](resource_statement_observations.csv) · [逐格證據](field_provenance.csv)
- [MCDA 排名](MCDA) · [MCDA 準則證據](mcda_criterion_lineage.csv) · [驗收紀錄](verification.json)
