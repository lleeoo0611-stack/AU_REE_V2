# Phase 6: national source integration and evidence expansion

This release extends the same Python/SQLite/R application and the existing canonical database. It is a national **source-record census**, not a claim that all independent Australian REE projects have been identified. Historical 1,006 screening records and 339 archived selections retain their original identities.

## Verified database increment

| Measure | Phase 5 | Phase 6 |
|---|---:|---:|
| Canonical PROJECT registry groups | 27 | 31 |
| Source-scoped comparable resources | 16 | 19 |
| Selected source snapshot entries | 47 | 75 |
| Distinct SHA values in selected entries | see Phase 5 lock | 73 |
| Selected PDF entries | 27 | 38 |
| Distinct validated statement values | 72 | 114 |
| Typed study cases / parameters | 7 / 24 | 9 / 40 |
| Scorable Resource / Strategic / Technical / Development / Infrastructure / Commercial | 16 / 6 / 0 / 3 / 16 / 0 | 19 / 8 / 0 / 4 / 19 / 0 |
| Strict Development / full-evidence / formal C1 admissions | 0 / 0 / 0 | 0 / 0 / 0 |

The four additional PROJECT IDs are Narraburra and three explicitly advertised SA project records: Koppamurra, Wudinna and Kalkaroo. Narraburra and Koppamurra gain controlled technical resource evidence. Wudinna and Kalkaroo remain government project descriptions awaiting primary technical documents. These four IDs are not four newly proven unique physical projects. The primary Koppamurra claim uses the already discovered government `SA_MINING_PROJECT_SITE_NO/2298466` identity.

Compared with the frozen Phase 5 entity inventory, new source-bound typed entities comprise **578 SITE, 93 DEPOSIT, 177 PROSPECT, 245 OCCURRENCE, four PROJECT and three DEPOSIT_SCOPE** IDs. The 122 WA native project-code parents retain PROJECT_CANDIDATE status and their existing IDs. They are explicit government parent records, not technically certified MCDA alternatives.

## Actual government originals

| State / source | Complete raw records | REE-related native records |
|---|---:|---:|
| WA MINEDEX | 48,509 | 424 |
| NSW METINDEX | 30,898 | 107 |
| VIC MINSITE | 18,794 | 39 |
| SA MINDEP CSV | 8,815 | 83 |
| TAS MRT | 8,301 | 18 |
| QLD MINOCC occurrence layer | 5,209 | 12 |
| NT MODAT | 2,105 | 18 |
| SA developing projects / major mines | 35 / 31 | 2 / 1 |
| Total source records | 122,697 | 704 |

All original statewide records precede local REE/mineral-term filtering. The filter includes mineralogical indicators and incidental commodities; a match is not proof of an economic REE project. Each source has a disclosed inventory scope. In particular, QLD layer17 is the **occurrence** layer, not a claim of complete operating-mine coverage. ACT has national GA coverage only. GA AIMR was re-requested and unchanged; the critical-minerals layer has a new response version, with all421 native IDs and names stable.

The existing acquisition module now handles WFS count-bound paging, ArcGIS object-ID inventories and CSV originals; raw service responses are content-addressed separately. Native attributes, aliases, geological classes and parent codes stay in records.raw. Only explicit government classifications create DEPOSIT/PROSPECT/OCCURRENCE nodes. SITE nodes represent reported locations, not mine footprints. WA project-code/site-code relations and SA advertised mineral-deposit foreign keys establish typed relations without name/proximity merging.

There are **1,250 new source-bound relations**: 515 geological-entity/site links, 424 WA project/site links, 295 WA project/geological-feature links, four SA cross-layer native-ID references, three document-supported deposit equivalences, three technical resource-scope links, five representative-point links and one Brothers parent-scope link. Multiple edges do not establish multiple independent projects or additive resources.

