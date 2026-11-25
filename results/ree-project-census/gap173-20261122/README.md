# Phase 22 × ASX 剩餘 173 格的第二輪查核

相對 [bed5213 的 Census](../gap189-20261122/README.md)，本輪實際補值 **28 格**，改判不適用 **1 格**，保留待補 **144 格**。研究截日為 2026-11-13。

| 全表指標 | 前版 | 本版 |
|---|---:|---:|
| 有值 | 2,468 | 2,496 |
| 不適用 | 1,714 | 1,715 |
| 適用但缺值 | 561 | 532 |
| 固定分母覆蓋率 | 81.34% | 82.27% |

兩版均為 93 筆專案列 × 51 欄。覆蓋率使用原本的 3,034 格；適用性調整的格仍保留在比較分母。[Census 總表](REE%20project%20census.csv) · [173 格逐格處置](followup_review.csv) · [全表前後差異](coverage_delta.csv)

另有 10 格既有「總說明」補記代表範圍及時間，未列入新增實值。

## 實際補入的座標

經緯度採 GDA2020，下表四捨五入至六位小數。最遠距離是代表點到該礦權範圍最遠頂點的距離。用途為標示該期探勘或交還範圍。[座標來源和精度](spatial_point_quality.csv)

| 專案 | 緯度 | 經度 | 最遠距離 | 代表範圍 |
|---|---:|---:|---:|---|
| Achilles | -26.780187 | 122.179168 | 12.94 公里 | 2025 年 7 月轉讓的兩張礦權。已核對 Windidda 鑽孔與減地後界線的關係。 |
| Barballin | -30.933325 | 118.082157 | 11.64 公里 | E70/6146 的歷史已授權範圍，2024 年交還。重建 42 個法定區塊。 |
| Charley Creek South-East | -23.380471 | 133.355139 | 21.35 公里 | URO 於 2024 年交還的 EL33006 西部範圍。政府公告 277/24，110 個法定區塊。 |
| Kenny | -31.952742 | 122.277363 | 12.03 公里 | 2025 年 7 月的 E63/1888，已反映先前部分減地，其後於 9 月交還。 |
| Mukinbudin | -30.720053 | 118.055337 | 22.62 公里 | 2026 年 9 月清冊所列的 E70/5939。 |
| New Goldfield | -15.817574 | 143.663273 | 12.61 公里 | EPM 26646 已授權、EPM 28913 申請中。依發行人完整清單取聯集。 |
| North Dam | -31.281736 | 121.418157 | 4.13 公里 | 截至 2026 年 9 月季報的 E15/1495、M15/1841 聯集。政府抽取的到期欄與狀態欄另見逐格註記。 |
| Peak Charles | -32.940643 | 121.505343 | 12.20 公里 | 2025 年度仍保留的 E63/2163，涵蓋 Gimli 稀土探勘範圍。 |
| Perenjori | -29.346455 | 116.472466 | 19.87 公里 | 2025 年 7 月政府封存與同時期發行人清單涵蓋的三張礦權。 |
| Rocky Gully | -34.549987 | 117.158344 | 6.51 公里 | 2026 年 9 月清冊的 E70/5037、E70/6140；同公司 Pingrup 屬另一案。 |

## 其他實值與不適用

| 專案 | 欄位 | 結果 |
|---|---|---|
| Barballin REE Project | 礦床型態代碼 | iac |
| Goschen — Area 1 resource scope | 預估年產TREO_t_per_year | 4900 |
| Greater Brothers | 礦床型態代碼 | iac |
| Mt Craig Copper–REE Exploration Project — Taruga | 礦床型態代碼 | iac |
| Ravensthorpe REE Exploration Project — Young River, Dalyup and Bremer | 礦床型態 | Ionic clay-hosted REE exploration model for the Ravensthorpe licences; historical drilling over and adjacent to the tenements indicates prospectivity |
| Ravensthorpe REE Exploration Project — Young River, Dalyup and Bremer | 礦床型態代碼 | iac |
| Splinter | ASX代碼 | 不適用 |
| Splinter | 未上市公司 | 是 |
| Wandagee REE Exploration Project — Consolidated Zinc | 礦床型態 | Kimberlite exploration target for potential REE mineralisation at Wandagee |

