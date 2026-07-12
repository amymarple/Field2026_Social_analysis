# Temporal summary — does the site-leaving rule change across the night / across nights?

*Standalone, current-state (2026-07-11). 5-min read. Clean hysteretic decision unit only
(`hysteretic_buf14_exit30_ep15`, 43,273 leave epochs, 8 nights). Whole nights are the held-out
blocks. All statuses are Candidate — pilot frame/hardware limits.*

## Question

After conditioning on ROI, elapsed dwell, layout, weather/regime, measurement quality, and current
group-social state, does the mapping from state → site-departure probability **change** across
hour-of-night, across nights, or both? A change in *marginal* behavior by hour (different occupancy,
dwell, crowding) is **not** a policy change — only a change in the **conditional rule within
comparable states** counts.

## Headline

**No.** The conditional leaving rule is **time-invariant** on this data: letting the rule vary by
hour-of-night or by night does **not** improve held-out-night prediction. The large hour-to-hour
differences are **state-occupancy changes under one shared rule**, not a time-varying policy. The
selftest confirms the method *would* have certified a genuine hour-varying rule (planted effect: held-
out Δbits 0.018, permutation z 159) and correctly rejects a marginal-only difference — so this is a
trustworthy negative, not a detection failure.

## Direct answers to the five questions

1. **Is the ~0.012-bit social increment spread through the night, concentrated, or sign-changing?**
   **Spread and consistent in sign.** Crowding **suppresses leaving in every block** (n_within_1m
   coefficient −0.56 early / −1.01 mid / −1.17 late — more neighbors → *less* likely to leave, i.e.
   huddle cohesion). It is somewhat stronger in the deep-rest mid/late hours *in-sample*, but does not
   cancel or flip. It is not concentrated in one window.

2. **Does hour-dependent structure repeat across nights?** **No.** Allowing the social/dwell/ROI
   slopes to vary by hour-block gives **held-out Δbits −0.0004** (frac-positive-nights 0.50), and the
   hour-label permutation null (within comparable ROI×dwell×animal strata) gives **z 0.73** — the
   apparent hourly slope differences do not transfer to held-out nights.

3. **Are night differences habituation/context, or unstable drift?** **Neither, meaningfully.** The
   night-to-night spread of the conditional social effect is **not** above a night-label permutation
   null (SD 0.0025 vs 0.0022, **z 0.51**). Replacing arbitrary night identity with structured context
   (habituation trend, early/mid/late phase, wet, fireworks, burrow) adds **≈0 held-out** (max = phase
   +0.0014 bits; habituation is negative −0.0018). Night differences are marginal state occupancy, not
   conditional-rule drift.

4. **Does temporal variation reveal individual differences the pooled model averaged away?** **Not
   indicated.** The individual leaving-policy was already negligible (~0.001 bits) on the pooled clean
   unit, and the hour-varying gain is ≈0, so an identity×time interaction is not warranted here.

5. **Time-varying group-social choice model, or one shared rule + changing state occupancy?** **One
   shared rule.** A **time-INVARIANT** environment + dwell + group-social hazard is sufficient; adding
   time-variation does not improve out-of-sample prediction.

## Robustness

- **Sensitivity:** the negative held-out hour-varying gain holds across the segmentation grid
  (buf7/buf14/buf21: Δbits −0.0007 / −0.0004 / −0.0004; best structured-context ≈0 in all).
- **Night-dominance:** the (near-zero) hour gain is not created or destroyed by any single night
  (fireworks 07-04, wet nights, truncated 07-05, burrow nights) or any single animal
  (`temporal_night_dominance.csv`).
- **Method validity:** the two-scenario selftest (`selftest_temporal_policy.py`) certifies a planted
  transferable hour-varying rule and rejects a planted marginal-only difference.

## Evidence status

**Candidate — "the conditional site-leaving rule is time-invariant; crowding-suppression is
approximately constant across the night."** Not Established: single 8-night pilot, `--fast`
permutations, movement-proxy outcome, unverified inch frame, 3-block hour resolution (finer resolution
not justified by support). The *direction* (crowding suppresses leaving) is a Candidate biological
reading; the *time-invariance* is a Candidate null result robust to the checks above.

## What this does NOT license

- It does not say the social effect is absent — it is robustly present (see `SCIENTIFIC_SUMMARY.md`),
  just **not time-varying**.
- It does not rule out finer-grained temporal structure a larger dataset might reveal; it says the
  current data give no transferable evidence for it.
- The reward-feasibility *gate* mechanically passes now (a transferable social policy exists), but the
  recommended endpoint remains the **interpretable time-invariant hierarchical semi-Markov hazard
  model** — the social effect is group-level and modest (~4% skill); IRL adds no identifiable content.

## Artifacts

`temporal_model_comparison.csv`, `hour_varying_effects.csv`, `night_varying_effects.csv`,
`temporal_nulls.csv`, `temporal_policy_support.csv`, `temporal_night_dominance.csv`,
`temporal_effects.png`, `temporal_policy_results.json`. Ledger:
`change_log/2026-07-11-temporal-policy.md`. Clean base run:
`policy_identifiability_report.md` (provenance = `hysteretic_buf14_exit30_ep15`).
