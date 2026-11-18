# Phase 22 × ASX Project Census

同一個 `au-ree-v2 all` 入口執行來源選入、證據驗證、SQLite 入庫、總表匯出、篩選與 MCDA。SQLite 結構、證據範圍、分數規則、情境權重和三方法 R 引擎沿用 Phase 22。總表保留 ASX 測試已定案的 51 欄，與 2026-11-16 HTML 的共用欄位與順序一致。

## 現行成果

來源截止日為 2026-11-13。技術揭露編碼沿用 Phase 22 的 2026-11-05 審查日。

- [REE Project Census CSV](evidence-repair-20261118/REE%20project%20census.csv) · [逐格差異](evidence-repair-20261118/coverage_delta.csv)
- [逐格追溯](evidence-repair-20261118/field_provenance.csv) · [缺值原因](evidence-repair-20261118/missing_fields.csv) · [覆蓋率](evidence-repair-20261118/coverage.json)
- [頁碼與標記](evidence-repair-20261118/page_bindings.csv) · [新資源觀測](evidence-repair-20261118/resource_bindings.csv) · [氧化物原件核驗](evidence-repair-20261118/oxide_basis_bindings.csv) · [Wolverine 資源類別](evidence-repair-20261118/wolverine_category.json)
- [官方代表點名稱綁定](evidence-repair-20261118/location_bindings.json) · [截止日前存檔收據](evidence-repair-20261118/location_replay_receipts.json)
- [Census 篩選](evidence-repair-20261118/census_selection.csv) · [MCDA 納入判定](evidence-repair-20261118/mcda_census_gate.csv) · [各面板排名](evidence-repair-20261118/MCDA)
- [驗收紀錄](evidence-repair-20261118/verification.json)

| 指標 | 上一版 | 本版 |
|---|---:|---:|
| Census 非空格（93 列 × 51 欄） | 1,528（32.22%） | 2,120（44.70%） |
| 第 9 版對照缺漏（2,101 格） | 688 | 114 |
| 第 9 版對照相同格 | 1,347 | 1,931 |
| 第 9 版對照有值但內容或結構不同 | 66 | 56 |

本版新增 592 格、更新 42 格，沒有已填格轉為空白。修復包含 22 個專案的 244 筆氧化物材料基準、112 處頁面標記、4 個靜態 PDF 版本及 11 組官方代表點。第 9 版原有 900 格相同值及 609 格保護值均全數保留。

剩餘 114 格中，60 格缺合格的規則輸入、50 格缺已審核的欄位值、4 格來源晚於截止日。上一版對照中標記為來源未取得的 21 格已全部解除。逐格對照沿用[第 9 版 CI](https://github.com/lleeoo0611-stack/AU_REE_V2/actions/runs/44170481863)的數值相等規則。

SQLite 結構、完整性與外鍵核對均通過。Phase 22 的 64 個凍結成果檔全數匹配，494 項 Python 測試全數通過。92 個 canonical Project 通過 Census 篩選，16 份 MCDA 排名檔與上一版逐位元相同，六構面維持 5 案。Wolverine 總表保留原件公布的 70.5 kt，排名驗證沿用 Phase 22 已綁定的 70.08 kt。

## 缺值修復與重播

本版保留原重播的 174 筆來源快照，並從本機收件庫選入 4 個有獨立 SHA 的 PDF 版本。已核對的靜態 SHA 只適用於離線入口。同一公告網址可以有不同的原件位元組，程式以各登錄鍵明示的 SHA 驗證本機版本。

座標部分重播兩份附有 2026-11-11 擷取收據的官方資料。六筆官方短名以專案 ID、圖徵 ID、州別和座標一同驗證，並明示綁定適用的 Census 名稱。代表點沿用既有地理規則與原件脈絡驗證。

原件頁碼與標記在既有證據閘門核驗。經移轉遺失的材料基準依 ASX 已審核的數值、單位、原件、日期與資源範圍逐筆復核。材料基準修復保留所選礦量與表列範圍。重礦物階段的品位在有明確原件證據時才換算，資源小計、不同礦床與總量依各聲明範圍使用。

缺值檔維持原有欄名與主要原因代碼。詳細內容按欄位附上相關的審查紀錄、資源聲明的驗證結果和階段掃描阻礙。MCDA 依同一次回放的總表篩選選取 canonical Project ID。同一聲明的礦量、品位、基準、日期和四捨五入區間相符時，容許區間內的公布值與計算值並存，排名沿用可核對的 Phase 22 凍結觀測。

保留 `work/census-evidence-release-20261118/source_acquisition.json` 及收據指向的原始檔案即可重播。Windows 環境請設定 `TESSERACT` 及 `TESSDATA_PREFIX` 指向使用中的 OCR 執行檔及英文語言資料。

```sh
au-ree-v2 all --as-of 2026-11-13 --source-replay work/census-evidence-release-20261118/source_acquisition.json --work work/census-replay
```

[歷史 Census 成果與重播紀錄](../archive/ree-project-census/README.md) · [Phase 22 凍結成果](../phase22-2026-11-06/README.md)
