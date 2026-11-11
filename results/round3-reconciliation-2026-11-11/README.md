# 第三輪分支與 Iluka 核查

## 分支差異

核查時遠端 `experiment/asx-public-acquisition-20261109` 為 cde12ab；已完成的第三輪在本機 `experiment/round3-researcher-approved-20261111`，HEAD f2d657c。舊分支仍是53欄，不代表第三輪未執行。本次核查不重做任務0，不把既有29格再算一次。完整0–5輸出雜湊與測試收據已獨立檢查，詳見 baseline_verification.json。

## Iluka

見 `docs/ILUKA_WIM100_SOURCE_RECONCILIATION.md`。540 Mt是原件公布的bulk mineral resource，HM25 Mt；NdPr由同範圍HM氧化物比例計算。未報告bulk TREO品位／總量，故TREO旗標空白，不是「否」。第三輪兩層判定已把WIM100列為有已選MRE，共38／55案。

## 精度修正

本次新增可逆十進位呈現，不修改已凍結標準證據值或歷史報告。來源原始token計算的中央值若與浮點輸出僅差數ULP才修正；這不是重新估計資源量，也不聲稱額外量測有效位數。逐格原值與provenance保留於呈現追溯文件，新增格數0。

覆蓋率保持第三輪既有口徑：標準證據2170/4743（45.75%）、兩層2170/3038（71.43%）。展示表含總說明2204格，另列不得當新證據。

本輪發布／測試結果以旁附的精度重建收據與最終測試紀錄為準。原0–5收據不覆寫。

## 最終驗證

- 精度修正9個展示格，新增資料0格；NdPr由89.75000000000001呈現為89.75。
- 兩次獨立呈現重建逐位元一致，原發布的全部檔案位元可還原。
- 完整離線回歸1041 tests＋546 subtests通過；發布後35項精度與schema專項通過。
- 已在本第三輪工作樹更新current。舊原件全部嵌入current的numeric_presentation_original.json，未改原asx工作樹或凍結0–5成果。
- 重跑：先依numeric_presentation_original.json以round3_schema.unpack還原至全新目錄，再執行 `python tools/format_source_decimals.py --source <還原目錄> --out <另一全新目錄>`。發布收據內逐檔hash可核對。
- 正常推送第三輪分支，不強推、不合併原asx分支；推送結果以遠端最新commit為準。
