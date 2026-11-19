# Phase 22 × ASX 資源缺值複核

以[前版 Census](../resource-review-448-20261119/README.md)的 414 個資源空白為母體，共 24 個專案，截日 2026-11-13。補入 46 格，368 格待證。新版 Census 共 93 個專案、51 欄，2,319 格有值。

## 補入欄位

| 專案 | 補入 | 依據 |
|---|---:|---|
| Sandy Mitchell | 21 | 原估算附表第 88–89 頁的 15 項元素 ppm 按化學式換算對應氧化物，並更新 NdPr、八項重稀土、磁性氧化物重算、四項公布標記及組成統計。原件的 TREO 不含釔，含釔合計與 TREO 的比率維持空白。 [Ark Mines 原公告](https://arkmines.com/wp-content/uploads/2026/09/2A1698314_AHK.pdf) |
| Dubbo | 18 | 同一 75.18 Mt Toongi 資源在第 69 頁全屬性表提供 14 項缺失氧化物。鉺合計欄有排字錯誤，兩個資源分類均列 0.011%，以分類噸數核算。補足 NdPr、八項重稀土、磁性氧化物重算及四項公布標記。 [ASX 原公告](https://announcements.asx.com.au/asxpdf/20250711/pdf/06lq7vsvvk6yms.pdf) |
| Wudinna | 4 | 靜態 PDF 第 15 頁影像表的總列為 149.92 Mt、470 ppm TREO、285 ppm 扣鈰。依同列計出 27.7352 kt CeO₂，連帶補入三個組成統計欄。 [Cobra 資源公告](https://investors.cobraplc.com/announcements/VQ0lGG-cobra-resources-plc-maiden-rare-earth-mineral-resource-estimate) |
| Mount Ridley | 3 | 第 6 頁的分區及全區質量表與第 22、53 頁化學型式交叉核驗。採入 CeO₂ 20.677 kt、Yb₂O₃ 2.010 kt，並補足八項重稀土合計。 [Mount Ridley 資源公告](https://www.marketindex.com.au/data-api/api/v1/announcements/XASX%3AMRD%3A6A1317610/pdf/inline/major-heavy-rare-earth-resource-at-mount-ridley-project) |

原件的磁性氧化物合計各自保留在來源報告欄。從逐項品位推得的合計另列於重算欄，兩欄可追溯各自的四捨五入及原表口徑。WIM100 的 476.25 kt 僅代表原位重礦物部分的 15 項氧化物，因此不套用到五個全礦分母相關欄位。 [Iluka 原公告](https://www.iluka.com/media/0o0novln/29jan26-wim100-mineral-resource-estimate-increase.pdf)

## 剩餘缺值與可採證據

| 原因 | 格數 | 補證條件 |
|---|---:|---|
| 同一估算未驗得個別欄值 | 261 | 取得標明估算版次、截限、範圍及材料基準的原件分項 |
| 合計或比例缺完整組分 | 79 | 取得欄位規定的全部組分，或同定義的原件合計 |
| 候選數值的資源範圍或材料基準不同 | 11 | 取得同一全礦估算的分項或原件明示可核的轉換依據 |
| 原件只公布合計，無法拆分 | 10 | 取得發行人公布的分項表或同範圍分類表 |
| 缺少同估算全礦 TREO 分母 | 5 | 取得涵蓋全礦的原位品位或資源量 |
| 元素合計包含釔，TREO 分母排除釔 | 1 | 取得同估算、同氧化物範圍的分母 |
| 氧化物化學型式未核實 | 1 | 取得原件註解、方法附錄或發行人更正 |

## 驗收與重播

- 16 份排名與上一版逐位元一致，名次異動為 0。六構面排名納入 5 案。
- v9 保護清單中 604 格與原參考值一致，2 格是前版已追加的總說明。Dubbo 有 3 格按同一估算的新分項重算，詳見 [組成統計差異](v9_verified_composition_changes.csv)。v9 對照仍有 6 格空白。
- SQLite 結構、完整性與外鍵檢查通過。Phase 22 凍結版 64 個檔案通過重播比對，510 項 Python 測試全數通過。

`au-ree-v2 all` 執行來源驗證、SQLite、Census、篩選及 MCDA。重播需要本次取得的完整來源收據及靜態檔案庫。跨環境時，可將收據所列的檔案以其 SHA-256 為無副檔名的檔名放入 `--replay-assets` 目錄。

```sh
au-ree-v2 all --source-mode offline --as-of 2026-11-13 \
  --source-replay work/census-resource-414-verified/source_acquisition.json \
  --replay-assets work/phase22-census-replay-bundle/assets \
  --work work/census-resource-414-replay
```

- [Census CSV](REE%20project%20census.csv) · [414 格處置表](resource_gap_disposition.csv) · [24 案原件複核](resource_case_review.csv)
- [逐格變動](coverage_delta.csv) · [欄位追溯](field_provenance.csv) · [資源觀測](resource_statement_observations.csv)
- [MCDA](MCDA) · [驗收紀錄](verification.json)
