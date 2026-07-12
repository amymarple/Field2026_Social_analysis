# Implementation plan — Phase 1 / Module 3: unified locomotor state machine + bout-initiation hazard

**Date:** 2026-07-11 · **Status:** plan (coding follows; no biological promotion here).
**Roadmap:** [`implementation_plan/behavioral_policy_roadmap.md`](behavioral_policy_roadmap.md) Phase 1 ·
**registry:** [`configs/behavioral_policy_modules.yaml`](../wiser/configs/behavioral_policy_modules.yaml) modules 1–4 ·
**map:** [`docs/behavioral_policy_map.md`](../docs/behavioral_policy_map.md).

## What this builds and why

The built model is the **exit side** of one loop: *site-residence termination* (leaving hazard,
module 5). Module 3 is its **entry-side twin**: given the animal is **settled at rest in a named ROI**,
what is the hazard of **initiating a locomotor bout**? Building it also forces the **unified locomotor
state machine** (modules 1–2 substrate + a movement hysteresis), which repairs the scope gap — we model
*when residence ends* but not *when the resting animal starts moving*, nor the difference between the two.

The organizing framework stays the **hierarchical semi-Markov state machine**. This is NOT the social
graph (a late-Phase-5 challenger). No IRL, no reward inference.

## The four distinctions (measurement gate — each operationalized AND selftested)

1. **movement initiation ≠ ROI departure.** A bout onset need not relocate the animal. Diagnostic:
   cross-tab onsets vs named-ROI departures; expect onsets ≫ departures.
2. **activity-in-place ≠ leaving.** Each bout is labelled `in_place` (start rest-ROI == settle ROI) vs
   `relocating` (a different named ROI). A bout can occur without an ROI transition.
3. **brief pause ≠ settlement.** A short stationary blip inside a bout (< movement exit debounce) must
   NOT split the bout or create a rest episode; only a sustained stop inside an ROI is settlement.
4. **entry ≠ settled (arrival ≠ settled).** Entering a named ROI while still moving is `local_active`,
   not `rest`; rest requires the ROI-state AND the stationary-state both sustained.

## State machine (jitter-tolerant, reuses the module-5 substrate)

Per animal-night, on the **clean valid stream** (speed above the ~7 in jitter floor; gaps 'unknown'):

- **ROI substrate = module 5's exact output.** Call `semimarkov_decisions.hysteretic_visits(...)` and
  stamp each 5 s bin with its covering named visit's ROI, else `open`. Identical, flicker-merged
  segmentation — no divergence, no refactor of module 5.
- **Movement machine (new).** Per bin: `frac_moving` = fraction of the bin's fixes with
  `speed_inps_smooth > MOVING_THR_INPS` (12 in/s, the jitter ceiling). Evidence MOVING (≥ near_frac) /
  STATIONARY (≤ far_frac) / UNCERTAIN (else) / empty→NaN; debounce with the SAME
  `wiser_analysis_utils._hysteresis_state` (enter ACTIVE after `move_enter_s`, exit after `move_exit_s`;
  UNCERTAIN/empty hold). `move_exit_s` is the distinction-3 guard (a pause shorter than it holds ACTIVE).
- **Unified per-bin state** (∈ {`rest`,`local_active`,`transit`,`pause`,`unknown`}):
  `unknown` if empty/gap; else `local_active`/`transit` if ACTIVE (in-ROI / open); else `rest`/`pause`
  if STATIONARY (in-ROI / open). `rest` = settled (module 2). Episodes = contiguous same-state runs.
- **Bouts** = contiguous ACTIVE runs (module-4 substrate); labelled `in_place`/`relocating`.

## Bout-initiation hazard table (module 3 estimand — the entry-side twin of `build_leave_table`)

At-risk unit = each `epoch_s` slice of a **rest episode** (settled in a named ROI). One row per epoch:
- `initiated` = 1 only on the terminal epoch of a rest episode ended by a **bout onset**; 0 otherwise.
- Right-censored when the episode ends by gap/unknown/nightend; **epochs spanning a gap are dropped**
  (unknown, never an onset); **below-plane dropout ROIs (refuge_4 burrow nights) excluded entirely** —
  same discipline as `build_leave_table` / `em.is_dropout`.
