# 全體 93 案的資源本體論效益

**15 個既有資源值首次通過描述性比較的來源查核。** 固定分母為 93 個 Census 專案，有至少一個可用欄位的專案從 29 增至 37。拆開後，補讀原件數字及欄標增加 12 個欄位，精確單位對照再增加 3 個欄位。加入估算關係增加 8 筆來源佐證，這 8 筆都對應已可比較的欄位。[逐專案帳冊](project_scope.csv) · [逐筆決策及原件定位](decisions_overlay.jsonl)

## 評估範圍

使用 Phase 22 研究截日 2026-11-13 的凍結資料。以 gap173 發布版 Census 的 93 個穩定 ID 為母體，截至 coverage-locked 發布版仍是相同名單。固定用途為並列各專案**所選資源估算**直接報告的礦石量、TREO 品位及含 TREO 量，跨案配對要求同欄位及同資源分類。所選聲明、來源資格與可用日期沿用原流程。351 筆選值前候選中，349 筆屬於這 93 案的 40 案。另兩筆是 Central Mia 範圍的外部 ID，只保留作阻擋紀錄。[候選重建](../ontology-gain-20261126/inventory_manifest.json) · [全體分母與出界記錄](portfolio_summary.json)

在原有規則拒絕原因為「缺原數或不支援原單位」的 17 筆內，回查該組的全部原件。15 筆具備可追查的表題、列、欄標或完整正文。另兩筆重礦物基準維持阻擋。估算關係另處理上輪有分歧的 23 筆，保留 11 筆關係判定與 12 筆反例的雙側原文。新增證據均來自已凍結的靜態 PDF。之所以可以計算邊際效益，是因後三組共用相同的原始觀測與原件。[可執行來源對照表](../../config/ontology/portfolio_statement_evidence_v1.json)

## 四組實測

| 條件 | 接納候選列 | 去重後專案欄位 | 有可用值的專案／93 | 符合描述用途的專案配對 |
|---|---:|---:|---:|---:|
| PR #16 原有最佳方法 B1 | 65 | 65 | 29 | 114 |
| L，補讀原件，沿用可直接辨識的原單位 | 77 | 77 | 37 | 175 |
| N，同一批補讀內容，加入精確單位對照 | 80 | 80 | 37 | 179 |
| C，再加入有原件支持的估算關係 | 88 | 80 | 37 | 179 |

去重單位為「專案 × 欄位 × 指定用途」。跨欄位同一組專案只計一次，已確證相同觀測的重刊去重。179 對代表可並列申報值，仍保留各自的 cutoff、量測條件和估算範圍。固定的 12 個舊反例均未接納，原本已接納的 65 筆都保留。這是開發資料上的回歸與原件查核。舊留出明細未出現新增接納，本輪沒有新建獨立盲審母體。[原始分子、分母、與差異 ID](effect_summary.json) · [逐對明細](project_pairs.jsonl)

### 新增可用欄位

| 專案 | 通過原件複核的已存數值 |
|---|---|
| Brockman | 41.6 Mt、0.20% TREO |
| Dubbo | 75.18 Mt |
| Jupiter | 0.17% TREO |
| Mangaroon – Yin | 29.98 Mt、1.04% TREO |
| Mons – Block3 East | 7.23 Mt、0.0538% TREO |
| Mt Clere – Tower | 101 Mt、0.084% TREO |
| Mt Weld | 106.6 Mt、4.12% TREO、4,389 kt TREO |
| Narraburra | 94.9 Mt、0.073895% TREO |

精確單位對照的獨立收益是 Brockman 噸數的 `M Tonnes → Mt`，以及 Mt Weld 的 `Million Tonnes → Mt` 與 `‘000 tonnes → kt`。兩個專案已由其他欄位進入 L 組，因此新增 3 個欄位、0 個專案。其餘 12 筆依既有支援的原始單位，即可完成換算。

## 對照表如何執行

| 參照 | 實際驗證內容 | 實測例子 |
|---|---|---|
| JORC | 資源分類組成、直接報告的資源量、所選範圍與 cutoff；分開看估算基準日與報告發布日。 | Cummins 較早估算的 6 筆保留為已被取代。Mt Weld 同頁正文 **4.12%** 可支持精確值；表列 **4.1%** 僅支持同估算及原申報精度。 |
| EarthResourceML | 用本地穩定專案及資源範圍 ID，記錄版本、重刊、範圍差異。逐側驗原件 SHA、頁碼及表列。 | Wolverine 的 7.3 Mt 資源表重刊可互作佐證；另一張 7.5 Mt、品位同為 0.96% 的表包含庫存，仍有兩筆明確衝突。Lyons 全案或 Lyons 11 的四筆與所選 12 & 13 範圍分開。 |
| QUDT | 核對原文、量別、單位因子與既存數值。材料與分母及其化學基準需要各自的原件證據。 | Mt Weld 的 4,389 千公噸換成同一規格的 4,389 kt。Nowie 與 Donald 兩筆以重礦物為分母的值，沒有靠百分比單位通過。 |
| SKOS | 用精確別名定位概念，將詞彙映射與個別估算關係分開。 | `M Tonnes` 的對照只適用於已選公噸質量欄。Lyons 12 & 13 的兩筆有同估算證據，但候選端與選定端的化學基準表達仍無法確證等價，保留待補證。 |

C 組的 8 筆精確佐證來自 Yttria、Salazar、Wolverine、Mt Weld，各兩筆。關係規則也把找不到相同表列識別、尚無原件證據可判定的列列為待證。證實衝突的 12 筆則各有可查的取代、範圍或庫存原因。原始資料、歷史試驗和正式權重維持凍結，新增入庫值與正式 MCDA 專案皆為 0。[規則、標準欄位與用途](../../config/ontology/resource_portfolio_v1.json) · [正式 C1 資格](../ree-project-census/gap173-20261122/formal_c1_release.json)

## 其餘專案

- **37 案至少有一個可用欄位**。36 案有完整的 TREO 資源組，WIM100 只有能通過本用途的部分資料。
- **3 案有候選，這個用途下仍全數受阻**。Wudinna 有 Census 資源組，但三筆候選屬非靜態 PDF 的來源鏈。Burracoppin 和 Greater Brothers 有政府彙整線索，也尚缺本用途要求的已驗證資源聲明。
- **53 案沒有此用途的候選觀測**。加上前述兩個只有線索的專案，共 55 案沒有選定資源估算。這一組的實質改善依賴可用的估算原件；語意對照可協助定位，現階段的欄位仍留空。

本輪對所有 Census 專案使用同一資源比較用途，技術、年產、座標等欄位有各自的資料與資格條件。先前凍結資料中的 381 筆技術表格紀錄，沿用現有技術核對，本輪的 15 欄增益只計資源值。[逐案範圍及剩餘原因](project_scope.csv) · [技術背景盤點](../ontology-gain-20261126/upstream_audit.json)

## 重播

在專案根目錄以已安裝本專案依賴的 Python 執行。ASSETS 指向先前 gap173 靜態 PDF 套件中的 assets 目錄。

```sh
python -m tools.ontology_portfolio --assets "$ASSETS" --output work/portfolio-replay
python -m tools.ontology_portfolio_scope --overlay work/portfolio-replay/decisions_overlay.jsonl --output work/portfolio-replay
```

[輸入指紋、重播及驗收收據](verification.json)
