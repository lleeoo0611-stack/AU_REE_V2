# CI 驗證去重

基準為 `feat/phase10-evidence-recovery-yield-20261127` 的 `2af6f611e51eb4ac9dda73419d1afeba70d1307e`。程式提交為 `fb537073f07a1df1b3667c388ae813e2ca2d20b9`，在獨立工作樹開發。Phase 11 的未提交修改仍在原工作樹。

## 工作流程

- Research 在同儲存庫的 PR 同時需要 Public 時產生完整 Python XML 測試報告。Public 核對同一 PR、實際 merge commit、runner 映像、Python 套件版本、R 與 OCR 執行工具、截日前證據收據和 XML SHA-256。驗證不符、找不到報告或遇到 API 錯誤時，Public 執行原本的完整測試。獨立發布流程仍在本機工作執行測試。
- `tools/phase10_ci.py` 為兩套 workflow 使用的路由。每次 PR 更新檢查完整 base 到受測提交的差異。單元測試改動執行對應測試，R 相關測試送到 R 整合工作，科學與正式資料改動執行封存重播。完整套件已列入 Research 時，快速工作只需檢查 diff。Public 會取消同 PR 的舊提交執行。
- 獨立公開來源重建、兩個乾淨封存重播、R 回歸、截日前證據及發布檢查保留。既有 workflow 與 job 名稱保留。

## 耗時與驗證

| 量測口徑 | 基準 | 修改後 | 狀態 |
| --- | ---: | ---: | --- |
| 本機同一 PDF → SQLite → R 測試的 Public 重複執行 | 25.196 秒 | 0.578 秒 | `PASS`，耗時少 97.7% |
| GitHub PR #27 Public 採納完整驗證 | 3,508.692 秒 | 未量測 | `PENDING_VALIDATION` |
| GitHub PR #27 Research 完整驗證 | 2,460.899 秒 | 未量測 | `PENDING_VALIDATION` |

本機量測於 2026-11-27 20:04:06.744591–20:04:32.519242 UTC 執行一次成功的既有整合案例，1 項通過且無略過。0.578 秒含製作收據 0.296 秒及驗證／複製 XML 0.282 秒。XML 逐位元一致，SHA-256 為 `2ef9b0cf903484363406f625248b5f901c3634ec38fecfada891349eb4989e8c`。本機量測未包含 GitHub 產物上傳或跨工作流程傳輸。整體 PR 耗時與 20% 目標仍待同口徑的 hosted CI 量測。[既有 Public 日誌](https://github.com/lleeoo0611-stack/AU_REE_V2/actions/runs/46044442609/job/140660248823) · [既有 Research 日誌](https://github.com/lleeoo0611-stack/AU_REE_V2/actions/runs/46044442614/job/140660217685)

PR #27 的 Public 記錄 906 項 Python 測試，步驟耗時約 446 秒。公開來源重建單獨耗時約 2,960 秒，是目前最大的等待成本。Phase 10 基準 `2af6f61` 的 Research 通過，完整工作耗時 36 分 17 秒。[Phase 10 Research](https://github.com/lleeoo0611-stack/AU_REE_V2/actions/runs/46054675956) · [Phase 10 Public](https://github.com/lleeoo0611-stack/AU_REE_V2/actions/runs/46054675947)

| 項目 | 狀態 |
| --- | --- |
| `actionlint`、`git diff --check`、24 項路由／公開來源診斷／依賴測試 | `PASS` |
| 既有 PDF → SQLite → R 整合案例及 XML 重用 | `PASS` |
| GitHub 跨 workflow 收據傳輸及端到端 CI 耗時 | `PENDING_VALIDATION` |
| 11 月 13 日全部歷史原件重播 | `BLOCKED_MISSING_ASSETS`，沿用 Phase 10 的 19 份缺件紀錄 |

`src/`、`R/`、`config/`、`data/` 與 `results/` 的 Git 樹與基準一致。沿用 78 個生產模組、343 條內部相依邊與無循環結構。三支科學函式的程式與複雜度一致。Research 共用 Public 已使用的 XML 測試報告工具，生產套件依賴一致。稀疏工作樹初次執行缺少整合 fixture 的既有參照檔，補齊後完成上述量測。

## 重現命令

在完整 checkout 安裝既有 CI 依賴與 R，以乾淨 Git 工作樹執行。`ImageOS` 與 `ImageVersion` 取自受測 runner。兩個工作使用同一受測 SHA，並各自產生截日前證據收據。

```sh
actionlint .github/workflows/research.yml .github/workflows/automated-build.yml
mkdir -p work
PYTHONPATH=src:tests python -m unittest -v test_phase10_ci test_v5_workflow_diagnostics test_module_dependencies \
  test_automated_build_clean.AutomatedBuildCleanTests.test_workflow_routing_uses_complete_pr_base_for_every_update \
  test_automated_build_clean.AutomatedBuildCleanTests.test_ci_build_has_no_experiment_dependency
python tools/verify_pre_cutoff_evidence.py --events-file config/pre_cutoff_evidence_events.json
python -m xmlrunner discover -s tests -p test_resource_admission_integration.py -o work/ci-python/test-xml
python tools/phase10_ci.py seal-python --bundle work/ci-python
python tools/phase10_ci.py verify-python --bundle work/ci-python
git diff --exit-code 2af6f61..HEAD -- src R config data results
```

| 階段 | UTC | 實際耗時 |
| --- | --- | ---: |
| 診斷 | 19:45:41–19:49:34 | 3 分 53 秒 |
| 實作 | 19:49:34–19:58:35 | 9 分 01 秒 |
| 驗證 | 19:58:35–20:04:32 | 5 分 57 秒 |
| 整理、記錄 | 20:04:32–20:06:18 | 1 分 46 秒 |
| 總計 | 19:45:41–20:06:18 | 20 分 37 秒 |
