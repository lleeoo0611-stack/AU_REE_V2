# Phase 19 — 技術資訊揭露透明度

正式研究定義：`technical-disclosure-transparency-v1`。截止日：2026-11-05。

**這是包含資訊透明度的研究篩選，不是技術能力、製程績效、技術可行性或 JORC 合規排名。**

## 已完成的實質結果

- 31既有群組、217項判定：充分揭露82、具範圍與理由的明確未知4、限定文件未充分揭露69、尚無法查核62。

- 20群組具完整七項點分數；11群組提供已確認得分、未知數與可能範圍。無中點、隨機補值或逐案重配權。

- 71份既有PDF／HTML、3078頁原生文字建立相同搜尋索引；24份原件實際支持本輪逐項判讀。未新增外部原始文件或假稱新測量值。

- 本輪是凍結既有文件母體的查核，不是全網公開文件的完備性調查。名稱／關鍵字命中僅導覽；頁碼、原句、子條件解釋與判定理由均另存。

- 沿用work/phase5/canonical.sqlite；每版本以既有derived表存248列（31×7項加總分）。沒有第二個正式資料庫、沒有Schema migration、沒有改寫原始觀測。

- 主程式T1已改為technical_disclosure_pct；原回收契約保留T_RECOVERY_LEGACY供歷史重建及補充用途。舊development coverage cohort語意保留，並非新透明度分析進場條件。

## 七項規則與可查核資料

[最低條件及proposal修訂對照](codebook.md)。每項所有子條件均達標才得1；TD4藥劑、能源、水三類缺一不可；清楚交代未驗證原因可得1，研究／設計尺度不加成熟度分。

[完整217項：來源日期、頁碼、原句、子條件與理由](disclosure_items.csv)；[共同搜尋與停止紀錄](disclosure_search_audit.csv)；[不可變判讀輸入](review_input.json)。

狀態：1=充分；1*=明確未知但完整交代範圍及理由；0=完成限定文件查核後仍不充分；?=未取得、身分／範圍不明或重大矛盾。N/7×100為已確認下界；有?時點分數為NULL。

|群組（非一律獨立Project）|TD1|TD2|TD3|TD4|TD5|TD6|TD7|N|未知|分數／可能範圍|
|---|---|---|---|---|---|---|---|---:|---:|---:|
|Browns Range Project — Wolverine scope|0|1|1|1|1|1|1|6|0|85.71|
|Cowalinya Rare Earth Project|1|1|1|0|1|1|1|6|0|85.71|
|Donald Rare Earth and Mineral Sands Project|1|1|1|0|1|1|1|6|0|85.71|
|Koppamurra Rare Earths Project|0|1|1|1|1|1|1|6|0|85.71|
|Nolans Project|0|1|1|1|1|1|1|6|0|85.71|
|Cummins Range Rare Earths-Phosphate Project|0|1|1|0|1|1|1|5|0|71.43|
|Goschen — Area 1 resource scope|1|1|1|0|0|1|1|5|0|71.43|
|North Stanmore Heavy Rare Earth Project|0|1|1|0|1*|1|1|5|0|71.43|
|Dubbo Project|1|1|?|0|0|1|1|4|1|57.14–71.43|
|Jupiter development study within Brothers|0|1|1|0|1|1|0|4|0|57.14|
|Salazar Critical Minerals Project|1|1|1|0|0|1|0|4|0|57.14|
|Wudinna Rare Earths Project|0|1|1|0|?|1|1|4|1|57.14–71.43|
|Circle Valley|0|1|1|0|0|1|0|3|0|42.86|
|Kalkaroo|0|1*|1*|0|0|1|0|3|0|42.86|
|Mt Weld Project|0|1|0|0|0|1|1|3|0|42.86|
|Yangibana Rare Earths and Niobium Project|0|1|1|0|0|1|0|3|0|42.86|
|Yttria REE Project|0|1|0|0|0|1|1|3|0|42.86|
|Fingerboards|0|1|0|0|0|1|0|2|0|28.57|
|Mangaroon Project — Yin resource scope|0|0|1|0|0|1|0|2|0|28.57|
|Mount Ridley|0|1|0|0|0|1|0|2|0|28.57|
|Splinter Rock Rare Earth Project|?|1|?|?|1|?|?|2|5|28.57–100.00|
|Lyons|0|0|0|0|0|1*|0|1|0|14.29|
|Narraburra Rare Earths Project|?|?|?|?|?|1|?|1|6|14.29–100.00|
|Brockman Project|?|?|?|?|?|?|?|0|7|0.00–100.00|
|Burracoppin Project|0|0|0|0|0|0|0|0|0|0.00|
|Greater Brothers|?|?|?|?|?|?|?|0|7|0.00–100.00|
|Mons Project — Block3 East resource scope|?|?|?|?|?|?|?|0|7|0.00–100.00|
|Mt Clere Project — Tower resource scope|?|?|?|?|?|?|?|0|7|0.00–100.00|
|Mt Stirling|?|?|?|?|?|?|?|0|7|0.00–100.00|
|Redlings Rare Earth Project|?|?|?|?|?|?|?|0|7|0.00–100.00|
|Splinter|?|?|?|?|?|?|?|0|7|0.00–100.00|



