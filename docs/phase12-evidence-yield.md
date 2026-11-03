# Phase 12：證據產出、可比較性與研究進展

本階段自 Phase 11 `f8aff1442d39a1919786c0ea46be049022b59ada` 建立獨立分支 `feat/phase12-evidence-yield`，以原開發分支為 PR base，不合併 Draft PR #1。沿用 `work/phase5/canonical.sqlite`、Python CLI、Evidence Selection、官方 GIS 與 R 引擎；SQLite Schema、正式準則與六個 Gate 均未改動。研究資料截止日 **2026-11-03**，取得視窗至 **2026-11-04**，上游正式 Gate cutoff 仍為 **2026-10-29**。

## 實際資料增量

| 指標 | Phase 11 | Phase 12 |
|---|---:|---:|
| Canonical registry groups | 31 | 31 |
| Resource-defined scopes | 22 | 22 |
| Selected source snapshots | 104 | 121 |
| 原始 PDF snapshots | 44 | 49 |
| 自動辨識文件（含零候選文件） | 13 | 25 |
| 文件候選 | 957 | 1330 |
| 現行驗證版本下的文件觀測 | 371 | 442 |
| Selected validated numeric statements | 265 | 292 |
| 結構化事件 | 19 | 21 |
| 可評分 R／S／T／D／I／C | 22／9／0／5／20／6 | 22／10／0／9／20／8 |
| Strict Development／Full-evidence／Formal C1 | 0／0／0 | 0／0／0 |
| 未解決 deposit pairs／政府候選關係 | 36／112 | 36／112 |

新增五份 PDF 中，**兩份是本次實際補入研究證據的主文件**：Cummins Range 2023 enhanced Scoping Study（ASX 原公告）及 North Stanmore 2026-10-30 季報（發行人公告 PDF）。另三份 VHM 網頁連結文件未形成新的可評分證據；不把下載數當作有效技術文獻數。其他既有原件新增辨識／解析快照，無政府 Census Project 或實體配對增量。

**由兩份新文件及三份既有原件補錄的29筆人工定位、由現有程式驗證的數值候選中，27 筆有效、2 筆 REVIEW；沒有新增可靠的自動數值格。** 27 筆為 Development 4、Strategic 1、Technical 22。文件管線增加71筆通過現行驗證的文字觀測；文字 NULL 值不代表新增 recovery 或融資款項。來源、SHA、頁碼、原始語句、scope、日期角色與轉換／驗證版本保留於既有 claims、Selection 和輸出。

- Browns Range、Goschen：新增已完成 DFS／歷史 DFS 再確認，保留設計或 Area1 範圍與日期；不是目前施工／生產的認定。
- Cummins Range：完成的三階段 Scoping Study；Stage2a／2b／3 的9筆 feed grade、recovery、product grade，以及6筆分產品 NORM 值。這是 Scoping 模型，不是 DFS 或操作實測。
- North Stanmore：PFS 完成事件、5筆 TIMA secondary-phosphate deportment 與2筆樣本／鑽孔數。保留33樣本、18孔、pilot-concentrate範圍及 Pr/Nd 高、Tb/Dy 很高的不確定性描述；deportment不是recovery。
- Jupiter：原件p7約23%的四磁性稀土比例，p27明示 Pr₆O₁₁＋Nd₂O₃＋Tb₄O₇＋Dy₂O₃；與選定資源的 source／scope／statement／date 相同。沒有以不同 cutoff／JORC 類別的四捨五入數據重組比例。來源未界定「約」的誤差範圍，因此不設定±0.5；rounding simulation將其視為固定條件輸入，不宣稱測量誤差為零。
- Cummins 擬議 grant/debt/equity 與 North Stanmore 非約束 EXIM LOI：新增兩筆 Project 融資規劃事件，均不是承諾資金、已簽貸款、financial close或drawdown。公司cash、產品寄送資格測試不當作Project融資或binding offtake。

North Stanmore 季報另報新版278.8Mt／483ppm MRE。完整原始分類及REO定義尚未核實；167頁 PFS 公告鏡像下載逾時，未冒稱取得原件。兩筆摘要保留 REVIEW，舊的2025已驗證scope仍獨立保存，`cohort_coverage.csv`明列 `NEWER_UNHARMONIZED_DISCLOSURE_EARLIER_VERIFIED_SCOPE_RETAINED`。包含此案的排名是已驗證舊資源與新披露研究階段的條件式探索比較，不是最新資源總量排名。

