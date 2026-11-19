# 澳洲稀土 Census 整合證據模型審查版

本次新增 **Voyager 的礦床型態描述 1 格**，可追溯至 2023-08-14 的靜態 ASX 公告實體第 3 頁。該頁將黏土與鋁土礦定位到 Voyager 礦權，旁述的資源量與浸出試驗屬於相鄰專案。收據記錄本機於 2026-11-19 取得原件，依既有「文件公開日」規則納入 11 月 13 日截面。此值僅描述其勘探地質背景。[Census 總表](REE%20project%20census.csv) · [逐格差異](coverage_delta.csv) · [來源選入與日期角色](source_selection.csv)

| 項目 | plan620 | 本次 |
|---|---:|---:|
| 穩定 Census 專案 × 欄位 | 93 × 51 | 93 × 51 |
| 有值 | 2,456 | 2,457 |
| 不適用 | 1,709 | 1,709 |
| 待補證 | 578 | 577 |
| 選定資源估算組／完整 TREO 案例 | 38／37 | 38／37 |
| MCDA 排名面板／現行六構面案例 | 16／5 | 16／5 |
| 正式 C1 核准案 | 0 | 0 |

沒有新增 Census 資源量、品位、年產量、座標或公司身分值。已有值的 37 格補記來源範圍，涉及 29 格礦床型態代碼與 8 格開發階段代碼或類別；既有值及其原件相同。沒有改值、撤回、重開或新判不適用。另有 5 筆資源長表觀測補錄原有 cutoff 文字。[欄位狀態](field_status.csv) · [研究差異](research_comparison.json)

| 待補證原因 | 格數 | 可採用的下一份證據 |
|---|---:|---|
| 已選估算缺欄位輸入 | 363 | 同估算版本、日期、範圍、分類和 cutoff 的資源／組成表，含該元素或可重算的輸入。 |
| 部分基準或組成 | 5 | 同物料的分母、化學物種、基準與必要組成。 |
| 缺可用專案代表點 | 82 | 適用截日的官方圖徵、完整專案範圍、角色、CRS 及精度。 |
| 缺可比年產預估 | 56 | 同開發情境、設計規模、年度和產品基準的已揭露預估。 |
| 分類所需證據不足 | 41 | 有效原文對應範圍和既有分類定義，再按核准對照表映射。 |
| 尚無核實來源值 | 30 | 補入可定位到穩定 Project ID、公開日期及原頁的來源值。 |

Nutgrove 的昆州 EPM 28000 有 2026-11-03 官方凍結界線，礦權代表點距最遠頂點 8.10 公里，低於原門檻 25 公里。發行人 2026 年公告 p.10 支持當期勘探範圍，仍缺截至截日的完整專案礦權範圍。Barballin 有 E70/6146 的案號，尚缺適用版本的正式西澳礦權邊界。兩案經緯度續列待補證。[逐格缺值](missing_fields.csv) · [空間來源與精度](spatial_point_quality.csv)

363 格選定估算缺值分布於 21 筆專案列，涉及 15 種氧化物的 266 格及合計、占比等衍生欄位的 97 格。Fingerboards、Lyons 12/13、Aileron、Charley Creek 和 Mt Weld 各缺 24 格；Mangaroon Yin、Yangibana 和 Mons Block 3 East 各缺 23 格，八案共 189 格。另 5 格部分基準全在 Wimmera WIM100。其原件分列 540 Mt 整礦、25 Mt 重礦物及重礦物組成，仍需同一估算的整礦 TREO 數據。[缺值與來源](field_status.csv)

只有 **Dubbo 和 Yangibana** 現有五項可用的六構面準則。Dubbo 缺技術揭露的單點分數 T1；Toongi Phase B 堆浸試驗原件有加酸單位、重複欄題和 Dy 37.7%／37.3% 三處歧義，現行技術揭露區間為 57.14–71.43%。Yangibana 缺 S1，須取得對應 2026-06-30、100% 合資總資源估算的 Nd、Pr、Dy、Tb 氧化物占 TREO 或同基準可重算組成。若找到符合截日的來源且其他條件相同，可分別增加一個探索性六構面案例。若新公告晚於截日，應在新的研究截面評估。[93 案六構面上下界及已知值](disclosure_composite_matrix.csv)