完整點資料子集最高為6/7（85.71），Browns Range、Nolans、Donald、Koppamurra與Cowalinya並列；未查核群組仍可能高於此分數，不宣稱五案是31群組的已知全體前五。

Cowalinya頁9明列8.4%雜質高於通常<5%條件，故產品限制揭露可得分；這不代表產品合格。Kalkaroo尚未完成REE回收研究，但明確交代礦物相及回收途徑未建立的原因，相關揭露仍可得分。

Fingerboards未標示原發布日，保留NULL；SHA綁定網頁於2026-11-03已存檔，能支持截止日前的可見內容，不倒推事件日期。

## Aim A：矩陣與排名

沿用既有AHP假設矩陣、SAW、PROMETHEE II、固定理想點TOPSIS及R引擎。全體六構面Technical權重承接10%／20%／10%，沒有增加總權重。部分面板依原有active-panel規則等比例正規化，**不是完整六構面總排名**。

|面板|可觀測點資料n|實際分析|
|---|---:|---|
|透明度|20|七項二分分數；保留並列|
|資源＋透明度|13|三方法、三情境、相同母體有／無T|
|資源＋港口＋透明度|12|三方法、三情境、相同母體有／無T|
|完整六構面點資料|1|樣本不足，未產出可比較點排名|
|31群組六構面區間|31|2232列條件式分數／名次外包範圍；不是31唯一名次|

[透明度排序及並列](disclosure_ranking.csv)；[31群組六構面矩陣](disclosure_composite_matrix.csv)；[31群組區間排名](disclosure_composite_ranking.csv)。

資源＋透明度13案的PROMETHEE II在三情境均由Nolans列首位；資源＋港口＋透明度12案：資源與戰略情境為Jupiter，開發情境為Cowalinya。這些首位受準則集合、固定效用與文件母體限制，不能當技術或商業成功判定。

[13案排名](resource_disclosure/ranking.csv)／[12案排名](resource_port_disclosure/ranking.csv)。

## Aim B：敏感度與未知

比較原Technical權重、T=0、5%、10%、20%、30%。其餘構面維持原相對比例，權重總和為1；另比較移除Development。每項未知僅取可能集合，不作均勻抽樣、誤差假設或信賴區間。

[完整權重](disclosure_weights.csv)；[區間敏感度](disclosure_interval_sensitivity.csv)；[同一已觀測母體的逐案名次變化](disclosure_point_rank_changes.csv)；[變化摘要](rank_change_summary.json)。

R對可觀測面板完成每情境1000次權重偏好模擬、留一準則／構面、效用函數與母體敏感度、跨方法比較。本輪新面板以凍結的非Technical點分數為條件，沒有傳入來源四捨五入界限，故新面板的誤差模擬輸出為Missing；不是宣稱所有來源都沒有可信界限。原R1四捨五入依據保留於baseline provenance及既有面板，本輪未完成其重新傳播。

R保留平均並列名次，新增joint-first頻率以涵蓋共同首位；共同首位頻率可加總超過1，並非成功機率或互斥機率向量。未知集合區間與偏好模擬分位數分開。

## Aim C：與Development的重疊

有點透明度及Development值的配對僅n=7，描述性Spearmanρ=0.209。沒有顯著性檢定、因果判斷或『已排除重疊』的結論。

TD6只評是否說清尺度與資料性質，不給DFS比實驗室更多分；但較成熟專案通常有較長文件，仍有資訊量及生命週期混雜。保留移除D及移除T的結果供檢查。

[配對資料](disclosure_development_overlap.csv)。

## 尚無法查核的具體原因

