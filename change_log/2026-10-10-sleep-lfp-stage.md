# Sleep LFP stage (cohort 2026c) — change log

Plan: [implementation_plan/2026-10-10-sleep-lfp-stage.md](../implementation_plan/2026-10-10-sleep-lfp-stage.md)
(revision 1). Behaviour-stage close: [change_log/2026-10-08-sleep-internal-schedule.md](2026-10-08-sleep-internal-schedule.md)
(part W) and the Fable plateau audit [docs/methods/sleep_plateau_audit_2026-10-10.md](../docs/methods/sleep_plateau_audit_2026-10-10.md).

## 2026-10-10 — revision 1 and L1

**Revision 1 (the user).**
- Depth = the scorer's raw slow-wave slope (`imu_fixch` `SleepScoreRaw.npz` `sw`), already computed. No new site and no
  delta density: delta waves are UP / DOWN states, related to but not the same as depth.
- The theta / delta ratio for L2(b) is the scorer's `th`, with the theta session's CA1 `log_td` as an independent check.
- The scores are not recomputed. L2(c) is on hold until the manual video labels.
- Existing products were checked with the SWR, theta and delta sessions.

**Code.** `ephys/sleep_lfp.py L1 | --selftest`. It reuses `rem_ripple_model.record_arrays / block_tables / depth_z /
pred_job / outcome_split` (the SWR session's code, unchanged); new: the window features, the comparisons, rule (e).
Depth cache: `$OUT_ROOT/2026c/sleep_lfp_inputs/sw_imu_fixch.pkl`. Run 12 min.

**Definitions (headline).** dep = mean z-depth over the NREM seconds in $[t-150, t-30)$ s (≥ 60 s); dep60 = $[t-180,
t-60)$; depc = the same width 1 h earlier (control); dep_fut = $[t+30, t+150)$. Models P, D, P + D, P + D + D × dark on
identical forward-chained steps; Δ held-out log-loss %, total / REM / WAKE.

**Results** (#65–#68; #4 updated):
- P is not a depth proxy: P + D vs D −2.0 % / −1.9 %, 6/6, REM −5 % (#65).
- Depth adds nothing beyond P on FINAL (−0.045 %); on pass2med −0.24 %, mostly waking, on the scoring's own axis (#66).
- The night gate is not depth: the dark coefficient is unchanged, and depth × dark gives no gain (#67).
- The count predicts the coming depth: MSE −3.4 % / −1.0 %, slope negative, 6/6 (#68).

