# AU_REE_V2 四項覆蓋率工程（2026-11-11）

依指定順序：**任務1 → 任務3 → 任務2 → 任務4**。基線 commit `2cce9fd89b92fd2d8ce4969d2c738a1dffb78e2d`，分支 `experiment/asx-public-acquisition-20261109`。

## 正式結果與核准模擬分開

正式研究者決定全部 `decided_by=null`。本次未代填核准人、未發布 `results/asx-current/`、未推送遠端。任務1實際新增0格；後三項因核准閘關閉亦新增0格。既有1,985格及其來源不變；93列、53欄、2,944空白不變。

| 任務 | 正式新增／變更 | 隔離核准模擬 | 待審／決定 |
|---|---:|---|---|
| 1 候選元素表 | 0／0 | 不需核准，實際0 | 259表次待審；Dubbo既有Y₂O₃同值核實 |
| 3 開發階段 | 0／0 | 單獨開啟提案後新增70格，1,985→2,055；空白2,944→2,874 | 15案待審；39案無原文；64案礦床型態按29種原文整理 |
| 2 政府座標 | 0／0 | 未取得官方資料，核准後真實新增量未知，不以合成測試代替 | 58案座標缺口；8項資料集／圖層選擇 |
| 4 兩項例外 | 0／0 | 單獨開啟兩條後新增8格、更新4個允許衍生欄；1,985→1,993；空白2,944→2,936 | Splinter、Circle Valley兩項限定決定 |

模擬使用獨立的 `TEST_FIXTURE_ONLY_NOT_RESEARCHER_APPROVAL` 決定檔，不是研究者核准，也不是已生效資料。任務3與4的數字各自相對同一1,985格基線，不能把兩份總數相加；任務2沒有真實核准資料，故不捏造四項全啟用後總量。

## 覆蓋率

沿用原規則：全表分母4,929；排除既有123格結構性空白後分母4,806，不修改排除規則。TREO子集以實際有總TREO量的研究列重算。

| 狀態 | 全表 | 沿用排除規則 | 有TREO資源量列 |
|---|---|---|---|
| 正式基線及四項預設關閉結果 | 1,985/4,929＝40.2719% | 1,985/4,806＝41.3025% | 36列；1,181/1,908＝61.8973% |
| 僅任務3核准模擬 | 2,055/4,929＝41.6920% | 2,055/4,806＝42.7591% | 36列；1,229/1,908＝64.4130% |
| 僅任務4核准模擬 | 1,993/4,929＝40.4342% | 1,993/4,806＝41.4690% | 37列；1,224/1,961＝62.4171% |

任務4模擬中Splinter新增canonical TREO，因此TREO子集增加一列；這不是改分母規則。57列原先缺TREO的整體缺口不是任務1目標；只有明確指定的Splinter例外在隔離核准模擬中改變。

## 為何實際格數低於預期

- 任務1的194候選頁原本有252張表；本次目標研究列實際關聯245張獨立表、260表次，不能混稱。既有選定列缺原件行列綁定、跨文件缺已驗證同MRE證據、不同頁／資源範圍或非canonical標籤都保守待審。這不表示原件沒有可填資料，也不是所有候選格已完成專家審查。詳見[逐案及拒收分布](../task1-2026-11-11/README.md)。
- 任務3不把bare Scoping/PFS/DFS/Feasibility名稱當完成，不把進行中較高階研究當已完成，也不把計畫FID／未來施工當現況。因此不是預估150–180格，而是實測70格核准模擬。Operating仍不推成達設計產能D3，退出不自動歸X，A3不自動指派。
- 任務2決定未核准，程式未發任何資料下載請求。VIC／TAS六案沒有文件列出的端點，維持空白；NT只允許核准後下載欄位報告。合成fixtures只驗證程式，不能作研究成果。

## 研究者決定清單

正式入口：[researcher_rule_decisions.json](../../config/researcher_rule_decisions.json)。僅研究者填寫適當 `decided_by`，各筆保留 `decision_id`、`rule`、`scope`、`decided_date`、`notes`。不得只因本文件描述模擬結果就啟用。

1. 任務3的A1/A2（是否有選定MRE）、已完成Scoping/PFS→B1、已完成DFS/BFS/Feasibility→B2、明示FID→C1、現正施工→C2，以及進行中研究／Operating／退出的處理規則。參見[規則提案](../task3-2026-11-11/proposed_decisions.json)及[礦床型態決定表](../task3-2026-11-11/deposit_type_decision_sheet.csv)。礦床型態規則本次未改，clay/regolith不推成IAC。
2. 任務2：WA MINEDEX、SA SARIG及兩個mining projects輔助圖層、QLD MINOCC、NSW MinView、GA OZMIN備援、NT STRIKE欄位報告。參見[資料集提案及授權](../task2-2026-11-11/README.md)。
3. 任務4：僅Splinter的指定statement允許Ce₂O₃→CeO₂；僅Circle Valley指定statement允許來源NdPr合計。Mount Ridley、Lyons、年產量及HTML對照欄不動。[來源與化學計量核對](../task4-2026-11-11/README.md)。

## 安全與重現

同範圍驗證器仍檢查原件SHA、原生行列、資源類別、截止品位、單位、版本與有效日。新元素只經既有review驗證路徑；不以鑽孔或選冶樣比例乘全案TREO。單位容差依原文印出的精度，不用固定百分比。新來源只能填空白；允許的既有衍生欄變更必須有同案新來源值支持，逐格揭露。

政府資料重播驗證整份原始回應及封存收據、完整商品query、分頁offset／total／終止證據，不能刪除競爭候選後宣稱唯一。QLD只用GDA94屬性座標對，不混用EPSG3857 geometry。來源精度文字保留原值；沒有已核實距離比較器時明記未檢查，不假稱通過距離驗證。

Census SHA固定 `99ed9c0fc004960f92680ee782ef8764c189a08d98bce4d14c2d0e5ad99091d0`。既有inventory、歷史結果、DRAFT codebook核准欄、排除規則及使用者原有未提交layout工作保留。決定檔雜湊納入每項重建收據。各項 `acceptance.json` 記錄兩次來源重建、四CSV與summary/audit一致、測試與保護檢查；`core_rebuild_receipt.json` 是核心重建收據。

離線來源重建須保有本機封存原件與 `asx_local_asset_roots.json` 指定路徑。先執行 `tools/rebuild_asx_census.py --out-prefix <fresh-prefix>`，再對a/b兩份53欄輸出各執行 `tools/apply_archived_element_additions.py`；後一步保留基線既有的Dubbo五格，不能漏掉。任務2若將來核准取得資料，須把所有raw response及其receipt一同封存，之後用 `tools/integrate_official_locations.py --acquisitions` 離線重播並再次核對兩份結果。每次使用新輸出資料夾，不重寫歷史結果。

本次沒有執行 `--publish-current`。後續發布只可在相應決定已正式核准、所有測試與兩次完整重建均通過後進行。

## 最終驗收結果

四項各自完成兩次完整離線來源重建，共8次正式重建；各階段434 tests＋353 subtests既有受影響回歸均通過。最終整個repository離線測試 **834 tests＋532 subtests全部通過，0失敗、0錯誤、0跳過**。跨項測試與上述全suite有重疊，不相加冒稱獨立測試數。

19筆決定全部null，正式1,985填值／2,944空白。既有current六檔逐位元不變、978個歷史／保護檔雜湊不變，原有18個未提交檔案內容未改。詳細收據見validation.json及各任務acceptance.json。