## 科學品質修正與 benchmark

逐筆檢查原始新增值時，發現 Cummins MRE p2 的 P₂O₅ **4.2／5.9／4.6%** 被舊規則誤讀為 TREO ppm；正確 TREO 為3320／2590／3170ppm。三列的六個候選值全部留待查，不把正確tonnage與錯誤grade拆開授予通過。舊候選／驗證版本保留；`scientific-context-v4-column-binding`拒絕沒有positioned binding、且tonnes與TREO之間存在其他數量的表格。這項修正使暫定+33數值更正為**+27**，不以增加筆數保留錯誤。

另隔離 glossary、hypothetical future funding、company cash；新增礦物學文字辨識，但來源文字或礦物名稱不直接產生正式技術分數。詳細方法與實際閱讀範圍見 [文獻核對](phase12-literature.md)。本階段未用另一個LLM作為原始證據核實。

`data/phase12_document_benchmark.json`為目的抽樣：**8文件、13頁、22數值格、23接受判定案例**。包含Resource／Reserve、密度／P₂O₅／TREO−Ce、Nb／THM、不同礦區、跨頁同表頭、glossary及財務負例。

| 同一擴充gold | v3 | v4 |
|---|---:|---:|
| 數值 TP／FP／FN | 8／3／14 | 5／0／17 |
| 數值 precision／recall | 0.7273／0.3636 | 1／0.2273 |
| 接受判定 TP／FP／FN／TN | 3／3／6／11 | 3／0／6／14 |

五個輸出格的scope／unit／locator指標為1；scope指標限於Project與表格標題，不代表已完成canonical resource admission。保守漏失17/22格，仍是主要解析瓶頸。不是盲測、不是全澳準確率，也不能與Phase10不同gold的31/33直接比較。Phase9／10 benchmark綁定各自原lock，未改其既有數字。

## Aim A：共同樣本與排名

| 面板 | 舊n | 新n | 變化原因 |
|---|---:|---:|---|
| Resource＋Strategic | 9 | 10 | Jupiter同資源REO比例 |
| Resource＋Study maturity | 5 | 9 | Browns／Goschen／Cummins／North Stanmore dated study |
| Resource＋Financing milestone | 5 | 7 | Cummins／North Stanmore規劃事件 |
| Resource＋4類Infrastructure | 7 | 7 | 無GIS新證據 |
| Resource＋Port | 20 | 20 | 無新resource或port |
| DFS concentrate相關三面板 | 2 | 2 | 嚴格相同endpoint／basis／DFS model |
| 官方WA resource screen | 17 | 17 | 未改政府摘要篩選 |

Jupiter進入Resource＋Strategic後，在三種偏好及三種方法均為第一。Resource＋Study的resource情境，SAW／TOPSIS為Jupiter第一、PROMETHEEII為Nolans第一；development及strategic情境均為Nolans第一。Resource＋Financing中，resource情境為Jupiter，另兩情境為Nolans。這些是面板內條件式排名，不是全澳開發成功率或六構面正式結果。

## Aim B／C：解釋資料選樣與模型效果

R可選第七參數`evidence-cohort-v1`；舊五／六參數路徑不變。`evidence_cohort_sensitivity.csv`要求相同Project、resource scope、共同準則定義及精確相同shared scores；先比較同準則在廣母體與common集合的refit，再比較同common集合的新增準則／權重分配。兩種效應分開，不宣稱純準則因果效應。

- Composition：common10，90個Project×scenario×method格，reference rank變化0，criteria＋weight變化15。
- Infrastructure：common7，63格，reference變化2、criteria＋weight變化25。development情境中，PROMETHEE的Jupiter／Mount Ridley因參照母體20→7互換第一、第二；SAW／TOPSIS沒有這個reference反轉。
- Study：common8，72格，reference變化0、criteria＋weight變化47。
- Financing：common6，54格，reference變化0、criteria＋weight變化28。

上述格數不是獨立Project樣本數。`criterion_contributions.csv`提供SAW與PROMETHEE的加法分解；這是模型數學，不是外部地質關聯。`cohort_missingness_description.csv`以獨立Project彙整可評分／不可評分群組的資源量描述，不推定MCAR／MAR／MNAR。既有deposit-type描述、leave-out、方法／函數／權重／rounding Monte Carlo繼續執行。沒有來源範圍的測量誤差未模擬，排名頻率不是開發成功機率。

