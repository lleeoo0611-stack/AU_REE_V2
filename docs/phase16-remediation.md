# Phase 16 補修：來源範圍、科學身分及分製程分析

研究日期：2026-11-05（Asia/Taipei）。接續 `29b9b68`，沿用 Draft PR #6。此版本是 Phase 16 補修，沒有合併 PR 或啟動 Phase 17。正式資料庫仍為 `work/phase5/canonical.sqlite`；Schema 未改。

## 修正與資料流

原件／Manifest → 原有 Evidence／Study Case → 同一 Selection → 來源記錄身分／科學觀測身分／佐證 → 用途契約 → 原有 Python 矩陣組裝及 R 引擎 → 覆蓋與部分準則分析。

- `official.py` 採 `minedex-commodity-v2` 精確標籤規則，明列 15 個鑭系元素、Y、REE 總／輕／重集合。Sc 與 Monazite／Xenotime 另列，沒有礦物→REO 推換。舊版子字串規則只留作鎖定歷史重建。
- `technical.py` 保留舊 `technical-burden-profile-v1`。新 `technical-profile-remediation-v2` 先分段落用途，再保留來源所支持的需求與條件；存在某種處理不等於負擔較高。目錄／標題、純試驗目的與未揭露資訊不成立績效。設計用量不冒充營運量測。
- 科學觀測身分不包含 value，保護給料、終點、尺度、日期及其角色、統計量、scenario、物料分支、試驗／樣本、條件與單位。異值留下衝突關係，真正重複保留全部 evidence ID／定位；跨文件相等須有明示測量連結。舊、新 analytical ID 有逐列 bridge。原 1,822 列沒有證實發生該種範圍遺失，不把反例修復當成找回實驗。
- `target_applicability` 依 SHA／頁碼／引文、樣本、目標母體及覆蓋依據判定，具正例、缺失、不匹配及衝突反例。實際 Project 外推仍為零，並逐列保留原因；不是固定 False 或簽核條件。
- `analysis.prepare_technical_panel()` 只組裝符合用途的來源案例，由原 `run_r()`／`R/run_mcda.R` 評分。無新評分器、正式資料庫或 runtime 模組。R 增加零權重排除及固定群組總權重；舊面板不用新增欄位，舊正權重計算路徑不變。

## 三項缺陷及原始資料

同一 MINEDEX ZIP `33b5aeb8…`／CSV `9b127f74…` 的 15 漏列已逐列核對，共 68→83 列，仍是 22 個原生 Project code／22 個代表 Site。新增的是 15 個 SOURCE_RECORD，不是 15 個獨立 Project。完整 2,666 列的標籤判定另匯出；主要 83 列與 Sc 10 列、相關礦物 11 列保持分開。

原 26 筆文字命中全部有補修處置及原件 SHA 核對。`technical_burden_remediation.csv` 是程式分類；`data/phase16_remediation_source_audit.json` 另核對原頁文字，區分逐字來源、非逐字工程摘要及定位線索。這不是獨立專家評閱。三項原頁核對的 Koppamurra／Cowalinya 主張透過既有 claims 入庫，數值為 NULL；自動結果與核對主張不互相覆寫。

本次在既有下載流程中嘗試三份預先登錄的發行人原件：Sybella、Kennedy、Sandy Mitchell，均已取得 SHA 與解析快照，18.192 秒；沒有使用替代入口或超過六份上限。它們是文件層級保留集，沒有可靠登錄身分及完整比較範圍的候選不轉成 Project 或主面板樣本。WebLink origin／認證／條件的舊限制保留，沒有猜測端點或稱為 Live 成功。

選取快照 254→272：六個是新增 PDF／解析快照，其餘十二個是截止日移至 2026-11-05 後選入的既有 discovery HTML，不是新技術文件。原先凍結目錄不改寫。

## Technical 定義及實際分析

Technical 在具名礦石／礦山方案和產品終點下，描述回收／分離績效與達成產品所需的物理、化學、除雜及殘渣投入。T-A／T-B 是需求與機制分類，沒有共同強度次序，不映射成 1／2／3，也沒有新六構面通用分數。

