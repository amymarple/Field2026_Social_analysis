# Implementation plan — Phase 3 / Module 7: in-bout approach/avoid (coarse, heading-free, gate-first)

**Date:** 2026-07-12 · **Status:** plan (built + selftested; real-data gate running). Roadmap Phase 3.
Registry: [`configs/behavioral_policy_modules.yaml`](../wiser/configs/behavioral_policy_modules.yaml) module 7.
Prerequisites [1, 4] built (module 3 produces `bouts.csv`). Governed by
[`change_log/2026-07-11-dbv-crosscheck-locomotor.md`](../change_log/2026-07-11-dbv-crosscheck-locomotor.md).

## Why heading-free, and why gate-first

The module-7 spec's literal outcome is "per-step relative bearing toward/away". **DBV falsified reliable
heading at WISER resolution** (pause reorientation inseparable from a jitter null; heading-changepoint
detector 30–77 % false-positive). The spec itself only allows "**coarse approach/avoid at ≥ 1 m**". So
this module measures approach/avoid as a **net distance change over a validated active bout**, NOT an
instantaneous heading — and, per the user's directive and the module-3/6 pattern, runs the **measurement
gate before any model**.

## Definitions

For each validated active bout (module-3 `bouts.csv`, excluding `spans_dropout`/`has_gap`) of a focal,
and each conspecific present at ≥ 1 m at bout start:
- `disp` = ‖focal_end − focal_start‖ (bout displacement); `d0` = ‖focal_start − partner_start‖;
- **`toward`** = (d0 − ‖focal_end − partner_start‖) / disp ∈ [−1, 1] — the fraction of the bout that went
  toward the partner's start position (+1 straight at, −1 straight away). Heading-free.
- Included only if `disp ≥ min_disp_in` (jitter-safe; default 14 in = 2× floor) and `d0 ≥ 1 m` (both
  sides above the ~7 in floor → frame-invariant, resolvable). Partner position is strictly at/before start.

## Measurement gate (BEFORE any model)

- **Support:** ≥ 40 (bout, partner) pairs.
- **Direction-randomized null (RESOLVABLE):** rotate each bout's displacement by a uniform random angle
  about its start; recompute mean `toward`. `|z| ≥ 2` ⇒ a real toward/away bias exists above geometry
  (null mean ≈ 0).
- **Day-shuffle (SOCIAL):** replace each partner's start position with the SAME partner at the same
  clock-hour on a DIFFERENT night; recompute. `|z| ≥ 2` ⇒ the bias is **real-time social**, not
  shared-resource **layout** geometry (both animals use the same sites). This is the decisive control
  and the DBV/module-5 day-shuffle logic.
- **Gate:** RESOLVABLE = support ∧ direction-|z|≥2; SOCIAL = RESOLVABLE ∧ day-shuffle-|z|≥2. The
  approach/avoid **model is fit only if SOCIAL**; else the honest verdict is "coarse directional bias is
  layout, not social" or "no signal above geometry/jitter".

## Files

- `src/approach_avoid.py` — `bout_approach_context`, `direction_null_z`, `day_shuffle_z`,
  `measurement_gate`, `build_model_table` (gated). numpy/pandas.
- `scripts/selftest_approach_avoid.py` — planted approach / avoid / random-direction / sub-floor /
  sub-1 m / SOCIAL-vs-LAYOUT (day-shuffle discrimination). **PASS (8/8).**
- `scripts/build_approach_avoid.py` — real-data: module-3 `bouts.csv` + shared `load_clean_stream`
  fixes → context → gate → (gated) model table + report + manifest.
- Outputs → `outputs/approach_avoid_2026-06-28_to_2026-07-05/` (git-ignored).

## Constraints (must persist)

WITHIN validated active bouts only (not stationary epochs — else crowding-suppressed *initiation* would
confound steering with failure-to-initiate). ≥ 1 m only; jitter-safe displacement; strictly-pre-decision
partner position. **Association, not motivation:** "in-bout approach/avoid tendency", never "chooses to
approach" / "attraction/aversion". Group-level; pair-resolved (dyadic) only if module 13 passes. Frame
UNVERIFIED (topology + coarse distance only). Whole nights are the outer inference blocks.

## Verification

selftest 8/8; real-data gate (this run); adversarial measurement-bug review; then change_log +
ANALYSIS_STATUS + registry module 7. If the gate is a NO-GO for social, that is the documented result
(no model), exactly as gate-first intends.
