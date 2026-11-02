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

- Add national/state Project discovery and evidenced parent/child/merge/split decisions; schema supports dated relations but no automated legal entity adjudication is claimed.
- Discover new issuer/ASX announcements (current registry refreshes known document URLs only), bind new table extractions to new SHA versions and extend event timelines.
- Expand same-scope composition, recovery/mineralogy/NORM, development, approvals, financing and offtake evidence. No geological type is substituted for processing difficulty.
- Add versioned roads, operational rail and power layers with complete spatial queries. Only port proximity is currently integrated.
- Expand beyond the two-scope pilot, freeze comparable six-domain cohorts and document expert AHP judgments if actually obtained.
- Measurement uncertainty requires source-supported bounds; the existing rounding experiment is not a measurement-error model.
- Cohort deletion returns no numerical result with n=2; external Aim C inference is explicitly incomplete until independent predictors and adequate samples exist.
- Scheduled new snapshots persist as Actions artifacts (90 days), not automatic commits. Promote reviewed artifacts into the managed manifest to retain them permanently.

These are unfinished research requirements, not acceptance PASS claims.
