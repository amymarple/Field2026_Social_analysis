# Do NREM ripples carry REM-scheduling information beyond the NREM counter? (cohort 2026c) — plan, before computing

2026-10-09. Written before any ripple feature enters the REM model.

## The user's request

The user wants to add ripples to the next round of the REM prediction model as a candidate explanatory variable, not as
a hard criterion for naps or REM. "The same NREM duration may contain different hippocampal activity." The order:

1. Keep the existing nap definition and the independent sleep staging; use ripples to describe nap physiology (done:
   `ephys_spikes_night_naps_2026c.md`, `ephys_spikes_swr_rem_naps_2026c.md`, `ephys_spikes_swr_rem_macro_2026c.md`).
2. Predict future REM transitions: on top of the current NREM counter, the clock and the wake history, add the ripple rate
   of the preceding NREM, and test whether held-out-date prediction improves. Only information before the prediction time
   may enter.
3. If there is a stable gain, compare the recent ripple rate with the cumulative ripple count: is REM readiness closer to
   how much NREM elapsed, or to what happened in it?

The question behind it: is "ripple-rich, REM-poor" (naps, early main sleep) a coincidence of the clock and sleep pressure,
or a link?

## Method guard (the user's point)

The kept SWR events exclude events scored REM and those with high theta / delta. They must not be used to validate REM
labels.

- **Features use only NREM before the step.** For the step at time t, ripples count only from seconds < t.
- **Every feature has two versions:**
  - from kept events;
  - from **all detected NREM events**, i.e. every event whose peak second is scored NREM, the theta / movement / LFP-EMG
    flags ignored.
- **The pass rule is applied to both.** A gain that exists only with the kept events is attributed to the filtering.
- Ripples never re-define states. The 1-s FINAL staging stays as it is.

## Model (reused unchanged from `ephys/sleep_model.py` / `sleep_model_e.py`; details confirmed with the model's owner)

- 10-s NREM steps, outcome stay / REM / WAKE, multinomial logit (C = 1e4).
- Reference model: the current reference REM-entry model, e.g. Step B's B-full with the counter `P_tw600_k0`, and any
  terms the owner names. It contains:
  - base terms: the elapsed spline, the 2-harmonic clock, the experiment day, `has_anchor`, `dark`, animal intercepts;
  - L1 terms;
  - the counter spline.
- Validation: forward chaining over the day-half blocks; `cmp` reports Δ = held-out log-loss change in % with a bootstrap
  CI over folds; "holds" = CI < 0 and ≥ 5 / 6 animals better.

## Data subset