- Covariates: `rest_elapsed_s` (mandatory dwell basis $f(\tau)$), ROI + resource type, `clock_hour`,
  regime (wet/fireworks/truncated/burrow), weather (attached by decision time), and **strictly
  pre-decision jitter-safe group-social** (`n_within_1m`, `mean_others_dist_in`) via the existing
  `add_pre_decision_social` (backward `merge_asof`, `allow_exact_matches=False`).

Reuses `choice_models` unchanged: `lono_bits`/`social_increment`/`personalization_gain`/
`conditional_permutation_null`/`time_shift_social_null`/`day_shuffle_social_null` with
`y_col="initiated"`, `dwell_col="rest_elapsed_s"`.

## Gates (Phase-1 four-gate framework)

- **Measurement:** onset = speed-onset above jitter (a **LOWER bound**; in-nest sub-jitter stirring &
  the ~18:00 arousal invisible → never "wake"). The four distinctions are selftested (planted
  bout-vs-flicker, pause-vs-settlement, arrival-vs-settled, onset-vs-departure) + dropout/gap discipline.
- **Support:** onsets & rest episodes per animal-night; all four states populated (driver A0-analog).
- **Predictive:** held-out-night initiation hazard beats marginal + circular-shift + conditional-
  permutation nulls (bits/decision, whole-night blocks); social increment gated by time-shift + day-shuffle.
- **Interpretation:** "locomotor-bout initiation hazard / movement onset", not "decided to forage",
  not "wake"; states are a proxy, not an ethogram.

## Files

**New:**
- `src/locomotor_states.py` (numpy/pandas + `wiser_analysis_utils`, `semimarkov_decisions`): the state
  machine, bout table + `in_place`/`relocating`, the rest-episode + initiation at-risk table, the
  four-distinction diagnostics, strictly-pre-decision social attach (reuses `add_pre_decision_social`).
- `scripts/selftest_locomotor_states.py` — offline planted scenarios (four distinctions + dropout/gap +
  a genuine predictable-onset sanity), exit-coded PASS/FAIL. No DB.
- `scripts/build_locomotor_states.py` — load→clean→state machine→initiation table + bouts + diagnostics
  → CSVs + manifest (shares the module-5 loader via an extracted `load_clean_stream`).
- `scripts/analyze_locomotor_initiation.py` — held-out initiation-hazard ladder (marginal → state →
  +weather → +social) + nulls + effect curve + support audit → CSVs + report (formula+text definitions).

**Touched (low-risk):** `scripts/build_decision_tables.py` — extract the load/clean block into
`load_clean_stream()` and have `main()` call it (behaviour-preserving; guarded by a 1-night module-5
smoke + the module-5 selftest). `ANALYSIS_STATUS.md`, `configs/behavioral_policy_modules.yaml`
(modules 1–4 status), the roadmap status line, a `change_log/2026-07-11-locomotor-bout-initiation.md`.

## Verification

1. `selftest_policy_identifiability.py` (module-5 regression — smd untouched) → PASS.
2. `selftest_locomotor_states.py` (the four distinctions + dropout/gap + predictable-onset) → PASS.
3. Module-5 1-night smoke after the loader extraction → identical leave/dest counts.
4. Real-data build (8 nights 06-28→07-05, matching module 5's window) + the initiation ladder.
5. Adversarial measurement-bug review (leakage/look-ahead, jitter selection-on-same-variable,
   dropout-as-event, train/test design misalignment) before promoting anything past ⚠️ candidate.

## Scope guard (travels with every result)

This is the **locomotor-bout initiation** module (module 3) — the entry-side twin of the built leaving
hazard, one module of a 14-module hierarchical agent. Onset is a **lower bound**; the frame is
UNVERIFIED (topology + coarse distances only); rest is a low-speed proxy (not sleep). Not "the policy",
not "search", not "wake", not "decided to forage".
