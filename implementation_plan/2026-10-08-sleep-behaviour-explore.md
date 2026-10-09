# Sleep behaviour explore: the internal schedule, day vs night sleep, and a model of the implicit scheduler (cohort 2026c)

**Date:** 2026-10-08. **Status:**
- written before any of its results;
- **Steps A and B DONE 2026-10-09** (the user: "正式版跑吧然后B直接上"):
  - [Step A report](../results/2026c/ephys_spikes/reports/ephys_spikes_sleep_explore_A_2026c.md);
  - [Step B report](../results/2026c/ephys_spikes/reports/ephys_spikes_sleep_explore_B_2026c.md) + post-hoc
    [diagnosis](../results/2026c/ephys_spikes/reports/ephys_spikes_sleep_explore_B_diag_2026c.md);
  - claims #6a, #32–#36 in the claim audit;
- **Step C DONE 2026-10-09** (the user: "干完做C"):
  - [Step C report](../results/2026c/ephys_spikes/reports/ephys_spikes_sleep_explore_C_2026c.md);
  - claims #14b (now Established), #35, #37–#39.
- **Steps D and E DONE 2026-10-09** (the user: "可以DE上吧"):
  - [E report](../results/2026c/ephys_spikes/reports/ephys_spikes_sleep_explore_E_2026c.md) (start with its Reading);
  - [D1](../results/2026c/ephys_spikes/reports/ephys_spikes_sleep_explore_D1_2026c.md),
    [D2 + E (ii) / (vi)](../results/2026c/ephys_spikes/reports/ephys_spikes_sleep_explore_D2E_2026c.md),
    [E held-out](../results/2026c/ephys_spikes/reports/ephys_spikes_sleep_explore_E_heldout_2026c.md);
  - claims #40–#43.
- **Amendment 1 (§9), parts S, G and F2 DONE 2026-10-09** (the user: "模型可以预测睡眠的稳定性么… F可以干了 #43可以干";
  the S2b / S3 addendum: "真正的模型应该可以预测干扰"):
  - [S report](../results/2026c/ephys_spikes/reports/ephys_spikes_sleep_explore_S_2026c.md) (start with its Reading),
    [G report](../results/2026c/ephys_spikes/reports/ephys_spikes_sleep_explore_G_2026c.md),
    [F2 report](../results/2026c/ephys_spikes/reports/ephys_spikes_sleep_explore_F2_2026c.md) (WISER / environment / social);
  - claims #44–#47, #43 updated (stays Candidate); Step F2 listed without numbers (none held on both scorings).
- **F1 (sequence-only hypotheses H5, H7–H11, H20, H23) DONE 2026-10-09:** [F1 report](../results/2026c/ephys_spikes/reports/ephys_spikes_sleep_explore_F1_2026c.md);
  claims #48–#53, notes on #6b, #14, #34. **Amendment 1 complete.**
- **Amendment 2 (§10), part P DONE 2026-10-09:** [P report](../results/2026c/ephys_spikes/reports/ephys_spikes_sleep_explore_P_2026c.md)
  (start with its Reading); claims #56–#57, #47 corrected; part Q not triggered (residuals on different quantities).
