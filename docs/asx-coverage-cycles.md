# 雙線資料覆蓋循環

沿用隔離分支 `experiment/asx-public-acquisition-20261109`，研究截止 2026-11-05。這次固定起點為 `bc6a901` 的 55 案 × 53 欄：1,168 格有值、1,747 格空白。

每輪同時追查未解的候選／外部名稱，以及現有專案的資源量、TREO 品位、氧化物組成與平均年產量。搜尋命中先進審查；取得文件不等於允許填值。文件指紋、專案歸屬、實體頁面、格位、單位、物料分母、資源範圍與日期都須通過，才重新從唯讀 Census 產出總表。

每輪依序執行：搜尋與下載、擷取與來源審查、重建 53 欄表、回歸測試、獨立重複產出、計數、提交與推送。失敗或未完成的一條搜尋線不能當成邊際收益為零。

## 停止條件與計數

`tools/review_coverage_cycle.py` 驗證輸出完整性，分開統計原案新填值、科學數值、新案資料、既有值更新、格式變化、撤回及合併移除。只有候選與數值兩條線都完成，且來源、測試、重現檢查通過，才判定當輪新增填值是否 **< 3**。

採較保守的原案新填值加新案所有已填欄位總數判定；新案仍獨立列帳。即使原案當輪只有少量新值，只要仍有新案資料通過，循環也會繼續。停止不代表全國專案已窮盡或所有空白都無法找到資料。

累計成果必須另外直接比較最初 55 案基準。某輪撤回、後輪恢復的相同欄位不能再當成原始缺口的新補值。新案帶來的新空白也不應誤認為原案資料退步。

## 來源與合併規則

ASX 代碼為文件日期的已驗證報告公司代碼，不自動聲稱即時權利或上市狀態。只有相同非空已驗證代碼，且同名或有證據的同專案別名，才可明確合併。區域同名、鄰近礦權或相同公司不同專案均不充分；不跨資源範圍加總數量。

WIM100 的稀土氧化物百分比以重礦物（HM）為分母。嚴格 opt-in 的轉換以同一資源列的已報告 HM 噸位計算各氧化物含量，再以同列礦石量作內部 ppm 表示；不能直接把 HM 百分比當 bulk-ore TREO 品位。Sc 排除，來源捨入區間保留，沒有原件公布的 TREO 總量、品位及比率維持空白。

Yangibana 的平均年產 NdPr 使用同一 19 年 DFS、100% 專案基準的直接年報揭露。原研究日期與後續年報重申日期分別保留。相同工程研究的範圍文字需有來源證明才能對齊，不能依資料新舊自動合併不同研究。

## 可續跑的操作入口

```text
python tools/capture_research_sources.py --requests OWNED_REQUEST_CONFIG --out ASSET_ROOT
python tools/discover_asx_archives.py --issuer-code CODE --years YEAR --out ARCHIVE_ROOT
python tools/export_project_summary.py --help
python tools/extend_project_identity.py --help
python tools/review_external_project_names.py --help
python tools/review_coverage_cycle.py --before BEFORE_53 --after AFTER_53 --manifest REVIEW_MANIFEST --out CYCLE_REVIEW
python tools/package_coverage_cycle.py --help
```

沿用 [第六輪的重建方式](asx-gap-round6.md)，資產目錄另加入 `auto_numeric=work/auto-iteration-numeric`、`auto_candidates=work/auto-iteration-candidates`、`coverage_fresh=work/coverage-20261110/fresh`。每輪使用各自配置快照，不能以最終配置冒充較早一輪的來源驗證。

循環審查器檢查計數、來源與檔案指紋、測試收據及停止資格；搜尋完成與語意判讀由本次研究審查紀錄宣告，不把計數器說成獨立 PDF 金標審查。新資料仍需相同來源審查關卡，不能無條件自動填值。

公開結果位於 `results/asx-coverage-2026-11-10/`，各輪保留總表、逐格來源、缺口、三份來源／歸屬／代碼配置、測試收據、增量及停止判斷。原始 PDF、SQLite、頁面影像／全文、原始 Gemini 輸入列與搜尋全文不公開；本機逐項對照另行交付。

歷史測試資料在精簡工作樹不完整時，使用本分支的程式與設定，連結 canonical 歷史資料作唯讀測試來源並限制寫入。沒有略過原測試斷言，不聲稱完整歷史／R 重建或新的遠端 CI 通過。
