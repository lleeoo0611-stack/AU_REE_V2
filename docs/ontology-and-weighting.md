# 本體論可比性測試與權重學習

實驗日期：2026-11-26（臺北）；證據截止日：2026-11-13。

**結論：NLP 可以協助擷取文件中的實體、數值與關係；資料能否用於同一項比較，仍須有明確的語義與證據。這輪已完成 SKOS／PROV／SHACL 原型與既有腳本的比較，但新增可用資料為 0，尚未證明本體論比現有規則帶來更多可比資料。**

本次是已知案例的開發回歸測試，不是獨立盲測，也沒有重新訓練 NLP、重開來源 PDF 或改動正式 Census／C1 Eligibility／MCDA 權重。

## NLP 的適用範圍

建議擷取單位是「有來源的觀測」，至少保留實體、數值、單位、化學基準、材料與分母、資源類別、試驗／流程階段、時間與情境、文件 SHA、實體頁碼及原文片段。單獨擷取 `recovery = 80%` 不足以判斷它是浸出、選礦或全流程回收率。

Swain & Cole（2016）的 ChemDataExtractor 在其化學性質紀錄測試報告 precision 93.5%、recall 89.6%（Table 3，作者稿印刷頁 22）。這支持領域 NLP 可用於科學資訊擷取，但不能當成本專案稀土文件的實測準確率。[原文 DOI](https://doi.org/10.1021/acs.jcim.6b00207)；[作者稿](https://api.repository.cam.ac.uk/server/api/core/bitstreams/fd6d8f15-592b-4426-8d73-937bb5feba0c/content)。

若來源沒有說明 NdPr 是元素量或哪種氧化物組合，NLP 與本體論均應保留未知。數值完整、來源定位正確、實體及語義關係正確，應分別測量；不能只用數字辨識率評估端到端品質。

## 已實作的對照試驗

基準沿用 `tools/normalization_comparison.py`、`tools/evaluate_normalization.py` 及既有來源選擇／發布驗證，不將現有單位轉換的收益算成本次新增成果。

來源為 [既有 review](../results/normalization-pilot-20261125/case_review.json) 與 `results/ree-project-census/gap173-20261122/`。review SHA-256 固定為 `3973b3323ff92d37ff7eaf310a6378ae8c575bd9cc0667d475a0dd53b6a0b86b`。本次 fixture 是 AI 協助將既有審查內容投影為語義欄位；預期答案、案例名稱與審查理由不參與比較器判斷，但案例設計已知原始答案，因此不能視為盲測。

| 指標 | 既有腳本 | 加入本體論原型 | 解讀 |
|---|---:|---:|---|
| 已知不適用的候選用途 | 阻擋 13 組 | 阻擋 13 組 | 沒有新增誤收 |
| 原本有效的用途控制案例 | 接受 5 組 | 接受 5 組 | 沒有損失正向控制 |
| 上述案例涉及不同 Project | 11 | 11 | 不等於 11 個統計獨立樣本 |
| 原審查保留未知的儲存格 | 32 | 32 | 每組僅選代表性語義檢查，不當成 32 次獨立測試 |
| 通過既有來源／數值／單位門檻的資源儲存格 | 62 | 62 | 沿用既有通過條件 |
| Census 單位相容的不同專案配對 | 106 | 106 | 新增 0；限欄位、分類與單位層面的配對 |
| 新增已驗證 Census 數值 | — | 0 | 原始資料未被補值 |

本體論輸出為 5 個 `COMPATIBLE_FOR_DECLARED_USE`、12 個 `CONTEXT_MISMATCH`、1 個 `INSUFFICIENT_CONTEXT`。未知欄位與已知不匹配分開記錄；同一案例同時存在兩者時，狀態使用 mismatch，但缺少欄位仍保留在報告。

原始單位的相容配對為 80，既有單位標準化後為 106；這 26 對的增加來自原有程式。106 對沒有證明 cutoff、估值日期、水分基準、TREO 成員定義等全部一致，不應稱為完整科學可比性。

另外測試了 11 個人工構造的詞彙別名：9 個明示 exactMatch 可解析，2 個 closeMatch 維持不足。這只是詞彙契約測試，不能宣稱真實文件 recall 增加。

### 實際案例如何限制比較

以下頁碼是既有 review 記錄的 **PDF 實體頁碼**；本輪核對其來源 SHA、選擇與發布紀錄，沒有重新檢視 PDF bytes。完整 SHA 與原審查文字見上述 review 及 fixture。

| 來源案例 | 頁碼 | 語義問題與處理 |
|---|---|---|
| Donald，review index 0 | 6、117–118 | 20–250 µm 重礦物分離物的氧化物資料，及元素到氧化物的轉換常數，不能當成全礦石資源品位 |
| Sandy Mitchell，index 1 | 74 | TREO 與 TREO+Y 的成員和分母不同；不能只改欄位名稱或單位 |
| Lyons，index 2 | 1、18 | NdPr 未指明 Nd₂O₃ + Pr₆O₁₁；化學基準維持未知 |
| Mt Weld，index 3 | 3、9–10 | Ore Reserve 的 Dy 與 Mineral Resource 的合計 Tb+Dy 不可互換，也不能自行拆分合計值 |
| Goschen，index 8 | 4、9、21 | 前五年與全計畫平均不同，材料與化學基準也必須對應 |

## 本體論對照應採用的背景

以現有證據庫為資料來源，建立可版本化的語義讀取層。先以具體研究問題決定必填語義，再對照標準，不建立另一份平行的正式資料庫。

| 層次與設計背景 | 對應概念 | 專案設計要求 |
|---|---|---|
| [CRIRSCO 2024](https://crirsco.com/product/crirsco-international-reporting-template-2024/)、[JORC 2012](https://www.jorc.org/docs/jorc_code2012.pdf)、[CIM 2014](https://mrmr.cim.org/media/1092/cim_definition_standards_20142.pdf) | Exploration Target、Mineral Resource、Ore/Mineral Reserve、分類與修正因素 | 保留原報告制度、版本、有效日期、分類、cutoff 與範圍；概念對照不等於數值可直接相加 |
| [EarthResourceML 2.0](https://earthresourceml.org/) 與 [CGI 地學詞彙](https://cgi.vocabs.ga.gov.au/vocab/) | 礦化點、礦床、礦山、礦業活動、商品、資源／儲量；地質與礦物學分類 | Project 維持穩定 ID，以關係連到 deposit、mine、processing facility；不因名稱或座標接近合併 |
| [SOSA／SSN 2017](https://www.w3.org/TR/2017/REC-vocab-ssn-20171019/) | Observation、observed property、feature of interest、sample、procedure、phenomenon/result time | 區分全礦石、精礦、浸出液與產品；描述試驗步驟、條件、尺度與代表性。resultTime 不直接等於 publication date 或 known_at |
| [QUDT](https://www.qudt.org/doc/DOC_SCHEMA-QUDT.html) 與專案 REE 擴充 | 數量種類、單位、維度；元素／氧化物與 TREO 成員集合 | 單位可換算不代表分母相同；另外定義 dry/wet、bulk/HM、NdPr 氧化物組成與 Y 是否納入 |
| [SKOS Reference §10](https://www.w3.org/TR/skos-reference/#mapping) | 標準名稱、別名及 exact／close／broad／related mapping | 語言模型或 embedding 提出候選；經證據確認後才成為 exact 對照。近義與上下位關係不自動升格為等價 |
| [PROV-O](https://www.w3.org/TR/prov-o/) 與 [SHACL 2017](https://www.w3.org/TR/2017/REC-shacl-20170720/) | 原始證據、衍生與處理活動；圖形約束驗證 | 保存 SHA、頁碼、擷取方式、轉換版本；以必要欄位、型別與允許值檢查指定用途 |

本輪實際使用的是專案小型詞彙表、SKOS mapping、PROV 來源連結與 SHACL `minCount`／`maxCount`／`hasValue`。CRIRSCO、EarthResourceML、SOSA、QUDT 是後續設計背景，尚未完成全面形式對照。本輪沒有啟用 OWL 推論、外部 RDF 匯入或 sameAs 合併。SHACL 通過只表示符合已宣告條件，不保證來源事實正確。

由這些層次組成的比較契約，建議至少問：是不是同類數量、同一材料與分母、同一化學基準、相容資源分類、相容流程終點、相容時間／情境，以及是否有可追溯證據。資料缺少必要維度時保留不足，不因更多本體類別而補出事實。

## 權重算法的選擇

**有驗證過的歷史開發事件時，優先測試既有 `outcome_mcda` 的非負、正則化 logistic 模型；目前沒有完整事件標籤時，以等權參考與 CRITIC／熵權情境評估排名穩健性。** 本輪沒有將上述方法設定成正式研究權重。

CRITIC 依各準則的標準差與相關程度計算資訊量：`C_j = s_j × Σ_k(1-r_jk)`，再將 C 正規化成總和 1。它可減少重複資訊的影響，但大變異、低相關的噪音仍可能得到高權重。熵權依數值分布差異賦權，也沒有使用開發結果。兩者屬資料結構的賦權方法，不能單靠算法名稱主張工程或決策重要性。[Diakoulaki et al. 1995](https://doi.org/10.1016/0305-0548(94)00059-H)。熵權公式來源：[Xu 2004，The two models](https://doi.org/10.1016/S0377-2217(03)00146-2)。

### 已執行的權重反例

八筆人工資料含一個與標籤完全對齊的訊號，以及一個在兩種標籤中分布完全相同的欄位；兩者都使用固定 0–1 效用尺度。

| 方法 | 訊號欄位權重 | 無預測資訊欄位權重 |
|---|---:|---:|
| 等權 | 50.00% | 50.00% |
| CRITIC | 39.56% | 60.44% |
| 熵權 | 28.06% | 71.94% |
| 既有 outcome_mcda | 100.00% | 0.00% |

這個構造反例說明依分布計算的權重未必反映預測資訊。它沒有獨立測試集，也沒有證明監督模型在真實礦業資料比較準確；重複的 prediction vectors 已明示為原八筆資料的重建，不報告泛化指標。

### 可保留 MCDA 表達方式的事件模型

對已定義且方向一致的效用值 `u_j(x)`，擬合：

```text
p_i = sigmoid(b + Σ_j β_j u_j(x_i)), β_j ≥ 0
loss = mean(binary log loss) + (λ/2) × Σ_j β_j²
w_j = β_j / Σ_k β_k
S_i = Σ_j w_j u_j(x_i)
```

既有原型固定 λ=0.01，這是軟體示範設定，沒有聲稱經真實資料選到最佳值。若係數總和接近零，不產生有效權重。S 是可加性分數；事件機率還依賴截距與係數總強度，不能將 S 直接解讀成機率。

權重只描述「在選定事件、時窗、樣本與效用尺度下的預測關聯」。歷史 FID 或投產結果無法識別所有戰略、環境或政策價值偏好。研究目的、準則集合、單調方向及效用尺度仍包含研究判斷；資料驅動方法能減少直接指定數字的主觀性，不能消除決策選擇。預測與偏好學習的區別參考 [Hüllermeier & Słowiński 2024，Part II §2.1.2](https://link.springer.com/article/10.1007/s10288-023-00561-5)。

實際訓練需沿用 [實驗資料契約](research-experiments.md)：同一 Project 不跨訓練／測試、只使用預測時點已知的特徵、零標籤須有完整追蹤證據、保留共同澳洲測試名單。固定期二元模型只使用追蹤成熟的案例；若要利用未成熟追蹤資料，另行設計存活分析。

開發階段是序位資料，將它線性打分含有階距假設。資料足夠時可比較有單調約束的分段效用函數，固定端點以保持權重可辨識性。高度相關準則的係數可能不穩定，即使預測表現相近，也應按 Project 重抽樣檢查權重區間與排名穩健性。PCA loading、SHAP 平均絕對值或既有 MCDA 排名不直接作為新的決策權重或獨立結果標籤。

## 執行與產物

```bash
python -m pip install -c requirements-constraints.txt -e '.[experiments,ontology]'
python -m tools.evaluate_ontology --output-dir work/ontology-v1
python -m tools.weighting_counterexample --output work/weighting-counterexample.json
python -m unittest discover -s tests -p 'test_ontology.py'
python -m unittest discover -s tests -p 'test_normalization*.py'
python -m unittest discover -s tests -p 'test_module_dependencies.py'
```

本次保存的四項本體論產物在 `results/ontology-pilot-20261126/`：`ontology_report.json`、`evidence.nt`、`shapes.nt`、`vocabulary.nt`。反例另存為 `results/ontology-weighting-counterexample-20261126.json`。報告包含輸入／程式 SHA、依賴版本、每例來源與約束違反；80 個 EvidenceContext 節點均有來源頁面連結。

本體論 CLI 允許相同內容重跑，內容改變時要求新輸出目錄。資料來源 SHA 與 Census release manifest 重新核對；`pdf_bytes_reverified=false`、`fresh_nlp_extraction=false` 必須保留。13 個本體論測試、8 個既有標準化測試與 1 個模組相依測試已通過。

## 下一個能檢驗研究增益的實驗

固定三組比較：既有腳本、同一 NLP 擷取器加既有規則、同一 NLP 擷取器加語義對照與約束。先在新公司／新文件建立由獨立審查者標註的測試集，再凍結擷取器、詞彙映射與規則；相同專案的改版文件、同一報告的重複公告不得分散進開發與測試組。

主要指標應包含：來源定位與完整觀測擷取的 precision／recall、錯誤可比判定率、正確可用資料的覆蓋率、仍需人工審查比例，以及工時。比較資料覆蓋率時須維持預先宣告的錯誤上限，並區分「明確不相容」與「證據不足」。目前 13+5 組只能作為回歸案例，不能重複利用來宣稱上述增益。

全球資料的試驗仍以相同澳洲測試集比較 AU_REE 與 GLOBAL_REE。跨礦種只納入有可比語義的共同特徵，不以缺值補值將非稀土專案變成稀土專案。最後再以有來源的歷史事件驗證權重學習及 Brier score、log loss、校準與排名穩健性，才能判斷它對 Aim A、B、C 的實際貢獻。
