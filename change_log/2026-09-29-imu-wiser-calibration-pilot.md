# IMU ↔ WISER calibration pilot (cohort 2026c) — 2026-09-29

Plan: [`implementation_plan/2026-09-29-imu-wiser-calibration-pilot.md`](../implementation_plan/2026-09-29-imu-wiser-calibration-pilot.md)
(approved by the user 2026-09-29 after the read-only IMU audit). Report:
[`results/2026c/wiser_baseline/reports/wiser_baseline_imu_calibration_pilot_2026c.md`](../results/2026c/wiser_baseline/reports/wiser_baseline_imu_calibration_pilot_2026c.md)
(full Definitions, tables, figures). Measurement only — no behavioural claim.

## What changed

- **New driver** `wiser/scripts/analyze_imu_wiser_calibration.py` (`--cohort`, `--imu-root`, `--output`,
  `--selftest`). Base Python (pandas, numpy, scipy, matplotlib); reuses `add_speed`, `add_validity_flags`,
  `rest_mask`, `_rect_membership`, `wiser_io._connect_readonly`, `common/output_paths` (via the wiser shim) and
  `common/cohorts`; parses `IMU_STILL_THR` from `ephys/imu_lfp_state_check.py` (no copy); raw-lane layout from
  `ephys/read_imu.py`. No existing analysis file was modified.
- **New config** `wiser/configs/imu_wiser_calibration_2026c.json`: sessions, windows, the WISER DB copy (+ expected
  sha256 prefix), masks, the accuracy report's reference numbers, the tag-table discrepancy. A new cohort = a copy
  of this file + a re-run.
