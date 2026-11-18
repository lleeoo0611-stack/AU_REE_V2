# Census 封存索引

[現行總表與執行方式](../../ree-project-census/README.md)

| 封存版本 | 原交付提交 | 93 列 × 51 欄非空格 | 2,101 格基準相同 |
|---|---|---:|---:|
| [初次整合本機重播](local-ocr-20261118/verification.json) | `043d078` | 1,135 | 946 |
| [靜態 PDF 擴充](local-static-pdfs-20261118/verification.json) | `201a32d` | 1,406 | 1,231 |

封存移動保留總表、逐格追溯、缺值原因、排序及驗收資料的原始位元組。重現歷史結果請從原交付提交使用當時的程式與來源收據。

初次整合版使用 `work/verified-asx-replay.json` 與 `work/replay-assets/`。靜態 PDF 擴充版使用 `work/static-run-final/source_acquisition.json` 與收據指向的原件，該版本新增 51 筆驗證過的 PDF 來源，其中 40 筆原登錄於 ASX 主站。Southern Cross 的 GCX 年報實體第 55 頁也在該版完成整頁複核。
