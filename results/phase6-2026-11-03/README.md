# Phase 6 national database release

Cutoff: 2026-11-03. Run: 20261103T083625-339a07fd.

31 canonical PROJECT registry groups; 19 comparable source-defined resource scopes; 122,697 current government source records from seven states and territories, locally filtered to704 REE-related native records. These counts are not interchangeable or a certified count of independent Australian REE projects.

The previous31 unresolved pairs now have28 remaining;12 new deposit pairs produce40 total. Of the previoussix technical gaps, Splinter remains unfilled; newly discovered Wudinna/Kalkaroo add two primary-document gaps, makingthree total. Fingerboards remains process-proposal evidence only; Lyons basis remains unresolved; Brothers is shared parent context.

Panels:19/7/8/4/2/17. Scorable coverage:R19/S8/T0/D4/I19/C0. Strict Development, full-evidence and formalC1 remainzero.

See [source details and interpretation](../../docs/phase6-national-database.md), government_source_coverage.csv, government_native_entities.csv, entity_hierarchy.csv, database_domain_coverage.csv, resource_statement_quality.csv and comparison_* files. Keep original/raw source evidence, scored criteria and cohort definitions distinct.

Two local originals have credential-bearing references. Their bytes and ledger entries remain unchanged locally; the selected lock uses explicitly labelled public derivatives with originalSHA256 and redaction metadata. Public replay reconstructs scientific data, not withheld credential strings. logical_database.json is a sanitized historical export; the canonical SQLite history stays local. No private raw captures are included in Git.

```sh
au-ree-v2 rebuild --as-of 2026-11-03 --snapshot-lock results/phase6-2026-11-03/snapshot_lock.json --compare-to results/phase5-2026-11-03 --work work/phase6-replay
```

Validation:69 Python tests passed; R analytical invariants passed. GitHub Actions results are linked from PR#1. Source content hash: 5730ed2363600715e105fd4ccc96654e90266f86ce6f976f029ce3d2dea5b9fd.
