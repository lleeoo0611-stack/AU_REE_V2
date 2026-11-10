# CSV分類對照與封存元素表專項（2026-11-11）

同一隔離分支，基線47232f71。**93筆研究列、53欄不變；新增41格，填值1,944→1,985，空白2,985→2,944。**全數為本輪開始前已存在專案的補值；新增專案0、其資料格0。研究列不等於獨立礦案，Yttria與Mt Stirling重疊資源不加總。本專項不是第21輪，未增加完整搜尋輪數或收斂連續輪數。

| 新增類型 | 格數 | 說明 |
|---|---:|---|
| 使用者CSV分類對照 | 36 | 礦床型態代碼28、開發階段代碼4、開發階段類別4；涉及31案 |
| 衍生數值 | 4 | Dubbo Y2O3重量、已核實元素數、部分元素總和、部分元素總和/TREO |
| 科學資料說明 | 1 | Dubbo部分元素一致性說明，未宣稱15項閉合 |
| 直接公布的總表數值／新增專案資料 | 0 | 原件新增核實一個品位輸入1,400ppm，總表採用其衍生kt，不冒稱直接公布kt |

## CSV來源與對照邊界

本機使用者指定原檔為31,375 bytes、92筆、52欄，SHA-256 `cadf4b7068d4be5a090d803bbc7c747314c9aa601f51e7bbe1296797a756f5ad`。完整位元組副本在私有`work/attachment-elements-20261111/template-original.csv`，與本機原檔雜湊一致，未由擷取文字重建。**本執行環境未提供Library附件下載工具，未核實Library附件和本機原檔逐位元相同，也未聲稱已完成Library物化。**本機檔案是使用者先前明確指定的同名來源。

核實詞彙：hard=硬岩型、iac=離子吸附型黏土、placer=砂礦型；A1/A2/A3=探勘（初期探索／資源調查／細部探勘）、B1/B2=評估（初期可行性／經濟評估）、C1/C2=開發（最終投資決定／建設中）、D3=開採（產能達設計目標）、X1/X2/XX=暫停（尋求合資／超過4季未更新／中止）。完整原詞彙在`config/user_template_mapping.json`，不含附件專案原始資料列。

採用明確礦床型態與明示early/initial exploration的A1對照。未將一般clay/regolith推成IAC；未將一般Exploration推成A1/A2/A3；未將Operating或started production推成達設計產能D3；未將scoping/PFS/DFS標籤自行等同附件未定義的B1/B2界線。64種未明確對應原文列於`unmapped_classification.csv`。原生文字、日期及原有代碼保留。實際DRAFT分類表、approved_by、approved_date與其雜湊均未改變。新對照僅作用於明列完整原文，且新來源紀錄保留原PDF來源及CSV詞彙來源雙重雜湊。

## 已封存PDF的元素擷取與科學核對

實際掃描25個元素資料不完整研究列所關聯的45份封存PDF，共2,615頁；以JORC Table1、oxide distribution、完整氧化物式、Unicode下標及字距變體辨識194個候選頁，抽出252個原生表格。無表格擷取錯誤；無可辨識表格時保留原生文字位置，未猜補欄位。沒有安裝Camelot/pdfplumber，使用既有MuPDF表格與文字定位能力。PDF、表格全文與影像留本機，不推送。

**194個候選頁不代表252表均已完成新的逐格科學審查。**原始資源範圍、類別、截止品位、版本、日期、REO basis、樣品／產品身分或分母不明者不晉升。沒有只因噸數品位相近而跨文件合併。既有個別氧化物已齊但合計尚未計算的缺口為0；原投影已有完整集合衍生邏輯。

新增Dubbo：同一已選用原PDF（SHA `734d9ea3…04218ab`），實體p26／Table2／2017 Toongi總資源列。Y2O3欄表頭明示ppm；Total列75.18Mt、1,400ppm。原生行列交點及整頁影像已核對，並保留儲存格範圍與影像SHA。計算`75.18 × 1400 × 0.001 = 105.252 kt Y2O3`。未借用42.81Mt Measured子集、選冶複合樣或分類列Nd/Pr平均值。原表TREO7400ppm不含Y；現有canonical8800ppm含1400ppmY的轉換不變。原表只核實資源年份2017，新紀錄明列年精度與繼承的canonical版本日期，未冒稱原表重新核實完整2017-09-19。未核實的新截止品位不跨文件帶入。

