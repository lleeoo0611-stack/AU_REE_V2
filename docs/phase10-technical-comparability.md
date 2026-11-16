# Phase 10: one technical comparison contract

Baseline: `f0c308d9336565ae1b4a63c789044d03aa0de94c`, cutoff 2026-11-03.
One canonical SQLite database, existing observation/case tables, unchanged
stable identities, no schema migration or additional production module.

## Data flow and maintenance

Extraction still records source values and context. `evidence.ingest_recognized`
validates original/artifact SHA, page, row tokens, identity, date and units.
`selection.resolve` now creates a versioned technical view of that same inventory.
`technical_record` classifies mineralogy/processing, process performance and
evidence quality without creating tables or scores. `technical_compare` checks
the existing criterion contract, feed, endpoint, basis, scale, quantity, scope,
conditions and explicit model assumptions. `technical_comparability` handles
duplicate scientific identities and concurrent conflicts before selection.
Criteria and matrices consume these decisions; the R engine is unchanged.

The current policy opts into these rules. Frozen Phase5–9 policies do not.
Current runs replace `document_recovery_groups.csv` and
`recovery_comparability.csv` with the single `technical_comparability.csv`;
historical replays still produce their original outputs. Existing study,
process-variable, criteria-resolution and coverage exports remain available.
No parallel technical selection engine, technical store, quality score or
processing-complexity ordinal codebook was introduced.

