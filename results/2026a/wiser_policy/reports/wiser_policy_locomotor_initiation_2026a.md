# Locomotor-bout-initiation report — WISER agent-policy (Phase 1 / Module 3)

**Provenance:** decision unit = `locomotor_buf14_exit30_move10_ep5`; 198735 at-risk rest epochs, 1016 onsets; generated 2026-07-11T23:51:32.800595; n_perm=20. **All metrics from THIS single run.**

**Status:** ⚠️ candidate. Module 3 is the ENTRY-side twin of the built site-residence-termination (leaving) hazard: given the animal is SETTLED at rest in a named ROI, the hazard of INITIATING a locomotor bout. Onset = speed-onset ABOVE the ~7 in jitter floor — a **LOWER bound** (in-nest sub-jitter stirring, the ~18:00 arousal, are invisible → **not 'wake'**). Whole nights are the outer blocks (~8); primary loss = held-out **bits/decision**. Frame UNVERIFIED. NOT 'the policy', NOT 'decided to forage'.

## Definitions (formula + plain text)

- **Unified locomotor state** (per 5 s bin): `rest` (settled: named-ROI-state ∧ stationary),
  `local_active` (named-ROI-state ∧ active), `transit` (open ∧ active), `pause` (open ∧ stationary),
  `unknown` (empty/gap). ROI-state = module-5 hysteretic segmentation; movement-state = speed
  hysteresis (enter ACTIVE after 10 s moving, exit after 10 s stationary; a shorter pause HOLDS).
- **Bout-initiation hazard** $h_i(t)=P(\text{initiate a bout in }[t,t{+}\Delta)\mid \text{at rest at }t, z_t)$,
  $\operatorname{logit}h_i(t)=\beta\cdot z_t+f_r(\tau)$; $\tau$ = elapsed rest (mandatory basis),
  $\Delta$ = epoch (s). Plain: per time-slice while settled at rest, the probability of starting a
  locomotor bout given elapsed rest + covariates. Event = the movement-state ACTIVE onset that ends
  a rest episode (NOT an ROI departure).
- **Held-out bits** $H=-\frac1N\sum\log_2 p(\text{initiated}\mid z)$ (bits/decision), leave-one-night
  -out. **skill** $=1-H_{\text{model}}/H_{\text{marginal}}$. **Δbits** $=H_{\text{base}}-H_{\text{model}}$.
- **Social increment**: held-out Δbits of adding jitter-safe group-social ($n_{\le1\text{m}}$,
  mean-others-distance), gated by a within-night **circular time-shift** null and a **day-shuffle**
  null (same animal×ROI×clock-hour on a different night); z of observed vs null.
- **Personalization gain** $\Delta\text{bits}(i,\text{night})=H(\text{pooled})-H(\text{personalized})$,
  the identity part fit only on animal $i$'s TRAINING nights; env-matched conditional identity
  permutation for the null.
- **Excluded predictors:** `moving_frac` (LEAKAGE — the onset epoch's moving fixes encode the event),
  `nn_dist_in` (partly sub-jitter).

## The four distinctions (measurement gate; causal guarantees in `selftest_locomotor_states.py`)

- **D1 initiation ≠ departure:** onsets 1051, module-relocating departures 40 (ratio 26.275). Initiation
  is a distinct, more frequent event than ROI departure.
- **D4 arrival ≠ settled:** 0.011071428571428621 of named-ROI visits contain no rest bin (moving pass-throughs).

## Results

**Support:** 1016 onsets over 198735 at-risk rest epochs
(0.51%); states populated = {'rest': True, 'local_active': True, 'transit': True, 'pause': True} → gate
**SUPPORTED**. State coverage, not statistical power; ~8 night-blocks under whole-night holdout under-power a <0.003 bit effect (NO-GO = effect upper bound).

**Predictive gate (state):** marginal 0.0462 → M1 state 0.0434
bits (skill 0.062) → the initiation hazard **IS
predictable from residence state**. +weather → M2 0.0435 (Δbits
-0.0002); +social → M3 0.0433 (Δbits 0.0002).

**Social (strictly pre-decision, jitter-safe):** mean Δbits 0.0002 (frac+ nights 0.75); time-shift z = 4.32423780289058; day-shuffle z = 4.2090230763170995 → **NO-GO — no social increment beyond state/weather**.

**Individual (secondary):** personalization Δbits median = 7.491153456864325e-05; cond-perm z = 2.2891960636845163 → **NO-GO (negligible, as in module 5)**.

**Effect curve:** empirical initiation hazard vs elapsed rest in `initiation_hazard_curve.csv`;
by resource type in `initiation_hazard_by_resource.csv`.

## Classification & scope

Each result is behavioral / measurement-artifact / mixed / lower-bound. Onset is a **lower bound**
(sub-jitter stirring invisible). This is the **locomotor-bout-initiation** module (module 3) — one of
14; it does NOT represent the destination, approach/avoid, search, or motivation modules. Permutations:
20. Artifacts: `support_per_animal_night.csv`, `social_increment.csv`, `personalization_gain.csv`,
`initiation_hazard_curve.csv`, `locomotor_initiation_results.json`, `distinction_diagnostics.json`.
