# Phase16：Technical 操作化、來源驗證與研究呈現決策

本次以 Phase15 `b1c36e93652c646ae02dfec7a8dd1234e38b6eff`／Draft PR#5 為基準。沿用同一 CLI、`work/phase5/canonical.sqlite`、Manifest、Selection 與 R 引擎，SQLite Schema 未變；未合併先前 PR，亦不啟動 Phase17。開始時本機與遠端基準一致、工作目錄乾淨。

已參照專案「評估科學成果進度」的 Phase15 審核、提案第7–9張投影片及兩份討論文件。討論文件的 Phase14「885筆」、API能力與序位骨架均未直接當作本階段事實或已驗證量尺。

## 已落地的模型決策

採用 **`PARTIAL_MCDA_PLUS_SCOPED_TECHNICAL_PROFILES`**。Technical 衡量目標稀土的可處理性與處理負擔，回收率、品位、藥耗維持指定給料／終點的分組績效。T-A／T-B目前提供有來源限定的分類與機制描述，**沒有採用全體共同數值量尺**。這已由主 CLI 執行並輸出 `technical_model_decision.json`，不是留待下階段才決定。

規則唯一來源為 `config/evidence_policy.json` 的 `technical_profile`，版本 `technical-burden-profile-v1`。規則先固定再套用；區分正面支持的較低負擔、明確額外需求、已觀察障礙與未知／衝突。不同證據狀態保留集合，不採最高、最新或最差值覆蓋。沒有報告問題不代表低負擔；沒有資料不代表不適用。明示的缺值與 N/A 均不支持物理性能判讀，原值保持 NULL。

T-A的試劑／能量需求與T-B的除雜／殘渣處理分開。相同酸耗不重複計權；研究階段、試驗規模與代表性獨立記錄，沒有DFS、文件數、流程步數或礦床名稱加分。原礦Th/U不是輻射劑量；外包下游亦不代表負擔消失。分類未經獨立專家驗證，額外需求也不是經校準的負擔強度順序。

