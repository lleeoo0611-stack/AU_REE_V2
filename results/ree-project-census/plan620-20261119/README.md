# Phase 22 × ASX Census 逐格補證結果

資料截日為 **2026-11-13**。93 個專案、51 欄。對前版 620 格待補證逐格執行上次的 153 個處理批次，填入 **46 格**，2 格改判不適用，原清單餘 572 格。另有 6 格因上游證據更新而重新列為待補，故全表目前有 **578 格待補證**、1709 格不適用、2456 格有值。

[Census 總表](REE%20project%20census.csv) · [620 格處置及重開條件](gap_disposition.csv) · [新增、更新與撤回](coverage_delta.csv) · [欄位來源](field_provenance.csv) · [驗收](verification.json)

| 原清單類型 | 原格數 | 已填 | 改判不適用 | 原清單仍缺 |
|---|---:|---:|---:|---:|
| 資源估算 | 368 | 0 | 0 | 368 |
| 專案座標 | 86 | 4 | 0 | 82 |
| 預估年產 | 57 | 1 | 0 | 56 |
| 礦床型態 | 43 | 15 | 0 | 28 |
| 開發階段 | 28 | 14 | 0 | 14 |
| 產品 | 18 | 4 | 2 | 12 |
| 公司與上市資訊 | 12 | 0 | 0 | 12 |
| 總說明 | 8 | 8 | 0 | 0 |

原清單補入的欄位為 產品/產出 4、礦床型態 13、開發階段代碼 2、開發階段類別 2、開發階段 10、緯度 2、經度 2、預估年產NdPr_t_per_year 1、礦床型態代碼 2、總說明 8。原有值更新 4 格，撤回 4 格。重新待補的欄位包含 Viper REE Project — EMU（開發階段代碼）、Viper REE Project — EMU（開發階段類別）、Viper REE Project — EMU（產品/產出）、Southern Cross Li-REE Project — GCX（開發階段代碼）、Southern Cross Li-REE Project — GCX（開發階段類別）、Southern Cross Li-REE Project — GCX（產品/產出）。

## 證據與適用範圍

- Charley Creek 概評的混合稀土碳酸鹽含 REO 設計產能為每年 3,645 噸，同一產品中 Nd₂O₃ 占 14.93%、Pr₆O₁₁ 占 4.24%。依報告精度約為 **699 噸 NdPr 氧化物／年**。CSV 保留推算值 698.7465。這是 2013 年概評所採設計情境。北斯坦莫爾研究表報乾基平均噸數，缺明確年度分母，維持空白。
- 資源欄的 368 格沿用 22 個同範圍估算批次，核對 21 個不同原件版本。分項化學式、分母、材料與所選資源範圍均須相容。只有合計的文件，以及礦石與精礦、資源與儲量的不同基準，均已記錄在逐格清單。
- Nowie 以截日前封存的官方礦權圖層及具版本的公開時間證據，得到 EL6666 代表點。Cannie 兩張礦權聯集的最遠距離約 31.63 公里，超過原有 25 公里門檻。Deep Leads 的官方點位與所選 88.6 Mt 估算的發行人模型圖相符。[座標品質](spatial_point_quality.csv)
- WIM150 採 Australian Zircon 2015 年規劃的稀土礦物精礦。Euston 採礦場規劃重礦物精礦，Coburn 採設計含獨居石的鋯精礦。歷史設計、實際出貨及下游精煉產品依文件分列於欄位來源。
- 待證的公司欄涵蓋歷史開發商、僅有海外交易代碼的發行人，以及混合上市與私人參與方的合資案。公司登記形式、交易所證券碼與合資營運角色分別核對。

Voyager 年報僅列 2024 年 10 月。表中的 10 月 31 日是月底的狀態核對日。Brockman 的氧化物產品是 2012 年概評偏好的歷史設計，與 2026 年重新評估開發選項的工作分開記錄。

## 本次補入或校正的歷史階段

| 專案 | Census 來源狀態與日期 |
|---|---|
| Franklyn Kaolin–REE Project — Nackara Arc | Exploration — iTech re-assayed kaolin-rich intervals from Archer’s 2019 drill holes for REEs at Franklyn（來源狀態日：2022-07-29） |
| Lake Campion REE Exploration Project — IGO | IGO reports withdrawal of its mapped Lake Campion tenure during FY25（來源狀態日：2025-06-30） |
| Viper REE Project — EMU | EMU ceased its REE exploration focus after a passive seismic survey at Viper; the proposed aircore programme did not proceed and tenement relinquishment had commenced（來源狀態日：2024-06-30） |
| Voyager Rare Earth Project — Tasmania | Lithium Universe formally relinquished its Voyager rare earth project in October 2024（來源狀態日：2024-10-31） |
| Lake Tay REE Project | White Cliff signed to acquire the Lake Tay REE project and applied for surrounding licences. Its first field visit was still being planned（來源狀態日：2022-10-31） |
| Perenjori Uranium–REE Exploration Project — HRE | Exploration soil assays returned rare earth values without a spatially coherent anomalous zone（來源狀態日：2025-06-13） |
| West Arunta Project — Luni Niobium–REE scope | Maiden drilling reported niobium and rare earth intersections at Luni（來源狀態日：2022-11-16） |
| Southern Cross Li-REE Project — GCX | Terra Metals withdrew from the Southern Cross project by relinquishing E77/3009, E77/3010, E77/3011 and E77/3012 after the June 2025 quarter（來源狀態日：2025-07-30） |
| Ravensthorpe REE Exploration Project — Young River, Dalyup and Bremer | Strategic review completed; divestment process initiated for the Ravensthorpe licences（來源狀態日：2024-06-30） |
| Kalkaroo | Laboratory testwork on bastnasite recovery from oxidised West Kalkaroo ore; pilot separation equipment being set up（來源狀態日：2022-01-31） |

## 重播及排名

同一個 Phase 22 × ASX 入口重建 SQLite、輸出 Census、篩選後執行三種 MCDA。16 份排名中 16 份逐位元相同，名次變動 0 筆。六構面面板有 5 個專案。第 9 版 2,101 格參考對照有 2019 格相同、6 格缺值；609 格保護組有 602 格相同。Nowie 的兩格座標恢復與實驗基準一致。Viper 與 Southern Cross 各撤回兩格舊階段分類，因此第 9 版對照空白由 4 格升至 6 格，保護組中相同格由 604 降至 602。此變化可逐格追到發行人最新可採用的歷史狀態。[對照差異](v9_new_regressions.csv) · [對照空白](v9_remaining_missing.csv)。凍結流程的 64 個檔案通過比對，完整測試通過 520 項。[MCDA](MCDA) · [驗收與比對](verification.json) · [來源版本及截日](source_selection.csv)

[本版收據](source_acquisition.json)已驗證可依 SHA 從本機原件庫取得 683 個原件與附檔。請使用保存同一位元組的原件庫，並安裝本專案原有的 R 與 OCR 環境。

```sh
au-ree-v2 all --source-mode offline --as-of 2026-11-13 \
  --source-replay results/ree-project-census/plan620-20261119/source_acquisition.json \
  --replay-assets work/phase22-census-replay-bundle/assets --work work/census-plan620-replay
```

本次未補的格子保留逐格原因。遇有符合截日的新原件版本、先前未核對的有效頁面、可重建的歷史圖層或上游證據改變時，以穩定專案 ID 和欄名重開對應批次。
