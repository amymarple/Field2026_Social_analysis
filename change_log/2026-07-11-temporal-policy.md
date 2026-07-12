# Change log — Temporal policy test + clean-run artifact fix

**Date:** 2026-07-11
**Status:** ⚠️ candidate. Two parts: (A) fixed the report/JSON artifact inconsistency so the technical
report matches the clean hysteretic run; (B) tested whether the site-leaving *rule* varies across
hour-of-night / across nights. Reads the **clean hysteretic decision unit only** — never the
superseded raw run.
**Summary:** [`outputs/policy_identifiability_.../TEMPORAL_POLICY_SUMMARY.md`]
**Supersedes/extends:** [2026-07-10-decision-unit-hysteretic-social](2026-07-10-decision-unit-hysteretic-social.md)

## A. Artifact inconsistency fixed (provenance)

The main-dir `policy_identifiability_report.md` + `results.json` still held the **superseded raw
point-in-ROI** run (contaminated social NO-GO) while `SCIENTIFIC_SUMMARY.md` reflected the clean
hysteretic rerun. Fixed:
- Promoted the clean `grid/buf14_exit30_ep15/` decision tables to the main dir; **regenerated
  `policy_identifiability_report.md` + `results.json`** from them.
- Added an explicit **provenance block** (`config_id=hysteretic_buf14_exit30_ep15`,
  `decision_unit=hysteretic_roi_state`, n_leave=43,273, n_dep=2,511, `generated_utc`, `n_perm`) — all
  A0/M1–M5/nulls/verdicts now correspond to ONE run.
- Folded the **day-shuffle null (z 28.6)** and **jitter-safe social increment (Δbits 0.0118)** into the
  M5 section of the analyzer (`choice_models.day_shuffle_social_null`, `SOCIAL_SAFE`), so the GO gate
  now requires surviving time-shift **and** day-shuffle **and** the jitter-safe features.
- Preserved the raw run under `superseded_raw_pointinroi/` (README: do not cite).
- **Reward-feasibility gate note:** on the clean unit the gate mechanically flips to GO (a transferable
  social policy now exists). This means IRL preconditions are met, **not** that a reward is identified;
  the recommended endpoint remains the **interpretable time-invariant hierarchical semi-Markov hazard
  model** (social effect is group-level + modest ~4% skill; IRL adds no identifiable content).

## B. Time-varying-rule test — clean NEGATIVE

**Question:** after conditioning on ROI, dwell, layout, weather/regime, measurement quality, and
current group-social state, does the state→departure mapping change across hour-of-night / across
nights? (A marginal-behavior change by hour is NOT a policy change — only a conditional-rule change
within comparable states.) New `src/temporal_policy.py` + `scripts/analyze_temporal_policy.py`.
`clock_hour` is stored in UTC → converted to local (−4 h) before blocking (bug caught + fixed in
build: the "early" dusk block was initially empty).

Nested leaving-hazard models (whole nights held out):
- **M0** pooled (hour MAIN effect only) → **M1** hour-varying slopes (hour-block × {social, dwell,
  major-ROI}, ridge partial pooling). **Held-out Δbits = −0.0004** (frac+nights 0.50); **hour-label
  permutation null z 0.73** → the conditional rule does NOT vary by hour.
- **M2** night-slope variance (in-sample — a held-out night's slope is unobservable): per-night social
  effect **SD 0.0025 vs night-label null 0.0022, z 0.51** → no night-to-night conditional drift.
- **M3** structured context (held-out testable): habituation −0.0018, phase +0.0014, wet +0.0001,
  fireworks +0.0003, burrow +0.0006 — all ≈0 → night differences are not structured adaptation.
- **M4** hour×context **NOT RUN** (gate unmet: M1 ≈0).
- **Sensitivity** across buf7/buf14/buf21: hour-varying Δbits −0.0007/−0.0004/−0.0004 → robust.
- **Night-dominance:** the near-zero gain is not driven by fireworks/wet/truncated/burrow or any one
  animal (`temporal_night_dominance.csv`).

**Effect direction (the retained social finding):** crowding **suppresses leaving in all blocks**
(n_within_1m coef −0.56 early / −1.01 mid / −1.17 late — huddle cohesion), consistent sign, no
cancellation; somewhat stronger in-sample in deep-rest hours but the variation does not transfer.

**Answers to the 5 questions:** (1) social increment spread through the night, consistent
suppress-leaving sign; (2) hourly structure does NOT repeat across nights; (3) night differences are
neither habituation nor unstable drift — just marginal state occupancy; (4) no individual×time
structure indicated (individual already negligible); (5) **one shared time-invariant rule + changing
state occupancy**, not a time-varying group-social policy.

## Verification

- `selftest_temporal_policy.py` **PASS**: planted transferable hour-varying rule → certified (held-out
  Δbits 0.018, hour-label z 159); planted marginal-only state difference (same rule, different crowding
  by hour) → correctly NOT called a policy change (Δbits −0.0002). So the real-data negative is a
  trustworthy null, not a detection failure.
- `selftest_policy_identifiability.py` still 13/13.

## Caveats (candidate)

`--fast` permutations (re-run full for pub-grade z); movement-proxy outcome; unverified inch frame;
3-block hour resolution (finer not justified by support); single 8-night pilot. The endpoint remains
the interpretable time-invariant hierarchical semi-Markov hazard model; do NOT run IRL.
