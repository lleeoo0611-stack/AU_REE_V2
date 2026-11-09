# Current ASX coverage review

Iteration 8, based on remote `b494607` and its unchanged 43-project cohort.

## Verified additions

Four metadata blanks are filled, taking coverage from 968 to **972 / 2,236 cells**, with **1,264 blanks**. Scientific coverage remains **330 / 1,075** across the fixed 25 scientific columns. No scientific estimates change and no values are withdrawn.

- Narraburra developer: **Orbit Resources Limited**. The [30 October 2026 issuer announcement](https://orbitresources.au/downloads/announcements/obt_2026103001.pdf), physical p1, says the Matrix IPO is deferred and Orbit retains 100% ownership. It also explicitly identifies ASX: OBT, supporting listed status `否` for the unlisted-company column. The former Godolphin name and proposed Matrix transaction are not treated as current ownership.
- Wudinna developer: **Cobra Resources plc**. The [26 October 2026 issuer release](https://hermes-cdn.investorhub.com/announcement-pdfs/lse/7804646.pdf?v=63960217384) identifies Cobra and LSE: COBR on p1. Physical p23 binds Boland/Head tenements to LAM Wudinna Pty Ltd, wholly owned by Cobra. Listed status is supported across those exact pages in the same immutable PDF, not inferred from a company suffix.

The source ledger records URLs, hashes, dates, evidence markers and exact ownership text rectangles. Both listing proofs match the selected issuer, exchange/ticker, project wording and explicit 100% ownership statement. These are dated issuer disclosures, not current legal-title certification or resource-effective dates. The new `DATED_ISSUER_METADATA` role cannot admit resource or production observations.

## Validation and source recovery

Two complete local exports used the exact original canonical SQLite and hash-verified source caches. Compared with the latest merged 43-project baseline, every previously filled master-table value is unchanged; only the four metadata blanks above are filled. Four required HTML captures were recovered from existing local cache after public retrieval returned 403; the blocked pages were not bypassed. All 13 required round5 PDFs were verified and used directly from the local cache, preserving their newer evidence. One exact archived ASX index was restored into isolated source staging. Existing announcement URL/date relationships remain validated.

The metadata validator keeps its original checks and adds a constrained ASX/LSE proof route. Exact ownership rectangles avoid interleaved columns. Tests reject wrong issuers, tickers, projects, percentages, negated ownership, altered statements, unsupported exchanges and invalid rectangles. Every filled output cell has one current provenance record; every blank has a diagnostic. Final suite results and hashes appear in `validation.json`.

## Additional research awaiting compatible data

- Sandy Mitchell: the original [22 September 2026 MRE](https://announcements.asx.com.au/asxpdf/20260922/pdf/074c2k0rwv83p1.pdf) is now visually verified despite its broken native font extraction. Physical pp88–89 contain the original 379,421,288 t resource and original oxide/element basis. This corrects the earlier research limitation: the unresolved issue is **the refined 373.3 Mt resource lacks a matching revised TREO grade/composition**, not that the original table remains unreadable. October scoping and quarterly reports give only revised MzEq. Annual monazite/xenotime mass and test-concentrate chemistry are not converted into oxide output.
- Splinter: an original CSA technical appendix was recovered from public WAMEX records. It is distinct from OD6 Splinter Rock and contains individually reported oxides, but deliberately uses Ce2O3. Its evidence is under separate basis/partial-resource validation; this iteration does not import or normalize those quantities.

Only current outputs and review are replaced. No new historical result bundle, raw PDF, rendered page or SQLite database is published. No new research MCDA ranking or remote-CI success is claimed.

Cloud full suite: 484 tests, 480 passed, 4 optional R tests skipped, zero failures. Laptop focused ASX/metadata suite and three restored-fixture regressions: 162 tests passed. Two complete local exports matched byte for byte.

The laptop full-suite attempt was incomplete: 366 tests ran with 37 errors and one failure because the sparse checkout omitted historical fixtures. The frozen-policy assertion and SQLite cleanup failure were traced to missing historical configurations and passed after those exact fixtures were restored. This is not a claim that the complete historical suite passed on Windows.