**A：採用探索性分製程數值示範。** 新契約 `process-specific-technical-v1` 使用原礦→礦物精礦的設計預測：Yangibana 85.7%／27%，Browns Range 84%／25%。主張只適用各自具名 DFS 方案，Browns 含 BRPP stockpile，沒有把 Wolverine-only 資源貼到整個礦山計畫。浸出液、MREC、煅燒 MREO、分離氧化物與樣本試驗不混入。

比較保留既有 typed case 的 TREO_INCLUDING_Y 定義；Browns 原件明列氧化物集合，Yangibana 季報沒有重述完整元素集合、引用的更新 DFS 有 Y 氧化物價格籃。本示範依既有共同 basis 註記與明示模型假設解讀，不稱為新驗證的化學等價性、實際營運或正式 C1。產品 TREO 品位也不代表所有雜質、價格籃或承購規格相同。

事前登錄後、看排名前，先排除尖峰／穩態年產量的不同比較口徑；GIS 試跑又確認 Yangibana 缺已選取港口距離。主分析改用兩案均為 0.6 的既有 D1 作固定背景，無區辨貢獻，不作 Technical 品質加分，亦無資源數量借用。這是隔離 Technical 定義影響的決策示範，不能解釋為綜合開發潛勢排名。

兩面板各有 10 組設定：Technical 總權重 0／0.25／0.5／1，正權重各分回收／品位 80:20、50:50、20:80；總權重零只執行一次。固定 0–100% 量尺對照樣本 min–max，均用原 SAW／PROMETHEE II／TOPSIS、AHP 假設矩陣與既有 seed 20261102／1,000 次權重抽樣。Technical 群組總權重在每次抽樣固定；沒有生成量測誤差。來源未給誤差，rounding 輸出標未量化。

相同兩案與背景下，無 Technical 時平均名次均 1.5；有正 Technical 權重時 Yangibana 在本次三方法／映射／子權重配置均領先，因兩項點值皆較高，沒有呈現兩項間權衡。這是條件式名目支配，不是統計顯著差異、全域必要偏好或全澳排名。移除任一案後只剩單案，樣本 min–max 與跨案排名保持不可計算。Operating-only 情境樣本零。

**B：保留可重算單案投入，未採共同跨案負擔分數。** Cummins 12 個乾給料設計強度保留 stage、試劑、分母及 evidence ID；不同試劑不加總。Cowalinya 24.8 kg/t 是 32% HCl 來源配方／指定 leach feed。若另假設 32% 為質量分率，條件式有效成分當量為 7.936 kg/t；不是已核實量測，含水及投入／淨消耗衡算仍有缺口。沒有把 g/L 轉成 kg/t，也未與不同試驗回收拼接。

**C：來源產品限制診斷，未採共同序位。** Cowalinya 四-composite、1 kg blend 的首輪 MREC 有 8.4% 雜質，對照來源稱通常 <5% 的基準，診斷 c/L=1.68。數值由同 case 的既有 metric 與來源 benchmark 取得，不寫死在程式。它不是買方約束規格或整體 Project 失敗，亦未證明所有規格都已檢查。

**D：已執行充分性檢查，不能試算。** 同一四-composite feed 的品位分率為 0.002595，但缺同案 q、至 MREC 的整體 R、買方規格與分攤／邊界。功能單位留 NULL；不連接另外 45 個 preferred composites 的 84.9% 浸出及 24.8 kg/t。這不是完整 LCA。

Aim A 提供來源案例×指標及用途／缺口；Aim B 分開權重、映射、方法、範圍與成員情境；Aim C 保留來源礦物學／流程與既有地理描述，不按礦床類型先給分，也不做小樣本回歸或因果解釋。獨立單位是兩個 Project 下的兩個設計方案；格位、文字命中與模擬次數都不是獨立實驗，實驗獨立性總數未知。


## 原版與補修版的可比計數