## 研究母體與排名

SQLite 有 7,845 個已登錄實體（含 5,525 個礦權、301 個礦床與 94 個 Project 節點）。Census 的 93 筆發表列依穩定 Project ID 核對。39,517 筆觀測中，2,882 筆為 AUTO_VALIDATED、35,617 筆為已登錄政府原始紀錄、558 筆為範圍待核的官方摘要、460 筆待審。資料庫有 328 個依來源分開的資源陳述脈絡、1,210 筆相關事實、9 個技術研究案例；Census 資源長表可選用的觀測有 519 筆。[驗收紀錄](verification.json) · [資源長表](resource_statement_observations.csv)

**Aim A**　16 面板樣本數分別為資源－基礎設施 pilot 17、發行人資源－基礎設施 6、六構面 5、六構面揭露 5、發行人資源組成 10、WA 官方資源 17、發行人資源－研究 7、發行人資源－融資里程碑 8、發行人資源－精礦 2、含回收率 2、選礦精礦篩選 2、技術精礦固定尺度 2、技術精礦樣本尺度 2、僅揭露 20、資源揭露 14、資源－港口－揭露 12。每一列的納入依據可回查。歷史 Phase 22 的 33 群組、22 資源案例與 6 個完整案例另有凍結版本。[逐案面板判定](mcda_panel_decisions.csv) · [六構面排名](MCDA/six_domain_disclosure/ranking.csv)

**Aim B**　相較 plan620，16 面板共 160 份矩陣、準則、權重、三法排名與穩健性輸出逐項雜湊相同，318 條準則追溯相同。獨立重跑也逐檔相符。蒙地卡羅使用同一種子 20261102、1,000 次抽樣。46 筆距離仍缺同範圍可比較的第二點，涉及 5 個空間面板；目前無法從實證估計更換點位的排名效果。[各面板輸入與差異](research_comparison.json) · [GIS 檢查](census_gis_rank_sensitivity.csv)

**Aim C**　六構面 5 案都有已選資源估算且具完整 TREO，現行分期為 B1 兩案、B2 三案。其餘 88 案有 33 案選到資源估算，其中 32 案有完整 TREO。兩組已填欄位引用的不同 PDF 版本數中位數為 3 和 2。這顯示排名母體受到揭露程度與成熟度的選樣影響；本版僅作描述。[逐案礦床、地區、資源與來源分布](aim_c_availability.csv)

## 同一流程在 GitHub 即時取件時的差異