WFS count changes, missing/repeated keys, truncated ArcGIS pages and hash failures are checked. Local duplicate business keys are isolated; TAS has three duplicated non-REE IDs, which do not block its valid REE records. SARIG WFS1.1 requires omitting startIndex on its first small page; service exceptions are preserved. A later SA update returned502 after retries and retained the last good snapshot. NT was re-fetched: **2,105 unchanged native-ID groups, zero added/removed/changed**, no duplicate entities. Generated WFS response FIDs do not create false data changes.

SA CSV has three truncated UTF8 spans. Original bytes remain intact; the decoder records their offsets and retains literal hex escapes instead of guessing characters. REMP2025 XLSX timed out; no workbook rows were accepted. Acquisition status files record these limitations, rather than treating failure as an empty state.

## Original 31 pairs and six technical gaps

The prior31 unresolved pairs lose **three**: Circle Valley, Narraburra and Koppamurra. Each now has a primary named technical scope, retained government native IDs, consistent state/name and positions satisfying the unchanged500m rule. **28 prior pairs remain**. New typed government deposits add **12** unresolved deposit pairs, making **40 total**. A separate114 name/state relation-candidate pairs are explicitly unconfirmed; they are not additional accepted equivalences. See comparison_identity_followup.csv and government_identity_candidates.csv.

Yttria retains its3,685.359m location conflict and both source IDs. Different representative points are not reconciled without footprint evidence. Splinter remains independent of OD6 Splinter Rock.

| Original gap | New controlled evidence / limit |
|---|---|
| Greater Brothers | Existing Jupiter Scoping Study p2 explicitly locates Jupiter within broader Brothers; parent/child relation only, no added Jupiter resource |
| Goschen | 15Oct2025 original MRE p12: **Area1 only**,94.2Mt,0.08%in-situ TREO+Y2O3,74kt reported; THM-phase2.8% is stored separately |
| Lyons | 25Oct2023 maiden MRE p1:0.99Mt,0.32%reportedTREO,3.221kt; Y basis unresolved; Lyons11 contained arithmetic conflict retained; excluded common resource panel |
| Circle Valley | 25Jul2022 ANSTO five-composite bench leach:805–1,386ppm feed,10%HCl,6h,50C; TREO average/max76/82%, magnet average/max82/86%; no whole-resource recovery inference |
| Fingerboards | Captured GCM original process proposal page:planned7.2Mtpa,14,000tpa RE minerals,200tpaDy/Tb oxides,1,800tpaNd/Pr oxides; feasibility underway; no completed-study/JORC admission |
| Splinter | Primary original not recovered; HRE-linked report URL404; do not substitute Splinter Rock documents |

Only **one of the original six** remains without controlled source context. Fingerboards has proposal/process evidence only, Lyons has non-harmonized resource evidence and Brothers has shared context: these are not three new comparable resource alternatives. The expanded database has **three total technical gaps**: original Splinter plus newly discovered Wudinna and Kalkaroo.

## Additional primary observations

- **Narraburra:** original Godolphin2023 annual report, physicalp94/printed92, mirrored by AnnualReports. April2023 month-precision regolith MRE:94.9Mt at738.95ppmTREO includingY,300ppmTREO-CeO2 cutoff, Indicated+Inferred. Four-oxide magnet definition supports130.79/738.95=17.6994%; elementalU11.10ppm andTh32.93ppm remain separate observations. The published TREO formula repeatsEr2O3; this source typo is retained and the table LREO+HREO reconciliation is noted, not silently rewritten.
- **Koppamurra:** original25Jun2026 PFS p8:global243Mt at751ppmTREO includingY, M+I+I; magnet25.3%; U3O8=2ppm andThO2=19ppm are oxide bases, not elementalU/Th. The26MtProbableReserve is a subset, never added. PFS p11 supports68%resource-to-final-calcined-MREO recovery in a typed PFS-model case. It is not pooled with concentrate recovery or bench leach. Dated PFS ordinal3 increases the resource/study panel, without claiming operating status or strict Development eligibility. InitialCAPEX178mAUD is a cost model, not committed financing.
- **Goschen commercial:** both2Jul2026 Iluka and VHM original announcements are retained. Iluka AppendixA supplies nine contractual observations:40mAUD limit;10/30mAUD tranches;3/4-year maturities;10%coupon;146ktREC containing86ktREO over18years. Shareholder approval, FID, funding/financial-close, due-diligence and other conditions are explicit. None is a disbursement or available-cash observation. Iluka says take-or-pay; VHM says take-and-pay: both source terms remain unresolved without the executed contract.

