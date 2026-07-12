# Implementation plan — Agent-Policy Identifiability (WISER, hierarchical semi-Markov, explicit layout + weather-aware)

**Date:** 2026-07-09
**Status:** approved design; Phase 1 (audits A0–A2 + models M1–M5 + transfer audit + reward verdict).
Simulation and reward inference are gated behind the Phase-1 verdict.
**Change log (after verification):** `change_log/2026-07-09-agent-policy-identifiability.md`

## What this study can and cannot establish

**CAN:** quantify how much **identity** and **current social state** improve **out-of-night**
prediction of two navigational decisions — *when to leave an ROI* and *where to go next* — beyond an
**explicit-layout + dynamic-environment** baseline; separate **stable cross-night personalization**
from within-night fit; separate a **social-state predictive increment** from herd-level shared-use;
use **weather as dynamic context, a measurement-quality determinant, and a transfer axis**; deliver a
**go/no-go verdict on reward inference**.

**CANNOT:** establish **causal** social or weather influence (only predictive association); fit a
**high-dimensional weather-response** model (≈8 nights, weather confounded with night, habituation,
fireworks, burrow); recover a **physical/metric spatial** policy or make **fine distance** claims (the
WISER→field transform is **absent/unverified**; only topology + coarse, jitter-bounded distances are
usable); prove **stationarity** from the pre-burrow-dropout window; **identify a reward function**
(deferred, likely NO-GO); treat the ≈40 animal-nights as independent (whole **nights** are the outer
blocks); call anything a "policy" from coefficients or within-night fit alone; call a predictor
"environmental" when it contains pooled animal behavior.

## Context

Eventual goal: infer individual + social decision policies, simulate the agents, test long-horizon
prediction — but **first** establish identifiability; **do not begin with IRL**. Prior work shows
shared use dominates individual habit (pooled-corridor residual ≈ −0.01; 0/10 pairs above the
shared-pool null), sociality is **herd, not dyadic** (0/10 beat day-shuffle), the 8-night window is
**non-stationary** (stabilization 0.14→0.96; wet 06-30/07-01/07-04; fireworks 07-04; shelter-4 burrow
UWB dropout 07-03→07-07; 07-05 ~25% truncated), positions are **inches in an unverified frame**
(~7 in jitter). A naive forward policy/IRL would re-learn geometry and mislabel it a policy.

## Central question (estimand)

> When the same animal is observed on **different nights** in **sufficiently comparable decision
> states**, does knowledge of its **identity** and/or **current social state** improve **out-of-night**
> prediction of what it does, beyond an explicit-layout + dynamic-environment navigational baseline?

Target = **stable conditional decision structure that transfers across nights**, not coefficient
significance, not in-sample fit.

## Decision representation — hierarchical semi-Markov (two separate processes)

**A. Leaving hazard (estimand 1).** Discrete-time hazard over at-risk epochs while animal *i* is
resident in ROI *r* with elapsed dwell τ:  logit hᵢ(t) = β·zₜ + f_r(τ), hᵢ(t)=P(leave *r* in
[t,t+Δ) | still in *r*). **Dwell τ mandatory** — f_r(τ) (spline/piecewise per ROI) absorbs ordinary
residence-time dependence so it is not misread as memory/policy. At-risk unit = (animal, visit,
epoch); loss = Bernoulli cross-entropy (bits/epoch) + hazard calibration.

**B. Destination choice given a leave (estimand 2).** For each realized departure from origin *o*:
P(next ROI = j | *o*, choice set C(*o*), zₜ) via conditional logit over C(*o*). **C(*o*) =
origin-specific reachable/supported destinations** (training-fold transitions from *o* with ≥ n_min
support; layout adjacency as fallback). Unit = each departure; loss = categorical cross-entropy over
C(*o*) (bits) + **move-conditioned** + **macro-averaged** + calibration.

Bout initiation/termination are supporting definitions for visit segmentation, not action categories.

## Predictor taxonomy (explicit layout is the PRIMARY static representation)

1. **Static opportunity structure — explicit physical layout, not pooled occupancy.** From the
   versioned environment map: ROI id + **resource type** (house/food/water/refuge/tunnel/open-field),
   **adjacency/reachability graph**, choice-set membership, distance-to-edge, and coarse
   (jitter-bounded) inter-ROI / path distances. Animal-independent, non-behavioral.
2. **Dynamic environmental context** — prespecified **low-dimensional** per-decision weather:
   outdoor temperature, **temp−dewpoint gap** (humidity), **rain** (rate/recent), **solar radiation
   (daylight/photoperiod)**, and optionally wind/pressure. **Shelter/microclimate temperature is
   unavailable in-window** (ambient AWN only; CH07/CH08 interior cams post-window) — carried as a
   documented hook, not a variable. **No high-dimensional weather-response; no causal weather claims.**
