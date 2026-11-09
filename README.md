# AU_REE_V2

Experimental branch: [all-field coverage cycles](docs/asx-coverage-cycles.md), [current continuation report](results/asx-continuation-2026-11-10/README.md). Current table: 71 projects × 53 columns, 1417 filled cells and 2346 unknowns. This series starts from 59 projects and stops only after a complete round adds zero verified cells; unresolved downloads cannot count as zero yield. Original 59, newly admitted projects and cumulative original 55 coverage are audited separately. Source-bound ASX and same-project rules remain in force; canonical SQLite is unchanged. [Previous series](results/asx-coverage-2026-11-10/README.md).

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

The source registry now includes Geoscience Australia's TOPO250K 2WD road classes,
operational railway/siding lines and mapped >=66 kV power lines, plus the Australian
Government **Resources and Energy Major Projects 2025** XLSX listing. Run
`au-ree-v2 acquire` and then `au-ree-v2 all --as-of YYYY-MM-DD` to reconstruct
the extended source set; archived `data/manifest.json` snapshots remain the only
inputs used in a normal offline replay. Registered targets become evidence only after original bytes/checksums are retained. Phase6/7 contain frozen state inventories and GIS layers; the latest REMP2025 workbook update remains unavailable after timeout.

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

Current iterative ASX coverage and review: [results/asx-current](results/asx-current/REVIEW.md).
This directory contains only the latest reviewed summary and verification, not duplicated iteration archives.
