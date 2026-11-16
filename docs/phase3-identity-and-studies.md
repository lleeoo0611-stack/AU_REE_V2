# Phase 3 — national identity and study-case evidence, 2026-11-03

The same Python entrypoint, SQLite database and R engine now distinguish discovery records,
source-native identities, document-supported equivalences and engineering study cases. Existing IDs,
source snapshots and historical scope records are retained. No researcher signature or independent
approval is inferred from document extraction or rule validation.

## National discovery and resolution

The pinned AU_REE commit `093d724cc25fc319725bf347fc4d8ab196aadaf3` supplies the full historical
1,006-row screening index: WA 505, NSW 170, VIC 64, QLD 40, NT 28, SA 178 and TAS 21.
It preserves 121 source-advertised WA parent codes as PROJECT_CANDIDATE records, never approved Projects.
This is a recovered historical index, **not** a fresh download of all state raw government datasets.
Two credential-bearing reference cells were removed after repeated URL decoding. The manifest records
their candidate IDs/columns, original upstream SHA-256 and the derivative hash; no identity or classification
field was replaced. The source-adapter `native_id` column remains a label until its designated native field
is independently established (GA's historical adapter sometimes used a name, not ENO).

287 index candidates have an exact candidate-ID link to the 339 archived selections. An absent link is
not proof of missing government evidence: some controlled GA layers have additional records, and the
two historical reconstructions have different scopes. The remaining references stay visible.

All 339 archived selections receive a native-resolution disposition: 111 exact native deposit links,
206 state-native Site links and 22 legacy-only records without an official native link. All IDs and
multi-feature source bundles remain available; source-record links do not establish a unique Project.
State-native fields are fixed by adapter, not searched arbitrarily. Nonunique same-source IDs and
cross-layer SA IDs cannot merge distinct named locations (including Olympic Dam / Clarke).

Two equivalences currently satisfy explicit document/location rules:

- The source-registered Central Mia Project label and the WA Mount Ridley Project label refer to the
  same parent Project (issuer annual report p13). The Central Mia resource scope remains separate.
- Two government Mia deposit records agree in name, state and location within 500m and are supported
  by the primary Mia resource document. This is a rule-supported identity, not legal-footprint verification.

28 registered Project IDs therefore form 27 canonical registry groups. The 203 native deposit records
form 202 canonical groups under accepted rules, **not 202 certified unique physical deposits**.
Of 39 cross-layer same-name/state deposit pairs, 1 is document-supported, 11 have location conflicts
and 27 still require technical identity evidence. Yttria is deliberately not forced through the location rule.
Native Site records remain source-specific location records, not certified mine footprints.

The output has a canonical membership table, accepted decisions, native ledger and review leads.
Canonical aliases never delete old entities. Concurrent resource scopes under one canonical Project
are excluded from a common panel pending an explicit scope choice; they are not summed or picked by score.
Jupiter is linked to the wider Brothers program, not merged with it. Donald/Jackson and MIN5532,
RL2002/RL2003 remain distinct document-referenced deposits/tenements; references are not current title checks.

## New primary documents and bounded evidence

| Document | Captured evidence | Important separation |
| --- | --- | --- |
| ASM Dubbo Heap Leach Scoping Study, 11 July 2025, PDF pp24,26,51 | Toongi resource; alternative scoping route; three mining-zone Nd leach inputs; processing loss and capex assumptions | Older multi-product OFS is not the maturity of the new heap-leach route. Element leaching is not overall ore-to-product recovery. |
| Critica Jupiter Scoping Study, 20 October 2026, pp3,14,25 | 1.7Bt at 1,700ppm TREO, two-significant-figure total; base recovery 58%, design basis 63%; study stage and unsecured funding | Full resource, 107Mt production target, MREC recovery and wider Brothers landholding are separate scopes. |
| Hastings quarter, 30 October 2026, pp5,7,8 | Yangibana Stage1 DFS: whole-ore flotation recovery 85.7%, concentrate 27% TREO, A$333.4m capex; financing and care/maintenance status | No binding financing reported. Completed DFS does not mean active development, FID or a financed project. Thailand plant is separate. |
| Astron Annual Report 2024, pp9,18,20,24 | Donald Phase1/Phase2/ Jackson distinction; A$183m earn-in and 49% interest, REEC offtake and process route | This is dated historical evidence requiring reaffirmation, not proof all project funding is available in 2026. |

Every study case is hash/page/marker bound. Data errors or one unreadable document produce local Review Queue
items and leave other cases usable. The database retains case evidence versions under content-derived keys.
Financial commitments, capacity, capex, earn-in conditions, funding absence and corporate holdings are
not converted to an invented common finance ordinal or a common currency without a transformation.

### Dubbo oxide-basis reconciliation

The original 2017 Toongi table reaffirmed in the 2025 study reports 7,400ppm lanthanide oxides and
1,400ppm Y2O3 separately. Its TREO footnote excludes Y2O3. The harmonized all-REE oxide grade is
therefore `7,400 + 1,400 = 8,800ppm`, yielding `75.18 × 8,800 / 1000 = 661.584kt` contained oxide.
Original values/bases remain separate observations. The transformation contract requires identical
statement, scope, date, units and source hash; changed arithmetic or cross-scope components fail QA.
The 1,660ppm magnet-oxide total yields 18.8636% of the harmonized TREO. This is an explicit oxide
sum/ratio, not an inferred assay or an automatic HM/monazite conversion. Printed rounding and
historical effective dates remain material limits.

## Cohorts and research outcomes

- Seven issuer-scoped resource cases support the inventory/port panel. Only the five previously
  queried Projects have the complete maintained-road/operational-rail/high-voltage-power panel;
  Dubbo/Jupiter's unqueried AOIs remain missing instead of borrowing another site's GIS coverage.
- Three cases have complete magnet-oxide shares: Mia, Yttria and normalized Dubbo. NdPr-only
  shares and product-basket composition are not substituted for a full resource magnet share.
- Three cases support the resource/study-stage panel: Nolans, Dubbo and Jupiter. Stage is an
  internal criterion in this panel; a stage/rank relationship is consequently not external causal evidence.
- Two DFS model cases (Browns Range and Yangibana) share the whole-ore TREO → mineral-concentrate
  endpoint. Recovery and concentrate grade form a **process-indicator screen**, not an overall development
  ranking. Mineralogy, ore-feed grade and test protocols are not harmonized. Under the point inputs
  Yangibana exceeds Browns Range on these two indicators, while its report also states care/maintenance
  and no binding financing. Technical indicators alone therefore do not establish development readiness.
- Jupiter's MREC base recovery, its distinct design basis, and Dubbo's element/zone leach inputs remain
  separate comparison groups. Dubbo Nd model-zone values span 68.7–79.9%; this is a zone range,
  not a statistical error distribution or whole-plant recovery. Missing measurement bounds remain
  unquantified; point-input case uncertainty outputs are blank, not spuriously precise confidence intervals.
- The 20-row government summary screen is retained as exploratory and separate from issuer-scoped panels.

Aim B retains weight/method/scoring/criterion/domain/cohort experiments for eligible partial panels.
Deleting the only domain or leaving a single alternative is explicitly not estimable. Aim C remains
descriptive host-type/stage association and internal model sensitivity; no causal geological claim or
development-success probability is made from these selected samples.

Of the 27 canonical registry groups, 4 have primary resource plus study evidence, 3 resource-only,
2 study-case-only and 18 no controlled primary technical scope yet. The coverage table lists other
unverified or differently scoped resource claims so a dated primary scope cannot masquerade as a
latest Project total. These are corpus coverage states, not negative findings about unlocated reports.
The complete six-domain and strict resource/recovery Development cohorts remain incomplete.

## Remaining evidence work

Validation includes 39 local Python tests, independent R numerical invariants and a dedicated R
contract test ensuring absent measurement bounds produce blank intervals. Tests also cover all 1,006
index rows and 121 parent references, preserved 339 selections, native-ID ambiguity, typed equivalence,
scope-safe oxide conversion, case collisions, idempotency and isolation of unreadable documents.

Recover original state raw chunks and reconcile remaining source adapters, 38 unresolved cross-layer
deposit pairs, source-advertised parent codes and unlinked physical Sites. Reaffirm historical finance
events and technical scopes before cutoff-specific current-status claims. Add properly scoped recovery
bounds and engineering uncertainty; obtain comparable funding conditions and costs without assuming zero.
The full index and local disposition ledgers are complete within their declared scopes; full national
Project–Deposit–Site identity certification and complete six-domain research are **not** yet complete.

Run the same system:

```sh
au-ree-v2 all --as-of 2026-11-03 --work work/phase3
au-ree-v2 rebuild --as-of 2026-11-03 --snapshot-lock results/phase3-2026-11-03/snapshot_lock.json --work work/phase3-replay
```
