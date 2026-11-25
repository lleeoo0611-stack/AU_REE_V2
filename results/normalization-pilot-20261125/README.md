# Phase 22 × ASX 資料正規化試驗

資料截日為 2026-11-13，固定基線為 [93 個專案的 Census](../ree-project-census/gap173-20261122/README.md)。本試驗在已驗收的架構提交 `25c21579d966fdc8c425453b1c07ededf9a4f170` 上執行，從既有 Census、逐格來源與凍結 PDF 讀取資料。推導結果存放在本測試目錄，正式 Census 與排名仍透過既有單一入口產生。

## 覆蓋率

有值格數為 **2,496／3,034（82.27%）**。18 格資源量基準缺口與 14 格年產量缺口，新增實值 0 格、改判不適用 0 格，全表適用但空白 532 格。

| 原件複核結果 | 格數 |
|---|---:|
| Donald 的重礦物表缺少次要元素品位 | 9 |
| WIM100 缺少非重礦物部分的質量衡算 | 5 |
| Mt Weld 僅有合併氧化物資源量或不同範圍的儲量 | 2 |
| Lyons 的 NdPr 化學式及 Sandy Mitchell 的含釔分母各有一格待證 | 2 |
| 已有資源估算或擬議研究，尚缺可採用的年產時程 | 6 |
| 年產數字屬其他廠房或不同情境 | 4 |
| 礦物產品噸數、定價籃子或期間無法換成同產品的氧化物年產量 | 4 |

逐格驗收使用 15 份凍結 PDF、34 個實體頁。32 頁核對原文標記，另 2 頁為圖表，由審查者閱讀後以原件雜湊及實體頁固定。5 個已有實值的對照均通過，包含 Wudinna 的 101 ppm NdPr 與 27.7352 kt CeO₂，以及三案的年產。原件定位參考前次審查，因此這項結果衡量已知困難案例的判讀一致性。詳見[逐格預期結果及原件定位](case_review.json)。

## 可對比度

第一項量測凍結同一批 62 格正數，涵蓋 28 個專案與 28 份獲准使用的 PDF。每格均有原始數字、原單位、儲存值，以及可驗證的 Census 直接引用。兩專案必須有相同欄位、相同資源類別。下表以不重複的專案對計算；同一對可能符合多個欄位。

| 欄位 | 原始單位字串相同 | 換為既有 Census 單位 |
|---|---:|---:|
| 礦石量 | 65 | 106 |
| TREO 品位 | 42 | 72 |
| 所含 TREO 量 | 10 | 16 |
| 至少一個欄位可比，跨欄去重 | **80** | **106** |

增加的 26 對可歸因於正式 Census 既有的單位統一。在這 62 格上，測試分支相對正式版的單位配對增量為 0。跨專案仍須考慮截限、TREO 定義、水分基準與估算日期。這批資料涵蓋 112 個候選來源欄位中的 62 格，其他格的排除原因及每格使用的觀測識別碼均記在[量測結果](pilot_result.json)。

第二項試驗使用 Jupiter 靜態 PDF 第 19 頁的指示資源 160 Mt 與推斷資源 1,500 Mt。各氧化物以分類噸數加權，並逐一與既有的同估算氧化物含量核對。由此得到 **15 個合併資源全礦品位**，其中 4 個能和 Splinter Rock 第 2 頁直接報告的品位比較。兩案均報告指示加推斷資源。Jupiter 估算日為 2026-10-12，Splinter Rock 為 2024-05-29。

| 全礦氧化物，ppm | Jupiter 加權品位（約） | Splinter Rock 原表 |
|---|---:|---:|
| Nd₂O₃ | 283 | 226 |
| Pr₆O₁₁ | 82 | 64 |
| Dy₂O₃ | 14 | 14 |
| Tb₄O₇ | 3 | 3 |

這四項出自 **同一對專案**。15 個品位均由既有數據推導，原始分類品位、噸數和逐格觀測識別碼保留於結果供複算。兩案的名義截限同為 1,000 ppm TREO。Splinter Rock 定義中明列 Y 與 Ce；Jupiter 說明排除 Sc 與 Ga，未明示該截限使用的完整氧化物清單。依完整相同截限組成判定，目前可驗證的配對為 **0**。四項描述性比較均未納入 MCDA。

## 單一流程重播結果

2026-11-25 的離線重播與基線有 14 份 Census 及來源檔、16 個 MCDA 面板共 160 份檔案雜湊一致。235 筆來源版本及截日決策相同，SQLite 完整性通過，外鍵違規 0 筆。SAW、TOPSIS 及 PROMETHEE II 共核對 1,542 個名次與 8,322 次兩兩排序，面板成員、分數及排名均無異動。將同一試驗分別套用於已發布 Census 及本次重播輸出，兩份試驗結果的 SHA-256 均為 `382538124fcb08d2fb63f9d52a3d1f91597b400d4f3719e13937a6c3b67acf86`。[逐面板驗收紀錄](replay_verification.json)

## 重現

在已安裝本專案的環境，由儲存庫根目錄執行。第一行使用既有收據及原件重建 Census 和 MCDA，第二行將測試套用到重播輸出。`KIT/assets` 指向既有 SHA-256 命名的原件目錄。OCR 與 R 依既有部署設定。

```sh
au-ree-v2 all --source-mode offline --as-of 2026-11-13 --source-replay results/ree-project-census/gap173-20261122/source_acquisition.json --replay-assets KIT/assets --tessdata data/ocr --work work/normalization-replay --out results/ree-project-census/normalization-replay
python -m tools.evaluate_normalization --release results/ree-project-census/normalization-replay --assets KIT/assets --output work/normalization-result.json
```

也可直接以已發布 Census 作為輸入，省略第二行的 `--release`。輸出不含本機路徑或執行時間，可與 [pilot_result.json](pilot_result.json) 逐欄核對。
