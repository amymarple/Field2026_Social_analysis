# Change log — Agent-policy identifiability (hierarchical semi-Markov, Phase 1)

**Date:** 2026-07-09 (run 2026-07-10)
**Status:** ⚠️ candidate — **but the M4/M5 identifiability verdicts below are INVALIDATED (2026-07-10)
by decision-unit contamination; see the banner.** The framework, audits (A0–A2), and the nested
layout/weather/shared-use comparison stand; the individual/social NO-GO must be re-tested on a
jitter-tolerant decision unit before it can be believed.
**Plan:** [implementation_plan/2026-07-09-agent-policy-identifiability.md](../implementation_plan/2026-07-09-agent-policy-identifiability.md)

> ## ⛔ INVALIDATION (2026-07-10): the decision unit was jitter-flicker, not behavior
> Post-hoc diagnostics on the built tables showed the raw point-in-ROI segmentation shreds real
> occupancy into spurious micro-visits: **50% of visits are a single 5-s epoch, median named-ROI dwell
> 5.6 s, and ~57% of all 6,715 "departures" are self-returns** (leave ROI → re-enter the SAME ROI),
> with a **median inter-visit excursion of 8.8 s (55% < 10 s, 85% < 30 s)** — i.e. a rat resting at a
> house edge wobbling across the boundary at the ~7 in jitter floor (house_1 alone = 5,267 "visits"
> totaling 16.6 h). The leaving hazard and destination choice are therefore dominated by **measurement
> flicker, which is unpredictable by construction**, so the **individual (M4) and social (M5) NO-GO
> are NOT a valid test of policy identifiability** — they are INVALIDATED, not merely under-powered.
> Fix in progress: hysteretic, buffer-tolerant ROI-state visits (reusing `wiser_shelter_state` /
> `_hysteresis_state`) + a preregistered buffer × sustained-exit × epoch sensitivity grid, evaluated on
> decision-unit diagnostics BEFORE the ladder is re-run. The A0–A2 audits, the nested
> marginal→layout→weather→shared-use comparison, and the reward-feasibility *framework* are unaffected;
> only the M4/M5 identifiability numbers are withdrawn.

## Question

Can **identity** and/or **current social state** improve **out-of-night** prediction of two
navigational decisions — *when to leave an ROI* (leaving hazard) and *where to go next* (destination
choice) — **beyond an explicit-layout + dynamic-environment baseline**? Target = **stable conditional
decision structure that transfers across nights**, not coefficients or in-sample fit. 8 nights
(2026-06-28→07-05, 5 rats; Sova removed 06-29 via tag cutoff), whole nights the outer blocks.

## What was built (all new; additive)

- **`src/environment_map.py`** + **`configs/environment_map/2026-06-28_to_2026-07-05.yaml`** — the
  versioned physical layout as the PRIMARY static-opportunity representation (resource types,
  nominally-symmetric groups, intervention calendar incl. tunnel_1 06-28-only and the refuge_4 burrow
  dropout window, registration bounds). Registration is UNVERIFIED (no WISER→field transform) → only
  topology + coarse (≥14 in) distances are used; the food-inside-house co-location is correctly
  flagged unreliable-distance.
- **`src/weather_context.py`** — a PRESPECIFIED low-dim weather vector (temp, temp−dewpoint gap, rain,
  solar/daylight) used identically in every model, plus the weather-dependent measurement-process
  audit (validity/dropout/jitter vs weather×ROI×animal×night). No causal weather claims, no
  high-dimensional weather response.
- **`src/semimarkov_decisions.py`** — visit segmentation → leaving-hazard at-risk epochs (dwell
  mandatory) + destination departures (origin-specific choice sets) + STRICTLY pre-decision social
  features; gaps/below-plane dropout kept 'unknown' (never a departure).
- **`src/choice_models.py`** — penalized logistic hazard + per-origin destination scoring, held-out
  bits/decision + calibration, same-animal cross-night personalization, env-matched conditional
  permutation, social increment + within-night time-shift null, matched-choice.
- Drivers: **`scripts/build_decision_tables.py`** (`cv`) → CSV tables + measurement audit + manifest;
  **`scripts/analyze_policy_identifiability.py`** (anaconda3, scipy/sklearn) → A0–M5 + verdict + report.
- **`scripts/selftest_policy_identifiability.py`** — 11 planted scenarios, PASS.
- Outputs → `outputs/policy_identifiability_2026-06-28_to_2026-07-06/` (git-ignored). Compute split:
  build in `cv`, model in anaconda3, decoupled via CSV (cv lacks scipy/sklearn).

## Key results (candidate — a clean NEGATIVE result)

Decision tables: **21,443 leave epochs, 6,715 departures, 10,562 visits**; individual arm well-powered
(43 multi-animal comparable (roi × dwell) strata).

- **Explicit layout is the workhorse; weather and shared-use add ≈0.** Held-out bits/decision:
  marginal **0.878** → M1 layout+dwell **0.859** (skill **+0.021**) → M2 +weather **0.860**
  (Δbits −0.001) → M3 +shared-use **0.859** (Δbits +0.001). Observed state is **Markov-sufficient**
  (history Δbits −0.001).
- **Individual decision policy: NO-GO.** Same-animal cross-night personalization Δbits median
  **−0.0005** (positive on only **25%** of held nights; not dominated by one animal/night), env-matched
  conditional-permutation **z −0.72**. No identifiable individual leaving-policy beyond the shared
  baseline — the leaving decision is shared, not personal.
- **Social decision policy: NO-GO.** Strictly pre-decision social increment Δbits **≈0**, within-night
  time-shift null **z 0.92**. No social-state predictive increment.
