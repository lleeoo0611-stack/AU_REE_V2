# AU_REE_V2

## Census 覆蓋率正規化測試

固定分母 3,034 格下，實際補入 Franklyn 經緯度、Voyager 礦床代碼與 Lyons 合併 NdPr 蘊藏量，覆蓋率由 82.27% 升至 82.40%。16 組排名相同。[本輪結果與重播方式](results/ree-project-census/coverage-locked-20261125/README.md) · [逐格差異](results/ree-project-census/coverage-locked-20261125/coverage_delta.csv)

## Phase 22 × ASX 的 173 格續查

本輪追查 80 格座標、39 格礦床或開發階段分類，以及其他 54 格。兩版研究截日同為 2026-11-13，覆蓋率沿用原分母 3,034 格。[本輪總表與驗收](results/ree-project-census/gap173-20261122/README.md) · [逐格處置與來源](results/ree-project-census/gap173-20261122/followup_review.csv)

持有本輪原件套件時可從空工作目錄重建全部結果。

```sh
au-ree-v2 all --source-mode offline --as-of 2026-11-13 --source-replay results/ree-project-census/gap173-20261122/source_acquisition.json --replay-assets KIT/assets --tessdata data/ocr --work work/replay173
```

## Phase 22 × ASX 的 189 格補證與重播

本輪沿用 2026-11-13 的研究截日，以原來的 3,034 個適用格比較覆蓋率。新總表、逐格補證紀錄、排名差異及重播收據見[本輪驗收](results/ree-project-census/gap189-20261122/README.md)。

持有本輪原件套件時，可用同一入口重建 SQLite、Census 及篩選後的 MCDA。

```sh
au-ree-v2 all --source-mode offline --as-of 2026-11-13 --source-replay results/ree-project-census/gap189-20261122/source_acquisition.json --replay-assets KIT/assets --tessdata TESSDATA_DIR --work work/gap189-replay
```

持有前版原件庫時，亦可使用前版收據與原件庫，外加 `--static-pdfs ADDITIONS`。該目錄應包含來源登錄指定的三份靜態 PDF 與 2026-11-02 ASIC 名冊 ZIP。流程會核對原件雜湊、版本及截日，另輸出 `gap_review.csv` 追蹤原始缺格。

## 2026-11-20 整合證據模型開發版

Census 使用 2026-11-13 的來源截日，技術揭露使用 2026-11-05 的編碼基準，正式 C1 使用政策指定的 2026-10-29。SQLite 寫入連線可原地遷移先前版本。正式六 Gate、研究用十二階段與樣品方法均有各自的可追溯輸出。[本版實際結果與驗收](results/ree-project-census/integrated-evidence-v1-20261120/README.md) · [資料契約](docs/phase22-asx-maintenance-audit.md) · [正式資格](docs/phase4-discovery-eligibility.md)

在乾淨 checkout 安裝套件、R 4.5.2 和 Tesseract 英文模型。先把本版的原件套件放在指定位置。該套件包括 `assets/<SHA-256>`、`asset_manifest.json`、`bundle_verification.json` 及 `source_acquisition.json`。原件由提供套件的保管人交付，公開倉庫提供收據。CLI 在空的工作目錄建庫。

```sh
python -m pip install -c requirements-constraints.txt .
au-ree-v2 all --source-mode offline --as-of 2026-11-13 --source-replay KIT/source_acquisition.json --replay-assets KIT/assets --tessdata TESSDATA_DIR --work work/rebuild
```

持有既有 SHA 原件庫時，可用下列命令建立並逐檔核對本版套件。Python、SQLite、R、Tesseract 版本、執行期套件及英文模型雜湊隨 `census_release.json` 保存。Linux CI 與 Windows 本機使用各自的 OCR 安裝，跨環境比較須同時核對模型雜湊。篩選後的三種 R 排名仍使用 Phase 22 的正式評分契約。

```sh
python tools/bundle_census_replay.py --receipt results/ree-project-census/integrated-evidence-v1-20261120/source_acquisition.json --source-assets ORIGINALS_BY_SHA --out work/portable-kit
```

