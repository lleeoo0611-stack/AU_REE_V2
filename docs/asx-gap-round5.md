# 澳洲 REE：16 項候選收錄與第五輪缺口驗證

同一隔離分支 `experiment/asx-public-acquisition-20261109`。資料截止 2026-11-05，取得及核對日期 2026-11-10。
以 `2433816` 的 **37 案 × 52 欄、900 格有值／1,024 格空白**為比較基準。
兩項工作皆已執行：逐項審查前輪 16 個候選，以及擴大追查原案的資源、品位、成分與年產量。
沿用 proposal 的可追溯資料收集與專案比較目的，不改算 MCDA，不把研究列收錄當成正式 C1 或採礦權認證。

## 結果與分母

| 範圍 | 專案數 | 已填格 | 空白格 | 25 個科學數值欄位 |
|---|---:|---:|---:|---:|
| 原基準 | 37 | 900 | 1,024 | 324 / 925 |
| 同一批原案更新後 | 37 | 904 | 1,020 | 327 / 925 |
| 本輪新增專案 | 6 | 64 | 248 | 3 / 150 |
| 擴充總表 | 43 | 968 | 1,268 | 330 / 1,075 |

原案新增 **4 格：3 個資源數值及 1 個有資源估計標記**，都屬明確限定的 Lyons 12、13 資源範圍。
另有 5 格既有值更新：Lyons 的範圍名稱、Lyons 和 Narraburra 的來源名稱／網址；2 格只是數字格式差異，撤回 0 格。
新案的 64 格另計。空白 1,268 格＝原案 1,020 格＋新案 248 格，沒有把新增列的欄位算成填掉原缺口。

有配對資源量／TREO 品位的列從 28 增至 30：原案新增 Lyons 限定範圍，新案新增 Aileron。
完整 15 氧化物組仍 9 案；年產 TREO 仍 6 案，年產 NdPr 仍 5 案，模板完整 HREE8 年產仍 0 案。
本輪沒有新增個別氧化物或合格年產數字；有搜尋及核對，不以樣品、階段產量或不同產品分母湊值。

## 16 項候選的逐案處置

| 處置 | 名稱及歸屬 |
|---|---|
| 新收錄 6 項 | Wimmera、Balranald、Euston、Aileron、Charley Creek、Comet |
| 母子範圍 4 項 | Dickson Well → Power Minerals Eyre Peninsula；Minos → Indiana Central Gawler Craton；Target 21 → Marmota Mulgathing；Morgans Creek → Taruga Mt Craig（Flinders 山區不是另一個 Flinders Project）範圍 |
| 仍需補證 5 項 | Caralue Bluff、Franklyn 的獨立專案邊界／帶日期原件仍未完成；Billeroo 為地質複合體與礦化點，開發商專案身分未建立；Olympic Dam、Carrapateena 的 REE 礦化／尾礦研究未構成已驗證的獨立 REE 採礦資源範圍 |
| 加工／庫存範圍 1 項 | Eneabba 精煉廠及歷史重礦物庫存，不另列為原位 REE 採礦專案；多種料源處理能力不分配給單一礦山 |

每項都有 URL、來源雜湊、頁面及處置，見 `candidate_followup.csv`。
子範圍的母專案未因此自動收錄；5 項待補證並不等於沒有專案或沒有 REE 潛力。
累計 29 個逐案審查名稱中，10 項為研究擴充列：前輪 4 項、本輪 6 項。
原 canonical SQLite 仍是 33 個群組；來源紀錄、候選、研究列與正式核准仍分開。

新增列的具體原件：

