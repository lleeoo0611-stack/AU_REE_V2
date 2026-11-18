# 第10版：固定存證事件與公司層核准標記驗收

基準fc8b1b0，比較基準第9版乾淨CI44170481863。[Draft PR #12](https://github.com/lleeoo0611-stack/AU_REE_V2/pull/12)，target feat/same-sha-fallback-20261116，不merge。PR #11已依研究者先前指示合併，因此本輪另開Draft PR。

驗收提交`6eeaeae118bf404eef3fe458b9cdcf42252ce6a5`；[一次乾淨CI](https://github.com/lleeoo0611-stack/AU_REE_V2/actions/runs/44261812557)、[一次離線研究CI](https://github.com/lleeoo0611-stack/AU_REE_V2/actions/runs/44261812454)。**609／609、原900／900 SAME守住，流失0格。**

|分類|第9版|第10版|增減|
|---|---:|---:|---:|
|SAME|900|930|+30|
|DIFFERENT|34|34|+0|
|FORMAL_MISSING|1123|1093|-30|
|KNOWN_STRUCTURAL_DIFFERENCE|44|44|+0|
|NUMERIC_TOLERANCE_SAME|0|0|+0|

新增SAME 30格，分組{"P2_COMPANY_MARKER": 22, "OTHER": 8}；離2101格全SAME仍差1171。比較規則完全沿用第9版，結構差異與數值容差不算SAME。沒有反事實重建，按實際來源與核准位置歸因。

|新增SAME專案|欄位|原分類|歸因|
|---|---|---|---|
|AU-1103c5aa8bb63077ac61|未上市公司|FORMAL_MISSING|P2_COMPANY_MARKER|
|AU-1103c5aa8bb63077ac61|ASX代碼|FORMAL_MISSING|P2_COMPANY_MARKER|
|AU-1c907e00c797bf8b3ce1|ASX代碼|FORMAL_MISSING|P2_COMPANY_MARKER|
|AU-203b4d90e5c23a323610|ASX代碼|FORMAL_MISSING|P2_COMPANY_MARKER|
|AU-3a0020b6daf659f62138|ASX代碼|FORMAL_MISSING|P2_COMPANY_MARKER|
|AU-4286ab9c245effb445ff|ASX代碼|FORMAL_MISSING|P2_COMPANY_MARKER|
|AU-70cc41e3a7106f983f73|未上市公司|FORMAL_MISSING|P2_COMPANY_MARKER|
|AU-70cc41e3a7106f983f73|ASX代碼|FORMAL_MISSING|P2_COMPANY_MARKER|
|AU-794821a2df9b7a244f96|ASX代碼|FORMAL_MISSING|P2_COMPANY_MARKER|
|AU-8f3fe174a998d20ee4cf|ASX代碼|FORMAL_MISSING|P2_COMPANY_MARKER|
|AU-a9b72e86940271be45a3|未上市公司|FORMAL_MISSING|P2_COMPANY_MARKER|
|AU-a9b72e86940271be45a3|ASX代碼|FORMAL_MISSING|P2_COMPANY_MARKER|
|AU-b31d00e2272ffa6ccbd3|未上市公司|FORMAL_MISSING|P2_COMPANY_MARKER|
|AU-b3ae34ac85d16018bd4b|ASX代碼|FORMAL_MISSING|P2_COMPANY_MARKER|
|AU-b50a5b57669586191c33|開發商|FORMAL_MISSING|OTHER|
|AU-b50a5b57669586191c33|專案名稱|FORMAL_MISSING|OTHER|
|AU-b50a5b57669586191c33|所在地_中文|FORMAL_MISSING|OTHER|
|AU-b50a5b57669586191c33|所在地_英文|FORMAL_MISSING|OTHER|
|AU-b50a5b57669586191c33|州省地區|FORMAL_MISSING|OTHER|
|AU-b50a5b57669586191c33|有來源文件|FORMAL_MISSING|OTHER|
|AU-b50a5b57669586191c33|資料來源名稱|FORMAL_MISSING|OTHER|
|AU-b50a5b57669586191c33|資料來源URL|FORMAL_MISSING|OTHER|
|AU-c5e94422a89a23f82408|ASX代碼|FORMAL_MISSING|P2_COMPANY_MARKER|
|AU-cae6c11543b0da5f840d|ASX代碼|FORMAL_MISSING|P2_COMPANY_MARKER|
|AU-d1394abdef4c8d971c78|ASX代碼|FORMAL_MISSING|P2_COMPANY_MARKER|
|AU-d28382dfa82f1664065e|ASX代碼|FORMAL_MISSING|P2_COMPANY_MARKER|
|AU-e50ba6a268ea89226495|ASX代碼|FORMAL_MISSING|P2_COMPANY_MARKER|
|AU-f46f6d53e7196650495d|未上市公司|FORMAL_MISSING|P2_COMPANY_MARKER|
|AU-f46f6d53e7196650495d|ASX代碼|FORMAL_MISSING|P2_COMPANY_MARKER|
|AU-f81823bd8ba271840345|ASX代碼|FORMAL_MISSING|P2_COMPANY_MARKER|

## T1 固定事件入庫

事件檔逐位元組複製第9版CI原件；config檔與工具常數均為`a35421e6238b459ec6979a0843b1fa683a3ad1233b63c1dc378e68a1b3c70826`，CI驗證通過，正好2筆指定PushEvent。API是輔助核對，空窗／不可連不否定存證，同id時間或head衝突則invalid。兩個workflow都讀固定事件檔，缺少／invalid proof只印warning；VIC預期維持invalid。

|來源|valid|API輔助核對|推送時間UTC|原因|
|---|---|---|---|---|
|reviewed_source_521f635719be1686|True|MATCHED|2026-11-10T11:14:55+00:00|[]|
|reviewed_source_9e1ac5bb894d9077|True|MATCHED|2026-11-10T11:42:29+00:00|[]|
|reviewed_source_a197d77204b48c23|True|MATCHED|2026-11-10T11:42:29+00:00|[]|

第9版10格P6座標仍全部SAME。[10格守門](ci/t1_existing_10_p6_guard.csv)、[存證收據](ci/pre_cutoff_evidence_verified.json)。VIC沒有新增事件，仍PUSH_TIME_NOT_PROVEN_FOR_COMMIT；快照、宣告與截日不變。

原文使用CRLF；準備提交7996196曾被Git轉成LF，尚未開PR或跑CI即停止。研究者另行核准僅此檔案的一行.gitattributes例外，6eeaeae已還原原始位元組。工作檔、提交blob與乾淨匯出皆符合原SHA後才開本PR，沒有把SHA常數換成轉換後版本。[核准](event_bytes_exception_approval.json)、[驗證](event_bytes_verification.json)、[歷史停止證據](event_bytes_stop.json)。

## T2 公司層標記

研究者2026-11-18明確核准保留舊標記，只追加核准兩標記。[核准](append_markers_researcher_approval.json)。[不可變核准帳本](p2_marker_proposals_researcher_approved.csv)：70列Y、22列HOLD、135列空白；工具固定核准ID並核對第9版原提案SHA與全部欄位。只改70個指定位置的markers，舊marker、頁碼、SHA與數值均不動。

CI核准列結果：{"PASS": 70}；衝突0。FAILED_IN_CI 0列已反映到[審核表](p2_marker_proposals_approved.csv)，保留該頁前300字於[失敗表](p2_ci_marker_failures.csv)。沒有修marker或頁碼；來源不可驗者另外列NOT_CHECKED_SOURCE_UNAVAILABLE。[70列結果](p2_ci_marker_results.csv)。

40格公司欄位中，23格全部所需提案核准、17格有HOLD。23格中實際SAME 22格，未恢復1格；逐格列CI原因與queue，見[未恢復](p2_expected_but_not_restored.csv)、[40格實際結果](p2_company_cells_actual.csv)。這是對預期的核對，不把提案數或通過列數當成恢復格數。

唯一未恢復是Wandagee（AU-b50a5b57669586191c33）的ASX代碼。核准bffe8af62feb3459fa68只補/identity_declaration（第4頁）；原ASX屬性/attributes/1/context_evidence/0、1、2在第1、4、8頁仍各只有一個marker，因此strict_claims仍記MISSING_PAGE_OR_TWO_MARKERS。第9版提案盤點只列出該格的身分宣告，未完整列出這三個context，所以原23格是上限，不能當保證；本輪未自行補新marker或擴大核准範圍。[三個缺口](p2_unrestored_binding_gaps.csv)。

未套用任何其他專案層P2、P3/P4或總說明格式修改。明列核准的bffe8af62feb3459fa68雖屬ASX代碼提案，位置是/identity_declaration；共用身分宣告若讓其他欄位恢復，列OTHER並保留逐格值／來源，不冒充公司層直接恢復。[其他變化](ci/other_project_changes.csv)、[全部比較](ci/cell_comparison.csv)。

本輪8格OTHER全屬Wandagee：開發商、專案名稱、所在地中文／英文、州省地區、有來源文件、資料來源名稱／URL。因這筆明列核准的共用身分宣告通過，既有驗證規則採用已有輸入；沒有另外套用專案層提案或修改格式。

## 51欄coverage

|指標|第9版|第10版|
|---|---:|---:|
|filled_cells|1086|1116|
|T1 coverage|44.98%|45.22%|
|T2 coverage|26.96%|28.01%|

分母與不適用處理沿用正式規則，詳見[coverage](ci/coverage.json)。

## 程式範圍與測試

src變動0，累計**2157**；既有比較工具、robots、主機停止、B1、來源宣告、VIC快照、研究截日、氧化物係數及數值都未改。只新增一個config事件檔，其餘程式改動在tools/tests/workflow；claims僅追加70個核准位置的標記。

另有研究者明確核准的一行.gitattributes例外，只保護此事件檔原始位元組。新增16項測試，CI完整486項Python與R通過；Phase20、21-a、21-b、22-a、22-b MATCHED。研究CI是離線回歸，線上取得工作未執行。[研究證據](research_ci_checks.json)。兩個準備提交完成修補後才開PR，僅觸發一次乾淨CI與一次離線研究CI；收尾只含報告並skip ci，不重跑。

## 剩餘缺漏

|原因|格數|
|---|---:|
|RULE_INPUT_MISSING|293|
|NO_SOURCE_VALUE|62|
|SOURCE_NOT_ACQUIRED|734|
|SOURCE_AFTER_CUTOFF|4|

已停止等待研究者審查，PR保持Draft、不merge。