Steps whose bout lies in a ripple-covered session (tier validated / good in the SWR quality guide, after the ripple
analysis' time exclusions) and whose recent window holds ≥ 3 min of eligible NREM. Every model in a comparison is fitted
on exactly this subset. The steps lost (count, share by animal / clock hour) are reported.

## Features (z-scored linear `extra` columns)

- **`rr10`: recent ripple rate.** Events / eligible NREM minutes over the last 10 min of NREM seconds before the step,
  within the record, on the current and earlier NREM bouts. It is relative to the animal × block NREM mean, as a ratio,
  so blocks are comparable.
- **`rr_bout`:** the same over the current NREM bout only, from its start to the step. It needs ≥ 60 s; else it takes
  `rr10`.
- **`lC`: cumulative ripple count** since the last REM, ln(1 + count), in block-relative units: events divided by the
  block's mean rate, so the count reads in "expected NREM minutes".
- **`lC_P`: the counter's ripple analogue.** The counter P's update rule, with NREM adding ripples instead of minutes, and
  the same τ_w and κ as the reference counter.

## Tests (pre-registered)

- **T1:** reference + `rr10` vs reference. Also + `rr_bout`.
- **T2** (only if T1 holds for both event versions):
  - reference + `lC` vs reference;
  - a model with `lC_P` replacing the NREM-minute counter vs the reference, i.e. ripples instead of minutes;
  - both counters together.
  - Reading: if the ripple counter alone matches or beats the minute counter, and the minute counter adds nothing beyond
    it, then REM readiness tracks what happened in NREM. If the minute counter wins and ripples add nothing, it tracks
    elapsed NREM.
- **T3, the direction of the effect** (description): the sign of the `rr10` coefficient on the REM outcome in the
  full-data fit, per animal.
- **Pass rule:** the owner's rule (Δ CI < 0 and ≥ 5 / 6 animals better), on both event versions.
- **Sensitivity:**
  - SF11 (CA1 only to 09-02 19:08) excluded;
  - the pass2med scoring if the owner uses it.

## Caution in reading

- Ripple counts are not memory processing: replay content can fall while ripples rise (Giri et al. 2024, sleep
  deprivation).
- A held-out gain is predictive information, not a mechanism: ripples and REM may both follow an unmeasured state, such
  as cortical slow-wave dynamics or temperature.

## Amendment 1 — the model owner's reply (written before any fit; supersedes the sections above where they differ)

The owner of `ephys/sleep_model.py` (session "daynight sleep explore") confirmed the reference and asked for changes.

**Reference model.** Step B's B-full with the counter fixed at `P_tw600_k0`: spec `{"L1": True, "hist": "P_tw600_k0"}`.
- base + L1 + a 4-knot spline of ln(1 + P).
- P = NREM minutes since the last REM; emptied by REM (κ = 0); × exp(−d / 600 s) over any wake; frozen over unknown.
- Held out, it beats gate-only by −2.17 % (FINAL) and −1.97 % (pass2med), 6/6 animals.
- Nothing later replaced it (S homeostat, momentum, S / G / F2 added nothing).
- `sleep_model.py` is reused unchanged: `records_for`, `build_data`, `to_arrays`, `run_folds`, `tables`, `cmp`.
- `tables` drops fold 0, so 15 folds, as in Step B.

**Both scorings are required.** FINAL (`states_1s_final`) and pass2med (`states_1s_pass2med`). A term holds only if it
holds on both.

**Event versions.**
- **Primary = ALL:** every detected event whose peak second is NREM *in the scoring being modelled*, all flags ignored.
  Reason: the scorer's REM / NREM call uses the same LFP (theta / delta), and the kept events drop REM- and theta-flagged
  events.
- **Sensitivity = KEPT:** `excluded == False` and the peak second NREM in that scoring.

**Windows: two separate questions, both pre-registered.** Window length W = 10 min of wall clock; lag L.
- **L = 0 (precursor test):** the window ends at the step start. A gain here can be the transition already under way: the
  ripples drop in the last minute before REM (6/6).
- **L = 60 s (readiness test, primary for the user's question):** the window ends 60 s before the step start. Only a gain
  here supports "REM readiness tracks ripples".
- **L = 120 s:** sensitivity.
- `rr_bout` is dropped: it has no clean lagged form, and dropping it keeps the family small.
- Only events with peak second < (step start − L) enter, never one inside the step.

**Feature definitions.**
- **Window rate:** `rr_L = ln((k + 0.5) / (m · r̄_b(t)))`, with:
  - k = events in the window's NREM seconds;
  - m = NREM minutes in the window;
  - r̄_b(t) = the animal × probe-block NREM rate (same event version), from covered NREM seconds of that block before
    t − L.
  - **The causal normaliser is the primary**, honouring "only information before the prediction time". It needs ≥ 30 min
    of covered block NREM before t − L, else missing.
  - Sensitivity: the whole-block mean (it uses later data of the block).
- **Ripple counter C (T2):** the bookkeeping of `P_tw600_k0` exactly, with NREM adding events instead of minutes:
  - NREM: C ← C + events / r̄_b (events up to the step start, so C reads in "expected NREM minutes");
  - WAKE of d s: C ← C · exp(−d / 600);
  - REM: C ← 0;
  - unknown: C frozen.
  - It needs every NREM second since the last REM, or since the record start, to be covered.

**Coverage and subsets.** A second is covered when:
- its session has SWR tier validated / good;
- it is before `use_until`;
- it is outside the probe-advance settle windows;
- it is before 09-11 19:40 (already cut by `records_for`).

The handling half hour is *not* removed: it is a behaviour effect the model's own terms carry, not a detection problem.

- **S1 (T1)** = steps where:
  - the step's second is covered;
  - all NREM seconds of [t − W − 120 s, t) are covered;
  - each of the three windows (L = 0 / 60 / 120 s) has m ≥ 3 min;
  - the causal normaliser exists.
- **S2 (T2)** = S1 ∩ counter-covered.
- Every model in a comparison is refitted on the same subset. The steps lost are reported by animal and by hour.

**Animal rule fixed before results.** SF11's ripples end at 09-02 19:08 (it was hand-checked only to ~17:04). That falls
inside the first six day-half blocks, which only train, so SF11 has no test steps. The comparisons therefore have 5
animals.
- holds = CI upper < 0 **and ≥ n − 1 of the n animals with test steps better**, computed from `cmp`'s `animals_better` /
  `animals`. That is 4/5 here; `cmp`'s own `holds` hard-codes 5.
- The subset's animal count is printed before any fit.

**Tests.** Per scoring, on the subset named; Δ = held-out log-loss change in %.
- **T1** (S1): B + `rr_L` vs B, for L = 0, 60, 120 s.
  - ALL primary; KEPT and the whole-block normaliser as sensitivities (L = 0 and 60 s only).
- **T2** (S2):
  - P vs C, each in the history slot: `{"L1": True, "hist": "ripcount"}` vs B (not nested; Δ reported).
  - B + ln(1 + C) as a linear extra vs B.
  - B + ln((C + 0.5) / (P + 0.5)), the discounted relative rate since the last REM, vs B.
  - Pre-registered reading: T2 is read as "how much NREM vs what happened in it" **only if T1 holds** for L = 60 s.
    Otherwise it is reported as description. Strong collinearity with P is expected.
- **D (depth control, only if a ripple term holds):** B + depth_L vs B + depth_L + rr_L.
  - depth_L = mean raw-slope z (imu_fixch `SleepScoreRaw.npz` `sw`, z within animal × block) over the window's NREM
    seconds.
- **T3 (description):** the sign of the `rr_L` coefficient on the REM outcome in a full-subset fit, per animal (fitted
  with the animal intercepts, the rr term interacted with animal).

**Alignment check.** The rebuilt step table must match the owner's cached held-out B-full steps
(`D:/Field2026_analysis_out/2026c/sleep_heldout_steps/heldout_steps_{final,pass2med}.csv.gz`): merge on
(record_id, bout_start, elapsed) and verify y. The B-full Δ vs gate-only on all steps should reproduce Step B before
the subset is taken.

**Second target** (the owner's suggestion, only if a ripple term holds): which movements wake (claim audit #45).

## Amendment 2 — artifact checks of the T2 counter result (written after T1 / T2 on FINAL, before any check below)

**What was seen.** On FINAL:
- T1 (window rates) gives no gain at any lag: L = 60 s ALL −0.006 % [−0.036, +0.021], 3/5.
- T2 (ripple counter since the last REM) passes the numeric rule:
  - C replacing P: −0.33 %, 5/5;
  - B + ln(1 + C): −0.30 %, 5/5;
  - B + ρ: −0.33 %, 5/5;
  - KEPT is larger: −0.41 / −0.48 %.

**Status.** By this plan's rule T2 is description, since T1 failed at L = 60 s. Before anything is read, the checks below
separate artifacts.
- **Primary term:** ρ (ALL).
- **Every check runs on both scorings, on S2.**

**K1, where the gain sits.**
- Held-out per-step probabilities of B and B + ρ, from the same forward chaining (own fold loop: `design` + the same
  logit).
- Δ is split into the binary REM log-loss (REM vs not) and the binary WAKE log-loss, with 95 % CIs over folds.
- A gain that sits only in WAKE is not REM readiness.

**K2, the pre-REM precursor.** Lagged counter.
- Within the current bout, events count only up to t − L; earlier bouts count in full.
- P is lagged the same way: P_L = P_start + max(0, elapsed − L) / 60.
- ρ_L = ln((C_L + 0.5) / (P_L + 0.5)), for L = 60 s and 120 s.
- If the gain vanishes at L = 60 s, it is the transition already under way, integrated.

**K3, shifted-ripple controls.** Three circular shifts of each record's sequence of per-NREM-second event counts.
- Shift offsets: 0.3 / 0.5 / 0.7 of that record's covered NREM seconds.
- Normaliser: the same, from the true events.
- What a shift keeps: each record's mean rate and its NREM structure.
- What it breaks: the timing of ripples relative to the REM cycle and to the clock within the record.
- The true ρ gain must exceed every shift's gain, and no shift may hold. If a shift gains as much, the information is the
  record-level rate (which records are ripple-rich), not ripple timing in the cycle.

**K4, depth.**
- d̄ = the discount-weighted mean NREM depth z since the last REM (P's bookkeeping, NREM seconds weighted by their raw-slope
  z; seconds without a slope are skipped).
- Test: B + d̄ + ρ vs B + d̄.

**K5, normaliser.** ρ with the whole-block normaliser (sensitivity).

**K6, direction (description).** The sign of ρ and of ln(1 + C) per animal on REM and on WAKE (as T3).

**Reading, pre-registered.** ρ is read as REM-readiness information carried by NREM ripples only if, on both scorings:
- (i) the lagged ρ_60 holds;
- (ii) the true gain exceeds every shift and no shift holds;
- (iii) it holds beyond depth;
- (iv) the binary REM log-loss improves (CI < 0).

A failure says which explanation remains:
- (i) fails: a precursor;
- (ii) fails: record-level rate;
- (iii) fails: depth;
- (iv) fails: a waking signal.

Even if every condition holds, the claim stays a Candidate: one cohort, five test animals, an effect of a few tenths of a
percent.

## Amendment 3 — after the read-only Fable audit (written before any test below)

**What the audit found.** No leakage and no material bug. Two readings of Amendment 2 do not hold as run:
- **The lag test (i) is uninformative where the gain sits.** 70–80 % of the unlagged gain is on steps in the first minute
  of a NREM bout. For elapsed < 60 s, ρ_60 equals ρ at the bout start by construction. So "the gain vanishes with the lag"
  was largely guaranteed there, not found.
- **40 % of the S2 REM entries come from NREM bouts ≤ 60 s.** These are ripple-poor: median C 0.12 vs 8.3; 26 % have zero
  ripples. The gain may therefore be "short ripple-poor NREM stretches resume REM". That is plausibly a property of the
  scorer's NREM labels within REM episodes: the scorer and the detector read the same LFP.
- **The depth control (iii) was run on a subset that loses 35 % of the REM entries** (`dbar` needs ≥ 60 discounted NREM-s
  since the last REM), with no same-subset baseline. So (iii) cannot be read as run.

**New tests.** On S2, ALL events, both scorings.
- **K7, the lag where it is meaningful:**
  - restrict to steps with elapsed ≥ 60 s, and separately ≥ 120 s;
  - on each: B vs B + ρ0, and B vs B + ρ60.
- **K4b, the depth control with its own baseline.** On the K4 subset (`dbar` finite):
  - B vs B + ρ0 (baseline);
  - B vs B + d̄;
  - B + d̄ vs B + d̄ + ρ0 (as K4).
- **K8, description.** REM- and WAKE-ending bouts by bout length (≤ 60 s, 60–120 s, 2–5 min, > 5 min):
  - n;
  - share preceded directly by REM, and by WAKE;
  - the current bout's ripples before the last step (median, share zero);
  - median C.

**Reading, fixed now.**
- **K7.** If ρ0 holds on the elapsed ≥ 60 s steps and ρ60 does not, on both scorings, then information in the last 60 s
  before a step is shown where the lag can see it. That is a transition-local ripple drop within longer bouts.
  If ρ0 does not hold there either, the counter's gain comes from the first minute of NREM bouts. Its reading is then
  "ripple-poor short NREM stretches, mostly after REM, return to REM", a bout-level property. It is not separable from
  how the scorer cuts REM episodes, and it is not a pre-REM drop.
- **K4b.** (iii) is read from B + d̄ + ρ0 vs B + d̄ on the same subset as its baseline B + ρ0 vs B. "Carried by depth"
  needs the first to fail while the second holds.
- **The null is bounded.** The T1 CIs exclude a gain larger than about 0.05 % from a linear 10-min window term at lags
  0–120 s, with these limits:
  - 5 test animals;
  - SF11 only in training;
  - sleep-onset NREM after long wakes is not tested (S1 needs ≥ 3 min of NREM in the past 12 min).

## Output

- `ephys/rem_ripple_model.py` (`run`, `--selftest`);
- report `results/2026c/ephys_spikes/reports/ephys_spikes_rem_ripple_model_2026c.md` + CSVs;
- change log `change_log/2026-10-09-rem-ripple-model.md`.