Wudinna僅補強原件：p3 Table1確有112ppm四項磁性氧化物合計，p15核對品位單位。但總表已有磁性合計及占比，**新增0**。原有16.7761702128kt以公布70.4kt TREO乘112/470計算；另一種以捨入150Mt×112ppm所得16.8kt不是新增資料，不替換原值或來源。此差異及中途統計更正均在來源review config記錄。

排除或持續待審的例子：Cummins舊519Mt版本組成不套用現524.3Mt版本；Jupiter僅分類／子區域氧化物不合成全球總數；Circle Valley只有合併NdPr，不能拆成各別Nd/Pr；Goschen Area1缺Ho/Lu，其他區或公司總數不補入；Brockman原生Ce2O3不改名CeO2；轉換係數、稀土價格表及產品／樣品分配不作資源組成。逐案原有來源限制及本次新增見`element_project_review.csv`，未逐格完成的新候選繼續待審。

## 缺口與政府端點

剩餘2,944格：UNKNOWN2,579、PENDING_CODEBOOK242、NO_COMPARATOR_SOURCE93、NOT_APPLICABLE_STAGE30。原始覆蓋率`1985/4929 = 40.27%`；沿用原123格排除規則後`1985/4806 = 41.30%`。分母規則、Census、既有資源量／品位／年產量及座標未改。年產量未新增，主要缺相容工程研究的明確年平均與產品氧化物口徑。

政府資料只交付[端點＋授權＋欄位對照](../../docs/GOVERNMENT_LOCATION_ENDPOINTS.md)，包含WA、GA、SA、QLD、NSW、NT的現行metadata與待查項。各庫屬性CRS與geometry CRS不同，不能混用。接入與填座標待使用者確認。沒有猜測未提供的第3項工作。

## 測試、保護與重建

專項測試29項＋8子案例、既有受影響回歸434項＋353子案例，全數通過，0失敗／錯誤／跳過。兩組有重疊，不能直接相加當獨立測試數。最初暫存目錄權限錯誤經正常本機權限重跑；測試資料缺review ID已補正。另已核對實際原件的行列、來源SHA與來源擷取收據。跨範圍、版本、類別、日期、截止條件、REO basis不同時拒收；浮點容差僅絕對1e-9，不能通過實質資料差異。

兩次完整來源離線重建，再各自執行一次獨立元素新增投影，四個CSV及兩份完整summary/audit均相同。核心重建啟動時尚未將mapping hash列入wrapper清單，兩份summary已記錄相同mapping hash；補充重建收據明確綁定該hash，不偽造原始核心收據。

全部原有1,944格數值與逐格來源紀錄均保留；inventory位元組相同；947個實際存在的歷史結果／來源設定檔雜湊不變。另3,886個歷史Git路徑未在稀疏工作樹展開，未冒稱已逐檔讀取。Census SHA保持`99ed9c0fc004960f92680ee782ef8764c189a08d98bce4d14c2d0e5ad99091d0`。無ASX請求、無403繞過、無付費或登入來源、無新專案或合併。

重現命令（PowerShell，先放置上述SHA一致的完整CSV至config指定本機路徑；每次使用新的輸出前綴）：

```powershell
$env:PYTHONPATH='src'
.venv/Scripts/python.exe tools/reextract_archived_elements.py --out work/new-element-scan
.venv/Scripts/python.exe tools/rebuild_asx_census.py --out-prefix work/new-mapped-replay
.venv/Scripts/python.exe tools/apply_archived_element_additions.py --before work/new-mapped-replay-a-53 --out work/new-final-a
.venv/Scripts/python.exe tools/apply_archived_element_additions.py --before work/new-mapped-replay-b-53 --out work/new-final-b
.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/test_asx_template_mapping.py tests/test_asx_classification.py tests/test_archived_element_additions.py tests/test_asx_rebuild.py
.venv/Scripts/python.exe work/asx-fullscope-20261110/run_tests.py --affected
```

報告工具需本專項基線收據與`final-approved-a/b`本機資料夾（名稱不表示codebook核定）；`--publish-current`僅在舊欄值／來源、保護雜湊、測試及兩份重建均通過後更新現行表。歷史round1–20與舊輸出不重寫。