## Phase 22 × ASX Project Census

同一入口執行來源擷取、SQLite 入庫、Census 匯出、篩選及 Phase 22 的 MCDA。

[現行總表、驗收與封存索引](results/ree-project-census/README.md) · [維護審查與國際資料庫試跑](docs/phase22-asx-maintenance-audit.md)

```sh
au-ree-v2 all --source-mode live --as-of 2026-11-13 --work work/census-live
au-ree-v2 all --source-mode offline --source-replay work/census-live/source_acquisition.json --as-of 2026-11-13 --work work/census-replay
au-ree-v2 all --source-mode offline --static-pdfs PATH_TO_PDF_LIBRARY --as-of 2026-11-13 --work work/census-static
```

線上建置沿用 ASX 測試的主機停止、請求額度與同 SHA 後備規則。Phase 22 封存來源優先保留原鍵與原版本，ASX 擴充其餘來源。新發現的候選文件須經來源與宣告查核才會進入證據。離線重播需要收據與其指向的原件，會逐一驗證 SHA。請保留建置工作目錄中的原件。

`--static-pdfs` 直接讀取本機原件，依登錄的 SHA 與出版日期選入資料，可重複指定資料夾。搭配 `--source-replay` 可保留既有封存來源並補入同 SHA 的 PDF。兩種離線選項共用後續的頁碼查核、SQLite、總表與排名。

`--source-mode frozen --snapshot-lock PATH` 從指定凍結來源輸出 Census。既有 `rebuild --snapshot-lock PATH` 仍是驗證 Phase 22 科學成果的入口。`--out` 與 `--census-filter` 需要明確的 Census 來源模式，不會自行切換來源或截日。

完整離線重播可將已取得的原件存成 SHA 命名的本機套件。套件含原始來源與取件收據，放在本機工作目錄。發布的 `census_release.json` 提供來源 SHA、日期角色、設定雜湊、Census 母體與各排名面板的輸入輸出雜湊。

```sh
python tools/bundle_census_replay.py --receipt work/census-live/source_acquisition.json --out work/census-replay-bundle
au-ree-v2 all --source-mode offline --source-replay work/census-replay-bundle/source_acquisition.json --replay-assets work/census-replay-bundle/assets --as-of 2026-11-13 --work work/census-replay
```

總表輸出到 `results/ree-project-census/<run-id>/REE project census.csv`。欄名和順序沿用 ASX 測試的 51 欄合約，與 2026-11-16 HTML 共用欄位一致。歷史 HTML 裡已退役的兩個欄位依 ASX 合約留在歷史成果。

可加上 `--census-filter "州省地區=西澳大利亞州"` 或使用 CSV 中其他欄名及實際值。同一欄位的多個值採 OR，不同欄位採 AND。篩選記錄與來源追溯隨總表輸出。MCDA 先確認通過篩選的穩定 Project ID，再沿用各面板的證據和可比性條件。具備資料的面板將排名寫入同一個結果目錄。

歷史研究仍使用下方的 `rebuild --snapshot-lock`。 `discover` 提供搜尋計畫，實際取得來源由 `all --refresh` 執行。 `acquire` 是同一擷取階段的執行入口，只回傳來源收據。

已完成的整合 SQLite 可以唯讀匯出。搬移時保留同一工作目錄下的 `databases/<run-id>/canonical.sqlite` 及 `runs/<run-id>/`。匯出會核對此執行的設定與來源鎖、完成收據、專案身分表、取得結果及已驗證的衍生頁面。外部原件以明確指定的 SHA 原件庫重新定位。來源驗證失敗會停止匯出。

```sh
au-ree-v2 export-summary --database WORK/databases/RUN_ID/canonical.sqlite \
  --replay-assets BUNDLE/assets --out WORK/verified-export
```

Latest: **Phase 22 — native-candidate acquisition, source-bound evidence and shared-method MCDA**, cutoff **2026-11-05**, configuration `research-v8-native-candidate-shared-draws`. See [results, limits and reconstruction](results/phase22-2026-11-06/README.md), [verification](results/phase22-2026-11-06/evaluation.json), and [evidence priorities](results/phase22-2026-11-06/six_domain_gap_priority.csv).

