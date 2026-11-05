# Phase16 reproducible research release

Frozen canonical run: `20261104T133335-142044b9`.

Research cutoff 2026-11-03; explicit retrospective acquisition through 2026-11-04; upstream formal cutoff 2026-10-29. `config/evidence_policy.json` is frozen within `configuration.json`.

```powershell
$env:PYTHONPATH='src;.;tools'
python -m au_ree_v2 rebuild --as-of 2026-11-03 --snapshot-lock results/phase16-2026-11-04/snapshot_lock.json --work work/phase16-replay --rscript 'C:/Program Files/R/R-4.5.2/bin/Rscript.exe'
python tools/check_phase16.py results/phase16-2026-11-04 work/phase16-replay/latest.json --reference
python tools/evaluate_phase16.py work/phase16-evaluation.json
python -m unittest discover -s tests -v
Rscript tests/test_methods.R
```

To repeat live centralized-source acquisition, use `python -m au_ree_v2 acquire --centralized --as-of 2026-11-03`. It records current transport/access outcomes and preserves new raw versions; it is separate from the frozen historical replay above. A newer product is not backdated into the old cutoff.

For two independent reconstructions use two previously absent `--work` directories and compare their `latest.json` with `check_phase16.py` without `--reference`. Every analysis output is regenerated. Source extraction artifacts are explicitly frozen, SHA-verified inputs, not reused MCDA outputs.

- `technical_observations.csv`: the unified view of cells, study parameters and text; physical meaning, applicability and Project extrapolation remain separate.
- `technical_project_profiles.csv` / `technical_burden_evidence.csv`: source-scoped T-A/T-B interpretations, Unknown/conflict, rule IDs and evidence links. Empty Project score is intentional.
- `technical_comparison_groups.csv`: numerical source-case groups; these are not a national score or independent experiment inventory.
- `technical_model_decision.json`: executed partial-MCDA plus technical-profile strategy; no new ordinal mapping or weighting.
- `minedex_resource_batch.csv` / `.json`: original WA batch fields, native-ID relations and missing estimate-date / basis limitations. Not original JORC evidence.
- The existing `technical_cells`, `technical_derived`, flow, grade/recovery and SVG exports retain source-specific empirical results; `R/technical_plots.R` redraws the figures.

Canonical evidence history is losslessly archived as `logical_database.json.gz` to stay below the publisher's single-file size limit. Its raw JSON SHA and sizes are in `summary.json`; the main CLI still writes native JSON in `work`. This archive includes prior inactive versions held by the canonical database. It is not the selected-state clean logical database, nor a complete SQLite binary backup including historical derived runs. The latter distinction is explicit in verification receipts. Decompress with Python's standard `gzip` module when needed.

Historical Phase5–15 frozen releases are unchanged. Code content SHA for this release: `1a09381b297a0be7ec94045e8851ab6cf3f34475f0d0c5dccd7ebe2fb298cc89`; the commit field records the Phase15 development parent. See [research interpretation](../../docs/phase16-technical-model.md) and [quantified receipt](../../data/phase16_research_summary.json).
