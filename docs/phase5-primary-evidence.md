# Phase 5 — primary evidence and comparable sample expansion

This increment uses the existing Python CLI, SQLite schema and R methods. All quantities below are from the 2026-11-03 frozen run and its Phase 4 comparison. Registry groups are not a certified count of unique Australian physical Projects.

| Measure | Phase 4 | Phase 5 |
| --- | ---: | ---: |
| Canonical registry groups | 27 | 27 |
| Historical national screening rows | 1,006 | 1,006 |
| Unresolved cross-layer deposit pairs | 38 | 31 |
| Groups without controlled primary technical evidence | 18 | 6 |
| Resource-defined source scopes | 7 | 16 |
| Strict Development / full-evidence | 0 / 0 | 0 / 0 |
| Selected source snapshots / PDF snapshots | 27 / 12 | 47 / 27 |
| Distinct validated statement values | 30 | 72 |
| Typed study cases / numerical study parameters | 5 / 15 | 7 / 24 |
| Resource-port / full GIS / composition / resource-study / concentrate / official-summary panels | 7 / 5 / 3 / 3 / 2 / 20 | 16 / 7 / 6 / 3 / 2 / 17 |

Distinct validated statement values exclude obsolete page-extraction bindings and duplicate extraction versions of the same source/statement/value. Historical observation versions remain in SQLite; the count is not the number of MCDA-ready criteria. Of the twelve addressed evidence gaps, nine supply new comparable resource scopes, Brockman and Burracoppin supply primary but unharmonized numerical evidence, and Mt Stirling has a documented shared Yttria scope. Those last three do not add an independent resource alternative.

## Primary resource statements admitted

| Existing Project registry ID | Primary source and physical page | Admitted scope and input |
| --- | --- | --- |
| WA_DMPE_REE_2026_PROJECT/north-stanmore | Victory ASX release 11 August 2025, p6 | 320.640Mt, **486ppm TREO**; 510ppm includes Sc2O3 and is retained separately; HGMIN+MIN total, 330ppm TREO+Sc2O3 cutoff |
| WA_DMPE_REE_2026_PROJECT/splinter-rock | OD6 ASX presentation 20 April 2026, p44, explicitly reaffirms 29 May 2024 MRE | 682Mt at 1,338ppm TREO; six prospects, 1,000ppm cutoff; complete magnet share 22.9% |
| WA_DMPE_REE_2026_PROJECT/cummins-range | RareX ASX MRE 1 May 2023, p2 | Combined Rare Dyke+Phos Dyke 519.3Mt at 3,170ppm TREO including Y2O3; phosphate cutoff2.5%; older controlled statement, not a claim to the latest total |
| WA_DMPE_REE_2026_PROJECT/redlings | Marquee ASX quarter 31 July 2025, p4, reaffirms 22 January 2025 MRE | 11Mt at1,130ppm TREO, Inferred,800ppm cutoff; excludes exploration target; MREO definition not automatically used as a full four-oxide share |
| WA_DMPE_REE_2026_PROJECT/salazar | West Cobar original ASX MRE 8 October 2024, p7 | Newmont+OConnor 230Mt at1,178ppm TREO,600ppm cutoff; excludes separately reported Ga/Sc/Ti/Al resources |
| WA_DMPE_REE_2026_PROJECT/mangaroon | Dreadnought ASX MRE 30 November 2023, p1 | **Yin only**,29.98Mt at1.04% TREO,0.20% cutoff; excludes Gifford Creek; NdPr29% is not a full magnet share |
| WA_DMPE_REE_2026_PROJECT/cowalinya | HRE ASX Annual Report2024, p4 |159Mt at870ppm TREO,400ppm TREO-CeO2 cutoff;2023 MRE reaffirmed2024; complete magnet share28% |
| WA_DMPE_REE_2026_PROJECT/mt-clere | Krakatoa ASX 8 August2023, p7 | Tower only,101Mt at840ppm TREO; original21 November2022 MRE;300ppm TREO-CeO2 cutoff |
| WA_DMPE_REE_2026_PROJECT/mons | Nimy original issuer announcement,12 November2025, served by Market Index PDF mirror,p7 | Block3East,7.23Mt at538ppm TREO,Inferred; oxide+transition in70g/tGa2O3 model only; REO byproduct; **model date October2025 with month precision**, publication12 November2025 |