Current evidence: **33 canonical registry groups, 22 resource cases, 20 complete transparency point scores and 6 complete six-domain cases**. Wolverine/Browns Range joins the previous five after original resource composition and Project financing-plan disclosure recovery. New national candidate Kennedy enters resource/composition ranking, with seven disclosure items Unknown; it is not a new complete six-domain case. Barkly's resource arithmetic conflict and unavailable detailed prospectus remain unresolved. Counts of source rows, native sites, resource scopes, groups and independent Projects remain distinct.

Technical remains **[Technical Disclosure Transparency v1](docs/technical-disclosure.md)**: seven binary items, denominator7, unknowns retained; not technical capability, feasibility or JORC compliance. New scopes enter the same incremental review as Unknown until source-bound coding is complete. Frozen Phase19/20 reviews and results remain unchanged. Formal C1 gates and approval status remain separate from exploratory completeness.

Unregistered native candidates now produce stable evidence-search tasks and can enter the same registry through source-bound `register-candidate` declarations. Dynamic WAMEX searches, cursor-aware acquisition and the versioned common classifier retain original IDs and unresolved crosswalks. Current evidence views exclude superseded coding without deleting history. R core-panel computation and peer comparisons have separate verified dependencies; shared draws feed SAW, PROMETHEE II and TOPSIS without changing historical PROMETHEE sequences. One formal SQLite store remains in use.

Reconstruction and tests:

```sh
au-ree-v2 all --as-of 2026-11-05 --work work/phase5
au-ree-v2 rebuild --as-of 2026-11-05 --snapshot-lock results/phase22-2026-11-06/snapshot_lock.json --work work/phase22-replay
python tools/check_replay.py results/phase22-2026-11-06 work/phase22-replay/latest.json
python -m unittest discover -s tests -v
Rscript tests/test_methods.R
```

On Windows supply `--rscript "C:/Program Files/R/R-4.5.2/bin/Rscript.exe"` when R is not on PATH. `--skip-r` explicitly omits ranking. Cache hits report reuse, not a new Monte Carlo execution. Government source coverage is not national Project completeness. ACT dedicated acquisition, external territories and the REMP2025 workbook remain incomplete. The prospective agent-labelled validation is not independent national ground truth; independent high-impact disclosure recoding is still outstanding. Six selected cases do not support national inference or Aim C causality.

Historical releases: [Phase21](results/phase21-2026-11-05/README.md), [Phase20](results/phase20-2026-11-05/README.md), [Phase19](results/phase19-2026-11-05/REPORT.md), [Phase16 remediation](docs/phase16-remediation.md), and the earlier frozen results below. Branch/PR names are historical; PR #6 stays Draft and is not automatically merged.

One Python / SQLite / R research system for Australian rare-earth evidence, official GIS and explicitly scoped exploratory MCDA. Government source records, deposits and registry groups are not interchangeable independent Projects. No national completeness or national six-domain development ranking is claimed.

```sh
python -m pip install .
au-ree-v2 all --as-of 2026-11-05 --work work/phase5
python -m unittest discover -s tests -v
Rscript tests/test_methods.R
```

Python 3.11+ and R 4.5.2 are used in CI. No R packages are required. On Windows, pass
`--rscript "C:/Program Files/R/R-4.5.2/bin/Rscript.exe"` if R is not on PATH.
`--skip-r` explicitly produces coverage without ranking. All inputs are managed in this repository;
no pre-existing local database, downloads or CSV exports are required. Public endpoints can be
refreshed, while committed source snapshots allow offline reconstruction.

```sh
au-ree-v2 all --dry-run
au-ree-v2 acquire
au-ree-v2 all --refresh
au-ree-v2 recognize --source-key SOURCE_KEY
au-ree-v2 evidence --project mt-weld
au-ree-v2 gis --as-of 2026-11-02
au-ree-v2 rebuild --as-of 2026-11-02 --work work/replay --snapshot-lock work/runs/RUN_ID/snapshot_lock.json
au-ree-v2 diff --before BEFORE/logical_database.json --after AFTER/logical_database.json
```

