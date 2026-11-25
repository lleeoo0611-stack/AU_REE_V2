# Phase 22 × ASX 檢索實驗後的 Census

兩次獨立離線重跑分別產生 2,500／3,034（82.40%）與 2,501／3,034（82.43%），增加 0.033 個百分點。全表適用但缺值 527 格；原有不適用集合相同。兩組 SQLite 均通過完整性與外鍵檢查。16 組 MCDA 的 160 份實體輸出和原版的指紋均相同。生產程式保持 42 個模組、157 條內部引用、零循環。全套 Python 測試 615 項、針對性測試 36 項及五組 R 方法測試通過。

Perenjori 新增的礦床型態代碼為 `iac`，保留探勘模型、離子吸附性尚未證實的限定。資料截日為 2026-11-13。[Census 總表](REE%20project%20census.csv) · [逐格差異](coverage_delta.csv) · [欄位來源](field_provenance.csv) · [配對實驗、驗收與重現方式](../../nlp-census-ab-20261126/README.md)

本版沿用前版來源收據與相同的 715 份原件套件。[可攜來源收據](../coverage-locked-20261125/source_acquisition.json) · [原件指紋清單](../coverage-locked-20261125/asset_manifest.json)
