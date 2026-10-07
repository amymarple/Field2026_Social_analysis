# NREM → REM transitions and recent sleep history, v2 (2026-10-07)

Plan: [implementation_plan/2026-10-06-sleep-rem-cycle-history.md](../implementation_plan/2026-10-06-sleep-rem-cycle-history.md),
revision 2. v1: [2026-10-06-sleep-rem-cycle-history.md](2026-10-06-sleep-rem-cycle-history.md), kept as the record.
Report: [results/2026c/ephys_spikes/reports/ephys_spikes_sleep_cycles_v2_final_2026c.md](../results/2026c/ephys_spikes/reports/ephys_spikes_sleep_cycles_v2_final_2026c.md).
Claim audit: [ephys_spikes_sleep_cycles_v2_claim_audit_2026c.md](../results/2026c/ephys_spikes/reports/ephys_spikes_sleep_cycles_v2_claim_audit_2026c.md).

## What changed from v1 (the user's review of v1)

- **States:** the FINAL scores (`imu_remclean` + SF07 09-05 from `pass2med_remclean`;
  [2026-10-07-sleep-fixed-thresholds.md](2026-10-07-sleep-fixed-thresholds.md)).
- **24 h main analysis.** Light / dark is a stratum; the light-only fit is kept as sensitivity.
- **Continuous records.** Sessions ≤ 60 s apart are joined (28 joins, 670 s marked unknown); real gaps end a record.
  Nothing is assumed about a gap's state.
- **History without a REM anchor.** Wake / NREM fractions in the last 10 / 60 / 180 min with their completeness, plus a
  `has_anchor` indicator.
  - 19 406 steps without a REM anchor (sleep after a long wake / after a gap) are now in the model; v1 dropped them.
- **Time.** Two-harmonic phase + experiment time since release (spline), instead of the integer day.
- **Validation.**
  - Main: leave out one of 22 day-half blocks; the battery rounds end every record, so no cycle or history crosses a fold.
  - Secondary: forward chaining.
- New `ephys/sleep_cycles_v2.py` (`--selftest` 14 checks PASS). Bulk:
  `D:/Field2026_analysis_out/2026c/sleep_cycles_v2_final_<ts>/`.

## Data

- 129 records; 4488 cycles (4448 complete).
- 185 869 model steps (151 256 light, 34 613 dark).
- Events: 3933 → REM (231 in the dark phase), 7686 → Wake.

## Results (held out; Δ = change in log-loss vs M0, relative to M0's 0.2661 nats / step; CI = bootstrap over blocks)

| Comparison | Relative | 95 % CI | Blocks better |
|---|---|---|---|
| M1 vs M0, 24 h | **−1.99 %** | [−2.35, −1.58] | 22/22 |
| M2 vs M1 (history × phase) | +0.07 % | [−0.14, +0.38] | 13/22 |
| M0 + anchor terms (REM_pre, N_prior, W_cum, has_anchor) | −1.24 % | | 22/22 |
| M0 + windows (10/60/180 min) | −1.00 % | | 19/22 |
| M0 + W_cum (+ has_anchor) | −1.15 % | | 22/22 |
| M0 + N_prior (+ has_anchor) | −0.43 % | | 19/22 |
| M0 + REM_pre (+ has_anchor) | −0.31 % | [−0.67, −0.08] | 18/22 |
| M1 vs M0, light steps only | −2.08 % | | 18/22 |
| M1 vs M0, night steps only | −0.49 % | [−1.36, +0.58] | 9/13 |
| M1 vs M0, forward chaining | −1.85 % | | 15/16 |

**Direction** (full fit, M1, REM vs stay, per SD; SEs cluster-robust by block):

| Term | Coefficient | Per-animal sign |
|---|---|---|
| Wake since the last REM | **−0.65** | negative in 6/6 |
| `has_anchor` | +0.62 | — |
| Previous REM length (conditional on the windows) | +0.13 | positive in 6/6 |
| NREM since the last REM | ≈ 0 | — |

- **`has_anchor`:** before the first REM of a record, REM is less likely, i.e. no REM at the start of a sleep bout after a
  long wake.
- **NREM since the last REM** ≈ 0 because the windows absorb it.
- **Windows** (compositional; the fractions sum to 1 with REM):
  - more REM in the last 10 min → REM less likely (a short refractory period);
  - more REM in the last 3 h → REM more likely (REM clusters over hours).
- **M2 interactions.** In the full fit, REM_pre × phase, W_cum × phase and fW60 × phase have p < 0.05, but they add
  **nothing out of sample** (M2 vs M1 above).

## Reading (technical; statuses in the claim audit)

- **History predicts.** Recent sleep history predicts the next NREM → REM / Wake transition: about 2 % held out, in every
  held-out day-half, and forward in time.
  - Wake since the last REM is the strongest single term.
  - REM is unlikely right after REM and at the start of sleep after a long wake, and clusters over hours.
- **No time-of-day dependence.** No evidence that the history dependence changes with time of day (24 h, held out). The
  in-sample interaction terms do not replicate out of sample.
- **The night alone is underpowered:** 231 REM entries, CI includes 0.
- **No trade-off.** Nothing here shows "one stage longer → the other shorter"; the descriptive relations are as in v1.
- **Sensitivity still open:** no joining across the 28 file splits. Per-session thresholds differ at a join, but the
  joins hold only 670 s.
- **Sensitivity done: v2 on `imu_remclean` without the SF07 09-05 substitution.** That run (tag `remclean`) was stopped
  after its held-out comparison, before the coefficients, so it has no report. Its
  `…sleep_cycles_v2_remclean_{cv,model_comparison}_2026c.csv` show M1 vs M0 −1.98 % (22 blocks) and M2 vs M1 +0.03 %
  (12/22): the same as the final scores.

## Verification

- `python ephys/sleep_cycles_v2.py --selftest` (14 checks), `python ephys/sleep_cycles.py --selftest` (12) PASS.
- Folds: whole day-half blocks; no record crosses a block (the battery rounds end records).
- The agent did not judge the figures.
