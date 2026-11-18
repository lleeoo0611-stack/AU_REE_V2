# Phase 22 × ASX Project Census

整合基底為第 10 版提交 `6eeaeae`。Phase 22 的 SQLite 結構、證據範圍、分數規則、情境權重、三方法 R 引擎與凍結原件沿用原版。第 9 版乾淨 CI `44170481863` 的 2,101 格用於覆蓋比較。

來源擷取、原件與頁碼驗證、入庫、總表、篩選和 MCDA 都經過 `au-ree-v2 all`。有相同原件 SHA、日期、基準和資源數值的重複宣告，沿用能在當次 SQLite 驗到的 Phase 22 原始觀測 ID。若來源或數值不同，保留既有衝突處理。各面板按 Census 篩選後的 canonical Project ID，再檢查自身證據條件。

總表採 ASX 測試已定案的 51 欄。欄名與順序逐一對照 2026-11-16 HTML，歷史的年產重稀土及磁性稀土差額兩欄留在歷史檔。每個空白有原因，每個有值欄位有對應的追溯列。

本機重播以第 9 版收據中找得到且 SHA 相符的 123 筆來源為 ASX 輸入，包含該版選入的 102 份原始 PDF。第 9 版另有 10 筆登錄來源沒有找到同 SHA 檔案。本次重播來源截止日為 2026-11-13，技術揭露編碼依 Phase 22 的 2026-11-05 審查日重核原件。

## 驗收結果

- [封存總表](../archive/ree-project-census/local-ocr-20261118/REE%20project%20census.csv) 包含 93 列、51 欄、1,135 個非空格。70 個 canonical Project 通過總表和身分篩選。
- [封存六構面排名](../archive/ree-project-census/local-ocr-20261118/MCDA/six_domain/ranking.csv) 的 6 個 Project ID 與凍結 Phase 22 相符。共產出 16 個 MCDA 面板。全部矩陣與排名列均已和總表篩選及穩定 ID 核對。
- 依第 9 版的比較規則，2,101 格中有 946 格相同、1,080 格空白、75 格有值但存在內容或來源結構差異。原 900 格相同保留 898 格。609 格保護集保留 607 格。
- Southern Cross Li-REE Project — GCX 的「開發階段代碼」和「開發階段類別」留空。原件 SHA 以 `aeb46f66` 開頭，實體第 55 頁的本機 OCR 平均詞信心為 67.81888075，觸發既有低信心判定。
- SQLite 完整性與外鍵通過，結構與 Phase 22 相同。Phase 22 回放 64 個科學檔案匹配，489 項 Python 測試與 R 分析不變量通過。[封存驗收紀錄](../archive/ree-project-census/local-ocr-20261118/verification.json)

第 10 版 [乾淨建置](https://github.com/lleeoo0611-stack/AU_REE_V2/actions/runs/44261812557) 與 [離線研究 CI](https://github.com/lleeoo0611-stack/AU_REE_V2/actions/runs/44261812454) 均成功。上述逐格數字來自新分支的本機重播。新分支的線上試跑已保存探測及部分擷取收據，這一輪的交付驗收採本機重播。

## 原交付版的本機重播

提交 `043d078` 對應此處的原交付結果。保留此工作樹的 `work/verified-asx-replay.json`、`work/replay-assets/` 和原有 Git 快照即可在該版本重播。Windows OCR 補驗使用 UB Mannheim 的 Tesseract 5.4.0 可攜檔與專案封存的英文語言資料。

```sh
au-ree-v2 all --as-of 2026-11-13 --source-replay work/verified-asx-replay.json --work work/census-replay
```

指定本機 `TESSERACT` 與 `TESSDATA_PREFIX` 可重播掃描頁檢查。線上重抓使用 `all --refresh` 和同一個後續流程。原件無法取得、檔案改版、截日較晚與未核對定位均列在追溯資料。

## 靜態 ASX PDF 建置

由同一入口讀取本機 PDF。來源選入依既有登錄、SHA-256 和出版日期核對，後續頁碼、標記與資源範圍驗證照常執行。補入的原件保留在 `work/static-asx-library/`。

```sh
au-ree-v2 all --as-of 2026-11-13 --source-replay work/static-replay-basis.json --static-pdfs work/static-asx-library --work work/static-census-replay
```

`work/static-replay-basis.json` 沿用上次重播的原件清單，並反映澳洲稀土公司季度報告首頁驗證的 2026-10-30 出版日。新一輪取得收據是 `work/static-run-final/source_acquisition.json`，保持收據指向的原件即可重播這次的來源選入。

Southern Cross 的 GCX Metals 年報實體第 55 頁按既有整頁目視複核規則核對，記錄已綁定原件與渲染頁面的 SHA。若日後原件或渲染內容不符，該筆整頁複核會失效。

靜態建置選入 51 筆新增 PDF 來源，其中 40 筆的原登錄網址在 ASX 主站。本輪未執行網路擷取。總表為 93 列、51 欄、1,406 個非空格，較原交付版增加 271 格。Southern Cross 恢復為 `A1`／`探勘`。[靜態 PDF 總表](local-static-pdfs-20261118/REE%20project%20census.csv)

第 9 版 2,101 格中，1,231 格相同、809 格空白、61 格有值但存在內容或來源結構差異。原 900 格相同與 609 格保護集全數保留。68 項相關測試通過，Phase 22 凍結回放的 64 個科學成果檔全數匹配。[驗收紀錄](local-static-pdfs-20261118/verification.json)

83 個 canonical Project 通過總表和身分篩選，產出 16 個 MCDA 面板。六構面排名為 5 案。Cummins Range 的 2023 年聲明為 519.3 Mt、3,170 ppm，新增的 2024 年聲明為 524.3 Mt、3,120 ppm。證據選擇將各自的資源範圍留待核對，Cummins Range 目前暫缺六構面排名。[六構面排名](local-static-pdfs-20261118/MCDA/six_domain/ranking.csv)