- **Outputs.** Bulk `D:\Field2026_analysis_out\2026c\imu_wiser_calibration_pilot_20260929_1232\` (per-second tables
  with every mask column, bouts, M4 windows, M1 curves and bootstrap, `summary.json`, `input_provenance.json` with
  sha256 of every input, `run_manifest.json`, figure copies). In-repo: the report, three figures
  `results/2026c/wiser_baseline/figures/wiser_baseline_imu_calibration_pilot_{m1_lag,m2_m3_scatter_speed,m4_turns}_2026c.png`,
  and the pointer `run_manifest_imu_calibration_pilot_2026c.json`. The folder's `run_manifest.json` belongs to the
  accuracy report and was **not** overwritten (`write_run_manifest` has a fixed file name — a convention gap when two
  reports share a direction folder).

## Inputs and QC

- Night 2026-09-08 20:00 → 09-09 06:00 (regime B), SF07/SF08/SF09/SF10/SF12, tags 3079/3062/3077/306b/3059. Events:
  SF11 dropped implant with tag 3058 in the CH07 box 09-07 06:12–08:12 (fixed-tag reference); SF07 at a paddock corner
  09-09 22:33–23:06 (behaviour log).
- IMU = make_imu `.imu.npz` (50 Hz, full-precision `t_pc_ms`), read only **after** the 09-29 regeneration by commit
  `6451d6c` (frozen flag, `invalid` after `imu_valid_until`, integer `t_pc_ms`) had finished for these sessions. WISER =
  `3rdcohort_Spike_2026_3_4.sqlite` working copy, `mode=ro` + `query_only`, sha256 `82ccadfde589…` (matches the
  accuracy report).
- **Mask per second** (dropped if any): < 40 samples, saturated, make_imu `frozen`, the audit's derived frozen rule,
  `invalid`, NaN, > 50 % Fusion-unreliable, handling window, all-tag silence ± 2 min, outside tag validity. Removed on
  the night: 443–992 s per animal of 36,000 (saturated 106–312 s, unreliable 377–890 s); frozen, invalid, handling,
  silence and tag validity removed **nothing** on this night.
- **Frozen rule verified** on the two known freezes from the raw lanes (± 10-min probes, raw → 100 Hz → |ω|, VeDBA as in
  make_imu): SF12 `14_20260902_191103.245` flag 09-02 19:39:36 → 09-03 00:22:17 (16,962 s), rule onset 19:39:37;
  SF07 `9_20260906_194035.495` flag 07:56:37 → 08:06:07 (570 s), rule 07:56:38 → 08:06:06 — both within 1–3 s of the
  expected times. Hits on the pilot night: 0 (flag) / 0 (rule) for all five animals. On the regenerated files the
  derived rule cannot fire inside a freeze (blanked to NaN), so the flag is the primary QC.

## Headline definitions (full set in the report)

- **Effective lag** $\tau^\*=\arg\max_{\tau\in[-3,3]}\mathrm{corr}\big(\log_{10}(\overline{\mathrm{VeDBA}}_{0.25s}+0.01),\ v_W(t+\tau)\big)$,
  step 0.05 s; $v_W$ = `add_speed` smoothed speed of valid fixes; 95 % CI from a 300-s block bootstrap (1000
  replicates). + = WISER later than the IMU. Includes WISER latency and head-vs-body kinematics, not only clock offset.
- **IMU-still second** $\mathrm{VeDBA}_{1s}<\theta_a$ (per-animal `IMU_STILL_THR`, 0.307–0.387 m/s²) and
  $|\omega|_{1s}<10$ °/s, QC-ok; **bout** = run ≥ 60 s.
- **Radial deviation** $r_i=\lVert\mathbf p_i-\operatorname{median}_B\mathbf p\rVert$ over the fixes of an IMU-still
  bout (aligned by τ*, trimmed 1 s each end, ≥ 30 fixes); p50/p90/RMSE in inches (precision, not accuracy).
- **Speed floor** $F_q=Q_q(v_i)$ over valid fixes inside IMU-still bouts.
- **Heading change** $\Delta\psi_W=\sum_{k=1}^{2}\operatorname{atan2}(\mathbf d_k\times\mathbf d_{k+1},\mathbf d_k\cdot\mathbf d_{k+1})$
  over three successive aligned 1-s-median displacements (path ≥ 30 in), vs $\Delta\psi_I=\int\omega\cdot\hat{\mathbf u}\,dt$
  over the matching 2 s. + = WISER +x → +y, and + = counter-clockwise from above for the IMU (assuming the gyro reports
  right-hand-rule rates about the accelerometer's axes — undocumented chip).
- **Rest agreement** $\kappa=(p_o-p_e)/(1-p_e)$ of $\mathrm{rest}_W$ (majority of a second's fixes below 10.24 in/s,
  library `rest_mask`) vs IMU-still.

## Results and verdicts (pre-registered criteria)

| Metric | Result | Verdict |
|---|---|---|
| M1 lag | τ* +0.20/+0.15/+0.10/+0.20/+0.15 s (SF07/08/09/10/12), CI widths 0.05–0.10 s, spread 0.10 s; median +0.15 s | **PASS** |
| M2 jitter floor | IMU-selected p50/p90/RMSE **2.39/5.95/4.98 in** (1-s medians 1.54/4.02/3.73); 89 bouts (house 60, outside 29); −33/−27/−15 % vs 3.57/8.19/5.87 | **PASS**; selector-bias flag **raised — WISER-selected numbers are the higher ones** |
| M3 speed floor | p95/p99 **4.97/8.11 in/s** in IMU-still bouts (all still seconds p99 9.07) vs 6.23/10.24 | reported |
| M4 handedness | Spearman ρ +0.32/+0.17/+0.28/+0.26/+0.25 (all p ≤ 1e-5; y-mirror flips every sign); sign agreement 65–71 %; scale brackets contain 1 | **INCONCLUSIVE** (only SF07 reaches \|ρ\| ≥ 0.3 and 70 %) |
| M5 rest agreement | κ 0.01–0.02; sensitivity 82–83 %, specificity 23–27 %; rest_W true in 74–78 % of night seconds, IMU-still in 7–13 % | reported |

- **M2 direction.** The IMU-selected scatter is also below the WISER-selected ≥ 60-s night pauses (4.48–4.60 /
  10.87 in) and below the WISER-selected rest bouts at every `anchors_used` (9 anchors: 2.21/5.07 vs 3.3/7.1 in); no
  trend with bout duration (post hoc: 60–120 s 2.41/5.85, 120–300 s 2.39/6.01 in). Likeliest reading: the WISER-side
  selector (8-in radius) admits real small movements, so the published WISER precision is conservative. Category:
  mixed (a still head can ride a moving body; WISER's own at-rest filtering is unknown).
- **Fixed-tag reference.** Raw-IMU stillness of the dropped implant: 6,884 of 7,200 s still (95.6 %); 116 short
  non-still runs (largest 06:28–06:30, VeDBA_1s up to 4.2 m/s² — jostled in the huddle). WISER 3058 over IMU-still runs:
  4.30/12.18/8.10 in (whole window 5.30/13.81/9.20, matching the accuracy report's 5.26/13.77/9.19). Only 39 % of its
  fixes used 9 anchors (on-head tags 71 %), so it is a worst-case in-house placement, not the on-animal floor.
- **SF07 corner event.** WISER holds the tag in place until 23:01; over 22:33–23:01 the head is still in 1,014 of
  1,655 QC-ok s and vigorously active for 76 s from 22:58:11 (VeDBA ≈ 3.1 m/s², |ω| ≈ 194 °/s) while WISER does not
  move — WISER-"motionless" is not head-still (the M5 construct gap).

## Deviations from the approved text (decided before the results) and post-hoc additions

1. Implant stillness from the **raw** `analogin.dat` (read-only), because the regenerated files blank SF11 after
   06:10 (`invalid`); coordinator instruction 2026-09-29.
2. make_imu's `frozen` flag is primary; the audit's derived rule is a cross-check (verified on raw, see above).
3. Named run pointer instead of `run_manifest.json` (see Outputs).
4. **Post hoc, labelled in the report, no verdict uses them:** the M2 bout-duration table and the reference rows
   (WISER-selected night pauses, per-anchor rest bouts), added after the first run to read the flag's direction; the
   SF07 event's WISER-stationary span summary. No threshold was changed after seeing results.

## Other findings

- **Tag-table discrepancy (not affecting this night):** `wiser/configs/rat_identities_2026c.csv` puts tag 3059 on
  SF12 from 08-30 19:00; the accuracy report's first 3059 fix is 08-31 06:36.
- The M1 same-bins rule keeps ~40 % of the night's 0.25-s bins: 14–15 % of night time lies in inter-fix intervals
  > 1 s (normal cadence pauses) and ~9,300 fixes per tag have no `add_speed` value (no neighbour within ± 0.5 s).

## Verification

- `python wiser/scripts/analyze_imu_wiser_calibration.py --selftest` → **PASS** (synthetic: freeze found at
  1000.02–1020.0 s and masked with a handling window; lag +0.8 s recovered as +0.70 s, CI [+0.65, +0.90] — 10-seed
  check: mean error −0.03 s; Rayleigh jitter p50/p90/RMSE within 1 %; M4 ρ +0.97 and −0.97 after mirroring, scale
  bracket [0.98, 1.03]; κ 0.89).
- Full run `--cohort 2026c`: 41–47 s (target < 15 min); deterministic (seeded bootstrap; two consecutive runs gave
  identical `summary.json` apart from the runtime field).

## Rerun

```powershell
python wiser\scripts\analyze_imu_wiser_calibration.py --cohort 2026c
python wiser\scripts\analyze_imu_wiser_calibration.py --selftest
```

## Next (not done)

- M4 needs either a video event with a known turn direction or a stronger test (longer windows, daytime runs) —
  a new plan, since the criteria here are fixed.
- M5 on daytime rest (the main rest period) before `rest_mask` is used as a rest/sleep measure for cohort 3.
- `analyses/registry.yaml` has no card for this question yet.
