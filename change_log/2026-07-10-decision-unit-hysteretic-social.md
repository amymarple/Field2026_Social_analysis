# Change log — Decision-unit fix (hysteretic ROI state) reverses the social verdict

**Date:** 2026-07-10
**Status:** ⚠️ candidate. **Supersedes the INVALIDATED M4/M5 verdicts of
[2026-07-09-agent-policy-identifiability](2026-07-09-agent-policy-identifiability.md).** The
decision unit was rebuilt jitter-tolerant; the identifiability ladder was re-run across a
preregistered grid. Headline: a **robust real-time social effect on leaving decisions** that the
earlier jitter-flicker decision unit had FALSELY reported as NO-GO.

## Why (the invalidation)

The raw point-in-ROI segmentation shredded rest into **jitter-flicker micro-visits** (50% of visits
= one 5-s epoch; median named dwell 5.6 s; **57% of "departures" were self-returns** with an 8.8-s
median excursion — a rat wobbling across a house edge at the ~7-in jitter floor; house_1 alone =
5,267 "visits"/16.6 h; only 10% of the night attributed to any shelter). So the leaving hazard and
destination targets were dominated by **unpredictable measurement flicker**, invalidating (not merely
weakening) the individual/social NO-GO. Post-hoc diagnostics surfaced this; neither the selftest
(clean synthetic ROI membership) nor the measurement auditor (regime/provenance, not segmentation)
caught it.

## What was built

- **`semimarkov_decisions.hysteretic_visits`** — jitter-tolerant ROI-state visits, reusing the
  shelter-state machinery (`wiser_analysis_utils._hysteresis_state` + buffered `_rect_membership`,
  generalized to circles): per-ROI buffered NEAR/FAR/UNCERTAIN evidence → hysteresis (enter after
  sustained NEAR, exit only after sustained FAR, uncertain/dropout HOLD) → combined ROI state →
  visits. **Food folded into its house** (food_i ⊂ house_i). Flicker-vs-genuine-loop merge: a
  same-ROI return is merged only when the excursion is short AND stayed near the boundary AND
  established no other ROI — a long/far/other-ROI excursion is preserved as a genuine leave-and-return.
- **`scripts/diagnose_decision_unit.py`** — preregistered grid (buffer {1,2,3}× jitter × sustained-
  exit {10,30,60}s) with decision-unit health metrics (visit-duration by ROI type, occupancy, 1-epoch
  fraction, self-return frequency + excursion, gap-ended fraction, genuine transitions, animal-night
  support). Does NOT fit a model — establishes the state is behavioral before the ladder.
- **`scripts/build_ladder_grid.py`** + **`scripts/aggregate_ladder_grid.py`** — build decision tables
  under the chosen grid (one load, segment N ways, leave-table per epoch) and run the ladder across
  all configs, reporting verdict robustness (not a cherry-picked threshold).
- **`scripts/check_social_robustness.py`** — day-shuffle null + jitter-floor-safe feature test for
  the emergent social effect.
- Selftest: added planted **boundary-flicker → one visit** and **genuine leave-return loop →
  preserved** scenarios (13/13 PASS).

## Decision-unit diagnostics (8 nights) — the state is now behavioral

| representation | shelter dwell med | self-return frac | frac visit <5 s | occupancy (h / % of 328 rat-h) |
|---|---|---|---|---|
| RAW point-in-ROI | 5.8 s | 0.88 | 0.45 | 34 / 10% |
| hyst buf14 exit30 | 55 s | 0.33 | **0.00** | 183 / 56% |
| hyst buf21 exit60 | 75 s | 0.20 | **0.00** | 229 / 70% |

The **segmentation** (not a coarse bin) removes the flicker: 1-epoch-visit fraction → 0 even at the
finest 5-s epoch, so the hazard bin stays fine (5–15 s). Residual self-returns are now genuine
excursion-and-return loops (median excursion ≥30 s at exit30). buffer=2× jitter (14 in) is the
principled center. `buf21` (3×) begins to over-claim occupancy.

## Ladder re-run across the grid (buffer{7,14,21}×exit{30,60}@ep15 + buf14_exit30@ep{5,15,30})

Robust across ALL 8 configs (`grid/grid_ladder_summary.csv`):
- **Environment + dwell (M1):** skill **0.13–0.26** (real, robust).
- **Weather ≈0, animal-derived shared-use ≈0, observed-state Markov-sufficient** (all robust).
- **Individual policy — statistically detectable but NEGLIGIBLE.** Same-animal cross-night
  personalization: conditional-permutation **z 2.0–9.1** (above the env-matched null in 7/8 configs),
  positive on 63–88% of held nights — **but magnitude only ~0.001 bits/decision** (below the GO
  threshold). Identity leaves a stable but trivially small trace.
- **Social influence — ROBUST GO (reversed).** Strictly pre-decision **group** social state predicts
  leaving: Δbits **~0.012 (~4% skill)**, positive on **all 8 nights**, **GO in all 8 configs**,
  time-shift null **z 11–32**. On the representative config it also survives the harder **day-shuffle
  null (z ~30)** and, critically, the **jitter-floor-safe feature set** (drop sub-floor `nn_dist_in`,
  keep 1 m-radius neighbor count + mean distance) gives the **same effect with a higher z** — so it is
  **not** a sub-floor pseudo-proximity artifact and **not** shared circadian arousal. It is
  **identity-agnostic real-time group coupling** (a rat's leave/stay decision depends on the current
  crowding of conspecifics), consistent with the prior "herd, not dyads" but now a **positive**
  decision-level result. The flicker-contaminated unit had FALSELY reported this NO-GO.

## Interpretation / next model

The eventual generative model is an **environment + dwell + real-time group-social semi-Markov choice
model** (no individual-reward personalization — the individual term is negligible; no dyadic term — the
social effect is group-level). Reward inference (IRL) remains gated and, given the small effect sizes
and non-stationarity, is still not indicated; the interpretable choice model is the endpoint.

## Verification

- Selftest 13/13 PASS (incl. flicker→one-visit, genuine-loop→preserved). Diagnostics grid + ladder
  grid ran clean on all 8 nights. Social GO stress-tested with day-shuffle + jitter-safe features.

## Caveats (candidate)

- `--fast` permutations for the grid (day-shuffle/time-shift used 25–30) — re-run at full budget
  before publication-grade z; the direction is robust across 8 configs × 8 nights.
- Social effect is **group-level, identity-agnostic** — pair-resolved (who responds to whom) is a
  follow-up. Effect size is modest (~0.012 bits / ~4% skill), though highly consistent.
- Inch frame unverified (topology + coarse distances only); occupancy % assumes the night window; the
  buffer choice trades occupancy vs self-return (reported across the grid, not cherry-picked).
- Extend to the 11-night window; add per-row `mc_run_id`/measurement_context sidecar (auditor).