3. **Historical shared-use structure — an animal-derived BEHAVIORAL increment, NOT environment.**
   Training-fold pooled hazard-by-(ROI,dwell) and origin→destination propensities, **leave-focal-out**.
   Any gain **over the explicit layout** may reflect emergent trails, shared habit, or unmeasured
   affordances — reported as such, never as "environmental."
4. **Current social state** — contemporaneous conspecifics, **strictly pre-decision**.

## Versioned environment map + registration audit (extends existing configs)

- **Versioned map** (`configs/environment_map/*.yaml`, extending `data_manifests/2026-06-29-wiser-pilot.yaml`
  `time_varying_structures` + `configs/wiser_rois.json`), keyed by night/intervention period with
  `valid_from`/`valid_until`: boundary + edge geometry; **houses** (sleep shelters) with entrances/
  doorway sub-ROIs; **food/water** locations + availability (constant in-window unless logged);
  **refuges** 1–4; **tunnel_1** (present 06-28 only, removed 06-29 07:00); **refuge_4 burrow**
  formation (dig ~07-03, removed 07-07) as an emergent physical modification; **known WISER blind /
  high-dropout regions** (refuge_4 below-plane burrow window); emergent trail networks only if
  separately quantified, tagged time-varying (never static geometry).
- **Registration audit (bounds, does not fit a transform).** ROIs are already placed **directly in
  WISER inches (confirmed per-ROI)**, so graph/topology + coarse distances are usable now; the
  physical WISER→field transform is **absent/unverified**. The audit: validate ROI placement against
  ROI-entry clustering, quantify placement + ~7 in jitter uncertainty, and **forbid fine distance
  predictors when that uncertainty is comparable to the behavioral scale**. Fitting a physical
  transform stays deferred (georeference blocker).

## Weather-dependent measurement-process audit (BEFORE any policy modeling)

Quantify whether the **observation process** — not behavior — varies with weather. Using
`add_validity_flags` (gap/low-anchor/valid), `flag_summary`, and `speed_noise_floor`/
`grid_speed_noise_floor`, estimate how **observation probability (validity, dropout)** and
**localization noise (stationary jitter)** vary with **weather × ROI × animal × night**. Hard rule:
**a gap stays "unknown," never coded as staying or leaving.** This audit gates trust in the decision
tables and feeds the measurement-quality terms carried through every model.

## Metrics (unambiguous)

Primary = held-out **cross-entropy in bits/decision**, separately for leaving (Bernoulli) and
destination (categorical): H_model; **Δbits = H_baseline − H_model**; skill = 1 − H_model/H_baseline;
perplexity = 2^H (only that). Not interchangeable; no "McFadden R²." Destination also move-conditioned
+ macro-averaged. Calibration (reliability) for both.

## Cross-validation & inference

- **Outer independent block = whole NIGHT.** ≈8 nights are the outer unit — **not** 40 independent cells.
- **Individual arm — same-animal cross-night personalization** (a state×identity model can't be scored
  by fully holding the animal out): fit pooled on training nights; fit **animal *i*'s personalization
  on *i*'s other training nights only**; score both on a **held-out night for that same animal**;
  **Δbits(i,night)=H_holdout(pooled) − H_holdout(personalized)**. No held-out-night leakage.
- **Inner:** tuning (smoothing, spline dof, n_min) via nested CV on training nights only; layout
  predictors, shared-use fields, choice sets, weather adjustment, and nulls all built **inside the
  training fold**.
- **Same prespecified low-dim weather adjustment** enters shared, personalized, and social models
  identically; individual/social gains are **reported conditional on weather** and unfolded by regime.
- **Inference:** report Δbits **effect size**, its **sign/distribution across held-out nights**,
  whether **dominated by one animal/night**, and calibration; uncertainty via **block bootstrap over
  nights**. No per-fix p-values; no organizing around many p<0.05; no overfragmentation.

## Preserved guardrails

Frame-invariant predictors · jitter-aware thresholds (speed > floor; social ≥ 1 m = 39.37 in) · gaps
unknown/never interpolated · training-fold-only estimation · measurement-regime audit · planted-effect
selftests · IRL gated/likely negative · every derived quantity defined **formula + plain text**
(`/analysis-definitions`).

## Staged design

**Pre-modeling audits (each gates what follows):**
- **A0 — Decision-table validity & support [kill gate].** decisions/animal-night, dwell coverage,
  origin→destination counts, choice-set support, **overlap of comparable states across animals/nights**,
  missingness/dropout near decisions, count of decisions that actually support identity comparison.
- **A1 — Environment map + registration audit.**
- **A2 — Weather / dynamic-environment table + measurement-process audit.**

