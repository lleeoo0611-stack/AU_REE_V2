# National identity and study-case research, cutoff 2026-11-03

See [sources, cohorts and unresolved evidence](../../docs/phase3-identity-and-studies.md).
`provenance.json` gives the actual execution ID, selected source/code/configuration hashes and file checksums.

## Read the evidence first

- `national_screen_index.csv`: all 1,006 historical screening rows, source-adapter labels and exact selection links.
- `native_identity_ledger.csv`: 339 archived selections, with explicit native-ID dispositions.
- `canonical_membership.csv` and `identity_decisions.csv`: non-destructive aliases with source evidence.
- `deposit_identity_review.csv`: cross-layer same-name leads; location conflicts remain unmerged.
- `technical_project_coverage.csv`: primary evidence, unsupported scopes and other resource claims by canonical group.
- `entity_hierarchy.csv`: Program/Project, Deposit scope, Site/source record and reported tenement relations.
- `study_cases.csv` / `study_parameter_evidence.csv`: five dated study cases, with actual process, recovery endpoint,
  scale, finance conditions and historical/currentness limits. Capex is not committed financing.
- `recovery_comparability.csv` / `recovery_zone_ranges.csv`: endpoint groups and model-zone ranges, not pooled recovery.
- `review_queue.csv`: explicit unresolved or conflicting data. Missing evidence is not a negative resource finding.

## Compare only within each frozen panel

| Folder | Sample | Interpretation |
| --- | --- | --- |
| `resource_infrastructure_pilot` | 7 | Issuer resource inventory and representative-point port proximity; the folder name is retained for compatibility |
| `issuer_resource_infrastructure` | 5 | Complete four-layer infrastructure coverage and inventory |
| `issuer_resource_composition` | 3 | Complete magnet-oxide share on an all-REE oxide basis |
| `issuer_resource_study` | 3 | Inventory and route-specific study maturity; not financing or actual operating readiness |
| `beneficiation_concentrate_screen` | 2 | DFS-model TREO-to-mineral-concentrate process indicators; feed/mineralogy not harmonized |
| `official_wa_resource_screen` | 20 | Government-summary resource screen, distinct from issuer-level JORC scope verification |

In the resource/study panel, the resource-oriented assumed scenario places Jupiter above Nolans,
whereas the development-oriented assumed scenario places Nolans above Jupiter. These are model
preference effects within that selected three-case panel, not expert preferences or development probabilities.
In the process-indicator panel, Yangibana's recovery and concentrate grade exceed Browns Range's point
inputs, yet its report also states care/maintenance and no binding financing. This is not an overall Project ranking.

Do not compare numerical ranks from different folders as one scale. MC weight frequencies are not success
probabilities. Missing measurement bounds in study cases produce blank uncertainty fields, not fabricated
confidence intervals. The full six-domain cohort remains incomplete, and external geological/technical drivers
remain descriptive. Neither the 1,006-row screen nor 27 canonical registry groups is a completed national
Project identity certification. No formal independent approval or research signature is claimed.

```sh
au-ree-v2 rebuild --as-of 2026-11-03 --snapshot-lock results/phase3-2026-11-03/snapshot_lock.json --work work/phase3-replay
```
