# Phase 15 source-bound technical research

Frozen from canonical CLI run `20261104T100827-bb0d2956`.

Research cutoff 2026-11-03; retrospective acquisition through 2026-11-04; formal upstream cutoff 2026-10-29.

```powershell
$env:PYTHONPATH='src;.'
python -m au_ree_v2 rebuild --as-of 2026-11-03 --snapshot-lock results/phase15-2026-11-04/snapshot_lock.json --work work/phase15-replay --rscript 'C:/Program Files/R/R-4.5.2/bin/Rscript.exe'
python tools/check_phase15.py results/phase15-2026-11-04 work/phase15-replay/latest.json --reference
```

`technical_cells.csv` is a source-bound transcript, including missing tokens and held anomalies. `technical_derived.csv` contains conditional calculations, not independent measurements. The SVGs redraw from these CSVs through `R/technical_plots.R`; no global technical score is adopted. The original `REPORT.md` describes the unchanged general MCDA panels; see `docs/phase15-source-bound-technical.md` for the new empirical interpretation.

The historical Git field records development parent e97272b. Code content SHA is `397bbfeee4af8e9a842da2b45a884e521f206cf95ad982829eab1915182e320f`, verified against the final source files. No prior frozen results were rewritten.