Every observation binds source SHA-256, physical page, checked markers, date, unit, classification and scope. Sources are immutable snapshots, not search-result summaries. The mineral resources have different effective dates and explicit cutoffs; these are selected source-scope comparisons, not harmonized latest whole-Project totals.

Salazar's aggregate table reports Pr6O11=55, Nd2O3=193, Dy2O3=22 and Tb4O7=4.0ppm. The source-bound transformation produces274ppm and100×274/1178=23.2598% magnet oxides. Component identity, source, statement and scope must agree. Component rounding bounds are propagated; the approximately25% figure describing **Newmont only** is not substituted for the two-deposit total.

## Evidence retained outside common resource/recovery criteria

Burracoppin's original 1 June2023 table,p2, reports35.709Mt bulk,14.731Mt in the minus45µm fraction,1,356.4ppm in that fraction and20kt REO. Multiplying the full bulk tonnage by the fine-fraction grade would overstate resource oxide. Four reported values are retained in observations with explicit fraction bases, with no invented bulk grade.

Hastings Annual Report2025,p17,reaffirms Brockman's January2021 JORC2012 table:41.6Mt,0.20% reported TREO and0.11% Y2O3. These values are retained as reported observations; Y inclusion has not been sufficiently harmonized for the common TREO panel.

HRE Annual Report2024,p9 adds two distinct cases. The84.9% magnet leach extraction is the mean of45 **selected preferred composites**, conditioned on >75% extraction and <40kg/t32%HCl; it is not whole-ore or resource-average recovery. The separate1kg,4-composite concept blend produced51.8%TREO MREC with8.4% impurities (above the source's typical commercial specification). Overall recovery is absent. Neither case is pooled with DFS-model whole-ore concentrate recovery or Jupiter's scoping MREC recovery.

ASM Annual Financial Report2026 had readable rendered pages but broken character mappings. Native extraction and positioned extraction were attempted; only physical pages4 and6 required OCR at200dpi. The derivative keeps native text, positioned text, OCR text, source/page/model hashes, engine version and extraction status. Page6 supports historical gross corporate equity raises A$24.9m and A$55m. They are stored on a **COMPANY**, not as Dubbo financing, cash available, capex cover or a financing ordinal. Statement dates follow the reported announcement/completion references, not invented drawdown dates.

## Identity and spatial results

Seven pairs gained primary named-scope evidence in addition to official native IDs, matching state/name and location checks: North Stanmore, Splinter Rock, Cummins Range, Cowalinya, Mangaroon, Tower and Burracoppin. The existing <=500m rule was retained; aliases preserve both source IDs. No new Project IDs were created. These are document-supported registry equivalences, not legal-footprint or title certification.

Yttria's generic AssertionError is replaced by a specific diagnostic: the two official representative points are3,685.359m apart. Its original16 April2024 announcement describes a2km initial resource strike and a wider exploration corridor; this does not prove both points refer to the identical physical scope. They remain independent. The original p1 explicitly places Yttria on Mt Stirling; a typed parent-scope relation is added, with no Project equivalence or duplicate resource sum.

Official road, operational rail and >=66kV power layers were reacquired with complete object-ID inventories, including Dubbo and Jupiter windows. All seven previously resource-registered Projects now have four-layer GIS coverage. The nine newly admitted resource scopes have port/power metrics where valid; road/rail coverage is not borrowed from another AOI. Distances remain EPSG:3577 representative-point Euclidean proximity, not legal road access, freight capability or grid capacity. Projected geometries are indexed once per layer to avoid repeated full transformations.

## Government source reconciliation

The original WA February2026 flyer was finally captured. Its resource table is on **physical page2**; older transcription metadata said page1. Current inventory locators link the original hash and corrected page, while historical transcription bytes remain unchanged. The original itself prints grades0.87% for Cowalinya,0.84% for Mt Clere and0.54% for Mons. Corresponding issuer statements give870,840 and538ppm. Matching statement/report date and tonnage exposes approximately tenfold discrepancies. All twenty government rows remain in the inventory; the three inconsistent rows are excluded from its exploratory MCDA screen with both source hashes and unmodified values, leaving17. They are not corrected by assuming a decimal shift.

## Aim A / B / C

All six panels rerun SAW, PROMETHEE II and TOPSIS with the existing three assumed scenarios and AHP audit. In the16-scope resource/port panel, resource_assumption has Mt Weld first under SAW/TOPSIS and Jupiter first under PROMETHEE II. Under development_assumption (a preference label in this partial panel), Splinter Rock ranks first under PROMETHEE II/TOPSIS and Jupiter under SAW. These are partial-panel model outcomes, not actual readiness or success forecasts. Splinter Rock is first across methods/scenarios in the selected six-scope resource/composition panel.

Monte Carlo weight experiments, source-rounding bounds, scoring/method comparisons, criterion/domain removal and cohort sensitivity are retained. Absence of measurement error bounds is not filled with an arbitrary distribution. `comparison_ranks.csv` joins common/new alternatives across Phase4 and5; a rank shift reflects cohort/evidence/model context, not temporal geological improvement. `comparison_provenance.json` hashes the actual input ranking files and snapshot locks.

Aim C retains descriptive external host-type contrasts. In the resource-oriented resource/port scenario, the six classified hard-rock scopes have median rank5.5 and seven clay-hosted scopes median10; in the development-oriented preference scenario their medians are9.5 and5. These selected, small, noncontemporaneous groups do not support a geological causal claim or multivariable model; three alternatives lack that broad host classification.

Six-domain **scorable** canonical coverage (denominator27 registry groups) is Resource16, Strategic6, Technical0, Development3, Infrastructure16 and Commercial0. Technical cases and company financing observations add real evidence without satisfying a common whole-ore recovery or project-financing criterion. Full four-layer GIS coverage is7. Strict Development/full-evidence and formal C1 admitted remain zero. Objective source facts are exported per formal gate; no formal C1 definition, signature or new manual approval requirement was introduced.

## Remaining six evidence gaps and limits

Greater Brothers remains a broader/program scope with Jupiter overlap to reconcile. Splinter (private Splinter REE Resources) is distinct from OD6 Splinter Rock and lacks a captured primary technical statement. Goschen and Fingerboards still need controlled resource/oxide-scope extraction rather than an HM/monazite conversion. Circle Valley lacks a validated original statement in this corpus. Lyons has a company resource webpage lead but needs the original statement and internally consistent quantities. Brockman and Burracoppin additionally remain outside common resource scoring for the basis/fraction reasons above; Mt Stirling is shared context, not another resource alternative.

Acquisition now supports allowlisted issuer search templates, keyword filtering, bounded linked pagination, global URL deduplication, direct-PDF response detection and local retries. The live discovery attempted eleven entry/search/page URLs; some issuer endpoints failed and dynamic ASX listings remain incomplete. It does not claim exhaustive ASX or state coverage. Newly discovered documents remain unscored until source/scope extraction is verified.

Validation:57 tests in the complete local suite plus the final evidence regression suite (58 unique tests), R numerical invariants, selected-page OCR, native-ID stability, source-bound transformations, seven pair decisions, historical Phase4 coverage, case isolation, source conflicts and idempotent ingestion. GitHub Actions executes the same system and Phase4 comparison.

```sh
au-ree-v2 all --as-of 2026-11-03 --compare-to results/phase4-2026-11-03 --work work/phase5
au-ree-v2 rebuild --as-of 2026-11-03 --snapshot-lock results/phase5-2026-11-03/snapshot_lock.json --work work/phase5-replay
au-ree-v2 pdf-extract --as-of 2026-11-03 --source-key north_stanmore_mre2025 --pages 6
# For pages needing OCR, pass --tessdata data/ocr explicitly.
```