|群組|原因|
|---|---|
|Wudinna|TD5：文中引用的純化／產品公告原件尚未納入此文件母體。|
|Redlings|七項未知：現有季度報告及探索目標引用，不能代替原始技術方法／結果文件。|
|Splinter Rock|TD1、3、4、6、7未知：簡報已有路線與產品敘述，其引用的完整技術公告仍缺。|
|Brockman|七項未知：同公司年報大量技術內容屬Yangibana，缺可歸屬Brockman的原件。|
|Dubbo|TD3未知：酸添加敘述與表格單位不同，另有重複欄標；未自行修正。|
|Greater Brothers|七項未知：Jupiter為巢狀子範圍，不移植給整個區域。|
|Splinter|七項未知：政府來源身分尚未確認等同Splinter Rock。|
|Mt Clere／Tower|七項未知：現有季度敘述多屬北部區域勘查，不能作Tower資源範圍的技術方法。|
|Mt Stirling|七項未知：Yttria選樣結果不等於整個母群組揭露。|
|Narraburra|TD1–5、7未知：年報引用的2023-04-05原始浸出公告未取得。|
|Mons／Block3 East|七項未知：現有技術回收結果屬Ga，不能借作REE技術揭露。|

Greater Brothers不承接Jupiter；Splinter不承接SplinterRock；MtStirling不承接Yttria。Mons的Ga回收不冒充REE回收，MtClere北部區域勘查不冒充Tower樣本。

Dubbo的酸單位／重複欄標矛盾保留未知。Wudinna產品純化、SplinterRock詳細流程與Narraburra原始浸出公告等仍須補原件；本輪未因此阻塞其他項目。

## Proposal及結果文字的必要改動

proposal原件及sources/同步資料保持唯讀。正式文字修訂對照已列在codebook.md：RQ1與Slide7/8改為Technical Disclosure Transparency；AimA及總排名改稱包含資訊透明度的綜合篩選；AimB分開偏好模擬與未知集合；AimC僅作生命週期／揭露關聯。**本輪未完成原proposal的technical feasibility評估。**

可採用的RQ1：How do Australian REE project groups compare across resource endowment, strategic composition, technical disclosure transparency, development readiness, infrastructure and disclosed commercial conditions?

## 程式與重現

資料流：原始SHA／文件日期與可見日期 → 固定母體搜尋索引 → 有子條件原句的研究內容編碼 → technical.assess_disclosure → 固定七項評分 → 同一SQLite derived／Selection T1 → 既有analysis與R引擎。

新增的正式輸入僅data/technical_disclosure_v1.json；評分在既有technical.py，矩陣／敏感度在既有analysis.py，主CLI增加disclosure入口並接回all/analyze。無Schema變更、無新套件。

歷史鎖定設定仍使用舊定義；較早日期不借用2026-11-05的判讀。正式C1六項Gate與既有核定狀態不由這個結果自動變更。

```powershell

$env:PYTHONPATH='.;src;tests'

& work/pinned-env/Scripts/python.exe -m au_ree_v2 disclosure --as-of 2026-11-05 --work work/phase5 --snapshot-lock results/phase19-2026-11-05/snapshot_lock.json --rscript 'C:\Program Files\R\R-4.5.2\bin\Rscript.exe'

```

需保留現有canonical.sqlite及相同來源快照；這是沿用同一資料庫的重現，不是另建資料庫。

程式起點HEAD 403e4a2，現有分支feat/phase16-technical-model。工作開始時已有未提交的framework與來源擴充；本輪保留並整合。未推送、未合併，未宣稱GitHub Actions已執行。

來源內容判讀為代理執行的研究編碼；已驗證原件引用與規則運算，未宣稱獨立雙人標註或全澳公開資料完整性。

## 驗證紀錄

見verification.json及隨附測試紀錄。先前失敗／權限問題的紀錄保留於work/phase19；不計為通過。

JORC骨架來源：[JORC Code 2012 Table 1](https://www.jorc.org/docs/JORC_code_2012.pdf)。本研究七項計分與權重不是JORC官方制度。


驗證完成：全套289項Python測試通過；最後僅修正CSV情境順序後，14項相關測試通過。R五類不變量與4464個界限交叉驗證通過。兩次同庫封存重跑54份CSV一致。現有all主流程（--skip-r）亦已完成，新T1在value_trace中逐列核對；三個可觀測面板的R分析另已完成。未推送／合併，GitHub Actions未執行。


程式內容版本SHA-256：`194429f5d54afcc8ea01b83a5fc1b37ce0ae145f052d6f1afec534efec060d91`。來源／實體／原始觀測表在完整主流程後仍與重跑前完全一致。


完整發布檢查亦已通過：3722份文字工件；交付包另逐一核對成員雜湊。
