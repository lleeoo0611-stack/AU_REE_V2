# Phase 21 — 架構整合、效能與 National Census

研究截止日 **2026-11-05**；`research-v7-national-disclosure-incremental`。Technical 維持 `technical-disclosure-transparency-v1`，七項二分規則、固定分母7。以下是探索性篩選，衡量包含資訊透明度的綜合條件，不是純技術能力、開發成功率或全澳投資排名。

## 實際資料增量

| 指標／計數單位 | Phase 20 | Phase 21 |
|---|---:|---:|
| Canonical 登錄群組 |31|32|
| 原始 PROJECT 實體列（未視為獨立礦業 Project） |32|33|
| 指定政府來源原始紀錄，含來源間重疊及 tenure |149,599|149,618|
| 政府原生廣義候選實體，含礦物／文字提及及 Sc-related |712|728|
| SITE |763|779|
| PROSPECT |179|186|
| OCCURRENCE |245|254|
| DEPOSIT |296|296|
| PROJECT_CANDIDATE |122|124|
| Resource-defined cases |21|21|
| 原始 PDF／HTML（選定版本） |71|72|
| 來源快照（選定版本，含衍生擷取） |276|278|
| 六構面完整點值案例 |3|5|
| 正式 C1 核定 |0|0|

六準則的點值覆蓋，分母是當期群組而非全澳獨立 Project：**R21／S11→13／T20／D8／I19／C7**。T 是20個完整點分數及12個未知範圍；224項判定為83充分揭露、4明確揭露未知但達標、69未充分揭露、68尚無法查核。未知未補零或中點。

本次實際刷新9個州級來源及 GA AIMR。WA MINEDEX、TAS MRT、SA developing／major project lists 保存4個新版本；NSW、NT、VIC、QLD指定來源與 SA CSV 為未變更或304，GA未變更。QLD其他既有圖層／title快照的時點另列，不能把它們當成本次全數刷新。完整讀取指定服務不等於全國普查完成。ACT尚無專用礦產 adapter；Jervis Bay、Norfolk、Christmas、Cocos (Keeling)、Ashmore and Cartier、Coral Sea、Heard and McDonald及 Australian Antarctic Territory 未分別完成查核，不作零紀錄宣告。

新增 **Barkly Rare Earths Project**，原始 IPO 公告明示其與 Vanadis、Benmara prospects 的關係，建立2條來源核實包含關係，不拆分或加總資源。公告40Mt×2,100ppm約84kt，另報82kt；保留三個原值及品質衝突，沒有放寬精度強迫其進入 R1。詳細招股書403、issuer首頁429，取得公開 ASX 原件鏡像後仍保留未核實項目。Buntine、其他公司的 peer表與企業IPO資金均未移植為 Barkly 的六構面點值。

既有跨來源待確認配對 **36→36**，沒有宣稱全部解決。新增關係主要是可追溯的 native memberships 及 Barkly 兩個明示 prospects；名稱／空間配對仍僅是候選。31個原有群組 ID 全部保留。

## 進入排名的新增證據

- **Cummins Range S1=22.8%**：2023-05-01原始資源公告PDF第2頁，MRE-based distribution 的 Nd、Pr、Tb、Dy氧化物比例；不是價格或 basket-price權重。
- **Nolans S1=26.78%**：2019 DFS PDF第37頁 Table12的 Total欄；同一2017-06-07 M+I+I資源。原有56Mt、2.6%資源量與品位不變，改綁原始DFS第15頁，避免跨來源混配。
- 8個報告組成值與其轉換／定義紀錄共14列；TREO分布的一百萬ppm分母是**數學定義**，明標非新量測。不是14次獨立測量。

五案為 **Jupiter within Brothers、Goschen Area1、Koppamurra、Cummins Range、Nolans**。新增完整樣本全部來自既有群組補件；新發現的 Barkly 尚未成為完整排名案例。完整性只指目前六個採用準則，不代表完整 commercial/ESG 或正式 C1。

資源及戰略情境：三方法均由 Nolans居首。開發情境：SAW／PROMETHEE II由Nolans居首，TOPSIS由Goschen Area1居首。三個舊案例的固定效用及 SAW／TOPSIS分數一致；新增案例插入、共同案例次序逆轉與 PROMETHEE母體效應分列於[母體比較](cohort_rank_changes.csv)。

三情境、每情境1,000次偏好抽樣、方法／函數／留一準則／母體敏感性沿用原R引擎。來源四捨五入界限已傳入透明度專用面板，與未知外包絡及權重抽樣分開。35個已採用項目逐一翻轉0/1的[編碼壓力測試](disclosure_coding_sensitivity.csv)中，有31組「情境×方法×案例×項目」改變首位集合；是反事實壓力測試，不是實際改分、誤差率或信賴區間。Nolans／Cummins原件定位、欄位、適用範圍與原判定均複核，原七項編碼保留。

Aim C仍限描述：T與D共同點分數n=7、Spearmanρ≈0.209；不能推論因果或不存在重疊。去除D／T的權重分析另保留，樣本量不足以支持全國統計推論。

## 程式與效能

