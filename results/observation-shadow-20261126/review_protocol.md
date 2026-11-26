# 原件審查與獨立評估

先從 [review_pages.jsonl](review_pages.jsonl) 取得文件 SHA 及 PDF 實體頁碼，利用同一份靜態原件套件開啟頁面。頁碼從 1 開始，沿用 PDF 頁序。頁面標記 `RESOURCE` 是抽樣用的原文關鍵詞提示，並未判定頁上觀測是否適用。遇到續表及表註時查閱同一份原件的相鄰頁或明示引用。保留該觀測所屬的頁，在 `context` 內記錄支持範圍、原表、材料、化學基準、單位與日期的其他頁。

1. 複製 [review_reference_template.json](review_reference_template.json) 作為自己的標註檔。判讀前只取得原件、這份審查規格，以及用途定義。
2. 對每頁把指定用途涉及的完整觀測逐項列出，包括沒有候選編號的觀測。目標為原件直接報告的礦石量、TREO 品位、含 TREO 量與能辨識的相近用途反例。寫入 `project_id`、`quantity`（資源量為 `ore_mt`、品位為 `grade`、含量為 `contained_treo_kt`）、原樣 `token`、`unit`、`context`、`verdict`、可唯一定位且包含該數值的 `quote`。若引文中同一 token 重複，填入從 0 起算的 `token_occurrence_in_quote`。縮短引文時仍須保留足夠的上下文定位唯一出現位置。
3. `context` 記錄證實的結構化欄位及其證據。資源觀測優先使用 `scope`、`category`、`estimate_date`、`cutoff`、`chemical_basis`、`material_basis`、`denominator_basis`。比較程式逐欄核對這些參照值，範圍與類別須按 profile 保存。另有出處說明或精度可附於觀測的 `notes`，保留實際原精度。
4. 對各觀測使用 `CONFIRMED`（原件與此用途條件均成立）、`INCOMPATIBLE`（有原件支持的矛盾）或 `INSUFFICIENT`（證據不足）。頁內的觀測及反例已完整列舉時，設 `enumeration: COMPLETE`。其餘頁標 `PARTIAL` 或 `NOT_REVIEWED`。沒有符合觀測的頁可以完整標註為空清單。完整標註後仍沒有被任何擷取器定位的觀測會計入漏擷取。
5. 在 `relations` 加入要判定的觀測對。每個物件包含 `verdict`、`relation`、`sides`。兩端各記 `source_sha256`、`physical_page`、`quote`、`token`、`token_occurrence_in_quote`。估算版本、日期角色、分類範圍、cutoff、庫存、精度等以原件為準。完整列舉受審頁內的關係後，設 `relation_review: COMPLETE`。
6. 由有資格、未看過任何預測的人員完成或獨立複核後，填寫 `review_kind: INDEPENDENT_HUMAN`、研究使用的審查者代碼 `reviewer_id`、`reviewed_without_predictions: true`、可追溯的 `adjudication_reference`。AI 輔助標註可保留作開發複查，使用 `AI_PROVISIONAL`。評估器僅在已完成的獨立頁上計分，並保留標註與對齊缺項。

預測位置以同一原件、實體頁與數值出現位置對齊。對重複的數字，需要可辨認的完整引文。頁面行序以 PyMuPDF 排序擷取的原文字串為準。表格跨欄或閱讀順序差異有可能使自動對齊失敗，這類候選會另列為 `unlocated_candidates`。建議核對這些項目後再解讀精確率與召回率。

```sh
python -m tools.semantic_review \
  --prepare-from results/observation-shadow-20261126/review_split.json \
  --assets "$ASSETS" --output work/observation-review

python -m tools.semantic_review \
  --packet results/observation-shadow-20261126/review_pages.jsonl \
  --reference work/observation-review/review_reference_completed.json \
  --decisions results/observation-shadow-20261126/decisions.jsonl \
  --relationships results/observation-shadow-20261126/relationship_candidates.jsonl \
  --assets "$ASSETS" --output work/observation-review
```

分組保留兩個資源文件家族。去掉已用於先前評估、調規則或來源判讀的家族後，這套凍結原件沒有留下可抽樣的技術家族。技術獨立驗證須先凍結新的、按專案與報告家族隔離的原件，再使用相同逐頁審查方法。

本次抽出的 8 頁與已有候選頁沒有交集。Deep Leads 的既有候選位於第 6 頁，Fingerboards 的候選位於第 36 頁。這反映本輪擷取是在既有候選頁補查原文。審查頁的分母保持原樣。確認其中是否有漏擷取的目標觀測，仍需完成逐頁原件標註。[審查進度與輸入指紋](review_evaluation.json)
