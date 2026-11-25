# 獨立證據頁盲評與人工查核時間

此輪先固定候選頁與分派，再由兩位真人獨立計時。協調者分別交付各自的 `packet.json` 與頁面影像。作答前請勿查閱公開預測、答案、評分結果、分派金鑰或另一位審查者的資料。檔數與內容有時能暗示組別，解讀時應保留這項限制。

每個專案的座標、礦床或階段問題對同一位審查者均分到同一組。另一位審查者看到相反組別。同一專案的成對座標只計時一次，逐欄留下判斷。候選頁可支持實值、顯示衝突，或提供不足以填值的背景。請記錄原件支持的內容及範圍。這些判斷保存在獨立檔案中，正式資料採用仍經 Phase 22 原有入口。

也可將[獨立審核腳本](../../tools/nlp_blind_review.py)、單一封包及對應影像交給審查者，在獨立目錄以 `python nlp_blind_review.py review` 執行下方相同參數。錄入與統計使用 Python 標準函式庫；僅從 PDF 預先產生影像時需要 PyMuPDF。

## 協調者準備

首次建立本地私有分派時，可執行下列命令。將 `PATH_TO_PREDICTIONS` 換成該次固定的 `predictions.json`。本輪已產生的兩份真實封包位於 `work/nlp-ab-human-20261126/reviewer-1/packet.json`、`work/nlp-ab-human-20261126/reviewer-2/packet.json`。下列命令使用另一個全新目錄建立新的隨機分派；重用已存在的本輪封包可保留原分派。

```sh
python -m tools.nlp_blind_review prepare --predictions PATH_TO_PREDICTIONS --out work/new-private-packets
```

程式以密碼學隨機種子分派。分派表及私有種子只留在 `coordinator/allocation.json`。請各自交付單一封包，分開執行查核。公開版保留盲評說明與去識別的統計。原始 PDF 來自既有 SHA 原件庫。下列以第一位為例，第二位需換成 `reviewer-2`、不同的審查者代碼、影像目錄與紀錄目錄。

```sh
python -m tools.nlp_blind_review render --packet work/nlp-ab-human-20261126/reviewer-1/packet.json --assets KIT/assets --out work/nlp-ab-reviewer-1-images
python -m tools.nlp_blind_review review --packet work/nlp-ab-human-20261126/reviewer-1/packet.json --reviewer R1 --session work/nlp-ab-reviewer-1-session --images work/nlp-ab-reviewer-1-images
```

準備影像只讀取清單內原件並核對 SHA-256 與實體頁碼。每位審查者在自己的終端機輸入 `human` 同意後開始。每案輸入 `start` 才顯示題目和頁面清單。閱讀完成後輸入 `stop`，再逐欄記錄判斷、數值、證據頁與理由。計時單位為秒，採用單調時鐘，區間為 `start` 至 `stop`，包括開頁和核對，排除製圖及後續輸入判斷。空佇列也須真人處理才有查核時間。開始前可用 `skip` 跳過，進行中可輸入 `incomplete` 結束未完成的工作。重新開啟同一個 session 不會重複計算已開始的案例。

## 彙整時間

```sh
python -m tools.nlp_blind_review report --allocation work/nlp-ab-human-20261126/coordinator/allocation.json --session work/nlp-ab-reviewer-1-session --session work/nlp-ab-reviewer-2-session
```

`rules` 表示既有規則，`rules_nlp` 表示既有規則加文字檢索。彙整會分列已完成、已跳過、未完成、未量測及兩組都完成的案例，並拒絕兩份封包使用相同審查者代碼；確認兩位審查者身分獨立是協調者的工作。每組完整查核的時間須待該組全數作答後才會產生。沒有真人 session 時可省略兩個 `--session`，結果的秒數及時間差會是 `null`。[本輪計時狀態](human_timing.json)
