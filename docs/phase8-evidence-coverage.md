# Phase 8: evidence coverage and MCDA readiness

The operational database remains `work/phase5/canonical.sqlite`. No schema migration, second database, new production module or replacement R engine is introduced. The source store, shared selection, typed studies, GIS and existing R methods are reused. Phase 5/6/7 frozen outputs are unchanged.

## Verified increment against Phase 7

| Measure | Phase 7 | Phase 8 |
|---|---:|---:|
| Canonical Project registry groups, not a national total |31|31|
| REE-related native government entities |712|712|
| Newly acquired QLD native Tenements, separately counted |0|5,522|
| Issuer-documented prospects added |0|2|
| Comparable source-scoped Mineral Resource cases |19|22|
| Distinct validated numeric statements |114|132|
| Engineering cases / numeric parameters |9 / 40|9 / 40|
| Verified typed events |12|19 (18 Commercial, 1 Development)|
| Selected source snapshots / PDF entries |76 / 38|89 / 42|
| Project groups with any controlled primary technical scope |28|30|
| Unresolved deposit pairs |40|36|
| Unconfirmed government relation candidates |116|112|
| Confirmed representative-site relations among those candidates |0|4|
| Main-code scorable groups R / S / T / D / I / C |19 / 8 / 0 / 4 / 19 / 6|22 / 9 / 0 / 5 / 20 / 6|
| Endpoint-specific TC1 / TC2 eligible Project groups |2 / 2|2 / 2|
| Strict Development / full evidence / formal C1 |0 / 0 / 0|0 / 0 / 0|

All counts come from the sealed database exports. Resource cases are scoped statements, not additive whole-Project totals. There are no newly certified independent Projects in this increment. Two internally identified issuer PROSPECT entities and 5,522 official TENEMENT entities are not promoted to Projects.

`comparison_metrics.csv`, `comparison_identity_followup.csv` and `comparison_primary_gap_followup.csv` retain row-level baseline reconciliation. The 116 government pair rows remain queryable: four now have a confirmed representative-site relationship and 112 remain candidates. A representative-site relationship never equates SITE and DEPOSIT.

## Acquired originals and interpretation

`data/phase8_acquisition.json` records source URLs, hashes, dates, raw counts and original API-response counts. The immutable source bytes are in `data/snapshots/` and the sealed `snapshot_lock.json` binds the selection.

- **Yangibana 2026 annual report:** physical pp13-14, JORC 2012, 100% Project Mineral Resource 29.93Mt at 0.93% TREO, reported 276.955kt TREO. This reaffirms an October2023 estimate as of30June2026; it is neither the separately printed Ore Reserve nor a 40% ownership-attributable inventory. Rounded inputs explain the small arithmetic difference. NdPr grade0.32% is retained as raw Strategic evidence; no Dy/Tb or complete magnet ratio is invented. The existing30October2026 Stage1 DFS concentrate evidence supplies a dated study criterion, not current activity status.
- **Brockman, same annual report p14:** main Project Inferred Resource41.6Mt at0.20% TREO, 700ppm Nb2O5 cutoff. Southern Extension, niobium resources and Yangibana are excluded. Contained TREO is calculated from rounded source inputs with explicit bounds, not presented as a separately reported total.
- **Wudinna RNS4065A,26October2026:** issuer HTTP429 retries failed; the same original announcement was retained from the London Stock Exchange. Its embedded JavaScript string is decoded without execution; CSS/scripts cannot become evidence. The22October2026 combined Boland/Head MRE is150Mt at470ppm TREO, reported70.4kt, Indicated+Inferred. Reported grade includes Ce andY; the cutoff definition differs and remains explicit. The reported four-magnet-oxide group112ppm divided by470ppm supplies23.8298%, with printed rounding bounds. Separately rounded NdPr101ppm andDyTb10ppm are not forced to sum to112ppm. Exploration targets are excluded. Boland and Head PROSPECT relations document the combined scope; their resources are not counted again. Scoping is planned and the reported ISR-recoverable resource fraction is not an overall process recovery.
- **Kalkaroo ASX19February2020:** physical p7 records four geochemical sample statistics, including maximum calculated TREY oxides8482ppm and reported mean HREE319ppm. These are not JORC resources, plant recoveries or resource-average grades. The reported plus/minus134ppm has no established measurement-error interpretation. This closes the absence-of-primary-process-evidence gap while leaving the REE resource and common Technical criterion missing.
- **Nolans ASX30October2026:** issuer-authored14-page original PDF retained from a public filing mirror, whose host is not ASX. Title, date, issuer authorisation and relevant pages were checked. Seven new events cover pending senior credit/contractual close, separate EFA and GRMF conditional subscriptions, two offtake updates, early construction and lender ESAP actions. Corporate cash885m is not assigned to the Project. Early construction is not evidence that financing conditions are satisfied. Lender ESAP action signoff is not all mining approvals or financial close. Exact dates not disclosed by the original are not fabricated.

