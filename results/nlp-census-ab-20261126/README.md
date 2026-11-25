# 既有規則與 BM25 證據頁檢索的配對實驗

在固定的 39 個專案、90 格缺值中，加入 BM25 後，前五頁命中率由 **24／49（49.0%）升至 31／49（63.3%）**。新增的 7 個命中全是座標判讀頁。正式 Census 新增 **1 個礦床型態代碼**。兩組都用 Phase 22 的同一個離線入口、截日 2026-11-13、同一份來源收據及 3,034 格原始覆蓋率分母。[前版基準](../ree-project-census/coverage-locked-20261125/README.md) · [本次 Census](../ree-project-census/nlp-retrieval-20261126/REE%20project%20census.csv)

## 同一批問題的差異

58 格座標分成 29 個專案位置問題。20 格礦床描述或代碼分成 18 個問題，12 格開發階段代碼或類別分成 6 個問題。合計 53 題，對同一問題的成對欄位只查找一次。

| 證據頁指標 | 既有規則 | 既有規則加 BM25 |
|---|---:|---:|
| 座標，前五頁命中 | 5／28（17.9%） | 12／28（42.9%） |
| 礦床類型，前五頁命中 | 13／15（86.7%） | 13／15（86.7%） |
| 開發階段，前五頁命中 | 6／6（100%） | 6／6（100%） |
| 全部可評分問題，前五頁命中 | 24／49（49.0%） | 31／49（63.3%） |
| 全部可評分問題，第一頁命中 | 24／49（49.0%） | 24／49（49.0%） |
| 改以可評分欄位計算，前五頁命中 | 35／84（41.7%） | 49／84（58.3%） |
| 53 題合計送審頁次 | 29 | 265 |
| 去重後實際送審的原件頁 | 26 | 100 |
| 正式新增實值／原 90 格 | 0 | 1 |
| 複核判錯的新入庫格 | 0（無新增） | 0（新增 1 格） |
| 真人查核分鐘 | 未量測 | 未量測 |

「命中」要求同一原件指紋與相同實體頁碼。相關頁可以支持保留空白。Duke 礦床、Durack 座標及 West Arunta 礦床的已知參照全在隔離文件內；Southern Cross 礦床沒有已判定的參照頁。共排除 4 題、6 格於命中率分母，仍納入 90 格入庫驗收。以全部 53 題為分母的已知命中數為 24 與 31。參照標註並未窮盡每份文件的所有可用頁，因此也不能據此估計完整頁面精確率。[逐題命中](query_hits.csv) · [逐格命中](cell_hits.csv) · [機器可讀指標](retrieval_metrics.json)

A 組讀取既有 Census 規則為該專案、該欄位實際留下的來源頁碼，包括能解釋排除原因的頁面。B 組保留相同順序，將剩餘名額補到五頁。BM25 用專案名稱與欄位詞彙檢索已選入 PDF 的原生文字。兩組每題上限相同，但 B 多送審 236 頁次，因此本次結果能說明候選頁的發現能力，省時幅度須等待真人計時。每題若把 B 截到 A 實際返回的頁數，53 題的清單均完全一致。本試驗沒有另外測量在同樣多的新增頁次下，人工搜尋或其他排序法能找到多少頁。

## 實際採用及保留空白的原因

Perenjori 的既有規則找到 HRE 2025-06-13 公告第 1 頁，BM25 把同一份公告的第 13 頁排在第 2 名。JORC 地質說明將主要鈾靶與次要的稀土離子吸附黏土探勘模型分開；第 12 頁確認專案的三張礦權。沿用既有受限分類後，礦床型態代碼為 **iac**，證據層級為 **EXPLORATION_MODEL_ONLY**，保留 **IONIC_NOT_CONFIRMED**。兩組原本都命中第 1 頁，因此後來發現的第 13 頁改善了入庫結果，並未回寫預先固定的命中率標註。[分類候選逐頁複核](../../data/validation/nlp_classification_adjudication_20261126.json)

