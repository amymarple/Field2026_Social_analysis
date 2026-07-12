# aggregate/ — cross-cohort layer (structurally present, empty for now)

This layer holds analyses that combine **more than one cohort** (e.g. 2026a vs 2026b comparisons, pooled
effect sizes, cross-season stability). It is intentionally empty: there is only one cohort (`2026a`) so far,
and single-cohort results belong under `results/2026a/<direction>/`, not here.

When a second cohort exists, add cross-cohort scripts + outputs here without touching the per-cohort tree:
- cross-cohort code is cohort-agnostic and reads from `results/*/<direction>/` via `common/output_paths.py`;
- cross-cohort outputs are keyed by the **set** of cohorts they span, e.g. `aggregate/2026a+2026b/<direction>/`;
- do not fold a single-cohort result up into `aggregate/`.

No cross-cohort claims may be made until this layer is populated and verified.