Use a new `--work` directory for an independent historical reconstruction. Each work directory has
one canonical SQLite store with stable native IDs, immutable source hashes, observation scope,
page locators, transformation version, dated relationships and run/error logs. Historical source versions
are retained. `snapshot_lock.json` pins the exact inputs; configuration, code hash and logical database
hash accompany each run. New source bytes never reuse an old PDF extraction without a checksum review.

Outputs under `work/runs/<Run ID>/` include Census CSV/GeoJSON, cohort coverage, resources,
value-level provenance, review issues, R ranking comparison, weight-only and source-rounding-only
Monte Carlo intervals, leave-criterion/domain-out, scoring/threshold sensitivity, cohort sensitivity,
partial dominance and AHP consistency audit. Data missing from a criterion stays missing.

Resource, historical Development and current six-domain cohorts have versioned entry rules; the current resource-defined sample is 21. The historical Development cohort still requires compatible recovery and must not gate the new disclosure-based six-domain panel.
The original November2 pilot compared
Mt Weld's reported Mineral Resource with Browns Range's **Wolverine-only** Mineral Resource,
not total Browns Range project inventory. Reported contained totals are retained after rounding checks.
Government representative deposit points are not legal project footprints or proof of transport access.

The scenario weights and their reciprocal AHP matrices are **researcher assumptions**, not elicited
expert preferences. Scores use fixed, versioned physical anchors. Rank frequencies describe
the specified preference experiment, not mine development success probabilities. External Aim C
inference remains incomplete; model sensitivity is not evidence of geological causation.

One [workflow](.github/workflows/research.yml) runs clean reconstruction and regression tests on pushes/PRs,
with manual/weekly source refresh and retained artifacts. Source failures leave the frozen evidence available.
Source discovery includes bounded issuer pagination, unseen-document priority and PDF recognition. Government adapters retain original responses, complete native-ID inventories and incremental versions.

## Source and GIS acquisition

The source registry includes Geoscience Australia's TOPO250K 2WD road classes,
operational railway/siding lines and mapped >=66 kV power lines, plus the Australian
Government **Resources and Energy Major Projects 2025** XLSX listing. Run
`au-ree-v2 all --refresh --as-of YYYY-MM-DD` to acquire and use the extended source set in one run.
For an offline replay, pass the saved acquisition receipt or an historical snapshot lock.
Registered targets become evidence after original bytes and checksums are retained.
Phase6/7 contain frozen state inventories and GIS layers.

Spatial line features are queried through complete ArcGIS object-ID inventories in
project-scoped EPSG:3577 search windows. A distance is released only if the source
window covers the selected project coordinate and the nearest line is strictly
inside the registered radius. Road distance is not a vehicle route, operational
rail geometry is not a freight service commitment, and a mapped power line is
not proof of connection capacity. Coordinates are cutoff-filtered to prevent
historical runs from reading later source records. `gis_metrics.csv` exposes
metric, query boundary, layer hash and coordinate-source hash.

The REMP workbook is an **additional, non-exhaustive project discovery source**
(the official list omits earlier exploration and projects below its cost threshold).
Rows containing REE terminology are ingested as stable per-snapshot
`SOURCE_RECORD` entities, never silently promoted into `PROJECT` entities.
`census_candidates.csv` exposes every matched source row with sheet, line number
and source SHA; `deposit_type_summary.csv` summarizes the existing official
deposit entities. Matching these records to independent, stable mining projects
remains part of the national Census expansion.

See [migration decisions and unfinished acceptance scope](docs/migration.md).

The [frozen real-source pilot results](results/pilot-2026-11-02/README.md) include directly readable
ranking, sensitivity, source-level trace and exact replay inputs. They are limited scientific outputs,
not acceptance of all V2 research requirements.

## Historical Phase 2: official WA resource listing (2026)