| 指標 | 原 Phase16 | 補修 |
|---|---:|---:|
| canonical groups／資源 cases |31／21|31／21|
| 選取快照／已解析文件 |254／38|272／41|
| 有效來源數值／Project-selected 數值 |711／709|711／709|
| Project-selected Technical 數值 |558|558|
| 統一 Technical 分析紀錄 |1,822|1,825|
| 程式判定可作來源判讀 |1,333|1,087|
| 來源限定數值剖面 |494|494|
| T-A／T-B 有有效來源規則／核對主張的 Project |6／6|6／4|
| MINEDEX 主要列 |68|83|
| MINEDEX 原始數值／NULL 欄位 |252／156|318／180|
| 新增獨立 Project／新共同 MCDA Project |—|0／0|
| Full-evidence／正式 C1 |0／0|0／0|

1,087 是新程序旗標，非人工逐列確認數；下降包括移除目錄／計畫與保守漏判，原始內容未刪除。558／494 不同口徑，不能相減當缺值。三項新 NULL 主張、六筆格位佐證及新原件分開計數。原九面板 n19/7/8/2/2/10/6/17/2 不變，142 個舊面板科學 CSV 與原版相同；新增兩個定義／正規化示範面板各 n2，並非新增兩個 Project。嚴格 T1 仍零；全 registry 的 R21/S10/T0/D9/I19/C8 口徑維持，TC1／TC2 示範不加進 T1 全域覆蓋。

來源／原始回應的 509 個唯一檔案 SHA、281 個封存輸出雜湊、原 406 筆 Manifest 記錄及 7,623 個舊 entity ID 已核對；僅新增 15 個 SOURCE_RECORD。SQLite integrity=ok、外鍵違規=0。這些是當期實測，並不證明全澳 Census 完整。

## 評估、重建與驗證

保留集在調整規則前按文件固定；Browns／Koppamurra／Cowalinya 等舊案例都是開發／回歸。新三份原件跨酸浸—除雜—MREC、解吸、物理選礦，是目的性、非盲抽樣。

九個指定數值找回 8 個、漏 1 個；完整數量／範圍綁定 0/9。四項主張判讀 0 TP／0 FP／2 FN／2 TN，性質標籤吻合 0/4。僅評估指定語句，未做全頁標註，不能虛構 precision。三份文件的候選亦實際經共享比較契約檢查，全部排除（TN3、無正例，不能由此估計資格召回）。這些失敗完整保留，不回頭調規則；未符合身分、basis、feed、endpoint 的候選不能改變主面板。AI 原頁核對不是專家信度或全國解析準確率。

測試及耗時以 `data/phase16_remediation_*` receipts、同一 PR 的最新 head checks 為準。開發中 Windows 臨時目錄權限失敗、R 執行時改檔中斷、群組欄位誤套舊面板的失敗均不計成功；修正後驗收另列。歷史 Phase5–16 必須實際回放；本期另做兩個獨立 clean，以原容差檢查靜態點值，排名、權重、RNG／模擬仍 exact。

## 方法查閱範圍

