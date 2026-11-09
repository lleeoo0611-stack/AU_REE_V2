# Current ASX coverage review

Iteration 2: Redlings declared-cutoff resource composition, based on `20d8ad2`.

## Verified result

- Master table: 750 / 1,716 filled cells across 33 projects × 52 columns; 966 blanks remain. This iteration fills 25 previously blank Redlings cells and withdraws none.
- Fixed scientific subset: 249 / 825 cells across the same 25 scientific columns, up 19. The other six new cells are composition diagnostics, not additional resource measurements.
- The original ASX announcement of 22 January 2025 (`idsId=02906350`, SHA-256 `1417f7495f8101992bd14719c42975d83eaba067b83dda56aa93187e030c9d43`) explicitly selects the 800 ppm TREO cutoff: global Inferred resource, all five prospects, 11 Mt at 1,130 ppm TREO. Table 1 on page 2 supplies 15 oxide grades; Table 2 on page 3 supplies 12,430 tonnes TREO. Lower/higher cutoff sensitivity rows are not combined.
- All 18 observations pass exact source row/column/header/unit validation and visual review. Each of 18 deliberate token corruptions is rejected. The unusual published Y2O3 grade of 0.05 ppm is preserved, not guessed or corrected.
- Oxide grades total 1,132.12 ppm versus reported TREO 1,130 ppm. The 2.12 ppm difference fits the 3.815 ppm sum of half-unit rounding intervals at each displayed precision; the source explicitly warns about rounded estimates. The ledger records this limited tolerance.
- Two existing numeric cells only change formatting (11.0 → 11; 12.430000000000001 → 12.43); two source-identification fields change. All substantive fills belong to Redlings. Each filled cell has one current provenance entry; every blank has a diagnostic. Missing values remain missing, not zero.

## Reviewed but not filled

- Wudinna: available individual-oxide table contains top-cut thresholds, not resource mean grades.
- Brockman: complete 2012 distribution belongs to an older 36.2 Mt resource, not the current 41.6 Mt estimate. More recent Y2O3 requires compatible basis/date reconciliation.
- Burracoppin: 35.709 Mt bulk resource and 14.731 Mt minus-45 µm fraction must not be confused. The 1,356.4 ppm grade describes the fine fraction; applying it to bulk tonnage would overstate contained REO.

These leads remain unresolved, not exhausted proof that the data do not exist. This pass stops rather than mixing incompatible scopes to inflate coverage.

## Verification and reproduction

Full suite: 415 tests, 411 passed, four skipped because R is unavailable, zero failures. All four CSV exports are byte-identical across repeated runs. No R/MCDA recalculation is claimed. Earlier image-cell transcripts remain visually reviewed, not independent OCR.

`config/asx_iteration_sources.json` records the accepted acquisition URL. Download the source into an asset root named `gap_research` with the content-addressed path in the review ledger, then export with the other existing asset roots. `tools/audit_summary_iteration.py` checks the current publication's cell/provenance/missing-data contract and exact CSV hashes.

This directory holds only the latest results and review. No new historical result bundles, raw PDFs, full-page renders or SQLite databases are published; existing Git history is not rewritten.
