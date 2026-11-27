# 2026-11-28 舊版 claims-locators 收據封存

- 封存基準：`2af6f611e51eb4ac9dda73419d1afeba70d1307e`（`feat/phase10-evidence-recovery-yield-20261127`）。
- 完整封存分支：[`archive-phase10-legacy-20261128`](https://github.com/lleeoo0611-stack/AU_REE_V2/tree/archive-phase10-legacy-20261128)，保留原始相對路徑與所有 Git blob。
- 本輪工作分支：`chore/archive-legacy-claims-20261128`。
- 封存範圍：`results/claims-locators-2026-11-16/{v5,v6,ci_v4,ci_t0}/`，113 檔、50012243 bytes（約 47.70 MiB）。
- 移出原因：這些是舊版實驗與 CI 中間輸出，較新的 v8–v10 已作為比較與標記工具的基準；封存不表示這些歷史觀測無效。
- 保留現行：`src/`、`tests/`、`config/`、`data/`、全部 `results/phase*/`、`results/ree-project-census/`、`claims-locators` v8–v10。原始來源、SHA、Project ID、截日及 frozen locks 完全不動。
- 還原方法：在清理分支上執行 `git restore --source archive-phase10-legacy-20261128 -- results/claims-locators-2026-11-16/v5 results/claims-locators-2026-11-16/v6 results/claims-locators-2026-11-16/ci_v4 results/claims-locators-2026-11-16/ci_t0`，再自行提交；亦可從封存分支檢視或下載原路徑。
- 重要：封存分支保留資料，工作樹減少約 47.70 MiB；Git 歷史倉庫的實際磁碟大小不會因此直接縮減。
- 驗證限制：已以 Git 樹狀清單、相關腳本及 CI 設定確認未移動正式證據。因執行環境無法連線 GitHub 進行完整 checkout，Python / R 整合與封存重播仍須由 PR CI 驗證。

逐檔原路徑、大小與 Git blob SHA-1 見 [JSON 清冊](2026-11-28-claims-locators-manifest.json)。