Ravensthorpe 與 Barballin 的黏土型代碼依發行人的勘探模型；Greater Brothers 與 Mt Craig 的鑽探支持各自已鑽範圍的黏土賦存。四者的證據均保留「離子吸附尚未證實」註記。Wandagee 的金伯利岩只是勘探目標，代碼維持待補。Goschen 採 DFS 對應的含氧化物年產，保留原件「約 4,900 噸／年」的精度。[逐格來源](field_provenance.csv)

## 剩餘缺值

本輪仍有 30 案、共 60 格座標待補。分類尚缺 21 格礦床描述或代碼，另有 6 案的開發階段代碼與類別合計 12 格。

| 類別 | 格數 | 主要重開條件 |
|---|---:|---|
| E2 | 22 | 缺相符的有版本代表圖徵，或已查圖形的範圍、狀態不合。取得與同案時點及完整礦權相符的圖徵後重開。 |
| E3 | 38 | 位置衝突、只涵蓋子區或鑽孔、礦權聯集超過 25 公里或代表點在界外。需可核實的專案代表位置。 |
| E4 | 33 | 需要可唯一映射的礦床模型、同範圍已完成的開發里程碑，或適用於該案的退出分類決策。 |
| D1 | 18 | 需要同一估算範圍、物料分母及氧化物定義，或可核實的完整質量衡算。 |
| E1 | 14 | 需要吻合產品、工程情境、年度期間及含量基準的產量。 |
| E5 | 2 | 缺同一法人、角色及當期上市身分的證明。 |
| E6 | 11 | 尚缺同案流程所產出稀土產品的原件。 |
| R | 6 | Viper、Southern Cross 的舊值已撤回；須有同案的里程碑或產品終點。 |

此外，350 格等待同一資源估算的分項或其必要上游輸入，38 格等待工程研究；這 388 格仍計入適用分母。[累計缺格台帳](gap_review.csv)

部分地點已有可核實的拒收數據。NT 的 EL33000 與 EL33004 分別為 36.25、26.73 公里；昆州 Gilberton 與 Aramac 分別為 25.52、28.71 公里；西澳 Munbinia 與 Diemals 分別為 34.30、43.78 公里。Wandagee 的形心在界外，Merredin 的原生授權日期與發行人申請狀態有衝突。[分案依據與來源版本](followup_review.csv)

## MCDA 與重播

16 個面板、SAW、TOPSIS、PROMETHEE II 三種方法均重新計算。兩版各 160 個實際輸入輸出檔案已重算雜湊，共 8,322 次兩兩排序比較，單項名次變動 0，兩兩排序變動 0。面板成員變動 0。六領域揭露面板有 5 案，正式 C1 經簽核的專案為 0 案。[面板逐項比較](research_comparison.json) · [獨立驗收](verification.json)

SQLite 完整性通過，外鍵違規 0 筆。591 項 Python 測試及 5 組 R 方法檢查通過。單一流程使用前版凍結收據，加上 23 份已驗證的靜態原件。可攜套件有 711 份原件與 801 筆引用，獨立重播的 235 筆版本及截日決策完全一致。政府 ZIP 的版本日期取自原 HTTP 回應的公開封存，原件以 SHA-256 核對。[來源收據](source_acquisition.json) · [原件逐檔校驗](asset_manifest.json) · [套件核對](bundle_verification.json)

本機持有重播原件時，可從專案根目錄執行以下命令。比較步驟從兩版的總表與狀態計算結果；逐格審查檔提供各案的原件和重開條件。

```sh
au-ree-v2 all --source-mode offline --as-of 2026-11-13 --source-replay results/ree-project-census/gap173-20261122/source_acquisition.json --replay-assets KIT/assets --tessdata data/ocr --work work/replay173 --out results/ree-project-census/replay173
python tools/compare_census_release.py results/ree-project-census/gap189-20261122 results/ree-project-census/replay173 --review-notes results/ree-project-census/gap173-20261122/followup_review.csv --out work/compare173
```