當期資料流：原件／來源選取 → 同一SQLite與穩定ID → 透明度來源查核 → `prepare()`一次建立矩陣與記憶體trace → 同次選取建立透明度分析 → R → 排名後研究描述。

移除重複的凍結baseline組裝、CSV讀回、hierarchy建置與整份readiness重跑。商業覆蓋是R所需的前置資料，獨立計算一次並與後置研究描述共用。實體配對先依州／正規名稱分組，再套原規則。SQLite新增存取索引及WAL，無新正式資料表、無第二套registry或MCDA引擎。當期發現與文件辨識讀取同一資料庫；claims保留為來源編碼與alias覆寫。舊`_unified_observations_v1()`仍是共用標準化相依，不能依名稱刪除；凍結設定的相容路徑保留，當期不自動重跑歷史版本。

資源範圍先登錄再產生 canonical membership，關係在身分規則執行後讀取，避免第一次建庫少列範圍。代表點關係鍵包含來源版本，並辨識既有舊鍵，讓更新版本與重複匯入都能正確保留。歷史稽核資料不清除：累積庫仍含舊 Nolans 資源聲明綁定、歷史範圍及已處理待查紀錄；乾淨重建只載入鎖定輸入。因此不可把所有稽核表或 SQLite 檔案宣稱為逐位元相同。正式選取資源、群組、矩陣及排名另行比對，差異明細見發布驗證收據。DEPOSIT_SCOPE 的26個保留ID包含舊版綁定，不是26個獨立礦床或本次新增資源。

來源頁面快取綁定原件SHA、pypdf版本、頁碼及參數；仍先驗證原件。R快取綁定矩陣／界限、準則、權重、同批面板、商業覆蓋、R程式／版本、種子、抽樣數與方法；用`--vanilla`隔離啟動設定。命中時明報重用、驗證完整輸出SHA；權重、原件或快取毀損的失效測試通過。Unknown、0與不同選冶終點的規則不變。

[效能收據](performance.json)：同一Phase20資料庫三輪實體解析，中位 **16.02→8.45秒**，範圍12.89–20.19／7.28–10.48秒；結果雜湊、455次SELECT及9,589回傳列一致。該步驟Python程序峰值約198MB，沒有記憶體下降證據。暖重跑pypdf解析112→16次，透明度組裝／readiness／hierarchy各2→1次。

實際Phase21五案、16面板、1,000次抽樣的R階段三輪：冷快取中位 **68.92秒**（64.21–79.33），暖快取 **3.75秒**（3.51–4.53）；16次R分析啟動→0，仍做版本查核。非R輸入的metadata變更重跑中位2.30秒。九次科學CSV逐位元一致。這是**R階段約18.4倍**，不能套成全流程。擴張後一次離線完整主流程約123.91秒。端到端開發量測同時有其他工作、且跨中間修訂，完整提供原始數據但不作受控整體加速宣稱；全流程及R子程序峰值RSS未量測。增量政府API目前仍完整讀取指定清單再比對版本，不宣稱已完成伺服器端變更流。

## 驗證、篩選品質與重建

[72列參考集](../../data/census_validation_v1.json)依完整州別／文件群組分割41／31列，含同一QLD native ID的重複來源列，不是72個獨立Project。標註是單一代理查讀原始欄位、在初版實作後封存，**不是盲測或獨立gold standard**。廣義候選與排除Sc-only的REE候選混淆矩陣分別提供於[驗證結果](census_validation.json)。不計全國recall，不用大量無關配對聲稱identity accuracy；身分配對與數值綁定尚無獨立完整參考母體。

306項Python測試、R五類不變量通過。Phase20八份科學參考檔重建一致。執行／快取紀錄仍保存SHA，但與科學CSV分開比對，不能把重用紀錄要求成新一次執行紀錄。最新兩次乾淨重建與CI狀態見[發布驗證](release_validation.json)，不沿用舊head的CI成功。

```sh
au-ree-v2 all --as-of 2026-11-05 --work work/phase5
au-ree-v2 rebuild --as-of 2026-11-05 --snapshot-lock results/phase21-2026-11-05/snapshot_lock.json --work work/phase21-replay
python tools/check_replay.py results/phase21-2026-11-05 work/phase21-replay/latest.json
python tools/evaluate_census.py --out work/census-validation --reference data/census_validation_v1.json
python -m unittest discover -s tests -v
Rscript tests/test_methods.R
```

既有正式庫是`work/phase5/canonical.sqlite`；其他work目錄只用於量測／驗證。review以SHA封存，設定與原件lock可重建。來源發布日、資源／事件有效日、擷取日分開；政府原始資料未揭露的有效日不冒充資源日期。取得收據的個別請求僅保留本次日期與耗時，未虛構精確UTC秒。

Proposal沿用Phase19已核定文字調整：Technical寫作資訊透明度，總排名寫作包含資訊透明度的綜合評估，Commercial限披露融資里程碑；研究者權重不稱專家elicitation，未知範圍不稱信賴區間。原proposal及`sources/`唯讀資料未修改。尚需增加國家級新發現的完整案例、取得Barkly詳細原件並釐清資源算術、處理36組身分候選、取得REMP原始workbook及ACT／其他領地來源、建立獨立驗證集。
