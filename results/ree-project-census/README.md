# Phase 22 × ASX Project Census

同一個 `au-ree-v2 all` 入口執行來源選入、證據驗證、SQLite 入庫、總表匯出、篩選與 MCDA。SQLite 結構、證據範圍、分數規則、情境權重和三方法 R 引擎沿用 Phase 22。總表保留 ASX 測試的 51 欄，與 2026-11-16 HTML 共用欄位及順序相符。

## 現行成果

2026-11-19 完成 Phase 22 × ASX 架構審核落地與離線重播。定稿補入 10 格，v9 剩 6 格空白。 [發布說明](current-20261119/README.md) · [Census CSV](current-20261119/REE%20project%20census.csv) · [驗收紀錄](current-20261119/verification.json)

## 2026-11-18 歷史成果

來源截止日為 2026-11-13。技術揭露編碼沿用 Phase 22 的 2026-11-05 審查日。

- [REE Project Census CSV](residual-repair-20261118/REE%20project%20census.csv) · [逐格差異](residual-repair-20261118/coverage_delta.csv)
- [逐格追溯](residual-repair-20261118/field_provenance.csv) · [全表缺值](residual-repair-20261118/missing_fields.csv) · [第 9 版基準剩餘缺值](residual-repair-20261118/v9_remaining_missing.csv)
- [頁面與身分核驗](residual-repair-20261118/page-proofs.json) · [公司證據](residual-repair-20261118/company-final-proofs.json) · [官方座標證據](residual-repair-20261118/coordinate-proofs.json) · [礦床分類證據](residual-repair-20261118/deposit-proofs.json)
- [Census 篩選](residual-repair-20261118/census_selection.csv) · [MCDA 納入判定](residual-repair-20261118/mcda_census_gate.csv) · [各面板排名](residual-repair-20261118/MCDA)
- [驗收紀錄](residual-repair-20261118/verification.json)

| 指標 | 上一版 | 本版 |
|---|---:|---:|
| Census 非空格（93 × 51） | 2,120（44.70%） | 2,223（46.87%） |
| 第 9 版對照缺漏（2,101 格） | 114 | 16 |
| 第 9 版對照相同格 | 1,931 | 2,026 |
| 第 9 版有值但內容或結構不同 | 56 | 59 |

本版新增 103 格並更新 4 格總說明，沒有已填格轉成空白。新增內容包含 67 格公司欄、9 組座標、兩筆研究預估年產量、3 個礦床型態代碼及 Ravensthorpe 的身分與來源欄。新增座標證據使 3 格原先與第 9 版相同的總說明改列為有值但內容不同，609 格保護值及第 9 版初始 900 格相同值均全數保留。

第 9 版剩餘 16 格缺漏分屬 Goschen Central 的 6 格整體礦石資源指標、Mount Ridley 的 4 格座標及礦床證據、Nowie 與 Wimmera 的 4 格截日後座標，以及 Nolans 和 Euston 的 2 格公司欄。

93 個 canonical Project 通過 Census 篩選，16 份 MCDA 排名檔與上一版逐位元相同，六構面維持 5 案。SQLite 結構、完整性及外鍵通過，Phase 22 的 64 個凍結成果檔全數相符，496 項 Python 測試全數通過。

## 證據與重播

這一批按實體頁碼和原文核對公司與階段證據，並獨立核對年產量表列數字、單位、產品形態及研究情境。Jupiter／Brothers 的公司宣告改綁相同 SHA 的原始報告。Ravensthorpe 用原件標題、礦權區域與申報公司重新驗證。公司代碼及上市狀態沿用可查驗的日期及申報關係。

西澳代表點綁定核對同一來源的專案名稱、官方名稱、圖徵 ID、州別與營運商。北領地用 2026-11-11 擷取的 GA 礦點存檔檢驗 NT STRIKE 的座標基準。礦床分類沿用原有核准規則與原件地質描述。標記 `IONIC_NOT_CONFIRMED` 保留在適用欄位的追溯資料中。

保留 `work/census-residual-final-20261118/source_acquisition.json` 及收據指向的原始檔即可重播。Windows 環境請設定 `TESSERACT` 與 `TESSDATA_PREFIX`。

```sh
au-ree-v2 all --as-of 2026-11-13 --source-replay work/census-residual-final-20261118/source_acquisition.json --work work/census-replay
```

[歷史 Census 成果與重播紀錄](../archive/ree-project-census/README.md) · [Phase 22 凍結成果](../phase22-2026-11-06/README.md)
