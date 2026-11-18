# Automated build: validated strict pipeline, partial source availability

Base: `b5e2a73438e2f3aa9f4adc3ab0f6ff0f898f0fca` (Phase 22). Review authority: `980bedbcc250e720e1eab9c734032b5df72c3c39:config/asx_source_reviews.json`, read with `git show`. Branch: `feat/automated-build-claims-20261113`. No experimental merge or push to the formal development branch. Corrected live build completed successfully on 2026-11-15, with explicitly partial source availability.

## T0: stable identities

All 63 added IDs reproduce exactly; 99-row crosswalk in `docs/registry-crosswalk.md`. Original 36 entities retained unchanged, with only reviewed observations appended. Of the 63 identities, 59 have an allowed source review and enter claims; four historical Charley identities remain documented but are deferred because their identity originals are not in the 208 authorized source reviews. No dangling source keys were invented. See `project-migration.csv`.

The Yttria/Mt Stirling requested same-project-renamed relation is not asserted: the cited approved record describes an issuer rename, explicitly not project identity equivalence. Existing entities and source-supported containment relation remain unchanged.

## T1: public source registry

208 reviews reference 112 unique original SHA-256 values. 17 reuse an existing registered key; 95 sources added. 82 selected URLs are on ASX hosts. Non-ASX preference replacements: zero, because no reviewed same-SHA group contains both ASX and non-ASX alternatives. Sources have no imported path/asset_set fields. See `source-migration.csv`.

The Splinter WAMEX ReportDetails URL is preserved exactly; it is not silently replaced with a discovered PDF. Its source remains unverified pending the approved government-query route.

## T2: declarations, not accepted measurements

169 of 335 observations migrated with physical page, at least two existing markers, SHA, scope, statement, original value/unit/basis, date metadata and original reviewed cell binding. All values require source/page reverification at build. 16 Y2O3 observations use the existing equivalent `reported_y2o3_ppm` vocabulary without changing their quantities.

166 observations excluded: 157 have no equivalent existing variable for individual La/Ce/Sm/Eu/Gd/Ho/Er/Tm/Yb/Lu; 9 lack the required page/marker contract. Every observation is listed in `observation-migration.csv`. The total-lanthanide variable is not misused for individual elements.

Selected section boxes are retained as `ocr_clip` coordinates in existing locator text; existing extraction machinery must perform the selected-page/region verification in the strict build. Eight Wolverine declarations have no explicit category in the review and retain null category rather than invent one; resource variables must remain review-gated if that category is required.

31 deposit descriptions on new entities are copied from source-reviewed attributes using the same identity source; original entity attributes remain untouched. Their source/page/marker binding is in identity_locator, with per-item accounting in `deposit-migration.csv`. No coordinates were inferred; no coordinate attributes exist in the allowed review input.

48 researcher decisions are individually documented in `rule-migration.csv`, not silently installed into a new schema. Stage/coordinate rules remain out of this round. Splinter Ce conversion and Circle Valley NdPr combination are cell-scoped exceptions, not authority for general conversion; no new transform was run or derived value invented.

## Approved fetch policy and implementation

The owner has allowed an opt-in strict path in acquisition.py/CLI and `fetch_policy: strict` in existing evidence_policy, work-only downloads, and fallback only to committed snapshots matching the declared SHA exactly. Existing non-strict and frozen rebuild behavior must remain unchanged.

`index-host-review.md` inventories government APIs, proposed government directory exceptions, forbidden commercial/ASX indexes and exact-document hosts. The owner approved this classification and its government exceptions. The opt-in strict acquisition/CLI path is implemented; the corrected live acquisition/build has completed. The owner also approved exactly one discovery.py guard-line exception: missing path/files produce SOURCE_NOT_ACQUIRED receipts rather than raising KeyError. Existing-path corruption/SHA behavior is unchanged. Final source diff is 329 added/deleted lines, below the 500-line cap.

## Verification

Final code: 358 unittest tests and 151 subtests pass with zero failures/errors; the R analytical regression script exits 0. See unittest.xml, R-tests.xml and R-tests.log. Phase 20, 21 and 22 actual frozen rebuilds and check_replay were rerun against final code and all exited 0; see frozen-replay.xml. The registered-but-unacquired discovery regression and existing-path byte-equivalence check pass. The corrected live command exited 0 and completed R analysis without skipping it. No original PDF or frozen result was modified.