Three newly used PDFs, one original RNS HTML and three government inventories supply the main increment. The fourth additional PDF entry is a discovered historical VHM noteholder meeting document, not a new technical observation or current funding update. Other retained discovery pages are discovery evidence only. `data/phase8_discovery.json` records bounded attempts for all six requested issuers; inaccessible or JavaScript-driven pages do not establish current status. Exhaustive latest-document coverage is not claimed for Dubbo, Goschen, Jupiter or Donald.

## National native data and relationships

Queensland CurrentQldResourceAuthorities layers40/80/120 were actually downloaded through the existing complete-OID inventory and500-record paging adapter. EPM2816, MDL201 and ML2505 rows form5522 distinct `permitid` values, with16 archived API responses. All title polygons, holders, status, dates and previous-permit references remain original evidence. The three inventories do not explicitly designate REE in their mineral fields. They are therefore stored as TENEMENT records under `QLD_RESOURCE_AUTHORITY`, separately from the712 REE-native entities. No Project affiliation, right to develop, current validity or tenure identity is inferred from holder names or polygon proximity.

Selected government inventory raw rows total149599, including the prior overlapping MINOCC layers; this is not a count of distinct physical assets. Existing seven-state/GA sources remain available. Title attributes contribute32576 additional NULL-valued source-text observations, not32576 project-level financing observations or scores.

Two additional native deposit equivalence edges link WA S0002531 to GA ENO335930 (Cummins Range) and SA MINDEP11871 to GA ENO806972 (Koppamurra). Existing primary MRE/PFS pages, designated native IDs, official name/state consistency and the existing representative-location check support these edges; transitive membership resolves four old pair rows. Project, SITE and DEPOSIT kinds remain distinct. Yttria location conflict, Greater Brothers/Jupiter scope separation and Splinter/Splinter Rock independence are retained. The extension is enabled only by `document-native-extension-phase8-v1`, so frozen earlier locks do not acquire later identity decisions.

## Technical and Commercial comparison

Technical raw evidence383→387 comprises the existing338 government-text observations,11 numerical technical statements,34 engineering parameters and four new Kalkaroo sample statistics. T1 remains0: a final separated-REO, whole-ore, validated-plant-design contract cannot admit concentrate, leach solution, selected composites or MREC/PFS estimates.

An independent `issuer_resource_concentrate_recovery` panel now compares R1+TC1 for Browns Range/Yangibana. TC1 is whole-ore, TREO-including-Y recovery to mineral concentrate at DFS-model scale,84% versus85.7%. It does not replace T1. The existing R1+TC1+TC2 panel also becomes rankable at n2. The resource scopes and engineering mine plans remain separately labelled; inventory is not multiplied by these recoveries to invent recoverable resources. TC1 records process yield rather than stage, but eligibility is conditioned on DFS maturity. Both alternatives have DFS cases; a two-case constant-stage sample cannot estimate an independent maturity effect. TC2 product grade and recovery are not assumed statistically independent. No complexity/reagent-burden ordinal is invented from operation counts.

Commercial numerical observations14 and engineering parameters6 are unchanged. Commercial typed events12→18, plus one separate Development event. Distinct raw Commercial evidence37→32619 is dominated by32576 title attributes; excluding those title attributes, the increase is37→43. The scientific raw identity now includes event/facility/contract IDs, preventing different instruments with the same date and scope from being collapsed in coverage. Selection already works per instrument and the financing codebook remains unchanged. Candidate C1 coverage6 is a dated milestone, not available cash, percentage financed or formal C1. Nolans stays at conditional milestone2; no close/drawdown upgrade is made.

## MCDA and Aim A/B/C

| Exploratory panel | Phase 7 n | Phase 8 n |
|---|---:|---:|
| Resource + global port point proximity |19|20|
| Resource + all four infrastructure measures |7|7|
| Resource + full magnet composition |8|9|
| Resource + dated study maturity |4|5|
| Resource + concentrate recovery + grade |1, no ranking|2|
| Resource + concentrate recovery only |absent|2|
| Resource + disclosed financing milestone |4|5|
| Endpoint-only concentrate engineering cases |2|2|
| WA government resource-summary screen |17|17|

