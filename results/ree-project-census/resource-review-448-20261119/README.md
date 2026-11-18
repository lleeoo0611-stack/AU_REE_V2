# Phase 22 × ASX 資源缺值複核

以[前版 Census](../resource-repair-20261119/README.md)的 448 格空白為固定母體，逐格處理 25 個專案。截日維持 2026-11-13。本輪補入 34 格，414 格保留待證。Census 仍有 93 個專案、51 欄，全表已有 2,272 格有值。

## 採入結果

| 專案與選用範圍 | 補入格數 | 來源與計算 |
|---|---:|---|
| Jupiter 2026-10-12，同一 1,000 ppm TREO 截限 | 22 | 原始 PDF 第 19 頁 Table 8。將 160 Mt 指示及 1,500 Mt 推定的 15 項氧化物各以列內噸數和品位換算後相加，另更新合計與完整性欄。NdPr 合計 606.04 kt，15 項合計 2,759.44 kt。原發布全礦 1.7 Bt 依表列精度保留。 |
| Mt Clere Tower | 4 | 季報第 7 頁 101 Mt 總列。840 ppm TREO 與 517 ppm 扣鈰品位的差值，換算為 32.623 kt CeO₂，連帶產出三個組成統計欄。 |
| Narraburra | 4 | 年報第 94 頁 94.9 Mt 風化層全礦列。738.95 ppm 與 500.31 ppm 的差值，換算為 22.646936 kt CeO₂，連帶產出三個組成統計欄。 |
| Wudinna Boland＋Head | 1 | RNS 靜態 PDF 第 1、3 頁對照同版 HTML。用同一估算的 150 Mt 與 101 ppm 計算 NdPr 15.15 kt。 |
| Yangibana 100% JV 全資源 | 1 | 年報第 14 頁 Table 2 同列 29.93 Mt、0.32% Nd₂O₃+Pr₆O₁₁，換算 NdPr 95.776 kt。 |
| Mangaroon Yin 0.20% TREO 截限 | 1 | 原公告第 11、16 頁與後續發行人季報重列 NdPr 89,300 t。保留原公告首頁 89,900 t 的衝突紀錄。 |
| Mount Ridley Blocks 1、2 | 1 | 公告第 6 頁兩區 Y₂O₃ 各自通過品位與噸數的精度對帳，6,422 與 20,843 t 合計 27.265 kt。Yb₂O₃ 第二區仍有品位與噸數差異。 |

[Cobra 資源公告](https://investors.cobraplc.com/announcements/VQ0lGG-cobra-resources-plc-maiden-rare-earth-mineral-resource-estimate) · [Critica 原始資源公告](https://announcements.asx.com.au/asxpdf/20261012/pdf/07560pwzkdgsrg.pdf) · [Dreadnought 發行人季報重列](https://company-announcements.afr.com/asx/dre/cac17766-af8c-11f0-af0f-3eb0efcdc8e9.pdf)

## 保留空白的原因

| 原因 | 格數 |
|---|---:|
| 所選估算尚未驗得個別欄位輸入 | 287 |
| 合計或比例缺完整組分 | 88 |
| 候選數值屬不同範圍或材料基準 | 15 |
| 原件只公布合計 | 14 |
| 同估算全礦 TREO 分母未驗得 | 5 |
| 化學型式或氧化物口徑待確認 | 3 |
| 靜態附表影像的數值未通過核驗 | 1 |
| 同估算數值衝突仍待對帳 | 1 |

複核索引共掃描 177 份已核過 SHA-256 的靜態 PDF、8,759 個實體頁面。索引提供候選頁面，採用值另核對表列、分類、年月、截限及材料基準。每一格均有處置、原件版本、頁碼或下一個可採證據條件。原始文件的查找與選入仍透過既有來源流程。補充 PDF 僅在版號、資源範圍、日期、分類與原估算的數值一致時提供成分證據。

## 驗收

- v9 保護清單中 607 格維持完全相同，2 格是成分證據加入後自動追加的總說明。原說明保留在新文字中。v9 空白剩 6 格。
- 16 份排名與上一版逐位元一致，名次異動為 0。六構面維持 5 案。
- SQLite 完整性及外鍵檢查通過，資料結構符合 Phase 22。
- Phase 22 的 64 個凍結檔通過重播比對，147 項相關測試全數通過。

`au-ree-v2 all` 仍是來源、SQLite、Census 及 MCDA 的單一入口。本次以已核對的靜態原件及收據離線重播，資料時間與來源選入沿用前版。

```sh
au-ree-v2 all --source-mode offline --as-of 2026-11-13 \
  --source-replay work/resource-date-proof/source_acquisition.json \
  --replay-assets work/phase22-census-replay-bundle/assets \
  --work work/census-resource-448-final
```

- [Census CSV](REE%20project%20census.csv) · [448 格處置表](resource_gap_disposition.csv) · [25 案原件複核](resource_case_review.csv)
- [逐格變動](coverage_delta.csv) · [欄位追溯](field_provenance.csv) · [資源觀測](resource_statement_observations.csv)
- [MCDA](MCDA) · [驗收紀錄](verification.json)
