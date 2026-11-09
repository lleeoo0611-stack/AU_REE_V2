# Current ASX coverage review

Iteration 4, reconciled against remote `b1625cf` before applying changes.

## Result

- 821 / 1,716 cells filled across the unchanged 33 × 52 cohort; 895 remain blank.
- Fixed 25-column scientific subset: 293 / 825, up 17. Total new fills: 28 (17 scientific, six composition diagnostics, five metadata). No withdrawals. Two existing Nolans magnetic values change floating-point representation only.
- Kennedy and Yttria values already merged by parallel work were independently checked, not counted again.

## Nolans: complete reported resource composition

Original [ASX DFS release, 7 February 2019](https://announcements.asx.com.au/asxpdf/20190207/pdf/442fgrbxqwrxdd.pdf), SHA-256 `63bc0386c935658dc977d4a5552390ad51ba2f0c7ce0e5c2b31754b8e7a1a5eb`:

- Physical p36 Table 11: global Measured + Indicated + Inferred resource, 56 Mt at 2.6% TREO, 1% lower cutoff, effective 7 June 2017. This matches the selected resource, not a reserve or processing sample.
- Physical p37 Table 12: all 15 individual oxide proportions of resource TREO, **Total** column. The selected Ho2O3 value is 0.04%, not the adjacent Indicated-column value 0.4%.
- Each original proportion is bound to its exact row, column, title and unit. Bulk oxide ppm = reported percentage of TREO × selected bulk TREO grade (%) × 100. The conversion factor must be the exact selected resource-grade observation and cell. These are transparently converted reported proportions, not independently measured bulk ppm or an assumed mineral mixture.
- Proportions sum 100.077%. No renormalization: the 20.02 ppm closure difference is below the 123.63 ppm sum of displayed proportion half-unit intervals × 260. Shared grade rounding is not added to that tolerance.
- Added all 15 oxide contained amounts, NdPr (384.384 kt), and the complete eight-element heavy group (28.78512 kt), plus six composition diagnostics. The dated resource remains distinct from newer annual-production forecasts.
- Code now supports strictly scoped transposed oxide rows and `%TREO` conversion; seven new tests cover valid conversion and reject missing/wrong factors, incorrect arithmetic, wrong categories/rows and out-of-range proportions. Existing scope and unit checks remain enforced.

## Metadata

The same source ledger adds Barkly Rare Earths Limited as developer from physical p7 of its prospectus, explicitly identifying the Company's flagship Barkly Project. Four listing-status cells are supported by explicit ASX ticker plus 100%-owned project statements: Salazar (2024 source p1), Cummins Range (2024 p1), Nolans (2022 p2), and Yttria (2024 p1). Dates and source provenance are retained; no listing inference is made from Barkly's proposed IPO.

## Additional public-source searches reviewed, not filled

- Circle Valley/Yttria: original tables duplicate current data. Circle Valley's additional NdPr column is combined, not separate oxides.
- Yin/Mons: combined NdPr and metallurgical samples are not a resource-wide individual-oxide suite.
- Narraburra: original [19 April 2023 release](https://announcements.asx.com.au/asxpdf/20230419/pdf/45nsv13j5vtntn.pdf) provides aggregate groups; detailed later compositions describe drillhole/metallurgical composites. Fresh bedrock is explicitly excluded from the resource.
- Tower: the located research composition is inferred from test samples, not an issuer-reported resource mean.
- Kennedy: [issuer 2025 annual report](https://www.devexresources.com.au/wp-content/uploads/2025/09/61284182.pdf), November update and current project page confirm the already-integrated 150 Mt estimate. No authoritative replacement for an unrelated 243 Mt search snippet was found.
- Lyons: official 2026 annual report repeats tonnage/grade in a biography but does not reconcile conflicting contained totals.
- Mt Weld: full oxide table is an Ore Reserve at a different cutoff, not the selected Mineral Resource. Nameplate capacity is not annual-average production.
- Dubbo/Yangibana: peer baskets and historical/subdeposit compositions cannot replace matched global resource composition.
- Cummins Range: remaining aggregate HREO cannot be split into individual oxides.
- Goschen South/Central tables concern different deposits/issuers, not VHM's selected Area 1; Fingerboards' earlier government-catalogue addition was not duplicated.

This pass stops at these evidence boundaries, not a claim that all public documents or remaining gaps have been exhausted. No paid services or access-control bypass were used.

## Verification

Full suite: 440 tests, 436 passed, four skipped because R is unavailable, zero failures. See `validation.json` for hashes. All four CSVs reproduce byte-for-byte. Every filled cell has one current provenance entry and every blank has a diagnostic. Missing is not zero. Newly needed live ASX archive captures changed bytes; exact announcement URL/date relationships were checked before binding replacement hashes. Source PDFs and databases are not published. No R/MCDA recalculation or remote-CI success is claimed; earlier image transcripts remain visually reviewed, not independent OCR.

Only this current result set is replaced. No new historical results directory is added, and existing Git history or other contributors' result bundles are not rewritten.