這項選擇與區分客觀績效及偏好價值函數的[英國政府MCDA指引，2024，Assessing component value](https://analysisfunction.civilservice.gov.uk/policy-store/an-introductory-guide-to-mcda/)一致；它不替本研究自訂分類背書。[JORC2012 Table1 Sections3–4](https://www.jorc.org/docs/JORC_code_2012.pdf)用於核對冶金假設與代表性要求，並非MCDA門檻。[IAEA Safety Reports Series68，2011，§2.4及§3.1](https://www-pub.iaea.org/MTCD/Publications/PDF/Pub1512_web.pdf)按製程、物料流與暴露途徑討論NORM；本次只讀相關章節，未以舊報告替代現行法規或專案劑量評估。

## 資料流與語意修復

原流程以表格格位做案例計算，工程參數及文字另留在Technical audit。現在是：

`原件／表格／Study Parameter／文字 → 同一Selection → unified_observations → 用途契約 → T-A/T-B來源判讀與數值群組 → 部分MCDA及Technical剖面`

`document-recognition-v6-context-bound`保留v1–5重建路徑。新路徑取消由版型取得的試驗尺度、composite給料、Scoping設計及selected-test預設；從原文連結頁碼、SHA與引文，未知保持未知，尺度衝突保留。文件研究階段與物理試驗尺度分開。原生幾何取得移至共用helper，未增加Project名稱／答案值分支。

統一視圖分別輸出：證據是否支持技術判讀、能否進入指定數值比較、能否外推至Project。工程參數、沒有表格格位的Koppamurra／Cowalinya及礦物學敘述均不再因資料形式被排除。`NOT_COMPARABLE`僅表示未符合該用途契約。

每筆保留穩定Project／case ID、來源SHA、頁碼／locator、日期、基準、給料、終點、尺度、原始敘述及規則版本。相同分析紀錄去重；有明示列標記、同來源／頁碼、值與單位的佐證連回原格位。跨基準或標記歧義不強制合併。這不是獨立實驗數估計。

視圖的`study_date`沿用case／揭露的有效日期，不表示未揭露的實驗日；原始`date_role`保留於同一`resolved_evidence.csv`的`raw`，透過evidence ID連回。出版日、產品更新日與資源估計日不互換。

原始來源快照與16份本階段已入庫、但未選入最終lock的開發擷取版本保留。它們是canonical歷史，不計入當期文件、測量或研究輸入增量。

## Phase15→16 實際增量

| 指標 | Phase15 | Phase16 |
|---|---:|---:|
| canonical registry groups／resource-defined cases |31／21|31／21|
| 選取來源快照／已辨識文件 |251／37|254／38|
| 新取得不同SHA的PDF原件 |—|0|
| 有效來源數值觀測列 |703|711|
| Project-selected數值列 |701|709|
| 其中Technical數值列 |550|558|
| 原生技術格位／有效數值格位 |379／371|381／373|
| 資源母體具來源限定性能的Project |9|9|
| 全registry六構面可評分R/S/T/D/I/C |21/10/0/9/19/8|相同|
| Development／Full-evidence／正式C1 |0/0/0|相同|
| 九個MCDA面板n |19/7/8/2/2/10/6/17/2|相同|

711包括兩筆未通過Project身分選取的有效來源數值。新增8列主要是Browns Range格位與既有工程回收率的文字揭露，不是8次新實驗。新增辨識文件為已有原件的Cowalinya年報；沒有宣稱新下載一份PDF。

統一視圖共1,822筆分析紀錄，含381格、34筆Technical Study Parameter及文字等形式。六個明示缺值不支持物理判讀；1,333筆具有來源限定內容，494筆可作指定來源範圍數值剖面。後者涵蓋11個registry Project、其中9個resource-defined Project，不能解讀為494次實驗或11案共同量尺。

T-A與T-B各6案有規則命中的來源限定判讀，兩者交集3案、聯集9案；Project層級可外推分數均為0。260個來源／case／數量／基準／終點群組供局部描述，不能把單案群組當作新增跨案MCDA面板。381個原始格位與6筆自動連結的格位佐證分開記錄，獨立物理測量數保持未知；保留其他已知或可能的重複揭露。

## 案例結果與Aim A／B／C

- **Browns Range**：正式解析讀出第116頁25%精礦品位、84%回收到精礦。這份文件已用於規則修復，現在屬開發／回歸集。
- **Nolans**：La係數連回第45頁腳註，僅適用包含La回收迴路的方案；base case排除，不將0.924改成0。其他係數不自動取得base-case適用性；Yb／Tb方程標籤衝突保留。
- **Dubbo**：負Er值、Central重複25mm、East六欄50g/L及敘述kg/t差異保留。45個欄標對照差值仍是附條件描述，非酸效應因果估計。
- **Cummins**：2023乾給料試劑強度與2026高品位選定composite性能保持不同來源／年份。12個設計試劑強度、6個富集比與2個附條件保留比可重算，未拼成一個Project性能—負擔分數。
- **Donald**：10個物料分支一致性診斷維持原scope，不能變成whole-ore TREO；平行產品不相乘。
- **Koppamurra／Cowalinya**：PFS mine-plan resource-to-final-MREO的68%，與45個偏好composites的84.9%浸出率不共享分母或終點。Cowalinya產品8.4%雜質及來源所述商業規格問題仍保留，不把「首次概念試驗」等同整體Project已無法開發，也不把單階段高浸出率視為全流程高效率。
- **Goschen Central**：與既有VHM Goschen仍無可靠Project關係，維持獨立候選。MINEDEX也沒有以同名或距離替它解決身分。

Aim A已輸出Project×T-A/T-B來源判讀、Unknown原因及比較群組，並重跑既有九面板；142個既有面板CSV與Phase15相同，沒有新增共同MCDA樣本。使用的是資料可用性選出的部分準則母體，存在揭露與研究成熟度選樣偏差。

Aim B沒有採用新的序位數值映射，因此T-A/T-B映射／拆分權重敏感度為**不適用**，而非通過穩健性檢驗；Technical總權重沒有增加。既有AHP假設、SAW／PROMETHEE II／TOPSIS、Monte Carlo、留一準則及母體敏感度重新執行，排名與模擬結果未變。未知不補零、不填中間分、不逐案刪除構面後重新配權；未輸出虛假的全域排名上下界或開發成功機率。

Aim C以原文中的給料、產品、處理及礦物學資訊支持機制比較；沒有先按礦床類型評分再用類型解釋分數。可回答「哪一範圍、哪個處理邊界下有何需求／損失」，不能回答「全澳哪個Project技術最好」或作小樣本因果推論。

## 開發與保留評估

[固定評估結果](../data/phase16_evaluation.json)將兩部分分開：

- 原有核心308格、Donald選定10格、Nolans15係數及已修復Browns2格：共335個固定格位，335TP／0FP／0FN，均為開發／回歸，並非335次測試或通用準確率。
- 未用於本階段規則調整的Koppamurra第11頁兩個回收率語句：2TP／0FP／0FN。採既有PFS-to-final-MREO案例的目的性選樣，已知檔案、非盲測、非全澳隨機抽樣。
- Koppamurra／Cowalinya三項保留來源判讀：僅1項吻合。Koppamurra「removing impurities」與Cowalinya超規格敘述未被目前字面規則轉成對應T-B分類，保持Unknown；未拿這兩份文件回頭調整規則來消除漏判。

因此不宣稱已驗證通用的T-A/T-B量尺。原文、數值與特定終點資料仍可使用；保留集揭露的是自動分類的限制。標註與原頁核對為AI輔助一致性工作，不能稱為獨立專家驗證。

## 集中來源實測

### MINEDEX Resource Estimates by Project

由[官方DASC入口](https://dasc.dmirs.wa.gov.au/home?productAlias=MINEDEX_ResourceEstimatesbyProject)實際讀取目錄、三個advertised roots及CSV ZIP下載，共5個邏輯請求；成功重取且內容SHA不變，整段本機呼叫8.895秒。這是實測耗時，沒有與不同功能的PDF查找流程比較而宣稱節省比例。

ZIP SHA `33b5aeb88ec339adcf0c765b0bb1440ef8978a76b374ef183363283a728bb6e8`；CSV member SHA `9b127f7436c50ec67978313eb9e3c478e0696fff0dbef7a602b158beed3eb8a7`。目錄日期2026-11-03、HTTP Last-Modified為該日19:14:10 GMT，實際取得日2026-11-04不回填。僅在明示取得窗口，且目錄／HTTP日期均不晚於cutoff時納入這個已發布批次產品；一般live GIS不能據此回溯。

原始檔有2,666筆各礦種列、32欄；完整稀土／相關元素篩選取得68個Project–commodity列，對應22個原生Project code。原生`PROJ_CODE`與`LOC_SITE`接回既有22個Project candidate及22個Site，新增68個SOURCE_RECORD及136個來源限定關係，沒有新增獨立Project、Deposit或Site。

408個Resource／Reserve欄位觀測中252個為來源數值、156個NULL，與AUTO_VALIDATED研究數值分開。原單位包括million tonnes、percent及tonnes；保留資源與儲量、不同commodity及原始單位，不跨列加總。資料字典說明資源為Measured＋Indicated＋Inferred總量，並無分類拆分；2,666列的`EXTRACT_DA`皆空白，沒有原始估計日期。「Rare earth oxides」亦未界定Y是否包含。因而只作官方結構化核對，不等於原始JORC或選冶試驗，未擴大Resource-defined或正式準則樣本。

ZIP包含授權、metadata與資料字典，原始回應／取得時間／SHA沿用Manifest；出版檢查實際解開CSV與PDF檢查。這是西澳資源產品，沒有把MapServer/0礦點索引或西澳覆蓋宣稱為全澳Census。

### WebLink

[官方API文件](https://datadirector.weblink.com.au/knowledge-base/weblink-data-api/)已真實取得並封存SHA，核實`year`、`headlinesPerPage`、`pageNumber`等文件參數。但文件提供相對路徑，沒有確認本研究可用的正式服務origin、認證、研究授權、歷史涵蓋及分頁終止語意。

固定目標為NTU2025 Browns Range DFS及REE2023 Cummins Scoping。公司／年份索引測試為**NOT_EVALUATED_ACCESS_CONDITIONS_NOT_ESTABLISHED**，找回率為NULL，不能當成零筆公告或Live成功。沒有猜測API base URL、使用模擬回應、寄信或購買。需由服務商提供上述條件後才可測量同一目標集的取得效率；目前無法估計節省時間。InvestorHub／Investi仍僅作補充線索。

## 維護性、驗證成本與重現

沒有新增正式資料庫、Schema或runtime模組。共用用途gate處理不同形式，原生幾何與科學語意分離；規則集中在同一policy，不維護第二份codebook設定。V6快取同時檢查來源SHA、Project來源關係、registry、解析版本、PyMuPDF版本及parser／語意實作相依雜湊。

[AST量測](../data/phase16_maintainability.json)使用相同演算法比較兩版：`recognize_document`由116行／90個分支節點變為118行／88節點；`cli.execute`377／130變為387／136。這裡的分支包含BoolOp與comprehension，不能與Phase15另一種分支計數直接比較。語意與觀測視圖增加了程式量，不能宣稱總複雜度下降；改善在於責任界線與共用條件，CLI仍是集中點。

驗證分為日常受影響測試、PR完整Python／R與相關重建、核心契約／封存完整歷史及當期兩次clean。開發分支Push不再另跑同一整套；PR保留既有`research` job。核心src／R／config變更會自動擴大到歷史與當期兩次clean；舊版各重建一次並比對凍結參考，不再每個歷史版本各做兩次clean。手動archive入口仍保留，Live job與離線重建分開。

[先前CI實測](../data/phase16_validation_baseline.json)：Phase15 Push runner883秒、PR runner1,408秒；兩者重疊，不能把合計2,291秒當使用者等待時間。Phase16最終runner各步時間與CI結論以本PR checks／說明為準，沒有先承諾固定加速比例。舊版參考仍保留既有1e-12靜態點值容差；排名、RNG及Monte Carlo不新增容差。

[完整性紀錄](../data/phase16_integrity.json)：500個選取來源／原始回應檔SHA、380筆原Manifest紀錄及7,555個原ID保留；新增68個SOURCE_RECORD後共有7,623個ID，SQLite integrity及外鍵通過。來源格位、SourceRecord、Project candidate與獨立Project分開計數。

凍結輸出中的長期canonical證據歷史以`logical_database.json.gz`無損保存，CLI仍在work產生原生JSON。壓縮只為符合單檔出版限制，不是第二資料庫；原始JSON SHA與大小記錄於summary。長期canonical保留未選取版本，不能宣稱與只含研究lock的clean歷史列完全相同；當期選取結果比對與兩次clean邏輯資料庫一致性分開驗證。

本機最終233項Python測試通過（349.972秒），新增18項Phase16測試；R三組invariants亦通過。Phase15歷史回放的142個panel CSV、7份既有evidence及7份Technical輸出一致，沒有本機浮點差異。當期兩次clean與GitHub全歷史驗收的實際結果記錄於研究摘要與本PR checks；未執行項目不宣稱通過。

當期兩次獨立clean已通過142個panel CSV＋7份既有evidence＋7份Technical＋7份Phase16輸出exact比對，兩個clean邏輯資料庫SHA亦相同；canonical的當期科學輸出與clean一致。236個凍結輸出雜湊及壓縮歷史解壓SHA已驗證。八份解析快照經相依雜湊檢查後重用0.450秒、Manifest位元未變；這與首次八份解析52.097秒是相同來源集的不同快取狀態，並非公告取得效率提升百分比。

正式T1、TC1/TC2、C1六項Gate及既有權重均保留。未解的來源身分、共同尺度、可信測量不確定性及保留集T-B漏判仍是限制；它們沒有阻塞其他案例。

重現命令及可編輯CSV／SVG見[Phase16結果](../results/phase16-2026-11-04/README.md)。當期量化增量與完整驗證紀錄見[研究摘要](../data/phase16_research_summary.json)。