**Nested predictive models (both processes; each must beat the previous held-out, at night-block level):**
- **M1 — Explicit-layout baseline** (topology, resource type, dwell, clock, regime).
- **M2 — + dynamic environment/weather** (prespecified low-dim).
- **M3 — + historical shared-use field** (training-fold, leave-focal-out; animal-derived increment).
- **Memory check** (M3→M4): history beyond dwell? If essential → observed-state MDP / reward misspecified.
- **M4 — Personalized** (same-animal cross-night) + **matched-choice for symmetric resources**
  (house_1/food_1 ↔ house_2/food_2; refuge pairs; water N/S). GO iff held-out Δbits(M4−M3) positive on
  a majority of held-out (animal,night), consistent sign, not dominated by one animal/night, calibrated,
  survives weather adjustment. Secondary: conditional identity permutation within comparable-state strata.
- **M5 — Pre-decision social-state increment.** Strictly pre-decision features; whole-night holdout;
  GO iff held-out Δbits beats **both** within-night time-shift and day-shuffle, survives weather.

**Post-result audit:** unfold M4/M5 gains by night, early/late, weather regime, dropout burden.

**Gated endpoints:** generative simulation (after positive M4/M5); reward inference (strongly gated,
likely NO-GO — observational equivalence from unobserved odor/temp/food/habituation/social).

## Files

**New:** `src/environment_map.py`, `src/weather_context.py`, `src/semimarkov_decisions.py`,
`src/choice_models.py`; `scripts/build_decision_tables.py` (`cv`),
`scripts/analyze_policy_identifiability.py` (anaconda3), `scripts/selftest_policy_identifiability.py`;
`configs/environment_map/2026-06-28_to_2026-07-05.yaml`; (gated) `scripts/simulate_agents.py`.
Outputs → `outputs/policy_identifiability_2026-06-28_to_2026-07-06/` (git-ignored).

**Reuse:** `trajectory_stereotypy.load_incremental_days`/`add_night_label`/`select_night_window`;
`wiser_analysis_utils` `add_speed`, `add_validity_flags`, `flag_summary`, `apply_tag_cutoffs`,
`assign_roi`/`load_rois`, `roi_time_and_transitions`, `per_tag_transitions`, `movement_bouts`,
`resample_common_grid`/`pairwise_distances`, `grid_speed_noise_floor`, `speed_noise_floor`,
`load_weather`/`load_weather_multi`/`merge_activity_weather`, `distance_to_edge`;
`plotting.load_rat_identities`; `dayshuffle_null`. Extend pooled helpers → training-fold + leave-focal-out.

## Synthetic self-test (all required)

1. Pure topology/shared-use → no individual gain. 2. Stable individual bias transferring across nights
→ M4 GO. 3. Visitation-only pseudo-difference → M4 rejects. 4. Genuine pre-decision social effect
beating time-shift + day-shuffle → M5 GO. 5. Post-decision-leakage social effect → rejected.
6. Nonstationary within-night-only bias → M4 does not certify. 7. Weather-confounded pseudo-individual
effect → rejected after weather adjustment. 8. Dropout-as-departure trap → kept "unknown."
9. Matched-choice symmetric-shelter preference → certified iff transfers across nights.

## Decision table

| Stage | Comparison | Held-out unit | Positive means | Positive does NOT mean | Go/No-go |
|---|---|---|---|---|---|
| A0 | support audit | — | enough comparable cross-night decisions | any effect exists | else stop individual arm |
| A1 | registration audit | — | topology + coarse distances usable | fine metric distances usable | bounds allowed predictors |
| A2 | measurement-process audit | night | obs prob/jitter mapped vs weather | behavior changed | mislabeled dropout blocked |
| M1 | layout vs marginal | night | topology+dwell captured | any individual/social structure | reference model |
| M2 | +weather vs M1 | night | dynamic context predicts | causal weather effect | context adjustment |
| M3 | +shared-use vs M2 | night | animal-derived use adds | environmental structure | describe as behavioral |
| memory | +history vs dwell | night | longer memory matters | reward identifiable | if essential → reward misspecified |
| M4 | personalized vs M3 | held-out night, same animal | stable individual decision structure | trait/causal; within-night fit | GO→M5; else no individual policy |
| M5 | +pre-decision social vs M4 | whole night | social-state predictive increment | causal influence; stable dyads unless pair passes | GO→transfer/sim; else herd/shared-use |
| transfer | unfold by regime/weather | night | effect stable, survives weather | universal/mechanistic | one-night/dropout/weather-driven → downgrade |
| sim | simulated vs held-out macro | night, horizon | generative validity | reward recovered | gate for reward |
| reward | IRL preconditions | — | reward *might* be identifiable | reward *is* identified | almost certainly NO-GO |

## Compute split & staging

Build decision tables + maps + audits in `cv`; fit models/stats in `C:\Users\Cornell\anaconda3\python.exe`
(scipy/sklearn/statsmodels); decouple via parquet. **Phase 1:** A0–A2 + M1–M5 + transfer + reward
verdict → report, STOP, review. **Phase 2:** simulation (gated). **Phase 3:** reward (strongly gated).
Dispatch `wiser-measurement-auditor` before promoting any finding.
