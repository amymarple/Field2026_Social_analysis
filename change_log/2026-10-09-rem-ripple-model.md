# Ripples in the REM-entry model: no scheduling information beyond the NREM counter; a transition-local drop (2026-10-09)

Plan (pre-registered; Amendment 1 = the model owner's reply, Amendment 2 = the artifact checks, both written before they
ran): [implementation_plan/2026-10-09-rem-ripple-model.md](../implementation_plan/2026-10-09-rem-ripple-model.md).

The user asked to add the NREM ripple rate to the REM prediction (counting) model as a candidate predictor, not as a nap or
REM criterion, and to test held-out gain with only pre-prediction information. The question behind it: is "ripple-rich,
REM-poor" (naps, early main sleep) a coincidence of shared drivers, or a link? The model and its rules came from the owner
session "daynight sleep explore".

## What changed

- **New `ephys/rem_ripple_model.py`**, with commands:
  - `run`: T1 / T2 / T3 + the reproduction of Step B;
  - `checks`: Amendment 2, K1–K6;
  - `posthoc`: where the gain sits;
  - `report`;
  - `--selftest`, 6 checks, among them: the ripple counter with unit events equals P_tw600_k0 exactly; the windows exclude
    the step; the causal normaliser.
- **The REM model is reused unchanged** from `ephys/sleep_model.py`: `records_for`, `build_data`, `to_arrays`, `design`,
  `run_folds`, `tables`, `cmp`.
- **Report:** `results/2026c/ephys_spikes/reports/ephys_spikes_rem_ripple_model_2026c.md`, plus `_comparisons_2026c.csv`, the
  figure `ephys_spikes_rem_ripple_model_2026c.png` and the pointer `run_manifest_rem_ripple_model_2026c.json`.
- **Runs:**
  - `$OUT_ROOT/2026c/rem_ripple_model_20261009_1314/`: S1 features, fold tables, T3;
  - `$OUT_ROOT/2026c/rem_ripple_checks_20261009_1340/`: checks, K1 split, K6, post hoc.
- **Input cache:** `$OUT_ROOT/2026c/rem_ripple_inputs/swr_events_and_slope.pkl` (SWR event peaks + flags and the imu_fixch
  raw slope per session, read once from storage).

## Definitions (headline; full set in the report)

- **Step:** 10 s of NREM; the outcome stay / REM / WAKE at its end (Step B).
- **Reference model B** = B-full with the counter fixed at P_tw600_k0: NREM minutes since the last REM, × e^{−d/600 s}
  over wakes, emptied by REM. It also contains the clock, the experiment day, L1 wake history and the animal.
- **Covered second:** SWR tier validated / good, before `use_until`, outside the probe-advance settle windows.
- **ALL events (primary):** every detected event whose peak second is NREM in the scoring modelled, flags ignored.
- **KEPT (sensitivity):** the same with `excluded == False`.
- **Window rate:** $rr_L = \ln\frac{k+0.5}{(m/60)\,\bar r_b(t-L)}$ over $[t-L-600, t-L)$. $\bar r_b$ = the animal ×
  probe-block NREM rate before $t-L$ (causal).
- **Ripple counter:** $C = E/\bar r_b(t)$, with $E$ kept exactly like P (events instead of minutes).
- **Rate since REM:** $\rho = \ln\frac{C+0.5}{P+0.5}$.
- **Δ** = held-out log-loss change in % of the smaller model (forward chaining over day-halves, 15 folds, bootstrap CI over
  folds).
- **holds** = CI < 0 and ≥ n − 1 of the n animals with test steps better (n = 5: SF11's ripples end inside the
  train-only blocks). A term counts only if it holds on both scorings, FINAL and pass2med.

## Results

**Data.**
- The rebuilt steps match the owner's cached held-out steps row for row: 126,231 FINAL, 126,889 pass2med, y identical.
- B vs gate-only reproduces Step B on the same 122,735 test steps / 2,544 REM entries:
  - FINAL −2.35 %, against Step B's −2.17 % (Step B chose the counter's grid point per fold);
  - pass2med −1.97 %, the same as Step B.
- Subsets: S1 = 127k (FINAL) / 132k (pass2med) steps with a ripple-covered past 12 min; S2 ≈ S1.

**T1, the recent rate (10-min window).** No gain at any lag on either scoring.
- Primary, L = 60 s, ALL: FINAL −0.006 % [−0.036, +0.021], pass2med +0.019 %.
- In-sample direction: slightly positive on REM (+0.10 per SD).

**T2, the ripples accumulated since the last REM.** Pass the numeric rule on both scorings:
- C replacing P: −0.33 % / −0.30 %, 5/5;
- ρ on B: −0.33 % / −0.28 %;
- KEPT is larger: −0.48 / −0.45 %.

By the plan this was description, because T1 failed, so it went through Amendment 2.

**Amendment 2, artifact checks of ρ (ALL).** Conditions (i) and (iii) fail:
- **(i) Lagged 60 s:** the whole gain vanishes (FINAL −0.010 %, pass2med +0.001 %); at 120 s too.
- **(ii) Circular shifts** of each record's ripple sequence: no gain (0–2/5 better). The gain is in the timing → pass.
- **(iii) Beyond depth** (discounted mean NREM depth since the last REM): FINAL −0.21 % holds, pass2med −0.06 % [−0.17,
  +0.02] does not → fail.
- **(iv) Outcome:** the unlagged gain sits in REM (binary REM log-loss −0.56 % / −0.46 %, 5/5) more than in WAKE
  (−0.14 / −0.13 %) → pass.
- **K5:** the whole-block normaliser gives the same as the causal one.
- **K6:** ρ is negative on REM in 6/6 animals (in-sample). At the 60-s lag it is about 0.

**Post hoc (not pre-registered).**
- 54 % (FINAL) / 64 % (pass2med) of the unlagged gain sits on the single 10-s step right before REM entry. There ρ is −0.085,
  against about 0 elsewhere.
- About 60 % of it is in bouts that end in REM within their first minute: short NREM stretches with few ripples.

## Reading

**Coincidence or link?**
- At the scale of the REM cycle, the preceding NREM ripples add no REM-entry information beyond the NREM counter, the
  clock and the wake history.
- The macro reciprocity (ripple-rich naps, REM-poor nights) is accounted for by drivers the model already has.
- The only ripple information about REM is **local**: ripples vanish in the last minute before REM entry. That is the
  transition under way (the pre-REM drop, 6/6), not a readiness signal.

**Status.**
- No slow ripple → REM effect: tested and **not supported**.
- The transition-local drop: a robust description (6/6 animals, both event versions, both scorings), not a mechanism.

**Limits.**
- One cohort; five test animals (SF11's ripples end on 09-02).
- Ripple counts are not replay content.

## Verification

- `python ephys/rem_ripple_model.py --selftest` → PASS (6 checks).
- Alignment and reproduction as above.
- Every model of a comparison is fitted on the same subset.
- Both scorings were run.