- **Amendment 3 (§11), part T DONE 2026-10-09:** [T report](../results/2026c/ephys_spikes/reports/ephys_spikes_sleep_explore_T_2026c.md);
  T1 / T2 fail on both scorings (#58); FINAL's REM residual base-dependent, pass2med's debt slope robust (#43).

**Builds on:**
- the internal-schedule plan [2026-10-07-sleep-internal-schedule.md](2026-10-07-sleep-internal-schedule.md) (Phases 0–6;
  §20 points here);
- its [claim audit](../results/2026c/ephys_spikes/reports/ephys_spikes_sleep_schedule_claim_audit_2026c.md), updated
  2026-10-08 from the logic audit;
- the logic audit [docs/methods/sleep_logic_audit_2026-10-08.md](../docs/methods/sleep_logic_audit_2026-10-08.md)
  (Fable + the main session's checks; read its header first).

## 1. The stage and its scope (the user, 2026-10-08)

**Name.** The "**sleep behaviour explore**": explore as many hypotheses as possible before touching detailed LFP. If an
internal scheduler exists, it must be visible from the sleep sequence alone, so the sleep model needs no detailed LFP.

**Allowed inputs:**
- the scored 1-s states — FINAL (`states_1s_final`), with `pass2med_remclean` (fixed thresholds) as the check for every
  contrast whose two sides are different sessions (night vs day, before vs after a round);
- time, light phase (NOAA sunrise / sunset), experiment day;
- the head IMU: the 50-Hz movement onsets, the Phase-6 event library, the IMU seconds cache;
- WISER default tracks: house, field, co-located housemates per second;
- outdoor temperature and rain (weather console);
- the handling gaps (Phase-0 gap table).

**Not allowed now (next stage, LFP):** SWR, delta waves, theta, z-SW depth, LFP-EMG. The existing LFP-feature claims
(#4 depth, #16 night-REM theta, #29c follower LFP-EMG) stay out of the chain and the model.

**Caveats, stated wherever they apply:**
- Video tracking is not in yet. Body contact, huddling, and the identity of whoever starts a group movement need video.
- WISER house = ROI + 14 in, ~4–7 in jitter. It says "in the same house", not "in contact".
- The sleep states come from the scorer. The head IMU is its EMG, and two of its rules depend on head movement:
  - `imu_nremgate`: movement + slow wave = WAKE;
  - `imu_remclean`: REM with ≥ 3 of 5 s of head movement = WAKE.
  Any claim that links IMU movement to the scored state carries this caveat.

**Cut:** everything from 09-11 19:40 (the five females) stays out of inference. Hypothesis H25 is a description of
after-cut data.

## 2. Where the logic stands (from the logic audit; statuses in the claim audit)

**Theme 1, the schedule: only REM entry is regulated, by up to three inputs at three time scales.**
1. **A minutes-scale count.** When REM starts is set by the NREM accumulated since the last REM — a count, not a clock
   (#1–#3, Established).
2. **Short and long wakes.**
   - Brief wakes (< 2 min) keep the information (#5, Established).
   - Any wake ≥ 7 min is **not resumed**: the NREM before it no longer counts (#6a, Candidate strong; Fable's censored
     Cox, to be reproduced, step A).
   - Only at night do longer wakes push REM further back, graded over hours (#6b, Candidate, night only).
3. **A slow REM deficit?** REM missing before a morning battery round is repaid within 1–3 h, specifically REM (#10,
   Candidate strong). Within continuous day sleep nothing is repaid (#9). Whether this needs a separate deficit or
   falls out of the count + gate is open (step D).
4. **No day-to-day 24-h balance.** The night → day "trade-off" was a cohort-wide drift of sleep from night into day
   (#13 withdrawn as a balance; #30 drift, Established descriptive).
5. **NREM.** Sleep after a wake is NREM-dense, much more at night. The wake-length part is not separable from the night
   (#31, Candidate). Whether NREM has its own rebound is an open hypothesis (H4).
6. **Housemates and temperature.** Housemates perturb (coupled movements within 0.1 s, mostly absorbed) but do not drive
   REM. Temperature nudges the REM share, not entry timing.

**Theme 2, day vs night: same machinery, a lower REM-entry gain at night, plus the night's long wakes on top.**
- **At matched short prior wakes:**
  - the night enters REM ~0.45× as often (5.0 vs 11.7 REM bouts per NREM h after 2–7-min wakes);
  - the first REM comes later;
  - REM bouts last the same.
  This is #14b, Candidate until rerun on `pass2med` with per-animal signs (step A).
- **The night's long wakes add a delay on top.** They run a median of 78 vs 14 min by day and delay REM further; only
  42–44 % of the sleeps after them reach REM.
- **Open:** where and with whom the rats sleep, whether the gain follows the light step or a circadian curve, and what
  drove the 12-day drift.

**Theme 3, the scheduler: the implicit theme under both.** It is modelled as one set of rules, specified in §4, that
must reproduce Themes 1 and 2 and the regular daily totals (NREM 9.7 ± 0.2 h, REM 1.8 ± 0.1 h per 24 h) despite constant
interruption. Candidate idea to test: "daily totals are regular because the inputs are regular, not because a budget
is enforced".

## 3. Definitions fixed now (shared by every step)

- **Step.** 10 s, as in the current hazard model. Per step from NREM: stay / REM / WAKE (multinomial). From REM: stay /
  NREM / WAKE. From WAKE: stay / NREM.
- **Validation.**
  - Forward chaining over the 22 day-half blocks (15–16 folds); Δ = held-out log-loss change in % of the smaller model,
    95 % CI by bootstrap over folds.
  - **Holds** = CI < 0 and ≥ 5/6 rats.
  - Per-animal signs are always reported.
- **Wake bins.** < 40 s (MA, Watson 2016), 40–120 s, 2–7 min, 7–30 min, 30–120 min, ≥ 2 h.
- **Matched prior wake.** Episodes (Watson SLEEP rule, as Phase 3) whose preceding wake falls in the same bin; compared
  within bin.
- **Post-handling exclusion.** For day/night contrasts, the 3 h after any battery-round gap are excluded (they are
  analysed separately in step D).
- **Light.** NOAA sunrise–sunset at the field site (as Phase 3). Clock hours are never used as a proxy.
- **Day baselines.** Every expected-amount baseline that compares windows on either side of dawn or dusk includes
  phase × experiment day (or day fixed effects). Reason: the opposite night / day trends of the drift (#30) contaminate
  a common linear day term.

## 4. The scheduler model (Theme 3), specified now

Deterministic latent variables, computed from the observed sequence given a few time constants. No HMM: "the state is
a function of the observed history" is the hypothesis, and the old gate for a hidden-state model (history beyond the
accumulated quantity) was never triggered.

**P — the REM-entry count, in minutes.**
- Rises by 1/6 per NREM step.
- Over a wake of length d (any length, MAs included): P ← P · exp(−d / τ_w).
- At the end of a REM bout of length r: P ← P · (1 − φ(r)), with φ(r) = 1 − exp(−r / κ).
- Unknown epochs: P is frozen, and an "unknown since" flag enters the hazard.

**S — an NREM homeostat** (0–1; for the simulation and H4):
- dS = (1 − S) / τ_r per wake step;
- dS = −S / τ_d per sleep step.

**D — a slow REM deficit, in minutes** (step D decides whether it is needed):
- dD = +ρ per non-REM step, −1/6 per REM step, floored at 0.

**G — the gate:**
- 2-harmonic time of day + a dark step, on REM entry;
- the same two terms, separately, on wake entry.

**Inputs:** a decaying post-handling term after each gap. Housemate and temperature terms are added only after the base
model passes.

**Observation model.**
- From NREM, the hazards are multinomial:
  - REM vs stay: α_R + f(P) + γ_S·S + δ·D + G_R + animal;
  - WAKE vs stay: α_W + γ_W·S + G_W + animal.
- REM exits: constant + phase (no history, per #14).
- Sleep onset from WAKE: S + phase + housemates (needed only for the simulation).

**Simulation.** Simulated sequences get the scorer's rules before any comparison:
- minimum state length 6 s;
- REM ≥ 7 s;
- no REM after a > 10-s wake.
Unknown epochs are censored in the likelihood.

**Estimation.**
- Time constants are profiled over grids:
  - τ_w ∈ {0, 15 s, 30 s, 1, 2, 5, 10, 30 min, ∞};
  - κ ∈ 4 values;
  - τ_r, τ_d ∈ 3 × 3.
- An inner multinomial GLM (IRLS) is fitted at each grid point.
- Time constants are shared across rats (per-animal profile curves shown as a check only). Intercepts and gate
  amplitudes are per animal.
- CPU only; < 1 h per full grid.
- Identifiable: τ_w (from the 2–7-min wakes; a wide CI is expected), κ, β_dark vs ln d (because matched episodes
  exist), ρ·δ (across gaps and nights only).
- Probably flat: τ_r / τ_d. Their profile curves are reported, not tuned.

## 5. Steps, in order, with pass / fail rules written now

### Step A — the reproduction gate (hours)

Fable's checks are reproduced in repo code (`ephys/sleep_explore.py`, new) before any status changes. Each item states
its pass rule.

| A# | check | pass → status change |
|---|---|---|
| A1 | #6 as a censored survival model. Every post-wake sleep after a wake ≥ 7 min is kept (also those that never reach REM). Cox for first-REM latency in NREM time ~ ln d + N_pre + dark + animal strata, on both scorings, plus a forward-chained version (train earlier blocks, predict the next). | N_pre ≈ 0 with CI excluding −0.15 (resumption predicts ≈ −0.3), ≥ 5/6 rats → #6a Established (scoped). |
| A2 | #6 split by phase: ln d slope in light (7–30-min wakes) vs dark (7 min–4 h), with categorical bins. | Dark slope > 0 with CI > 0 and light CI including 0 → #6b stays "night only". Any light dose effect → #6b re-scoped. |
| A3 | Matched night gain: REM bouts per NREM h and first-REM latency (Cox), dark vs light within the 2–7-min and 7–30-min bins, post-handling hours excluded, both scorings, per-animal signs. | Night ratio ≤ 0.6 in both bins, ≥ 5/6 rats, both scorings → #14b Established. |
| A4 | #10 morning payback: day-demeaned, NREM debt partialled, bouts vs bout-duration decomposition, fixed thresholds + FINAL. | REM-debt slope > 0.2 with p < 0.05 at 1 and 3 h, day-demeaned → #10 stays Candidate (strong) (promotion needs step D). |
| A5 | De-circularising #28b / #29a, three parts. (a) In the Phase-6 library, woke60 of first movers vs controls, excluding wakes that begin < 15 s after the onset. (b) The same on the 7 pilot sessions scored with the ungated `imu` variant (`D:/3rd_rat_spikes/analysis/sleep/imu/`, `useEMG_NREM=False`). (c) A full ungated rescore on the server only if (a) and (b) disagree. | Mover excess (vs control) remains ≥ half its size under (a) → "movement raises waking" kept with the caveat; otherwise it is definitional and is withdrawn. |

### Step B — the minimal scheduler model: P + G (≈ 2 days)

**Code.** `ephys/sleep_model.py` (new), reusing the feature, fold and baseline machinery of `sleep_schedule.py`.

**Models compared, held out by forward chaining:**
- **B-full:** P(τ_w, κ) + G + clock terms + animal intercepts;
- **M2t:** the current best feature model;
- **reset:** τ_w = 0 for d ≥ 7 min, pause below;
- **pause:** τ_w = ∞;
- **gate-only:** no P (clock + elapsed + dark);
- **no-dark:** B-full without the dark step.

**Pass:**
- B-full is not worse than M2t by more than 0.1 %;
- B-full beats reset and pause (holds);
- B-full beats gate-only by at least 0.5 % (the #2 margin);
- the τ_w profile minimum is interior (30 s–10 min) and stable when one animal is left out.

**Reads:** "reset vs discount" settled as one number, τ_w; whether the dark step is needed once P is in.

### Step C — day vs night, matched (≈ 1 day)

**C1. Gain vs prior wake.** B-full + ln d + dark × ln d, post-handling hours excluded, both scorings, per-animal signs.

Pass for "the night is a gain independent of the prior wake": the dark coefficient on REM vs stay is ≤ ln 0.6 with ln d
and P in the model, ≥ 5/6 rats, same sign on `pass2med`. dark × ln d is reported as the night-only ramp.

**C2. Light step vs circadian curve vs prior wake.**
- Data: episodes starting within ±2 h of sunset and of sunrise, prior wake < 7 min, P at onset.
- Models: 2-harmonic clock vs + a step at the light transition vs + ln d only.

Pass for "light-driven": the step improves held-out log-loss on the transition hours (holds).

**C3. Where and with whom (WISER).** Co-located housemates per second and house vs field, from the Phase-5 base terms.
- Tests: the REM-entry hazard and the NREM → WAKE hazard with group size × phase; and the dark coefficient within
  house-with-mates sleep only.
- Pass for "the gain is not a location / company effect": the dark coefficient changes by ≤ 0.1 when restricted.
- Group size is reported with sign counts; "huddling" is never claimed.

**C4. The 12-day drift.**
- Per animal-day: night and day sleep share ~ experiment day + nightly temperature + rain + WISER time outside the
  house, animal fixed effects.
- Pass for "environmental": R² > 0.5 from weather + activity, with the day term n.s. Otherwise "adaptation / unexplained".
- Description, not regulation.

### Step D — the origin of the morning payback (≈ 1 day + the model)

**D1. Natural dawn wakes.** Natural wakes ≥ 30 min ending 05:00–09:00 without a round; the same debt / payback
regression as #10 (fixed thresholds), with NREM debt and the main-sleep onset time as covariates.

**D2. Simulation without D.** Simulate the step-B model (P + G, no D), conditional on the observed long wakes and gaps,
100 replicates; compute the same payback slope on the simulated data.

**Pass for "a slow REM deficit exists":**
- D1 slope > 0.2 with p < 0.05 and ≥ 4/4 rats with windows; and
- the D2 slope < 0.1.

If D2 reproduces the slope, the payback is the count seen through the gate: D is dropped and #10 is re-read.

### Step E — the full generative model (≈ 3 days)

**Additions:** S, the WAKE- and REM-exit hazards, the momentum alternative (a 2nd-order semi-Markov model with hazards
on the previous two bouts' types and log durations; Stephenson 2025), and D if step D keeps it.

**Generative checks.** Simulation conditional on the observed long wakes (≥ 7 min) and gaps, 100 replicates. Must
reproduce:
- (i) daily REM mean and SD within ±25 % of 1.8 ± 0.1 h, and NREM within ±10 % of 9.7 ± 0.2 h;
- (ii) the carry-over curve: the held-out gain of pre-wake history by wake bin, in sign and order;
- (iii) REM share 6.8 vs 17.4 % and 4 vs 11 bouts per NREM h, within ±20 %;
- (iv) first-REM latency medians by wake bin and phase, within ±25 %;
- (v) the morning payback slope (with D in [0.2, 1.0]);
- (vi) a night → day deviation correlation ≈ 0 after a day term (the model has no budget).

**Pass / fail:**
- the model must beat momentum held out, especially on bouts after wakes;
- a failure on (i)–(iv) means the specification is wrong, not the data.

### Step F — the hypothesis batch (hours each; from the logic audit's list, sleep-behaviour scope)

One line each: hypothesis, test, pass rule. Each is run as a separate short part of `sleep_explore.py`, reported
together; each gets a claim number only if it holds.

| H | hypothesis | test | pass |
|---|---|---|---|
| H4 | NREM after a wake follows the wake's activity (WISER distance / time in the field during the wake), not only its length | NREM excess (1 h) ~ ln d + activity + dark, within night | activity CI > 0, ≥ 5/6 |
| H5 | The night ramp (#6b) is time of night, not wake length | within dark: latency ~ ln d + hours since sunset, P at onset | ln d stays with CI > 0 |
| H6 | REM discharge scales with REM length (Park) | φ(r) vs constant, inside step B | holds |
| H7 | REM bout duration is unregulated (the planned C3 never run) | ln REM duration ~ P at onset + dark + ln d + temperature + group size | all n.s. (scoped negative) or a named predictor holds |
| H8 | REM exits differ by phase | share of REM bouts ending in WAKE vs NREM, night vs day, matched duration | ≥ 5/6 same sign |
| H9 | There is no daily REM quota | add "REM minutes since sunrise" (and since the last long wake) to step B | adds nothing (CI includes 0) |
| H10 | Sequential cycles are rarer at night through the gain, not through interruptions | second REM within 135 s vs MA count in the interval, by phase | phase effect survives the MA count |
| H11 | MA rate rises with P (pre-REM fragility) | MAs per NREM min ~ P, by phase | slope > 0, ≥ 5/6 |
| H12 | Arousability tracks the state variables | P(wake within 60 s ∣ movement) from the Phase-6 library ~ P + time since sleep onset + phase + group size, with the A5 controls | P or phase holds |
| H13 | = C4 (the drift is environmental) | step C4 | as C4 |
| H14 | Warmth raises REM share through maintenance, not entry | REM bout duration and REM → WAKE exits ~ temperature anomaly | one holds, entry stays null |
| H15 | Group size changes sleep maintenance, not REM entry | NREM → WAKE hazard and sleep-onset latency ~ co-located housemates, by phase | maintenance term holds, entry n.s. |
| H16 | A housemate leaving the house ends the partner's sleep | partner WAKE hazard 0–2 min after a housemate exits (WISER) vs a time-shift chance | ratio > 1.5, ≥ 5/6 |
| H17 | Sleeping at a new site after a long wake delays REM | first-REM latency when the WISER house differs from the pre-wake site, matched wake length | site change CI > 0 |
| H18 | Handling delays REM beyond the wake it causes | post-round first-REM latency vs natural wakes of matched length and clock time | round term CI > 0 |
| H19 | The post-REM refractory dip is wall-clock, the build-up NREM-time | separate clocks for the dip and the rise, inside step B | separate clocks hold |
| H20 | Inter-REM intervals shorten within a sleep episode (ultradian progression) | k-th interval ~ k at matched P and phase | slope < 0, ≥ 5/6 |
| H21 | = C2 (light step vs circadian curve) | step C2 | as C2 |
| H22 | Rain disturbs sleep | REM entry and WAKE exits, rainy vs dry nights, matched prior wake | holds |
| H23 | The 2–7-min wakes are two kinds (quiet vs active) | split by WISER displacement / IMU activity during the wake; carry-over gain per kind | carry-over differs, CI excludes 0 |
| H24 | Fragmentation beyond totals (#17) is the count's discount in disguise | frag60's gain once τ_w is in the model | gain vanishes |
| H25 | The five females (from 09-11 19:40) change the gate or the arousability | descriptive, after-cut only | description only |

**Video only (listed, not run):** huddle / body contact vs REM entry; who starts group movements; which housemate left.

## 6. Wording rules and "do not do"

**Wording.**
- Mechanism words (scheduler, gate, homeostat, deficit) stay interpretations.
- A model that passes may be described as: "REM timing follows one count of NREM since the last REM, discounted by any
  wake with a time constant τ_w, read through a gain of ~X at night [with / without] a slow REM deficit; the daily REM
  total emerges from these rules without a daily budget".
- Never: a neural scheduler, light-vs-activity causality, that REM must occur, anything the scorer's rules built in.

**Do not:**
- report #13 as a balance or a one-way budget;
- present "two time constants";
- build on #4, #16 or #29c;
- say "long wakes reset" without the not-resumed / night-graded split;
- read movement → state without the scorer-gate caveat;
- count ≤ 1-s followers as group events;
- use FINAL alone for cross-session contrasts;
- use a common linear day term across dawn or dusk;
- fit per-animal time constants, an HMM / HSMM or a stochastic P before step B passes;
- make body-contact claims from WISER;
- read the hazard decline after 20–30 min of NREM since REM as refractoriness (night mixture);
- read the NREM excess after night wakes as a wake-length rebound (#31).

## 7. Outputs

**Code:**
- `ephys/sleep_explore.py` — step A; step F later;
- `ephys/sleep_explore_c.py` — step C;
- `ephys/sleep_explore_d.py` — D1, plus `payback_from_records` / `budget_from_records`;
- `ephys/sleep_model.py` — step B;
- `ephys/sleep_model_diag.py` — the post-hoc split of step B;
- `ephys/sleep_model_e.py` — E held-out: momentum, S;
- `ephys/sleep_sim.py` — the E simulator and checks (i) / (iii) / (iv);
- `ephys/sleep_sim_checks.py` — D2 and E (ii) / (vi).

All of them, each with `--selftest` (synthetic
sequences with known answers; the τ_w profile must recover the simulated τ_w). Standalone CLIs, as built (the
planned dispatch from `sleep_schedule.py` was not added).

**Results:**
- reports `results/2026c/ephys_spikes/reports/ephys_spikes_sleep_explore_<step>_2026c.md` + CSVs + figures;
- bulk `$OUT_ROOT/2026c/sleep_explore_<step>_<ts>/`;
- pointers `run_manifest_sleep_explore_<step>_2026c.json`.

**Records:** claims continue the claim audit's numbering (#30 →). Change log
`change_log/2026-10-08-sleep-internal-schedule.md` (new sections) or a new dated change log once step B runs.

**Run location:** local only (CPU); no server step is foreseen. A full ungated rescore (A5 c) would be a separate,
preprocessing job through `run_then_store.sh`, and only on the user's go.

## 8. Order, gates and decisions for the user

1. **Step A** (hours) → status updates in the claim audit.
2. **Step B** (≈ 2 days) → the gate for everything model-based.
3. **Steps C and D** in parallel (≈ 2 days).
4. **Step E** (≈ 3 days), only if step B passes.
5. **Step F:** cheap hypotheses can run alongside A–C: H5, H7, H8, H9, H10, H11, H14, H15, H16, H17, H18, H20, H22.
   The model-dependent ones (H6, H19, H24) run inside step B.

**Decisions for the user:**
- go / no-go per step;
- whether to run the A5 (c) rescore if (a) and (b) disagree;
- which F hypotheses come first, if not all.

## 9. Amendment 1 (2026-10-09; the user: "模型可以预测睡眠的稳定性么… F可以干了 #43可以干") — written before these results

Three parts run in parallel. Definitions, scorings and validation are as in §3, unless stated otherwise.

### S — can the counter model predict sleep stability?

**Model.** Step B's B-full at `P_tw600_k0`. Per-step probabilities are held out by forward chaining: a step in block
k is predicted by the fit on blocks < k; the first 6 blocks are never predicted.

**S1 — which movements end in waking (H12).**
- Events: the Phase-6 library's first movers (source movement, pre-state NREM), tight followers, non-movers, and the
  random co-sleep controls.
- Model propensity: each event is mapped to the animal's NREM step that contains it; its propensity is the held-out
  per-10-s WAKE probability `p_W` of that step.
- (a) Discrimination: AUC of `p_W` for woke60 among first movers, per scoring, with a bootstrap CI over blocks.
  - Compared with the AUC of a clock-only (gate-only) model.
  - Repeated with the A5 control: wakes starting < 15 s after the onset excluded.
- (b) Movement beyond the model: observed / expected woke60 (expected = 1 − (1 − p_W)^6) for movers and for controls;
  the movement effect is (O/E movers) / (O/E controls).
- Pass for "the model predicts which disturbances end in waking": AUC ≥ 0.60 with a CI above 0.5; above the
  gate-only AUC (bootstrap CI of the difference > 0); ≥ 5/6 rats with AUC > 0.5; both scorings.
- The movement effect is reported, not pass/fail.

**S2 — stability after battery rounds vs natural long wakes.**
- Windows: the 0–1 h and 1–3 h of NREM steps after (a) a usable round gap (record start) and (b) a natural wake
  ≥ 30 min inside a record.
- Measures: observed / expected (O/E) NREM → WAKE and NREM → REM transitions (expected = the sum of the held-out
  per-step probabilities), with bootstrap CIs over blocks and per-animal O/E.
- Pass for "the model predicts post-round stability": the WAKE O/E after rounds lies in [0.8, 1.25] with a CI that
  includes 1.
- The REM O/E after rounds vs after natural wakes is the H18 test below (G2).

### G — where does the REM repayment after morning rounds (#43) come from? (`n.origin_43`)

**G1 — dawn timing without handling.** D1 found no payback after natural dawn wakes (−0.02, 41 windows).
- Add its power: the minimal detectable slope (80 % power, α 0.05) from the windows' debt variance and residual SD.
- If that slope is > 0.34 (the observed round slope), D1 is uninformative and G1 stays open.

**G2 — handling-specific post-round sleep (H18).**
- Compared: post-round vs natural wakes of ≥ 30 min, matched on wake length bin and morning / evening.
- Measures:
  - first-REM latency in NREM time (Cox, animal strata);
  - REM-entry O/E (as S2) in the 0–1 h and 1–3 h after.
- Pass for "handling delays REM beyond the wake it causes": post-round REM O/E below the natural-wake O/E (bootstrap
  CI of the difference < 0), ≥ 5/6 rats, both scorings.

**G3 — the round's own sleep loss.**
- Gap debt: the REM expected during the unrecorded gap (the phase × day baseline rate × gap duration) is added as a
  second debt term next to the 3-h pre-round debt.
- Pass for "the payback is the round's sleep loss": the gap-debt slope > 0 (CI) AND the pre-round debt slope falls by
  ≥ 30 %.
- Also reported: the payback slope by gap-length tertile.

**G4 — gate release.**
- For morning rounds only: the payback slope vs the clock time of the first post-round sleep onset relative to
  sunrise, and vs the model's predicted REM-entry gain at that time.
- Pass for "a deficit released where the gate opens": a larger slope where the predicted gain is higher (interaction
  CI > 0). Reported with caution: n ≈ 49 windows.

**Reading rule.**

| result | reading |
|---|---|
| G2 pass, G3 fail | handling-specific |
| G3 pass | the round's sleep loss |
| G1 informative and positive | dawn timing |
| all fail | #43 stays Candidate (power) |

### F — the step-F hypotheses (table in §5, pass rules as written there)
- **Sequence-only batch:** H5, H7, H8, H9, H10, H11, H20, H23.
- **WISER / environment / social batch:** H4, H14, H15, H16, H17, H22, H25.
- **Run elsewhere:** H12 in S1 and H18 in G2. H6, H13, H19, H21 and H24 were run in steps B–C.
- Each hypothesis gets a claim number only if it holds (plan §5).

### Addendum to S (2026-10-09, the user, before any S result): the battery rounds as a systematic perturbation

The user: "这些电池刚好作为一个系统干扰项，真正的模型应该可以预测干扰." The rounds are a known, repeated perturbation, so a
true model must predict the response to them, not only fit ordinary sleep. Two additions:

**S2b — perturbation-blind prediction.**
- The same forward-chained B-full, with every step in the 3 h after a usable round gap (cause round_logged /
  round_inferred) REMOVED from training; the model has then never seen a post-round response.
- It predicts the post-round steps of the test block: WAKE and REM O/E in the 0–1 h and 1–3 h windows.
- Pass for "the model predicts the response to the perturbation": both O/E in [0.8, 1.25] with CIs including 1, on both
  scorings. Reported next to S2 (the model that has seen post-round data).

**S3 — the simulated perturbation response.**
- The generative model (sleep_sim v2) fitted on the data WITHOUT the 3-h post-round windows; 100 replicates,
  conditional on the observed long wakes and gaps.
- For every round, from the first post-round second, observed vs simulated:
  - REM minutes and NREM minutes in 1 h / 3 h / 6 h (censored at the record end);
  - REM bouts in the same windows;
  - the first-REM latency.
- Summaries: the mean over rounds, for morning and evening rounds separately.
- Pass for "the rules predict the response": the observed mean inside the simulated 95 % range at 1, 3 and 6 h for
  REM and NREM minutes and for the first-REM latency, on both scorings.
- The REM payback slope (D2) is already known NOT to be predicted. S3 shows whether the rest of the response is.

## 10. Amendment 2 (2026-10-09; the user: "干吧") — perturbation dynamics before any REM-need variable; written before these results

**Why.** The user's note (2026-10-09): a rule "after a perturbation, add REM in proportion to the REM missed" only shows
that a model can fit the repayment; it does not show how it arises. An internal variable with its own dynamics, fitted
on other data and frozen, may predict it — and must be allowed to fail. The repayment is not yet one target: its debt
slope is pass2med-only (#43); FINAL shows extra REM 3 h after morning rounds that follows the gap's expected REM (G3).
What both scorings agree on is the acute waking excess (#44) and the later first REM in wall time (#47), with REM entry
per NREM step at the model's rate. So the arousal dynamics come first; a REM-need variable only if a REM residual remains.

**Part P (this amendment).** Driver `ephys/sleep_perturb.py`; `sleep_sim.py` gains an optional arousal input
(identical output when absent). Both scorings. Rounds = usable round gaps (round_logged / round_inferred), as S.

Definitions:
- Arousal term on the NREM → WAKE logit only: $\eta_{WAKE} \mathrel{+}= a\,e^{-s/\tau_A}$, $s$ = seconds since the
  post-round record start; $\tau_A \in \{10, 20, 40, 80\}$ min. The stay and REM logits are untouched, so
  $P(\text{REM} \mid \text{not WAKE})$ is unchanged and only whether the rat woke informs $a$ (binary WAKE likelihood
  with the base model's logit as offset; $(a, \tau_A)$ = maximum likelihood over the grid × continuous $a$).
- Base for the step-level part: B-full at P_tw600_k0 trained on all steps EXCEPT the 3 h after rounds (as S2b's blind
  model, all blocks). Symmetric base for the control: trained without the 3 h after rounds AND the 3 h after natural
  wakes ≥ 30 min.
- Base for the generative part: sleep_sim v2 fitted on the records with every post-round 3 h masked (as S3 blind).
- Hold-out: 2-fold cross-fit over rounds by the parity of the round record's start date; each round is predicted /
  simulated with $(a, \tau_A)$ fitted on the other half.

Tests and pass rules (both scorings):
- **P1, the arousal is captured (held out).**
  - Cross-fitted blind + A vs blind on the post-round steps (0–3 h): Δ log-loss CI < 0 (block bootstrap) and ≥ 5/6 rats
    better;
  - and the 0–1 h WAKE O/E with A in [0.8, 1.25] with CI including 1.
- **P1b, handling is special.** The same term fitted after natural wakes ≥ 30 min ($a_{nat}$, symmetric base):
  $a_{round} - a_{nat}$ with block-bootstrap CI > 0.
- **P2, the later first REM follows from the arousal alone (allowed to fail; REM rules untouched).** In the cross-fitted
  simulation with A (100 replicates, conditional on the observed long wakes and gaps), the observed first-REM KM median
  after morning AND evening rounds lies inside the simulated 95 % range, and ≥ 12 of S3's 14 measures (REM / NREM
  minutes at 1, 3, 6 h, both latencies) are inside.
- **P3, no harm to ordinary sleep.** Step E's checks (i), (iii), (iv) on all records simulated with A: ≥ 27/28 pass,
  and not fewer than without A (same blind model).
- **P4, duration (description).** Rounds split into gap-length tertiles within each kind: observed vs simulated (with A)
  REM / NREM minutes at 1 and 3 h and the latency. The model has no duration term, so it predicts no duration effect.
- **Residual REM (decides part Q).** With A in the simulation: S3's morning REM at 3 h and D2's day-demeaned morning REM
  payback slope (`payback_from_records`, 1 h and 3 h) on the simulated records vs observed.

Reading:

| result | reading |
|---|---|
| P1 + P2 pass | the delayed REM after a round is explained by a decaying arousal; no REM-need variable needed for the timing |
| P1 pass, P2 fail | the arousal is real but does not account for the REM timing; a REM-side process remains |
| a REM residual outside the simulated range in the same direction on both scorings | part Q is warranted |
| a residual on one scoring only | no unified target; #43 stays Candidate, no part Q |

**Part Q (only if triggered; written now, run later).** Compare, fitted without any post-round step and frozen:
(i) a slow REM-need state (time constant hours, kept over wakes, emptied by REM; accumulating in NREM only, or over all
time since the last REM including the gap) and (ii) partial discharge during REM (κ > 0; already disfavoured in ordinary
sleep, #33). Acceptance: the frozen model predicts the post-round REM time course, the gap-length effect and the
behaviour after natural wakes, and keeps pass2med's 1–3-h post-round REM-entry O/E of 0.85 [0.78, 0.94] (a REM-need
model that predicts more REM entry there fails).

**Note after the run (2026-10-09).** Step E has 14 checks per scoring; "27/28" in P3 was read per scoring as ≥ 13/14 (the earlier "27/28 on each scoring" meant 27 of 28 in total). P1b's symmetric base never saw a bout after a wake ≥ 30 min, so a_nat is an extrapolation; P1b is reported but not read.

## 11. Amendment 3 (2026-10-09; the user: "上") — part T, a two-phase arousal; written before these results

**Why.** In part P, a single decaying arousal restores the first-hour waking (#56), but the rats then recover more sleep
than the simulation (FINAL morning NREM 3 h, REM 3 h and 6 h, pass2med evening NREM 6 h above), and S2 shows fewer
wakes than expected 1–3 h after a round (O/E 0.83–0.88, CIs touching 1). Question: is there a second, consolidation
phase (waking below baseline later), and does it — fitted on waking alone — produce the later sleep recovery, including
FINAL's extra REM at 3 h, through the existing count rules? Allowed to fail. The first-REM delay (#57) is not a target:
no constraint independent of the outcome exists for it.

**Definitions** (as part P unless stated; driver `ephys/sleep_perturb.py runT`):
- Two-phase term on the NREM → WAKE logit only:
  $\eta_{WAKE} \mathrel{+}= a\,e^{-s/\tau_1} + b\,(s/\tau_2)\,e^{1 - s/\tau_2}$; the second term is 0 at $s = 0$ and peaks at
  $s = \tau_2$ with value $b$ (expected $b < 0$). $\tau_1 \in \{10, 20, 40, 80\}$ min, $\tau_2 \in \{60, 90, 120, 180\}$ min;
  $(a, b)$ by 2-D Newton on the binary WAKE likelihood with the base logit as offset; the grid pair with the highest
  likelihood.
- Window: the 6 h after the post-round record start (steps with $s < 6$ h). Both bases leave out these 6 h (step-level
  B-full and the generative sleep_sim fit), so neither has seen a post-round step up to 6 h.
- Comparator: part P's one-phase term refitted on the same window and bases.
- Cross-fit over rounds by date parity, as in part P.

**Tests (both scorings):**
- **T1, a second phase exists (held out).** Cross-fitted two-phase vs one-phase on the post-round steps 0–6 h: Δ log-loss
  CI < 0 (block bootstrap) and ≥ 5/6 rats better; and $b < 0$ in both halves.
- **T2, the later recovery follows from consolidation (allowed to fail; REM rules untouched).** In the cross-fitted
  simulation with the two-phase term (100 replicates), the observed mean REM and NREM minutes at 1, 3 and 6 h after
  morning and evening rounds (12 measures) are all inside the simulated 95 % range. Latencies reported, not part of the
  rule.
- **T3, no harm.** Step E's checks with the two-phase term: ≥ 13/14 per scoring and not fewer than without.
- **Residual.** FINAL's morning REM at 3 h and pass2med's day-demeaned morning debt slope at 3 h with the two-phase term.

**Reading:**

| result | reading |
|---|---|
| T1 + T2 pass | the response is a two-phase arousal; the later sleep recovery (and FINAL's extra REM at 3 h if it comes inside) follows from consolidation through the count rules |
| T1 pass, T2 fail | a consolidation phase exists but does not produce the recovery; a further process remains |
| T1 fail | no second phase detectable in the waking; the later recovery is not a waking effect |
| the residual stays outside on one scoring | as in part P: no unified REM target, #43 stays Candidate |