Comparison status is relative to a declared numerical screen. A source-specific
leach result labelled NOT_COMPARABLE remains a valid observation; this does not
mean the test itself is scientifically invalid. Reason codes explain missing
conditions or representativeness and mismatched quantity, scope, endpoint,
feed, REO basis or scale. NULL-valued validated descriptions are DESCRIPTIVE_ONLY.
The table retains source/date/case, conditions, assumptions and allowed analysis.
`study_date` retains the input's reported effective/disclosure date, not an
inferred experimental day. Detailed date-role qualifiers remain in the original
observation and `resolved_evidence.csv` raw provenance (for example CircleValley's
announcement date versus May/June tests, and Asra's disclosure date).
Duplicate sources corroborate one case/quantity rather than increasing samples.
Conflicts produce NULL, with all evidence IDs and source/page locators retained.

## Scientific basis and boundaries

These are operational research contracts, not scores derived from literature.
Public abstracts/snippets and the accessible JORC text were checked; subscription
full texts were not obtained or assumed to have been read.

- [Jordens, Cheng & Waters (2013)](https://doi.org/10.1016/j.mineng.2012.10.017)
  reviews mineral beneficiation and distinct physical separation operations.
  It motivates retaining mineralogy and stage/endpoint, not counting operations
  as a universal measure of difficulty.
- [McNulty, Hazen & Park (2022)](https://doi.org/10.1557/s43577-022-00288-4)
  reviews ore-processing and separation routes. It supports distinguishing
  routes and process boundaries; its reported industry range is not used to
  impute any Project's recovery or measurement uncertainty.
- [Borst et al. (2020)](https://www.nature.com/articles/s41467-020-17801-5)
  directly investigates mineralogical/speciation controls and describes defined
  sample, reagent and leaching conditions. Its samples do not establish that
  any Australian selected composite represents its whole resource.
- [JORC Code (2012), Table1 Section4](https://www.jorc.org/docs/JORC_code_2012.pdf)
  requires reporting process suitability, the nature/amount/representativeness
  of testwork, domaining, recovery factors and deleterious elements. This
  motivates explicit quality/representativeness limits, not a weighted score.
- [Dayo-Olupona, Genc & Onifade (2020)](https://doi.org/10.1016/j.resourpol.2020.101879)
  concerns criteria-based technology adoption using a hypothetical mining case.
  It supports keeping decision definitions explicit; it does not validate a
  REE-specific complexity ranking or this study's weights.

The existing TC1/TC2 concentrate screen compares independent dated DFS mine-plan
forecasts under explicit assumptions, not matched laboratory experiments or
measured operating performance. Different mine-plan scopes are retained and
are not substituted for global resource-average performance. Missing laboratory
conditions are not invented for these engineering forecasts. Laboratory results
need their own defined common contract; none has yet been adopted across Projects.
Formal T1, D1, C1, panel definitions and the six C1 gates are unchanged.

## Existing cases

| Evidence | Retained distinction | Current numerical use |
| --- | --- | --- |
| Browns Range / Yangibana | Whole ore to mineral concentrate; TREO including Y; DFS design; independent mine plans | Two cases/two Projects, TC1 recovery and TC2 concentrate grade |
| Jupiter | 58% scheduled-feed MREC base versus 63% alternative design | Distinct parameters; not concentrate or final-separated recovery |
| Koppamurra | 68% PFS mine-plan resource-to-calcined mixed REO; not global243Mt resource performance | Descriptive case value; endpoint/feed/scale differ |
| Dubbo | Nd West79.9%, Central68.7%, East75.9%; post-leach loss separate | Three zone inputs in one case; no multiplication or probability model |
| Cowalinya | Selected45-composite diagnostic84.9% versus separate1kg MREC product51.8%TREO | Selection limitation retained; product grade is not recovery |
| Circle Valley | Five bench composites; mean/max and TREO/magnet bases distinct; HCl10%,6h,50C | Scoped testwork; pressure/representativeness not established |
| Asra / Yttria | Two acids × selected tests/means × seven oxide quantities | 112values,16test rows,one Project; no pooled overall recovery |

## Document validation

A generic positioned-cell repair uses exact tonnage/TREO headers, native cell
values, column positions and matching row tokens. Split headers must align
horizontally and be immediately above the body table. Density is not skipped
by an assumed index. Missing basis and unresolved mineral fractions remain held.

Wolverine physicalp54 now verifies7.3Mt and0.96%, retaining the Wolverine
deposit scope separately from the DFS feed including stockpiles. The old gold
benchmark incorrectly expected ppm for its grade; the new evaluation fixes this
under a new version while retaining an exact legacy evaluation mode.
Koppamurra physicalp8 now aligns243Mt/751ppm rather than density1.6, but its
local explicit TREO definition remains unresolved. Its two cells stay outside
the validated benchmark. No resource inventory is duplicated or promoted.

The33-cell benchmark improves29→31true positives,0false positives,4→2misses:
precision100%, recall87.88→93.94%. This is a selected benchmark, not corpus-wide
accuracy. Two previously unparsed document pages (Burracoppin and Brockman annual
report) add five held candidates,zero incorrectly validated totals. Rotated
mineral-fraction tables and multiple-resource/reserve contexts remain unresolved.
See `data/phase10_unseen_layouts.json`; this is a safety test, not a recall claim.

## Reproduce

Measured result:641technical rows (497mineralogy/processing,138performance,
6quality), of which134are descriptive-only,503do not satisfy the declared
comparison screen or source validation, and4numeric observations qualify:
TC1/TC2 for two independent DFS cases/Projects. These are evidence rows, not
641Projects or independent experiments. Technical raw coverage stays641,
T1qualified0, TC1/TC2qualified2each; Commercial raw coverage stays32632and
its exploratory financing milestone remains6Projects. The six main scorable
domain counts remainR22/S9/T0/D5/I20/C6, resource-defined22, strict Development,
full-evidence and formalC1zero. Source snapshots remain100(including44PDFs),
with nine replacement extraction versions and no new original documents.
Selected validated numeric statements increase263→265from the Wolverine row.

AimA reruns the nine existing partial panels, retaining all sample sizes
(20/7/9/5/2/2/5/2/17). In the two-case concentrate-only screen Yangibana ranks
ahead of BrownsRange under all three scenarios and all three methods; this is
a conditional engineering forecast comparison, not a six-domain ranking.
AimB's125panel CSVs, including weight, function, method, leave-out, cohort and
rounding sensitivity, are byte-identical to Phase9. No measurement-error range
was invented. AimC gains queryable semantic/representativeness descriptors,
but no additional independent technical Project or basis for new inference.

All7554entity IDs and original-source hashes remain unchanged. SQLite
quick-check and foreign-key checks pass. Phase5–9 scientific reconstructions
match24/24/31/36/36files respectively. The remaining36identity pairs,
112unconfirmed government relations and Splinter technical gap are unchanged;
this phase does not claim a National Census expansion.

Validation:147Python tests passed locally on the final implementation;
21are Phase10-specific. R analytical invariants passed (Windows locale startup
warnings only). An initial sandbox run failed11legacy temporary-directory tests
with WinError5; the unchanged tests passed with ordinary execution permissions.
The publication scan checked1752text artifacts, and staged source/data/result
bytes were checked against the recorded hashes. Earlier frozen results were
not edited.

Clean Phase10 replay reproduces the technical comparison table byte-for-byte,
all criterion/resource rows, all7554IDs and36point-science files. Five evidence
exports match exactly. Commercial `raw_versions` differs32634versus32632because
the operational store retains two historical metadata versions; scientific
coverage agrees. Full operational observation history is37015versus35996versions,
including unselected extraction/REVIEW history, not additional selected science.

One existing R limitation is now explicit:122of125panel CSV rowsets match the
clean replay. Three `rounding_uncertainty.csv` tables differ in simulated
frequencies because the R random stream is assigned by matrix row position and
clean SQLite insertion order differs. Maximum frequency differences are0.6,
2.0and0.9percentage points for composition, study and global-port panels;
all rank medians and5/95quantiles agree. This is not a measurement-uncertainty
estimate or changed point ranking. The R engine and frozen simulations were
preserved in this minimal technical-integration change; deterministic
entity-keyed random streams remain follow-up work. See
`data/phase10_clean_replay.json`. The canonical Phase9→10comparison still has
all125panel CSVs byte-identical; this is distinct from clean-bootstrap replay.

```sh
au-ree-v2 all --as-of 2026-11-03 --work work/phase5
au-ree-v2 rebuild --as-of 2026-11-03 --snapshot-lock results/phase10-2026-11-03/snapshot_lock.json --work work/technical-replay
python tools/check_replay.py results/phase10-2026-11-03 work/technical-replay/latest.json
python tools/evaluate_documents.py work/technical_benchmark.json
python tools/evaluate_documents.py work/legacy_benchmark.json --phase9
python -m unittest discover -s tests -v
Rscript tests/test_methods.R
```

Measured coverage, replay and validation results are recorded with the frozen
Phase10 results and `data/phase10_research_summary.json`.
