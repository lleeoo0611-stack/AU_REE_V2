# Phase 22 與 ASX 整合驗收

本次使用 2026-11-13 截止的離線來源。技術揭露沿用 Phase 22 的 2026-11-05 審查口徑。SQLite 為正式證據來源，Census 固定 51 欄，MCDA 先依 Census 及面板條件篩選。

## 全表與 v9 對照

| 指標 | 上一版 | 定稿 |
|---|---:|---:|
| 有值格（93 × 51） | 2,223 | 2,233 |
| 原始覆蓋率 | 46.87% | 47.08% |
| 空白格 | 2,520 | 2,510 |
| 完整 TREO 資源估算 | 36 | 37 |
| v9 相同 | 2,026 | 2,032 |
| v9 有值、有內容或結構差異 | 59 | 63 |
| v9 空白 | 16 | 6 |

依現行規則排除 1,692 格不適用後，定稿覆蓋率為 73.19%。新增 10 格，更新 2 格總說明，609 個 v9 保護格全數保留。

- Goschen Central 補 6 格。公告第 3 頁 Table 2 的 Total 列為 620 Mt 和 584 ppm，正文以約 36 萬噸確認同一全礦石估算的量級。以表列值計算 362.08 kt TREO。磁性氧化物和組成比例保留各自的原件與計算追溯。
- Mount Ridley 補 2 格。公告第 7 頁把黏土宿主描述連到 Blocks 1 & 2。研究分類採原有黏土規則並標示離子吸附尚未確認。第 24–38 頁的鑽孔座標保留為鑽孔證據。
- Nolans 補上市狀態。2026-10-30 季報第 1 頁確認公司現名、ARU 與 Nolans 的關聯。
- Euston 補開發商。Iluka 2022 年報第 13、41 頁分別支持具日期的開發角色與新南威爾斯 Euston 研究範圍。

剩餘 v9 空白以本次截止日判定。Mount Ridley 缺兩區塊的代表點。Nowie 和 Wimmera 的同源座標仍缺截日前發布時間證據。另兩個維州專案 Cannie 和 Donald 也受同類截日條件影響，其座標空白不在 v9 固定母體。

Fingerboards 仍有 4 個來源未取得格。維州規劃機關公布的是多種礦物的年產合計，未提供可分拆的 TREO 或 NdPr 年產。 [維州規劃機關](https://www.planning.vic.gov.au/environmental-assessments/browse-projects/referrals/fingerboards-critical-minerals-project)

## 架構與復現

| 項目 | 本次實作 |
|---|---|
| 執行與取得 | 同一 `au-ree-v2 all` 明確區分離線、即時與凍結模式。輸出目的地與篩選條件獨立於來源模式。 |
| 缺值狀態 | 提供全表逐格狀態、適用性與結構化的證據拒用原因。沿用舊缺值代碼供 v9 比對。 |
| 身分與資源 | 公司標籤、上市狀態及已採用別名分別保存來源。臨時 SQLite View 依原件、資源聲明、範圍與有效日提供長格式觀測，保留單位、分類和材料基準。 |
| 技術與空間 | 已選技術案例連到來源、給料與回收終點。空間品質表保存來源及已知 CRS。固定母體的 GIS 敏感度只接受有證據的替代點和同一圖層。 |
| MCDA 發布 | 每個面板有納入／排除狀態、準則至證據的對照、矩陣與權重檔的雜湊，以及方法和種子。分析母體與正式 C1 資格分別記錄。 |

乾淨的來源工作區驗證了 420 筆選入來源，離線套件的 656 個檔案皆通過 SHA 核驗。Phase 22 的 64 個凍結成果通過重播比較，SQLite 結構相符，完整性檢查通過且外鍵違規為 0。501 項測試通過。

16 份 MCDA 排名與上一版逐位元一致，六構面面板維持 5 案。318 筆準則輸入皆可追溯。46 筆 GIS 距離檢查未找到經驗證且可比較的替代點，5 個含空間準則面板均依此記錄敏感度結果。

- [Census CSV](REE%20project%20census.csv) · [覆蓋率](coverage.json) · [本輪差異](coverage_delta.csv) · [v9 剩餘缺值](v9_remaining_missing.csv)
- [逐格狀態](field_status.csv) · [逐格證據](field_provenance.csv) · [資源估算觀測](resource_statement_observations.csv) · [實體關係及公司標籤](census_identity_roles.csv)
- [位置品質](spatial_point_quality.csv) · [GIS 敏感度檢查](census_gis_sensitivity.csv) · [固定母體排名敏感度](census_gis_rank_sensitivity.csv)
- [發布資料契約](census_release.json) · [排名輸入追溯](mcda_criterion_lineage.csv) · [MCDA 面板選入原因](mcda_panel_decisions.csv) · [驗收紀錄](verification.json)

離線重播套件及原件收據保留在本機 `work/phase22-census-replay-bundle`。發布紀錄提供可對照的 SHA 與資料版本。
