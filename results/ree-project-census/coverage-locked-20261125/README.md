# Phase 22 × ASX 的 Census 覆蓋率正規化測試

研究截日為 2026-11-13。以前版相同的 93 個專案、51 個欄位和 3,034 格原始適用分母逐格驗收。測試採用同一個離線入口，先核驗靜態原件及凍結來源，再由 SQLite 產生 Census 和篩選後的 MCDA。[前版基準](../gap173-20261122/README.md) · [本次總表](REE%20project%20census.csv) · [全表差異](coverage_delta.csv)

## 實際結果

實際新增 4 格，固定分母覆蓋率從 2,496／3,034（82.27%）升至 2,500／3,034（82.40%），增加 0.13 個百分點。原有實值全數保留，適用性變動 0 格。Franklyn 的既有總說明另更新代表點資訊。

| 專案 | 新值 | 可使用的範圍 |
|---|---|---|
| Franklyn | 緯度 −33.2772965、經度 139.4657582（GDA2020） | 政府報告第 17 頁與 iTech 公告第 2 頁連回南澳 MinDep 10098、SITE_NO 1982184。這是命名礦點的代表位置，原始水平精度為 50 公尺。採用 2026-11-03 凍結版本。 |
| Voyager | 礦床型態代碼 `iac` | 2023 年公開說明書第 55、205 頁涵蓋兩個礦權。分類對應發行人的探勘模型，離子吸附機制仍待驗證。 |
| Lyons 12 & 13 | NdPr 氧化物蘊藏量 1.035 kt | 同一推斷資源列的 0.69 Mt 乾礦量乘以 0.15% 合併品位。2024 年半年報連回該估算及鑽探公告，後者明列 Nd₂O₃＋Pr₆O₁₁。依原始輸入精度約 1.0 kt，個別氧化物仍留白。 |

對照每格的來源版本、實體頁、轉換方式與精度，可查 [欄位來源](field_provenance.csv)、[座標品質](spatial_point_quality.csv) 與[採用版本](source_selection.csv)。

## 缺值與排名

4,743 格中有值 2,500 格、不適用 1,715 格、適用但缺值 528 格。原分母仍包含歷次改判不適用的 6 格。缺值中，271 格缺所選資源估算的特定分項，79 格缺計算所需組分，38 格等待工程研究。其餘 140 格包括 58 格座標、32 格分類、17 格資源計量基準、14 格年產口徑、11 格產品、2 格公司證據與 6 格先前撤回值。[逐格缺值與重開條件](gap_review.csv)

16 組 MCDA 的入選樣本與 160 份 R 輸出均相同。SAW、TOPSIS、PROMETHEE II 合計比對 1,542 個名次、8,322 次兩兩排序，變動均為 0。

## 離線重建

本輪程式版本為 `0dff6beb5aca52e565c37289e3ab295737e76942`。來源套件包含 715 份按 SHA-256 命名的檔案。取得套件並安裝專案既有的 R、Tesseract 與英文模型後，在空工作目錄使用原入口。公開倉庫提供收據及原件指紋。[來源收據](source_acquisition.json) · [重播套件驗證](bundle_verification.json)

```sh
au-ree-v2 all --source-mode offline --as-of 2026-11-13 --source-replay results/ree-project-census/coverage-locked-20261125/source_acquisition.json --replay-assets KIT/assets --tessdata data/ocr --work work/replay-normalized-coverage
```

持有前版的 711 份原件時，也可使用前版收據與原件庫，並以 `--static-pdfs ADDITIONS` 提供本次四份註冊 PDF。兩種方式都經過同一來源驗證與相同的截日規則。模組相依圖逐邊比對為 42 個模組、157 條引用、0 個循環。[完整驗收](verification.json) · [Census 與各排名差異](research_comparison.json)
