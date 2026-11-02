# Migration decisions and acceptance boundary

Legacy repository inspected at `093d724cc25fc319725bf347fc4d8ab196aadaf3` (main, fetched 2026-11-02).
The local read-only Proposal `sources/20260906 purposal.pptx` was read alongside the legacy README,
R/run_mcda.R, config/{sources,criteria,gis}.json, src/au_ree/stages/{gis,eligibility}.py,
tests/test_stages.py and original resource-review tables. The user's V2 brief supersedes the old
chat policy requiring six independently signed gates before any ranking.

| Legacy component | Decision and evidence |
| --- | --- |
| R AHP, SAW, PROMETHEE II, TOPSIS, Monte Carlo | Adapt compact numerical kernels; validate against analytical dominance/tie/consistency tests. Legacy implementation inspected, not assumed correct from presence of tests. |
| Cohort-relative SAW/TOPSIS scaling | Replace by fixed physical anchors before scoring. Audit threshold and scoring-function sensitivity separately. |
| EPSG:3577 point-to-geometry distance | Retain with complete archived GIS ID inventory; independent signature is not required to compute a reproducible public-data metric. |
| Source-native identity and SHA-256 provenance | Retain. Do not merge project and deposit identities or infer legal footprint from a point. |
| Six-gate all-or-nothing eligibility | Replace by frozen coverage-based cohorts; review issues are local to affected observations. No fabricated independent approval. |
| Batch-specific scripts/workflows and historical review sheets | Leave in legacy repository. One source registry, one CLI, one schema and one workflow in V2. |
| Local approved database and missing state-export CSV inputs | Do not migrate as runtime dependencies. Commit managed public source originals and immutable manifests. |

## Verified minimum vertical slice

149 GA source deposits, two explicitly registered project/resource scopes, 64 official GA ports,
two dated issuer resource PDFs. These are selected pilot data, **not a complete national Project Census**.
The source IDs are not 151 independent projects. Neither project has a complete six-domain panel yet.
The three scenarios are assumptions; a two-criterion pilot cannot answer the full development-potential question.

Current tests cover clean isolated bootstraps, byte-identical logical data/scientific outputs, idempotent import,
identity stability, snapshot look-ahead prevention, basis/category/units/range checks, conflicting evidence,
nonblocking unrelated projects, failed acquisition with retained snapshots, partial ArcGIS refusal,
GIS metric invariants and independent R numerical invariants. CI execution is confirmed only by the actual run.

## Remaining scope

- Extend official REMP workbook source-record discovery and GA deposits with state registries, ASX/issuer project evidence, machine-resolved cross-source identities and stable project IDs. REMP candidates are not automatically counted as Projects; no full national Census yet.
- Discover new issuer/ASX announcements (current registry refreshes known document URLs only), bind new table extractions to new SHA versions and extend event timelines.
- Expand same-scope composition, recovery/mineralogy/NORM, development, approvals, financing and offtake evidence. No geological type is substituted for processing difficulty.
- GA road, operational rail and power layers now have versioned source definitions and complete project-scoped ArcGIS retrieval with distance/coverage checks; actual national coverage is pending first durable layer snapshots. Existing offline pilot still contains ports only.
- Expand beyond the two-scope pilot, freeze comparable six-domain cohorts and document expert AHP judgments if actually obtained.
- Measurement uncertainty requires source-supported bounds; the existing rounding experiment is not a measurement-error model.
- Cohort deletion returns no numerical result with n=2; external Aim C inference is explicitly incomplete until independent predictors and adequate samples exist.
- Scheduled new snapshots persist as Actions artifacts (90 days), not automatic commits. Promote reviewed artifacts into the managed manifest to retain them permanently.

These are unfinished research requirements, not acceptance PASS claims.

## Phase 2 official resource table ingestion (2026-11-02)

Government of Western Australia, Department of Mines, Petroleum and Exploration,
*Rare Earth Elements: Investment Opportunities*, February 2026, physical PDF page 1,
'Projects with REE resources ... as at January 2026'. Original:
https://www.wa.gov.au/media/159141/download?inline=

Twenty WA project rows have preserved reported resource values, dates, owner,
development status, PDF table row number and SHA-256-addressed transcription.
The PDF is registered separately for raw-byte acquisition: a CSV derived from a
public PDF is **not** an original-source snapshot. Two existing project IDs are
preserved; 18 WA-listed project identities are added. No automatic resource-scope
promotion, no cross-record resource summation, and no inferred six-domain scores.
Exact matched deposit names/states create link candidates only. Project-domain
coverage is exported for all listed projects so unavailable evidence remains
explicit. Other states, issuer crosschecks, additional evidence and full C1 gate
reconstruction remain unfinished.

### National profile coverage

Austrade, *Australian Critical Minerals Prospectus*, March 2026,
printed pp. 5, 31-37 (7 REE upstream profiles),
https://international.austrade.gov.au/content/dam/austrade-assets/international/documents/reports/critical-minerals/australian-critical-minerals-prospectus-march-2026.pdf

Added 7 dated descriptive project profiles for WA, VIC, NSW and NT. The explicit
Browns Range and Yangibana crosswalk retains prior IDs; the other 5 projects
receive distinct stable IDs. Status/flow-sheets/financing/approvals/offtake
remain literal source-described observations, never fabricated ordinal scores.
PDF archival remains a separate reproducibility step; a text transcription
with original page locators is not the native PDF byte snapshot.