There are **2,795 government text observations**, with numeric valueNULL, documented fields and capture dates; missing effective dates remain explicitly undisclosed. They are raw observations, not scores. database_domain_coverage.csv separates source text from114 distinct validated numeric statement values. Typed study parameters are counted separately.

The source-internal arithmetic checker detects the Lyons11 discrepancy without merging subscopes. Existing generic matching-date/tonnage government-vs-issuer grade checks still exclude Cowalinya, MtClere and Mons from the government screen; all20 government rows remain stored and17 are scored.

## Research applications and interpretation

Partial panels are now **19 / 7 / 8 / 4 / 2 / 17** for resource-port / full infrastructure / composition / resource-study / concentrate / WA official summary. GIS distances are19ports,19power,7road and7rail. These are proximity measures with original coverage bounds; no new road, freight, grid-capacity or legal-access claim is inferred.

AimA retains three assumed AHP scenarios and SAW/PROMETHEEII/TOPSIS. In the19-case resource-port panel, resource-assumption SAW/TOPSIS put MtWeld first and PROMETHEE puts Jupiter first; composition-panel SplinterRock remains first across methods/scenarios. These are partial-criterion exploratory results.

AimB reruns weight MonteCarlo, rounding bounds, scoring-function, leave-out, cohort and cross-method checks. Resource-port method Spearman correlations span0.9421–0.9965, versus0.9529–0.9941 atPhase5; this reflects different cohorts/evidence, not an improvement test. No unsupported measurement-error distribution is introduced.

AimC now describes hard-rock(n6), clay-hosted(n9), mineral-sands(n1) and unclassified(n3) resource cases. Resource-assumption hard-rock/clay median ranks are5.5/11; development-assumption medians11/6. Selected samples and geological labels support description only, not statistical significance or causation.

## Publication and replay

Two newly acquired originals contain third-party credential query values (one in the SA CSV and two in a Meeka webpage). **Original files, original manifest entries and the canonical SQLite history are retained unchanged locally.** New public derivative versions remove the parameters and values, retain originalSHA256, transform name/count and local-retention disclosure. The originals are explicitly Git-ignored, not deleted. Public exports scrub historical credential references while retaining scientific values and IDs. Public replay reconstructs the scientific dataset from the derivative lock; it does not reproduce the withheld credential strings. Every available historical file remains hash-checked; only an explicitly declared unpublished original may be absent from a public replay.

The published snapshot_lock, output hashes and comparison input hashes identify the exact version. CI reconstructs November2, frozenPhase5 and newPhase6 separately. CI no longer overwrites frozen Phase2 results. There is no new database, formal gate definition or manual approval mechanism.

```sh
au-ree-v2 acquire --source-key nt_modat_live
au-ree-v2 all --as-of 2026-11-03 --compare-to results/phase5-2026-11-03 --work work/phase5
au-ree-v2 rebuild --as-of 2026-11-03 --snapshot-lock results/phase6-2026-11-03/snapshot_lock.json --work work/phase6-replay
```

Remaining limits: Splinter original recovery; Wudinna/Kalkaroo primary documents;28 prior and12 new deposit pairs; additional114 cross-source relation candidates; QLD operating-mine/tenement coverage and other state tenement layers; exhaustive issuer feeds; REMP download; Fingerboards original EES PDFs(403), resource scope and completed study; LyonsY basis and inconsistent subtable; comparable recovery endpoints, actual financing disbursements and the original formalC1 gate evidence. None blocks unrelated valid database observations.
