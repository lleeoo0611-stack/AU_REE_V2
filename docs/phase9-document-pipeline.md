# Phase 9: automatic document evidence

Baseline: Phase8 `5c0b9fcc8c108181d9e771f03d7dc6b186198893`.
Cutoff: 2026-11-03. Canonical operational store remains
`work/phase5/canonical.sqlite`. No schema migration, new production module,
parallel formal database or replacement R engine was introduced.

## Executable flow

`discovery.search_tasks` derives bounded issuer-search jobs from existing
registry identities/aliases and source metadata. Company/ASX identifiers remain
NULL when unavailable; the search is not exhaustive. Issuer detail/pagination
budgets, explicit allowed-host fallbacks, URL/SHA deduplication and local failure
statuses remain in the existing discovery/acquisition implementation.

`pdf_extract.recognize_document` classifies document mentions, scans pages,
locates aligned resource totals and laboratory extraction rows, captures native
tables/cell geometry and retains surrounding definitions. Cross-page matching
headers produce continuation candidates, never an automatic resource sum.
The existing native/positioned/selective-Tesseract fallback is reused; no new
document required OCR. Classification is a relevance label, not proof of a
completed study or financing event.

`capture_documents` writes SHA-addressed extraction artifacts to the same
manifest. `acquire` and `all --refresh` automatically recognize acquired
documents under the versioned Phase9 policy. Unchanged originals, extraction
contracts and registry identities reuse checksum-verified artifacts. The
`recognize` CLI also supports offline processing and source-key subsets.

`evidence.ingest_recognized` verifies original/artifact SHA, physical page/text,
row tokens, numeric/unit ranges, resource/reserve categories and rounding-aware
contained-TREO consistency. Accepted records go directly into existing
`observations`; insufficient candidates remain excluded or REVIEW with reasons.
No new Project-specific claim values were added to `claims.json` or
`study_cases.json`. Shared Evidence Selection remains the only scoring route.

Resource tables retain source-defined scopes, cutoff, oxide definitions and
category. Automatically recognized resource fields use `reported_resource_*`
until a compatible effective date and selected resource scope are established.
Publication dates are explicitly disclosure dates, not invented resource dates.
Individual oxides/elements have their own basis; Sc is not folded into TREO.
Acid-leach tests retain sample ID/interval, reported mean versus individual test,
reagent, temperature, residence time, feed and leach endpoint. Unresolved acid
concentration, pressure and scale remain Missing.

Commercial/development disclosures retain NULL numeric values. Qualitative
"full recoveries" is not converted to100%; conditional facilities are not cash.
Company funds require explicit Project attribution and cannot be assigned from
an adjacent Project sentence. Forward-looking studies/events remain candidates.

Extraction SHA must be present in the analysis lock as well as original SHA.
This prevents later extraction versions leaking through an older PDF snapshot.
Original observations and previous extraction artifacts remain queryable.

## Actual acquisition and database increment

AR3 issuer pages returned429. The issuer-linked original Hermes PDF was
downloaded successfully: 30October2026 quarterly, SHA
`0a592d02d0a071484617f6a39c041a28523466db007282956c905447b8cc56d9`.
Its PDF metadata title includes "Draft"; the body is the dated ASX release linked
from the public issuer announcement. Its qualitative pilot recovery is not a
numeric recovery or completed DFS.

Asra's Weblink original URL returned404. The public Aspect Huntley filing mirror
provided the issuer-authored 2April2024 technical announcement, SHA
`288f07ef6630bb20031240f92d99114cfab43385bd493f45ef000213747c4e70`.
Title/date/issuer identity and physical p2 were checked. The unavailable original
URL could not be compared byte-for-byte. The mirror is identified explicitly.

The acquisition receipt records six actual endpoints: four unavailable primary
endpoints and two successful alternatives. Search failures are not absence of
Projects/evidence.29 registry-derived tasks were generated for this targeted run;
they are not proof of complete national or issuer coverage.

| Measure | Phase8 | Phase9 |
|---|---:|---:|
| Selected snapshots / PDF entries |89/42|100/44|
| Documents parsed by new pipeline |0|9:8PDF +1HTML|
| PDF physical pages / HTML records |0/0|396/1|
| Relevant page units / native tables |0/0|345/28|
| Automatic candidates |0|656|
| Accepted candidates / raw observations |0/0|170/283|
| Accepted automatic numeric / NULL disclosures |0/0|131/152|
| Distinct selected validated numeric statements |132|263|
| Canonical registry groups / source-scoped resource cases |31/22|31/22|
| Original entities preserved |7,554|7,554 unchanged|
| New hierarchy / source bindings |0/0|1/2|
| Unresolved deposit pairs / government candidates |36/112|36/112|
| Primary technical gaps |1|1|

Candidate outcomes:170accepted,69REVIEW and417without sufficient Project
attribution/validation. One row may produce multiple element observations.
The131numeric observations include118Technical,8Strategic and5Resource fields.
Of these,112are Asra's16selected-test/mean rows ×7oxide extraction columns.
Others include source repetitions and finer original-resource evidence, not
131new independent measurements. They are not added to resource inventory.