`aim_c_technical_features.csv`連結source-bound礦物提及、處理scope／endpoint／scale、品質資訊與排名。礦物提及不等於整個資源的主賦存礦物；多試驗、多zone、不同來源仍是同一Project。技術inventory為749筆：4NUMERIC_COMPARABLE／202DESCRIPTIVE_ONLY／543NOT_COMPARABLE。共同DFS精礦定義仍只有Browns Range／Yangibana兩個獨立Project；正式T1未完成。未做樣本不足或非獨立變數的多變量／因果推論。

## 架構、版本與重建

資料流從「source lock＋現行claims直接匯入」修正為「source lock＋SHA綁定claims契約→來源／scope／validation選取→Coverage／Criteria→既有R」。

- `evidence.py`使用既有configuration的`claims_sha256`讀取不可變契約；從Git原blob恢復六個歷史版本，SHA逐一相符。無需修改既有凍結輸出。
- Current合同的observation ID集合隔離舊metadata，SQLite保留所有歷史列；不刪除／重編Project或source IDs。自動觀測的artifact與validation版本由同一`observation_visible`規則選取，Coverage及差異計數不混入已淘汰的AUTO版本。
- `discovery.py`在原任務加上未解析原件、shared gaps、potential resource-panel gain、可靠來源／endpoint及失敗成本的可解釋優先級；是預算heuristic，不是yield成功率。一次16項有界來源處理（含6項原件重用）中6項HTTP429失敗，其他原件仍處理；既有重試與不可變SHA重用保留。
- `pdf_extract.py`明示v1／v2 parser；v1候選可精確重建。Targeted acquisition只解析選定source keys。沒有新增production module、正式資料表、MCDA引擎、永久queue或人工簽核。
- 原canonical SQLite保留；獨立clean／歷史測試DB均位於可丟棄`work/`。共7,554個entity IDs不變。Census groups31，未聲稱全澳完整。
- 正式186個Gate cells仍無formal admission；72格有部分客觀source facts。沒有新增簽名、crosswalk或正式Panel核准。

Seed20261102、1000draws、Dirichlet concentration30、`entity-keyed-rng-v2`不變。Run ID、實際code content SHA、claims SHA、snapshot/config hashes與測試receipt見 [Phase12 outputs](../results/phase12-2026-11-04/README.md) 及 `data/phase12_research_summary.json`。執行時HEAD仍是Phase11，source content hash綁定實際開發碼，不能把metadata parent Commit誤稱為Phase12實作Commit。

```sh
au-ree-v2 rebuild --as-of 2026-11-03 --snapshot-lock results/phase12-2026-11-04/snapshot_lock.json --work work/phase12-replay
python tools/check_phase11.py results/phase12-2026-11-04 work/phase12-replay/latest.json
python tools/evaluate_documents.py work/phase12-benchmark.json --phase12
```

同環境所有panel CSV及六個evidence／coverage匯出使用零數值容差；只正規化CSV行尾，runtime的R平台描述字串例外。跨平台reference沿用既有static point science1e-12政策，新增靜態contribution／cohort score分解使用相同規則；每個rank、weight、count及MonteCarlo統計仍須精確，不修改凍結結果掩蓋差異。

## 依影響與成本排序的後續瓶頸

1. 取得North Stanmore原PFS/MRE全表，核實新分類、TREO／Sc／Y定義及對舊scope的替代關係；目前mirror逾時，先保存季度再確認及REVIEW，不覆寫舊資源。
2. 修復positioned表頭與跨頁scope／REO definition連結。Cummins P₂O₅、Koppamurra密度／續表、Yangibana多表是可自動化的高價值版型；先降低錯配，才增加通過數。
3. 共同Technical endpoint、test scale、sample代表性與條件仍不足。補取同定義試驗／工程原件；不把Scoping、pilot、單階段浸出與DFS合併。Processing Complexity仍缺可操作化且可比的正式codebook依據。
4. 融資有效期限、CP、counterparty與真正financial close／drawdown原件；現在可評分的是披露milestone，不能用金額或承購補成資金到位。
5. 道路／鐵路7案、port／power20案的官方幾何覆蓋與Project代表點限制；目前只可解釋proximity。另36組deposit配對、112個政府候選、Splinter原件及正式Gate證據仍未解決。

Phase12完成後停止本次自主開發；沒有另設排程或自動延伸下一階段。