Aim A reuses three assumed domain-weight scenarios, AHP consistency audit, SAW, PROMETHEE II and TOPSIS. Yangibana leads both concentrate/resource panels in all three scenarios/methods; this is a two-alternative exploratory comparison. In the five-case resource/financing panel Jupiter leads the resource scenario, Nolans the development and strategic scenarios. Splinter Rock leads the nine-case resource/composition panel. No complete six-domain or formal C1 ranking is produced.

Aim B retains1000-draw weight experiments, method comparison, alternative scoring, leave-one-criterion/cohort sensitivity and separate reported-rounding bounds. All three methods agree on the new concentrate comparison. Yangibana ranks first in100% of the specified weight draws; that reflects dominance within this narrow panel, not certainty of development. With Yangibana joining the financing panel, Jupiter's resource-scenario first-place model frequency changes95.2%→91.8%, while Nolans' strategic-scenario frequency changes95.8%→98.1% (development remains100%). Relative ordering among the four old financing alternatives is retained, while Yangibana inserts ahead of Goschen in the resource scenario (Goschen4→5 under all three methods) and in strategic TOPSIS. PROMETHEE preference flows and weight-draw frequencies depend on the cohort. No unsupported measurement error is sampled. `comparison_ranks.csv` separates newly added alternatives from common ones; these are evidence/cohort effects, not temporal development outcomes.

Aim C retains descriptive geology, resource, dated-study and GIS outputs. Wudinna's Boland/Head resource uses the existing wider Project representative point for GIS, not a newly validated resource footprint. Yangibana/Brockman lack accepted GIS coordinates in this run, and Wudinna lacks a complete four-layer intersection. These gaps do not block Resource/Strategic/Technical analyses. The new Technical n2 and financing n5 panels do not justify multivariate or causal inference; no significance claim is made.

## Formal definitions and verification

The original AU_REE proposal text and `C0_FREEZE_AND_C1_C2_POLICY.md` / upstream eligibility configuration were inspected. Policy `C0_F1F2_COHORT_C1C2_V1_20261031` retains the six gates ID,ROLE,WINDOW,JORC,PANEL,GIS_RELEASE and says9/12-criterion panels remain candidates. The existing V2 compatibility configuration already records this boundary. Nothing here selects an approved formal panel or imports signatures. Nolans' new early-construction disclosure and Yangibana care-and-maintenance context must not be mistaken for pre-FID current eligibility. D1 is dated study evidence, not an automatic current-activity classifier.

The new tests cover original documents, source-container decoding, incompatible scopes, NULL events, stable native IDs, two prospect relations, resource non-duplication, instrument identity and idempotence. A Phase6 regression fixture now reads its frozen Phase6 lock rather than an evolving same-day manifest; its19-case assertion is preserved. Acquisition/discovery verify saved bytes and refuse to overwrite an invalid immutable capture. One newly fetched Critica search HTML failed local post-save integrity/read checks, was excluded before use and retained unpublished under `work/retained_originals/`; its cause is not established. No observation relies on it.

The full local suite passed103 Python tests and R analytical invariants; after the final HTML-error-isolation addition, all15 focused Phase8 tests passed. CI runs the full104-test suite (89 baseline+15 additions). Phase5/6/7 scientific reconstruction comparisons passed for24/24/31 matrix/ranking/criteria/weight files. The canonical sealed run is `20261103T123611-1eabcb23`, source-content SHA `13ff6fe1cec67712988f779597ffc5aee745e60bb4354b40651adc662a9b7849`. The retained canonical store can contain earlier extraction/review versions; clean reconstruction and repeated execution are compared by scientific identities and stable entity IDs, not by incidental extraction-history row counts.

```powershell
$env:PYTHONPATH='src'
python -m au_ree_v2 all --as-of 2026-11-03 --compare-to results/phase7-2026-11-03 --work work/phase5
python -m au_ree_v2 rebuild --as-of 2026-11-03 --snapshot-lock results/phase8-2026-11-03/snapshot_lock.json --work work/phase8-replay
python tools/check_replay.py results/phase8-2026-11-03 work/phase8-replay/latest.json
python -m unittest discover -s tests -v
Rscript tests/test_methods.R
```

The remaining primary gap is Splinter: only the official historical resource summary/native scope is available, not the underlying JORC original. Remaining36 deposit pairs/112 government candidates require their specific scope/location/ID evidence. Current financing availability, additional endpoint-matched technical cases, exhaustive issuer coverage, title-to-Project foreign keys and missing GIS scopes remain incomplete. Missing stays NULL and does not mean zero or absence.
