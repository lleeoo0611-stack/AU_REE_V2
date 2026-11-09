# Current ASX coverage review

Iteration 1: source-cell validation hardening, based on `7ca6047`.

- Reconciled the newest 25-review source ledger with exact native table-cell bindings, source sections, headers, units and selected forecast scenarios.
- Preserved all 725 filled cells in the 33 × 52 master table (byte-identical to the preceding published table); 991 blanks remain.
- Fixed scientific subset: 230 / 825 cells across the same 25 columns used in independent testing. This denominator excludes identity and metadata.
- Removed a superseded Donald project-name provenance row. Every current filled cell now has exactly one matching provenance entry, and every blank has a diagnostic.
- Added a repeatable current-only integrity audit: `tools/audit_summary_iteration.py`.
- Reacquired reviewed source PDFs and verified their hashes. The live Barkly index changed bytes; its refreshed capture was reviewed for the same exact announcement URL and date, and the new hash was bound explicitly rather than bypassing the old hash check.

Image-cell transcripts remain visually reviewed, not independent OCR. Source contracts still require scientific review; deterministic checks do not prove arbitrary scope choices. No R/MCDA results are claimed.

This directory holds the latest output only. Subsequent iterations replace its contents; this change does not rewrite Git history or duplicate older result bundles. Source PDFs, full-page renders and SQLite are excluded from the current publication.

Run `python tools/audit_summary_iteration.py --results results/asx-current --out work/current-audit.json` to verify the publication's cell/provenance/missing-data contract and exact output hashes.

Verification: 415 full-suite tests, 411 passed and 4 skipped because R is unavailable; no failures. Repeated exports are byte-identical across all four CSVs.