## Final result and limitations

The requested `au-ree-v2 all --refresh --as-of 2026-11-13 --work work/clean` completed with exit 0 in run `20261115T073343-03d348a3`. The cutoff remains 2026-11-13; retrieval occurred on 2026-11-15 and is not backdated. `formal-export/` contains 211 byte-verified existing-format output files, excluding original downloads, native/page caches, SQLite and PDFs. `formal-export/resources.csv` is the formal resource table; `census.csv`, `resolved_evidence.csv`, `review_queue.csv` and `summary.json` preserve its wider context.

169 migrated declarations reconcile exactly: 145 SOURCE_NOT_ACQUIRED; 24 AUTO_VALIDATED with empty issues. Of the 24, downstream resolution accepts 18 as VALID_RAW_EVIDENCE and excludes six Salazar values as SOURCE_AFTER_CUTOFF. All nine new page artifacts have correct actual byte hashes. The 19 resource-table rows are not 19 additions: only one row references migrated declarations (three observations). There is no claim that all sources or the experimental coverage target were obtained.

185 acquisition/query receipts: 24 FETCHED_SHA_VERIFIED, 23 SNAPSHOT_FALLBACK_SAME_SHA, 117 UNAVAILABLE, 8 FETCHED_UNBOUND_GOVERNMENT_OR_SOURCE, 5 COMMITTED_MANAGED_SAME_SHA, 3 SOURCE_NOT_ACQUIRED, 2 PARSED, 2 CONFLICTING_DECLARED_SOURCE_SHA, and 1 NO_FIXED_QUERY_NOT_EXPANDED. These are transport/selection statuses, not scientific acceptance. There are 133 DNS failure reasons, consistent with the connection interruption during this run; unavailable evidence is not filled from prior work caches. See acquisition_report.csv and acquisition_hosts.md for per-host HTTP evidence and separate issuer/IR versus aggregator counts.

The final guard audit quarantines official transcriptions without reliable parent-PDF SHA binding, propagates SHA constraints across exact-URL aliases, and prohibits fallback after candidate mismatch or conflicting declared SHA. Final src diff: 329 added/deleted lines, including exactly one discovery.py guard replacement. Experiment reference only: 73.29% (2159/2946); this is not a build/config input or a coverage result for this run. Delivery is limited to the feature branch; no merge or current publication is performed.


The initial live trial was stopped before completion after a final audit identified the registered Fingerboards project landing URL. Strict now rejects that exact landing URL without a request or fallback (SOURCE_NOT_ACQUIRED / INDEX_LANDING_DISABLED); specific LSE articles and fixed-ID Weblink document delivery remain eligible. The subsequent failed live run started 2026-11-13 16:11 UTC+08 in a new per-build cache, without reading earlier work caches.

Formal Phase 22 has resource, technical, census and review exports rather than the experimental 51-column summary exporter. No comparable 51-column coverage percentage is fabricated from experimental result CSVs. Acquisition success, validated claims and scientific acceptance must be reported separately.

## Windows live-run diagnostics (2026-11-15)

The 2026-11-13 live run completed acquisition but exited 1 during final output hashing. A populated SQLite WAL transaction reproduced PermissionError on canonical.sqlite-shm. Strict databases now live under work/databases/<run_id>, outside the deliverable output tree; historical non-strict storage is unchanged. Clean-checkout regression verifies the private database exists but is absent from output hashes.

A second byte-level issue was confirmed in generated page artifacts: Windows text newline translation changed LF payload bytes after SHA calculation. Runtime page artifacts now use write_bytes; regression verifies the actual file SHA and LF bytes. The failed run contained 145 migrated declarations with SOURCE_NOT_ACQUIRED and 24 observations rejected for EXTRACTION_READ_FAILED. These are diagnostic results, not accepted new evidence.

A fresh corrected all --refresh validation began 2026-11-15 14:46 UTC+08 with the requested as-of 2026-11-13. It completed successfully, does not read previous raw work caches, and correctly retains partial-source/cutoff limitations. Prior failed acquisition reports and logs are preserved locally for diagnosis.
