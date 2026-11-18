# Phase 22 × ASX Project Census

同一個 `au-ree-v2 all` 入口執行來源選入、證據驗證、SQLite 入庫、總表匯出、篩選與 MCDA。SQLite 結構、證據範圍、分數規則、情境權重和三方法 R 引擎沿用 Phase 22。總表保留 ASX 測試已定案的 51 欄，欄名與順序對照 2026-11-16 HTML。

## 現行成果

來源截止日為 2026-11-13。技術揭露編碼沿用 Phase 22 的 2026-11-05 審查日。

- [REE Project Census CSV](coverage-review-20261118/REE%20project%20census.csv)
- [逐格新增與變更](coverage-review-20261118/coverage_delta.csv)、[頁面標記複核](coverage-review-20261118/page_bindings.csv)
- [逐格來源](coverage-review-20261118/field_provenance.csv)、[缺值原因](coverage-review-20261118/missing_fields.csv)
- [總表篩選紀錄](coverage-review-20261118/census_selection.csv)、[MCDA 納入判定](coverage-review-20261118/mcda_census_gate.csv)、[各面板排名](coverage-review-20261118/MCDA)
- [覆蓋率明細](coverage-review-20261118/coverage.json)、[驗收紀錄](coverage-review-20261118/verification.json)

| 指標 | 上一版靜態 PDF | 本版 |
|---|---:|---:|
| 總表非空格（93 列 × 51 欄） | 1,406（29.64%） | 1,528（32.22%） |
| 第 9 版比較基準相同格（2,101 格） | 1,231 | 1,347 |
| 第 9 版比較基準缺值格（2,101 格） | 809 | 688 |
| 第 9 版比較基準有值但內容或結構不同 | 61 | 66 |
| 通過 Census 身分與篩選條件的 canonical Project | 83 | 92 |

新增 122 格，沒有已填格轉成空白。增加最多的是 ASX 代碼（26）、有來源文件（10）、專案名稱、州省地區及中英文所在地（各 9）。原有值僅兩格更新，均屬 Mount Ridley 的來源資訊。專案的中央 Mia 礦床原始 ASX 公告通過身分核驗後，來源名稱和 URL 轉為指向該公告。

第 9 版原有的 900 格相同與 609 格保護集均全數保留。比較基準仍缺 688 格，其中 588 格缺合格的規則輸入、70 格為原件未揭露、21 格來源未取得、5 格沒有適用的 MRE、4 格來源晚於截止日。基準採用[第 9 版 CI](https://github.com/lleeoo0611-stack/AU_REE_V2/actions/runs/44170481863)的數值相等規則。

SQLite 結構與 Phase 22 相符，完整性和外鍵核對通過。Phase 22 凍結回放的 64 個成果檔全數匹配，490 項 Python 測試全數通過。本輪沿用 16 個 MCDA 面板，各面板排名檔與上一版相同，六構面維持 5 案。

## 靜態 PDF 複核與重播

本版重用上一版核對過的 174 筆來源快照，其中 153 份是 PDF。先比對原件 SHA-256、出版日及實體頁碼，再按 ASX 測試的方式核對同頁標記和專案脈絡。沿用同頁標記時，來源、頁碼與宣告必須一致。標記通過後仍交由原管線判定證據，總表篩選完才按各 MCDA 面板的證據條件納入。

保留 `work/static-run-final/source_acquisition.json` 和收據指向的原件，即可在本機重播。Windows 環境請將 `TESSERACT` 和 `TESSDATA_PREFIX` 指向原建置所用的本機 OCR 執行檔與英文語言資料。

```sh
au-ree-v2 all --as-of 2026-11-13 --source-replay work/static-run-final/source_acquisition.json --work work/census-coverage-replay
```

建立或擴充靜態庫時，可用 `--source-replay work/static-replay-basis.json --static-pdfs work/static-asx-library` 作為同一入口的來源參數。SHA、出版日、頁碼與標記仍由原管線核驗。相同原件 SHA、日期、基準和資源數值的重複宣告，沿用當次 SQLite 可核對的 Phase 22 原始觀測 ID。

[歷史 Census 成果與重播紀錄](../archive/ree-project-census/README.md) · [Phase 22 凍結成果](../phase22-2026-11-06/README.md)