研究主結果採用已固定日期、版本和 SHA 的原件套件。GitHub Clean 以公開來源重新取件，網路判定通過，235 個來源中有 1 個網路錯誤（0.43%）。兩者均通過各自的建置驗證。獨立核對的 25 份資料及排名檔與當次完成收據相符。[實際來源、面板與排名比較](public_clean_acceptance.json) · [GitHub 原始驗收產物](https://github.com/lleeoo0611-stack/AU_REE_V2/actions/runs/44604405484/artifacts/14573153055)

| 同為 93 案 × 51 欄 | 固定原件研究版 | GitHub 即時公開來源 |
|---|---:|---:|
| 有值／不適用／待補證 | 2,457／1,709／577 | 1,524／1,291／1,928 |
| 選定資源估算組／完整 TREO | 38／37 | 18／18 |
| Census 通過身分篩選 | 93 | 74 |
| 至少進入一個面板的不同專案／專案面板成員次數 | 31／131 | 32／142 |
| 六構面探索面板／正式 C1 | 5／0 | 6／0 |

即時來源的 1,928 格待補證分為來源未取得 1,370、規則輸入缺 487、沒有來源值 49、SHA 已變 14、截日後 8。固定套件的組成、日期與內容決定可重現的研究截面。把輸入換成即時來源，16 個面板中有 8 個的成員或名次不同，另 8 個一致。三個面板共四組「情境 × 方法」的榜首有變化。

即時六構面比固定版多 Cummins Range 一案，其餘五案相同。即時面板的資源與磁性占比來自 2023-05-01 的同一估算，範圍為 Rare Dyke 與 Phos Dyke 合併、P₂O₅ cutoff 2.5%，分別採 1,646.181 kt TREO 及 22.8%。固定版資料庫保有 2023-05-01 的 519.3 Mt、0.317% 與 2024-01-25 的 524.3 Mt、0.312%。Census 採後者；MCDA 的範圍審查保留 MULTIPLE_SCOPES_REQUIRE_DEFINITION，R1、S1 均未形成單點。GitHub 此次取得 2024 文件時遇到 HOST_STOPPED:NOT_PDF，2023 原件則以符合 SHA 的快照納入。即時環境少了一份原件，恰好未觸發同一項範圍歧義，因此形成第六個探索樣本。兩版正式 C1 都為 0。[固定版準則矩陣](disclosure_composite_matrix.csv) · [即時建庫驗收](public_clean_acceptance.json)

| 面板與情境 | 方法 | 固定原件榜首 | 即時來源榜首 |
|---|---|---|---|
| resource_infrastructure_pilot，development | PROMETHEE II | Mount Ridley–Central Mia | Splinter Rock |
| resource_infrastructure_pilot，development | TOPSIS | Jupiter（Brothers 內的開發研究） | Splinter Rock |
| resource_disclosure，resource_assumption_with_T | PROMETHEE II | Jupiter | Mt Weld |
| resource_port_disclosure，development_assumption_with_T | PROMETHEE II | Koppamurra | Cowalinya |

## 此版的驗收與重建

- 開發基準 `a03cfb194a0e8ab2d9a441e4a1b6ea14e86ead61`，科學重播提交 `4c3a94e606d109f52cecc942acec48c64d8f648e`，設定 SHA-256 `35f2723687eab87223e250c72c53b88308b3a90705d047497d55958a1f34b3be`。後續 `d2bc53b` 修正 CI 產生註解副本，`ec23344` 修正可攜清單的原件歸屬，`5d83732` 修正歷史公司標記在整合版中的稽核範圍。[草稿 PR 與當期 CI](https://github.com/lleeoo0611-stack/AU_REE_V2/pull/13)
- Census 截日 2026-11-13，技術編碼基準 2026-11-05，正式 C1 政策截日 2026-10-29。公告公開日、封存收據日期和本次取得時間分欄。[發布收據](census_release.json)
- 一次從乾淨 checkout、空白工作目錄及指定的原件庫建庫，全程來源重播禁止 Python 網路連線，產生 SQLite、Census、完整 R 與 16 份排名。另一個工作區獨立產生相同總表和 160 份面板研究檔案。唯讀匯出的 14 份 CSV／JSON 與建庫輸出逐位元相同，coverage 的差異僅為執行識別／資料庫雜湊欄；唯讀前後的 SQLite 位元組相同。SQLite integrity 為 ok、外鍵違規 0。歷史 Phase 22 的 64 份檔案通過既有比較規則。[重建指令與環境](../../../README.md) · [驗收明細](verification.json)
- 乾淨科學提交實跑 560 項 Python 測試。後續打包及 CI 修正另跑 18 項相關測試（與全套有重疊）。R 五組數學與分組檢查通過。舊庫連續遷移兩次，五個核心資料表內容一致，716 個已填資源欄位均能解析其證據輸入。[驗收紀錄](verification.json)
- 線上探測有 50 個 DNS 成功。六筆 ASX 測試中，Browns Range、Mia、Yttria 的靜態 PDF 均取得與封存相同的 SHA；另一主機首筆回 HTML，其餘兩筆依規則停止。Voyager 按離線原件政策重播。本機另對 234 個來源執行全量線上取件，64 個直接下載且 SHA 符合。29 個有網路錯誤標記（12.39%，既有上限 5%），判為 RUN_INVALID_NETWORK，未進入本版建庫。詳見[線上逐來源收據](live_acquisition_report.csv)及[網路判定](live_network_status.json)。最終程式提交 5d83732 的 GitHub Clean 與 Research 均通過。Clean 執行 568 項測試，70/70 公司標記通過原頁驗證。[GitHub Checks](https://github.com/lleeoo0611-stack/AU_REE_V2/pull/13/checks)
- 開發時曾遇到舊 checkout 路徑長度與暫存資料夾權限限制，改用短路徑及新建的可攜套件完成獨立重播。初次 GitHub Clean 也揭露孤立資料庫讀取設定、搬移後仍可讀舊路徑、環境套件資訊誤判等三項回歸。後續修正加入封閉失敗、搬移測試及環境版本讀取。最新版 GitHub Research 已通過 562 項測試、R 及兩次 Phase 22 重建。[早期失敗](https://github.com/lleeoo0611-stack/AU_REE_V2/actions/runs/44590433142) · [最新版 Research](https://github.com/lleeoo0611-stack/AU_REE_V2/actions/runs/44594143506)公開 Git 只交付原件清單與來源收據，重播的保管人須另提供 1,268,847,893 bytes 原件套件。[原件清單](asset_manifest.json) · [重播輸入收據](source_acquisition.json) · [套件雜湊](bundle_verification.json)

本版公司標記稽核仍會重建 v10 的整份凍結聲明。對整合線，另驗原 70 筆簽核的 Project ID、欄位、來源、SHA、頁碼和標記，再核對本次總表實際選入的證據。原版工具比較整份當期聲明時，因後續歷史更新而誤判；`5d83732` 修正適用範圍。以本機 35 個不同原件頁面重驗，70 筆簽核全部通過，已選來源相同 70 筆、取代 0 筆，另通過 15 項相關測試。最終程式提交的 GitHub Research 實跑 568 項 Linux 測試、兩次 Phase 22 重建與發布檢查，全部通過。GitHub 前次 Linux 建庫的 4 份來源／設定／追溯檔也通過雜湊比對，70 筆簽核均對應同版原件。[最終 Clean](https://github.com/lleeoo0611-stack/AU_REE_V2/actions/runs/44604405484) · [最終 Research](https://github.com/lleeoo0611-stack/AU_REE_V2/actions/runs/44604406584)

## 資料、方法與研究用途

| 工作包 | 可使用的成果 | 資料與適用界線 |
|---|---|---|
| A　資料品質 | Voyager 的 ASX 靜態原件第 3 頁把黏土與鋁土礦定位到該案礦權。[逐格差異](coverage_delta.csv)列出每項更動及來源。短名、尚未核實的正面里程碑與不完整掃描有分開的回歸案例。 | Voyager 的觀測層級為勘探目標。Avonbank、Copi、WIM150 的正式總表仍列 B2。 |
| B　流程與可攜性 | 取件與證據層改用共用 CSV 介面。單一 CLI 仍負責取件、驗證、SQLite、Census、篩選與 R。搬移後的唯讀匯出按 run、配置、來源、原件與附件雜湊核對。 | 完整重播須取得原件套件與英文 OCR 模型。原件套件有 684 份檔案、774 次引用；85 筆引用直接載明取得方式，689 筆未明載；另有 300 筆引用可匹配所屬快照的歷史收據狀態，兩項統計可重疊。公開倉庫提供收據，原件由保管人交付。缺少可長期下載的公開套件網址。 |
| C　關聯模型 | SQLite schema v1 以可查詢的資源陳述版本、分類、組成、技術終點、產品與公司角色視圖連回既有原始觀測和穩定 ID。母估算、分項和衍生值可依來源與材料回查。[資源欄位計算鏈](resource_statement_lineage.csv) | 同一 MRE 的不同刊本可各自保留。須依所選 scope 計算研究案例。歷史關係表的占位日期另有明確解讀；沒有來源的持股、生效日期、包含／取代關係保留待查。 |
| D　樣品分析與品質 | [分析證據](assay_method_evidence.csv)涵蓋 Duke 的細粒土壤、Franklyn 高嶺土鑽樣、Nutgrove 岩屑及 Goschen Central 重礦物。表內連至原始觀測、物料、前處理、分析法、結果基準、實際披露的 QC 與原文頁碼。 | 四例均有方法，原件明示採用 ISO／GB/T 的實例為 0。ISO 24181-1、23596、23597 與 GB/T 40798 按各自適用基質及測項比較，採用官方公開書目／摘要。未知的 LOD、CRM、blank、duplicate 保留空白。 |
| E　候選分期 | [93 案新舊對照](milestone_comparison.csv)、[來源事件](milestone_events.csv)和候選 codebook `candidate-milestones-20261120-v1` 可獨立審查。Avonbank、Copi、WIM150 有完成 FS／DFS 的原件，對應候選 B3。 | 候選資料分列已達門檻、首次 MRE 日期、截止時可查的營運狀態、進行中的工作與設施範圍。Coburn 的 D2 對應報導所指選廠及產品。兩個 Census ID 引用同一 Yttria 礦床時須依範圍去重。 |
| F　正式 C1 與探索性研究 | [逐 Gate 判定](formal_c1_gates.csv)、[9／12 項對照](formal_c1_panel_comparison.csv)、[正式發布判定](formal_c1_release.json)和 [Aim C 資料可得性](aim_c_availability.csv)來自同次建置。正式政策截日為 2026-10-29。 | 現行核准 crosswalk 與簽核表均無紀錄，正式可發布案件為 0。探索面板仍採 SAW、PROMETHEE II 與 TOPSIS。Technical Disclosure Transparency 的 7 項固定分母繼續使用。 |

候選里程碑有 23 筆來源事件。20 筆確認里程碑，另有 2 筆營運狀態與 1 筆進行中研究。93 專案中 17 案可列出最高已確認里程碑，分別為 A1 三案、A3 六案、B1 兩案、B2 一案、B3 四案、D2 一案；其餘 76 案保留待審。正式 C1 六項 Gate 共評估 558 次，兩種政策候選面板均有 24 案找到至少一項相關變數，完整且基準相符的案件均為 0。依正式截日可定位部分來源事實的案數分別為 ID 92、ROLE 23、WINDOW 91、JORC 38、PANEL 24、GIS_RELEASE 0。進入正式樣本仍須逐 Gate 連到有效證據、固定面板與研究者簽核。

Goschen Central 鋱含量可重算。2024-12-03 原件第 3 頁在整體礦石基準報告捨入值 2 ppm，乘 620 Mt 為 1.24 kt。第 12 頁報告重礦物含量 2.2%、其中 Tb₂O₃ 為 0.011%，換算為 Tb₄O₇ 得 1.533207 kt。Census 使用第 12 頁的計算鏈，第 3 頁以另一筆來源觀測保留。[兩條計算鏈](goschen_comparison.csv)

## 研究者待決

| 研究定義 | 可選方案與本版樣本影響 | 建議 |
|---|---|---|
| 正式 C1 面板與 ID 核定 | 原政策有 9／12 項候選。兩者目前完整相容樣本均為 0；關聯身分、GIS、研究活動及各 Gate 尚需同範圍的來源與真正簽核。 | 按研究目的事前固定面板，再以逐案表核對；決定後保存版本和核准紀錄。 |
| A2 系統性界定與 D3 穩定達標 | 可維持「待審」，或由研究者指定適用的調查／設計版本、產品指標與觀察期。目前登錄的來源事件中，沒有這兩類可直接核定的案例。 | 先取得能比較兩種情形的真實原件，再決定分界。 |
| 將候選十二階段納入排名 | 可繼續用於分類，或在另行核定效用尺度後做隔離敏感度分析。目前缺候選分數映射。 | 本版保留描述性分期。Proposal／方法章將 Technical 明確標成技術資訊揭露透明度，依給料、終點、尺度與產品基準另述實際製程績效。 |

建議先審查遷移與來源重播，再審查樣品和分期對照，最後由研究者決定是否採用正式面板。此次只向 Census 整合線提交 Draft PR。
