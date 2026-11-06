# 預期成果試作 — 2026-11-06

研究來源固定於 `b5e2a73438e2f3aa9f4adc3ab0f6ff0f898f0fca`，使用 `results/phase22-2026-11-06/`，資料截止日為 2026-11-05。本次是探索性成果呈現；既有資料庫、Project ID、準則、權重、評分函數與正式 C1 核定均未修改。

## 實際產物

本次對話附件提供完整 HTML、Excel、27 張獨立 PNG/SVG 圖、CSV、GeoJSON、重建 Python 程式與固定版本輸入封存。大型展示檔與重建程式目前隨對話 ZIP 交付，未全部加入 Git；本分支保存唯讀輸入匯出 workflow、試作摘要與驗證紀錄。

| Proposal 預期成果 | 本次實作 |
|---|---|
| Australian REE Project Database | 33 canonical 群組的匯出視圖、22 個資源範圍案例；保留 ID、scope、來源 URL、SHA256 與缺值 |
| Project Distribution Map | 24 個具可選用代表點的群組，標出 6 個完整探索案例；9 個缺少選定座標的群組不臆測位置 |
| End-member Rankings | 3 情境 × 3 方法 × 6 案例＝54 個分數／名次；沿用既有 interval_mcda 以退化區間重算 |
| Monte Carlo Rank Distribution | 封存 108,000 筆逐次排名；3 情境、2 種擾動、1000 draws、3 方法、6 案例；重算 108 列摘要 |
| Preference Ternary | 端元權重凸組合，步長 1%，每方法 5151 格點；9 個頂點與原排名一致 |

Excel 含 12 個分頁，提供可編輯效用矩陣、情境權重及 18 筆公式驅動 SAW 重算。其他方法與 Monte Carlo 表為既有計算結果匯入；不宣稱所有模型均可直接在 Excel 中重算。

## 試作結果

- 資源、戰略兩端元在三方法中均由 Nolans 居首。開發端元的 SAW、PROMETHEE II 首位為 Nolans，TOPSIS 首位為 Goschen Area 1。
- SAW 與 PROMETHEE II 在全部 5151 個三角圖格點由 Nolans 居首。
- TOPSIS 中 Nolans 居首 5124 格點，Goschen Area 1 居首 27 格點，分別為 99.4758% 與 0.5242%。這是離散格點比例，不是精確面積、隨機抽樣機率或開發成功率。
- 三角圖只涵蓋三組情境權重的凸組合。Monte Carlo 的六準則 Dirichlet 抽樣可超出此凸組合，因此兩種結果不能直接視為矛盾。
- Aim C 另提供既有 SAW/PROMETHEE 準則貢獻；這是數學分解，並未完成外部地質關聯或因果驗證。

## 本次實際驗證

- 450 個匯出檔案 SHA256 全數吻合。
- 54 個端元分數：最大差 `5.551115123125783e-16`；名次差異 0。
- 108000 筆逐次分數與名次一致；18000 個方法／情境／draw 群組均有相同 6 個案例。
- 108 列摘要共 756 個數值重算一致；最大差 `2.6645352591003757e-15`。
- 三角圖 9 個方法／端元頂點一致。
- 36 組 SAW/PROMETHEE 準則貢獻加總與原分數一致。
- Excel 公式錯誤掃描 0；18 筆 SAW 公式與封存分數在浮點容差內一致。

以上不是原始 PDF 的獨立重編碼、全資料庫重建或全套研究流程測試重跑。

## 統計口徑與科學界線

正式 C1 admitted 仍為 0。六構面完整探索案例為 6；不可描述為全澳正式排名。點值覆蓋率使用 `disclosure_baseline.json` 與 `disclosure_scores.csv`，R1/S1/T1/D1/I4/C1 為 22/15/20/8/20/8。`project_domain_evidence.csv` 的廣義證據狀態與這個點值口徑不同，不能直接當成同一統計量。

Technical 是 `technical-disclosure-transparency-v1`（七項固定分母），不是技術能力或回收率。I4 僅表示港口代表點距離。Commercial 準則代碼 C1 與正式資格群組 C1 不同。Goschen 僅採 Area 1；Browns Range 僅採 Wolverine；Jupiter 採完整資源範圍而非礦山排程。所有資源均為原地資源，不是可回收產品。

## 遇到的問題

原 CI artifact 約 580 MB，超出連接器下載上限，因此新增唯讀、固定 commit 的精簡匯出。匯出 run：`42188440679`，artifact：`13488407975`，約 14.8 MB，包含 450 個檔案與逐檔 SHA256。GitHub artifact 保存期有限；對話交付 ZIP 另保留一份完整輸入封存，避免依賴臨時下載網址。

地圖有 9 個群組缺選定座標，保持缺值。試作也揭露廣義證據表與已選定評分點值的口徑差異；沒有修改原科學產物以強制兩者一致。
