# Phase 2: primary-evidence expansion, 2026-11-03

The existing CLI and canonical SQLite schema now reconstruct national government source
records, source-qualified Project/Site grouping and technical resource scopes together.
This supplements the previously published Phase 2 government-summary screen; it does not
replace unresolved evidence with approvals or invent a completed national Census.

## Current evidence and counts

- 27 PROJECT records from issuer registries and official project lists; these are not a certified
  count of unique independent Australian projects. Name-only links remain candidates.
- 203 DEPOSIT native records across two national GA layers (149 AIMR plus 54 REE-filtered
  Critical Minerals records). Cross-layer physical-deposit duplicates are not silently merged.
- 339 historical screened national source selections remain identifiable by native ID and original
  chunk hash; 366 total source records include official catalogue and WA summary rows.
- 21 WA native SITE records and one source-coded PROJECT_CANDIDATE parent. A source-advertised
  project code establishes only the source's membership assertion, not legal ownership or JORC scope.
- Five hash-bound issuer resource scopes: Mt Weld, Wolverine-only, Nolans Bore, Central Mia-only
  and Yttria. Nolans reuses its existing Austrade PROJECT ID; it is not counted as another project.
  The five DEPOSIT_SCOPE children preserve the exact technical scope, not fabricated new sites.

The complete GA Critical Minerals layer has 421 rows; a versioned commodity-expression filter
retains 54 REE source records. Inactive/source status is preserved, not used as blanket exclusion.
The current national screening retains explicit coverage gaps and is not yet an exhaustive new
download and harmonization of all state registries.

## Primary-source observations

| Scope | Primary source and locator | Captured data / caveat |
| --- | --- | --- |
| Nolans Bore, NT | Arafura Annual Report 2025, PDF pp 15, 17, 7, 20 | 56 Mt at 2.6% TREO, source-reaffirmed 2017 resource; NdPr/TREO 26.4%; DFS reaffirmation; 66% binding NdPr offtake capacity and US$775m conditional senior debt. Neither finance drawdown nor complete project funding is inferred. |
| Central Mia, WA | Mount Ridley 2024 annual report, PDF p13, printed p10 Table 1 | Inferred 168 Mt at 1,201 ppm TREO, 25% PrNdDyTb oxide share. Does not include later Grass Patch scope. |
| Yttria, WA | Asra 31 July 2025 quarterly, PDF p14 | Indicated + Inferred total 15.0 Mt at 490 ppm TREO; magnet oxide share 22.5%; U 0.6 ppm and Th 1.0 ppm. Element assays are not substituted for a regulatory NORM burden score. |

Nolans' NdPr share excludes Dy/Tb and is deliberately not the complete magnet-REO criterion.
Technical sighter tests and descriptive flowsheets do not establish a comparable overall recovery.
Reported financing commitments retain conditions and scope; no arbitrary financing ordinal is assigned.
Raw PDFs, page markers, exact units, dates, source SHA, transformation rules and issues remain managed.

## Infrastructure

Five official deposit anchors drive independently inventoried projected AOIs. Archived complete query
unions contain 4,291 maintained TOPO250K roads, 373 operational railway/siding features and 332
mapped >=66kV power-line features. All five resource scopes have validated distances to each of
these layers and to the 64-port national layer. Out-of-radius or unqueried points cannot receive
a certified scoped distance. Project representative points are not site boundaries or legal access.
An additional complete 3,147-feature power layer preserves all mapped classes separately; where
the high-voltage scoped layer is available it supplies the final project power metric.

## Research outputs and limits

1. Aim A: five-scope inventory + four infrastructure metrics under three assumed scenarios and
   PROMETHEE II, SAW and fixed-ideal TOPSIS; separate two-scope resource/composition comparison.
   The earlier 20-project WA resource-summary screen remains separate and explicitly provisional.
2. Aim B: weight-only Monte Carlo, printed-rounding-only experiment, threshold/function changes,
   criterion/domain deletion, leave-one-project-out and method agreement. Correlated infrastructure
   measures share the domain weight; raw-data measurement uncertainty remains unquantified.
3. Aim C: descriptive host-type/rank contrasts use GA classifications of evidenced representative
   deposits, not inferred geology from rank. Small selected groups preclude causal or significance
   claims. Existing 20-source external stage associations and national geographical descriptions remain.

No five-scope case has comparable observations across all six domains: Development cohort = 0,
Full-evidence cohort = 0. Missing recovery and comparable financing variables stay missing.
This is expanded research with explicit partial panels, not full six-domain completion.

## Validation and replay

28 Python tests and independent R invariants are run locally and in the consolidated CI workflow.
The new integration test verifies five exact resource calculations, unchanged IDs, idempotent
hierarchy, four distances for every scoped project, 54 commodity-filtered GA records, and that
conditional debt and NdPr-only shares cannot masquerade as different scored variables.
Earlier 2026-11-02 reconstruction and archived results remain separate.

```sh
au-ree-v2 all --as-of 2026-11-03 --work work/phase2
au-ree-v2 rebuild --as-of 2026-11-03 --snapshot-lock results/phase2-primary-2026-11-03/snapshot_lock.json --work work/replay-phase2
```