The two means,66%TREO for HCl and49%for sulfuric/magnesium-chloride tests,
remain separate50°C/16h selected-sample tests. They are not overall recoveries
and are not compared with Circle Valley's different6h acid tests.

Two originals explicitly locate Yttria within Mt Stirling. They automatically
support one hierarchy edge, with two source bindings and both Project IDs
retained. This does not resolve Yttria's representative-point conflict or justify
deposit equivalence. No new government inventory, independent Project, Deposit
or Tenement is claimed in this phase.

## Coverage and research applications

Selected raw Technical evidence387→641 includes candidate/review rows and
engineering parameters; qualifying T1remains0, TC1/TC2remain2/2. Raw Commercial
32619→32632 includes32576government title attributes; excluding them43→56.
Only5new automatic Commercial disclosures validate as raw NULL-valued text.
Typed events remain19(18Commercial +1Development), distinct from those texts.

Main scorable coverage remains **R22/S9/T0/D5/I20/C6**. C6is the exploratory
dated financing-milestone codebook, not formal C1admission or available cash.
Strict Development/full-evidence/formal C1remain0/0/0. Formal definitions and
ID/ROLE/WINDOW/JORC/PANEL/GIS_RELEASE gates are unchanged.

Nine panel sizes remain20(global-port),7(four-layer infrastructure),9(composition),
5(study),2(concentrate),2(independent concentrate recovery),5(financing),
2(endpoint-case screen),17(official summary). All125panel CSV files are
byte-identical to Phase8, including AimB sensitivity/uncertainty outputs;
621method/scenario rank comparisons have zero changes. AimA leaders remain
conditional on existing panels/assumed weights. No unsupported measurement
error is added to AimB. AimC now has queryable test/process descriptors, but
one newly detailed Project and incomplete conditions do not justify a new
cross-project recovery regression or causal inference.

The strict T1contract remains whole-ore/final-separated-REO/validated-plant-design.
It excludes concentrate, leach and mixed-intermediate routes by definition; it
must not be represented as absence of metallurgy. Candidate recovery groups
instead preserve endpoint/feed/element/scale/reagent/conditions/statistic.
These groups currently lack complete conditions or multiple eligible Projects.
No substitute formal technical criterion, maturity double-counting, speculative
processing-complexity ordinal or new finance-sufficiency score is introduced.

`evidence_pipeline_diagnostics.csv` separates372Project×criterion cells:
100scorable,7scope/basis incompatible,6extracted-not-validated,
81raw-but-criterion-not-established,158acquisition/extraction/search-incomplete,
20source-not-discovered. Search completeness stays Unknown. No exhaustive
"not disclosed" or stage-not-applicable conclusion is invented. Discovery and
document receipts separately preserve HTTP/download/extraction failures;
Project attribution remains unknown for unbound failures.

## Validation and limits

- Local full suite:124passed after Windows sandbox temp-directory failures were
  isolated by rerunning unchanged tests with ordinary execution permissions.
  Final document suite:22passed, including fresh reparsing of both new originals,
  version reuse, token tampering, oxide basis and hierarchy tests. CI runs126.
- R analytical invariants passed. Frozen Phase5/6/7/8 scientific reconstructions
  match24/24/31/36files. Phase9 clean replay matches36scientific files,
  eight document/membership artifacts byte-for-byte, unordered resource and
  criterion rows, valid raw scientific identities and diagnostic states.
- Rendered-cell benchmark:33cells across six table scopes/five documents;
  29true positives,0false positives,4misses, precision100%, recall87.88%.
  Units and SHA/physical-page location are complete for accepted benchmark
  cells. This is a small selected benchmark, not corpus-wide precision/recall.
  Koppamurra density/multiline columns and Browns Range's Wolverine layout
  remain explicit missed fields; printed Mt Weld4.1% is not overwritten by the
  narrative4.12% value.
- Warm-cache Asra parse:14pages/4tables/39candidates,11.76s and21.7MB tracked
  Python peak. SQLite streaming36,641historical observation versions took1.23s;
  native-library allocations are excluded and these are not capacity guarantees.
- The canonical store retains extraction history, including unpublished draft
  versions. A clean replay reconstructs selected active evidence/science, not
  the operational store's incidental extraction-history bytes. In this release
  it omits13additional legacy REVIEW rows and some metadata versions; these
  differences do not change the validated scientific identities or rankings.

Remaining limits: bounded static issuer discovery, incomplete publication dates
for some existing presentations, table continuations requiring scope resolution,
unaligned resource layouts, incomplete process conditions and unresolved national
identities. Splinter's original technical gap remains. These local gaps do not
block the other documents or valid partial MCDA panels.

## Reproduce

```sh
au-ree-v2 recognize --as-of 2026-11-03 --source-key SOURCE_KEY
au-ree-v2 all --as-of 2026-11-03 --work work/phase5
au-ree-v2 rebuild --as-of 2026-11-03 --snapshot-lock results/phase9-2026-11-03/snapshot_lock.json --work work/phase9-replay
python tools/check_replay.py results/phase9-2026-11-03 work/phase9-replay/latest.json
python tools/evaluate_documents.py work/document_benchmark.json
python -m unittest discover -s tests -v
Rscript tests/test_methods.R
```
