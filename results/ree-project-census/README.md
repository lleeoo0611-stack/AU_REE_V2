# Phase 22 × ASX Project Census

整合基底為第 10 版提交 `6eeaeae`。Phase 22 的 SQLite 結構、證據範圍、分數規則、情境權重、三方法 R 引擎與凍結原件沿用原版。第 9 版乾淨 CI `44170481863` 的 2,101 格用於覆蓋比較。

來源擷取、原件與頁碼驗證、入庫、總表、篩選和 MCDA 都經過 `au-ree-v2 all`。有相同原件 SHA、日期、基準和資源數值的重複宣告，沿用能在當次 SQLite 驗到的 Phase 22 原始觀測 ID。若來源或數值不同，保留既有衝突處理。各面板按 Census 篩選後的 canonical Project ID，再檢查自身證據條件。

總表採 ASX 測試已定案的 51 欄。欄名與順序逐一對照 2026-11-16 HTML，歷史的年產重稀土及磁性稀土差額兩欄留在歷史檔。每個空白有原因，每個有值欄位有對應的追溯列。

本機重播以第 9 版收據中找得到且 SHA 相符的 123 筆來源為 ASX 輸入，包含該版選入的 102 份原始 PDF。第 9 版另有 10 筆登錄來源沒有找到同 SHA 檔案。本次重播來源截止日為 2026-11-13，技術揭露編碼依 Phase 22 的 2026-11-05 審查日重核原件。

## 驗收結果

- [REE Project Census](local-ocr-20261118/REE%20project%20census.csv) 包含 93 列、51 欄、1,135 個非空格。70 個 canonical Project 通過總表和身分篩選。
- [六構面排名](local-ocr-20261118/MCDA/six_domain/ranking.csv) 的 6 個 Project ID 與凍結 Phase 22 相符。共產出 16 個 MCDA 面板。全部矩陣與排名列均已和總表篩選及穩定 ID 核對。
- 依第 9 版的比較規則，2,101 格中有 946 格相同、1,080 格空白、75 格有值但存在內容或來源結構差異。原 900 格相同保留 898 格。609 格保護集保留 607 格。
- Southern Cross Li-REE Project — GCX 的「開發階段代碼」和「開發階段類別」留空。原件 SHA 以 `aeb46f66` 開頭，實體第 55 頁的本機 OCR 平均詞信心為 67.81888075，觸發既有低信心判定。
- SQLite 完整性與外鍵通過，結構與 Phase 22 相同。Phase 22 回放 64 個科學檔案匹配，489 項 Python 測試與 R 分析不變量通過。[驗收紀錄](local-ocr-20261118/verification.json)

第 10 版 [乾淨建置](https://github.com/lleeoo0611-stack/AU_REE_V2/actions/runs/44261812557) 與 [離線研究 CI](https://github.com/lleeoo0611-stack/AU_REE_V2/actions/runs/44261812454) 均成功。上述逐格數字來自新分支的本機重播。新分支的線上試跑已保存探測及部分擷取收據，這一輪的交付驗收採本機重播。

## 本機重播

保留此工作樹的 `work/verified-asx-replay.json`、`work/replay-assets/` 和原有 Git 快照即可重播。Windows OCR 補驗使用 UB Mannheim 的 Tesseract 5.4.0 可攜檔與專案封存的英文語言資料。

```sh
au-ree-v2 all --as-of 2026-11-13 --source-replay work/verified-asx-replay.json --work work/census-replay
```

指定本機 `TESSERACT` 與 `TESSDATA_PREFIX` 可重播掃描頁檢查。線上重抓使用 `all --refresh` 和同一個後續流程。原件無法取得、檔案改版、截日較晚與未核對定位均列在追溯資料。
