# Phase 11 frozen research outputs

Evidence cutoff: **2026-11-03**. Research release date: **2026-11-04 Asia/Taipei**.

See [the report](../../docs/phase11-deterministic-research.md), [measured differences](../../data/phase11_research_summary.json), [reproducibility receipt](../../data/phase11_reproducibility.json), and [run summary](summary.json).

```sh
au-ree-v2 rebuild --as-of 2026-11-03 --snapshot-lock results/phase11-2026-11-04/snapshot_lock.json --work work/phase11-replay
python tools/check_phase11.py results/phase11-2026-11-04 work/phase11-replay/latest.json --reference
```

201 generated artifacts are SHA-256 bound by summary.json. The code content SHA binds the Python/R implementation before publication; the commit field records the parent revision at execution. No original, Phase 5–10 frozen output, source ID or Project ID was overwritten.

The logical database JSON preserves operational version history; it is an immutable export, not a second production database. Independent clean bootstrap may omit unselected historical extraction versions. The replay contract covers selected evidence and all scientific panel outputs, including Monte Carlo frequencies, rather than all database-history bytes.

All panels are exploratory. Formal C1, strict Development and full-evidence cohorts remain zero. Technical model forecasts, leach test rows, offtake and conditional financing retain their individual scope and legal/scientific meaning.

For two independent rebuilds in the same recorded environment, omit --reference: all panel fields, including scores and Monte Carlo frequencies, must match exactly. The cross-platform reference retains the existing1e-12static-point rule and reports every difference; ranks and stochastic statistics remain exact. See the report for nine measured Windows/Linux last-bit differences.