座標新增命中的專案為 Lake Campion、Cannie、iTech Eyre Peninsula、Merredin、Mt Craig、Charley Creek South 與 Ravensthorpe。新頁可以確認探勘或權屬範圍，但沒有提供符合規則的專案代表點。例如 Greater Brothers 的 15 張礦權均可匹配政府圖層，計算出的代表點卻落在聯集外。Aramac 的圖面只標示 Dunns Road 採樣網格。仍缺 58 格座標與 31 格分類。[座標候選逐頁複核](../../data/validation/nlp_coordinate_adjudication_20261126.json)

兩次獨立離線重跑分別產生 2,500／3,034（82.40%）與 2,501／3,034（82.43%），增加 0.033 個百分點。全表適用但缺值 527 格；原有不適用集合相同。兩組 SQLite 均通過完整性與外鍵檢查。16 組 MCDA 的 160 份實體輸出和原版的指紋均相同。生產程式保持 42 個模組、157 條內部引用、零循環。全套 Python 測試 615 項、針對性測試 36 項及五組 R 方法測試通過。[A/B 入庫及排名驗收](census_verification.json) · [設計驗算](design_audit.json)

## 留出與查核邊界

開發對照只用 Mt Weld 與 Browns Range 的 3 份原件。39 個目標專案全部留出；用內容指紋合併重複來源鍵，另外隔離 38 份涉及開發專案或發行人的文件。兩組共用 166 份留出 PDF、7,607 個實體頁，其中 7,597 頁有可搜尋的原生文字。凍結的檢索詞、查詢規則與兩份原件參照先於排名產生。這是本輪 NLP 開發的專案與報告家族留出。部分目標和證據原已用於歷次 Phase 22 查核，結果不可解讀為對歷史上從未審閱的新發行人的準確率。[預定方案](protocol.md) · [逐份文件分組](split.json) · [固定候選](predictions.json)

兩次模型審查分別建立參照、再複核隱去 A/B 組別及排序的候選聯集。此輪無獨立真人判讀；錯誤入庫計數限於本輪實際新增且逐頁複核的格。真人查核另提供互補的兩份私有題單，同一審查者對同一專案只看到一種條件，實際完成後才會寫入工時。計時器及本地頁面影像均獨立於 SQLite。[獨立查核與計時操作](HUMAN_REVIEW.md) · [本輪工時紀錄](human_timing.json)

## 重現

A 組的正式 Census 使用基準提交 `8b5ac86`；B 組的新增證據在 `ac870af`。兩者使用同一個含 715 份原件的套件。於對應提交各執行一次，分別指定新的工作與結果目錄：

```sh
au-ree-v2 all --source-mode offline --as-of 2026-11-13 --source-replay results/ree-project-census/coverage-locked-20261125/source_acquisition.json --replay-assets KIT/assets --tessdata data/ocr --work WORK_DIR --out results/ree-project-census/NEW_RELEASE_DIR
```

在包含本實驗工具的提交，可用下列指令重算候選、命中率與入庫驗收。評分只讀自己的凍結標註，檢索只讀前版來源決策、規則留下的頁碼和原件。空的工作目錄可避免覆蓋已交付的判讀成果。

```sh
python -m tools.nlp_census_experiment --release results/ree-project-census/coverage-locked-20261125 --assets KIT/assets --out work/ab-eval --cache work/ab-pages
python -m tools.score_nlp_page_retrieval --experiment work/ab-eval --references data/validation/nlp_coordinate_pages_20261126.json data/validation/nlp_classification_pages_20261126.json
python -m tools.verify_nlp_census_ab --baseline results/ree-project-census/coverage-locked-20261125 --rules-release A_RELEASE --rules-work A_WORK --nlp-release B_RELEASE --nlp-work B_WORK --experiment work/ab-eval --adjudications data/validation/nlp_coordinate_adjudication_20261126.json data/validation/nlp_classification_adjudication_20261126.json
```