The Western Australian Government DMPE February 2026 REE investment flyer (physical
PDF page 1, resource table as at January 2026) supplies **20** government-listed
projects with dated ore Mt, TREO grade, reported contained TREO, named owner and
qualitative development status. A frozen, SHA-256-addressed CSV transcription and
row-level source locators are in the same canonical SQLite database; the original
PDF URL is in the source registry, with an independent raw-PDF acquisition target.
Do not mistake the CSV transcription for the original PDF snapshot.

Two explicitly linked project identities (Mt Weld and Browns Range) retain their
original stable IDs; 18 new WA-government-list IDs are distinct PROJECT entities.
They are a **partial WA expansion**, not a complete all-Australia Census. The source
rows are also kept as SOURCE_RECORD entities with dated LISTED_AS_PROJECT relations.
The government resource figures have status OFFICIAL_SUMMARY_SCOPE_UNVERIFIED
because the table does not define JORC categories or reconcile each project/deposit
resource scope. They are never substituted for the two existing, PDF-checked
resource claims in formal MCDA. Official status and owner are descriptive data;
missing Strategic, Technical, financing and approvals scores remain missing.

Each run now outputs official_resource_inventory.csv, project_domain_evidence.csv,
and census_link_candidates.csv. Exact-name/state GA deposit hits are **candidate
links only**: no entity merger, inferred project footprint or GIS release.
Geoscience Australia's national deposit collection and the WA project list must
not be added together as a count of unique Australian projects. Aim A/B full-panel
ranking and Aim C statistical inference remain blocked by incomplete evidence.

## Multi-state national project profiles (Austrade 2026)

Seven REE upstream projects from Austrade's March 2026 *Australian Critical
Minerals Prospectus* (printed pp. 5 and 31-37) are retained as national
SOURCE_RECORDs and linked to PROJECT identities, including five new stable
project identities across VIC, NSW and NT. Existing Browns Range and Yangibana
entities are reused through explicit aliases, not name-only fuzzy matching.
Profiles carry source-anchored descriptions of strategic products, process
routes, study milestones and financing/approvals/offtake. These are **descriptive
reporting-date facts**, not validated recovery rates, funds available, confirmed
permits for other projects or C1 MCDA scores. The same schema exports
national_prospectus_evidence.csv and more informative project_domain_evidence.csv.
Raw Austrade PDF acquisition is registered independently from the
SHA-256-addressed table transcription. The 2026 prospectus is an investment
selection, not a national Census closure or complete six-domain evidence panel.

## Nationwide deposit geography (descriptive Aim C)

Every official GA deposit position in the selected 2025 AIMR layer can be
compared to the complete GA major-port point layer, independently of the Project registry. Outputs `deposit_port_distances.csv` and
`aim_c_deposit_type_port_summary.csv` give per-deposit EPSG:3577 proximity and
state/deposit-type medians; every row preserves exact source hashes and geographic
unit. Missing/invalid coordinates are reported as missing, never zero or
silently removed from population counts. This is nationwide **DEPOSIT**
descriptive GIS, *not* 149 independent projects, an end-to-end transport route,
or Aim C's proposed project ranking driver inference. Project-scoped road,
rail and power snapshots are never extrapolated to these deposits.

## Legacy national E1 source selections (frozen cross-state evidence)

The independent 2026-10-29 AU_REE national screening archive contains **339
selected records**: 317 records copied from official-source feature selections
and 22 legacy-only historical ledger entries. These are loaded into the same
SQLite store as SOURCE_RECORD, never promoted to PROJECT, with the original
source family/native ID, raw selected attributes, geometry, locator, original
chunk SHA-256 and pinned old-repository commit. The selected-feature snapshot
is hash-locked and committed. It represents a subset of the prior 1006 raw
screening candidates, not the complete national project census or the original
full government-source download. In V2, 83 GA AIMR-selected records can be
linked to already registered official GA DEPOSIT native IDs; these links are
geological source relations only, not project/deposit identity assumptions.

