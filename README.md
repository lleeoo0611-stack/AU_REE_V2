# AU_REE_V2

Independent Python / SQLite / R research system for Australian rare-earth projects.
The first working slice reconstructs real public evidence, computes official GIS port distances,
and runs a **resource/infrastructure pilot**, with full provenance and explicit limits.
It does not claim a complete national Project Census or a six-domain development-potential ranking.

```sh
python -m pip install .
au-ree-v2 all --as-of 2026-11-02
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

Resource, Development and Full-evidence cohorts are separate. Two registered project scopes have
dated TREO Mineral Resources; six-domain coverage is currently incomplete. The pilot compares
Mt Weld's reported Mineral Resource with Browns Range's **Wolverine-only** Mineral Resource,
not total Browns Range project inventory. Reported contained totals are retained after rounding checks.
Government representative deposit points are not legal project footprints or proof of transport access.

The scenario weights and their reciprocal AHP matrices are **researcher assumptions**, not elicited
expert preferences. Scores use fixed, versioned physical anchors. Rank frequencies describe
the specified preference experiment, not mine development success probabilities. External Aim C
inference remains incomplete; model sensitivity is not evidence of geological causation.

One [workflow](.github/workflows/research.yml) runs clean reconstruction and regression tests on pushes/PRs,
with manual/weekly source refresh and retained artifacts. Source failures leave the frozen evidence available.
Known-document refresh is implemented; discovery of new announcements is still to be added.

## Automated official-source expansion (in progress)

The source registry now includes Geoscience Australia's TOPO250K 2WD road classes,
operational railway/siding lines and mapped >=66 kV power lines, plus the Australian
Government **Resources and Energy Major Projects 2025** XLSX listing. Run
`au-ree-v2 acquire` and then `au-ree-v2 all --as-of YYYY-MM-DD` to reconstruct
the extended source set; archived `data/manifest.json` snapshots remain the only
inputs used in a normal offline replay. The new entries in `config/sources.json`
are registered acquisition targets, **not yet frozen evidence** until their live
bytes and checksums have been retained as snapshots.

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

## Phase 2: official WA resource listing (2026)

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
compared to the complete GA major-port point layer, independently of the 25
registered Project entities. Outputs `deposit_port_distances.csv` and
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
