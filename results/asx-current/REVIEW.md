# Current ASX coverage review

Iteration 9, based on remote `b610eff5c1f0fce169dbb58e31bca4efe7a7f13b` and its unchanged 43-project cohort.

## Verified additions

Splinter gains **23 previously blank cells**, including **17 scientific cells**. Two existing source-name/URL cells now identify the original technical report. No other project changes and no values are withdrawn.

- Overall coverage: **995 / 2,236 cells**, with **1,241 blanks**.
- Scientific coverage: **347 / 1,075 cells** across the fixed 25 scientific columns.
- Complete ore/TREO resource pairs: **30 before and after**. This partial record does not add a complete TREO resource.

## Original source and selected scope

The source is CSA Global's R254.2015 technical report, Appendix 7 of [WAMEX report A109432](https://wamex.dmp.wa.gov.au/Wamex/Search/ReportDetails?ANumber=109432). PDF SHA-256: `428c8f759ec2f4dc393177f0fccce12cc96c9b1359638d003f7ea30b6d388df7`.

Physical page 72, Table 35, binds **22.849 Mt** to the Splinter **Inferred** row at the source-defined **500 ppm TREO+Y2O3 cutoff**. Native cell positions bind that cutoff group, category, ore tonnage and 14 compatible oxide grades. Newmont, unclassified mineralisation, combined Total rows and other cutoffs are excluded. Splinter is not OD6's Splinter Rock.

The source explicitly uses **Ce2O3**, proven by its Table 33 conversion row on physical page 69 and the selected resource-table header. It is not substituted or normalized to the template's CeO2 basis.

The accepted partial record contains ore mass, 14 individually reported compatible oxides, and sums whose complete required oxide sets are present:

- NdPr: 4.912535 kt.
- HREE8 (Tb, Dy, Ho, Er, Tm, Yb, Lu and Y): 3.770085 kt.
- Independent NdPrTbDy recalculation: 5.460911 kt.
- Sum of known compatible oxides: 15.057491 kt, explicitly not total TREO.

These are arithmetic results from source-rounded ore and grade values; their decimal places do not add measurement precision.

## Values and dates kept unknown

CeO2, generic TREO grade, total TREO, the legacy generic magnet-resource amount, magnet/TREO share, element-sum/TREO ratio and complete-resource indicator remain blank. Annual production and unrelated metadata gaps are unchanged.

**2015-11-09 is the technical report's issue date and an ordering date only.** Geological/resource effective date and public release date remain unknown. Both unknown-date flags and their explicit roles are retained in current field provenance and summary limitations. No formal C1 approval or current legal-title certification is implied.

## Validation and reproducibility

Two complete local exports use the exact original canonical SQLite, unchanged at SHA-256 `99ed9c0fc004960f92680ee782ef8764c189a08d98bce4d14c2d0e5ad99091d0`, and hash-verified original sources. All four output CSVs match byte for byte between runs. Every filled cell has current provenance and every blank has a diagnostic.

The default complete-resource path still requires paired ore and compatible TREO grade. Partial projection requires explicit source/statement/scope/date binding, native cutoff/category proof, compatible individual oxides and the declared incompatible cerium basis. Eight real-source negative controls rejected altered basis, category, cutoff, date and total/grouped-value claims.

The integrated production code passed the cloud full suite: **506 tests, 502 passed, four optional R-dependent skips, zero failures/errors**. The laptop's **184-test ASX/metadata/partial-resource regression group passed with zero failures/errors/skips**. The earlier laptop full-suite attempt was limited by omitted historical fixtures; no complete Windows historical-suite pass is claimed.

Only current summary, provenance, gaps, audit and review are updated. Raw PDFs, SQLite, temporary acquisition files and historical result bundles are not published. No new research MCDA ranking or remote-CI success is claimed.