| 來源 | 本次查閱與用途 | 不支持的推論 |
|---|---|---|
| [JORC 2012](https://www.jorc.org/docs/JORC_code_2012.pdf) | Table1 §4 冶金因素段落：流程、試驗／域、代表性、產品規格的核對框架 | 不提供本研究權重，也不給正式 Gate PASS；非現行法規全查 |
| [OECD/JRC 2008](https://www.oecd.org/content/dam/oecd/en/publications/reports/2008/08/handbook-on-constructing-composite-indicators-methodology-and-user-guide_g1gh9301/9789264043466-en.pdf) | Step6及Step7相關節錄：構念、加權／補償性、正規化、敏感度 | 不替本案等距效用、缺值插補或權重提供權威背書 |
| [Borst et al. 2020 公開全文](https://research-repository.st-andrews.ac.uk/bitstream/handle/10023/20575/Borst_2020_NC_Adsorption_CC.pdf?sequence=1) | 讀取摘要及全文起始部分，未完整核讀；保留礦物／吸附機制依據的重要性 | 不把其他樣本數值外推到本期 Project |

Jordens／Vahidi DOI 入口此次未成功取得可讀內容，未宣稱完整核讀。SMAA-PROMETHEE 只查摘要，未新增 SMAA／ROR；既有 Monte Carlo 不改名，也不把排名頻率稱為開發成功機率。功能單位式依任務提示及量綱核對，不借文獻中別案數值補缺。

## 重現

```powershell
$env:PYTHONPATH='src;.;tools'
work/pinned-env/Scripts/python.exe -m au_ree_v2 rebuild --as-of 2026-11-05 --snapshot-lock results/phase16-remediation-2026-11-05/snapshot_lock.json --work work/remediation-clean-a --rscript 'C:/Program Files/R/R-4.5.2/bin/Rscript.exe'
work/pinned-env/Scripts/python.exe -m au_ree_v2 rebuild --as-of 2026-11-05 --snapshot-lock results/phase16-remediation-2026-11-05/snapshot_lock.json --work work/remediation-clean-b --rscript 'C:/Program Files/R/R-4.5.2/bin/Rscript.exe'
work/pinned-env/Scripts/python.exe tools/check_phase16_remediation.py work/remediation-clean-a/latest.json work/remediation-clean-b/latest.json
work/pinned-env/Scripts/python.exe tools/evaluate_phase16_remediation.py work/held-evaluation.json
```

完整可編輯結果、設定與 snapshot lock：`results/phase16-remediation-2026-11-05/`。邏輯資料庫歷史匯出採無損 gzip，主 CLI／SQLite 不變；封存 code commit 欄記錄開發父提交，實際程式由 content SHA 核對。最新 CI 狀態放在 PR checks，不改寫凍結時刻的來源或結果。

## 本機驗收紀錄

- 完整 Python 256 項通過，測試本體 931.643 秒、外圍命令 936.604 秒。其後新增的來源版本歷史測試另通過；最後補修測試共 24 項全部通過（5.825 秒）。不是把重複執行相加成 280 個獨立測試；CI 對最新樹重新收集完整集合。
- R 五組 invariants 通過；原 Phase16 benchmark exact。
- 本期兩次獨立 clean 分別 398.453／397.990 秒：170 個面板 CSV、7 份既有證據、7 份 Technical、7 份 Phase16、13 份補修匯出及定義敏感度均符合原規則。本機靜態點差異零；兩個 clean 邏輯 JSON 檔案 SHA 均 `4c59543fedbd8e2520b890b8b0e222f4aec6bee728abd394d31976cc37a5c0ee`。兩庫 integrity=ok／FK=0；canonical 保留較多未選入歷史，不宣稱整個歷史與 clean 相同。
- 正式資料庫本次完整執行 471.429 秒。本機 Phase5–12 歷史回放通過；Phase12 曾因磁碟不足失敗，清理本次產生的可重建測試／驗證副本後重跑通過。正式 SQLite、原件及已凍結結果未刪除。Phase13 本機重建未完成即停止，剩餘完整歷史驗收交由核心變更 CI；未把 cancelled／pending 報成通過。
- 首輪本機出版掃描通過 3,642 個檔案；最新完整樹仍由 CI 重新掃描。PR checks 是發布 head 的最終狀態，以上本機封存紀錄不先宣稱 CI 成功。

## 面板衝突防護補充

凍結結果對應 `dbb804f` 的程式內容；後續檢查補上主面板不能繞過共用科學觀測視圖的防護：同案異值、同案不同 scenario／scope／日期均不任取最後一筆；完全相同的語意佐證可保留，但不增加 Project。衝突只排除受影響案例，其餘案例繼續。

此修正未新增原始資料，也沒有重寫凍結檔案。以本期實際 Selection 匯出重建輸入、保留原工程參數型別並套用既有 interchange canonicalization，兩案的資格、來源輸入、矩陣、準則、權重與範圍情境共10檔 exact。新程式 content SHA 及核對記錄見 `data/phase16_remediation_panel_guard.json`；27項補修測試通過。最新 head 的完整歷史與兩次新 CLI clean 由 CI 再驗證，不把原凍結 code SHA 冒稱為後續修正程式。
