# P3：同 SHA 已取得但 review_queue 仍為 SOURCE_NOT_ACQUIRED

基準為第 8 版 CI，不重建過去版本、不改 src、claims 或任何來源。

## 來源與原因

queue 主要由 src/au_ree_v2/cli.py 的 strict_claims 產生：使用同次 strict_refresh 回傳的 snapshots 與同次 acquisition outcomes，以 source_key 做 by_key 查找。它先判斷 identity_source；身分來源未取得時，會把這個錯誤傳給每筆 observations／attributes，再以該觀測自己的 SHA 寫 issue。故 issue.source_sha 已取得，不代表缺的是這一份文件。沒有讀舊 manifest 來判定本輪取得狀態。

evidence.py 的 ingest_project_attributes 也會就 source_key 缺少寫相同原因；ingest_claims 對 required_source_keys 任一缺少會跳過整個專案。census.py 匯出的 missing_fields.details 則附整個專案的 review_queue，並不是此格的逐項因果證明。把同專案 queue 直接視為每格的唯一阻礙會高估可救回量。

## 52 格逐格診斷

52 格／11 個已取得 SHA 的範圍與附件一致。44 格的主要問題是另一份 identity_source 沒取得（包括 HOST_STOPPED、UNAVAILABLE、CONFLICTING_DECLARED_SOURCE_SHA 或已停用來源）；觀測自己的 SHA 已取得不會解除身分要求，仍不能直接採用。

Greater Brothers 的 jupiter_scoping2026 已驗 SHA，但 phase6_jupiter_brothers_page2 別名未取得，且在 required_source_keys 裡，導致全案跳過。未上市公司與 ASX 代碼兩格即使改用同 SHA 正式 key，還有 context_evidence 單一標記問題。其餘四格（礦床型態、三個階段欄位）的 WA 屬性已通過本輪頁面驗證，解除 key gate 後輸入可供原規則運算；這是只讀預估，不保證與參考 SAME、也不是 CI 驗收。

Jupiter 的 ASX 代碼同樣有別名與單標記 context；礦床型態代碼還需要另一份 5e88f8aaf0d5… 的 asx_document_03154309，本輪 HOST_STOPPED，不能用 ea4d6a… 代替。

[逐格表](p3_cells.csv)分為四格有可用輸入、三格仍卡 context、四十五格仍卡身分或其他原件。這不是 52 格都能靠更正 reason 恢復。

## 最小修正估計（本輪不套用）

兩個 Jupiter 專案可提資料提案：把使用 ea4d6a… 的 phase6_jupiter_brothers_page2 source_key，以及 Greater Brothers 對應 required_source_keys，改指本輪已驗證的 jupiter_scoping2026。SHA／頁碼／標記不改。此方案 **src 0 行**，但仍需研究者另核准 claims 變更，且上述 context 仍須兩個實際標記。本輪沒有寫入。

若僅改善診斷，讓 identity_error 的 issue 詳細紀錄實際缺少的身分 key／SHA，並讓 required_source_keys 缺少有專屬 issue，估計約 4–8 行 src；只修理由不會增加可用格。若改成通用的同 SHA alias 重用，必須另設 key/SHA/種類與變更來源防護，不能把它藏在 reason 修正裡；本輪不實作。
