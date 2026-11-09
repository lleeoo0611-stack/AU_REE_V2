# Current ASX coverage review

Iteration 5, based on `9b85c84`.

## Result and scope change

The current 33 × 52 table contains **829 / 1,716 filled cells**, with **887 blanks**. The fixed 25-column scientific subset is **301 / 825**. This iteration fills eight new scientific cells and withdraws none; 17 existing cells change because the selected Mount Ridley resource scope changes.

**Mount Ridley now explicitly reports Blocks 1 and 2, not Mia and not the whole project.** These complementary resources are not added together. The original Mia review remains validated in the ledger as `CONTEXT_ONLY`, excluded from the current projection even as a fallback. The source's p24 reaffirms Mia separately. Thus the new 122.546251 Mt versus previous 168 Mt is a reporting-scope change, not a claimed resource downgrade or replacement geological estimate.

## Source and accepted data

[Original ASX release, 24 March 2026](https://www.asx.com.au/asx/v2/statistics/displayAnnouncement.do?display=pdf&idsId=03075245), SHA-256 `245f282102453bf6dc97056eba1ac4b889f8d506d07b5515bc354caec94ab170`:

- Physical p6 Table 1: Blocks 1 + 2, Inferred, >300 ppm TREO cutoff; exact total 122,546,251 tonnes at 889 ppm. The inconsistent rounded headline 122.56 Mt is not used.
- Table 2 reports 108,954 tonnes TREO. Grade × tonnes gives 108,943.617 tonnes; the difference is within the displayed TREO-grade rounding interval.
- Table 3 supplies 12 accepted individual oxide grades. All 12 grade-derived contained masses reconcile with Table 4 within their displayed rounding bounds (see `source_consistency.csv`). Eight were previously blank: La, Sm, Eu, Gd, Ho, Er, Tm and Lu. Existing Pr, Nd, Tb and Dy are replaced consistently with the selected block scope.
- Table 3 is selected for grade-derived oxide masses; direct reported Table 4 values are independent consistency checks, not silently substituted. Therefore small displayed differences can remain.
- Four conventional magnet oxides total 232.9 ppm, or 26.197975% of TREO. The direct component-mass sum is 28.541022 kt. The existing total-TREO × magnet-share output is 28.543742 kt because reported TREO differs slightly from rounded grade × tonnes; this is a rounding-method distinction, not new measured metal.

## Deliberately withheld

- **Ce:** Tables 3/4 label Ce2O3, while the source formula and 1.2284 conversion on pp22/52/53 identify CeO2. No silent stoichiometry correction.
- **Y:** 222.6 ppm predicts 27,278.795 t, versus Table 4's 27,265 t. Difference 13.795 t exceeds the 6.627 t displayed-rounding envelope.
- **Yb:** 16.2 ppm predicts 1,985.249 t, versus Table 4's 2,010 t. Difference 24.751 t exceeds that envelope.
- Source MREO aggregate is not imported: its p22 definition conflicts with the conventional four-oxide set. Magnet values are independently derived from explicit Pr/Nd/Tb/Dy cells.

A focused correction search found that the 30 April 2026 quarterly repeats the same discrepancies; the [30 September 2026 issuer annual report](https://docs.relait.com.au/MRD-Annual-Report-to-shareholders-1094266337225606145-1790749027.pdf) repeats aggregate resources without reconciling these individual cells. Ce, Y and Yb remain blank with specific diagnostics. No complete 15-oxide closure or complete eight-element heavy-group amount is claimed. No composition from Mia, metallurgical samples, reserves or peer projects is mixed into this scope.

## Validation and remaining research

The source validator now accepts parentheses around an exact TREO header only after verifying the original cell anchor. New positive/negative tests retain rejection of HREO. `CONTEXT_ONLY` evidence requires an explicit reason, cannot become a fallback selected resource, and does not relax the single-preferred-resource rule.

Final full suite: 446 tests, 442 passed, four skipped because R is unavailable, zero failures. Hashes are in `validation.json`. All four standard CSV outputs reproduce byte-for-byte; all filled cells have one matching current provenance row and every blank has a diagnostic. The source database is opened read-only. No R/MCDA recalculation or remote-CI success is claimed.

The preceding pass's Nolans full suite remains in the current table. Further searches also checked Splinter Rock and Salazar annual outputs: OD6's 2025 optioneering range is explicitly aspirational, not a selected annual-average production forecast, while Salazar disclosures describe planned studies/testwork. These are not numeric fills. The other examined gaps remain limited by combined-only NdPr, sample-versus-resource composition, incompatible reserves/deposit scopes, or unresolved source contradictions. This is an evidence boundary for this pass, not proof that no further public data exist.

Only current outputs/review are replaced; no new historical result bundle is added. Existing Git history and others' prior bundles are retained. Source PDFs, full-page renders and SQLite are not published. Paid services and access-control bypass were not used.
