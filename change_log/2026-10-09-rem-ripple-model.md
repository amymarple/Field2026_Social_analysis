# Ripples in the REM-entry model: no scheduling information beyond the NREM counter; ripple-poor short NREM bouts return to REM (2026-10-09)

Plan (pre-registered; Amendment 1 = the model owner's reply, Amendment 2 = the artifact checks, Amendment 3 = after a
read-only Fable audit; each written before it ran): [implementation_plan/2026-10-09-rem-ripple-model.md](../implementation_plan/2026-10-09-rem-ripple-model.md).

The user asked to add the NREM ripple rate to the REM prediction (counting) model as a candidate predictor, not as a nap or
REM criterion, and to test held-out gain with only pre-prediction information. The question behind it: is "ripple-rich,
REM-poor" (naps, early main sleep) a coincidence of shared drivers, or a link? The model and its rules came from the owner
session "daynight sleep explore".

## What changed

- **New `ephys/rem_ripple_model.py`**, with commands:
  - `run`: T1 / T2 / T3 + the reproduction of Step B;
  - `checks`: Amendment 2, K1–K6;
  - `posthoc`: where the gain sits;
  - `followup`: Amendment 3, K7 / K4b / K8;
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

**Amendment 2, artifact checks of ρ (ALL).** Conditions (i) and (iii) fail as run; both readings are revised by Amendment 3 below:
- **(i) Lagged 60 s:** the whole gain vanishes (FINAL −0.010 %, pass2med +0.001 %); at 120 s too.
- **(ii) Circular shifts** of each record's ripple sequence: no gain (0–2/5 better). The gain is in the timing → pass.
- **(iii) Beyond depth** (discounted mean NREM depth since the last REM): FINAL −0.21 % holds, pass2med −0.06 % [−0.17,
  +0.02] does not → fail.
- **(iv) Outcome:** the unlagged gain sits in REM (binary REM log-loss −0.56 % / −0.46 %, 5/5) more than in WAKE
  (−0.14 / −0.13 %) → pass.
- **K5:** the whole-block normaliser gives the same as the causal one.
- **K6:** ρ is negative on REM in 6/6 animals (in-sample). At the 60-s lag it is about 0.

**Post hoc (not pre-registered).**
- 54 % (FINAL) / 64 % (pass2med) of the unlagged gain sits on the last 10-s step before REM entry.
- 70–80 % of it sits on steps in the first minute of a NREM bout.

**Fable audit (read-only).**
- It found no leakage and no material bug.
- Amendment 2's lag check is uninformative where the gain sits: for steps < 60 s into a bout, the lagged ρ carries no
  within-bout information by construction.
- Amendment 2's depth check ran on a subset that loses 35 % of the REM entries, with no same-subset baseline.
- So Amendment 3 was written before running.

**Amendment 3.**
- **K7, steps ≥ 60 s into a bout:**
  - unlagged ρ: FINAL −0.115 % (holds, 5/5); pass2med −0.105 % (CI spans 0, does not hold);
  - lagged ρ: nothing on either.
- **K7, steps ≥ 120 s into a bout:** nothing on either scoring.
- **K4b, depth with its own baseline:**
  - FINAL: ρ alone −0.155 % (does not hold), beyond depth −0.205 % (holds);
  - pass2med: ρ alone −0.127 % (holds), beyond depth −0.063 % (does not hold).
  - Inconclusive.
- **K8, the short bouts:**
  - 40 % (FINAL) / 41 % (pass2med) of REM entries come from NREM bouts ≤ 60 s;
  - 42–43 % of them directly after REM;
  - ripple rate 24 / 21 per min, against 51 / 48 in short bouts ending in WAKE;
  - 28 % with no ripple;
  - in bouts > 5 min the rate before REM equals the rate before WAKE (74 vs 76 / 73 vs 75 per min).

## Reading (revised after the audit)

**Coincidence or link?**
- At the scale of the REM cycle, the preceding NREM ripples add no REM-entry information beyond the NREM counter, the
  clock and the wake history:
  - no held-out gain larger than about 0.05 % from a 10-min window rate at lags 0–120 s;
  - no gain from ripples older than the last minute.
- The macro reciprocity (ripple-rich naps, REM-poor nights) is accounted for by drivers the model already has.
- The only REM-predictive ripple signal is the **ripple poverty of short NREM bouts that end in REM**, within their first
  one to two minutes and often inside a REM episode.
  - The scorer's REM / NREM call and the detector read the same LFP, so this cannot be separated from how the scorer cuts
    REM episodes.
  - It is **not** a pre-REM ripple drop within longer bouts.
  - The earlier wording "transition-local drop in the last minute before REM" is withdrawn.

**Status.**
- No ripple → REM-scheduling effect: tested and **not supported**. Scoped and bounded as above.
- Short REM-ending NREM bouts are ripple-poor: a description (both scorings), not a mechanism.
- The depth control is inconclusive.

**Limits.**
- One cohort; five test animals (SF11's ripples end on 09-02, so it is only in training).
- Sleep-onset NREM after long wakes is not in S1.
- Ripple counts are not replay content.

## Verification

- `python ephys/rem_ripple_model.py --selftest` → PASS (6 checks).
- Read-only Fable audit: no leakage, no material bug; its two corrections are addressed by Amendment 3.
- Alignment and reproduction as above.
- Every model of a comparison is fitted on the same subset.
- Both scorings were run.