- **Wimmera：**[2026-01-29 WIM100 資源公告](https://www.asx.com.au/asx/v2/statistics/displayAnnouncement.do?display=pdf&idsId=03053666)，實體第 1 頁明示 Iluka、Victoria、Wimmera／WIM100。540 Mt、4.6% 是 HM，不是 TREO。與 Avonbank、WIM150、Eneabba 分開。
- **Balranald：**[Iluka 2025 年報](https://www.asx.com.au/asx/v2/statistics/displayAnnouncement.do?display=pdf&idsId=03061353)，實體第 23 頁確認 NSW 採礦專案及 REE 副產品；第 42 頁日期 2026-02-18。沒有使用精煉廠年產能力。
- **Euston：**[政府公開的環評 Scoping Report](https://majorprojects.planningportal.nsw.gov.au/prweb/PRRestService/mp/01/getContent?AttachRef=PDA-49591461%2120230119T024434.317+GMT)，第 2 頁版本核准日 2023-01-11，第 6 頁為 NSW 專案及六個礦床，包含 Ki Downs。該環評文件不當成工程 Scoping Study，也未用 HMC 當 TREO。
- **Aileron：**[2026-04-22 更新公告](https://www.asx.com.au/asx/v2/statistics/displayAnnouncement.do?display=pdf&idsId=03084938) 確認 WA 獨立專案；[2026 年報](https://www.asx.com.au/asx/v2/statistics/displayAnnouncement.do?display=pdf&idsId=03157945) 實體第 9 頁的 0.25% Nb₂O₅ cutoff 總列才有配對 TREO：120 Mt、0.36%、433 kt。26 Mt 的高品位子集不相加；0.77% 為鈮品位，不是 TREO。年報發布 2026-10-27 由官方索引綁定，文件簽署日 2026-09-25 分開保存；資源屬 2026 年 4 月估計的後續重申。
- **Charley Creek：**[Enova 2025 年報](https://www.asx.com.au/asx/v2/statistics/displayAnnouncement.do?display=pdf&idsId=03077988)，第 2 頁 2026-03-31、第 17 頁 NT／Charley Creek。Cattle Creek 為其中範圍；歷史 805 Mt 不配上新鑽孔或試驗樣品品位，也不混入公司巴西專案。
- **Comet：**[Petratherm 2024 年報](https://www.asx.com.au/asx/v2/statistics/displayAnnouncement.do?display=pdf&idsId=02861291)，第 17 頁確認 SA Comet 包含 Meteor／Artemis，第 25 頁日期 2024-09-30。不把 Muckanippie／Rosewood 的鈦資源轉入 REE 欄。

## 原案資源及成分核對

**Lyons：**取得[2023-10-25 原始公告](https://wcsecure.weblink.com.au/clients/lanthaneinresources/headline.aspx?headlineid=61176136)。
第 1、6 頁重現 2,266＋670≠3,221 t 的全案衝突；沒有宣稱總表矛盾已消除。
明列子範圍 Lyons 12、13，採第 6 頁同列 **0.69 Mt、0.33% TREO、2,266 t TREO**；三者在來源有效位數範圍內一致。
總表名稱明示 `12&13 resource scope`，排除 Lyons 11 與全案總列。不是把全案當作 0.69 Mt。
既有 37 案仍有 8 列缺配對：Burracoppin、Greater Brothers、Splinter、Mt Stirling、Kalkaroo、Sandy Mitchell、Avonbank、Copi。
原前輪最早六案中，其他五案的細粒／bulk、母子重複、私人原件、錯案及非 REE 資源問題仍未解除。

**Narraburra：**[2023-04-19 原件](https://announcements.asx.com.au/asxpdf/20230419/pdf/45nsv13j5vtntn.pdf) 第 6 頁資源表為影像。
逐格視讀最後 All Ind＋Inf 列：94.9 Mt、738.95 ppm TREO、130.79 ppm MREO；第 7 頁再核對 Indicated／Inferred 範圍。
MREO 定義是 Pr₆O₁₁＋Nd₂O₃＋Tb₄O₇＋Dy₂O₃，對應 12.411971 kt、17.6994383923134%。
這兩格在基準已存在，新增的是原件儲存格與定義綁定，沒有重算成新增補值。
報告一組合計不等於各個元素分別公布，不填個別氧化物、需兩者皆公布的 NdPr、HREE8 或元素公布數。

另重查 Tower、Circle Valley、Yin、Brockman、Mt Weld 等原件／附件：合計、資源子集、礦石儲量、局部高品位樣品或處理能力不能跨範圍補入當前資源組成。
未取得可靠新值的欄位保留未知。搜尋成功與下載頁數不當成數值完整率。

## 年產量與取得限制

重新取得 North Stanmore 2026-09-14 簡報（ASX 03139002）。第 9 頁雖以年度產量為題，列明 Initial 10 Years；1,868／362 不當成全期年產 TREO／NdPr。
2026-08-18 PFS 第 7 頁 Total／High Grade／Low Grade 的 Average／LoM 欄繼續保留原限制：dt 是乾噸，沒有明示年度分母，不用約 20 年倒推。
Yangibana 的 Ore Reserve NdPr 比例不乘到年度精礦；Sandy Mitchell 的礦物年產、Avonbank／Copi 的 HMC 或獨居石／磷釔礦年產也不是可直接採用的氧化物年產。
模板 HREE8 仍為 Tb、Dy、Ho、Er、Tm、Yb、Lu、Y，不能以 Dy＋Tb 或含 Gd 的另一組 HREO 取代。

本輪 23 個明確網址，21 份 PDF 取得、2 個網址失敗；PDF 21／22 成功，共 1,033 頁，其中 ASX 公開原件 18／18 成功。頁數是文件總長，不是逐頁金標驗收數。
Iluka 舊網站年報網址 404，改取同份 ASX 原件；Cobra 網頁 429 便保留失敗收據，沒有重試繞過。
另取得 21 個公告索引：19 個解析、2 個 LNR 舊代碼索引未取得，合計 1,133 個不同帶日期公告連結，未全部下載。
網址名稱含 2024 的 Iluka 資源附件實際內容是 2025 年末表，沒有從檔名猜有效日。

## Gemini.csv 的使用

89 列僅作名稱線索，沒有數值可直接匯入。18 列可精確連到目前名稱／別名，69 列仍是未驗證線索，1 列為海外線索，1 列可能是 Narraburra 的拼字差異；公司和股票代碼皆未因名稱匹配而自動覆寫。
[Meteoric 原始網站](https://meteoric.com.au/) 確認 Caldeira 位於巴西，澳洲公司總部不代表澳洲礦山。
Cowalinya 的 HRE 與輸入的 HVY 公司組合、WIM100 的 Iluka／WIM 名稱混用亦列為核對事項。
公開成果只含輸入雜湊、統計及來源說明；含原始輸入欄位的名稱核對表只交付本機，不推送。
這是篩查，不宣稱 89 列皆已逐份完成技術與現行權利查核。

## 驗證與重現

最終相關回歸測試 265 項及 41 個子案例通過；針對性測試 93 項及 30 個子案例通過，兩組重疊，不相加，收據見 `validation.json`。
兩次完整匯出的四個 CSV 必須逐位元相同，每個已填格恰有一筆目前來源，每個空白有診斷。
SQLite SHA 保持 `99ed9c0fc004960f92680ee782ef8764c189a08d98bce4d14c2d0e5ad99091d0`，原凍結資料、原始 52 欄契約與既有研究結果保留。
沒有宣稱重建所有歷史研究或通過遠端 CI。

入口：`capture_research_sources.py`、`discover_asx_archives.py`、`audit_project_discovery.py`、`export_project_summary.py`、`validate_asx_candidates.py --allow-cohort-expansion`、`screen_external_project_names.py`、`package_asx_round5.py`。
匯出同時指定兩份 review/discovery ledger；除前輪 asset roots，再提供 `round5=work/asx-round5-sources`、`asx-round5-archives=work/asx-round5-archives`。
派生成果為 `results/asx-gap-round5-2026-11-10`，目前版本同步 `results/asx-current`。原始 PDF、完整頁面文字、影像、SQLite 及輸入原始列不公開推送。
