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

## 2026-10-10 — revision 2: L1b (naps vs main sleep) and the rule-(e) selection check

Plan §8, committed (87541f7) before results. `ephys/sleep_lfp.py L1b` (labels from the SWR session's night_sleep_wiser;
selftest adds the continuing-NREM window test). Run 9 min.

- Naps vs main sleep, REM entry, FINAL:
  - nap × P +0.08 %, nap × depth −0.14 %, nap main effect +0.17 %, all CIs covering 0;
  - 175 nap REM entries (94 strict), 6/6 → #69 (no difference detected; naps are all dark).
- Rule (e) on future windows entirely NREM: FINAL MSE −7.6 % but the sign holds in only 4/6; pass2med +0.2 % → #68
  goes down to Candidate (partly composition).
- Wording (main session, after astra's review): #65 and #67 scoped to this depth measure and window.

## 2026-10-10 — revision 3: L2(b) (theta before the first REM, evening rounds vs natural evening wakes)

Plan §9, committed (a9eb109) before results. `ephys/sleep_lfp.py L2b` (`record_series`, `theta_series`,
`first_rem_events`; selftest adds the event rules). Inputs: the `load_sw` cache (th), the theta session's per-second
cache (`theta_seconds`), part H's house entries. Run < 1 min.

- Pre-registered pass: not met on either scoring, and uninformative — the REM-like th share is at its floor
  (0.0–0.5 % of NREM seconds, near-structural: the scorer calls high-th seconds REM).
- Secondary: z-th +0.19 / +0.25 SD before the first post-round REM; CA1 REM-like theta +4.7 / +3.2 points (5/5, 4/5).
- Post hoc (after the first results): without the last 2 min +0.21 / +0.25 (5/6, 4/6); clock-matched 19–24 h
  +0.17 / +0.29; CA1 on IMU-still seconds +1.8 / +2.0 points (about half of the excess is in head-moving seconds);
  the final-minute rise is not larger.
- → #70 (Candidate): a lighter, theta-richer, partly restless NREM before the first post-round REM, not a late REM
  label; #60's evidence updated.

