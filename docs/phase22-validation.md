# Phase 22 prospective validation contract

Frozen before Phase 22 classifier, pairing, extraction or sampling changes.
Baseline: bb7da099941eb222c3baa2537e34d137fe3fb208; cutoff 2026-11-05.
The Phase 21 72-row set remains used regression data, not an independent test.

## Units, sampling and annotation

Candidate unit: government native record and its retained source fields. Group
all versions of a native entity together; exclude native IDs in the old set.
Use seed 20261106, SHA ordering within state/source/lexical sampling strata
(explicit REE/element, mineral, scandium, unrelated). Lexical strata only select
records, not their reference labels. Retain frame sizes and inclusion fractions;
purposeful difficult records are reported separately, without population weights.
Annotate raw fields without calling the classifier or inspecting predictions.
Keep source SHA, locator, literal fields and a rationale. Freeze labels before
evaluation. Do not use test results to tune Phase 22 rules. Any subsequent tuning
converts this set to used validation data and requires a fresh future holdout.

Pairing unit: an evidenced relation, not all possible pairs. Include explicit
native-ID relations, renamed/same-name/different-location and nested-scope
examples. Bind truth to the particular endpoints and relation type. Report
candidate recall separately from confirmed identity decisions and pending cases.
Binding unit: a reported table cell with value, unit, REO basis, effective date,
feed/material, statement category and resource/study boundary. An Exploration
Target, Mineral Resource and Ore Reserve are different categories.

Labels are source-reviewed by the executing agent; no independent human or
second-agent review has been obtained. Prospective freezing reduces reuse bias
but does not constitute a blind independent gold standard. Uncertain reference
labels are retained as uncertain and excluded from binary denominators.

## Predeclared acceptance and reporting

- No automatic Project promotion from names, distance, ownership or tenements.
- Candidate performance: report TP/FP/FN/TN, precision/recall/F1 and role errors
  by stratum and source; require no regression versus the fixed baseline on the
  same held sources. No claim of national recall or statistically established
  superiority from this bounded sample.
- Pair generation: report recall over explicitly evidenced reference relations;
  no unsupported auto-merge is acceptable. Report false merges/splits/relations
  and unresolved fraction only where reference truth supports the denominator.
- Cell binding: zero wrongly admitted values in the reviewed source-cell set;
  a missing or conflicting binding must remain excluded. Report each dimension
  and errors separately, not synthetic overall identity accuracy.
- Preserve all original Project IDs, seven-item disclosure denominator, unknown
  states, fixed utility scales, weights, C1 policy, seed and 1,000 draws.
- Verify Phase 21 point results and PROMETHEE draw distributions before accepting
  the three-method expansion. New methods must consume identical draws without
  advancing the legacy RNG stream.
- Final clean/current and cumulative/current scientific views must agree;
  all-history audit outputs may differ. No deletion of history to make them equal.

No independent recoding is claimed for a repeat review by this same agent.
High-impact judgments are checked against original pages and disagreements kept;
formal coding changes require actual evidence, not hypothetical item flips.
