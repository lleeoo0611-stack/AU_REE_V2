# Phase 20 — six-domain evidence expansion

Research cutoff: 2026-11-05. Configuration: `research-v6-current-disclosure-evidence`. Technical retains the Phase 19 `technical-disclosure-transparency-v1` definition.

The complete six-domain sample increased from **1 to 3 groups**: Jupiter within Brothers, Goschen Area 1 and Koppamurra. Goschen's four magnet oxides and TREO use the same Area 1 resource statement and THM material basis; the shared material factor cancels in the ratio (22.5%). Koppamurra's source explicitly describes a project funding plan and ongoing discussions: its code is **PLANNED_OR_NONBINDING**, not secured funding. No new external original was acquired in Phase 20.

The existing main pipeline now refreshes non-Technical values from the current selected evidence instead of the Phase 19 score snapshot. The new six-domain cohort requires all six scored criteria, without the historical overall-recovery gate. Historical locks preserve their earlier semantics. One production SQLite database and the existing Python/R engines remain in use.

## Results and limits

- [Evaluation and code-content identity](evaluation.json): 292 Python tests passed; [test log](tests.log). Two same-store executions matched ten key scientific files exactly. The receipt records pre-upload validation, including the then-uncommitted Git state; upload does not rewrite that history.
- [Release validation](release_validation.json): a fresh reconstruction with R matched eight frozen matrix/ranking/criteria/weight files under the existing reference rule; five R invariant families passed. The pre-upload publication scan passed 3,772 text artifacts and all five new staged immutable snapshot hashes were verified. This receipt preserves its pre-push/CI-pending state; current GitHub status is reported on the PR.
- [31-group matrix](disclosure_composite_matrix.csv), [six-domain point matrix](six_domain/matrix.csv), [three-method rankings](six_domain/ranking.csv), [weight sensitivity](six_domain/weight_uncertainty.csv), [with/without-transparency ranking](six_domain_disclosure/ranking.csv), and [unknown-domain/weight envelopes](disclosure_composite_ranking.csv).
- [Evidence recovery priority](six_domain_gap_priority.csv): 28 groups still lack one or more point domains. Cummins Range and Nolans each lack Strategic S1; Dubbo lacks a point Technical disclosure score. Priority is based on missing domains, not a performance ranking.
- [Value-level provenance](value_trace.csv) and [current baseline](disclosure_baseline.json) retain source scope, dates, transformations and scoring anchors.
- Selective cited-page verification took 3.62 seconds versus 16.54 seconds in one same-corpus experiment (4.56×), with all 217 item judgments identical. This is not a full-pipeline speedup estimate.

Three complete groups do not support national inference, independent-project counts or Aim C causal conclusions. Technical measures disclosure transparency, not feasibility. Commercial covers disclosed financing milestones, not the full commercial/ESG scope of the original proposal. Unknowns are not imputed. Source rounding propagation in the disclosure-specific interchange remains incomplete; the main six-domain matrix retains its source rounding bounds. Strategic rankings differ by MCDA method. Formal C1/C2 approval remains unchanged.

## Reconstruction

From the repository root, with the package and R installed:

```sh
au-ree-v2 rebuild --as-of 2026-11-05 --snapshot-lock results/phase20-2026-11-05/snapshot_lock.json --work work/phase20-replay
python tools/check_replay.py results/phase20-2026-11-05 work/phase20-replay/latest.json
```

This independent validation workspace reconstructs committed snapshots and the archived claims contract; it is not a second production database. To update the existing production store:

```sh
au-ree-v2 all --as-of 2026-11-05 --work work/phase5
```

On Windows, supply `--rscript "C:/Program Files/R/R-4.5.2/bin/Rscript.exe"` if necessary. `--skip-r` explicitly skips ranking. The `disclosure` command uses the existing production store; current configurations refresh the other domains, while the frozen Phase 19 configuration retains its frozen baseline.

Historical [Phase 19 results](../phase19-2026-11-05/REPORT.md) and their one-group six-domain count remain unchanged. The GitHub branch name `feat/phase16-technical-model` is historical; the current research phase is 20. No separate Phase 17/18 release is asserted.
