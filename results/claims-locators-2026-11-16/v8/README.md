# 第 8 版：404 不停止主機（B2）

基準 56bf4dc（程式 ed98e0d），研究者賴力維 2026-11-17 23:42 核准。沿用 feat/claims-locators-20261116、Draft PR #11，target feat/same-sha-fallback-20261116，不 merge。

只將 acquisition.py 一個條件改為資料請求 4xx 且非 404 才停止主機。404 仍拋錯、由原有流程處理快照備援或 UNAVAILABLE；403、429、410 等其他資料 4xx 仍停止。robots 403/404/410、817 行順序、快照分支、所有其他 src 不變。

src +1/-1，淨增 **0**；依歷來 git diff 070df10 的新增＋刪除算法，累計實測 **2,130／2,134**。替換原有行也計入增刪，故與提示詞預期 2,128 有 2 行差異；實體行數未增加，仍低於核准上限。[範圍核對](preflight.json)。

新增 **4** 項本機 HTTP 測試；26 項相關測試、完整 **452 項 Python 與 R 通過**。涵蓋 404 後續來源仍請求、替代候選續行、無快照 UNAVAILABLE、有同 SHA 快照備援及第 7 版兩次 404 後 Lyons／ACDC 可取得；既有測試改為守住其他 4xx 停止規則。

第 7 版 claims、係數、推導宣告完全不動；sources、VIC 快照、截日、609 清單不動。VIC 8 格 SOURCE_AFTER_CUTOFF 是研究者接受的已知限制。

等待唯一一次 CI。609 少一格，或任何主機因 404 停止，即停下回報、不改值、不重跑。比較使用 ac65aaf 的第 6 版 CI，所有分類分開，NUMERIC_TOLERANCE_SAME 不算 SAME。CI 完成後補正式 15 氧化物、總說明、逐格增減與主機停止收據。
