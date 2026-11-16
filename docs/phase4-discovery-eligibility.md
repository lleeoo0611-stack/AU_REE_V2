# Source discovery and eligibility compatibility

The existing CLI now includes `au-ree-v2 discover`. Four official/issuer HTML seeds are snapshotted before parsing allowlisted HTTPS PDF links. Content hashes deduplicate documents; failed pages, downloads and PDF parsing are local outcomes. Transient HTTP/network errors retry three times. Static HTML only is supported: this is not a complete ASX feed, recursive crawler or national government service discovery. A page with no allowed PDF links is not proof there are no reports.

A live run discovered and saved ASM Annual Financial Report 2026 (43 physical pages), document SHA-256 `4c1bc8edc6d26b0c5eaf16e385c0e95534c071092624e9d14c338d2783002eb7`. The link title states 25 September 2026, but publication_date remains NULL pending document validation. Some body text has font encoding problems. No numerical observations, funding availability or resource totals were inferred. New pages and PDF snapshots enter the same source manifest and SQLite sources table on the next normal run; discovery creates no Projects or alternate database.

## Gap reconstruction

Every normal analysis rebuilds `unresolved_identity_pairs.csv` (38 pairs, native entity IDs, source hashes, name/state, distance and actual reason), and `primary_scope_gaps.csv` (18 canonical groups, aliases/names, existing unverified resource claims and needed evidence). The 38 are 11 location conflicts and 27 technical-identity evidence gaps. There are no new accepted equivalences in this increment. The 18 indicate absent controlled primary scope in this corpus, not proof of absent public documents.

## C1 compatibility proposal and effect

`config/eligibility_compatibility.json` preserves the inspected prior `C0_F1F2_COHORT_C1C2_V1_20261031` policy verbatim inside the compatibility record. That policy requires ID, ROLE, WINDOW, JORC, PANEL and GIS_RELEASE, signed source evidence, pre-FID active Australian projects, and says the 12/9-criterion panel was not selected. V2 coverage panels do not establish these gates. The earlier PRE_FID_SCOPING_DFS_GATE_V1 coverage policy (70 percent, four domains) also cannot replace the six independent gates.

The compatibility approach keeps V2 panels exploratory and generates versioned per-group/per-gate `NOT_EVALUATED_NO_IMPORTED_GATE_EVIDENCE` records; it does not create another approval procedure, fabricate FAIL/PASS, import obsolete cohort counts, or modify the accepted formal definition. `eligibility_cohorts.csv` separately reports registry, resource-defined, Development, full-evidence and exploratory membership. Formal C1 evaluated/admitted counts are zero **because the gate evidence and fixed panel have not been imported**, not because all Projects failed. A future source-bound import of the correct cutoff-specific ledger and selected panel is needed before formal C1 output. Automatic evidence processing remains independent of formal signature claims.

## Research effect and remaining work

No new scorable resource/recovery/GIS observations were admitted. Resource-defined n=7, strict Development n=0 and full-evidence n=0 remain unchanged. Existing panels (7/5/3/3/2/20) are rerun by the same Python/R pipeline; discovery alone does not change their ranks. Aim A remains partial-panel evaluation, Aim B retains distinct preference/rounding/measurement/cohort treatments, and Aim C remains descriptive. National physical-entity certification, state raw-source acquisition, pagination/ASX feed discovery, reliable PDF extraction, dated finance reaffirmation, and six-domain evidence expansion remain unfinished.

Run `au-ree-v2 discover`, then `au-ree-v2 all --as-of 2026-11-03 --work work/phase4`. Exact analysis replay uses the output snapshot_lock.json; discovery is deliberately a separate explicit network operation and is never executed by offline replay.
