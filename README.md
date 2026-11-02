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

See [migration decisions and unfinished acceptance scope](docs/migration.md).

The [frozen real-source pilot results](results/pilot-2026-11-02/README.md) include directly readable
ranking, sensitivity, source-level trace and exact replay inputs. They are limited scientific outputs,
not acceptance of all V2 research requirements.
