# Census 封存索引

[現行總表與執行方式](../../ree-project-census/README.md)

| 封存版本 | 原交付提交 | 93 列 × 51 欄非空格 | 2,101 格基準相同 |
|---|---|---:|---:|
| [初次整合本機重播](local-ocr-20261118/verification.json) | `043d078` | 1,135 | 946 |
| [靜態 PDF 擴充](local-static-pdfs-20261118/verification.json) | `201a32d` | 1,406 | 1,231 |
| [頁面標記覆核](coverage-review-20261118/verification.json) | `598ae41` | 1,528 | 1,347 |
| [資源基準與原件修復](evidence-repair-20261118/verification.json) | `8259d91` | 2,120 | 1,931 |

封存移動保留總表、逐格追溯、缺值原因、排序及驗收資料的原始位元組。重現歷史結果請從原交付提交使用當時的程式與來源收據。

初次整合版使用 `work/verified-asx-replay.json` 與 `work/replay-assets/`。靜態 PDF 擴充版使用 `work/static-run-final/source_acquisition.json` 與收據指向的原件，該版本新增 51 筆驗證過的 PDF 來源，其中 40 筆原登錄於 ASX 主站。Southern Cross 的 GCX 年報實體第 55 頁也在該版完成整頁複核。

頁面標記覆核版重用同一份靜態 PDF 收據，查核 101 處頁面標記並補上 122 格。該版的來源、逐格差異和排名可由原交付提交及封存結果查閱。

資源基準與原件修復版重播靜態 PDF 及截止日前的官方存檔，恢復 244 筆氧化物觀測的材料基準並新增 592 格。
