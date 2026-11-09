# Current ASX coverage review

Iteration 3: remaining-991 gap expansion, integrating source-cell hardening from `20d8ad2` and parallel Redlings work from `f8975a0`, with the third acquisition/review round based on `7ca6047`.

- Reconciled the 33-review v2 ledger, retaining the existing 25 reviewed sources and adding native source-cell bindings for 44 expanded resource observations plus the annual-product calculation inputs.
- Filled 68 blanks relative to the requested 991-gap baseline (58 numeric); 25 Redlings fills were already present in parallel commit `f8975a0`, so 43 are additional to that 750-filled version. Overall, updated 12 existing values/source labels, and withdrew none. The unchanged 33 × 52 cohort now contains 793 filled cells and 923 blanks.
- Fixed scientific subset: 276 / 825 cells, up from 230 / 825 across the same 25 columns. This denominator excludes identity and metadata.
- Preserved current-only provenance: every filled cell has exactly one matching source entry, and every blank has a diagnostic.
- Seven priority resource gaps were reviewed. Fingerboards is filled from a clearly labelled government catalogue, without claiming independent issuer-JORC verification; six remain withheld for documented scope/basis/conflict/source gaps.
- Kennedy and Redlings add complete 15-oxide resource sets. Yttria adds four individual magnet oxides. Donald adds annual contained TREO/NdPr calculated from one product row with matched mass, grade, oxide fractions and annual units.
- Added a repeatable current-only integrity audit: `tools/audit_summary_iteration.py`.
- Six additional ASX original PDFs were acquired (410 pages), all six readable. Eight renamed-issuer/year archive pages were parsed; four contain zero dated links, which does not establish historical absence.
- The live Barkly index changed bytes again during integration; its refreshed capture is bound explicitly and the same announcement URL/date relationship passes the retained archive check.

Image-cell transcripts remain visually reviewed, not independent OCR. Source contracts still require scientific review; deterministic checks do not prove arbitrary scope choices. No R/MCDA results are claimed.

This directory holds the latest output only. Subsequent iterations replace its contents; this change does not rewrite Git history or duplicate older result bundles. Source PDFs, full-page renders and SQLite are excluded from the current publication.

Run `python tools/audit_summary_iteration.py --results results/asx-current --out work/current-audit.json` to verify the publication's cell/provenance/missing-data contract and exact output hashes.

Verification and exact test counts are in `validation.json`; these are targeted related regressions, not a new full historical rebuild or remote-CI claim. Repeated exports are byte-identical across all four CSVs, and the source database hash is unchanged.

Details and gap dispositions: [third-round research report](../../docs/asx-gap-round3.md), [per-source search reviews](../asx-gap-round3-2026-11-10/research_gap_reviews.csv), and [field changes](../asx-gap-round3-2026-11-10/field_changes.csv).