Outputs: national_e1_candidates.csv, national_e1_coverage.csv and
national_e1_port_distances.csv. GIS describes SOURCE_RECORD point locations
using a globally complete official port layer; it does not release project
logistics scores. The old project/occurrence records remain separate from
25 source-backed named PROJECT identities. External issuer corroboration and
new nationwide discovery remain open.

## WA resource-only exploratory MCDA (n=20, separate from validated resource cohort)

An independently labelled `official_wa_resource_screen` is computed from 20
rows in one Western Australian government February 2026 project resource table.
It uses reported **contained TREO (R1)** and **TREO grade (R2)** with fixed,
versioned physical score anchors; both quantities have an algebraic dependence
through ore tonnage, so this is a resource-screening trade-off, not a six-domain
independent-criteria assessment. Three transparent researcher *assumption*
preferences (80/20 inventory, 20/80 grade, 50/50) run the existing R AHP
consistency, PROMETHEE II, SAW, TOPSIS, weight and rounding experiments,
leave-criterion-out, cohort removal, dominance pairs, and cross-method tests.
The rounding experiment covers only the reporting precision (±0.5 kt TREO,
±0.005 percentage points grade), not geological/measurement uncertainty.
The matrix retains each original raw value, source SHA, table locator, stage
and explicit `OFFICIAL_SUMMARY_SCOPE_UNVERIFIED` status. **None of these 20
observations pass the issuer-JORC resource-defined gate, and a government-only
screen is not a development-potential ranking.** The original 2 issuer-verified
resource/port pilot and separate six-domain cohorts remain unaffected.

R also exports `aim_c_stage_rank_association.csv`: an exploratory Spearman
association between government-described development stage and resource-only
screen rank. Stage is an external descriptor absent from this score matrix,
so the output is not a mechanical criterion correlation; selection bias,
confounding and small stage-group sizes prohibit causal inference.

**Security of historical selection:** one historical public-document URL in the
legacy selected-feature archive contained an access query parameter. The V2
committed snapshot is a deterministic redacted derivative; its own SHA-256 and
the immutable upstream original selection SHA-256 are both retained. The
redacted selection preserves feature identity, attributes, coordinates and
original government chunk hashes, while the original query parameter is never
republished in current database snapshots or result exports.

The historical selection snapshot also contained escaped-newline encodings of
this same access parameter. V2 sanitization now removes all seven occurrences
before inclusion in the current source manifest. The original upstream hash
remains as an attestation, not a redistributed unredacted payload.

Historical Phase 4 increment: [source discovery and C1 compatibility](docs/phase4-discovery-eligibility.md), [frozen outputs](results/phase4-2026-11-03/README.md).

Historical Phase 5 increment: [sources and research results](docs/phase5-primary-evidence.md), [frozen comparison](results/phase5-2026-11-03/README.md).


Phase14 adds [bounded official WAMEX/GSQ report discovery and measured recovery](docs/phase14-official-reports.md): four WAMEX originals,315→321 validated numeric statements, unchanged21 resource cases and no extra common MCDA sample. [Frozen results](results/phase14-2026-11-04/README.md) preserve the original gates and methods. Live update status is reported separately from offline scientific CI; GSQ document delivery remains partial.

## Phase 15：來源限定的技術擷取與分析

已將既有 Dubbo／Cummins 原件及新取得的 Donald／Nolans 技術表接入同一 CLI、SQLite 與 Evidence Selection。379 個來源格位包含 371 個通過驗證的數值，產生試劑強度、品位—回收率、附條件精選保留比及流程一致性分析；不代表379次獨立測量，也未更改正式T1或C1。

[研究報告](docs/phase15-source-bound-technical.md) · [凍結結果與重現命令](results/phase15-2026-11-04/README.md) · [逐文件評估](data/phase15_document_benchmark.json)。

Phase16：來源限定的 Technical 操作化、MINEDEX 批次核對與驗證分層，見 [研究報告](docs/phase16-technical-model.md) 及 [可重建結果](results/phase16-2026-11-04/README.md)。

Phase 16 remediation: [source scope, identity repair and process-specific MCDA](docs/phase16-remediation.md); [reconstructable results](results/phase16-remediation-2026-11-05).