- **Matched-choice: 1/9.** Only **Nox (12386)** shows a stable cross-night *house* preference (0.93 for
  house_1; LONO transfer error 0.05); the other four switch. A lone weak individual signal (cf. the
  prior Dormi occupancy outlier — different animal, different metric), not a general individual policy.
- **Reward-feasibility: NO-GO** (policy does not transfer → the stationarity gate fails). Consistent
  with the honest prior: with a shared-dominated, non-stationary, partially-observed, measurement-
  degraded system, reward collapses to the layout's potential. **Preferred endpoint = the interpretable
  semi-Markov choice model, not IRL.**

**Classification:** *behavioral* (the shared layout+dwell structure is real and transfers); the
individual/social NO-GO is *behavioral lower-bound* (no structure survives cross-night transfer at this
resolution), not a measurement artifact — the measurement audit flags refuge_4/07-04 (burrow night,
jitter ~19 in/s, gap 5%) as the worst stratum but the verdicts do not hinge on it. This **confirms the
prior shared-road / herd-not-dyadic findings at the DECISION level.**

## Definitions (headline; full formula+text list in the report `## Definitions`)

- **Leaving hazard**: $\operatorname{logit}h_i(t)=\beta\cdot z_t+f_r(\tau)$, $h_i(t)=P(\text{leave ROI }r\text{ in }[t,t{+}\Delta)\mid\text{resident})$; $\tau$ = elapsed dwell (mandatory), $\Delta$ = epoch (5 s).
- **Held-out bits** $H=-\frac1N\sum\log_2 p(\text{observed}\mid z)$ (bits/decision); **Δbits** $=H_{\text{base}}-H_{\text{model}}$; **skill** $=1-H_{\text{model}}/H_{\text{base}}$.
- **Personalization gain** $\Delta\text{bits}(i,n)=H_{\text{holdout}}(\text{pooled})-H_{\text{holdout}}(\text{personalized})$; identity part fit only on animal $i$'s TRAINING nights (held-out night excluded).
- **Conditional permutation** (individual null): shuffle identity WITHIN roi strata, $z=(\text{obs}-\mu)/\sigma$. **Time-shift null** (social): circular within-night shift of the pre-decision social features.
- **Matched-choice stable_pref**: cross-night LONO transfer error < 0.15 AND $|\text{pref}-1/|group||>0.15$.

## Verification

- **`selftest_policy_identifiability.py` → PASS (11/11)**: certifies planted individual (transfers) +
  social (beats time-shift) effects; rejects visitation-only pseudo-difference, nonstationary
  within-night-only bias, weather-confounded pseudo-individual (0.152→0.005 bits after adjustment),
  post-decision leakage, dropout-as-departure (gap and shallow-tracked), and the differential-cross-
  night-missingness design-alignment trap.
- Build (2-night smoke + full 8-night) and full analysis run clean; `wiser-measurement-auditor`
  dispatched on the output dir.
- **Adversarial code review (parallel workflow) caught + fixed 4 correctness defects** the selftest
  had missed, all now regression-guarded: (1) numeric missing-indicator columns not aligned between
  train/test in `build_design` (crash or silent coefficient misalignment on nights with different
  social/weather NaN patterns) → thread the missing-column set like `categories`; (2) below-plane
  dropout visit ending in a tracked 'leave' leaked `left=1` (biased refuge_4 hazard) → unconditional
  drop; (3) stationary-jitter proxy selected stillness on the same raw speed it measured (could invert
  the rain-vs-dry ordering) → select on `speed_inps_smooth`; (4) social-grid bins stamped by `min`
  time leaked post-decision positions into the "strictly pre-decision" feature at ~4.4 Hz → stamp by
  bin end.

## Audit (`wiser-measurement-auditor`, read-only)

Report: `outputs/audit/wiser_audit_policy_identifiability_2026-06-28_to_2026-07-06.{md,json}`.
Verdict: **the NO-GOs are NOT artifacts of measurement regime.** The only degraded strata
(valid_frac < 0.7) are the open-field `edge` pseudo-ROI (0.12% of fixes) which **never enters the
decision tables** — decisions come from high-validity shelter ROIs (house valid_frac ~0.98). And the
individual arm's negativity is **driven by the cleanest, highest-support night (07-02, Δbits −0.025)**
while the two weakly-positive nights are the degraded ones (wet 06-30, truncated 07-05) — the opposite
of what a degradation-masked real policy would show. Verified: refuge_4 has **0 leave rows on burrow
nights**; Sova appears **only on 06-28** (cutoff honored); dedup removed 2.24M double-counted rows.
Honest caveats carried by this candidate: (i) run used **`--fast` permutations** (M4 n=20, M5 n=15) →
z's are smoke-level, direction safe but not publication-grade; (ii) **M4 power is thin** (~8
night-blocks) → NO-GO is a **lower bound on effect size**, not exact zero (A0 confirms state coverage,
not statistical power); (iii) **`nn_dist_in` is partly sub-jitter-floor** (52% < 14 in) → conservative
for the current NO-GO, but any *future* social GO driven by it would be a pseudo-proximity artifact;
(iv) provenance is weaker than the CV side — no per-row `mc_run_id` / `measurement_context` sidecar yet.

## Follow-ups

- **Extend to the 11-night window** (06-28→07-08, matching D1/D2/D3) now that 5-rat data closed 07-09
  (Hypnos dropped) — more outer blocks tightens the nulls.
- Run full permutations (currently `--fast`, 20) for the reported z's; add the **day-shuffle** social
  null alongside the time-shift null.
- Upgrade the destination model from per-origin scoring to a **conditional logit** with
  alternative-specific layout features (resource type, coarse distance) for a cleaner M1→M5 on the
  destination process.
- Stages 6–7 (generative simulation, reward inference) remain gated and, on this verdict, are not
  indicated — stop at the interpretable semi-Markov choice model.
