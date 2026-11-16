# Frozen real-source pilot, cutoff 2026-11-02

This is a two-scope, two-criterion experiment, not a national project ranking or a complete
development-potential assessment. All numerical inputs trace through value_trace.csv and
snapshot_lock.json to the managed originals. provenance.json records the actual code content hash,
configuration, source set, logical data hash and output checksums.

| Selected resource scope | Effective date | Reported contained TREO |
| --- | --- | --- |
| Mt Weld Mineral Resource | 2024-06-30 | 4,389 kt |
| Browns Range, Wolverine only | 2025-01-15 | 70.5 kt |

The Wolverine comparison excludes separate Pilot Plant stockpiles and other Browns Range deposits.
Neither quantity is recoverable product. The cutoff constrains source availability and does not
make the resource effective dates equal or establish these as the latest statements for either issuer.

The pilot scores resource inventory and official GA port proximity using frozen physical anchors.
Mt Weld ranks first in the three baseline scenarios under PROMETHEE II, SAW and fixed-ideal TOPSIS.
Neither scope Pareto-dominates the other on the two active criteria. In the development-assumption
scenario, 1,000 weight-only PROMETHEE draws rank Mt Weld first in 58.2% and Wolverine first in 41.8%.
These are frequencies under a specified Dirichlet preference experiment, not confidence intervals
for real-world success. Resource- and strategic-assumption scenarios favor Mt Weld in all 1,000 draws.
Strategic composition and actual development readiness are absent from this pilot; scenario names
refer to the parent assumed domain weights restricted to the two available domains.

Source-rounding-only experiments are separate. Measurement uncertainty is not quantified.
Top-3 and top-5 frequencies are left blank because the sample has only two alternatives.
Method-correlation statistics and delete-one-project ranks are not estimable at this sample size.
The six-domain cohort and external Aim C inference remain incomplete. Deposit type must not be
interpreted as a causal driver from two selected cases.

Regenerate all outputs from repository root with:

```sh
au-ree-v2 rebuild --as-of 2026-11-02 --snapshot-lock results/pilot-2026-11-02/snapshot_lock.json --work work/pilot-replay
```
